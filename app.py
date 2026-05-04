"""PaperPilot Streamlit UI — thin client calling FastAPI."""

import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BACKEND = "http://127.0.0.1:8000"
TIMEOUT_HEALTH = 10.0
TIMEOUT_EXTRACT = 120.0
PREVIEW_CHARS = 8000

st.set_page_config(page_title="PaperPilot", layout="wide")
st.title("PaperPilot")

backend_url = os.getenv("BACKEND_URL", DEFAULT_BACKEND).rstrip("/")

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
    "使用后端 **pypdf** 抽字；不上传至千问。若需 **URL / arXiv** 将在后续版本追加。**本阶段无需配置 DASHSCOPE_API_KEY**。"
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
                st.caption(f"共 **{len(text)}** 个字符；下方预览前 **{PREVIEW_CHARS}** 字。")
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
