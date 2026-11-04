"""HTTP 边界请求模型，与领域查询语言独立演进。"""

from typing import Any

from pydantic import BaseModel, Field


class RecordInput(BaseModel):
    """带资源 ID 和乐观版本的管理请求，不接受直接写入 ORM 实体。"""

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=200)
    config: dict[str, Any]
    version: int | None = None


class SendMessage(BaseModel):
    """用户消息请求的长度边界，避免无限制输入占用模型上下文。"""

    content: str = Field(min_length=1, max_length=8000)


class IdentityExchange(BaseModel):
    """宿主后端提交的外部身份，不包含可由客户端伪造的角色字段。"""

    external_id: str = Field(min_length=1, max_length=100)
