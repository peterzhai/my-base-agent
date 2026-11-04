"""文档解析与切分；保留来源位置，不执行 OCR。"""

from pathlib import Path


def extract(path: Path, suffix: str) -> list[tuple[str, str]]:
    """按扩展名选择文档解析器，保留页码或段落来源；不执行 OCR，空文本交由导入层报告。"""
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        if len(reader.pages) > 2000:
            raise ValueError("PDF 超过 2000 页，请拆分导入")
        return [(f"第 {i + 1} 页", page.extract_text() or "") for i, page in enumerate(reader.pages)]
    if suffix == ".docx":
        import zipfile

        with zipfile.ZipFile(path) as archive:
            if sum(x.file_size for x in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("DOCX 解压体积过大")
        from docx import Document as WordDocument

        doc = WordDocument(path)
        parts = [(f"段落 {i + 1}", p.text) for i, p in enumerate(doc.paragraphs) if p.text.strip()]
        parts += [
            (f"表格 {i + 1}", "\n".join(" | ".join(c.text for c in row.cells) for row in table.rows))
            for i, table in enumerate(doc.tables)
        ]
        return parts
    return [("全文", path.read_text(encoding="utf-8-sig"))]


def split_sections(sections: list[tuple[str, str]], size: int = 700, overlap: int = 100):
    """按有重叠的字符窗口切块，保留来源位置。重叠用于降低上下文被边界切断的风险。"""
    for location, content in sections:
        content = content.replace("\x00", "").strip()
        for offset in range(0, len(content), size - overlap):
            piece = content[offset : offset + size].strip()
            if piece:
                yield location, piece
