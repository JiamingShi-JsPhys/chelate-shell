# Chelate Shell（螯合壳）

**面向科研与工程工作流的确定性调度器——20 个科研技能随它一起交付，而且是真的会跑。**

单点技能各自解决一个问题，但 Agent 面对复杂任务时，仍得自己决定：调哪个、按什么顺序、产物放哪。Chelate Shell 把两半放进同一个仓库：20 个引擎，以及一个按固定阶段顺序调度它们、并为每次调用写下类型化门禁的微内核。

- **对科研人员：** 这些技能是真在算——SymPy 五层判定加 pint 交叉校验、RDKit 原子守恒、R 混合模型与中介分析、OpenCV 轨迹跟踪、出版级统计图，不是提示词模板。
- **对 Agent：** `core/router.py` 生成确定性计划，派发前扫描提示注入，遇到第一个 `FAIL` 就停下流水线。
- **对留痕：** 每次调用都在 `process/gates/` 留下一个 `GateResult`。`PASS`、`UNVERIFIED`、`FAIL` 是三种不同状态，只有最后一种是终止态。

[English](README.md) · **简体中文**

**版本：** 1.3.2 | **许可证：** MIT | **Python：** 3.10+ | **技能数：** 20

> 仅作科研辅助。依赖任何输出之前，请先读[安全与开源声明](#安全与开源声明)。

---

## 目录

**上手**

- [它跑起来是这样](#它跑起来是这样)
- [你可以直接这样问](#你可以直接这样问)
- [为什么需要 Chelate Shell？](#为什么需要-chelate-shell)
- [安装与下载](#安装与下载)
- [快速上手](#快速上手)

**工作原理**

- [架构与流水线](#架构与流水线)
- [1.3.0 新增的命令](#130-新增的命令)
- [1.3.0 新增的子代理](#130-新增的子代理)
- [仓库布局](#仓库布局)

**其余**

- [环境要求](#环境要求)
- [测试](#测试)
- [安全与开源声明](#安全与开源声明)
- [已知局限](#已知局限)
- [报告问题与反馈](#报告问题与反馈)
- [致谢](#致谢)
- [商标声明](#商标声明)
- [开源许可与作者](#开源许可与作者)

---

## 它跑起来是这样

```text
> /chelate-shell:formula-validator   v = d/t    单位：v=m, d=m, t=s

FAIL · SYMBOLIC
pint unit mismatch — LHS [length], RHS [length]/[time]
gate    → process/gates/formula-validator_20261112T130046Z.json
report  → process/reports/equation-4c9b2ce5-20261112-210045.md
```

量纲错了不是一句提醒：它是一次门禁失败、一份落盘的报告，以及就此停下的流水线。

## 你可以直接这样问

| 用自己的话说 | 路由到 | 拿回什么 |
|---|---|---|
| “校验 `F = m*a`，单位 F=N、m=kg、a=m/s²” | `formula-validator` | 五层检查的 PASS / FAIL，外加一份 Markdown 报告 |
| “核验 draft.md 里的每条 DOI” | `reference-auditor` | 逐条比对 Crossref；假 DOI 直接让门禁 FAIL |
| “这两版稿子对得上吗？” | `conflict-detector` | 每一处矛盾，带严重程度 |
| “体检 data.csv” | `data-profiler` | 行数、缺失值、1.5·IQR 离群值、重复行 |
| “这个标注数据集有泄漏吗？” | `ml-auditor` | 数据泄漏与标签错误的判定（scikit-learn） |
| “画一张电压随时间的图” | `sci-visualizer` | 矢量 PDF + PNG，落在 `process/figures/` |
| “抽取这些 PDF 第 3–7 页的文字” | `fulltext-extractor` | 纯文本 + JSON 旁车文件，落在 `process/` |
| “找几篇关于 X 的新论文” | `literature-retriever` | arXiv 元数据，存成 JSON |
| “把视频里的小球轨迹追出来” | `video-tracker` | 坐标、FFT 频谱、物理一致性探针 |
| “把我的报告合成一个 LaTeX 文件” | `latex-exporter` | 一份可直接编译的 `.tex` |
| “生成这个网格并检查它” | `3d-modeler` | OBJ，外加绕序 / 退化面 / 包围盒审计 |
| “这段文字是不是在尝试注入指令？” | `security-guard` | 注入标记与危险调用点 |

全部 20 个技能、各自到底算了什么，见 [仓库布局](#仓库布局)。

**怎么装：** 一条插件命令，或另外三条路径——见 [安装与下载](#安装与下载)。

---

## 为什么需要 Chelate Shell？

当前 AI 生态里，每个技能（Skill）都在解决单点问题：校验公式、追踪视频、整理文件。但当 Agent 面对复杂任务时，它常常不知道**该按什么顺序、在什么位置调用哪个技能**。散落的、无状态的技能调用，往往会导致上下文污染、文件版本混乱、甚至产生不可信的 AI 幻觉。

Chelate Shell 从两个层面回应这个问题，两者都在同一个仓库里。

**20 个技能直接实现各自的算法**，不是提示词模板。`formula-validator` 在 SymPy 之上执行五层判定，并用 pint 交叉校验单位；`quantitative-validator` 通过 RDKit 配平化学方程式；`longitudinal-analysis` 在 R 中调用 lme4 与 lavaan；`video-tracker` 在 OpenCV 中执行 CSRT 跟踪并对轨迹计算 FFT；`ml-auditor` 用 scikit-learn 检查标注数据集的数据泄漏与标签错误；`sci-visualizer` 用 matplotlib 与 seaborn 渲染出版级统计图；`fulltext-extractor` 按页区间抽取 PDF 文本；`latex-exporter` 仅用标准库把 Markdown 报告合成为可编译的 `.tex`。每个技能都已接入流水线，并纳入测试套件。

**调度器提供单个技能无法自行提供的保证。** `core/router.py` 拆解任务、强制四区工作区结构，并按确定性的阶段顺序路由，使相同输入始终产生相同计划；同时为每次调用写下一个类型化门禁，在第一个 `FAIL` 处停止流水线，缺少依赖时明确报告 `UNVERIFIED`，并维护 `_broadcast/` 索引，使后续会话只读一份摘要而不必打开所有原件。

---

## 架构与流水线

`core/router.py` 读取 20 个 manifest，按规范阶段顺序生成计划，派发前先对文本输入做
提示注入扫描，然后逐个调用技能适配器。每次调用写下一个 `GateResult`：`PASS` 继续，
`UNVERIFIED` 只让该技能降级、流水线继续，第一个 `FAIL` 则锁定 `process/` 并终止。

流程图、四个阶段与提升路径：**[docs/ARCHITECTURE_zh.md](docs/ARCHITECTURE_zh.md)**。

## 安装与下载

如果你用的是 Claude Code，装上只需要这一条：

```bash
claude plugin install chelate-shell --marketplace https://github.com/JiamingShi-JsPhys/chelate-shell.git
```

其他宿主各有各的一行命令——Codex、dsh、CodeBuddy，以及八个读规则文件的宿主——都收在 **[docs/INSTALL_COMMANDS_zh.md](docs/INSTALL_COMMANDS_zh.md)**。

一共三种装法。有插件市场的宿主把整套装成**一个插件**——这是保留微内核自动调度的唯一形式；没有插件通道的宿主则以**规则文件**接入，一个脚本就能把全部规则文件一次写好；第三种是把这件事直接交给 AI。

### 方法一：从插件市场用 URL 安装

下面每个宿主都有自己的插件市场。把本仓库的 Git URL 注册进去，再安装它列出的插件即可（URL 重复注册没有副作用，第二次会提示已存在）。

```text
/plugin marketplace add https://github.com/JiamingShi-JsPhys/chelate-shell.git#v1.3.2
/plugin install chelate-shell@chelate-shell-marketplace
```

`#v1.3.2` 把安装钉在这个发布上；去掉它则跟随默认分支。

### 方法二：用命令安装

Claude Code、Codex、dsh、CodeBuddy 用一行插件命令安装；Cursor、Windsurf、Cline、Continue、Roo Code、GitHub Copilot 与 opencode 读规则文件，一个脚本把这些文件一次写好。全部命令、全部参数与可选依赖集中在一页：**[docs/INSTALL_COMMANDS_zh.md](docs/INSTALL_COMMANDS_zh.md)**。
### 方法三：让 AI 帮你装

```bash
请访问 GitHub 仓库 `https://github.com/JiamingShi-JsPhys/chelate-shell` 并克隆它，然后运行 `python install.py --project . --global`。如果你的宿主有插件系统，请改为把整套作为单一插件安装；该脚本覆盖的是读规则文件的那些宿主。
```

> **警告**：使用 AI 自动安装时，AI 有概率会将 `skills/` 目录下的独立技能直接打散，平铺复制到平台的全局技能目录中。这会导致 Chelate Shell 的“微内核自动调度架构”失效，退化为 20 个散装技能。如果你需要完整的插件调度功能，请使用方法一。

## 快速上手

装好插件后不用离开对话框：输入 `/` 选择技能或命令即可。不需要开终端，也不需要写绝对路径——工作区就是你当前正在操作的文件夹。

### 技能

20 个技能全部注册在 `chelate-shell` 命名空间下，一个 `/` 就能调出来：

```text
/chelate-shell:task-organizer      把这个文件夹初始化成任务工作区
/chelate-shell:formula-validator   校验 F = m*a，单位 F=N、m=kg、a=m/s^2
/chelate-shell:reference-auditor   核验 draft.md 里的每条 DOI 是否存在于 Crossref
/chelate-shell:security-guard      扫描 draft.md 的提示注入与危险调用
/chelate-shell:data-profiler       体检 data.csv
```

技能名后面直接说你要做什么，由技能自己决定执行哪个动作，并写下一个门禁结果。假 DOI 不是提示一下就放过——它会让门禁 FAIL 并终止流水线。

### 1.3.0 新增的命令

两条命令把较重的引擎收成一行：

| 命令 | 作用 |
|---|---|
| `/chelate-shell:figure` | 从 CSV 或 JSON 数据集出图（柱状 / 折线 / 散点 / 箱线），输出到 `process/figures/`，同时给矢量 PDF 与位图 PNG |
| `/chelate-shell:model3d` | 从 JSON 规格生成 Wavefront `.obj`，或审计、合并已有网格，输出到 `process/models/` |

```text
/chelate-shell:figure data.csv —— 画电压随时间的散点图
/chelate-shell:model3d spec.json
```

两者都在沙箱内运行并带 120 秒熔断：输入异常时降级为 `UNVERIFIED`，不会把整条流水线卡住。

### 1.3.0 新增的子代理

`agents/` 下的两个角色随插件一起注册：

| 子代理 | 适用场景 | 可调用的技能 |
|---|---|---|
| `spatial_agent` | 3D 内容——图像转 3D、视频转 3D、场景合成、网格质检 | 3d-modeler、sci-visualizer、security-guard |
| `visual_agent` | 出版级视觉——二维图表、静态示意图、gif 逐帧、出图质检、LaTeX 导出 | sci-visualizer、latex-exporter、security-guard |

任务匹配时 Claude 会自动交给它们，也可以在请求里点名。每个子代理都受技能白名单、可写路径白名单（`assets/`、`process/`、`results/`）与步数预算约束，越不出自己的角色范围。

### 需要命令行时

同样的操作也可以无头运行，供 CI 与脚本调用；参数、`a` / `b` / `c` 三种流水线模式与调试开关见 [ORCHESTRATOR.md](ORCHESTRATOR.md) §5。

## 环境要求

只需要 Python 3.10+，别的都不用提前准备：微内核与多数技能仅依赖标准库。少数数据处理与网络类技能会额外用到常见的第三方包（numpy、pandas、sympy、rdkit、matplotlib、requests 等）；每个技能的 `manifest.json` 精确声明了自己需要什么，运行时由 `core/sandbox.py` 检查。缺包不会让流水线崩溃——只有那一个技能会带提示降级为 `UNVERIFIED` 门禁，其余照常运行。本仓库不内置任何第三方代码，每个库仍保持其自身的宽松许可。逐技能的完整依赖矩阵见 [docs/DEPENDENCIES_zh.md](docs/DEPENDENCIES_zh.md)。

## 仓库布局

`core/` 是微内核，`lib/chelate_core/` 存放每个适配器都引用的共享逻辑，
`skills/` 下每个技能一个目录（扁平——宿主扫描器不会下探到命名空间目录），
各宿主的插件清单或规则文件各占一个点目录。

逐目录说明，以及 20 个技能各自算什么：**[docs/REFERENCE_zh.md](docs/REFERENCE_zh.md)**。

## 测试

```bash
python -m pytest tests/ -q
```

357 个测试：装齐可选依赖时 347 通过、10 跳过；只有 pytest 的环境里跳过 36 个，
跑的是 `UNVERIFIED` 路径。另有 8 个技能自带上游套件，位于
`skills/<skill>/tests/`，每个目录单独一个进程运行。

两套环境、覆盖清单与逐技能条数：**[docs/TESTING_zh.md](docs/TESTING_zh.md)**。

## 安全与开源声明

> **免责声明**：本仓库包含作者为自动化科研工作流而开发的辅助工具，并非经过同行评审的学术项目。部分样板代码或实用脚本可能在 AI 辅助下生成，并经过作者高层面的审查与修改整合。作者对任何第三方代码问题不承担责任，但承诺及时处理任何合理的诉求。
>
> 本工具**永远不会代替你做实验**。数据必须由学生在实验室手动采集，AI 在实验环节物理隔离。生成的报告仅为“数据分析草稿”，最终学术责任由使用者本人及所在机构承担。

## 已知局限

诚实的边缘情况声明；依赖以下输出前请务必注意：

- **自动 ROI 检测会翻车**：`video-tracker` 在低对比度视频上可能失败，每次运行必须对照参考验证。标记为*实验/不稳定*。
- **公式检查不是数学证明**：`formula-validator` 是确定性判定。返回 `unknown` 代表某项检查“弃权”，这是合法状态，绝不能强行解释为通过。
- **纵向分析依赖 R 语言**：`longitudinal-analysis` 的某些高级统计步骤经由 R 脚本执行；若环境中缺失 `Rscript`，这些步骤会被跳过并记入日志，**绝不要试图用 Python 手写代码替代被跳过的 R 步骤**。
- **版本追踪是结构化而非语义化的**：`document-evolution-tracker` 按块对齐做 diff；某个概念只有在字面匹配时才被认为“存在”。
- **DOI 审计只验证存在性**：`reference-auditor` 确认 DOI 在 Crossref 中存在，不确认它就是你引用的那篇文献——引用正确性仍是作者的责任。
- **注入扫描是筛查而非沙箱**：`security-guard` 只能标记已知特征与危险调用点，无法证明一个文件绝对安全。
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
## 致谢

**NotFatJustRound** —— [issue #1](https://github.com/JiamingShi-JsPhys/chelate-shell/issues/1) 要求补上 CI，并发现了 npm `files` 列表漏掉了核心代码。

[完整致谢](docs/ACKNOWLEDGEMENTS_zh.md)

## 商标声明

“PASCO” 与 “Capstone” 是 PASCO Scientific 的注册商标。`capstone-labmate` 技能是独立的第三方互操作与教学辅助工具，与 PASCO Scientific 无隶属、赞助或背书关系。所有 `.cap` 解析均在本地运行；使用者有责任遵守所在机构的学术诚信政策。

## 开源许可与作者

本仓库整体采用 [MIT License](LICENSE) 发布，详见根目录下的 `LICENSE` 文件。每个技能目录也携带具有相同条款的独立 `LICENSE` 文件。

**作者与维护者**：Jiaming Shi（Westlake University）
