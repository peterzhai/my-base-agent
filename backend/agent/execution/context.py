"""模块公开契约与值对象；不包含 HTTP、数据库或工厂具体业务。"""

import asyncio
from dataclasses import dataclass, field

from backend.agent.policies.contracts import Principal


@dataclass
class ExecutionContext:
    """单次执行的工作上下文：组合身份、追踪、取消和预算，不保存全局共享会话。"""

    principal: Principal
    trace_id: str
    max_steps: int = 12
    timeout_seconds: int = 90
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)
    steps: int = 0

    def check(self) -> None:
        """检查取消状态与步骤预算，每次逻辑动作计步；预算耗尽时停止而不是继续调用模型。"""
        if self.cancelled.is_set():
            raise asyncio.CancelledError()
        self.steps += 1
        if self.steps > self.max_steps:
            raise RuntimeError("执行步数已达到上限")
