# -*- coding: utf-8 -*-
"""批量实验编排：抽取 → 绑定修复 → 校验 → 对齐 → 频次聚合，按 run 循环，失败即停。

用法：
  python 批量实验.py --paper A05
  python 批量实验.py --paper A05 --runs Q_run_1_S,A_run_1_S --no-pause
  python 批量实验.py --paper P01 --skip-extract --skip-align   # 只跑本地步骤

步骤说明：
  1. 抽取论证树（需 API）：run_论证树.json 不存在时调用 _论证树一次性抽取.py
  2. source_binding 修复 A 全量绑定与 B 并集
  3. 校验结构一致性
  4. 【人工确认】source_binding 产出的 evidence_candidates 需人工审阅后才计入 sources；
     默认在此暂停，回车继续；--no-pause 跳过（仅当你已确认过）
  5. 整树 LLM 对齐（需 API）：整树_LLM对齐.json 未完成时调用 _整树LLM对齐.py
  6. 频次聚合：读 频次聚合.json 出 ACI/SCI

产物：各 run 目录下的 run_论证树.json / 整树_LLM对齐.json / 频次聚合.json；
      最后汇总到 实验数据/<paper>/03_实验输出/Q_A_实验/_批量汇总.csv
"""
import argparse, csv, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "脚本"
DATA = ROOT / "实验数据"


def run_step(cmd, label, run_name):
    """执行一步，非零退出即抛异常中断整个批量。"""
    print(f"\n{'='*60}\n[{run_name}] {label}\n{'='*60}", flush=True)
    print(">>", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        raise SystemExit(f"[{run_name}] {label} 失败（退出码 {r.returncode}），批量中断。"
                         f"已完成的 run 不受影响，修复后重跑本脚本会跳过已完成步骤。")


def discover_runs(base):
    """自动发现 Q_run_* / A_run_* 目录（排除 A_human_baseline）。"""
    runs = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d.name.startswith("Q_run_") or d.name.startswith("A_run_")):
            runs.append(d.name)
    return runs


def step_done(run_dir, step):
    """判断某步是否已完成（可跳过）。"""
    if step == "extract":
        return (run_dir / "run_论证树.json").exists()
    if step == "align":
        f = run_dir / "整树_LLM对齐.json"
        if not f.exists():
            return False
        try:
            return json.loads(f.read_text(encoding="utf-8")).get("complete") is True
        except Exception:
            return False
    if step == "aggregate":
        return (run_dir / "频次聚合.json").exists()
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", required=True, help="论文编号，如 A05")
    ap.add_argument("--runs", default=None, help="逗号分隔 run 名；默认自动发现 Q_run_*/A_run_*")
    ap.add_argument("--no-pause", action="store_true", help="source_binding 后不暂停等人工确认")
    ap.add_argument("--skip-extract", action="store_true", help="跳过抽取（run_论证树.json 已存在）")
    ap.add_argument("--skip-align", action="store_true", help="跳过对齐（只跑本地步骤）")
    args = ap.parse_args()

    paper_dir = DATA / args.paper
    if not paper_dir.exists():
        sys.exit(f"论文目录不存在：{paper_dir}")
    base = paper_dir / "03_实验输出" / "Q_A_实验"
    if not base.exists():
        sys.exit(f"Q_A_实验 目录不存在：{base}")

    runs = [r.strip() for r in args.runs.split(",")] if args.runs else discover_runs(base)
    if not runs:
        sys.exit("未发现任何 run 目录。")
    print(f"论文 {args.paper}，共 {len(runs)} 个 run：{runs}", flush=True)

    py = sys.executable
    for run_name in runs:
        run_dir = base / run_name
        if not run_dir.exists():
            print(f"[跳过] {run_name} 目录不存在", flush=True)
            continue

        # 1. 抽取
        if not args.skip_extract and not step_done(run_dir, "extract"):
            run_step([py, str(SCRIPTS / "_论证树一次性抽取.py"), run_name, str(paper_dir)],
                     "抽取论证树", run_name)
        else:
            print(f"[{run_name}] 抽取：已完成（跳过）", flush=True)

        # 2. source_binding
        run_step([py, str(SCRIPTS / "source_binding.py"), str(run_dir)],
                 "source_binding 修复", run_name)

        # 3. 校验
        run_step([py, str(SCRIPTS / "校验.py"), str(run_dir)],
                 "结构校验", run_name)

        # 4. 人工确认
        if not args.no_pause:
            print(f"\n[{run_name}] 请人工确认 evidence_candidates 后按回车继续（Ctrl+C 中断）", flush=True)
            try:
                input()
            except KeyboardInterrupt:
                sys.exit("\n用户中断。已完成的 run 不受影响。")

        # 5. 对齐
        if not args.skip_align and not step_done(run_dir, "align"):
            run_step([py, str(SCRIPTS / "_整树LLM对齐.py"), "--paper", args.paper, "--runs", run_name],
                     "整树 LLM 对齐", run_name)
        else:
            print(f"[{run_name}] 对齐：已完成或跳过", flush=True)

        # 6. 频次聚合
        run_step([py, str(SCRIPTS / "频次聚合.py"), str(run_dir)],
                 "频次聚合", run_name)

    # 汇总
    summary_path = base / "_批量汇总.csv"
    rows = []
    for run_name in runs:
        run_dir = base / run_name
        f = run_dir / "频次聚合.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        main = d["main"]
        rows.append({
            "run": run_name,
            "ACI": main["overall"]["ACI"],
            "ACI_B": main["by_level"]["B"]["ACI"],
            "ACI_C": main["by_level"]["C"]["ACI"],
            "SCI": main["SCI"],
            "evidence_coverage": main["evidence_edges"]["coverage"],
            "claim_coverage": main["claim_edges"]["coverage"],
            "precision": main["overall"]["model_precision_binary"],
            "n_human_BC": main["overall"]["n_human_nodes"],
            "n_model_BC": main["overall"]["n_model_nodes"],
            "rounds": d["n_rounds"],
        })
    if rows:
        with open(summary_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\n汇总已写入：{summary_path}（{len(rows)} 个 run）", flush=True)
    else:
        print("\n无可用 频次聚合.json，未生成汇总。", flush=True)


if __name__ == "__main__":
    main()
