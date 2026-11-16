# -*- coding: utf-8 -*-
"""★ N1-C：★ 冻结第二批独立评测集（★ 从风险台账 `not_sampled_in_frame` 提取）。

★ §三 六项核实条件：
  ① 与 N1-A 的 50 条**无重叠**
  ② 原始 RFC 文档及 SHA256 **一致**
  ③ 原文跨度与证据**可重新定位**（★ 用 M1-Q2 契约独立复核）
  ④ **无泄漏**：★ 不含模型状态 / 错误归因 / 人工结论
  ⑤ ★ **模型预测基线与生成配置已在人工标注前冻结**
  ⑥ ★ 样本**未因预期错误类型而在冻结后被替换**（★ 按既有抽样规则机械提取）
"""
import collections
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from core.fused.extraction.normative_extract import resolve_span_evidence

OUTD = ROOT / "guard/_out/n1c"
OUTD.mkdir(parents=True, exist_ok=True)
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
DELIV.mkdir(parents=True, exist_ok=True)
P079 = ROOT / "guard/_out/m1_q3/p079"
N1B = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
       / "N1-B人工真值与模型质量审查")

# ★ 冻结总体清单（★ 156 条，含四类）
pop = {json.loads(l)["sample_id"]: json.loads(l) for l in
       (ROOT / "guard/_out/n1r2/n1r2_population.jsonl").read_text(encoding="utf-8").splitlines()
       if l.strip()}
