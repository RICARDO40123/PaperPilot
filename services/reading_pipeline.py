"""NL → structured intent → deep-read recommendation (two LLM calls)."""

from __future__ import annotations

import json

from models.intent import StructuredReadingIntent
from models.reading_api import ReadingPipelineResponse
from models.recommendation import ReadingRecommendation
from services import llm

STRUCTURE_SYSTEM = """你是「文献阅读需求」结构化助手。用户会用自然语言说明：为什么找这篇文章、想得到什么启发或内容。
你的任务：把用户原话整理成**结构化 JSON**，供后续步骤单独使用（后续**不得**再依赖用户原始措辞，只依赖本 JSON）。

规则：
1. 只输出**一个** JSON 对象，不要 Markdown、不要代码围栏外的解释。
2. 键名必须完全一致，类型正确；缺失信息用合理默认（字符串用 \"\"，数组用 []）。
3. ambiguity_notes：简要写出用户表述中含糊、歧义或需假设之处；没有则写空字符串 \"\"。
4. 不要编造用户没表达过的具体论文主题；只做需求整理。

JSON 键：
{
  "motivation": "字符串",
  "desired_outcomes": ["字符串", ...],
  "information_gaps": ["字符串", ...],
  "constraints": ["字符串", ...],
  "open_questions": ["字符串", ...],
  "ambiguity_notes": "字符串"
}
"""

RECOMMEND_SYSTEM = """你是科研阅读顾问。输入包含两部分：
(1) **结构化用户需求** —— 这是你判断的唯一「用户意图」依据，**禁止**再引用或猜测用户原始自然语言中未出现在该 JSON 里的内容。
(2) **论文文本摘录** —— 可能不完整；仅据此讨论与论文相关的事实，**禁止编造**未出现在摘录中的实验结果、数字、结论。

任务：基于 (1) 与 (2)，输出**一个** JSON，判断是否值得**精读全文**（deep read），并给出简明理由。

规则：
1. 只输出 JSON，不要其它文字。
2. 若摘录过短或为空，应降低确信度，在 reasons_con 中说明信息不足，不要虚构论文内容。
3. should_deep_read 为布尔值。

JSON 键：
{
  "should_deep_read": true或false,
  "summary_verdict": "一句话结论",
  "reasons_pro": ["支持精读的理由"],
  "reasons_con": ["不建议精读或可先略读的理由"],
  "next_steps": ["可执行的下一步建议"]
}
"""


def structure_user_intent(user_prompt: str) -> StructuredReadingIntent:
    user_block = f"用户原话：\n{user_prompt.strip()}"
    data = llm.chat_json(STRUCTURE_SYSTEM, user_block)
    return StructuredReadingIntent.model_validate(data)


def recommend_deep_read(
    structured: StructuredReadingIntent,
    paper_text: str,
    max_paper_chars: int,
) -> tuple[ReadingRecommendation, int]:
    excerpt = (paper_text or "")[: max(0, max_paper_chars)]
    structured_block = json.dumps(
        structured.model_dump(), ensure_ascii=False, indent=2
    )
    user_msg = (
        "以下为**结构化用户需求**（唯一意图依据）：\n"
        f"{structured_block}\n\n"
        "以下为**论文摘录**（可能不完整）：\n"
        f"{excerpt}"
    )
    data = llm.chat_json(RECOMMEND_SYSTEM, user_msg)
    return ReadingRecommendation.model_validate(data), len(excerpt)


def run_pipeline(
    user_prompt: str,
    paper_text: str = "",
    max_paper_chars: int = 12_000,
) -> ReadingPipelineResponse:
    structured = structure_user_intent(user_prompt)
    rec, used = recommend_deep_read(structured, paper_text, max_paper_chars)
    return ReadingPipelineResponse(
        structured_intent=structured,
        recommendation=rec,
        paper_chars_used=used,
    )
