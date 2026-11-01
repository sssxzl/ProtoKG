"""tests/fused/test_traffic_extractor.py —— traffic extractor（client.log/rtsp.csv → norm）。"""
from __future__ import annotations

from core.fused.traffic_extractor import (
    _sanitize_auth, _extract_client_log, _extract_csv, extract_traffic_norms,
    _load_traffic_schema,
)


def test_sanitize_auth_redacts_credentials():
    raw = ('Digest username="admin", realm="IP Camera", nonce="0004cf", '
           'uri="rtsp://x/y", response="c976ae"')
    out = _sanitize_auth(raw)
    assert 'username="<user>"' in out
    assert 'nonce="<nonce>"' in out
    assert 'response="<response>"' in out
    assert '"admin"' not in out
    assert '"c976ae"' not in out
    assert 'realm="IP Camera"' in out  # realm 非敏感保留


def test_extract_client_log_kinds():
    log = (
        "Sending request: OPTIONS rtsp://10.0.0.1:554/x RTSP/1.0\n"
        "Cseq: 2\n"
        "User-Agent: LibVLC\n"
        "\n"
        "Received a complete response:\n"
        "RTSP/1.0 200 OK\n"
        "Cseq: 2\n"
        "Public: OPTIONS, DESCRIBE, PLAY\n"
        "\n"
        "Sending request: DESCRIBE rtsp://10.0.0.1:554/x RTSP/1.0\n"
        "Cseq: 3\n"
        "Authorization: Digest username=\"admin\", nonce=\"abc\", response=\"def\"\n"
    )
    import tempfile, os
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "client.log"
        p.write_text(log, encoding="utf-8")
        norms = _extract_client_log(p, "run1", "rtsp", _load_traffic_schema("rtsp"))
    kinds = {n["kind"] for n in norms}
    assert "message" in kinds
    assert "state_machine" in kinds
    assert "outcome" in kinds
    assert "field" in kinds
    # 方法存在性 = 实际调用 ∪ 服务器声明
    method_names = {n["name"] for n in norms if n["kind"] == "message"}
    assert {"OPTIONS", "DESCRIBE", "PLAY"} <= method_names
    # 脱敏生效：field norm 里不应出现明文凭据
    for n in norms:
        assert '"admin"' not in n["content"]
        assert '"def"' not in n["content"]
    # field 的 occurrence 与 samples 用不同 norm_id（去重时互不吞并）
    field_nids = {n["norm_id"] for n in norms if n["kind"] == "field"}
    assert any(nid.endswith(".occ") for nid in field_nids)
    assert any(nid.endswith(".samples") for nid in field_nids)


def test_extract_rtsp_csv_fallback():
    import tempfile, os
    from pathlib import Path
    csv_text = (
        "frame.number,rtsp.method,rtsp.status\n"
        "1,OPTIONS,\n"
        "2,,200\n"
        "3,DESCRIBE,\n"
        "4,,401\n"
    )
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "rtsp.csv"
        p.write_text(csv_text, encoding="utf-8")
        norms = _extract_csv(p, "run1", "rtsp", _load_traffic_schema("rtsp"))
    method_names = {n["name"] for n in norms if n["kind"] == "message"}
    assert {"OPTIONS", "DESCRIBE"} <= method_names
    assert any(n["kind"] == "outcome" for n in norms)


def test_extract_traffic_norms_nested_dirs():
    """数据流量目录两层嵌套（stream/run/client.log）也能被递归定位。"""
    norms = extract_traffic_norms("rtsp")
    assert len(norms) > 0
    kinds = {n["kind"] for n in norms}
    assert "message" in kinds
    assert "state_machine" in kinds


def test_infer_traffic_fields_llm_fallback():
    """LLM 兜底：从流量观测字段提取语义（对齐 LLM-Boofuzz「LLM 解析流量提取协议信息」）。"""
    from core.fused.traffic_extractor import infer_traffic_fields
    from core.llm import StubLLMClient
    stub = StubLLMClient(response={"fields": [
        {"name": "CSeq", "definition": "序列号，用于匹配请求与响应"},
        {"name": "Session", "definition": "会话标识"},
    ]})
    norms = infer_traffic_fields("rtsp", llm=stub)
    assert any(n["name"] == "CSeq" and "definition=" in n["content"]
               for n in norms)
    assert any(n["name"] == "Session" for n in norms)
    assert all(n["kind"] == "field" for n in norms)
    assert all(n["kb_source_type"] == "traffic_raw" for n in norms)
