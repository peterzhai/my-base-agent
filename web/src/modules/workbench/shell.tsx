/** 管理后台外观：负责登录和页面组合，领域表单与聊天组件均委托给独立组件。 */
import { LogoutOutlined } from "@ant-design/icons";
import { AgentClient, ChatWindow } from "@factory-agent/chat";
import { Alert, Button, Card, Input, Space, Tag, message } from "antd";
import React, { useCallback, useMemo, useState } from "react";

import { sections } from "../configuration/schema";
import { Documents } from "../knowledge";
import { Logs } from "../operations";
import { Overview } from "../overview";
import { Records } from "../configuration";

export function Workbench() {
  const [token, setToken] = useState(
    sessionStorage.getItem("factory-admin-token") ?? "",
  );
  const [section, setSection] = useState("overview");
  const [loggingIn, setLoggingIn] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const getToken = useCallback(async () => token, [token]);
  const client = useMemo(
    () => new AgentClient("/api/v1", getToken),
    [getToken],
  );
  const login = async () => {
    setLoggingIn(true);
    setError("");
    try {
      const response = await fetch("/api/v1/auth/admin-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail);
      sessionStorage.setItem("factory-admin-token", body.access_token);
      setToken(body.access_token);
      setPassword("");
    } catch (e) {
      setError(String(e));
    } finally {
      setLoggingIn(false);
    }
  };
  if (!token)
    return (
      <div className="login-page">
        <div className="login-intro">
          <div className="brand">
            ✦ <span>工厂 Agent</span>
          </div>
          <h1>
            连接知识。
            <br />
            理解业务。
            <br />
            辅助每一次决策。
          </h1>
          <p>运行在内网的智能问答与 Agent 基础平台</p>
        </div>
        <Card className="login-card">
          <Tag color="green">ADMIN WORKSPACE</Tag>
          <h2>登录管理工作台</h2>
          <p className="muted">使用部署时配置的管理员密码</p>
          <Input.Password
            aria-label="管理员密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onPressEnter={login}
            size="large"
            placeholder="管理员密码"
          />
          {error && (
            <Alert type="error" message={error} style={{ marginTop: 12 }} />
          )}
          <Button
            type="primary"
            size="large"
            block
            loading={loggingIn}
            onClick={login}
            style={{ marginTop: 20 }}
          >
            进入工作台 →
          </Button>
          <p className="muted tiny">
            开发默认密码见项目 README；生产环境必须独立配置。
          </p>
        </Card>
      </div>
    );
  const current = sections.find((s) => s.key === section)!;
  return (
    <div className="workspace">
      <aside className="sidebar">
        <div className="brand">
          ✦{" "}
          <span>
            工厂 Agent<small>FOUNDATION / 01</small>
          </span>
        </div>
        <div className="nav-label">工作空间</div>
        <nav>
          {sections.map((s, i) => (
            <React.Fragment key={s.key}>
              {i === 6 && <div className="nav-label">底座与治理</div>}
              <button
                aria-label={s.label}
                className={section === s.key ? "active" : ""}
                onClick={() => setSection(s.key)}
              >
                {s.icon}
                <span>{s.label}</span>
                {section === s.key && <span className="nav-dot" />}
              </button>
            </React.Fragment>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="status-dot" />
          内网部署 · MySQL + FAISS<a href="/demo">查看宿主接入示例 ↗</a>
        </div>
      </aside>
      <div className="main-wrap">
        <header className="topbar">
          <span>
            工作空间 <span className="muted"> / {current.label}</span>
          </span>
          <Space>
            <Tag color="green">受控访问</Tag>
            <Button
              type="text"
              icon={<LogoutOutlined />}
              onClick={() => {
                sessionStorage.removeItem("factory-admin-token");
                setToken("");
              }}
            >
              退出
            </Button>
          </Space>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">AGENT OPERATIONS</div>
              <h2>{current.label}</h2>
            </div>
            <span className="muted tiny">通用底座 / 工厂应用</span>
          </div>
          {section === "overview" ? (
            <Overview client={client} go={setSection} />
          ) : section === "chat" ? (
            <div className="debug-chat">
              <ChatWindow
                identityKey="admin"
                apiBaseUrl="/api/v1"
                getAccessToken={getToken}
                onError={(e) => message.error(e.message)}
              />
            </div>
          ) : section === "documents" ? (
            <Documents client={client} />
          ) : ["jobs", "audits"].includes(section) ? (
            <Logs kind={section} client={client} />
          ) : (
            <Records key={section} kind={section} client={client} />
          )}
        </main>
      </div>
    </div>
  );
}
