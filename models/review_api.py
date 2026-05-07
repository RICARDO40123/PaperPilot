from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    tables: list[str] = Field(
        ...,
        min_length=2,
        max_length=20,
        description="每篇论文的 9 维度 Markdown 表格（按顺序编号用于引用 [1]..）。",
    )

