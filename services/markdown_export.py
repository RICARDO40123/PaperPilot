"""Serialize analysis JSON to Markdown for download / Zotero notes."""

from __future__ import annotations

from typing import Any

from models.analysis import AnalyzeResponse


def analysis_to_markdown(result: dict[str, Any] | AnalyzeResponse) -> str:
    if isinstance(result, AnalyzeResponse):
        d = result.model_dump()
    else:
        d = dict(result)

    lines: list[str] = ["# PaperPilot 全文分析\n"]

    note = d.get("truncation_note") or ""
    if note:
        lines.extend([f"> {note}\n", ""])

    lines.extend(
        [
            "## 一句话概括",
            d.get("one_liner_zh", "") or "—",
            "",
            "## 方法要点",
            d.get("method_summary", "") or "—",
            "",
            "## 局限",
            d.get("limitations", "") or "—",
            "",
            f"**类型猜测**：{d.get('paper_type_guess', '') or '—'}  ",
            f"**元信息**：{d.get('metadata_summary', '') or '—'}",
            "",
            "## 关键句",
        ]
    )

    for i, item in enumerate(d.get("key_sentences") or [], start=1):
        if not isinstance(item, dict):
            continue
        lines.append(f"### {i}. 原文")
        lines.append(f"> {item.get('en', '')}")
        lines.append(f"- 注释：{item.get('zh_note', '')}")
        lines.append(f"- 重要性：{item.get('why_important', '')}")
        lines.append("")

    lines.extend(["## 中英对照（按段）", ""])
    for i, item in enumerate(d.get("paragraph_pairs") or [], start=1):
        if not isinstance(item, dict):
            continue
        lines.append(f"### 段落 {i}")
        lines.append("**EN**")
        lines.append(item.get("en", "") or "—")
        lines.append("")
        lines.append("**中文**")
        lines.append(item.get("zh", "") or "—")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
