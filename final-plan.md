# PaperPilot 最终执行计划（小白跟做版）

> **项目名**：PaperPilot  
> **做什么**：一个用 Python 写的本地网页，帮你读论文——摘要、关键句注释、中英对照、是否值得放进 Zotero——省掉反复复制粘贴。  
> **技术路线**：**Streamlit（前端） + FastAPI（后端）**，全 Python 前后端分离；通义千问 API + PDF/链接解析在后端完成（详见 `plan.md` 第 4 节）。  
> **回退方案**：分离做不顺时，可把 `services/` 直接在 Streamlit 里 `import`，两个终端变一个，`streamlit run` 即可（功能对齐，报告里写明「单体回退版」即可）。  
> **好思路从哪来**：参考 `paper-analyst` 的「结构化输出 + 反幻觉标注 + PDF 质量分层」，写进我们自己的 Prompt 和页面，**不依赖** Claude Skill 运行时（详见 `plan2.md`）。

### 平时怎么跑（分离模式）

需要**两个终端**，虚拟环境相同即可：

1. 后端：`uvicorn api.main:app --reload --port 8000`（具体模块路径以你仓库为准）  
2. 前端：`streamlit run app.py --server.port 8501`  

`.env` 里给 Streamlit 用：`BACKEND_URL=http://127.0.0.1:8000`。

下面按顺序做即可；每步都有「你要干什么」和「怎样算做完」。

---

## 读前 3 件事（5 分钟）

| 序号 | 你要明白的事 |
|------|----------------|
| 1 | **API Key** 会花钱或有限额，只放在 `.env`，**不要**提交到 GitHub。 |
| 2 | **第一版**先啃动 **英文论文 + arXiv 或 PDF**，别的网站以后再加。 |
| 3 | 卡住时优先问：**后端 FastAPI 挂了没**（浏览器打开 `http://127.0.0.1:8000/docs`）、**CORS 是否放行**、**Streamlit 里的 `BACKEND_URL` 对不对**；再区分是解析没文字、还是大模型 API 报错、还是页面没显示。 |

---

## 阶段 0：电脑与仓库准备好

### 你要做的

1. 安装 **Python 3.10+**（装好后终端里 `python --version` 能看到版本）。  
2. 项目目录：`D:\coding\PythonLesson\final`（或你自己的路径，整篇文档里路径按你的实际改）。  
3. Git 已关联 GitHub 远程（你之前已用 HTTPS 推送成功；以后 `git add` / `commit` / `push` 即可备份）。

### 完成标志

- 能在该目录打开终端，Python 可用。  
- `git remote -v` 指向你的 `PaperPilot` 仓库。

---

## 阶段 1：建「空房子」——项目文件夹与依赖（分离架构）

### 你要做的

1. 在 `final` 下建建议结构（名字可以微调，但建议一开始就这样，省得乱）：

```text
final/
  app.py                  # Streamlit：只做 UI + 用 httpx 调后端（薄）
  requirements.txt        # 依赖列表
  .env                    # DASHSCOPE_API_KEY、BACKEND_URL（不要提交）
  .env.example            # 只写变量名与示例 URL，供提交用
  .gitignore              # 忽略 .env、__pycache__、.venv 等
  api/
    __init__.py
    main.py               # FastAPI 入口：CORS、挂载路由、uvicorn 指向它
    routes/               # extract.py、reading.py 等
      __init__.py
  services/
    __init__.py
    parser.py             # PDF / URL 抽文本（由 FastAPI 路由调用）
    llm.py                # DashScope 千问 + JSON 解析
    reading_pipeline.py   # 结构化需求 + 精读建议（两阶段 LLM）
    pipeline.py           # 全文摘要 / 注释 / 翻译编排（后写）
  models/
    __init__.py
    schema.py             # Pydantic / dataclass：请求与响应、「分析结果」结构
  prompts/
    system.txt            # 系统提示词（可后补；先建空文件也行）
```

2. 建虚拟环境（推荐）：

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install streamlit python-dotenv fastapi "uvicorn[standard]" httpx
```

后续再按需加：`pypdf` 或 `pymupdf`、`requests`、`beautifulsoup4`、阿里云 dashscope SDK 等。

3. **`api/main.py` 首期目标**：挂载 `GET /health`（返回 `{"ok": true}`），并配置 **CORS** 允许 `http://localhost:8501` 与 `http://127.0.0.1:8501`（开发期可先宽松，交作业前再收紧）。

