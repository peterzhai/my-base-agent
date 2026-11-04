/** 工作台概览：只聚合可展示的资源数量，不承担业务授权与 Agent 决策。 */
import { ArrowRightOutlined } from "@ant-design/icons";
import { AgentClient } from "@factory-agent/chat";
import { Button, Card, Statistic } from "antd";
import { useEffect, useState } from "react";

export function Overview({
  client,
  go,
}: {
  client: AgentClient;
  go: (s: string) => void;
}) {
  const [counts, setCounts] = useState([0, 0, 0, 0]);
  useEffect(() => {
    Promise.all(
      ["knowledge-bases", "topics", "agents", "models"].map((k) =>
        client.json(`/admin/records/${k}`),
      ),
    )
      .then((items) => setCounts(items.map((x) => x.length)))
      .catch(() => {});
  }, [client]);
  return (
    <>
      <div className="hero">
        <div className="eyebrow">FACTORY INTELLIGENCE / WORKSPACE</div>
        <h1>
          让知识与数据，
          <br />
          成为工作中的答案。
        </h1>
        <p>连接系统文档和业务数据库，为每个部门提供有依据的智能问答。</p>
        <Button type="primary" size="large" onClick={() => go("chat")}>
          开始问答调试 <ArrowRightOutlined />
        </Button>
        <div className="hero-orbit" aria-hidden="true">
          <div />
          <div />
          <span>✦</span>
        </div>
      </div>
      <div className="stats-grid">
        {["知识库", "业务主题", "Agent", "模型服务"].map((label, i) => (
          <Card key={label}>
            <Statistic title={label} value={counts[i]} />
            <span className="muted tiny">已配置资源</span>
          </Card>
        ))}
      </div>
      <div className="overview-grid">
        <Card
          title="从这里开始"
          extra={<span className="muted tiny">配置 → 验证 → 接入</span>}
        >
          {[
            {
              title: "01 / 整理知识资料",
              text: "按部门授权知识库，上传操作手册与规范。",
              key: "knowledge-bases",
            },
            {
              title: "02 / 定义业务主题",
              text: "明确字段、关联、统计口径及部门权限。",
              key: "topics",
            },
            {
              title: "03 / 接入业务系统",
              text: "映射宿主身份，嵌入独立 React 聊天组件。",
              key: "identity-maps",
            },
          ].map((item) => (
            <button
              className="start-row"
              key={item.key}
              onClick={() => go(item.key)}
            >
              <span>
                <strong>{item.title}</strong>
                <small>{item.text}</small>
              </span>
              <ArrowRightOutlined />
            </button>
          ))}
        </Card>
        <Card title="执行路径">
          <div className="flow-node">提问与会话上下文</div>
          <div className="flow-line">↓</div>
          <div className="flow-node accent">感知 · 意图识别与路由</div>
          <div className="flow-line">↙　　↘</div>
          <div className="flow-split">
            <span>知识检索 / RAG</span>
            <span>受控数据查询</span>
          </div>
          <div className="flow-line">↓</div>
          <div className="flow-node">回答 · 来源引用 · 数据表格</div>
          <p className="muted tiny">身份、权限和执行预算贯穿全流程</p>
        </Card>
      </div>
    </>
  );
}
