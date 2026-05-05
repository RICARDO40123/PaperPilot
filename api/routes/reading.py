"""Structured intent + deep-read recommendation (Qwen via DashScope)."""

from fastapi import APIRouter, HTTPException

from models.intent import StructuredReadingIntent
from models.reading_api import (
    ReadingAdviseRequest,
    ReadingPipelineResponse,
    RecommendReadingRequest,
    RecommendReadingResponse,
    StructureIntentRequest,
)
from services.llm import LLMConfigError
from services.reading_pipeline import (
    recommend_deep_read,
    run_pipeline,
    structure_user_intent,
)

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
