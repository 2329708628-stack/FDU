# -*- coding: utf-8 -*-
"""论证树一次性抽取：整篇一次调用 LLM，自下而上提取论证树（每个正文自然段一个 C 节点）。

规格（2026-10-25 修订）：**每个正文自然段必须产出恰好 1 个 C 节点**，不得跳过、不得合并。
纯史料引文段/数据段同样产出 C，并标记 quote_only=true，供下游按 --drop-quote-only 剔除。

替代 v3.2 五调用抽取 + 逐段论点压缩：一篇论文只调一次 API（deepseek-chat, temp=0）。

层级约定（与 v3.2 一致，供下游 _试点_新管线.py / _批量判定对照.py 复用）：
  A：全文唯一结论节点（结语段归纳），depth=1
  B：章节节点（一、二、三…），depth=2（由 derive_skeleton 确定性推导，id 固定）
  C：段落主张（每个正文自然段恰好 1 条；纯史料引文段也产出 C 并标记 quote_only）

用法：
  python _论证树一次性抽取.py <run 目录名> [论文目录(默认 A05)] [--overwrite]
    <run 目录> = 数据集/数据清洗后论文/<论文>/03_实验输出/Q_A_实验/<run 目录名>
    默认写出 <run>/run_论证树.json（不覆盖旧 run.json）；加 --overwrite 才写 run.json
"""
import json, os, sys, time, datetime, re, shutil
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / ".pylibs"))


sys.path.insert(0, str(Path(__file__).parent))
from 公共库 import load_paper, derive_skeleton, m_key, c_id_for, descendants, union_sources, para_in_span

API_FILE = LAB / "API.txt"

# ---- 冻结配置（2026-10-25）：全部 7 篇人类基线树共用，不得逐篇调整 ----
# 原 deepseek-chat 端点对本项目密钥不可用，统一走 paratera 网关。
FROZEN = {
    "model": "DeepSeek-V4-Pro-0813",
    "base_url": "https://llmapi.paratera.com/v1",
    "temperature": 0.0,
    "max_tokens": 8192,
    "spec": "每个正文自然段恰好 1 个 C 节点；A=全文结论，B=章节，C=段落主张",
    "clean_source": "原文_clean_自然段.json（full.md 自然段级重洗）",
}
MODEL = os.environ.get("DEEPSEEK_MODEL", FROZEN["model"])
TEMPERATURE = 0.0
MAX_TOKENS = 8192
DROP_QUOTE_ONLY = False  # --drop-quote-only：剔除纯史料引文段节点，回到旧口径


def read_api():
    key = os.environ.get('DEEPSEEK_API_KEY')
    if not key:raise RuntimeError('Set DEEPSEEK_API_KEY; no secret is included in this package')
    return key, os.environ.get('DEEPSEEK_BASE_URL', FROZEN["base_url"])


def chat(prompt, max_retries=5):
    import requests
    key, base = read_api()
    url = base.rstrip("/") + "/chat/completions"
    payload = {
        "model": MODEL, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
    }
    last = None
    for i in range(max_retries + 1):
        try:
            r = requests.post(url, headers={"Authorization": f"Bearer {key}"},
                              json=payload, timeout=900)
        except requests.exceptions.RequestException as e:
            last = e
            time.sleep(10 * (i + 1))
            continue
        if r.status_code == 429:
            time.sleep(30 * (i + 1))
            continue
        if r.status_code != 200:
            last = f"HTTP {r.status_code}: {r.text[:300]}"
            time.sleep(10 * (i + 1))
            continue
        j = r.json()
        txt = j["choices"][0]["message"]["content"]
        return txt, None, j.get("usage") or {}
    return None, str(last), {}


def clean_json(raw):
    s = (raw or "").strip()
    i = s.find("{")
    j = s.rfind("}")
    if i >= 0 and j > i:
        return s[i:j + 1]
    return s


