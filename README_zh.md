# Chelate Shell（螯合壳）

> **本地 Agent 技能生态中缺失的那个调度器。**
>
> 打通本地技能孤岛，构建可复现的科研流水线。
> 作为一个带微内核的调度器，Chelate Shell 将 18 个底层技能组织成跨平台的确定性工作流，并用硬性门禁减少 AI 幻觉。

[English](README.md) · **简体中文**

**版本：** 1.2.0 | **技能数：** 18

---

## 安全与开源声明

> **免责声明**：本仓库包含作者为自动化科研工作流而开发的辅助工具，并非经过同行评审的学术项目。部分样板代码或实用脚本可能在 AI 辅助下生成，并经过作者高层面的审查与修改整合。作者对任何第三方代码问题不承担责任，但承诺及时处理任何合理的诉求。
>
> 本工具**永远不会代替你做实验**。数据必须由学生在实验室手动采集，AI 在实验环节物理隔离。生成的报告仅为“数据分析草稿”，最终学术责任由使用者本人及所在机构承担。

---

## 为什么需要 Chelate Shell？

当前 AI 生态里，每个技能（Skill）都在解决单点问题：校验公式、追踪视频、整理文件。但当 Agent 面对复杂任务时，它常常不知道**该按什么顺序、在什么位置调用哪个技能**。散落的、无状态的技能调用，往往会导致上下文污染、文件版本混乱、甚至产生不可信的 AI 幻觉。

Chelate Shell 是一个**确定性的调度器（Orchestrator）**。它自身不仅提供了 18 个技能（拥有独立底层代码）去解领域问题；它还像一位资深项目经理那样拆解用户意图，强制标准化的工作区目录结构，并**确定性地**把任务路由到对应技能。

---

## 安装与下载

一共三种装法。有插件市场的宿主把整套装成**一个插件**——这是保留微内核自动调度的唯一形式；没有插件通道的宿主则以**规则文件**接入，一个脚本就能把全部规则文件一次写好；第三种是把这件事直接交给 AI。

### 方法一：从插件市场用 URL 安装

下面每个宿主都有自己的插件市场。把本仓库的 Git URL 注册进去，再安装它列出的插件即可（URL 重复注册没有副作用，第二次会提示已存在）。

```bash
https://github.com/JiamingShi-JsPhys/chelate-shell
```

### 方法二：用命令安装

**Claude Code** —— 在终端执行（v2.1.292+），一步完成注册与安装：

```bash
claude plugin install chelate-shell --marketplace https://github.com/JiamingShi-JsPhys/chelate-shell.git
```

**Claude Code** —— 在会话内执行（v2.1.275+），先用 URL 添加市场，并锁定发布 tag：

```text
/plugin marketplace add https://github.com/JiamingShi-JsPhys/chelate-shell.git#v1.2.0
```

再安装它列出的条目：

```text
/plugin install chelate-shell@chelate-shell-marketplace
```

**Codex** —— 把 URL 注册为 Git 市场；`--ref` 锁定发布 tag，HTTPS 换成 SSH 或本地路径同样可用：

```bash
codex plugin marketplace add https://github.com/JiamingShi-JsPhys/chelate-shell.git --ref v1.2.0
```

**Codex** —— 从该市场安装插件：

```bash
codex plugin add chelate-shell@chelate-shell-marketplace
```

**dsh（DeepSeek Harness）** —— 直接从同一个仓库 URL 安装进指定 profile：

```bash
dsh plugin --profile web add github:JiamingShi-JsPhys/chelate-shell#v1.2.0
```

**CodeBuddy** —— 先把 URL 加为 Git 市场：

```text
/plugin marketplace add https://github.com/JiamingShi-JsPhys/chelate-shell.git#v1.2.0
```

再安装它列出的条目：

```text
/plugin install chelate-shell@chelate-shell-marketplace
```

Cursor、Windsurf、Cline 的 IDE 扩展、Continue、Roo Code、GitHub Copilot 与 opencode 各自从自己的位置读取规则文件，而且它们都不接受本仓库作为插件——Cline 的 `cline plugin install` 只接受 JS/TS 插件包，Cursor 的插件格式是另一套打包，`opencode plugin <module>` 装的是 npm 模块。**没有任何厂商提供能识别别家规则文件的安装器**，所以本仓库自带一个：

