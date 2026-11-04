"""Development-only host backend. The production host must use its existing authenticated session."""

import os

import httpx
from fastapi import FastAPI, HTTPException

from backend.config import settings

if settings().environment == "production":
    raise RuntimeError("示例宿主不得在生产环境启用")
app = FastAPI(title="示例宿主后端")


@app.post("/session/{account}")
async def session(account: str):
    """只为两个固定开发账号向平台交换令牌；生产宿主应从已认证会话中读取账号。"""
    if account not in {"host-demo-a", "host-demo-b"}:
        raise HTTPException(403, "无效演示用户")
    async with httpx.AsyncClient(trust_env=False) as client:
        result = await client.post(
            os.getenv("AGENT_API", "http://127.0.0.1:8000/api/v1") + "/auth/exchange",
            headers={"X-Service-Key": settings().service_key},
            json={"external_id": account},
        )
        if result.status_code != 200:
            raise HTTPException(502, "身份交换失败")
        return result.json()
