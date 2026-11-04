/** 宿主接入示例：从示例后端获取令牌，切换账号时改变 identityKey 以清理旧会话。 */
import { ChatLauncher } from "@factory-agent/chat";
import { Card, Select, Statistic, Tag } from "antd";
import { useCallback, useState } from "react";

export function DemoHost() {
  const [account, setAccount] = useState("host-demo-a");
  const token = useCallback(async () => {
    const result = await fetch(`/host-api/session/${account}`, {
      method: "POST",
    });
    if (!result.ok) throw new Error("请启动示例宿主后端（8001 端口）");
    return (await result.json()).access_token;
  }, [account]);
  return (
    <div className="demo-host">
      <Tag color="gold">合成数据 · 集成示例</Tag>
      <h1>生产管理系统</h1>
      <p>此页面模拟现有 React 系统，右下角的聊天窗口由独立组件包提供。</p>
      <Select
        aria-label="切换示例账号"
        value={account}
        onChange={setAccount}
        options={[
          { value: "host-demo-a", label: "一车间员工" },
          { value: "host-demo-b", label: "二车间员工" },
        ]}
        style={{ width: 200 }}
      />
      <div className="stats-grid">
        <Card>
          <Statistic title="当前班次" value="白班" />
        </Card>
        <Card>
          <Statistic title="系统状态" value="运行中" />
        </Card>
      </div>
      <a href="/">返回管理后台</a>
      <ChatLauncher
        identityKey={account}
        apiBaseUrl="/api/v1"
        getAccessToken={token}
      />
    </div>
  );
}
