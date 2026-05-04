"""Extract API response models."""

from pydantic import BaseModel, Field


class ExtractResponse(BaseModel):
    """POST /extract/file 返回：正文与 PDF 质量档位（不经 LLM）。"""

    text: str = Field(..., description="合并后的纯文本")
    pdf_quality: str = Field(..., description="良好 / 降级 / 严重降级 及简短原因")
    source: str = Field(default="upload", description="upload | url")
    warning: str | None = Field(default=None, description="可选提示")
