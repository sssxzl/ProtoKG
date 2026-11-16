# -*- coding: utf-8 -*-
"""★ N1-C 阶段：★ **独立评估脚本（★ 指标与输出格式已在揭盲前冻结）**。

★ ★ 本脚本在**收到 N1-C 人工真值之前不得运行评估部分**（★ 只做输入契约校验）。
★ ★ 揭盲后**仅执行一次**冻结版本的独立评估。

★ ══ 冻结的指标定义（★ 分子/分母/适用样本）══

★ **层一：确定性影子层（★ 不依赖模型状态）**
★  · 适用样本 = N1-C 全部 50 条（★ 只要有候选字段 + 原文即可算）
★  · M1 人工成立候选的**直接误拒** = V1 路由=rejected ∧ truth=valid_confirmed
★  · M2 人工不成立候选的**正确拒收** = V1 路由=rejected ∧ truth≠valid_confirmed
★  · M3 无效候选进入 pending / routed_to_LLM 的数量
★  · M4 有效候选进入 pending / routed_to_LLM 的数量
★  · M5 routed_to_LLM 的**潜在**调用数量（★ **不得计为已执行调用**）
★  · M6 候选质量分层（★ 按 evidence_support：fully_supported / partially_supported / …）

★ **层二：模型相对层（★ 依赖冻结模型状态）**
★  · 适用样本 = ★ **仅 N1-C 中有冻结模型状态者**；★ 其余 **N/A**
★  · M7 confirmed 变化及其关键字段完整性
★  · M8 三态判断与知识类型闸门的**错误归因**

★ ★ **不得补造历史模型状态；★ 不得重新调用 LLM**
"""
import collections
import csv
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
OUTD = ROOT / "guard/_out/_n1c"
sys.path.insert(0, str(ROOT / "guard/_out/_n1c"))

TRUTH_ENUM = {"valid_confirmed", "valid_rejection",
              "pending_insufficient_evidence", "uncertain_requires_human"}
SUP_ENUM = {"supported", "partially_supported", "contradicted",
            "evidence_insufficient"}
BLIND_FIELDS = ["subject", "action", "object", "strength", "polarity",
                "condition", "exception", "evidence_support", "truth_label",
                "review_note"]
QUALITY_MAP = {"supported": "fully_supported",
               "partially_supported": "partially_supported",
               "contradicted": "contradicted",
               "evidence_insufficient": "evidence_insufficient"}


def _read(p):
    return list(csv.DictReader(pathlib.Path(p).read_text(encoding="utf-8").splitlines()))


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def validate_inputs(csv_a, csv_b, csv_arb):
    """★ 输入契约校验（★ 揭盲前也可运行）。"""
    _errs = []
    _a, _b, _arb = _read(csv_a), _read(csv_b), _read(csv_arb)
    _ids = {r["sample_id"] for r in _a}
    if len(_a) != 50:
        _errs.append(f"★ A 表应为 50 条（★ 实 {_len(_a) if False else len(_a)}）")
    if _ids != {r["sample_id"] for r in _b}:
        _errs.append("★ A/B sample_id 不一致")
    if _ids != {r["sample_id"] for r in _arb}:
        _errs.append("★ A/仲裁 sample_id 不一致")
    # ★ 标签合法性
    for _rows, _tag in ((_a, "A"), (_b, "B")):
        for _r in _rows:
            _t = (_r.get(f"★ {_tag}:truth_label") or "").strip()
            _e = (_r.get(f"★ {_tag}:evidence_support") or "").strip()
            if _t and _t not in TRUTH_ENUM:
                _errs.append(f"★ {_r['sample_id']}：非法 truth_label「{_t}」")
            if _e and _e not in SUP_ENUM:
                _errs.append(f"★ {_r['sample_id']}：非法 evidence_support「{_e}」")
    return _a, _b, _arb, _errs


def freeze_artifact_check(csv_a, csv_b, csv_arb):
    """★ 盲审包哈希须与发放清单一致（★ 防止发放后被改动）。"""
    _p = OUTD / "n1c_pack_hashes.json"
    if not _p.is_file():
        return None
    _known = json.loads(_p.read_text(encoding="utf-8"))
    _now = {"N1-C_盲审标注表_A.csv": _sha(csv_a),
            "N1-C_盲审标注表_B.csv": _sha(csv_b),
            "N1-C_仲裁表.csv": _sha(csv_arb)}
    return {k: {"发放时": _known.get(k), "当前": v,
                "一致": _known.get(k) == v} for k, v in _now.items()}


