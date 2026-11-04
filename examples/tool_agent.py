"""A reusable tool Agent example with no factory, database, or HTTP imports.

Run: python -m examples.tool_agent
"""

import asyncio

from pydantic import BaseModel

from backend.core.contracts import ExecutionContext, Principal, Tool, ToolRegistry


class AddInput(BaseModel):
    """加法工具输入模型：类型校验在受控调用入口完成。"""

    a: float
    b: float


async def add(ctx, arguments):
    """示例工具处理函数：只计算已校验参数的和，不负责自行判断调用权限。

    ctx：共享的执行预算和身份上下文"""
    return {"sum": arguments.a + arguments.b, "trace_id": ctx.trace_id}


async def main():
    """持续领取后台任务；没有任务时短暂让出事件循环，避免空转占满 CPU。"""
    registry = ToolRegistry()
    registry.register(Tool("add", AddInput, add))
    context = ExecutionContext(Principal("example", "example", ("employee",)), "example-run")
    print(await registry.get("add").invoke(context, {"a": 12, "b": 30}))


if __name__ == "__main__":
    asyncio.run(main())
