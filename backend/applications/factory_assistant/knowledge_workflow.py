"""KnowledgeWorkflow：独立职责节点，通过组合注入依赖，便于替换与单元测试。"""

from fastapi import HTTPException

from backend.applications.factory_assistant.dependencies import KnowledgePorts


class KnowledgeWorkflow:
    """知识能力策略：先检索后校验，提供可组合的领域结果。"""

    def __init__(self, dependencies: KnowledgePorts):
        """保存显式依赖，不在节点内部创建模型、数据库或其他节点。"""
        self.d = dependencies

    async def retrieve(self, state):
        """检索策略：领域故障转换为部分失败，权限异常必须向上抛出。"""
        self.d.check()
        self.d.events.append(self.d.context.trace_id, "status", {"message": "检索授权知识库"})
        try:
            evidence = await self.d.retrieve(
                state["question"], self.d.context.principal, kb_ids=self.d.agent_config.get("kb_ids")
            )
            return {"evidence": evidence}
        except (PermissionError, HTTPException):
            raise
        except Exception:
            return {"errors": ["知识检索未完成，请检查文档索引或模型服务"]}

    async def validate(self, state):
        """证据策略：防止检索期间撤权或版本切换导致旧证据进入模型。"""
        self.d.check()
        return {"evidence": self.d.validate_evidence(state.get("evidence", []), self.d.context.principal)}

    async def knowledge(self, state):
        """检索后立即复核来源；安全检查不会被回答生成替代。"""
        found = await self.retrieve(state)
        result = await self.validate({**state, **found})
        return {**found, **result}
