# 逐技能依赖（1.2.0）

由每个技能的 `manifest.json` 声明，运行时由
`core/sandbox.py` 检查。缺失必需依赖时，只有那一个技能降级为
`UNVERIFIED` 门禁，永远不会拖垮流水线。

| 技能 | 必需依赖 | 可选依赖（缺失则对应功能降级，不会崩溃） |
| --- | --- | --- |
| `ai-trace-remover` | 无（纯标准库） | 无 |
| `bibtex-normalizer` | `bibtexparser` | 无 |
| `capstone-labmate` | 无（纯标准库） | `numpy`（向量化加速）, `matplotlib`（绘图）, `pypdf`（PDF 文本） |
| `conflict-detector` | 无（纯标准库） | `PyYAML`（读取 `.yaml` 配置；JSON 配置零依赖） |
| `data-profiler` | `pandas` | 无 |
| `document-evolution-tracker` | 无（纯标准库） | `PyYAML`（读取 `.yaml` 配置；JSON 配置零依赖） |
| `figure-generator` | `matplotlib`, `seaborn`, `pandas` | 无 |
| `formula-validator` | `sympy`, `numpy`, `pint` | 无 |
| `fulltext-extractor` | `pdfminer.six` / `pypdf` | 无 |
| `latex-exporter` | 无（纯标准库） | 无 |
| `literature-retriever` | `arxiv` | 无 |
| `longitudinal-analysis` | `pandas` | `numpy`, `R (lme4, lavaan)`, `python-docx`（docx 导出）, `PyYAML`（`.yaml` 配置） |
| `ml-auditor` | `scikit-learn`, `pandas` | `cleanlab`（标签问题的第二意见） |
| `multi-dim-manager` | 无（纯标准库） | `PyYAML`（读取 `.yaml` 配置；JSON 配置零依赖） |
| `quantitative-validator` | `rdkit` | 无 |
| `reference-auditor` | `requests` | 无 |
| `task-organizer` | 无（纯标准库） | `openpyxl`（xlsx 快速通道）, `PyPDF2`（PDF 后端之一） |
| `video-tracker` | `numpy`, `opencv-python` | `matplotlib`（FFT 频谱图）, `PyYAML`（`.yaml` 配置） |

所有第三方库均为运行时导入，**本仓库不内置（vendored）任何第三方代码**；每个库仍保持其自身许可（numpy/pandas 为 BSD，OpenCV 为 Apache-2.0，SymPy/pint/requests/bibtexparser/arxiv 为
BSD/MIT/Apache，pdfminer.six 为 MIT，pypdf 为 BSD-3-Clause）。
