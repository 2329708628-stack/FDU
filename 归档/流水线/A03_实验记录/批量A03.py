#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A03 批量：对全部 30 个模型 run 执行 抽取→绑定→校验→对齐(10轮)→频次聚合。
可重复运行（已完成者自动跳过 / 对齐续跑）。
用法：python 批量A03.py [--from-assemble]
  --from-assemble  先运行装配和统一名册
"""
import os, subprocess, sys, json, re, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPE = ROOT / '提取与生成管线'
LAB = ROOT / '实验数据' / 'A03' / '03_实验输出' / 'Q_A_实验'
PY = sys.executable

ENV = dict(os.environ)
if not ENV.get('DEEPSEEK_API_KEY'):
    raise SystemExit('请先通过环境变量设置 DEEPSEEK_API_KEY；共享包不包含密钥。')


def sh(cmd, cwd=ROOT, timeout=1800):
    r = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def run_assembly():
    print('=== 步骤 1: 装配 ===')
    rc, out = sh([PY, str(A03_DIR / '装配A03.py')])
    print(out)
    if rc != 0:
        print('装配失败！')
        sys.exit(1)

    print('\n=== 步骤 2: 统一名册 ===')
    rc, out = sh([PY, str(A03_DIR / '统一名册A03.py')])
    print(out)
    if rc != 0:
        print('统一名册失败！')
        sys.exit(1)


def run_pipeline(only=None):
    runs = sorted(d.name for d in LAB.iterdir()
                  if d.is_dir() and re.match(r'^[QA][SML]_R\d$', d.name)
                  and (only is None or d.name in only))
    print(f'\n=== 管线处理 {len(runs)} 个 run ===')

    log = []
    for run in runs:
        rd = LAB / run
        steps = []

        # 1) 抽取
        if not (rd / 'run_论证树.json').exists():
            rc, out = sh([PY, str(PIPE / '_论证树一次性抽取.py'), run,
                          str(ROOT / '实验数据' / 'A03')])
            steps.append(('抽取', rc, out.splitlines()[-1] if out else ''))
            if rc != 0:
                log.append((run, steps)); print(run, '抽取失败', out[:200]); continue
        else:
            steps.append(('抽取', 0, '已存在'))

        # 2) 绑定
        rc, out = sh([PY, str(PIPE / 'source_binding.py'), str(rd)])
        steps.append(('绑定', rc, out.splitlines()[-1] if out else ''))
        if rc != 0:
            log.append((run, steps)); print(run, '绑定失败', out[:200]); continue

        # 3) 校验
        rc, out = sh([PY, str(PIPE / '校验.py'), str(rd)])
        steps.append(('校验', rc, out.splitlines()[-1] if out else ''))
        if rc != 0:
            log.append((run, steps)); print(run, '校验失败', out[:200]); continue

        # 4) 对齐（10 轮）
        rc, out = sh([PY, str(PIPE / '_整树LLM对齐.py'),
                      '--paper', 'A03', '--human-run', 'A_human_baseline', '--run', run])
        steps.append(('对齐', rc, out.splitlines()[-1] if out else ''))
        if rc != 0:
            log.append((run, steps)); print(run, '对齐失败', out[:200]); continue

        # 5) 聚合（带 A-7 top-2 合并）
        rc, out = sh([PY, str(PIPE / '频次聚合.py'), str(rd)])
        steps.append(('聚合', rc, out.splitlines()[0] if out else ''))
        if rc != 0:
            log.append((run, steps)); print(run, '聚合失败', out[:200]); continue

        # A-7 top-2 合并后处理
        try:
            a7 = Path(str(rd)) / 'apply_a7_merge.py'
            if a7.exists():
                rc2, out2 = sh([PY, str(a7)])
                steps.append(('A7', rc2, '已合并' if rc2 == 0 else out2[:100]))
        except Exception:
            pass

        log.append((run, steps))
        print(f'[{run}] OK  ' + ' | '.join(f'{s}:{r}' for s, r, _ in steps))

    print('\n=== 管线汇总 ===')
    ok = sum(1 for _, s in log if all(r == 0 for _, r, _ in s))
    print(f'成功 {ok}/{len(runs)}')
    for run, s in log:
        if not all(r == 0 for _, r, _ in s):
            print('  [失败]', run, s)

    log_path = LAB.parent.parent / 'A03_批量_日志.json'
    previous = {}
    if log_path.exists():
        previous = dict(json.loads(log_path.read_text(encoding='utf-8')).get('runs', []))
    previous.update(log)
    log_path.write_text(
        json.dumps({'runs': [[r, s] for r, s in sorted(previous.items())]},
                   ensure_ascii=False, indent=1), encoding='utf-8')
    if ok != len(runs):
        raise SystemExit(1)


A03_DIR = ROOT / 'A03_实验记录'
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--from-assemble', action='store_true',
                    help='先运行装配和统一名册')
    ap.add_argument('--only', help='只处理逗号分隔的指定 run')
    args = ap.parse_args()
    if args.from_assemble:
        run_assembly()
    run_pipeline(set(args.only.split(',')) if args.only else None)
