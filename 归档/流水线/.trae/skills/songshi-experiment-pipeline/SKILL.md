---
name: songshi-experiment-pipeline
description: 把一个宋史史料库实验从资源检查跑到 30 篇论文与 CCI/ECI 对齐汇总，含提示词、生成与统计脚本模板、易错点清单。用于新建或推进 A/B 组实验。
---

# 宋史实验流水线

每个实验固定设计：**2 条件（Q 中性提问 / A 给定观点）× 3 档史料池（S/M/L）× 5 轮 = 30 篇模型论文**，
再与一篇人类基准论文的论证树做 10 轮 LLM 对齐，输出 **CCI / ECI** 与 A-7 合并结果。

> **术语与 JSON 字段名的对应关系（2026-10-25 订正）**
> 计分定义 v2.0 起，正式报告口径为 **CCI（观点收敛度）/ ECI（证据结构收敛度）**，
> 旧名 ACI / SCI 作废。但 `measurement.py` 输出的 **JSON 字段名仍沿用旧名**，
> 语义一一对应，读数据时按此映射取：
>
> | 正式名 | 定义 | JSON 字段名 |
> |---|---|---|
> | CCI | 被模型覆盖的人类命题数 / 人类命题总数 | `ACI`（binary coverage） |
> | ECI | 模型保留的人类结构边数 / 结构边总数 | `SCI`（combined edges） |
>
> 文档一律写 CCI / ECI；只有直接取 JSON 时才用旧字段名。

统一口径（`提取与生成管线/实验设置.json`）：`rounds=10`、`main_k=6`、`robust_k=4`、
`cross_level=true`、`exclude_A=true`、`source_id_policy=exact_shared_roster`。
**任何实验都不得改动这些值**，否则与已有实验不可比。

## 分段与节点粒度（硬规格，2026-10-25 修订）

1. **段落 = 论文的自然段**（PDF/Word 里以空行分隔的段），不合并、不切碎。
   - 切分源：优先按 PDF 重切（见 `references/执行手册.md` P0.5），次之 full.md 空行切分。
   - 作者/单位/摘要/关键词/引言**不进** `原文_clean.json` 的 `paragraphs`（引言文本可存 meta 留档）。
2. **每个正文自然段恰好 1 个 C 节点**：不跳过、不合并、不跨段。
   纯史料引文段照发节点，标记 `quote_only=true`（下游需要时可用 `--drop-quote-only` 剔除）。
3. **验收不通过不得进入 P1**：

```bash
python3 - <<'PY'
import json, re
from pathlib import Path
c = json.loads(Path('<ID>/00_原文/原文_clean.json').read_text(encoding='utf-8'))
md = Path('<ID>/原始输入/full.md').read_text(encoding='utf-8').split('\n\n')
natural = sum(1 for b in md if b.strip() and not b.strip().startswith('#'))
proc = sum(1 for p in c['paragraphs'] if p['type'] == 'text')
print('自然段', natural, '处理段', proc, '最长块', max(len(p['text']) for p in c['paragraphs']))
assert abs(proc - natural) / max(natural, 1) < 0.2, '分段粒度不达标：处理段与自然段落差过大'
assert len(max(c['paragraphs'], key=lambda p: len(p['text']))['text']) < 2500, '存在超长合并块'
PY
```

> 历史教训：A01–A10 的人工 CSV 标注把 27–60 个自然段合并成 6–33 个处理块，
> 直接压低了 C 节点数（A02 27 段→5 节点、A06 →5、A09 →8），使"人类树大小"失去跨实验可比性，
> 并制造了假的"反转放大效应"。分段粒度错了，后面全链路跟着错且不会报错。

## 先做哪一步

按 `references/执行手册.md` 的 P0→P6 顺序执行，不要跳步。每一步都有验收条件，不通过不要进入下一步。

| 阶段 | 命令 | 通过条件 |
|---|---|---|
| P0 资源检查 | 见手册 | 史料池 passage 数、人类树 A/B/C 节点数、M 名册数三项对齐；**外加分段粒度验收（见下）** |
| P1 转写 | `scripts/新增实验.py` | `<ID>_实验记录/` 生成 6 个脚本，NODES 字典含全部历史实验 |
| P2 史料池 | `scripts/建档三档.py` | 同一批引文 × 不同上下文长度（S=引用片段 / M=200字 / L=400字，源=史料总库.xlsx，覆盖率≥0.7），三档条数相同、MD5 互不相同 |
| P3 生成 | `生成<ID>.py` | 30/30 `finish_reason=stop`，汉字 ≥ 3000 |
| P4 小样 | `QS_R1` 单链路 | CCI 量级合理，嵌套/异常结构被正确识别 |
| P5 全量 | `批量<ID>.py` | 30/30 有 `频次聚合.json` |
| P6 汇总 | `A7合并<ID>.py` + `build_report<ID>.py` | 汇总 JSON 30 run，报告 HTTP 200 |

## 不要凭记忆改脚本

新建实验用脚手架，不要 `sed 's/A10/B01/g'`：

```bash
python3 .trae/skills/songshi-experiment-pipeline/scripts/新增实验.py \
  --id B01 --topic "主题" --human-src "B组交付包/B01/第二轮复现"
```

脚手架会复制 A10 的 6 个脚本、替换实验 ID，并**重写 `NODES` 字典与两处 `for p in [...]` 列表**
为磁盘上全部实验 + 新实验。sed 会把旧实验 ID 一起换掉，导致报告静默丢实验（A07 丢 A06、A08 丢 A07）。

## 三条硬约束

1. **不改模型论文**。只允许做引用标记规范化（空格变体），不得改文字内容。
2. **共享名册必须覆盖人类树全部引用**，且 `A1.sources` 强制等于完整名册（`exact_shared_roster`）。
3. **A-7 是后处理**，不重跑对齐，只重算票；报告里必须同时给原始与 A-7 两套数。

## 依赖的项目路径

本 skill 只含流程与模板逻辑，实际执行依赖项目根下这些目录（只在同一套项目里有效）：

| 路径 | 作用 |
|---|---|
| `提取与生成管线/` | 抽取、绑定、校验、对齐、聚合、`measurement.py`、`实验设置.json`、`deepseek_env.sh` |
| `A10_实验记录/` | 六个脚本的模板来源（默认模板实验） |
| `数据集/史料池（主要）/` | `<ID>_史料池.json` |
| `X组交付包_*/<ID>/第二轮复现/` | `run_论证树.json` 与 `00_原文/` |
| `实验数据/<ID>/03_实验输出/Q_A_实验/` | 管线输出根，含 `A_human_baseline` |

把 skill 转给同伴时，**要连同 `提取与生成管线/` 与一个已完成实验的 `_实验记录/` 目录一起给**，
否则脚手架找不到模板，管线命令也跑不起来。

## 排查顺序

结果异常时按这个顺序查，不要先怀疑模型：

1. 引用标记是否有空格变体 → `坑位表.md` 第 1 条
2. 共享名册长度是否对 → 人类引用数 vs 史料池 passage 数
3. 人类树 B/C 层 `sources` 是否为后代并集
4. 是否有 run 缺 `run_论证树.json` 或对齐不足 10 轮

详细坑位与历史修复见 `references/坑位表.md`；提示词与条件文本见 `references/提示词与条件.md`；
十实验数据基线见 `references/十实验基线.md`。
