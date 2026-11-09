"""tests/fused/test_source.py —— source 源（协议实现源码）→ Fact 映射。"""
from __future__ import annotations

import json
from pathlib import Path

from core.fused.source import source_norm_to_facts
from core.fused.registry import load_registry
from core.fused.validation import validate_fact

SOURCE_NORM = {
    "norm_id": "rtsp.source.method.options",
    "protocol": "rtsp",
    "kind": "method",
    "name": "OPTIONS",
    "content": "liveMedia 服务端实现接收并处理 OPTIONS 方法（定义处 E:\\科研\\想法idea\\rag-chatafl\\kb\\协议实现源码\\RTSPServer.cpp:354）",
    "source": "file:RTSPServer.cpp",
    "kb_source_type": "source",
}


def test_source_norm_to_fact_structure():
    facts = source_norm_to_facts(SOURCE_NORM)
    assert len(facts) == 1
    f = facts[0]
    assert f.fact_key.subject.type == "method"
    assert f.fact_key.subject.name == "OPTIONS"
    assert f.fact_key.aspect == "definition"
    c = f.claims[0]
    assert c.value.type == "text"
    assert c.value.data == "liveMedia 服务端实现接收并处理 OPTIONS 方法"
    assert c.epistemic_type == "descriptive"
    assert c.authority == "source"


def test_source_locator_extracted():
    f = source_norm_to_facts(SOURCE_NORM)[0]
    ev = f.claims[0].evidence[0]
    assert ev.locator == "E:\\科研\\想法idea\\rag-chatafl\\kb\\协议实现源码\\RTSPServer.cpp:354"
    assert ev.document == "file:RTSPServer.cpp"
    assert ev.source_type == "source"


def test_source_definition_strips_location_suffix():
    """「（定义处 ...）」后缀从 value 剥离，只留语义描述。"""
    norm = dict(SOURCE_NORM, content="处理 OPTIONS 方法（定义处 /x/y/RTSPServer.cpp:10）")
    f = source_norm_to_facts(norm)[0]
    assert f.claims[0].value.data == "处理 OPTIONS 方法"


def test_source_empty_content_returns_empty():
    assert source_norm_to_facts(dict(SOURCE_NORM, content="")) == []
    assert source_norm_to_facts(dict(SOURCE_NORM, name="")) == []


def test_all_real_source_norms_pass_fail_closed():
    norms_path = Path("derived") / "spec" / "rtsp" / "norms" / "norms.jsonl"
    norms = [json.loads(l) for l in norms_path.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    src_norms = [n for n in norms if n.get("kb_source_type") == "source"]
    assert len(src_norms) == 10
    registry = load_registry()
    total = 0
    for n in src_norms:
        for f in source_norm_to_facts(n):
            validate_fact(f, registry)
            total += 1
    assert total == 10
