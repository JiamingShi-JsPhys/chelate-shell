# Chelate Shell（螯合壳）

> **The missing orchestrator for your local agent skills.**
> 把散落的本地技能，螯合成一个确定性的科研与工程工作流。

[English](README.md) · **简体中文**

**版本：** 1.1.0 | **核心技能数：** 14 | **架构：** 物理扁平化 + 微内核调度

---

## 安全与开源声明

> **免责声明**：本仓库包含作者为自动化科研工作流而开发的辅助工具，并非经过同行评审的学术项目。部分样板代码或实用脚本可能在 AI 辅助下生成，并经过作者高层面的审查与修改整合。作者对任何第三方代码问题不承担责任，但承诺及时处理任何合理的诉求。
> 
> 本工具**永远不会代替你做实验**。数据必须由学生在实验室手动采集，AI 在实验环节物理隔离。生成的报告仅为“数据分析草稿”，最终学术责任由使用者本人及所在机构承担。

> **商标声明**："PASCO" 与 "Capstone" 是 PASCO Scientific 的注册商标。`capstone-labmate` 是独立的第三方互操作与教学辅助工具，与 PASCO Scientific 无隶属、赞助或背书关系。

---

## 为什么需要 Chelate Shell？

当前 AI 生态里，每个技能（Skill）都在解决单点问题：校验公式、追踪视频、整理文件。但当 Agent 面对复杂任务时，它常常不知道**该按什么顺序、在什么位置调用哪个技能**。

Chelate Shell 是一个**微内核调度器（Microkernel Router）**，它自身不写底层代码去解领域问题。它读取每个技能的 `manifest.json` 建立路由表，确定性地把任务按阶段分发给对应技能，并用硬门禁守住质量底线。

### v1.1.0 核心架构

14 个技能**全部平铺**在 `skills/` 下（无 `namespaces/` 之类嵌套目录），逻辑层级全部写进 `manifest.json`：

```text
chelate-shell/
├── .claude-plugin/    # Claude Code 插件清单（plugin.json + marketplace.json）
├── .codebuddy-plugin/ # CodeBuddy 插件清单
├── .codex-plugin/     # Codex 插件清单
├── .dsh-plugin/       # DeepSeek Harness 插件入口（index.js，导出 name + apply）
├── assets/            # icon.png（插件图标）
├── index.js / package.json / cordis.patch.yml  # dsh 生态打包文件
├── ORCHESTRATOR.md    # 给 Agent 看的路由契约（v1.1.0）
├── core/          # 微内核：router.py（调度）+ registry.py（路由表）+ sandbox.py（隔离）
├── contracts/     # 全局契约：gate_result.py + schema.json
├── lib/chelate_core/  # 全局核心库：共享算法与适配器工具箱（程序提到外面）
├── skills/        # 14 个技能，完全平铺，每个都是薄壳
│   ├── SKILL.md       # 给 AI 看的说明书
│   ├── manifest.json  # 给 Router 看的通行证
│   ├── README.md      # 给人看的说明
│   ├── LICENSE        # 授权协议
│   ├── run.py         # 极薄适配器（只做参数转换，不写核心算法）
│   └── assets/        # 配置与模板等死资源
└── tests/         # 自动化测试（含能力清点守卫，防阉割）
```

### 四平台插件清单

仓库同时是四个宿主平台的插件，`.claude-plugin/`、`.codebuddy-plugin/`、
`.codex-plugin/`、`.dsh-plugin/` 各自持有对应平台的 `plugin.json`。v1.0.0 的
清单曾被 Claude Code **静默拒绝**，根因是两个字段格式错误，现已修复并被
`tests/test_plugin_manifests.py` 锁定：

- **`author` 必须是对象** `{"name": "Jiaming Shi"}`——写成裸字符串会导致校验失败、插件被直接忽略；
- **`skills` 字段省略**——原来写成字符串 `"./skills"` 同样校验失败；省略后宿主会自动扫描根目录的 `skills/` 文件夹，正好契合本项目的扁平结构；
- **`icon` 不放 `plugin.json`**——这是第二个被拒原因，图标只留在仓库的 `assets/icon.png`。

所有 `manifest.json` / `plugin.json` / `package.json` 的 `version` 保持一致（当前 1.1.0），测试套件对任何不一致直接报错。

**阶段划分（manifest 中的 `stage` 字段）：**

| 阶段 | 技能 |
|------|------|
| `workspace` 基建 | task-organizer、multi-dim-manager、document-evolution-tracker |
| `ingest` 提取 | capstone-labmate、video-tracker、fulltext-extractor、literature-retriever、bibtex-normalizer |
| `gates` 门禁 | formula-validator、longitudinal-analysis、conflict-detector、reference-auditor、data-profiler |
| `processors` 加工 | ai-trace-remover |

