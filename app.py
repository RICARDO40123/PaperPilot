"""PaperPilot Streamlit UI — thin client calling FastAPI."""

import os
import time
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
if "structured_intent" not in st.session_state:
    st.session_state.structured_intent = None
if "last_recommendation" not in st.session_state:
    st.session_state.last_recommendation = None
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "show_bilingual_panel" not in st.session_state:
    st.session_state.show_bilingual_panel = False
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
if "page_text_cache" not in st.session_state:
    st.session_state.page_text_cache = {}
if "translation_cache" not in st.session_state:
    st.session_state.translation_cache = {}
if "analyze_job_id" not in st.session_state:
    st.session_state.analyze_job_id = None
if "analyze_job_started_at" not in st.session_state:
    st.session_state.analyze_job_started_at = 0.0
if "translate_job_id" not in st.session_state:
    st.session_state.translate_job_id = None
if "translate_job_started_at" not in st.session_state:
    st.session_state.translate_job_started_at = 0.0
if "translate_job_cache_key" not in st.session_state:
    st.session_state.translate_job_cache_key = ""
if "reading_job_id" not in st.session_state:
    st.session_state.reading_job_id = None
if "reading_job_started_at" not in st.session_state:
    st.session_state.reading_job_started_at = 0.0
if "reading_job_kind" not in st.session_state:
    st.session_state.reading_job_kind = ""
if "poll_translate_ui" not in st.session_state:
    st.session_state.poll_translate_ui = {}
if "poll_analyze_ui" not in st.session_state:
    st.session_state.poll_analyze_ui = {}
if "poll_reading_ui" not in st.session_state:
    st.session_state.poll_reading_ui = {}


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
    cached = st.session_state.page_text_cache.get(key)
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
    st.session_state.page_text_cache[key] = (text, page_count)
    return text, page_count


def _fetch_page_image(page: int, dpi: int) -> bytes:
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
    return r.content


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


