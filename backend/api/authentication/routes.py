"""authentication 路由：只组织本领域 HTTP 交互；路径与响应保持兼容。"""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.api.dependencies import User
from backend.api.schemas import IdentityExchange
from backend.bootstrap.settings import settings
from backend.infrastructure.identity.security import (
    audit,
    constant_equal,
    issue_token,
)
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import (
    Record,
)

router = APIRouter()


class AdminLogin(BaseModel):
    """管理员登录请求，仅接收密码，不允许提交任意用户或角色。"""

    password: str = Field(max_length=200)


@router.post("/api/v1/auth/admin-login")
def admin_login(body: AdminLogin):
    """验证部署配置的管理员凭据后签发短期令牌；不在浏览器中保存管理员密码。

    body：经过边界模型校验的请求体"""
    if not constant_equal(body.password, settings().admin_password):
        raise HTTPException(401, "密码错误")
    with Session() as db:
        user = db.get(Record, ("users", "admin"))
        if not user or not user.config.get("enabled", True):
            raise HTTPException(401, "管理员未初始化或已禁用")
        return {"access_token": issue_token(user), "expires_in": settings().token_minutes * 60}


@router.post("/api/v1/auth/exchange")
def exchange(body: IdentityExchange, x_service_key: Annotated[str | None, Header()] = None):
    """仅宿主后端服务凭据可换取令牌；外部身份必须先在平台映射，浏览器不能自行赋予角色。

    body：经过边界模型校验的请求体"""
    if not x_service_key or not constant_equal(x_service_key, settings().service_key):
        raise HTTPException(401, "宿主服务认证失败")
    with Session() as db:
        mapping = next(
            (
                r
                for r in db.scalars(select(Record).where(Record.kind == "identity-maps"))
                if r.config.get("external_id") == body.external_id and r.config.get("enabled", True)
            ),
            None,
        )
        user = db.get(Record, ("users", mapping.config["user_id"])) if mapping else None
        if not user or not user.config.get("enabled", True):
            raise HTTPException(403, "用户尚未授权，请联系管理员映射身份")
        token = issue_token(user)
    audit(user.id, "auth.exchange", mapping.id)
    return {"access_token": token, "expires_in": settings().token_minutes * 60}


@router.get("/api/v1/me")
def me(user: User):
    """返回当前令牌对应的实时身份，供宿主确认账号和部门映射。

    user：HTTP 层解析出的身份"""
    return {
        "id": user.user_id,
        "department": user.department,
        "roles": user.roles,
        "permission_version": user.permission_version,
    }
