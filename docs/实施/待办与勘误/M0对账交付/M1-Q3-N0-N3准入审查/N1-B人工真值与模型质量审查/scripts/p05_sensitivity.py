# -*- coding: utf-8 -*-
"""★ N1-B 第 4b 步：★ **主口径敏感性分析**（★ 防止选择偏差造成虚假结论）。

★ 背景：★ 主口径取「批次优先级最高的首次真实 API 判定」⇒ ★ 若同候选在别的批次
★ 给出过 confirmed，★ 则该选择会**系统性低估** confirmed 精度、**高估**误拒率。
★ ⇒ ★ 本步骤把**全部批次判定**摊开，★ 给出各口径下的结论对比。
"""
import collections
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTD = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
        / "N1-B人工真值与模型质量审查")

frozen = {json.loads(l)["sample_id"]: json.loads(l) for l in
          (OUTD / "N1-B_冻结人工真值.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()}
model = {json.loads(l)["candidate_id"]: json.loads(l) for l in
         (OUTD / "N1-B_模型状态关联明细.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()}

# ★ 口径 A：★ 主口径（优先级最高批次的首次真实 API 判定）
# ★ 口径 B：★ **任一批次**出现 confirmed ⇒ 记 confirmed（★ 最宽松）
# ★ 口径 C：★ **全部批次**都是同一状态且非 rejected ⇒ 记该状态（★ 严格）
# ★ 口径 D：★ 仅用**单一批次**（逐批次各算一次，★ 看结论随批次的变化）

rows = []
for sid, fr in sorted(frozen.items()):
    _m = model.get(sid)
    if not _m:
        continue
    _recs = _m.get("★ 各批次判定", [])
    _real = [r for r in _recs if not r["det"]]
    _vs = [r["L2"] for r in _real]
    _truth = fr["★ ★ 冻结规范真值"]
    _main = _m.get("★ L2 状态")
    _A = _main
    _B = "confirmed" if "confirmed" in _vs else (_main or "★ N/A")
    _C = (_vs[0] if _vs and len(set(_vs)) == 1 else "★ 跨批不一致")
    rows.append({
        "sample_id": sid, "分组": fr["分组"],
        "★ 人工规范真值": _truth,
        "★ 口径A 主口径": _A,
        "★ 口径B 任一批次confirmed": _B,
        "★ 口径C 全部批次一致": _C,
        "★ 全部批次判定": [{"batch": r["batch"], "L2": r["L2"], "det": r["det"],
                       "side": r["side"]} for r in _recs],
        "★ 真实API判定集合": sorted(set(_vs)),
        "★ 跨批不一致": len(set(_vs)) > 1,
        "★ 出现过 confirmed": "confirmed" in _vs,
    })


def _prec(rs, key):
    _c = [r for r in rs if r[key] == "confirmed"]
    _ok = [r for r in _c if r["★ 人工规范真值"] == "valid_confirmed"]
    _rej = [r for r in rs if r[key] == "rejected"]
    _miss = [r for r in _rej if r["★ 人工规范真值"] == "valid_confirmed"]
    return {
        "★ 分母(confirmed)": len(_c),
        "★ confirmed 正确": len(_ok),
        "★ confirmed precision": (round(len(_ok) / len(_c), 4) if _c else "N/A"),
        "★ 分母(rejected)": len(_rej),
        "★ 错误拒收": len(_miss),
        "★ 错误拒收率": (round(len(_miss) / len(_rej), 4) if _rej else "N/A"),
    }


print("  ★ 三种主口径对比（★ 全部有模型状态的样本）：")
_cmp = {}
for _k, _key in (("A 主口径（优先级最高批次）", "★ 口径A 主口径"),
                  ("B 任一批次出现 confirmed", "★ 口径B 任一批次confirmed"),
                  ("C 仅全部批次一致者可用", "★ 口径C 全部批次一致")):
    _rs = [r for r in rows if r[_key] != "★ N/A" and r[_key] != "★ 跨批不一致"]
    _cmp[_k] = _prec(_rs, _key)
    print(f"      {_k}: {json.dumps(_cmp[_k], ensure_ascii=False)}")

# ★ 逐批次口径（★ 看结论是否随批次漂移）
print()
print("  ★ 逐批次口径（★ 单批次分析）：")
_batches = sorted({r["batch"] for r in rows for r in r["★ 全部批次判定"]})
_by_batch = {}
for _b in _batches:
    _rs = []
    for r in rows:
        _hit = [x for x in r["★ 全部批次判定"] if x["batch"] == _b and not x["det"]]
        if _hit:
            _rs.append({"★ 人工规范真值": r["★ 人工规范真值"],
                        "★ L2": _hit[0]["L2"]})
    if not _rs:
        continue
    _cm = collections.Counter(x["★ L2"] for x in _rs)
    _by_batch[_b] = {"★ 样本数": len(_rs), "★ L2 分布": dict(_cm),
                     "★ confirmed precision": _prec(_rs, "★ L2")["★ confirmed precision"],
                     "★ 错误拒收率": _prec(_rs, "★ L2")["★ 错误拒收率"]}
    print(f"      {_b:22s} n={len(_rs):2d}｜{dict(_cm)}｜"
          f"confirmed prec={_by_batch[_b]['★ confirmed precision']}｜"
          f"误拒率={_by_batch[_b]['★ 错误拒收率']}")

# ★ 出现过 confirmed 的候选
_conf_seen = [r for r in rows if r["★ 出现过 confirmed"]]
print()
print(f"  ★ ★ 出现过 confirmed 的候选 = {len(_conf_seen)}")
for r in _conf_seen:
    print(f"      {r['sample_id'][:26]:28s} {r['分组']} 真值={str(r['★ 人工规范真值'])[:20]:22s}"
          f" 判定集合={r['★ 真实API判定集合']}")

# ★ 跨批不一致的候选（★ 与人工真值交叉）
_incons = [r for r in rows if r["★ 跨批不一致"]]
_ci_vc = [r for r in _incons if r["★ 人工规范真值"] == "valid_confirmed"]
print()
print(f"  ★ 跨批不一致候选 = {len(_incons)}｜其中人工判 valid_confirmed = {len(_ci_vc)}")

(OUTD / "N1-B_主口径敏感性.json").write_text(json.dumps({
    "★ 三口径对比": _cmp,
    "★ 逐批次口径": _by_batch,
    "★ 出现过 confirmed 的候选": _conf_seen,
    "★ 跨批不一致候选数": len(_incons),
    "★ 跨批不一致且人工判成立": len(_ci_vc),
    "★ ★ 结论": ("★ 主口径选择会显著影响结论 ⇒ ★ **必须同时报告多口径**，"
               "★ 不得只报单一口径"),
}, ensure_ascii=False, indent=2), encoding="utf-8")
(OUTD / "N1-B_口径敏感性逐样本.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
print(f"\n  ⇒ {OUTD/'N1-B_主口径敏感性.json'}")