### 门禁契约

所有 `gates` 阶段技能完成执行后，必须写出结构化裁决到 `process/gates/<skill>_<ts>.json`：

```json
{
  "skill": "reference-auditor",
  "status": "FAIL",
  "evidence_level": "EXACT",
  "reason": "量纲不匹配 / DOI 不存在 …",
  "artifacts": ["process/gates/…"]
}
```

**任一 gate 返回 `FAIL`，Router 立即终止流水线**：中间产物永远锁死在 `process/`，严禁进入 `results/`；只有全部门禁通过，产物才晋升到 `results/promoted_<ts>/`。

### 路由规则

*   **简单任务旁路**：单次公式检查、一次性去 AI 味。直接调用对应技能，不建目录。
*   **复杂任务强制**：任何涉及交付物的多步任务，**第一步必须先调用 `task-organizer`**，建立四区工作区结构。
*   **流转流向**：输入从初始区读，中间产物写 `process/`，最终结果写 `results/`。
*   **出厂质检**：`results/` 里的最终交付物，必须经过门禁阶段技能把关后方可晋升。
*   *调度器的完整契约见根目录 `README.md` 与 `docs/CONSTRUCTION_PLAN.md`。*

---

## 安装与下载 (Installation)

本仓库是一个跨平台的 Agent 技能套件。请选择最适合你的安装方式：

### 方法一：通过 Git 链接安装（最推荐，Agent 原生方式）

1. 打开你所在平台的插件管理（或市场配置）界面。
2. 选择“从 Git 仓库安装”或“添加自定义市场”。
3. 输入本仓库地址并确认：`https://github.com/JiamingShi-JsPhys/chelate-shell`

### 方式二：让 AI 帮你装

直接复制以下 Prompt 发给你的 AI Agent，它会自动完成克隆和配置：

> "请访问 GitHub 仓库 `https://github.com/JiamingShi-JsPhys/chelate-shell`，克隆该仓库，并根据当前 Agent 平台的规范，将 `skills/` 目录下的所有技能注册到你的系统中。"

> **警告**：使用 AI 自动安装时，AI 极大概率会将 `skills/` 目录下的独立技能直接打散，并平铺复制到平台的全局技能目录中。这会导致 Chelate Shell 的“微内核自动调度架构”失效，退化为 14 个散装技能。如果你需要完整的插件调度功能，请使用方式一。

**环境依赖提示**：微内核与多数技能仅依赖 Python 标准库。少数涉及数据处理/网络的技能需要第三方库（见下方依赖矩阵）。缺失依赖时，系统会优雅降级为 `UNVERIFIED` 门禁并给出提示，不会直接崩溃。

---

## 快速上手 (Quick Start)

所有命令均在仓库根目录执行，**绝不硬编码绝对路径**。

**1. 查看路由表（14 个技能）**
```bash
python cli.py list
```

**2. 跑一条完整流水线（干跑）**
```bash
python cli.py pipeline --root /path/to/workspace --mode a --dry-run
```

**3. 初始化复杂任务工作区**
```bash
python skills/task-organizer/run.py --root <workspace> --action init
python skills/task-organizer/run.py --root <workspace> --action broadcast
```

**4. 确定性校验物理公式（旁路模式）**
```bash
python skills/formula-validator/run.py --root <workspace> --action validate \
    -- --expr "F = m*a" --units F=N --units m=kg --units a=m/s**2
```

**5. 审计草稿中的 DOI（假 DOI 直接 FAIL 并终止流水线）**
```bash
python skills/reference-auditor/run.py --root <workspace> --action audit --input draft.md
```

**6. 去除草稿的 AI 痕迹**
```bash
python skills/ai-trace-remover/run.py --root <workspace> --action scan -- <file>
```

**7. 用 `--inputs` 声明本次运行的输入文件（自动接线）**
```bash
python cli.py pipeline --root ./test_workspace --inputs 我的文件.md data.csv
```
每个文件按 `--root` 解析（相对路径以工作区根为准，绝对路径原样使用）；
文件缺失时在运行任何技能之前直接报错退出（exit 2）。声明输入后，流水线
只保留 manifest `input_types` 覆盖这些文件类型的技能（`--selected` 显式
选择优先），且每个文件会作为 `--input` 自动传给对应的适配器——扩展名
未声明任何 manifest 类型的文件会打印 `[INPUT]` 警告且不接线。

---

## 技能依赖矩阵

