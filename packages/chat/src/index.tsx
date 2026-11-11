/** 独立聊天 UI：采用组合把传输客户端、历史选择、消息展示和宿主身份连接起来。
 * identityKey 变化会重建内部实例，防止切换账号后继续展示上个账号的会话。
 * 模型文字以 React 文本渲染，不使用 dangerouslySetInnerHTML，避免引用内容变成脚本。
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  ConfigProvider,
  Drawer,
  Empty,
  Input,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  type ThemeConfig,
} from "antd";
import { AgentClient } from "./client";
import "./style.css";
export { AgentClient } from "./client";

export interface ChatWindowProps {
  apiBaseUrl: string;
  agentId?: string;
  /** Change on logout/account switch. Aborts requests and clears local conversation state. */
  identityKey: string;
  getAccessToken: () => Promise<string>;
  mode?: "panel" | "floating";
  theme?: ThemeConfig;
  onClose?: () => void;
  onError?: (error: Error) => void;
}
interface Message {
  id: string;
  role: string;
  content: string;
  payload?: any;
}

/** 有状态视图：只管理界面与请求生命周期，业务授权由服务端处理。 */
function ChatInner({
  apiBaseUrl,
  agentId = "factory",
  getAccessToken,
  mode = "panel",
  theme,
  onClose,
  onError,
}: ChatWindowProps) {
  const client = useMemo(
    () => new AgentClient(apiBaseUrl, getAccessToken),
    [apiBaseUrl, getAccessToken],
  );
  const [conversations, setConversations] = useState<
    { id: string; title: string }[]
  >([]);
  const [conversation, setConversation] = useState<string>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<any>();
  const controller = useRef<AbortController>();
  const running = useRef<string>();
  const mounted = useRef(true);
  const end = useRef<HTMLDivElement>(null);
  const fail = (value: unknown) => {
    if (!mounted.current) return;
    const err = value instanceof Error ? value : new Error(String(value));
    setError(err.message);
    onError?.(err);
  };
  const refresh = async () => {
    const result = await client.json(
      `/conversations?agent_id=${encodeURIComponent(agentId)}`,
    );
    if (mounted.current) setConversations(result);
  };
  useEffect(() => {
    mounted.current = true;
    refresh().catch(fail);
    return () => {
      mounted.current = false;
      controller.current?.abort();
      if (running.current)
        client
          .json(`/runs/${running.current}/cancel`, { method: "POST" })
          .catch(() => {});
    };
  }, [client, agentId]);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [messages, status]);
  const load = async (id: string) => {
    if (busy) return;
    try {
      const result = await client.json(`/conversations/${id}/messages`);
      setConversation(id);
      setMessages(result);
      setError("");
    } catch (e) {
      fail(e);
    }
  };
  const send = async (question = input) => {
    if (!question.trim() || busy) return;
    setBusy(true);
    setError("");
    setInput("");
    setStatus("正在连接");
    const localId = crypto.randomUUID();
    const abort = new AbortController();
    controller.current = abort;
    const update = (fn: (m: Message) => Message) => {
      if (mounted.current)
        setMessages((prev) => prev.map((m) => (m.id === localId ? fn(m) : m)));
    };
    try {
      let id = conversation;
      if (!id) {
        const created = await client.json("/conversations", {
          method: "POST",
          body: JSON.stringify({ agent_id: agentId }),
          signal: abort.signal,
        });
        id = created.id;
        setConversation(id);
      }
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "user", content: question },
        { id: localId, role: "assistant", content: "", payload: {} },
      ]);
      const result = await client.json(`/conversations/${id}/runs`, {
        method: "POST",
        body: JSON.stringify({ content: question }),
        signal: abort.signal,
      });
      running.current = result.run_id;
      await client.events(
        result.run_id,
        (event) => {
          if (!mounted.current) return;
          if (event.event === "status") {
            setStatus(event.data.message);
            update((m) => ({
              ...m,
              payload: {
                ...m.payload,
                trace: [...(m.payload?.trace ?? []), event.data.message],
              },
            }));
          }
          if (event.event === "reset")
            update((m) => ({ ...m, content: "", payload: {} }));
          if (event.event === "delta")
            update((m) => ({ ...m, content: m.content + event.data.text }));
          if (event.event === "citations")
            update((m) => ({
              ...m,
              payload: { ...m.payload, citations: event.data.items },
            }));
          if (event.event === "table")
            update((m) => ({
              ...m,
              payload: {
                ...m.payload,
                tables: [...(m.payload?.tables ?? []), event.data],
              },
            }));
          if (event.event === "done") {
            const output = event.data.output;
            update((m) => ({
              ...m,
              content: output.answer,
              payload: { ...output, run_id: result.run_id },
            }));
          }
          if (event.event === "error") fail(new Error(event.data.message));
          if (event.event === "cancelled") setStatus("已停止生成");
        },
        abort.signal,
      );
      await refresh();
    } catch (e) {
      if (!abort.signal.aborted) fail(e);
    } finally {
      running.current = undefined;
      if (mounted.current) {
        setBusy(false);
        setStatus("");
      }
    }
  };
  // 取消既通知服务端，又中断本地流；只断开网络不代表远端任务已停止。
  const stop = async () => {
    if (running.current)
      await client
        .json(`/runs/${running.current}/cancel`, { method: "POST" })
        .catch(fail);
    controller.current?.abort();
    setBusy(false);
    setStatus("已停止生成");
  };
  // 引用每次重新走鉴权接口，不把最初检索成功当作永久授权。
  const source = async (id: string) => {
    try {
      setPreview(await client.json(`/chunks/${id}`));
    } catch (e) {
      fail(e);
    }
  };
  // 使用临时 Blob URL 下载并回收，避免长期保留敏感文档对象。
  const original = async () => {
    if (!preview) return;
    try {
      const response = await client.response(
        `/documents/${preview.document_id}/original`,
      );
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = preview.document;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      fail(e);
    }
  };
  return (
    <ConfigProvider
      prefixCls="fa-ant"
      theme={{ token: { colorPrimary: "#176b62", borderRadius: 10 }, ...theme }}
    >
      <section className={`fa-chat fa-chat-${mode}`} aria-label="工厂智能问答">
        <header className="fa-chat-header">
          <div>
            <strong>工厂智能助手</strong>
            <span>知识有出处 · 数据有口径</span>
          </div>
          <Space>
            <Button
              size="small"
              disabled={busy}
              onClick={() => {
                setConversation(undefined);
                setMessages([]);
                setError("");
              }}
            >
              新会话
            </Button>
            {onClose && (
              <Button type="text" onClick={onClose} aria-label="关闭聊天">
                ×
              </Button>
            )}
          </Space>
        </header>
        <div className="fa-chat-toolbar">
          <Select
            aria-label="历史会话"
            placeholder="选择历史会话"
            value={conversation}
            disabled={busy}
            onChange={load}
            options={conversations.map((c) => ({
              label: c.title,
              value: c.id,
            }))}
            style={{ width: "100%" }}
          />
        </div>
        {error && (
          <Alert
            type="error"
            showIcon
            message={error}
            closable
            onClose={() => setError("")}
          />
        )}
        <div className="fa-chat-messages" aria-live="polite">
          {!messages.length && (
            <div className="fa-chat-welcome">
              <Tag color="green">内网工作空间</Tag>
              <h2>你好，有什么可以帮你？</h2>
              <p>查询系统操作知识，或了解你有权访问的业务数据。</p>
              {["MES 如何报工？", "今天产量是多少？", "各物料库存是多少？"].map(
                (q) => (
                  <Button key={q} block onClick={() => send(q)}>
                    {q} ↗
                  </Button>
                ),
              )}
            </div>
          )}
          {messages.map((m) => (
            <article key={m.id} className={`fa-chat-message fa-chat-${m.role}`}>
              <div className="fa-chat-role">
                {m.role === "user" ? "你" : "智能助手"}
              </div>
              {m.payload?.trace?.length > 0 && (
                <details className="fa-chat-trace">
                  <summary>
                    查看模块执行过程（{m.payload.trace.length} 步）
                  </summary>
                  <ol>
                    {m.payload.trace.map((step: string, index: number) => (
                      <li key={index}>{step}</li>
                    ))}
                  </ol>
                </details>
              )}
              <div className="fa-chat-content">
                {m.content || (busy ? <Spin size="small" /> : "本次未生成回答")}
              </div>
              {!!m.payload?.citations?.length && (
                <div className="fa-chat-citations">
                  {m.payload.citations.map((c: any, i: number) => (
                    <Button
                      key={c.chunk_id}
                      size="small"
                      onClick={() => source(c.chunk_id)}
                    >
                      [{i + 1}] {c.document} · {c.location}
                    </Button>
                  ))}
                </div>
              )}
              {m.payload?.tables?.map((t: any, i: number) => (
                <div key={i} className="fa-chat-table">
                  <Typography.Text strong>{t.topic}</Typography.Text>
                  <Table
                    size="small"
                    pagination={{ pageSize: 5 }}
                    scroll={{ x: "max-content" }}
                    columns={t.columns.map((key: string) => ({
                      title: key,
                      dataIndex: key,
                      render: (value: any) => String(value ?? "—"),
                    }))}
                    dataSource={t.rows.map((r: any, j: number) => ({
                      ...r,
                      key: j,
                    }))}
                  />
                  <small>
                    {t.definition} · {t.queried_at}
                    {t.truncated ? " · 结果已截断" : ""}
                  </small>
                </div>
              ))}
              {m.payload?.run_id && (
                <Space size={4}>
                  <Button
                    size="small"
                    type="text"
                    onClick={() =>
                      client
                        .json(`/runs/${m.payload.run_id}/feedback`, {
                          method: "POST",
                          body: JSON.stringify({ rating: 1 }),
                        })
                        .catch(fail)
                    }
                  >
                    有帮助
                  </Button>
                  <Button
                    size="small"
                    type="text"
                    onClick={() =>
                      client
                        .json(`/runs/${m.payload.run_id}/feedback`, {
                          method: "POST",
                          body: JSON.stringify({ rating: -1 }),
                        })
                        .catch(fail)
                    }
                  >
                    需改进
                  </Button>
                </Space>
              )}
            </article>
          ))}
          <div ref={end} />
        </div>
        <footer className="fa-chat-composer">
          <div className="fa-chat-status">
            {busy && <Spin size="small" />} {status}
          </div>
          <Input.TextArea
            aria-label="输入问题"
            placeholder="输入你的问题，Enter 发送，Shift + Enter 换行"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            autoSize={{ minRows: 2, maxRows: 5 }}
            maxLength={8000}
            onPressEnter={(e) => {
              if (!e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                send();
              }
            }}
          />
          <div className="fa-chat-send">
            <small>回答基于授权资料，请核对业务口径</small>
            {busy ? (
              <Button onClick={stop}>停止生成</Button>
            ) : (
              <Button
                type="primary"
                disabled={!input.trim()}
                onClick={() => send()}
              >
                发送 ↑
              </Button>
            )}
          </div>
        </footer>
      </section>
      <Drawer
        title={preview?.document}
        open={!!preview}
        onClose={() => setPreview(undefined)}
        width={520}
      >
        <Tag>{preview?.location}</Tag>
        <p style={{ whiteSpace: "pre-wrap" }}>{preview?.content}</p>
        <Button onClick={original}>下载原文</Button>
      </Drawer>
    </ConfigProvider>
  );
}

/** 固定面板外观：以身份和 Agent 生成 key，明确组件重建边界。 */
export function ChatWindow(props: ChatWindowProps) {
  return (
    <ChatInner
      key={`${props.identityKey}:${props.agentId}:${props.apiBaseUrl}`}
      {...props}
    />
  );
}

/** 悬浮入口：组合 ChatWindow，不复制聊天逻辑。 */
export function ChatLauncher(
  props: Omit<ChatWindowProps, "mode"> & { defaultOpen?: boolean },
) {
  const [open, setOpen] = useState(props.defaultOpen ?? false);
  useEffect(() => setOpen(props.defaultOpen ?? false), [props.identityKey]);
  return open ? (
    <div className="fa-chat-floating-wrap">
      <ChatWindow
        {...props}
        mode="floating"
        onClose={() => {
          setOpen(false);
          props.onClose?.();
        }}
      />
    </div>
  ) : (
    <button
      className="fa-chat-launcher"
      onClick={() => setOpen(true)}
      aria-label="打开智能助手"
    >
      ✦ 智能助手
    </button>
  );
}
