"""conversations 路由：只组织本领域 HTTP 交互；路径与响应保持兼容。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.agent.policies.contracts import Principal
from backend.api.dependencies import User
from backend.api.schemas import SendMessage
from backend.applications.factory_assistant.runtime import permission_scope, start_run
from backend.infrastructure.identity.security import (
    require_resource,
)
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import (
    Conversation,
    Message,
    Run,
)

router = APIRouter()


class NewConversation(BaseModel):
    """New带用户归属的会话元信息；一个会话可含多次运行。"""

    agent_id: str = "factory"


@router.post("/api/v1/conversations")
def create_conversation(body: NewConversation, user: User):
    """创建属于当前用户且绑定指定 Agent 的新会话，创建前检查 Agent 可用性。

    body：经过边界模型校验的请求体
    user：HTTP 层解析出的身份"""
    require_resource("agents", body.agent_id, user)
    with Session.begin() as db:
        row = Conversation(user_id=user.user_id, agent_id=body.agent_id)
        db.add(row)
        db.flush()
        return {"id": row.id, "title": row.title}


def own_conversation(ident: str, user: Principal):
    """检查会话归属和当前 Agent 可用性；管理员身份也不自动允许读取其他用户会话。

    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    with Session() as db:
        conv = db.get(Conversation, ident)
        if not conv or conv.user_id != user.user_id:
            raise HTTPException(404, "会话不存在")
        require_resource("agents", conv.agent_id, user)
        return conv


@router.get("/api/v1/conversations")
def list_conversations(user: User, agent_id: str = "factory"):
    """读取当前领域的资源列表；调用前的认证依赖决定访问边界，列表响应不得包含敏感凭据。

    user：HTTP 层解析出的身份"""
    require_resource("agents", agent_id, user)
    with Session() as db:
        return [
            {"id": r.id, "title": r.title}
            for r in db.scalars(
                select(Conversation)
                .where(Conversation.user_id == user.user_id, Conversation.agent_id == agent_id)
                .order_by(Conversation.created_at.desc())
                .limit(100)
            )
        ]


@router.get("/api/v1/conversations/{ident}/messages")
def list_messages(ident: str, user: User):
    """读取当前领域的资源列表；调用前的认证依赖决定访问边界，列表响应不得包含敏感凭据。

    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    own_conversation(ident, user)
    scope = permission_scope(user)
    with Session() as db:
        messages = db.scalars(
            select(Message).where(Message.conversation_id == ident).order_by(Message.created_at)
        )
        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content if m.payload.get("scope") == scope else "权限或资料已变化，请重新提问。",
                "payload": m.payload if m.payload.get("scope") == scope else {},
            }
            for m in messages
        ]


@router.post("/api/v1/conversations/{ident}/runs")
async def create_run(ident: str, body: SendMessage, user: User):
    """保存用户消息与待执行运行，并检查同会话的并发状态；将实际执行交给生命周期服务。

    ident：资源唯一标识
    body：经过边界模型校验的请求体
    user：HTTP 层解析出的身份"""
    own_conversation(ident, user)
    scope = permission_scope(user)
    with Session.begin() as db:
        conv = db.scalar(select(Conversation).where(Conversation.id == ident).with_for_update())
        current = db.scalar(
            select(Run).where(Run.conversation_id == ident, Run.status.in_(["queued", "running"]))
        )
        if current:
            raise HTTPException(409, "当前会话仍在生成中")
        run = Run(conversation_id=ident, user_id=user.user_id, input=body.content, output={"scope": scope})
        db.add(run)
        db.add(Message(conversation_id=ident, role="user", content=body.content, payload={"scope": scope}))
        if conv.title == "新会话":
            conv.title = body.content[:50]
        db.flush()
        run_id = run.id
    start_run(run_id)
    return {"run_id": run_id}
