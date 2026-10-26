#!/usr/bin/env python3
"""从【史料总库.xlsx】生成三档史料池：同一批引文，扩展不同长度的上下文。

论文方案（论文v3 line 33）：三档 = 同一批引文，各扩展不同长度的上下文。
  S 档 = 引用片段（核心引文）
  M 档 = 史料原文_200字（200 汉字上下文）
  L 档 = 史料原文_400字（400 汉字上下文，前 200 字即 M 档）

数据源：工作区根 史料总库.xlsx，工作表「史料库」
  列：篇目 | 论文 | 史料编号 | 脚注序号 | 汉字数 | 史料文本 | 引用片段 | 史料原文_200字 | 史料原文_400字 | 上下文来源

质量门：只有「引用片段」在 200 字上下文中覆盖率 ≥ --min-cov（默认 0.7）的条目才入池，
        保证 M/L 档确实是"含同一引文的更长上下文"；否则该条剔除并在档位说明中记录原因。

用法：
  python3 建档三档.py --id A03
  python3 建档三档.py --id A03 --check
  python3 建档三档.py --id A03 --min-cov 0.6 --base /path/史料总库.xlsx
"""
import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LINE_RE = re.compile(r'^\[(?P<id>[A-Z]\d{2})-(?P<m>M\d+[a-z]?)\]\s*出处：(?P<src>.+?)｜引文：')
import opencc
cc = opencc.OpenCC('t2s')
JUNK = re.compile(r'\^\{|\}|\{|\^\d+')
WS = re.compile(r'\s+')
VAR = str.maketrans({'隄': '堤', '嵗': '岁', '歳': '岁', '邨': '村', '疎': '疏'})


def clean(s):
    """去脚注残留 + 繁转简 + 合并空白换行（保证 pool 条目单行，不被按行解析截断）。"""
    return WS.sub('', cc.convert(JUNK.sub('', str(s or '')))).strip()


def base_id(mid):
    return re.sub(r'[a-z]$', '', str(mid))


def load_zongku(xlsx):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    ws = wb['史料库']
    out = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r or not r[0]:
            continue
        out.setdefault(str(r[0]).strip(), []).append({
            'mid': str(r[2]).strip(),
            'src': str(r[5] or '').strip(),
            'S': clean(r[6]),
            'M': clean(r[7]),
            'L': clean(r[8]),
        })
    wb.close()
    return out


def parse_pool(all_txt, aid):
    out = {}
    for ln in all_txt.splitlines():
        m = LINE_RE.match(ln)
        if m and m.group('id') == aid:
            out[m.group('m')] = (m.group('src').strip(),
                                 clean(ln.split('｜引文：', 1)[1] if '｜引文：' in ln else ''))
    return out


def coverage(quote, text):
    """引文在上下文中的字符覆盖率（繁简归一后按匹配块计）。"""
    import opencc
    cc = opencc.OpenCC('t2s')
    q = re.sub(r'[^\u4e00-\u9fff]', '', cc.convert(str(quote or '')))
    t = re.sub(r'[^\u4e00-\u9fff]', '', cc.convert(str(text or ''))).translate(VAR)
    q = q.translate(VAR)
    if not q or not t:
        return 0.0
    sm = SequenceMatcher(None, q, t, autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks() if b.size >= 2) / len(q)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--id', required=True)
    ap.add_argument('--base', default=str(ROOT / '史料总库.xlsx'))
    ap.add_argument('--min-cov', type=float, default=0.7)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    aid = a.id

    rec_dir = ROOT / f'{aid}_实验记录'
    poc = rec_dir / '史料池输入'
    all_f = poc / 'pool_text_all.txt'
    if not Path(a.base).exists():
        raise SystemExit(f'缺少史料总库：{a.base}')
    if not all_f.exists():
        raise SystemExit(f'缺少 {all_f}')

    zk = load_zongku(Path(a.base))
    if aid not in zk:
        raise SystemExit(f'史料总库中没有篇目 {aid}')
    pool = parse_pool(all_f.read_text(encoding='utf-8'), aid)
    mids = sorted(pool, key=lambda x: int(x[1:]))

    by_base = {}
    for r in zk[aid]:
        by_base.setdefault(base_id(r['mid']), []).append(r)

    tiers = {'S': [], 'M': [], 'L': []}
    nchar = {'S': 0, 'M': 0, 'L': 0}
    used, no_ctx, low_cov = [], [], []

    for mid in mids:
        cands = by_base.get(mid, [])
        if not cands:
            no_ctx.append(mid)
            continue
        scored = [(coverage(r['S'] or pool[mid][1], r['M']), r) for r in cands]
        best_cov, best = max(scored, key=lambda x: x[0])
        if best_cov < a.min_cov:
            low_cov.append((mid, round(best_cov, 2)))
            continue
        src = pool[mid][0] or best['src']
        body = {'S': best['S'] or pool[mid][1], 'M': best['M'], 'L': best['L']}
        used.append(mid)
        for lv in 'SML':
            tiers[lv].append(f'[{aid}-{mid}] 出处：{src}｜引文：{body[lv]}')
            nchar[lv] += len(re.sub(r'[^\u4e00-\u9fff]', '', body[lv]))

    n = len(tiers['S'])
    same = n == len(tiers['M']) == len(tiers['L'])
    order = nchar['S'] <= nchar['M'] <= nchar['L']
    print(f'{aid}：入池 {n} 条（总库有行 {len({base_id(r["mid"]) for r in zk[aid]})} 个 id；'
          f'原池 {len(mids)} 条）')
    print(f'  剔除·总库无上下文 {len(no_ctx)} 条：{no_ctx}')
    print(f'  剔除·引文不在200字上下文内(<{a.min_cov}) {len(low_cov)} 条：{low_cov}')
    for lv in 'SML':
        print(f'  {lv} 档：{len(tiers[lv])} 条，{nchar[lv]} 汉字')
    print(f'三档条数一致：{"OK" if same else "失败"}    字数 S≤M≤L：{"OK" if order else "失败"}')
    if not same or not order:
        raise SystemExit('三档结构不合格，未写盘')
    if a.check:
        print('（--check，未写盘）')
        return

    for lv in 'SML':
        (poc / f'pool_text_{lv}.txt').write_text('\n'.join(tiers[lv]), encoding='utf-8')
    (rec_dir / f'档位说明_{aid}.json').write_text(json.dumps({
        'rule': '同一批引文，扩展不同长度上下文（S=引用片段 / M=史料原文200字 / L=史料原文400字）',
        'source': '史料总库.xlsx#史料库',
        'entries': n,
        'char_counts': nchar,
        'same_citation_set': same,
        'min_coverage': a.min_cov,
        'dropped_no_context': no_ctx,
        'dropped_low_coverage': [m for m, _ in low_cov],
    }, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'已写入 pool_text_{{S,M,L}}.txt 与 档位说明_{aid}.json')


if __name__ == '__main__':
    main()
