# Chelate Shell（螯合壳）

> **The missing orchestrator for your local agent skills.**
> 把散落的本地技能，螯合成一个确定性的科研与工程工作流。

[English](README.md) · **简体中文**

**版本：** 1.1.2 | **核心技能数：** 14 | **架构：** 4 层（workspace / ingest / gates / processors）

---

## 安全与开源声明

> **免责声明**：本仓库包含作者为自动化科研工作流而开发的辅助工具，并非经过同行评审的学术项目。部分样板代码或实用脚本可能在 AI 辅助下生成，并经过作者高层面的审查与修改整合。作者对任何第三方代码问题不承担责任，但承诺及时处理任何合理的诉求。
>
> 本工具**永远不会代替你做实验**。数据必须由学生在实验室手动采集，AI 在实验环节物理隔离。生成的报告仅为“数据分析草稿”，最终学术责任由使用者本人及所在机构承担。

> **商标声明**："PASCO" 与 "Capstone" 是 PASCO Scientific 的注册商标。`capstone-labmate` 是独立的第三方互操作与教学辅助工具，与 PASCO Scientific 无隶属、赞助或背书关系。所有 `.cap` 解析均在本地运行；用户有责任遵守所在机构的学术诚信政策。

---

## 为什么需要 Chelate Shell？

当前 AI 生态里，每个技能（Skill）都在解决单点问题：校验公式、追踪视频、整理文件。但当 Agent 面对复杂任务时，它常常不知道**该按什么顺序、在什么位置调用哪个技能**。

Chelate Shell 是一个**编排器（Orchestrator）**。它自身不写底层代码去解领域问题。它像一位高级项目经理：拆解用户意图、强制标准化工作区目录结构，并**确定性地**把任务路由到对应技能。

### v1.1.0 架构：物理扁平 + 适配器隔离 + 微内核

14 个技能**全部平铺**在 `skills/` 下（无嵌套分类目录），这样单层扫描的 AI 平台能发现每一个技能。逻辑分层信息存放在每个技能的 `manifest.json` 中，由微内核 `core/` 读取并构建流水线。

```text
chelate/
├── .claude-plugin/            # Claude Code 插件清单 + 市场配置
├── .codebuddy-plugin/         # CodeBuddy 插件清单 + 市场配置
├── .codex-plugin/             # Codex 插件清单 + 市场配置
├── .dsh-plugin/               # DeepSeek Harness CJS 入口（apply(ctx)）
├── assets/                    # icon.png（插件清单共享）
├── index.js                   # CJS 插件入口（dsh 生态）
├── package.json               # npm/dsh 打包元数据
├── cordis.patch.yml           # cordis bundle 补丁
├── ORCHESTRATOR.md            # 给 Agent 看的路由契约（v1.1.0）
├── core/                      # 微内核
│   ├── router.py                # 调度器：manifest 驱动的流水线
│   ├── registry.py              # 扫描 skills/ 构建路由表
│   └── sandbox.py               # 依赖解析 / 降级
├── contracts/                   # 全局契约
│   ├── gate_result.py           # {skill, status, evidence_level, reason, artifacts}
│   └── schema.json              # manifest.json 校验规范
├── lib/chelate_core/            # 共享核心库（逻辑都在这里）
│   ├── adapter.py               # 薄适配器工具箱：argparse、门禁发射、legacy 运行器
│   ├── paths.py / yamlmini.py   # 路径解析 / assets/config.yaml 加载
│   ├── pdf_text.py              # PDF 提取核心（pdfminer.six / pypdf）
│   ├── arxiv_search.py          # arXiv 搜索核心
│   ├── bibtex_norm.py           # BibTeX 解析 / 去重 / 规范化核心
│   ├── doi_audit.py             # DOI 提取 + Crossref 验证核心
│   ├── csv_profile.py           # CSV 画像核心（pandas）
│   └── formula_merge.py         # legacy D1-D5 + pint 裁决合并策略
├── skills/                      # 14 个技能，完全平铺
│   ├── task-organizer/          #   workspace  （基础设施）
│   ├── multi-dim-manager/       #   workspace  （基础设施）
│   ├── document-evolution-tracker/ # workspace （基础设施）
│   ├── capstone-labmate/        #   ingest     （提取）
│   ├── video-tracker/           #   ingest     （提取）
│   ├── fulltext-extractor/      #   ingest     （提取，新增）
│   ├── literature-retriever/    #   ingest     （提取，新增）
│   ├── bibtex-normalizer/       #   ingest     （提取，新增）
│   ├── formula-validator/       #   gates
│   ├── longitudinal-analysis/   #   gates
│   ├── conflict-detector/       #   gates
│   ├── reference-auditor/       #   gates      （新增）
│   ├── data-profiler/           #   gates      （新增）
│   └── ai-trace-remover/        #   processors
│       ├── SKILL.md             #   给 AI 平台的指令
│       ├── manifest.json        #   给 Router 的元数据
│       ├── README.md            #   给人看的文档
│       ├── LICENSE              #   MIT（每技能独立副本）
│       ├── run.py               #   薄适配器：仅 CLI 接线
│       └── assets/              #   config.yaml 等静态资源
└── tests/                       # 自动化测试套件（156 个测试）
```

