"""tests/test_rag_seedgen.py —— 知识中枢 → RAG → LLM → 种子（第一步全量分桶）。"""
from __future__ import annotations

from core.fused.downstream.rag_seedgen import (
    load_fact_views, assemble_bundle, render_seed_prompt,
    generate_seeds, validate_seed, parse_seed_response,
    load_source_manifest,
)
from core.llm import StubLLMClient
from core.models import SeedCorpus, SeedMessage


# ===========================================================================
# 分桶
# ===========================================================================

def _hub_source_set(protocol: str = "rtsp") -> list[str]:
    """中枢本次参与的源集合（``sources.json`` = 唯一权威）。

    ★ 批次 2.5（F6）：``profile.allowed_methods``（**源码侧**人工白名单）改为
      **按 source_set 决定**是否启用 ⇒ 白名单的适用性随源集合而变。
    """
    doc = load_source_manifest(protocol) or {}
    return [str(s).strip().lower() for s in (doc.get("source_set") or [])]


def test_load_fact_views_has_all_five_sources():
    views = load_fact_views()
    # 总数随 KB 更新而变化（五源 + 会话语义/边界回写），不做硬编码，只断言非空 + 多源
    assert len(views) > 0
    authorities = {v["all_claims"][0]["authority"] for v in views if v.get("all_claims")}
    # 至少含 source/expert_note/vuln/traffic 四源（rfc 依赖 norms.jsonl，可能为 0）
    assert {"source", "expert_note", "vuln", "traffic"} <= authorities


def test_assemble_methods():
    """方法桶：**按 source_set 分流**。

    ★ 批次 2.5（F6）：``profile.allowed_methods`` 是**源码侧**白名单 ⇒ **按 source_set
      决定**是否启用（判据同 ``scripts/seedgen.py``）：
        · ``source`` ∈ source_set ⇒ 启用 ⇒ RFC 抽到的非实现方法（ANNOUNCE/REDIRECT）被裁掉
        · ``source`` ∉ source_set ⇒ **不启用** ⇒ 保留 RFC 抽到的**真实**方法
    ★ 批次 2.5（F3）：``state_changing`` **不再直读 profile**（那里只列
      SETUP/PLAY/PAUSE/TEARDOWN），改为**从 facts 的 target_state 推导**
      ⇒ 凡是出现在**具体状态转移**里的方法都判为改状态（OPTIONS 亦然）。
    """
    src_set = _hub_source_set()
    apply_allowed = (not src_set) or ("source" in src_set)
    b = assemble_bundle(load_fact_views(), source_set=src_set or None,
                        apply_allowed_methods=apply_allowed)
    methods = b["methods"]
    assert len(methods) >= 8
    assert "SETUP" in methods and "PLAY" in methods and "TEARDOWN" in methods
    assert methods["SETUP"].get("state_changing") is True
    # ★ F3：state_changing 从 facts 的 target_state 推导（不再直读 profile 的固定列表）
    #   ⇒ 判据 = 「该方法出现在**具体状态转移**里」；OPTIONS 亦出现在协议骨架的
    #   Idle→OPTIONS→Idle 等转移中 ⇒ 判为 True（旧口径下 profile 只列
    #   SETUP/PLAY/PAUSE/TEARDOWN，故 OPTIONS 曾判 False）。
    trans_methods = {t[1] for rows in b["transitions_by_source"].values() for t in rows}
    for name, info in methods.items():
        assert bool(info.get("state_changing")) is (name in trans_methods), \
            f"{name} 的 state_changing 应与「出现在具体状态转移里」一致"
    # ★ F6：白名单按 source_set 决定是否启用 ⇒ 不启用时保留 RFC 抽到的真实方法
    if not apply_allowed:
        assert {"ANNOUNCE", "RECORD", "REDIRECT"} <= set(methods), \
            "source ∉ source_set ⇒ 不应裁掉 RFC 抽到的真实方法"


def test_assemble_transitions_keep_method():
    """transition 必须保留 method（刚修复的缺陷）。"""
    b = assemble_bundle(load_fact_views())
    transitions = b["transitions"]
    assert ("Init", "SETUP", "Ready") in transitions
    assert ("Ready", "PLAY", "Playing") in transitions
    # wildcard 转移被丢弃
    assert all(s != "*" and d != "$current" for s, m, d in transitions)


def test_assemble_message_instances_state_normalized():
    """message_instances 的 key 状态名必须与 transitions 归一化一致（否则字段级实例失效）。

    回归测试：2026-10-21 修复——assemble_bundle 对 transitions 做了 _normalize_state
    （INIT→Init）但 message_instances 用未归一化状态名（INIT/READY），导致
    edge_cover 查不到字段级实例。
    """
    b = assemble_bundle(load_fact_views())
    mi = b.get("message_instances") or {}
    assert mi, "应有字段级实例（source 源 AutoSeeder 产出）"
    trans_set = {(s, m, d) for s, m, d in b["transitions"]}
    # 每个实例 key 都能命中归一化后的 transitions（状态名大小写一致）
    for key in mi:
        assert key in trans_set, \
            f"message_instances key {key} 状态名未归一化，无法命中 transitions"
    # SETUP 的字段级实例存在（关键转移）
    assert any(k[1] == "SETUP" for k in mi)


def test_assemble_required_headers():
    b = assemble_bundle(load_fact_views())
    assert b["required_headers"]["SETUP"] == ["CSeq", "Transport"]
    assert b["required_headers"]["PLAY"] == ["CSeq", "Session"]


