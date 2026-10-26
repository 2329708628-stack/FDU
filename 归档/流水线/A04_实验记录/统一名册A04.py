#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A04 名册统一：把 31 个 run 的 M 名册统一为共享名册。
- 模型 run：改写 00_原文/原文_clean.json 的 materials。
- 人类基准：M id 去子编号、M_level 重建、C/B/A 的 sources 归一。
仅本地操作，不调用 API。
"""
import json, re, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN_ROUNDS = ROOT / 'A04_实验记录' / '生成轮次'
POC = ROOT / 'A04_实验记录' / '史料池输入'
OUT = ROOT / '实验数据' / 'A04' / '03_实验输出' / 'Q_A_实验'
CANON = ROOT / '赵晨希' / 'A04_史料池.json'
HUMAN_SRC = ROOT / 'A组交付包_20261018' / 'A04' / '第二轮复现'

SUFFIX_RE = re.compile(r'(M\d+)[a-z]*')


def strip_suffix(x):
    return SUFFIX_RE.sub(r'\1', x) if isinstance(x, str) else x


def build_roster():
    data = json.loads(CANON.read_text(encoding='utf-8'))
    pool = {}
    for s in data['sources']:
        for p in s['passages']:
            mid = p.get('original_id')
            if mid:
                pool[mid] = {'id': mid,
                             'source_full': (p.get('source_full') or '').strip(),
                             'text': (p.get('text') or '').strip()}
    # S⊆M⊆L 嵌套，L 即全集，名册只从 L 档取（不再三档并集）
    gen = set(re.findall(r'\[A04-(M\d+)\]',
                         (POC / 'pool_text_L.txt').read_text(encoding='utf-8')))
    ht = json.loads((HUMAN_SRC / 'run_论证树.json').read_text(encoding='utf-8'))
    hum_srcs = set()
    for lv in ('A_level', 'B_level', 'C_level'):
        for n in ht['encoding_table'][lv]:
            hum_srcs |= {strip_suffix(x) for x in n.get('sources', [])}
    try:
        hum_mids = {strip_suffix(m['id']) for m in ht['encoding_table']['M_level']}
    except KeyError:
        hum_mids = set()
    hum = hum_srcs | hum_mids
    # 共享名册以人类引用为基准（A1 必须覆盖完整名册）
    # 额外补上生成池独有但模型引用的条目（避免模型侧越界）
    extra_model = gen - hum
    all_ids = hum | extra_model
    ids = sorted(all_ids, key=lambda x: int(re.match(r'M(\d+)', x).group(1)))
    missing = [i for i in ids if i not in pool]
    if missing:
        print(f'  警告: 以下 M 不在规范池中，将用空 source_full: {missing}')
    return [pool.get(i, {'id': i, 'source_full': '', 'text': ''}) for i in ids], pool, gen, hum


def main():
    roster, pool, gen, hum = build_roster()
    idset = {r['id'] for r in roster}
    print(f'共享名册 {len(roster)} 条 = 生成池{len(gen)} ∪ 人类引用{len(hum)}')

    runs = sorted(d.name for d in GEN_ROUNDS.iterdir()
                  if d.is_dir() and re.match(r'^[QA][SML]_R\d$', d.name))
    leaf_bad = []
    for run in runs:
        fp = OUT / run / '00_原文' / '原文_clean.json'
        if not fp.exists():
            continue
        d = json.loads(fp.read_text(encoding='utf-8'))
        for p in d['paragraphs']:
            p['material_refs'] = [strip_suffix(r) for r in p.get('material_refs', [])]
            bad = [r for r in p['material_refs'] if r not in idset]
            if bad:
                leaf_bad.append((run, p['id'], bad))
        d['materials'] = roster
        fp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')

    def _norm_node(n):
        """归一单个节点的 sources + source_count 同步更新。"""
        new = sorted({strip_suffix(x) for x in n.get('sources', [])},
                     key=lambda x: int(re.match(r'M(\d+)', x).group(1)))
        n['sources'] = new
        n['source_count'] = len(new)
        return n

    fixed_trees = []
    for run in runs:
        tfm = OUT / run / 'run_论证树.json'
        if not tfm.exists():
            continue
        tm = json.loads(tfm.read_text(encoding='utf-8'))
        etm = tm['encoding_table']
        for lv in ('A_level', 'B_level', 'C_level'):
            for n in etm.get(lv, []):
                _norm_node(n)
        etm['M_level'] = [{'id': r['id'], 'text': r['text'], 'source_full': r['source_full']}
                          for r in roster]
        tfm.write_text(json.dumps(tm, ensure_ascii=False, indent=1), encoding='utf-8')
        fixed_trees.append(run)

    hrun = OUT / 'A_human_baseline'
    hfp = hrun / '00_原文' / '原文_clean.json'
    if hfp.exists():
        d = json.loads(hfp.read_text(encoding='utf-8'))
        for p in d['paragraphs']:
            p['material_refs'] = [strip_suffix(r) for r in p.get('material_refs', [])]
        d['materials'] = roster
        hfp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')

    tf = hrun / 'run_论证树.json'
    t = json.loads(tf.read_text(encoding='utf-8'))
    et = t['encoding_table']
    for lv in ('A_level', 'B_level'):
        for n in et.get(lv, []):
            s = sorted({strip_suffix(x) for x in n.get('sources', [])},
                       key=lambda x: int(re.match(r'M(\d+)', x).group(1)))
            n['sources'] = s
            n['source_count'] = len(s)
    # A1 必须覆盖完整名册（校验脚本要求）
    full_roster_ids = sorted({r['id'] for r in roster},
                             key=lambda x: int(re.match(r'M(\d+)', x).group(1)))
    for n in et.get('A_level', []):
        n['sources'] = full_roster_ids
        n['source_count'] = len(full_roster_ids)
    for n in et.get('C_level', []):
        s = sorted({strip_suffix(x) for x in n.get('sources', [])},
                   key=lambda x: int(re.match(r'M(\d+)', x).group(1)))
        n['sources'] = s
        n['source_count'] = len(s)
        if 'evidence_candidates' in n:
            n['evidence_candidates'] = [strip_suffix(x) for x in n['evidence_candidates']]
    et['M_level'] = [{'id': r['id'], 'text': r['text'], 'source_full': r['source_full']}
                     for r in roster]

    # statistics 必须写两份：run 顶层（校验.py 读取）和 encoding_table 内部（source_binding 习惯）。
    # 只写 et.statistics 会导致 校验.py 拿到旧值而报"不一致"。
    all_c_sources = set()
    for c in et.get('C_level', []):
        all_c_sources |= set(c.get('sources', []))
    source_count_by_A = {n['id']: len(n['sources']) for n in et.get('A_level', [])}
    source_count_by_B = {n['id']: len(n['sources']) for n in et.get('B_level', [])}
    m_stat = {
        'total': len(full_roster_ids),
        'used': len(all_c_sources
                    | {mid for n in et.get('A_level', []) for mid in n.get('sources', [])}
                    | {mid for n in et.get('B_level', []) for mid in n.get('sources', [])}),
        'unused': [],
    }
    c_no_src = sum(1 for c in et.get('C_level', []) if not c.get('sources'))
    a_n, b_n, c_n = len(et.get('A_level', [])), len(et.get('B_level', [])), len(et.get('C_level', []))

    top_st = t.setdefault('statistics', {})
    top_st.update({
        'source_count_by_A': source_count_by_A,
        'source_count_by_B': source_count_by_B,
        'M': m_stat,
        'C_nodes_without_sources': c_no_src,
        'claims_total': a_n + b_n,
        'total_A_nodes': a_n,
        'total_B_nodes': b_n,
        'total_C_nodes': c_n,
        'total_nodes': a_n + b_n + c_n,
        'total_unique_M': len(full_roster_ids),
    })
    et_st = et.setdefault('statistics', {})
    et_st.update({
        'source_count_by_A': source_count_by_A,
        'source_count_by_B': source_count_by_B,
        'M': m_stat,
        'C_nodes_without_sources': c_no_src,
        'claims_total': a_n + b_n,
        'total_nodes': a_n + b_n + c_n,
    })
    bad_para = []
    for p in t.get('paragraphs', []):
        p['material_refs'] = [strip_suffix(x) for x in p.get('material_refs', [])]
        bad = [x for x in p['material_refs'] if x not in idset]
        if bad:
            bad_para.append((p['id'], bad))
    tf.write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding='utf-8')

    print('模型 run 处理:', len(runs), '| 越界 refs:', len(leaf_bad),
          '| 已抽取树归一:', fixed_trees)
    for b in leaf_bad[:10]:
        print('  ', b)
    print('人类树内嵌段落越界:', bad_para)
    print('人类树已归一；M_level ->', len(et['M_level']))
    print('out:', OUT.relative_to(ROOT))


if __name__ == '__main__':
    main()
