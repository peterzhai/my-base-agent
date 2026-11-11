"""回归测试：使用隔离数据验证行为契约；重点覆盖权限、失败和恢复路径，不能连接工厂业务库。"""

import asyncio

import pytest

from backend.bootstrap.settings import settings
from backend.agent.execution.context import ExecutionContext
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import Conversation, Record, Run
from backend.infrastructure.identity.security import principal_for_user
from backend.applications.factory_assistant.runtime import build_graph, execute_run, permission_scope


def conversation(client, headers):
    """conversation 是本模块的辅助步骤；其调用位置与事务/异常边界由上层流程控制。"""
    result = client.post("/api/v1/conversations", headers=headers, json={"agent_id": "factory"})
    assert result.status_code == 200, result.text
    return result.json()["id"]


def ask(client, headers, question):
    """ask 是本模块的辅助步骤；其调用位置与事务/异常边界由上层流程控制。

    question：用户问题"""
    ident = conversation(client, headers)
    result = client.post(f"/api/v1/conversations/{ident}/runs", headers=headers, json={"content": question})
    assert result.status_code == 200, result.text
    run_id = result.json()["run_id"]
    events = client.get(f"/api/v1/runs/{run_id}/events", headers=headers)
    assert events.status_code == 200
    run = client.get(f"/api/v1/runs/{run_id}", headers=headers).json()
    return ident, run_id, events.text, run


def test_admin_and_host_exchange(client, headers):
    """验证 admin and host exchange 的行为契约；断言失败表示该路径的约束被破坏。"""
    assert client.get("/api/v1/admin/records/users", headers=headers()).status_code == 403
    assert client.post("/api/v1/auth/exchange", json={"external_id": "host-demo-a"}).status_code == 401
    response = client.post(
        "/api/v1/auth/exchange",
        headers={"X-Service-Key": settings().service_key},
        json={"external_id": "host-demo-a", "roles": ["admin"]},
    )
    token = response.json()["access_token"]
    user = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert user["id"] == "demo-a" and user["roles"] == ["employee"]


@pytest.mark.parametrize(
    "question,expected",
    [("MES 如何报工？", "knowledge"), ("今天产量是多少？", "data"), ("根据报工规范统计今天产量", "mixed")],
)
def test_end_to_end_routes(client, headers, question, expected):
    """验证 end to end routes 的行为契约；断言失败表示该路径的约束被破坏。

    question：用户问题"""
    _, run_id, events, run = ask(client, headers(), question)
    assert run["status"] == "done", events
    assert "event: done" in events and "模拟模型演示" in run["output"]["answer"]
    if expected in ("data", "mixed"):
        assert run["output"]["tables"][0]["rows"] == [{"total_produced": 200}]
    if expected in ("knowledge", "mixed"):
        assert run["output"]["citations"]
    if expected == "data":
        assert not run["output"]["citations"]


def test_ambiguous_query_clarifies(client, headers):
    """验证 ambiguous query clarifies 的行为契约；断言失败表示该路径的约束被破坏。"""
    _, _, _, run = ask(client, headers(), "查一下产量")
    assert "时间范围" in run["output"]["answer"]
    assert not run["output"]["tables"]


def test_conversation_and_citation_ownership(client, headers):
    """验证 conversation and citation ownership 的行为契约；断言失败表示该路径的约束被破坏。"""
    ident, run_id, _, run = ask(client, headers(), "MES 如何报工？")
    assert client.get(f"/api/v1/conversations/{ident}/messages", headers=headers("demo-b")).status_code == 404
    assert client.get(f"/api/v1/runs/{run_id}", headers=headers("demo-b")).status_code == 404
    citation = run["output"]["citations"][0]
    with Session.begin() as db:
        kb = db.get(Record, ("knowledge-bases", "manuals"))
        kb.config = {"enabled": True, "departments": ["workshop-b"]}
        kb.version += 1
    assert client.get(f"/api/v1/chunks/{citation['chunk_id']}", headers=headers()).status_code == 404
    assert (
        client.get(f"/api/v1/documents/{citation['document_id']}/original", headers=headers()).status_code
        == 404
    )
    messages = client.get(f"/api/v1/conversations/{ident}/messages", headers=headers()).json()
    assert all("报工操作规范" not in m["content"] for m in messages)
    assert client.get(f"/api/v1/runs/{run_id}/events", headers=headers()).status_code == 403


