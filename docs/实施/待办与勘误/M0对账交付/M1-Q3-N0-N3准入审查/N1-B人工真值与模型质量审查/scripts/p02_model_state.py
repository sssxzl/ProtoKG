# -*- coding: utf-8 -*-
"""★ N1-B 第 2 步：★ **揭盲** —— 构建候选级**模型状态关联表**。

★ ★ 严格口径（★ 用户要求）：
  · 模型状态**必须来自冻结的历史批次**（★ 不得重调 LLM）
  · ★ **不能把不同模型调用结果混在一起形成虚假的单批次指标**
  · 逐次记录：run_id / model / prompt_hash / parser·schema 版本 / L1 / L2 /
    最终状态 / 是否确定性短路 / 缓存与复判信息
  · ★ **L1 状态在历史批次中未记录 ⇒ 标记 N/A（★ 不用估计值填补）**
  · ★ 同一候选跨批次出现**不同判定** ⇒ 单列「不稳定」，★ **不计入单批次指标**
"""
import collections
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from core.fused.extraction import normative_verify as nv

OUTD = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
        / "N1-B人工真值与模型质量审查")
P079 = ROOT / "guard/_out/m1_q3/p079"

# ★ 冻结批次（★ 顺序即优先级：★ 生产复判批次优先）
BATCHES = [
    ("N3-补齐复判", ROOT / "guard/_out/n3/n3_recall_records.jsonl"),
    ("N2-稳定性扩展", ROOT / "guard/_out/n2/n2_records.jsonl"),
    ("B5-P1-有效候选复判", P079 / "p07_a5_p1_rows.jsonl"),
    ("B5-P0-状态迁移复判", P079 / "p07_a4_p0_rows.jsonl"),
    ("P3-S-稳定性探针", ROOT / "guard/_out/m1_q3/p07b5/p3s_records.jsonl"),
    ("B4-成本试验", ROOT / "guard/_out/m1_q3/p07b/b4_records.jsonl"),
]
_PARA = {
    "parser_version": getattr(nv, "PARSER_VERSION", None),
    "schema_version": getattr(nv, "SCHEMA_VERSION", None),
    "verifier_version": getattr(nv, "VERIFIER_VERSION", None),
    "★ l2_system_sha": hashlib.sha256(nv._L2_SYSTEM.encode()).hexdigest()[:16],
    "★ l2_user_template_sha": hashlib.sha256(nv._L2_USER.encode()).hexdigest()[:16],
}
_COMMIT = "b4eeb49"   # ★ P0.7 联合验收时的代码版本（★ 冻结基准）

# ★ 逐次判定
runs = []
for _tag, _p in BATCHES:
    if not _p.is_file():
        continue
    for _i, _r in enumerate([json.loads(l) for l in
                              _p.read_text(encoding="utf-8").splitlines()
                              if l.strip()]):
        if _r.get("skipped"):
            continue
        if not _r.get("verdict") or _r.get("error"):
            continue
        _side = _r.get("side") or _r.get("which") or "new"
        _short = _r.get("skipped") or _r.get("api_attempts", 0) == 0
        runs.append({
            "candidate_id": _r["candidate_id"], "side": _side,
            "★ batch": _tag,
            "★ run_id": f"{_tag}#{_i}",
            "model": _r.get("model"),
            "prompt_hash": _r.get("prompt_hash"),
            "★ L1 状态": "★ N/A（★ 历史批次未记录 L1）",
            "★ L2 状态": _r["verdict"],
            "★ 确定性短路": bool(_short),
            "api_attempts": _r.get("api_attempts", 0),
            "input_tokens": _r.get("input_tokens"),
            "output_tokens": _r.get("output_tokens"),
            "finish_reason": _r.get("finish_reason"),
            "raw_response_sha256": _r.get("raw_response_sha256"),
            "reason": (str(_r.get("reason"))[:200] if _r.get("reason") else None),
            "code_commit": _r.get("code_commit") or _COMMIT,
            **_PARA,
        })

