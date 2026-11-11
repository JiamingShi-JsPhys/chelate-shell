# 致谢

报告了问题、并因此改变了这个项目的人；README 列名字，这一页写细节。

**简体中文** · [English](ACKNOWLEDGEMENTS.md)

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