def test_sensitive_config_redaction_and_version_control(client, headers):
    """验证 sensitive config redaction and version control 的行为契约；断言失败表示该路径的约束被破坏。"""
    auth = headers("admin")
    source = next(
        x for x in client.get("/api/v1/admin/records/datasources", headers=auth).json() if x["id"] == "demo"
    )
    assert "url_encrypted" not in source["config"] and "url" not in source["config"]
    assert source["config"]["has_url"]
    body = {**source, "name": "更新名称"}
    first = client.put("/api/v1/admin/records/datasources/demo", headers=auth, json=body)
    assert first.status_code == 200, first.text
    assert client.put("/api/v1/admin/records/datasources/demo", headers=auth, json=body).status_code == 409


def test_upload_duplicate_and_invalid_type(client, headers):
    """验证 upload duplicate and invalid type 的行为契约；断言失败表示该路径的约束被破坏。"""
    auth = headers("admin")
    for i in range(2):
        result = client.post(
            "/api/v1/admin/documents",
            headers=auth,
            data={"kb_id": "manuals"},
            files={"file": ("hello.md", b"hello knowledge", "text/plain")},
        )
        assert result.status_code == 200, result.text
        assert result.json()["duplicate"] == bool(i)
    assert (
        client.post(
            "/api/v1/admin/documents",
            headers=auth,
            data={"kb_id": "manuals"},
            files={"file": ("bad.exe", b"bad")},
        ).status_code
        == 422
    )


def test_user_permission_version_revokes_token(client, headers):
    """验证 user permission version revokes token 的行为契约；断言失败表示该路径的约束被破坏。"""
    auth = headers()
    with Session.begin() as db:
        user = db.get(Record, ("users", "demo-a"))
        user.version += 1
    assert client.get("/api/v1/me", headers=auth).status_code == 401


@pytest.mark.asyncio
async def test_checkpoint_resumes_after_route_and_pending_writes():
    """验证 checkpoint resumes after route and pending writes 的行为契约；断言失败表示该路径的约束被破坏。"""
    principal = principal_for_user("demo-a")
    scope = permission_scope(principal)
    with Session.begin() as db:
        conversation = Conversation(user_id=principal.user_id)
        db.add(conversation)
        db.flush()
        run = Run(
            user_id=principal.user_id,
            conversation_id=conversation.id,
            input="今天产量是多少？",
            output={"scope": scope},
        )
        db.add(run)
        db.flush()
        run_id = run.id
        conversation_id = conversation.id
        config = db.get(Record, ("agents", "factory")).config
    graph = build_graph(ExecutionContext(principal, run_id, max_steps=24), conversation_id, config, scope)
    graph_config = {"configurable": {"thread_id": f"{principal.user_id}:{run_id}"}}
    await graph.ainvoke({"question": "今天产量是多少？"}, config=graph_config, interrupt_after=["route"])
    state = await graph.aget_state(graph_config)
    assert state.next == ("data",)
    await execute_run(run_id, resume=True)
    with Session() as db:
        row = db.get(Run, run_id)
        assert row.status == "done" and row.output["tables"][0]["rows"] == [{"total_produced": 200}]


@pytest.mark.asyncio
async def test_cancel_stops_inflight_model(monkeypatch):
    """验证 cancel stops inflight model 的行为契约；断言失败表示该路径的约束被破坏。"""
    from backend.infrastructure.models.gateway import Gateway

    class SlowGateway(Gateway):
        """SlowGateway 的数据或接口边界。字段和方法以本模块职责为限，不承担跨层隐式初始化。"""

        async def complete(self, *a, **kw):
            """执行一次非流式模型调用；可要求 JSON 格式，传输错误采用有限重试，业务层仍需验证输出。"""
            await asyncio.sleep(30)

    monkeypatch.setattr("backend.applications.factory_assistant.runtime.agent_gateway", lambda _: SlowGateway())
    principal = principal_for_user("demo-a")
    with Session.begin() as db:
        c = Conversation(user_id=principal.user_id)
        db.add(c)
        db.flush()
        r = Run(
            user_id=principal.user_id,
            conversation_id=c.id,
            input="今天产量",
            output={"scope": permission_scope(principal)},
        )
        db.add(r)
        db.flush()
        ident = r.id
    task = asyncio.create_task(execute_run(ident))
    await asyncio.sleep(0.1)
    task.cancel()
    await task
    with Session() as db:
        assert db.get(Run, ident).status == "cancelled"


def test_evaluation_report(client, headers):
    """验证 evaluation report 的行为契约；断言失败表示该路径的约束被破坏。"""
    result = client.post("/api/v1/admin/evaluations/smoke/run", headers=headers("admin"))
    assert result.status_code == 200, result.text
    assert result.json()["passed"] == 3, result.text
