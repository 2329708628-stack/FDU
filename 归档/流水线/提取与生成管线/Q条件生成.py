# -*- coding: utf-8 -*-
"""Q/A 实验：Q 条件——基于史料（S）由大模型生成论文。

Q/A 实验条件的唯一差异为前置指令：
  Q 组：基于以下史料，分析 X 与 Y 的关系
  A 组：论证以下观点，使用给定史料支撑
本脚本为 Q 组：把 source_pool.json 的全部 passages 喂给模型，
让其围绕指定问题（默认 A01 的"北宋湖北茶叶经济贸易的情况、原因和影响"）生成论文。

用法：
  python 脚本/步骤8_Q_A_实验/Q条件生成.py [论文目录(默认 A01_湖北茶叶经济)] [run号(默认 1)] [问题(默认见 DEFAULT_Q)] [tier(默认 AUTO)]
  tier = S/M/L（读 source_pool_{tier}.json）；AUTO=读 source_pool.json（全量）
产物写入 <论文目录>/03_实验输出/Q_A_实验/Q_run_<n>[_<tier>]/(tier=AUTO 时目录不带后缀)：
  输入_prompt.txt    完整 prompt
  生成_论文.md       模型输出
  meta.json          模型/温度/时间/token 等
"""
import json, os, sys, time, datetime
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
# .venv 是空的，但 .pylibs 提供了 requests；统一加进 sys.path
_pylibs = str(LAB / ".pylibs")
if _pylibs not in sys.path:
    sys.path.insert(0, _pylibs)


from 提示词模板 import render_prompt

DRY_RUN = '--dry-run' in sys.argv
if DRY_RUN:sys.argv.remove('--dry-run')

API_FILE = LAB / "API.txt"

DEFAULT_Q = "北宋时期湖北地区茶叶经济贸易的情况、原因和影响"
MODEL = "deepseek-chat"
TEMPERATURE = 0.7
MAX_TOKENS = 32768


def read_api():
    key = os.environ.get('DEEPSEEK_API_KEY')
    if not key:raise RuntimeError('Set DEEPSEEK_API_KEY; no secret is included in this package')
    return key, os.environ.get('DEEPSEEK_BASE_URL','https://api.deepseek.com')


def build_prompt(S_block, question, tier="S", role="宋代经济史学者"):
    """Q 条件任务行：给定研究问题，让模型自下而上分析；正文由共享模板提供，与 A 组逐字相同。"""
    q = question.rstrip("？?。")
    task_line = f"你是一位{role}，请基于以下史料池，分析{q}。"
    return render_prompt(task_line, S_block, tier)


def build_S_block(source_pool):
    """把 source_pool.json 的 passages 平铺成编号文本块。"""
    lines = []
    for src in source_pool["sources"]:
        title = src.get("title", "")
        dynasty = src.get("dynasty", "")
        for p in src["passages"]:
            pid = p["passage_id"]
            mid = p.get("original_id", "")
            text = p.get("text", "").strip()
            cite = p.get("source_full", "")
            vol = p.get("volume", "")
            vol_part = f" 卷{vol}" if vol else ""
            head = f"[{pid}]" + (f"（原 {mid}）" if mid else "")
            lines.append(f"{head} 《{title}》{dynasty}{vol_part}")
            lines.append(f"原文：{text}")
            lines.append(f"出处：{cite}")
            lines.append("")
    return "\n".join(lines)