```bash
git clone https://github.com/JiamingShi-JsPhys/chelate-shell.git && python chelate-shell/install.py --project <项目> --global
```

这一条命令会一次性写好全部规则文件：

- `--project <项目>` 负责项目级文件——Cursor、Windsurf、Cline、Continue、Roo Code、GitHub Copilot，以及 Codex、Cursor、Copilot Agent 与 opencode 都会读的通用 `AGENTS.md`。
- `--global` 负责用户级文件——`~/.config/opencode/AGENTS.md`、`$CODEX_HOME/AGENTS.md`（默认 `~/.codex/AGENTS.md`），以及 `~/.claude` 已存在时的 `~/.claude/CLAUDE.md`——并自动跳过本机没有安装的宿主。

重复运行是安全的：内容相同的文件报告 `unchanged`，已经改动过的规则文件在你不加 `--force` 时保持原样。

先看清单，不写任何文件：

```bash
python chelate-shell/install.py --list
```

预演一次：

```bash
python chelate-shell/install.py --project <项目> --global --dry-run
```

只装某一个宿主：

```bash
python chelate-shell/install.py --project <项目> --only cursor,windsurf
```

克隆下来的仓库要放在 Agent 能访问到的位置：每个规则文件都点名了 `cli.py`、`ORCHESTRATOR.md` 与 `task-organizer`，宿主 Agent 因此可以像插件宿主一样进入同一条流水线。规则文件只描述“怎么调用”，并不内置代码。

**opencode 也可以完全不复制** —— 用 `opencode.json` 的 `instructions` 数组原地指向规则文件，无需复制，还能随项目提交给整个团队：

```json
{{
  "$schema": "https://opencode.ai/config.json",
  "instructions": ["../chelate-shell/AGENTS.md"]
}}
```

**不想跑脚本时的手动方式** —— 自己复制，目标路径就是脚本会写入的那一处：

```text
<克隆目录>/AGENTS.md  →  <项目>/AGENTS.md
```

### 方法三：让 AI 帮你装

> “请访问 GitHub 仓库 `https://github.com/JiamingShi-JsPhys/chelate-shell` 并克隆它，然后运行 `python install.py --project . --global`。如果你的宿主有插件系统，请改为把整套作为单一插件安装；该脚本覆盖的是读规则文件的那些宿主。”

> **警告**：使用 AI 自动安装时，AI 有概率会将 `skills/` 目录下的独立技能直接打散，平铺复制到平台的全局技能目录中。这会导致 Chelate Shell 的“微内核自动调度架构”失效，退化为 18 个散装技能。如果你需要完整的插件调度功能，请使用方法一。

**环境依赖提示**：微内核与多数技能仅依赖 Python 标准库。少数涉及数据处理/网络的技能需要第三方库（见 [docs/DEPENDENCIES_zh.md](docs/DEPENDENCIES_zh.md)）；缺失依赖时，系统会优雅降级为 `UNVERIFIED` 门禁并给出提示，不会直接崩溃。

## 快速上手

所有命令均在仓库根目录执行，**绝不硬编码绝对路径**。

列出路由表：

```bash
python cli.py list
```

直接运行单个技能（以查假文献为例）：

```bash
python cli.py run reference-auditor --root /path/to/workspace --action audit --input draft.md
```

干跑一条流水线（展示计划的执行顺序）：

```bash
python cli.py pipeline --root /path/to/workspace --mode a --input-kind pdf --dry-run
```

完整流水线（提取 → 门禁 → 加工）：

```bash
python cli.py pipeline --root /path/to/workspace --mode a --input-kind pdf
```

只跑门禁，带逐技能参数：

```bash
python cli.py pipeline --root /path/to/workspace --mode c --selected reference-auditor --skill-arg "reference-auditor:--input draft.md"
```

初始化复杂任务工作区：

```bash
python skills/task-organizer/run.py --root <workspace> --action init
```

