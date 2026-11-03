# -*- coding: utf-8 -*-
"""tests/fused/test_rfc_field_value_samples.py —— 批次 2.0（P0）RFC 字段取值样本。

★ 背景：RFC 源此前只贡献 syntax + definition ⇒ 知识中枢 ``headers`` 桶
  **取值池大面积为空**（rtsp 28/58 = 48%、sip 26/63 = 41%，且 sip 的
  **必填头** Via/From/To/CSeq/Call-ID/Max-Forwards **全空**）
  ⇒ 直接压制 ⑤ 层 ``value-pool-boundary`` 规则（没有另一个取值可换）
  ⇒ 也是批次 1 里 R-2（CSeq 取值池空）的根因。
  而 RFC 规范里**明确写着**这些头的合法取值 ⇒ **是漏抽，不是规范里没有**。

★ 覆盖八条：
  ① "Example of use:" 引导段能抽到
  ② 连续 ≥2 行的头块（完整报文示例）能抽到
  ③ **散文不被抽到**（"Server: A server is a network element…"）
  ④ 值清洗：含空格的散文被拒
  ⑤ 头名**大小写归一**（Content-length / CONTENT / expires 不重复）
  ⑥ norm → fact：aspect=value_enum、value type=set
  ⑦ 协议级**跨文件合并**（同名字段的取值合并而非丢弃）
  ⑧ 中枢里 value_enum 进 ``headers`` 桶（消费端能用）
"""
from __future__ import annotations

from core.fused import rfc_extractor as RX   # noqa: E402
from core.fused import norm as NORM           # noqa: E402

PROTOCOL = "rtsp"


# ===========================================================================
# ① ② 语境判别
# ===========================================================================

def test_example_lead_block_is_extracted():
    """★ "Example of use:" 引导段能抽到。"""
    text = (
        "12.1 Accept\n"
        "\n"
        "   The Accept request-header field specifies content types.\n"
        "\n"
        "   Example of use:\n"
        "     Accept: application/rtsl, application/sdp;level=2\n"
    )
    out = RX._extract_field_value_samples(
        text.splitlines(), {"accept": "Accept"})
    assert out["Accept"] == ["application/rtsl, application/sdp;level=2"]


def test_contiguous_header_block_is_extracted():
    """★ 连续 ≥2 行的头块（完整报文示例）能抽到。"""
    text = (
        "INVITE sip:alice@atlanta.com SIP/2.0\n"
        "Via: SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bK776asdhds\n"
        "Max-Forwards: 70\n"
        "To: Alice <sip:alice@atlanta.com>\n"
        "CSeq: 314159 INVITE\n"
        "Call-ID: a84b4c76e66710@pc33.atlanta.com\n"
    )
    known = {"via": "Via", "max-forwards": "Max-Forwards", "to": "To",
             "cseq": "CSeq", "call-id": "Call-ID"}
    out = RX._extract_field_value_samples(text.splitlines(), known)
    assert out["Via"][0].startswith("SIP/2.0/UDP")
    assert out["Max-Forwards"] == ["70"]
    assert out["CSeq"] == ["314159 INVITE"]
    assert out["Call-ID"] == ["a84b4c76e66710@pc33.atlanta.com"]


# ===========================================================================
# ③ 散文不被抽到
# ===========================================================================

def test_prose_line_is_not_extracted():
    """★ 散文里的 "Name: ..." **不被抽到**（单行、不在连续块内）。"""
    text = (
        "12.1 Server\n"
        "\n"
        "   Server: A server is a network element that receives requests in\n"
        "   order to process the requests and generate a response.\n"
    )
    out = RX._extract_field_value_samples(text.splitlines(),
                                          {"server": "Server"})
    assert "Server" not in out


def test_unknown_header_name_is_not_extracted():
    """★ 头名不在已知字段集合里 ⇒ 不抽（避免正文噪音）。"""
    text = "Note: this is just a note\nSecond: another\n"
    out = RX._extract_field_value_samples(text.splitlines(), {"accept": "Accept"})
    assert out == {}


# ===========================================================================
# ④ 值清洗
# ===========================================================================

