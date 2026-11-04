"""旧 RAG 兼容入口；公开名称重导出至独立知识模块。"""

from backend.capabilities.knowledge.evidence import revalidate_evidence as revalidate_evidence
from backend.capabilities.knowledge.indexing import active_chunks as active_chunks
from backend.capabilities.knowledge.indexing import cached_index as cached_index
from backend.capabilities.knowledge.indexing import index_directory as index_directory
from backend.capabilities.knowledge.indexing import index_signature as index_signature
from backend.capabilities.knowledge.indexing import rebuild_index as rebuild_index
from backend.capabilities.knowledge.ingestion import ingest as ingest
from backend.capabilities.knowledge.parsing import extract as extract
from backend.capabilities.knowledge.parsing import split_sections as split_sections
from backend.capabilities.knowledge.retrieval import KnowledgeRetriever as KnowledgeRetriever
