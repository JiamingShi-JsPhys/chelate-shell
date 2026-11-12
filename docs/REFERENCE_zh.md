[简体中文](../README_zh.md) · [English](REFERENCE.md)

# 参考

仓库里的每一个目录，以及 20 个技能各自做什么。README 首页只留简版：`core/`
是微内核，`lib/chelate_core/` 是共享逻辑，`skills/` 下每个技能一个目录。

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
├── agents/                           # 子 Agent 角色定义
│   ├── spatial_agent.md              # 网格/3D 角色（3d-modeler）
│   └── visual_agent.md               # 图表/可视化角色（sci-visualizer + latex-exporter）
├── AGENTS.md                         # 通用 Agent 规范（Codex / Cursor / Copilot / opencode）
├── assets/                           # icon.png（各插件清单共用）
├── bootstrap.py                      # 各 run.py 共用的导入与门禁写入工具
├── CHANGELOG.md                      # 版本发布说明
├── cli.py                            # 命令行入口：list / run / pipeline
├── commands/                         # 斜杠命令
│   ├── figure.md                     # /figure —— 从 CSV 或 JSON 数据集出图
│   └── model3d.md                    # /model3d —— OBJ 网格生成 / 合并 / 审计
├── contracts/                        # 全局通信契约
│   ├── __init__.py
│   ├── gate_result.py                # {skill, status, evidence_level, reason, artifacts}
│   └── schema.json                   # manifest.json 的强校验规范
├── cordis.patch.yml                  # cordis bundle 补丁
├── core/                             # 微内核
│   ├── __init__.py
│   ├── registry.py                   # 扫描 skills/ 并注册进路由表
│   ├── router.py                     # 确定性调度器（解析 manifest 生成流水线）
│   ├── sandbox.py                    # 依赖隔离与 120 秒超时熔断
│   ├── security_shield.py            # 提示注入文本扫描 + AST 危险调用扫描
│   └── subagent_manager.py           # 子 Agent 角色注册表
├── docs/                             # 本页、架构、测试、安装命令、依赖矩阵
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
├── ORCHESTRATOR.md                   # 给 Agent 看的路由契约（v1.3.0）
├── package.json                      # npm/dsh 打包元数据
├── README.md
├── README_zh.md
├── skills/                           # 20 个技能，全部平铺——一个技能一个目录
│   ├── 3d-modeler/                   # [domain_extensions] 纯 Python OBJ 网格
│   │                                 # 生成 / 合并 / 审计，含网格质检；沙箱运行
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
│   ├── sci-visualizer/               # [generation] 出版级统计图（matplotlib +
│   │                                 # seaborn + pandas），含 AMOS 风格 SEM 路径图
│   │                                 # 渲染器，另可扫描 gif 逐帧
│   ├── security-guard/               # [infrastructure] 提示注入文本扫描 +
│   │                                 # AST 危险调用点扫描
│   ├── task-organizer/               # [workspace] 四区工作区初始化、文件整理
│   │                                 # （C1–C8 校验、去重、快照、撤销/重做）、
│   │                                 # _broadcast/INDEX.md 上下文索引
│   └── video-tracker/                # [ingest]    OpenCV 坐标提取（CSRT/Template）、
│                                     # FFT 频谱分析、物理一致性探针
├── tests/                            # 根套件（357 条）；每个技能另带 skills/<skill>/tests/
└── THIRD_PARTY_LICENSES.txt          # 第三方许可清单
```

---
