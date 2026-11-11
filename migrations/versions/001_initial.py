"""Initial platform schema; MySQL 8.0.31 compatible."""

from alembic import op

import backend.infrastructure.persistence.entities  # noqa: F401
from backend.infrastructure.persistence.database import Base

revision = "001"
down_revision = None


def upgrade():
    """upgrade 是本模块的辅助步骤；其调用位置与事务/异常边界由上层流程控制。"""
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    if bind.dialect.name == "mysql":
        op.execute("ALTER TABLE chunks ADD FULLTEXT INDEX ft_chunks_content (content) WITH PARSER ngram")


def downgrade():
    """downgrade 是本模块的辅助步骤；其调用位置与事务/异常边界由上层流程控制。"""
    Base.metadata.drop_all(op.get_bind())
