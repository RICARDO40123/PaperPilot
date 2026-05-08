from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    papernotes: list[str] | None = Field(
        default=None,
        min_length=2,
        max_length=20,
        description="每篇论文的 PaperNote Markdown（按顺序编号用于引用 [1]..）。",
    )
    # backward-compatible: old field name
    tables: list[str] | None = Field(
        default=None,
        min_length=2,
        max_length=20,
        description="兼容旧字段名（历史表格输入）。",
    )

    def sources(self) -> list[str]:
        if self.papernotes:
            return self.papernotes
        if self.tables:
            return self.tables
        return []