def build_prompt(paras, A_defs, B_defs, front_matter, pidx):
    # 段落分组：按最深层 B 归属，把章节标题与正文段组织成树
    # 引言段（front_matter，首个章节标题之前的正文）不属论证主体，不参与抽取
    text_paras = [p for p in paras if p.get("type") == "text" and p["id"] not in front_matter]

    b_lines = []
    for b in B_defs:
        b_lines.append(f"{b['id']} [锚点：{b['title_label']}] depth={b['depth']} parent={b.get('parent')}")

    a_lines = []
    for a in A_defs:
        a_lines.append(f"{a['id']} [锚点：{a['title_label']}] span={a.get('span')}")

    p_lines = []
    for p in text_paras:
        pm = ",".join(p.get("material_refs", []))
        p_lines.append(f"{p['id']}（refs:{pm or '无'}）: {p['text']}")

    return f"""你是历史学论文论证结构形式化编码器。请对全文一次性提取论证树：自下而上归纳，只保留「论点」，剔除一切「论据」。

【核心原则】
1. 小标题只作结构锚点，用于固定层级，不直接当论点。
2. 每个结构单元（各节、各正文段）都要另行归纳一句「该单元论点」。
3. 归纳路径自下而上：先概括每个正文段的核心论点(C)；将同一节内各段论点归纳为该节论点(B)；将各节论点归纳为全文核心结论(A/总论点)。
4. 每个正文自然段都要产出节点：纯论据/史料/律文/数据/过渡段也要单独成节点，不并入上级论点。

【论据剔除——绝对禁止写进论点】
例子、案例、事件、数字、价格、数量、统计、引文、诗文、书名、篇名、人物、地名、官职、朝代年号、法律条文原文，以及"如/例如/据统计/记载/XX云/XX曰"引导的内容，一律剔除。
特别强调：
- 法律条文的照抄或复述（如"笞三十""杖一百""立市券""价定立券""听悔"等）是史料(M)，不是论点，禁止写进 C。
- 价格数字（如"每匹二十贯""一头5贯""每斤百三十文""十二贯""三点九贯"）是史料(M)，不是论点，禁止写进 C。
- 只有作者自己的评价判断（如"…有利于规范市场""…反映官府管理成熟""…价格浮动较大""…推动贸易繁荣"）才是论点。

【层级与编号约束】
- C = 段落主张：**每个正文自然段必须恰好产出 1 条，一条不多、一条不少**。禁止跳过任何一段，禁止把多段合并成一条。
- 纯史料引文段/律文段/数据段/过渡段也必须产出 1 条 C：text 写该段实际陈述的内容要点（照录史料要旨即可），并在该条上标 "quote_only": true；其余各段标 "quote_only": false。
- 除原文没有论点可归纳的情况外，不用"该段无论点"之类的说法替代；有内容就归纳，归纳不出来也照陈述内容写。
- B = 章节论点：对每个给出的 B 节点归纳恰好 1 条，id 必须与输入 B 节点 id 逐字一致。
- A = 全文核心结论：由结语段（及全文）归纳，id = A1。

【写法要求】
- 论点须是可独立判断的陈述句，20~60 字，主谓宾完整。
- 直接写论点，不用"作者认为""本文指出"开头；不照抄小标题；不解释、不评价、不添加原文没有的观点。
- C 的 text 只保留作者判断，删掉该段内的数字、价格、律文、引文、例证。

【输入：层级锚点】
A 节点：
{chr(10).join(a_lines) if a_lines else '（无）'}

B 节点：
{chr(10).join(b_lines) if b_lines else '（无）'}

已排除的引言段 front_matter（首个章节标题之前的正文，不属论证主体，请勿为其产出 C）：
{", ".join(front_matter) if front_matter else "（无）"}

【输入：正文段】
{chr(10).join(p_lines)}

【输出 JSON（只输出一个 JSON 对象，不要 markdown 代码块、不要说明文字）】
{{
  "A_claim": "全文核心结论",
  "B_claims": [{{"id": "B1", "claim": "..."}}, ...],
  "C_claims": [{{"anchor": "P6", "text": "...", "quote_only": false}}, ...]
}}
规则：
1. B_claims 覆盖输入的全部 B 节点（id 原样）。
2. **C_claims 必须覆盖全部正文自然段，条数等于正文自然段条数**（一个 anchor 一条，不可重复、不可遗漏）；
   每条须带 quote_only 标记。输出前请自数一遍条数，与输入正文段数逐一比对。
"""


