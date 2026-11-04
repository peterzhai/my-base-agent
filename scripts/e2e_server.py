"""Isolated test/demo server; never reads or mutates the developer's platform database."""

import asyncio
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

folder = Path(tempfile.mkdtemp(prefix="factory-agent-e2e-"))
os.environ["ENVIRONMENT"] = "development"
os.environ["DATABASE_URL"] = f"sqlite:///{folder}/platform.db"
os.environ["DATA_DIR"] = str(folder)
os.environ["ADMIN_PASSWORD"] = "development-admin-password"
os.environ["SERVICE_KEY"] = "development-service-key"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from backend.app import app, lifespan  # noqa: E402
from backend.bootstrap import seed_demo  # noqa: E402
from backend.infrastructure.jobs.worker import main, process_one  # noqa: E402
from backend.infrastructure.persistence.database import Base, engine  # noqa: E402

Base.metadata.create_all(engine)
seed_demo()


async def seed():
    """在测试服务启动前处理演示导入，确保首个浏览器请求已有可检索证据。"""
    while await process_one():
        pass


asyncio.run(seed())


@asynccontextmanager
async def test_lifespan(application):
    """验证 lifespan 的行为契约；断言失败表示该路径的约束被破坏。"""
    async with lifespan(application):
        worker = asyncio.create_task(main())
        try:
            yield
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)


app.router.lifespan_context = test_lifespan

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app, host="127.0.0.1", port=int(os.environ.get("E2E_API_PORT", "18760")), loop="asyncio", http="h11"
    )
