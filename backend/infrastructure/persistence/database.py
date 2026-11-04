"""数据库适配器：集中创建连接与会话。使用会话工厂划定事务边界，不把数据库连接传到浏览器或模型中。"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.bootstrap.settings import settings


class Base(DeclarativeBase):
    """平台 ORM 声明基类，只提供映射元数据，不是业务服务的父类。"""

    pass


def make_engine(url: str):
    """按数据库适配器配置连接；SQLite 的线程与 WAL 参数仅服务于开发测试。

    url：仅供服务端使用的连接地址"""
    args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
    engine = create_engine(url, pool_pre_ping=True, connect_args=args)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def configure(dbapi_connection, _):
            """初始化 SQLite 连接的 WAL 和外键设置，不在 MySQL 连接上执行这些语句。"""
            dbapi_connection.execute("PRAGMA journal_mode=WAL")
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


engine = make_engine(settings().database_url)
Session = sessionmaker(engine, expire_on_commit=False)
