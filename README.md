# PaperPilot

论文阅读辅助：Streamlit 前端 + FastAPI 后端（Python 课设）。需求与路线见 [final-plan.md](final-plan.md)、总需求见 [plan.md](plan.md)。

## 功能概览（与实现对齐）

| 能力 | 说明 |
|------|------|
| 健康检查 | `GET /health` |
| PDF 抽正文 | `POST /extract/file`（`pypdf`，不经大模型）；Streamlit 会把结果缓存在会话，供下游使用 |
| **结构化阅读需求** | `POST /reading/structure-intent`：用户自然语言 → [`StructuredReadingIntent`](models/intent.py)（JSON），供后续步骤**唯一**作为「用户意图」依据 |
| **精读建议** | `POST /reading/recommend`：入参仅 `structured_intent` + `paper_text` 摘录，**不携带用户原始 prompt**；返回是否精读、理由与下一步 |
| 一键建议 | `POST /reading/advise`：内部顺序 = 结构化 + 精读建议 |
| **全文分析** | `POST /analyze`：基于 `paper_text`（可截断）输出概括、关键句、中英段落对等 JSON；[`services/analyze_pipeline.py`](services/analyze_pipeline.py)；页面可 **下载 Markdown**（[`services/markdown_export.py`](services/markdown_export.py)） |

实现要点：`services/reading_pipeline.py`（精读两段 Prompt）、`services/analyze_pipeline.py`（全文分析 Prompt）、`services/llm.py`（DashScope）、`api/routes/reading.py`、`api/routes/analyze.py`。环境变量：`DASHSCOPE_API_KEY`、可选 `QWEN_MODEL`。

## 环境

- Python 3.10+
- 安装依赖：`pip install -r requirements.txt`
- 复制配置：`copy .env.example .env`。
  - **PDF 抽取**：只需 `BACKEND_URL`。
  - **精读建议 / 结构化需求 / 全文分析 `/analyze`**：均需 **`DASHSCOPE_API_KEY`** + `dashscope`。可选 **`QWEN_MODEL`**（默认 `qwen-turbo`）。

## 启动（需两个终端，项目根目录）

**终端 A — 后端：**

```bat
cd /d D:\coding\PythonLesson\final
uvicorn api.main:app --reload --port 8000
```

**终端 B — 前端：**

```bat
cd /d D:\coding\PythonLesson\final
streamlit run app.py --server.port 8501
```

浏览器打开 Streamlit（一般为 `http://127.0.0.1:8501`）：健康检查 → 抽取 PDF（文本进入会话）→ **全文分析**（`/analyze`，可下载 Markdown）→ **精读建议**（`/reading/*`）。API 文档：`http://127.0.0.1:8000/docs`。

**验收参考（与 [plan.md](plan.md) 第 9 节一致）**：一篇英文 PDF → 抽取成功 → **全文分析**可见概括、关键句与中英对照 → 可下载 `.md`。

**若健康检查返回 503/502 但后端已启动**：常为系统 **`HTTP_PROXY` / VPN** 把访问 `127.0.0.1` 的请求拐到代理；`app.py` 已对后端请求关闭环境代理（`trust_env=False`）。仍异常时请核对 `.env` 中 `BACKEND_URL`、或在浏览器直接打开 `http://127.0.0.1:8000/docs` 试 `GET /health`。

## 许可与致谢

`paper-analyst` 等第三方内容见各子目录内 `LICENSE` / 说明。
