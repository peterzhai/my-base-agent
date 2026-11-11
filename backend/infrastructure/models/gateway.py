"""OpenAI-compatible intranet adapter plus a deterministic, clearly labelled simulator."""

import asyncio
import hashlib
import json
import re
import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import numpy as np
from prometheus_client import Counter, Histogram

from backend.bootstrap.settings import settings
from backend.infrastructure.identity.security import decrypt
from backend.infrastructure.persistence.database import Session
from backend.infrastructure.persistence.entities import Record

MODEL_LATENCY = Histogram("agent_model_seconds", "Model service latency", ["operation"])
MODEL_TOKENS = Counter("agent_model_tokens", "Reported model token usage", ["kind"])
_limit = asyncio.Semaphore(settings().model_concurrency)


class Gateway:
    """模型协议适配器：隔离具体 HTTP 格式，便于以模拟实现替换真实服务。"""

    def __init__(self, config: dict | None = None):
        """通过构造函数保存本对象依赖；优先注入协作者，避免业务方法自行寻找全局资源。

        config：配置或运行定位信息"""
        if config is None:
            with Session() as db:
                row = db.get(Record, ("models", "default"))
                config = row.config if row else {"provider": "mock"}
        self.config = config
        self.mock = config.get("provider", "mock") == "mock"
        self.model_key = (
            "mock:128"
            if self.mock
            else hashlib.sha256(
                json.dumps(
                    {
                        "url": config.get("base_url"),
                        "model": config.get("embedding_model"),
                        "revision": config.get("embedding_revision", "1"),
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
        )

    def client(self):
        """构造模型 HTTP 客户端并在服务端解密密钥，禁用环境代理以保持内网访问边界。"""
        key = decrypt(self.config["api_key_encrypted"]) if self.config.get("api_key_encrypted") else ""
        return httpx.AsyncClient(
            base_url=self.config["base_url"].rstrip("/") + "/",
            headers={"Authorization": f"Bearer {key}"} if key else {},
            timeout=float(self.config.get("timeout_seconds", 40)),
            trust_env=False,
        )

    def _chat_options(self) -> dict:
        """传递显式配置的生成参数，适配本地 Qwen 思考模式而不写死模型特有行为。"""
        options = self.config.get("chat_options", {})
        return {
            key: value
            for key, value in options.items()
            if key in {"max_tokens", "reasoning_effort", "chat_template_kwargs"}
        }

    async def complete(self, messages: list[dict], *, structured: bool = False) -> str:
        """执行一次非流式模型调用；可要求 JSON 格式，传输错误采用有限重试，业务层仍需验证输出。

        messages：有序的模型上下文消息"""
        start = time.monotonic()
        try:
            async with _limit:
                if self.mock:
                    # :mock 使用规则生成模型结果，不调用真实模型。
                    return self._mock(messages, structured)
                body = {"model": self.config["chat_model"], "messages": messages, "temperature": 0}
                # 本地推理服务可显式关闭思考输出；只允许与生成相关的参数，不能覆盖模型、消息或认证。
                body.update(self._chat_options())
                if structured:
                    body["response_format"] = {"type": "json_object"}
                async with self.client() as client:
                    for attempt in range(2):
                        try:
                            response = await client.post("chat/completions", json=body)
                            response.raise_for_status()
                            data = response.json()
                            for kind, count in data.get("usage", {}).items():
                                if isinstance(count, int):
                                    MODEL_TOKENS.labels(kind).inc(count)
                            return data["choices"][0]["message"]["content"]
                        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                            if attempt or (
                                isinstance(exc, httpx.HTTPStatusError)
                                and exc.response.status_code not in (429, 502, 503, 504)
                            ):
                                raise RuntimeError("内网模型服务暂不可用") from None
                            await asyncio.sleep(0.5)
        finally:
            MODEL_LATENCY.labels("complete").observe(time.monotonic() - start)

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """按增量读取模型 SSE 文本；已输出内容不能无条件自动重试，否则会重复或拼接错误答案。

        messages：有序的模型上下文消息"""
        start = time.monotonic()
        try:
            if self.mock:
                # :mock 将规则生成的回答包装为流式输出。
                answer = self._mock(messages, False)
                for offset in range(0, len(answer), 12):
                    await asyncio.sleep(0)
                    yield answer[offset : offset + 12]
                return
            async with _limit, self.client() as client:
                async with client.stream(
                    "POST",
                    "chat/completions",
                    json={
                        "model": self.config["chat_model"],
                        "messages": messages,
                        "stream": True,
                        "temperature": 0,
                        **self._chat_options(),
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            value = line[5:].strip()
                            if value == "[DONE]":
                                break
                            choices = json.loads(value).get("choices", [])
                            if choices and choices[0].get("delta", {}).get("content"):
                                yield choices[0]["delta"]["content"]
        except (httpx.HTTPError, KeyError, ValueError):
            raise RuntimeError("模型流式响应中断，请重试") from None
        finally:
            MODEL_LATENCY.labels("stream").observe(time.monotonic() - start)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """将输入批次转换为向量；真实服务与模拟实现遵守相同返回形状，调用者负责校验维度和有效数值。

        texts：待向量化文本批次"""
        if self.mock:
            # :mock 字符哈希生成确定性向量，不具备真实语义嵌入能力。
            vectors = []
            for text in texts:
                v = np.zeros(128, dtype=np.float32)
                chars = re.sub(r"\s", "", text.lower())
                for i in range(max(1, len(chars) - 1)):
                    token = chars[i : i + 2]
                    v[int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "little") % 128] += 1
                norm = np.linalg.norm(v)
                vectors.append((v / norm if norm else v).tolist())
            return vectors
        async with _limit, self.client() as client:
            try:
                response = await client.post(
                    "embeddings", json={"model": self.config["embedding_model"], "input": texts}
                )
                response.raise_for_status()
                values = sorted(response.json()["data"], key=lambda x: x["index"])
                if len(values) != len(texts):
                    raise ValueError("向量返回数量不匹配")
                return [x["embedding"] for x in values]
            except (httpx.HTTPError, KeyError, ValueError):
                raise RuntimeError("向量模型服务不可用或响应无效") from None

    def _mock(self, messages: list[dict], structured: bool) -> str:
        """:mock 用确定性规则模拟路由、查询计划与回答，仅用于流程测试而不模拟模型智能水平。

        messages：有序的模型上下文消息"""
        request = json.loads(messages[-1]["content"])
        task = request.get("task")
        question = request.get("question", "")
        if task == "route":
            topics = request.get("topics", [])
            if re.search(r"^(那|那么|昨天呢|今天呢)", question):
                previous = next(
                    (
                        m["content"]
                        for m in reversed(request.get("history", []))
                        if m.get("role") == "user" and m.get("content") != question
                    ),
                    "",
                )
                if previous:
                    question = re.sub("今天|昨天|本周", "", previous) + " " + question
            is_data = bool(re.search("产量|库存|订单|多少|统计|合格率|报工记录", question))
            is_knowledge = bool(re.search("如何|怎么|规范|规定|操作|流程|口径|故障", question))
            topic = next(
                (
                    t
                    for t in topics
                    if ("库存" in question and "库存" in t["name"])
                    or ("库存" not in question and "生产" in t["name"])
                ),
                topics[0] if topics else None,
            )
            route = "mixed" if is_data and is_knowledge else "data" if is_data else "knowledge"
            if is_data and not topic:
                route = "clarify"
            return json.dumps(
                {
                    "route": route,
                    "question": question,
                    "topic_id": topic["id"] if topic else None,
                    "sequential": is_data and is_knowledge and "口径" in question,
                    "clarification": "当前没有获授权的数据主题，请联系管理员。",
                },
                ensure_ascii=False,
            )
        if task == "plan":
            topic = request["topic"]
            dims = topic.get("dimensions", {})
            metrics = topic.get("metrics", {})
            filters = []
            if topic.get("time_field") and not any(
                w in question for w in ["今天", "昨天", "本周", "全部", "所有"]
            ):
                return json.dumps(
                    {"clarification": "请明确产量统计的时间范围，例如今天、昨天或本周。"}, ensure_ascii=False
                )
            if topic.get("time_field") and any(w in question for w in ["今天", "昨天", "本周"]):
                today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
                start = today - timedelta(
                    days=1 if "昨天" in question else today.weekday() if "本周" in question else 0
                )
                end = start + timedelta(days=1) if "本周" not in question else today + timedelta(days=1)
                filters = [
                    {"field": topic["time_field"], "op": "gte", "value": str(start)},
                    {"field": topic["time_field"], "op": "lt", "value": str(end)},
                ]
            return json.dumps(
                {
                    "dimensions": list(dims)[:1] if "各" in question else [],
                    "metrics": list(metrics)[:1],
                    "filters": filters,
                    "order_by": [],
                    "limit": 100,
                    "clarification": "",
                }
            )
        if task == "summary":
            return str(request.get("history", ""))[-2000:]
        evidence = request.get("evidence", [])
        tables = request.get("tables", [])
        answer = "【模拟模型演示】\n"
        if evidence:
            answer += "根据已授权文档：\n" + "\n".join(
                f"[{i + 1}] {x['content'][:500]}" for i, x in enumerate(evidence)
            )
        if tables:
            answer += "\n查询已完成，结果见数据表格。统计口径：" + "；".join(t["topic"] for t in tables)
        if not evidence and not tables:
            answer += "当前没有足够的授权资料，无法确认答案。"
        if request.get("errors"):
            answer += "\n部分任务未完成：" + "；".join(request["errors"])
        return answer


def agent_gateway(agent_config: dict) -> Gateway:
    """依据 Agent 的模型配置选择具体适配器；模型停用或缺失时失败，不静默切换至其他模型。"""
    model_id = agent_config.get("model_id", "default")
    with Session() as db:
        row = db.get(Record, ("models", model_id))
        if not row or not row.config.get("enabled", True):
            raise RuntimeError("Agent 模型配置不可用")
        return Gateway(row.config)
