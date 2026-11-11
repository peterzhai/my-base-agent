"""Synthetic RAG capacity benchmark. Isolated temp DB; no access to real factory data."""

import argparse
import asyncio
import json
import os
import resource
import sys
import tempfile
import time
from pathlib import Path


async def benchmark(chunks, concurrency, dimension):
    """生成隔离合成数据并分波执行并发检索，报告仅代表检索层资源消耗。"""
    folder = Path(tempfile.mkdtemp(prefix="factory-agent-bench-"))
    os.environ["DATABASE_URL"] = f"sqlite:///{folder}/benchmark.db"
    os.environ["DATA_DIR"] = str(folder)
    os.environ["ENVIRONMENT"] = "development"
    import numpy as np

    from backend.capabilities.knowledge import KnowledgeRetriever, rebuild_index
    from backend.agent.policies.contracts import Principal
    from backend.infrastructure.models.gateway import Gateway
    from backend.infrastructure.persistence.database import Base, Session, engine
    from backend.infrastructure.persistence.entities import Chunk, Document, Record

    Base.metadata.create_all(engine)
    rng = np.random.default_rng(42)
    # :mock 随机向量及下方合成知识块仅用于容量压测。
    matrix = rng.normal(size=(chunks, dimension)).astype(np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    with Session.begin() as db:
        db.add(
            Record(
                kind="knowledge-bases",
                id="benchmark",
                name="容量测试",
                config={"enabled": True, "roles": ["employee"], "departments": ["a"]},
            )
        )
        doc = Document(
            id="benchmark",
            kb_id="benchmark",
            name="合成资料.md",
            path="unused",
            sha256="benchmark",
            status="ready",
        )
        db.add(doc)
    for offset in range(0, chunks, 1000):
        with Session.begin() as db:
            db.add_all(
                [
                    Chunk(
                        id=f"chunk-{i}",
                        document_id="benchmark",
                        kb_id="benchmark",
                        ordinal=i,
                        location=f"块 {i}",
                        content=f"合成报工操作规范 {i}，按工单提交生产完成数量。",
                        embedding=matrix[i].tobytes(),
                        model_key=f"benchmark:{dimension}",
                    )
                    for i in range(offset, min(chunks, offset + 1000))
                ]
            )
    started = time.monotonic()
    await asyncio.to_thread(rebuild_index, "benchmark")
    build_seconds = time.monotonic() - started

    class BenchmarkGateway(Gateway):
        """:mock 容量测试用向量适配器：直接返回固定维度向量，排除真实模型服务耗时。"""

        def __init__(self):
            """通过构造函数保存本对象依赖；优先注入协作者，避免业务方法自行寻找全局资源。"""
            self.model_key = f"benchmark:{dimension}"

        async def embed(self, texts):
            """将输入批次转换为向量；真实服务与模拟实现遵守相同返回形状，调用者负责校验维度和有效数值。

            texts：待向量化文本批次"""
            return [matrix[0].tolist() for _ in texts]

    retriever = KnowledgeRetriever(BenchmarkGateway())
    principal = Principal("benchmark", "a", ("employee",))
    timings = []
    errors = []

    async def query(i):
        """执行一项并发检索并验证返回知识库，收集耗时与错误用于统计。"""
        started = time.monotonic()
        try:
            found = await retriever.search("报工操作规范", principal, kb_ids=["benchmark"])
            if not found or any(x["kb_id"] != "benchmark" for x in found):
                raise ValueError("检索结果为空或越权")
        except Exception as exc:
            errors.append(type(exc).__name__)
        timings.append(time.monotonic() - started)

    started = time.monotonic()
    # Three bounded waves rather than creating an unbounded request queue.
    for wave in range(3):
        await asyncio.gather(*(query(i) for i in range(concurrency)))
    elapsed = time.monotonic() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mb = rss / (1024**2 if sys.platform == "darwin" else 1024)
    report = {
        "kind": "synthetic-retrieval-only",
        "database": "sqlite-development-adapter",
        "chunks": chunks,
        "dimension": dimension,
        "concurrency": concurrency,
        "requests": len(timings),
        "errors": errors,
        "index_build_seconds": round(build_seconds, 3),
        "elapsed_seconds": round(elapsed, 3),
        "p50_seconds": round(float(np.percentile(timings, 50)), 3),
        "p95_seconds": round(float(np.percentile(timings, 95)), 3),
        "peak_process_rss_mb": round(peak_mb, 1),
        "model_service_seconds": 0,
        "note": "Local machine only; excludes real model, MySQL, HTTP and concurrent ingestion. Not target VM SLA.",
    }
    output = Path("data/benchmark.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=int, default=50000)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--dimension", type=int, default=768)
    args = parser.parse_args()
    if not 1 <= args.chunks <= 50000 or not 1 <= args.concurrency <= 10 or not 64 <= args.dimension <= 4096:
        parser.error("参数超出容量测试范围")
    asyncio.run(benchmark(args.chunks, args.concurrency, args.dimension))