def test_value_cleaning_rejects_prose_with_spaces():
    """★ 含空格且首 token 不像 token ⇒ 判为散文，拒收。"""
    assert RX._clean_sample_value("A server is a network element") == ""
    assert RX._clean_sample_value("application/sdp") == "application/sdp"
    assert RX._clean_sample_value("SETUP, PLAY") == "SETUP, PLAY"
    assert RX._clean_sample_value(
        "SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bK") == \
        "SIP/2.0/UDP pc33.atlanta.com;branch=z9hG4bK"
    # 续行符要去掉
    assert RX._clean_sample_value("application/sdp \\") == "application/sdp"
    # 超长 ⇒ 拒
    assert RX._clean_sample_value("x" * 200) == ""


# ===========================================================================
# ⑤ 头名大小写归一
# ===========================================================================

def test_header_name_case_is_normalized():
    """★ 大小写变体归到同一规范字段名（不重复计数）。"""
    text = (
        "Content-Type: application/sdp\n"
        "Content-Length: 142\n"
    )
    known = {"content-type": "Content-Type", "content-length": "Content-Length"}
    out = RX._extract_field_value_samples(text.splitlines(), known)
    assert set(out) == {"Content-Type", "Content-Length"}
    assert out["Content-Type"] == ["application/sdp"]


# ===========================================================================
# ⑥ norm → fact
# ===========================================================================

def test_field_value_norm_maps_to_value_enum_fact():
    """★ aspect=value_enum、value type=set、subject type=header。"""
    norm = {
        "norm_id": "rtsp.field_value.accept",
        "kind": "field_value",
        "name": "Accept",
        "content": "Accept | values: application/sdp |~| application/rtsl",
        "kb_source_type": "rfc",
        "source": "file:rfc2326.txt#@samples",
        "protocol": PROTOCOL,
    }
    facts = NORM.field_value_norm_to_facts(norm)
    assert len(facts) == 1
    fk = facts[0].fact_key
    assert fk.aspect == "value_enum"
    assert fk.subject.type == "header"
    assert fk.subject.name == "Accept"
    claim = facts[0].claims[0]
    assert claim.value.type == "set"
    assert set(claim.value.data) == {"application/sdp", "application/rtsl"}


def test_field_value_norm_is_registered_in_kind_map():
    """★ 新 kind 已注册到 RFC_KIND_MAP（否则映射器返回 0 条 ⇒ 静默丢失）。"""
    assert "field_value" in NORM.RFC_KIND_MAP
    norm = {
        "kind": "field_value", "name": "X",
        "content": "X | values: v1 |~| v2",
        "kb_source_type": "rfc", "source": "file:a.txt#@samples",
        "protocol": PROTOCOL,
    }
    assert len(NORM.map_norm_to_facts(norm)) == 1


# ===========================================================================
# ⑦ 协议级跨文件合并
# ===========================================================================

def test_protocol_level_merge_of_field_values():
    """★ 同名字段跨文件 ⇒ 取值**合并**（不丢弃后续文件的取值）。"""
    merged = RX._parse_value_samples("Accept | values: a |~| b")
    assert merged == ["a", "b"]
    # 合并后 content 重新拼装 ⇒ 解析回来仍是完整列表
    body = "Accept | values: " + RX.VALUE_SAMPLE_SEP.join(merged + ["c"])
    assert RX._parse_value_samples(body) == ["a", "b", "c"]


# ===========================================================================
# ⑧ 中枢里 value_enum 进 headers 桶
# ===========================================================================

def test_value_enum_lands_in_headers_bucket():
    """★ value_enum fact ⇒ ``headers`` 桶的取值池（消费端能用）。"""
    from core.fused.downstream.rag_seedgen import assemble_bundle

    view = {
        "fact_key": {
            "protocol": PROTOCOL, "version": "1.0",
            "subject": {"type": "header", "name": "Accept",
                        "qualifiers": {}, "path": []},
            "aspect": "value_enum", "condition": {"type": "always"},
        },
        "resolution": None,
        "all_claims": [{
            "claim_id": "c1", "fact_id": "f1",
            "value": {"type": "set", "data": ["application/sdp",
                                              "application/rtsl"]},
            "epistemic_type": "normative_unspecified", "authority": "rfc",
            "scope": None, "evidence_summary": ["rfc:Accept"],
            "confidence": None,
        }],
    }
    b = assemble_bundle([view], PROTOCOL)
    assert b["headers"]["Accept"]["values"] == ["application/rtsl",
                                                  "application/sdp"]
    # ★ 溯源可追到 rfc 源
    assert b["by_source"]["headers"] == {"rfc": 1}