def main():
    if len(sys.argv)<5:raise SystemExit('用法：Q条件生成.py 论文目录 run号 "研究问题" S/M/L [角色] [--dry-run]')
    paper_dir = Path(sys.argv[1])
    run_no = sys.argv[2] if len(sys.argv) > 2 else "1"
    question = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_Q
    tier = (sys.argv[4] if len(sys.argv) > 4 else "AUTO").upper()
    if tier not in {"S","M","L"}:raise ValueError("必须明确指定 S/M/L")
    role = sys.argv[5] if len(sys.argv) > 5 else "宋代经济史学者"

    if tier == "AUTO":
        sp_name = "source_pool.json"
        out_dir = paper_dir / "03_实验输出" / "Q_A_实验" / f"Q_run_{run_no}"
    else:
        sp_name = f"source_pool_{tier}.json"
        out_dir = paper_dir / "03_实验输出" / "Q_A_实验" / f"Q_run_{run_no}_{tier}"
    sp_path = paper_dir / "02_史料池" / sp_name
    if not sp_path.exists():
        sys.exit(f"找不到史料池: {sp_path}")
    source_pool = json.loads(sp_path.read_text(encoding="utf-8"))
    S_block = build_S_block(source_pool)
    prompt = build_prompt(S_block, question, tier, role)
    if (out_dir/'生成_论文.md').exists() or (out_dir/'输入_prompt.txt').exists():
        raise FileExistsError('该 run 已有产物，请使用新 run 号；dry-run 后请先移出提示词再正式运行')
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "输入_prompt.txt").write_text(prompt, encoding="utf-8")

    if DRY_RUN:
        print('Prompt saved; dry run, no API call')
        return
    if source_pool.get('metadata',{}).get('historical_input') is False and os.environ.get('ACK_RECONSTRUCTED_INPUTS')!='1':
        raise RuntimeError('Reconstructed inputs require ACK_RECONSTRUCTED_INPUTS=1; this is a new experiment')
    import requests
    api_key, base_url = read_api()
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "stream": True,
        "messages": [{"role": "user", "content": prompt}],
    }

    print(f"模型={MODEL}  温度={TEMPERATURE}  最大输出={MAX_TOKENS}")
    print(f"prompt 字符数={len(prompt)}  史料源数={len(source_pool['sources'])}  passages={source_pool['statistics']['total_passages']}")
    print(f"输出目录={out_dir}")
    print(f"API={url}")
    print("开始流式生成...")

    t0 = time.time()
    chunks = []
    first_token_t = None
    finish_reason = None
    usage = None
    with requests.post(url, headers=headers, json=payload, stream=True, timeout=600) as r:
        if r.status_code != 200:
            sys.exit(f"HTTP {r.status_code}: {r.text[:500]}")
        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue
            if not raw.startswith("data:"):
                continue
            data = raw[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            if usage is None and obj.get("usage"):
                usage = obj["usage"]
            try:
                choice = obj["choices"][0]
            except (KeyError, IndexError):
                continue
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]
            piece = choice.get("delta", {}).get("content", "") or ""
            if piece:
                if first_token_t is None:
                    first_token_t = time.time()
                chunks.append(piece)
                sys.stdout.write(piece)
                sys.stdout.flush()
    elapsed = time.time() - t0
    ttft = (first_token_t - t0) if first_token_t else 0.0
    full = "".join(chunks)
    print()
    print(f"\n[完成] 用时={elapsed:.1f}s  首token={ttft:.2f}s  输出字符={len(full)}  finish={finish_reason}")

    (out_dir / "生成_论文.md").write_text(full, encoding="utf-8")

    meta = {
        "complete": finish_reason == "stop",
        "experiment": "Q_A",
        "condition": "Q",
        "tier": tier,
        "paper_id": paper_dir.name.split("_")[0],
        "run_no": run_no,
        "model": MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "question": question,
        "prompt_chars": len(prompt),
        "source_pool": {
            "total_sources": source_pool["statistics"]["total_sources"],
            "total_passages": source_pool["statistics"]["total_passages"],
            "S_block_chars": len(S_block),
        },
        "output_chars": len(full),
        "elapsed_sec": round(elapsed, 2),
        "time_to_first_token_sec": round(ttft, 2),
        "finish_reason": finish_reason,
        "usage": usage,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if finish_reason != "stop":raise RuntimeError("输出未完整结束，已保存但不得进入正式实验")
    print(f"meta 已保存: {out_dir / 'meta.json'}")


if __name__ == "__main__":
    main()
