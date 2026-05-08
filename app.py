"""PaperPilot Streamlit UI — thin client calling FastAPI."""

import os
import time
import json
import uuid
from html import escape

import httpx
import streamlit as st
from dotenv import load_dotenv

from services.markdown_export import analysis_to_markdown

load_dotenv()

DEFAULT_BACKEND = "http://127.0.0.1:8000"
TIMEOUT_HEALTH = 10.0
TIMEOUT_EXTRACT = 120.0
TIMEOUT_READING = 180.0
TIMEOUT_ANALYZE = 240.0
TIMEOUT_ANALYZE_JOB = 15.0
TIMEOUT_READING_JOB = 15.0
ANALYZE_POLL_INTERVAL = 1.0
MAX_ANALYZE_JOB_WAIT_SEC = 600.0
MAX_TRANSLATE_JOB_WAIT_SEC = 600.0
MAX_READING_JOB_WAIT_SEC = 600.0
PREVIEW_CHARS = 8000

st.set_page_config(page_title="PaperPilot", layout="wide")
st.title("PaperPilot")

backend_url = os.getenv("BACKEND_URL", DEFAULT_BACKEND).rstrip("/")

if "paper_text" not in st.session_state:
    st.session_state.paper_text = ""
if "reading_structured_intent" not in st.session_state:
    st.session_state.reading_structured_intent = None
if "reading_last_recommendation" not in st.session_state:
    st.session_state.reading_last_recommendation = None
if "analyze_result" not in st.session_state:
    st.session_state.analyze_result = None
if "pdf_bytes" not in st.session_state:
    st.session_state.pdf_bytes = b""
if "pdf_name" not in st.session_state:
    st.session_state.pdf_name = ""
if "reader_page_count" not in st.session_state:
    st.session_state.reader_page_count = 0
if "reader_current_page" not in st.session_state:
    st.session_state.reader_current_page = 1
if "reader_page_input" not in st.session_state:
    st.session_state.reader_page_input = 1
if "reader_nav_to_page" not in st.session_state:
    st.session_state.reader_nav_to_page = None
if "reader_page_text_cache" not in st.session_state:
    st.session_state.reader_page_text_cache = {}
if "reader_translation_cache" not in st.session_state:
    st.session_state.reader_translation_cache = {}
if "reader_page_image_cache" not in st.session_state:
    st.session_state.reader_page_image_cache = {}
if "analyze_job_id" not in st.session_state:
    st.session_state.analyze_job_id = None
if "analyze_job_started_at" not in st.session_state:
    st.session_state.analyze_job_started_at = 0.0
if "reader_translate_job_id" not in st.session_state:
    st.session_state.reader_translate_job_id = None
if "reader_translate_job_started_at" not in st.session_state:
    st.session_state.reader_translate_job_started_at = 0.0
if "reader_translate_cache_key" not in st.session_state:
    st.session_state.reader_translate_cache_key = ""
if "reading_job_id" not in st.session_state:
    st.session_state.reading_job_id = None
if "reading_job_started_at" not in st.session_state:
    st.session_state.reading_job_started_at = 0.0
if "reading_job_paper_id" not in st.session_state:
    st.session_state.reading_job_paper_id = None
if "reading_job_kind" not in st.session_state:
    st.session_state.reading_job_kind = ""
if "reader_poll_translate_ui" not in st.session_state:
    st.session_state.reader_poll_translate_ui = {}
if "analyze_poll_ui" not in st.session_state:
    st.session_state.analyze_poll_ui = {}
if "reading_poll_ui" not in st.session_state:
    st.session_state.reading_poll_ui = {}

if "papers" not in st.session_state:
    # paper_id -> per-paper isolated state
    st.session_state.papers = {}
if "current_paper_id" not in st.session_state:
    st.session_state.current_paper_id = None
if "analyze_table_markdown" not in st.session_state:
    st.session_state.analyze_table_markdown = ""
if "review_markdown" not in st.session_state:
    st.session_state.review_markdown = ""
if "papernote_markdown" not in st.session_state:
    st.session_state.papernote_markdown = ""
if "papernote_just_generated" not in st.session_state:
    st.session_state.papernote_just_generated = False


def _new_paper_entry(
    paper_id: str,
    pdf_name: str,
    pdf_bytes: bytes,
    paper_text: str = "",
) -> dict:
    inferred_len = len((paper_text or "").strip())
    analyze_default = min(100000, max(2000, inferred_len if inferred_len else 14000))
    reading_default = min(100000, max(2000, inferred_len if inferred_len else 12000))
    return {
        "paper_id": paper_id,
        "pdf_name": pdf_name,
        "pdf_bytes": pdf_bytes,
        "paper_text": paper_text,
        # reader view state
        "reader_page_count": 0,
        "reader_current_page": 1,
        "reader_page_input": 1,
        "reader_nav_to_page": None,
        # reader caches
        "reader_page_text_cache": {},
        "reader_translation_cache": {},
        "reader_page_image_cache": {},
        # analyze/recommend results
        "analyze_table_markdown": "",
        "papernote_markdown": "",
        "reading_structured_intent": None,
        "reading_last_recommendation": None,
        "analyze_max_chars": analyze_default,
        "reading_max_paper_chars": reading_default,
    }


def _ensure_current_paper_id() -> str | None:
    pid = st.session_state.current_paper_id
    if pid and pid in st.session_state.papers:
        return pid
    if st.session_state.papers:
        st.session_state.current_paper_id = next(iter(st.session_state.papers.keys()))
        return st.session_state.current_paper_id
    return None


def _bind_current_paper_to_session_state() -> None:
    pid = _ensure_current_paper_id()
    if not pid:
        return
    paper = st.session_state.papers[pid]

    st.session_state.pdf_bytes = paper["pdf_bytes"]
    st.session_state.pdf_name = paper["pdf_name"]

    st.session_state.paper_text = paper.get("paper_text", "")

    st.session_state.reader_page_count = int(paper.get("reader_page_count", 0) or 0)
    st.session_state.reader_current_page = int(
        paper.get("reader_current_page", 1) or 1
    )
    st.session_state.reader_page_input = int(paper.get("reader_page_input", 1) or 1)
    st.session_state.reader_nav_to_page = paper.get("reader_nav_to_page")

    st.session_state.reader_page_text_cache = paper["reader_page_text_cache"]
    st.session_state.reader_translation_cache = paper["reader_translation_cache"]
    st.session_state.reader_page_image_cache = paper["reader_page_image_cache"]

    st.session_state.analyze_table_markdown = paper.get("analyze_table_markdown", "")
    st.session_state.papernote_markdown = paper.get("papernote_markdown", "")
    st.session_state.analyze_max_chars = int(
        paper.get("analyze_max_chars", st.session_state.get("analyze_max_chars", 14000))
    )
    st.session_state.reading_max_paper_chars = int(
        paper.get(
            "reading_max_paper_chars",
            st.session_state.get("reading_max_paper_chars", 12000),
        )
    )

    st.session_state.reading_structured_intent = paper.get(
        "reading_structured_intent"
    )
    st.session_state.reading_last_recommendation = paper.get(
        "reading_last_recommendation"
    )


