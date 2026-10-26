# -*- coding: utf-8 -*-
"""人类基线论证树验收（自然段级）。

校验项：
  1. 每个正文自然段恰好 1 个 C 节点（硬规格）；
  2. C 节点与段落 1:1 对应，无遗漏、无重复；
  3. A 恰好 1 个；
  4. 最长正文块 < 2500 字（P0.5 分段粒度验收）；
  5. 冻结配置一致（模型 / 温度 / 数据源文件名）。
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(r'C:/Users/23297/Downloads/FDUROP')
BASE = ROOT / r'归档/数据集/数据清洗后论文'
RUN = 'A_human_自然段基线'
PIDS = ['A01', 'A02', 'A03', 'A04', 'A05', 'A06', 'A07', 'A08', 'A09', 'A10']
FROZEN_MODEL = 'DeepSeek-V4-Pro-0813'
FROZEN_CLEAN = '原文_clean_自然段.json'
MAX_BLOCK = 2500


def main():
    rows, problems = [], []
    for pid in PIDS:
        tp = BASE / pid / '03_实验输出' / 'Q_A_实验' / RUN / 'run_论证树.json'
        cp = BASE / pid / '00_原文' / FROZEN_CLEAN
        if not tp.exists():
            problems.append(f'{pid}: 缺论证树 {tp.name}')
            continue
        tree = json.loads(tp.read_text(encoding='utf-8'))
        clean = json.loads(cp.read_text(encoding='utf-8'))
        enc, st = tree['encoding_table'], tree['statistics']
        meta = tree['meta']

        nA, nB, nC = (st['total_A_nodes'], st['total_B_nodes'], st['total_C_nodes'])
        text_paras = [p for p in clean['paragraphs'] if p.get('type') == 'text']
        n_text = len(text_paras)
        lens = [len(p['text']) for p in text_paras]
        maxblk = max(lens) if lens else 0

        # C 与段落 1:1（C 节点用 anchor 标记所属自然段）
        anchors = [c.get('anchor') for c in enc['C_level']]
        real = [a for a in anchors if a]
        missing = sorted({p['id'] for p in text_paras} - set(real))
        dup = len(real) - len(set(real))
        orphan = sorted(set(real) - {p['id'] for p in text_paras})
        if orphan:
            problems.append(f'{pid}: C 锚定到不存在的段落 {orphan}')

        refs = {m for p in clean['paragraphs'] for m in p.get('material_refs', [])}
        nM = st['total_unique_M']
        wo = st['C_nodes_without_sources']
        # 父节点仅有一个直属 C 时，该 C 与父合并计数（旧 A01「21 式」口径）
        kids = Counter(c.get('parent') for c in enc['C_level'] if c.get('parent'))
        solo = sum(1 for c in enc['C_level']
                   if c.get('parent') and kids[c['parent']] == 1)

        if len(meta.get('model', '')) and meta['model'] != FROZEN_MODEL:
            problems.append(f'{pid}: 模型不一致 {meta["model"]}')
        if meta.get('clean_source') != FROZEN_CLEAN:
            problems.append(f'{pid}: 数据源不一致 {meta.get("clean_source")}')
        if meta.get('temperature') != 0:
            problems.append(f'{pid}: 温度非 0')
        if nA != 1:
            problems.append(f'{pid}: A 节点数={nA}')
        if nC != n_text:
            problems.append(f'{pid}: C={nC} ≠ 正文段={n_text}')
        if missing:
            problems.append(f'{pid}: 段落未产 C {missing}')
        if dup:
            problems.append(f'{pid}: 重复 C 归属 {dup} 处')
        if maxblk >= MAX_BLOCK:
            problems.append(f'{pid}: 最长块 {maxblk} 超 {MAX_BLOCK}')

        rows.append({
            'pid': pid, 'A': nA, 'B': nB, 'C': nC, '正文段': n_text,
            'CCI分母': nB + nC - solo, '合并': solo, '无史料C': wo,
            'M使用': f"{len(refs)}/{nM}", 'M率': len(refs) / max(nM, 1),
            '最长块': maxblk, '1对1': 'OK' if not missing and not dup else 'NG',
        })

    print(f'{"篇":<5}{"A":>3}{"B":>4}{"C":>4}{"正文段":>6}{"1对1":>6}'
          f'{"CCI分母":>8}{"合并":>5}{"无史料C":>7}{"M使用":>10}{"M率":>7}{"最长块":>7}')
    print('-' * 78)
    for r in rows:
        print(f'{r["pid"]:<5}{r["A"]:>3}{r["B"]:>4}{r["C"]:>4}{r["正文段"]:>6}{r["1对1"]:>6}'
              f'{r["CCI分母"]:>8}{r["合并"]:>5}{r["无史料C"]:>7}{r["M使用"]:>10}'
              f'{r["M率"]:>6.0%}{r["最长块"]:>7}')
    tot = sum(r['C'] for r in rows)
    print('-' * 78)
    print(f'合计 C 节点 {tot}；CCI 分母（B+C−合并）{sum(r["CCI分母"] for r in rows)}'
          f'；其中无史料 C {sum(r["无史料C"] for r in rows)}（ECI 不产生边，CCI 仍计入）')
    if problems:
        print('\n[问题]')
        for x in problems:
            print(' -', x)
    else:
        print(f'\n全部通过：{len(rows)} 篇均为「每正文自然段 1 个 C」，冻结配置一致。')


if __name__ == '__main__':
    main()
