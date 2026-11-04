"""configuration 路由：只组织本领域 HTTP 交互；路径与响应保持兼容。"""

import json

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.engine import make_url

from backend.api.dependencies import KINDS, Admin, User
from backend.api.schemas import RecordInput
from backend.bootstrap.settings import settings
from backend.capabilities.data_query.schemas import TopicConfig
from backend.infrastructure.identity.security import (
    allowed,
    audit,
    decrypt,
    encrypt,
)
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import (
    Record,
    now,
)

router = APIRouter()


def public_record(row: Record):
    """构造脱敏的配置响应，只暴露是否已设置密钥，不把密文当作可公开数据。"""
    config = {k: v for k, v in row.config.items() if not k.endswith("_encrypted")}
    for key in ["api_key", "url"]:
        if row.config.get(key + "_encrypted"):
            config["has_" + key] = True
    return {
        "id": row.id,
        "name": row.name,
        "config": config,
        "version": row.version,
        "updated_at": row.updated_at.isoformat(),
    }


def validate_config(kind: str, config: dict, existing: dict | None = None):
    """校验管理员配置并加密敏感字段；更新时未提供新密钥则保留已有密文。

    kind：资源类别
    config：配置或运行定位信息"""
    conf = {k: v for k, v in config.items() if not k.startswith("has_") and not k.endswith("_encrypted")}
    for key in ["api_key", "url"]:
        supplied = conf.pop(key, None)
        if supplied:
            conf[key + "_encrypted"] = encrypt(supplied)
        elif existing and existing.get(key + "_encrypted"):
            conf[key + "_encrypted"] = existing[key + "_encrypted"]
    for key in ["roles", "departments", "kb_ids", "topic_ids"]:
        if key in conf and (
            not isinstance(conf[key], list) or not all(isinstance(x, str) for x in conf[key])
        ):
            raise ValueError(f"{key} 必须为字符串数组")
    if kind == "topics":
        conf = TopicConfig.model_validate(conf).model_dump()
        with Session() as db:
            if not db.get(Record, ("datasources", conf["datasource_id"])):
                raise ValueError("数据源不存在")
    if kind == "datasources":
        if "url_encrypted" not in conf:
            raise ValueError("必须设置数据源连接串")
        parsed = make_url(decrypt(conf["url_encrypted"]))
        if parsed.drivername not in ("mysql+pymysql", "sqlite"):
            raise ValueError("首期数据源仅支持 mysql+pymysql")
        if parsed.drivername == "sqlite" and settings().environment == "production":
            raise ValueError("生产环境不支持 SQLite 数据源")
    if kind == "models":
        if conf.get("provider") not in ("mock", "openai-compatible"):
            raise ValueError("模型 provider 无效")
        if conf["provider"] != "mock":
            from urllib.parse import urlparse

            url = urlparse(conf.get("base_url", ""))
            if url.scheme not in ("http", "https") or not url.hostname or url.username:
                raise ValueError("模型服务地址必须是有效 HTTP(S) 地址")
            if not conf.get("chat_model") or not conf.get("embedding_model"):
                raise ValueError("必须设置聊天和向量模型标识")
    if kind == "agents":
        if (
            not 8 <= int(conf.get("max_steps", 24)) <= 100
            or not 10 <= int(conf.get("timeout_seconds", 90)) <= 300
        ):
            raise ValueError("Agent 执行预算无效")
    if kind == "users":
        if not conf.get("department"):
            raise ValueError("必须配置用户部门")
    if kind == "identity-maps":
        if not conf.get("external_id") or not conf.get("user_id"):
            raise ValueError("必须配置宿主用户标识及平台用户")
        with Session() as db:
            if not db.get(Record, ("users", conf["user_id"])):
                raise ValueError("映射用户不存在")
    return conf


