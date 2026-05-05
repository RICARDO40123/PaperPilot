"""Full-paper analysis API models (POST /analyze)."""

from typing import Literal

from pydantic import BaseModel, Field


class KeySentenceItem(BaseModel):
    model_config = {"extra": "ignore"}

    en: str = ""
    zh_note: str = ""
    why_important: str = ""


class ParagraphPair(BaseModel):
    model_config = {"extra": "ignore"}

    en: str = ""
    zh: str = ""


class AnalyzeRequest(BaseModel):
    paper_text: str = Field(..., min_length=20, max_length=2_000_000)
    mode: Literal["quick", "full"] = "full"
    max_input_chars: int = Field(default=14_000, ge=2_000, le=100_000)


class AnalyzeResponse(BaseModel):
    one_liner_zh: str = ""
    method_summary: str = ""
    limitations: str = ""
    key_sentences: list[KeySentenceItem] = Field(default_factory=list)
    paragraph_pairs: list[ParagraphPair] = Field(default_factory=list)
    paper_type_guess: str = ""
    metadata_summary: str = Field(
        default="",
        description="标题/年份/venue 等若无法从摘录识别则写「未给出」",
    )
    truncation_note: str = ""
