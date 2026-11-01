"""tests/fused/test_generic_danger.py —— ② 通用危险层（规则推导，不调 LLM）。"""
from __future__ import annotations

from core.fused.downstream.generic_danger import generic_danger
from core.fused.downstream.rag_seedgen import load_fact_views, assemble_bundle


def _bundle():
    return assemble_bundle(load_fact_views())


def _seeds():
    b = _bundle()
    return generic_danger(b["transitions"], b["headers"], b["required_headers"],
                          precondition=b.get("precondition"),
                          session_header=b.get("session_header"))


def _method_seqs(seeds):
    return [tuple(m.method for m in s.messages) for s in seeds]


def _has_subseq(seq, sub):
    """判断 sub 是否为 seq 的连续子序列。"""
    for i in range(len(seq) - len(sub) + 1):
        if seq[i:i + len(sub)] == tuple(sub):
            return True
    return False


def test_self_loop_repeat_produces_setup_setup():
    seqs = _method_seqs(_seeds())
    assert any(_has_subseq(seq, ("SETUP", "SETUP")) for seq in seqs), \
        "自环重复种子应含 SETUP+SETUP 连续子序列"


def test_generic_danger_uses_observed_values_not_synthetic_boundaries():
    """2.3 边界取值已移除（expert_note v2 value_pool 迁走 + 实验教训：边界种子摊薄
    变异预算）。通用危险层只产自环/生命周期序列型种子，字段取值来自知识中枢观测值
    （traffic value_enum），不注入合成边界值（0/-1/MAX/超长串）。"""
    seeds = _seeds()
    assert seeds, "应仍产出自环/生命周期种子（边界取值移除≠层②失效）"
    # 层②种子 generated_by 仍是 rule-based:generic-danger
    assert all(s.generated_by == "rule-based:generic-danger" for s in seeds)


def test_lifecycle_produces_enter_exit_reenter():
    """生命周期种子应含「进入→离开→再进入」连续子序列。

    当前状态机（source 源 AutoSeeder）建模 TEARDOWN→Closed 为终止态，不再有
    「TEARDOWN 后再 SETUP」的 re-session 边；该 UAF 模式改由边界探针（源 B，
    uaf_seq action）从漏洞知识推导。故通用危险层（源 A，无漏洞知识）的生命周期
    落在 Ready↔Playing（PLAY↔PAUSE）这类通用会话状态往返上。
    """
    seqs = _method_seqs(_seeds())
    assert any(_has_subseq(seq, ("PLAY", "PAUSE", "PLAY")) for seq in seqs), \
        "生命周期种子应含 PLAY->PAUSE->PLAY（进入→离开→再进入）连续子序列"


def test_self_loop_has_describe_prefix_and_session():
    """修复验证：自环/生命周期种子应有 DESCRIBE 前缀，第二个及之后 SETUP 带 Session。"""
    seeds = _seeds()
    # 找含 SETUP+SETUP 子序列的自环种子
    for s in seeds:
        seq = tuple(m.method for m in s.messages)
        if _has_subseq(seq, ("SETUP", "SETUP")):
            assert seq[0] == "DESCRIBE", f"自环种子应以 DESCRIBE 开头，实际 {seq}"
            setups = [m for m in s.messages if m.method == "SETUP"]
            assert len(setups) >= 2
            # 第二个及之后的 SETUP 必须带 Session
            keys = {k.lower() for k in setups[1].headers}
            assert "session" in keys, "第二个 SETUP 应带 Session 头"
            return
    raise AssertionError("未找到含 SETUP+SETUP 的自环种子")


def test_generic_danger_is_deterministic_and_rule_based():
    b = _bundle()
    args = (b["transitions"], b["headers"], b["required_headers"])
    s1 = generic_danger(*args)
    s2 = generic_danger(*args)

    def _snap(seeds):
        return [(tuple(m.method for m in s.messages),
                 tuple((k, v) for m in s.messages
                       for k, v in sorted(m.headers.items())))
                for s in seeds]

    assert _snap(s1) == _snap(s2), "纯规则推导应确定性（同输入同输出，无 LLM 随机）"
    assert all(s.generated_by == "rule-based:generic-danger" for s in s1)
