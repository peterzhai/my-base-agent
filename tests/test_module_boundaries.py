"""架构契约：保证目录迁移形成真实的依赖边界，而不是只更换文件位置。"""

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.agent.context import ContextBuilder

ROOT = Path(__file__).resolve().parents[1]


def backend_imports(path):
    """读取语法树中的项目导入；字符串注释和错误消息不算模块依赖。"""
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("backend."):
            yield node.module
        elif isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names if alias.name.startswith("backend."))


def test_agent_kernel_has_no_application_or_infrastructure_dependency():
    """内核不得反向依赖工厂、基础设施或 HTTP；旧根级转发文件不属于内核实现。"""
    for path in (ROOT / "backend/agent").glob("*/*.py"):
        for module in backend_imports(path):
            assert module.startswith("backend.agent."), f"{path}: {module}"


def test_canonical_modules_do_not_use_legacy_imports():
    """新增实现只导入唯一的新路径；兼容层仅供旧调用方和旧测试使用。"""
    for folder in ["agent", "capabilities", "infrastructure", "applications", "api", "bootstrap"]:
        for path in (ROOT / "backend" / folder).rglob("*.py"):
            if folder == "agent" and path.parent == ROOT / "backend/agent":
                continue
            for module in backend_imports(path):
                assert not module.startswith(("backend.infra.", "backend.services.", "backend.core.")), (
                    path,
                    module,
                )


@pytest.mark.parametrize(
    "old,new",
    [
        ("backend.infra.db", "backend.infrastructure.persistence.database"),
        ("backend.infra.models", "backend.infrastructure.persistence.entities"),
        ("backend.infra.gateway", "backend.infrastructure.models.gateway"),
        ("backend.services.runtime", "backend.applications.factory_assistant.runtime"),
        ("backend.services.jobs", "backend.infrastructure.jobs.worker"),
    ],
)
def test_legacy_import_uses_same_module_identity(old, new):
    """旧路径与新路径必须引用同一模块，防止产生第二份连接池、任务表或模拟替换点。"""
    assert importlib.import_module(old) is importlib.import_module(new)


@pytest.mark.asyncio
async def test_context_builder_retains_recent_history_without_model_call():
    """短历史无需调用模型，也不写入摘要；小模块可以不依赖数据库独立测试。"""

    class NoModel:
        """禁止使用模型的替身，任何摘要调用都视为回归。"""

        async def complete(self, *args, **kwargs):
            """在本案例中调用摘要没有必要，应让测试立即失败。"""
            pytest.fail("short history must not invoke model")

    ports = SimpleNamespace(
        conversation_id="c",
        context=SimpleNamespace(principal=object()),
        scope="scope",
        history=lambda *_: [{"role": "user", "content": "hello"}],
        save_summary=lambda *_: pytest.fail("unexpected write"),
        gateway=NoModel(),
    )
    assert await ContextBuilder(ports).build() == [{"role": "user", "content": "hello"}]


@pytest.mark.asyncio
async def test_context_builder_summarizes_and_preserves_recent_messages():
    """长历史压缩后仍保留最近四条，摘要必须带当前权限指纹写入。"""
    records = [{"role": "user", "content": str(i) + "x" * 700} for i in range(12)]
    saved = []

    class SummaryModel:
        """确定性摘要替身，不访问任何真实模型服务。"""

        async def complete(self, messages, **kwargs):
            """验证调用确实是历史摘要任务，再返回固定摘要。"""
            assert "summary" in messages[-1]["content"]
            return "summary-result"

    ports = SimpleNamespace(
        conversation_id="c",
        context=SimpleNamespace(principal=object()),
        scope="scope",
        history=lambda *_: records,
        save_summary=lambda *args: saved.append(args),
        gateway=SummaryModel(),
    )
    result = await ContextBuilder(ports).build()
    assert result == [{"role": "system", "content": "summary-result"}] + records[-4:]
    assert saved == [("c", "scope", "summary-result")]
