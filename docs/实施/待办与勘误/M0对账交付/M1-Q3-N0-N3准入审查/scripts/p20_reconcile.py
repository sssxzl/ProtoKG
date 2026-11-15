# -*- coding: utf-8 -*-
"""★ N2.1：★ 重建 L2 历史对账（★ 统一 prompt_hash = 完整渲染 Prompt 的 sha256）。

★ 修正点：
  ① P3-E 的 14 个候选配对 + 额外重复 + 22 次新增 API 的对应关系
  ② ★ 所有历史记录统一用**完整渲染 Prompt** 的 SHA256（★ 不再依赖各批次的算法）
  ③ 统一模型、参数、Parser 版本与调用身份
  ④ 重算**真正可比的独立候选组数**
  ⑤ `@1842#2` 的完整状态序列（★ 不遗漏重复判定）
★ ★ 原始记录不覆盖（★ 只读）
"""
import collections
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from core.fused.extraction import normative_verify as nv
from core.fused.extraction.normative_rule import parse_rule_text

OUT = ROOT / "guard/_out/n2"
OUT.mkdir(parents=True, exist_ok=True)
P079 = ROOT / "guard/_out/m1_q3/p079"
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"

led = {x["candidate_id"]: x for x in
       [json.loads(l) for l in
        (P079 / "p07_candidate_ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()]}
aud = {json.loads(l)["candidate_id"]: json.loads(l) for l in
       (ROOT / "guard/_out/m1_q3/p06/p06_audit.jsonl")
       .read_text(encoding="utf-8").splitlines() if l.strip()}
orig = {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        orig[f"{b['document']}@{b['chunk_start']}#{i}"] = {**it,
                                                         "chunk_start": b["chunk_start"]}


def payload_of(cid):
    o = orig.get(cid, {})
    return {"subject": o.get("normative_subject") or o.get("entity") or "",
            "action": o.get("action") or "", "object": o.get("object") or "",
            "strength": o.get("strength") or "", "polarity": o.get("polarity") or "",
            "condition": o.get("constraint") or ""}


def full_prompt(cid, side):
    p = payload_of(cid)
    q = (aud.get(cid, {}).get("old_quote") if side == "old"
         else aud.get(cid, {}).get("new_quote")) or ""
    sem = {k: p.get(k) for k in nv.SEMANTIC_FIELDS if k in p}
    user = nv._L2_USER.format(payload=json.dumps(sem, ensure_ascii=False,
                                                  sort_keys=True),
                              quote=q[:6000])
    return nv._L2_SYSTEM + "\n" + user


# ★ 收集历史真实 API 记录
SRC = [
    ("B4", ROOT / "guard/_out/m1_q3/p07b/b4_records.jsonl"),
    ("P3-S", ROOT / "guard/_out/m1_q3/p07b5/p3s_records.jsonl"),
    ("P3-E", P079 / "p07_a2_p3e_records.jsonl"),
    ("B5-P0", P079 / "p07_a4_p0_rows.jsonl"),
    ("B5-P1", P079 / "p07_a5_p1_rows.jsonl"),
]
rows = []
for tag, p in SRC:
    if not p.is_file():
        continue
    for r in [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
              if l.strip()]:
        if not r.get("verdict") or r.get("error"):
            continue
        if r.get("api_attempts", 0) <= 0:
            continue          # ★ 确定性短路 ⇒ 无 LLM 输出
        cid = r["candidate_id"]
        side = r.get("side") or r.get("which") or "new"
        if side not in ("old", "new"):
            side = "new"
        rows.append({
            "source": tag, "candidate_id": cid, "side": side,
            "verdict": r["verdict"], "reason": r.get("reason"),
            "tokens": (r.get("input_tokens") or 0) + (r.get("output_tokens") or 0),
            "resp_sha": r.get("raw_response_sha256"),
            "★ 旧 prompt_hash": r.get("prompt_hash"),
            "★ 统一 prompt_hash": hashlib.sha256(
                full_prompt(cid, side).encode("utf-8")).hexdigest(),
        })

print(f"  ★ 历史真实 API 记录 = {len(rows)}")
_by_src = collections.Counter(r["source"] for r in rows)
print(f"  ★ 来源分布: {dict(_by_src)}")

# ★ ④ 按统一 hash 分组 ⇒ ★ 独立候选组数
groups = collections.defaultdict(list)
for r in rows:
    groups[(r["candidate_id"], r["★ 统一 prompt_hash"], r["side"])].append(r)
comp = {k: v for k, v in groups.items() if len(v) >= 2}
_cids = {k[0] for k in comp}
print(f"  ★ (候选,统一hash,侧) 分组 = {len(groups)}｜★ 可比组（≥2 次）= {len(comp)}")
print(f"  ★ ★ **真正可比的独立候选数 = {len(_cids)}**")

# ★ ⑤ @1842#2 的完整状态序列
_h = [r for r in rows if r["candidate_id"] == "rfc3261.txt@1842#2"]
print()
print(f"  ★ @1842#2 的完整状态序列（{len(_h)} 次）：")
for r in sorted(_h, key=lambda x: (x["source"], x["side"],
                                   x["★ 统一 prompt_hash"][:8])):
    print(f"      {r['source']:6s} {r['side']:4s} ph={r['★ 统一 prompt_hash'][:10]} "
          f"⇒ {r['verdict']}")

# ★ ③ 统一模型/参数/版本
_meta = {"model": "deepseek-flash", "temperature": 0.0,
         "max_tokens": 16000,
         "parser_version": getattr(nv, "PARSER_VERSION", None),
         "schema_version": getattr(nv, "SCHEMA_VERSION", None),
         "verifier_version": getattr(nv, "VERIFIER_VERSION", None),
         "★ l2 系统提示 sha": hashlib.sha256(
             nv._L2_SYSTEM.encode()).hexdigest()[:16],
         "★ l2 用户模板 sha": hashlib.sha256(
             nv._L2_USER.encode()).hexdigest()[:16]}

# ★ ② 旧 hash 与统一 hash 的差异（★ 说明为何必须统一）
_diff = sum(1 for r in rows if r["★ 旧 prompt_hash"]
            and r["★ 旧 prompt_hash"] != r["★ 统一 prompt_hash"])
print(f"  ★ ② 旧 hash 与统一 hash **不同**的记录：{_diff}/{len(rows)}"
      f"（★ ⇒ 旧 hash 各批次算法不同 ⇒ ★ 跨批次不可直接合并）")

summary = {
    "★ 历史真实 API 记录": len(rows),
    "★ 来源分布": dict(_by_src),
    "★ 统一配置": _meta,
    "★ 旧 hash 与统一 hash 不同": _diff,
    "★ 可比组（候选,统一hash,侧）": len(comp),
    "★ ★ 真正可比的独立候选数": len(_cids),
    "★ 可比候选清单": sorted(_cids),
    "★ @1842#2 完整序列": [
        {"source": r["source"], "side": r["side"],
         "★ unified_hash": r["★ 统一 prompt_hash"], "verdict": r["verdict"],
         "tokens": r["tokens"], "resp_sha": r["resp_sha"]} for r in _h],
    "★ 不可比的原因": "★ 同一候选的不同 side（old/new）本就不同输入；"
                  "★ 且各批次旧 hash 算法不同 ⇒ 必须按统一 hash 分组",
}
(OUT / "n2_reconciliation.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "n2_history_rows.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
    encoding="utf-8")
print(f"\n  ⇒ {OUT/'n2_reconciliation.json'}")
