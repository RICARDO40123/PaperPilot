"""Deep-read recommendation from structured intent + paper excerpt."""

from pydantic import BaseModel, Field


class ReadingRecommendation(BaseModel):
    """是否精读及理由；不得假设未在摘录中出现的论文细节。"""

    model_config = {"extra": "ignore"}

    should_deep_read: bool = Field(description="是否建议精读全文")
    summary_verdict: str = Field(default="", description="一句话结论")
    reasons_pro: list[str] = Field(default_factory=list, description="支持精读的理由")
    reasons_con: list[str] = Field(
        default_factory=list, description="不建议精读或可先略读的理由"
    )
    next_steps: list[str] = Field(
        default_factory=list, description="下一步行动（含若不必精读时如何做）"
    )
