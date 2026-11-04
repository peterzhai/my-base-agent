"""知识能力公开入口；延迟导入避免解析器加载时触发整个检索依赖链。"""

from importlib import import_module

_EXPORTS = {
    "KnowledgeRetriever": "retrieval",
    "revalidate_evidence": "evidence",
    "ingest": "ingestion",
    "extract": "parsing",
    "split_sections": "parsing",
    "rebuild_index": "indexing",
    "index_directory": "indexing",
    "cached_index": "indexing",
    "active_chunks": "indexing",
    "index_signature": "indexing",
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    """只加载明确公开的符号；其他名称必须显式导入内部实现。"""
    if name not in _EXPORTS:
        raise AttributeError(name)
    return getattr(import_module(f"{__name__}.{_EXPORTS[name]}"), name)
