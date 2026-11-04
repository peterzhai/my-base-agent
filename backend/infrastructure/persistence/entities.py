"""平台持久化模型：配置、会话、知识、运行、任务与审计分别建模。图检查点是恢复状态，不等于长期语义记忆。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.persistence.database import Base


def uid():
    """生成独立资源标识，避免把用户输入作为数据库主键序列。"""
    return str(uuid.uuid4())


def now():
    """生成无时区的 UTC 存储时间；业务日期查询单独按配置时区解释。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Record(Base):
    """Versioned admin configuration, including identity maps; credentials are encrypted."""

    __tablename__ = "records"
    kind: Mapped[str] = mapped_column(String(40), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Conversation(Base):
    """带用户归属的会话元信息；一个会话可含多次运行。"""

    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), default="factory")
    title: Mapped[str] = mapped_column(String(100), default="新会话")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Message(Base):
    """用户或助手消息，载荷保存权限指纹及来源，供安全历史读取。"""

    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Document(Base):
    """原始文档版本与生命周期状态，决定哪些分块可进入检索。"""

    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Chunk(Base):
    """带文档来源、位置和向量模型标识的文本块。"""

    __tablename__ = "chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)
    model_key: Mapped[str] = mapped_column(String(200))
    __table_args__ = (UniqueConstraint("document_id", "ordinal"),)


class Job(Base):
    """可恢复的后台任务：租约用于区分有效工作者，尝试次数限制故障重试。"""

    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Run(Base):
    """一次请求的生命周期记录：会话可以包含多个运行，不能以会话 ID 替代运行 ID。"""

    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    input: Mapped[str] = mapped_column(Text)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class RunEvent(Base):
    """运行事件的有序持久化记录，游标用于 SSE 重连。"""

    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    event: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict] = mapped_column(JSON)


class Audit(Base):
    """管理与执行行为记录，供追溯和用户反馈分析。"""

    __tablename__ = "audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(80))
    resource: Mapped[str] = mapped_column(String(200))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class CheckpointRow(Base):
    """持久化一个图检查点及父定位，不等于业务会话消息。"""

    __tablename__ = "graph_checkpoints"
    thread_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(200), primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    checkpoint: Mapped[bytes] = mapped_column(LargeBinary(length=16777215))
    metadata_blob: Mapped[bytes] = mapped_column(LargeBinary(length=16777215))


class CheckpointWrite(Base):
    """记录检查点中的任务输出，防止恢复时丢失已完成节点结果。"""

    __tablename__ = "graph_writes"
    thread_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(200), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(100))
    value: Mapped[bytes] = mapped_column(LargeBinary(length=16777215))