每个技能目录都携带同一套表面：`SKILL.md` 给 AI，`manifest.json` 给 Router，`README.md` 给人，`LICENSE`，以及 `run.py`——一个**薄适配器**，只负责解析参数和格式化门禁结果。

### 四平台插件清单（Claude Code / CodeBuddy / Codex / dsh）

仓库同时是四个宿主平台的插件。每个 `.xx-plugin/` 目录存放该平台的 `plugin.json`（平台有市场配置时还有 `marketplace.json`）。v1.0.0 的清单曾因两个契约违规被 Claude Code **静默拒绝**，现已被 `tests/test_plugin_manifests.py` 锁定：

- **`author` 必须是对象**（`{"name": "Jiaming Shi"}`），不能是裸字符串——字符串会导致校验失败，插件被直接忽略。
- **`skills` 字段省略，而非 `"./skills"`**——这里写字符串同样会校验失败；字段缺失时宿主会自动扫描 `skills/` 目录，恰好匹配本项目的扁平布局。（写字符串列表也合法，但没必要。）
- **`icon` 不放在 `plugin.json` 中**——这是第二个被拒原因；共享的 `assets/icon.png` 留在仓库供人使用。

`version` 在所有技能 manifest、所有 `plugin.json` 和 `package.json` 中保持单一值（当前 1.1.2）；测试套件在任何不一致时失败。

### 程序在技能之外

业务逻辑**从不**实现在技能文件夹内。5 个新技能是 `lib/chelate_core/*` 之上的纯接线；9 个迁移技能保持字节级不变的旧代码树，通过 `lib/chelate_core/adapter.py` 驱动。后果：

- **无重复代码**——一个 PDF 解析器、一个 Crossref 客户端、一个 BibTeX 去重器，被所有消费者共享。
- **核心可测试**——`tests/test_new_skills.py` 直接测试库；守卫测试（`tests/test_no_stubs.py`）在技能文件夹重新实现核心函数或超出适配器预算时失败。
- **崩溃隔离**——重依赖在库核心内导入；损坏的核心降级为 `UNVERIFIED` 门禁，而不是拖垮流水线。

### Manifest 契约

```json
{
  "name": "formula-validator",
  "version": "1.1.2",
  "stage": "gates",
  "input_types": ["latex_string", "plain_text"],
  "output_type": "gate_result",
  "output_types": ["gate_result"],
  "dependencies": ["sympy", "numpy", "pint"],
  "sandbox_required": false,
  "entrypoint": "run.py",
  "description": "..."
}
```

`sandbox_required` 标记必须隔离运行的技能（预留给 v1.2.0 的重依赖场景；v1.1.0 所有技能为 `false`）。完整规范见 `contracts/schema.json`（`additionalProperties: false`——未知字段被拒绝，契约不会腐烂）。

### 门禁契约

所有 `gates` 阶段技能返回结构化结果：

```json
{
  "skill": "reference-auditor",
  "status": "FAIL",
  "evidence_level": "EXACT",
  "reason": "DOI 10.9999/fake-doi-12345 not found in Crossref",
  "artifacts": ["process/reference_audit_20261023T114148Z.json"]
}
```

`status` 为 `PASS` / `FAIL` / `UNVERIFIED`；`evidence_level` 为 `EXACT` / `SYMBOLIC` / `EMPIRICAL` / `UNVERIFIED`。**只有 `FAIL` 会硬阻断流水线。**

### 流水线执行

