#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""以 A03 的已修正流程为模板建立新实验。

用法：
  python3 新增实验.py --id B01 --topic "主题" --human-src "B组交付包/B01/第二轮复现"
  python3 新增实验.py --id B01 --topic "主题" --dry-run

做的事：
 1. 建 <ID>_实验记录/{生成轮次,史料池输入,<ID>_最终汇总报告}
 2. 复制模板实验（默认 A03）的八个脚本，替换实验编号
 3. 在生成脚本里加一道"条件文本未填"的启动检查
"""
import argparse
import ast
import json
import re
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[4]   # .trae/skills/.../scripts -> workspace
TEMPLATES = ['建档', '生成', '装配', '统一名册', '批量', 'A7合并', '汇总', 'build_report']
PLACEHOLDER = '【待填'

def tree_nodes(tree_path):
    """返回（A+B+C 总数, sources 非空节点数）。"""
    t = json.loads(Path(tree_path).read_text(encoding='utf-8'))
    et = t['encoding_table']
    raw = scored = 0
    for lv in ('A_level', 'B_level', 'C_level'):
        for n in et.get(lv, []):
            raw += 1
            if n.get('sources'):
                scored += 1
    return raw, scored


def script_name(stem, exp_id):
    return f'{stem}_{exp_id}.py' if stem == 'build_report' else f'{stem}{exp_id}.py'


def replace_once(text, old, new, where):
    if old not in text:
        raise SystemExit(f'模板结构已变，未找到 {where}：{old[:60]}')
    return text.replace(old, new, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--id', required=True, help='新实验编号，如 B01')
    ap.add_argument('--topic', required=True, help='实验主题（写入提示词存档与报告标题）')
    ap.add_argument('--human-src', default=None,
                    help='人类基准目录（含 run_论证树.json 的 第二轮复现 目录）')
    ap.add_argument('--template', default='A03', help='模板实验编号，默认 A03（已修正三档设计）')
    ap.add_argument('--out-root', default=str(WORKSPACE), help='输出根目录')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    new_id, tmpl = a.id.strip(), a.template.strip()
    if not re.fullmatch(r'[A-Z]\d{2}', new_id):
        raise SystemExit(f'实验编号格式应为字母+两位数字，收到 {new_id!r}')

    root = Path(a.out_root)
    tdir = root / f'{tmpl}_实验记录'
    if not tdir.is_dir():
        raise SystemExit(f'模板目录不存在：{tdir}')
    dest = root / f'{new_id}_实验记录'
    if dest.exists():
        raise SystemExit(f'目标已存在，未覆盖：{dest}')

    # ---- 节点数 ----
    raw = scored = None
    if a.human_src:
        tp = Path(a.human_src) / 'run_论证树.json'
        if not tp.exists():
            raise SystemExit(f'找不到人类树：{tp}')
        raw, scored = tree_nodes(tp)

    print(f'新增实验 {new_id}（模板 {tmpl}，主题 {a.topic}）')
    if raw is not None:
        print(f'  人类树 A+B+C 共 {raw} 节点，其中 sources 非空 {scored} 个')
    else:
        print('  未提供 --human-src；生成前必须指定并核验人类基准')

    plan = []
    for stem in TEMPLATES:
        src = tdir / script_name(stem, tmpl)
        if not src.exists():
            raise SystemExit(f'模板脚本缺失：{src}')
        plan.append((src, dest / script_name(stem, new_id)))
    plan.append((tdir / '提示词.md', dest / '提示词.md'))

    print('\n将写入：')
    for s, d in plan:
        print(f'  {s.name} -> {d.relative_to(root)}')
    for sub in ('生成轮次', '史料池输入', f'{new_id}_最终汇总报告'):
        print(f'  mkdir {new_id}_实验记录/{sub}/')

    if a.dry_run:
        print('\n（dry-run，未写盘）')
        return

    # ---- 建目录 ----
    for sub in ('生成轮次', '史料池输入', f'{new_id}_最终汇总报告'):
        (dest / sub).mkdir(parents=True)
    prompt_doc = (tdir / '提示词.md').read_text(encoding='utf-8').replace(tmpl, new_id)
    prompt_doc = re.sub(r'(?m)^(## 主题\n)[^\n]+',
                        lambda m: m.group(1) + a.topic, prompt_doc, count=1)
    prompt_doc = re.sub(r'(?m)^(- \*\*Q（中性研究问题）\*\*：).*$',
                        r'\1【待填：中性研究问题】', prompt_doc, count=1)
    prompt_doc = re.sub(r'(?m)^(- \*\*A（给定核心观点）\*\*：).*$',
                        r'\1【待填：给定核心观点】', prompt_doc, count=1)
    (dest / '提示词.md').write_text(prompt_doc, encoding='utf-8')

    # ---- 模型脚本：ID 替换 + 条件文本占位 ----
    for src, dst in plan:
        if src.suffix != '.py':
            continue
        t = src.read_text(encoding='utf-8').replace(tmpl, new_id)
        if src.name.startswith('生成'):
            for key in ('Q_TEXT', 'A_TEXT'):
                m = re.search(rf"^{key} = \(.*?\)\n", t, re.S | re.M)
                if not m:
                    m = re.search(rf"^{key} = '.*?'\n", t, re.M)
                if m:
                    t = t[:m.start()] + f"{key} = '{PLACEHOLDER}：{key} 条件文本】'\n" + t[m.end():]
            # 启动检查：条件文本仍是占位符就不让跑
            guard = (f"    if {PLACEHOLDER!r} in Q_TEXT or {PLACEHOLDER!r} in A_TEXT:\n"
                     f"        raise SystemExit('请先填写 Q_TEXT / A_TEXT 条件文本（见 {new_id}_实验记录/提示词.md）')\n")
            t = replace_once(t, '    if not API_KEY:', guard + '    if not API_KEY:', '生成脚本的 API_KEY 检查')
            if 'def load_pool(tier):' not in t:
                raise SystemExit('模板结构已变，缺少按 S/M/L 档读取史料池的函数')
        if src.name.startswith('装配') and a.human_src:
            m = re.search(r"^HUMAN_SRC = .*$", t, re.M)
            if m:
                t = t[:m.start()] + f"HUMAN_SRC = ROOT / '{a.human_src}'" + t[m.end():]
        dst.write_text(t, encoding='utf-8')
        ast.parse(t)  # 语法自检

    # ---- build_report：新版从本篇汇总动态生成，无历史 NODES 常量 ----
    rf = dest / script_name('build_report', new_id)
    t = rf.read_text(encoding='utf-8')
    ast.parse(t)
    print('\n报告脚本：使用本篇汇总动态生成，无需改写历史实验列表')

    print('\n下一步：')
    print(f'  1. 填 {new_id}_实验记录/提示词.md 与 生成{new_id}.py 的 Q_TEXT / A_TEXT')
    print(f'  2. 生成 pool_text_{{S,M,L}}.txt：先落 pool_text_all.txt，再跑 '
          f'建档{new_id}.py（= 建档三档.py --id {new_id}，从 史料总库.xlsx 取三档）')
    print(f'  3. source 提取与生成管线/deepseek_env.sh 后跑 生成{new_id}.py')
    print('  详细命令见 references/执行手册.md')


if __name__ == '__main__':
    main()
