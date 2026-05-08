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


def build_analyze_user_message(req: AnalyzeRequest) -> tuple[str, int, bool]:
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
    return user_msg, len(excerpt), truncated


def parse_analyze_raw(raw_text: str, req: AnalyzeRequest, excerpt_len: int, truncated: bool) -> AnalyzeResponse:
    data = llm.extract_json_object(raw_text)
    try:
        resp = AnalyzeResponse.model_validate(data)
    except Exception:  # noqa: BLE001
        try:
            resp = AnalyzeResponse.model_validate(coerce_relaxed_dict(data))
        except Exception as e2:  # noqa: BLE001
            raise ValueError(
                f"模型 JSON 与契约不匹配：{e2}\n原始键：{list(data.keys())}"
            ) from e2

    ks_max, pp_max = _limits(req.mode)
    resp.key_sentences = resp.key_sentences[:ks_max]
    resp.paragraph_pairs = resp.paragraph_pairs[:pp_max]
    if truncated:
        raw_len = len(req.paper_text or "")
        resp.truncation_note = (
            f"本次分析仅基于论文正文前 {excerpt_len} 个字符；全文共 {raw_len} 字符。"
        )
    else:
        resp.truncation_note = ""
    return resp


TABLE_TEMPLATE = """| 维度 | 内容 |
|------|------|
| 论文标题 | |
| 作者 | |
| 发表年份 | |
| 研究问题 | |
| 研究方法 | |
| 主要发现 | |
| 创新点 | |
| 局限性 | |"""

TABLE_SYSTEM = """你是科研论文阅读助手。你的任务是：从输入的论文内容摘录中，抽取信息并填写指定维度的 Markdown 表格。

硬性输出规则：
1. 只输出 Markdown 表格，不要输出任何解释、标题、编号或额外文本。
2. 表格必须严格符合给定模板的 Markdown 表格语法与行数；每个维度都必须有且仅一行对应内容。
3. 若摘录中没有该维度的相关信息，填写“未提及”。
4. 每个维度内容需信息充分、具体、可验证，尽量包含关键细节（如任务设定、方法机制、实验现象、指标趋势、数据规模或约束条件），避免泛泛而谈。
5. 不限制句数，但需控制长度：单个维度建议不超过约 300 字；只有在信息确实必要时可略超。
6. 内容使用中文。
"""


def build_table_user_message(req: AnalyzeRequest) -> tuple[str, str]:
    raw = req.paper_text or ""
    if len(raw.strip()) < 20:
        raise ValueError("论文文本过短，请先抽取正文。")
    cap = max(2000, min(req.max_input_chars, len(raw)))
    excerpt = raw[:cap].strip()
    truncated = len(raw) > len(excerpt)

    user_msg = (
        "请仔细阅读以下学术论文的内容，并按照给定的表格模板填写每个维度的信息。\n\n"
        "要求：\n"
        "1. 严格按照表格模板的格式输出，保持 Markdown 表格语法\n"
        "2. 每个维度都需要填写，如果论文中没有相关信息，填写\"未提及\"\n"
        "3. 内容应信息充分、具体、可验证，尽量给出关键细节，避免泛泛而谈\n"
        "4. 使用中文填写\n"
        "5. 不限制句数，但单个维度建议不超过约 140 字；只有在必要时可略超\n"
        "6. 只输出填好的表格，不要添加额外说明\n\n"
        "表格模板：\n"
        f"{TABLE_TEMPLATE}\n\n"
        "以下为论文内容摘录：\n"
        f"{excerpt}\n"
    )
    if truncated:
        user_msg += "\n（注：以上为前置摘录，可能存在信息不完整；请遵循“未提及”的规则。）\n"
    return user_msg, excerpt


def extract_markdown_table(text: str) -> str:
    """从模型输出中尽量提取第一段 Markdown 表格。若失败则返回原文裁剪。"""
    if not text:
        return ""
    target = "| 维度 | 内容 |"
    lines = text.splitlines()
    start_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith(target):
            start_idx = i
            break
    if start_idx is None:
        return text.strip()
    out: list[str] = []
    for ln in lines[start_idx:]:
        if ln.strip().startswith("|"):
            out.append(ln.rstrip())
        else:
            # 表格中可能出现空行；空行也允许中断
            if out:
                break
    md = "\n".join(out).strip()
    return md or text.strip()


