# Chelate Shell

> **The missing orchestrator for your local agent skills.**
> 把散落的本地技能，螯合成一个确定性的科研与工程工作流。

[English](README.md) · **简体中文**

**版本：** 1.0.0 | **核心技能数：** 9 | **架构层级：** 4

---

## 为什么需要 Chelate Shell？

当前 AI 生态里，每个技能（Skill）都在解决单点问题：校验公式、追踪视频、整理文件。但当 Agent 面对复杂任务时，它常常不知道**该按什么顺序、在什么位置调用哪个技能**。

Chelate Shell 是一个**调度器（Orchestrator）**，它自身不写底层代码去解领域问题。它像一个资深项目经理，负责拆解意图、强制标准工作区结构，并**确定性地**把任务路由到对应的技能。

### 核心架构
我们的 9 个技能被严格划分为 4 个层级（各层级内按字母顺序排列），确保 AI 不会在工作区里乱扔文件：

```text
Chelate Shell (Router)
│
├── 基础基建层 (Base Infrastructure)
│   ├── multi-dim-manager   # 多维状态管理 (快照/回滚)
│   └── task-organizer      # 标准化工作区 (material/process/results)
│
├── 数据流转层 (Data Pipeline)
│   ├── capstone-labmate    # PASCO 数据解析与图表
│   ├── longitudinal-analysis # 纵向数据统计建模
│   └── video-tracker       # 视频追踪与 FFT 频谱
│
├── 认知与质检层 (Cognitive & QC)
│   ├── ai-trace-remover    # 去除 AI 痕迹，优化人类表达
│   ├── conflict-detector   # 跨文档矛盾检测 (数值/布尔)
│   └── formula-validator   # 确定性公式校验 (量纲/极限/符号)
│
└── 监控层 (Monitor)
    └── document-evolution-tracker # 追踪文档版本演化
```
上述skill都可以在我的仓库[agent-skills](https://github.com/JiamingShi-JsPhys/agent-skills)找到

### 路由规则
*   **简单任务旁路**：单次公式检查、一次性去 AI 味。直接调用质检层技能，不建目录。
*   **复杂任务强制**：任何涉及交付物的多步任务，**第一步必须先调用 `task-organizer`**，建立 `material/initial/`、`process/`、`results/` 三层结构。
*   **流转流向**：输入从 `material/initial/` 读，中间产物写 `process/`，最终结果写 `results/`。
*   **出厂质检**：`results/` 里的最终交付物，必须经过 `conflict-detector` 和 `ai-trace-remover` 双重把关。
*   *调度器的完整契约见 [ORCHESTRATOR.md](ORCHESTRATOR.md)。*

---

## 安装与下载 (Installation)

本仓库是一个跨平台的 Agent 技能套件，支持 **Claude Code、WorkBuddy、OpenAI Codex 以及 DeepSeek Harness (DSH)**。请选择最适合你的安装方式：

### 方式一：让 AI 帮你装（最推荐，Agent 原生方式）

直接复制以下 Prompt 发给你的 AI Agent，它会自动完成克隆、配置和挂载：

> "请访问 GitHub 仓库 `https://github.com/JiamingShi-JsPhys/chelate-shell`，克隆该仓库，并根据当前 Agent 平台的规范（如 Claude Code 或 OpenAI Codex），将 `skills/` 目录下的所有技能注册到你的系统中。"

### 方式二：下载 Release 压缩包（适合非开发者）

1. 前往 [Releases](https://github.com/JiamingShi-JsPhys/chelate-shell/releases) 页面，下载最新版本的 `.zip` 压缩包。
2. 解压后，将整个 `chelate-shell` 文件夹放入你对应 AI 平台的技能目录中：
   - **Claude Code**: `~/.claude/skills/`
   - **Codex**: `~/.codex/skills/`
   - **DSH**: `~/.dsh/skills/`
      - **WorkBuddy**: `~/.workbuddy/skills/`
3. 重启 AI 客户端，输入 `/skills` 确认加载成功。

### 方式三：使用 Git 命令行克隆（适合开发者）

```bash
# 1. 克隆仓库
git clone https://github.com/JiamingShi-JsPhys/chelate-shell.git

# 2. 将技能目录移动到你的平台目录 (以 Claude Code 为例)
cp -r chelate-shell/skills/* ~/.claude/skills/
```

> **环境依赖提示**：核心调度器及多数技能仅依赖 Python 标准库。少数涉及数据处理的技能（如 `formula-validator`、`video-tracker`）需要安装 `sympy`、`numpy`、`opencv-python` 等第三方库。缺失依赖时，系统会优雅降级并给出提示，不会直接崩溃。详见下方的依赖矩阵。

---

## 快速上手 (Quick Start)

所有命令均在 `chelate-shell` 插件根目录执行，**绝不硬编码绝对路径**。

**1. 初始化复杂任务工作区**
```bash
cd skills/task-organizer
python -m scripts.run init <root>
python -m scripts.run organize <root> # 自动归档，失败自动回滚
```

**2. 确定性校验物理公式（旁路模式）**
```bash
cd skills/formula-validator
python scripts/cli.py validate --expr "sqrt(k/m) = omega" \
    --units "k=kg/(s**2)" --units "m=kg"
```

**3. 去除草稿的 AI 痕迹**
```bash
cd skills/ai-trace-remover
python -m src.cli <file> --json
```

**4. 追踪文档版本的演化**
```bash
cd skills/document-evolution-tracker
python -m src.cli run --config config/examples/family.json --concepts "entropy,partition function"
```

---

## 技能依赖矩阵

| 技能 | 必需依赖 | 可选依赖（缺失则降级功能） |
| --- | --- | --- |
| `task-organizer` | 无 | `openpyxl`, `PyYAML` |
| `multi-dim-manager` | 无 | `PyYAML` |
| `capstone-labmate` | `numpy`, `matplotlib`, `pypdf` | 无 |
| `longitudinal-analysis` | `numpy`, `pandas`, `statsmodels`, `scipy` | `python-docx`, `R (lme4, lavaan)` |
| `video-tracker` | `numpy`, `opencv-contrib-python` | `matplotlib` |
| `ai-trace-remover` | 无 | 无 |
| `conflict-detector` | 无 | `PyYAML` |
| `formula-validator` | `sympy`, `numpy`, `scipy`, `mpmath` | 无 |
| `document-evolution-tracker` | 无 | `PyYAML` |

---

## 已知局限 (Limitations)

诚实的边缘情况声明；依赖以下输出前请务必注意：

- **自动 ROI 检测会翻车**：`video-tracker` 在低对比度视频上可能失败，每次运行必须对照参考验证。标记为*实验/不稳定*。
- **公式检查不是数学证明**：`formula-validator` 是确定性判定。返回 `unknown` 代表某项检查“弃权”，这是合法状态，绝不能强行解释为通过。
- **纵向分析依赖 R 语言**：`longitudinal-analysis` 的某些高级统计步骤经由 R 脚本执行；若环境中缺失 `Rscript`，这些步骤会被跳过并记入日志，**绝不要试图用 Python 手写代码替代被跳过的 R 步骤**。
- **版本追踪是结构化而非语义化的**：`document-evolution-tracker` 按块对齐做 diff；某个概念只有在字面匹配时才被认为“存在”。
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

---

## 安全与开源声明

> **免责声明**：本仓库包含作者为自动化科研工作流而开发的辅助工具，并非经过同行评审的学术项目。部分样板代码或实用脚本可能在 AI 辅助下生成，并经过作者高层面的审查与修改整合。作者对任何第三方代码问题不承担责任，但承诺及时处理任何合理的诉求。
> 
> 本工具**永远不会代替你做实验**。数据必须由学生在实验室手动采集，AI 在实验环节物理隔离。生成的报告仅为“数据分析草稿”，最终学术责任由使用者本人及所在机构承担。