1. **Registry**：启动时 Router 扫描 14 个 `manifest.json`（`skills/` 下恰好一层）构建内存路由表。
2. **Ingest**：按类型匹配输入——`.pdf` 排队 `fulltext-extractor`（和 `capstone-labmate`），`.bib` 排队 `bibtex-normalizer`，关键词排队 `literature-retriever`。
3. **Gates**：门禁技能串行执行——`formula-validator` → `reference-auditor` → `data-profiler` → `longitudinal-analysis` → `conflict-detector`。
4. **硬阻断**：第一个返回 `FAIL` 的门禁立即终止流水线（红色终端输出）。中间产物锁定在 `process/`，永不晋升到 `results/`。
5. **晋升**：只有全部门禁通过后，`process/` 才复制到 `results/promoted_<ts>/`，随后进入 processors 阶段。

### 调试

一个开关，覆盖所有层：给任何 `cli.py` 子命令（`list` / `run` / `pipeline`）或 `core/router.py` 加 `--debug`，或导出 `CHELATE_DEBUG=1` 对整个进程树生效。该开关设置同一个环境变量，因此技能子进程会自动继承。

```bash
# 直接调试单个技能（--debug 放在技能名前后均可）
python cli.py run data-profiler --root /path/to/workspace --action profile --input data.csv --debug

# 调试整条流水线
CHELATE_DEBUG=1 python cli.py pipeline --root /path/to/workspace --mode c --selected reference-auditor
```

开启后，stderr 收到 `[chelate:debug]` 行，覆盖：路由表扫描、解析后的子进程命令与 cwd、依赖判定（降级 / 缺失）、返回码与耗时、每个技能最后几行 stderr、legacy action → 模块映射、最终门禁路径与状态。**stdout 永不被污染**——单行门禁契约 JSON 保持机器可解析。输出颜色遵循 `NO_COLOR` / `CHELATE_FORCE_COLOR`。

事后分析方面，每次运行留下机器可读轨迹：`process/gates/<skill>_<ts>.json`（每个技能一个门禁结果）、`results/pipeline_report_<ts>.json`（完整决策记录，含命令、降级标志、缺失依赖、返回码、每个技能的秒数）、`_broadcast/pipeline_index_<ts>.json`（紧凑上下文压缩索引）。

---

## 安装与下载

本仓库是一个跨平台的 Agent 技能套件。请选择最适合你的安装方式：

### 方法一：通过 Git 链接安装（最推荐，Agent 原生方式）

1. 打开你所在平台的插件管理（或市场配置）界面。
2. 选择“从 Git 仓库安装”或“添加自定义市场”。
3. 输入本仓库地址并确认：`https://github.com/JiamingShi-JsPhys/chelate-shell`

### 方法二：让 AI 帮你装

直接复制以下 Prompt 发给你的 AI Agent，它会自动完成克隆和配置：

> "请访问 GitHub 仓库 `https://github.com/JiamingShi-JsPhys/chelate-shell`，克隆该仓库，并根据当前 Agent 平台的规范，将 `skills/` 目录下的所有技能注册到你的系统中。"

> **警告**：使用 AI 自动安装时，AI 极大概率会将 `skills/` 目录下的独立技能直接打散，并平铺复制到平台的全局技能目录中。这会导致 Chelate Shell 的“微内核自动调度架构”失效，退化为 14 个散装技能。如果你需要完整的插件调度功能，请使用方法一。

**环境依赖提示**：微内核与多数技能仅依赖 Python 标准库。少数涉及数据处理 / 网络的技能需要第三方库（见下方依赖矩阵）。缺失依赖时，系统会优雅降级为 `UNVERIFIED` 门禁并给出提示，不会直接崩溃。

---

## 快速上手

所有命令均在仓库根目录执行，**绝不硬编码绝对路径**。

```bash
# 列出 14 个已注册技能
python cli.py list

# 直接运行单个技能
python cli.py run reference-auditor --root /path/to/workspace \
    --action audit --input draft.md

# 干跑一条流水线（显示计划执行顺序）
python cli.py pipeline --root /path/to/workspace --mode a --input-kind pdf --dry-run

# 完整流水线：ingest -> gates -> processors
python cli.py pipeline --root /path/to/workspace --mode a --input-kind pdf

# 仅门禁，带逐技能参数
python cli.py pipeline --root /path/to/workspace --mode c \
    --selected reference-auditor \
    --skill-arg "reference-auditor:--input draft.md"

# 声明本次运行的输入文件：每个文件会作为 --input 传给
# manifest input_types 覆盖其类型的计划技能（缺失文件在运行前
# 以 exit 2 快速失败）
python cli.py pipeline --root ./test_workspace --inputs draft.md data.csv
```

