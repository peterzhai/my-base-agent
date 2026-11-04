"""组合根（Composition Root）：唯一负责把具体基础设施装配到节点协议的地方。

依赖倒置不等于消除具体类；具体类应集中在系统边界，而不是散落在业务节点。
此处保留 LangGraph 的检查点语义，不同时引入第二种执行引擎。
"""

from langgraph.graph import END, START, StateGraph

from backend.agent.perception.router import IntentRouter
from backend.agent.policies.guard import ExecutionGuard
from backend.agent.response.composer import ResponseComposer
from backend.applications.factory_assistant.composition import MixedWorkflow
from backend.applications.factory_assistant.data_workflow import DataWorkflow
from backend.applications.factory_assistant.dependencies import NodeDependencies
from backend.applications.factory_assistant.knowledge_workflow import KnowledgeWorkflow
from backend.capabilities.data_query import query_data
from backend.capabilities.knowledge import KnowledgeRetriever, revalidate_evidence
from backend.infrastructure.identity.security import authorized_records, principal_for_user, require_resource
from backend.infrastructure.persistence.checkpoints import SQLCheckpointSaver
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import Conversation, Run


def assemble_graph(
    ctx, conversation_id, agent_config, scope, *, gateway_factory, events, scope_provider, history_provider
):
    """工厂方法：依赖由调用者提供，节点通过组合复用，不继承数据库实现。"""
    from backend.applications.factory_assistant.state import State

    def is_cancelled():
        """应用边界负责查询运行状态；内核守卫只接收布尔结果。"""
        with Session() as db:
            run = db.get(Run, ctx.trace_id)
            return bool(run and run.cancelled)

    guard = ExecutionGuard(ctx, scope, principal_for_user, scope_provider, is_cancelled)

    def save_summary(ident, current_scope, summary):
        """摘要与权限指纹一起存储，避免旧权限内容被复用。"""
        import json

        with Session.begin() as db:
            db.get(Conversation, ident).summary = json.dumps(
                {"scope": current_scope, "text": summary}, ensure_ascii=False
            )

    dependencies = NodeDependencies(
        ctx,
        conversation_id,
        agent_config,
        scope,
        gateway_factory(agent_config),
        events,
        guard.check,
        history_provider,
        authorized_records,
        save_summary,
        KnowledgeRetriever().search,
        revalidate_evidence,
        query_data,
        lambda ident, principal: require_resource("topics", ident, principal),
    )
    router = IntentRouter(dependencies)
    knowledge = KnowledgeWorkflow(dependencies)
    data = DataWorkflow(dependencies)
    mixed = MixedWorkflow(knowledge.knowledge, data.data)
    response = ResponseComposer(dependencies)
    # 路由表即策略注册点；新增策略不需要扩展一个巨型 if/elif 执行器。
    strategies = {
        "knowledge": knowledge.knowledge,
        "data": data.data,
        "mixed": mixed.mixed,
        "clarify": mixed.clarify,
    }
    builder = StateGraph(State)
    builder.add_node("route", router.route)
    for name, strategy in strategies.items():
        builder.add_node(name, strategy)
        builder.add_edge(name, "answer")
    builder.add_node("answer", response.answer)
    builder.add_edge(START, "route")
    builder.add_conditional_edges(
        "route", lambda state: state["route"]["route"], {key: key for key in strategies}
    )
    builder.add_edge("answer", END)
    return builder.compile(checkpointer=SQLCheckpointSaver())
