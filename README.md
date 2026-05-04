# PaperPilot

论文阅读辅助：Streamlit 前端 + FastAPI 后端（Python 课设）。需求与路线见 [final-plan.md](final-plan.md)。

## 环境

- Python 3.10+
- 安装依赖：`pip install -r requirements.txt`
- 复制配置：`copy .env.example .env`。阶段 2（PDF 抽取）只需 **`BACKEND_URL`**；**`DASHSCOPE_API_KEY` 可留空**，千问在后续阶段再接。

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

浏览器打开 Streamlit（一般为 `http://127.0.0.1:8501`）：可先点「检查后端健康」，再在 **「抽取 PDF 正文」** 上传 `.pdf` 并点「抽取正文」。API 文档：`http://127.0.0.1:8000/docs`，抽取接口：`POST /extract/file`。

**若健康检查返回 503/502 但后端已启动**：常为系统 **`HTTP_PROXY` / VPN** 把访问 `127.0.0.1` 的请求拐到代理；`app.py` 已对后端请求关闭环境代理（`trust_env=False`）。仍异常时请核对 `.env` 中 `BACKEND_URL`、或在浏览器直接打开 `http://127.0.0.1:8000/docs` 试 `GET /health`。

## 许可与致谢

`paper-analyst` 等第三方内容见各子目录内 `LICENSE` / 说明。
