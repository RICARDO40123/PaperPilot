# PaperPilot

论文阅读辅助：Streamlit 前端 + FastAPI 后端（Python 课设）。需求与路线见 [final-plan.md](final-plan.md)、总需求见 [plan.md](plan.md)。

## 功能概览（与当前 UI 对齐）

| 能力 | 说明 |
| --- | --- |
| 健康检查 | `GET /health`（直接访问 `http://127.0.0.1:8000/` 无根路由，可能 404，属正常） |
| PDF 抽正文/按页 | `POST /extract/file`、`POST /extract/page-text`、`POST /extract/page-image`；用于全文抽取与双栏阅读器 |
| 多论文会话 | 前端支持一次上传多篇 PDF，并通过“切换当前论文”在会话中切换；阅读器、翻译、全文分析、精读建议均按当前论文隔离缓存 |
| 双栏阅读器 | 左侧页图、右侧整页翻译（流式 + 缓存） |
| 全文分析（逐篇） | `POST /analyze/table/stream`：生成 8 维度 Markdown 填表；`POST /analyze/papernote/stream`：生成 PaperNote；两者均流式展示并可下载 Markdown |
| 综合文献综述 | 独立模块，基于多篇 PaperNote 勾选聚合；`POST /review/stream` 流式生成综述并下载 Markdown |
| 精读建议 | 支持“结构化需求”“生成精读建议”“一键精读”；前端展示为可读文本（不显示原始 JSON），并支持 Markdown 下载 |
| 文件命名 | 下载文件统一采用 `原PDF文件名_*.md`；综合综述为所选论文名拼接前缀（如 `UNet_SAM2UNet_review.md`） |

**后台任务与并发**：[`services/task_store.py`](services/task_store.py) 内 **分析 / 翻译 / 精读** 各用独立 `Semaphore`（默认可各 2 路并发），不同类型任务可并行；同类超限时在线程池槽位上等待。任务 `progress` 为粗粒度（如 0 → 10 → 100），非模型真实百分比。

**Streamlit 轮询**：[`app.py`](app.py) 在**整页控件渲染完成后**调用 `poll_background_jobs()`，统一拉取翻译/分析/精读状态，**至多一次** `sleep` + `rerun`，避免翻译轮询截断下方「全文分析」等区块。

实现要点：`services/reading_pipeline.py`、`services/analyze_pipeline.py`、`services/translate_core.py`、`services/llm.py`、`api/routes/extract.py`、`reading.py`、`analyze.py`、`translate.py`。环境变量：`OPENAI_API_KEY`、可选 `OPENAI_BASE_URL`、`OPENAI_MODEL`。

## 环境

- Python 3.10+
- 安装依赖：`pip install -r requirements.txt`
- 复制配置：`copy .env.example .env`。
  - **PDF 抽取 / 按页渲染**：只需 `BACKEND_URL`；按页图片依赖 **`pymupdf`**（见 `requirements.txt`）。
  - **整页翻译 / 精读 / 结构化需求 / 全文分析**：均需 **`OPENAI_API_KEY`** + `openai`。可选 **`OPENAI_BASE_URL`**（默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`）与 **`OPENAI_MODEL`**（默认 `qwen-turbo`）。

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

浏览器打开 Streamlit（一般为 `http://127.0.0.1:8501`）：健康检查 → 上传一篇或多篇 PDF → 选择当前论文 → 使用四个模块：
- **双栏阅读器**：按页浏览 + 整页翻译  
- **全文分析**：逐篇填表 + PaperNote（均流式）  
- **综合综述**：勾选多篇 PaperNote 生成综述（流式）  
- **精读建议**：结构化需求/一键精读 + 可读文本结果 + Markdown 下载  

API 文档：`http://127.0.0.1:8000/docs`。

**验收参考**：
- 上传 2 篇 PDF，成功切换当前论文，且阅读器/翻译内容随论文切换  
- 在“全文分析”中分别生成填表与 PaperNote，均可立即下载 `.md`  
- 在“综合综述”中勾选 >=2 篇已生成 PaperNote 的论文，流式生成并下载综述 `.md`  
- 在“精读建议”中生成结果后仅显示可读正文（无 JSON 面板），并可下载 `.md`

**若健康检查返回 503/502 但后端已启动**：常为系统 **`HTTP_PROXY` / VPN** 把访问 `127.0.0.1` 的请求拐到代理；`app.py` 已对后端请求关闭环境代理（`trust_env=False`）。仍异常时请核对 `.env` 中 `BACKEND_URL`、或在浏览器直接打开 `http://127.0.0.1:8000/docs` 试 `GET /health`。

## 许可与致谢

`paper-analyst` 等第三方内容见各子目录内 `LICENSE` / 说明。
