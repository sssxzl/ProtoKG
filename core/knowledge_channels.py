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

#: 通道键 → 类别/归属 的**默认**（profile.json 的 ``knowledge_channels``
#: 段可覆盖；缺省时用这张表 ⇒ 老 profile 不加段也能工作）。
DEFAULT_CHANNELS: dict[str, dict[str, str]] = {
    "seedgen.precondition":     {"class": CLASS_IMPL, "owner": "expert_note"},
    "seedgen.session_header":   {"class": CLASS_IMPL, "owner": "expert_note"},
    "seedgen.url_template":     {"class": CLASS_IMPL, "owner": "expert_note"},
    "seedgen.state_changing":   {"class": CLASS_IMPL, "owner": "expert_note"},
    "seedgen.required_headers": {"class": CLASS_SPEC, "owner": "rfc"},
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


__all__ = [
    "CLASS_SPEC", "CLASS_IMPL", "CLASS_ENV",
    "DEFAULT_CHANNELS", "load_profile", "load_channels",
    "channel_class", "channel_owner", "channel_allowed", "summarize",
]
