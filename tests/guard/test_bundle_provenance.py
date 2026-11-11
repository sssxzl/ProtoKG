# -*- coding: utf-8 -*-
"""tests/test_bundle_provenance.py —— 批次 1.6 **步 3**（溯源保留）。

★ 覆盖五条：
  ① 桶映射表 ``_BUCKET_BY_KIND`` **逐组合验证**（每个 ``(类型, aspect)``
     单独组装 ⇒ 落在且**只**落在指定桶）⇒ 映射表错了测试就红；
  ② ``by_source`` 的计数与事实数一致（桶级统计准确）；
  ③ ``fact_index`` + ``bucket_fact_ids`` ⇒ 桶里每条都能**回指到源**；
  ④ ``bucket_origin`` 把「facts 派生」与「profile 兜底」**分列**；
  ⑤ ★ **只加顶层新键 ⇒ 既有桶结构逐字节不变 ⇒ prompt 渲染不变**
     ⇒ 种子产物逐字节不变（旧消费者零影响）。
"""
from __future__ import annotations

import importlib
import json

rag_seedgen = importlib.import_module("core.fused.downstream.rag_seedgen")
assemble_bundle = rag_seedgen.assemble_bundle
render_seed_prompt = rag_seedgen.render_seed_prompt

PROTOCOL = "rtsp"

#: 步 3 新增的顶层键（**只加不改** ⇒ 其它键必须逐字节不变）
NEW_KEYS = ("by_source", "bucket_fact_ids", "fact_index", "bucket_origin")

#: 覆盖代码里所有会进桶的 ``(subject_type, aspect)`` 组合
ALL_KINDS = (
    ("method", "state_changing"), ("method", "definition"),
    ("method", "existence"), ("method", "relation_to_other"),
    ("method", "security_property"), ("method", "precondition"),
    ("method", "session_header"), ("method", "url_template"),
    ("method", "legal_boundary"), ("method", "vuln_pattern"),
    ("header", "syntax"), ("header", "definition"),
    ("header", "value_enum_spec"),
    ("header", "security_property"), ("header", "legal_boundary"),
    ("header", "response_expectation"), ("header", "vuln_pattern"),
    ("relation", "target_state"), ("relation", "method_sequence"),
    ("relation", "message_instance"),
    ("status", "definition"),
    ("protocol", "value_enum_spec"), ("actor", "value_enum_spec"),
)

#: ★ 已知**不进任何桶**的组合（既有行为，本步不改，只如实记录）。
#:   ★ 2026-11-11：`occurrence`（实测频次）已整体删除 ⇒ 此表清空
#:   ⇒ 真实骨架里实测 13 条这样的事实被丢弃。
#: ★ 2026-11-11：`occurrence`（实测频次）已删除 ⇒ 无「有意不映射」的组合
NO_BUCKET_KINDS = ()


#: ★ 测试用的方法名：必须在 rtsp 的 ``allowed_methods`` 里（否则会被白名单过滤），
#:   且**不在** profile 的 ``state_changing`` 集里（否则事实与兜底同值 ⇒ 桶不变，
#:   测不出「这条事实进了哪个桶」）。
METHOD_NAME = "OPTIONS"


def _canon(obj) -> str:
    """稳定序列化（tuple key → 字符串 key；dict 排序）⇒ 可比较。"""
    if isinstance(obj, dict):
        return "{" + ",".join(
            f"{json.dumps(('|'.join(map(str, k)) if isinstance(k, tuple) else str(k)))}"
            f":{_canon(v)}"
            for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))
        ) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_canon(v) for v in obj) + "]"
    if isinstance(obj, set):
        return "{" + ",".join(sorted(_canon(v) for v in obj)) + "}"
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


