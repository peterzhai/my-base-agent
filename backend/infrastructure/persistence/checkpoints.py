"""SQLAlchemy-backed LangGraph saver; MySQL in production, SQLite in tests."""

import asyncio
import base64
import json
from collections.abc import Sequence

from langgraph.checkpoint.base import WRITES_IDX_MAP, BaseCheckpointSaver, CheckpointTuple
from sqlalchemy import select

from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import CheckpointRow, CheckpointWrite


class SQLCheckpointSaver(BaseCheckpointSaver):
    """LangGraph 存储适配器：实现协议而不改变图的恢复语义。"""

    def pack(self, value):
        """使用框架序列化协议记录类型与二进制载荷，再以 Base64 封装为可存储字节。"""
        kind, payload = self.serde.dumps_typed(value)
        return json.dumps([kind, base64.b64encode(payload).decode()]).encode()

    def unpack(self, value):
        """un使用框架序列化协议记录类型与二进制载荷，再以 Base64 封装为可存储字节。"""
        kind, payload = json.loads(value)
        return self.serde.loads_typed((kind, base64.b64decode(payload)))

    @staticmethod
    def config(thread, ns, ident):
        """构造线程、命名空间与检查点 ID 的定位配置，不读取环境变量。

        ident：资源唯一标识"""
        return {"configurable": {"thread_id": thread, "checkpoint_ns": ns, "checkpoint_id": ident}}

    def get_tuple(self, config):
        """加载指定或最新检查点及其待写入结果，保持父检查点关联，以便恢复执行。

        config：配置或运行定位信息"""
        conf = config["configurable"]
        thread, ns = conf["thread_id"], conf.get("checkpoint_ns", "")
        with Session() as db:
            query = select(CheckpointRow).where(
                CheckpointRow.thread_id == thread, CheckpointRow.namespace == ns
            )
            if conf.get("checkpoint_id"):
                query = query.where(CheckpointRow.checkpoint_id == conf["checkpoint_id"])
            row = db.scalar(query.order_by(CheckpointRow.checkpoint_id.desc()).limit(1))
            if not row:
                return None
            writes = list(
                db.scalars(
                    select(CheckpointWrite)
                    .where(
                        CheckpointWrite.thread_id == thread,
                        CheckpointWrite.namespace == ns,
                        CheckpointWrite.checkpoint_id == row.checkpoint_id,
                    )
                    .order_by(CheckpointWrite.idx)
                )
            )
            return CheckpointTuple(
                self.config(thread, ns, row.checkpoint_id),
                self.unpack(row.checkpoint),
                self.unpack(row.metadata_blob),
                self.config(thread, ns, row.parent_id) if row.parent_id else None,
                [(w.task_id, w.channel, self.unpack(w.value)) for w in writes],
            )

    def list(self, config, *, filter=None, before=None, limit=None):
        """按线程、时间游标和元数据筛选检查点；限制数量发生在过滤之后。

        config：配置或运行定位信息"""
        with Session() as db:
            query = select(CheckpointRow)
            if config:
                conf = config["configurable"]
                query = query.where(
                    CheckpointRow.thread_id == conf["thread_id"],
                    CheckpointRow.namespace == conf.get("checkpoint_ns", ""),
                )
            if before:
                query = query.where(CheckpointRow.checkpoint_id < before["configurable"]["checkpoint_id"])
            rows = list(db.scalars(query.order_by(CheckpointRow.checkpoint_id.desc())))
        count = 0
        for row in rows:
            result = self.get_tuple(self.config(row.thread_id, row.namespace, row.checkpoint_id))
            if filter and any(result.metadata.get(k) != v for k, v in filter.items()):
                continue
            if limit is not None and count >= limit:
                break
            yield result
            count += 1

    def put(self, config, checkpoint, metadata, new_versions):
        """以事务持久化检查点和元信息，返回后续执行需要的检查点定位配置。

        config：配置或运行定位信息"""
        conf = config["configurable"]
        thread, ns = conf["thread_id"], conf.get("checkpoint_ns", "")
        with Session.begin() as db:
            db.merge(
                CheckpointRow(
                    thread_id=thread,
                    namespace=ns,
                    checkpoint_id=checkpoint["id"],
                    parent_id=conf.get("checkpoint_id"),
                    checkpoint=self.pack(checkpoint),
                    metadata_blob=self.pack(metadata),
                )
            )
        return self.config(thread, ns, checkpoint["id"])

    def put_writes(self, config, writes: Sequence, task_id: str, task_path: str = ""):
        """幂等保存节点输出；普通写入不覆盖已存在的同任务序号，特殊通道遵循 LangGraph 协议。

        config：配置或运行定位信息"""
        conf = config["configurable"]
        with Session.begin() as db:
            for i, (channel, value) in enumerate(writes):
                idx = WRITES_IDX_MAP.get(channel, i)
                key = (conf["thread_id"], conf.get("checkpoint_ns", ""), conf["checkpoint_id"], task_id, idx)
                existing = db.get(CheckpointWrite, key)
                if existing and idx >= 0:
                    continue
                db.merge(
                    CheckpointWrite(
                        thread_id=key[0],
                        namespace=key[1],
                        checkpoint_id=key[2],
                        task_id=task_id,
                        idx=idx,
                        channel=channel,
                        value=self.pack(value),
                    )
                )

    def delete_thread(self, thread_id):
        """删除指定领域资源；检查权限和资源状态后才进行持久化，并保留必要审计。"""
        with Session.begin() as db:
            db.query(CheckpointWrite).filter_by(thread_id=thread_id).delete()
            db.query(CheckpointRow).filter_by(thread_id=thread_id).delete()

    async def aget_tuple(self, config):
        """异步适配入口：在线程中复用同步实现，避免阻塞事件循环；保持相同的返回值和异常语义。

        config：配置或运行定位信息"""
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(self, config, **kwargs):
        """a按线程、时间游标和元数据筛选检查点；限制数量发生在过滤之后。

        config：配置或运行定位信息"""
        rows = await asyncio.to_thread(lambda: list(self.list(config, **kwargs)))
        for row in rows:
            yield row

    async def aput(self, config, checkpoint, metadata, new_versions):
        """异步适配入口：在线程中复用同步实现，避免阻塞事件循环；保持相同的返回值和异常语义。

        config：配置或运行定位信息"""
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        """异步适配入口：在线程中复用同步实现，避免阻塞事件循环；保持相同的返回值和异常语义。

        config：配置或运行定位信息"""
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id):
        """将线程删除操作移入工作线程，避免数据库操作阻塞事件循环。"""
        await asyncio.to_thread(self.delete_thread, thread_id)
