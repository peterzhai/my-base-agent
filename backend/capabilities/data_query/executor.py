"""数据库只读执行边界：限制查询耗时并确保连接释放。"""

from sqlalchemy import create_engine, text

from backend.bootstrap.settings import settings


def execute_readonly(url: str, sql: str, params: dict) -> list[dict]:
    """为本次查询建立受限连接，设置查询超时和只读事务；无论成功失败都回滚并释放连接。

    url：仅供服务端使用的连接地址
    sql：由受控编译器生成的 SQL
    params：与 SQL 分离的绑定值"""
    is_sqlite = url.startswith("sqlite")
    if is_sqlite and settings().environment == "production":
        raise ValueError("生产业务查询必须使用 MySQL")
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={}
        if is_sqlite
        else {
            "connect_timeout": 5,
            "read_timeout": settings().query_timeout_seconds + 1,
            "write_timeout": 5,
        },
    )
    try:
        with engine.connect() as conn:
            if is_sqlite:
                conn.exec_driver_sql("PRAGMA query_only=ON")
            else:
                conn.exec_driver_sql(
                    "SET SESSION MAX_EXECUTION_TIME = " + str(settings().query_timeout_seconds * 1000)
                )
                conn.exec_driver_sql("START TRANSACTION READ ONLY")
            try:
                return [dict(row) for row in conn.execute(text(sql), params).mappings()]
            finally:
                conn.rollback()
    finally:
        engine.dispose()