def poll_background_jobs() -> None:
    """在整页控件渲染完成后调用：统一轮询翻译/分析/精读任务，最多一次 sleep + rerun。"""
    need_wait = False
    completed = False

    def _reading() -> None:
        nonlocal need_wait, completed
        rid = st.session_state.reading_job_id
        if not rid:
            st.session_state.poll_reading_ui = {}
            return
        elapsed_r = time.time() - float(st.session_state.reading_job_started_at or 0)
        if elapsed_r > MAX_READING_JOB_WAIT_SEC:
            st.session_state.reading_job_id = None
            st.session_state.poll_reading_ui = {}
            st.error("精读任务等待超时，请重试。")
            return
        try:
            with httpx.Client(timeout=TIMEOUT_READING_JOB, trust_env=False) as client_s:
                r = client_s.get(f"{backend_url}/reading/job/{rid}")
            if r.status_code == 404:
                st.session_state.reading_job_id = None
                st.session_state.poll_reading_ui = {}
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
                st.session_state.poll_reading_ui = {
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
                st.session_state.poll_reading_ui = {}
            elif status == "done":
                with httpx.Client(timeout=TIMEOUT_READING, trust_env=False) as client_l:
                    rr = client_l.get(f"{backend_url}/reading/result/{rid}")
                if rr.status_code == 200:
                    body = rr.json()
                    st.session_state.reading_job_id = None
                    st.session_state.poll_reading_ui = {}
                    if kind == "structure":
                        st.session_state.structured_intent = body
                        st.session_state.last_recommendation = None
                    elif kind == "recommend":
                        st.session_state.last_recommendation = body
                    elif kind == "advise":
                        st.session_state.structured_intent = body.get("structured_intent")
                        st.session_state.last_recommendation = {
                            "recommendation": body.get("recommendation"),
                            "paper_chars_used": body.get("paper_chars_used", 0),
                        }
                    completed = True
                else:
                    try:
                        detail = rr.json().get("detail", rr.text)
                    except Exception:  # noqa: BLE001
                        detail = rr.text
                    st.error(f"获取精读结果失败（HTTP {rr.status_code}）：{detail}")
                    st.session_state.reading_job_id = None
                    st.session_state.poll_reading_ui = {}
            else:
                st.session_state.poll_reading_ui = {}
                st.warning(f"未知精读任务状态：{status}")
        except httpx.RequestError as e:
            st.error(f"精读轮询失败：{e}")

    def _analyze() -> None:
        nonlocal need_wait, completed
        jid = st.session_state.analyze_job_id
        if not jid:
            st.session_state.poll_analyze_ui = {}
            return
        elapsed = time.time() - float(st.session_state.analyze_job_started_at or 0)
        if elapsed > MAX_ANALYZE_JOB_WAIT_SEC:
            st.session_state.analyze_job_id = None
            st.session_state.poll_analyze_ui = {}
            st.error("分析等待超时，请重试或检查后端与模型服务。")
            return
        try:
            with httpx.Client(timeout=TIMEOUT_ANALYZE_JOB, trust_env=False) as client_s:
                r = client_s.get(f"{backend_url}/analyze/job/{jid}")
            if r.status_code == 404:
                st.session_state.analyze_job_id = None
                st.session_state.poll_analyze_ui = {}
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
                st.session_state.poll_analyze_ui = {
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
                st.session_state.poll_analyze_ui = {}
            elif status == "done":
                with httpx.Client(timeout=TIMEOUT_ANALYZE, trust_env=False) as client_l:
                    rr = client_l.get(f"{backend_url}/analyze/result/{jid}")
                if rr.status_code == 200:
                    st.session_state.analysis_result = rr.json()
                    st.session_state.analyze_job_id = None
                    st.session_state.poll_analyze_ui = {}
                    completed = True
                else:
                    try:
                        detail = rr.json().get("detail", rr.text)
                    except Exception:  # noqa: BLE001
                        detail = rr.text
                    st.error(f"获取分析结果失败（HTTP {rr.status_code}）：{detail}")
                    st.session_state.analyze_job_id = None
                    st.session_state.poll_analyze_ui = {}
            else:
                st.session_state.poll_analyze_ui = {}
                st.warning(f"未知分析任务状态：{status}")
        except httpx.RequestError as e:
            st.error(f"分析轮询失败：{e}")

    def _translate() -> None:
        nonlocal need_wait, completed
        tid = st.session_state.translate_job_id
        if not tid:
            st.session_state.poll_translate_ui = {}
            return
        elapsed_t = time.time() - float(st.session_state.translate_job_started_at or 0)
        if elapsed_t > MAX_TRANSLATE_JOB_WAIT_SEC:
            st.session_state.translate_job_id = None
            st.session_state.poll_translate_ui = {}
            st.error("翻译等待超时，请重试。")
            return
        try:
            with httpx.Client(timeout=TIMEOUT_ANALYZE_JOB, trust_env=False) as client_s:
                r = client_s.get(f"{backend_url}/translate/job/{tid}")
            if r.status_code == 404:
                st.session_state.translate_job_id = None
                st.session_state.poll_translate_ui = {}
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
                st.session_state.poll_translate_ui = {
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
                st.session_state.translate_job_id = None
                st.session_state.poll_translate_ui = {}
            elif status == "done":
                ckey = st.session_state.translate_job_cache_key or ""
                with httpx.Client(timeout=TIMEOUT_ANALYZE, trust_env=False) as client_l:
                    rr = client_l.get(f"{backend_url}/translate/result/{tid}")
                if rr.status_code == 200:
                    zh = str(rr.json().get("zh", "")).strip()
                    if ckey:
                        st.session_state.translation_cache[ckey] = zh
                    st.session_state.translate_job_id = None
                    st.session_state.poll_translate_ui = {}
                    completed = True
                else:
                    try:
                        detail = rr.json().get("detail", rr.text)
                    except Exception:  # noqa: BLE001
                        detail = rr.text
                    st.error(f"获取翻译结果失败（HTTP {rr.status_code}）：{detail}")
                    st.session_state.translate_job_id = None
                    st.session_state.poll_translate_ui = {}
            else:
                st.session_state.poll_translate_ui = {}
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
        st.error(f"HTTP 错误: {e.response.status_code} — {e.response.text}{hint}")
    except httpx.RequestError as e:
        st.error(
            f"无法连接后端 `{url}`。请先在该目录另开终端运行：\n\n"
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

uploaded = st.file_uploader("选择 PDF 文件", type=["pdf"], key="pdf_uploader")

if st.button("抽取正文", key="btn_extract"):
    if not uploaded:
        st.warning("请先选择 PDF 文件。")
    else:
        file_bytes = uploaded.getvalue()
        files = {
            "file": (
                uploaded.name,
                file_bytes,
                "application/pdf",
            )
        }
        post_url = f"{backend_url}/extract/file"
        try:
            with httpx.Client(timeout=TIMEOUT_EXTRACT, trust_env=False) as client:
                r = client.post(post_url, files=files)
            if r.status_code == 200:
                data = r.json()
                st.success(f"**pdf_quality**：{data.get('pdf_quality', '')}")
                if data.get("warning"):
                    st.warning(data["warning"])
                text = data.get("text", "")
                st.session_state.pdf_bytes = file_bytes
                st.session_state.pdf_name = uploaded.name
                st.session_state.reader_current_page = 1
                st.session_state.reader_page_input = 1
                st.session_state.reader_nav_to_page = None
                st.session_state.reader_page_count = 0
                st.session_state.page_text_cache = {}
                st.session_state.translation_cache = {}
                st.session_state.paper_text = text
                st.caption(
                    f"共 **{len(text)}** 个字符（已保存到会话）；下方预览前 **{PREVIEW_CHARS}** 字。"
                )
                st.text_area("正文预览", value=text[:PREVIEW_CHARS], height=420)
            else:
                try:
                    err = r.json()
                    detail = err.get("detail", r.text)
                except Exception:  # noqa: BLE001
                    detail = r.text
                st.error(f"抽取失败（HTTP {r.status_code}）：{detail}")
        except httpx.RequestError as e:
            st.error(
                f"无法连接后端 `{post_url}`。请确认已运行 `uvicorn api.main:app --port 8000`。\n\n详情：{e}"
            )

if st.session_state.paper_text:
    st.caption(f"当前会话已缓存论文文本：**{len(st.session_state.paper_text)}** 字符。")

st.divider()
st.subheader("双栏阅读器（纯 Python：左图右译）")
st.caption(
    "左侧按页渲染 PDF 图片，右侧显示整页中文翻译（页面阅读样式）。"
    " 「翻译本页」为后台任务 + 轮询，避免长时间卡住界面。"
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
        page_dpi = st.slider("页面清晰度(DPI)", min_value=96, max_value=260, value=160, step=8)
    with c_cache:
        if st.button("清空阅读器缓存", key="btn_clear_reader_cache"):
            st.session_state.page_text_cache = {}
            st.session_state.translation_cache = {}
            st.success("已清空页文本与翻译缓存。")

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
            st.error(f"请求失败：{e}")

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
            st.error(f"请求失败：{e}")

        if not page_text.strip():
            st.warning("当前页未抽取到可用文本（可能是扫描页或图片页）。")
        else:
            page_cache_key = f"page::{st.session_state.reader_current_page}"
            if st.button("翻译本页", key="btn_translate_page"):
                try:
                    with httpx.Client(timeout=30.0, trust_env=False) as client:
                        r = client.post(
                            f"{backend_url}/translate/submit",
                            json={"text": page_text, "mode": "page"},
                        )
                    if r.status_code == 200:
                        st.session_state.translate_job_id = r.json().get("job_id")
                        st.session_state.translate_job_started_at = time.time()
                        st.session_state.translate_job_cache_key = page_cache_key
                        st.success("已提交翻译任务…")
                        st.rerun()
                    else:
                        try:
                            detail = r.json().get("detail", r.text)
                        except Exception:  # noqa: BLE001
                            detail = r.text
                        st.error(f"提交翻译失败（HTTP {r.status_code}）：{detail}")
                except httpx.RequestError as e:
                    st.error(f"请求失败：{e}")

            if st.session_state.translation_cache.get(page_cache_key):
                _render_page_like(st.session_state.translation_cache.get(page_cache_key, ""))
            else:
                st.info("点击“翻译本页”后，这里会显示与左侧对应的整页中文内容。")

if st.session_state.translate_job_id:
    pt = st.session_state.poll_translate_ui or {}
    st.progress(min(max(int(pt.get("progress") or 0), 0), 100) / 100.0)
    st.caption(pt.get("msg") or "翻译：已提交，等待状态更新…")

st.divider()
st.subheader("全文分析（千问 · 异步任务）")
st.caption(
    "基于会话中的 **论文正文** 调用千问，生成概括、关键句点评与段落对照。"
    " 提交后后台执行，页面会轮询状态；需 **OPENAI_API_KEY**。超长正文仅截取前 N 字（见下方）。"
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

if st.button("生成全文分析", key="btn_analyze"):
    if not st.session_state.paper_text.strip():
        st.warning("请先在上方抽取 PDF 正文，或自行粘贴到会话（当前为空）。")
    else:
        try:
            payload = {
                "paper_text": st.session_state.paper_text,
                "mode": analyze_mode,
                "max_input_chars": int(analyze_cap),
            }
            with httpx.Client(timeout=30.0, trust_env=False) as client:
                r = client.post(f"{backend_url}/analyze/submit", json=payload)
            if r.status_code == 200:
                body = r.json()
                st.session_state.analyze_job_id = body.get("job_id")
                st.session_state.analyze_job_started_at = time.time()
                st.success("已提交分析任务，正在排队/执行…")
                st.rerun()
            else:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:  # noqa: BLE001
                    detail = r.text
                st.error(f"提交失败（HTTP {r.status_code}）：{detail}")
        except httpx.RequestError as e:
            st.error(f"请求失败：{e}")

if st.session_state.analyze_job_id:
    pa = st.session_state.poll_analyze_ui or {}
    st.progress(min(max(int(pa.get("progress") or 0), 0), 100) / 100.0)
    st.caption(pa.get("msg") or "全文分析：已提交，等待状态更新…")

analysis_data = st.session_state.analysis_result
if analysis_data:
    st.markdown("### 分析结果")
    _render_analysis_result(analysis_data)

st.divider()
st.subheader("精读建议（千问 · 结构化需求）")
st.caption(
    "流程：**自然语言 → 结构化 JSON（唯一意图依据）→ 结合论文摘录给出是否精读**。"
    " 后续推理**不直接使用**你的原始句子，只使用结构化结果。"
    " 以下为后台任务 + 轮询，避免长时间卡住界面。"
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
)

if do_structure:
    if not user_prompt.strip():
        st.warning("请先填写上面的阅读动机/需求。")
    else:
        try:
            with httpx.Client(timeout=30.0, trust_env=False) as client:
                r = client.post(
                    f"{backend_url}/reading/structure-intent/submit",
                    json={"user_prompt": user_prompt.strip()},
                )
            if r.status_code == 200:
                st.session_state.reading_job_id = r.json().get("job_id")
                st.session_state.reading_job_kind = "structure"
                st.session_state.reading_job_started_at = time.time()
                st.success("已提交结构化任务…")
                st.rerun()
            else:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:  # noqa: BLE001
                    detail = r.text
                st.error(f"提交失败（HTTP {r.status_code}）：{detail}")
        except httpx.RequestError as e:
            st.error(f"请求失败：{e}")

if do_recommend:
    if not st.session_state.structured_intent:
        st.warning("请先点击「1 · 结构化需求」，或直接用「一键」。")
    else:
        try:
            payload = {
                "structured_intent": st.session_state.structured_intent,
                "paper_text": st.session_state.paper_text,
                "max_paper_chars": int(max_chars),
            }
            with httpx.Client(timeout=30.0, trust_env=False) as client:
                r = client.post(
                    f"{backend_url}/reading/recommend/submit",
                    json=payload,
                )
            if r.status_code == 200:
                st.session_state.reading_job_id = r.json().get("job_id")
                st.session_state.reading_job_kind = "recommend"
                st.session_state.reading_job_started_at = time.time()
                st.success("已提交精读建议任务…")
                st.rerun()
            else:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:  # noqa: BLE001
                    detail = r.text
                st.error(f"提交失败（HTTP {r.status_code}）：{detail}")
        except httpx.RequestError as e:
            st.error(f"请求失败：{e}")

if do_pipeline:
    if not user_prompt.strip():
        st.warning("请先填写阅读动机/需求。")
    else:
        try:
            with httpx.Client(timeout=30.0, trust_env=False) as client:
                r = client.post(
                    f"{backend_url}/reading/advise/submit",
                    json={
                        "user_prompt": user_prompt.strip(),
                        "paper_text": st.session_state.paper_text,
                        "max_paper_chars": int(max_chars),
                    },
                )
            if r.status_code == 200:
                st.session_state.reading_job_id = r.json().get("job_id")
                st.session_state.reading_job_kind = "advise"
                st.session_state.reading_job_started_at = time.time()
                st.success("已提交一键任务…")
                st.rerun()
            else:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:  # noqa: BLE001
                    detail = r.text
                st.error(f"提交失败（HTTP {r.status_code}）：{detail}")
        except httpx.RequestError as e:
            st.error(f"请求失败：{e}")

if st.session_state.reading_job_id:
    pr = st.session_state.poll_reading_ui or {}
    st.progress(min(max(int(pr.get("progress") or 0), 0), 100) / 100.0)
    st.caption(pr.get("msg") or "精读任务：已提交，等待状态更新…")

if st.session_state.last_recommendation:
    body = st.session_state.last_recommendation
    used = body.get("paper_chars_used", 0)
    st.caption(f"论文摘录使用：**{used}** 字符。")
    st.markdown(_fmt_recommendation(body))
    with st.expander("原始 JSON（recommendation）"):
        st.json(body.get("recommendation", body))

if st.session_state.structured_intent and not (do_structure or do_pipeline):
    with st.expander("当前会话中的结构化需求"):
        st.json(st.session_state.structured_intent)

poll_background_jobs()