流水线模式：`a` 自动（ingest → gates → processors），`b` 仅提取，`c` 仅门禁。`--inputs` 将计划收窄到能消费声明文件的技能（显式 `--selected` 列表始终优先）；扩展名未声明任何 manifest 类型的文件会打印 `[INPUT]` 警告且不接线。

### 技能专项命令

```bash
# 初始化复杂任务工作区
python skills/task-organizer/run.py --root <workspace> --action init
python skills/task-organizer/run.py --root <workspace> --action broadcast

# 确定性校验物理公式（旁路模式）
python skills/formula-validator/run.py --root <workspace> --action validate \
    -- --expr "F = m*a" --units F=N --units m=kg --units a=m/s**2

# 审计草稿中的 DOI（假 DOI 直接 FAIL 并终止流水线）
python skills/reference-auditor/run.py --root <workspace> --action audit --input draft.md

# 去除草稿的 AI 痕迹
python skills/ai-trace-remover/run.py --root <workspace> --action scan -- <file>
```

---

## 14 个技能

**Workspace（基础设施）**
- `task-organizer` — 四区工作区初始化、文件组织（C1–C8 校验、去重、快照、撤销/重做）、`_broadcast/INDEX.md` 上下文索引
- `multi-dim-manager` — 参数空间扩展、SHA-256 快照、哈希审计日志、安全回滚到任意历史轮次
- `document-evolution-tracker` — 跨文档版本的段落级 diff 与概念谱系追踪

**Ingest（提取）**
- `capstone-labmate` — PASCO Capstone `.cap` 二进制解析、CSV/JSON 转换、带水印草稿报告
- `video-tracker` — OpenCV 坐标提取（CSRT/Template 跟踪器）、FFT 频谱分析、物理一致性探测
- `fulltext-extractor` *（新）* — pdfminer.six 文本提取到 `process/`（pypdf 回退）
- `literature-retriever` *（新）* — arXiv 关键词搜索到 JSON
- `bibtex-normalizer` *（新）* — `.bib` 解析、去重、规范化输出

**Gates（门禁）**
- `formula-validator` — SymPy D1–D5 层（量纲分析、极限枚举、数值采样、符号证明）与 `pint` 物理单位交叉检查合并
- `longitudinal-analysis` — 时间序列 OLS 加 R 后端 LMM（lme4）、中介分析（lavaan）和敏感性分析；无 Rscript 时降级为纯 Python 步骤
- `conflict-detector` — 跨文档矛盾引擎，带正则数字提取硬交叉检查
- `reference-auditor` *（新）* — DOI 提取与 Crossref 验证；不存在的 DOI 使门禁失败
- `data-profiler` *（新）* — pandas CSV 画像：行数、缺失值统计、1.5·IQR 离群比、重复值、常量列

**Processors（处理器）**
- `ai-trace-remover` — 模板句移除 + 0–100 "AI 相似度"评分（洁净室英文词库加完整中文词库）

---

## 迁移保证（v1.0.0 → v1.1.0）

9 个旧技能**字节级**迁移：179 个 Python 文件（约 37,400 行）及所有非代码资产经 SHA-256 验证复制，内部包布局（`scripts.*`、`src.*`、`R/`、`templates/`、`config/`）不变。唯一新增是每个技能的根 `run.py` 适配器、其 `manifest.json`，以及 `formula-validator` 的新 `scripts/core/pint_units.py` 层。守卫测试（`tests/test_capability_guard.py`）每次运行重新验证文件一致性和每个关键模块函数的存在性。

---

## 测试

```bash
python -m pytest tests/ -q     # 156 个测试
```

套件覆盖：门禁契约、manifest schema 校验、扁平布局强制、流水线规划与 FAIL 终止、迁移守卫、legacy D1–D5 与 FFT/物理探测、5 个新技能、工作区输入路径解析、`--inputs` 自动接线（manifest 类型匹配、计划收窄、缺失文件快速失败）、统一调试层（开关语义 + router 调试管道的真实子进程集成测试），以及 manifest 契约套件（四个宿主平台的插件 manifest：author 对象、无字符串 `skills`、无 `icon`、版本同步；SKILL.md frontmatter 与各 manifest 一致）。

---

## 依赖矩阵（Requirements）

Python 3.10+。每个技能的依赖在其 `manifest.json` 中声明，运行时由 `core/sandbox.py` 解析；缺失依赖使技能降级为 `UNVERIFIED` 门禁而非崩溃流水线。

