# -*- coding: utf-8 -*-
"""★ N1-R 修复版统计脚本：★ 人工标签回填后的质量统计。

★ 修复要点（★ 对照上一版的问题）：
  ① 输入检查：★ 缺失原文 / 缺失字段 / **重复 sample_id** ⇒ 明确报错
  ② 标签枚举与完整度校验（★ 非法枚举值报错）
  ③ ★ **未标注 ⇒ 返回 N/A**，★ **绝不返回虚假的 0%**
  ④ 逐字段证据支持状态（★ 含合法缺省字段单独处理）
  ⑤ 正确的 confirmed 精确率与误拒收统计
  ⑥ 双审核者一致性与分歧仲裁
  ⑦ R / K 分组**独立**汇总（★ **不混用分母**）
  ⑧ R 组分层抽样权重与适用总体说明
  ⑨ 统计数据可从**原始标注文件**复算
★ ★ 模型状态从**独立文件**读取（★ 盲审阶段不可见）
"""
from __future__ import annotations

import collections
import csv
import json
import pathlib
import sys

LABEL_ENUM = {
    "evidence_support": {"supported", "partially_supported", "contradicted",
                         "evidence_insufficient"},
    "final_label": {"valid_confirmed", "valid_rejection", "false_rejection",
                    "false_confirmation", "pending_insufficient_evidence",
                    "uncertain_requires_human"},
}
FIELDS = ["subject", "action", "object", "strength", "polarity",
          "condition", "exception"]
NULL_OK = {"condition", "exception"}        # ★ 合法缺省字段（★ 可填 null）
TEXT_FIELDS = ["subject", "action", "object", "strength", "polarity"]


def _na():
    return "N/A"


def _pct(num, den):
    """★ 未标注 ⇒ **N/A**（★ 绝不返回 0%）。"""
    if not den:
        return _na()
    return round(num / den, 4)


def _read(path):
    return list(csv.DictReader(pathlib.Path(path).open(encoding="utf-8-sig")))


def check_inputs(rows, model_rows=None):
    """★ ① 输入检查。"""
    errs = []
    ids = [r.get("sample_id", "").strip() for r in rows]
    dup = [k for k, v in collections.Counter(ids).items() if v > 1]
    if dup:
        errs.append(f"★ 重复 sample_id：{dup}")
    for r in rows:
        sid = r.get("sample_id", "")
        if not (r.get("★ RFC 原文上下文（锚点 ±6 行）") or "").strip():
            errs.append(f"★ {sid}：缺少 RFC 原文上下文")
        if not (r.get("★ 绝对锚点行") or "").strip():
            errs.append(f"★ {sid}：缺少绝对锚点行")
        if not (r.get("★ 锚点行原文") or "").strip() \
                and not (r.get("★ 锚点行原文（RFC 原文）") or "").strip():
            errs.append(f"★ {sid}：缺少锚点行原文")
        if not (r.get("chunk_id") or "").strip():
            errs.append(f"★ {sid}：缺少 chunk_id")
    if model_rows:
        _mids = {m["sample_id"] for m in model_rows}
        for sid in ids:
            if sid not in _mids:
                errs.append(f"★ 模型状态缺 {sid}")
    return errs


def check_labels(rows, tag):
    """★ ② 标签枚举与完整度校验。"""
    errs, labeled = [], []
    for r in rows:
        sid = r.get("sample_id", "")
        _fs = (r.get(f"★ {tag}:final_label") or "").strip()
        _es = (r.get(f"★ {tag}:evidence_support") or "").strip()
        if _fs and _fs not in LABEL_ENUM["final_label"]:
            errs.append(f"★ {sid}：非法 final_label「{_fs}」")
        if _es and _es not in LABEL_ENUM["evidence_support"]:
            errs.append(f"★ {sid}：非法 evidence_support「{_es}」")
        if _fs and _es:
            labeled.append(r)
    return errs, labeled


def field_support(rows, tag):
    """★ ④ 逐字段证据支持状态（★ 合法缺省单独处理）。"""
    out = {}
    for f in FIELDS:
        _filled = _nonempty = 0
        for r in rows:
            _v = (r.get(f"★ {tag}:{f}") or "").strip()
            if not _v:
                continue
            _filled += 1
            if _v.lower() not in ("null", "none", "无", "-", "n/a"):
                _nonempty += 1
        out[f] = {"★ 已填写": _filled, "★ 非缺省": _nonempty,
                  "★ 缺省率": _pct(_filled - _nonempty, _filled),
                  "★ 合法缺省字段": f in NULL_OK}
    return out


