"""documents 路由：只组织本领域 HTTP 交互；路径与响应保持兼容。"""

import hashlib
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from backend.api.dependencies import Admin, User
from backend.bootstrap.settings import settings
from backend.infrastructure.identity.security import (
    audit,
    require_resource,
)
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import (
    Audit,
    Chunk,
    Document,
    Job,
)

router = APIRouter()


@router.get("/api/v1/admin/documents")
def list_documents(user: Admin):
    """读取当前领域的资源列表；调用前的认证依赖决定访问边界，列表响应不得包含敏感凭据。

    user：HTTP 层解析出的身份"""
    with Session() as db:
        docs = db.scalars(select(Document).order_by(Document.created_at.desc()).limit(500))
        return [
            {
                "id": d.id,
                "kb_id": d.kb_id,
                "name": d.name,
                "version": d.version,
                "status": d.status,
                "deleted": d.deleted,
                "error": d.error,
                "created_at": d.created_at.isoformat(),
            }
            for d in docs
        ]


@router.post("/api/v1/admin/documents")
async def upload_document(user: Admin, kb_id: Annotated[str, Form()], file: Annotated[UploadFile, File()]):
    """限制文件格式和体积，流式保存原始文件，再创建持久化导入作业；解析不阻塞上传请求。

    user：HTTP 层解析出的身份
    kb_id：知识库标识"""
    require_resource("knowledge-bases", kb_id, user)
    name = Path((file.filename or "").replace("\\", "/")).name[:200]
    suffix = Path(name).suffix.lower()
    if suffix not in (".txt", ".md", ".pdf", ".docx"):
        raise HTTPException(422, "仅支持 TXT、Markdown、文字 PDF 和 DOCX")
    ident = str(uuid.uuid4())
    folder = settings().data_dir / "documents"
    folder.mkdir(exist_ok=True)
    path = folder / (ident + suffix)
    digest, total = hashlib.sha256(), 0
    try:
        with path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > settings().max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "文件超过上传大小限制")
                digest.update(chunk)
                output.write(chunk)
        if not total:
            raise ValueError("文件为空")
        with Session.begin() as db:
            existing = db.scalar(
                select(Document).where(
                    Document.kb_id == kb_id,
                    Document.sha256 == digest.hexdigest(),
                    Document.deleted.is_(False),
                    Document.status.in_(["queued", "ready"]),
                )
            )
            if existing:
                path.unlink(missing_ok=True)
                return {"document_id": existing.id, "duplicate": True}
            versions = list(
                db.scalars(select(Document.version).where(Document.kb_id == kb_id, Document.name == name))
            )
            doc = Document(
                id=ident,
                kb_id=kb_id,
                name=name,
                path=str(path.resolve()),
                sha256=digest.hexdigest(),
                version=max(versions, default=0) + 1,
            )
            job = Job(kind="ingest", payload={"document_id": ident})
            db.add_all([doc, job])
            db.flush()
            job_id = job.id
    except Exception:
        path.unlink(missing_ok=True)
        raise
    audit(user.user_id, "document.uploaded", ident)
    return {"document_id": ident, "job_id": job_id, "duplicate": False}


@router.delete("/api/v1/admin/documents/{ident}")
def delete_document(ident: str, user: Admin):
    """立即标记文档不可见并排队重建索引；授权读取不能等待索引异步清理才生效。

    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    with Session.begin() as db:
        doc = db.get(Document, ident)
        if not doc:
            raise HTTPException(404, "文档不存在")
        doc.deleted = True
        db.add(Job(kind="reindex", payload={"kb_id": doc.kb_id}))
    audit(user.user_id, "document.deleted", ident)
    return {"deleted": True}


@router.post("/api/v1/admin/jobs/{ident}/retry")
def retry_job(ident: str, user: Admin):
    """只重新排队失败且关联资料仍有效的作业，防止重试已删除文档。

    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    with Session.begin() as db:
        job = db.get(Job, ident)
        if not job or job.status != "failed":
            raise HTTPException(409, "仅失败任务可以重试")
        job.status, job.attempts, job.error = "queued", 0, ""
        if job.kind == "ingest":
            doc = db.get(Document, job.payload["document_id"])
            if doc.deleted:
                raise HTTPException(409, "文档已删除")
            doc.status = "queued"
    return {"queued": True}


@router.post("/api/v1/admin/knowledge-bases/{ident}/reindex")
def reindex(ident: str, user: Admin):
    """创建知识库索引重建任务，不在 HTTP 请求线程执行整库向量计算。

    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    require_resource("knowledge-bases", ident, user)
    with Session.begin() as db:
        job = Job(kind="reindex", payload={"kb_id": ident})
        db.add(job)
        db.flush()
        return {"job_id": job.id}


@router.get("/api/v1/admin/jobs")
def jobs(user: Admin):
    """返回最近的后台作业状态与进度，便于管理员判断失败与重试。

    user：HTTP 层解析出的身份"""
    with Session() as db:
        return [
            {
                "id": j.id,
                "kind": j.kind,
                "status": j.status,
                "progress": j.progress,
                "attempts": j.attempts,
                "error": j.error,
                "payload": j.payload,
            }
            for j in db.scalars(select(Job).order_by(Job.created_at.desc()).limit(200))
        ]


@router.get("/api/v1/admin/audits")
def audits(user: Admin):
    """返回最近审计记录；仅管理员可访问，不把审计作为公开消息流。

    user：HTTP 层解析出的身份"""
    with Session() as db:
        return [
            {
                "id": r.id,
                "user_id": r.user_id,
                "action": r.action,
                "resource": r.resource,
                "details": r.details,
                "created_at": r.created_at.isoformat(),
            }
            for r in db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(300))
        ]


@router.get("/api/v1/documents/{ident}/original")
def original(ident: str, user: User):
    """读取原文前检查文档状态和知识库授权，不把文件路径当作访问凭证。

    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    with Session() as db:
        doc = db.get(Document, ident)
        if not doc or doc.deleted or doc.status != "ready":
            raise HTTPException(404, "文档不存在")
        require_resource("knowledge-bases", doc.kb_id, user)
        return FileResponse(doc.path, filename=doc.name, headers={"Cache-Control": "no-store"})


@router.get("/api/v1/chunks/{ident}")
def citation(ident: str, user: User):
    """按当前文档版本检查引用，避免删除或替换后的旧片段被直接读取。

    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    with Session() as db:
        chunk = db.get(Chunk, ident)
        doc = db.get(Document, chunk.document_id) if chunk else None
        if not doc or doc.deleted or doc.status != "ready":
            raise HTTPException(404, "引用不存在或已失效")
        require_resource("knowledge-bases", doc.kb_id, user)
        return {
            "content": chunk.content,
            "location": chunk.location,
            "document": doc.name,
            "document_id": doc.id,
        }
