# 持久化模块

## 职责

SQL 引擎、ORM 实体、图检查点、运行事件和授权历史。

## 依赖与公开边界

不负责路由和提示词。会话历史、运行检查点、长期语义记忆是不同概念。

## 阅读顺序与使用说明

database.py → entities.py；events.py 是事件适配，history.py 是历史读取，checkpoints.py 是 LangGraph 存储协议。

## 文件清单

- `__init__.py`
- `checkpoints.py`
- `database.py`
- `entities.py`
- `events.py`
- `history.py`

## 学习要点

通过公开协议或明确入口组合能力，避免跨层访问内部存储。阅读函数注释中的权限、异常、事务和恢复约束；新增实现必须保持这些契约。目录的存在不代表该能力具备自主决策循环。
