[English](README.md) · [中文说明](README_zh.md)

# video-tracker（视频追踪器）

基于 OpenCV 的坐标提取（CSRT / 模板匹配追踪器）、FFT 频谱分析与物理一致性探针
（瞬移 / 平滑度、守恒律、运动方程）。所有输出文件均为非破坏性生成：
原始视频始终只读，追踪结果写入 output/，不改动输入。

## 使用

```bash
python -m scripts.run <probe|track|fft|physics|report|demo> --config <json>
```

路由适配器（薄封装 — 底层同一套代码）：

```bash
python run.py --root <workspace> --action demo -- --output <dir>
```

## 已知局限

- 追踪器提取的是像素坐标，不直接测量物理量：质量、比例尺与帧率的换算由
  配置声明并校验（量纲一致性检查在 physics 探针中执行），而不是猜测。
- 目标被遮挡时可能丢失；重捕获基于模板匹配，可能锁定到相似物体。
- FFT 频谱假设信号平稳且带宽有限；噪声或加速运动会使峰位模糊、带宽估计失真。

## 许可

MIT — 见 [LICENSE](LICENSE)。
