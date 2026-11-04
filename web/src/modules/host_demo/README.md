# 宿主接入演示

page.tsx 使用独立 ChatLauncher；切换账号必须改变 identityKey。

公开入口为 `index.ts`。其他模块通过公开组件组合此模块；共享配置有明确的 schema 文件。请求使用 AgentClient 处理令牌与错误；真实身份与授权始终由服务端验证。
