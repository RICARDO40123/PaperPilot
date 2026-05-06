"""Structured intent + deep-read recommendation (Qwen via DashScope)."""

from typing import Any

from fastapi import APIRouter, HTTPException

from models.intent import StructuredReadingIntent
from models.reading_api import (
    ReadingAdviseRequest,
    ReadingPipelineResponse,
    RecommendReadingRequest,
    RecommendReadingResponse,
    StructureIntentRequest,
)
from models.reading_job import ReadingJobStatusResponse, ReadingJobSubmitResponse
from services.llm import LLMConfigError
from services.reading_pipeline import (
    recommend_deep_read,
    run_pipeline,
    structure_user_intent,
)
from services.task_store import reading_job_store, start_reading_job

router = APIRouter(prefix="/reading", tags=["reading"])


@router.post("/structure-intent", response_model=StructuredReadingIntent)
def post_structure_intent(body: StructureIntentRequest) -> StructuredReadingIntent:
    try:
        return structure_user_intent(body.user_prompt)
    except LLMConfigError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/recommend", response_model=RecommendReadingResponse)
def post_recommend(body: RecommendReadingRequest) -> RecommendReadingResponse:
    try:
        rec, used = recommend_deep_read(
            body.structured_intent,
            body.paper_text,
            body.max_paper_chars,
        )
        return RecommendReadingResponse(recommendation=rec, paper_chars_used=used)
    except LLMConfigError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/advise", response_model=ReadingPipelineResponse)
def post_advise(body: ReadingAdviseRequest) -> ReadingPipelineResponse:
    try:
        return run_pipeline(
            body.user_prompt,
            paper_text=body.paper_text,
            max_paper_chars=body.max_paper_chars,
        )
    except LLMConfigError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# --- Async jobs (submit + poll + result) ---


@router.post("/structure-intent/submit", response_model=ReadingJobSubmitResponse)
def post_structure_intent_submit(body: StructureIntentRequest) -> ReadingJobSubmitResponse:
    reading_job_store.cleanup()
    try:
        job_id = reading_job_store.submit_structure(body)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e
    start_reading_job(job_id)
    return ReadingJobSubmitResponse(job_id=job_id)


@router.post("/recommend/submit", response_model=ReadingJobSubmitResponse)
def post_recommend_submit(body: RecommendReadingRequest) -> ReadingJobSubmitResponse:
    reading_job_store.cleanup()
    try:
        job_id = reading_job_store.submit_recommend(body)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e
    start_reading_job(job_id)
    return ReadingJobSubmitResponse(job_id=job_id)


@router.post("/advise/submit", response_model=ReadingJobSubmitResponse)
def post_advise_submit(body: ReadingAdviseRequest) -> ReadingJobSubmitResponse:
    reading_job_store.cleanup()
    try:
        job_id = reading_job_store.submit_advise(body)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e
    start_reading_job(job_id)
    return ReadingJobSubmitResponse(job_id=job_id)


@router.get("/job/{job_id}", response_model=ReadingJobStatusResponse)
def get_reading_job(job_id: str) -> ReadingJobStatusResponse:
    reading_job_store.cleanup()
    rec = reading_job_store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="任务不存在或已过期。")
    return ReadingJobStatusResponse(
        job_id=rec.job_id,
        kind=rec.kind,
        status=rec.status,
        progress=rec.progress,
        error=rec.error,
        created_at=rec.created_at,
    )


@router.get("/result/{job_id}")
def get_reading_result(job_id: str) -> dict[str, Any]:
    reading_job_store.cleanup()
    rec = reading_job_store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="任务不存在或已过期。")
    if rec.status == "failed":
        raise HTTPException(status_code=422, detail=rec.error or "任务失败")
    if rec.status != "done" or rec.result is None:
        raise HTTPException(
            status_code=409,
            detail=f"任务尚未完成，当前状态：{rec.status}",
        )
    return rec.result
