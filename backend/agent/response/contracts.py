"""节点只声明所需能力；不依赖应用容器、SQL 或 Web 实现。"""

from typing import Callable, Protocol

from backend.agent.execution.context import ExecutionContext
from backend.agent.execution.events import EventStore
from backend.agent.models.contracts import ModelGateway


class ResponsePorts(Protocol):
    """响应节点组织已授权结果；不需要知道历史存储与文档解析实现。"""

    context: ExecutionContext
    agent_config: dict
    gateway: ModelGateway
    events: EventStore
    check: Callable
    validate_evidence: Callable
    authorize_topic: Callable
