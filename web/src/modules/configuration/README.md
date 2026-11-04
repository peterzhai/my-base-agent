# 配置管理

page.tsx 展示配置列表，editor.tsx 处理表单，schema.tsx 保存表单模板与导航元信息；模板不是服务端授权。

公开入口为 `index.ts`。其他模块通过公开组件组合此模块；共享配置有明确的 schema 文件。请求使用 AgentClient 处理令牌与错误；真实身份与授权始终由服务端验证。