def _persist_current_paper_from_session_state() -> None:
    pid = _ensure_current_paper_id()
    if not pid:
        return
    paper = st.session_state.papers[pid]

    paper["pdf_bytes"] = st.session_state.pdf_bytes
    paper["pdf_name"] = st.session_state.pdf_name
    paper["paper_text"] = st.session_state.paper_text

    paper["reader_page_count"] = st.session_state.reader_page_count
    paper["reader_current_page"] = st.session_state.reader_current_page
    paper["reader_page_input"] = st.session_state.reader_page_input
    paper["reader_nav_to_page"] = st.session_state.reader_nav_to_page

    paper["reader_page_text_cache"] = st.session_state.reader_page_text_cache
    paper["reader_translation_cache"] = st.session_state.reader_translation_cache
    paper["reader_page_image_cache"] = st.session_state.reader_page_image_cache

    current_table_md = str(st.session_state.get("analyze_table_markdown", "") or "")
    cached_table_md = str(paper.get("analyze_table_markdown", "") or "")
    if current_table_md.strip():
        paper["analyze_table_markdown"] = current_table_md
    elif cached_table_md:
        # Prevent blank overwrite when switching modules/reruns.
        st.session_state.analyze_table_markdown = cached_table_md
    else:
        paper["analyze_table_markdown"] = ""

    current_note_md = str(st.session_state.get("papernote_markdown", "") or "")
    cached_note_md = str(paper.get("papernote_markdown", "") or "")
    if current_note_md.strip():
        paper["papernote_markdown"] = current_note_md
    elif cached_note_md:
        # Prevent blank overwrite when switching modules/reruns.
        st.session_state.papernote_markdown = cached_note_md
    else:
        paper["papernote_markdown"] = ""
    paper["analyze_max_chars"] = int(
        st.session_state.get("analyze_max_chars", paper.get("analyze_max_chars", 14000))
    )
    paper["reading_max_paper_chars"] = int(
        st.session_state.get(
            "reading_max_paper_chars",
            paper.get("reading_max_paper_chars", 12000),
        )
    )

    paper["reading_structured_intent"] = st.session_state.reading_structured_intent
    paper["reading_last_recommendation"] = st.session_state.reading_last_recommendation


def _render_analysis_result(data: dict) -> None:
    if data.get("truncation_note"):
        st.info(data["truncation_note"])
    st.markdown(f"### 一句话\n{data.get('one_liner_zh', '')}")
    st.markdown(
        f"**类型**：{data.get('paper_type_guess', '')}  "
        f"**元信息**：{data.get('metadata_summary', '')}"
    )
    st.markdown("### 方法要点")
    st.markdown(data.get("method_summary") or "—")
    st.markdown("### 局限")
    st.markdown(data.get("limitations") or "—")
    st.markdown("### 关键句")
    for i, row in enumerate(data.get("key_sentences") or [], start=1):
        if not isinstance(row, dict):
            continue
        with st.expander(f"关键句 {i}"):
            st.markdown(f"> {row.get('en', '')}")
            st.markdown(f"**注释**：{row.get('zh_note', '')}")
            st.markdown(f"**重要性**：{row.get('why_important', '')}")
    st.caption(f"已生成段落对照：**{len(data.get('paragraph_pairs') or [])}** 对。")
    md_bytes = analysis_to_markdown(data).encode("utf-8")
    st.download_button(
        label="下载 Markdown",
        data=md_bytes,
        file_name="paperpilot_analysis.md",
        mime="text/markdown",
        key="download_analysis_md",
    )
    with st.expander("原始 JSON（分析结果）"):
        st.json(data)


def _fmt_recommendation(data: dict) -> str:
    rec = data.get("recommendation", data)
    lines = [
        f"### 结论：{'**建议精读**' if rec.get('should_deep_read') else '**可先略读或不精读**'}",
        f"**一句话**：{rec.get('summary_verdict', '')}",
        "",
        "**支持精读**",
    ]
    for x in rec.get("reasons_pro") or []:
        lines.append(f"- {x}")
    lines.extend(["", "**需谨慎 / 不精读**"])
    for x in rec.get("reasons_con") or []:
        lines.append(f"- {x}")
    lines.extend(["", "**下一步**"])
    for x in rec.get("next_steps") or []:
        lines.append(f"- {x}")
    return "\n".join(lines)


def _pdf_file_tuple() -> tuple[str, bytes, str]:
    return (
        st.session_state.pdf_name or "uploaded.pdf",
        st.session_state.pdf_bytes,
        "application/pdf",
    )


def _fetch_page_text(page: int) -> tuple[str, int]:
    key = f"page_text::{page}"
    cached = st.session_state.reader_page_text_cache.get(key)
    if isinstance(cached, tuple) and len(cached) == 2:
        return cached
    files = {"file": _pdf_file_tuple()}
    data = {"page": str(page)}
    with httpx.Client(timeout=TIMEOUT_EXTRACT, trust_env=False) as client:
        r = client.post(f"{backend_url}/extract/page-text", files=files, data=data)
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:  # noqa: BLE001
            detail = r.text
        raise RuntimeError(f"获取第 {page} 页文本失败（HTTP {r.status_code}）：{detail}")
    body = r.json()
    text = str(body.get("text", ""))
    page_count = int(body.get("page_count", 0))
    st.session_state.reader_page_text_cache[key] = (text, page_count)
    return text, page_count


def _fetch_page_image(page: int, dpi: int) -> bytes:
    cache_key = f"page_image::{page}::{dpi}"
    cache = st.session_state.reader_page_image_cache
    if isinstance(cache, dict):
        hit = cache.get(cache_key)
        if isinstance(hit, (bytes, bytearray)):
            return bytes(hit)
    files = {"file": _pdf_file_tuple()}
    data = {"page": str(page), "dpi": str(dpi)}
    with httpx.Client(timeout=TIMEOUT_EXTRACT, trust_env=False) as client:
        r = client.post(f"{backend_url}/extract/page-image", files=files, data=data)
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:  # noqa: BLE001
            detail = r.text
        raise RuntimeError(f"渲染第 {page} 页图片失败（HTTP {r.status_code}）：{detail}")
    out = r.content
    if isinstance(cache, dict):
        cache[cache_key] = out
    return out


