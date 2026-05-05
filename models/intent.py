"""Structured reading intent (NL → JSON). Downstream steps use this, not raw user text."""

from pydantic import BaseModel, Field


class StructuredReadingIntent(BaseModel):
    """由模型从用户自然语言整理；后续精读建议仅依赖本结构。"""

    model_config = {"extra": "ignore"}

    motivation: str = Field(default="", description="为何读这篇文章 / 背景")
    desired_outcomes: list[str] = Field(default_factory=list, description="希望获得的产出或启发")
    information_gaps: list[str] = Field(
        default_factory=list, description="想补齐的知识或信息空白"
    )
    constraints: list[str] = Field(
        default_factory=list, description="时间、深度、语言、领域等约束"
    )
    open_questions: list[str] = Field(
        default_factory=list, description="希望论文能回答的具体问题"
    )
    ambiguity_notes: str = Field(
        default="",
        description="对用户表述含糊之处的说明；无则空字符串",
    )
