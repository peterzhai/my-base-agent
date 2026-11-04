"""知识检索外观：组合授权范围、向量索引与中文关键词检索。"""

import asyncio

import faiss
import numpy as np
from sqlalchemy import or_, select, text

from backend.agent.policies.contracts import Principal
from backend.capabilities.knowledge.evidence import revalidate_evidence
from backend.capabilities.knowledge.indexing import cached_index
from backend.infrastructure.identity.security import authorized_records
from backend.infrastructure.models.gateway import Gateway
from backend.infrastructure.persistence.database import Session, engine
from backend.infrastructure.persistence.entities import Chunk, Document


class KnowledgeRetriever:
    """授权混合检索外观：组合模型向量、FAISS 缓存与全文检索，隐藏索引细节。"""

    def __init__(self, gateway: Gateway | None = None):
        """通过构造函数保存本对象依赖；优先注入协作者，避免业务方法自行寻找全局资源。

        gateway：通过协议注入的模型访问能力"""
        self.gateway = gateway or Gateway()

    async def search(
        self, query: str, principal: Principal, top_k: int = 6, kb_ids: list[str] | None = None
    ) -> list[dict]:
        """在用户获授权且被 Agent 开放的知识库内检索，再复核来源有效性。

        query：用户检索问题
        principal：已由服务端验证的身份
        top_k：最多返回的证据条数"""
        kbs = authorized_records("knowledge-bases", principal)
        if kb_ids is not None:
            kbs = [kb for kb in kbs if kb.id in kb_ids]
        if not kbs:
            return []
        vector = np.asarray(await self.gateway.embed([query]), dtype=np.float32)
        if vector.ndim != 2 or vector.shape[0] != 1 or not np.isfinite(vector).all():
            raise ValueError("查询向量无效")
        faiss.normalize_L2(vector)
        results = await asyncio.to_thread(self._search_sync, query, vector, kbs, top_k)
        return revalidate_evidence(results, principal)

    def _search_sync(self, query, vector, kbs, top_k):
        """在线程中执行 CPU 检索，合并向量与关键词排名，只加载最终命中的正文。

        query：用户检索问题
        top_k：最多返回的证据条数"""
        faiss.omp_set_num_threads(1)
        scores = {}
        for kb in kbs:
            index, ids = cached_index(kb.id, self.gateway.model_key)
            if index is None:
                continue
            if index.d != vector.shape[1]:
                raise ValueError("向量维度不匹配，请重建知识库")
            distances, positions = index.search(vector, min(top_k * 3, len(ids)))
            for rank, (distance, position) in enumerate(zip(distances[0], positions[0])):
                if position >= 0 and distance > 0.12:
                    scores[ids[position]] = scores.get(ids[position], 0) + 1 / (60 + rank + 1)
            with Session() as db:
                if engine.dialect.name == "mysql":
                    lexical_ids = list(
                        db.execute(
                            text(
                                "SELECT c.id FROM chunks c JOIN documents d ON d.id=c.document_id "
                                "WHERE c.kb_id=:kb AND d.status='ready' AND d.deleted=0 "
                                "AND MATCH(c.content) AGAINST (:q IN NATURAL LANGUAGE MODE) "
                                "ORDER BY MATCH(c.content) AGAINST (:q IN NATURAL LANGUAGE MODE) DESC LIMIT 18"
                            ),
                            {"kb": kb.id, "q": query},
                        ).scalars()
                    )
                else:
                    # Development fallback does not materialize the corpus in every request.
                    tokens = sorted({query[i : i + 2] for i in range(max(1, len(query) - 1))})[:12]
                    lexical_ids = list(
                        db.scalars(
                            select(Chunk.id)
                            .join(Document, Chunk.document_id == Document.id)
                            .where(
                                Chunk.kb_id == kb.id,
                                Document.status == "ready",
                                Document.deleted.is_(False),
                                or_(*(Chunk.content.contains(token) for token in tokens)),
                            )
                            .order_by(Chunk.id)
                            .limit(18)
                        )
                    )
            for rank, ident in enumerate(lexical_ids):
                scores[ident] = scores.get(ident, 0) + 1 / (60 + rank + 1)
        ranked = sorted(scores, key=scores.get, reverse=True)[:top_k]
        with Session() as db:
            rows = list(
                db.execute(
                    select(Chunk, Document)
                    .join(Document, Chunk.document_id == Document.id)
                    .where(Chunk.id.in_(ranked), Document.status == "ready", Document.deleted.is_(False))
                )
            )
            by_id = {chunk.id: (chunk, doc) for chunk, doc in rows}
        return [
            {
                "chunk_id": ident,
                "document_id": by_id[ident][0].document_id,
                "kb_id": by_id[ident][0].kb_id,
                "document": by_id[ident][1].name,
                "location": by_id[ident][0].location,
                "content": by_id[ident][0].content,
                "score": scores[ident],
                "version": by_id[ident][1].version,
            }
            for ident in ranked
            if ident in by_id
        ]
