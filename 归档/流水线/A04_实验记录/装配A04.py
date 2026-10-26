#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""装配 A04 实验数据骨架：为 30 篇模型论文生成 00_原文/原文_clean.json，并装配人类基准。"""
import json, os, re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
A04 = ROOT / 'A04_实验记录'
GEN = A04 / '生成轮次'
POC = A04 / '史料池输入'
OUT = ROOT / '实验数据' / 'A04' / '03_实验输出' / 'Q_A_实验'
HUMAN_SRC = ROOT / 'A组交付包_20261018' / 'A04' / '第二轮复现'

CN = '一二三四五六七八九十'
HEAD_RE = re.compile(r'^\s*#{0,6}\s*[' + CN + r']+\s*[、.．,，]')
CONCL_RE = re.compile(r'^(结\s*语|结\s*论|余\s*论|小\s*结|总\s*结)')
CITE_RE = re.compile(r'\[A04-(M\d+)\]')
POOLS = {'S': 'pool_text_S.txt', 'M': 'pool_text_M.txt', 'L': 'pool_text_L.txt'}


def load_materials(level):
    mats, seq = [], 0
    for ln in (POC / POOLS[level]).read_text(encoding='utf-8').splitlines():
        m = re.match(r'\[A04-(M\d+)\]\s*出处：(.*?)｜引文：', ln)
        if not m:
            continue
        seq += 1
        mats.append({'id': m.group(1), 'seq': seq, 'text': m.group(2).strip()})
    return mats


def parse_md(text):
    paras = []
    for raw in text.split('\n'):
        s = raw.strip()
        if not s:
            continue
        if not paras:
            paras.append({'type': 'title', 'text': s, 'material_refs': []})
            continue
        if HEAD_RE.match(s):
            core = re.sub(r'^\s*#{0,6}\s*', '', s)
            core = re.sub(r'^[' + CN + r']+\s*[、.．,，]?\s*', '', core).strip()
            hl = 0 if CONCL_RE.match(core) else 1
            paras.append({'type': 'title', 'text': s, 'heading_level': hl,
                          'material_refs': []})
            continue
        refs = CITE_RE.findall(s)
        paras.append({'type': 'text', 'text': s, 'material_refs': refs})

    if not any(p.get('type') == 'title' and p.get('heading_level') == 0 for p in paras):
        j = None
        for i in range(len(paras) - 1, -1, -1):
            if paras[i]['type'] == 'text' and paras[i]['text'].startswith('综合史料池'):
                j = i
                break
        if j is None:
            j = len(paras) - 1
        paras.insert(j, {'type': 'title', 'text': '结语', 'heading_level': 0,
                         'material_refs': []})

    for i, p in enumerate(paras, 1):
        p['id'] = f'P{i}'
    return paras


def level_of(run):
    return run[1]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mats_cache = {lv: load_materials(lv) for lv in POOLS}

    runs = sorted(d.name for d in GEN.iterdir()
                  if d.is_dir() and re.match(r'^[QA][SML]_R\d$', d.name))
    report = []
    for run in runs:
        fp = GEN / run / '论文_模型原始输出.md'
        if not fp.exists():
            report.append((run, 'MISSING', 0, 0))
            continue
        paras = parse_md(fp.read_text(encoding='utf-8'))
        mats = mats_cache[level_of(run)]
        valid = {m['id'] for m in mats}
        bad = sorted({r for p in paras for r in p['material_refs']} - valid)
        d = OUT / run / '00_原文'
        d.mkdir(parents=True, exist_ok=True)
        (d / '原文_clean.json').write_text(json.dumps(
            {'paragraphs': paras, 'materials': mats}, ensure_ascii=False, indent=1),
            encoding='utf-8')
        ntext = sum(p['type'] == 'text' for p in paras)
        report.append((run, ('OK' if not bad else '越界:' + ','.join(bad)),
                       len(paras), ntext))

    hd = OUT / 'A_human_baseline'
    hd.mkdir(parents=True, exist_ok=True)
    shutil.copytree(HUMAN_SRC / '00_原文', hd / '00_原文', dirs_exist_ok=True)
    shutil.copy2(HUMAN_SRC / 'run_论证树.json', hd / 'run_论证树.json')

    print(f'{"轮次":<8}{"状态":<16}{"段落":>5}{"正文":>5}')
    for r, st, np_, nt in report:
        print(f'{r:<8}{st:<16}{np_:>5}{nt:>5}')
    print(f'\n共装配模型 run {len(runs)} 个；人类基准来自 交付包/A04/第二轮复现')
    print('输出目录:', OUT.relative_to(ROOT))


if __name__ == '__main__':
    main()
