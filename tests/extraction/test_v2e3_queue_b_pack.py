# -*- coding: utf-8 -*-
"""★ V2-E3：★ 队列 B 盲审发放包的回归测试（★ 防 CSV/编码损坏）。"""
from __future__ import annotations

import collections
import csv
import io
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
     / "M1-Q3-V2-E3队列B盲审发放与保留来源预案")


def _rows(p):
    """★ ★ 必须用 csv.reader + StringIO（★ 不可用 splitlines()）"""
    return list(csv.DictReader(
        io.StringIO(pathlib.Path(p).read_text(encoding="utf-8"))))


def _base():
    return [json.loads(l) for l in
            (D / "V2-E3_原文与证据不可编辑字段基线.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()]


# ══ ① 验收八项 ══
def test_acceptance_all_passed():
    _a = json.loads((ROOT / "guard/_out/_n1c_v2/e3/v2e3_queue_b_acceptance.json")
                    .read_text(encoding="utf-8"))
    assert _a["★ 通过"] is True
    assert len(_a["★ 各项检查"]) == 8


# ══ ② 基线完整性 ══
def test_baseline_54_rows_unique_ids():
    _b = _base()
    assert len(_b) == 54
    _ids = [x["snippet_id"] for x in _b]
    assert len(set(_ids)) == 54


def test_baseline_evidence_sha_matches_text():
    import hashlib
    for _b in _base():
        assert hashlib.sha256(_b["★ 证据原文"].encode()).hexdigest() == \
            _b["★ 证据原文 sha256"], _b["snippet_id"]


def test_baseline_rfc_sha_verifiable():
    import hashlib
    for _b in _base():
        _p = ROOT / f'kb/{_b["protocol"]}/spec/{_b["document"]}'
        assert _p.is_file(), _b["snippet_id"]
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _b["rfc_sha256"]


# ══ ③ 盲审包结构 ══
def test_snippet_pack_has_54_rows_and_edit_columns():
    _r = _rows(D / "V2-E3_队列B_审核者A_片段级标注表.csv")
    assert len(_r) == 54
    for _c in ("★ 是否存在目标知识", "★ 知识类别", "★ 是否需跨句/跨节证据",
               "★ 审核意见", "★ 不确定原因"):
        assert _c in _r[0]
    # ★ 标签列必须全空（★ Agent 未代填）
    for _row in _r:
        for _c in ("★ 是否存在目标知识", "★ 知识类别", "★ 审核意见"):
            assert not (_row[_c] or "").strip()


def test_knowledge_pack_has_14_contract_fields():
    _r = _rows(D / "V2-E3_队列B_审核者A_原子知识级标注表.csv")
    assert len(_r) == 54
    for _c in ("gold_knowledge_id", "snippet_id", "knowledge_kind", "evidence_span",
               "subject", "action", "object", "strength", "polarity", "condition",
               "exception", "evidence_support", "review_note"):
        assert _c in _r[0], _c
    for _row in _r:
        for _c in ("knowledge_kind", "strength", "polarity", "evidence_support"):
            assert not (_row[_c] or "").strip()


def test_arbitration_template_has_required_audit_fields():
    _r = _rows(D / "V2-E3_队列B_第三方仲裁模板.csv")
    assert len(_r) == 54
    for _c in ("★ 仲裁者 ID（★ 匿名编号）", "★ 审核日期", "★ 仲裁理由",
               "★ 是否 unresolved"):
        assert _c in _r[0], _c


# ══ ④ Excel 友好模板不含原文 ══
def test_excel_template_excludes_raw_text():
    _r = _rows(D / "V2-E3_队列B_审核者A_Excel友好编辑模板.csv")
    assert len(_r) == 54
    _cols = set(_r[0].keys())
    assert "★ 原文（不可编辑）" not in _cols
    assert not any("原文" in c for c in _cols)


# ══ ⑤ 编码与结构保护 ══
def test_all_pack_files_utf8_no_bom_lf():
    for _p in sorted(D.glob("*.csv")):
        _b = _p.read_bytes()
        assert not _b.startswith(b"\xef\xbb\xbf"), _p.name
        assert b"\r\n" not in _b, _p.name


def test_csv_roundtrip_with_special_chars():
    """★ ★ 往返完整性（★ 引号/逗号/换行/⏎/反斜杠）。"""
    _probe = 'a"b,c\nd⏎e\\f'
    _buf = io.StringIO()
    _w = csv.writer(_buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    _w.writerow(["x"]); _w.writerow([_probe])
    _back = list(csv.reader(io.StringIO(_buf.getvalue())))
    assert _back[1][0] == _probe


def test_splitlines_would_corrupt_multiline_field():
    """★ ★ 反证：★ splitlines() 会破坏多行字段（★ N1-C 断行的根因）。"""
    _probe = "line1\nline2"
    _buf = io.StringIO()
    _w = csv.writer(_buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    _w.writerow(["x"]); _w.writerow([_probe])
    _text = _buf.getvalue()
    _good = list(csv.reader(io.StringIO(_text)))
    _bad = list(csv.DictReader(_text.splitlines()))
    assert _good[1][0] == _probe
    assert len(_bad) != 2 or _bad[0]["x"] != _probe   # ★ splitlines 破坏


def test_hash_manifest_matches_files():
    _m = json.loads((D / "V2-E3_发放包文件哈希.json").read_text(encoding="utf-8"))
    import hashlib
    for _n, _h in _m["★ 文件哈希"].items():
        assert hashlib.sha256((D / _n).read_bytes()).hexdigest() == _h, _n


def test_no_llm_calls_in_this_stage():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/e3").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t, _f.name
        assert "chat_json" not in _t, _f.name
