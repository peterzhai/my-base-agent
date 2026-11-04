# 知识 / RAG模块

## 职责

解析、切分、导入、索引、授权检索与证据复核。

## 依赖与公开边界

数据库是权威数据源，FAISS 是派生缓存；只在授权知识库中检索。

## 阅读顺序与使用说明

parsing.py → ingestion.py → indexing.py → retrieval.py → evidence.py；contracts.py 声明 Retriever。公开入口提供明确重导出。

## 文件清单

- `__init__.py`
- `contracts.py`
- `evidence.py`
- `indexing.py`
- `ingestion.py`
- `parsing.py`
- `retrieval.py`

## 学习要点

通过公开协议或明确入口组合能力，避免跨层访问内部存储。阅读函数注释中的权限、异常、事务和恢复约束；新增实现必须保持这些契约。目录的存在不代表该能力具备自主决策循环。
