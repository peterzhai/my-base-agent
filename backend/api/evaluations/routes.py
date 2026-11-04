"""evaluations 路由：只组织本领域 HTTP 交互；路径与响应保持兼容。"""

from fastapi import APIRouter, HTTPException

from backend.api.dependencies import Admin
from backend.infrastructure.identity.security import (
    audit,
)
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import (
    Record,
)

router = APIRouter()


@router.post("/api/v1/admin/evaluations/{ident}/run")
async def evaluate(ident: str, user: Admin):
    """取得管理员指定评测集并运行评测，审计结构结果而不直接承诺答案正确率。

    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    from backend.applications.factory_assistant.evaluation import run_evaluation

    with Session() as db:
        record = db.get(Record, ("evaluations", ident))
        if not record:
            raise HTTPException(404, "评测集不存在")
        config = record.config
    report = await run_evaluation(config, user)
    audit(user.user_id, "evaluation.completed", ident, report)
    return report
