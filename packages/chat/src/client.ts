/** 浏览器 API 适配器（Facade）：把认证、错误转换与 SSE 解析封装为稳定接口。
 * 它只负责传输，不负责判断用户角色；同一组件可接入不同宿主的令牌提供者。
 */
/** 服务端持久化事件；id 用于重连游标，事件类型决定载荷形状。 */
export interface StreamEvent {
  id?: number;
  event: string;
  data: any;
}
export type TokenProvider = () => Promise<string>;

/** 通过组合 TokenProvider 复用认证能力，避免继承某个宿主的登录组件。 */
export class AgentClient {
  constructor(
    public base: string,
    public getAccessToken: TokenProvider,
  ) {}
  /** 每次请求读取短期令牌；401 最多重取一次，防止无界重试。
   * FormData 的 boundary 由浏览器生成，不能手工指定 application/json。
   */
  async response(path: string, init: RequestInit = {}): Promise<Response> {
    for (let attempt = 0; attempt < 2; attempt++) {
      const token = await this.getAccessToken();
      const headers = new Headers(init.headers);
      headers.set("Authorization", `Bearer ${token}`);
      if (init.body && !(init.body instanceof FormData))
        headers.set("Content-Type", "application/json");
      const response = await fetch(this.base.replace(/\/$/, "") + path, {
        ...init,
        headers,
      });
      if (response.status === 401 && !attempt) continue;
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : `请求失败（${response.status}）`,
        );
      }
      return response;
    }
    throw new Error("登录已过期");
  }
  /** 在通用响应处理之上解析 JSON，让页面不重复实现认证和错误转换。 */
  async json<T = any>(path: string, init?: RequestInit): Promise<T> {
    return (await this.response(path, init)).json();
  }
  /** 增量解析 SSE：网络包边界不是事件边界，因此使用 buffer 等待空行分隔。
   * 重连从最后游标继续；done 的完整结果覆盖局部增量，reset 清理恢复前内容。
   * 用户取消通过 AbortSignal 传播，不能将主动取消当作可自动重试的故障。
   */
  async events(
    runId: string,
    receive: (event: StreamEvent) => void,
    signal: AbortSignal,
  ) {
    let cursor = 0;
    let terminal = false;
    for (let attempt = 0; attempt < 3 && !terminal; attempt++) {
      try {
        const response = await this.response(
          `/runs/${runId}/events?after=${cursor}`,
          { signal },
        );
        if (!response.body) throw new Error("浏览器不支持流式响应");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        try {
          while (true) {
            const { value, done } = await reader.read();
            buffer += decoder
              .decode(value, { stream: !done })
              .replace(/\r\n/g, "\n");
            let boundary: number;
            while ((boundary = buffer.indexOf("\n\n")) >= 0) {
              const block = buffer.slice(0, boundary);
              buffer = buffer.slice(boundary + 2);
              const event: StreamEvent = { event: "message", data: {} };
              const data: string[] = [];
              for (const line of block.split("\n")) {
                if (line.startsWith("event:"))
                  event.event = line.slice(6).trim();
                if (line.startsWith("id:"))
                  event.id = Number(line.slice(3).trim());
                if (line.startsWith("data:"))
                  data.push(line.slice(5).trimStart());
              }
              if (!data.length) continue;
              event.data = JSON.parse(data.join("\n"));
              if (event.id !== undefined) cursor = event.id;
              receive(event);
              if (["done", "error", "cancelled"].includes(event.event))
                terminal = true;
            }
            if (done || terminal) break;
          }
        } finally {
          await reader.cancel();
        }
        if (!terminal) {
          const run = await this.json(`/runs/${runId}`, { signal });
          if (run.status === "done") {
            receive({ event: "done", data: { output: run.output } });
            terminal = true;
          } else if (["failed", "cancelled"].includes(run.status)) {
            receive({
              event: run.status === "failed" ? "error" : "cancelled",
              data: { message: "运行已结束，请重新提问" },
            });
            terminal = true;
          }
        }
      } catch (error) {
        if (signal.aborted || attempt === 2) throw error;
      }
    }
    if (!terminal && !signal.aborted)
      throw new Error("连接中断，请打开历史会话查看结果");
  }
}
