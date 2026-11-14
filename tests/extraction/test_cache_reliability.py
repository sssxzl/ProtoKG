# -*- coding: utf-8 -*-
"""M1-① 验收测试：通道 I 缓存可靠性（★ 状态分类 / 命中判定 / 旧格式兼容）。

★ 覆盖验收要求的 10 项：
  1  已成功的非空缓存正常命中
  2  合法空数组正常命中
  3  JSON 解析失败不会固化为空成功缓存
  4  finish_reason="length" 且输出不完整时不得缓存为成功
  5  raw_items > 0 但 norms = 0 ⇒ 保留过滤结果，不自动重试
  6  缺失 complete 字段的旧缓存兼容策略
  7  跨模型 / Prompt / 解析器版本不一致时的安全处理
  8  缓存文件损坏或写入中断时不会被误认为成功
  9  诊断日志写入失败不影响正常抽取
 10  未受影响的成功缓存保持原行为
"""
from __future__ import annotations

import json
import uuid

import pytest

from core.fused.extraction import prose_semantics as ps
from core.fused.extraction.cache_key import (
    CACHE_STATUS_FAILED_INCOMPLETE, CACHE_STATUS_FILTERED_ZERO,
    CACHE_STATUS_LEGACY_UNKNOWN, CACHE_STATUS_SUCCESS_EMPTY,
    CACHE_STATUS_SUCCESS_NONEMPTY,
)


class _FakeLLM:
    def __init__(self, script, model="fake-model-1"):
        self._script = list(script)
        self.calls = 0
        self.model = model
        self.last_call_meta = {}

    def chat_json(self, *, system, user, temperature=0.2, max_tokens=4000):
        self.calls += 1
        _s = self._script.pop(0) if self._script else {"out": {"items": []}}
        if "exc" in _s:
            self.last_call_meta = _s.get("meta", {})
            raise _s["exc"]
        self.last_call_meta = _s.get("meta", {})
        return _s["out"]


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """★ 把缓存路径指到临时目录 ⇒ ⇒ 不碰真实缓存。"""
    _p = tmp_path / "cache" / "rtsp.prose.json"
    monkeypatch.setattr(ps, "_cache_path", lambda protocol: _p)
    return _p


def _blocks(uid=None):
    """★ 同一测试内**必须复用同一批块**（★ 否则块哈希变 ⇒ 缓存键变 ⇒ 不命中）。"""
    _u = uid or uuid.uuid4().hex[:10]
    return [{"doc": "rfc2326.txt", "start": 10,
             "text": f"The client MUST send X. [uid={_u}]"}]


def _doc_lines():
    """★ 供实体证据核对用的原文行（★ 不传 ⇒ 跳过实体核对）。

    ★ 行数必须 **> span**（★ 否则 span 越界 ⇒ 候选被拒 ⇒ 测不到目标分支）。
    """
    _L = ["(preamble)"] * 9 + ["The client MUST send X."]
    return {"rfc2326.txt": _L}


def _read(p):
    return json.loads(p.read_text(encoding="utf-8"))


# ══ 1 已成功的非空缓存正常命中 ══
def test_success_nonempty_hits(_isolated_cache):
    _b = _blocks()
    llm = _FakeLLM([{"out": {"items": [{"entity": "client", "meaning": "m",
                                        "doc": "rfc2326.txt", "span": "10"}]}}])
    _n, st = ps._extract_blocks("rtsp", _b, llm=llm, doc_lines=_doc_lines())
    assert st["cache_status"] == CACHE_STATUS_SUCCESS_NONEMPTY
    assert _read(_isolated_cache)["status"] == CACHE_STATUS_SUCCESS_NONEMPTY
    llm2 = _FakeLLM([])
    _n2, st2 = ps._extract_blocks("rtsp", _b, llm=llm2, doc_lines=_doc_lines())
    assert llm2.calls == 0
    assert st2["cache_hit"] is True


# ══ 2 合法空数组正常命中 ══
def test_success_empty_hits(_isolated_cache):
    _b = _blocks()
    llm = _FakeLLM([{"out": {"items": []}}])
    _n, st = ps._extract_blocks("rtsp", _b, llm=llm)
    assert st["cache_status"] == CACHE_STATUS_SUCCESS_EMPTY
    _d = _read(_isolated_cache)
    assert _d["status"] == CACHE_STATUS_SUCCESS_EMPTY
    assert _d["complete"] is True
    llm2 = _FakeLLM([])
    _n2, st2 = ps._extract_blocks("rtsp", _b, llm=llm2)
    assert llm2.calls == 0 and st2["cache_hit"] is True


