# -*- coding: utf-8 -*-
"""v3.2 公共库：骨架机械推导、编号、sources 并集、论文路径解析。
被 run校验器.py / run组装器.py / 三轮锚点对比.py 复用。

数据约定：
  论文目录/00_原文/原文_clean.json  含 paragraphs（id/type/text/material_refs）与 materials（id/...）
  run JSON：v3.2 编码产物（meta.version == "3.2"）
"""
import json, re, sys
from pathlib import Path

CN = "一二三四五六七八九十"
RE_H2 = re.compile(r"^\s*[（(][" + CN + r"]+[）)]")
RE_H3 = re.compile(r"^\s*\d{1,2}\s*[.、．]\s*\S")
RE_H1_NUM = re.compile(r"^\s*[" + CN + r"]+\s*[、.．]?\s*\S")
# 结论类（容忍"结 语"这类字间空格）；仅指真正的收尾章，不含引言
RE_CONCL = re.compile(r"^\s*(结\s*语|结束语|余\s*论|结\s*论|小\s*结|总\s*结)\s*[：:]?\s*$")
# 带编号的结论章（「四、结语」「五、结论与展望」）：去掉编号后以此开头即视为结论
RE_CONCL_PREFIX = re.compile(r"^(结\s*语|结束语|余\s*论|结\s*论|小\s*结|总\s*结)")
# 引言类：按一级标题处理，不是结论
RE_INTRO = re.compile(r"^\s*(引\s*言|绪\s*论|引\s*论|导\s*言|前\s*言)\s*[：:]?\s*$")
# 兼容旧名：旧 RE_SPECIAL 混装了 引论|绪论，此处收敛为结论类
RE_SPECIAL = RE_CONCL
# 退化的一级标题：整段只剩编号（PDF 里章节序号与标题文字被拆成两块，如单独一个「三」）
RE_LONE_H1 = re.compile(r"^[" + CN + r"]$")
# 无标题结论段：末段以这些词开头
RE_CONCL_PARA = re.compile(r"^\s*(综上所述|综上|总而言之|总之|要\s*之|概言之)")
RE_YEAR = re.compile(r"^\s*\d{3,4}\s*[.、．]")  # 年份/表号，排除出 H3


def heading_level(text):
    """判定标题层级。返回 0=结论类；1=一级（含引言类）；2=二级；3=三级；None=非标题。

    层级约定（v3.3）：
      0 → A（全文唯一结论，depth=1）
      1 → B（depth=2，一级标题「一、二、三」及引言/绪论）
      2 → B（depth=3，二级标题「（一）（二）」）
      3 → B（depth=4，三级标题「1. 2.」）
    """
    raw = (text or "").strip()
    if not raw:
        return None
    t = re.sub(r"\s+", "", raw)
    if len(t) > 45:
        return None
    # 无编号的结论/引言标题
    if RE_CONCL.match(t):
        return 0
    if RE_INTRO.match(t):
        return 1
    if RE_LONE_H1.match(t):
        return 1
    # 结构层级：按原文编号形式判定
    if RE_H1_NUM.match(raw):
        lvl = 1
    elif RE_H2.match(raw):
        lvl = 2
    elif RE_H3.match(raw) and not RE_YEAR.match(raw):
        lvl = 3
    else:
        return None
    # 一级编号下带结论关键词的（「四、结语」「四 结论」）归为结论，不降为章节
    if lvl == 1:
        # 编号后的分隔符可能是顿号/句点/空格，故在保留原始空格的串上剥离编号
        core = re.sub(r"^[" + CN + r"\d]+\s*[、.．,，:：]?\s*", "", raw).strip()
        tcore = re.sub(r"\s+", "", core)
        if tcore != t and (RE_CONCL.match(tcore) or RE_CONCL_PREFIX.match(tcore)):
            return 0
    return lvl


def load_paper(paper_dir):
    """返回 (paragraphs_list, materials_list, clean_json_path)。

    自 2026-10-25 起全管线统一以「自然段级重洗版」为唯一基线：
    优先读取 00_原文/原文_clean_自然段.json，不存在时才回退原 原文_clean.json。
    回退情况会在调用方 meta 中以 clean_source 标记，便于追溯。
    """
    p = Path(paper_dir)
    clean = p / "00_原文" / "原文_clean_自然段.json"
    if not clean.exists():
        clean = p / "00_原文" / "原文_clean.json"
    if not clean.exists():
        sys.exit("找不到 %s —— 该论文尚未完成 01_引用提取/清洗" % clean)
    d = json.loads(clean.read_text(encoding="utf-8"))
    return d["paragraphs"], d["materials"], clean


