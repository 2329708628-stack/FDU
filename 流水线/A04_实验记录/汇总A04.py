#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总 A04 全部 run 的 ACI/SCI（n=6 主阈值 + n=4 鲁棒阈值 + A-7 topN 合并）。

频次聚合 JSON 结构：main.overall.ACI / robustness.overall.ACI / a7_merge.topN.nK.ACI，
与 A03/A04–A10 口径一致。
"""
import json, re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
AID = 'A04'
TOPIC = '唐宋瓷窑官的产生与宋代瓷窑官制度的演变'
LAB = ROOT / '实验数据' / AID / '03_实验输出' / 'Q_A_实验'
OUT = ROOT / f'{AID}_实验记录' / f'对齐汇总_{AID}.json'
HUMAN = LAB / 'A_human_baseline' / 'run_论证树.json'
TIER_JSON = ROOT / f'{AID}_实验记录' / f'档位说明_{AID}.json'


def load_freq(run_dir):
    fp = run_dir / '频次聚合.json'
    if not fp.exists():
        return None
    d = json.loads(fp.read_text(encoding='utf-8'))
    out = {
        'ACI_n6': d.get('main', {}).get('overall', {}).get('ACI'),
        'SCI_n6': d.get('main', {}).get('SCI'),
        'ACI_n4': d.get('robustness', {}).get('overall', {}).get('ACI'),
        'SCI_n4': d.get('robustness', {}).get('SCI'),
        'main_threshold': d.get('main_threshold', 6),
        'robustness_threshold': d.get('robustness_threshold', 4),
    }
    a7 = d.get('a7_merge', {})
    for N in (2, 3, 4):
        blk = a7.get(f'top{N}', {})
        if blk:
            out[f'ACI_a7_top{N}_n6'] = blk.get('n6', {}).get('ACI')
            out[f'ACI_a7_top{N}_n4'] = blk.get('n4', {}).get('ACI')
            out[f'SCI_a7_top{N}_n6'] = blk.get('n6', {}).get('SCI')
    return out


def main():
    runs = sorted(d.name for d in LAB.iterdir()
                  if d.is_dir() and re.match(r'^[QA][SML]_R\d$', d.name))

    human_tree = {}
    if HUMAN.exists():
        t = json.loads(HUMAN.read_text(encoding='utf-8'))['encoding_table']
        A, B, C = (t.get(f'{k}_level', []) for k in 'ABC')
        zero_c = sum(1 for c in C if not c.get('sources'))
        human_tree = {
            'A_nodes': len(A), 'B_nodes': len(B), 'C_nodes': len(C),
            'C_zero_source': zero_c,
            'total_scored': len(A) + len(B) + len(C) - zero_c,
            'nested_B': [b['id'] for b in B if b.get('parent', 'A1').startswith('B')],
            'M_roster': len(t.get('M_level', [])),
            'score_rule': '全部 A/B/C 节点减去无 sources 的 C 节点（exclude_A=true 时 A 层不参与计分）',
        }

    tiers = {}
    if TIER_JSON.exists():
        d = json.loads(TIER_JSON.read_text(encoding='utf-8'))
        # 新三档设计：同一批引文，扩展不同上下文长度；以 char_counts 表示各档规模
        tiers = d.get('char_counts') or {lv: d[lv].get('entries') for lv in 'SML' if lv in d}

    by_run = {}
    cond_data = defaultdict(lambda: {'ACI_n6': [], 'SCI_n6': [], 'ACI_n4': [],
                                     'ACI_a7_top2_n6': [], 'ACI_a7_top3_n6': [],
                                     'ACI_a7_top4_n6': [], 'ACI_a7_top2_n4': []})
    complete, incomplete = [], []

    for run in runs:
        freq = load_freq(LAB / run)
        if freq is None or freq.get('ACI_n6') is None:
            incomplete.append(run); continue
        by_run[run] = freq
        for k in cond_data[run[:2]]:
            v = freq.get(k)
            if v is not None:
                cond_data[run[:2]][k].append(v)
        complete.append(run)

    def m(vs): return round(sum(vs)/len(vs), 3) if vs else None

    condition_means = {
        c: {k: m(v) for k, v in d.items()} | {'count': len(d['ACI_n6'])}
        for c, d in sorted(cond_data.items())
    }

    overall = {}
    for g in 'QA':
        agg = defaultdict(list)
        for c, d in cond_data.items():
            if c.startswith(g):
                for k, vs in d.items():
                    agg[k].extend(vs)
        overall[g] = {k: m(vs) for k, vs in agg.items() if vs} | {'n': len(agg.get('ACI_n6', []))}

    deltas = [(r, by_run[r]['ACI_n4'] - by_run[r]['ACI_n6']) for r in complete]
    sens_orig = sum(1 for _, d in deltas if d > 0.15)
    a7_deltas = [(r, by_run[r]['ACI_a7_top2_n4'] - by_run[r]['ACI_a7_top2_n6'])
                 for r in complete if by_run[r].get('ACI_a7_top2_n4') is not None]
    sens_a7 = sum(1 for _, d in a7_deltas if d > 0.15)

    summary = {
        'paper': AID,
        'topic': TOPIC,
        'complete_runs': complete,
        'incomplete_runs': incomplete,
        'human_tree': human_tree,
        'settings': {'rounds': 10, 'main_k': 6, 'robust_k': 4,
                     'source_id_policy': 'exact_shared_roster',
                     'exclude_A': True, 'cross_level': True},
        'tiers': tiers,
        'tier_rule': '同一批引文，扩展不同长度上下文（S=核心引文 / M≈200字 / L≈400字）',
        'tier_axis_valid': True,
        'tier_axis_note': '2026-10-24 从史料上下文库CSV重建三档并重跑：三档引文集合相同，仅上下文长度不同',
        'by_run': by_run,
        'condition_means': condition_means,
        'overall': overall,
        'sensitivity': {
            'orig': {'n_sensitive': sens_orig,
                     'pct': round(sens_orig / len(complete) * 100, 1) if complete else None},
            'a7_top2': {'n_sensitive': sens_a7,
                        'pct': round(sens_a7 / len(a7_deltas) * 100, 1) if a7_deltas else None},
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
        print(f'  {g} 总体 ACI(n=6)={overall[g].get("ACI_n6")}  A7top2={overall[g].get("ACI_a7_top2_n6")}')
    print(f'敏感性 原始={summary["sensitivity"]["orig"]["pct"]}%  A7={summary["sensitivity"]["a7_top2"]["pct"]}%')
    print(f'档位效应 Q={summary["tier_effect"]["Q"]}')
    print(f'档位效应 A={summary["tier_effect"]["A"]}')


if __name__ == '__main__':
    main()
