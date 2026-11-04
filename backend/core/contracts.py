"""兼容旧的集中式协议入口；新代码从各能力模块导入，避免形成巨型公共模块。"""

from backend.agent.execution.context import ExecutionContext as ExecutionContext
from backend.agent.execution.events import EventStore as EventStore
from backend.agent.memory.contracts import MemoryStore as MemoryStore
from backend.agent.models.contracts import ModelGateway as ModelGateway
from backend.agent.perception.schemas import Route as Route
from backend.agent.policies.contracts import ExecutionPolicy as ExecutionPolicy
from backend.agent.policies.contracts import Principal as Principal
from backend.agent.tools.registry import Tool as Tool
from backend.agent.tools.registry import ToolRegistry as ToolRegistry
from backend.capabilities.knowledge.contracts import Retriever as Retriever
