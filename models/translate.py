"""Lightweight translation API models."""

from typing import Literal

from pydantic import BaseModel, Field


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=30_000)
    mode: Literal["page", "paragraph"] = "page"


class TranslateResponse(BaseModel):
    zh: str = ""
