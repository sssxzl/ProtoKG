# -*- coding: utf-8 -*-
"""core/knowledge_channels.py —— **知识通道登记表**（批次 2.5 F2）。

★ 为什么需要这个模块：
  「指定知识源跑实验却混进别的源」的根因是：**知识进入消费端的通道有好多条**
  （中枢 facts / profile.json 直读 / targets/ 下的协议资产 / 代码内常量），
  而**只有中枢 facts 那一条**受 ``source_set`` 过滤。
  ⇒ 本模块把「每条通道是什么知识、归属哪个源」**显式登记**，
  消费端据此决定「这条通道在本次源集合下**允不允许**用」。

★ 三层定性（class）：
  · ``L1`` **协议规范知识** —— RFC 文本本身能给出（能指向章节/段落）
  · ``L2`` **目标实现知识** —— 目标程序源码能给出（能指向源码符号）
  · ``L3`` **目标环境事实** —— 实测/部署配置给出（目标实例的事实，**不是**知识源）

★ 归属（owner）：
  ``rfc`` / ``expert_note`` / ``traffic`` / ``vuln`` / ``source``；
  ``-`` 表示**不属任何知识源**（目标环境事实）。

★ 判定规则（消费端统一用这一条）：
  ``owner`` ∈ 本次 ``source_set`` ⇒ 允许；否则 ⇒ **禁用**。
  ``L3``（owner = ``-``）⇒ **恒允许**（它是目标事实，不是「别的源的知识」）。
"""
from __future__ import annotations

import json
from typing import Optional

from core import paths

#: 三个类别
CLASS_SPEC = "L1"        # 协议规范知识
CLASS_IMPL = "L2"        # 目标实现知识
CLASS_ENV = "L3"         # 目标环境事实

#: **源 → 类别**（台账按源判定「这条知识是不是本次源集合的」）。
#:   ★ ``rfc`` = L1（规范知识）；其余四源都是 L2（实现/观测/漏洞/专家知识）；
#:   ``profile`` = 协议骨架（**混合** ⇒ 其内部按 origin 维度再分，
#:   由 ``build_hub --exclude-skeleton-dims`` 控制）。
SOURCE_CLASS: dict[str, str] = {
    "rfc": CLASS_SPEC,
    "expert_note": CLASS_IMPL,
    "traffic": CLASS_IMPL,
    "vuln": CLASS_IMPL,
    "source": CLASS_IMPL,
    "profile": "MIXED",
}

#: **桶 → 通道**（桶的内容来自哪条知识通道 ⇒ 台账给它 class/owner）。
#:   只列**不由 facts 直接派生**的桶；facts 派生的桶按 ``by_source`` 逐源判定。
BUCKET_CHANNEL: dict[str, str] = {
    "precondition": "seedgen.precondition",
    "session_header": "seedgen.session_header",
    "url_template": "seedgen.url_template",
    "required_headers": "seedgen.required_headers",
    # ★ 2026-11-07：语义规则投影的两个桶改用具名通道 —— 原先与
    #   `required_headers` 共用一个通道名，台账里看不出「这是约束投影」。
    #   class/owner 仍按「约束出自 RFC 规范」定为 SPEC/rfc，但注意
    #   **P 侧（response_expectation）的内容多为按确定性规则推断**：
    #   见 `rag_seedgen._resolve_expected_behavior()` 的三档来源
    #   （evidence / rule_corrected / rule_inferred）⇒ 引用条数时必须按来源
    #   分档，不能整体称「规范直出」。
    "legal_boundary": "seedgen.legal_boundary",
    "response_expectation": "seedgen.response_expectation",
    "vulnerability": "vuln",
    "statuses": "seedgen.required_headers",
}

#: 通道键 → 类别/归属 的**默认**（profile.json 的 ``knowledge_channels``
#: 段可覆盖；缺省时用这张表 ⇒ 老 profile 不加段也能工作）。
DEFAULT_CHANNELS: dict[str, dict[str, str]] = {
    "seedgen.precondition":     {"class": CLASS_IMPL, "owner": "expert_note"},
    "seedgen.session_header":   {"class": CLASS_IMPL, "owner": "expert_note"},
    "seedgen.url_template":     {"class": CLASS_IMPL, "owner": "expert_note"},
    "seedgen.state_changing":   {"class": CLASS_IMPL, "owner": "expert_note"},
    "seedgen.required_headers": {"class": CLASS_SPEC, "owner": "rfc"},
    "seedgen.legal_boundary":       {"class": CLASS_SPEC, "owner": "rfc"},
    "seedgen.response_expectation": {"class": CLASS_SPEC, "owner": "rfc"},
    "allowed_methods":          {"class": CLASS_IMPL, "owner": "source"},
    "vuln":                     {"class": CLASS_IMPL, "owner": "vuln"},
    "traffic_schema":           {"class": CLASS_IMPL, "owner": "traffic"},
    "boundary_probe.transport_tokens": {"class": CLASS_SPEC, "owner": "-"},
    "resources_file":           {"class": CLASS_ENV, "owner": "-"},
    "templates_file":           {"class": CLASS_IMPL, "owner": "traffic"},
}


