"""回归测试：使用隔离数据验证行为契约；重点覆盖权限、失败和恢复路径，不能连接工厂业务库。"""

import asyncio
import os
import tempfile
from pathlib import Path

TEST_DIR = Path(tempfile.mkdtemp(prefix="factory-agent-tests-"))
os.environ["DATA_DIR"] = str(TEST_DIR)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DIR}/platform.db"
os.environ["ENVIRONMENT"] = "development"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402
from backend.bootstrap import seed_demo  # noqa: E402
from backend.infra.db import Base, Session, engine  # noqa: E402
from backend.infra.models import Record  # noqa: E402
from backend.infra.security import issue_token  # noqa: E402
from backend.services.jobs import process_one  # noqa: E402


@pytest.fixture(autouse=True)
def database():
    """database 是本模块的辅助步骤；其调用位置与事务/异常边界由上层流程控制。"""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed_demo()

    async def drain():
        """drain 是本模块的辅助步骤；其调用位置与事务/异常边界由上层流程控制。"""
        while await process_one():
            pass

    asyncio.run(drain())
    yield


@pytest.fixture
def client():
    """client 是本模块的辅助步骤；其调用位置与事务/异常边界由上层流程控制。"""
    with TestClient(app) as value:
        yield value


@pytest.fixture
def headers():
    """headers 是本模块的辅助步骤；其调用位置与事务/异常边界由上层流程控制。"""

    def value(user_id="demo-a"):
        """value 是本模块的辅助步骤；其调用位置与事务/异常边界由上层流程控制。"""
        with Session() as db:
            token = issue_token(db.get(Record, ("users", user_id)))
        return {"Authorization": f"Bearer {token}"}

    return value