def _view(stype: str, aspect: str, authority: str = "rfc",
          name: str = METHOD_NAME, fid: str = "f1", claim_id: str = "c1") -> dict:
    """按 ``(subject_type, aspect)`` 构造一条**能真正进桶**的事实。

    ★ 关键：每个 aspect 的 ``value`` 形状与 ``subject.qualifiers`` 必须与
      ``assemble_bundle`` 的读取方式一致 ⇒ 否则该事实会被「读不出值」而
      静默不落桶（测不出归属）。
    """
    subject = {"type": stype, "name": name, "qualifiers": {}, "path": []}
    value: object = True
    if aspect == "value_enum_spec":
        value = ["v1"]
    elif aspect == "relation_to_other":
        # ★ 用一个 profile 里**没有**的头名 ⇒ 桶内容必然变化（否则被去重吸收）
        value = {"target": {"name": "X-Custom-Header"}}
    elif aspect == "precondition":
        value = {"prerequisite": "OPTIONS"}
    elif aspect == "session_header":
        value = {"header": "Session", "from_occurrence": 1}
    elif aspect == "url_template":
        value = "rtsp://127.0.0.1/{stream}"
    elif aspect in ("legal_boundary", "vuln_pattern", "response_expectation",
                    "security_property"):
        value = {"dim": "x"}
    elif aspect == "message_instance":
        value = {"fields": [{"name": "CSeq", "value": "1"}]}
        subject["qualifiers"] = {
            "source": {"type": "state", "name": "Init",
                       "qualifiers": {}, "path": []},
            "target": {"type": "state", "name": "Ready",
                       "qualifiers": {}, "path": []},
            "method": {"type": "method", "name": "SETUP",
                       "qualifiers": {}, "path": []},
        }
    elif aspect == "target_state":
        subject["qualifiers"] = {
            "source": {"type": "state", "name": "Init",
                       "qualifiers": {}, "path": []},
            "target": {"type": "state", "name": "Ready",
                       "qualifiers": {}, "path": []},
            "method": {"type": "method", "name": "SETUP",
                       "qualifiers": {}, "path": []},
        }
    elif aspect == "method_sequence":
        subject["qualifiers"] = {
            "source": {"type": "method", "name": "OPTIONS",
                       "qualifiers": {}, "path": []},
            "target": {"type": "method", "name": "DESCRIBE",
                       "qualifiers": {}, "path": []},
            "method": {"type": "method", "name": "*",
                       "qualifiers": {}, "path": []},
        }
    return {
        "fact_key": {
            "protocol": PROTOCOL, "version": "1.0",
            "subject": subject,
            "aspect": aspect, "condition": {"type": "always"},
        },
        "resolution": None,
        "all_claims": [{
            "claim_id": claim_id, "fact_id": fid,
            "value": {"type": "struct", "data": value},
            "epistemic_type": "normative", "authority": authority,
            "scope": None, "evidence_summary": [f"{authority}:{name}"],
            "confidence": None,
        }],
    }


# ===========================================================================
# ① 桶映射表逐组合验证
# ===========================================================================

def test_bucket_by_kind_mapping_covers_all_kinds():
    """★ 映射表覆盖所有可能进桶的组合（漏了 ⇒ 测试红）。"""
    mapping = rag_seedgen._BUCKET_BY_KIND
    for kind in ALL_KINDS:
        assert kind in mapping, f"映射表漏了组合 {kind}"
    # ★ 不落桶的组合**不得**出现在映射表里
    for kind in NO_BUCKET_KINDS:
        assert kind not in mapping, f"{kind} 不进任何桶，不该出现在映射表"


def test_known_no_bucket_kinds_indeed_enter_no_bucket():
    """★ 已知不落桶的组合（如实记录既有行为）。"""
    bucket_names = {
        "methods", "headers", "required_headers", "transitions",
        "method_sequences", "security", "statuses", "protocol", "actors",
        "precondition", "session_header", "url_template", "legal_boundary",
        "response_expectation", "vuln_pattern", "message_instances",
    }
    base = assemble_bundle([], PROTOCOL)
    for stype, aspect in NO_BUCKET_KINDS:
        b = assemble_bundle([_view(stype, aspect)], PROTOCOL)
        changed = {k for k in bucket_names if _canon(b.get(k)) != _canon(base.get(k))}
        assert not changed, f"({stype},{aspect}) 实际改变了桶 {sorted(changed)}"


def test_each_kind_lands_only_in_its_bucket():
    """★ 每个组合单独组装 ⇒ **只**改变映射表指定的那个桶。

    ★ 判据用「**与空事实基线对比**」而不是「桶是否非空」———
      因为 profile.json 兜底会让 ``precondition`` / ``required_headers`` /
      ``session_header`` / ``url_template`` **恒非空**（与事实无关）。
    """
    mapping = rag_seedgen._BUCKET_BY_KIND
    bucket_names = {
        "methods", "headers", "required_headers", "transitions",
        "method_sequences", "security", "statuses", "protocol", "actors",
        "precondition", "session_header", "url_template", "legal_boundary",
        "response_expectation", "vuln_pattern", "message_instances",
    }
    base = assemble_bundle([], PROTOCOL)
    for stype, aspect in ALL_KINDS:
        target = mapping[(stype, aspect)]
        b = assemble_bundle([_view(stype, aspect)], PROTOCOL)
        changed = {k for k in bucket_names
                   if _canon(b.get(k)) != _canon(base.get(k))}
        assert target in changed, (
            f"({stype},{aspect}) 应改变 `{target}`，实际改变 {sorted(changed)}")
        # ★ 允许的额外变化只有 `methods`：`assemble_bundle` 对 method 主体先做
        #   `methods.setdefault(name, {})` ⇒ 即使该 aspect 不进 methods 桶，
        #   也会给 methods **新增一个空条目**（既有行为，非本步引入）。
        assert changed - {target} <= {"methods"}, (
            f"({stype},{aspect}) 落到了不该落的桶 {sorted(changed - {target})}")


