"""事件存储适配器：为 SSE 提供可恢复游标。"""

from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import RunEvent


class SQLRunEvents:
    """事件存储适配器：将 EventStore 协议映射为 SQL 事务。"""

    def append(self, run_id: str, event: str, data: dict) -> int:
        """以事务保存事件并返回自增游标，使流式客户端可以按顺序恢复读取。

        run_id：单次运行唯一标识"""
        with Session.begin() as db:
            row = RunEvent(run_id=run_id, event=event, data=data)
            db.add(row)
            db.flush()
            return row.id
