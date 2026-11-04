"""节点契约测试：使用替代协作者验证策略，而不依赖真实模型、检索或业务库。"""

import asyncio
from types import SimpleNamespace

import pytest

from backend.agent.composition import MixedWorkflow
from backend.agent.knowledge import KnowledgeWorkflow


@pytest.mark.asyncio
async def test_mixed_sequential_passes_evidence_before_query():
    """串行策略必须先产生口径证据，再调用数据能力；调用者不关心协作者具体类型。"""
    order = []

    async def knowledge(state):
        """替代知识策略：仅产生本案例指定的证据与同步信号，不触发真实检索。"""
        order.append("knowledge")
        return {"evidence": [{"content": "approved definition"}]}

    async def data(state):
        """替代查询策略：检查调用顺序或同步条件，避免真实数据库成为测试前提。"""
        order.append("data")
        assert state["evidence"][0]["content"] == "approved definition"
        return {"tables": [{"rows": []}]}

    result = await MixedWorkflow(knowledge, data).mixed({"route": {"sequential": True}})
    assert order == ["knowledge", "data"]
    assert result["tables"]


@pytest.mark.asyncio
async def test_missing_definition_prevents_query():
    """缺少口径时不能用自主猜测代替，数据策略不得被调用。"""

    async def knowledge(state):
        """替代知识策略：仅产生本案例指定的证据与同步信号，不触发真实检索。"""
        return {"evidence": []}

    async def data(state):
        """替代查询策略：检查调用顺序或同步条件，避免真实数据库成为测试前提。"""
        pytest.fail("口径缺失时不应查询数据")

    result = await MixedWorkflow(knowledge, data).mixed({"route": {"sequential": True}})
    assert result["clarification"]


@pytest.mark.asyncio
async def test_parallel_strategies_are_started_together():
    """通过互相等待的协作者证明并行分支没有退化成顺序调用。"""
    first, second = asyncio.Event(), asyncio.Event()

    async def knowledge(state):
        """替代知识策略：仅产生本案例指定的证据与同步信号，不触发真实检索。"""
        first.set()
        await second.wait()
        return {"evidence": []}

    async def data(state):
        """替代查询策略：检查调用顺序或同步条件，避免真实数据库成为测试前提。"""
        second.set()
        await first.wait()
        return {"tables": []}

    await asyncio.wait_for(MixedWorkflow(knowledge, data).mixed({"route": {"sequential": False}}), 1)


@pytest.mark.asyncio
async def test_knowledge_strategy_does_not_hide_authorization_failure():
    """里氏替换约束：替代检索器仍需传播权限异常，不能当作普通检索失败吞掉。"""

    async def denied(*args, **kwargs):
        """模拟检索期间撤权；该异常必须从策略层传播给运行生命周期。"""
        raise PermissionError("revoked")

    dependency = SimpleNamespace(
        check=lambda: None,
        events=SimpleNamespace(append=lambda *args: None),
        context=SimpleNamespace(trace_id="test", principal=object()),
        agent_config={},
        retrieve=denied,
    )
    with pytest.raises(PermissionError):
        await KnowledgeWorkflow(dependency).retrieve({"question": "test"})
