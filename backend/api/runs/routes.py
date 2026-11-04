"""runs 路由：只组织本领域 HTTP 交互；路径与响应保持兼容。"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.agent.policies.contracts import Principal
from backend.api.conversations import own_conversation
from backend.api.dependencies import User
from backend.applications.factory_assistant.runtime import active_tasks, permission_scope, start_run
from backend.infrastructure.identity.security import (
    audit,
)
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import (
    Run,
    RunEvent,
)

router = APIRouter()


def own_run(ident: str, user: Principal):
    """检查运行所有者、会话授权与当前权限指纹；猜到运行 ID 不代表有读取权限。

    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    with Session() as db:
        run = db.get(Run, ident)
        if not run or run.user_id != user.user_id:
            raise HTTPException(404, "运行不存在")
        own_conversation(run.conversation_id, user)
        if run.output.get("scope") != permission_scope(user):
            raise HTTPException(403, "权限或资料已变化，请重新提问")
        return run


@router.get("/api/v1/runs/{ident}")
async def get_run(ident: str, user: User):
    """检查归属后返回当前状态；尚未启动的排队任务在事件循环中启动。

    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    run = own_run(ident, user)
    if run.status == "queued":
        start_run(ident)
    return {"id": run.id, "status": run.status, "output": run.output}


@router.get("/api/v1/runs/{ident}/events")
async def stream_events(ident: str, user: User, after: int = Query(0, ge=0)):
    """从持久化事件表按游标读取 SSE，并在流过程中复查权限；终态后关闭连接。

    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    run = own_run(ident, user)
    if run.status == "queued":
        start_run(ident)

    async def stream():
        """按增量读取模型 SSE 文本；已输出内容不能无条件自动重试，否则会重复或拼接错误答案。"""
        cursor = after
        while True:
            try:
                own_run(ident, principal_from_current(user))
            except HTTPException:
                yield 'event: error\ndata: {"message":"权限已变化，请重新登录"}\n\n'
                break
            with Session() as db:
                rows = list(
                    db.scalars(
                        select(RunEvent)
                        .where(RunEvent.run_id == ident, RunEvent.id > cursor)
                        .order_by(RunEvent.id)
                        .limit(100)
                    )
                )
                status = db.get(Run, ident).status
            for row in rows:
                cursor = row.id
                yield f"id: {row.id}\nevent: {row.event}\ndata: {json.dumps(row.data, ensure_ascii=False)}\n\n"
            if status in ("done", "failed", "cancelled") and len(rows) < 100:
                break
            if not rows:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.15)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def principal_from_current(user):
    """根据已有身份版本重新读取用户，流式连接也不能绕过中途撤权。

    user：HTTP 层解析出的身份"""
    from backend.infrastructure.identity.security import principal_for_user

    return principal_for_user(user.user_id, user.permission_version)


@router.post("/api/v1/runs/{ident}/cancel")
async def cancel_run(ident: str, user: User):
    """将取消意图持久化并通知进程内任务；已进入终态的运行不再重复修改结果。

    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    own_run(ident, user)
    with Session.begin() as db:
        run = db.get(Run, ident)
        if run.status in ("done", "failed", "cancelled"):
            return {"status": run.status}
        run.cancelled = True
        if run.status == "queued":
            run.status = "cancelled"
    task = active_tasks.get(ident)
    if task:
        task.cancel()
    return {"status": "cancelled"}


class Feedback(BaseModel):
    """反馈请求：评分有明确范围，备注有长度上限。"""

    rating: int = Field(ge=-1, le=1)
    comment: str = Field(default="", max_length=1000)


@router.post("/api/v1/runs/{ident}/feedback")
def feedback(ident: str, body: Feedback, user: User):
    """记录用户对本人运行结果的评分与备注，后续评测可分析这些审计记录。

    ident：资源唯一标识
    body：经过边界模型校验的请求体
    user：HTTP 层解析出的身份"""
    own_run(ident, user)
    audit(user.user_id, "run.feedback", ident, body.model_dump())
    return {"ok": True}
