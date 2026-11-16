# -*- coding: utf-8 -*-
"""★ H1 §二：★ **复核 H0 的两个统计口径**（★ 97 与 canonical 保全率 0）。"""
import collections
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUTD = ROOT / "guard/_out/_n1c_v2/h1"
OUTD.mkdir(parents=True, exist_ok=True)

rows = [json.loads(l) for l in
        (ROOT / "guard/_out/_n1c_v2/h0/h0_field_ledger.jsonl")
        .read_text(encoding="utf-8").splitlines() if l.strip()]
lost = [r for r in rows if r["★ 状态"] == "unexpectedly_lost"]
print(f"  ★ unexpectedly_lost 记录数 = {len(lost)}")
_bycand = collections.Counter(r["candidate_id"] for r in lost)
_byfield = collections.Counter(r["field"] for r in lost)
_bykind = collections.Counter(r["knowledge_kind"] for r in lost)
_bydoc = collections.Counter(
    r.get("★ source_reference") or "".split("#@")[0].replace("file:", "") for r in lost)
print(f"  ★ 唯一 candidate_id = {len(_bycand)}")
print(f"  ★ 唯一 (candidate_id, field) = {len({(r['candidate_id'], r['field']) for r in lost})}")
print(f"  ★ 按字段：{dict(_byfield)}")
print(f"  ★ 按 knowledge_kind：{dict(_bykind)}")
print(f"  ★ 每候选丢失字段数分布：{dict(collections.Counter(_bycand.values()))}")
print(f"  ★ 按文档（前 8）：{dict(_bydoc.most_common(8))}")
print(f"  ★ 涉及字段是否含 '合法缺省/不适用'：")
_llm_only = [r for r in lost if r["★ LLM 层非空"] is True]
print(f"      ★ LLM 层【确实非空】的记录 = {len(_llm_only)}（★ 即【真丢失】）")
print(f"      ★ LLM 层为空却被判 lost 的 = {len(lost) - len(_llm_only)}（★ 统计口径错误）")

# ★ canonical 保全率 0 的口径核验
print()
print("  ★ canonical 保全率核验：")
_all = [r for r in rows if r["field"] != "evidence_span"]
_zero = [r for r in _all if r["★ canonical 视图非空"] is False]
print(f"      ★ 非 evidence_span 记录 = {len(_all)}｜canonical 视图非空 = 0 的 = {len(_zero)}")
print(f"      ★ ★ 原因：★ 核验脚本**从未提供 canonical 视图**（★ canonical_view 参数恒为 None）")
print(f"      ★ ★ ⇒ **0 是【未测量】，★ 不是【测得为零】**")
_canon_known = [r for r in rows if r.get("★ canonical 映射去向")
                and "无直接槽位" not in r["★ canonical 映射去向"]
                and "未映射" not in r["★ canonical 映射去向"]]
print(f"      ★ 有 canonical 承载路径的字段（★ 按映射表）："
      f"{sorted({r['field'] for r in _canon_known})}")
print(f"      ★ 无直接槽位的字段（★ 按映射表）："
      f"{sorted({r['field'] for r in rows if '无直接槽位' in (r.get('★ canonical 映射去向') or '')})}")

_out = {
    "★ unexpectedly_lost 复核": {
        "★ 统计单位": "★ **字段级流转记录**（★ 1 条 = 1 个 candidate_id × 1 个字段）",
        "★ 记录数": len(lost),
        "★ 唯一 candidate_id": len(_bycand),
        "★ 唯一 (candidate_id, field)": len({(r["candidate_id"], r["field"]) for r in lost}),
        "★ 每候选丢失字段数分布": dict(collections.Counter(_bycand.values())),
        "★ 按字段": dict(_byfield),
        "★ 按知识类型": dict(_bykind),
        "★ 按文档（前 10）": dict(_bydoc.most_common(10)),
        "★ 其中 LLM 层确实非空（★ 真丢失）": len(_llm_only),
        "★ 其中 LLM 层为空却判 lost（★ 口径错）": len(lost) - len(_llm_only),
        "★ ★ 结论": ("★ **97 是【字段级记录数】，★ 不是「97 条有效知识丢失」**；★ "
                 f"★ 实际涉及 **{len(_bycand)} 个候选**；★ "
                 f"★ 且其中 **{len(_llm_only)} 条**才是【LLM 已产出却未保留】的【真丢失】"),
    },
    "★ canonical 保全率 0 复核": {
        "★ 现象": "★ ④ 映射阶段保全率 全为 0",
        "★ ★ 根因": ("★ **核验脚本从未提供 canonical 视图**（★ `canonical_view` 恒为 None）"
                 "★ ⇒ **0 是【未测量】，★ 不是【测得为零】**"),
        "★ 有 canonical 承载路径的字段": sorted(
            {r["field"] for r in rows
             if r.get("★ canonical 映射去向")
             and "无直接槽位" not in r["★ canonical 映射去向"]
             and "未映射" not in r["★ canonical 映射去向"]}),
        "★ 无直接槽位的字段（★ 按映射表）": sorted(
            {r["field"] for r in rows
             if "无直接槽位" in (r.get("★ canonical 映射去向") or "")}),
        "★ ★ 结论": ("★ ★ **不得把所有非同名字段统计为丢失**；★ 需沿 canonical 实际承载路径"
                 "★ （规范文本 / qualifiers / Assertion / provenance / 关联 Fact）逐条核对"),
    },
}
(OUTD / "h1_recheck97.json").write_text(
    json.dumps(_out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'h1_recheck97.json'}")