def derive_skeleton(paragraphs, concl_pids=None):
    """从 paragraphs 机械推导骨架（即提示词调用①的 Python 实现）。

    层级约定（v3.3）：
      A：全文唯一结论节点，depth=1；来源优先级：
         ① 结论类标题（结语/余论/结论/小结/总结）；
         ② 末段以"综上…"开头的正文段（title_pid=None）；
         ③ 由 `结论段判定_LLM.py` 给出的结论段集合 concl_pids（无标题论文）。
         三者皆无则 A 为空（由调用方输出 WARN）。
      B：各章节标题节点，depth = 层级 + 1（一级→2，二级→3，三级→4，依此类推）。
      C：段落级主张（叶子），语义与旧版一致，由调用②生成。

    返回 dict：
      A: [{id,depth,title_label,span,parent,order,title_pid}]
      B: [{id,depth,title_label,span,parent,title_pid}]
      front_matter: [P...]  第一个章节标题之前的正文段
      para_index: {Pid: 段落序列位置}
    """
    paras = paragraphs
    pidx = {p["id"]: i for i, p in enumerate(paras)}

    # ---- 收集标题段 ----
    # 首个 title 段通常是论文主标题；仅当它无法被识别为任何层级标题时才跳过
    heads = []  # [seq_idx, level, text, pid]
    first_title_seen = False
    for i, p in enumerate(paras):
        if p.get("type") != "title":
            continue
        t = (p.get("text") or "").strip()
        lvl = p["heading_level"] if "heading_level" in p else heading_level(t)
        if not first_title_seen:
            first_title_seen = True
            if lvl is None:
                continue  # 论文主标题
        if lvl is None:
            continue  # 无法识别的标题段（如簿书格式误标）→ 不当结构节点
        heads.append([i, lvl, t, p["id"]])

    # ---- 结论节点：标题优先，其次末段"综上…"兜底，最后 LLM 判定的结论段 ----
    concl_heads = [h for h in heads if h[1] == 0]
    concl_para_idx = None
    concl_span = None          # (start_idx, end_idx) 由 LLM 判定给出
    if not concl_heads:
        for k in range(len(paras) - 1, -1, -1):
            p = paras[k]
            if p.get("type") != "text":
                continue
            if RE_CONCL_PARA.match((p.get("text") or "").strip()):
                concl_para_idx = k
            break  # 只看最后一个正文段
    if not concl_heads and concl_para_idx is None and concl_pids:
        picked = sorted({pidx[x] for x in concl_pids if x in pidx
                         and paras[pidx[x]].get("type") == "text"})
        if picked:
            # 结论必为收尾：只取「以最后一段结尾的连续段」，剔除章节内小结的误圈
            s, keep, cur = set(picked), [], picked[-1]
            while cur in s:
                keep.append(cur)
                cur -= 1
            concl_span = (min(keep), max(keep))

    # 章节 span 的上界：结论起始段（标题式结论不受此限，由 level 比较自然截断）
    stop_idx = concl_para_idx if concl_para_idx is not None else (
        concl_span[0] if concl_span else None)

    def span_of(h_i, level, stop=None):
        """标题 i 之后、第一个 level<=自身 的标题 j 之前的正文段闭区间。"""
        start = end = None
        for k in range(h_i + 1, len(paras)):
            if stop is not None and k >= stop:
                break
            pk = paras[k]
            if pk.get("type") == "title":
                lk = pk["heading_level"] if "heading_level" in pk else heading_level(pk.get("text"))
                if lk is not None and lk <= level:
                    break
                continue
            if start is None:
                start = pk["id"]
            end = pk["id"]
        return [start, end]

    A, B = [], []
    a_id = None
    if concl_heads:
        h_i, _, text, pid = concl_heads[0]
        a_id = "A1"
        A.append({"id": "A1", "depth": 1, "title_label": text,
                  "span": span_of(h_i, 0), "parent": None, "order": 0,
                  "title_pid": pid})
    elif concl_para_idx is not None:
        a_id = "A1"
        pp = paras[concl_para_idx]["id"]
        A.append({"id": "A1", "depth": 1, "title_label": "结论",
                  "span": [pp, pp], "parent": None, "order": 0,
                  "title_pid": None, "derived_from_para": pp})
    elif concl_span is not None:
        a_id = "A1"
        s, e = concl_span
        A.append({"id": "A1", "depth": 1, "title_label": "结语",
                  "span": [paras[s]["id"], paras[e]["id"]], "parent": None, "order": 0,
                  "title_pid": None, "derived_from_para": paras[s]["id"],
                  "llm_conclusion": True,
                  "para_ids": [paras[k]["id"] for k in range(s, e + 1)
                               if paras[k].get("type") == "text"]})

    # ---- 章节节点：按层级嵌套编号 ----
    stack = []   # [(level, id)] 祖先链，level 升序
    sib = {}     # (父路径, level) -> 同级计数
    for h_i, lvl, text, pid in heads:
        if lvl == 0:
            continue
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        parent_id = stack[-1][1] if stack else a_id
        key = (tuple(s[1] for s in stack), lvl)
        sib[key] = sib.get(key, 0) + 1
        n = sib[key]
        bid = "B%d" % n if lvl == 1 else "%s.%d" % (parent_id, n)
        B.append({"id": bid, "depth": lvl + 1, "title_label": text,
                  "span": span_of(h_i, lvl, stop_idx), "parent": parent_id,
                  "title_pid": pid, "span_raw": span_of(h_i, lvl)})
        stack.append((lvl, bid))

    # LLM 判定的结论段若恰好等于最后一个一级章节的全部正文段 → 该章节整体上提为 A
    # （仅当该章无下级子章节、且上提后 B 层不为空时；否则保留 B 节点）
    if A and A[0].get("llm_conclusion") and B:
        tops = [b for b in B if b["depth"] == 2]
        if len(tops) > 1:
            last = tops[-1]
            has_sub = any(b["parent"] == last["id"] for b in B)
            if (not has_sub and last["span_raw"] and last["span_raw"][0]
                    and last["span_raw"] == A[0]["span"]):
                A[0]["title_label"] = last["title_label"]
                A[0]["title_pid"] = last["title_pid"]
                A[0]["promoted_from_B"] = last["id"]
                B = [b for b in B if b["id"] != last["id"]]

    # front_matter：第一个章节标题之前的正文段
    first_struct_idx = min((h[0] for h in heads if h[1] >= 1), default=None)
    front = []
    if first_struct_idx is not None:
        for k in range(first_struct_idx):
            if paras[k].get("type") == "text":
                front.append(paras[k]["id"])

    return {"A": A, "B": B, "front_matter": front, "para_index": pidx,
            "paragraphs": paras}


