# -*- coding: utf-8 -*-
"""S/M/L 三档史料池派生：根据 source_pool.json 生成三种上下文规模版本。

档位定义（以每条史料单元的 text 为核心句）：
  S（Small）: 原文核心句——仅 text 本身，不加前后文。
  M（Medium）: 核心句 ±100 字符。在 context 内定位 text，向两侧各扩展 100 字符。
  L（Large） : 核心句 ±200 字符。在 context 内定位 text，向两侧各扩展 200 字符。

扩展规则：
  1. 在 passage['context'] 中定位 text 子串位置；能定位 → 向两侧扩展 target 字符（含 text 本身）。
  2. context 为空或 text 无法在 context 定位 → 该条退化为 S（text 本身），并计入退化统计。
  3. 扩展若超出 context 边界，截取现有可得部分。
产物写入 <论文目录>/02_史料池/ 下三个文件：
  source_pool_S.json / source_pool_M.json / source_pool_L.json
三者除 passage 的 text 字段外结构相同（保留 source_full/volume/context 备查）。

用法：python 派生SML史料池.py <论文目录>
"""
import json, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

LEVELS = {"S": 0, "M": 100, "L": 200}


def expand(text, context, n):
    """在 context 中定位 text，向两侧各扩展 n 字符。返回扩展后的窗口。"""
    if not context:
        return text, False
    pos = context.find(text)
    if pos >= 0 and context.count(text) != 1:
        return text, False
    if pos < 0:
        # 尝试去空白后匹配
        t = text.strip()
        c = context.strip()
        pos = c.find(t)
        if pos < 0:
            return text, False
        if c.count(t) != 1:
            return text, False
        context = c
        text = t
    lo = max(0, pos - n)
    hi = min(len(context), pos + len(text) + n)
    return context[lo:hi], True


def derive(src_pool, level):
    n = LEVELS[level]
    degraded = []
    ns_srcs = []
    for s in src_pool["sources"]:
        ps = []
        for p in s["passages"]:
            text = p.get("text", "").strip()
            ctx = p.get("context", "") or ""
            if n > 0:
                new_text, ok = expand(text, ctx, n)
                if not ok:
                    degraded.append(p["passage_id"])
            else:
                new_text = text
            ps.append({**p, "text": new_text})
        ns_srcs.append({**s, "passages": ps})
    out = {
        "metadata": {
            **src_pool.get("metadata", {}),
            "version": "2.1",
            "tier": level,
            "note": f"上下文规模档位 {level}：{('原文核心句' if n == 0 else f'核心句±{n}字符')}",
        },
        "statistics": {
            "total_sources": len(ns_srcs),
            "total_passages": sum(len(s["passages"]) for s in ns_srcs),
            "degraded_to_text": len(degraded),
        },
        "sources": ns_srcs,
    }
    return out, degraded


def main():
    paper_dir = Path(sys.argv[1])
    sp_path = paper_dir / "02_史料池" / "source_pool.json"
    if not sp_path.exists():
        sys.exit(f"找不到 source_pool.json: {sp_path}")
    pool = json.loads(sp_path.read_text(encoding="utf-8"))

    for level in ("S", "M", "L"):
        out, degraded = derive(pool, level)
        path = paper_dir / "02_史料池" / f"source_pool_{level}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{level}] 源={out['statistics']['total_sources']} "
              f"条={out['statistics']['total_passages']} "
              f"退化到原文={len(degraded)}  {path}")
        if degraded:
            print("    退化 passage:", degraded)


if __name__ == "__main__":
    main()