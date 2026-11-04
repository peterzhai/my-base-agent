"""工厂流程节点的依赖容器：使用组合共享能力，不以继承共享业务实现。"""

from dataclasses import dataclass
from typing import Callable, Protocol

from backend.agent.execution.context import ExecutionContext
from backend.agent.execution.events import EventStore
from backend.agent.models.contracts import ModelGateway
from backend.agent.perception.contracts import PerceptionPorts as PerceptionPorts
from backend.agent.response.contracts import ResponsePorts as ResponsePorts


@dataclass
class NodeDependencies:
    """组合根的完整依赖容器；每个节点通过下方更窄的 Protocol 只声明自己需要的能力。"""

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
    retrieve: Callable
    validate_evidence: Callable
    query: Callable
    authorize_topic: Callable


# 接口隔离：装配时可使用同一个容器，但每类节点只声明自己需要的端口。
# Protocol 使用结构化类型，不要求实现类继承这些接口，降低适配器侵入性。


class KnowledgePorts(Protocol):
    """知识节点仅依赖授权检索与证据复核能力，可替换为测试检索器。"""

    context: ExecutionContext
    agent_config: dict
    events: EventStore
    check: Callable
    retrieve: Callable
    validate_evidence: Callable


class DataPorts(Protocol):
    """数据节点只要求受控查询能力，不接触数据库密码或 SQL 连接。"""

    context: ExecutionContext
    gateway: ModelGateway
    events: EventStore
    check: Callable
    query: Callable