def load_profile(protocol: str) -> dict:
    """读 profile.json（不存在 ⇒ 空 dict）。"""
    p = paths.target_profile(protocol)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_channels(protocol: str) -> dict[str, dict[str, str]]:
    """本协议的**知识通道登记表**：通道 → {class, owner, note?}。

    ★ 合并顺序：``DEFAULT_CHANNELS``（兜底） ← profile.json 的
      ``knowledge_channels``（覆盖）⇒ 老 profile 缺段也能用，新 profile 可精调。
    """
    out: dict[str, dict[str, str]] = {
        k: dict(v) for k, v in DEFAULT_CHANNELS.items()
    }
    prof = load_profile(protocol)
    declared = prof.get("knowledge_channels") or {}
    if isinstance(declared, dict):
        for key, val in declared.items():
            if not isinstance(val, dict):
                continue
            cur = out.setdefault(str(key), {})
            cur["class"] = str(val.get("class") or cur.get("class") or CLASS_IMPL)
            cur["owner"] = str(val.get("owner") or cur.get("owner") or "-")
            if val.get("note"):
                cur["note"] = str(val["note"])
    return out


def channel_class(protocol: str, channel: str) -> str:
    """某通道的类别（缺省 ⇒ ``L2`` 保守）。"""
    return str(load_channels(protocol).get(channel, {}).get("class") or CLASS_IMPL)


def channel_owner(protocol: str, channel: str) -> str:
    """某通道的归属源（缺省 ⇒ ``-``）。"""
    return str(load_channels(protocol).get(channel, {}).get("owner") or "-")


def channel_allowed(protocol: str, channel: str,
                     source_set: Optional[set[str]] = None) -> bool:
    """该通道在本次 ``source_set`` 下**是否允许**使用。

    ★ 判定：
      · ``L3``（目标环境事实，owner = ``-``）⇒ **恒允许**
        （它是「目标实例的事实」，不是「别的源的知识」）
      · 否则 ⇒ ``owner`` ∈ ``source_set`` 才允许
        （``source_set`` 缺省 = 不过滤 ⇒ 允许，保持旧行为）
    """
    info = load_channels(protocol).get(channel, {})
    cls = str(info.get("class") or CLASS_IMPL)
    owner = str(info.get("owner") or "-")
    if cls == CLASS_ENV:
        return True
    if source_set is None:
        return True
    return owner.lower() in {str(s).lower() for s in source_set}


def summarize(protocol: str) -> dict:
    """登记表摘要（供台账/审计打印）。"""
    return {
        "protocol": protocol,
        "channels": {
            k: {"class": v.get("class"), "owner": v.get("owner")}
            for k, v in sorted(load_channels(protocol).items())
        },
    }


def source_class(source: str) -> str:
    """某个知识源的类别（``rfc``→L1；其余→L2；``profile``→MIXED）。"""
    return SOURCE_CLASS.get(str(source or "").strip().lower(), CLASS_IMPL)


def owner_allowed(owner: str, source_set: Optional[set[str]] = None) -> bool:
    """归属源在本次 ``source_set`` 下是否允许（``-``/空 ⇒ 恒允许）。"""
    ow = str(owner or "-").strip().lower()
    if ow in ("", "-"):
        return True
    if source_set is None:
        return True
    return ow in {str(s).strip().lower() for s in source_set}


#: **应存在的桶全集**（台账要连「应该有但当前为空」的桶也列出来
#: ⇒ 审计时能看出「本该由 expert_note 支撑的会话语义，在纯 RFC 档是空的」）。
BUCKET_UNIVERSE: tuple[str, ...] = (
    "methods", "headers", "transitions", "method_sequences",
    "message_instances", "required_headers", "precondition",
    "session_header", "url_template", "statuses", "legal_boundary",
    "response_expectation", "vulnerability",
)