重建上下文压缩索引：

```bash
python skills/task-organizer/run.py --root <workspace> --action broadcast
```

确定性校验物理公式（旁路模式）：

```bash
python skills/formula-validator/run.py --root <workspace> --action validate -- --expr "F = m*a" --units F=N --units m=kg --units a=m/s**2
```

审计草稿中的 DOI（假 DOI 直接 FAIL 并终止流水线）：

```bash
python skills/reference-auditor/run.py --root <workspace> --action audit --input draft.md
```

去除草稿的 AI 痕迹：

```bash
python skills/ai-trace-remover/run.py --root <workspace> --action scan -- <file>
```

用 `--inputs` 声明本次运行的输入文件（自动接线）：

```bash
python cli.py pipeline --root ./test_workspace --inputs draft.md data.csv
```

调试单个技能（`--debug` 放在技能名前后均可）：

```bash
python cli.py run data-profiler --root /path/to/workspace --action profile --input data.csv --debug
```

用环境变量调试整条流水线：

```bash
CHELATE_DEBUG=1 python cli.py pipeline --root /path/to/workspace --mode c --selected reference-auditor
```

流水线模式：`a` 自动（提取 → 门禁 → 加工）、`b` 仅提取、`c` 仅门禁。`--inputs` 把计划收窄到能消费所声明文件的技能（显式 `--selected` 列表永远优先）；扩展名未声明任何 manifest 类型的文件会打印 `[INPUT]` 警告且不接线。每个声明的文件都按 `--root` 解析（相对路径以工作区根为准，绝对路径原样使用）；文件缺失时在运行任何技能之前直接以 exit 2 失败。

## 环境要求

只需要 Python 3.10+，别的都不用提前准备：微内核与多数技能仅依赖标准库。少数数据处理与网络类技能会额外用到常见的第三方包（numpy、pandas、sympy、rdkit、matplotlib、requests 等）；每个技能的 `manifest.json` 精确声明了自己需要什么，运行时由 `core/sandbox.py` 检查。缺包不会让流水线崩溃——只有那一个技能会带提示降级为 `UNVERIFIED` 门禁，其余照常运行。本仓库不内置任何第三方代码，每个库仍保持其自身的宽松许可。逐技能的完整依赖矩阵见 [docs/DEPENDENCIES_zh.md](docs/DEPENDENCIES_zh.md)。

## 仓库布局