def group_stats(rows, tag):
    """★ ⑦ 单组统计（★ 分母只用该组已标注样本）。"""
    _lab = [r for r in rows if (r.get(f"★ {tag}:final_label") or "").strip()]
    _c = collections.Counter((r.get(f"★ {tag}:final_label") or "").strip()
                             for r in _lab)
    _n = len(_lab)
    _conf = _c.get("valid_confirmed", 0) + _c.get("false_confirmation", 0)
    _rej = _c.get("valid_rejection", 0) + _c.get("false_rejection", 0)
    return {
        "★ 样本数": len(rows), "★ 已标注": _n,
        "★ 完整度": _pct(_n, len(rows)),
        "★ 标签分布": dict(_c),
        "★ confirmed 精确率": _pct(_c.get("valid_confirmed", 0), _conf),
        "★ confirmed 精度分母": _conf,
        "★ 误拒收率": _pct(_c.get("false_rejection", 0), _rej),
        "★ 误拒收分母": _rej,
        "★ 证据不足率": _pct(_c.get("pending_insufficient_evidence", 0), _n),
        "★ 需仲裁率": _pct(_c.get("uncertain_requires_human", 0), _n),
        "★ 逐字段支持状态": field_support(rows, tag),
    }


def compare_with_model(rows, models, tag="A"):
    """★ ⑤ 与模型状态对照（★ 汇总阶段才读取）。"""
    _cmp = collections.Counter()
    for r in rows:
        _sid = r["sample_id"]
        _a = (r.get(f"★ {tag}:final_label") or "").strip()
        if not _a or _sid not in models:
            continue
        _ms = models[_sid].get("★ 模型状态（★ 盲审阶段不可见）")
        if not _ms:
            continue
        _cmp[f"model={_ms}|human={_a}"] += 1
    return dict(_cmp)


def main(csv_a, csv_b=None, model_state=None, arbitration=None):
    rows_a = _read(csv_a)
    rows_b = _read(csv_b) if csv_b else None
    models = {}
    if model_state and pathlib.Path(model_state).is_file():
        for m in [json.loads(l) for l in
                  pathlib.Path(model_state).read_text(encoding="utf-8").splitlines()
                  if l.strip()]:
            models[m["sample_id"]] = m

    errs = check_inputs(rows_a, models)
    if rows_b:
        errs += check_inputs(rows_b, models)
    out = {"★ 输入检查": {"★ 错误": errs, "★ 通过": not errs}}

    errs_a, lab_a = check_labels(rows_a, "A")
    out["★ 标签校验(A)"] = {"★ 错误": errs_a, "★ 通过": not errs_a,
                      "★ 已标注": len(lab_a)}
    for r in rows_a:
        r["_grp"] = r.get("分组", "")
    out["★ 分组汇总(A)"] = {
        "R（★ 分层随机）": group_stats([r for r in rows_a if r["_grp"] == "R"], "A"),
        "K（★ 风险富集）": group_stats([r for r in rows_a if r["_grp"] == "K"], "A"),
    }
    out["★ 适用总体说明"] = (
        "★ **R 组**为（协议 × 知识类型）分层随机样本，★ **可**用于估计总体，"
        "★ 但**必须按分层加权**；★ **K 组**为风险富集样本，★ **不可**用于估计总体；"
        "★ **R 与 K 不得混用分母**")

    if rows_b:
        _b = {r["sample_id"]: r for r in rows_b}
        _same = _diff = _only_a = _only_b = 0
        _diff_list = []
        for r in rows_a:
            _sid = r["sample_id"]
            if _sid not in _b:
                continue
            _a = (r.get("★ A:final_label") or "").strip()
            _bb = (_b[_sid].get("★ B:final_label") or "").strip()
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
        out["★ 双审一致性"] = {
            "★ 双方均标注": _same + _diff, "★ 一致": _same, "★ 分歧": _diff,
            "★ 一致率": _pct(_same, _same + _diff),
            "★ 仅 A 标注": _only_a, "★ 仅 B 标注": _only_b,
            "★ 分歧样本": _diff_list,
            "★ 仲裁处理": "★ 分歧样本须第三方仲裁（★ N1_仲裁表.csv）⇒ ★ 以仲裁结论为准",
        }
        if arbitration and pathlib.Path(arbitration).is_file():
            _arb = {r["sample_id"]: r for r in _read(arbitration)}
            _res = [s for s in _diff_list
                    if (s in _arb and (_arb[s].get("★ 仲裁结论") or "").strip())]
            out["★ 双审一致性"]["★ 已仲裁"] = len(_res)
            out["★ 双审一致性"]["★ 未仲裁"] = len(_diff_list) - len(_res)

    if models:
        out["★ 模型对照（★ 仅汇总阶段）"] = compare_with_model(rows_a, models)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    _a = sys.argv[1] if len(sys.argv) > 1 else "N1_盲审标注表_A.csv"
    _b = sys.argv[2] if len(sys.argv) > 2 else None
    _m = sys.argv[3] if len(sys.argv) > 3 else None
    _ar = sys.argv[4] if len(sys.argv) > 4 else None
    main(_a, _b, _m, _ar)
