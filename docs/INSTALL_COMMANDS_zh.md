# 安装命令

各宿主的安装命令、`install.py` 的参数以及可选依赖。方法一与方法三足够短，留在 README 里：[chelate-shell](../README_zh.md) · [English](INSTALL_COMMANDS.md)

## 方法二：用命令安装

**Claude Code** —— 在终端执行（v2.1.292+），一步完成注册与安装：

```bash
claude plugin install chelate-shell --marketplace https://github.com/JiamingShi-JsPhys/chelate-shell.git
```

**Claude Code** —— 在会话内执行（v2.1.275+），先用 URL 添加市场，并锁定发布 tag：

```text
/plugin marketplace add https://github.com/JiamingShi-JsPhys/chelate-shell.git#v1.3.2
```

再安装它列出的条目：

```text
/plugin install chelate-shell@chelate-shell-marketplace
```

**Codex** —— 把 URL 注册为 Git 市场；`--ref` 锁定发布 tag，HTTPS 换成 SSH 或本地路径同样可用：

```bash
codex plugin marketplace add https://github.com/JiamingShi-JsPhys/chelate-shell.git --ref v1.3.2
```

**Codex** —— 从该市场安装插件：

```bash
codex plugin add chelate-shell@chelate-shell-marketplace
```

**dsh（DeepSeek Harness）** —— 直接从同一个仓库 URL 安装进指定 profile：

```bash
dsh plugin --profile web add github:JiamingShi-JsPhys/chelate-shell#v1.3.2
```

**CodeBuddy** —— 先把 URL 加为 Git 市场：

```text
/plugin marketplace add https://github.com/JiamingShi-JsPhys/chelate-shell.git#v1.3.2
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
{
  "$schema": "https://opencode.ai/config.json",
  "instructions": ["../chelate-shell/AGENTS.md"]
}
```

**不想跑脚本时的手动方式** —— 自己复制，目标路径就是脚本会写入的那一处：

```text
<克隆目录>/AGENTS.md  →  <项目>/AGENTS.md
```