# ★ 候选级汇总（★ ★ **单批次口径** ⇒ 取**优先级最高批次**的首次真实 API 判定）
_byc = collections.defaultdict(list)
for _r in runs:
    _byc[_r["candidate_id"]].append(_r)

model_state = {}
for cid, rs in _byc.items():
    _real = [r for r in rs if not r["★ 确定性短路"]]
    _all_v = {r["★ L2 状态"] for r in rs}
    _real_v = {r["★ L2 状态"] for r in _real}
    _instable = len(_all_v) > 1
    _primary = None
    for _tag, _ in BATCHES:            # ★ 按优先级取首个真实 API 判定
        _c = [r for r in _real if r["★ batch"] == _tag]
        if _c:
            _primary = _c[0]
            break
    if _primary is None and rs:
        _primary = rs[0]
    model_state[cid] = {
        "candidate_id": cid,
        "★ 主口径 batch": _primary["★ batch"] if _primary else None,
        "★ 主口径 run_id": _primary["★ run_id"] if _primary else None,
        "model": _primary["model"] if _primary else None,
        "prompt_hash": _primary["prompt_hash"] if _primary else None,
        "★ L1 状态": "★ N/A（★ 历史批次未记录 L1）",
        "★ L2 状态": _primary["★ L2 状态"] if _primary else None,
        "★ 最终状态": _primary["★ L2 状态"] if _primary else "★ 无判定记录",
        "★ 确定性短路": bool(_primary["★ 确定性短路"]) if _primary else None,
        "★ ★ 跨批次不稳定": _instable,
        "★ 跨批次出现过的状态": sorted(_all_v),
        "★ 真实 API 批次的判定集合": sorted(_real_v),
        "★ 全部记录数": len(rs),
        "★ 真实 API 记录数": len(_real),
        "★ 各批次判定": [{"batch": r["★ batch"], "run_id": r["★ run_id"],
                     "L2": r["★ L2 状态"], "det": r["★ 确定性短路"],
                     "prompt_hash": (r["prompt_hash"] or "")[:12],
                     "side": r["side"]} for r in rs],
        **_PARA,
    }

# ★ 候选级「唯一 L2 状态」分布（★ ★ **单批次口径** ⇒ 只取主口径）
_dist = collections.Counter(v["★ 最终状态"] for v in model_state.values())
# ★ 跨批次不稳定者（★ ★ 不计入单批次指标）
_unstable = [cid for cid, v in model_state.items() if v["★ ★ 跨批次不稳定"]]

summary = {
    "★ 口径声明": {
        "主口径": "★ 每个候选取**批次优先级最高**的一次**真实 API** L2 判定（★ 生产复判批次优先）",
        "★ L1": "★ **N/A**（★ 历史批次记录只含 L2）⇒ ★ 不用估计值填补",
        "★ 缓存": "★ l2_check 不使用缓存 ⇒ 每次判定均为真实请求",
        "★ 不混批": "★ 跨批次判定不一致者**单列**，★ **不计入单批次指标**",
    },
    "★ 逐次判定记录数": len(runs),
    "★ 涉及候选数": len(model_state),
    "★ 主口径 L2 分布": dict(_dist),
    "★ ★ 跨批次不稳定候选": _unstable,
    "★ 不稳定候选数": len(_unstable),
    "★ 批次": [{"batch": t, "file": str(p.relative_to(ROOT))} for t, p in BATCHES],
    "★ 冻结代码版本": _COMMIT,
    "★ Parser/Schema 版本": _PARA,
}
(OUTD / "N1-B_模型状态关联.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
(OUTD / "N1-B_模型状态关联明细.jsonl").write_text(
    "\n".join(json.dumps(v, ensure_ascii=False)
              for _, v in sorted(model_state.items())) + "\n", encoding="utf-8")
print(f"  ★ 逐次判定 {len(runs)} 条｜候选 {len(model_state)} 个")
print(f"  ★ 主口径 L2 分布：{dict(_dist)}")
print(f"  ★ ★ 跨批次不稳定候选（{len(_unstable)}）：{_unstable}")
print(f"  ⇒ {OUTD/'N1-B_模型状态关联.json'}")
