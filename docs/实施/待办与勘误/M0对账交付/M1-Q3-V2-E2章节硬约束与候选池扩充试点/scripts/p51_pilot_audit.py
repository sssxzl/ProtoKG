# -*- coding: utf-8 -*-
"""★ V2-E2 §八：★ **试点验收统计**（★ 10 项，★ 不得只看新增数量）。"""
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTD = ROOT / "guard/_out/_v2_e2_pilot"
E2 = ROOT / "guard/_out/_n1c_v2/e2"

_recs = [json.loads(l) for l in
         (OUTD / "V2-E2_新增候选审计.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()]
_sum = json.loads((OUTD / "V2-E2_LLM抽取试点运行报告.json").read_text(encoding="utf-8"))
_cfg = json.loads((OUTD / "V2-E2_受限LLM试点配置.json").read_text(encoding="utf-8"))
_docs = ROOT / "kb"

# ★ 候选级（★ 有 candidate 全量的记录）
_cands = [r for r in _recs if r.get("★ ★ candidate 全量")]
_calls = [r for r in _recs if not r.get("★ ★ candidate 全量")]

# ★ ① ② ③
_docs_n = len({r["★ document_id"] for r in _recs if r.get("★ document_id")})
_chunks_n = len({r.get("★ chunk_id") for r in _recs if r.get("★ chunk_id")})

# ★ ④ 每份 RFC 新增候选数
_by_doc = collections.Counter(r["★ document_id"] for r in _cands)
# ★ ⑤ 候选的知识类型分布
_kind = collections.Counter()
for r in _cands:
    _c = r.get("★ ★ candidate 全量") or {}
    _k = (_c.get("kind") or _c.get("type") or _c.get("category")
          or _c.get("aspect") or "★ 未标注")
    _kind[str(_k)] += 1
# ★ ⑥ 可定位证据比例
_loc = sum(1 for r in _cands
            if r.get("★ source_span") and r["★ source_span"][0])
# ★ ⑦ 主体/动作/对象/条件完整性
_comp = collections.Counter()
for r in _cands:
    _c = r.get("★ ★ candidate 全量") or {}
    for _f in ("subject", "action", "object", "condition"):
        _v = _c.get(_f) or _c.get("normative_subject") or ""
        _comp[_f] += 1 if str(_v).strip() else 0
# ★ ⑧ 重复候选与无效候选
_dup = 0
_seen = set()
for r in _cands:
    _c = r.get("★ ★ candidate 全量") or {}
    _key = (r.get("★ document_id"), str(_c.get("entity") or ""),
            str((r.get("★ source_span") or [None])[0]))
    if _key in _seen:
        _dup += 1
    _seen.add(_key)
_invalid = sum(1 for r in _cands
               if not str((r.get("★ ★ candidate 全量") or {}).get("entity") or "").strip())
# ★ ⑨ 不同协议的实际产出
_by_proto = collections.Counter(r["★ protocol"] for r in _cands)
# ★ ⑩ 未来独立候选评测可获得的样本容量
_pilot_docs = sorted({(r["★ protocol"], r["★ document_id"]) for r in _recs
                      if r.get("★ document_id")})
_reserved = [json.loads(l) for l in
             (E2 / "v2e2_source_isolation.jsonl").read_text(encoding="utf-8").splitlines()
             if l.strip()]
_reserved_n = sum(1 for r in _reserved if r["★ 来源集合"] == "③ 未来独立评估保留")

_report = {
    "① 实际处理 RFC 文档数": _docs_n,
    "① 实际处理 chunk 数": _chunks_n,
    "② 实际 LLM 调用数": _sum["★ 实际 LLM 调用数（★ 估算）"],
    "② token 消耗": {"input": _sum["★ input tokens"], "output": _sum["★ output tokens"],
                "合计": _sum["★ token 合计"]},
    "② 估算费用 USD": _sum["★ 估算费用 USD"],
    "③ 调用成功/失败/解析失败/缓存": {
        "★ 成功块": len({r.get("★ chunk_id") for r in _calls if r.get("★ parse_status") == "★ ok"}),
        "★ 异常块": len({r.get("★ chunk_id") for r in _calls if r.get("★ parse_status") != "★ ok"}),
        "★ 缓存命中": sum(1 for r in _recs if "hit" in str(r.get("★ cache_status"))),
        "★ 缓存未命中": sum(1 for r in _recs if "miss" in str(r.get("★ cache_status"))),
        "★ 解析失败": len([r for r in _recs if r.get("★ parse_status") == "★ 解析失败"])},
    "④ 每份 RFC 新增候选数": dict(sorted(_by_doc.items())),
    "⑤ 候选知识类型分布": dict(_kind),
    "⑥ 可定位证据比例": {
        "★ 候选数": len(_cands),
        "★ 有 source_span 的": _loc,
        "★ 比例": round(_loc / max(1, len(_cands)), 4)},
    "⑦ 主体/动作/对象/条件完整性": {
        _f: {"★ 完整数": _comp[_f], "★ 比例": round(_comp[_f] / max(1, len(_cands)), 4)}
        for _f in ("subject", "action", "object", "condition")},
    "⑧ 重复候选数": _dup, "⑧ 无效候选数（★ entity 为空）": _invalid,
    "⑨ 各协议实际产出": dict(_by_proto),
    "⑩ 未来独立候选评测可获容量": {
        "★ 本轮试点文档数（★ 不可再作独立来源）": len(_pilot_docs),
        "★ 保留来源文档数": _reserved_n,
        "★ 说明": "★ 保留来源仍需抽取才能成为候选；★ 抽取配置须冻结"},
    "★★ ★ 必须强调": ("★ **新增 52 条候选只是观察指标**；★ **不得**解释为 52 条真实规范知识"
                 "（★ 未经人工审核）；★ 本批**只**用于评估候选生成可行性与成本，"
                 "★ **不得**作为 V2 最终独立泛化验证数据"),
}
(OUTD / "V2-E2_试点验收统计.json").write_text(
    json.dumps(_report, ensure_ascii=False, indent=2), encoding="utf-8")
print("  ★ 试点验收统计：")
for _k, _v in _report.items():
    if isinstance(_v, dict) and len(_v) > 10:
        print(f"      {_k}: （{len(_v)} 项）")
    else:
        print(f"      {_k}: {json.dumps(_v, ensure_ascii=False)[:190]}")
