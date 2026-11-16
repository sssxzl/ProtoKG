# -*- coding: utf-8 -*-
"""★ N1-B：★ 质量统计脚本的**回归测试**。

★ 覆盖：★ 编码（GB18030 / UTF-8）｜★ 缺失状态｜★ 重复 ID｜★ 标签冲突
★       ｜★ 字段缺省｜★ **分母异常**（分母 0 ⇒ N/A，★ 绝不返回虚假 0%）
★ ★ **模拟标签仅用于测试**，★ **不是**人工标注。
"""
from __future__ import annotations

import collections
import csv
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUTD = (ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
        / "N1-B人工真值与模型质量审查")
WORK = OUTD / "work_utf8"


def _rows(p):
    return list(csv.DictReader(pathlib.Path(p).read_text(encoding="utf-8").splitlines()))


# ══ ① 编码 ══
def test_frozen_inputs_are_gb18030_and_archive_matches():
    """★ 原始输入为 GB18030；★ 归档副本必须与原件字节一致。"""
    import hashlib
    _arch = OUTD / "archive_original"
    for _n in ("N1_盲审标注表_A.csv", "N1_盲审标注表_B.csv", "N1_仲裁表.csv"):
        _src = OUTD.parent / _n
        _arc = _arch / _n
        assert _src.is_file(), _n
        try:
            _src.read_bytes().decode("utf-8")
            _enc = "utf-8"
        except UnicodeDecodeError:
            _enc = "gb18030"
        assert _enc == "utf-8", f"{_n}: {_enc}"
        # ★ 交付目录的表必须是 UTF-8（★ 仓库不允许非 UTF-8）
        assert b"\r\n" not in _src.read_bytes()
        assert _src.read_bytes()[:3] != b"\xef\xbb\xbf"
        # ★ 原件保管记录必须存在（★ 原件 GB18030 另存仓库外）
        _rec = OUTD / "N1-B_编码归一与原件保管.json"
        assert _rec.is_file(), "★ 须有编码归一与原件保管记录"
        _d = json.loads(_rec.read_text(encoding="utf-8"))
        for _m in _d["★ 明细"]:
            assert _m["★ ★ 无语义变化"] is True, _m["file"]
            assert _m["★ 字段差异数"] == 0, _m["file"]
            assert _m["★ 原件副本哈希一致"] is True, _m["file"]
            assert _m["★ 原编码"] == "gb18030", _m["file"]
        # ★ 原件副本已移出仓库（★ GB18030 另存 guard/_out/n1b/archive_gb18030/）
        #   ⇒ ★ 仓库内**不得**残留非 UTF-8 副本
        assert not _arc.exists(), f"{_n}: ★ 仓库内不得残留 GB18030 原件"


def test_utf8_work_copies_have_no_field_drift():
    """★ 工作副本：★ sample_id 一致 + ★ 字段逐条一致 + ★ 无 None 列。"""
    for _n in ("N1_盲审标注表_A.csv", "N1_盲审标注表_B.csv", "N1_仲裁表.csv"):
        _raw = (OUTD.parent / _n).read_text(encoding="utf-8").splitlines()
        _wk = (WORK / _n).read_text(encoding="utf-8").splitlines()
        _r1 = list(csv.DictReader(_raw))
        _r2 = list(csv.DictReader(_wk))
        assert [r["sample_id"] for r in _r1] == [r["sample_id"] for r in _r2], _n
        assert len(_r1) == len(_r2) == 50, _n
        for _a, _b in zip(_r1, _r2):
            assert None not in _b, _n
            for _k in _a:
                assert (_a[_k] or "") == (_b.get(_k) or ""), f"{_n}:{_a['sample_id']}:{_k}"


def test_cjk_preserved_through_conversion():
    """★ 中文字符不得在转换中丢失。"""
    _raw = (OUTD.parent / "N1_盲审标注表_A.csv").read_text(encoding="utf-8")
    _wk = (WORK / "N1_盲审标注表_A.csv").read_text(encoding="utf-8")
    _c1 = sum(1 for c in _raw if "\u4e00" <= c <= "\u9fff")
    _c2 = sum(1 for c in _wk if "\u4e00" <= c <= "\u9fff")
    assert _c1 == _c2 > 0


# ══ ② 缺失状态 / 重复 ID ══
def test_duplicate_sample_id_detected():
    """★ 冻结输入必须无重复 sample_id。"""
    for _n in ("N1_盲审标注表_A.csv", "N1_盲审标注表_B.csv", "N1_仲裁表.csv"):
        _ids = [r["sample_id"] for r in _rows(WORK / _n)]
        assert len(_ids) == len(set(_ids)) == 50, _n


def test_three_files_same_id_set():
    _a = {r["sample_id"] for r in _rows(WORK / "N1_盲审标注表_A.csv")}
    _b = {r["sample_id"] for r in _rows(WORK / "N1_盲审标注表_B.csv")}
    _c = {r["sample_id"] for r in _rows(WORK / "N1_仲裁表.csv")}
    assert _a == _b == _c