```text
chelate-shell/
├── .claude-plugin/                   # Claude Code 插件清单 + marketplace
├── .clinerules/                      # Cline 规则文件
├── .codebuddy-plugin/                # CodeBuddy 插件清单 + marketplace
├── .codex-plugin/                    # Codex 插件清单 + marketplace
├── .continue/rules/                  # Continue 规则目录
├── .cursor/rules/                    # Cursor 规则文件（.mdc）
├── .dsh-plugin/                      # DeepSeek Harness CJS 入口（apply(ctx)）
├── .github/                          # GitHub Copilot 指令文件
├── .gitignore
├── .roo/rules/                       # Roo Code 规则目录
├── .windsurf/rules/                  # Windsurf 规则文件
├── AGENTS.md                         # 通用 Agent 规范（Codex / Cursor / Copilot / opencode）
├── assets/                           # icon.png（各插件清单共用）
├── bootstrap.py                      # 各 run.py 共用的导入与门禁写入工具
├── CHANGELOG.md                      # 版本发布说明
├── cli.py                            # 命令行入口：list / run / pipeline
├── contracts/                        # 全局通信契约
│   ├── __init__.py
│   ├── gate_result.py                # {skill, status, evidence_level, reason, artifacts}
│   └── schema.json                   # manifest.json 的强校验规范
├── cordis.patch.yml                  # cordis bundle 补丁
├── core/                             # 微内核
│   ├── __init__.py
│   ├── registry.py                   # 扫描 skills/ 并注册进路由表
│   ├── router.py                     # 确定性调度器（解析 manifest 生成流水线）
│   └── sandbox.py                    # 依赖隔离与 120 秒超时熔断
├── docs/                             # 设计笔记、审计报告、文件功能映射
├── index.js                          # CJS 插件入口（dsh 生态）
├── install.py                        # 一条命令装好所有规则文件的安装器（见安装章节）
├── lib/chelate_core/                 # 共享底层逻辑库（逻辑住在这里）
│   ├── __init__.py
│   ├── adapter.py                    # 薄适配器工具箱：argparse、门禁发射、legacy 运行器
│   ├── arxiv_search.py               # arXiv 搜索核心
│   ├── bibtex_norm.py                # BibTeX 解析 / 去重 / 规范化核心
│   ├── csv_profile.py                # CSV 体检核心（pandas）
│   ├── debug.py                      # 贯通全链路的 [chelate:debug] 开关
│   ├── doi_audit.py                  # DOI 抽取 + Crossref 核验核心
│   ├── formula_merge.py              # legacy D1-D5 + pint 裁决合并策略
│   ├── paths.py                      # 路径解析
│   ├── pdf_text.py                   # PDF 提取核心（pdfminer.six / pypdf）
│   └── yamlmini.py                   # assets/config.yaml 加载
├── LICENSE
├── ORCHESTRATOR.md                   # 给 Agent 看的路由契约（v1.2.0）
├── package.json                      # npm/dsh 打包元数据
├── README.md
├── README_zh.md
├── skills/                           # 18 个技能，完全平铺
│   ├── ai-trace-remover/             # [processors] 模板句清除与 0–100「AI 味」评分
│   │                                 # （英文 + 中文词表）
│   ├── bibtex-normalizer/            # [ingest]    .bib 解析、去重、规范化输出
│   ├── capstone-labmate/             # [ingest]    PASCO Capstone .cap 二进制解析、
│   │                                 # CSV/JSON 转换、带水印的草稿报告
│   ├── conflict-detector/            # [gates]     跨文档矛盾引擎，正则数字抽取
│   ├── data-profiler/                # [gates]     pandas CSV 体检：行数、缺失值、
│   │                                 # 1.5·IQR 异常值比率、重复行、常值列
│   ├── document-evolution-tracker/   # [workspace] 跨文档版本的段落级 diff、
│   │                                 # 概念谱系追踪
│   ├── figure-generator/             # [processors] 出版级统计图（matplotlib + seaborn），
│   │                                 # 含 AMOS 风格 SEM 路径图渲染器；沙箱运行
│   ├── formula-validator/            # [gates]     SymPy D1–D5 层（量纲分析、极限枚举、
│   │                                 # 数值采样、符号证明）+ pint 单位交叉校验
│   ├── fulltext-extractor/           # [ingest]    pdfminer.six 文本提取进 process/
│   │                                 # （pypdf 回退）
│   ├── latex-exporter/               # [processors] 把 process/ 下的 Markdown 与 process/figures/
│   │                                 # 下的图形合并为一个可编译 .tex
│   ├── literature-retriever/         # [ingest]    arXiv 关键词搜索转 JSON
│   ├── longitudinal-analysis/        # [gates]     时间序列 OLS 加 R 支撑的 LMM（lme4）、
│   │                                 # 中介分析（lavaan）、敏感性分析；
│   │                                 # 缺少 Rscript 时降级为纯 Python 步骤
│   ├── ml-auditor/                   # [gates]     数据泄漏与标签错误审计，基于
│   │                                 # scikit-learn（cleanlab 可选）；沙箱运行
│   ├── multi-dim-manager/            # [workspace] 参数空间展开、SHA-256 快照、
│   │                                 # 哈希审计日志、回滚到任意历史轮次
│   ├── quantitative-validator/       # [gates]     分子式与化学方程式的原子守恒
│   │                                 # （Hill 记法文法 + rdkit 交叉校验）；沙箱运行
│   ├── reference-auditor/            # [gates]     DOI 抽取与 Crossref 核验；
│   │                                 # 假 DOI 直接 FAIL 门禁
│   ├── task-organizer/               # [workspace] 四区工作区初始化、文件整理
│   │                                 # （C1–C8 校验、去重、快照、撤销/重做）、
│   │                                 # _broadcast/INDEX.md 上下文索引
│   └── video-tracker/                # [ingest]    OpenCV 坐标提取（CSRT/Template）、
│                                     # FFT 频谱分析、物理一致性探针
├── tests/                            # 自动化测试套件（291 个测试）
└── THIRD_PARTY_LICENSES.txt          # 第三方许可清单
```

