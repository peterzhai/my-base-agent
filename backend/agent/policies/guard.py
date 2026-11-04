"""执行守卫：通过回调读取实时身份、权限指纹和取消状态，不访问 ORM。"""

import asyncio
from collections.abc import Callable

from backend.agent.execution.context import ExecutionContext
from backend.agent.policies.contracts import Principal


class ExecutionGuard:
    """每个节点和每段输出统一执行安全检查，避免策略自行遗漏。"""

    def __init__(
        self,
        context: ExecutionContext,
        expected_scope: str,
        principal_loader: Callable[[str, int], Principal],
        scope_provider: Callable[[Principal], str],
        cancelled: Callable[[], bool],
    ):
        """注入外部状态读取函数；守卫的校验顺序与具体数据库解耦。"""
        self.context = context
        self.expected_scope = expected_scope
        self.principal_loader = principal_loader
        self.scope_provider = scope_provider
        self.cancelled = cancelled

    def check(self, consume_step: bool = True) -> None:
        """逻辑节点计步；流式片段只检查取消与权限，不重复消耗节点预算。"""
        if consume_step:
            self.context.check()
        elif self.context.cancelled.is_set():
            raise asyncio.CancelledError()
        principal = self.principal_loader(
            self.context.principal.user_id, self.context.principal.permission_version
        )
        if self.scope_provider(principal) != self.expected_scope:
            raise PermissionError("权限或资料发生变化，请重新提问")
        if self.cancelled():
            self.context.cancelled.set()
            raise asyncio.CancelledError()
