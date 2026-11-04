"""模块公开契约与值对象；不包含 HTTP、数据库或工厂具体业务。"""

from typing import Any, Protocol

from backend.agent.policies.contracts import Principal


class MemoryStore(Protocol):
    """长期记忆扩展端口；当前尚未提供持久化实现。"""

    async def get(self, principal: Principal, key: str) -> Any:
        """在身份隔离的命名空间读取记忆，不等同于取得注册工具。"""
        ...

    async def put(self, principal: Principal, key: str, value: Any) -> None:
        """写入授权记忆；未来实现必须定义保留期限与撤销策略。"""
        ...
