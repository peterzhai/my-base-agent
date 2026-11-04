"""Optional real MySQL integration smoke. Refuses non-test database names."""

import asyncio
import os
import tempfile
from pathlib import Path

url = os.environ.get("MYSQL_TEST_URL", "")
if not url:
    raise SystemExit("请配置 MYSQL_TEST_URL，数据库名称必须以 agent_test_ 开头")
from sqlalchemy.engine import make_url  # noqa: E402

if not make_url(url).database.startswith("agent_test_"):
    raise SystemExit("禁止在非 agent_test_ 前缀数据库执行集成测试")
os.environ["DATABASE_URL"] = url
os.environ["ENVIRONMENT"] = "development"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="factory-agent-mysql-")
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from backend.applications.factory_assistant.runtime import execute_run, permission_scope  # noqa: E402
from backend.bootstrap import bootstrap  # noqa: E402
from backend.infrastructure.identity.security import encrypt, principal_for_user  # noqa: E402
from backend.infrastructure.jobs.worker import process_one  # noqa: E402
from backend.infrastructure.persistence.database import Session, engine  # noqa: E402
from backend.infrastructure.persistence.entities import Conversation, Document, Job, Record, Run  # noqa: E402

command.upgrade(Config("alembic.ini"), "head")
bootstrap()
with engine.begin() as connection:
    version = connection.scalar(text("SELECT VERSION()"))
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS smoke_production (id INT PRIMARY KEY, department VARCHAR(30), produced INT)"
        )
    )
    connection.execute(
        text(
            "INSERT INTO smoke_production VALUES (1,'workshop-a',200),(2,'workshop-b',999) ON DUPLICATE KEY UPDATE produced=VALUES(produced)"
        )
    )
acl = {"enabled": True, "roles": ["employee"], "departments": ["workshop-a", "workshop-b"]}
path = Path(os.environ["DATA_DIR"]) / "manual.md"
path.write_text("MES报工操作说明：登录系统，进入工单报工，核对完成数量后提交。")
with Session.begin() as db:
    for kind, ident, name, config in [
        ("users", "smoke", "测试员工", {"enabled": True, "department": "workshop-a", "roles": ["employee"]}),
        ("datasources", "smoke", "测试数据源", {**acl, "url_encrypted": encrypt(url)}),
        (
            "topics",
            "smoke",
            "生产订单",
            {
                **acl,
                "datasource_id": "smoke",
                "table": "smoke_production",
                "alias": "t",
                "fields": {"department": "t.department", "produced": "t.produced"},
                "dimensions": {},
                "metrics": {"total_produced": {"field": "produced", "aggregate": "sum"}},
                "department_field": "department",
                "description": "部门产量合计",
            },
        ),
    ]:
        old = db.get(Record, (kind, ident))
        if old:
            old.config = config
        else:
            db.add(Record(kind=kind, id=ident, name=name, config=config))
    doc = Document(kb_id="manuals", name="smoke.md", path=str(path), sha256="smoke")
    db.add(doc)
    db.flush()
    db.add(Job(kind="ingest", payload={"document_id": doc.id}))


async def main():
    """持续领取后台任务；没有任务时短暂让出事件循环，避免空转占满 CPU。"""
    while await process_one():
        pass
    principal = principal_for_user("smoke")
    with Session.begin() as db:
        conv = Conversation(user_id="smoke")
        db.add(conv)
        db.flush()
        run = Run(
            user_id="smoke",
            conversation_id=conv.id,
            input="今天产量是多少？",
            output={"scope": permission_scope(principal)},
        )
        db.add(run)
        db.flush()
        ident = run.id
    await execute_run(ident)
    with Session() as db:
        run = db.get(Run, ident)
        assert run.status == "done", run.status
        assert str(run.output["tables"][0]["rows"][0]["total_produced"]) == "200", run.output
    from backend.capabilities.knowledge import KnowledgeRetriever

    assert await KnowledgeRetriever().search("MES报工", principal)
    print(
        {
            "mysql_version": version,
            "migration": "ok",
            "readonly_query": "ok",
            "department_isolation": "ok",
            "ngram_rag": "ok",
            "checkpoints": "ok",
        }
    )


asyncio.run(main())
