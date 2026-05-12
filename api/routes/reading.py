"""Structured intent + deep-read recommendation (Qwen via DashScope)."""

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

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
    RECOMMEND_SYSTEM,
    build_recommend_user_message,
    parse_recommend_raw,
    recommend_deep_read,
    run_pipeline,
    structure_user_intent,
)
from services import llm
from services.task_store import reading_job_store, start_reading_job

router = APIRouter(prefix="/reading", tags=["reading"])
_log = logging.getLogger("paperpilot.routes.reading")


def _stream_event(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


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


@router.post("/recommend/stream")
def post_recommend_stream(body: RecommendReadingRequest) -> StreamingResponse:
    def _gen() -> Any:
        try:
            user_msg, used = build_recommend_user_message(
                body.structured_intent,
                body.paper_text,
                body.max_paper_chars,
            )
            pieces: list[str] = []
            for chunk in llm.chat_text_stream(RECOMMEND_SYSTEM, user_msg):
                if not chunk:
                    continue
                pieces.append(chunk)
                yield _stream_event({"type": "delta", "text": chunk})
            rec = parse_recommend_raw("".join(pieces))
            resp = RecommendReadingResponse(recommendation=rec, paper_chars_used=used)
            yield _stream_event({"type": "final", "data": resp.model_dump()})
        except Exception as e:  # noqa: BLE001
            _log.warning("/reading/recommend/stream error: %s", e)
            yield _stream_event({"type": "error", "detail": str(e)})

    return StreamingResponse(_gen(), media_type="application/x-ndjson; charset=utf-8")


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


@router.post("/advise/stream")
def post_advise_stream(body: ReadingAdviseRequest) -> StreamingResponse:
    def _gen() -> Any:
        try:
            structured = structure_user_intent(body.user_prompt)
            yield _stream_event(
                {
                    "type": "stage",
                    "name": "structured_intent_ready",
                    "data": structured.model_dump(),
                }
            )
            user_msg, used = build_recommend_user_message(
                structured,
                body.paper_text,
                body.max_paper_chars,
            )
            pieces: list[str] = []
            for chunk in llm.chat_text_stream(RECOMMEND_SYSTEM, user_msg):
                if not chunk:
                    continue
                pieces.append(chunk)
                yield _stream_event({"type": "delta", "text": chunk})
            rec = parse_recommend_raw("".join(pieces))
            resp = ReadingPipelineResponse(
                structured_intent=structured,
                recommendation=rec,
                paper_chars_used=used,
            )
            yield _stream_event({"type": "final", "data": resp.model_dump()})
        except Exception as e:  # noqa: BLE001
            _log.warning("/reading/advise/stream error: %s", e)
            yield _stream_event({"type": "error", "detail": str(e)})

    return StreamingResponse(_gen(), media_type="application/x-ndjson; charset=utf-8")


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
