# -*- coding: utf-8 -*-
"""B/C 组人类论文 原文_clean.json 自然段级重洗脚本（新管线第一步）。

与 A 组 rebuild_clean.py 同构，差异：
  1. 文本源统一为 归档/.../<pid>/00_原文/full.md（B 组无 原始输入/full.md）；
  2. 只走继承模式（无 PDF 精确页），B/C 的 PDF 文本层不可用；
  3. 首个章节标题识别兼容裸编号「# 一」/「# 二」；
  4. 末尾 back matter（作者简介/责任编辑/参考文献/附录）整块剔除，不进 paragraphs；
  5. C01、C10 原文丢标题：用 TITLE_PATCH 在指定正文块前补回裸编号标题，
     不改动 full.md，补丁明细写入重洗报告。

用法:
  python rebuild_clean_BC.py B01
  python rebuild_clean_BC.py --all
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(r'C:/Users/23297/Downloads/FDUROP')
BASE = ROOT / r'归档/数据集/数据清洗后论文'
OUTDIR = ROOT / r'脚本&数据/重洗_BC组'

CIRC = '①②③④⑤⑥⑦⑧⑨⑩'
FN_ORDER = {c: i for i, c in enumerate(CIRC)}

PIDS = [f'B{i:02d}' for i in range(1, 11)] + [f'C{i:02d}' for i in range(1, 11)]

# 第一个正文章节标题：一、…／裸「一」／引言／前言／绪言／绪论／问题的提出
FIRST_SECTION = re.compile(r'^#+\s*(一[\s、]|一$|引言|前言|绪[言论]|问题的提出)')

# 正文之后的附属块：不产论证节点，整块剔除
BACK_MATTER = re.compile(r'^[（(]?\s*(作者简介|责任编辑|参考文献|附\s*录|英文摘要)')

# 无「作者简介：」前缀的独立作者传记块（仅文档尾部 3 块内判定，避免误伤正文人物小传）
BIO_TAIL = re.compile(r'^[（(]?\s*[\u4e00-\u9fa5]{2,4}[（(]\d{4}\s*[—\-－~～]')

# 原文结构性标题丢失的人工补丁：pid → [(正文块起始文本, 补入标题)]
TITLE_PATCH = {
    'C01': [('与宋代大多数文人一样', '# 二')],
    'C10': [('戴栩，字文子，号浣川', '# 一'), ('戴栩忧于南宋', '# 二')],
}


def norm(s):
    """去空白与 PDF 私用区字符，用于文本比对。"""
    return re.sub(r'[\s\ue5d2\ue5cf\u3000\uf0b7*]', '', s)


def is_nonbody(b):
    """表格 / 图片块不产论证节点，整块剔除。"""
    bl = b.lower()
    return '<table' in bl or '</table>' in bl or b.startswith('![') or b.startswith('<img')


def apply_title_patch(pid, blocks):
    """在指定正文块前插入丢失的章节标题，返回 (blocks, 补丁明细)。"""
    patches = TITLE_PATCH.get(pid, [])
    if not patches:
        return blocks, []
    out, logs = list(blocks), []
    for probe, heading in patches:
        key = norm(probe)
        idx = next((i for i, b in enumerate(out) if not b.startswith('#') and key in norm(b)), None)
        if idx is None:
            logs.append(f'补丁未命中：{heading} ← 「{probe}」')
            continue
        if idx > 0 and out[idx - 1].strip() == heading:
            continue
        out.insert(idx, heading)
        logs.append(f'补入「{heading}」于块 {idx}，其前文本：{out[idx - 1][:24] if idx else "（文首）"}')
    return out, logs


def segment(pid, md_text):
    """full.md → (段落列表, 前置文本列表, 剔除块列表, 补丁明细)。"""
    raw = [b.strip() for b in re.split(r'\n\s*\n', md_text) if b.strip()]
    dropped = [(i, b[:50]) for i, b in enumerate(raw) if is_nonbody(b)]
    blocks = [b for b in raw if not is_nonbody(b) and not BACK_MATTER.match(b)]
    for i in range(len(blocks) - 1, max(len(blocks) - 4, -1), -1):
        if BIO_TAIL.match(blocks[i]):
            dropped.append((len(raw) + len(dropped), '尾部作者简介：' + blocks[i][:50]))
            del blocks[i]
    blocks, patch_logs = apply_title_patch(pid, blocks)
    try:
        first_section = next(i for i, b in enumerate(blocks) if FIRST_SECTION.match(b))
    except StopIteration:
        raise SystemExit(f'[{pid}] 未找到首个正文章节标题（一/引言…），请检查 full.md')

    front_texts = [re.sub(r'\s', '', b) for b in blocks[1:first_section]
                   if not b.startswith('#')]
    kept = [('title', blocks[0].lstrip('#').strip())]
    for b in blocks[first_section:]:
        if b.startswith('#'):
            kept.append(('title', b.lstrip('#').strip()))
        else:
            kept.append(('text', re.sub(r'\s', '', b)))
    paras = [{'id': f'P{n}', 'type': t, 'text': x} for n, (t, x) in enumerate(kept, 1)]
    return paras, front_texts, dropped, patch_logs


def build_roster(materials):
    """M 名册 → {(期刊页码, 圈号): M_id}；返回 (roster, 空页码条目)。"""
    roster, empty = {}, []
    for m in materials:
        pg = str(m.get('page', '')).strip()
        fn = m.get('footnote_number')
        if pg.isdigit() and fn in FN_ORDER:
            key = (int(pg), fn)
            roster.setdefault(key, m['id'])
        else:
            empty.append(m)
    return roster, empty


def assign_pages_inherit(paras, old_paras, roster):
    """继承模式：新段文本回查旧段落，继承其页码。"""
    old_norm = [(op, norm(op.get('text', ''))) for op in old_paras if op.get('type') == 'text']
    notes = []
    last_pg = None
    for p in paras:
        if p['type'] == 'title':
            p['pg'] = None
            continue
        t = norm(p['text'])
        probe = t[:40] if len(t) >= 40 else t
        hit_pg = None
        for op, ot in old_norm:
            if probe and probe in ot:
                sp = str(op.get('page', '')).strip()
                if sp.isdigit():
                    hit_pg = int(sp)
                    break
        if hit_pg is None:  # LCS 兜底，容忍 OCR/格式噪声
            best, bp = 0, None
            for op, ot in old_norm:
                r = SequenceMatcher(None, probe, ot).find_longest_match(0, len(probe), 0, len(ot))
                if r.size > best:
                    sp = str(op.get('page', '')).strip()
                    if sp.isdigit():
                        best, bp = r.size, int(sp)
            if best >= 20:
                hit_pg = bp
                notes.append(f"{p['id']}: 继承页由LCS兜底(sim={best})→期刊页{bp}")
            else:
                hit_pg = last_pg
                notes.append(f"{p['id']}: 继承页失败，沿用上一段页{hit_pg}")
        p['pg'] = hit_pg
        last_pg = hit_pg
    return notes


def bind_refs(paras, roster, lookahead=8, lookbehind=2):
    """段内圈号 → M（本页精确优先，缺失时向前后邻近页搜索）。"""
    used, logs, conflicts = set(), [], []
    for p in paras:
        if p['type'] == 'title':
            p['material_refs'] = []
            continue
        pg = p.get('pg')
        refs, unresolved = [], []
        for mt in re.finditer('[' + CIRC + ']', p['text']):
            fn = mt.group()
            mid = None
            if pg is not None:
                cand = roster.get((pg, fn))
                if cand and cand not in used:
                    mid = (cand, pg)
                if mid is None:  # 向后：段落实际跨到了后面的页
                    for d in range(1, lookahead + 1):
                        cand = roster.get((pg + d, fn))
                        if cand and cand not in used:
                            mid = (cand, pg + d)
                            break
                if mid is None:  # 向前：继承页码偏大
                    for d in range(1, lookbehind + 1):
                        cand = roster.get((pg - d, fn))
                        if cand and cand not in used:
                            mid = (cand, pg - d)
                            break
            if mid:
                refs.append(mid[0])
                used.add(mid[0])
                if abs(mid[1] - pg) > 1:
                    conflicts.append(f"{p['id']}: {fn} 命中期刊页{mid[1]}，段页{pg}")
            else:
                unresolved.append(f"{fn}@{mt.start()}(期刊页{pg})")
        p['material_refs'] = refs
        if unresolved:
            logs.append((p['id'], unresolved))
    return logs, conflicts


def cross_check(paras, old_paras):
    """旧段 refs 并集 vs 其子段 refs 并集。"""
    old_norm = [(op, norm(op.get('text', ''))) for op in old_paras if op.get('type') == 'text']
    agg = defaultdict(set)
    for p in paras:
        if p['type'] != 'text':
            continue
        t = norm(p['text'])
        probe = t[:40] if len(t) >= 40 else t
        for op, ot in old_norm:
            if probe and probe in ot:
                agg[op['id']] |= set(p['material_refs'])
                break
    lines = []
    for op in old_paras:
        if op.get('type') != 'text':
            continue
        old_refs = set(op.get('material_refs', []))
        new_refs = agg.get(op['id'], set())
        miss = sorted(old_refs - new_refs)
        extra = sorted(new_refs - old_refs)
        if miss or extra:
            lines.append(f"- 旧{op['id']}: 丢失{miss} 新增{extra}")
    return lines


def run_one(pid):
    md_path = BASE / pid / '00_原文/full.md'
    old_path = BASE / pid / '00_原文/原文_clean.json'
    out_path = BASE / pid / '00_原文/原文_clean_自然段.json'
    if not md_path.exists():
        raise SystemExit(f'[{pid}] 缺少 full.md: {md_path}')
    if not old_path.exists():
        raise SystemExit(f'[{pid}] 缺少 原文_clean.json: {old_path}')

    old = json.loads(old_path.read_text(encoding='utf-8'))
    materials = old['materials']
    paras, front_texts, dropped, patch_logs = segment(pid, md_path.read_text(encoding='utf-8'))
    roster, empty_roster = build_roster(materials)

    mode_note = '旧段落页码继承 + 相邻页回退'
    notes = assign_pages_inherit(paras, old['paragraphs'], roster)
    logs, conflicts = bind_refs(paras, roster)
    inherit_lines = cross_check(paras, old['paragraphs'])

    out = {
        'meta': {
            'paper_id': pid,
            'provenance': ('full.md 自然段重切；material_refs 由 (期刊页码, 脚注圈号) 确定性恢复；'
                           f'页码来源：{mode_note}'),
            'rebuild_date': '2026-10-26',
            'note': ('自然段级重洗副本，未覆盖原 原文_clean.json；'
                     '前置（作者/单位/摘要/关键词/DOI/引言）与尾部作者简介不进 paragraphs'),
            'front_matter': front_texts,
        },
        'paragraphs': [
            {'id': p['id'], 'type': p['type'], 'text': p['text'],
             'page': str(p['pg']) if p.get('pg') is not None else '',
             'material_refs': p.get('material_refs', [])}
            for p in paras
        ],
        'materials': materials,
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')

    n_text = sum(1 for p in paras if p['type'] == 'text')
    used = {m for p in paras for m in p.get('material_refs', [])}
    lens = [len(p['text']) for p in paras if p['type'] == 'text']
    long_blocks = [(p['id'], len(p['text'])) for p in paras
                   if p['type'] == 'text' and len(p['text']) >= 2500]

    OUTDIR.mkdir(parents=True, exist_ok=True)
    rep = [f'# {pid} 重洗报告（自然段级）', '',
           f'- 模式：{mode_note}',
           f'- 处理段 {len(paras)}（标题 {len(paras) - n_text} / 正文 {n_text}）',
           f'- 正文段字数：合计 {sum(lens)}，最长 {max(lens) if lens else 0}，均值 {sum(lens) // max(n_text, 1)}',
           f'- refs 总计 {sum(len(p.get("material_refs", [])) for p in paras)}，'
           f'M 使用 {len(used)}/{len(materials)} = {len(used) / max(len(materials), 1):.1%}',
           f'- 单调性冲突：{len(conflicts)} 条',
           '', '## 标题补丁（原文标题缺失）',
           *(['- ' + x for x in patch_logs] or ['- 无']),
           '', '## 剔除的非正文块（表格 / 图片 / 作者简介等）',
           *([f'- 原块[{i}]: {t}' for i, t in dropped] or ['- 无']),
           '', '## ≥2500 字超长块', *([f'- {i}: {n} 字' for i, n in long_blocks] or ['- 无']),
           '', '## 页匹配备注', *(['- ' + x for x in notes] or ['- 无']), '']
    if conflicts:
        rep += ['## 单调性冲突明细', *['- ' + x for x in conflicts[:40]], '']
    rep += ['## 未解析圈号（应为研究文献脚注或页归属失败）']
    rep += [f'- {i}: ' + '; '.join(u) for i, u in logs] or ['- 无']
    rep += ['', '## 空页码 M 条目（旧数据孤儿，待人工定位）']
    rep += [f'- {m["id"]} 圈号{m.get("footnote_number")}: {m["text"][:60]}…' for m in empty_roster] or ['- 无']
    rep += ['', '## 旧块级并集继承检查', *(['- ' + x for x in inherit_lines] or ['- 全部继承完整'])]
    (OUTDIR / f'重洗报告_{pid}.md').write_text('\n'.join(rep), encoding='utf-8')

    print(f'[{pid}] 段落 {len(paras)}（正文 {n_text}） 最长段 {max(lens) if lens else 0} '
          f'| M 使用 {len(used)}/{len(materials)} | 未解析圈号 {sum(len(u) for _, u in logs)} '
          f'| 超长块 {len(long_blocks)} | 继承差异 {len(inherit_lines)}')
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pid', nargs='?')
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()
    if args.all:
        for pid in PIDS:
            try:
                run_one(pid)
            except SystemExit as e:
                print(f'!! {e}')
        return 0
    if not args.pid:
        ap.error('需给出 pid 或 --all')
    return run_one(args.pid)


if __name__ == '__main__':
    sys.exit(main())
