"""节点只声明所需能力；不依赖应用容器、SQL 或 Web 实现。"""

from typing import Callable, Protocol

from backend.agent.execution.context import ExecutionContext
from backend.agent.execution.events import EventStore
from backend.agent.models.contracts import ModelGateway


class PerceptionPorts(Protocol):
    """感知只需要上下文、模型、事件、历史和可用主题，不需要数据库连接。"""

    context: ExecutionContext
    conversation_id: str
    agent_config: dict
    scope: str
    gateway: ModelGateway
    events: EventStore
    check: Callable
    history: Callable
    topics: Callable
    save_summary: Callable
