"""回归测试：使用隔离数据验证行为契约；重点覆盖权限、失败和恢复路径，不能连接工厂业务库。"""

import json

import httpx
import pytest
from docx import Document
from pypdf import PdfWriter

from backend.bootstrap.settings import Settings
from backend.infrastructure.models.gateway import Gateway
from backend.capabilities.knowledge import extract, split_sections


@pytest.mark.asyncio
async def test_real_adapter_json_embeddings_and_sse(monkeypatch):
    """验证 real adapter json embeddings and sse 的行为契约；断言失败表示该路径的约束被破坏。"""

    def serve(request):
        """serve 是本模块的辅助步骤；其调用位置与事务/异常边界由上层流程控制。"""
        body = json.loads(request.content)
        if request.url.path.endswith("embeddings"):
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
        if body.get("stream"):
            lines = [
                "data: "
                + json.dumps({"choices": [{"delta": {"content": part}}]}, ensure_ascii=False)
                + "\n\n"
                for part in ["你", "好"]
            ]
            return httpx.Response(
                200, text="".join(lines) + "data: [DONE]\n\n", headers={"Content-Type": "text/event-stream"}
            )
        assert body["response_format"]["type"] == "json_object"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"ok":true}'}}], "usage": {"total_tokens": 4}}
        )

    gateway = Gateway(
        {
            "provider": "openai-compatible",
            "base_url": "http://intranet/v1",
            "chat_model": "chat",
            "embedding_model": "embed",
        }
    )
    monkeypatch.setattr(
        gateway,
        "client",
        lambda: httpx.AsyncClient(base_url="http://intranet/v1/", transport=httpx.MockTransport(serve)),
    )
    assert await gateway.embed(["测试"]) == [[0.1, 0.2]]
    assert json.loads(await gateway.complete([{"role": "user", "content": "hello"}], structured=True)) == {
        "ok": True
    }
    assert (
        "".join([piece async for piece in gateway.stream([{"role": "user", "content": "hello"}])]) == "你好"
    )


@pytest.mark.asyncio
async def test_model_failure_has_bounded_retry(monkeypatch):
    """验证 model failure has bounded retry 的行为契约；断言失败表示该路径的约束被破坏。"""
    attempts = []

    def serve(request):
        """serve 是本模块的辅助步骤；其调用位置与事务/异常边界由上层流程控制。"""
        attempts.append(1)
        return httpx.Response(503)

    gateway = Gateway(
        {"provider": "openai-compatible", "base_url": "http://intranet/v1", "chat_model": "chat"}
    )
    monkeypatch.setattr(
        gateway,
        "client",
        lambda: httpx.AsyncClient(base_url="http://intranet/v1/", transport=httpx.MockTransport(serve)),
    )
    with pytest.raises(RuntimeError, match="暂不可用"):
        await gateway.complete([{"role": "user", "content": "hello"}])
    assert len(attempts) == 2


def test_docx_paragraphs_tables_and_pdf_without_text(tmp_path):
    """验证 docx paragraphs tables and pdf without text 的行为契约；断言失败表示该路径的约束被破坏。"""
    doc = Document()
    doc.add_paragraph("报工操作说明")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "数量"
    table.cell(0, 1).text = "100"
    path = tmp_path / "manual.docx"
    doc.save(path)
    sections = extract(path, ".docx")
    assert any("报工操作说明" in content for _, content in sections)
    assert any("100" in content for _, content in sections)
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    pdf = tmp_path / "scan.pdf"
    writer.write(pdf)
    assert not list(split_sections(extract(pdf, ".pdf")))


def test_production_configuration_rejects_example_secrets():
    """验证 production configuration rejects example secrets 的行为契约；断言失败表示该路径的约束被破坏。"""
    value = Settings(environment="production", database_url="mysql+pymysql://user:pass@localhost/test")
    with pytest.raises(ValueError):
        value.validate_production()
