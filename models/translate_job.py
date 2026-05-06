"""Async translate job API models."""

from datetime import datetime

from pydantic import BaseModel, Field


class TranslateJobSubmitResponse(BaseModel):
    job_id: str = Field(..., description="任务 ID，用于轮询状态与拉取结果")


class TranslateJobStatusResponse(BaseModel):
    job_id: str
    status: str = Field(..., description="queued | running | done | failed")
    progress: int = Field(default=0, ge=0, le=100)
    error: str | None = None
    created_at: datetime
