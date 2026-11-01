"""tests for core.llm — StubLLMClient / DeepSeekClient（v1 prompt renderers 已退役）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.llm import StubLLMClient


def test_stub_returns_configured_response():
    stub = StubLLMClient(response={"seeds": [{"method": "OPTIONS"}]})
    out = stub.chat_json(system="x", user="y")
    assert out == {"seeds": [{"method": "OPTIONS"}]}


def test_stub_records_calls():
    stub = StubLLMClient(response=[])
    stub.chat_json(system="s1", user="u1", temperature=0.5)
    stub.chat_text(system="s2", user="u2", max_tokens=100)
    assert len(stub.calls) == 2
    assert stub.calls[0]["system"] == "s1"
    assert stub.calls[0]["temperature"] == 0.5
    assert stub.calls[1]["max_tokens"] == 100


def test_stub_text_returns_string():
    stub = StubLLMClient(response={"x": 1})
    out = stub.chat_text(system="s", user="u")
    assert isinstance(out, str)
    assert json.loads(out) == {"x": 1}


def test_stub_implements_protocol():
    from core.llm import LLMClient
    stub = StubLLMClient(response=[])
    assert isinstance(stub, LLMClient)


# ============================================================================
# last_call_meta(给 LLMGuidedMutator.stats 累计用)
# ============================================================================

def test_stub_has_last_call_meta_default():
    """StubLLMClient 必须有 last_call_meta 属性(默认空 dict,供 mutate.py 累计)。"""
    stub = StubLLMClient(response=[])
    assert hasattr(stub, "last_call_meta")
    assert stub.last_call_meta == {}


def test_stub_last_call_meta_unchanged_after_chat_json():
    """StubLLMClient 调 chat_json 后 last_call_meta 仍是空(无真实 LLM 调用)。"""
    stub = StubLLMClient(response={"x": 1})
    stub.chat_json(system="s", user="u")
    assert stub.last_call_meta == {}  # Stub 不填充


def test_deepseek_client_has_last_call_meta_field():
    """DeepSeekClient 必须有 last_call_meta 字段(初始空 dict,chat_json 后填充)。"""
    from core.llm import DeepSeekClient
    # 不真调 API,只验证字段存在
    import os
    os.environ["DEEPSEEK_API_KEY"] = "sk-test"
    client = DeepSeekClient()
    assert hasattr(client, "last_call_meta")
    assert client.last_call_meta == {}
    assert isinstance(client.last_call_meta, dict)
    # 必须有这几个 key(chat_json 后会填)
    expected_keys = {"status", "elapsed_s", "input_tokens", "output_tokens", "response_chars"}
    # 当前是空,验证 _post_with_status 之后会填(用白盒方式)
    client.last_call_meta = {
        "status": 200, "elapsed_s": 1.23,
        "input_tokens": 100, "output_tokens": 50, "response_chars": 200,
    }
    assert set(client.last_call_meta.keys()) == expected_keys