| 技能 | 必需依赖 | 可选（优雅降级） |
|-------|----------------------|------------------------------|
| video-tracker | numpy, opencv | matplotlib（FFT 图）, PyYAML（`.yaml` 配置） |
| formula-validator | sympy, numpy, pint | — |
| longitudinal-analysis | pandas | numpy, R（lme4/lavaan）, python-docx（`--format docx` 导出）, PyYAML（`.yaml` 配置） |
| capstone-labmate | *（仅标准库）* | numpy（向量化路径）, matplotlib（绘图）, pypdf（PDF 文本） |
| task-organizer | *（仅标准库）* | openpyxl（快速 `.xlsx` 路径）, PyPDF2（一个 PDF 后端） |
| multi-dim-manager, document-evolution-tracker, conflict-detector | *（仅标准库）* | PyYAML（`.yaml` 配置；JSON 配置零依赖） |
| ai-trace-remover | *（仅标准库）* | — |
| fulltext-extractor | pdfminer.six / pypdf | — |
| literature-retriever | `arxiv` | — |
| bibtex-normalizer | `bibtexparser` | — |
| reference-auditor | `requests` | — |
| data-profiler | `pandas` | — |

第三方包仅在运行时使用；本仓库不内置（vendored）任何第三方代码，各自保留原许可证（如 numpy/pandas BSD、OpenCV Apache-2.0、SymPy/pint/requests/bibtexparser/arxiv BSD/MIT/Apache，pdfminer.six 为 MIT，pypdf 为 BSD-3-Clause——均为宽松许可证）。可选依赖通过 `try`/`ImportError` 或按动作条件导入，缺失时仅降级该功能（或该配置格式），绝不降级整个技能。

---

## 已知局限

诚实的边缘情况声明；依赖以下输出前请务必注意：

- **自动 ROI 检测会翻车**：`video-tracker` 在低对比度视频上可能失败，每次运行必须对照参考验证。标记为*实验/不稳定*。
- **公式检查不是数学证明**：`formula-validator` 是确定性判定。返回 `unknown` 代表某项检查“弃权”，这是合法状态，绝不能强行解释为通过。
- **纵向分析依赖 R 语言**：`longitudinal-analysis` 的某些高级统计步骤经由 R 脚本执行；若环境中缺失 `Rscript`，这些步骤会被跳过并记入日志，**绝不要试图用 Python 手写代码替代被跳过的 R 步骤**。
- **版本追踪是结构化而非语义化的**：`document-evolution-tracker` 按块对齐做 diff；某个概念只有在字面匹配时才被认为“存在”。
- **DOI 审计只验证存在性**：`reference-auditor` 确认 DOI 在 Crossref 中存在，不确认它就是你引用的那篇文献——引用正确性仍是作者的责任。
- **数据体检不洗数据**：`data-profiler` 只报告缺失值/异常值/重复行，从不修改输入文件。
- **确定性仅限调度层**：调度器能保证相同的输入路由到相同的技能，但无法让一个本身非确定性的底层算法变得确定。

---

## 报告问题与反馈

**常规 Bug / 功能建议**：
首选在仓库的 [Issues](https://github.com/JiamingShi-JsPhys/chelate-shell/issues) 页面提交。提交时请附上：复现步骤、预期行为、实际行为以及运行环境（操作系统、Python 版本）。

**安全漏洞报告（仅限此类型）**：
请**不要**在公开的 Issues 页面提交安全漏洞。请发送邮件至 `jiamingshi_git@outlook.com`。
- **邮件主题**：必须包含前缀 `agent-skill_report` 以及具体技能名与简述。
  - 示例：`agent-skill_report task-organizer: 路径穿越漏洞可读取任务文件夹之外的路径`
- **邮件正文**：必须包含详细的复现步骤、运行环境。
- 针对“文件丢失或损坏”的严重报告，请附带前后目录树结构（`tree` 输出）与生成的 `verification_report.md`。

*提交清晰、可复现 Issue 或 Pull Request 的贡献者，将被列入下个版本 Release 说明的致谢名单。*

---

## 开源许可与作者

本仓库整体采用 [MIT License](LICENSE) 发布，详见根目录下的 `LICENSE` 文件。每个技能目录也携带自己的 `LICENSE` 文件，条款相同。

**Author & Maintainer**: Jiaming Shi (Westlake University)