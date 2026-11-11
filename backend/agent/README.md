# Agent 内核模块

## 职责

管理感知、上下文、执行预算、工具协议、记忆协议和输出。

## 依赖与公开边界

只能依赖 agent 内的协议与值对象及标准/纯类型依赖；不能导入 applications、infrastructure、API。

## 阅读顺序与使用说明

从 policies/contracts.py 的 Principal 和 execution/context.py 的 ExecutionContext 开始。

## 模块清单

- perception、context、execution：感知、上下文装配与执行控制。
- tools、models、memory：工具、模型与记忆协议。
- response、policies：响应组织与权限守卫。

应用组装和业务工作流位于 applications/factory_assistant。

## 学习要点

通过公开协议或明确入口组合能力，避免跨层访问内部存储。阅读函数注释中的权限、异常、事务和恢复约束；新增实现必须保持这些契约。目录的存在不代表该能力具备自主决策循环。
