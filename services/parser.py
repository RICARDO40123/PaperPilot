"""PDF / URL text extraction (no LLM). Stage 2: PDF upload only."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError
try:
    import fitz  # pymupdf
except ImportError:
    fitz = None

# 质量分层阈值（字符数，去首尾空白后）
QUALITY_SEVERE_MAX = 200
QUALITY_DEGRADED_MAX = 2000


def assess_pdf_quality(text: str) -> tuple[str, str | None]:
    """返回 (pdf_quality 描述, 可选 warning)。"""
    stripped = text.strip()
    n = len(stripped)
    if n < QUALITY_SEVERE_MAX:
        return (
            f"严重降级-疑似扫描或图片版PDF（可抽取字符约 {n}）",
            "若正文几乎为空，请尝试其它 PDF 版本或使用 OCR 工具。",
        )
    if n < QUALITY_DEGRADED_MAX:
        return (
            f"降级处理-文本较少（约 {n} 字符），可能排版复杂或仅为摘要页",
            None,
        )
    return "良好", None


def extract_pdf_bytes(data: bytes) -> tuple[str, str, str | None]:
    """
    从 PDF 字节抽取全文，并给出质量标签与可选提示。
    返回 (full_text, pdf_quality, warning)。
    """
    if not data:
        raise ValueError("PDF 内容为空")

    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as e:
        raise ValueError(f"无法解析 PDF：{e}") from e

    if getattr(reader, "is_encrypted", False):
        raise ValueError("PDF 已加密，无法抽取文本。请先解密后再上传。")

    parts: list[str] = []
    try:
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"读取页面文本失败：{e}") from e

    text = "\n\n".join(parts)
    quality, warning = assess_pdf_quality(text)
    return text, quality, warning


def _open_pdf_reader(data: bytes) -> PdfReader:
    if not data:
        raise ValueError("PDF 内容为空")
    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as e:
        raise ValueError(f"无法解析 PDF：{e}") from e
    if getattr(reader, "is_encrypted", False):
        raise ValueError("PDF 已加密，无法抽取文本。请先解密后再上传。")
    return reader


def get_pdf_page_count(data: bytes) -> int:
    reader = _open_pdf_reader(data)
    return len(reader.pages)


def extract_pdf_page_text(data: bytes, page_index: int) -> tuple[str, int]:
    reader = _open_pdf_reader(data)
    total = len(reader.pages)
    if total <= 0:
        raise ValueError("PDF 无可读页面。")
    if page_index < 0 or page_index >= total:
        raise ValueError(f"页码越界：{page_index + 1}（总页数 {total}）")
    try:
        text = reader.pages[page_index].extract_text() or ""
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"抽取第 {page_index + 1} 页文本失败：{e}") from e
    return text, total


def render_pdf_page_image(data: bytes, page_index: int, dpi: int = 160) -> tuple[bytes, int]:
    if fitz is None:
        raise ValueError("未安装 pymupdf，请执行：pip install pymupdf")
    if not data:
        raise ValueError("PDF 内容为空")
    if dpi < 72 or dpi > 400:
        raise ValueError("dpi 取值范围建议为 72~400")
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"无法解析 PDF：{e}") from e
    total = doc.page_count
    if total <= 0:
        doc.close()
        raise ValueError("PDF 无可读页面。")
    if page_index < 0 or page_index >= total:
        doc.close()
        raise ValueError(f"页码越界：{page_index + 1}（总页数 {total}）")
    try:
        page = doc.load_page(page_index)
        scale = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = pix.tobytes("png")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"渲染第 {page_index + 1} 页图片失败：{e}") from e
    finally:
        doc.close()
    return image, total
