"""工厂应用运行外观：管理运行状态、图恢复、取消与最终回答。"""

import asyncio

from backend.agent.execution.context import ExecutionContext
from backend.applications.factory_assistant.state import State as State
from backend.infrastructure.identity.scope import permission_scope
from backend.infrastructure.identity.security import (
    audit,
    principal_for_user,
    require_resource,
)
from backend.infrastructure.models.gateway import agent_gateway
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import Conversation, Message, Run
from backend.infrastructure.persistence.events import SQLRunEvents
from backend.infrastructure.persistence.history import history_for

active_tasks: dict[str, asyncio.Task] = {}


def build_graph(ctx: ExecutionContext, conversation_id: str, agent_config: dict, scope: str):
    """兼容外观：调用组合根组装节点，再交由 LangGraph 适配器连接。

    保留旧入口是为了让 API、恢复任务与既有测试无需同时迁移。
    """
    from backend.applications.factory_assistant.assembly import assemble_graph

    return assemble_graph(
        ctx,
        conversation_id,
        agent_config,
        scope,
        gateway_factory=agent_gateway,
        events=SQLRunEvents(),
        scope_provider=permission_scope,
        history_provider=history_for,
    )


async def execute_run(run_id: str, resume: bool = False):
    """管理一次运行的状态转换。恢复沿用检查点，成功持久化回答；取消和超时必须进入明确终态。

    run_id：单次运行唯一标识
    resume：是否尝试从已有检查点恢复"""
    with Session.begin() as db:
        run = db.get(Run, run_id)
        if not run or run.status in ("done", "cancelled"):
            return
        run.status = "running"
        user_id, conversation_id, question = run.user_id, run.conversation_id, run.input
        expected_scope = run.output.get("scope")
        conversation = db.get(Conversation, conversation_id)
        agent_id = conversation.agent_id
    events = SQLRunEvents()
    try:
        principal = principal_for_user(user_id)
        scope = permission_scope(principal)
        if expected_scope != scope:
            raise PermissionError("权限或资料已变化，请重新提问")
        agent = require_resource("agents", agent_id, principal)
        ctx = ExecutionContext(
            principal,
            run_id,
            max_steps=agent.config.get("max_steps", 24),
            timeout_seconds=agent.config.get("timeout_seconds", 90),
        )
        graph = build_graph(ctx, conversation_id, agent.config, scope)
        config = {"configurable": {"thread_id": f"{user_id}:{run_id}"}, "recursion_limit": 30}
        initial = (
            None
            if resume and await graph.aget_state(config) and (await graph.aget_state(config)).values
            else {"question": question}
        )
        if resume:
            # Retries replay one canonical answer; clients reset previous partial output.
            events.append(run_id, "reset", {})
        async with asyncio.timeout(ctx.timeout_seconds):
            result = await graph.ainvoke(initial, config=config)
        output = {
            "scope": scope,
            "answer": result.get("answer", ""),
            "citations": [
                {k: v for k, v in item.items() if k != "content"} for item in result.get("evidence", [])
            ],
            "tables": result.get("tables", []),
        }
        # A completed checkpoint can be replayed after process death before DB finalization.
        with Session.begin() as db:
            run = db.get(Run, run_id)
            if run.cancelled:
                raise asyncio.CancelledError()
            run.status, run.output = "done", output
            db.add(
                Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=output["answer"],
                    payload={**output, "run_id": run_id},
                )
            )
        events.append(run_id, "done", {"run_id": run_id, "output": output})
        audit(user_id, "run.done", run_id)
    except asyncio.CancelledError:
        with Session.begin() as db:
            run = db.get(Run, run_id)
            run.status, run.cancelled = "cancelled", True
        events.append(run_id, "cancelled", {"message": "已停止生成"})
    except Exception as exc:
        safe = (
            str(exc) if isinstance(exc, (PermissionError, TimeoutError)) else "执行失败，请检查配置或稍后重试"
        )
        if isinstance(exc, TimeoutError):
            safe = "执行超时，请缩小问题范围后重试"
        with Session.begin() as db:
            db.get(Run, run_id).status = "failed"
        events.append(run_id, "error", {"message": safe})
        audit(user_id, "run.failed", run_id, {"error_type": type(exc).__name__})
    finally:
        active_tasks.pop(run_id, None)


def start_run(run_id: str, resume: bool = False):
    """按运行 ID 去重启动进程内任务；该去重范围是单 API 进程，不是分布式锁。

    run_id：单次运行唯一标识
    resume：是否尝试从已有检查点恢复"""
    if run_id not in active_tasks:
        active_tasks[run_id] = asyncio.create_task(execute_run(run_id, resume))
