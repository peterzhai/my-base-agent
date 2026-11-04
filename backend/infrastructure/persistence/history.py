"""会话历史读取适配器：按当前权限指纹隔离旧内容。"""

from sqlalchemy import select

from backend.agent.policies.contracts import Principal
from backend.infrastructure.identity.scope import permission_scope
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import Message


def history_for(conversation_id: str, principal: Principal):
    """只读取仍符合当前权限指纹的会话历史，避免旧权限下的文本再次进入模型上下文。

    conversation_id：会话唯一标识
    principal：已由服务端验证的身份"""
    scope = permission_scope(principal)
    with Session() as db:
        messages = list(
            db.scalars(
                select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
            )
        )
    return [
        {"role": m.role, "content": m.content, "payload": m.payload}
        for m in messages
        if m.payload.get("scope") == scope
    ]
