"""PaperPilot Streamlit UI — thin client calling FastAPI."""

import os
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
if "page_text_cache" not in st.session_state:
    st.session_state.page_text_cache = {}
if "translation_cache" not in st.session_state:
    st.session_state.translation_cache = {}

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


def _translate_text(text: str, mode: str) -> str:
    key = f"{mode}::{text.strip()}"
    cached = st.session_state.translation_cache.get(key)
    if cached:
        return cached
    with httpx.Client(timeout=TIMEOUT_ANALYZE, trust_env=False) as client:
        r = client.post(f"{backend_url}/translate", json={"text": text, "mode": mode})
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:  # noqa: BLE001
            detail = r.text
        raise RuntimeError(f"翻译失败（HTTP {r.status_code}）：{detail}")
    zh = str(r.json().get("zh", "")).strip()
    st.session_state.translation_cache[key] = zh
    return zh


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
    " 若为扫描版 PDF，整页文本抽取可能较弱。"
)

if not st.session_state.pdf_bytes:
    st.info("请先在上方上传并抽取 PDF，之后可在此进行按页阅读与翻译。")
else:
    c_page, c_dpi, c_cache = st.columns([1, 1, 1])
    with c_page:
        st.number_input(
            "当前页码",
            min_value=1,
            value=max(1, int(st.session_state.reader_current_page)),
            step=1,
            key="reader_current_page",
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
            st.session_state.reader_current_page = max(
                1, int(st.session_state.reader_current_page) - 1
            )
    with nav_m:
        if st.button("下一页", key="btn_next_page"):
            next_page = int(st.session_state.reader_current_page) + 1
            max_page = st.session_state.reader_page_count or next_page
            st.session_state.reader_current_page = min(next_page, max_page)
    with nav_r:
        if st.session_state.reader_page_count:
            st.caption(f"已知总页数：**{st.session_state.reader_page_count}**")
        else:
            st.caption("总页数将在首次拉取页文本或渲染后更新。")

    left, right = st.columns([1, 1])
    with left:
        st.markdown("#### 原文页图")
        try:
            image = _fetch_page_image(st.session_state.reader_current_page, page_dpi)
            st.image(image, use_container_width=True)
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
                    zh_page = _translate_text(page_text, mode="page")
                    st.session_state.translation_cache[page_cache_key] = zh_page
                except RuntimeError as e:
                    st.error(str(e))
                except httpx.RequestError as e:
                    st.error(f"请求失败：{e}")

            if st.session_state.translation_cache.get(page_cache_key):
                _render_page_like(st.session_state.translation_cache.get(page_cache_key, ""))
            else:
                st.info("点击“翻译本页”后，这里会显示与左侧对应的整页中文内容。")

st.divider()
st.subheader("全文分析（千问 · POST /analyze）")
st.caption(
    "基于会话中的 **论文正文** 调用千问，一次性生成概括、关键句点评与中英段落对照。"
    " 需 **OPENAI_API_KEY**（OpenAI 兼容接口）。超长正文仅截取前 N 字（见下方）。"
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
            with httpx.Client(timeout=TIMEOUT_ANALYZE, trust_env=False) as client:
                r = client.post(f"{backend_url}/analyze", json=payload)
            if r.status_code == 200:
                data = r.json()
                st.session_state.analysis_result = data
                if data.get("truncation_note"):
                    st.info(data["truncation_note"])
                st.markdown(f"### 一句话\n{data.get('one_liner_zh', '')}")
                st.markdown(f"**类型**：{data.get('paper_type_guess', '')}  \n**元信息**：{data.get('metadata_summary', '')}")
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
                st.caption(
                    f"已生成中英段落对照：**{len(data.get('paragraph_pairs') or [])}** 对。"
                )
                md_bytes = analysis_to_markdown(data).encode("utf-8")
                st.download_button(
                    label="下载 Markdown",
                    data=md_bytes,
                    file_name="paperpilot_analysis.md",
                    mime="text/markdown",
                    key="download_analysis_md",
                )
                with st.expander("原始 JSON（/analyze）"):
                    st.json(data)
            else:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:  # noqa: BLE001
                    detail = r.text
                st.error(f"分析失败（HTTP {r.status_code}）：{detail}")
        except httpx.RequestError as e:
            st.error(f"请求失败：{e}")

analysis_data = st.session_state.analysis_result
if analysis_data:
    st.markdown("### 中英翻译对照阅读")
    c_open, c_close = st.columns(2)
    with c_open:
        if st.button("打开中英对照", key="btn_open_bilingual"):
            st.session_state.show_bilingual_panel = True
    with c_close:
        if st.button("收起中英对照", key="btn_close_bilingual"):
            st.session_state.show_bilingual_panel = False

    if st.session_state.show_bilingual_panel:
        pairs = analysis_data.get("paragraph_pairs") or []
        if not pairs:
            st.info("当前分析结果里没有段落对照，请先点击“生成全文分析”。")
        else:
            st.caption("左侧英文原文，右侧中文翻译。")
            for i, row in enumerate(pairs, start=1):
                if not isinstance(row, dict):
                    continue
                st.markdown(f"**段落 {i}**")
                c_en, c_zh = st.columns(2)
                with c_en:
                    st.markdown(row.get("en", "") or "—")
                with c_zh:
                    st.markdown(row.get("zh", "") or "—")

st.divider()
st.subheader("精读建议（千问 · 结构化需求）")
st.caption(
    "流程：**自然语言 → 结构化 JSON（唯一意图依据）→ 结合论文摘录给出是否精读**。"
    " 后续推理**不直接使用**你的原始句子，只使用结构化结果。"
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
            with httpx.Client(timeout=TIMEOUT_READING, trust_env=False) as client:
                r = client.post(
                    f"{backend_url}/reading/structure-intent",
                    json={"user_prompt": user_prompt.strip()},
                )
            if r.status_code == 200:
                st.session_state.structured_intent = r.json()
                st.session_state.last_recommendation = None
                st.success("已生成结构化需求（已写入会话）")
                st.json(st.session_state.structured_intent)
            else:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:  # noqa: BLE001
                    detail = r.text
                st.error(f"失败（HTTP {r.status_code}）：{detail}")
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
            with httpx.Client(timeout=TIMEOUT_READING, trust_env=False) as client:
                r = client.post(
                    f"{backend_url}/reading/recommend",
                    json=payload,
                )
            if r.status_code == 200:
                body = r.json()
                st.session_state.last_recommendation = body
                used = body.get("paper_chars_used", 0)
                st.caption(f"本次用于建议的论文摘录长度：**{used}** 字符。")
                st.markdown(_fmt_recommendation(body))
                with st.expander("原始 JSON（recommendation）"):
                    st.json(body.get("recommendation", body))
            else:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:  # noqa: BLE001
                    detail = r.text
                st.error(f"失败（HTTP {r.status_code}）：{detail}")
        except httpx.RequestError as e:
            st.error(f"请求失败：{e}")

if do_pipeline:
    if not user_prompt.strip():
        st.warning("请先填写阅读动机/需求。")
    else:
        try:
            with httpx.Client(timeout=TIMEOUT_READING, trust_env=False) as client:
                r = client.post(
                    f"{backend_url}/reading/advise",
                    json={
                        "user_prompt": user_prompt.strip(),
                        "paper_text": st.session_state.paper_text,
                        "max_paper_chars": int(max_chars),
                    },
                )
            if r.status_code == 200:
                body = r.json()
                st.session_state.structured_intent = body.get("structured_intent")
                st.session_state.last_recommendation = {
                    "recommendation": body.get("recommendation"),
                    "paper_chars_used": body.get("paper_chars_used", 0),
                }
                st.success("已完成结构化 + 精读建议")
                with st.expander("结构化需求（后续步骤仅依赖此对象）"):
                    st.json(body.get("structured_intent"))
                st.caption(
                    f"论文摘录使用：**{body.get('paper_chars_used', 0)}** 字符。"
                )
                st.markdown(_fmt_recommendation(body))
            else:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:  # noqa: BLE001
                    detail = r.text
                st.error(f"失败（HTTP {r.status_code}）：{detail}")
        except httpx.RequestError as e:
            st.error(f"请求失败：{e}")

if st.session_state.structured_intent and not (do_structure or do_pipeline):
    with st.expander("当前会话中的结构化需求"):
        st.json(st.session_state.structured_intent)
