# 工厂问答应用模块

## 职责

组装感知、知识与数据策略，运行固定 LangGraph 工作流并管理生命周期。

## 依赖与公开边界

工厂专属知识/查数顺序、状态和评测留在本模块；不冒充通用自主 Agent 内核。

## 阅读顺序与使用说明

assembly.py 是组合根；runtime.py 管运行；composition.py 管串并行；state.py 管领域状态；*_workflow.py 管能力适配。

## 文件清单

- `__init__.py`
- `assembly.py`
- `composition.py`
- `data_workflow.py`
- `dependencies.py`
- `evaluation.py`
- `knowledge_workflow.py`
- `runtime.py`
- `state.py`

## 学习要点

通过公开协议或明确入口组合能力，避免跨层访问内部存储。阅读函数注释中的权限、异常、事务和恢复约束；新增实现必须保持这些契约。目录的存在不代表该能力具备自主决策循环。
