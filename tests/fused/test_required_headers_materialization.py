# -*- coding: utf-8 -*-
"""tests/fused/test_required_headers_materialization.py —— 批次 1.6 **步 4**。

★ 覆盖六条：
  ① 物化产生正确的事实（条数 / 方法 / 头名 / authority=profile）；
  ② ★ bundle 的 ``required_headers`` 与 profile.json 的**等价**（判据①）；
  ③ **兼容期回退**：中枢没物化时仍从 profile.json 取（不破链）；
  ④ ★ 物化事实**不污染** ``methods`` 桶（否则 prompt 变 ⇒ 种子漂移）；
  ⑤ ``available_sources`` 含 ``profile`` 且 **origin 单独标注**（判据②）；
  ⑥ ★ 中枢已物化时，组装端**不再直读** profile.json 的这份知识。
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

build_hub = importlib.import_module("scripts.build_hub")
paths_mod = importlib.import_module("core.paths")
rag_seedgen = importlib.import_module("core.fused.downstream.rag_seedgen")
assemble_bundle = rag_seedgen.assemble_bundle

PROTOCOL = "rtsp"


@pytest.fixture()
def profile_dir(tmp_path, monkeypatch):
    """把 profile.json 复制到 tmp_path 并让 paths 指向它。"""
    src = paths_mod.target_profile(PROTOCOL)
    data = json.loads(src.read_text(encoding="utf-8"))
    prof = tmp_path / "profile.json"
    prof.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    monkeypatch.setattr(paths_mod, "target_profile", lambda p: prof)
    return prof


@pytest.fixture()
def hub(tmp_path, monkeypatch):
    root = tmp_path / "per_source" / PROTOCOL
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths_mod, "per_source_root",
                        lambda p: tmp_path / "per_source" / p.lower())
    monkeypatch.setattr(paths_mod, "hub_root",
                        lambda *a: tmp_path / "per_source" / PROTOCOL)
    return root


def _rh_view(method: str, headers: list[str]) -> dict:
    return {
        "fact_key": {
            "protocol": PROTOCOL, "version": "1.0",
            "subject": {"type": "method", "name": method,
                        "qualifiers": {}, "path": []},
            "aspect": "required_headers",
            "condition": {"type": "always"},
        },
        "resolution": None,
        "all_claims": [{
            "claim_id": f"c2_rh_{method}", "fact_id": f"f2_rh_{method}",
            "value": {"type": "struct", "data": {"headers": headers}},
            "epistemic_type": "normative", "authority": "profile",
            "scope": None,
            "evidence_summary": [f"profile:{method}.required_headers"],
            "confidence": None,
        }],
    }


# ===========================================================================
# ① 物化产生正确的事实
# ===========================================================================

def test_materialize_writes_required_headers_facts(hub, profile_dir):
    """★ 物化：每个方法一条事实，authority=profile。"""
    n = build_hub._materialize_required_headers(PROTOCOL)
    assert n == 9, f"应物化 9 条（rtsp 9 个方法，2026-11-07 补了 RECORD），实际 {n}"

    dest = paths_mod.per_source_facts_dir(PROTOCOL, "profile") / "profile.jsonl"
    views = [json.loads(ln) for ln in dest.read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    rh = [v for v in views
          if v["fact_key"]["aspect"] == "required_headers"]
    assert len(rh) == 9   # ★ 2026-11-07：8 → 9（补了 RECORD）
    got = {v["fact_key"]["subject"]["name"]:
           v["all_claims"][0]["value"]["data"]["headers"] for v in rh}
    prof = json.loads(profile_dir.read_text(encoding="utf-8"))
    expected = prof["seedgen"]["required_headers"]
    assert got == {k: list(v) for k, v in expected.items()}
    # ★ authority 标 profile（与「本次抽取的源」分得开）
    assert all(v["all_claims"][0]["authority"] == "profile" for v in rh)


# ===========================================================================
# ② 从 facts 取的 required_headers 与 profile.json 等价
# ===========================================================================

def test_bundle_required_headers_from_facts_equals_profile(hub, profile_dir):
    """★ 判据①：facts 提供的 required_headers 与 profile.json **等价**。"""
    prof = json.loads(profile_dir.read_text(encoding="utf-8"))
    expected = {k: sorted(set(v))
                for k, v in prof["seedgen"]["required_headers"].items()}
    views = [_rh_view(m, list(h))
             for m, h in prof["seedgen"]["required_headers"].items()]
    b = assemble_bundle(views, PROTOCOL)
    assert b["required_headers"] == expected


def test_bundle_required_headers_from_facts_plus_relation_to_other(hub,
                                                                    profile_dir):
    """★ facts 的必填头与 ``relation_to_other`` 的追加**合并**。"""
    views = [_rh_view("SETUP", ["CSeq", "Transport"])]
    extra = {
        "fact_key": {
            "protocol": PROTOCOL, "version": "1.0",
            "subject": {"type": "method", "name": "SETUP",
                        "qualifiers": {}, "path": []},
            "aspect": "relation_to_other",
            "condition": {"type": "always"},
        },
        "resolution": None,
        "all_claims": [{
            "claim_id": "c9", "fact_id": "f9",
            "value": {"type": "struct", "data": {"target": {"name": "X-Extra"}}},
            "epistemic_type": "normative", "authority": "rfc",
            "scope": None, "evidence_summary": ["rfc:SETUP"],
            "confidence": None,
        }],
    }
    b = assemble_bundle(views + [extra], PROTOCOL)
    assert b["required_headers"]["SETUP"] == ["CSeq", "Transport", "X-Extra"]


def test_compat_fallback_merges_not_overwrites(hub, profile_dir):
    """★ 兼容期回退**必须合并**：facts 的 ``relation_to_other`` 追加不能被抹掉。

    ★ 回归：步 4 初版把「profile 基线」直接**覆盖** required_headers
      ⇒ ``relation_to_other`` 追加的头名被抹掉 ⇒ 与步 4 之前不等价。
    """
    extra = {
        "fact_key": {
            "protocol": PROTOCOL, "version": "1.0",
            "subject": {"type": "method", "name": "SETUP",
                        "qualifiers": {}, "path": []},
            "aspect": "relation_to_other",
            "condition": {"type": "always"},
        },
        "resolution": None,
        "all_claims": [{
            "claim_id": "c9", "fact_id": "f9",
            "value": {"type": "struct", "data": {"target": {"name": "X-Extra"}}},
            "epistemic_type": "normative", "authority": "rfc",
            "scope": None, "evidence_summary": ["rfc:SETUP"],
            "confidence": None,
        }],
    }
    b = assemble_bundle([extra], PROTOCOL)   # ★ 没有 required_headers 事实 ⇒ 回退
    prof = json.loads(profile_dir.read_text(encoding="utf-8"))
    base = sorted(set(prof["seedgen"]["required_headers"]["SETUP"]))
    assert b["required_headers"]["SETUP"] == sorted(set(base + ["X-Extra"]))


# ===========================================================================
# ③ 兼容期回退
# ===========================================================================

def test_bundle_falls_back_to_profile_when_not_materialized(hub, profile_dir):
    """★ 中枢没物化 ⇒ 回退读 profile.json（兼容期不破链）。"""
    prof = json.loads(profile_dir.read_text(encoding="utf-8"))
    expected = {k: sorted(set(v))
                for k, v in prof["seedgen"]["required_headers"].items()}
    b = assemble_bundle([], PROTOCOL)
    assert b["required_headers"] == expected


# ===========================================================================
# ④ 物化事实不污染 methods 桶
# ===========================================================================

def test_required_headers_facts_do_not_pollute_methods(hub, profile_dir):
    """★ 物化事实**不新增** methods 条目（否则 prompt 变 ⇒ 种子漂移）。"""
    prof = json.loads(profile_dir.read_text(encoding="utf-8"))
    base = assemble_bundle([], PROTOCOL)
    views = [_rh_view(m, list(h))
             for m, h in prof["seedgen"]["required_headers"].items()]
    b = assemble_bundle(views, PROTOCOL)
    assert set(b["methods"].keys()) == set(base["methods"].keys())


# ===========================================================================
# ⑤ available_sources + origin 分列
# ===========================================================================

def test_available_sources_and_origin_marking(hub, profile_dir):
    """★ 判据②：`available_sources` 含 profile；origin **单独标注**。"""
    prof = json.loads(profile_dir.read_text(encoding="utf-8"))
    views = [_rh_view(m, list(h))
             for m, h in prof["seedgen"]["required_headers"].items()]
    b = assemble_bundle(views, PROTOCOL)
    assert "profile" in b["available_sources"]
    origin = b["bucket_origin"]["required_headers"]
    assert origin["facts"] is True, "物化后应标 facts 来源"
    assert origin["profile"] is False, "物化后不应再标 profile 兜底"


# ===========================================================================
# ⑥ 组装端不再直读 profile.json 的这份知识
# ===========================================================================

def test_bundle_works_without_profile_json_when_materialized(hub, profile_dir,
                                                             monkeypatch):
    """★ 中枢已物化 ⇒ **删掉 profile.json 也能**给出正确的必填头。

    ⇒ 证明组装端**不再直读** profile.json 的这份知识（读的是中枢里的事实）。
    """
    prof = json.loads(profile_dir.read_text(encoding="utf-8"))
    views = [_rh_view(m, list(h))
             for m, h in prof["seedgen"]["required_headers"].items()]
    expected = {k: sorted(set(v))
                for k, v in prof["seedgen"]["required_headers"].items()}
    # ★ 让 profile.json 读不到
    monkeypatch.setattr(paths_mod, "target_profile",
                        lambda p: Path("/nonexistent/profile.json"))
    b = assemble_bundle(views, PROTOCOL)
    assert b["required_headers"] == expected
