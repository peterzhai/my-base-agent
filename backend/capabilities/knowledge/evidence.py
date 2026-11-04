"""证据复核：文档删除、更新或撤权后，旧引用不得继续进入模型。"""

from backend.agent.policies.contracts import Principal
from backend.infrastructure.identity.security import allowed
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import Chunk, Document, Record


def revalidate_evidence(evidence: list[dict], principal: Principal) -> list[dict]:
    """重新检查文档、知识库授权和版本；检索完成后发生的撤权同样必须生效。

    evidence：检索出的带版本来源片段
    principal：已由服务端验证的身份"""
    output = []
    with Session() as db:
        for item in evidence:
            doc = db.get(Document, item["document_id"])
            kb = db.get(Record, ("knowledge-bases", item["kb_id"]))
            chunk = db.get(Chunk, item["chunk_id"])
            if (
                doc
                and kb
                and chunk
                and allowed(principal, kb.config)
                and not doc.deleted
                and doc.status == "ready"
                and doc.version == item["version"]
            ):
                output.append(item)
    return output
