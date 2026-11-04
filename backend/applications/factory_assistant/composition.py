"""MixedWorkflow：独立职责节点，通过组合注入依赖，便于替换与单元测试。"""

import asyncio


class MixedWorkflow:
    """组合策略对象：复用知识与数据能力，而不是继承它们的实现。"""

    def __init__(self, knowledge, data):
        """构造时注入两个能力策略，避免先创建后 bind 形成未初始化对象。"""
        self.knowledge, self.data = knowledge, data

    async def mixed(self, state):
        """组合策略：仅在两个任务无依赖时并发，存在口径依赖则串行。"""
        if state["route"].get("sequential"):
            found = await self.knowledge(state)
            if not found.get("evidence"):
                return {**found, "clarification": "未找到可确认的知识口径，请补充资料或明确统计方式。"}
            result = await self.data({**state, **found})
        else:
            found, result = await asyncio.gather(self.knowledge(state), self.data(state))
        return {
            "evidence": found.get("evidence", []),
            "tables": result.get("tables", []),
            "clarification": result.get("clarification", ""),
            "errors": found.get("errors", []) + result.get("errors", []),
        }

    async def clarify(self, state):
        """澄清策略：缺少关键条件时停止执行，不能猜测业务范围。"""
        return {
            "clarification": state["route"].get("clarification") or "请补充查询对象、时间范围或业务主题。"
        }
