"""Shared translation prompt + LLM call (sync routes and background jobs)."""

from __future__ import annotations

from models.translate import TranslateRequest
from services import llm

TRANSLATE_SYSTEM = """你是学术英文翻译助手。
任务：将用户提供的英文内容忠实翻译为中文。

规则：
1. 只输出中文翻译结果，不要解释，不要额外补充。
2. 保留原文段落结构与顺序；不要改写成摘要。
2.1 如果 mode=page，尽量保持原文换行与阅读节奏，让输出看起来像一页连续正文。
3. 术语尽量统一；公式、变量名、引用编号保持原样。
4. 如果输入非英文或混合文本，也尽量按原结构翻译可翻译部分。
"""


def translate_to_zh(req: TranslateRequest) -> str:
    user_msg = f"mode={req.mode}\n\n原文：\n{req.text}"
    zh = llm.chat_text(TRANSLATE_SYSTEM, user_msg)
    return zh.strip()
