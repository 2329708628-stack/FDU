#!/usr/bin/env python3
"""A-7 top-N 合并（后处理，无 API 调用）。

逻辑：对每个人类节点 h，收集 10 轮中所有 RELATED 候选模型节点的票，
取票数最高的 top-N 个候选，逐轮合并（该轮 top-N 中任一有票则计 1 票，
每轮最多 1 票），合并后票数再卡阈值 n=6 / n=4。

消除"票被摊薄导致假阴性"的排布敏感性。
结果写回各 run 的 频次聚合.json 的 a7_merge 字段。
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '提取与生成管线'))

from measurement import aggregate, RELATED, config  # noqa: E402
from _整树LLM对齐 import load_tree  # noqa: E402
from 管线公共 import read_json, atomic_json  # noqa: E402

LAB = ROOT / '实验数据' / 'A04' / '03_实验输出' / 'Q_A_实验'
TOPNS = (2, 3, 4)


def a7_merge(human, model, data, cfg):
    rounds = [data['pairs']] + [r['pairs'] for r in data.get('extra_repeats', [])]
    hs = {n['node_id']: n for n in human}
    ms = {n['node_id']: n for n in model}

    def eligible(h, m):
        hn, mn = hs.get(h), ms.get(m)
        return bool(hn and mn and hn['level'] in {'B', 'C'} and mn['level'] in {'B', 'C'}
                    and (cfg['cross_level'] or hn['level'] == mn['level']))

    # 每轮的 RELATED (h,m) 集合（同轮去重）
    per_round = []
    for ps in rounds:
        s = {(p['human'], p['model']) for p in ps
             if p['label'] in RELATED and eligible(p['human'], p['model'])}
        per_round.append(s)

    # 每个人类节点的候选模型节点总票数
    cand = defaultdict(Counter)
    for s in per_round:
        for h, m in s:
            cand[h][m] += 1

    results = {}
    for topn in TOPNS:
        merged_edges = []
        for h, counter in cand.items():
            top = [m for m, _ in counter.most_common(topn)]
            freq = sum(1 for s in per_round if any((h, m) in s for m in top))
            best_m = counter.most_common(1)[0][0]
            merged_edges.append(dict(human=h, model=best_m, label='RELATED',
                                     relation_present=1, freq=freq))
        out = {}
        for k in (cfg['main_k'], cfg['robust_k']):
            edges = [e for e in merged_edges if e['freq'] >= k]
            agg = aggregate(human, model, edges, cfg)
            ov = agg['overall']
            out[f'n{k}'] = dict(ACI=ov['ACI'], SCI=agg['SCI'],
                                covered=ov['covered_human_nodes'],
                                n_human=ov['n_human_nodes'], n_edges=len(edges))
        results[f'top{topn}'] = out
    return results


def main():
    cfg = config()
    human_tree = load_tree(LAB / 'A_human_baseline')
    done, skipped = 0, []
    for rd in sorted(LAB.iterdir()):
        if not rd.is_dir() or rd.name == 'A_human_baseline':
            continue
        align = rd / '整树_LLM对齐.json'
        freq_f = rd / '频次聚合.json'
        if not align.exists() or not freq_f.exists():
            skipped.append((rd.name, '缺对齐/聚合文件'))
            continue
        data = read_json(align)
        if not data.get('complete') or data.get('n_repeats') != cfg['rounds']:
            skipped.append((rd.name, f"轮次不足 {data.get('n_repeats')}/{cfg['rounds']}"))
            continue
        model_tree = load_tree(rd)
        merged = a7_merge(human_tree, model_tree, data, cfg)
        freq = read_json(freq_f)
        freq['a7_merge'] = merged
        atomic_json(freq_f, freq)
        m2 = merged['top2'][f"n{cfg['main_k']}"]['ACI']
        m3 = merged['top3'][f"n{cfg['main_k']}"]['ACI']
        m4 = merged['top4'][f"n{cfg['main_k']}"]['ACI']
        print(f"{rd.name}: ACI(n=6) top2={m2:.3f} top3={m3:.3f} top4={m4:.3f}")
        done += 1
    print(f"\n完成 {done} run；跳过 {len(skipped)}: {skipped}")


if __name__ == '__main__':
    main()
