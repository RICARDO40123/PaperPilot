# PaperPilot

论文阅读辅助：Streamlit 前端 + FastAPI 后端（Python 课设）。需求与路线见 [final-plan.md](final-plan.md)、总需求见 [plan.md](plan.md)。

## 功能概览（与实现对齐）

| 能力               | 说明                                                                                                                                                                                                                                      |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 健康检查           | `GET /health`                                                                                                                                                                                                                             |
| PDF 抽正文         | `POST /extract/file`（`pypdf`，不经大模型）；Streamlit 会把结果缓存在会话，供下游使用                                                                                                                                                     |
| **结构化阅读需求** | 同步：`POST /reading/structure-intent` → [`StructuredReadingIntent`](models/intent.py)。异步：`POST /reading/structure-intent/submit` → `GET /reading/job/{id}` → `GET /reading/result/{id}`（Streamlit 默认）                                |
| **精读建议**       | 同步：`POST /reading/recommend`。异步：`POST /reading/recommend/submit` → `GET /reading/job/{id}` → `GET /reading/result/{id}`（Streamlit 默认）                                                                                            |
| 一键建议           | 同步：`POST /reading/advise`。异步：`POST /reading/advise/submit` + 同上轮询                                                                                                                                                              |
| **整页翻译**       | 同步：`POST /translate`。异步：`POST /translate/submit` → `GET /translate/job/{id}` → `GET /translate/result/{id}`（Streamlit 默认）                                                                                                        |
| **全文分析**       | 同步：`POST /analyze`。异步（Streamlit 默认）：`POST /analyze/submit` → `GET /analyze/job/{id}` 轮询 → `GET /analyze/result/{id}`；[`services/task_store.py`](services/task_store.py)；业务逻辑仍见 [`services/analyze_pipeline.py`](services/analyze_pipeline.py)；可 **下载 Markdown**（[`services/markdown_export.py`](services/markdown_export.py)） |

实现要点：`services/reading_pipeline.py`（精读两段 Prompt）、`services/analyze_pipeline.py`（全文分析 Prompt）、`services/llm.py`（OpenAI 兼容调用）、`api/routes/reading.py`、`api/routes/analyze.py`。环境变量：`OPENAI_API_KEY`、可选 `OPENAI_BASE_URL`、`OPENAI_MODEL`。

## 环境

- Python 3.10+
- 安装依赖：`pip install -r requirements.txt`
- 复制配置：`copy .env.example .env`。
  - **PDF 抽取**：只需 `BACKEND_URL`。
  - **精读建议 / 结构化需求 / 全文分析 `/analyze`**：均需 **`OPENAI_API_KEY`** + `openai`。可选 **`OPENAI_BASE_URL`**（默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`）与 **`OPENAI_MODEL`**（默认 `qwen-turbo`）。

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

**可选：使用 `.sh` 启动脚本（Git Bash / WSL）**

```bash
# 终端 A
bash scripts/start_backend.sh

# 终端 B
bash scripts/start_frontend.sh
```

说明：脚本内部使用 `python -m uvicorn` 与 `python -m streamlit`，可复用当前激活环境（如 conda），避免 `streamlit: command not found`。

**Windows / PowerShell 推荐：使用 `.ps1` 启动脚本**

```powershell
# 终端 A
powershell -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1

# 终端 B
powershell -ExecutionPolicy Bypass -File .\scripts\start_frontend.ps1
```

浏览器打开 Streamlit（一般为 `http://127.0.0.1:8501`）：健康检查 → 抽取 PDF（文本进入会话）→ **全文分析**（`/analyze`，可下载 Markdown）→ **精读建议**（`/reading/*`）。API 文档：`http://127.0.0.1:8000/docs`。

**验收参考（与 [plan.md](plan.md) 第 9 节一致）**：一篇英文 PDF → 抽取成功 → **全文分析**可见概括、关键句与中英对照 → 可下载 `.md`。

**若健康检查返回 503/502 但后端已启动**：常为系统 **`HTTP_PROXY` / VPN** 把访问 `127.0.0.1` 的请求拐到代理；`app.py` 已对后端请求关闭环境代理（`trust_env=False`）。仍异常时请核对 `.env` 中 `BACKEND_URL`、或在浏览器直接打开 `http://127.0.0.1:8000/docs` 试 `GET /health`。

## 许可与致谢

`paper-analyst` 等第三方内容见各子目录内 `LICENSE` / 说明。