def m_key(m):
    """M 编号排序键：M13 -> 13。"""
    return int(re.sub(r"\D", "", m))


def c_id_for(parent_id, n, chapter_count=0):
    """C 编号 = C + 父节点数字路径 + .序号。
    B1.1->C1.1.n ; B2.3.1->C2.3.1.n ;
    结语主张（父为 A 层）续末章之后：三章论文 A1->C4.n；扁平篇（chapter_count=0）->C1.n。"""
    if parent_id.startswith("A"):
        return "C%d.%d" % (chapter_count + 1, n)
    return "C" + parent_id[1:] + ".%d" % n


def descendants(parent_id, A, B, C):
    """返回某节点整棵子树内的 C 节点列表。"""
    b_ids = {b["id"] for b in B}
    a_ids = {a["id"] for a in A}
    # 子 B
    child_b = set()
    stack = [parent_id] if parent_id in b_ids or parent_id in a_ids else []
    while stack:
        cur = stack.pop()
        for b in B:
            if b["parent"] == cur:
                child_b.add(b["id"])
                stack.append(b["id"])
    targets = child_b | ({parent_id} if parent_id in b_ids or parent_id in a_ids else set())
    return [c for c in C if c["parent"] in targets]


def union_sources(nodes):
    s = set()
    for n in nodes:
        s |= set(n.get("sources", []))
    return s


def para_in_span(pid, span, para_index):
    """段落 P 是否落在 span 闭区间内（按段落序列位置）。"""
    if not span or span[0] is None:
        return False
    i = para_index.get(pid)
    lo = para_index.get(span[0])
    hi = para_index.get(span[1]) if span[1] else lo
    return i is not None and lo is not None and hi is not None and lo <= i <= hi


def find_paper_dir(start):
    """从 run 文件路径或论文目录路径推断论文根目录（含 00_原文 的最近祖先）。"""
    p = Path(start)
    if p.is_file():
        p = p.parent
    for q in [p] + list(p.parents):
        if (q / "00_原文").exists():
            return q
    return p
