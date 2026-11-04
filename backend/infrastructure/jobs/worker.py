"""后台作业处理：通过任务租约领取、续期与有限重试恢复中断任务。只处理文档和索引，不是通用 Agent 调度器。"""

import asyncio
import uuid
from datetime import timedelta

from sqlalchemy import and_, or_, select, update

from backend.capabilities.knowledge import ingest, rebuild_index
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import Document, Job, now


def claim_job() -> tuple[str, str] | None:
    """在事务中领取可执行任务并更新租约。MySQL 行锁与条件更新共同防止重复领取。"""
    owner = str(uuid.uuid4())
    with Session.begin() as db:
        row = db.scalar(
            select(Job)
            .where(or_(Job.status == "queued", and_(Job.status == "running", Job.lease_until < now())))
            .order_by(Job.created_at)
            .with_for_update(skip_locked=True)
        )
        if not row:
            return None
        # Conditional update also supports SQLite development without row locking.
        result = db.execute(
            update(Job)
            .where(
                Job.id == row.id,
                or_(Job.status == "queued", and_(Job.status == "running", Job.lease_until < now())),
            )
            .values(
                status="running",
                lease_owner=owner,
                lease_until=now() + timedelta(seconds=60),
                attempts=Job.attempts + 1,
            )
        )
        return (row.id, owner) if result.rowcount else None


def heartbeat(job_id: str, owner: str, progress: int | None = None):
    """仅允许当前租约持有者续期或更新进度；租约丢失后不允许旧工作者继续宣告成功。

    owner：当前任务租约持有者"""
    with Session.begin() as db:
        values = {"lease_until": now() + timedelta(seconds=60)}
        if progress is not None:
            values["progress"] = progress
        changed = db.execute(
            update(Job)
            .where(Job.id == job_id, Job.lease_owner == owner, Job.status == "running")
            .values(**values)
        )
        if not changed.rowcount:
            raise RuntimeError("任务租约已丢失")


async def process_one() -> bool:
    """执行一项已领取作业，期间独立续租；失败按最大尝试次数重排或转为失败。"""
    claimed = await asyncio.to_thread(claim_job)
    if not claimed:
        return False
    job_id, owner = claimed

    async def renew():
        """在作业执行期间定时续租；父任务结束必须取消该协程。"""
        while True:
            await asyncio.sleep(15)
            await asyncio.to_thread(heartbeat, job_id, owner)

    renewal = asyncio.create_task(renew())
    try:
        with Session() as db:
            job = db.get(Job, job_id)
            kind, payload = job.kind, job.payload
            attempts = job.attempts
        if attempts > 3:
            raise RuntimeError("任务已达到最大重试次数")
        if kind == "ingest":
            await ingest(payload["document_id"], lambda n: heartbeat(job_id, owner, n))
        elif kind == "reindex":
            await asyncio.to_thread(rebuild_index, payload["kb_id"])
        else:
            raise ValueError("未知任务类型")
        with Session.begin() as db:
            job = db.get(Job, job_id)
            if job.lease_owner == owner:
                job.status, job.progress, job.error = "done", 100, ""
    except Exception as exc:
        with Session.begin() as db:
            job = db.get(Job, job_id)
            if job.lease_owner == owner:
                job.status = "queued" if job.attempts < 3 else "failed"
                job.error = str(exc)[:500]
                if job.kind == "ingest":
                    doc = db.get(Document, job.payload["document_id"])
                    if doc:
                        doc.error = job.error
                        if job.status == "failed":
                            doc.status = "failed"
    finally:
        renewal.cancel()
        await asyncio.gather(renewal, return_exceptions=True)
    return True


async def main():
    """持续领取后台任务；没有任务时短暂让出事件循环，避免空转占满 CPU。"""
    while True:
        if not await process_one():
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
