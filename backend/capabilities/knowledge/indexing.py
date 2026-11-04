"""索引派生缓存：生命周期、原子切换与并发冷加载集中管理。"""

import hashlib
import json
import os
import threading
import uuid
from collections import OrderedDict
from pathlib import Path

import faiss
import numpy as np
from sqlalchemy import select

from backend.bootstrap.settings import settings
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import Chunk, Document

_index_lock = threading.Lock()
_indexes = OrderedDict()
faiss.omp_set_num_threads(1)


def active_chunks(kb_id: str):
    """读取活跃文档的分块，供索引重建使用；在线热查询不能每次加载整库向量。

    kb_id：知识库标识"""
    with Session() as db:
        return list(
            db.scalars(
                select(Chunk)
                .join(Document, Chunk.document_id == Document.id)
                .where(Chunk.kb_id == kb_id, Document.status == "ready", Document.deleted.is_(False))
            )
        )


def index_directory(kb_id: str) -> Path:
    # kb_id is a validated config identifier; hash anyway to make paths independent of input.
    """使用知识库标识的哈希定位索引目录，避免直接拼接外部输入形成路径。

    kb_id：知识库标识"""
    folder = settings().data_dir / "indexes" / hashlib.sha256(kb_id.encode()).hexdigest()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def index_signature(kb_id: str) -> str:
    """将活跃文档 ID 与版本编码为索引失效依据；文档删除或替换后旧缓存不能继续作为当前知识。

    kb_id：知识库标识"""
    with Session() as db:
        versions = list(
            db.execute(
                select(Document.id, Document.version)
                .where(Document.kb_id == kb_id, Document.status == "ready", Document.deleted.is_(False))
                .order_by(Document.id)
            )
        )
    return hashlib.sha256(json.dumps([tuple(x) for x in versions]).encode()).hexdigest()


def cached_index(kb_id: str, model_key: str):
    """按活跃文档版本复用只读索引。冷加载采用单次构建锁，避免并发请求重复占用整库内存。

    kb_id：知识库标识"""
    signature = index_signature(kb_id)
    key = (kb_id, model_key)
    # Single-flight cold loading: concurrent requests share one read-only FAISS index.
    with _index_lock:
        existing = _indexes.get(key)
        if existing and existing[0] == signature:
            _indexes.move_to_end(key)
            return existing[1], existing[2]
        index = None
        directory = index_directory(kb_id)
        try:
            manifest = json.loads((directory / "manifest.json").read_text())
            if manifest.get("signature") == signature and manifest.get("key") == model_key:
                filename = manifest["file"]
                if Path(filename).name != filename:
                    raise ValueError("无效索引清单")
                index = faiss.read_index(str(directory / filename))
                ids = manifest["ids"]
        except (OSError, ValueError, KeyError, RuntimeError):
            index = None
        if index is None:
            rows = active_chunks(kb_id)
            if not rows:
                return None, []
            if any(row.model_key != model_key for row in rows):
                raise ValueError("知识向量模型已变更，请重新导入资料")
            ids = [row.id for row in rows]
            matrix = np.vstack([np.frombuffer(row.embedding, dtype=np.float32) for row in rows])
            faiss.normalize_L2(matrix)
            index = faiss.IndexFlatIP(matrix.shape[1])
            index.add(matrix)
        _indexes[key] = (signature, index, ids)
        _indexes.move_to_end(key)
        # At most 512 MB of retained indexes, apart from the currently used generation.
        while len(_indexes) > 1 and (
            len(_indexes) > 16
            or sum(entry[1].ntotal * entry[1].d * 4 for entry in _indexes.values()) > 512 * 1024**2
        ):
            _indexes.popitem(last=False)
        return index, ids


def rebuild_index(kb_id: str):
    """从权威向量构建新索引世代，以不可变文件和原子清单切换避免半写入文件被读取。

    kb_id：知识库标识"""
    signature = index_signature(kb_id)
    rows = active_chunks(kb_id)
    directory = index_directory(kb_id)
    with _index_lock:
        if not rows:
            (directory / "manifest.json").write_text(json.dumps({"ids": [], "key": ""}))
            return
        keys = {r.model_key for r in rows}
        if len(keys) != 1:
            raise ValueError("同一知识库的向量模型不一致，请重新导入全部文档")
        matrix = np.vstack([np.frombuffer(r.embedding, dtype=np.float32) for r in rows])
        faiss.normalize_L2(matrix)
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        generation = str(uuid.uuid4()) + ".faiss"
        faiss.write_index(index, str(directory / generation))
        (directory / "manifest.tmp").write_text(
            json.dumps(
                {
                    "ids": [r.id for r in rows],
                    "key": rows[0].model_key,
                    "file": generation,
                    "signature": signature,
                }
            )
        )
        # Immutable index generation + atomic manifest switch is safe across API and worker processes.
        os.replace(directory / "manifest.tmp", directory / "manifest.json")
