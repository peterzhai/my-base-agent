"""迁移环境：使用项目配置连接平台库，迁移只应由明确的部署步骤运行，不在每个请求中隐式修改表结构。"""

from alembic import context

import backend.infrastructure.persistence.entities  # noqa: F401
from backend.infrastructure.persistence.database import Base, engine

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
