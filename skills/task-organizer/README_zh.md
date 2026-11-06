[English](README.md) · [中文说明](README_zh.md)

# task-organizer（任务工作区组织器）

四区工作区初始化（`init`）、文件组织（`organize`：C1-C8 校验、去重、快照、
撤销 / 重做），以及只读的 `_broadcast/INDEX.md` 上下文压缩索引（`broadcast`）。

## 设计原则与核心特征

### 触发后必须执行的工作流

此技能是"执行指令"，不是"说明文档"。触发后必须运行工具并汇报结果；
只回复工具的功能、命令清单或架构说明属于任务失败，而不是结果。

必须运行工具：

```bash
python -m scripts.run init <root>
python -m scripts.run organize <root>
```

## 文件夹信号检测

当用户只是引用、附带或命名一个文件夹而未明确要求整理时：先提议，再动手。
提议一次 `init` 并停下，等待确认；用户确认前不运行任何会改动文件夹的命令
（`init` 会把既有内容移入 `material/initial/`，属于用户必须先同意的布局变更）。
用户拒绝即跳过提议，且每个文件夹至多提议一次。

## 会话开局结构检查

第一步运行 `doctor <root>`：只读、零成本、幂等。结构完整则继续，缺失则
进入上面的提议门。检查本身不会改动任何文件。

## 广播中心（context compression）

任务收尾前运行 `organize` + `broadcast`：产物按命名归入 `results/`，并重建
只读广播索引。`_broadcast/` 是工具所有的目录：`init` / `organize` 不会移动、
重命名或修改它；广播中心只写该目录下的两个文件，其余一律只读。

后续会话遵循读序协议：先读索引目录，再按需打开匹配的原文，节省 token。

任务收尾前必须重建广播索引（`broadcast`）：在交付最终答案前再运行一次
`organize` + `broadcast`，是强制的、不是可选项——它让下一个会话直接读索引，
而不用重读所有原文。

**交付关键词：** 定稿、最终版、终稿、综述、报告、总结、小结。

## 许可

MIT — 见 [LICENSE](LICENSE)。