# ===========================================================================
# ② 桶级统计准确
# ===========================================================================

def test_by_source_counts_match_facts():
    """★ `by_source` 的计数 = 各源贡献的事实条数。"""
    views = [
        _view("method", "definition", authority="rfc", name="A",
              fid="f1", claim_id="c1"),
        _view("method", "definition", authority="rfc", name="B",
              fid="f2", claim_id="c2"),
        _view("method", "definition", authority="vuln", name="C",
              fid="f3", claim_id="c3"),
    ]
    b = assemble_bundle(views, PROTOCOL)
    assert b["by_source"]["methods"] == {"rfc": 2, "vuln": 1}


# ===========================================================================
# ③ 条目级回指
# ===========================================================================

def test_bucket_entries_trace_back_to_source():
    """★ 桶 → fact_id → fact_index → authority（双向可追）。"""
    views = [
        _view("method", "definition", authority="rfc", name="A",
              fid="f1", claim_id="c1"),
        _view("header", "syntax", authority="traffic", name="CSeq",
              fid="f2", claim_id="c2"),
    ]
    b = assemble_bundle(views, PROTOCOL)
    assert b["bucket_fact_ids"]["methods"] == ["f1"]
    assert b["bucket_fact_ids"]["headers"] == ["f2"]
    assert b["fact_index"]["f1"]["authority"] == "rfc"
    assert b["fact_index"]["f1"]["bucket"] == "methods"
    assert b["fact_index"]["f2"]["authority"] == "traffic"
    # ★ 桶里每条都能回指
    for bucket, ids in b["bucket_fact_ids"].items():
        for fid in ids:
            assert fid in b["fact_index"], f"{bucket} 里的 {fid} 无法回指"


# ===========================================================================
# ④ facts 派生 vs profile 兜底分列
# ===========================================================================

def test_bucket_origin_separates_facts_and_profile():
    """★ 「facts 派生」与「profile 兜底」**分列**（不混说）。"""
    b = assemble_bundle([_view("method", "definition")], PROTOCOL)
    origin = b["bucket_origin"]
    assert origin["methods"]["facts"] is True
    # profile.json 声明了 rtsp 的必填头 ⇒ required_headers 标 profile=True
    assert origin["required_headers"]["profile"] is True
    assert origin["required_headers"]["facts"] is False


# ===========================================================================
# ⑤ 只加顶层新键 ⇒ 旧字段与 prompt 不变
# ===========================================================================

def test_new_keys_do_not_change_existing_fields_or_prompt():
    """★ **只加顶层新键** ⇒ 既有键的值与 prompt 渲染**逐字节不变**。"""
    views = [
        _view("method", "definition", name="SETUP", fid="f1", claim_id="c1"),
        _view("header", "syntax", name="CSeq",
              fid="f2", claim_id="c2"),
    ]
    b = assemble_bundle(views, PROTOCOL)
    stripped = {k: v for k, v in b.items() if k not in NEW_KEYS}

    # ① 新键存在
    for k in NEW_KEYS:
        assert k in b, f"新键 {k} 缺失"

    # ② prompt 渲染逐字节一致（⇒ 种子产物不变）
    p_full = render_seed_prompt(b, protocol=PROTOCOL)
    p_stripped = render_seed_prompt(stripped, protocol=PROTOCOL)
    assert p_full == p_stripped, "新键影响了 prompt ⇒ 种子会漂移"

    # ③ 既有键**不含**新键（不被就地塞进既有桶）
    for k, v in stripped.items():
        if isinstance(v, dict):
            for sub in v.values():
                if isinstance(sub, dict):
                    assert not (set(sub) & set(NEW_KEYS)), \
                        f"新键被塞进了既有桶 `{k}`"


def test_new_keys_are_serializable():
    """★ 新键可 JSON 序列化（bundle 会被落盘/传输）。"""
    b = assemble_bundle([_view("method", "definition")], PROTOCOL)
    text = json.dumps(b, ensure_ascii=False, default=str)
    assert '"by_source"' in text
    assert '"fact_index"' in text
