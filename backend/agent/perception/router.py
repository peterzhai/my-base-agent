"""IntentRouter：独立职责节点，通过组合注入依赖，便于替换与单元测试。"""

import json

from backend.agent.context import ContextBuilder
from backend.agent.perception.contracts import PerceptionPorts
from backend.agent.perception.schemas import Route


class IntentRouter:
    """感知策略对象：识别意图与授权主题，不直接执行数据库查询。"""

    def __init__(self, dependencies: PerceptionPorts):
        """保存显式依赖，不在节点内部创建模型、数据库或其他节点。"""
        self.d = dependencies

    async def route(self, state):
        """感知策略：依据授权能力和上下文进行路由，不执行工具。"""
        self.d.check()
        self.d.events.append(self.d.context.trace_id, "status", {"message": "理解问题与选择流程"})
        history = await ContextBuilder(self.d).build()
        topics = self.d.topics("topics", self.d.context.principal)
        if self.d.agent_config.get("topic_ids") is not None:
            topics = [t for t in topics if t.id in self.d.agent_config["topic_ids"]]
        response = await self.d.gateway.complete(
            [
                {
                    "role": "system",
                    "content": '你是感知与路由模块。结合会话补全问题，返回 JSON：{"route":"knowledge/data/mixed/clarify","question":"完整问题","topic_id":"获准主题ID或null","sequential":false,"clarification":"需澄清时的问题"}。仅使用可用主题。需要知识口径后再查数据时 sequential=true。缺失关键条件先澄清。',
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "route",
                            "question": state["question"],
                            "history": history,
                            "topics": [
                                {"id": t.id, "name": t.name, "description": t.config.get("description", "")}
                                for t in topics
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            structured=True,
        )
        decision = Route.model_validate_json(response)
        if decision.route not in {"knowledge", "data", "mixed", "clarify"}:
            raise ValueError("模型返回无效路由")
        if decision.route in {"data", "mixed"} and decision.topic_id not in {t.id for t in topics}:
            decision.route, decision.clarification = "clarify", "没有匹配的授权业务主题，请补充查询对象。"
        # 公开路由决定而非模型内部思维，帮助用户核对本次到底调用哪些能力。
        labels = {
            "knowledge": "知识检索",
            "data": "业务数据查询",
            "mixed": "知识与数据组合",
            "clarify": "补充条件",
        }
        order = "先检索口径再查数据" if decision.sequential else "独立任务可并行"
        self.d.events.append(
            self.d.context.trace_id,
            "status",
            {
                "message": f"感知完成 → {labels[decision.route]}；{order}"
                if decision.route == "mixed"
                else f"感知完成 → {labels[decision.route]}"
            },
        )
        return {
            "route": decision.model_dump(),
            "question": decision.question,
            "errors": [],
            "tables": [],
            "evidence": [],
        }
