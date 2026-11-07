# -*- coding: utf-8 -*-
"""core/kinds/ —— **协议类型体系**（横切层，2026-11-07 新增）。

★ 为什么要有这一层：
  文本协议（rtsp/sip/smtp）与二进制协议（DHCPv4）的**差异横跨三个阶段**：
    ① 抽取：文本靠「行模板 + ABNF」，二进制靠「位域图 + 定长表 + 选项表」；
    ② 中枢：二进制多一层**布局信息**（offset/length/endian）；
    ③ 渲染：文本用行模板，二进制要按字节布局拼。
  ⇒ 若把判定逻辑塞进 `fused/`（那是「知识抽取」专用），渲染层就得反向依赖
    抽取层 ⇒ 循环依赖 + 职责混乱。
  ⇒ 独立成 `core/kinds/`：**抽取层 / 渲染层 / 中枢层都只依赖它**。

★ 公共 API：
    from core.kinds import detect_protocol_kind
    kind = detect_protocol_kind("dhcpv4")      # → ProtocolKind
    kind.is_binary                                # → bool
    kind.evidence.as_dict()                       # → 可审计的判定依据
"""
from __future__ import annotations

from core.kinds.detector import (ProtocolKind, detect_protocol_kind,
                                 load_kind_artifact, save_kind_artifact)

__all__ = [
    "ProtocolKind",
    "detect_protocol_kind",
    "load_kind_artifact",
    "save_kind_artifact",
]