@router.get("/api/v1/admin/records/{kind}")
def list_records(kind: str, user: Admin):
    """读取当前领域的资源列表；调用前的认证依赖决定访问边界，列表响应不得包含敏感凭据。

    kind：资源类别
    user：HTTP 层解析出的身份"""
    if kind not in KINDS:
        raise HTTPException(404, "资源类型不存在")
    with Session() as db:
        return [
            public_record(row)
            for row in db.scalars(select(Record).where(Record.kind == kind).order_by(Record.name))
        ]


@router.put("/api/v1/admin/records/{kind}/{ident}")
def save_record(kind: str, ident: str, body: RecordInput, user: Admin):
    """在版本匹配时保存配置，避免旧表单覆盖新配置；安全约束通过后才递增版本。

    kind：资源类别
    ident：资源唯一标识
    body：经过边界模型校验的请求体
    user：HTTP 层解析出的身份"""
    if kind not in KINDS or body.id != ident:
        raise HTTPException(422, "无效资源类型或标识")
    with Session.begin() as db:
        row = db.get(Record, (kind, ident))
        if row and body.version != row.version:
            raise HTTPException(409, "配置已更新，请刷新后重新编辑")
        conf = validate_config(kind, body.config, row.config if row else None)
        if kind == "identity-maps":
            duplicates = [
                r
                for r in db.scalars(select(Record).where(Record.kind == kind, Record.id != ident))
                if r.config.get("external_id") == conf["external_id"]
            ]
            if duplicates:
                raise ValueError("宿主用户映射重复")
        if (
            ident == "admin"
            and kind == "users"
            and (not conf.get("enabled", True) or "admin" not in conf.get("roles", []))
        ):
            raise ValueError("不能禁用引导管理员或移除其管理员角色")
        if row:
            row.config, row.name, row.version, row.updated_at = conf, body.name, row.version + 1, now()
        else:
            row = Record(kind=kind, id=ident, name=body.name, config=conf)
            db.add(row)
        db.flush()
        result = public_record(row)
    audit(user.user_id, f"{kind}.saved", ident, {"version": result["version"]})
    return result


@router.delete("/api/v1/admin/records/{kind}/{ident}")
def delete_record(kind: str, ident: str, user: Admin):
    """删除指定领域资源；检查权限和资源状态后才进行持久化，并保留必要审计。

    kind：资源类别
    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    if kind not in KINDS or (kind == "users" and ident == "admin"):
        raise HTTPException(422, "不允许删除此资源")
    with Session.begin() as db:
        row = db.get(Record, (kind, ident))
        if not row:
            raise HTTPException(404, "资源不存在")
        db.delete(row)
    audit(user.user_id, f"{kind}.deleted", ident)
    return {"deleted": True}


@router.post("/api/v1/admin/models/{ident}/test")
async def test_model(ident: str, user: Admin):
    """验证 model 的行为契约；断言失败表示该路径的约束被破坏。

    ident：资源唯一标识
    user：HTTP 层解析出的身份"""
    from backend.infrastructure.models.gateway import Gateway

    with Session() as db:
        row = db.get(Record, ("models", ident))
        if not row:
            raise HTTPException(404, "模型不存在")
        gateway = Gateway(row.config)
    embeddings = await gateway.embed(["接口测试"])
    answer = await gateway.complete(
        [
            {"role": "system", "content": "输出 JSON"},
            {"role": "user", "content": json.dumps({"task": "route", "question": "你好", "topics": []})},
        ],
        structured=True,
    )
    json.loads(answer)
    streamed = ""
    async for piece in gateway.stream([{"role": "user", "content": json.dumps({"task": "answer"})}]):
        streamed += piece
    return {
        "ok": True,
        "embedding_dimension": len(embeddings[0]),
        "stream_ok": bool(streamed),
        "mock": gateway.mock,
    }


@router.get("/api/v1/agents")
def list_agents(user: User):
    """读取当前领域的资源列表；调用前的认证依赖决定访问边界，列表响应不得包含敏感凭据。

    user：HTTP 层解析出的身份"""
    with Session() as db:
        return [
            {"id": r.id, "name": r.name}
            for r in db.scalars(select(Record).where(Record.kind == "agents"))
            if allowed(user, r.config)
        ]
