"""架构契约：保证目录迁移形成真实的依赖边界，而不是只更换文件位置。"""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.agent.context import ContextBuilder

ROOT = Path(__file__).resolve().parents[1]


def backend_imports(path):
    """读取语法树中的项目导入；字符串注释和错误消息不算模块依赖。"""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("backend."):
            yield node.module
        elif isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names if alias.name.startswith("backend."))


def test_agent_kernel_has_no_application_or_infrastructure_dependency():
    """内核不得反向依赖工厂、基础设施或 HTTP。"""
    for path in (ROOT / "backend/agent").rglob("*.py"):
        for module in backend_imports(path):
            assert module.startswith("backend.agent."), f"{path}: {module}"


LEGACY_MODULES = (
    "backend.infra", "backend.services", "backend.core", "backend.config",
    "backend.agent.assembly", "backend.agent.composition", "backend.agent.knowledge",
    "backend.agent.data", "backend.agent.dependencies",
)


def is_legacy(module):
    return any(module == old or module.startswith(old + ".") for old in LEGACY_MODULES)


def test_repository_does_not_use_legacy_imports():
    """检查所有源码入口，包括 from 导入与动态导入、补丁目标字符串。"""
    for folder in ("backend", "tests", "scripts", "examples", "migrations"):
        for path in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module] + [node.module + "." + alias.name for alias in node.names]
                elif isinstance(node, ast.Call):
                    modules = [arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
                for module in modules:
                    assert not is_legacy(module), f"{path}: {module}"


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
