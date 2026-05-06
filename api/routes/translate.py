"""Lightweight translation routes."""

from fastapi import APIRouter, HTTPException

from models.translate import TranslateRequest, TranslateResponse
from models.translate_job import TranslateJobStatusResponse, TranslateJobSubmitResponse
from services.llm import LLMConfigError
from services.translate_core import translate_to_zh
from services.task_store import start_translate_job, translate_job_store

router = APIRouter(tags=["translate"])


@router.post("/translate", response_model=TranslateResponse)
def post_translate(body: TranslateRequest) -> TranslateResponse:
    try:
        return TranslateResponse(zh=translate_to_zh(body))
    except LLMConfigError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/translate/submit", response_model=TranslateJobSubmitResponse)
def post_translate_submit(body: TranslateRequest) -> TranslateJobSubmitResponse:
    translate_job_store.cleanup()
    try:
        job_id = translate_job_store.submit(body)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e
    start_translate_job(job_id)
    return TranslateJobSubmitResponse(job_id=job_id)


@router.get("/translate/job/{job_id}", response_model=TranslateJobStatusResponse)
def get_translate_job(job_id: str) -> TranslateJobStatusResponse:
    translate_job_store.cleanup()
    rec = translate_job_store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="任务不存在或已过期。")
    return TranslateJobStatusResponse(
        job_id=rec.job_id,
        status=rec.status,
        progress=rec.progress,
        error=rec.error,
        created_at=rec.created_at,
    )


@router.get("/translate/result/{job_id}", response_model=TranslateResponse)
def get_translate_result(job_id: str) -> TranslateResponse:
    translate_job_store.cleanup()
    rec = translate_job_store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="任务不存在或已过期。")
    if rec.status == "failed":
        raise HTTPException(status_code=422, detail=rec.error or "翻译失败")
    if rec.status != "done" or rec.result is None:
        raise HTTPException(
            status_code=409,
            detail=f"任务尚未完成，当前状态：{rec.status}",
        )
    return rec.result
