"""PDF / URL text extraction (no LLM). Stage 2: PDF upload only."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

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
