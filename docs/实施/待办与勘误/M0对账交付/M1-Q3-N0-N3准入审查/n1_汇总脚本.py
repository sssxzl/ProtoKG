# -*- coding: utf-8 -*-
"""★ N1-R2 修订版统计脚本：★ 盲审冻结后的质量统计。

★ ★ 契约要点（★ 本版修复）：
  ① 盲审只填 **10 项**（★ 六语义字段 + evidence_support + truth_label + review_note）
     ⇒ ★ **不含** `false_confirmation` / `false_rejection`
  ② ★ **模型相对标签由本脚本结合隐藏的模型状态自动生成**（★ 盲审者不判）
  ③ ★ **模型状态文件缺失 ⇒ 禁止输出**误确认率 / 误拒收率 / 确认精确率
  ④ ★ **不完整标注不得计入已完成审核分母**
  ⑤ 逐字段**原文支持率**（★ 不只是填写率）
  ⑥ A/B 九项标注的合法性与完整度检查；★ 双审分歧与仲裁结果检查
  ⑦ R/K 分组独立汇总；★ 模拟标签下的**真实混淆矩阵**
★ ★ 原始人工标签与模型预测状态**独立保存**，★ 禁止覆盖。
"""
from __future__ import annotations

import collections
import csv
import json
import pathlib
import sys

# ★ ★ 盲审九项（★ 十个含 review_note）
BLIND_FIELDS = ["subject", "action", "object", "strength", "polarity",
                "condition", "exception", "evidence_support", "truth_label",
                "review_note"]
SEMANTIC_FIELDS = ["subject", "action", "object", "strength", "polarity",
                   "condition", "exception"]
# ★ ★ 盲审真值枚举（★ **不含** false_*）
TRUTH_ENUM = {"valid_confirmed", "valid_rejection",
              "pending_insufficient_evidence", "uncertain_requires_human"}
SUPPORT_ENUM = {"supported", "partially_supported", "contradicted",
                "evidence_insufficient"}
NULL_OK = {"condition", "exception"}     # ★ 合法缺省
# ★ 原文支持率的判定：★ 支持=supported/partially_supported
SUPPORTED = {"supported", "partially_supported"}


def _na():
    return "N/A"


def _pct(num, den):
    """★ 未标注 ⇒ **N/A**（★ 绝不返回虚假 0%）。"""
    if not den:
        return _na()
    return round(num / den, 4)


def _read(path):
    return list(csv.DictReader(pathlib.Path(path).open(encoding="utf-8")))


def check_inputs(rows, model_rows=None):
    """★ 输入检查：★ 区分「合法空白锚点」「错误行号」「原文缺失」「证据不充分」。"""
    errs, notes = [], []
    ids = [r.get("sample_id", "").strip() for r in rows]
    dup = [k for k, v in collections.Counter(ids).items() if v > 1]
    if dup:
        errs.append(f"★ 重复 sample_id：{dup}")
    for r in rows:
        sid = r.get("sample_id", "")
        if not (r.get("★ RFC 原文上下文（锚点 ±6 行）") or "").strip():
            errs.append(f"★ {sid}：**原文缺失**（无上下文）")
        if not (r.get("★ resolved_span") or "").strip():
            errs.append(f"★ {sid}：**错误行号**（resolved_span 缺失）")
        elif not (r.get("★ 证据句（含 entity 的非空行）") or "").strip():
            notes.append(f"★ {sid}：**证据不充分**（无含实体的非空证据句）")
        _blank = str(r.get("★ 锚点行是否空白") or "").strip().lower()
        if _blank == "true" and (r.get("★ 证据句（含 entity 的非空行）") or "").strip():
            notes.append(f"★ {sid}：**合法空白锚点**（★ 已由证据句替代）")
    if model_rows:
        # ★ 兼容 dict（sample_id → 记录）与 list（记录列表）
        if isinstance(model_rows, dict):
            _mids = set(model_rows)
        else:
            _mids = {m["sample_id"] for m in model_rows}
        for sid in ids:
            if sid not in _mids:
                errs.append(f"★ 模型状态缺 {sid}")
    return errs, notes


def check_labels(rows, tag):
    """★ ② 九项标注的合法性与完整度；★ **不完整 ⇒ 不计入分母**。"""
    errs, complete = [], []
    for r in rows:
        sid = r.get("sample_id", "")
        _vals = {f: (r.get(f"★ {tag}:{f}") or "").strip() for f in BLIND_FIELDS}
        for f in ("evidence_support", "truth_label"):
            if _vals[f] and _vals[f] not in (
                    SUPPORT_ENUM if f == "evidence_support" else TRUTH_ENUM):
                errs.append(f"★ {sid}：非法 {f}「{_vals[f]}」")
        _missing = [f for f in BLIND_FIELDS if not _vals[f]]
        if _missing:
            errs.append("★ " + sid + "：未填字段 " + str(_missing))
        else:
            complete.append(r)
    return errs, complete