def export_views(run, run_dir):
    """导出两种人工可读视图（均为 run 的投影，JSON 仍是唯一权威产物）：
      ① 论证树本体：A/B/C 三级层级 + 论点文本，不含史料层 M；
      ② 论证树编码：A1-B1-C1.1-M1 形式的 ID 路径链。
    """
    et = run["encoding_table"]; A, B, C = et["A_level"], et["B_level"], et["C_level"]
    pidx = {p["id"]: i for i, p in enumerate(run.get("paragraphs", []))}
    meta = run.get("meta", {}); st = run.get("statistics", {})
    byid = {n["id"]: n for n in A + B + C}
    BIG = 1 << 30

    def pos_b(b):
        # B 节点不携带 title_pid，用 span 起点（该节点首个正文段）定序
        span = b.get("span") or []
        return pidx.get(span[0], BIG) if span and span[0] else BIG

    def kids(nid, lv):
        pool = B if lv == "B" else C
        return [n for n in pool if n.get("parent") == nid]

    def path_of(c):
        chain, p = [c["id"]], c.get("parent")
        while p and p in byid:
            chain.append(p); p = byid[p].get("parent")
        return list(reversed(chain))

    tree = ["# 论证树（A/B/C 三级，不含史料层）", "",
            "- 论文：%s" % meta.get("paper_title", ""),
            "- run：%s　模型：%s　温度：%s　版本：%s" % (
                meta.get("run_name", ""), meta.get("model", ""),
                meta.get("temperature", ""), meta.get("version", "")),
            "- 规模：A=%d　B=%d　C=%d（其中未绑定史料 %d 条）" % (
                len(A), len(B), len(C), st.get("C_nodes_without_sources", 0)), ""]

    def render(pid, prefix):
        items = [(pos_b(b), 0, "B", b) for b in kids(pid, "B")]
        items += [(pidx.get(c.get("anchor"), BIG), 1, "C", c) for c in kids(pid, "C")]
        items.sort(key=lambda x: (x[0], x[1]))
        for i, (_, _, lv, nd) in enumerate(items):
            last = i == len(items) - 1
            conn = "└─ " if last else "├─ "
            nxt = prefix + ("   " if last else "│  ")
            if lv == "B":
                tree.append("%s%s%s〔%s〕%s" % (prefix, conn, nd["id"], nd["title_label"], nd["claim"]))
                render(nd["id"], nxt)
            else:
                tree.append("%s%s%s（%s）%s" % (prefix, conn, nd["id"], nd["anchor"], nd["text"]))

    for a in A:
        tree.append("%s〔%s〕%s" % (a["id"], a["title_label"], a["claim"]))
        render(a["id"], "")

    code = ["# 论证树编码（A → B → … → C → M 的 ID 路径链）", "",
            "# 每行一条：从全文结论下溯到段落主张，再接该主张绑定的史料",
            "# 一个 C 绑定多个史料时逐个展开；C 未绑定史料记作「-（无史料）」", ""]
    for c in C:
        head = "-".join(path_of(c))
        srcs = sorted(c.get("sources", []), key=m_key)
        code.extend([head + "-" + m for m in srcs] or [head + "-（无史料）"])

    code += ["", "# 附：折叠 C 层的简写（A + 一级章节 B + 史料）", ""]
    seen = set()
    for c in C:
        chain = path_of(c)
        top = [chain[0]] + [x for x in chain[1:] if byid[x].get("depth") == 2][:1]
        for m in sorted(c.get("sources", []), key=m_key):
            key = "-".join(top + [m])
            if key not in seen:
                seen.add(key); code.append(key)

    (run_dir / "论证树_不含M层.md").write_text("\n".join(tree) + "\n", encoding="utf-8")
    (run_dir / "论证树_编码.txt").write_text("\n".join(code) + "\n", encoding="utf-8")
    print("  已导出：论证树_不含M层.md（%d 行）、论证树_编码.txt（%d 行）" % (len(tree), len(code)), flush=True)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit("用法：python _论证树一次性抽取.py <run 目录名> [论文目录(默认 A05)] "
                 "[--overwrite] [--drop-quote-only]")
    run_name = args[0]
    paper_dir = Path(args[1]) if len(args) > 1 else (LAB / "实验数据/A05")
    overwrite = "--overwrite" in sys.argv
    global DROP_QUOTE_ONLY
    DROP_QUOTE_ONLY = "--drop-quote-only" in sys.argv
    run_dir = paper_dir / "03_实验输出" / "Q_A_实验" / run_name

    paras, materials, clean_path = load_paper(run_dir)
    valid_M = {m["id"] for m in materials}

    # 无「结语/结论」标题的论文：读 结论段判定_LLM.py 的结论段集合
    concl_pids = None
    cf = run_dir / "00_原文" / "结论段_覆盖.json"
    if cf.exists():
        concl_pids = json.loads(cf.read_text(encoding="utf-8")).get("concl_pids") or None

    sk = derive_skeleton(paras, concl_pids=concl_pids)
    pidx = sk["para_index"]
    A_defs = sk["A"]
    B_defs = sk["B"]
    front = sk["front_matter"]

    print(f"[{run_name}] 段落={len(paras)}  M={len(materials)}  A={len(A_defs)}  B={len(B_defs)}  front={front}", flush=True)

    if len(A_defs)!=1:raise ValueError('请在手工整理表中明确结论标题')
    target=run_dir / ('run.json' if overwrite else 'run_论证树.json')
    if target.exists():raise FileExistsError('已有论证树，先备份并移出原文件或使用新 run；不重复调用覆盖')
    prompt = build_prompt(paras, A_defs, B_defs, front, pidx)
    prompt_path = run_dir / "_论证树_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    print(f"  prompt 字符数={len(prompt)}", flush=True)

    raw, err, usage = chat(prompt)
    if err:
        raise RuntimeError(f"API 失败：{err}")
    raw_path = run_dir / "_论证树_raw.txt"
    raw_path.write_text(raw, encoding="utf-8")
    print(f"  原始输出字符={len(raw)}  usage={usage}", flush=True)

    cleaned = clean_json(raw)
    try:
        obj = json.loads(cleaned)
    except Exception as e:
        print(f"  JSON 解析失败：{e}", flush=True)
        print(f"  （原始已存 {raw_path}）", flush=True)
        raise ValueError("抽取响应不是有效 JSON")

    a_claim = obj.get("A_claim", "")
    b_map = {it["id"]: it.get("claim", "") for it in obj.get("B_claims", [])}
    if not a_claim.strip() or set(b_map)!={b['id'] for b in B_defs} or not all(b_map.values()):
        raise ValueError('A/B 抽取不完整；原始响应已保存，不生成有效树')
    c_list = obj.get("C_claims", [])

    # ---- 组装 C 节点：parent 确定性指派 + 编号 ----
    valid_P = {p["id"] for p in paras}
    concl_pid = None
    for a in A_defs:
        if a.get("derived_from_para"):
            concl_pid = a["derived_from_para"]
        elif a.get("span") and a["span"][0]:
            concl_pid = a["span"][0]

    def assign_parent(anchor):
        for a in A_defs:
            if a.get("para_ids"):
                if anchor in a["para_ids"]:
                    return a["id"]
                continue
            if para_in_span(anchor, a.get("span"), pidx):
                return a["id"]
        best = None
        for b in B_defs:
            if para_in_span(anchor, b.get("span"), pidx):
                if best is None or b["depth"] > best["depth"]:
                    best = b
        if best:
            return best["id"]
        return None

    seen = set()
    C = []
    for c in c_list:
        anc = c.get("anchor")
        txt = (c.get("text") or "").strip()
        if not anc or anc not in valid_P or not txt:
            continue
        if anc in seen:
            print(f"  跳过重复 anchor：{anc}", flush=True)
            continue
        seen.add(anc)
        par = assign_parent(anc)
        if par is None:
            print(f"  跳过 C：无法归属 {anc}  text={txt[:30]}", flush=True)
            continue
        srcs = [m for m in paras[pidx[anc]].get("material_refs", []) if m in valid_M]
        C.append({"anchor": anc, "text": txt, "parent": par, "sources": srcs,
                  "quote_only": bool(c.get("quote_only"))})

    # 规格：每个正文自然段恰好 1 个 C。模型漏出的段落补齐占位，交人工补注（校验会报缺文本）
    expected = [p["id"] for p in paras if p.get("type") == "text" and p["id"] not in front]
    missing = [pid for pid in expected if pid not in seen]
    for pid in missing:
        par = assign_parent(pid)
        if par is None:
            print(f"  未产出 C 且无法归属：{pid}", flush=True)
            continue
        srcs = [m for m in paras[pidx[pid]].get("material_refs", []) if m in valid_M]
        C.append({"anchor": pid, "text": "〔待补：本段论点未由模型产出〕", "parent": par,
                  "sources": srcs, "quote_only": False})
    if missing:
        print(f"  补占位 C {len(missing)} 条（需人工补注）：{missing}", flush=True)

    # 编号（按 parent 标题位置 + anchor 页序）
    def node_pos(nid):
        for n in A_defs + B_defs:
            if n["id"] == nid:
                if n.get("title_pid"):
                    return pidx[n["title_pid"]]
                if n.get("derived_from_para"):
                    return pidx[n["derived_from_para"]]
        if nid in front:
            return pidx.get(nid, 1 << 30)
        return 1 << 30

    C.sort(key=lambda x: (node_pos(x["parent"]), pidx[x["anchor"]]))
    if DROP_QUOTE_ONLY:
        kept = [c for c in C if not c.get("quote_only")]
        print(f"  --drop-quote-only：剔除纯史料引文节点 {len(C) - len(kept)} 条", flush=True)
        C = kept
    chapter_count = max([int(m.group(1)) for m in
                         (re.match(r"B(\d+)", b["id"]) for b in B_defs) if m] or [0])
    counters = {}
    C_out = []
    for c in C:
        counters[c["parent"]] = counters.get(c["parent"], 0) + 1
        C_out.append({"id": c_id_for(c["parent"], counters[c["parent"]], chapter_count),
                      "anchor": c["anchor"], "text": c["text"],
                      "sources": sorted(c["sources"], key=m_key), "parent": c["parent"],
                      "quote_only": bool(c.get("quote_only"))})

    def span_pair(sp):
        return [sp[0], sp[1] if sp and len(sp) > 1 and sp[1] else sp[0]] if sp and sp[0] else [None, None]

    B_out = []
    for b in sorted(B_defs, key=lambda x: pidx[x["title_pid"]]):
        ms = union_sources(descendants(b["id"], A_defs, B_defs, C_out))
        B_out.append({
            "id": b["id"], "depth": b["depth"], "title_label": b["title_label"],
            "claim": b_map.get(b["id"], ""), "span": span_pair(b["span"]),
            "sources": sorted(ms, key=m_key), "source_count": len(ms),
            "supported": None, "supported_by": [], "parent": b.get("parent"),
        })

    A_out = []
    for a in sorted(A_defs, key=lambda x: (x["order"] if x["order"] is not None else -1)):
        ms = set(valid_M)
        A_out.append({
            "id": a["id"], "depth": a["depth"], "title_label": a["title_label"],
            "claim": a_claim, "span": span_pair(a["span"]),
            "sources": sorted(ms, key=m_key), "source_count": len(ms),
            "supported": None, "supported_by": [], "parent": None,
        })

    all_used_M = set()
    for c in C_out:
        all_used_M |= set(c["sources"])
    paragraphs_out = [{
        "id": p["id"], "type": p["type"], "text": p["text"],
        "material_refs": p.get("material_refs", []), "page": p.get("page", "1"),
    } for p in paras]
    materials_out = [{"id": m["id"], "text": m.get("text", ""),
                      "footnote_number": m.get("footnote_number"),
                      "source_full": m.get("source_full", "")} for m in materials]

    run = {
        "meta": {
            "paper_title": paras[0]["text"] if paras and paras[0].get("type") == "title" else run_name,
            "encoding_scheme": "A-B-C-M hierarchical encoding",
            "version": "3.2-once",
            "run_name": run_name, "model": MODEL,
            "temperature": TEMPERATURE,
            "frozen_config": FROZEN,
            "clean_source": Path(clean_path).name,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "note": "论证树一次性抽取（整篇一次调用；每个正文自然段 1 个 C 节点，纯史料引文段标记 quote_only；sources 由 anchor 段 material_refs 确定性绑定）",
        },
        "encoding_table": {
            "A_level": A_out,
            "B_level": B_out,
            "C_level": C_out,
            "M_level": materials_out,
        },
        "paragraphs": paragraphs_out,
        "front_matter": front,
        "statistics": {
            "total_A_nodes": len(A_out),
            "total_B_nodes": len(B_out),
            "total_C_nodes": len(C_out),
            "total_unique_M": len(materials),
            "nodes_by_depth": {str(d): (
                len(A_out) if d == 1 else sum(1 for b in B_out if b["depth"] == d))
                for d in range(1, max([1] + [b["depth"] for b in B_out]) + 1)},
            "source_count_by_A": {a["id"]: a["source_count"] for a in A_out},
            "source_count_by_B": {b["id"]: b["source_count"] for b in B_out},
            "C_nodes_without_sources": sum(1 for c in C_out if not c["sources"]),
            "claims_total": len(A_out) + len(B_out),
            "M": {"total": len(materials), "used": len(all_used_M),
                  "unused": sorted(valid_M - all_used_M, key=m_key)},
        },
    }

    out_path = run_dir / ("run.json" if overwrite else "run_论证树.json")
    if overwrite and out_path.exists():
        bak = run_dir / "run_v3.2_backup.json"
        shutil.copyfile(out_path, bak)
        print(f"  已备份旧 run.json → {bak}", flush=True)
    from source_binding import repair
    repair(run)
    from 校验 import validate
    from 管线公共 import atomic_json
    errors=validate(run)
    if errors:raise ValueError('; '.join(errors))
    atomic_json(out_path,run)
    export_views(run, run_dir)
    print(f"\n[完成] {run_name}  A={len(A_out)}  B={len(B_out)}  C={len(C_out)}", flush=True)
    print(f"  已排除引言段（不产 C）：{front or '（无）'}", flush=True)
    print(f"  M 使用: {len(all_used_M)}/{len(materials)} = {len(all_used_M)/len(materials)*100:.1f}%", flush=True)
    print(f"  输出: {out_path}", flush=True)
    print(f"  已跳过段落（纯论据/无论点）：{[p for p in valid_P if p not in seen and p not in {concl_pid or ''} and p != 'P3']}", flush=True)


if __name__ == "__main__":
    main()