def evaluate(csv_a, csv_b, csv_arb, model_state_path, v0v1_csv):
    """★ ★ **揭盲后仅执行一次**的独立评估（★ 指标按上文冻结定义）。

    ★ 层一（确定性影子）不依赖模型状态；★ 层二（模型相对）**仅对有冻结状态者**，★ 其余 N/A
    """
    _a, _b, _arb, _errs = validate_inputs(csv_a, csv_b, csv_arb)
    if _errs:
        raise SystemExit("★ 输入契约校验失败：\n  " + "\n  ".join(_errs))
    _am = {r["sample_id"]: r for r in _a}
    _bm = {r["sample_id"]: r for r in _b}
    _arb_map = {r["sample_id"]: r for r in _arb}
    _v0v1 = {r["candidate_id"]: r for r in _read(v0v1_csv)}

    # ★ ★ 冻结真值：★ 优先仲裁表 → 其次 A=B → 其次单侧 → 否则未解决
    _frozen = {}
    for _sid in sorted(_am):
        _av = (_am[_sid].get("★ A:truth_label") or "").strip()
        _bv = (_bm[_sid].get("★ B:truth_label") or "").strip()
        _arbv = (_arb_map[_sid].get("★ 仲裁后 truth_label") or "").strip()
        if _arbv:
            _tv, _src = _arbv, "arbitration"
        elif _av and _bv and _av == _bv:
            _tv, _src = _av, "A=B"
        elif _av and _bv:
            _tv, _src = None, "disagreement_unresolved"
        elif _av or _bv:
            _tv, _src = _av or _bv, "single_reviewer"
        else:
            _tv, _src = None, "unlabeled"
        _ea = (_am[_sid].get("★ A:evidence_support") or "").strip()
        _eb = (_bm[_sid].get("★ B:evidence_support") or "").strip()
        _es = _ea if (_ea and _ea == _eb) else (_ea or _eb)
        _frozen[_sid] = {"truth_label": _tv, "truth_source": _src,
                        "evidence_support": _es,
                        "quality": QUALITY_MAP.get(_es, "unknown")}

    # ★ 模型状态（★ 仅 N1-C 中有冻结状态者；★ 其余 N/A）
    _models = {}
    if model_state_path and pathlib.Path(model_state_path).is_file():
        for l in pathlib.Path(model_state_path).read_text(encoding="utf-8").splitlines():
            if l.strip():
                _d = json.loads(l)
                _models[_d["sample_id"]] = _d.get("★ 模型状态（★ 盲审阶段不可见）")

    rows = []
    for _sid in sorted(_frozen):
        _f = _frozen[_sid]
        _v = _v0v1.get(_sid, {})
        _r0, _r1 = _v.get("★ V0 路由"), _v.get("★ V1 路由")
        _ms = _models.get(_sid)
        rows.append({
            "sample_id": _sid,
            "★ 冻结真值": _f["truth_label"] or "★ 未解决",
            "★ 真值来源": _f["truth_source"],
            "★ evidence_support": _f["evidence_support"] or "★ 空",
            "★ 候选质量": _f["quality"],
            "★ V0 路由": _r0 or "★ N/A",
            "★ V1 路由": _r1 or "★ N/A",
            "★ 冻结模型状态": _ms if _ms else "★ N/A（★ 无冻结模型状态）",
        })

    # ══ 层一：确定性影子指标 ══
    def _layer1(route_key):
        _out = collections.defaultdict(collections.Counter)
        for r in rows:
            _t = r["★ 冻结真值"]
            _valid = (_t == "valid_confirmed")
            _out[r[route_key]][("有效" if _valid else "无效")] += 1
        return _out

    _l0, _l1 = _layer1("★ V0 路由"), _layer1("★ V1 路由")

    def _m(route):
        _o = _l1.get(route, collections.Counter())
        _valid, _invalid = _o.get("有效", 0), _o.get("无效", 0)
        return {"★ 有效候选": _valid, "★ 无效候选": _invalid,
                "★ 合计": _valid + _invalid}

    _metrics = {
        "★ M1 人工成立候选的直接误拒": {
            "★ 定义": "★ V1 路由=rejected ∧ 冻结真值=valid_confirmed",
            "★ V1": _m("★ rejected").get("★ 有效候选", 0),
            "★ V0（对照）": _m("★ rejected").get("★ 有效候选", 0)},
        "★ M2 人工不成立候选的正确拒收": {
            "★ 定义": "★ V1 路由=rejected ∧ 冻结真值≠valid_confirmed",
            "★ V1": _m("★ rejected").get("★ 无效候选", 0),
            "★ V0（对照）": _m("★ rejected").get("★ 无效候选", 0)},
        "★ M3 无效候选进入 pending / routed_to_LLM": {
            "★ 定义": "★ 冻结真值≠valid_confirmed 且路由为 pending / routed_to_LLM",
            "★ V1 pending": _m("★ pending").get("★ 无效候选", 0),
            "★ V1 routed_to_LLM": _m("★ routed_to_LLM").get("★ 无效候选", 0),
            "★ V0 pending": dict(_l0.get("★ pending", {})).get("无效", 0),
            "★ V0 routed_to_LLM": dict(_l0.get("★ routed_to_LLM", {})).get("无效", 0)},
        "★ M4 有效候选进入 pending / routed_to_LLM": {
            "★ 定义": "★ 冻结真值=valid_confirmed 且路由为 pending / routed_to_LLM",
            "★ V1 pending": _m("★ pending").get("★ 有效候选", 0),
            "★ V1 routed_to_LLM": _m("★ routed_to_LLM").get("★ 有效候选", 0),
            "★ V0 pending": dict(_l0.get("★ pending", {})).get("有效", 0),
            "★ V0 routed_to_LLM": dict(_l0.get("★ routed_to_LLM", {})).get("有效", 0)},
        "★ M5 routed_to_LLM 的潜在调用数量": {
            "★ 定义": "★ routed_to_LLM 的条数（★ **潜在量**）",
            "★ V1": _m("★ routed_to_LLM").get("★ 合计", 0),
            "★ V0": dict(_l0.get("★ routed_to_LLM", {})).get("有效", 0)
                  + dict(_l0.get("★ routed_to_LLM", {})).get("无效", 0),
            "★ ★ 实际执行": "★ **0**（★ 本轮不调用 LLM）"},
        "★ M6 候选质量分层（★ 按 evidence_support）": {
            _q: dict(collections.Counter(
                r["★ V1 路由"] for r in rows if r["★ 候选质量"] == _q))
            for _q in sorted({r["★ 候选质量"] for r in rows})},
    }

    # ══ 层二：模型相对（★ 仅对有冻结模型状态者）══
    _with = [r for r in rows if r["★ 冻结模型状态"] != "★ N/A（★ 无冻结模型状态）"]
    _without = len(rows) - len(_with)
    _ms_cm = collections.Counter(
        (r["★ 冻结模型状态"], r["★ 冻结真值"]) for r in _with)
    _metrics["★ M7 confirmed 变化及其关键字段完整性"] = {
        "★ 适用样本": len(_with),
        "★ 无冻结模型状态（⇒ 该层 N/A）": _without,
        "★ 模型状态 × 人工真值 混淆": {f"model={k[0]}|truth={k[1]}": v
                             for k, v in sorted(_ms_cm.items())},
        "★ ★ 说明": ("★ 影子判据**无 confirmed 出口** ⇒ ★ 本层只反映**历史模型状态**与"
                 "★ 人工真值的关系；★ **不得**把影子结果当作模型 confirmed"),
    }
    _metrics["★ M8 三态判断与知识类型闸门的错误归因"] = {
        "★ 定义": ("★ 把「V1 判 supported 但人工判不成立」拆成："
                "★ (a) 知识类型闸门缺失（★ 如版权声明段落）"
                "★ (b) 字段不完整 / 跨句未解析（★ 需人工判读）"
                "★ (c) 真·误判"),
        "★ 待归因清单": [{"sample_id": r["sample_id"],
                     "★ V1 路由": r["★ V1 路由"],
                     "★ 冻结真值": r["★ 冻结真值"],
                     "★ 候选质量": r["★ 候选质量"],
                     "★ 归因": "★ 待人工/人工判定"}
                    for r in rows
                    if r["★ V1 路由"] == "★ routed_to_LLM"
                    and r["★ 冻结真值"] != "valid_confirmed"],
    }

    _out = {
        "★ 指标定义版本": "n1c-eval-v1（★ 揭盲前冻结）",
        "★ 样本数": len(rows),
        "★ 真值来源分布": dict(collections.Counter(
            r["★ 真值来源"] for r in rows)),
        "★ 指标": _metrics,
        "★ 逐候选": rows,
    }
    with (OUTD / "n1c_eval_result.json").open("w", encoding="utf-8") as f:
        json.dump(_out, f, ensure_ascii=False, indent=2)
    with (OUTD / "n1c_eval_result.csv").open("w", newline="",
                                          encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(json.dumps({k: v for k, v in _out.items() if k != "★ 逐候选"},
                     ensure_ascii=False, indent=2))
    return _out


def main():
    _a = DELIV / "N1-C_盲审标注表_A.csv"
    _b = DELIV / "N1-C_盲审标注表_B.csv"
    _arb = DELIV / "N1-C_仲裁表.csv"
    _print = sys.argv[1] if len(sys.argv) > 1 else "validate"
    if _print == "validate":
        _a_r, _b_r, _arb_r, _errs = validate_inputs(_a, _b, _arb)
        print(f"  ★ 输入契约：★ A {len(_a_r)} 条｜B {len(_b_r)} 条｜仲裁 {len(_arb_r)} 条")
        print(f"  ★ 错误 {len(_errs)} 项：{_errs or '★ 无'}")
        _h = freeze_artifact_check(_a, _b, _arb)
        if _h:
            print("  ★ 盲审包哈希核对：")
            for _k, _v in _h.items():
                print(f"      {_k:26s} 一致={_v['一致']}")
        raise SystemExit(1 if _errs else 0)
    elif _print == "evaluate":
        evaluate(_a, _b, _arb,
                 OUTD / "n1c_model_state.jsonl",
                 DELIV / "N2-B0-R_V0_V1逐候选对照.csv")


if __name__ == "__main__":
    main()
