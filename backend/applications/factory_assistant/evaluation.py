"""应用级评测：检查路由与证据/表格是否满足案例要求；不把这些结构检查当作真实答案正确率。"""

import time

from backend.agent.execution.context import ExecutionContext
from backend.applications.factory_assistant.runtime import build_graph, permission_scope
from backend.infrastructure.identity.security import require_resource
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import Conversation, Run, uid


async def run_evaluation(config, principal):
    """按案例建立独立运行，核对路由和证据结构并汇总报告；每个案例都有可追溯状态。

    config：配置或运行定位信息
    principal：已由服务端验证的身份"""
    cases = config.get("cases", [])
    if not isinstance(cases, list) or not 1 <= len(cases) <= 30:
        raise ValueError("评测集应包含 1–30 个案例")
    agent = require_resource("agents", config.get("agent_id", "factory"), principal)
    report = []
    for case in cases:
        started = time.monotonic()
        run_id, conversation_id = uid(), uid()
        scope = permission_scope(principal)
        with Session.begin() as db:
            db.add(
                Conversation(id=conversation_id, user_id=principal.user_id, agent_id=agent.id, title="评测")
            )
            db.add(
                Run(
                    id=run_id,
                    conversation_id=conversation_id,
                    user_id=principal.user_id,
                    input=case["question"],
                    status="running",
                    output={"scope": scope},
                )
            )
        ctx = ExecutionContext(principal, run_id, max_steps=24)
        try:
            import asyncio

            async with asyncio.timeout(90):
                graph = build_graph(ctx, conversation_id, agent.config, scope)
                result = await graph.ainvoke(
                    {"question": case["question"]},
                    config={"configurable": {"thread_id": f"{principal.user_id}:{run_id}"}},
                )
            passed = result["route"]["route"] == case.get("expected_route", result["route"]["route"])
            passed &= not case.get("require_citations") or bool(result.get("evidence"))
            passed &= not case.get("require_table") or bool(result.get("tables"))
            report.append(
                {
                    "question": case["question"],
                    "passed": bool(passed),
                    "route": result["route"]["route"],
                    "seconds": round(time.monotonic() - started, 3),
                }
            )
            with Session.begin() as db:
                run = db.get(Run, run_id)
                run.status, run.output = "done", {"scope": scope, "evaluation": True}
        except Exception as exc:
            report.append({"question": case["question"], "passed": False, "error": type(exc).__name__})
            with Session.begin() as db:
                db.get(Run, run_id).status = "failed"
    return {"cases": report, "passed": sum(r["passed"] for r in report), "total": len(report)}
