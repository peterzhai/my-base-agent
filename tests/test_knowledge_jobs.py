"""回归测试：使用隔离数据验证行为契约；重点覆盖权限、失败和恢复路径，不能连接工厂业务库。"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from backend.infra.db import Session
from backend.infra.models import Document, Job, Record, now
from backend.infra.security import principal_for_user
from backend.services.jobs import claim_job, process_one
from backend.services.knowledge import KnowledgeRetriever, index_directory, ingest, revalidate_evidence


@pytest.mark.asyncio
async def test_rag_citations_and_revocation():
    """验证 rag citations and revocation 的行为契约；断言失败表示该路径的约束被破坏。"""
    user = principal_for_user("demo-a")
    found = await KnowledgeRetriever().search("MES 如何报工", user)
    assert found and "报工" in found[0]["content"]
    with Session.begin() as db:
        kb = db.get(Record, ("knowledge-bases", "manuals"))
        kb.config = {"roles": ["employee"], "departments": ["workshop-b"], "enabled": True}
    assert not revalidate_evidence(found, user)
    assert not await KnowledgeRetriever().search("报工", user)


@pytest.mark.asyncio
async def test_index_can_be_rebuilt_from_database_and_deleted_docs_disappear():
    """验证 index can be rebuilt from database and deleted docs disappear 的行为契约；断言失败表示该路径的约束被破坏。"""
    user = principal_for_user("demo-a")
    directory = index_directory("manuals")
    for path in directory.iterdir():
        path.unlink()
    found = await KnowledgeRetriever().search("报工", user)
    assert found
    with Session.begin() as db:
        db.get(Document, found[0]["document_id"]).deleted = True
    assert not await KnowledgeRetriever().search("报工", user)


@pytest.mark.asyncio
async def test_replacement_is_atomic():
    """验证 replacement is atomic 的行为契约；断言失败表示该路径的约束被破坏。"""
    from backend.config import settings

    path = settings().data_dir / "replacement.md"
    path.write_text("新版报工规范：先核对工单再提交。")
    with Session.begin() as db:
        old = db.scalar(select(Document))
        old_id = old.id
        new = Document(name=old.name, kb_id=old.kb_id, path=str(path), version=2, sha256="replacement")
        db.add(new)
        db.flush()
        new_id = new.id
    assert (await KnowledgeRetriever().search("报工", principal_for_user("demo-a")))[0][
        "document_id"
    ] == old_id
    await ingest(new_id)
    found = await KnowledgeRetriever().search("报工", principal_for_user("demo-a"))
    assert found and all(x["document_id"] == new_id for x in found)


def test_expired_lease_can_be_claimed_once():
    """验证 expired lease can be claimed once 的行为契约；断言失败表示该路径的约束被破坏。"""
    with Session.begin() as db:
        row = Job(
            kind="reindex",
            payload={"kb_id": "manuals"},
            status="running",
            lease_until=now() - timedelta(seconds=1),
            lease_owner="dead",
            attempts=1,
        )
        db.add(row)
        db.flush()
        job_id = row.id
    claimed = claim_job()
    assert claimed and claimed[0] == job_id and claimed[1] != "dead"
    assert claim_job() is None


@pytest.mark.asyncio
async def test_bad_document_retries_then_fails():
    """验证 bad document retries then fails 的行为契约；断言失败表示该路径的约束被破坏。"""
    with Session.begin() as db:
        doc = Document(kb_id="manuals", name="bad.pdf", path="/nonexistent/bad.pdf", sha256="bad")
        db.add(doc)
        db.flush()
        job = Job(kind="ingest", payload={"document_id": doc.id})
        db.add(job)
        db.flush()
        job_id = job.id
    for _ in range(3):
        assert await process_one()
    with Session() as db:
        job = db.get(Job, job_id)
        assert job.status == "failed" and job.attempts == 3
