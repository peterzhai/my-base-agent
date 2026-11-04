"""安全边界：令牌只标识用户，实时权限来自服务端。资源角色和部门取交集；密钥加密存储，授权不能交给大模型决定。"""

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select

from backend.agent.policies.contracts import Principal
from backend.bootstrap.settings import settings
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import Audit, Record


def cipher():
    """构造服务端凭据加解密器，生产必须使用显式密钥，开发回退仅方便本地演示。"""
    key = (
        settings().encryption_key
        or base64.urlsafe_b64encode(hashlib.sha256(settings().jwt_secret.encode()).digest()).decode()
    )
    return Fernet(key)


def encrypt(value: str) -> str:
    """加密需持久化的服务凭据。密文用于存储，不应返回浏览器或记录到审计详情。"""
    return cipher().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """仅在服务端实际访问外部资源时还原凭据；调用者负责不将结果泄漏到日志。"""
    return cipher().decrypt(value.encode()).decode()


def issue_token(user: Record) -> str:
    """生成有期限、受众和签发者约束的短期令牌，只保存身份与权限版本，不信任客户端角色声明。

    user：HTTP 层解析出的身份"""
    return jwt.encode(
        {
            "sub": user.id,
            "ver": user.version,
            "aud": "factory-agent",
            "iss": "agent-foundation",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=settings().token_minutes),
        },
        settings().jwt_secret,
        algorithm="HS256",
    )


def principal_from_token(token: str) -> Principal:
    """验证签名与令牌期限后重新读取服务端用户，权限版本变化会立即使旧令牌失效。

    token：待验证的短期签名令牌"""
    try:
        claims = jwt.decode(
            token,
            settings().jwt_secret,
            algorithms=["HS256"],
            audience="factory-agent",
            issuer="agent-foundation",
        )
        return principal_for_user(claims["sub"], claims["ver"])
    except (jwt.PyJWTError, KeyError):
        raise HTTPException(401, "登录已过期，请重新登录") from None


def principal_for_user(user_id: str, version: int | None = None) -> Principal:
    """根据平台用户配置构造不可变身份对象；禁用用户或过期权限版本不能继续运行。"""
    with Session() as db:
        user = db.get(Record, ("users", user_id))
        if not user or not user.config.get("enabled", True):
            raise HTTPException(401, "用户不可用")
        if version is not None and version != user.version:
            raise HTTPException(401, "用户权限已变化，请刷新登录")
        return Principal(
            user.id, user.config.get("department", ""), tuple(user.config.get("roles", [])), user.version
        )


def allowed(principal: Principal, config: dict) -> bool:
    """按启用状态、角色和部门判断可见性。无 ACL 默认拒绝普通用户，管理员也不能使用停用资源。

    principal：已由服务端验证的身份
    config：配置或运行定位信息"""
    if not config.get("enabled", True):
        return False
    if principal.admin:
        return True
    # Both configured dimensions must match. An empty ACL grants nobody.
    roles, departments = config.get("roles", []), config.get("departments", [])
    if not roles and not departments:
        return False
    return (not roles or bool(set(roles) & set(principal.roles))) and (
        not departments or principal.department in departments
    )


def authorized_records(kind: str, principal: Principal) -> list[Record]:
    """集中筛选可见资源，使感知模块只看到用户被允许选择的能力。

    kind：资源类别
    principal：已由服务端验证的身份"""
    with Session() as db:
        return [
            r for r in db.scalars(select(Record).where(Record.kind == kind)) if allowed(principal, r.config)
        ]


def require_resource(kind: str, ident: str, principal: Principal) -> Record:
    """授权即资源边界：无资源和无权限返回相同的不可见结果，减少资源存在性泄漏。

    kind：资源类别
    ident：资源唯一标识
    principal：已由服务端验证的身份"""
    with Session() as db:
        row = db.get(Record, (kind, ident))
        if not row or not allowed(principal, row.config):
            raise HTTPException(404, "资源不存在或无权访问")
        return row


def constant_equal(a: str, b: str):
    """使用恒定时间比较验证服务凭据，避免普通字符串比较泄漏匹配前缀。"""
    return hmac.compare_digest(a.encode(), b.encode())


def audit(user_id: str, action: str, resource: str, details: dict | None = None):
    """以独立事务写入安全审计，不存储明文服务密钥。"""
    with Session.begin() as db:
        db.add(Audit(user_id=user_id, action=action, resource=resource, details=details or {}))
