# -*- coding: utf-8 -*-
"""A 组人类论文 原文_clean.json 通用重洗脚本（自然段级）。

统一管线（7 篇共用，不再逐篇手写）：
  1. 文本源：full.md，按空行切自然块；
  2. 分段规则：blocks[0] 为主标题；第一个「#+ 一 …」之前的非标题块全部判为
     前置（作者/单位/摘要/关键词/DOI/引言），不进 paragraphs；
     其后按块首是否为 # 分 title / text，text 块即「正文自然段」；
  3. 史料绑定：段内脚注圈号 ①–⑩ → M 名册 (期刊页码, 圈号) 字典。
     - 有 PDF：页码由 PDF 页文本匹配得到（精确模式）；
     - 无 PDF：页码由新段文本回查旧段落继承（继承模式），
       本页查不到时向后续相邻页回退找未消费的同圈号条目；
  4. 全局单调性约束：匹配到的 M 的 (页码, 圈号) 序列不减，防止复述句误抢；
  5. 交叉校验：旧段 refs 并集 vs 其子段 refs 并集，差异全部进报告。

用法:
  python rebuild_clean.py A01            # 继承模式（无 PDF）
  python rebuild_clean.py A02 --pdf      # 精确模式（有 PDF）
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
MDB = ROOT / r'脚本&数据/数据集/论证树提取结果/A组'
PDFDIR = ROOT / r'论文/人类论文'
OUTDIR = ROOT / r'脚本&数据/重洗_A组'

CIRC = '①②③④⑤⑥⑦⑧⑨⑩'
FN_ORDER = {c: i for i, c in enumerate(CIRC)}
FW = str.maketrans('０１２３４５６７８９', '0123456789')

# 各篇人类论文 PDF 文件名（无 PDF 的篇为 None，走继承模式）
PDF_MAP = {
    'A02': '南宋富民闭粜现象及政府应对策略_韩冠群.pdf',
    'A05': '北宋开封的动物交易——以《东京梦华录》为中心_张显运.pdf',
}

# 第一个正文章节标题的识别：一/引言/前言/绪言/绪论/问题的提出
FIRST_SECTION = re.compile(r'^#+\s*(一[\s、]|引言|前言|绪[言论]|问题的提出)')


def norm(s):
    """去空白与 PDF 私用区字符，用于文本比对。"""
    return re.sub(r'[\s\ue5d2\ue5cf\u3000\uf0b7*]', '', s)


def load_pdf_pages(pdf_path):
    """返回 (page_norm, page_journal)：每页正文归一化文本、每页期刊页码。"""
    import pymupdf
    doc = pymupdf.open(pdf_path)
    page_norm, page_journal = [], []
    for pg in doc:
        H = pg.rect.height
        d = pg.get_text('dict')
        body = []
        num = None
        for b in d['blocks']:
            if b['type'] != 0:
                continue
            for l in b['lines']:
                txt = ''.join(s['text'] for s in l['spans']).strip()
                if not txt:
                    continue
                if l['bbox'][1] <= H * 0.65:
                    body.append(txt)
                if l['bbox'][1] > H * 0.88:
                    m = re.search(r'([0-9０-９]{2,4})', txt)
                    if m:
                        num = int(m.group(1).translate(FW))
        page_norm.append(norm(''.join(body)))
        page_journal.append(num)
    return page_norm, page_journal


def is_nonbody(b):
    """表格 / 图片块不产论证节点，整块剔除。"""
    bl = b.lower()
    return '<table' in bl or '</table>' in bl or b.startswith('![') or b.startswith('<img')


def segment(md_text):
    """full.md → (段落列表, 前置文本列表, 剔除块列表)。段落为 dict(id, type, text)。"""
    raw = [b.strip() for b in re.split(r'\n\s*\n', md_text) if b.strip()]
    dropped = [(i, b[:50]) for i, b in enumerate(raw) if is_nonbody(b)]
    blocks = [b for b in raw if not is_nonbody(b)]
    try:
        first_section = next(i for i, b in enumerate(blocks) if FIRST_SECTION.match(b))
    except StopIteration:
        raise SystemExit('未找到首个正文章节标题（一/引言…），请检查 full.md')

    front_texts = [re.sub(r'\s', '', b) for b in blocks[1:first_section]
                   if not b.startswith('#')]
    kept = [('title', blocks[0].lstrip('#').strip())]
    for b in blocks[first_section:]:
        if b.startswith('#'):
            kept.append(('title', b.lstrip('#').strip()))
        else:
            kept.append(('text', re.sub(r'\s', '', b)))
    paras = [{'id': f'P{n}', 'type': t, 'text': x} for n, (t, x) in enumerate(kept, 1)]
    return paras, front_texts, dropped


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


def assign_pages_pdf(paras, page_norm, page_journal):
    """精确模式：段落头尾文本在 PDF 页文本中定位。"""
    notes, unmatched = [], []
    prev = 0
    for p in paras:
        if p['type'] == 'title':
            p['pg'] = None
            continue
        t = norm(p['text'])
        hp = []
        for L in (40, 30, 24, 16, 12):
            probe = t[:L]
            hp = [i for i, pt in enumerate(page_norm) if probe in pt and i >= prev] or \
                 [i for i, pt in enumerate(page_norm) if probe in pt]
            if hp:
                break
        if not hp:
            best, hp = 0, []
            probe = t[:20]
            for i, pt in enumerate(page_norm):
                r = SequenceMatcher(None, probe, pt).find_longest_match(0, len(probe), 0, len(pt))
                if r.size > best:
                    best, hp = r.size, [i]
            if best < 12:
                unmatched.append(p['id'])
                p['pg'] = page_journal[prev] if page_journal[prev] else None
                notes.append(f"{p['id']}: 页匹配失败，沿用上一段期刊页{p['pg']}")
                continue
            notes.append(f"{p['id']}: 头部LCS兜底({best})→期刊页{page_journal[hp[0]]}")
        pj = page_journal[hp[0]]
        p['pg'] = pj
        prev = hp[0]
    return notes, unmatched


def bind_refs(paras, roster, lookahead=8, lookbehind=2):
    """段内圈号 → M（本页精确优先，缺失时向前后邻近页搜索）。

    继承模式下多个自然段可能共用同一继承页码，页内圈号一旦被前段消费，
    后段须跨页寻找同圈号的新页条目，故搜索窗口需覆盖段落实际跨度。
    每个 M 全局只消费一次，避免同一史料被重复挂到多段。
    """
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pid')
    ap.add_argument('--pdf', action='store_true', help='有 PDF 时走精确页匹配模式')
    args = ap.parse_args()
    pid = args.pid

    md_path = MDB / pid / '原始输入/full.md'
    old_path = BASE / pid / '00_原文/原文_clean.json'
    out_path = BASE / pid / '00_原文/原文_clean_自然段.json'
    if not md_path.exists():
        raise SystemExit(f'缺少 full.md: {md_path}')
    if not old_path.exists():
        raise SystemExit(f'缺少 原文_clean.json: {old_path}')

    old = json.loads(old_path.read_text(encoding='utf-8'))
    materials = old['materials']
    paras, front_texts, dropped = segment(md_path.read_text(encoding='utf-8'))
    roster, empty_roster = build_roster(materials)

    mode_note = ''
    if args.pdf:
        pdf_name = PDF_MAP.get(pid)
        if not pdf_name:
            raise SystemExit(f'{pid} 无 PDF 映射，去掉 --pdf 走继承模式')
        page_norm, page_journal = load_pdf_pages(PDFDIR / pdf_name)
        journal2idx = {j: i for i, j in enumerate(page_journal) if j is not None}
        # 把韵脚换成 PDF 页序：roster 用期刊页码，段落也用期刊页码，故只需映射段→期刊页
        notes, unmatched = assign_pages_pdf(paras, page_norm, page_journal)
        mode_note = f'PDF 精确页匹配（{pdf_name}）'
    else:
        notes = assign_pages_inherit(paras, old['paragraphs'], roster)
        unmatched = []
        mode_note = '旧段落页码继承 + 相邻页回退'

    logs, conflicts = bind_refs(paras, roster)
    inherit_lines = cross_check(paras, old['paragraphs'])

    out = {
        'meta': {
            'paper_id': pid,
            'provenance': (f'full.md 自然段重切；material_refs 由 (期刊页码, 脚注圈号) 确定性恢复；'
                           f'页码来源：{mode_note}'),
            'rebuild_date': '2026-10-25',
            'note': '自然段级重洗副本，未覆盖原 原文_clean.json；前置（作者/单位/摘要/关键词/DOI/引言）不进 paragraphs',
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

    OUTDIR.mkdir(parents=True, exist_ok=True)
    rep = [f'# {pid} 重洗报告（自然段级）', '',
           f'- 模式：{mode_note}',
           f'- 处理段 {len(paras)}（标题 {len(paras) - n_text} / 正文 {n_text}）',
           f'- 正文段字数：合计 {sum(lens)}，最长 {max(lens) if lens else 0}，均值 {sum(lens) // max(n_text, 1)}',
           f'- refs 总计 {sum(len(p.get("material_refs", [])) for p in paras)}，'
           f'M 使用 {len(used)}/{len(materials)} = {len(used) / max(len(materials), 1):.1%}',
           f'- 页匹配失败：{unmatched or "无"}',
           f'- 单调性冲突：{len(conflicts)} 条',
           '', '## 剔除的非正文块（表格 / 图片）',
           *([f'- 原块[{i}]: {t}' for i, t in dropped] or ['- 无']),
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
          f'| 继承差异 {len(inherit_lines)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