def test_assemble_security_from_vuln():
    b = assemble_bundle(load_fact_views())
    assert len(b["security"]) >= 29  # vuln 29 facts 分桶
    assert any(stype == "method" and name == "SETUP"
               for stype, name, _ in b["security"])


# ===========================================================================
# 渲染 prompt
# ===========================================================================

def test_render_prompt_contains_key_knowledge():
    b = assemble_bundle(load_fact_views())
    system, user = render_seed_prompt(b, protocol="RTSP", n_seeds=5)
    assert "RTSP" in system
    assert "SETUP" in user
    assert "Init" in user
    assert "Transport" in user
    assert "[状态机转移]" in user
    assert "[必填字段]" in user
    assert "[安全关注" in user


# ===========================================================================
# 生成（StubLLM）
# ===========================================================================

def test_generate_seeds_parses_stub_response():
    b = assemble_bundle(load_fact_views())
    llm = StubLLMClient(response=[{
        "description": "SETUP→PLAY 正常会话",
        "state_path": ["Init", "Ready", "Playing"],
        "messages": [
            {"method": "SETUP",
             "headers": {"CSeq": "1", "Transport": "RTP/AVP"}, "body": ""},
            {"method": "PLAY",
             "headers": {"CSeq": "2", "Session": "{{session_id}}"}, "body": ""},
        ],
    }])
    seeds = generate_seeds(b, llm, protocol="RTSP", n_seeds=1)
    assert len(seeds) == 1
    assert seeds[0].messages[0].method == "SETUP"
    assert seeds[0].messages[1].method == "PLAY"
    # 记录了 prompt 调用
    assert len(llm.calls) == 1


def test_parse_seed_response_variants():
    # {"seeds": [...]}
    assert len(parse_seed_response({"seeds": [{"messages": [{"method": "OPTIONS"}]}]},
                                   "rtsp", [], [])) == 1
    # list
    assert len(parse_seed_response([{"messages": [{"method": "OPTIONS"}]}],
                                   "rtsp", [], [])) == 1
    # 空
    assert parse_seed_response("not json", "rtsp", [], []) == []


# ===========================================================================
# 校验
# ===========================================================================

def _valid_seed() -> SeedCorpus:
    return SeedCorpus(
        protocol="rtsp",
        target_state_path=["Init", "Ready", "Playing", "Init"],
        messages=[
            SeedMessage("SETUP",
                        {"CSeq": "1", "Transport": "RTP/AVP;unicast"}, ""),
            SeedMessage("PLAY", {"CSeq": "2", "Session": "{{session_id}}"}, ""),
            SeedMessage("TEARDOWN",
                        {"CSeq": "3", "Session": "{{session_id}}"}, ""),
        ],
    )


def test_validate_valid_seed_passes():
    b = assemble_bundle(load_fact_views())
    assert validate_seed(_valid_seed(), b) == []


def test_validate_unknown_method():
    b = assemble_bundle(load_fact_views())
    seed = SeedCorpus(
        protocol="rtsp",
        messages=[SeedMessage("FOOBAR", {"CSeq": "1"}, "")])
    errs = validate_seed(seed, b)
    assert any("未知方法" in e for e in errs)


def test_validate_missing_required_header():
    b = assemble_bundle(load_fact_views())
    seed = SeedCorpus(
        protocol="rtsp",
        messages=[SeedMessage("SETUP", {"CSeq": "1"}, "")])  # 缺 Transport
    errs = validate_seed(seed, b)
    assert any("缺必填头" in e and "Transport" in e for e in errs)


def test_validate_invalid_transition():
    b = assemble_bundle(load_fact_views())
    seed = SeedCorpus(
        protocol="rtsp",
        target_state_path=["Init"],
        messages=[SeedMessage("PLAY", {"CSeq": "1", "Session": "x"}, "")])
    errs = validate_seed(seed, b)
    assert any("不合法" in e for e in errs)  # Init 不能 PLAY


def test_assemble_bundle_stores_resolution_superseded():
    """assemble_bundle 应把 resolve_claims 的消解结果（含 superseded）存进
    methods[*].resolution，使「被覆盖声称可追溯」名副其实（支撑 RQ3 消融：查冲突方法、
    冲突消解方法与被覆盖声称清单）。"""
    # 构造 SETUP 的 state_changing 多源冲突：source(descriptive)=True vs traffic(observed)=False
    view = {
        "fact_key": {
            "protocol": "rtsp",
            "subject": {"type": "method", "name": "SETUP",
                        "qualifiers": {}, "path": []},
            "aspect": "state_changing",
            "condition": {"type": "always"},
        },
        "all_claims": [
            {"value": {"type": "bool", "data": True},
             "epistemic_type": "descriptive", "authority": "source",
             "claim_id": "c_src"},
            {"value": {"type": "bool", "data": False},
             "epistemic_type": "observed", "authority": "traffic",
             "claim_id": "c_trf"},
        ],
    }
    b = assemble_bundle([view], "rtsp")
    info = b["methods"]["SETUP"]
    assert "resolution" in info, "应存 resolution 字段"
    res = info["resolution"]["state_changing"]
    assert res["method"] == "precedence", f"消解方法应为 precedence，实际 {res['method']}"
    assert res["authority"] == "traffic", "observed 优先级最高，胜出源应为 traffic"
    assert res["superseded"] == ["c_src"], "source 的声称应被覆盖并保留"
    assert res["basis_claim_ids"] == ["c_trf"], "traffic 声称应被采纳"
    assert info["state_changing"] is False, "胜出值应为 False（observed）"
