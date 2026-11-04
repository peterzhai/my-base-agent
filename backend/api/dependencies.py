"""HTTP 认证依赖：API 层解析令牌，业务节点只接收 Principal。"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException

from backend.agent.policies.contracts import Principal
from backend.infrastructure.identity.security import (
    principal_from_token,
)

KINDS = {
    "evaluations",
    "knowledge-bases",
    "roles",
    "models",
    "departments",
    "agents",
    "topics",
    "users",
    "datasources",
    "identity-maps",
}


def current_user(authorization: Annotated[str | None, Header()] = None):
    """从 Bearer 头解析令牌并恢复实时身份；无令牌请求在进入业务路由前被拒绝。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "请先登录")
    return principal_from_token(authorization[7:])


User = Annotated[Principal, Depends(current_user)]


def administrator(user: User):
    """叠加管理员访问要求，复用身份解析依赖，避免每个管理接口重复写鉴权。

    user：HTTP 层解析出的身份"""
    if not user.admin:
        raise HTTPException(403, "需要管理员权限")
    return user


Admin = Annotated[Principal, Depends(administrator)]