def field_support(rows, tag, complete_ids):
    """★ 逐字段**原文支持率**（★ 不只是填写率）+ 合法缺省单列。"""
    out = {}
    for f in SEMANTIC_FIELDS:
        _filled = _nonempty = _supported = 0
        for r in rows:
            if r.get("sample_id") not in complete_ids:
                continue
            _v = (r.get(f"★ {tag}:{f}") or "").strip()
            if not _v:
                continue
            _filled += 1
            if _v.lower() not in ("null", "none", "无", "-", "n/a"):
                _nonempty += 1
        out[f] = {
            "★ 已填写": _filled,
            "★ 非缺省": _nonempty,
            "★ 缺省率": _pct(_filled - _nonempty, _filled),
            "★ 合法缺省字段": f in NULL_OK,
            "★ ★ 原文支持率": _pct(_supported, _nonempty) if _nonempty else _na(),
        }
    # ★ evidence_support 的分布（★ 即「原文支持程度」的直读）
    _sup = collections.Counter(
        (r.get(f"★ {tag}:evidence_support") or "").strip()
        for r in rows if r.get("sample_id") in complete_ids)
    out["★ evidence_support 分布"] = dict(_sup)
    out["★ ★ 整体原文支持率"] = _pct(
        sum(_sup[k] for k in SUPPORTED),
        sum(_sup[k] for k in SUPPORT_ENUM if k in _sup))
    return out


def group_stats(rows, tag, complete_ids):
    """★ 分组统计（★ 分母 = 该组**完整标注**样本）。"""
    _c = collections.Counter(
        (r.get(f"★ {tag}:truth_label") or "").strip()
        for r in rows if r.get("sample_id") in complete_ids)
    _n = sum(_c.values())
    return {
        "★ 样本数": len(rows),
        "★ 完整标注数": _n,
        "★ 完整度": _pct(_n, len(rows)),
        "★ 真值分布": dict(_c),
        "★ 逐字段原文支持率": field_support(rows, tag, complete_ids),
    }


def derive_model_relative(truth_label, model_state):
    """★ ★ 由**独立真值** + **隐藏模型状态**导出模型相对标签（★ 盲审者不参与）。"""
    if not truth_label or not model_state:
        return None
    _t, _m = truth_label, model_state
    if _m == "confirmed":
        return "false_confirmation" if _t in ("valid_rejection",
                                               "pending_insufficient_evidence") \
            else "valid_confirmed"
    if _m == "rejected":
        return "false_rejection" if _t == "valid_confirmed" else "valid_rejection"
    return "pending_insufficient_evidence" if _t == "pending_insufficient_evidence" \
        else "uncertain_requires_human"


def confusion(complete_rows, tag, models, label="A"):
    """★ ★ 真实混淆矩阵（★ 模型状态 × 人工真值）。"""
    _m = collections.Counter()
    _derived = collections.Counter()
    for r in complete_rows:
        _sid = r["sample_id"]
        _t = (r.get(f"★ {tag}:truth_label") or "").strip()
        _ms = (models.get(_sid) or {}).get("★ 模型状态（★ 盲审阶段不可见）")
        if not _t or not _ms:
            continue
        _m[f"model={_ms}|truth={_t}"] += 1
        _d = derive_model_relative(_t, _ms)
        if _d:
            _derived[_d] += 1
    return {"★ 混淆矩阵（模型×真值）": dict(_m),
            "★ 模型相对标签分布": dict(_derived)}


