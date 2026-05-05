"""Single-shot paper analysis via Qwen JSON output."""

from __future__ import annotations

from models.analysis import AnalyzeRequest, AnalyzeResponse
from services import llm

SYSTEM_ANALYZE = """你是英文学术论文阅读助手。输入为论文正文摘录（可能不完整）。请输出**唯一一个 JSON 对象**，不要说多余的话。

硬性规则：
1. 不得编造摘录中未出现的实验数值、数据集名称或结论；不确定写「未给出」。
2. paragraph_pairs：每一对是一段英文与对应中文译文，段落不要太碎（每段可含多句）；条数上限按用户在 User 中的 mode 指示。
3. key_sentences：从摘录中选最重要句子（英文原句），zh_note 用中文简要释义或点评；why_important 一两句话。
4. 所有字符串使用 UTF-8 文本；不要使用 null，缺失用空字符串。

JSON 键（必须全部存在）：
{
  "one_liner_zh": "一句话中文概括论文在做什么",
  "method_summary": "方法要点中文简述",
  "limitations": "局限与不确定性（中文）",
  "paper_type_guess": "如 empirical / survey / system / theory 等；不确定写未知",
  "metadata_summary": "若摘录能看出标题、年份、venue 简述；否则写未给出",
  "key_sentences": [{"en":"","zh_note":"","why_important":""}],
  "paragraph_pairs": [{"en":"","zh":""}]
}
"""


def _limits(mode: str) -> tuple[int, int]:
    if mode == "quick":
        return 5, 10
    return 10, 20


def run_analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    raw = req.paper_text or ""
    if len(raw.strip()) < 20:
        raise ValueError("论文文本过短，请先抽取正文。")

    cap = max(2000, min(req.max_input_chars, len(raw)))
    excerpt = raw[:cap].strip()
    truncated = len(raw) > len(excerpt)

    ks_max, pp_max = _limits(req.mode)
    mode_hint = (
        f"mode={req.mode}：key_sentences 至多 {ks_max} 条；"
        f"paragraph_pairs 至多 {pp_max} 对；段落意思连贯优先。"
    )

    user_msg = (
        f"{mode_hint}\n\n"
        f"论文摘录（共 {len(excerpt)} 字符）：\n---\n{excerpt}\n---"
    )

    data = llm.chat_json(SYSTEM_ANALYZE, user_msg)

    try:
        resp = AnalyzeResponse.model_validate(data)
    except Exception:  # noqa: BLE001
        try:
            resp = AnalyzeResponse.model_validate(coerce_relaxed_dict(data))
        except Exception as e2:  # noqa: BLE001
            raise ValueError(
                f"模型 JSON 与契约不匹配：{e2}\n原始键：{list(data.keys())}"
            ) from e2

    resp.key_sentences = resp.key_sentences[:ks_max]
    resp.paragraph_pairs = resp.paragraph_pairs[:pp_max]

    if truncated:
        resp.truncation_note = (
            f"本次分析仅基于论文正文前 {len(excerpt)} 个字符；全文共 {len(raw)} 字符。"
        )
    else:
        resp.truncation_note = ""

    return resp


def coerce_relaxed_dict(data: dict) -> dict:
    """补齐缺失键，便于降级校验。"""
    defaults = {
        "one_liner_zh": "",
        "method_summary": "",
        "limitations": "",
        "paper_type_guess": "",
        "metadata_summary": "",
        "key_sentences": [],
        "paragraph_pairs": [],
    }
    out = {**defaults, **{k: v for k, v in data.items() if k in defaults}}
    # normalize nested
    ks = []
    for item in out.get("key_sentences") or []:
        if isinstance(item, dict):
            ks.append(
                {
                    "en": str(item.get("en", "")),
                    "zh_note": str(item.get("zh_note", "")),
                    "why_important": str(item.get("why_important", "")),
                }
            )
    pp = []
    for item in out.get("paragraph_pairs") or []:
        if isinstance(item, dict):
            pp.append({"en": str(item.get("en", "")), "zh": str(item.get("zh", ""))})
    out["key_sentences"] = ks
    out["paragraph_pairs"] = pp
    return out