4. **`app.py` 首期目标**：页面上一个按钮，点一下 `httpx.get(f"{os.environ['BACKEND_URL']}/health")`，把 JSON 显示出来——证明**前后端通路**。

### 完成标志

- 终端 A：`uvicorn api.main:app --reload --port 8000`，浏览器打开 `http://127.0.0.1:8000/docs` 能看到接口。  
- 终端 B：`streamlit run app.py`，能显示 health 检查结果。  
- `.env` 已在 `.gitignore` 里，**永远不**把它 push 上去。

---

## 阶段 2：能「看见字」——解析 PDF 和链接（不经 AI，走 FastAPI）

### 你要做的

1. 在 **FastAPI** 增加路由，例如 `POST /extract`：接受上传文件或 JSON 里的 URL，返回 `{ "text": "...", "pdf_quality": "..." }`。  
2. **PDF**：在 `services/parser.py` 用 `pypdf`（或 `pymupdf`）抽纯文本；若字数极少，响应里带 **「疑似扫描版」** 标记（借鉴 paper-analyst 的 PDF 质量分层）。  
3. **URL**：第一版只做 **PDF 直链** 或 **arXiv 摘要页**；别处返回明确 `400` + 中文 `detail`。  
4. **Streamlit**：上传/填 URL 后，把内容 `POST` 给后端，用 `st.text_area` 展示返回的 `text` 前几千字。

### 完成标志

- 任选一篇 PDF 或 arXiv 链接，**经后端**能在页面上看到**真实论文文字**。  
- 抽失败时后端返回结构化错误，Streamlit 用 `st.error` 显示，而不是白屏。

---

## 阶段 2.5（已实现）：结构化需求 + 精读建议

在用户提示词较模糊时，先让模型把**自然语言阅读动机**整理成 **JSON 结构化需求**（`StructuredReadingIntent`），后续「是否精读」**只使用该 JSON + 论文摘录**，不再直接依赖用户原话。

### 你要做的（对照仓库）

1. `.env` 配置 **`DASHSCOPE_API_KEY`**（与可选 **`QWEN_MODEL`**）；`pip install dashscope`（见 `requirements.txt`）。  
2. 后端路由：`api/routes/reading.py` — `POST /reading/structure-intent`、`POST /reading/recommend`、`POST /reading/advise`。  
3. 编排与 Prompt：`services/reading_pipeline.py`；底层调用：`services/llm.py`。  
4. 前端：`app.py` 中「精读建议」区块；抽取的 `paper_text` 写入 **Streamlit `session_state`** 供建议接口使用。

### 完成标志

- `/docs` 可调通 `structure-intent` 与 `recommend`；页面上能先看到结构化 JSON，再看到 Markdown 形式的精读结论。  
- 未配置 Key 时接口返回 **503** 等明确错误，而非静默失败。

---

## 阶段 3：接通大脑——千问 API 走通一条路（建议后端直连 Key）

### 你要做的

1. 开通通义千问（DashScope 等），把 Key 放进 `.env`（**仅后端进程读取**，不要传到 Streamlit 浏览器）。  
2. 在 `services/llm.py` 写调用函数；可用 **`POST /reading/structure-intent`** 或临时 `POST /llm/ping` 验证连通（若尚未写 ping，以 `reading` 路由为准）。  
3. 再用论文摘录 + 结构化需求走 **`/reading/recommend`**，或单独写「摘要列要点」类接口；确认**稳定返回**。  
4. Streamlit 经 `httpx` 调上述路由，**不**在浏览器里放 API Key。

### 完成标志

- 启动后端后可用 `/docs` 试通千问相关接口；Streamlit 精读区块能经 HTTP 看到返回。  
- Key 错误或欠费时，后端返回 4xx/5xx + `detail`，前端 `st.error` 显示人话。

---

## 阶段 4：定「合同」——分析结果 JSON（借鉴 paper-analyst 的结构）

不要求和 paper-analyst 一模一样；**第一版**建议字段至少包括：

| 区块 | 用途 |
|------|------|
| `pdf_quality` | 良好 / 降级 / 严重降级 + 简短原因 |
| `paper_type_guess` | 论文类型（综述 / 实验 / 系统 / 理论等其一） |
| `metadata` | 标题、作者、年份、 venue（缺就写「未给出」） |
| `one_liner_zh` | 一句话中文总结 |
| `contributions` | 若干条贡献，每条：`text`、`evidence`、`tag`（`原文声明` / `模型归纳`） |
| `method_summary` | 方法要点小段 |
| `limitations` | 局限 |
| `read_recommendation` | 是否建议精读 + 理由（面向是否进 Zotero） |
| `key_sentences` | 列表：`en`、`zh_note`、`why_important` |
| `paragraph_pairs` | 可选：对齐的中英段落（用来做左右分栏） |

