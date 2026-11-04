"""应用启动入口：中间件、生命周期与路由装配；不再承载各领域 HTTP 实现。"""

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import select, text

from backend.api import authentication, configuration, conversations, documents, evaluations, runs
from backend.api.dependencies import Admin
from backend.applications.factory_assistant.runtime import active_tasks, start_run
from backend.bootstrap.settings import settings
from backend.infrastructure.persistence.database import Session, engine
from backend.infrastructure.persistence.entities import (
    Run,
)

logger = logging.getLogger("agent.api")
logging.basicConfig(level=logging.INFO, format="%(message)s")


@asynccontextmanager
async def lifespan(_app):
    # Migrations are explicit: production never silently creates or mutates schema.
    """启动时检查数据库并恢复未结束运行；关闭时取消当前进程持有的任务。"""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    with Session() as db:
        pending = list(db.scalars(select(Run).where(Run.status.in_(["queued", "running"]))))
    for run in pending:
        start_run(run.id, resume=True)
    yield
    tasks = list(active_tasks.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="工厂 Agent 底座", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().allowed_origins.split(","),
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Last-Event-ID", "X-Service-Key"],
    expose_headers=["X-Trace-ID"],
)


@app.middleware("http")
async def tracing(request, call_next):
    """为 HTTP 请求产生追踪 ID 并记录耗时和状态，不记录请求密钥或完整业务内容。"""
    trace = str(uuid.uuid4())
    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace
    logger.info(
        json.dumps(
            {
                "trace_id": trace,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "seconds": round(time.monotonic() - started, 4),
            }
        )
    )
    return response


@app.exception_handler(ValueError)
async def bad_request(request, exc):
    """将边界校验错误转换为 HTTP 422，保留对调用方有用的安全说明。"""
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=422, content={"detail": str(exc)[:500]})


@app.get("/api/v1/health")
def health():
    """执行数据库连通性检查后报告服务状态；不是完整业务健康或模型效果评估。"""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok", "environment": settings().environment}


@app.get("/api/v1/metrics")
def metrics(user: Admin):
    """仅管理员可读取模型耗时与用量指标，避免无鉴权暴露运维信息。

    user：HTTP 层解析出的身份"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# 组合根统一安装路由，领域模块之间不反向导入 app，避免循环依赖。

for route_module in [authentication, configuration, documents, conversations, runs, evaluations]:
    app.include_router(route_module.router)