| 技能 | 必需依赖 | 可选依赖（缺失则对应功能降级，不会崩溃） |
| --- | --- | --- |
| `task-organizer` | 无 | `openpyxl`（xlsx 快速通道）, `PyPDF2`（PDF 后端之一） |
| `multi-dim-manager` | 无 | `PyYAML`（读取 `.yaml` 配置；JSON 配置零依赖） |
| `document-evolution-tracker` | 无 | `PyYAML`（读取 `.yaml` 配置；JSON 配置零依赖） |
| `capstone-labmate` | 无 | `numpy`（向量化加速）, `matplotlib`（绘图）, `pypdf`（PDF 文本） |
| `video-tracker` | `numpy`, `opencv-python` | `matplotlib`（FFT 频谱图）, `PyYAML`（`.yaml` 配置） |
| `longitudinal-analysis` | `pandas` | `numpy`, `R (lme4, lavaan)`, `python-docx`（docx 导出）, `PyYAML`（`.yaml` 配置） |
| `formula-validator` | `sympy`, `numpy`, `pint` | 无 |
| `conflict-detector` | 无 | `PyYAML`（读取 `.yaml` 配置；JSON 配置零依赖） |
| `ai-trace-remover` | 无 | 无 |
| `fulltext-extractor` | `PyMuPDF` | 无 |
| `literature-retriever` | `arxiv` | 无 |
| `bibtex-normalizer` | `bibtexparser` | 无 |
| `reference-auditor` | `requests` | 无 |
| `data-profiler` | `pandas` | 无 |

所有第三方库均为运行时导入，**本仓库不内置（vendored）任何第三方代码**；可选依赖全部位于 `try`/`ImportError` 或按动作条件导入之后，缺失时只降级对应功能。

---

## 调试与诊断 (Debugging)

一个开关，覆盖全链路：给任何 `cli.py` 子命令（`list` / `run` / `pipeline`）或
`core/router.py` 加 `--debug`，或直接设置环境变量 `CHELATE_DEBUG=1`（会被所有
技能子进程继承）。调试输出一律走 stderr 并带 `[chelate:debug]` 前缀，stdout 的
门禁契约 JSON 行不受污染。

```bash
# 单个技能调试（--debug 放技能名前后均可）
python cli.py run data-profiler --root /path/to/workspace --action profile --input data.csv --debug

# 整条流水线调试
CHELATE_DEBUG=1 python cli.py pipeline --root /path/to/workspace --mode c --selected reference-auditor
```

调试信息覆盖：路由表扫描、实际子进程命令与工作目录、依赖裁决（降级/缺失）、
每个技能的返回码/耗时/stderr 尾部、legacy 动作到模块的映射、最终门禁路径与
状态。彩色输出遵循 `NO_COLOR` / `CHELATE_FORCE_COLOR`。事后取证产物：
`process/gates/<skill>_<ts>.json`、`results/pipeline_report_<ts>.json`、
`_broadcast/pipeline_index_<ts>.json`。

---

## 已知局限 (Limitations)

诚实的边缘情况声明；依赖以下输出前请务必注意：

- **自动 ROI 检测会翻车**：`video-tracker` 在低对比度视频上可能失败，每次运行必须对照参考验证。标记为*实验/不稳定*。
- **公式检查不是数学证明**：`formula-validator` 是确定性判定。返回 `unknown` 代表某项检查“弃权”，这是合法状态，绝不能强行解释为通过。
- **纵向分析依赖 R 语言**：`longitudinal-analysis` 的某些高级统计步骤经由 R 脚本执行；若环境中缺失 `Rscript`，这些步骤会被跳过并记入日志，**绝不要试图用 Python 手写代码替代被跳过的 R 步骤**。
- **版本追踪是结构化而非语义化的**：`document-evolution-tracker` 按块对齐做 diff；某个概念只有在字面匹配时才被认为“存在”。
- **DOI 审计只验证存在性**：`reference-auditor` 确认 DOI 在 Crossref 中存在，不确认它就是你引用的那篇文献——引用正确性仍是作者的责任。
- **数据体检不洗数据**：`data-profiler` 只报告缺失值/异常值/重复行，从不修改输入文件。
- **确定性仅限调度层**：调度器能保证相同的输入路由到相同的技能，但无法让一个本身非确定性的底层算法变得确定。

---

## 报告问题与反馈 (Report Issues)

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

## 开源许可与作者 (License & Author)

本仓库整体采用 [MIT License](LICENSE) 发布，详见根目录下的 `LICENSE` 文件。每个技能包内也可能携带独立的 `LICENSE` 声明。

**Author & Maintainer**: Jiaming Shi (Westlake University)