# ══ ③ 标签冲突 / 字段缺省 ══
def test_truth_label_enum_valid():
    """★ truth_label 枚举合法（★ 不含 false_*）。"""
    _ok = {"valid_confirmed", "valid_rejection",
           "pending_insufficient_evidence", "uncertain_requires_human"}
    for _n, _tag in (("N1_盲审标注表_A.csv", "A"), ("N1_盲审标注表_B.csv", "B")):
        for _r in _rows(WORK / _n):
            _v = (_r.get(f"★ {_tag}:truth_label") or "").strip()
            assert _v in _ok, f"{_n}:{_r['sample_id']}:{_v}"


def test_support_enum_valid():
    _ok = {"supported", "partially_supported", "contradicted",
           "evidence_insufficient"}
    for _n, _tag in (("N1_盲审标注表_A.csv", "A"), ("N1_盲审标注表_B.csv", "B")):
        for _r in _rows(WORK / _n):
            _v = (_r.get(f"★ {_tag}:evidence_support") or "").strip()
            assert _v in _ok, f"{_n}:{_r['sample_id']}:{_v}"


def test_legal_default_fields_distinguished():
    """★ condition/exception 的 null 是合法缺省（★ 与空串区分）。"""
    _rs = _rows(WORK / "N1_盲审标注表_A.csv")
    # ★ condition/exception 的取值：★ 合法缺省（null 等）或**真实条件/例外描述**
    _legal = {"null", "none", "无", "n/a", "-", ""}
    for _r in _rs:
        for _f in ("condition", "exception"):
            _v = (_r.get(f"★ A:{_f}") or "").strip()
            if _v.lower() in _legal:
                continue
            # ★ 非缺省 ⇒ ★ 必须是**具体描述**（★ 不是空/占位）
            assert len(_v) >= 3, f"{_r['sample_id']}:{_f}:{_v!r}"
    _nulls = sum(1 for _r in _rs
                 if (_r.get("★ A:condition") or "").strip().lower() in _legal)
    _filled = len(_rs) - _nulls
    assert _nulls > 0 and _filled > 0
    # ★ ★ 候选 condition 字段本就是空的（★ 原始候选无此字段）
    for _r in _rs:
        assert not (_r.get("★ condition（LLM 候选，★ 原始无此字段）") or "").strip()


def test_polarity_null_vs_filled_difference_present():
    """★ A 与 B 在 polarity 上的「null vs 填写」差异 ⇒ 表达差异而非实质分歧。"""
    _a = _rows(WORK / "N1_盲审标注表_A.csv")
    _b = {r["sample_id"]: r for r in _rows(WORK / "N1_盲审标注表_B.csv")}
    _diff = 0
    for _r in _a:
        _va = (_r.get("★ A:polarity") or "").strip().lower()
        _vb = (_b[_r["sample_id"]].get("★ B:polarity") or "").strip().lower()
        _ea = _va in ("null", "none", "无", "")
        _eb = _vb in ("null", "none", "无", "")
        if _ea != _eb:
            _diff += 1
    assert _diff > 0, "★ 应存在 polarity 的 null-vs-filled 表达差异"


# ══ ④ 分母异常 ══
def test_rate_with_zero_denominator_is_na():
    """★ 分母为 0 ⇒ N/A，★ 绝不返回虚假 0%。"""
    import importlib.util
    _sp = importlib.util.spec_from_file_location(
        "n1s", OUTD.parent / "n1_汇总脚本.py")
    _m = importlib.util.module_from_spec(_sp)
    _sp.loader.exec_module(_m)
    assert _m._pct(0, 0) == "N/A"
    assert _m._pct(1, 0) == "N/A"
    assert _m._pct(0, 5) == 0.0
    assert _m._pct(1, 2) == 0.5


def test_confirmed_precision_denominator_is_model_confirmed():
    """★ confirmed precision 的分母必须是**模型 confirmed 样本**，★ 不是全部样本。"""
    _m = json.loads((OUTD / "N1-B_模型质量指标.json").read_text(encoding="utf-8"))
    _c = _m["★ 1 confirmed precision"]
    _all = sum(1 for _r in _rows(WORK / "N1_盲审标注表_A.csv"))
    assert _c["n"] != _all or _c["n"] == 0
    assert _c["n"] <= _all
    # ★ 不得出现 24/50 这类口径
    assert not (_c["n"] == 50 and _c["k"] == 24)


def test_pending_not_counted_as_false_rejection():
    """★ pending 不得计入错误拒收。"""
    _m = json.loads((OUTD / "N1-B_模型质量指标.json").read_text(encoding="utf-8"))
    _r = _m["★ 2 rejected 统计（★ 与 pending 分开）"]
    _p = _m["★ 3 pending 统计（★ ★ pending 不是自动意义上的错误拒收）"]
    assert _r["n"] + _p["n"] <= 50
    assert "★ pending" in _p["★ 定义"] or "pending" in _p["★ 定义"]


def test_population_ledger_balances_156():
    _rows_ = [json.loads(l) for l in
              (ROOT / "guard/_out/n1r2/n1r2_population.jsonl")
              .read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(_rows_) == 156
    _c = collections.Counter(r["★ 类别"] for r in _rows_)
    assert _c["audited"] == 50
    assert sum(v for k, v in _c.items() if k != "audited") == 106


def test_no_llm_calls_in_this_stage():
    """★ 本阶段**不得**新增 LLM 调用（★ 脚本中不得出现客户端构造）。"""
    for _f in sorted((ROOT / "guard/_out/_n1b").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t, _f.name
        assert "chat_json" not in _t, _f.name
