"""Explicit seed commands. Production bootstrap never loads synthetic business data."""

import argparse
import asyncio
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text

from backend.bootstrap.settings import settings
from backend.infrastructure.identity.security import encrypt
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import Document, Job, Record


def bootstrap():
    """幂等建立平台引导配置；只补缺失资源，不覆盖管理员已修改的配置。"""
    values = [
        ("roles", "admin", "管理员", {}),
        ("roles", "employee", "员工", {}),
        ("departments", "workshop-a", "一车间", {}),
        ("departments", "workshop-b", "二车间", {}),
        ("users", "admin", "平台管理员", {"enabled": True, "department": "workshop-a", "roles": ["admin"]}),
        ("models", "default", "内网模型（待配置）", {"enabled": True, "provider": "mock"}),
        (
            "agents",
            "factory",
            "工厂问答助手",
            {
                "enabled": True,
                "model_id": "default",
                "max_steps": 24,
                "timeout_seconds": 90,
                "roles": ["employee", "admin"],
                "prompt": "你是工厂内网智能问答助手。使用中文回答。",
            },
        ),
        (
            "knowledge-bases",
            "manuals",
            "系统操作手册",
            {"enabled": True, "roles": ["employee", "admin"], "departments": ["workshop-a", "workshop-b"]},
        ),
    ]
    with Session.begin() as db:
        for kind, ident, name, config in values:
            if not db.get(Record, (kind, ident)):
                db.add(Record(kind=kind, id=ident, name=name, config=config))


def seed_demo():
    """仅开发环境导入合成资料与业务数据，用于验证流程，不能用于生产初始化。"""
    if settings().environment == "production":
        raise ValueError("生产环境不允许自动加载演示业务数据")
    bootstrap()
    path = (settings().data_dir / "business-demo.db").resolve()
    engine = create_engine(f"sqlite:///{path}")
    today = str(datetime.now(ZoneInfo("Asia/Shanghai")).date())
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS production_orders (id INTEGER PRIMARY KEY, department TEXT, workshop TEXT, produced INTEGER, produced_at TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, department TEXT, material TEXT, quantity INTEGER)"
            )
        )
        if not conn.scalar(text("SELECT COUNT(*) FROM production_orders")):
            conn.execute(
                text("INSERT INTO production_orders VALUES (:id,:department,:workshop,:produced,:date)"),
                [
                    {
                        "id": 1,
                        "department": "workshop-a",
                        "workshop": "一车间",
                        "produced": 120,
                        "date": today,
                    },
                    {
                        "id": 2,
                        "department": "workshop-a",
                        "workshop": "一车间",
                        "produced": 80,
                        "date": today,
                    },
                    {
                        "id": 3,
                        "department": "workshop-b",
                        "workshop": "二车间",
                        "produced": 999,
                        "date": today,
                    },
                ],
            )
            conn.execute(
                text(
                    "INSERT INTO inventory VALUES (1,'workshop-a','钢板',320),(2,'workshop-a','螺栓',680),(3,'workshop-b','机密物料',9999)"
                )
            )
    engine.dispose()
    acl = {"enabled": True, "roles": ["employee", "admin"], "departments": ["workshop-a", "workshop-b"]}
    values = [
        (
            "users",
            "demo-a",
            "一车间演示员工",
            {"enabled": True, "department": "workshop-a", "roles": ["employee"]},
        ),
        (
            "users",
            "demo-b",
            "二车间演示员工",
            {"enabled": True, "department": "workshop-b", "roles": ["employee"]},
        ),
        (
            "identity-maps",
            "demo-a",
            "示例宿主用户 A",
            {"enabled": True, "external_id": "host-demo-a", "user_id": "demo-a"},
        ),
        (
            "identity-maps",
            "demo-b",
            "示例宿主用户 B",
            {"enabled": True, "external_id": "host-demo-b", "user_id": "demo-b"},
        ),
        ("datasources", "demo", "合成业务数据库", {**acl, "url_encrypted": encrypt(f"sqlite:///{path}")}),
        (
            "topics",
            "production",
            "生产订单",
            {
                **acl,
                "datasource_id": "demo",
                "table": "production_orders",
                "alias": "t",
                "fields": {
                    "department": "t.department",
                    "workshop": "t.workshop",
                    "produced": "t.produced",
                    "produced_at": "t.produced_at",
                },
                "dimensions": {"workshop": "车间", "produced_at": "日期"},
                "metrics": {"total_produced": {"field": "produced", "aggregate": "sum", "label": "产量"}},
                "department_field": "department",
                "time_field": "produced_at",
                "description": "产量为 produced 字段求和，按报工日期统计，仅限用户所在部门。",
            },
        ),
        (
            "topics",
            "inventory",
            "库存",
            {
                **acl,
                "datasource_id": "demo",
                "table": "inventory",
                "alias": "t",
                "fields": {"department": "t.department", "material": "t.material", "quantity": "t.quantity"},
                "dimensions": {"material": "物料"},
                "metrics": {"total_quantity": {"field": "quantity", "aggregate": "sum", "label": "库存数量"}},
                "department_field": "department",
                "description": "当前库存数量汇总，仅限用户所在部门。",
            },
        ),
        (
            "evaluations",
            "smoke",
            "基础路由与证据评测",
            {
                "agent_id": "factory",
                "cases": [
                    {"question": "MES 如何报工？", "expected_route": "knowledge", "require_citations": True},
                    {"question": "今天产量是多少？", "expected_route": "data", "require_table": True},
                    {
                        "question": "根据报工规范统计今天产量",
                        "expected_route": "mixed",
                        "require_table": True,
                        "require_citations": True,
                    },
                ],
            },
        ),
    ]
    with Session.begin() as db:
        for kind, ident, name, config in values:
            if not db.get(Record, (kind, ident)):
                db.add(Record(kind=kind, id=ident, name=name, config=config))
        if not db.query(Document).filter_by(name="MES操作手册.md").first():
            path = (settings().data_dir / "documents" / "demo-manual.md").resolve()
            path.parent.mkdir(exist_ok=True)
            content = "# MES 报工操作规范\n登录 MES，进入生产执行 → 工单报工。选择工单，填写完成数量并核对班次，确认后提交。\n产量统计口径：按报工日期汇总已提交的完成数量。发现异常报工请联系车间主管复核。\n库存查询入口：仓储管理 → 库存台账。"
            path.write_text(content)
            doc = Document(
                kb_id="manuals",
                name="MES操作手册.md",
                path=str(path),
                sha256=hashlib.sha256(content.encode()).hexdigest(),
            )
            db.add(doc)
            db.flush()
            db.add(Job(kind="ingest", payload={"document_id": doc.id}))


def main():
    """初始化命令入口：默认仅创建平台配置，--demo 必须显式选择。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--drain-jobs", action="store_true")
    args = parser.parse_args()
    seed_demo() if args.demo else bootstrap()
    if args.drain_jobs:
        from backend.infrastructure.jobs.worker import process_one

        async def drain():
            """持续处理现有演示导入任务，直到队列为空，让首次启动即可检索。"""
            while await process_one():
                pass

        asyncio.run(drain())
