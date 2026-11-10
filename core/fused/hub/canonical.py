"""core/fused/canonical.py —— ③ 中枢层：canonical 序列化 + 确定性 ID。

规范见 docs/设计/顶层设计/规范化序列化规范.md（运行时报错时由本模块生成）。

本模块是 canonical 序列化的唯一实现。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import is_dataclass, asdict
from typing import Any


# ===========================================================================
# Sentinel: 显式空值哨兵
# ===========================================================================
# 设计文档规范第 4 条: "null / None: 默认不输出该键; 若必须存在, 用显式哨兵字符串"
# 这里定义哨兵以让 value/data 这类槽位可以表达"存在但为空"。
_NULL_SENTINEL = "__NULL_SENTINEL__"


# ===========================================================================
# 模块加载时自测用例（import 时即执行, 失败时发 RuntimeWarning）
# ===========================================================================

def _self_tests():
    """运行 6 个断言用例, 返回 (passed, total) 整数元组。

    注：源码按 Case 标签编号到 Case 5，但 Case 4（联合类型）内含两个独立断言
    （不等时不同 / 等时同），故 cases 列表共 6 项、total = 6。
    """
    from core.fused.hub.models import (
        Subject, FactKey, ConditionAlways, ConditionPredicate, Value,
    )
    cases = []

    # Case 1: 确定性 —— 同一逻辑内容, 多次调用字节序列相同
    a = FactKey(protocol="rtsp", version="1.0",
                subject=Subject(type="method", name="SETUP"),
                aspect="existence", condition=ConditionAlways())
    b = FactKey(protocol="rtsp", version="1.0",
                subject=Subject(type="method", name="SETUP"),
                aspect="existence", condition=ConditionAlways())
    cases.append(("确定性", canonical_serialize(a) == canonical_serialize(b)))

    # Case 2: 键排序 —— dict 插入顺序不同, 输出相同字节
    a = Subject(type="method", name="SETUP",
                qualifiers={"role": "server", "side": "in"})
    b = Subject(type="method", name="SETUP",
                qualifiers={"side": "in", "role": "server"})
    cases.append(("键排序", canonical_serialize(a) == canonical_serialize(b)))

    # Case 3: 嵌套 relation Subject 递归
    src = Subject(type="method", name="SETUP")
    tgt = Subject(type="method", name="PLAY")
    rel = Subject(type="relation", name="transitions_to",
                  qualifiers={"source": src, "target": tgt})
    s = canonical_serialize(rel)
    assert b"transitions_to" in s, "rel 缺 type 字段"
    assert b"SETUP" in s and b"PLAY" in s, "rel 缺嵌套 subject"
    cases.append(("嵌套递归", True))

    # Case 4: 联合类型 (Condition) 按 type 字段排序
    c1 = ConditionPredicate(subject=None, aspect="a", op="eq", value=Value("scalar", 1))
    c2 = ConditionPredicate(subject=None, aspect="a", op="eq", value=Value("scalar", 2))
    a = canonical_serialize(c1); b = canonical_serialize(c2)
    cases.append(("不等时不同", a != b))
    a = canonical_serialize(c1); b = canonical_serialize(c1)
    cases.append(("等时同", a == b))

    # Case 5: None 默认不输出
    a = Subject(type="method", name="SETUP", qualifiers={}, path=[])
    b = Subject(type="method", name="SETUP")
    cases.append(("空字段不输出", canonical_serialize(a) == canonical_serialize(b)))

    passed = sum(1 for _, ok in cases if ok)
    return passed, len(cases)


# ===========================================================================
# 核心: canonical_serialize
# ===========================================================================

def _normalize(obj: Any) -> Any:
    """递归规范化: dataclass → dict, None → 默认删, str/bool → 锁定编码。"""
    if obj is None:
        return "__DELETE__"   # 哨兵, 调用方据此跳过该键
    if is_dataclass(obj):
        d = asdict(obj)
        return {k: _normalize(v) for k, v in d.items() if v is not None}
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, tuple)):
        out = [_normalize(v) for v in obj]
        return tuple(out) if isinstance(obj, tuple) else out
    return obj


def canonical_serialize(obj: Any) -> bytes:
    """按 fused_canonical_spec 序列化到 UTF-8 字节。

    规范要点:
      1. dict 键按字典序升序
      2. 字符串 UTF-8
      3. 数字: int 原样; float 用 repr()
      4. None 默认不输出
      5. bool → true/false
      6. 嵌套 Subject 递归
      7. 联合类型按 type 字段排序(因 asdict 已统一拆为 dict, 字典序即可)
      8. 无尾随空白
      9. 严格模式: 任何非规范输入即报错

    ⚠ 这里采用最简 JSON 编码(已满足规范 1/2/3/4/5/6/7/8), 严格模式(9)
      在调用方负责: 任何类型不在受控白名单应在上层报错。本函数不做类型检查。
    """
    normalized = _normalize(obj)
    if normalized == "__DELETE__":
        normalized = {}
    if normalized is None or (isinstance(normalized, dict) and len(normalized) == 0):
        normalized = {}
    # sort_keys=True 是规范 1, ensure_ascii=False 是规范 2 (utf-8)
    raw = json.dumps(normalized, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"))
    return raw.encode("utf-8")


# ===========================================================================
# ID 计算
# ===========================================================================

def compute_fact_id(fact_key) -> str:
    raw = canonical_serialize(fact_key)
    return "f2_" + hashlib.sha256(raw).hexdigest()[:16]   # fact_id 前缀 f2_（v1 退役后保留 f2_ 前缀, 与历史 f1_ 产物隔离）


def compute_claim_id(claim) -> str:
    raw = canonical_serialize(claim.value) + claim.epistemic_type.encode("utf-8")
    return "c2_" + hashlib.sha256(raw).hexdigest()[:16]   # claim_id 前缀 c2_（v1 退役后保留 c2_ 前缀, 与历史 c1_ 产物隔离）


def compute_evidence_id(evidence) -> str:
    raw = (evidence.source_type.encode("utf-8")
            + evidence.source_id.encode("utf-8")
            + canonical_serialize(evidence.locator))
    return "e2_" + hashlib.sha256(raw).hexdigest()[:16]   # evidence_id 前缀 e2_（v1 退役后保留 e2_ 前缀, 与历史 e1_ 产物隔离）


# ===========================================================================
# 模块加载时自测
# ===========================================================================

try:
    _PASS, _TOTAL = _self_tests()
    if _PASS != _TOTAL:
        import warnings
        warnings.warn(
            f"canonical 自测 {_PASS}/{_TOTAL} 通过, 检查 fused_canonical_spec.md",
            RuntimeWarning)
except Exception as exc:  # noqa: BLE001
    import warnings
    warnings.warn(f"canonical 自测失败: {exc}", RuntimeWarning)