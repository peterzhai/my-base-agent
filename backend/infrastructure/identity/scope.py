"""权限指纹策略：可见资源及文档变化使旧运行不可复用。"""

import hashlib
import json

from sqlalchemy import select

from backend.agent.policies.contracts import Principal
from backend.infrastructure.identity.security import authorized_records
from backend.infrastructure.persistence.database import Session


def permission_scope(principal: Principal) -> str:
    """计算当前用户可见资源及文档版本的指纹。用于使旧回答和检查点在撤权后失效；不是身份令牌。

    principal：已由服务端验证的身份"""
    resources = []
    kb_ids = []
    for kind in ["knowledge-bases", "topics", "datasources", "agents"]:
        records = authorized_records(kind, principal)
        resources.extend((kind, r.id, r.version) for r in records)
        if kind == "knowledge-bases":
            kb_ids = [r.id for r in records]
    # Changes to document content invalidate summaries and historical evidence, too.
    from backend.infrastructure.persistence.entities import Document

    with Session() as db:
        documents = list(
            db.execute(
                select(Document.id, Document.version, Document.status, Document.deleted).where(
                    Document.kb_id.in_(kb_ids), Document.status == "ready", Document.deleted.is_(False)
                )
            )
        )
    payload = [
        principal.user_id,
        principal.department,
        principal.roles,
        principal.permission_version,
        sorted(resources),
        sorted(tuple(x) for x in documents),
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()