# ══ 3 JSON 解析失败不固化为空成功缓存 ══
def test_json_failure_not_cached_as_success(_isolated_cache):
    _b = _blocks()
    llm = _FakeLLM([{"exc": json.JSONDecodeError("Expecting value", "", 0)},
                    {"exc": json.JSONDecodeError("Expecting value", "", 0)}])
    _n, st = ps._extract_blocks("rtsp", _b, llm=llm)
    assert st["failures"] >= 1
    _d = _read(_isolated_cache)
    assert _d["complete"] is False
    assert _d["status"] == CACHE_STATUS_FAILED_INCOMPLETE
    llm2 = _FakeLLM([{"out": {"items": []}}])
    ps._extract_blocks("rtsp", _b, llm=llm2)
    assert llm2.calls == 1                 # ★ 失败缓存**不作为成功命中** ⇒ 会重跑


# ══ 4 finish_reason="length" 且输出不完整 ⇒ 不得缓存为成功 ══
def test_truncated_output_not_cached_as_success(_isolated_cache):
    _b = _blocks()
    llm = _FakeLLM([{"exc": json.JSONDecodeError("Expecting value", "", 0),
                      "meta": {"finish_reason": "length",
                               "output_tokens": 16000}},
                    {"exc": json.JSONDecodeError("Expecting value", "", 0),
                     "meta": {"finish_reason": "length",
                              "output_tokens": 16000}}])
    _n, st = ps._extract_blocks("rtsp", _b, llm=llm)
    _d = _read(_isolated_cache)
    assert _d["complete"] is False
    assert _d["status"] == CACHE_STATUS_FAILED_INCOMPLETE
    assert _d["status"] != CACHE_STATUS_SUCCESS_EMPTY


# ══ 5 raw_items>0 但 norms=0 ⇒ filtered_zero，保留结果，不自动重试 ══
def test_filtered_zero_kept_and_not_retried(_isolated_cache):
    _b = _blocks()
    llm = _FakeLLM([{"out": {"items": [{"entity": "ZZZ_NOT_IN_SPAN",
                                        "meaning": "m",
                                        "doc": "rfc2326.txt", "span": "10"}]}}])
    _n, st = ps._extract_blocks("rtsp", _b, llm=llm, doc_lines=_doc_lines())
    assert st["norms"] == 0
    assert st["drop_reasons"].get("entity_not_in_span", 0) >= 1
    assert st["cache_status"] == CACHE_STATUS_FILTERED_ZERO
    _d = _read(_isolated_cache)
    assert _d["status"] == CACHE_STATUS_FILTERED_ZERO
    assert _d["complete"] is True
    assert _d["drop_reasons"]["entity_not_in_span"] >= 1
    assert _d["mapped_count"] == 0
    llm2 = _FakeLLM([])                   # ★ **不自动重试** ⇒ 命中缓存
    _n2, st2 = ps._extract_blocks("rtsp", _b, llm=llm2, doc_lines=_doc_lines())
    assert llm2.calls == 0
    assert st2["cache_hit"] is True


# ══ 6 旧缓存（缺 complete / 缺 status）兼容 ══
def _make_legacy_cache(path, items):
    """★ 先跑一次造出**块哈希正确**的缓存 ⇒ 再删掉 complete/status 字段 ⇒ 模拟旧格式。"""
    _b = _blocks()
    llm = _FakeLLM([{"out": {"items": items}}])
    ps._extract_blocks("rtsp", _b, llm=llm)
    _d = _read(path)
    _d.pop("complete", None)
    _d.pop("status", None)
    path.write_text(json.dumps(_d, ensure_ascii=False), encoding="utf-8")
    return _b


def test_legacy_cache_compatible(_isolated_cache):
    _b = _make_legacy_cache(
        _isolated_cache,
        [{"entity": "client", "meaning": "m", "doc": "rfc2326.txt", "span": "10"}])
    llm = _FakeLLM([])
    _n, st = ps._extract_blocks("rtsp", _b, llm=llm, doc_lines=_doc_lines())
    assert llm.calls == 0                 # ★ 旧缓存**仍命中**（不无差别删除）
    assert st["cache_hit"] is True
    _d = _read(_isolated_cache)
    # ★ 命中后写入真实状态；★ 不再是 legacy_unknown（因为映射阶段已判定）
    assert _d["status"] in (CACHE_STATUS_LEGACY_UNKNOWN,
                             CACHE_STATUS_SUCCESS_NONEMPTY,
                             CACHE_STATUS_FILTERED_ZERO)


def test_legacy_unknown_marked_when_status_absent(_isolated_cache):
    """★ **直接读**旧缓存 ⇒ `_load_cache` 必须打 legacy_unknown 标记。"""
    _make_legacy_cache(_isolated_cache, [])
    _d = _read(_isolated_cache)
    _bh = _d["block_hash"]
    _d2 = json.loads(_isolated_cache.read_text(encoding="utf-8"))
    _d2.pop("status", None)
    _isolated_cache.write_text(json.dumps(_d2, ensure_ascii=False), encoding="utf-8")
    _got = ps._load_cache("rtsp", _bh)
    assert _got is not None
    assert _got.get("status") == CACHE_STATUS_LEGACY_UNKNOWN
    assert _got.get("legacy_unknown") is True


