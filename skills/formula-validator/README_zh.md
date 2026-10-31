[English](README.md) · [中文说明](README_zh.md)

# formula-validator（公式验证器）

SymPy D1-D5 五层确定性检查（量纲分析、极限枚举、数值采样、符号证明），
合并 pint 物理单位交叉核对。

## 使用

```bash
python -m scripts.cli <validate|check|derive|matrix> --expr "F = m*a" --units F=N
```

路由适配器（薄封装 — 底层同一套代码）：

```bash
python run.py --root <workspace> --action validate -- --expr "F = m*a" --units F=N --units m=kg --units a=m/s**2
```

## 断点与已知局限

- 定义式（`derive`）层依赖符号代数，无法处理的表达式会降级为
  UNVERIFIED（未知），而不是猜测。
- 数值采样层使用蒙特卡洛随机路径，结果随种子变化；固定种子可复现。
- 已知局限：深度嵌套表达式的符号层可能超时；数值层是实际兜底。

## 许可

MIT — 见 [LICENSE](LICENSE)。