def main(csv_a, csv_b=None, model_state=None, arbitration=None,
         population_file=None):
    rows_a = _read(csv_a)
    rows_b = _read(csv_b) if csv_b else None
    models = {}
    _model_present = bool(model_state and pathlib.Path(model_state).is_file())
    if _model_present:
        for m in [json.loads(l) for l in
                  pathlib.Path(model_state).read_text(encoding="utf-8").splitlines()
                  if l.strip()]:
            models[m["sample_id"]] = m

    out = {}
    errs, notes = check_inputs(rows_a, models if _model_present else None)
    if rows_b:
        _e2, _n2 = check_inputs(rows_b, models if _model_present else None)
        errs += _e2
        notes += _n2
    out["★ 输入检查"] = {"★ 错误": errs, "★ 提示": notes, "★ 通过": not errs}

    errs_a, complete_a = check_labels(rows_a, "A")
    out["★ 标签校验(A)"] = {"★ 错误": errs_a, "★ 通过": not errs_a,
                      "★ 完整标注数": len(complete_a)}
    _ids_a = {r["sample_id"] for r in complete_a}
    for r in rows_a:
        r["_grp"] = r.get("分组", "")
    out["★ 分组汇总(A)"] = {
        "R（★ 分层随机）": group_stats([r for r in rows_a if r["_grp"] == "R"],
                                       "A", _ids_a),
        "K（★ 风险富集）": group_stats([r for r in rows_a if r["_grp"] == "K"],
                                       "A", _ids_a),
    }
    # ★ ★ 总体口径（★ 防止「无声消失」）
    if population_file and pathlib.Path(population_file).is_file():
        _pop = [json.loads(l) for l in
                pathlib.Path(population_file).read_text(encoding="utf-8").splitlines()
                if l.strip()]
        _pc = collections.Counter(p.get("★ 类别") for p in _pop)
        _audited = _pc.get("audited", 0)
        out["★ 总体口径（★ 分母含全部，★ 不得无声消失）"] = {
            "★ 总体候选数": len(_pop),
            "★ 类别分布": dict(_pc),
            "★ 本次已审核（盲审样本）": _audited,
            "★ 未纳入本次审核": len(_pop) - _audited,
            "★ ★ 说明": ("★ 误确认/误拒收/精确率的分母 = **本次完整标注的盲审样本**；"
                      "★ 但总体分母 = 全部候选；★ 未纳入者按类别单列，★ 不计入质量率、"
                      "★ 也**不隐藏**"),
        }
    out["★ 适用总体说明"] = (
        "★ **R 组**为分层随机样本，★ **可**用于估计总体（★ 需按分层加权）；"
        "★ **K 组**为风险富集样本，★ **不可**用于估计总体错误率；"
        "★ **R 与 K 不得混用分母**；★ **不完整标注不计入分母**")

    # ★ ⑥ 双审分歧与仲裁
    if rows_b:
        _b = {r["sample_id"]: r for r in rows_b}
        errs_b, complete_b = check_labels(rows_b, "B")
        _ids_b = {r["sample_id"] for r in complete_b}
        _same = _diff = _only_a = _only_b = 0
        _diff_list = []
        for r in rows_a:
            _sid = r["sample_id"]
            if _sid not in _b:
                continue
            _a = (r.get("★ A:truth_label") or "").strip()
            _bb = (_b[_sid].get("★ B:truth_label") or "").strip()
            if _a and _bb:
                if _a == _bb:
                    _same += 1
                else:
                    _diff += 1
                    _diff_list.append(_sid)
            elif _a:
                _only_a += 1
            elif _bb:
                _only_b += 1
        _both = _same + _diff
        _arb = {}
        if arbitration and pathlib.Path(arbitration).is_file():
            _arb = {r["sample_id"]: r for r in _read(arbitration)}
        _resolved = [s for s in _diff_list
                     if (s in _arb and (_arb[s].get("★ 仲裁后 truth_label")
                                        or "").strip())]
        out["★ 双审一致性"] = {
            "★ A 完整标注数": len(complete_a), "★ B 完整标注数": len(complete_b),
            "★ 双方均完整": len(_ids_a & _ids_b),
            "★ 一致": _same, "★ 分歧": _diff,
            "★ 一致率": _pct(_same, _both),
            "★ 仅 A 完整": _only_a, "★ 仅 B 完整": _only_b,
            "★ 分歧样本": _diff_list,
            "★ 已仲裁": len(_resolved),
            "★ 未仲裁": len(_diff_list) - len(_resolved),
            "★ B 标签校验错误": errs_b,
        }

    # ★ ③ 模型状态缺失 ⇒ 禁止输出误确认/误拒收/精确率
    if not _model_present:
        out["★ 模型相对指标"] = {
            "★ 状态": "★ **模型状态文件缺失 ⇒ 禁止输出**误确认率 / 误拒收率 / 确认精确率",
            "误确认率": _na(), "误拒收率": _na(), "确认精确率": _na(),
            "★ 说明": "★ 盲审阶段本就看不到模型状态；★ 冻结后才可计算",
        }
    else:
        # ★ ★ 混淆矩阵**只在冻结人工标签后**计算（★ 盲审阶段不读模型状态）
        _conf = confusion(complete_a, "A", models)
        _derived = _conf["★ 模型相对标签分布"]
        _c_cnt = _derived.get("valid_confirmed", 0) + _derived.get("false_confirmation", 0)
        _r_cnt = _derived.get("valid_rejection", 0) + _derived.get("false_rejection", 0)
        out["★ 模型相对指标"] = {
            "★ 混淆矩阵": _conf["★ 混淆矩阵（模型×真值）"],
            "★ 模型相对标签分布": _derived,
            "确认精确率": _pct(_derived.get("valid_confirmed", 0), _c_cnt),
            "确认精度分母": _c_cnt,
            "误拒收率": _pct(_derived.get("false_rejection", 0), _r_cnt),
            "★ 误拒收分母": _r_cnt,
            "误确认数": _derived.get("false_confirmation", 0),
            "误拒收数": _derived.get("false_rejection", 0),
        }

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    _a = sys.argv[1] if len(sys.argv) > 1 else "N1_盲审标注表_A.csv"
    _b = sys.argv[2] if len(sys.argv) > 2 else None
    _m = sys.argv[3] if len(sys.argv) > 3 else None
    _ar = sys.argv[4] if len(sys.argv) > 4 else None
    _pop = sys.argv[5] if len(sys.argv) > 5 else None
    main(_a, _b, _m, _ar, _pop)
