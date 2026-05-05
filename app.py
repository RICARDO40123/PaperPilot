"""PaperPilot Streamlit UI — thin client calling FastAPI."""

import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BACKEND = "http://127.0.0.1:8000"
TIMEOUT_HEALTH = 10.0
TIMEOUT_EXTRACT = 120.0
TIMEOUT_READING = 180.0
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
    "使用后端 **pypdf** 抽字；抽取结果会写入会话，供下方「精读建议」作为论文上下文。"
    " **URL / arXiv** 可后续再加。"
)

uploaded = st.file_uploader("选择 PDF 文件", type=["pdf"], key="pdf_uploader")

if st.button("抽取正文", key="btn_extract"):
    if not uploaded:
        st.warning("请先选择 PDF 文件。")
    else:
        files = {
            "file": (
                uploaded.name,
                uploaded.getvalue(),
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
st.subheader("精读建议（千问 · 结构化需求）")
st.caption(
    "流程：**自然语言 → 结构化 JSON（唯一意图依据）→ 结合论文摘录给出是否精读**。"
    " 后续推理**不直接使用**你的原始句子，只使用结构化结果。"
    " 需在 `.env` 配置 **DASHSCOPE_API_KEY**，并 `pip install dashscope`。"
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
