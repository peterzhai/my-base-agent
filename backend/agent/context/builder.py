"""上下文装配器：使用注入的历史读取、摘要写入和模型接口。"""

import json
from typing import Callable, Protocol

from backend.agent.execution.context import ExecutionContext
from backend.agent.models.contracts import ModelGateway


class ContextPorts(Protocol):
    """上下文能力的最小接口；存储由组合根提供，不要求数据库对象。"""

    context: ExecutionContext
    conversation_id: str
    scope: str
    gateway: ModelGateway
    history: Callable
    save_summary: Callable


class ContextBuilder:
    """保持原有上下文语义：最近 12 条，过长时摘要加最近 4 条。

    这里采用字符数预算，不将其描述为精确 token 管理；未来可替换裁剪策略。
    """

    def __init__(self, ports: ContextPorts):
        """通过结构化协议接收协作者，测试不需要启动模型服务或数据库。"""
        self.ports = ports

    async def build(self) -> list[dict]:
        """只处理已经按权限过滤的历史，摘要同时保存权限指纹。"""
        history = self.ports.history(self.ports.conversation_id, self.ports.context.principal)[-12:]
        if sum(len(item["content"]) for item in history) <= 6000:
            return history
        compact = await self.ports.gateway.complete(
            [
                {"role": "system", "content": "简要总结历史中的查询对象、时间、口径，不增加事实。"},
                {
                    "role": "user",
                    "content": json.dumps({"task": "summary", "history": history}, ensure_ascii=False),
                },
            ]
        )
        self.ports.save_summary(self.ports.conversation_id, self.ports.scope, compact[:2000])
        return [{"role": "system", "content": compact[:2000]}] + history[-4:]
