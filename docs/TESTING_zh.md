[简体中文](../README_zh.md) · [English](TESTING.md)

# 测试

根测试套件、7 份逐技能套件，以及 CI 跑的两套环境。

## 测试

```bash
python -m pytest tests/ -q
```

共 394 个测试。装齐可选依赖时是 **383 通过、11 跳过**：一条需要未随仓库发布的 v1.0.0 源码树，一条断言 POSIX 文件权限（Windows 不强制，在 Linux 上会执行并通过），其余九条是引擎技能与还原版 legacy 树的 `no_stubs` 豁免；只有 pytest 的环境里则改为跳过依赖相关的用例——断言真实判定的测试都带 `requires()` 标记，所以套件照样全绿，而这条路径跑的正是新用户实际遇到的 `UNVERIFIED`。CI 两种环境各跑一遍，Python 3.10 与 3.12 都在。

每个技能还自带一份上游测试套件，放在 `skills/<skill>/tests/`——7 个有这样的目录，合计 915 条。它们不能放进同一个 pytest 进程（几个都定义了顶层 `tests` 模块，当初的 `ImportPathMismatchError` 就是这么来的），所以 CI 的第三个 job 是每个目录单独起一个进程。根测试套件覆盖：门禁契约、清单 schema 校验、扁平布局强制（manifest 必须正好位于 `skills/` 下一层）、流水线规划与 FAIL 终止、迁移守卫、legacy D1–D5 与 FFT/物理探针、v1.1.x 新增的 5 个技能、工作区输入路径解析、`--inputs` 自动接线、统一调试层、清单契约套件（四平台插件清单，以及 SKILL.md frontmatter 一致性）、无插件宿主的规则文件适配器、安全护盾、4 个重型引擎技能的真实逻辑与 `UNVERIFIED` 降级，以及仓库一致性守卫：每个技能的文档、清单、入口、`LICENSE` 与声明依赖始终保持一致。
