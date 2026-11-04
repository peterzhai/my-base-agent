"""模块公开契约与值对象；不包含 HTTP、数据库或工厂具体业务。"""

from typing import Protocol

from backend.agent.policies.contracts import Principal


class Retriever(Protocol):
    """检索端口：必须在用户授权范围内搜索，不能让调用方事后猜测权限。"""

    async def search(self, query: str, principal: Principal, top_k: int = 6) -> list[dict]:
        """返回带来源的证据片段；没有可用证据时返回空列表。"""
        ...