def _render_page_like(text: str, height: int = 780) -> None:
    safe = escape(text or "—")
    st.markdown(
        f"""
<div style="
    background: white;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 22px 26px;
    min-height: {height}px;
    max-height: {height}px;
    overflow: auto;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
">
  <div style="
      white-space: pre-wrap;
      line-height: 1.8;
      font-size: 16px;
      color: #222;
      font-family: 'Times New Roman', 'Noto Serif SC', serif;
  ">{safe}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def _http_detail(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("detail", resp.text))
    except Exception:  # noqa: BLE001
        return resp.text


def _api_err(component: str, status: int, detail: str) -> None:
    st.error(f"[{component}] HTTP {status}：{detail}")


def _render_page_like_html(text: str, height: int = 780) -> str:
    safe = escape(text or "—")
    return f"""
<div style="
    background: white;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 22px 26px;
    min-height: {height}px;
    max-height: {height}px;
    overflow: auto;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
">
  <div style="
      white-space: pre-wrap;
      line-height: 1.8;
      font-size: 16px;
      color: #222;
      font-family: 'Times New Roman', 'Noto Serif SC', serif;
  ">{safe}</div>
</div>
"""


def _iter_ndjson_events(resp: httpx.Response):
    for line in resp.iter_lines():
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _maybe_fragment(func):
    """若 Streamlit 支持 st.fragment，则仅重跑片段内控件，减轻整页灰态残影。"""
    deco = getattr(st, "fragment", None)
    if deco is not None:
        return deco(func)
    return func


def poll_background_jobs() -> None:
    """在整页控件渲染完成后调用：统一轮询翻译/分析/精读任务，最多一次 sleep + rerun。"""
    need_wait = False
    completed = False

    def _reading() -> None:
        nonlocal need_wait, completed
        rid = st.session_state.reading_job_id
        if not rid:
            st.session_state.reading_poll_ui = {}
            return
        elapsed_r = time.time() - float(st.session_state.reading_job_started_at or 0)
        if elapsed_r > MAX_READING_JOB_WAIT_SEC:
            st.session_state.reading_job_id = None
            st.session_state.reading_job_paper_id = None
            st.session_state.reading_poll_ui = {}
            st.error("精读任务等待超时，请重试。")
            return
        try:
            with httpx.Client(timeout=TIMEOUT_READING_JOB, trust_env=False) as client_s:
                r = client_s.get(f"{backend_url}/reading/job/{rid}")
            if r.status_code == 404:
                st.session_state.reading_job_id = None
                st.session_state.reading_job_paper_id = None
                st.session_state.reading_poll_ui = {}
                st.warning("精读任务已过期或不存在。")
                return
            if r.status_code != 200:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:  # noqa: BLE001
                    detail = r.text
                st.error(f"查询精读任务失败（HTTP {r.status_code}）：{detail}")
                return
            job = r.json()
            status = job.get("status", "")
            kind = job.get("kind", st.session_state.reading_job_kind)
            prog = int(job.get("progress") or 0)
            if status in ("queued", "running"):
                st.session_state.reading_poll_ui = {
                    "progress": prog,
                    "msg": (
                        f"精读（{kind}）：排队中…"
                        if status == "queued"
                        else f"精读（{kind}）：进行中…"
                    ),
                }
                need_wait = True
            elif status == "failed":
                st.error(job.get("error") or "任务失败")
                st.session_state.reading_job_id = None
                st.session_state.reading_job_paper_id = None
                st.session_state.reading_poll_ui = {}
            elif status == "done":
                with httpx.Client(timeout=TIMEOUT_READING, trust_env=False) as client_l:
                    rr = client_l.get(f"{backend_url}/reading/result/{rid}")
                if rr.status_code == 200:
                    body = rr.json()
                    st.session_state.reading_job_id = None
                    target_pid = st.session_state.reading_job_paper_id
                    st.session_state.reading_poll_ui = {}
                    if kind == "structure":
                        if target_pid and target_pid in st.session_state.papers:
                            st.session_state.papers[target_pid]["reading_structured_intent"] = body
                            st.session_state.papers[target_pid]["reading_last_recommendation"] = None
                            if target_pid == st.session_state.current_paper_id:
                                st.session_state.reading_structured_intent = body
                                st.session_state.reading_last_recommendation = None
                        else:
                            st.session_state.reading_structured_intent = body
                            st.session_state.reading_last_recommendation = None
                    elif kind == "recommend":
                        if target_pid and target_pid in st.session_state.papers:
                            st.session_state.papers[target_pid]["reading_last_recommendation"] = body
                            if target_pid == st.session_state.current_paper_id:
                                st.session_state.reading_last_recommendation = body
                        else:
                            st.session_state.reading_last_recommendation = body
                    elif kind == "advise":
                        if target_pid and target_pid in st.session_state.papers:
                            st.session_state.papers[target_pid]["reading_structured_intent"] = body.get(
                                "structured_intent"
                            )
                            st.session_state.papers[target_pid]["reading_last_recommendation"] = {
                                "recommendation": body.get("recommendation"),
                                "paper_chars_used": body.get("paper_chars_used", 0),
                            }
                            if target_pid == st.session_state.current_paper_id:
                                st.session_state.reading_structured_intent = body.get(
                                    "structured_intent"
                                )
                                st.session_state.reading_last_recommendation = {
                                    "recommendation": body.get("recommendation"),
                                    "paper_chars_used": body.get("paper_chars_used", 0),
                                }
                        else:
                            st.session_state.reading_structured_intent = body.get(
                                "structured_intent"
                            )
                            st.session_state.reading_last_recommendation = {
                                "recommendation": body.get("recommendation"),
                                "paper_chars_used": body.get("paper_chars_used", 0),
                            }
                    st.session_state.reading_job_paper_id = None
                    completed = True
                else:
                    try:
                        detail = rr.json().get("detail", rr.text)
                    except Exception:  # noqa: BLE001
                        detail = rr.text
                    st.error(f"获取精读结果失败（HTTP {rr.status_code}）：{detail}")
                    st.session_state.reading_job_id = None
                    st.session_state.reading_job_paper_id = None
                    st.session_state.reading_poll_ui = {}
            else:
                st.session_state.reading_poll_ui = {}
                st.warning(f"未知精读任务状态：{status}")
        except httpx.RequestError as e:
            st.error(f"精读轮询失败：{e}")

    def _analyze() -> None:
        nonlocal need_wait, completed
        jid = st.session_state.analyze_job_id
        if not jid:
            st.session_state.analyze_poll_ui = {}
            return
        elapsed = time.time() - float(st.session_state.analyze_job_started_at or 0)
        if elapsed > MAX_ANALYZE_JOB_WAIT_SEC:
            st.session_state.analyze_job_id = None
            st.session_state.analyze_poll_ui = {}
            st.error("分析等待超时，请重试或检查后端与模型服务。")
            return
        try:
            with httpx.Client(timeout=TIMEOUT_ANALYZE_JOB, trust_env=False) as client_s:
                r = client_s.get(f"{backend_url}/analyze/job/{jid}")
            if r.status_code == 404:
                st.session_state.analyze_job_id = None
                st.session_state.analyze_poll_ui = {}
                st.warning("分析任务已过期或不存在，请重新提交。")
                return
            if r.status_code != 200:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:  # noqa: BLE001
                    detail = r.text
                st.error(f"查询分析任务失败（HTTP {r.status_code}）：{detail}")
                return
            job = r.json()
            status = job.get("status", "")
            prog = int(job.get("progress") or 0)
            if status in ("queued", "running"):
                st.session_state.analyze_poll_ui = {
                    "progress": prog,
                    "msg": (
                        "全文分析：排队中（等待并发槽位）…"
                        if status == "queued"
                        else "全文分析：模型生成中…"
                    ),
                }
                need_wait = True
            elif status == "failed":
                st.error(job.get("error") or "分析失败")
                st.session_state.analyze_job_id = None
                st.session_state.analyze_poll_ui = {}
            elif status == "done":
                with httpx.Client(timeout=TIMEOUT_ANALYZE, trust_env=False) as client_l:
                    rr = client_l.get(f"{backend_url}/analyze/result/{jid}")
                if rr.status_code == 200:
                    st.session_state.analyze_result = rr.json()
                    st.session_state.analyze_job_id = None
                    st.session_state.analyze_poll_ui = {}
                    completed = True
                else:
                    try:
                        detail = rr.json().get("detail", rr.text)
                    except Exception:  # noqa: BLE001
                        detail = rr.text
                    st.error(f"获取分析结果失败（HTTP {rr.status_code}）：{detail}")
                    st.session_state.analyze_job_id = None
                    st.session_state.analyze_poll_ui = {}
            else:
                st.session_state.analyze_poll_ui = {}
                st.warning(f"未知分析任务状态：{status}")
        except httpx.RequestError as e:
            st.error(f"分析轮询失败：{e}")

    def _translate() -> None:
        nonlocal need_wait, completed
        tid = st.session_state.reader_translate_job_id
        if not tid:
            st.session_state.reader_poll_translate_ui = {}
            return
        elapsed_t = time.time() - float(st.session_state.reader_translate_job_started_at or 0)
        if elapsed_t > MAX_TRANSLATE_JOB_WAIT_SEC:
            st.session_state.reader_translate_job_id = None
            st.session_state.reader_poll_translate_ui = {}
            st.error("翻译等待超时，请重试。")
            return
        try:
            with httpx.Client(timeout=TIMEOUT_ANALYZE_JOB, trust_env=False) as client_s:
                r = client_s.get(f"{backend_url}/translate/job/{tid}")
            if r.status_code == 404:
                st.session_state.reader_translate_job_id = None
                st.session_state.reader_poll_translate_ui = {}
                st.warning("翻译任务已过期或不存在。")
                return
            if r.status_code != 200:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:  # noqa: BLE001
                    detail = r.text
                st.error(f"查询翻译任务失败（HTTP {r.status_code}）：{detail}")
                return
            job = r.json()
            status = job.get("status", "")
            prog = int(job.get("progress") or 0)
            if status in ("queued", "running"):
                st.session_state.reader_poll_translate_ui = {
                    "progress": prog,
                    "msg": (
                        "翻译：排队中…"
                        if status == "queued"
                        else "翻译：进行中…"
                    ),
                }
                need_wait = True
            elif status == "failed":
                st.error(job.get("error") or "翻译失败")
                st.session_state.reader_translate_job_id = None
                st.session_state.reader_poll_translate_ui = {}
            elif status == "done":
                ckey = st.session_state.reader_translate_cache_key or ""
                with httpx.Client(timeout=TIMEOUT_ANALYZE, trust_env=False) as client_l:
                    rr = client_l.get(f"{backend_url}/translate/result/{tid}")
                if rr.status_code == 200:
                    zh = str(rr.json().get("zh", "")).strip()
                    if ckey:
                        st.session_state.reader_translation_cache[ckey] = zh
                    st.session_state.reader_translate_job_id = None
                    st.session_state.reader_poll_translate_ui = {}
                    completed = True
                else:
                    try:
                        detail = rr.json().get("detail", rr.text)
                    except Exception:  # noqa: BLE001
                        detail = rr.text
                    st.error(f"获取翻译结果失败（HTTP {rr.status_code}）：{detail}")
                    st.session_state.reader_translate_job_id = None
                    st.session_state.reader_poll_translate_ui = {}
            else:
                st.session_state.reader_poll_translate_ui = {}
                st.warning(f"未知翻译任务状态：{status}")
        except httpx.RequestError as e:
            st.error(f"翻译轮询失败：{e}")

    _reading()
    _analyze()
    _translate()

    if completed:
        st.rerun()
    elif need_wait:
        time.sleep(ANALYZE_POLL_INTERVAL)
        st.rerun()


# --- 健康检查 ---
if st.button("检查后端健康 (/health)"):
    url = f"{backend_url}/health"
    try:
        with httpx.Client(timeout=TIMEOUT_HEALTH, trust_env=False) as client:
            r = client.get(url)
            r.raise_for_status()
            st.success("后端响应正常")
            st.json(r.json())
    except httpx.HTTPStatusError as e:
        hint = ""
        if e.response.status_code in (502, 503, 504):
            hint = (
                " （若你已启动 uvicorn 仍见此错误，多半是系统代理把本地请求转发到了公司代理；"
                "本页面已默认对本地后端关闭 `trust_env` 代理读取，若仍异常请检查 `.env` 里 `BACKEND_URL` "
                "或暂时关闭全局代理/VPN。）"
            )
        _api_err("健康检查", e.response.status_code, _http_detail(e.response) + hint)
    except httpx.RequestError as e:
        st.error(
            f"[健康检查] 无法连接 `{url}`。请先在该目录另开终端运行：\n\n"
            f"`uvicorn api.main:app --reload --port 8000`\n\n详情：{e}"
        )
else:
    st.info(
        "点击下方按钮测试与 FastAPI 的连通性。"
        f" 当前 `BACKEND_URL`：`{backend_url}`（可在 `.env` 中覆盖）。"
    )

st.divider()
st.subheader("抽取 PDF 正文（不经大模型）")
st.caption(
    "使用后端 **pypdf** 抽字；抽取结果会写入会话，供「全文分析」「精读建议」作为论文上下文。"
    " **URL / arXiv** 可后续再加。"
)

uploaded_files = st.file_uploader(
    "选择 PDF 文件（可多选）", type=["pdf"], accept_multiple_files=True, key="pdf_uploader"
)

if st.button("抽取正文", key="btn_extract"):
    if not uploaded_files:
        st.warning("请先选择 PDF 文件。")
    else:
        created_ids: list[str] = []
        post_url = f"{backend_url}/extract/file"

        with st.spinner("正在抽取 PDF 正文…"):
            with httpx.Client(timeout=TIMEOUT_EXTRACT, trust_env=False) as client:
                for uploaded in uploaded_files:
                    file_bytes = uploaded.getvalue()
                    paper_id = str(uuid.uuid4())
                    st.session_state.papers[paper_id] = _new_paper_entry(
                        paper_id=paper_id,
                        pdf_name=uploaded.name,
                        pdf_bytes=file_bytes,
                    )
                    created_ids.append(paper_id)

                    files = {
                        "file": (
                            uploaded.name,
                            file_bytes,
                            "application/pdf",
                        )
                    }
                    r = client.post(post_url, files=files)
                    if r.status_code != 200:
                        try:
                            err = r.json()
                            detail = err.get("detail", r.text)
                        except Exception:  # noqa: BLE001
                            detail = r.text
                        st.error(f"[抽取 PDF] {uploaded.name} 失败（HTTP {r.status_code}）：{detail}")
                        continue

                    data = r.json()
                    if data.get("warning"):
                        st.warning(f"[{uploaded.name}] {data['warning']}")

                    text = data.get("text", "")
                    paper = st.session_state.papers[paper_id]
                    paper["paper_text"] = text
                    inferred_len = len((text or "").strip())
                    paper["analyze_max_chars"] = min(100000, max(2000, inferred_len))
                    paper["reading_max_paper_chars"] = min(100000, max(2000, inferred_len))
                    paper["reader_current_page"] = 1
                    paper["reader_page_input"] = 1
                    paper["reader_nav_to_page"] = None
                    paper["reader_page_count"] = 0
                    paper["reader_page_text_cache"] = {}
                    paper["reader_translation_cache"] = {}
                    paper["reader_page_image_cache"] = {}

                    st.success(f"[{uploaded.name}] 抽取完成：共 {len(text)} 字")

        if created_ids:
            st.session_state.current_paper_id = created_ids[0]

        _bind_current_paper_to_session_state()

if st.session_state.papers:
    paper_ids = list(st.session_state.papers.keys())
    default_index = 0
    if st.session_state.current_paper_id in paper_ids:
        default_index = paper_ids.index(st.session_state.current_paper_id)
    st.caption(f"已加载论文：{len(paper_ids)} 篇")
    selected_id = st.radio(
        "切换当前论文（用于阅读器/翻译/填表/精读）",
        options=paper_ids,
        index=default_index,
        format_func=lambda pid: st.session_state.papers[pid]["pdf_name"],
        key="current_paper_picker",
    )
    # Persist active paper first, then switch binding to avoid losing unsynced outputs.
    previous_id = st.session_state.current_paper_id
    if previous_id and selected_id != previous_id:
        _persist_current_paper_from_session_state()
    st.session_state.current_paper_id = selected_id
    _bind_current_paper_to_session_state()

if st.session_state.paper_text:
    st.caption(f"当前会话已缓存论文文本：**{len(st.session_state.paper_text)}** 字符。")
    st.text_area("正文预览", value=st.session_state.paper_text[:PREVIEW_CHARS], height=420)

st.divider()
_jobs_open = bool(
    st.session_state.reader_translate_job_id
    or st.session_state.analyze_job_id
    or st.session_state.reading_job_id
)
with st.expander("后台任务状态（全局，页末统一轮询）", expanded=_jobs_open):
    st.caption("切换 Tab 不影响任务执行；进度由轮询更新。")
    if st.session_state.reader_translate_job_id:
        pt = st.session_state.reader_poll_translate_ui or {}
        st.progress(min(max(int(pt.get("progress") or 0), 0), 100) / 100.0)
        st.caption("翻译 · " + (pt.get("msg") or "已提交，等待状态更新…"))
    if st.session_state.analyze_job_id:
        pa = st.session_state.analyze_poll_ui or {}
        st.progress(min(max(int(pa.get("progress") or 0), 0), 100) / 100.0)
        st.caption("全文分析 · " + (pa.get("msg") or "已提交，等待状态更新…"))
    if st.session_state.reading_job_id:
        pr = st.session_state.reading_poll_ui or {}
        st.progress(min(max(int(pr.get("progress") or 0), 0), 100) / 100.0)
        st.caption("精读 · " + (pr.get("msg") or "已提交，等待状态更新…"))
    if not _jobs_open:
        st.caption("当前无进行中的后台任务。")

def _tab_reader_panel_impl():
    st.subheader("双栏阅读器（纯 Python：左图右译）")
    st.caption(
        "左侧按页渲染 PDF 图片，右侧显示整页中文翻译（页面阅读样式）。"
        " 「翻译本页」为**流式输出**；亦可使用下方全局后台任务轮询查看旧式异步翻译。"
        " 若为扫描版 PDF，整页文本抽取可能较弱。"
    )

    if not st.session_state.pdf_bytes:
        st.info("请先在上方上传并抽取 PDF，之后可在此进行按页阅读与翻译。")
    else:
        # Apply deferred navigation target before instantiating widgets.
        nav_target = st.session_state.get("reader_nav_to_page")
        if isinstance(nav_target, int) and nav_target >= 1:
            st.session_state.reader_current_page = nav_target
            st.session_state.reader_page_input = nav_target
            st.session_state.reader_nav_to_page = None

        c_page, c_dpi, c_cache = st.columns([1, 1, 1])
        with c_page:
            st.number_input(
                "当前页码",
                min_value=1,
                value=max(1, int(st.session_state.reader_page_input)),
                step=1,
                key="reader_page_input",
            )
        with c_dpi:
            page_dpi = st.slider(
                "页面清晰度(DPI)", min_value=96, max_value=260, value=160, step=8
            )
        with c_cache:
            if st.button("清空阅读器缓存", key="btn_clear_reader_cache"):
                st.session_state.reader_page_text_cache = {}
                st.session_state.reader_translation_cache = {}
                st.session_state.reader_page_image_cache = {}
                st.success("已清空页图、页文本与翻译缓存。")

        nav_l, nav_m, nav_r = st.columns([1, 1, 2])
        with nav_l:
            if st.button("上一页", key="btn_prev_page"):
                st.session_state.reader_nav_to_page = max(
                    1, int(st.session_state.reader_page_input) - 1
                )
                st.rerun()
        with nav_m:
            if st.button("下一页", key="btn_next_page"):
                next_page = int(st.session_state.reader_page_input) + 1
                max_page = st.session_state.reader_page_count or next_page
                st.session_state.reader_nav_to_page = min(next_page, max_page)
                st.rerun()
        with nav_r:
            st.session_state.reader_current_page = int(st.session_state.reader_page_input)
            if st.session_state.reader_page_count:
                st.caption(f"已知总页数：**{st.session_state.reader_page_count}**")
            else:
                st.caption("总页数将在首次拉取页文本或渲染后更新。")

        left, right = st.columns([1, 1])
        with left:
            st.markdown("#### 原文页图")
            try:
                image = _fetch_page_image(st.session_state.reader_current_page, page_dpi)
                st.image(image, width="stretch")
            except RuntimeError as e:
                st.error(str(e))
            except httpx.RequestError as e:
                st.error(f"[页图] 请求失败：{e}")

        with right:
            st.markdown("#### 中文页（整页翻译）")
            page_text = ""
            try:
                page_text, total = _fetch_page_text(st.session_state.reader_current_page)
                if total:
                    st.session_state.reader_page_count = total
            except RuntimeError as e:
                st.error(str(e))
            except httpx.RequestError as e:
                st.error(f"[页文] 请求失败：{e}")

            if not page_text.strip():
                st.warning("当前页未抽取到可用文本（可能是扫描页或图片页）。")
            else:
                page_cache_key = f"page::{st.session_state.reader_current_page}"
                rendered_stream_this_run = False
                if st.button("翻译本页", key="btn_translate_page"):
                    slot = st.empty()
                    pieces: list[str] = []
                    flush_chars = 40
                    staged = ""
                    stream_timeout = httpx.Timeout(connect=10.0, read=180.0, write=60.0, pool=10.0)
                    fallback_timeout = httpx.Timeout(connect=10.0, read=240.0, write=60.0, pool=10.0)

                    def _fallback_once() -> None:
                        with st.spinner("正在回退为一次性翻译…"):
                            with httpx.Client(timeout=fallback_timeout, trust_env=False) as client:
                                resp = client.post(
                                    f"{backend_url}/translate",
                                    json={"text": page_text, "mode": "page"},
                                )
                        if resp.status_code == 200:
                            final_zh = str(resp.json().get("zh", "")).strip()
                            if final_zh:
                                st.session_state.reader_translation_cache[page_cache_key] = final_zh
                                st.success("翻译完成（回退模式）。")
                            else:
                                st.warning("回退翻译返回为空。")
                        else:
                            _api_err("翻译本页（回退）", resp.status_code, _http_detail(resp))

                    try:
                        with st.spinner("正在流式翻译本页…"):
                            with httpx.Client(timeout=stream_timeout, trust_env=False) as client:
                                with client.stream(
                                    "POST",
                                    f"{backend_url}/translate/stream",
                                    json={"text": page_text, "mode": "page"},
                                ) as stream_resp:
                                    if stream_resp.status_code != 200:
                                        detail = _http_detail(stream_resp)
                                        raise RuntimeError(
                                            f"流式接口失败（HTTP {stream_resp.status_code}）：{detail}"
                                        )
                                    for chunk in stream_resp.iter_text():
                                        if not chunk:
                                            continue
                                        pieces.append(chunk)
                                        staged += chunk
                                        if len(staged) >= flush_chars:
                                            slot.markdown(
                                                _render_page_like_html("".join(pieces)),
                                                unsafe_allow_html=True,
                                            )
                                            rendered_stream_this_run = True
                                            staged = ""
                        if staged:
                            slot.markdown(
                                _render_page_like_html("".join(pieces)),
                                unsafe_allow_html=True,
                            )
                            rendered_stream_this_run = True
                        final_zh = "".join(pieces).strip()
                        if final_zh:
                            st.session_state.reader_translation_cache[page_cache_key] = final_zh
                            st.success("流式翻译完成。")
                        else:
                            st.warning("流式翻译未返回内容。")
                    except httpx.RequestError as e:
                        st.warning(f"流式翻译不可用，回退一次性接口。详情：{e}")
                        try:
                            _fallback_once()
                        except httpx.RequestError as ee:
                            st.error(f"[翻译本页（回退）] 无法连接后端。详情：{ee}")
                    except RuntimeError as e:
                        st.warning(f"{e}，回退一次性接口。")
                        try:
                            _fallback_once()
                        except httpx.RequestError as ee:
                            st.error(f"[翻译本页（回退）] 无法连接后端。详情：{ee}")

                cached_zh = st.session_state.reader_translation_cache.get(page_cache_key)
                if cached_zh:
                    if not rendered_stream_this_run:
                        _render_page_like(cached_zh)
                else:
                    st.info("点击“翻译本页”后，这里会显示与左侧对应的整页中文内容。")



    _persist_current_paper_from_session_state()


def _tab_analyze_panel_impl():
    st.subheader("逐篇填表（8维度 Markdown 表格，流式生成）")
    st.caption(
        "基于会话中的 **论文正文** 调用千问，按模板逐维度填写并只输出 Markdown 表格。"
        " 默认 **流式生成**；若输出失败会提示回退或报错。"
        " 需 **OPENAI_API_KEY**。超长正文仅截取前 N 字（见下方）。"
    )

    analyze_mode = st.radio(
        "分析深度",
        options=["full", "quick"],
        format_func=lambda x: "完整（更多关键句与段落对）" if x == "full" else "快速（较少条目）",
        horizontal=True,
        key="analyze_mode",
    )
    analyze_cap = st.number_input(
        "喂给模型的最大字符数（从正文开头截断）",
        min_value=2000,
        max_value=100000,
        value=14000,
        step=1000,
        key="analyze_max_chars",
    )
    rendered_table_stream_this_run = False
    rendered_note_stream_this_run = False

    if st.button("生成填表结果", key="btn_analyze"):
        if not st.session_state.paper_text.strip():
            st.warning("请先在上方抽取 PDF 正文，或自行粘贴到会话（当前为空）。")
        else:
            try:
                payload = {
                    "paper_text": st.session_state.paper_text,
                    "mode": analyze_mode,
                    "max_input_chars": int(analyze_cap),
                }
                stream_slot = st.empty()
                stream_text: list[str] = []
                final_data: dict | None = None
                stream_timeout = httpx.Timeout(connect=10.0, read=240.0, write=60.0, pool=10.0)
                with st.spinner("正在流式生成填表结果…"):
                    with httpx.Client(timeout=stream_timeout, trust_env=False) as client:
                        with client.stream(
                            "POST",
                            f"{backend_url}/analyze/table/stream",
                            json=payload,
                        ) as r:
                            if r.status_code != 200:
                                _api_err("全文分析", r.status_code, _http_detail(r))
                            else:
                                for event in _iter_ndjson_events(r):
                                    et = event.get("type")
                                    if et == "delta":
                                        piece = str(event.get("text", ""))
                                        if piece:
                                            stream_text.append(piece)
                                            stream_slot.markdown("".join(stream_text))
                                            rendered_table_stream_this_run = True
                                    elif et == "final":
                                        final_data = event.get("data")
                                        break
                                    elif et == "error":
                                        st.error(f"[全文分析流式] {event.get('detail', '未知错误')}")
                                        break
                if isinstance(final_data, dict):
                    table_md = str(final_data.get("table_markdown", ""))
                    st.session_state.analyze_table_markdown = table_md
                    pid = st.session_state.get("current_paper_id")
                    if pid and pid in st.session_state.papers:
                        st.session_state.papers[pid]["analyze_table_markdown"] = table_md
                    _persist_current_paper_from_session_state()
                    st.success("填表结果完成。")
            except httpx.RequestError as e:
                st.error(f"[全文分析] 无法连接后端。详情：{e}")

    if st.session_state.analyze_table_markdown and not rendered_table_stream_this_run:
        with st.expander("填表结果（Markdown 表格）", expanded=True):
            st.markdown(st.session_state.analyze_table_markdown)

    if st.button("生成 PaperNote 笔记", key="btn_papernote"):
        if not st.session_state.paper_text.strip():
            st.warning("请先在上方抽取 PDF 正文，或自行粘贴到会话（当前为空）。")
        else:
            try:
                payload = {
                    "paper_text": st.session_state.paper_text,
                    "mode": analyze_mode,
                    "max_input_chars": int(analyze_cap),
                }
                stream_slot = st.empty()
                stream_text: list[str] = []
                final_data: dict | None = None
                note_timeout = httpx.Timeout(connect=10.0, read=240.0, write=60.0, pool=10.0)
                with st.spinner("正在流式生成 PaperNote 笔记…"):
                    with httpx.Client(timeout=note_timeout, trust_env=False) as client:
                        with client.stream(
                            "POST",
                            f"{backend_url}/analyze/papernote/stream",
                            json=payload,
                        ) as r:
                            if r.status_code != 200:
                                _api_err("PaperNote", r.status_code, _http_detail(r))
                            else:
                                for event in _iter_ndjson_events(r):
                                    et = event.get("type")
                                    if et == "delta":
                                        piece = str(event.get("text", ""))
                                        if piece:
                                            stream_text.append(piece)
                                            with stream_slot.container(border=True):
                                                st.markdown("".join(stream_text))
                                            rendered_note_stream_this_run = True
                                    elif et == "final":
                                        final_data = event.get("data")
                                        break
                                    elif et == "error":
                                        st.error(f"[PaperNote 流式] {event.get('detail', '未知错误')}")
                                        break
                if isinstance(final_data, dict):
                    note_md = str(final_data.get("papernote_markdown", ""))
                    st.session_state.papernote_markdown = note_md
                    # Write-through to per-paper store immediately so “综合综述” can see it without switching.
                    pid = st.session_state.get("current_paper_id")
                    if pid and pid in st.session_state.papers:
                        st.session_state.papers[pid]["papernote_markdown"] = note_md
                    _persist_current_paper_from_session_state()
                    st.session_state.papernote_just_generated = True
                    st.success("PaperNote 笔记完成。")
                    st.rerun()
            except httpx.RequestError as e:
                st.error(f"[PaperNote] 无法连接后端。详情：{e}")

    if st.session_state.papernote_markdown and not rendered_note_stream_this_run:
        expand_note = bool(st.session_state.get("papernote_just_generated", False))
        with st.expander("PaperNote 笔记（Markdown）", expanded=expand_note):
            with st.container(border=True):
                st.markdown(st.session_state.papernote_markdown)
            st.download_button(
                label="下载 PaperNote Markdown",
                data=str(st.session_state.papernote_markdown).encode("utf-8"),
                file_name="paperpilot_papernote.md",
                mime="text/markdown",
                key="download_papernote_md",
            )
        if expand_note:
            st.session_state.papernote_just_generated = False

    st.caption("综合文献综述已拆分到独立模块「综合综述」，并且只基于 PaperNote 笔记生成。")



    _persist_current_paper_from_session_state()


def _tab_review_panel_impl():
    st.subheader("综合文献综述（基于 PaperNote）")
    st.caption(
        "该模块仅汇总各论文的 PaperNote 笔记。"
        " 请先为至少两篇论文生成 PaperNote，再执行综合综述。"
    )
    rendered_review_stream_this_run = False
    # Ensure currently opened paper's latest in-memory note is included in aggregation.
    _persist_current_paper_from_session_state()

    # Extra write-through: in fragment-rerun situations, the global note may update
    # but per-paper cache might not yet. Ensure we count the current paper correctly.
    active_pid = st.session_state.get("current_paper_id")
    active_note = st.session_state.get("papernote_markdown", "")
    if active_pid and active_pid in st.session_state.papers:
        if active_note and not str(st.session_state.papers[active_pid].get("papernote_markdown", "")):
            st.session_state.papers[active_pid]["papernote_markdown"] = active_note
            _persist_current_paper_from_session_state()

    available_notes: list[str] = []
    ready_ids: list[str] = []
    ready_names: list[str] = []
    missing_names: list[str] = []
    for pid in st.session_state.papers.keys():
        name = st.session_state.papers[pid].get("pdf_name", pid)
        note_md = st.session_state.papers[pid].get("papernote_markdown", "")
        if pid == active_pid and active_note and not str(note_md).strip():
            note_md = active_note
        if note_md and str(note_md).strip():
            available_notes.append(str(note_md))
            ready_ids.append(str(pid))
            ready_names.append(str(name))
        else:
            missing_names.append(str(name))

    if ready_names:
        st.caption("已具备 PaperNote 的论文：")
        st.write("、".join(ready_names))
    if missing_names:
        st.caption("尚未生成 PaperNote 的论文：")
        st.write("、".join(missing_names))

    selected_ids: list[str] = []
    if ready_ids:
        prev_ready_ids = set(st.session_state.get("review_selectable_papers", []))
        curr_ready_ids = set(ready_ids)
        current_selected = [
            pid
            for pid in st.session_state.get("review_selected_papers", [])
            if pid in curr_ready_ids
        ]
        # Auto-include newly available papers so users don't get stuck at <2 after fresh analyses.
        newly_available = [pid for pid in ready_ids if pid in (curr_ready_ids - prev_ready_ids)]
        merged_selected = current_selected + [pid for pid in newly_available if pid not in current_selected]
        if not merged_selected:
            merged_selected = list(ready_ids)
        st.session_state.review_selected_papers = merged_selected
        st.session_state.review_selectable_papers = list(ready_ids)

        selected_ids = st.multiselect(
            "勾选要参与综合综述的论文",
            options=ready_ids,
            default=st.session_state.review_selected_papers,
            format_func=lambda pid: st.session_state.papers[pid].get("pdf_name", pid),
            key="review_selected_papers",
        )

    selected_notes: list[str] = []
    for pid in selected_ids:
        note_md = st.session_state.papers.get(pid, {}).get("papernote_markdown", "")
        if note_md and str(note_md).strip():
            selected_notes.append(str(note_md))

    if len(selected_notes) < 2:
        st.info("当前可用于综述的 PaperNote 少于 2 篇。请先切换论文并生成 PaperNote 笔记。")
    else:
        st.caption(f"当前已勾选用于综述的 PaperNote：{len(selected_notes)} 篇")
        if st.button("生成综合文献综述", key="btn_review"):
            try:
                stream_slot = st.empty()
                stream_text = []
                final_data: dict | None = None
                review_timeout = httpx.Timeout(connect=10.0, read=240.0, write=60.0, pool=10.0)
                with st.spinner("正在流式生成综合文献综述…"):
                    with httpx.Client(timeout=review_timeout, trust_env=False) as client:
                        with client.stream(
                            "POST",
                            f"{backend_url}/review/stream",
                            json={"papernotes": selected_notes},
                        ) as r:
                            if r.status_code != 200:
                                _api_err("综合综述", r.status_code, _http_detail(r))
                            else:
                                for event in _iter_ndjson_events(r):
                                    et = event.get("type")
                                    if et == "delta":
                                        piece = str(event.get("text", ""))
                                        if piece:
                                            stream_text.append(piece)
                                            with stream_slot.container(border=True):
                                                st.markdown("".join(stream_text))
                                            rendered_review_stream_this_run = True
                                    elif et == "final":
                                        final_data = event.get("data")
                                        break
                                    elif et == "error":
                                        st.error(f"[综合综述流式] {event.get('detail', '未知错误')}")
                                        break
                if isinstance(final_data, dict):
                    st.session_state.review_markdown = str(
                        final_data.get("review_markdown", "")
                    )
                    st.success("综合文献综述完成。")
            except httpx.RequestError as e:
                st.error(f"[综合综述] 无法连接后端。详情：{e}")

    if st.session_state.review_markdown and not rendered_review_stream_this_run:
        with st.expander("综合文献综述（Markdown）", expanded=True):
            with st.container(border=True):
                st.markdown(st.session_state.review_markdown)
            st.download_button(
                label="下载综述 Markdown",
                data=str(st.session_state.review_markdown).encode("utf-8"),
                file_name="paperpilot_review.md",
                mime="text/markdown",
                key="download_review_md",
            )


def _tab_reading_panel_impl():
    st.subheader("精读建议（千问 · 结构化需求）")
    st.caption(
        "流程：**自然语言 → 结构化 JSON（唯一意图依据）→ 结合论文摘录给出是否精读**。"
        " 后续推理**不直接使用**你的原始句子，只使用结构化结果。"
        " 「生成精读建议 / 一键」为 **流式输出**；「结构化需求」仍可走异步任务 + 上方轮询。"
        " 需在 `.env` 配置 **OPENAI_API_KEY**（可配合 DashScope 兼容模式），并 `pip install openai`。"
    )

    user_prompt = st.text_area(
        "你为什么读这篇论文？想得到什么启发或内容？（可写得模糊，先做结构化）",
        height=120,
        key="user_reading_prompt",
    )

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        do_structure = st.button("1 · 结构化需求", key="btn_structure")
    with col_b:
        do_recommend = st.button("2 · 生成精读建议", key="btn_recommend")
    with col_c:
        do_pipeline = st.button("一键：结构化 + 建议", key="btn_pipeline")

    max_chars = st.number_input(
        "喂给模型的最大论文字符数",
        min_value=2000,
        max_value=100000,
        value=12000,
        step=1000,
        key="reading_max_paper_chars",
    )

    if do_structure:
        if not user_prompt.strip():
            st.warning("请先填写上面的阅读动机/需求。")
        else:
            try:
                with st.spinner("正在提交结构化需求任务…"):
                    with httpx.Client(timeout=30.0, trust_env=False) as client:
                        r = client.post(
                            f"{backend_url}/reading/structure-intent/submit",
                            json={"user_prompt": user_prompt.strip()},
                        )
                if r.status_code == 200:
                    st.session_state.reading_job_id = r.json().get("job_id")
                    st.session_state.reading_job_kind = "structure"
                    st.session_state.reading_job_started_at = time.time()
                    st.session_state.reading_job_paper_id = st.session_state.current_paper_id
                    st.success("已提交结构化任务…")
                    st.rerun()
                else:
                    _api_err("结构化需求", r.status_code, _http_detail(r))
            except httpx.RequestError as e:
                st.error(f"[结构化需求] 无法连接后端。详情：{e}")

    if do_recommend:
        if not st.session_state.reading_structured_intent:
            st.warning("请先点击「1 · 结构化需求」，或直接用「一键」。")
        else:
            try:
                payload = {
                    "structured_intent": st.session_state.reading_structured_intent,
                    "paper_text": st.session_state.paper_text,
                    "max_paper_chars": int(max_chars),
                }
                stream_slot = st.empty()
                stream_text: list[str] = []
                final_data = None
                stream_timeout = httpx.Timeout(connect=10.0, read=240.0, write=60.0, pool=10.0)
                with st.spinner("正在流式生成精读建议…"):
                    with httpx.Client(timeout=stream_timeout, trust_env=False) as client:
                        with client.stream(
                            "POST",
                            f"{backend_url}/reading/recommend/stream",
                            json=payload,
                        ) as r:
                            if r.status_code != 200:
                                _api_err("精读建议", r.status_code, _http_detail(r))
                            else:
                                for event in _iter_ndjson_events(r):
                                    et = event.get("type")
                                    if et == "delta":
                                        piece = str(event.get("text", ""))
                                        if piece:
                                            stream_text.append(piece)
                                            stream_slot.code("".join(stream_text), language="json")
                                    elif et == "final":
                                        final_data = event.get("data")
                                        break
                                    elif et == "error":
                                        st.error(f"[精读建议流式] {event.get('detail', '未知错误')}")
                                        break
                if isinstance(final_data, dict):
                    st.session_state.reading_last_recommendation = final_data
                    st.success("精读建议完成。")
            except httpx.RequestError as e:
                st.error(f"[精读建议] 无法连接后端。详情：{e}")

    if do_pipeline:
        if not user_prompt.strip():
            st.warning("请先填写阅读动机/需求。")
        else:
            try:
                stream_slot = st.empty()
                stream_text: list[str] = []
                final_data = None
                stream_timeout = httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0)
                with st.spinner("正在流式执行一键精读…"):
                    with httpx.Client(timeout=stream_timeout, trust_env=False) as client:
                        with client.stream(
                            "POST",
                            f"{backend_url}/reading/advise/stream",
                            json={
                                "user_prompt": user_prompt.strip(),
                                "paper_text": st.session_state.paper_text,
                                "max_paper_chars": int(max_chars),
                            },
                        ) as r:
                            if r.status_code != 200:
                                _api_err("一键精读", r.status_code, _http_detail(r))
                            else:
                                for event in _iter_ndjson_events(r):
                                    et = event.get("type")
                                    if et == "stage" and event.get("name") == "structured_intent_ready":
                                        data = event.get("data")
                                        if isinstance(data, dict):
                                            st.session_state.reading_structured_intent = data
                                    elif et == "delta":
                                        piece = str(event.get("text", ""))
                                        if piece:
                                            stream_text.append(piece)
                                            stream_slot.code("".join(stream_text), language="json")
                                    elif et == "final":
                                        final_data = event.get("data")
                                        break
                                    elif et == "error":
                                        st.error(f"[一键精读流式] {event.get('detail', '未知错误')}")
                                        break
                if isinstance(final_data, dict):
                    st.session_state.reading_structured_intent = final_data.get("structured_intent")
                    st.session_state.reading_last_recommendation = {
                        "recommendation": final_data.get("recommendation"),
                        "paper_chars_used": final_data.get("paper_chars_used", 0),
                    }
                    st.success("一键精读完成。")
            except httpx.RequestError as e:
                st.error(f"[一键精读] 无法连接后端。详情：{e}")

    if st.session_state.reading_last_recommendation:
        body = st.session_state.reading_last_recommendation
        used = body.get("paper_chars_used", 0)
        st.caption(f"论文摘录使用：**{used}** 字符。")
        with st.expander("精读建议正文", expanded=True):
            st.markdown(_fmt_recommendation(body))
        with st.expander("原始 JSON（recommendation）", expanded=False):
            st.json(body.get("recommendation", body))

    if st.session_state.reading_structured_intent and not (do_structure or do_pipeline):
        with st.expander("当前会话中的结构化需求", expanded=False):
            st.json(st.session_state.reading_structured_intent)

    _persist_current_paper_from_session_state()


_tab_reader_panel = _maybe_fragment(_tab_reader_panel_impl)
_tab_analyze_panel = _maybe_fragment(_tab_analyze_panel_impl)
# 综合综述需要在切 Tab 时立即读取最新 per-paper 状态；
# st.fragment 可能导致缓存不刷新，因此这里不做 fragment 隔离。
_tab_review_panel = _tab_review_panel_impl
_tab_reading_panel = _maybe_fragment(_tab_reading_panel_impl)

tab_options = ["双栏阅读器", "全文分析", "综合综述", "精读建议"]
if "active_module" not in st.session_state:
    st.session_state.active_module = "双栏阅读器"

segmented = getattr(st, "segmented_control", None)
if segmented is not None:
    active_module = segmented(
        "模块导航",
        options=tab_options,
        selection_mode="single",
        default=st.session_state.active_module,
        key="active_module",
    )
else:
    active_module = st.radio(
        "模块导航",
        options=tab_options,
        horizontal=True,
        key="active_module",
    )

if active_module == "双栏阅读器":
    _tab_reader_panel()
elif active_module == "全文分析":
    _tab_analyze_panel()
elif active_module == "综合综述":
    _tab_review_panel()
else:
    _tab_reading_panel()

_persist_current_paper_from_session_state()
poll_background_jobs()
