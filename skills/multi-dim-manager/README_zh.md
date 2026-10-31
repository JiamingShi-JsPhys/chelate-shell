[English](README.md) · [中文说明](README_zh.md)

# multi-dim-manager（多维参数管理器）

笛卡尔参数空间展开、每轮 SHA-256 文件快照、哈希审计日志，以及对任意历史轮次的安全回滚。

## 使用

```bash
python -m scripts.run <run|dryrun|rollback|summary|verify> --config <yaml>
```

路由适配器（薄封装 — 底层同一套代码）：

```bash
python run.py --root <workspace> --action dryrun -- --config config.example.yaml
```

## 非破坏性保证

- 快照与回滚均为非破坏性操作：轮次状态可审计，关键路径上的文件变更可
  逐轮追溯；任意轮次可回滚，原始字节通过快照保留。
- 回滚只恢复工作区内的文件与轮次状态，不影响工作区外的副作用。

## 许可

MIT — 见 [LICENSE](LICENSE)。
