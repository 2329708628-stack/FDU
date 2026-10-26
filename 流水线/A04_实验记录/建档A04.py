#!/usr/bin/env python3
"""A04 史料池三档：调用共享脚本「建档三档.py」从【史料总库.xlsx】生成。

三档定义（论文v3 line 33）：同一批引文，各扩展不同长度的上下文。
  S 档 = 引用片段（核心引文）
  M 档 = 史料原文_200字（200 汉字上下文）
  L 档 = 史料原文_400字（400 汉字上下文，前 200 字即 M 档）

数据源：工作区根 史料总库.xlsx → 工作表「史料库」
  列：引用片段 / 史料原文_200字 / 史料原文_400字

质量门：引用片段在 200 字上下文中覆盖率 ≥ 0.7 才入池。

用法：
  python3 建档A04.py
  python3 建档A04.py --check
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / '.trae' / 'skills' / 'songshi-experiment-pipeline' / 'scripts' / '建档三档.py'

if not SHARED.exists():
    raise SystemExit(f'缺少共享建档脚本：{SHARED}')

cmd = [sys.executable, str(SHARED), '--id', 'A04'] + sys.argv[1:]
raise SystemExit(subprocess.call(cmd))
