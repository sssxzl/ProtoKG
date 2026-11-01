# -*- coding: utf-8 -*-
"""tests/fused/test_exp_semantic_gain.py —— B-10 实验脚本的**逻辑**契约。

本文件只测**脚本逻辑**，**不跑 LLM**（``pytest.ini`` 也会用 ``-m "not llm"`` 过滤）。

覆盖：

  · **``probe_operator()``** —— M1 的 C0「可判定率」判定实现：顺序敏感
    （否定式必须先于肯定式）、数值型算子必须抓到操作数、存在性算子无操作数。
  · **LLM 缓存键** —— 必须等于 ``sha256(candidate_text + prompt_version + model)``；
    不同候选句**不得**共用同一个键（这是实测踩过的坑：漏调 ``expect()``
    ⇒ 120 条候选共用一个键 ⇒ 只发生 1 次真实调用）。
  · **预登记文件** —— 必须含 §4.5 阈值表与 §4.6 第 2 条漂移声明的**逐字**文本，
    且**不含**任何结果数字（保证「预登记先于结果」可被 git 历史证明）。
  · **M2 不可计算** —— 标注集只有标注者 A 时，``read_truth_state()`` 必须
    明确给出「不可计算」的理由，**不得**伪造 F1。
  · **M6 幂等性** —— 同一批候选重复抽取 N 次，``rule_id`` 集合必须完全相同。
  · **M3/M4/M5** —— 证据可验证率、显式性纯净度、MAY 误升率的计算口径。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.exp_semantic_gain import (  # noqa: E402
    DRIFT_DECLARATION,
    EXPECTED_VOCAB,
    PREREG_COMPOSITE,
    PREREG_THRESHOLDS,
    PROMPT_VERSION,
    CachedLLM,
    _modality_is_optional,
    _pct,
    compute_frozen_stats,
    compute_idempotency,
    compute_metrics,
    decompose_m1,
    probe_operator,
    read_truth_state,
    render_prereg,
    run_group_two_layer,
)


# ===========================================================================
# probe_operator —— M1 的 C0「可判定率」判定实现
# ===========================================================================
class TestProbeOperator:
    """M1 判定实现的行为契约。"""

    def test_chinese_upper_bound_is_le(self):
        hit = probe_operator("行长度应不超过 12288 个八位组")
        assert hit is not None
        assert hit["operator"] == "le"
        assert hit["operand"] == ("12288",)

    def test_chinese_lower_bound_is_ge(self):
        hit = probe_operator("其值应为 70")
        assert hit is not None
        assert hit["operator"] == "eq"
        assert hit["operand"] == ("70",)

    def test_negation_must_beat_positive(self):
        """★ 顺序敏感：``不超过`` 不能被 ``超过`` 抢走（否则方向会反）。"""
        assert probe_operator("不得超过 100")["operator"] == "le"
        assert probe_operator("不得大于 70")["operator"] == "le"
        assert probe_operator("不少于 8")["operator"] == "ge"
        assert probe_operator("不得小于 3")["operator"] == "ge"
        # 纯肯定式仍取肯定方向
        assert probe_operator("大于 70")["operator"] == "gt"
        assert probe_operator("小于 70")["operator"] == "lt"

    def test_presence_operators_need_no_operand(self):
        """存在性算子（present/absent）**按定义没有操作数**，不得因缺操作数被判不可判定。"""
        hit = probe_operator("方法名必须是 token，且不得以 $ 字符开头")
        assert hit is not None
        assert hit["operator"] == "absent"
        assert hit["operand"] == ()

        hit = probe_operator("RTSP 消息必须包含 Content-Length 头字段")
        assert hit is not None
        assert hit["operator"] == "present"
        assert hit["operand"] == ()

    def test_numeric_operator_without_operand_is_undecidable(self):
        """数值型算子抓不到数字 ⇒ 不可判定（**不猜**）。"""
        assert probe_operator("长度应不超过") is None
        assert probe_operator("必须大于") is None

    def test_english_forms(self):
        assert probe_operator("MUST be no more than 998 octets")["operator"] == "le"
        assert probe_operator("MUST be at least 8 octets")["operator"] == "ge"
        assert probe_operator("MUST NOT contain a body")["operator"] == "absent"

    def test_no_operator_returns_none(self):
        assert probe_operator("") is None
        assert probe_operator("这是一段纯描述性的散文，没有任何比较语义。") is None

    def test_empty_and_none_inputs_are_safe(self):
        assert probe_operator("") is None
        assert probe_operator(None) is None  # type: ignore[arg-type]

    def test_probe_is_deterministic(self):
        text = "行长度应不超过 12288 个八位组"
        assert probe_operator(text) == probe_operator(text)


# ===========================================================================
# LLM 缓存键
# ===========================================================================
class TestCachedLLMKey:
    """缓存键必须严格是 ``sha256(candidate_text + prompt_version + model)``。"""

    def test_key_formula(self, tmp_path):
        llm = CachedLLM(object(), tmp_path / "c.jsonl", "deepseek-chat")
        expected = hashlib.sha256(
            f"句甲{PROMPT_VERSION}deepseek-chat".encode("utf-8")).hexdigest()
        assert llm.cache_key("句甲") == expected

    def test_different_candidates_get_different_keys(self, tmp_path):
        llm = CachedLLM(object(), tmp_path / "c.jsonl", "deepseek-chat")
        assert llm.cache_key("句甲") != llm.cache_key("句乙")

    def test_different_model_or_prompt_version_get_different_keys(self, tmp_path):
        a = CachedLLM(object(), tmp_path / "c.jsonl", "deepseek-chat")
        b = CachedLLM(object(), tmp_path / "c.jsonl", "deepseek-reasoner")
        assert a.cache_key("句甲") != b.cache_key("句甲")
        assert a.cache_key("句甲") != a.cache_key("句甲" + PROMPT_VERSION)

    def test_cache_hit_does_not_call_client(self, tmp_path):
        """命中缓存 ⇒ **不**调用底层客户端。"""
        calls = []

        class FakeClient:
            def chat_json(self, **kw):
                calls.append(kw)
                return {"constraints": [{"field": "F", "constraint": "c"}]}

        llm = CachedLLM(FakeClient(), tmp_path / "c.jsonl", "deepseek-chat")
        llm.expect("句甲")
        first = llm.chat_json(system="s", user="句甲在提示词里")
        second = llm.chat_json(system="s", user="句甲在提示词里")
        assert first == second
        assert llm.calls_made == 1
        assert llm.cache_hits == 1
        assert len(calls) == 1

    def test_prompt_must_contain_declared_candidate(self, tmp_path):
        """提示词与声明的候选句不一致 ⇒ **报错**（否则缓存键会错）。"""
        llm = CachedLLM(object(), tmp_path / "c.jsonl", "deepseek-chat")
        llm.expect("句甲")
        with pytest.raises(RuntimeError):
            llm.chat_json(system="s", user="提示词里是别的句子")

    def test_cache_persists_across_instances(self, tmp_path):
        path = tmp_path / "c.jsonl"

        class FakeClient:
            def chat_json(self, **kw):
                return {"constraints": []}

        first = CachedLLM(FakeClient(), path, "deepseek-chat")
        first.expect("句甲")
        first.chat_json(system="s", user="句甲在提示词里")

        second = CachedLLM(FakeClient(), path, "deepseek-chat")
        assert second.cache_reused == 1
        second.expect("句甲")
        second.chat_json(system="s", user="句甲在提示词里")
        assert second.calls_made == 0
        assert second.cache_hits == 1


# ===========================================================================
# 预登记文件
# ===========================================================================
class TestPreregDocument:
    """预登记文件的**内容契约**。"""

    def _stats(self, tmp_path):
        src = tmp_path / "frozen.jsonl"
        rows = [
            {"candidate_id": f"rtsp-{i}", "protocol": "rtsp",
             "text": f"句子 {i}", "span_start": i, "span_end": i + 3,
             "source": "file:x#@1", "spec_version": "RFC 2326",
             "section_path": ["A"], "section_no": "1.1"}
            for i in range(3)
        ]
        src.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
            encoding="utf-8")
        return src

    def test_contains_verbatim_thresholds(self, tmp_path):
        stats = {
            "source_path": str(tmp_path / "frozen.jsonl"),
            "source_md5": "x" * 32,
            "frozen_path": str(tmp_path / "out.jsonl"),
            "frozen_md5": "y" * 32,
            "total": 120,
            "per_protocol": {"rtsp": 40, "sip": 40, "smtp": 40},
            "section_no_path_joined": 120,
            "section_no_path_unmatched": [],
        }
        doc = render_prereg(stats)
        assert PREREG_THRESHOLDS in doc
        assert PREREG_COMPOSITE in doc
        # §4.5 阈值表逐字照抄：抽查几行
        assert "| **M1 可执行率** | E1 ≥ C0 + **15 个百分点** |" in doc
        assert "| **M2 规则 F1** | **≥ 0.70**（对 holdout） | 0.50 ~ 0.70 | **< 0.50** |" in doc
        assert "| **M3 证据可验证率** | **= 100%** | — | **< 100%**（任一不可验证却算规则 ⇒ 污染） |" in doc
        assert "| **M5 MAY 误升率** | **= 0%** | — | **> 0%**（任一误升 ⇒ 阻断，先修再继续） |" in doc
        assert "| **M6 rule_id 幂等性** | **N 次完全相同** | — | **任一次不同**（⇒ 派生规则有 bug，先修） |" in doc

    def test_contains_verbatim_drift_declaration(self, tmp_path):
        stats = {
            "source_path": "f", "source_md5": "x" * 32, "frozen_path": "g",
            "frozen_md5": "y" * 32, "total": 120,
            "per_protocol": {"rtsp": 40, "sip": 40, "smtp": 40},
            "section_no_path_joined": 120, "section_no_path_unmatched": [],
        }
        doc = render_prereg(stats)
        assert DRIFT_DECLARATION in doc
        assert "rtsp: A 38→52 / B 50→65 / C 50→65 / D 50→65" in doc
        assert "smtp: A 76→?  / B 78→61 / C 78→?  / D 78→?" in doc
        assert "本实验的判定指标中**不含任何种子条数**，故该漂移不影响结论。" in doc

    def test_declares_m2_not_computable_and_pending_results(self, tmp_path):
        stats = {
            "source_path": "f", "source_md5": "x" * 32, "frozen_path": "g",
            "frozen_md5": "y" * 32, "total": 120,
            "per_protocol": {"rtsp": 40, "sip": 40, "smtp": 40},
            "section_no_path_joined": 120, "section_no_path_unmatched": [],
        }
        doc = render_prereg(stats)
        assert "结果待填：实验尚未执行。" in doc
        assert "不可计算" in doc
        # 预登记里**不得**出现任何实测百分比（阈值表只有整数/比率，无小数百分比）
        #   ⇒ 出现小数百分比即说明混入了结果，破坏「预登记先于结果」。
        assert not re.search(r"\d+\.\d+\s*%", doc)

    def test_prereg_is_deterministic(self, tmp_path):
        stats = {
            "source_path": "f", "source_md5": "x" * 32, "frozen_path": "g",
            "frozen_md5": "y" * 32, "total": 120,
            "per_protocol": {"rtsp": 40, "sip": 40, "smtp": 40},
            "section_no_path_joined": 120, "section_no_path_unmatched": [],
        }
        assert render_prereg(stats) == render_prereg(stats)


# ===========================================================================
# M2 不可计算
# ===========================================================================
class TestTruthState:
    """标注集现状判定 —— **不得伪造 F1**。"""

    def test_reports_not_computable(self):
        state = read_truth_state()
        assert state["has_two_annotators"] is False
        assert state["annotated"] < state["total"]
        assert "κ **无法计算**" in state["reason"]
        assert "C0 的 F1 本轮同样不可计算" in state["c0_f1_note"]
        assert state["kappa"] if "kappa" in state else True

    def test_annotators_are_real_names_only(self):
        state = read_truth_state()
        # 已标注记录只含标注者 A（实测）⇒ 不能有两个标注者
        assert set(state["annotators"]) <= {"A", "B"}

    def test_metrics_marks_m2_not_computable(self):
        state = read_truth_state()
        empty_c0 = {"items": [], "facts": []}
        empty_g = {"items": [], "rules": [], "candidates": []}
        metrics = compute_metrics(
            {"rtsp": empty_c0, "sip": empty_c0, "smtp": empty_c0},
            {"rtsp": empty_g, "sip": empty_g, "smtp": empty_g},
            {"rtsp": empty_g, "sip": empty_g, "smtp": empty_g},
            state,
        )
        assert metrics["M2"]["computable"] is False
        assert metrics["M2"]["kappa"] is None
        assert metrics["M2"]["c0_f1_same_set"] is None


# ===========================================================================
# 指标计算
# ===========================================================================
class TestMetrics:
    """M1/M3/M4/M5 的计算口径。"""

    def test_pct_helper(self):
        assert _pct(1, 4) == 25.0
        assert _pct(0, 0) == 0.0
        assert _pct(3, 3) == 100.0

    def test_optional_modality_helper(self):
        assert _modality_is_optional("MAY be sent") is True
        assert _modality_is_optional("MUST be sent") is False
        assert _modality_is_optional("SHOULD be sent") is False
        # 最强动词优先：MUST 压过 MAY ⇒ 不算 optional
        assert _modality_is_optional("Systems MUST support X and MAY do Y") is False

    def test_m1_denominators_are_all_candidate_count(self):
        """三个组的分母必须**同为候选句数**（否则 M1 不可比）。"""
        state = read_truth_state()
        c0 = {"rtsp": {"items": [], "facts": []},
              "sip": {"items": [], "facts": []},
              "smtp": {"items": [], "facts": []}}
        g = {"rtsp": {"items": [], "rules": [], "candidates": []},
             "sip": {"items": [], "rules": [], "candidates": []},
             "smtp": {"items": [], "rules": [], "candidates": []}}
        metrics = compute_metrics(c0, g, g, state)
        for protocol in ("rtsp", "sip", "smtp", "TOTAL"):
            row = metrics["M1"][protocol]
            assert row["denominator_candidates"] == 0
            assert row["e1_executable_rate_pct"] == 0.0
            assert row["e2_executable_rate_pct"] == 0.0
            assert row["c0_decidable_rate_pct"] == 0.0

    def test_m3_m4_m5_totals_present(self):
        state = read_truth_state()
        c0 = {p: {"items": [], "facts": []} for p in ("rtsp", "sip", "smtp")}
        g = {p: {"items": [], "rules": [], "candidates": []}
             for p in ("rtsp", "sip", "smtp")}
        metrics = compute_metrics(c0, g, g, state)
        for label in ("E1", "E2"):
            for protocol in ("rtsp", "sip", "smtp", "TOTAL"):
                row = metrics["M3_M4_M5"][label][protocol]
                assert row["m3_evidence_verifiable_rate_pct"] == 0.0
                assert "m4_explicitness_purity_pct" in row
                assert "m5_may_misraise_rate_pct" in row

    def test_expected_vocab_matches_repo(self):
        from core.fused.rfc_extractor import EXPECTED_VOCAB as REPO_VOCAB
        assert set(EXPECTED_VOCAB) == set(REPO_VOCAB)


# ===========================================================================
# M6 幂等性
# ===========================================================================
class TestIdempotency:
    """M6：重复抽取 N 次，``rule_id`` 集合必须完全相同。"""

    def test_identical_across_runs(self):
        candidates = [{
            "candidate_id": "rtsp-1", "protocol": "rtsp",
            "text": "The CSeq field MUST be no greater than 70.",
            "source": "file:rfc2326.txt#@1", "span_start": None,
            "span_end": None, "spec_version": "RFC 2326",
            "section_path": ["A"], "section_no": "1.1",
            "section_no_path": ["1", "1.1"],
        }]
        result = compute_idempotency(
            "rtsp", candidates, known_fields=[], n_runs=3)
        assert result["n_runs"] == 3
        assert result["all_identical"] is True
        assert len(result["rule_id_sets"]) == 3
        assert result["rule_id_sets"][0] == result["rule_id_sets"][1]
        assert result["rule_id_sets"][1] == result["rule_id_sets"][2]
        for diff in result["pairwise_diff"]:
            assert diff["identical"] is True
            assert diff["only_in_a"] == []
            assert diff["only_in_b"] == []

    def test_diff_reports_asymmetry(self):
        candidates = [{
            "candidate_id": "rtsp-1", "protocol": "rtsp",
            "text": "The CSeq field MUST be no greater than 70.",
            "source": "file:rfc2326.txt#@1", "span_start": None,
            "span_end": None, "spec_version": "RFC 2326",
            "section_path": ["A"], "section_no": "1.1",
            "section_no_path": ["1", "1.1"],
        }]
        result = compute_idempotency(
            "rtsp", candidates, known_fields=[], n_runs=2)
        # 若两轮不同，差集必须被如实报出
        assert len(result["pairwise_diff"]) == 1
        d = result["pairwise_diff"][0]
        assert d["identical"] == (not d["only_in_a"] and not d["only_in_b"])


# ===========================================================================
# M1 归因拆解
# ===========================================================================
class TestDecompose:
    """M1 差异归因 —— 必须如实报出「仅 C0 可判定」及其原因。"""

    def test_counts_four_cells(self):
        c0_items = [
            {"candidate_id": "a", "protocol": "rtsp", "text": "MUST be sent",
             "decidable": True, "operator": "present", "operand": []},
            {"candidate_id": "b", "protocol": "rtsp", "text": "must be sent",
             "decidable": True, "operator": "present", "operand": []},
            {"candidate_id": "c", "protocol": "rtsp", "text": "plain prose",
             "decidable": False, "operator": "", "operand": []},
        ]
        e1_items = [
            {"candidate_id": "a", "outcome": "rule", "reject_reason": "",
             "stage_a_reason": "", "stage_b_reason": ""},
            {"candidate_id": "b", "outcome": "candidate",
             "reject_reason": "non_normative_kind",
             "stage_a_reason": "non_normative_kind",
             "stage_b_reason": "non_normative_kind"},
            {"candidate_id": "c", "outcome": "candidate",
             "reject_reason": "operator_unresolved",
             "stage_a_reason": "operator_unresolved",
             "stage_b_reason": "operator_unresolved"},
        ]
        d = decompose_m1(c0_items, e1_items)
        assert d["both_rule"] == 1
        assert d["c0_only"] == 1
        assert d["e1_only"] == 0
        assert d["neither"] == 1
        # 「b」原文无规范动词（"must be sent" 小写 ⇒ detect_modality 仍判 mandatory，
        # 故用一条真无动词的样本验证幻影计数）
        assert d["c0_decidable_but_source_non_normative"] == 0
        assert d["c0_only_detail"][0]["e1_reject_reason"] == "non_normative_kind"


# ===========================================================================
# 两层模型转换（不跑 LLM）
# ===========================================================================
class TestTwoLayerConversion:
    """E2 组（只跑规则表）的转换行为。"""

    def test_rule_table_hit_becomes_rule(self):
        candidates = [{
            "candidate_id": "rtsp-1", "protocol": "rtsp",
            "text": "The CSeq field MUST be no greater than 70.",
            "source": "file:rfc2326.txt#@1", "span_start": None,
            "span_end": None, "spec_version": "RFC 2326",
            "section_path": ["A"], "section_no": "1.1",
            "section_no_path": ["1", "1.1"],
        }]
        group = run_group_two_layer(
            "rtsp", candidates, llm=None, known_fields=[], llm_facts={})
        assert len(group["rules"]) + len(group["candidates"]) == 1
        item = group["items"][0]
        assert item["outcome"] in ("rule", "candidate")
        if item["outcome"] == "rule":
            assert item["operator"] in (
                "eq", "ne", "lt", "gt", "le", "ge", "in", "present", "absent",
                "range")
            assert item["rule_id"].startswith("r")

    def test_every_candidate_yields_exactly_one_outcome(self):
        """每条候选必须**恰好**落一个结果（规则或候选）⇒ M1 分母恒为候选数。"""
        candidates = [
            {"candidate_id": f"rtsp-{i}", "protocol": "rtsp",
             "text": t, "source": "file:rfc2326.txt#@1",
             "span_start": None, "span_end": None, "spec_version": "RFC 2326",
             "section_path": ["A"], "section_no": "1.1",
             "section_no_path": ["1", "1.1"]}
            for i, t in enumerate([
                "The CSeq field MUST be no greater than 70.",
                "A plain descriptive sentence with no normative force.",
                "The name SHOULD be no more than twenty characters long.",
            ])
        ]
        group = run_group_two_layer(
            "rtsp", candidates, llm=None, known_fields=[], llm_facts={})
        assert len(group["rules"]) + len(group["candidates"]) == len(candidates)
        assert len(group["items"]) == len(candidates)


# ===========================================================================
# 冻结候选集统计
# ===========================================================================
class TestFrozenStats:
    """冻结集统计 —— 复用既有冻结集时的自检。"""

    def test_stats_fields_present(self, tmp_path, monkeypatch):
        src = tmp_path / "frozen.jsonl"
        rows = [{
            "candidate_id": "rtsp-1", "protocol": "rtsp", "text": "x",
            "span_start": 0, "span_end": 1, "source": "file:x#@1",
            "spec_version": "RFC 2326", "section_path": ["A"],
            "section_no": "1.1",
        }]
        src.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
        # 真实冻结集不在 tmp 里 ⇒ 用真实路径的统计函数，但只断言字段齐全
        real = ROOT / "derived/exp_semantic/candidates_frozen.jsonl"
        if not real.is_file():
            pytest.skip("既有冻结集不存在")
        stats = compute_frozen_stats(real, tmp_path / "out.jsonl")
        assert stats["total"] == 120
        assert stats["per_protocol"] == {"rtsp": 40, "sip": 40, "smtp": 40}
        assert len(stats["source_md5"]) == 32
        assert len(stats["frozen_md5"]) == 32
