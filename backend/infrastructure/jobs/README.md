# 后台任务模块

## 职责

领取持久化任务、续租、有限重试并调用文档与索引能力。

## 依赖与公开边界

只负责后台作业可靠性，不等于通用 Agent 定时调度。

## 阅读顺序与使用说明

worker.py:claim_job/process_one/main；运行命令 python -m backend.infrastructure.jobs.worker。

## 文件清单

- `__init__.py`
- `worker.py`

## 学习要点

通过公开协议或明确入口组合能力，避免跨层访问内部存储。阅读函数注释中的权限、异常、事务和恢复约束；新增实现必须保持这些契约。目录的存在不代表该能力具备自主决策循环。
