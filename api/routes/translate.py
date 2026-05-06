"""Lightweight translation routes."""

from fastapi import APIRouter, HTTPException

from models.translate import TranslateRequest, TranslateResponse
from services import llm
from services.llm import LLMConfigError

router = APIRouter(tags=["translate"])

TRANSLATE_SYSTEM = """你是学术英文翻译助手。
任务：将用户提供的英文内容忠实翻译为中文。

规则：
1. 只输出中文翻译结果，不要解释，不要额外补充。
2. 保留原文段落结构与顺序；不要改写成摘要。
3. 术语尽量统一；公式、变量名、引用编号保持原样。
4. 如果输入非英文或混合文本，也尽量按原结构翻译可翻译部分。
"""


@router.post("/translate", response_model=TranslateResponse)
def post_translate(body: TranslateRequest) -> TranslateResponse:
    user_msg = f"mode={body.mode}\n\n原文：\n{body.text}"
    try:
        zh = llm.chat_text(TRANSLATE_SYSTEM, user_msg)
        return TranslateResponse(zh=zh.strip())
    except LLMConfigError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
