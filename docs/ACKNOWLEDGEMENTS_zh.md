# 致谢

报告了问题、并因此改变了这个项目的人；README 列名字，这一页写细节。

**简体中文** · [English](ACKNOWLEDGEMENTS.md)

## 我的一些朋友

利用这个插件进行了数学、理论物理与实验物理方面的相关测试，并以许多真实场景帮助我将插件从 1.3.3 完善至 1.3.4。

真实的问题与纸面上的用例不是一回事：把插件放进自己正在做的那道题里用，才会遇到测试套件里永远不会出现的输入——某一类公式写法让判定弃权、某个量级下模型和预期对不上、某份数据让门禁给出一个站不住的结论。1.3.3 到 1.3.4 之间的不少改动，是从这些场景里长出来的。

## NotFatJustRound

[issue #1](https://github.com/JiamingShi-JsPhys/chelate-shell/issues/1)。

测试套件只在开发者本人的机器上是绿的。仓库根目录没有 `pytest.ini`，所以从全新
克隆跑 `pytest` 时，`skills/*/tests/` 会连同 `tests/` 一起被收集，而这些目录里的
同名模块覆盖了根目录的 `conftest.py`，整轮在收集阶段就以
`ImportPathMismatchError` 终止——一个测试都没跑。1.3.1 里把收集范围限定到
`tests/` 的 `pytest.ini`，以及每次 push 都跑一遍的 workflow，都来自这条报告。

同一个 issue 还发现 `package.json` 的 `files` 只带了 `skills/`，漏掉 `core/`、
`lib/`、`cli.py`、`bootstrap.py` 与 `contracts/`：用 npm 装下来会得到全部技能，
以及它们 import 不到的底层代码。

## DeepSec

本仓库用来做代码安全审计的工具（`deepsec shield scan`）。它的 L1 规则集与
SAST 规则找出了 1.3.2 修掉的两条命令注入路径——`multi-dim-manager` 用
`shell=True` 跑插件模板，以及 `core/sandbox.py` 会执行 manifest 指定的任意
程序。1.3.2 与 1.3.3 两条 CHANGELOG 里的"0 处发现"也出自它。
它对这个结果没有任何立场：中间有好几轮修复是被它打回来的，直到某一轮才干净。
