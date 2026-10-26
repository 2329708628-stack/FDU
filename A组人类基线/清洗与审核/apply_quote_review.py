# -*- coding: utf-8 -*-
"""Apply the 2026-10-25 human quote review without modifying the natural-paragraph baseline.

Output: A_human_引文审核基线 next to each A_human_自然段基线.
Run from any directory: python apply_quote_review.py
"""
import copy
import hashlib
import importlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIPE = ROOT / "脚本&数据/宋史实验流水线交付包/提取与生成管线"
sys.path.insert(0, str(PIPE))
from source_binding import repair  # noqa: E402
from 校验 import validate  # noqa: E402

extractor = importlib.import_module("_论证树一次性抽取")
BASE = ROOT / "归档/数据集/数据清洗后论文"
OLD = "A_human_自然段基线"
NEW = "A_human_引文审核基线"

# Source-bearing quotation paragraphs only. Existing M identifiers are transferred,
# never invented. The target is the author's claim that most directly interprets
# the quotation. A02 P8, A07 P30 and A10 P19 are noted as judgment calls in audit.
QUOTE_TARGETS = {
    "A02": {"P8": "P11", "P10": "P11"},
    "A03": {"P21": "P22", "P30": "P31"},
    "A05": {"P21": "P24", "P22": "P24", "P23": "P24"},
    "A07": {"P14": "P15", "P30": "P29"},
    "A08": {"P6": "P7"},
    "A09": {"P5": "P4", "P6": "P4"},
    "A10": {"P12": "P13", "P19": "P18"},
}
TABLE_CAPTIONS = {
    "A01": ["P7", "P10", "P27"],
    "A07": ["P17", "P27", "P28", "P35", "P36"],
    "A08": ["P24", "P25"],
}
# These are fragments of their target paragraph's sentence, not independent claims.
FRAGMENT_TARGETS = {
    "A01": {"P57": "P56", "P48": "P47"},
    "A04": {"P8": "P9"},
    "A05": {"P36": "P35"},
    "A09": {"P30": "P29", "P34": "P33", "P39": "P38"},
}
# The surviving C text must state the entire claim after restoring a broken sentence.
REVISED_CLAIMS = {
    "A01": {
        "P47": "鄂州与汉阳军凭借茶叶高产、品质和水路区位，共同构成湖北沿江茶叶经济带的核心之一。",
        "P56": "茶叶经济繁盛既促进经济与文化发展，也对地方民生和社会稳定产生深远而复杂的影响。",
    },
    "A09": {
        "P29": "宋廷转向战略进攻后继续经营制夏计划，朝堂政治对立也波及盐钞制度。",
        "P33": "薛向、张景温扩大官榷并按户配卖，压制市场自发调节，使地方市场发展倒退。",
    },
}
KEEP_FALSE_FLAGS = {
    "A01": ["P30", "P42", "P56"],
    "A02": ["P9"],
    "A06": ["P16"],
    "A07": ["P16"],
    "A08": ["P7", "P11", "P17"],
    "A10": ["P14"],
}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply(paper):
    source_dir = BASE / paper / "03_实验输出/Q_A_实验" / OLD
    target_dir = source_dir.parent / NEW
    source_file = source_dir / "run_论证树.json"
    source_bytes = source_file.read_bytes()
    run = json.loads(source_bytes.decode("utf-8"))
    revised = copy.deepcopy(run)
    cs = revised["encoding_table"]["C_level"]
    by_anchor = {c["anchor"]: c for c in cs}
    if len(by_anchor) != len(cs):
        raise ValueError(f"{paper}: duplicate C anchors")

    quotes = QUOTE_TARGETS.get(paper, {})
    tables = TABLE_CAPTIONS.get(paper, [])
    fragments = FRAGMENT_TARGETS.get(paper, {})
    removes = set(quotes) | set(tables) | set(fragments)
    if len(removes) != len(quotes) + len(tables) + len(fragments):
        raise ValueError(f"{paper}: overlapping review actions")
    audit = []
    for anchor, target in quotes.items():
        old, new = by_anchor[anchor], by_anchor[target]
        if not old.get("quote_only"):
            raise ValueError(f"{paper} {anchor}: expected quote_only")
        before = set(new.get("sources", []))
        new["sources"] = sorted(before | set(old.get("sources", [])), key=extractor.m_key)
        audit.append(dict(action="merge_quotation", paragraph=anchor,
                          removed_C=old["id"], target_paragraph=target,
                          target_C=new["id"], transferred_M=sorted(set(old.get("sources", []))),
                          added_M=sorted(set(new["sources"]) - before)))
    for anchor in tables:
        old = by_anchor[anchor]
        if old.get("sources"):
            raise ValueError(f"{paper} {anchor}: table caption has sources, needs review")
        audit.append(dict(action="exclude_table_residue", paragraph=anchor,
                          removed_C=old["id"], transferred_M=[]))
    for anchor, target in fragments.items():
        old, new = by_anchor[anchor], by_anchor[target]
        if old.get("sources"):
            # A quote split over paragraphs, such as A09 P6, is handled above.
            raise ValueError(f"{paper} {anchor}: fragment has sources, needs review")
        audit.append(dict(action="join_broken_sentence", paragraph=anchor,
                          removed_C=old["id"], target_paragraph=target,
                          target_C=new["id"], transferred_M=[]))
    for anchor, claim in REVISED_CLAIMS.get(paper, {}).items():
        old = by_anchor[anchor]["text"]
        by_anchor[anchor]["text"] = claim
        audit.append(dict(action="revise_surviving_claim", paragraph=anchor,
                          C=by_anchor[anchor]["id"], before=old, after=claim))
    for anchor in KEEP_FALSE_FLAGS.get(paper, []):
        old = by_anchor[anchor]
        if not old.get("quote_only"):
            raise ValueError(f"{paper} {anchor}: expected flagged C")
        old["quote_only"] = False
        audit.append(dict(action="retain_C_correct_flag", paragraph=anchor, C=old["id"]))

    revised["encoding_table"]["C_level"] = [c for c in cs if c["anchor"] not in removes]
    valid_m = {m["id"] for m in revised["encoding_table"]["M_level"]}
    for paragraph in revised["paragraphs"]:
        refs = paragraph.get("material_refs", [])
        extra = [m for m in refs if m not in valid_m]
        if extra:
            paragraph["material_refs"] = [m for m in refs if m in valid_m]
            audit.append(dict(action="exclude_unlisted_paragraph_M",
                              paragraph=paragraph["id"], excluded_M=extra,
                              note="original references remain in the unchanged natural-paragraph baseline"))
    # No retained node should still be called a pure quotation.
    if any(c.get("quote_only") for c in revised["encoding_table"]["C_level"]):
        raise ValueError(f"{paper}: unreviewed quote_only remains")
    revised = repair(revised)
    errors = validate(revised)
    if errors:
        raise ValueError(f"{paper}: " + "; ".join(errors))
    revised["meta"].update(run_name=NEW,
                           review_base=OLD,
                           review_base_sha256=hashlib.sha256(source_bytes).hexdigest(),
                           review_status="manual quote review applied; original paragraphs unchanged")
    revised["meta"]["review_rule"] = (
        "one C per ordinary body paragraph; standalone quotations assigned to a reviewed author claim; "
        "table residue excluded; broken sentences joined; original P and M retained for audit"
    )
    revised["statistics"]["quote_review_removed_C"] = len(removes)
    revised["statistics"]["quote_review_source_transfers"] = sum(bool(x.get("added_M")) for x in audit)
    review = dict(paper=paper, source_tree=str(source_file),
                  source_sha256=hashlib.sha256(source_bytes).hexdigest(),
                  original_C=len(cs), reviewed_C=len(revised["encoding_table"]["C_level"]),
                  quote_paragraphs=len(quotes), table_residue=len(tables),
                  broken_sentence_fragments=len(fragments), actions=audit)
    target_dir.mkdir(exist_ok=True)
    write_json(target_dir / "run_论证树.json", revised)
    write_json(target_dir / "审核记录.json", review)
    original_input = source_dir / "00_原文/原文_clean_自然段.json"
    (target_dir / "00_原文").mkdir(exist_ok=True)
    shutil.copy2(original_input, target_dir / "00_原文/原文_clean_自然段.json")
    extractor.export_views(revised, target_dir)
    return review


if __name__ == "__main__":
    summary = [apply(f"A{i:02d}") for i in range(1, 11)]
    print("Reviewed C:", sum(x["original_C"] for x in summary), "->", sum(x["reviewed_C"] for x in summary))
    print("Quotation paragraphs:", sum(x["quote_paragraphs"] for x in summary))
    print("Table residue:", sum(x["table_residue"] for x in summary))
    print("Broken sentence fragments:", sum(x["broken_sentence_fragments"] for x in summary))