def build_ledger(bucket_sources: dict, protocol: str,
                 source_set: Optional[set[str]] = None) -> dict:
    """构造**知识台账**：每个桶的 {class, owner, count, allowed}。

    ★ 参数 ``bucket_sources`` = ``{桶名: {源名: 条数}}``（即 ``bundle["by_source"]``）。

    ★ 台账的价值：**单源实验可自证纯净** —— 不用人工逐条判定，
      直接看「哪个桶、由哪个源贡献、这次允不允许」。
    """
    chans = load_channels(protocol)
    ledger: dict[str, dict] = {}
    violations: list[dict] = []
    # ★ 先铺「应有但为空」的桶（count=0）⇒ 台账完整 ⇒ 缺口可见
    for _b in BUCKET_UNIVERSE:
        if _b in (bucket_sources or {}):
            continue
        _chan = BUCKET_CHANNEL.get(_b)
        ledger[_b] = {
            "by_source": {}, "count": 0, "empty": True,
            **({"channel": _chan,
                "class": str(chans.get(_chan, {}).get("class") or ""),
                "owner": str(chans.get(_chan, {}).get("owner") or "")}
               if _chan else {}),
        }
    for bucket, src_counts in sorted((bucket_sources or {}).items()):
        chan = BUCKET_CHANNEL.get(bucket)
        per_src: dict[str, dict] = {}
        total = 0
        for src, cnt in sorted((src_counts or {}).items()):
            cls = source_class(src)
            owner = src
            # profile（协议骨架）是**混合** ⇒ 其内部按 origin 维度区分，
            # 由 build_hub --exclude-skeleton-dims 控制 ⇒ 台账只标 MIXED。
            if chan and src == "profile":
                cls = str(chans.get(chan, {}).get("class") or cls)
                owner = str(chans.get(chan, {}).get("owner") or owner)
            ok = owner_allowed(owner, source_set)
            if cls == "MIXED":
                # ★ 协议骨架是**混合**知识（source 侧 + traffic 侧）
                #   ⇒ 能否用由 **构建参数** ``--exclude-skeleton-dims`` 控制
                #   ⇒ 台账**不猜**，标 allowed=None（待定）并在 skeleton_dims 里
                #     给出实际的排除维度 ⇒ 审计时一眼可判。
                ok = None
            per_src[src] = {"count": cnt, "class": cls, "owner": owner,
                            "allowed": ok}
            total += cnt
            if ok is False and cls in (CLASS_SPEC, CLASS_IMPL):
                violations.append({"bucket": bucket, "source": src,
                                   "class": cls, "owner": owner,
                                   "count": cnt})
        entry = {"by_source": per_src, "count": total}
        if chan:
            entry["channel"] = chan
            entry["class"] = str(chans.get(chan, {}).get("class") or "")
            entry["owner"] = str(chans.get(chan, {}).get("owner") or "")
        ledger[bucket] = entry
    return {
        "protocol": protocol,
        # ★ **不记 source_set** —— 它是**调用入参**，不是知识属性
        #   ⇒ 记进去会让「不传 source_set」与「显式传全量集合」两种调用
        #     产出**不同的 bundle** ⇒ 破坏「默认路径逐字节不变」的不变量
        #     （护栏 test_default_call_is_byte_identical_to_unfiltered 抓到过）。
        #   ⇒ 需要看本次源集合时，由**调用方**（seedgen）打印即可。
        "skeleton_dims": _skeleton_dims(protocol),
        "buckets": ledger,
        "violations": violations,
        "violation_count": len(violations),
        "pure": not violations,
    }


def _skeleton_dims(protocol: str) -> dict:
    """中枢记录的**骨架来源维度**（谁构建时排除了哪些维度）。

    ★ 协议骨架是**混合**知识 ⇒ 台账无法从桶级信息判定它是否干净
      ⇒ 由 ``build_hub --exclude-skeleton-dims`` 在**构建时**决定，
      并记进中枢 ``sources.json`` ⇒ 台账读它 ⇒ 审计可判。
    """
    from core import paths as P
    f = P.per_source_root(protocol) / "sources.json"
    if not f.is_file():
        return {}
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    sk = doc.get("skeleton") or {}
    return {"excluded_dims": sk.get("excluded_dims") or [],
            "fact_count": sk.get("fact_count")}


__all__ = [
    "CLASS_SPEC", "CLASS_IMPL", "CLASS_ENV",
    "SOURCE_CLASS", "BUCKET_CHANNEL",
    "DEFAULT_CHANNELS", "load_profile", "load_channels",
    "channel_class", "channel_owner", "channel_allowed", "summarize",
    "source_class", "owner_allowed", "build_ledger",
]
