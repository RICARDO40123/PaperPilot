"""API bodies for reading advice pipeline."""

from pydantic import BaseModel, Field

from models.intent import StructuredReadingIntent
from models.recommendation import ReadingRecommendation


class StructureIntentRequest(BaseModel):
    user_prompt: str = Field(..., min_length=1, max_length=16_000)


class RecommendReadingRequest(BaseModel):
    """精读建议：仅使用 structured_intent + 论文摘录，不携带用户原始自然语言。"""

    structured_intent: StructuredReadingIntent
    paper_text: str = Field(default="", max_length=2_000_000)
    max_paper_chars: int = Field(default=12_000, ge=500, le=100_000)


class ReadingPipelineResponse(BaseModel):
    """一步完成：结构化 + 建议（可选论文上下文）。"""

    structured_intent: StructuredReadingIntent
    recommendation: ReadingRecommendation
    paper_chars_used: int = 0


class RecommendReadingResponse(BaseModel):
    recommendation: ReadingRecommendation
    paper_chars_used: int = 0


class ReadingAdviseRequest(BaseModel):
    """一条龙：自然语言需求 + 可选论文全文/摘录。"""

    user_prompt: str = Field(..., min_length=1, max_length=16_000)
    paper_text: str = Field(default="", max_length=2_000_000)
    max_paper_chars: int = Field(default=12_000, ge=500, le=100_000)
