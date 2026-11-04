# 旧服务兼容层模块

## 职责

兼容原 runtime/query/knowledge/jobs 等模块入口。

## 依赖与公开边界

新业务代码不导入此目录。别名或重导出仅保持旧调用方兼容。

## 阅读顺序与使用说明

真正实现位于 applications、capabilities、infrastructure；迁移期不直接删除旧入口。

## 文件清单

- `__init__.py`
- `evaluation.py`
- `jobs.py`
- `knowledge.py`
- `query.py`
- `runtime.py`
- `schemas.py`

## 学习要点

通过公开协议或明确入口组合能力，避免跨层访问内部存储。阅读函数注释中的权限、异常、事务和恢复约束；新增实现必须保持这些契约。目录的存在不代表该能力具备自主决策循环。
