"""Full-paper analysis (Qwen JSON) — sync and async job API."""

from fastapi import APIRouter, HTTPException

from models.analysis import AnalyzeRequest, AnalyzeResponse
from models.analyze_job import AnalyzeJobStatusResponse, AnalyzeJobSubmitResponse
from services.analyze_pipeline import run_analyze
from services.llm import LLMConfigError
from services.task_store import analyze_job_store, start_analyze_job

router = APIRouter(tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse)
def post_analyze(body: AnalyzeRequest) -> AnalyzeResponse:
    try:
        return run_analyze(body)
    except LLMConfigError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/analyze/submit", response_model=AnalyzeJobSubmitResponse)
def post_analyze_submit(body: AnalyzeRequest) -> AnalyzeJobSubmitResponse:
    analyze_job_store.cleanup()
    try:
        job_id = analyze_job_store.submit(body)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e
    start_analyze_job(job_id)
    return AnalyzeJobSubmitResponse(job_id=job_id)


@router.get("/analyze/job/{job_id}", response_model=AnalyzeJobStatusResponse)
def get_analyze_job(job_id: str) -> AnalyzeJobStatusResponse:
    analyze_job_store.cleanup()
    rec = analyze_job_store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="任务不存在或已过期。")
    return AnalyzeJobStatusResponse(
        job_id=rec.job_id,
        status=rec.status,
        progress=rec.progress,
        error=rec.error,
        created_at=rec.created_at,
    )


@router.get("/analyze/result/{job_id}", response_model=AnalyzeResponse)
def get_analyze_result(job_id: str) -> AnalyzeResponse:
    analyze_job_store.cleanup()
    rec = analyze_job_store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="任务不存在或已过期。")
    if rec.status == "failed":
        raise HTTPException(status_code=422, detail=rec.error or "分析失败")
    if rec.status != "done" or rec.result is None:
        raise HTTPException(
            status_code=409,
            detail=f"任务尚未完成，当前状态：{rec.status}",
        )
    return rec.result