---

## 测试

```bash
python -m pytest tests/ -q
```

共 291 个测试（290 通过，1 跳过：本机缺 v1.0.0 源树）。测试套件覆盖：门禁契约、清单 schema 校验、扁平布局强制、流水线规划与 FAIL 终止、迁移守卫、legacy D1–D5 与 FFT/物理探针、v1.1.x 新增的 5 个技能、工作区输入路径解析、`--inputs` 自动接线、统一调试层、清单契约套件（四平台插件清单，以及 SKILL.md frontmatter 一致性）、无插件宿主的规则文件适配器、4 个重型技能的真实逻辑与 `UNVERIFIED` 降级，以及仓库一致性守卫：每个技能的文档、清单、入口、`LICENSE` 与声明依赖始终保持一致。

## 已知局限

诚实的边缘情况声明；依赖以下输出前请务必注意：

- **自动 ROI 检测会翻车**：`video-tracker` 在低对比度视频上可能失败，每次运行必须对照参考验证。标记为*实验/不稳定*。
- **公式检查不是数学证明**：`formula-validator` 是确定性判定。返回 `unknown` 代表某项检查“弃权”，这是合法状态，绝不能强行解释为通过。
- **纵向分析依赖 R 语言**：`longitudinal-analysis` 的某些高级统计步骤经由 R 脚本执行；若环境中缺失 `Rscript`，这些步骤会被跳过并记入日志，**绝不要试图用 Python 手写代码替代被跳过的 R 步骤**。
- **版本追踪是结构化而非语义化的**：`document-evolution-tracker` 按块对齐做 diff；某个概念只有在字面匹配时才被认为“存在”。
- **DOI 审计只验证存在性**：`reference-auditor` 确认 DOI 在 Crossref 中存在，不确认它就是你引用的那篇文献——引用正确性仍是作者的责任。
- **数据体检不洗数据**：`data-profiler` 只报告缺失值/异常值/重复行，从不修改输入文件。
- **确定性仅限调度层**：调度器能保证相同的输入路由到相同的技能，但无法让一个本身非确定性的底层算法变得确定。

## 报告问题与反馈

**常规 Bug / 功能建议**：首选在仓库的 [Issues](https://github.com/JiamingShi-JsPhys/chelate-shell/issues) 页面提交。提交时请附上：复现步骤、预期行为、实际行为以及运行环境（操作系统、Python 版本）。

**安全漏洞报告（仅限此类型）**：请**不要**在公开的 Issues 页面提交。请发送邮件至 `jiamingshi_git@outlook.com`。

- **邮件主题**：必须包含前缀 `_report` 以及具体技能名与简述。
  - 示例：`report_chelate-shell: 路径穿越漏洞可读取任务文件夹之外的路径`
- **邮件正文**：必须包含详细的复现步骤、运行环境。
- 针对“文件丢失或损坏”的严重报告，请附带前后目录树结构（`tree` 输出）与生成的 `verification_report.md`。

*提交清晰、可复现 Issue 或 Pull Request 的贡献者，将被列入下个版本 Release 说明的致谢名单。*

## 商标声明

“PASCO” 与 “Capstone” 是 PASCO Scientific 的注册商标。`capstone-labmate` 技能是独立的第三方互操作与教学辅助工具，与 PASCO Scientific 无隶属、赞助或背书关系。所有 `.cap` 解析均在本地运行；使用者有责任遵守所在机构的学术诚信政策。

## 开源许可与作者

本仓库整体采用 [MIT License](LICENSE) 发布，详见根目录下的 `LICENSE` 文件。每个技能目录也携带具有相同条款的独立 `LICENSE` 文件。

**作者与维护者**：Jiaming Shi（Westlake University）
