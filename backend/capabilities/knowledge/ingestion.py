"""文档入库流程：批量向量化后以事务切换有效版本。"""

import asyncio
from pathlib import Path

import numpy as np
from sqlalchemy import func, select

from backend.bootstrap.settings import settings
from backend.capabilities.knowledge.indexing import rebuild_index
from backend.capabilities.knowledge.parsing import extract, split_sections
from backend.infrastructure.models.gateway import Gateway
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import Chunk, Document


async def ingest(document_id: str, progress=lambda _: None):
    """将文档解析并批量向量化；写入成功后事务切换活跃版本，避免替换期间旧知识突然不可读。

    document_id：文档标识"""
    with Session() as db:
        doc = db.get(Document, document_id)
        if not doc or doc.deleted:
            return
        path, name, kb_id = Path(doc.path), doc.name, doc.kb_id
    sections = await asyncio.to_thread(extract, path, Path(name).suffix.lower())
    pieces = list(split_sections(sections))
    if not pieces:
        raise ValueError("未提取到文字，扫描件请先转换为文字型文档")
    gateway = Gateway()
    with Session() as db:
        count = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id != document_id))
        if count + len(pieces) > settings().max_chunks:
            raise ValueError("超过文本块容量上限，请清理资料或调整资源后再导入")
    embeddings = []
    for start in range(0, len(pieces), 32):
        batch = await gateway.embed([content for _, content in pieces[start : start + 32]])
        embeddings.extend(batch)
        progress(min(85, int((start + len(batch)) / len(pieces) * 85)))
    matrix = np.asarray(embeddings, dtype=np.float32)
    if matrix.ndim != 2 or not np.isfinite(matrix).all() or (np.linalg.norm(matrix, axis=1) == 0).any():
        raise ValueError("向量模型返回无效向量")
    with Session.begin() as db:
        doc = db.get(Document, document_id)
        if doc.deleted:
            return
        # Single worker processes ingestion; replacements remain readable until this commit.
        db.query(Chunk).filter(Chunk.document_id == document_id).delete()
        for i, ((location, content), vector) in enumerate(zip(pieces, matrix)):
            db.add(
                Chunk(
                    document_id=document_id,
                    kb_id=kb_id,
                    ordinal=i,
                    location=location,
                    content=content,
                    embedding=vector.tobytes(),
                    model_key=gateway.model_key,
                )
            )
        previous = list(
            db.scalars(
                select(Document).where(
                    Document.kb_id == kb_id,
                    Document.name == name,
                    Document.id != document_id,
                    Document.status == "ready",
                    Document.deleted.is_(False),
                )
            )
        )
        for old in previous:
            old.status = "superseded"
        doc.status, doc.error = "ready", ""
    # Database vectors are immediately queryable; index is only a rebuildable acceleration cache.
    await asyncio.to_thread(rebuild_index, kb_id)
    progress(100)
