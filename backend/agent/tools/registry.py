"""模块公开契约与值对象；不包含 HTTP、数据库或工厂具体业务。"""

import asyncio
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from backend.agent.execution.context import ExecutionContext


class Tool:
    """受控工具对象：将参数模型、权限、超时与处理函数组合为一个能力。"""

    def __init__(
        self,
        name: str,
        inputs: type[BaseModel],
        handler: Callable[..., Awaitable[Any]],
        required_role: str | None = None,
        timeout: float = 10,
    ):
        """通过构造函数保存本对象依赖；优先注入协作者，避免业务方法自行寻找全局资源。"""
        self.name, self.inputs, self.handler = name, inputs, handler
        self.required_role, self.timeout = required_role, timeout

    async def invoke(self, ctx: ExecutionContext, arguments: dict) -> Any:
        """依次执行预算检查、角色授权和参数验证，再在超时范围内调用工具；不能绕过守卫直接执行。

        ctx：共享的执行预算和身份上下文"""
        ctx.check()
        if self.required_role and self.required_role not in ctx.principal.roles:
            raise PermissionError("无工具调用权限")
        validated = self.inputs.model_validate(arguments)
        return await asyncio.wait_for(self.handler(ctx, validated), timeout=self.timeout)


class ToolRegistry:
    """工具注册表：管理名称到受控工具对象的映射，不负责决定应调用哪个工具。"""

    def __init__(self):
        """通过构造函数保存本对象依赖；优先注入协作者，避免业务方法自行寻找全局资源。"""
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册唯一名称的工具；重复名称立即失败，避免同名能力被静默覆盖。"""
        if tool.name in self._tools:
            raise ValueError("工具名称重复")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        """按名称取得已注册工具；缺失工具应显式失败而不是调用不受控的备用能力。"""
        return self._tools[name]
