"""DataWorkflow：独立职责节点，通过组合注入依赖，便于替换与单元测试。"""

from fastapi import HTTPException

from backend.applications.factory_assistant.dependencies import DataPorts


class DataWorkflow:
    """数据能力策略：组合受控查询服务，隔离查询失败与授权失败。"""

    def __init__(self, dependencies: DataPorts):
        """保存显式依赖，不在节点内部创建模型、数据库或其他节点。"""
        self.d = dependencies

    async def execute_data(self, state):
        """查询策略：模型只生成查询计划，安全编译由查询能力负责。"""
        self.d.check()
        self.d.events.append(self.d.context.trace_id, "status", {"message": "生成并校验业务查询计划"})
        try:
            result = await self.d.query(
                state["question"],
                state["route"]["topic_id"],
                self.d.context,
                self.d.gateway,
                state.get("evidence", []),
            )
            if result.get("clarification"):
                return {"clarification": result["clarification"]}
            return {"tables": [result]}
        except (PermissionError, HTTPException):
            raise
        except Exception:
            return {"errors": ["数据查询未完成，请检查条件、业务主题或数据源"]}

    async def data(self, state):
        """执行单次受控查询，保留澄清和错误结果。"""
        return await self.execute_data(state)
