"""tests/test_traffic.py —— traffic 源（pcap/raw 观测）→ Fact 映射。"""
from __future__ import annotations


from core.fused.extraction.traffic import (
    parse_message, parse_field_samples,
    parse_state_machine, parse_outcome, parse_distribution_keys,
    parse_bracketed_list, traffic_norm_to_facts, traffic_norms_to_facts,
)
from core.fused.hub.registry import load_registry
from core.fused.hub.validation import validate_fact

MESSAGE_NORM = {
    "norm_id": "message.describe", "protocol": "rtsp", "kind": "message",
    "name": "describe", "content": "method=DESCRIBE occurrences=1 protocol=rtsp",
    "source": "tcp_0001/capture.pcapng", "kb_source_type": "traffic_pcap",
}
FIELD_OCC_NORM = {
    "norm_id": "field.cseq", "protocol": "rtsp", "kind": "field",
    "name": "cseq", "content": "CSeq header occurrences=10 protocol=rtsp",
    "source": "tcp_0001/capture.pcapng", "kb_source_type": "traffic_pcap",
}
FIELD_SAMPLE_NORM = {
    "norm_id": "field.rtsp_url", "protocol": "rtsp", "kind": "field",
    "name": "rtsp_url",
    "content": "unique URLs=2 samples=['rtsp://a/x', 'rtsp://a/y']",
    "source": "tcp_0001/client.log", "kb_source_type": "traffic_raw",
}
SM_NORM = {
    "norm_id": "state_machine.rtsp_method_seq", "protocol": "rtsp",
    "kind": "state_machine", "name": "rtsp_method_seq",
    "content": "observed transitions: OPTIONS → DESCRIBE → SETUP → PLAY → TEARDOWN",
    "source": "tcp_0001/capture.pcapng", "kb_source_type": "traffic_pcap",
}
OUTCOME_NORM = {
    "norm_id": "outcome.rtsp_status_codes", "protocol": "rtsp", "kind": "outcome",
    "name": "rtsp_status_codes", "content": "status code distribution: {'200': 5}",
    "source": "tcp_0001/packets.ndjson", "kb_source_type": "traffic_raw",
}
PROTOCOL_NORM = {
    "norm_id": "protocol.rtsp_transport", "protocol": "rtsp", "kind": "protocol",
    "name": "rtsp_transport", "content": "transport distribution: {'TCP': 20, 'UDP': 35}",
    "source": "tcp_0001/capture.pcapng", "kb_source_type": "traffic_pcap",
}
ACTOR_NORM = {
    "norm_id": "actor.rtsp_server", "protocol": "rtsp", "kind": "actor",
    "name": "rtsp_server", "content": "RTSP server observed on ports [8554]",
    "source": "tcp_0001/capture.pcapng", "kb_source_type": "traffic_pcap",
}


# ===== 解析器 =====

def test_parse_message():
    assert parse_message("method=DESCRIBE occurrences=1 protocol=rtsp") == "DESCRIBE"
    assert parse_message("no method here") is None


def test_parse_field_samples():
    assert parse_field_samples("unique URLs=2 samples=['rtsp://a/x', 'rtsp://a/y']") == \
        ["rtsp://a/x", "rtsp://a/y"]
    assert parse_field_samples("no samples") is None


def test_parse_state_machine_both_arrows():
    assert parse_state_machine("observed transitions: A → B → C") == ["A", "B", "C"]
    assert parse_state_machine("observed methods: A -> B -> C") == ["A", "B", "C"]


def test_parse_outcome():
    assert parse_outcome("status code distribution: {'200': 5}") == [("200", 5)]
    assert parse_outcome("status code distribution: {'200': 5, '404': 2}") == \
        [("200", 5), ("404", 2)]


def test_parse_distribution_and_bracketed():
    assert parse_distribution_keys("transport distribution: {'TCP': 20, 'UDP': 35}") == \
        ["TCP", "UDP"]
    assert parse_bracketed_list("server-advertised methods (8): ['DESCRIBE', 'PLAY']") == \
        ["DESCRIBE", "PLAY"]
    assert parse_bracketed_list("RTSP server observed on ports [8554]") == ["8554"]


# ===== 映射 =====

def test_message_maps_existence():
    facts = traffic_norm_to_facts(MESSAGE_NORM)
    assert len(facts) == 1
    f = facts[0]
    assert f.fact_key.subject.type == "method"
    assert f.fact_key.subject.name == "DESCRIBE"
    assert f.fact_key.aspect == "existence"
    assert f.claims[0].value.type == "scalar" and f.claims[0].value.data is True
    assert f.claims[0].epistemic_type == "observed"
    assert f.claims[0].authority == "traffic"


def test_field_occurrence_not_produced_and_samples():
    """★ 2026-11-11：字段的 ``occurrences=N``（实测频次）**不再产出 fact**。

    ★ 理由：知识抽取层**面向知识源**⇒ 只有抓包能得到「实测频次」
      ⇒ 它属于**投放期观测**，不是协议知识 ⇒ 不该占知识维度。
    """
    assert traffic_norm_to_facts(FIELD_OCC_NORM) == []
    samp = traffic_norm_to_facts(FIELD_SAMPLE_NORM)[0]
    assert samp.fact_key.aspect == "value_enum_observed"   # ★ 阶段 E4：traffic 侧=实测样本
    assert samp.claims[0].value.data == ["rtsp://a/x", "rtsp://a/y"]


def test_state_machine_splits_into_adjacent_pairs():
    facts = traffic_norm_to_facts(SM_NORM)
    assert len(facts) == 4  # OPTIONS→DESCRIBE→SETUP→PLAY→TEARDOWN = 4 对
    for f in facts:
        assert f.fact_key.subject.type == "relation"
        assert f.fact_key.subject.name == "method_sequence"
        assert f.fact_key.aspect == "method_sequence"


def test_protocol_actor_status_mapping():
    p = traffic_norm_to_facts(PROTOCOL_NORM)[0]
    assert p.fact_key.subject.type == "protocol"
    assert p.claims[0].value.data == ["TCP", "UDP"]
    a = traffic_norm_to_facts(ACTOR_NORM)[0]
    assert a.fact_key.subject.type == "actor"
    assert a.claims[0].value.data == ["8554"]
    # ★ 2026-11-11：状态码分布（实测频次）**不再产出 fact** ⇒ 无 fact
    assert traffic_norm_to_facts(OUTCOME_NORM) == []


# ===== 去重 =====

def test_dedup_records_capture_count():
    """相同 norm_id 重复展开 → 去重为 1 fact，quote 记录 capture 数。"""
    norms = [MESSAGE_NORM] * 3 + [dict(MESSAGE_NORM, kb_source_type="traffic_raw")] * 2
    facts, skipped = traffic_norms_to_facts(norms)
    assert len(facts) == 1
    assert skipped == 0
    quote = facts[0].claims[0].evidence[0].quote
    assert "observed in 5 captures" in quote


# ===== 全量 + fail-closed =====

def test_all_real_traffic_norms_pass_fail_closed():
    """从数据流量目录抽取真实 traffic norm（client.log/rtsp.csv），映射后全过 fail-closed。"""
    from core.fused.extraction.traffic_extractor import extract_traffic_norms
    traffic_norms = extract_traffic_norms("rtsp")
    assert len(traffic_norms) > 0  # 真实流量至少抽出 message/state_machine
    facts, skipped = traffic_norms_to_facts(traffic_norms)
    assert len(facts) > 0
    registry = load_registry()
    for f in facts:
        validate_fact(f, registry)
