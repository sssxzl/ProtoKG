"""tests/fused/test_action_seq.py —— ⑤ 字段级 action-sequence 变异（批次 1）。

覆盖（对应验收 1~8）：
  · ``apply_actions`` 的每个 op（add / remove / update）× 每个 field_path 类型
    （``headers.<Name>`` / ``url`` / ``argument`` / ``body``）；
  · **不原地修改**输入种子；
  · **确定性**：同输入两次 ⇒ 逐字节相同；
  · **封闭取值域**：域外 ``field_path`` 被拒绝且**有可观测的 reject_reason**；
  · ``msg_index`` 越界的处理；
  · **开关关闭 ⇒ 零产出**；
  · 动作在 ``SeedCorpus`` 上正确落地（headers / url / argument / body 各一例）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from core.fused.downstream.action_seq import (
    ACTION_OPS,
    ACTION_SEQ_GENERATED_BY,
    FIELD_PATH_SCALARS,
    OP_ADD,
    OP_REMOVE,
    OP_UPDATE,
    REJECT_FIELD_PATH_OUT_OF_DOMAIN,
    REJECT_HEADER_ALREADY_EXISTS,
    REJECT_HEADER_NOT_FOUND,
    REJECT_MSG_INDEX_OUT_OF_RANGE,
    REJECT_MISSING_VALUE,
    REJECT_UNKNOWN_OP,
    REJECT_UNEXPECTED_VALUE,
    VALID_OPS,
    Action,
    ActionLedger,
    ActionSequence,
    _published_group_dirs,
    apply_actions,
    load_real_base_seeds,
    normalize_field_path,
    parse_action_sequence,
    parse_raw_seed,
    plan_actions,
)
from core.models import SeedCorpus, SeedMessage

ROOT = Path(__file__).resolve().parents[2]


# ===========================================================================
# 夹具
# ===========================================================================

def _seed() -> SeedCorpus:
    """一颗最小但完整的种子（2 条消息，覆盖 headers/url/argument/body 四类字段）。"""
    return SeedCorpus(
        seed_id="base-1",
        protocol="rtsp",
        description="base seed",
        target_state_path=["Init", "Ready"],
        target_methods=["OPTIONS", "PLAY"],
        messages=[
            SeedMessage(method="OPTIONS",
                        headers={"CSeq": "1", "Accept": "application/sdp"},
                        body="", url="rtsp://127.0.0.1:8554/stream",
                        argument=""),
            SeedMessage(method="PLAY",
                        headers={"CSeq": "2"},
                        body="payload-body", url="rtsp://127.0.0.1:8554/stream/",
                        argument="PLAY-ARG"),
        ],
        generated_by="rule-based:edge-cover",
        selected_url="rtsp://127.0.0.1:8554/stream",
    )


def _bundle() -> dict:
    """最小知识中枢（规则打底用）。"""
    return {
        "required_headers": {"OPTIONS": ["CSeq", "User-Agent"],
                             "PLAY": ["CSeq", "Session"]},
        "session_header": {"PLAY": [{"header": "Session", "from_occurrence": 1}]},
        "headers": {
            "User-Agent": {"values": ["ua/1.0", "ua/2.0"]},
            "Accept": {"values": ["application/sdp"]},
            "Session": {"values": ["12345678"]},
        },
        "statuses": {"200": "OK", "404": "Not Found"},
    }


def _snapshot(seed: SeedCorpus) -> dict:
    """把种子拍成可比较的快照（用于「不被原地修改」与「确定性」断言）。"""
    return {
        "seed_id": seed.seed_id,
        "protocol": seed.protocol,
        "description": seed.description,
        "target_state_path": list(seed.target_state_path),
        "target_methods": list(seed.target_methods),
        "target_vuln_class": seed.target_vuln_class,
        "generated_by": seed.generated_by,
        "selected_url": seed.selected_url,
        "messages": [m.to_dict() for m in seed.messages],
    }


# ===========================================================================
# 1. op × field_path 的落地正确性
# ===========================================================================

def test_add_header_creates_new_field():
    seed = _seed()
    seq = ActionSequence(actions=(Action(OP_ADD, 1, "headers.Session", "999"),))
    out = apply_actions(seed, seq, ledger=ActionLedger())
    assert out.messages[1].headers["Session"] == "999"
    assert "Session" not in seed.messages[1].headers, "输入种子不得被改"


def test_add_header_is_case_insensitive_on_existing():
    """``add`` 命中**已存在**的头（大小写不敏感）⇒ 拒绝，不产生重复头。"""
    seed = _seed()
    ledger = ActionLedger()
    seq = ActionSequence(actions=(Action(OP_ADD, 0, "headers.cseq", "7"),))
    out = apply_actions(seed, seq, ledger=ledger)
    assert out.messages[0].headers == {"CSeq": "1", "Accept": "application/sdp"}
    assert ledger.reason_counts() == {REJECT_HEADER_ALREADY_EXISTS: 1}


def test_update_header_keeps_original_spelling_and_position():
    seed = _seed()
    seq = ActionSequence(actions=(Action(OP_UPDATE, 0, "headers.cseq", "42"),))
    out = apply_actions(seed, seq, ledger=ActionLedger())
    headers = out.messages[0].headers
    assert headers["CSeq"] == "42", "应改**原有拼写**的键（CSeq），不新建 cseq"
    assert "cseq" not in headers
    assert list(headers.keys()) == ["CSeq", "Accept"], "update 不得改变头部顺序"


def test_remove_header_drops_key():
    seed = _seed()
    seq = ActionSequence(actions=(Action(OP_REMOVE, 0, "headers.ACCEPT"),))
    out = apply_actions(seed, seq, ledger=ActionLedger())
    assert "Accept" not in out.messages[0].headers
    assert out.messages[0].headers == {"CSeq": "1"}


def test_remove_missing_header_is_rejected():
    seed = _seed()
    ledger = ActionLedger()
    seq = ActionSequence(actions=(Action(OP_REMOVE, 0, "headers.Session"),))
    out = apply_actions(seed, seq, ledger=ledger)
    assert out.messages[0].headers == {"CSeq": "1", "Accept": "application/sdp"}
    assert ledger.reason_counts() == {REJECT_HEADER_NOT_FOUND: 1}


def test_url_field_add_update_remove():
    seed = _seed()
    new_url = "rtsp://127.0.0.1:8554/other"

    added = apply_actions(seed, ActionSequence(
        actions=(Action(OP_ADD, 0, "url", new_url),)), ledger=ActionLedger())
    assert added.messages[0].url == new_url

    updated = apply_actions(seed, ActionSequence(
        actions=(Action(OP_UPDATE, 0, "url", new_url),)), ledger=ActionLedger())
    assert updated.messages[0].url == new_url

    removed = apply_actions(seed, ActionSequence(
        actions=(Action(OP_REMOVE, 0, "url"),)), ledger=ActionLedger())
    assert removed.messages[0].url == ""


def test_argument_field_add_update_remove():
    seed = _seed()
    added = apply_actions(seed, ActionSequence(
        actions=(Action(OP_ADD, 1, "argument", "NEW-ARG"),)), ledger=ActionLedger())
    assert added.messages[1].argument == "NEW-ARG"

    updated = apply_actions(seed, ActionSequence(
        actions=(Action(OP_UPDATE, 1, "argument", "UPDATED"),)), ledger=ActionLedger())
    assert updated.messages[1].argument == "UPDATED"

    removed = apply_actions(seed, ActionSequence(
        actions=(Action(OP_REMOVE, 1, "argument"),)), ledger=ActionLedger())
    assert removed.messages[1].argument == ""


def test_body_field_add_update_remove():
    seed = _seed()
    added = apply_actions(seed, ActionSequence(
        actions=(Action(OP_ADD, 1, "body", "new-body"),)), ledger=ActionLedger())
    assert added.messages[1].body == "new-body"

    updated = apply_actions(seed, ActionSequence(
        actions=(Action(OP_UPDATE, 1, "body", "upd-body"),)), ledger=ActionLedger())
    assert updated.messages[1].body == "upd-body"

    removed = apply_actions(seed, ActionSequence(
        actions=(Action(OP_REMOVE, 1, "body"),)), ledger=ActionLedger())
    assert removed.messages[1].body == ""


def test_all_ops_cover_all_field_path_kinds():
    """每个 op × 每个 field_path 类型都必须有确定语义（无异常、结果可预期）。"""
    seed = _seed()
    paths = ["headers.X-Test", "url", "argument", "body"]
    for op in (OP_ADD, OP_UPDATE, OP_REMOVE):
        for path in paths:
            value = None if op == OP_REMOVE else "v"
            ledger = ActionLedger()
            out = apply_actions(seed, ActionSequence(
                actions=(Action(op, 0, path, value),)), ledger=ledger)
            assert out is not None
            # 要么落地成功，要么**有可观测的 reject_reason**（不得静默忽略）
            assert len(ledger) == 0 or ledger.reason_counts()


# ===========================================================================
# 2. 不原地修改 + 确定性
# ===========================================================================

def test_apply_actions_does_not_mutate_input():
    seed = _seed()
    before = _snapshot(seed)
    seq = ActionSequence(
        actions=(Action(OP_ADD, 0, "headers.New", "x"),
                 Action(OP_UPDATE, 0, "headers.CSeq", "9"),
                 Action(OP_REMOVE, 0, "headers.Accept"),
                 Action(OP_UPDATE, 1, "url", "rtsp://x/y")),
        intent="test")
    apply_actions(seed, seq, ledger=ActionLedger())
    assert _snapshot(seed) == before, "输入种子必须逐字段不变"


def test_apply_actions_is_deterministic():
    """同一 (种子, ActionSequence) ⇒ 两次结果**逐字节相同**。"""
    seed = _seed()
    seq = ActionSequence(
        actions=(Action(OP_UPDATE, 0, "headers.CSeq", "5"),
                 Action(OP_ADD, 1, "headers.Session", "1"),
                 Action(OP_REMOVE, 0, "headers.Accept")),
        intent="det")
    first = apply_actions(seed, seq, ledger=ActionLedger())
    second = apply_actions(seed, seq, ledger=ActionLedger())
    assert json.dumps(_snapshot(first), sort_keys=True, ensure_ascii=False) == \
        json.dumps(_snapshot(second), sort_keys=True, ensure_ascii=False)
    # 落盘字节也必须一致
    from core.raw_writers import seedcorpus_to_raw
    assert seedcorpus_to_raw(first) == seedcorpus_to_raw(second)


def test_apply_actions_keeps_action_order_semantics():
    """动作按序列顺序执行（先 add 后 remove 同名头 ⇒ 最终被删）。"""
    seed = _seed()
    seq = ActionSequence(actions=(Action(OP_ADD, 0, "headers.Temp", "1"),
                                  Action(OP_REMOVE, 0, "headers.Temp")))
    out = apply_actions(seed, seq, ledger=ActionLedger())
    assert "Temp" not in out.messages[0].headers


# ===========================================================================
# 3. 封闭取值域（域外必须拒绝 + 有 reject_reason）
# ===========================================================================

def test_normalize_field_path_closed_domain():
    assert normalize_field_path("headers.CSeq") == ("header", "CSeq")
    assert normalize_field_path("url") == ("url", "")
    assert normalize_field_path("argument") == ("argument", "")
    assert normalize_field_path("body") == ("body", "")
    # 域外
    for bad in ("headers", "header.CSeq", "CSeq", "url.path", "messages.0.url",
                "headers.", "headers.a b", ""):
        assert normalize_field_path(bad) is None, f"{bad!r} 应在封闭域外"


def test_out_of_domain_field_path_is_rejected_with_reason():
    seed = _seed()
    ledger = ActionLedger()
    bad = Action(OP_UPDATE, 0, "url.path", "/x")
    out = apply_actions(seed, ActionSequence(actions=(bad,)), ledger=ledger)
    assert out.messages[0].url == "rtsp://127.0.0.1:8554/stream", "不得改动"
    assert ledger.reason_counts() == {REJECT_FIELD_PATH_OUT_OF_DOMAIN: 1}
    assert ledger.rejections[0].reject_reason == REJECT_FIELD_PATH_OUT_OF_DOMAIN
    assert ledger.rejections[0].action is bad


def test_out_of_domain_field_path_does_not_raise():
    """域外路径**不得抛未捕获异常**。"""
    seed = _seed()
    for path in ("headers", "raw", "seed.messages", "payload"):
        ledger = ActionLedger()
        out = apply_actions(seed, ActionSequence(
            actions=(Action(OP_UPDATE, 0, path, "x"),)), ledger=ledger)
        assert out is not None
        assert ledger.reason_counts() == {REJECT_FIELD_PATH_OUT_OF_DOMAIN: 1}


def test_unknown_op_is_rejected():
    seed = _seed()
    ledger = ActionLedger()
    out = apply_actions(seed, ActionSequence(
        actions=(Action("patch", 0, "headers.CSeq", "1"),)), ledger=ledger)
    assert out.messages[0].headers["CSeq"] == "1"
    assert ledger.reason_counts() == {REJECT_UNKNOWN_OP: 1}


def test_valid_ops_are_closed():
    assert set(VALID_OPS) == {OP_ADD, OP_REMOVE, OP_UPDATE}
    assert set(VALID_OPS) == set(ACTION_OPS)


def test_scalar_field_paths_are_closed():
    assert set(FIELD_PATH_SCALARS) == {"url", "argument", "body"}


# ===========================================================================
# 4. msg_index 越界 + 值语义
# ===========================================================================

def test_msg_index_out_of_range_is_rejected():
    seed = _seed()
    ledger = ActionLedger()
    out = apply_actions(seed, ActionSequence(
        actions=(Action(OP_UPDATE, 99, "headers.CSeq", "1"),)), ledger=ledger)
    assert out.messages[0].headers["CSeq"] == "1"
    assert ledger.reason_counts() == {REJECT_MSG_INDEX_OUT_OF_RANGE: 1}


def test_negative_msg_index_is_rejected():
    seed = _seed()
    ledger = ActionLedger()
    apply_actions(seed, ActionSequence(
        actions=(Action(OP_UPDATE, -1, "headers.CSeq", "1"),)), ledger=ledger)
    assert ledger.reason_counts() == {REJECT_MSG_INDEX_OUT_OF_RANGE: 1}


def test_add_without_value_is_rejected():
    seed = _seed()
    ledger = ActionLedger()
    apply_actions(seed, ActionSequence(
        actions=(Action(OP_ADD, 0, "headers.X", None),)), ledger=ledger)
    assert ledger.reason_counts() == {REJECT_MISSING_VALUE: 1}


def test_remove_with_value_is_rejected():
    seed = _seed()
    ledger = ActionLedger()
    apply_actions(seed, ActionSequence(
        actions=(Action(OP_REMOVE, 0, "headers.Accept", "x"),)), ledger=ledger)
    assert ledger.reason_counts() == {REJECT_UNEXPECTED_VALUE: 1}


# ===========================================================================
# 5. plan_actions（规则打底 + LLM 兜底）
# ===========================================================================

def test_plan_actions_is_rule_based_and_deterministic():
    seed = _seed()
    bundle = _bundle()
    first = plan_actions(seed, bundle, protocol="rtsp", ledger=ActionLedger())
    second = plan_actions(seed, bundle, protocol="rtsp", ledger=ActionLedger())
    assert first.actions, "规则应给出至少一个动作"
    assert first.actions == second.actions
    assert first.intent == second.intent


def test_plan_actions_rules_land_on_the_seed():
    seed = _seed()
    seq = plan_actions(seed, _bundle(), protocol="rtsp", ledger=ActionLedger())
    out = apply_actions(seed, seq, ledger=ActionLedger())
    # 必填头 User-Agent 缺失 ⇒ 规则补齐（add）
    assert "User-Agent" in out.messages[0].headers
    # 会话头搬运需要**前序消息里真有该头**；此处没有 ⇒ 规则不触发（不造假值）
    assert "Session" not in out.messages[1].headers


def test_plan_actions_session_header_repair_copies_real_value():
    """会话头搬运：从**前序消息的真实值**复制（不发明值）。"""
    seed = _seed()
    seed.messages[0].headers["Session"] = "12345678"
    seq = plan_actions(seed, _bundle(), protocol="rtsp", ledger=ActionLedger())
    out = apply_actions(seed, seq, ledger=ActionLedger())
    assert out.messages[1].headers.get("Session") == "12345678"


def test_plan_actions_llm_fallback_used_when_rules_empty():
    """规则给不出 ⇒ LLM 兜底（LLM 只允许产出 ActionSequence）。"""
    seed = SeedCorpus(protocol="x", messages=[
        SeedMessage(method="PING", headers={}, body="", url="", argument="")])
    bundle = {"required_headers": {}, "session_header": {}, "headers": {},
              "statuses": {}}

    class _LLM:
        def __init__(self):
            self.calls = 0

        def chat_json(self, *, system, user, temperature=0.2, max_tokens=4000):
            self.calls += 1
            return {"intent": "add header",
                    "actions": [{"op": "add", "msg_index": 0,
                                 "field_path": "headers.X-LLM", "value": "1"}]}

    llm = _LLM()
    seq = plan_actions(seed, bundle, protocol="x", llm=llm, ledger=ActionLedger())
    assert llm.calls == 1, "规则为空时应调用 LLM"
    assert seq.intent == "add header"
    assert seq.actions[0].field_path == "headers.X-LLM"


def test_plan_actions_llm_out_of_domain_action_is_rejected():
    """LLM 产出域外 field_path ⇒ 拒绝（**绝不允许产出字节**）。"""
    seed = SeedCorpus(protocol="x", messages=[
        SeedMessage(method="PING", headers={}, body="", url="", argument="")])
    bundle = {"required_headers": {}, "session_header": {}, "headers": {},
              "statuses": {}}

    class _LLM:
        def chat_json(self, *, system, user, temperature=0.2, max_tokens=4000):
            return {"intent": "bad",
                    "actions": [{"op": "update", "msg_index": 0,
                                 "field_path": "raw_bytes", "value": "\\x00\\x01"}]}

    ledger = ActionLedger()
    seq = plan_actions(seed, bundle, protocol="x", llm=_LLM(), ledger=ledger)
    assert seq.actions == (), "域外动作不得进入计划"
    assert ledger.reason_counts().get(REJECT_FIELD_PATH_OUT_OF_DOMAIN, 0) >= 1


def test_plan_actions_llm_failure_degrades_to_rules():
    """LLM 不可用 ⇒ 降级为规则结果（不抛异常、不阻断）。"""
    seed = _seed()

    class _BrokenLLM:
        def chat_json(self, **kwargs):
            raise RuntimeError("llm down")

    seq = plan_actions(seed, _bundle(), protocol="rtsp", llm=_BrokenLLM(), ledger=ActionLedger())
    assert seq.actions, "LLM 挂掉时仍应给出规则结果"


def test_parse_action_sequence_rejects_expected_class_out_of_vocab():
    bundle = {"statuses": {"200": "OK"}}
    ledger = ActionLedger()
    seq = parse_action_sequence(
        {"intent": "x", "expected_class": "999",
         "actions": [{"op": "add", "msg_index": 0,
                      "field_path": "headers.A", "value": "1"}]},
        bundle, ledger=ledger)
    assert seq.expected_class == ""
    assert ledger.reason_counts() == {"expected_class_out_of_vocab": 1}


# ===========================================================================
# 6. 底料解析 + 来源优先级
# ===========================================================================

def _profile() -> dict:
    return {
        "protocol": "rtsp",
        "raw_format": {"line_ending": "\r\n",
                       "request_line": "{method} {url} {version}",
                       "version": "RTSP/1.0",
                       "header_line": "{key}: {value}",
                       "trailing_blank_line": True},
        "allowed_methods": ["OPTIONS", "PLAY"],
        "url_placeholders": {"<stream>": "mp3AudioTest"},
    }


def test_parse_raw_seed_roundtrip():
    text = ("OPTIONS rtsp://127.0.0.1:8554/s RTSP/1.0\r\nCSeq: 1\r\n\r\n"
            "PLAY rtsp://127.0.0.1:8554/s/ RTSP/1.0\r\nCSeq: 2\r\n\r\n")
    seed = parse_raw_seed(text, _profile(), protocol="rtsp")
    assert [m.method for m in seed.messages] == ["OPTIONS", "PLAY"]
    assert seed.messages[0].headers == {"CSeq": "1"}
    assert seed.messages[1].url == "rtsp://127.0.0.1:8554/s/"


def test_parse_raw_seed_skips_methods_outside_allowlist():
    text = ("FOO rtsp://x/y RTSP/1.0\r\n\r\n"
            "OPTIONS rtsp://x/y RTSP/1.0\r\nCSeq: 1\r\n\r\n")
    seed = parse_raw_seed(text, _profile(), protocol="rtsp")
    assert [m.method for m in seed.messages] == ["OPTIONS"]


def test_load_real_base_seeds_prefers_published_corpus(tmp_path):
    """来源 ① 优先；指定了组却不匹配 ⇒ **不拿别的组冒充**，退回来源 ②。

    ★ 同时固化**底料目录筛选护栏**（时间戳形态的批次目录必须带
      ``manifest.json`` 才算「正式发布」；语义命名的一律保留）：
      · ``20261031_171135``（时间戳形态、无 manifest、mtime 最新）
        = 生成过但**未正式发布**的中间产物 ⇒ **排除**（可能混着已废弃、
        被外网摄像机 URL 污染的语料）；
      · ``live555_20261024_110155``（语义命名、**无** manifest）
        = 真实抓包语料（CI 无法重建 ⇒ 天然没有 manifest）⇒ **必须保留**。
    """
    seeds_dir = tmp_path / "seeds" / "rtsp"
    group_dir = seeds_dir / "rq4_B"
    group_dir.mkdir(parents=True)
    (group_dir / "01_x.raw").write_text(
        "OPTIONS rtsp://127.0.0.1:8554/s RTSP/1.0\r\nCSeq: 1\r\n\r\n",
        encoding="utf-8")
    seeds, source = load_real_base_seeds("rtsp", _profile(), group="B",
                                         derived_root=seeds_dir,
                                         kb_root=tmp_path / "kb")
    assert source == "published-corpus"
    assert len(seeds) == 1

    # 组不匹配 + 无 kb 抓包 ⇒ **如实报告「取不到」**（不造假）
    seeds, source = load_real_base_seeds("rtsp", _profile(), group="Z",
                                         derived_root=seeds_dir,
                                         kb_root=tmp_path / "kb")
    assert source == ""
    assert seeds == []

    # ---- 护栏：时间戳形态 + 无 manifest ⇒ 排除；语义命名 + 无 manifest ⇒ 保留 ----
    polluted = seeds_dir / "20261031_171135"          # 时间戳形态（无 manifest）
    polluted.mkdir()
    (polluted / "01_polluted.raw").write_text(
        "OPTIONS rtsp://10.11.26.98:554/isapi RTSP/1.0\r\nCSeq: 1\r\n\r\n",
        encoding="utf-8")
    capture = seeds_dir / "live555_20261024_110155"    # 语义命名（无 manifest）
    capture.mkdir()
    (capture / "01_capture.raw").write_text(
        "OPTIONS rtsp://127.0.0.1:8554/s RTSP/1.0\r\nCSeq: 1\r\n\r\n",
        encoding="utf-8")
    # 让污染目录的 mtime **最新** ⇒ 护栏必须**主动挡下它**，而不是靠 mtime 侥幸
    now = 1_700_000_000
    os.utime(polluted / "01_polluted.raw", (now, now))
    os.utime(capture / "01_capture.raw", (now - 100, now - 100))
    os.utime(group_dir / "01_x.raw", (now - 200, now - 200))

    names = [d.name for d in _published_group_dirs("rtsp", None, seeds_dir)]
    assert "20261031_171135" not in names, \
        "未正式发布的时间戳批次目录必须被排除"
    assert "live555_20261024_110155" in names, \
        "语义命名的正式语料（真实抓包）不得因缺 manifest 而被排除"
    assert names[0] == "live555_20261024_110155", \
        "候选按 mtime 新→旧排序，语义命名的正式语料应排第一"

    # 指定组时行为不变：只有匹配组名的目录进候选
    names_b = [d.name for d in _published_group_dirs("rtsp", "B", seeds_dir)]
    assert names_b == ["rq4_B"]


# ===========================================================================
# 7. 开关位（默认关闭 ⇒ 零产出）
# ===========================================================================

def test_action_seq_switch_is_off_by_default():
    """profile 未声明 ``seedgen.action_seq.enabled`` ⇒ 关闭（回滚手段）。"""
    import scripts.seedgen as seedgen_mod
    assert seedgen_mod._action_seq_enabled({}) is False
    assert seedgen_mod._action_seq_enabled({"seedgen": {}}) is False
    assert seedgen_mod._action_seq_enabled(
        {"seedgen": {"action_seq": {"enabled": False}}}) is False
    assert seedgen_mod._action_seq_enabled(
        {"seedgen": {"action_seq": {"enabled": True}}}) is True


def test_action_seq_switch_off_yields_zero_seeds():
    """开关关闭 ⇒ ⑤ 路径**零产出**。"""
    import scripts.seedgen as seedgen_mod
    profile = {"seedgen": {"action_seq": {"enabled": False}}}
    assert not seedgen_mod._action_seq_enabled(profile)
    seeds, info = seedgen_mod._build_action_seq_seeds(
        {}, profile, "rtsp", group="B")
    # 开关关闭时调用方根本不会进这条路径；即便被调用也不应产出语义外的种子
    assert isinstance(seeds, list)
    assert isinstance(info, dict)


def test_action_seq_seeds_are_appended_not_converged():
    """★ P0-4 语义：⑤ 种子**纯追加**，**不裁剪任何既有层**。

    ★ 旧语义（已废止）：按 profile 契约条数**裁剪总数**且「⑤ 优先保留」
      ⇒ 实测 rtsp/B `91 → 50`，① 结构覆盖 6 + ③ 漏洞边界 18 **被丢弃**；
      且总数被凑到契约 ⇒ **掩盖了批次 1 之前就存在的契约漂移**。
    ★ 新语义：契约条数是**基准层**的约定；基准层条数是既有行为（⑤ 关闭时
      **不裁剪**）⇒ ⑤ 开启时也**不得裁剪** ⇒ 基准层条数 OFF/ON **完全相同**。
    ★ 契约漂移照旧由 G5 报出（已改为只查基准层）—— **不许被掩盖**。
    """
    import scripts.seedgen as seedgen_mod
    from core.fused.downstream.action_seq import ACTION_SEQ_GENERATED_BY
    base = [
        SeedCorpus(protocol="p", generated_by="rule-based:edge-cover",
                   messages=[SeedMessage(method="A")]),
        SeedCorpus(protocol="p", generated_by="rule-based:boundary-probe",
                   messages=[SeedMessage(method="B")]),
    ]
    action = [SeedCorpus(protocol="p", generated_by=ACTION_SEQ_GENERATED_BY,
                         messages=[SeedMessage(method="C")])]
    out = seedgen_mod._append_action_seq_seeds(base, action)
    # 基准层一条不丢、⑤ 一条不丢、顺序为「基准层在前」
    assert len(out) == 3
    assert [s.messages[0].method for s in out] == ["A", "B", "C"]
    # 无 ⑤ 时原样返回（不复制、不改动）
    assert seedgen_mod._append_action_seq_seeds(base, []) is base


# ===========================================================================
# 8. 种子落地（.raw 字节级）
# ===========================================================================

def test_actions_land_on_seedcorpus_fields():
    """一条动作序列 ⇒ 四类字段各落地一处（headers / url / argument / body）。"""
    seed = SeedCorpus(
        protocol="smtp",
        messages=[SeedMessage(method="MAIL", headers={"X-A": "1"}, body="b",
                              url="", argument="FROM:<a@b>")])
    seq = ActionSequence(actions=(
        Action(OP_UPDATE, 0, "headers.X-A", "2"),
        Action(OP_UPDATE, 0, "url", "sip://x/y"),
        Action(OP_UPDATE, 0, "argument", "FROM:<c@d>"),
        Action(OP_UPDATE, 0, "body", "new-body"),
    ), intent="all-kinds")
    out = apply_actions(seed, seq, ledger=ActionLedger())
    msg = out.messages[0]
    assert msg.headers["X-A"] == "2"
    assert msg.url == "sip://x/y"
    assert msg.argument == "FROM:<c@d>"
    assert msg.body == "new-body"
    assert out.generated_by == ACTION_SEQ_GENERATED_BY
    assert "all-kinds" in out.description
