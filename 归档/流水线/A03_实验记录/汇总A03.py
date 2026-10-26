#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总 A03 全部 run 的 ACI/SCI（n=6 主阈值 + n=4 鲁棒阈值 + A-7 topN 合并）。

新版：频次聚合 JSON 结构是 main.overall.ACI / robustness.overall.ACI / a7_merge.topN.nK.ACI，
与 A04–A10 口径一致。
"""
import json, re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / '实验数据' / 'A03' / '03_实验输出' / 'Q_A_实验'
OUT = ROOT / 'A03_实验记录' / '对齐汇总_A03.json'
HUMAN = ROOT / '实验数据' / 'A03' / '03_实验输出' / 'Q_A_实验' / 'A_human_baseline' / 'run_论证树.json'


def load_freq(run_dir):
    fp = run_dir / '频次聚合.json'
    if not fp.exists():
        return None
    d = json.loads(fp.read_text(encoding='utf-8'))
    main_t = d.get('main_threshold', 6)
    rob_t = d.get('robustness_threshold', 4)
    out = {
        'ACI_n6': d.get('main', {}).get('overall', {}).get('ACI'),
        'SCI_n6': d.get('main', {}).get('SCI'),
        'ACI_n4': d.get('robustness', {}).get('overall', {}).get('ACI'),
        'SCI_n4': d.get('robustness', {}).get('SCI'),
        'main_threshold': main_t, 'robustness_threshold': rob_t,
    }
    a7 = d.get('a7_merge', {})
    for N in (2, 3, 4):
        a7_n = a7.get(f'top{N}', {})
        if a7_n:
            out[f'ACI_a7_top{N}_n6'] = a7_n.get('n6', {}).get('ACI')
            out[f'ACI_a7_top{N}_n4'] = a7_n.get('n4', {}).get('ACI')
            out[f'SCI_a7_top{N}_n6'] = a7_n.get('n6', {}).get('SCI')
    out['threshold_scan'] = d.get('threshold_scan', {})
    return out


def main():
    runs = sorted(d.name for d in LAB.iterdir()
                  if d.is_dir() and re.match(r'^[QA][SML]_R\d$', d.name))

    human_tree = {}
    if HUMAN.exists():
        t = json.loads(HUMAN.read_text(encoding='utf-8'))['encoding_table']
        human_tree = {
            'A': len(t.get('A_level', [])),
            'B': len(t.get('B_level', [])),
            'C': len(t.get('C_level', [])),
            'B_nodes': [{'id': b['id'], 'parent': b.get('parent'),
                         'sources': len(b.get('sources', []))}
                        for b in t.get('B_level', [])],
            'total_M': len(t.get('M_level', [])),
        }

    # 三档规模（同一批引文，不同上下文长度；取档位说明的 char_counts）
    tiers = {}
    tj = ROOT / 'A03_实验记录' / '档位说明_A03.json'
    if tj.exists():
        d = json.loads(tj.read_text(encoding='utf-8'))
        tiers = d.get('char_counts', {})

    by_run = {}
    cond_data = defaultdict(lambda: {'ACI_n6': [], 'SCI_n6': [], 'ACI_n4': [],
                                      'ACI_a7_top2_n6': []})
    complete, incomplete = [], []

    for run in runs:
        rd = LAB / run
        freq = load_freq(rd)
        if freq is None or freq.get('ACI_n6') is None:
            incomplete.append(run); continue
        by_run[run] = freq
        cond = run[:2]       # QS / QM / QL / AS / AM / AL
        for k in cond_data[cond]:
            v = freq.get(k)
            if v is not None:
                cond_data[cond][k].append(v)
        complete.append(run)

    def m(vs): return round(sum(vs)/len(vs), 3) if vs else None

    condition_means = {c: {k: m(v) for k, v in d.items()} | {'count': len(d['ACI_n6']),
                                                             'ACI_n6_values': [round(x,3) for x in d['ACI_n6']]}
                       for c, d in sorted(cond_data.items())}

    overall = {}
    for group, prefix in [('Q', 'Q'), ('A', 'A')]:
        agg = defaultdict(list)
        for c, d in cond_data.items():
            if c.startswith(prefix):
                for k, vs in d.items():
                    agg[k].extend(vs)
        overall[group] = {k: m(vs) for k, vs in agg.items() if vs} | {'n': len(agg.get('ACI_n6', []))}

    # 排布敏感性 = ACI(n=4) − ACI(n=6) > 0.15 的 run 占比（两条件合并）
    deltas = [(run, by_run[run]['ACI_n4'] - by_run[run]['ACI_n6']) for run in complete]
    sens_orig = sum(1 for _, d in deltas if d > 0.15)
    a7_deltas = [(run, by_run[run]['ACI_a7_top2_n4'] - by_run[run]['ACI_a7_top2_n6'])
                 for run in complete if by_run[run].get('ACI_a7_top2_n4') is not None]
    sens_a7 = sum(1 for _, d in a7_deltas if d > 0.15)

    summary = {
        'paper': 'A03',
        'topic': '10-13世纪吴江县、嘉定县水利开发与新县增设',
        'complete_runs': complete,
        'incomplete_runs': incomplete,
        'human_tree': human_tree,
        'settings': {
            'rounds': 10, 'main_k': 6, 'robust_k': 4,
            'source_id_policy': 'exact_shared_roster',
            'exclude_A': True, 'cross_level': True,
        },
        'tiers': tiers,
        'tier_rule': '同一批引文，扩展不同长度上下文（S=核心引文 / M≈200字 / L≈400字）',
        'by_run': by_run,
        'condition_means': condition_means,
        'overall': overall,
        'sensitivity': {
            'orig': {'n_sensitive': sens_orig, 'pct': round(sens_orig / len(complete) * 100, 1)},
            'a7_top2': {'n_sensitive': sens_a7, 'pct': round(sens_a7 / len(a7_deltas) * 100, 1) if a7_deltas else None},
            'threshold_n6_minus_n4_gt_0.15': True,
        },
        'tier_effect': {
            'Q': {lv: condition_means.get(f'Q{lv}', {}).get('ACI_n6') for lv in 'SML'},
            'A': {lv: condition_means.get(f'A{lv}', {}).get('ACI_n6') for lv in 'SML'},
        },
    }

    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'汇总 {len(complete)}/{len(runs)} 个 run')
    print(f'三档规模: {tiers}')
    for c, d in condition_means.items():
        print(f'  {c}: ACI(n=6)={d["ACI_n6"]}  SCI={d["SCI_n6"]}  n={d["count"]}')
    for g in 'QA':
        print(f'  {g} 总体: ACI(n=6)={overall[g].get("ACI_n6")}')
    print(f'敏感性 原始={summary["sensitivity"]["orig"]["pct"]}%  A7={summary["sensitivity"]["a7_top2"]["pct"]}%')
    print(f'档位效应 Q={summary["tier_effect"]["Q"]}')
    print(f'档位效应 A={summary["tier_effect"]["A"]}')


if __name__ == '__main__':
    main()