模型必须 **优先输出合法 JSON**（可在 Prompt 里说「只输出 JSON，不要 markdown」），再在 Python 里 `json.loads`；失败则降级为「整块 Markdown」应急。

### 你要做的

1. 在 `models/schema.py` 用数据结构描述以上字段（或先 dict 手写键名统一）。  
2. 在 `prompts/` 写好系统提示 + 用户提示模板：明确要求 **标注** `[原文声明]` / `[模型归纳]` / `未给出`。  
3. `pipeline.py`：由 FastAPI 路由调用；`raw_text → 截断/分块（长文稍后）→ 调 `llm` → 解析 JSON → 返回 Pydantic 模型或 dict`。

4. 对外保留例如 `POST /analyze`：请求体带 `text` 与模式 `quick|full`，响应为统一 JSON（与 `models/schema.py` 一致）。

### 完成标志

- 用 `/docs` 或 Streamlit 提交同一篇论文，响应**字段齐全**（内容可逐步调优）。  
- 超长论文可先只喂「标题+摘要+第一节」也能跑通，后面再加分块摘要。

---

## 阶段 5：页面像「工具」——Streamlit 布局

### 你要做的（按块实现）

1. **侧边栏**：上传 PDF / 输入 URL；可选「速览 / 完整」模式（作为请求参数传给 `/analyze`）。  
2. **数据流**：先 `POST /extract` 得正文 → 用户确认或自动再 `POST /analyze` → 前端按 JSON 渲染（不要把大块业务逻辑写在 Streamlit）。  
3. **主区上**：metadata 卡片、一句话总结、精读建议（高亮）。  
4. **主区中**：关键句表格或可展开列表（中英句 + 注释）。  
5. **主区下**：`st.columns(2)` 左英右中段落对照；或小屏时用 tabs。  
6. **按钮**：「复制摘要」「导出 Markdown」（可由前端把后端 JSON 格式化为 `.md`，`st.download_button`）。

### 完成标志

- 你不用打开 Word，单靠这个页（+ 后端已启动）就能完成：**判断值不值得读 → 复制进 Zotero 笔记**。  
加载中用 `st.spinner` 或 `status`，超时提示检查后端是否卡住。

---

## 阶段 6：收尾与答辩友好项

### 你要做的

1. `README.md`：如何安装；**如何开一个终端启动 uvicorn**、再开一个终端启动 Streamlit；`.env` 变量说明；若采用单体回退，写明一条命令的运行方式。  
2. 若大段借鉴了 MIT 授权的 `paper-analyst` 文档/脚本，在 README **致谢并保留许可说明**。  
3. 优化异常：网络超时、PDF 加密、429 限速——各给一句人话提示。  
4. 最后一轮：**挑 1～2 篇真论文截图**存档（交作业或个人记录用）。

### 完成标志

- 同学/老师能在另一台机按 README **复现运行**（除 API Key 外）。  
- 与 `plan.md` 第 9 节验收标准一致即可交卷。

---

## 建议日程（可按课表压缩）

| 天数 | 内容 |
|------|------|
| 第 1 天 | 阶段 0～1（含 FastAPI health + CORS + Streamlit 打通） |
| 第 2 天 | 阶段 2 PDF + URL `/extract` |
| 第 3 天 | 阶段 3 千问 + 阶段 4 JSON/Prompt/`/analyze` |
| 第 4 天 | 阶段 5 Streamlit 全布局 |
| 第 5 天 | 阶段 6 + 试论文；必要时记录「单体回退」用法 |

---

## 我们「开始」之后的第一条具体任务

**下一小步只做一件事**：在 `final` 里建好阶段 1 的目录、`requirements.txt`、`.gitignore`、`.env.example`；实现 `api/main.py`（`GET /health` + CORS）；实现最小 `app.py`，用 **httpx** 显示 health。两个进程都能启动即过关。  
做完再写 `services/parser.py` 与 `/extract`。

---

## 文档关系

- **粗需求与模块划分**：`plan.md`  
- **paper-analyst 能借什么**：`plan2.md`  
- **按天跟做的总路线**：本文件 `final-plan.md`

（完）
