"""tests/fused/test_boundary_probe.py —— 边界探针单元测试（oracle mock，不依赖虚拟机）。"""
from __future__ import annotations

from core.fused.downstream.boundary_probe import (
    derive_boundary_param, generate_candidates, derive_semantic_candidates,
    probe_boundary, emit_boundary_fact, derive_constraint_candidates,
)
from core.fused.downstream.rag_seedgen import load_fact_views, assemble_bundle


class _Req:
    def __init__(self, action):
        self.action = action
        self.case_id = "test"


def _bundle():
    return assemble_bundle(load_fact_views())


# ============ 边界参数推导（源 B） ============

def test_derive_boundary_param_double_setup():
    p = derive_boundary_param(_Req("double_setup"))
    assert p is not None and p.dim == "track_number"


def test_derive_boundary_param_interleave():
    p = derive_boundary_param(_Req("interleave_seq"))
    assert p is not None and p.dim == "transport_switch"


def test_derive_boundary_param_unknown_action():
    # 字段型/未映射的 action 返回 None（边界探针不处理）
    assert derive_boundary_param(_Req("long_value")) is None
    assert derive_boundary_param(_Req("no_such_action")) is None


# ============ 候选生成（源 B） ============

def test_generate_candidates_double_setup_tracks():
    cands = dict(generate_candidates(_Req("double_setup"), "matroskaFileTest"))
    assert set(cands) == {"legal", "illegal"}
    legal = cands["legal"]
    illegal = cands["illegal"]
    # legal：不同 track；illegal：同 track（且第二个 SETUP 带触发 Session）
    legal_tracks = [m.url.split("/")[-1] for m in legal.messages if m.method == "SETUP"]
    illegal_tracks = [m.url.split("/")[-1] for m in illegal.messages if m.method == "SETUP"]
    assert legal_tracks == ["track1", "track2"]
    assert illegal_tracks == ["track1", "track1"]
    # illegal 的第二个 SETUP 带触发 Session 值
    setups = [m for m in illegal.messages if m.method == "SETUP"]
    assert setups[1].headers.get("Session") == "000022B8"


def test_generate_candidates_unknown_action_empty():
    assert generate_candidates(_Req("long_value")) == []


# ============ 候选生成（源 A，无需漏洞库） ============

def test_derive_semantic_candidates_self_loop_and_lifecycle():
    bundle = _bundle()
    cands = derive_semantic_candidates(bundle)
    labels = [l for l, _ in cands]
    assert labels.count("legal") >= 1 and labels.count("illegal") >= 1
    # 自环候选存在：含「重复 SETUP」的 illegal
    seqs = [tuple(m.method for m in s.messages) for _, s in cands]
    assert any(seq.count("SETUP") >= 2 for seq in seqs), "应有重复 SETUP 的自环 illegal 候选"


# ============ 边界定位（oracle mock） ============

def test_probe_boundary_picks_legal_when_illegal_crashes():
    legal = generate_candidates(_Req("double_setup"))[0][1]
    illegal = generate_candidates(_Req("double_setup"))[1][1]

    def oracle(seed):
        return seed is legal  # legal 合法，illegal 越界

    result = probe_boundary([("legal", legal), ("illegal", illegal)], oracle)
    assert result is legal


def test_probe_boundary_none_when_all_illegal():
    illegal = generate_candidates(_Req("double_setup"))[1][1]

    def oracle(seed):
        return False  # 全越界

    assert probe_boundary([("illegal", illegal)], oracle) is None


# ============ 边界回写（legal_boundary fact） ============

def test_emit_boundary_fact_structure():
    fact = emit_boundary_fact("SETUP", "track_number", "不同track", "同track", "Session=000022B8")
    fk = fact["fact_key"]
    assert fk["subject"]["type"] == "method"
    assert fk["subject"]["name"] == "SETUP"
    assert fk["aspect"] == "legal_boundary"
    val = fact["all_claims"][0]["value"]["data"]
    assert val["dim"] == "track_number"
    assert val["trigger"] == "Session=000022B8"
    assert fact["all_claims"][0]["authority"] == "boundary_probe"


# ============ 源 A 第四类：rfc 约束候选（SemFuzz C/P → legal_boundary） ============

def test_derive_constraint_candidates():
    bundle = {
        "legal_boundary": {
            "QNAME": [{"dim": "QNAME", "legal": "单 label 长度 <= 63",
                       "illegal": "长度字段 > 实际内容", "trigger": "FORMERR"}],
        },
        "response_expectation": {},
    }
    cands = derive_constraint_candidates(bundle)
    assert len(cands) == 2
    labels = [l for l, _ in cands]
    assert labels == ["legal", "illegal"]
    # illegal 候选携带超长字段值（违反约束）
    illegal = cands[1][1]
    assert any("A" * 300 == m.headers.get("QNAME") for m in illegal.messages)


def test_derive_constraint_candidates_empty_when_no_boundaries():
    assert derive_constraint_candidates({"legal_boundary": {}, "response_expectation": {}}) == []


def test_derive_constraint_candidates_skips_malformed():
    bundle = {"legal_boundary": {"X": [{"dim": "X", "legal": "", "illegal": "bad"}]}}
    assert derive_constraint_candidates(bundle) == []


def test_generate_protocol_dict_protocol_specific_and_clean():
    """协议定向字典：协议特定 token 自动出现（rtsp track/SETUP、smtp MAIL FROM/EHLO），
    且无脏 token（中文/引号/#/括号的源码注释、描述文本）。"""
    from core.fused.downstream.boundary_probe import generate_protocol_dict

    def _toks(proto):
        b = assemble_bundle(load_fact_views(proto), proto)
        d = generate_protocol_dict(b, protocol=proto)
        return [l.strip('"') for l in d.splitlines() if l.strip()]

    # rtsp：URL 模板 track{N} 推导出 track1/track2（同 track 双 SETUP 触发 UAF 的关键）
    rtsp = _toks("rtsp")
    assert {"SETUP", "DESCRIBE", "track1", "track2"} <= set(rtsp)

    # smtp：含空格命令（MAIL FROM / RCPT TO）保留
    smtp = _toks("smtp")
    assert {"EHLO", "MAIL FROM", "RCPT TO", "AUTH"} <= set(smtp)

    # 全部协议字典无脏 token（中文/引号/#/括号）
    for proto in ("rtsp", "sip", "smtp"):
        for t in _toks(proto):
            assert not any(ch in t for ch in '"\'#()（）'), f"[{proto}] 脏 token: {t!r}"
            assert not any('\u4e00' <= c <= '\u9fff' for c in t), f"[{proto}] 中文 token: {t!r}"
