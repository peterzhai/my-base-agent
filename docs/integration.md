# React 宿主接入

构建组件后可通过 `npm pack --workspace @factory-agent/chat` 生成离线 tgz 包。支持 React 18/19 和 Ant Design 5；宿主安装相容的 peer dependencies。不要把两份 React 打入同一个页面。

```tsx
import { useCallback } from 'react';
import { ChatLauncher } from '@factory-agent/chat';
import '@factory-agent/chat/style.css';

export function Assistant({ currentUserId }: { currentUserId: string }) {
  const getAccessToken = useCallback(async () => {
    // 此接口属于宿主后端，使用宿主现有登录会话；浏览器不提交角色、部门或用户 ID。
    const response = await fetch('/internal/agent-token', {
      method: 'POST', credentials: 'same-origin',
      // 沿用宿主的 CSRF 防护配置。
    });
    if (!response.ok) throw new Error('请先登录业务系统');
    return (await response.json()).access_token;
  }, []);
  return <ChatLauncher
    identityKey={currentUserId}
    apiBaseUrl="https://agent.factory.internal/api/v1"
    agentId="factory"
    getAccessToken={getAccessToken}
    onError={error => console.error(error.message)}
  />;
}
```

`ChatWindow` 提供固定面板；其父容器应设置明确高度（建议 ≥ 600px）。`ChatLauncher` 提供悬浮按钮。支持 theme、onClose、onError；切换账号时必须改变 identityKey，退出时应卸载组件。新会话和历史会话按 Agent 分开。

宿主后端从已经认证的会话读取外部用户 ID，调用：

```http
POST /api/v1/auth/exchange
X-Service-Key: <仅保存在宿主后端的服务凭据>
Content-Type: application/json

{"external_id":"MES_USER_001"}
```

返回 `access_token`、`expires_in`。平台管理员提前维护 identity-maps，将外部 ID 映射到 users 中的用户，角色和部门来自后者。当前只有一个宿主服务凭据；多宿主接入需后续扩展带 issuer 的凭据和映射命名空间。

浏览器通过 Authorization Bearer 调用 API。SDK 每次请求获取令牌，401 时重新获取并重试一次，宿主可以在 getAccessToken 中按 expires_in 缓存令牌。跨域时在 ALLOWED_ORIGINS 配置宿主的完整 origin；推荐用工厂内部 HTTPS 入口。

SSE 事件类型：status、delta、citations、table、reset、done、error、cancelled。SDK 用 Fetch 读取，断线后按最后事件 ID 重连，done 返回规范化完整结果；reset 清除断电恢复前的部分输出。取消调用 POST /runs/{id}/cancel，关闭组件也会中断请求并尽力取消运行。

`examples/host_server.py` 仅用于开发，模拟两个固定用户。它明确禁止 production 环境运行，不能把其按账号直接领令牌的逻辑复制进生产宿主。

完整接口和请求模型见运行后的 `/docs` 与 `/openapi.json`。所有 ID 使用字母、数字、下划线或短横线；配置更新需要携带 version，过期版本返回 409。
