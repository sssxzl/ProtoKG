"""tests/fused/test_rag_seedgen_step2.py —— 第二步：subgraph 检索 + ReAct + 落盘。"""
from __future__ import annotations

from core.fused.downstream.rag_seedgen import (
    load_fact_views, assemble_bundle, retrieve_subgraph,
    generate_seeds_react, write_seeds,
)
from core.models import SeedCorpus, SeedMessage


class _ReplayLLM:
    """按顺序回放响应，用于测 ReAct 多轮（每轮不同响应）。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0) if self.responses else []


def _bundle():
    return assemble_bundle(load_fact_views())


# ===========================================================================
# subgraph 检索
# ===========================================================================

def test_retrieve_subgraph_hops1_only_setup():
    b = _bundle()
    sub = retrieve_subgraph(b, target_methods=["SETUP"], k_hops=1)
    assert set(sub["methods"].keys()) == {"SETUP"}
    assert set(sub["headers"].keys()) == {"CSeq", "Transport"}
    assert all(t[1] == "SETUP" for t in sub["transitions"])


def test_retrieve_subgraph_hops2_expands_neighbors():
    b = _bundle()
    sub = retrieve_subgraph(b, target_methods=["SETUP"], k_hops=2)
    # 2-hop 从 SETUP 的状态出发，扩展到 PLAY 等相邻 method
    assert "PLAY" in sub["methods"]
    assert ("Init", "SETUP", "Ready") in sub["transitions"]


def test_retrieve_subgraph_no_target_returns_full():
    b = _bundle()
    sub = retrieve_subgraph(b)
    assert sub is b  # 无目标 → 全量（同一对象）


def test_retrieve_subgraph_filters_security_by_subject():
    b = _bundle()
    sub = retrieve_subgraph(b, target_methods=["SETUP"], k_hops=1)
    # SETUP 的 security 保留
    assert any(t == "method" and n == "SETUP" for t, n, _ in sub["security"])


# ===========================================================================
# ReAct 迭代 refine
# ===========================================================================

def _valid_resp():
    return [{
        "description": "SETUP→PLAY",
        "state_path": ["Init", "Ready", "Playing"],
        "messages": [
            {"method": "SETUP",
             "headers": {"CSeq": "1", "Transport": "RTP/AVP"}, "body": ""},
            {"method": "PLAY",
             "headers": {"CSeq": "2", "Session": "{{session_id}}"}, "body": ""},
        ],
    }]


def test_react_first_round_invalid_then_corrected():
    b = _bundle()
    llm = _ReplayLLM([
        # 第 1 轮: Init 直接 PLAY（非法）
        [{"description": "bad", "state_path": ["Init"],
          "messages": [{"method": "PLAY",
                        "headers": {"CSeq": "1", "Session": "x"}, "body": ""}]}],
        # 第 2 轮: 修正为合法
        _valid_resp(),
    ])
    seeds = generate_seeds_react(b, llm, protocol="RTSP", n_seeds=1)
    assert len(llm.calls) == 2  # 跑了两轮
    assert seeds and seeds[0].messages[0].method == "SETUP"


def test_react_valid_first_round_stops_early():
    b = _bundle()
    llm = _ReplayLLM([_valid_resp()])
    seeds = generate_seeds_react(b, llm, protocol="RTSP", n_seeds=1)
    assert len(llm.calls) == 1  # 首轮即过，不重生成
    assert seeds


def test_react_passes_feedback_into_prompt():
    b = _bundle()
    llm = _ReplayLLM([
        [{"description": "bad", "state_path": ["Init"],
          "messages": [{"method": "FOOBAR",
                        "headers": {"CSeq": "1"}, "body": ""}]}],
        _valid_resp(),
    ])
    generate_seeds_react(b, llm, protocol="RTSP", n_seeds=1)
    # 第二轮 prompt 应含第一轮错误反馈
    assert "[上一轮校验错误" in llm.calls[1]["user"]
    assert "未知方法" in llm.calls[1]["user"]


# ===========================================================================
# .raw 落盘
# ===========================================================================

def test_write_seeds_writes_raw_files(tmp_path):
    seed = SeedCorpus(
        protocol="rtsp",
        target_methods=["SETUP", "PLAY"],
        messages=[
            SeedMessage("SETUP", {"CSeq": "1", "Transport": "RTP/AVP"}, ""),
            SeedMessage("PLAY", {"CSeq": "2", "Session": "{{session_id}}"}, ""),
        ],
    )
    written = write_seeds([seed], tmp_path)
    assert len(written) == 1
    raw = (tmp_path / written[0]).read_bytes().decode("utf-8")
    assert raw.startswith("SETUP ")
    assert "CSeq: 1" in raw
    assert "RTSP/1.0" in raw