REVIEW_SYSTEM = """你是学术综述助手。你只需要输出“综合文献综述”的正文内容，不要输出任何额外说明、标题前的数字列表说明、或参考文献列表。
要求：
1. 使用中文学术表达。
2. 当你引用某篇论文的信息时，必须使用 [num] 格式标注（num 从 1 开始，对应输入表格的顺序）。
3. 不要输出 Markdown 表格。
4. 不要输出与综述无关的内容。"""


def build_review_user_message(papernotes: list[str]) -> str:
    indexed = []
    for i, t in enumerate(papernotes, start=1):
        indexed.append(f"[{i}]\n{t}")
    notes_block = "\n\n".join(indexed)

    user_msg = (
        "请阅读以下多篇学术论文（每篇以 PaperNote 笔记形式给出），生成一份综合性文献综述报告，包括：\n\n"
        "1. **研究主题概述**: 简述这些论文共同关注的研究领域和核心问题\n"
        "2. **各论文主要贡献**: 逐一总结每篇论文的核心观点、方法和发现\n"
        "3. **研究方法对比**: 分析各论文采用的研究方法的异同\n"
        "4. **主要发现汇总**: 综合各论文的主要结论和发现\n"
        "5. **研究趋势与展望**: 基于这些论文，分析该领域的发展趋势和未来研究方向\n\n"
        "对于所有引用的内容或结论，使用[num]格式标注（如[1]、[2]），其中num对应各文献的编号。有多个引用来源时使用[1][2][3]格式。"
        "无需在最后给出完整参考文献列表。请使用清晰的结构和学术性语言。确保综述内容准确、逻辑连贯。\n\n"
        "输入笔记如下：\n"
        f"{notes_block}\n"
    )
    return user_msg


PAPERNOTE_SYSTEM = """你是科研论文笔记助手。你将收到论文正文摘录，请输出一份结构化中文笔记（Markdown）。

硬性规则：
1. 只输出 Markdown，不要输出 JSON，不要输出额外解释。
2. 不得编造正文中没有的信息；缺失信息统一写“未提及”。
3. 不要求每节固定句数；信息应尽量具体且可验证，避免空泛表述。
4. 允许使用二级/三级标题与列表，结构必须清晰。
"""

PAPERNOTE_TEMPLATE = """## 文献笔记

### 元信息
- 标题：
- 标题翻译（如有）：
- 作者：
- 发表年份：
- 期刊/会议：
- DOI：
- URL：
- 摘要（中文优先，缺失可英文）：
- 笔记日期：

### 研究核心
#### 内容
#### 创新点
#### 不足

### 研究内容
#### 数据
#### 方法
#### 实验
#### 结论

### 个人总结
#### 重点记录
#### 待解决
#### 思考启发
"""


def build_papernote_user_message(req: AnalyzeRequest) -> tuple[str, str]:
    raw = req.paper_text or ""
    if len(raw.strip()) < 20:
        raise ValueError("论文文本过短，请先抽取正文。")
    cap = max(2000, min(req.max_input_chars, len(raw)))
    excerpt = raw[:cap].strip()
    truncated = len(raw) > len(excerpt)
    user_msg = (
        "请基于以下论文内容摘录，生成一份 PaperNote 风格的中文笔记。\n\n"
        "要求：\n"
        "1. 严格使用给定的 Markdown 模板结构输出。\n"
        "2. 元信息字段（标题、作者、年份、期刊、DOI、URL、摘要）若无明确证据则填写“未提及”。\n"
        "3. 研究核心、研究内容、个人总结部分尽量具体，优先提取论文中的方法、实验、结果和局限细节。\n"
        "4. 只输出最终 Markdown 内容，不要添加额外说明。\n\n"
        "模板如下：\n"
        f"{PAPERNOTE_TEMPLATE}\n\n"
        "论文摘录如下：\n"
        f"{excerpt}\n"
    )
    if truncated:
        user_msg += "\n（注：这是截断摘录，若信息不足请写“未提及”。）\n"
    return user_msg, excerpt


def extract_papernote_markdown(text: str) -> str:
    if not text:
        return ""
    s = text.strip()
    header = "## 文献笔记"
    idx = s.find(header)
    if idx >= 0:
        return s[idx:].strip()
    return s


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
