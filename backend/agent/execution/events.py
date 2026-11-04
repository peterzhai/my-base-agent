"""模块公开契约与值对象；不包含 HTTP、数据库或工厂具体业务。"""

from typing import Protocol


class EventStore(Protocol):
    """事件持久化端口：运行时不必了解事件表和事务实现。"""

    def append(self, run_id: str, event: str, data: dict) -> int:
        """持久化有序事件并返回游标，用于客户端断线续读。"""
        ...
