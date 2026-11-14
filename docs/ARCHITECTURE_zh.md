[简体中文](../README_zh.md) · [English](ARCHITECTURE.md)

# 架构

`core/router.py` 如何把一个请求变成一次有计划、有门禁的运行。README 里只留两句话，
这一页是 agent 照着实现的完整契约。

## 架构与流水线

`core/router.py` 是微内核：它读取 19 个 `manifest.json`，按规范阶段顺序生成计划，在派发任何技能**之前**先对文本输入做提示注入扫描，然后逐个调用技能的适配器。每次调用都会在 `process/gates/` 写下一个 `GateResult`——`PASS`、`UNVERIFIED` 或 `FAIL`。

缺依赖时只把该技能降级为 `UNVERIFIED`，流水线继续。单个 `FAIL` 是终止态：流水线当场停止，中间产物锁在 `process/` 里。没有任何门禁失败**且人类已针对这次计划签发审批**时，`process/` 才会被提升到 `results/`；无论是否提升，都会写出类型化的流水线报告和 `_broadcast/` 索引——后续会话先读索引，再决定打开哪些原件。

```mermaid
flowchart LR
    IN["用户意图 + 输入文件"] --> CLI["cli.py pipeline<br/>--mode a / b / c"]
    CLI --> REG["core/registry.py<br/>扫描 19 个 manifest"]
    REG --> PLAN{"build_plan<br/>规范顺序<br/>--inputs 按类型收窄"}
    PLAN --> SCAN["core/security_shield.py<br/>派发前注入扫描"]
    SCAN -->|"命中标记"| BAD["FAIL：injection-scan<br/>派发前拦截"]

    subgraph ROUTER["core/router.py — 四阶段流水线"]
        direction TB
        WS["workspace · 3 个技能<br/>task-organizer、multi-dim-manager、<br/>document-evolution-tracker"]
        ING["ingest · 4 个技能<br/>video-tracker、fulltext-extractor、<br/>literature-retriever、bibtex-normalizer"]
        GAT["gates · 7 个技能<br/>formula-validator、conflict-detector、<br/>reference-auditor、data-profiler、<br/>quantitative-validator、ml-auditor、<br/>longitudinal-analysis"]
        PRO["processors · 2 个技能<br/>ai-trace-remover、latex-exporter"]
        WS --> ING --> GAT --> PRO
    end

    SCAN -->|"干净"| ING
    WS -.->|"任务起始书挡"| ING

    subgraph CALL["单次技能调用 — run_skill()"]
        direction TB
        AD["适配器 run.py<br/>--root --action"]
        SB["core/sandbox.py<br/>声明 sandbox_required 时 120 秒熔断"]
        AD -->|"需沙箱"| SB
    end
    GATE["process/gates/ — 每次运行一个 GateResult<br/>PASS / UNVERIFIED / FAIL"]

    ROUTER -->|"计划内每个技能"| AD
    AD --> GATE
    SB --> GATE
    AD -.->|"依赖缺失"| UNV["UNVERIFIED<br/>该技能降级；<br/>流水线继续"]
    UNV -.-> GATE

    GATE -->|"任一 FAIL"| STOP["PIPELINE TERMINATED<br/>process/ 锁定"]
    GATE -->|"无 FAIL"| APPROVE{"cli.py approve<br/>绑定本次计划的 token"}
    APPROVE -->|"有 token"| PROMOTE["results/promoted_TIMESTAMP/"]
    APPROVE -->|"无 token"| BLOCKED["blocked: approval<br/>results/ 不写任何东西"]
    GATE --> REPORT["results/pipeline_report_TIMESTAMP.json"]
    PROMOTE -.-> LOG["results/.promotions.jsonl<br/>带签名；cli.py audit 读它"]
    BLOCKED --> REPORT
    REPORT --> BC["_broadcast/pipeline_index_TIMESTAMP.json"]

    LAYER["分类元技能<br/>security-guard、sci-visualizer、3d-modeler"] -.->|"由 registry 路由，不占规范顺序"| ROUTER
```

图里刻意说明的四件事：

- **自动流水线是 `ingest → gates → processors`。** `workspace`（task-organizer）是任务开始时的书挡，在流水线之前或通过 `--selected` 进入；`--mode a` 不会自动调度它。
- **`UNVERIFIED` 不是失败。** 它表示该技能无法给出判定——缺可选依赖、调用方还没提供输入——其余流程照常继续。
- **只有 `FAIL` 是终止态。** 它把 `process/` 原样锁在中断处，中间产物可审计，但不会被误当成结果。
- **提升是唯一不可逆的一步，所以由人授权。** `promote()` 需要一条针对本次计划的 token（action、工作区、模式/选择、每个输入文件的哈希、15 分钟有效期、HMAC 签名），并记入 `results/.promotions.jsonl`。这道锁跨运行有效：只要某个技能最新的一份门禁是 `FAIL`，即使当前计划没有调度它，提升也会被拒绝。`python cli.py audit` 把 `results/` 里没有对应提升记录的文件点名，并以退出码 1 结束。

---
