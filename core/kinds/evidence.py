# -*- coding: utf-8 -*-
"""core/kinds/evidence.py —— 协议类型判定的**证据**结构（可审计）。

★ 为什么要有独立的证据对象：
  协议类型判定会影响**抽取通道**与**渲染 writer** 的选择 ⇒ 一旦判错，
  后果是「静默地抽错/渲染错」（不会报错，只是知识不对）。
  ⇒ 判定必须**可审计**：论文里要能写「本协议经自动判定为 binary，
    依据 B1=21 行位域图 / B3=5 处网络字节序 / B4=18 处魔数」。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class KindEvidence:
    """一条判定证据（判据名 + 命中数 + 样例）。"""

    #: 判据标识（**协议无关**的判据名，不含协议名）
    criterion: str
    #: 命中次数
    hits: int
    #: 样例（最多 3 条，用于人工核对）
    samples: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["samples"] = list(self.samples)
        return d


@dataclass(frozen=True)
class KindDecision:
    """协议类型的**判定结果 + 全部依据**（落盘用）。"""

    protocol: str
    #: "text" / "binary"
    kind: str
    #: 判定来源："profile"（人工声明）/ "auto"（自动探测）
    decided_by: str
    #: 命中的判据（判据名 → 证据）
    evidence: tuple[KindEvidence, ...] = ()
    #: 判定理由（人可读，落盘 + 日志）
    reason: str = ""
    #: 判定时的 kb 文件数（可审计：判定基于哪些底料）
    scanned_files: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "kind": self.kind,
            "decided_by": self.decided_by,
            "reason": self.reason,
            "scanned_files": self.scanned_files,
            "evidence": [e.as_dict() for e in self.evidence],
        }


__all__ = ["KindEvidence", "KindDecision"]
