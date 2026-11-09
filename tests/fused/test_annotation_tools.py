# -*- coding: utf-8 -*-
"""tests/fused/test_annotation_tools.py —— B 阶段人工标注集工具的行为契约。

本文件把「标注基础设施不能被悄悄破坏」固化成可执行断言。覆盖：

  · **冻结脚本** —— 确定性（两次跑同一份 md5）、分层规模（120 条 / 三协议各 40 /
    四类主体全非空）、train/holdout 分离（100/20）、span 可逐字核对、必需字段齐全
  · **标注校验器** —— 10 条规则逐一必须被拦下（**故意造非法值 → 退出码非 0**）
  · **κ 计算** —— 完全一致 ⇒ κ=1.0；50% 一致 ⇒ κ 显著 < 0.6；**类别分布退化**须显式报告
  · **指南防泄漏** —— 标注指南不得逐字/近似包含任何**待标注**候选

★ **本文件用 ``tmp_path`` 构造合成数据**，不依赖 ``derived/experiments/annotation/`` 下的
  实验产物（那些内容会随实验重生成而变，会让本文件变成"测实验产物"而不是
  "测工具逻辑"）。唯一例外是「指南防泄漏」那一条：它必须对着**真实冻结集**跑，
  因为泄漏风险恰恰发生在"指南 vs 真实候选"之间 —— 故该用例在冻结集不存在时
  自行 ``pytest.skip``（而不是静默通过）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.annotate_candidates import (  # noqa: E402
    MODALITIES,
    NOT_EXECUTABLE,
    OPERATORS,
    RESPONSE_CLASSES,
    build_template,
    check_guide_leaks,
    validate_all,
    validate_one,
)
from scripts.calc_cohen_kappa import (  # noqa: E402
    KAPPA_THRESHOLD,
    cohen_kappa,
    compare,
)
from scripts.freeze_annotation_candidates import (  # noqa: E402
    SUBJECT_TYPES,
    _allocate,
    _even_spread,
    _looks_like_field_name,
    _stable_key,
    classify_subject,
    freeze,
)

#: 合成候选池：覆盖四类主体 × 三个协议。
#: ★ 字段集与 ``freeze()`` 的真实产出**保持一致**（含 candidate_id / split）——
#:   测试夹具若比真实数据少字段，测出来的就是「夹具缺字段」而不是产品行为。
_FAKE_CANDIDATES = [
    {"candidate_id": "f1", "text": "A client MUST NOT issue a PLAY request",
     "source": "file:a.txt#@1", "protocol": "rtsp", "span_start": 0, "span_end": 38,
     "section_path": ["PLAY"], "section_no": "10.5", "spec_version": "RFC 2326",
     "subject_type": "method", "split": "train"},
    {"candidate_id": "f2", "text": "The Contact header field MUST be present",
     "source": "file:a.txt#@2", "protocol": "rtsp", "span_start": 40, "span_end": 80,
     "section_path": ["Contact"], "section_no": "8.1.1.8", "spec_version": "RFC 2326",
     "subject_type": "field", "split": "train"},
    {"candidate_id": "f3", "text": "457            Invalid Range                    PLAY",
     "source": "file:a.txt#@3", "protocol": "rtsp", "span_start": 82, "span_end": 125,
     "section_path": ["Status Code and Reason Phrase"], "section_no": "7.1.1",
     "spec_version": "RFC 2326", "subject_type": "status", "split": "train"},
    {"candidate_id": "f4",
     "text": "Session identifiers are opaque strings of arbitrary length.",
     "source": "file:b.txt#@4", "protocol": "sip", "span_start": 0, "span_end": 58,
     "section_path": ["Session Identifiers"], "section_no": "3.4",
     "spec_version": "RFC 3261", "subject_type": "message_type", "split": "train"},
    {"candidate_id": "f5", "text": "The start-line MUST be terminated by CRLF",
     "source": "file:b.txt#@5", "protocol": "sip", "span_start": 60, "span_end": 101,
     "section_path": ["SIP Messages"], "section_no": "7", "spec_version": "RFC 3261",
     "subject_type": "message_type", "split": "train"},
    {"candidate_id": "f6", "text": "The client MUST reject the AUTH command with a 501 reply",
     "source": "file:c.txt#@6", "protocol": "smtp", "span_start": 0, "span_end": 58,
     "section_path": ["The AUTH Command"], "section_no": "4", "spec_version": "RFC 4954",
     "subject_type": "method", "split": "train"},
]


# ===========================================================================
# 冻结脚本
# ===========================================================================
class TestFreezeDeterminism:
    """抽样必须**完全确定** —— roadmap §4.2 的「同一批候选句」是 C0/E1/E2 可比的前提。"""

    def test_stable_key_is_pure_function(self):
        """稳定哈希键只依赖内容，不依赖运行顺序 / 字典序。"""
        cand = {"source": "file:a.txt#@1", "span_start": 3, "text": "hello"}
        k1 = _stable_key("salt", "rtsp", cand)
        k2 = _stable_key("salt", "rtsp", dict(cand))
        assert k1 == k2
        # 换 salt 必须换键（否则 salt 形同虚设）
        assert _stable_key("other", "rtsp", cand) != k1
        # 换 protocol 必须换键
        assert _stable_key("salt", "sip", cand) != k1

    def test_stable_key_is_hex_sha256(self):
        cand = {"source": "file:a.txt#@1", "span_start": 3, "text": "hello"}
        key = _stable_key("salt", "rtsp", cand)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_even_spread_is_deterministic_and_bounded(self):
        idx = _even_spread(10, 3)
        assert idx == _even_spread(10, 3)
        assert all(0 <= i < 10 for i in idx)
        assert len(set(idx)) == 3

    def test_even_spread_edge_cases(self):
        assert _even_spread(0, 3) == []
        assert _even_spread(5, 0) == []
        assert _even_spread(2, 5) == [0, 1]      # k >= n ⇒ 全取
        assert _even_spread(5, 1) == [0]         # 单个 ⇒ 取首


class TestAllocate:
    """最大余数法分配：每层保底 + 按比例分配。"""

    def test_min_one_guarantees_coverage(self):
        sizes = {"method": 25, "field": 9, "status": 8, "message_type": 39}
        alloc = _allocate(40, sizes, min_one=True)
        assert sum(alloc.values()) == 40
        for st in SUBJECT_TYPES:
            if sizes[st] > 0:
                assert alloc[st] >= 1, f"{st} 层应保底 1 个"

    def test_allocation_never_exceeds_pool(self):
        sizes = {"method": 3, "field": 1, "status": 0, "message_type": 100}
        alloc = _allocate(40, sizes, min_one=True)
        for st in SUBJECT_TYPES:
            assert alloc[st] <= sizes[st], f"{st} 分配量超过池容量"

    def test_allocation_is_deterministic(self):
        sizes = {"method": 25, "field": 9, "status": 8, "message_type": 39}
        assert _allocate(40, sizes, True) == _allocate(40, sizes, True)

    def test_empty_pool(self):
        alloc = _allocate(10, {"method": 0, "field": 0, "status": 0,
                               "message_type": 0}, min_one=True)
        assert sum(alloc.values()) == 0


class TestSubjectClassifier:
    """主体分类只依据**章节结构**，不得引入方法/字段白名单。"""

    def test_status_section(self):
        cfg = {"method_sections": ["10"], "field_sections": ["6.2"],
               "status_sections": ["7.1.1"]}
        cand = {"section_no": "7.1.1", "section_path": ["Status Code and Reason Phrase"]}
        assert classify_subject(cand, cfg) == "status"

    def test_method_section(self):
        cfg = {"method_sections": ["10"], "field_sections": ["6.2"],
               "status_sections": ["7.1.1"]}
        cand = {"section_no": "10.5", "section_path": ["PLAY"]}
        assert classify_subject(cand, cfg) == "method"

    def test_field_section(self):
        cfg = {"method_sections": ["10"], "field_sections": ["6.2"],
               "status_sections": ["7.1.1"]}
        cand = {"section_no": "6.2", "section_path": ["Request Header Fields"]}
        assert classify_subject(cand, cfg) == "field"

    def test_fallback_is_message_type(self):
        cfg = {"method_sections": ["10"], "field_sections": ["6.2"],
               "status_sections": ["7.1.1"]}
        cand = {"section_no": "3.4", "section_path": ["Session Identifiers"]}
        assert classify_subject(cand, cfg) == "message_type"

    def test_never_returns_unknown(self):
        cfg = {"method_sections": [], "field_sections": [], "status_sections": []}
        for cand in _FAKE_CANDIDATES:
            assert classify_subject(cand, cfg) in SUBJECT_TYPES

    def test_field_name_heuristic(self):
        assert _looks_like_field_name("Call-ID") is True
        assert _looks_like_field_name("Via") is True
        assert _looks_like_field_name("Introduction") is False
        assert _looks_like_field_name("Request Header Fields") is False

    def test_classifier_does_not_read_profile(self):
        """★ 防泄漏硬约束：分类器**不得**读取 profile.json 的 allowed_methods。

        判据：源码里**不得出现对 profile.json 的文件读取**。
        注意 docstring 里**可以**提到这两个词 —— 那是在写「不许用它」的约束说明，
        若把文档说明也判成违规，这条约束就没法在代码里自我说明。故本断言查的是
        「有没有真的去读这个文件」，而不是「有没有提到这个文件名」。
        """
        import scripts.freeze_annotation_candidates as mod
        src = Path(mod.__file__).read_text(encoding="utf-8")
        # 去掉所有 docstring 与注释后再查（只看**可执行代码**）
        code = "\n".join(
            line.split("#", 1)[0] for line in src.splitlines()
        )
        for token in ('"profile.json"', "'profile.json'",
                      '"allowed_methods"', "'allowed_methods'"):
            assert token not in code, f"可执行代码里出现了 {token}"

    def test_classifier_only_reads_rfc_config(self):
        """★ 分层的唯一数据源是 rfc_config.json（章节结构），不是 profile.json。"""
        import scripts.freeze_annotation_candidates as mod
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "rfc_config.json" in src


class TestFreezeEndToEnd:
    """端到端：冻结脚本在真实 kb 上跑，产出必须满足 §4.6 的规模与分层要求。"""

    @pytest.fixture(scope="class")
    def frozen(self):
        return freeze(("rtsp", "sip", "smtp"), 40,
                      {"rtsp": 7, "sip": 7, "smtp": 6}, "test-salt")

    def test_total_is_120(self, frozen):
        assert len(frozen) == 120

    def test_per_protocol_is_40(self, frozen):
        counts = {}
        for r in frozen:
            counts[r["protocol"]] = counts.get(r["protocol"], 0) + 1
        assert counts == {"rtsp": 40, "sip": 40, "smtp": 40}

    def test_split_is_100_20(self, frozen):
        train = sum(1 for r in frozen if r["split"] == "train")
        holdout = sum(1 for r in frozen if r["split"] == "holdout")
        assert (train, holdout) == (100, 20)

    def test_holdout_is_stratified_by_protocol(self, frozen):
        holdout = {}
        for r in frozen:
            if r["split"] == "holdout":
                holdout[r["protocol"]] = holdout.get(r["protocol"], 0) + 1
        assert holdout == {"rtsp": 7, "sip": 7, "smtp": 6}

    def test_all_four_subject_types_present_per_protocol(self, frozen):
        """四类主体在**每个协议**里都非空（roadmap §4.6 第 1 条）。"""
        for proto in ("rtsp", "sip", "smtp"):
            subs = {r["subject_type"] for r in frozen if r["protocol"] == proto}
            assert subs == set(SUBJECT_TYPES), f"{proto} 缺主体类型: {set(SUBJECT_TYPES) - subs}"

    def test_candidate_ids_unique(self, frozen):
        ids = [r["candidate_id"] for r in frozen]
        assert len(ids) == len(set(ids))

    def test_required_fields_present(self, frozen):
        required = ("candidate_id", "protocol", "text", "span_start", "span_end",
                    "source", "section_path", "spec_version")
        for r in frozen:
            for f in required:
                assert f in r, f"{r.get('candidate_id')} 缺字段 {f}"

    def test_span_is_verbatim_verifiable(self, frozen):
        """★ span 必须能在源文件里逐字核对 —— 否则标注无从复核。"""
        from core import paths
        checked = 0
        for r in frozen:
            fname = r["source"].split("#@")[0][len("file:"):]
            path = paths.kb_source_dir(r["protocol"], "rfc") / fname
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert text[r["span_start"]:r["span_end"]] == r["text"], \
                f"{r['candidate_id']} span 不可核对"
            checked += 1
        assert checked == 120

    def test_is_reproducible(self):
        """两次冻结 ⇒ 完全相同的候选集。"""
        a = freeze(("rtsp", "sip", "smtp"), 40,
                   {"rtsp": 7, "sip": 7, "smtp": 6}, "test-salt")
        b = freeze(("rtsp", "sip", "smtp"), 40,
                   {"rtsp": 7, "sip": 7, "smtp": 6}, "test-salt")
        assert a == b

    def test_cli_is_reproducible_by_md5(self, tmp_path):
        """★ 验收项：脚本两次运行 md5 相同（用 --quiet 抑制摘要）。"""
        py = sys.executable
        outs = []
        for i in range(2):
            out = tmp_path / f"cand{i}.jsonl"
            r = subprocess.run(
                [py, str(ROOT / "scripts" / "freeze_annotation_candidates.py"),
                 "--out", str(out), "--quiet"],
                cwd=str(ROOT), capture_output=True, text=True)
            assert r.returncode == 0, r.stderr
            outs.append(hashlib.md5(out.read_bytes()).hexdigest())
        assert outs[0] == outs[1]


# ===========================================================================
# 标注校验器
# ===========================================================================
def _good_rec(cid: str, **over) -> dict:
    rec = {
        "candidate_id": cid,
        "has_normative_requirement": True,
        "modality": "MUST",
        "operator": "ge",
        "expected_response_class": None,
        "annotator": "A",
        "uncertain": False,
    }
    rec.update(over)
    return rec


class TestValidator:
    """★ 故意造非法值 ⇒ 必须被拦下（验收项 3）。"""

    KNOWN = {"x1", "x2", "x3"}

    def test_valid_record_passes(self):
        assert validate_one(_good_rec("x1"), self.KNOWN) == []

    def test_r1_missing_field(self):
        rec = _good_rec("x1")
        del rec["modality"]
        problems = validate_one(rec, self.KNOWN)
        assert any("缺字段" in p for p in problems)

    def test_r2_bad_modality(self):
        problems = validate_one(_good_rec("x1", modality="SUPER"), self.KNOWN)
        assert any("modality 非法" in p for p in problems)

    def test_r3_has_normative_must_be_bool(self):
        problems = validate_one(_good_rec("x1", has_normative_requirement="true"),
                                self.KNOWN)
        assert any("必须是 bool" in p for p in problems)

    def test_r4_bad_operator(self):
        """★ 验收项 3 的核心：`operator='BAD'` 必须被拒绝。"""
        problems = validate_one(_good_rec("x1", operator="BAD"), self.KNOWN)
        assert any("operator 非法" in p for p in problems)

    def test_r4_not_executable_operator_allowed(self):
        assert validate_one(_good_rec("x1", operator=NOT_EXECUTABLE), self.KNOWN) == []

    def test_r4_all_operators_allowed(self):
        for op in sorted(OPERATORS):
            rec = _good_rec("x1", operator=op)
            assert not any("operator 非法" in p
                           for p in validate_one(rec, self.KNOWN)), f"{op} 应被接受"

    def test_r5_bad_response_class(self):
        problems = validate_one(_good_rec("x1", expected_response_class="NOT_A_CLASS"),
                                self.KNOWN)
        assert any("expected_response_class 非法" in p for p in problems)

    def test_r5_null_response_class_allowed(self):
        assert validate_one(_good_rec("x1", expected_response_class=None), self.KNOWN) == []

    def test_r5_all_response_classes_allowed(self):
        for rc in sorted(RESPONSE_CLASSES):
            rec = _good_rec("x1", expected_response_class=rc)
            assert not any("expected_response_class 非法" in p
                           for p in validate_one(rec, self.KNOWN)), f"{rc} 应被接受"

    def test_r6_cross_consistency_modality(self):
        """has_normative=False ⇒ modality 必须是「无」。"""
        problems = validate_one(
            _good_rec("x1", has_normative_requirement=False, modality="MUST"),
            self.KNOWN)
        assert any("交叉不一致" in p and "modality" in p for p in problems)

    def test_r7_cross_consistency_operator(self):
        """has_normative=False ⇒ operator 必须是「不可」。"""
        problems = validate_one(
            _good_rec("x1", has_normative_requirement=False, modality="无",
                      operator="ge"),
            self.KNOWN)
        assert any("交叉不一致" in p and "operator" in p for p in problems)

    def test_r8_uncertain_requires_reason(self):
        problems = validate_one(_good_rec("x1", uncertain=True), self.KNOWN)
        assert any("uncertain_reason" in p for p in problems)

    def test_r9_unknown_candidate_id(self):
        problems = validate_one(_good_rec("NOPE"), self.KNOWN)
        assert any("candidate_id 未知" in p for p in problems)

    def test_r10_empty_annotator(self):
        problems = validate_one(_good_rec("x1", annotator="  "), self.KNOWN)
        assert any("annotator" in p for p in problems)

    def test_duplicate_ids_rejected(self):
        frozen = [{"candidate_id": "x1"}]
        problems = validate_all([_good_rec("x1"), _good_rec("x1")], frozen)
        assert any("重复" in p for p in problems)

    def test_missing_ids_rejected(self):
        frozen = [{"candidate_id": "x1"}, {"candidate_id": "x2"}]
        problems = validate_all([_good_rec("x1")], frozen)
        assert any("缺漏" in p for p in problems)

    def test_allow_partial_skips_missing_check(self):
        frozen = [{"candidate_id": "x1"}, {"candidate_id": "x2"}]
        problems = validate_all([_good_rec("x1")], frozen, require_complete=False)
        assert not any("缺漏" in p for p in problems)

    def test_cli_rejects_bad_operator_with_nonzero_exit(self, tmp_path):
        """★ 验收项 3 的 CLI 形态：非法文件 ⇒ 退出码非 0。"""
        bad = [{"candidate_id": "x1", "has_normative_requirement": True,
                "modality": "MUST", "operator": "BAD",
                "expected_response_class": None, "annotator": "A"}]
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "annotate_candidates.py"),
             "validate", "--annotations", str(path)],
            cwd=str(ROOT), capture_output=True, text=True)
        assert r.returncode != 0
        assert "operator 非法" in r.stderr

    def test_cli_accepts_good_file(self, tmp_path):
        good = [{"candidate_id": "x1", "has_normative_requirement": True,
                 "modality": "MUST", "operator": "ge",
                 "expected_response_class": None, "annotator": "A"}]
        path = tmp_path / "good.json"
        path.write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
        frozen = tmp_path / "frozen.jsonl"
        frozen.write_text(json.dumps({"candidate_id": "x1"}) + "\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "annotate_candidates.py"),
             "--frozen", str(frozen), "validate", "--annotations", str(path)],
            cwd=str(ROOT), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert "全部通过校验" in r.stdout


class TestTemplate:
    """模板必须**只给题面**，绝不能带答案。"""

    def test_template_has_no_answers(self):
        tpl = build_template(_FAKE_CANDIDATES, "A")
        items = [i for lst in tpl.values() for i in lst]
        assert items
        for item in items:
            assert item["has_normative_requirement"] is None
            assert item["modality"] is None
            assert item["operator"] is None
            assert item["expected_response_class"] is None
            assert item["annotator"] == "A"

    def test_template_keeps_provenance(self):
        tpl = build_template(_FAKE_CANDIDATES, "B")
        items = [i for lst in tpl.values() for i in lst]
        for item in items:
            assert item["candidate_id"]
            assert item["text"]
            assert "source" in item
            assert "span_start" in item

    def test_template_split_filter(self):
        frozen = [dict(c, split="train") for c in _FAKE_CANDIDATES]
        frozen[0]["split"] = "holdout"
        tpl = build_template(frozen, "A", split="holdout")
        assert sum(len(v) for v in tpl.values()) == 1


class TestGuideLeak:
    """★ 防信息泄漏的机械闸：指南不得泄漏待标注候选的答案。"""

    def test_exact_quote_is_leak(self, tmp_path):
        guide = tmp_path / "g.md"
        guide.write_text("示例：`A client MUST NOT issue a PLAY request`", encoding="utf-8")
        frozen = [{"candidate_id": "c1", "text": "A client MUST NOT issue a PLAY request"}]
        problems, _ = check_guide_leaks(guide, frozen)
        assert any("L1" in p for p in problems)

    def test_clean_guide_passes(self, tmp_path):
        guide = tmp_path / "g.md"
        guide.write_text("示例：`A client MUST NOT issue something`", encoding="utf-8")
        frozen = [{"candidate_id": "c1", "text": "A client MUST NOT issue a PLAY request"}]
        problems, _ = check_guide_leaks(guide, frozen)
        assert problems == []

    def test_short_candidate_overlap_is_note_not_block(self, tmp_path):
        """短候选与指南共享表格词汇属正常 ⇒ 只提示不阻断。"""
        guide = tmp_path / "g.md"
        guide.write_text("表格行示例 `| \"411\" ; Length Required`", encoding="utf-8")
        frozen = [{"candidate_id": "c1", "text": "411            Length Required  all"}]
        problems, notes = check_guide_leaks(guide, frozen)
        assert problems == []
        assert notes

    def test_real_guide_does_not_leak_real_frozen_set(self):
        """★ 对**真实冻结集**跑：标注指南必须零泄漏。"""
        frozen_path = ROOT / "derived" / "experiments" / "annotation" / "candidates_frozen.jsonl"
        guide_path = ROOT / "docs" / "工具" / "人工标注指南.md"
        if not frozen_path.is_file() or not guide_path.is_file():
            pytest.skip("冻结集或指南尚未生成（该用例需真实数据）")
        frozen = [json.loads(line) for line in
                  frozen_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        problems, _ = check_guide_leaks(guide_path, frozen)
        assert problems == [], f"指南泄漏了待标注候选: {problems}"


# ===========================================================================
# κ 计算
# ===========================================================================
class TestKappa:
    """★ 验收项 4：完全一致 ⇒ κ=1.0；50% 一致 ⇒ κ 显著 < 0.6。"""

    def test_perfect_agreement_is_one(self):
        labels = ["MUST"] * 50
        st = cohen_kappa(labels, list(labels))
        assert st["kappa"] == 1.0
        assert st["po"] == 1.0

    def test_half_agreement_is_below_threshold(self):
        """50% 一致 ⇒ κ 显著 < 0.6（roadmap 阈值）。"""
        a = ["MUST", "SHOULD"] * 50
        b = ["MUST", "MAY"] * 50
        st = cohen_kappa(a, b)
        assert st["kappa"] < KAPPA_THRESHOLD
        assert st["po"] == 0.5

    def test_degenerate_distribution_is_reported(self):
        """双方只用同一个类别 ⇒ pe=1 ⇒ κ 无定义 ⇒ 必须**显式**报告而非悄悄给个数。"""
        st = cohen_kappa(["MUST"] * 10, ["MUST"] * 10)
        assert st["degenerate"] is True
        assert st["note"]
        assert st["kappa"] == 1.0

    def test_disjoint_categories_is_not_degenerate(self):
        """★ 双方各用**互斥**的单类别 ⇒ pe=0 ⇒ κ=po 良定义，**不是**退化。

        （pe==1 ⟺ 双方集中在**同一个**类别；此时必然完全一致。
          类别互斥时 pe=0，κ=(po-0)/(1-0)=po，数学上完全良定义。）
        """
        st = cohen_kappa(["MUST"] * 10, ["SHOULD"] * 10)
        assert st["degenerate"] is False
        assert st["pe"] == 0.0
        assert st["kappa"] == 0.0

    def test_empty_sample(self):
        st = cohen_kappa([], [])
        assert st["kappa"] is None

    def test_mismatched_length_raises(self):
        with pytest.raises(ValueError):
            cohen_kappa(["MUST"], ["MUST", "SHOULD"])


class TestCompare:
    def test_per_field_kappa_reported(self):
        a = {"c1": _good_rec("c1"), "c2": _good_rec("c2")}
        b = {"c1": _good_rec("c1"), "c2": _good_rec("c2", operator="le")}
        result = compare(a, b)
        assert set(result["per_field"]) == {
            "has_normative_requirement", "modality", "operator",
            "expected_response_class"}

    def test_disagreements_listed(self):
        a = {"c1": _good_rec("c1")}
        b = {"c1": _good_rec("c1", operator="le")}
        result = compare(a, b)
        assert len(result["disagreements"]) == 1
        d = result["disagreements"][0]
        assert d["candidate_id"] == "c1"
        assert "operator" in d["diff_fields"]

    def test_only_common_ids_compared(self):
        a = {"c1": _good_rec("c1"), "c2": _good_rec("c2")}
        b = {"c1": _good_rec("c1")}
        result = compare(a, b)
        assert result["n_common"] == 1
        assert result["n_only_a"] == 1
        assert result["n_only_b"] == 0

    def test_exact_agreement_rate(self):
        a = {"c1": _good_rec("c1"), "c2": _good_rec("c2")}
        b = {"c1": _good_rec("c1"), "c2": _good_rec("c2")}
        result = compare(a, b)
        assert result["exact"]["rate"] == 1.0
        assert result["disagreement_rate"] == 0.0

    def test_cli_reports_kappa(self, tmp_path):
        """★ 验收项 4 的 CLI 形态。"""
        recs = [_good_rec(f"c{i}", operator="ge" if i % 2 == 0 else "le")
                for i in range(20)]
        pa = tmp_path / "a.json"
        pb = tmp_path / "b.json"
        pa.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
        pb.write_text(json.dumps(
            [dict(r, operator="ge") for r in recs], ensure_ascii=False),
            encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "calc_cohen_kappa.py"),
             "--a", str(pa), "--b", str(pb)],
            cwd=str(ROOT), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert "operator" in r.stdout
        assert "κ" in r.stdout

    def test_cli_does_not_modify_inputs(self, tmp_path):
        """★ κ 脚本只算不改 —— 「为了 κ 好看而改标注」是最需要防的失败模式。"""
        recs = [_good_rec("c1"), _good_rec("c2", operator="le")]
        pa = tmp_path / "a.json"
        pb = tmp_path / "b.json"
        pa.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
        pb.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
        before = (pa.read_bytes(), pb.read_bytes())
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "calc_cohen_kappa.py"),
             "--a", str(pa), "--b", str(pb)],
            cwd=str(ROOT), capture_output=True, text=True)
        assert (pa.read_bytes(), pb.read_bytes()) == before


# ===========================================================================
# 词表一致性（防止标注词表与 roadmap / semantic.py 漂移）
# ===========================================================================
class TestCRLFRobustness:
    """★ 换行风格鲁棒性 —— 本仓 ``core.autocrlf=true``，git checkout 会把仓库里
    存的 LF blob **物化成 CRLF 落盘**（实测：``scripts/build_hub.py`` 是
    ``i/lf w/crlf``）。因此**任何按字节读文件的校验都可能看到与提交时不同的结果**。

    本类断言：把交付物物化成 CRLF 后，**行为完全不变** —— 冻结产出字节一致、
    校验器结论一致、κ 结论一致、泄漏闸结论一致。

    ★ 这不是假设，是实测过的场景：2026-11-01 有一路执行了 ``git reset`` +
    重新提交，导致他人文档的换行符在落盘时被静默物化。
    """

    @pytest.fixture(scope="class")
    def crlf_probe(self, tmp_path_factory):
        """把三个脚本 + 指南物化成 CRLF，放到**仓根的直接子目录**。

        ★ 必须是仓根的直接子目录：脚本用 ``parents[1]`` 解析 REPO_ROOT，
          多一层会让 ``import core`` 失败（那不是 CRLF 的问题，是路径的问题）。
        """
        probe = tmp_path_factory.mktemp("_crlf_probe")
        for name in ("freeze_annotation_candidates.py", "annotate_candidates.py",
                     "calc_cohen_kappa.py"):
            src = (ROOT / "scripts" / name).read_bytes()
            (probe / name).write_bytes(src.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        guide = (ROOT / "docs" / "工具" / "人工标注指南.md").read_bytes()
        (probe / "人工标注指南.md").write_bytes(
            guide.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        return probe

    @pytest.fixture(scope="class")
    def repo_crlf_probe(self, tmp_path_factory):
        """把 CRLF 版放进**仓内**的临时目录跑（需要能 import core/）。

        ★ 目录名**必须带进程号**：本仓多人并行跑 pytest，
          固定目录名会让两个进程共用同一个探针目录 ⇒ 一方的 teardown
          把另一方正在用的文件删掉 ⇒ **测试结果随机漂移**
          （实测踩到：两次连跑，一次 3 失败、一次 1 失败）。
          ⇒ 目录名带 ``os.getpid()`` ⇒ 并行进程互不干扰。
        """
        probe = ROOT / f"_crlf_probe_{os.getpid()}"
        probe.mkdir(exist_ok=True)
        for name in ("freeze_annotation_candidates.py", "annotate_candidates.py",
                     "calc_cohen_kappa.py"):
            src = (ROOT / "scripts" / name).read_bytes()
            (probe / name).write_bytes(src.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        yield probe
        # ★ 用 shutil.rmtree 而不是「逐个 unlink + rmdir」：
        #   探针目录里跑的脚本会 `from annotate_candidates import …`，
        #   Python 会在**脚本旁边**生成 `__pycache__/` 目录
        #   （实测：Linux CI runner 上必然出现，Windows 上不一定出现）
        #   ⇒ 逐个 unlink 遇到目录就抛 `IsADirectoryError`
        #   ⇒ teardown 失败 ⇒ pytest 把**该类最后一个测试**记成 ERROR
        #   ⇒ CI 的 ERROR 集合多出 `test_frozen_jsonl_is_lf_on_disk`
        #   （真机实测：CI run 41356142634，Ubuntu 21 errors vs 基线 20）
        shutil.rmtree(probe, ignore_errors=True)

    def test_crlf_probe_is_actually_crlf(self, crlf_probe):
        """先确认探针真的物化成了 CRLF（否则下面的断言是空转）。"""
        b = (crlf_probe / "freeze_annotation_candidates.py").read_bytes()
        assert b.count(b"\r\n") > 0
        assert b.count(b"\n") - b.count(b"\r\n") == 0

    def test_freeze_output_identical_under_crlf(self, repo_crlf_probe, tmp_path):
        """★ CRLF 化后冻结产出**字节一致** ⇒ md5 不变 ⇒ 实验基线不受换行影响。"""
        out = tmp_path / "crlf.jsonl"
        r = subprocess.run(
            [sys.executable, str(repo_crlf_probe / "freeze_annotation_candidates.py"),
             "--out", str(out), "--quiet"],
            cwd=str(ROOT), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        lf_out = tmp_path / "lf.jsonl"
        r2 = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "freeze_annotation_candidates.py"),
             "--out", str(lf_out), "--quiet"],
            cwd=str(ROOT), capture_output=True, text=True)
        assert r2.returncode == 0, r2.stderr
        assert hashlib.md5(out.read_bytes()).hexdigest() == \
            hashlib.md5(lf_out.read_bytes()).hexdigest()

    def test_guide_leak_check_same_under_crlf(self, repo_crlf_probe):
        """★ CRLF 化后泄漏闸结论一致（不能因换行符而漏报或误报）。"""
        frozen = ROOT / "derived" / "experiments" / "annotation" / "candidates_frozen.jsonl"
        if not frozen.is_file():
            pytest.skip("冻结集尚未生成")
        guide_crlf = repo_crlf_probe / "人工标注指南.md"
        guide_src = (ROOT / "docs" / "工具" / "人工标注指南.md").read_bytes()
        (repo_crlf_probe / "人工标注指南.md").write_bytes(
            guide_src.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        r = subprocess.run(
            [sys.executable, str(repo_crlf_probe / "annotate_candidates.py"),
             "--frozen", str(frozen), "check-guide", "--guide", str(guide_crlf)],
            cwd=str(ROOT), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert "指南无泄漏" in r.stdout

    def test_validator_same_under_crlf(self, repo_crlf_probe):
        """★ CRLF 化后校验器结论一致。"""
        frozen = ROOT / "derived" / "experiments" / "annotation" / "candidates_frozen.jsonl"
        truth = ROOT / "derived" / "experiments" / "annotation" / "truth" / "rtsp.annotated.json"
        hold = ROOT / "derived" / "experiments" / "annotation" / "truth" / "rtsp.holdout.json"
        if not (frozen.is_file() and truth.is_file() and hold.is_file()):
            pytest.skip("标注集尚未生成")
        r = subprocess.run(
            [sys.executable, str(repo_crlf_probe / "annotate_candidates.py"),
             "--frozen", str(frozen), "validate",
             "--annotations", str(truth), "--include", str(hold)],
            cwd=str(ROOT), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert "全部通过校验" in r.stdout

    def test_kappa_same_under_crlf(self, repo_crlf_probe, tmp_path):
        """★ CRLF 化后 κ 结论一致。"""
        recs = [_good_rec(f"c{i}", operator="ge" if i % 2 == 0 else "le")
                for i in range(20)]
        pa = tmp_path / "a.json"
        pb = tmp_path / "b.json"
        pa.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
        pb.write_text(json.dumps(
            [dict(r, operator="ge") for r in recs], ensure_ascii=False),
            encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(repo_crlf_probe / "calc_cohen_kappa.py"),
             "--a", str(pa), "--b", str(pb)],
            cwd=str(ROOT), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert "operator" in r.stdout

    def test_frozen_jsonl_is_lf_on_disk(self):
        """★ 冻结产物按 **LF** 落盘（显式 newline="\\n"）⇒ 不随平台漂移。"""
        p = ROOT / "derived" / "experiments" / "annotation" / "candidates_frozen.jsonl"
        if not p.is_file():
            pytest.skip("冻结集尚未生成")
        b = p.read_bytes()
        assert b.count(b"\r\n") == 0, "冻结产物不应含 CRLF"


class TestGranularityImpact:
    """★ 「抽取粒度修正 ⇒ 哪些已标注条目会失效」的分析工具。

    背景：``core/fused/rfc_extractor.py`` 的 ``_SENT_SPLIT_RE`` 含 ``\\n+`` 分支
    ⇒ RFC 折行的散文**每行**都被当成一句 ⇒ 候选句大量是**半句**。
    粒度修正（合并折行）会改变候选文本 ⇒ 已标注条目失联。

    ★ 本工具**不依赖** ``rfc_extractor`` 的实现（那正是被改动的一层），
      只依据 RFC 原文的行结构 ⇒ 结论与「怎么改」无关。
    """

    def test_clean_regexes_match_extractor(self):
        """★ 本工具复制的三个清洗判据必须与 rfc_extractor **逐条相等**。

        ⚠ 抄写时踩过的坑：``_RE_RFC_TITLE`` 若写成 ``r"^\\s*(A|B|)"``（**空分支**）
        会**匹配一切** ⇒ 整篇文档被当成标题行 ⇒ 段落边界全错 ⇒ 分析结果全错。
        这条测试就是把那个坑钉死。
        """
        from core.fused import rfc_extractor as rx
        import scripts.annotate_candidates as mod
        assert mod._RE_PAGE_MARK.pattern == rx._RE_PAGE_MARK.pattern
        assert mod._RE_RFC_TITLE.pattern == rx._RE_RFC_TITLE.pattern
        assert mod._RE_EMPTY_OR_DOTS.pattern == rx._RE_EMPTY_OR_DOTS.pattern
        # 反向护栏：标题正则**不得**匹配普通正文行（空分支的经典症状）
        assert not mod._RE_RFC_TITLE.match("   the range specified and delivers")
        assert not mod._RE_RFC_TITLE.match("   range is reached. PLAY requests")

    def test_structural_lines_are_detected(self):
        from scripts.annotate_candidates import _is_structural_line
        for s in ('|          Range                    ; Section 12.29',
                  '|     "457"      ; Invalid Range',
                  'smpte-range  =   smpte-type "=" smpte-time "-"',
                  'Content-Length: 332',
                  '411            Length Required                  all',
                  '   '):
            assert _is_structural_line(s) is True, f"{s!r} 应判为结构性行"
        for s in ('   the range specified and delivers stream data until the end',
                  '   A client MUST NOT issue a PLAY request'):
            assert _is_structural_line(s) is False, f"{s!r} 应判为散文行"

    def test_logical_sentence_merges_wrapped_prose(self):
        """★ 合并折行后应得到**完整逻辑句**。

        ★ 注意本例的候选**位于段落中间**（前半句在上一行）⇒ ``before`` 非空，
          且 ``before`` **不以句末标点结尾** ⇒ 这正是「句子从中途开始」的信号。
        """
        from scripts.annotate_candidates import _logical_sentence
        raw = ("   The PLAY request positions the normal play time to the beginning of\n"
               "   the range specified and delivers stream data until the end of the\n"
               "   range is reached. PLAY requests may be pipelined (queued); a server\n"
               "   MUST queue PLAY requests to be executed in order.\n")
        ss = raw.index("the range specified")
        se = ss + len("the range specified and delivers stream data until the end of the")
        merged, before, after = _logical_sentence(raw, ss, se)
        # 合并后应覆盖**整个**逻辑句（含上一行的前半句 + 下一行的后半句）
        assert merged.startswith("The PLAY request positions")
        assert merged.endswith("range is reached.")
        assert "PLAY requests may be pipelined" not in merged   # 只取一句，不越界
        # 候选之前有内容且不以句末标点结尾 ⇒ 句子从中途开始
        assert before.strip() != ""
        assert not _TERMINATOR_AT_END.search(before.rstrip())
        # 候选之后有内容 ⇒ 句子尚未结束
        assert "range is reached" in after

    def test_logical_sentence_does_not_absorb_next_sentence(self):
        """★ 候选**本身已以句末标点结尾** ⇒ 句界就在候选末尾，**不可**并入下一句。

        ⚠ 实测踩到：早期版本无条件向后找句界 ⇒
        ``Session identifiers are opaque strings of arbitrary length.``
        被错并成 ``...arbitrary length. Linear white space must be URL-escaped.``
        ⇒ 预测「文本会变」而实际**不变**（假阳性）。
        这条测试把该 bug 钉死。
        """
        from scripts.annotate_candidates import _logical_sentence
        raw = ("   Session identifiers are opaque strings of arbitrary length. Linear\n"
               "   white space must be URL-escaped. A session identifier MUST be chosen\n"
               "   randomly and MUST be at least eight octets long to make guessing it\n"
               "   more difficult.\n")
        first = "Session identifiers are opaque strings of arbitrary length."
        ss = raw.index(first)
        se = ss + len(first)
        merged, _, _ = _logical_sentence(raw, ss, se)
        assert merged == first
        assert "white space must be URL-escaped" not in merged

    def test_logical_sentence_keeps_structural_line_standalone(self):
        """★ 表格行**不跨行合并**（否则会得到无意义的「Accept | Accept-Encoding |」串）。"""
        from scripts.annotate_candidates import _logical_sentence
        raw = ("                  |          Accept                   ; Section 12.1\n"
               "                  |          Range                    ; Section 12.29\n"
               "                  |          Referer                  ; Section 12.30\n")
        ss = raw.index("|          Range")
        se = ss + len("|          Range                    ; Section 12.29")
        merged, _, _ = _logical_sentence(raw, ss, se)
        assert merged == "|          Range                    ; Section 12.29"
        assert "Accept" not in merged

    def test_impact_on_real_frozen_set(self):
        """★ 对真实冻结集：绝大多数候选都是半句 ⇒ 粒度修正会改变它们。"""
        from scripts.annotate_candidates import granularity_impact, summarize_impact
        frozen_path = ROOT / "derived" / "experiments" / "annotation" / "candidates_frozen.jsonl"
        if not frozen_path.is_file():
            pytest.skip("冻结集尚未生成")
        frozen = [json.loads(line) for line in
                  frozen_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows = granularity_impact(frozen, {})
        summary = summarize_impact(rows)
        assert summary["total"] == len(frozen)
        # ★ 核心事实：半句占绝大多数（这是「粒度是瓶颈」的量化证据）
        assert summary["text_changes"] > summary["total"] * 0.8
        # 结构性行不应被算成「会变」
        assert summary["structural"] <= 12
        for r in rows:
            if r["structural"]:
                assert r["text_changes"] is False

    def test_impact_detects_verdict_flips(self):
        """★ 合并后**新出现规范动词** ⇒ 原「否/无」结论必须翻转。"""
        from scripts.annotate_candidates import granularity_impact
        frozen_path = ROOT / "derived" / "experiments" / "annotation" / "candidates_frozen.jsonl"
        if not frozen_path.is_file():
            pytest.skip("冻结集尚未生成")
        frozen = [json.loads(line) for line in
                  frozen_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows = granularity_impact(frozen, {})
        flips = [r for r in rows if r["verdict_may_flip"]]
        assert flips, "应至少发现一条「结论可能翻转」的条目"
        for r in flips:
            # 翻转的前提：旧文本没有规范动词，新文本有
            assert not _NORMATIVE_RE.search(r["text"]), r["candidate_id"]
            assert _NORMATIVE_RE.search(r["merged_text"]), r["candidate_id"]

    def test_impact_prediction_accuracy_against_real_extractor(self):
        """★ **预测工具 vs 真实抽取器**的对照检验（本工具的价值证明）。

        当 ``core/fused/rfc_extractor.py`` 已落地粒度修正时，
        本工具对「哪些已标注条目会失效」的预测应当**几乎全对**。
        判据：对**完整候选池**（不是 120 抽样）比对
          · 实际失效 = 旧 id 在新池中**不存在**
          · 预测失效 = 本工具判定 ``text_changes``
        要求：召回率 = 100%（**零漏报** —— 漏报会让重标做不全），
             精确率 ≥ 95%（多报只多做几次复核，不会漏标）。
        """
        from scripts.annotate_candidates import granularity_impact
        import hashlib as _h
        frozen_path = ROOT / "derived" / "experiments" / "annotation" / "candidates_frozen.jsonl"
        if not frozen_path.is_file():
            pytest.skip("冻结集尚未生成")
        try:
            from core.fused.rfc_extractor import extract_constraint_candidates
        except Exception:                                  # pragma: no cover
            pytest.skip("抽取器不可用")

        def _cid(p, c):
            raw = "|".join([p, str(c.get("source") or ""),
                            str(c.get("span_start")), str(c.get("text") or "")])
            return f"{p}-{_h.sha256(raw.encode('utf-8')).hexdigest()[:12]}"

        pool = {}
        for p in ("rtsp", "sip", "smtp"):
            for c in extract_constraint_candidates(p):
                pool[_cid(p, c)] = c
        if not pool:
            pytest.skip("新抽取器未产出候选")

        frozen = [json.loads(line) for line in
                  frozen_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows = granularity_impact(frozen, {})
        gone = {r["candidate_id"] for r in rows if r["candidate_id"] not in pool}
        pred = {r["candidate_id"] for r in rows if r["text_changes"]}
        if not gone:
            pytest.skip("抽取器尚未变更（无失效条目可对照）")
        hit = gone & pred
        recall = len(hit) / len(gone)
        precision = len(hit) / max(1, len(pred))
        assert recall == 1.0, f"漏报 {len(gone - pred)} 条 ⇒ 重标会做不全"
        assert precision >= 0.95, f"精确率 {precision:.1%} 偏低"

    def test_impact_is_read_only(self, tmp_path):
        """★ 本工具**只读** —— 不得改标注文件、不得写任何东西。"""
        from scripts.annotate_candidates import granularity_impact
        frozen_path = ROOT / "derived" / "experiments" / "annotation" / "candidates_frozen.jsonl"
        truth_path = ROOT / "derived" / "experiments" / "annotation" / "truth" / "rtsp.annotated.json"
        if not (frozen_path.is_file() and truth_path.is_file()):
            pytest.skip("标注集尚未生成")
        frozen = [json.loads(line) for line in
                  frozen_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        anns = json.loads(truth_path.read_text(encoding="utf-8"))
        before = truth_path.read_bytes()
        granularity_impact(frozen, {a["candidate_id"]: a for a in anns})
        assert truth_path.read_bytes() == before


#: RFC 2119 关键词（供 TestGranularityImpact 判定「新出现规范动词」）。
_NORMATIVE_RE = re.compile(
    r"\b(MUST NOT|MUST|SHALL NOT|SHALL|REQUIRED|SHOULD NOT|SHOULD|"
    r"RECOMMENDED|NOT RECOMMENDED|MAY NOT|MAY|OPTIONAL)\b")

#: 「本段文字到此结束」的位置判定（用于判断候选是否覆盖到段落末尾的句号）。
_TERMINATOR_AT_END = re.compile(r"[.!?][\"'’”)\]]*\s*$")


class TestVocabulary:
    def test_operator_vocabulary_matches_roadmap(self):
        """★ OPERATORS 必须与 roadmap §3.1 逐项相等（10 个）。"""
        assert OPERATORS == frozenset({
            "eq", "ne", "lt", "gt", "le", "ge", "in", "present", "absent", "range"})

    def test_modality_vocabulary(self):
        assert MODALITIES == frozenset({"MUST", "SHOULD", "MAY", "无"})

    def test_response_class_vocabulary_matches_rfc_config(self):
        """★ 期望响应类别必须与各协议 rfc_config.expected_response_classes 一致。"""
        import json as _json
        for proto in ("rtsp", "sip", "smtp"):
            cfg_path = (ROOT / "fused_hub" / "targets" / proto / "rfc_config.json")
            if not cfg_path.is_file():
                continue
            cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
            assert set(cfg["expected_response_classes"]) == set(RESPONSE_CLASSES), \
                f"{proto} 的 expected_response_classes 与标注词表漂移"

    def test_threshold_matches_roadmap(self):
        assert KAPPA_THRESHOLD == 0.6