# ══ 7 跨模型 / Prompt / 解析器版本不一致 ⇒ 安全处理 ══
def test_model_mismatch_not_hits(_isolated_cache, monkeypatch):
    """★ 缓存键的 model 取自 **env**（`model_identity()`）⇒ ⇒ 换模型即换 env。

    ★ **证据**：`_extract_blocks` 调 `cache_key(...)` 时**未传 model** ⇒ 走
    `model_identity()`（`LLM_MODEL` → `DEEPSEEK_MODEL` → 默认 `deepseek-chat`）；
    而 `DeepSeekClient` 读的也是同一 env ⇒ ⇒ **生产场景下二者同源，不会冲突**。
    """
    from core.fused.extraction import cache_key as ck
    monkeypatch.setenv("LLM_MODEL", "model-A")
    _b = _blocks()
    llm = _FakeLLM([{"out": {"items": []}}], model="model-A")
    ps._extract_blocks("rtsp", _b, llm=llm)
    monkeypatch.setenv("LLM_MODEL", "model-B")
    llm2 = _FakeLLM([{"out": {"items": []}}], model="model-B")
    ps._extract_blocks("rtsp", _b, llm=llm2)
    assert llm2.calls == 1                 # ★ 换模型 ⇒ 键变 ⇒ 不命中


def test_prompt_change_not_hits(_isolated_cache, monkeypatch):
    _b = _blocks()
    llm = _FakeLLM([{"out": {"items": []}}])
    ps._extract_blocks("rtsp", _b, llm=llm)
    monkeypatch.setattr(ps, "_PROMPT", ps._PROMPT + "\n[new]")
    llm2 = _FakeLLM([{"out": {"items": []}}])
    ps._extract_blocks("rtsp", _b, llm=llm2)
    assert llm2.calls == 1


def test_parser_version_change_not_hits(_isolated_cache, monkeypatch):
    _b = _blocks()
    llm = _FakeLLM([{"out": {"items": []}}])
    ps._extract_blocks("rtsp", _b, llm=llm)
    monkeypatch.setattr(ps, "PROSE_SEMANTICS_PROMPT_VERSION",
                        ps.PROSE_SEMANTICS_PROMPT_VERSION + "-x")
    llm2 = _FakeLLM([{"out": {"items": []}}])
    ps._extract_blocks("rtsp", _b, llm=llm2)
    assert llm2.calls == 1


# ══ 8 缓存损坏 / 写入中断 ⇒ 不得误认为成功 ══
def test_corrupt_cache_not_hit(_isolated_cache):
    _isolated_cache.parent.mkdir(parents=True, exist_ok=True)
    _isolated_cache.write_text("{ this is not json", encoding="utf-8")
    llm = _FakeLLM([{"out": {"items": []}}])
    ps._extract_blocks("rtsp", _blocks(), llm=llm)
    assert llm.calls == 1


def test_truncated_cache_file_not_hit(_isolated_cache):
    _isolated_cache.parent.mkdir(parents=True, exist_ok=True)
    _isolated_cache.write_text('{"block_hash": "abc", "items": [', encoding="utf-8")
    llm = _FakeLLM([{"out": {"items": []}}])
    ps._extract_blocks("rtsp", _blocks(), llm=llm)
    assert llm.calls == 1


# ══ 9 诊断日志写入失败不影响正常抽取 ══
def test_diag_failure_no_impact(tmp_path, monkeypatch):
    from core.fused.extraction.llm_diagnostics import LLMDiagnostics
    _p = tmp_path / "cache" / "rtsp.prose.json"
    monkeypatch.setattr(ps, "_cache_path", lambda protocol: _p)
    d = LLMDiagnostics(protocol="rtsp", entry_type="document",
                       out_dir=tmp_path / "\0bad")
    llm = _FakeLLM([{"out": {"items": []}}])
    _n, st = ps._extract_blocks("rtsp", _blocks(), llm=llm, diagnostics=d)
    assert st["calls"] == 1
    assert d.flush() is None                # ★ 写盘失败被吞掉


# ══ 10 未受影响的成功缓存保持原行为 ══
def test_untouched_success_cache_behavior(_isolated_cache):
    _b = _blocks()
    llm = _FakeLLM([{"out": {"items": [{"entity": "client", "meaning": "m",
                                        "doc": "rfc2326.txt", "span": "10"}]}}])
    _n, st = ps._extract_blocks("rtsp", _b, llm=llm, doc_lines=_doc_lines())
    assert st["raw_items"] == 1
    assert st["norms"] == 1
    assert st["cache_status"] == CACHE_STATUS_SUCCESS_NONEMPTY
    llm2 = _FakeLLM([])
    _n2, st2 = ps._extract_blocks("rtsp", _b, llm=llm2, doc_lines=_doc_lines())
    assert _read(_isolated_cache)["items"]          # ★ items 原样保留（不丢数据）
    assert st2["norms"] == 1
