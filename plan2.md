# PaperPilot × paper-analyst：Skill 形式说明与借鉴方案

本文说明 `paper-analyst` 这类资源的**技术形态**，并评估哪些内容可以**合规、可落地**地补强 `PaperPilot`（见 `plan.md`）。项目对外名称：**PaperPilot**。

---

## 1. 「Skill」到底是什么形式？

在你看到的 `paper-analyst` 仓库里，核心是 **给 AI 代理读的操作说明 + 配套资料**，而不是一个必须单独部署的「程序服务」。

典型结构（与本仓库中 `paper-analyst/paper-analyst-main/` 一致）：

| 部分 | 作用 |
|------|------|
| **`SKILL.md` 顶部的 YAML Frontmatter**（`---` 包住 `name`、`description`） | 在 Claude Code 等环境里注册技能名、触发场景说明，让工具知道「什么时候该用这个 skill」。 |
| **`SKILL.md` 正文** | 工作流步骤、模式划分、必须遵守的规则（例如反幻觉）。 |
| **`references/*.md`** | 可复用的「规范文档」：输出章节结构、论文类型量表、质检清单、幻灯片 schema 等。 |
| **`scripts/*.py`**（可选） | 辅助脚本，例如从 PDF 提取元数据或插图，供人或 AI 在本地调用。 |

用户使用方式通常是：在支持的客户端里用自然语言触发，或把 skill 安装到对应 skills 目录；**分析本身仍由模型 + 这些说明共同完成**。

**与 PaperPilot 的关系**：PaperPilot 是你的 **Python 网页应用**（已定 **`Streamlit` + `FastAPI`** 分离，见 `final-plan.md` / `plan.md` 第 4 节；做不顺可回退单体 Streamlit）。`paper-analyst` 是 **提示词/流程/文档 + 小脚本** 的 bundle。二者可以并存：前端负责展示与导出，后端负责解析与 LLM，Skill 里的思想 **内化** 为 **系统提示词、JSON 响应契约、质检规则、可选预处理脚本**。

---

## 2. 借鉴是否可行？结论

**可行，且推荐「有选择地借鉴」**，原因：

- **目标部分重叠**：都从 PDF/文本出发，做结构化理解、摘要、类型化方法分析、降低胡编风险。
- **形态可转换**：`references/output-schema.md`、`paper-type-rubric.md`、`quality-checklist.md` 可以直接改写成 PaperPilot 的后端 **Prompt 约束** 或 **响应 JSON Schema**，前端按块渲染即可。
- **边界清晰**：PaperPilot 侧重点在 **Zotero 决策路径**、**中英对照阅读**、**关键句注释**；`paper-analyst` 强项在 **深度六段式分析**、**组会 PPT 流水线**。不必 1:1 复制，按需裁剪。

注意：

- **许可证**：`paper-analyst` 使用 MIT（以仓库内 `LICENSE` 为准）。若在项目内**原文复制**较长文档或脚本，应保留版权与许可声明；借鉴「思路与自写概述」一般无妨，具体以你法务/课程要求为准。
- **模型与产品**：Skill 面向 Claude Code；PaperPilot 若用通义千问等 API，需在实现时 **重测** 每条规则是否被稳定遵守，必要时加后处理校验（例如必填字段、禁止空段）。

---

## 3. 建议从 paper-analyst 借什么、对应到 PaperPilot 哪里

### 3.1 强推荐（与 MVP 高度一致）

| paper-analyst 中的概念 | 借鉴到 PaperPilot |
|------------------------|-------------------|
| PDF 质量分层（良好 / 降级 / 严重降级） | 解析后在上传结果区显示状态；严重扫描件时提示 OCR 或换源，避免silent 乱编。 |
| 输出结构（基础信息、摘要直译+通俗解释、方法按类型模板、创新点带证据） | 与 `plan.md` 的「概括、关键句、对照翻译」合并：**主面板**用统一 JSON/分块 Markdown 驱动多区域展示。 |
| 反幻觉清单（`[原文声明]` / `[模型归纳]` / `[未明确给出]`） | 写入系统 Prompt；UI 用标签或小字说明，满足课程/自用可信度。 |
| 论文类型先做 rubric 再分析 | 先分类再选「方法段落」模板，减少泛泛而谈。 |

### 3.2 可选（第二阶段或「高级模式」）

| 概念 | 借鉴方式 |
|------|----------|
| `quick` / `standard` 等多模式 | Streamlit 侧边栏单选：速览 vs 完整分析，对应不同 token 与段落深度。 |
| `extended`（仅论文内引用推断前作） | 独立按钮「文献内关系速览」；明确提示**不联网**，避免与「外部检索」混淆。 |
| `presentation` / `pptx` 技能联动 | PaperPilot 可先只做 **「组会大纲 Markdown / 结构化 JSON 导出」**；真正生成 `.pptx` 再接库或独立工具，避免 MVP  scope 膨胀。 |
| `extract_pdf_meta.py` / `extract_pdf_figures.py` | 可作为 **可选预处理**：元数据填表、插图列表；与当前解析库（如 pymupdf/pypdf）统一依赖管理。 |

### 3.3 建议不强行对齐的部分

- **完全自动 PPT 成品**：若课程只要求网页 + 决策辅助，可只做「大纲导出」即达标。
- **与 Zotero 深度集成**：Skill 未涉及；仍以 `plan.md` 的「复制/导出 Markdown」为主，后续再加 Zotero API（若有）。

---

## 4. 落地实施顺序（简要）

1. **定 API 响应契约**：从 `output-schema.md` 删减出 PaperPilot v1 字段（必含：摘要双语、贡献点、方法要点、局限、是否推荐精读、每条结论的证据标签）。  
2. **固化系统 Prompt**：嵌入质量分层说明 + 反幻觉规则 + 论文类型 rubric 的压缩版（原文档可放仓库 `docs/prompt/` 便于版本管理）。  
3. **解析层**：URL/PDF 文本抽取 + 质量档位判断（规则 + 可选用脚本）。  
4. **UI**：分栏翻译区 + 结构化结果折叠面板；「速览/完整」模式开关。  
5. **合规与致谢**：若引用其文档片段，在 README 或本文件补充致谢与 MIT 声明。

---

## 5. 小结

- **Skill** ≈ 带元数据的 **`SKILL.md` + `references` 规范 + 可选 `scripts`**，供 AI 客户端加载，不是替代你写网页的框架。  
- **借鉴价值**主要在：**结构化输出、反幻觉标注、PDF 降级策略、论文分型模板**；与 PaperPilot 的 **中英对照 + Zotero 前筛** 可以很自然合并。  
- 按上表分阶段吸收，可控制工作量并避免与课程 MVP 冲突。

（完）
