"""Full-paper analysis (Qwen JSON)."""

from fastapi import APIRouter, HTTPException

from models.analysis import AnalyzeRequest, AnalyzeResponse
from services.analyze_pipeline import run_analyze
from services.llm import LLMConfigError

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