# ★ 跨度台账
spans = {json.loads(l)["sample_id"]: json.loads(l) for l in
         (ROOT / "guard/_out/n1r2/n1r2_span_ledger.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()}
# ★ N1-A 的 50 条
n1a_ids = {json.loads(l)["sample_id"] for l in
           (N1B / "N1-B_冻结人工真值.jsonl").read_text(encoding="utf-8").splitlines()
           if l.strip()}
# ★ 原始冻结件（★ 候选字段）
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"
FR = {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        FR[f"{b['document']}@{b['chunk_start']}#{i}"] = it
# ★ 文档原文
_docs = {}


def _lines(proto, doc):
    _k = (proto, doc)
    if _k not in _docs:
        _p = ROOT / f"kb/{proto}/spec/{doc}"
        _docs[_k] = {"lines": _p.read_text(encoding="utf-8", errors="replace")
                     .replace("\r\n", "\n").split("\n"),
                     "sha256": hashlib.sha256(_p.read_bytes()).hexdigest()}
    return _docs[_k]


# ★ ★ ① 机械提取：`not_sampled_in_frame` 全集（★ 不按错误类型挑选）
_frame_not_sampled = sorted(c for c, v in pop.items()
                             if v["★ 类别"] == "not_sampled_in_frame")
print(f"  ★ 风险台账中 not_sampled_in_frame = {len(_frame_not_sampled)}")

# ★ 核实它是否等于「100 条 evidence_supported 中未接受 N1-A 审核的完整剩余」
_frame = sorted(c for c, v in pop.items()
                if v["★ 类别"] in ("audited", "not_sampled_in_frame"))
_unreviewed = sorted(set(_frame) - n1a_ids)
print(f"  ★ 抽样框（audited + not_sampled）= {len(_frame)}")
print(f"  ★ 其中未被 N1-A 审核 = {len(_unreviewed)}")
_is_complete = (_unreviewed == _frame_not_sampled)
print(f"  ★ ★ ① 机械提取 == 抽样框剩余？ { _is_complete }")
if not _is_complete:
    print(f"      差集：{set(_unreviewed) ^ set(_frame_not_sampled)}")

# ★ ② 无重叠
_no_overlap = not (set(_frame_not_sampled) & n1a_ids)
# ★ ③ 文档 SHA256 与跨度可重新定位
rows = []
_bad_sha = []
_bad_span = []
for cid in _frame_not_sampled:
    _sp = spans[cid]
    _d = _lines(_sp["★ protocol"], _sp["★ document"])
    _ok_sha = (_d["sha256"] == _sp["★ rfc_sha256"])
    if not _ok_sha:
        _bad_sha.append(cid)
    # ★ 用 M1-Q2 契约**独立重新定位**
    _ev = resolve_span_evidence(_d["lines"], _sp["raw_span"], _sp["★ entity"],
                                chunk_start=_sp["chunk_start"],
                                chunk_end=_sp["chunk_end"])
    _rs = _ev.get("resolved_span")
    _ok_span = (_rs == _sp["resolved_span"]
                and _ev.get("span_mode") == _sp["span_mode"])
    if not _ok_span:
        _bad_span.append({"sample_id": cid, "台账": _sp["resolved_span"],
                          "复核": _rs, "台账mode": _sp["span_mode"],
                          "复核mode": _ev.get("span_mode")})
    rows.append({"sample_id": cid, "★ SHA256 一致": _ok_sha,
                 "★ 跨度可重新定位": _ok_span,
                 "resolved_span": _rs, "span_mode": _ev.get("span_mode"),
                 "chunk_start": _sp["chunk_start"], "chunk_end": _sp["chunk_end"],
                 "raw_span": _sp["raw_span"],
                 "★ entity": _sp["★ entity"],
                 "protocol": _sp["★ protocol"], "document": _sp["★ document"],
                 "rfc_sha256": _d["sha256"]})

print(f"  ★ ② 与 N1-A 无重叠：{_no_overlap}")
print(f"  ★ ③ SHA256 不一致：{len(_bad_sha)}｜跨度不可重新定位：{len(_bad_span)}")

# ★ ④ 无泄漏检查（★ 盲审文件将不含这些）
_LEAK_KEYS = ("模型", "L2", "final_state", "verdict", "误确认", "误拒",
              "错误归因", "人工真值", "truth_label", "review_note")
# ★ ⑤ 模型预测基线冻结（★ 在人工标注前）
baseline = {}
for cid in _frame_not_sampled:
    _m = None
    for _p in (P079.parent / "n2/n2_records.jsonl",
               P079.parent / "n3/n3_recall_records.jsonl",
               P079 / "p07_a5_p1_rows.jsonl", P079 / "p07_a4_p0_rows.jsonl",
               ROOT / "guard/_out/m1_q3/p07b5/p3s_records.jsonl",
               ROOT / "guard/_out/m1_q3/p07b/b4_records.jsonl"):
        if not _p.is_file():
            continue
        for l in _p.read_text(encoding="utf-8").splitlines():
            if not l.strip():
                continue
            _d = json.loads(l)
            if _d.get("candidate_id") != cid or not _d.get("verdict"):
                continue
            if _d.get("api_attempts", 0) <= 0:
                continue
            _m = _m or {"candidate_id": cid,
                        "★ 模型基线批次": [], "model": _d.get("model"),
                        "prompt_hash": _d.get("prompt_hash"),
                        "code_commit": _d.get("code_commit")}
            _m["★ 模型基线批次"].append({
                "batch": _p.stem, "side": _d.get("side") or _d.get("which"),
                "L2": _d.get("verdict"), "api_attempts": _d.get("api_attempts"),
                "prompt_hash": (_d.get("prompt_hash") or "")[:16]})
    baseline[cid] = _m
_have_base = sum(1 for v in baseline.values() if v)
print(f"  ★ ⑤ 有冻结模型基线的候选 = {_have_base}/{len(_frame_not_sampled)}"
      f"（★ 无基线者 ⇒ 该候选模型相对指标 N/A）")

# ★ ⑥ 未因预期错误类型被替换（★ 机械提取 ⇒ 天然满足；★ 记录提取方式）
freeze_manifest = {
    "★ 提取方式": "★ **机械提取**：`population.jsonl` 中 `★ 类别 == not_sampled_in_frame` 的全集",
    "★ 未按错误类型挑选": True,
    "★ 候选数": len(_frame_not_sampled),
    "★ 与 N1-A 无重叠": _no_overlap,
    "★ 是抽样框剩余的完整集合": _is_complete,
    "★ 抽样框总数": len(_frame),
    "★ N1-A 已审核": len(n1a_ids),
    "★ SHA256 不一致": _bad_sha,
    "★ 跨度不可重新定位": _bad_span,
    "★ 有冻结模型基线": _have_base,
    "★ 无模型基线（⇒ 模型相对指标 N/A）": sorted(
        c for c, v in baseline.items() if not v),
    "★ 泄漏键（★ 盲审文件不得含）": list(_LEAK_KEYS),
    "★ 样本逐条": rows,
}
(OUTD / "n1c_freeze_manifest.json").write_text(
    json.dumps(freeze_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
(OUTD / "n1c_model_baseline.json").write_text(
    json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'n1c_freeze_manifest.json'}")
print(f"  ⇒ {OUTD/'n1c_model_baseline.json'}")
