"""Async reading (精读) job API models."""

from datetime import datetime

from pydantic import BaseModel, Field


class ReadingJobSubmitResponse(BaseModel):
    job_id: str = Field(..., description="任务 ID")


class ReadingJobStatusResponse(BaseModel):
    job_id: str
    kind: str = Field(..., description="structure | recommend | advise")
    status: str = Field(..., description="queued | running | done | failed")
    progress: int = Field(default=0, ge=0, le=100)
    error: str | None = None
    created_at: datetime
