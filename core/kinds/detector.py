# -*- coding: utf-8 -*-
"""core/kinds/detector.py —— **协议类型判断阶段**（2026-11-07 新增）。

★ 定位：整个流程的**最前面**一步 —— 在任何抽取发生之前，先回答
  「这个协议是**文本**的还是**二进制**的？」，由它决定后续走哪条路径：
    · 抽取：文本走现有 8 通道；二进制走新增的位域/定长/选项表通道；
    · 渲染：文本走 ``_render_from_profile``；二进制走新增的字节布局渲染。

★ 判定策略：**配置优先 + 自动探测兜底**
  ① ``profile.json`` 里有 ``protocol_kind`` 字段 ⇒ **直接采信**（人的判断优先）；
  ② 未声明 ⇒ **自动探测**（四条**协议无关**判据，见下）。

★ 四条判据（全部不认协议名、不认头名）：
  B1 ``bitfield``  位域图行（``|  op (1)  |`` 形态）—— 二进制的**结构签名**
  B2 ``octet``     字节单位的用法密度（``N octets``）
  B3 ``byteorder`` 网络字节序表述（``network byte order``）
  B4 ``magic``     魔数常量（``0x`` + 6~8 位十六进制）

★ 判定规则：
    binary  ⇔  B1 > 0                      （位域图是决定性证据）
           ∨  (B2 ≥ 阈值) ∧ (B3 > 0 ∨ B4 > 0)
    其余 ⇒ text

★ 实测（2026-11-07，四个协议）：

    ┌─────────┬──────┬────────┬────────┬────────┬────────┐
    │ 协议    │ 文件 │ B1位域 │ B2octet│ B3字节序│ B4魔数 │
    ├─────────┼──────┼────────┼────────┼────────┼────────┤
    │ rtsp    │  1   │   0    │   10   │   1    │   0    │
    │ sip     │  1   │   0    │    4   │   0    │   0    │
    │ smtp    │  4   │   0    │   18   │   0    │   0    │
    │ dhcpv4  │ 36   │  21    │  185   │   5    │  18    │
    └─────────┴──────┴────────┴────────┴────────┴────────┘
    ⇒ 三个文本协议**全部**不触发 binary 判据；DHCP 命中三条。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from core.kinds.evidence import KindDecision, KindEvidence

# ===========================================================================
# 判据（协议无关）
# ===========================================================================

#: B1 位域图行：**实测形态**（RFC 2131 §4.1）``|     op (1)    |   htype (1)   |``
#:   ⇒ 长度标记**只有数字**（没有 "octet"/"byte" 单位词）⇒ 单位词必须**可选**。
#:   ★ 初版把单位词写成必需 ⇒ 实测 0 命中 ⇒ 位域判据完全失效（已修）。
RE_BITFIELD = re.compile(
    r"\|\s*([A-Za-z][A-Za-z0-9 _-]*?)\s*\((\d+)(?:\s*(?:octet|byte)s?)?\)\s*\|",
    re.IGNORECASE)

#: B2 字节单位
RE_OCTET = re.compile(r"\boctets?\b", re.IGNORECASE)

#: B3 网络字节序
RE_BYTEORDER = re.compile(r"network\s+byte[- ]order", re.IGNORECASE)

#: B4 魔数（4 字节的 16 进制常量）
RE_MAGIC = re.compile(r"0x[0-9A-Fa-f]{6,8}")

#: B2 的密度阈值（每千行命中数）—— 文本协议实测 0.4~1.7/千行，
#:   二进制协议实测 7.0/千行 ⇒ 阈值取 **3.0/千行**（中间留足余量）。
B2_PER_KILO = 3.0

#: 允许的协议类型取值
KIND_TEXT = "text"
KIND_BINARY = "binary"


@dataclass(frozen=True)
class ProtocolKind:
    """协议类型（判定结果 + 依据）。"""

    protocol: str
    kind: str
    decided_by: str
    reason: str
    evidence: tuple[KindEvidence, ...] = ()
    scanned_files: int = 0

    @property
    def is_binary(self) -> bool:
        return self.kind == KIND_BINARY

    @property
    def is_text(self) -> bool:
        return self.kind == KIND_TEXT

    @property
    def decision(self) -> KindDecision:
        return KindDecision(
            protocol=self.protocol, kind=self.kind, decided_by=self.decided_by,
            evidence=self.evidence, reason=self.reason,
            scanned_files=self.scanned_files)

    def as_dict(self) -> dict[str, Any]:
        return self.decision.as_dict()


# ===========================================================================
# 自动探测
# ===========================================================================

def _probe_kb(protocol: str) -> tuple[dict[str, int], dict[str, list[str]], int]:
    """扫 kb 的 RFC 原文 ⇒ ``(判据 → 命中数, 判据 → 样例, 文件数)``。

    ★ 只读 kb 的 ``spec/*.txt``（RFC 底料）⇒ 不依赖任何配置。
    """
    from core import paths
    counts = {"bitfield": 0, "octet": 0, "byteorder": 0, "magic": 0}
    samples: dict[str, list[str]] = {k: [] for k in counts}
    files = 0
    d = paths.kb_source_dir(protocol, "rfc")
    if not d.is_dir():
        return counts, samples, 0
    for f in sorted(d.glob("*.txt")):
        files += 1
        for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            st = ln.strip()
            if RE_BITFIELD.search(st):
                counts["bitfield"] += 1
                if len(samples["bitfield"]) < 3:
                    samples["bitfield"].append(st[:80])
            if RE_OCTET.search(st):
                counts["octet"] += 1
                if len(samples["octet"]) < 3:
                    samples["octet"].append(st[:80])
            if RE_BYTEORDER.search(st):
                counts["byteorder"] += 1
                if len(samples["byteorder"]) < 3:
                    samples["byteorder"].append(st[:80])
            if RE_MAGIC.search(st):
                counts["magic"] += 1
                if len(samples["magic"]) < 3:
                    samples["magic"].append(st[:80])
    return counts, samples, files


def _profile_declared_kind(protocol: str) -> Optional[str]:
    """读 ``profile.json`` 的 ``protocol_kind`` 字段（人工显式声明）。"""
    from core import paths
    p = paths.target_profile(protocol)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return None
    val = str(data.get("protocol_kind") or "").strip().lower()
    if val in (KIND_TEXT, KIND_BINARY):
        return val
    return None


# ===========================================================================
# 公共 API
# ===========================================================================

def detect_protocol_kind(protocol: str) -> ProtocolKind:
    """判定协议的**类型**（text / binary）。

    ★ 优先级：``profile.protocol_kind``（人工声明）> 自动探测。
    ★ **零副作用**：只读 kb 与 profile，不写任何文件
      （落盘由 :func:`save_kind_artifact` 负责，调用方决定）。
    """
    declared = _profile_declared_kind(protocol)
    counts, samples, files = _probe_kb(protocol)

    ev = tuple(
        KindEvidence(criterion=name, hits=counts[name],
                     samples=tuple(samples[name]))
        for name in ("bitfield", "octet", "byteorder", "magic"))

    if declared is not None:
        return ProtocolKind(
            protocol=protocol, kind=declared, decided_by="profile",
            reason=(f"profile.json 显式声明 protocol_kind={declared}"
                    f"（人工判断优先，跳过自动探测）"),
            evidence=ev, scanned_files=files)

    # ---- 自动探测 ----
    total_lines = 0
    from core import paths
    d = paths.kb_source_dir(protocol, "rfc")
    if d.is_dir():
        for f in sorted(d.glob("*.txt")):
            total_lines += len(
                f.read_text(encoding="utf-8", errors="ignore").splitlines())
    per_kilo = (counts["octet"] / max(1, total_lines)) * 1000.0

    if counts["bitfield"] > 0:
        kind = KIND_BINARY
        reason = (f"自动探测：命中位域图 {counts['bitfield']} 行"
                  f"（B1，二进制协议的结构签名）⇒ binary")
    elif per_kilo >= B2_PER_KILO and (counts["byteorder"] > 0
                                      or counts["magic"] > 0):
        kind = KIND_BINARY
        reason = (f"自动探测：字节单位密度 {per_kilo:.1f}/千行"
                  f"（≥{B2_PER_KILO}）且命中"
                  f"{'网络字节序 %d 处' % counts['byteorder'] if counts['byteorder'] else ''}"
                  f"{'魔数 %d 处' % counts['magic'] if counts['magic'] else ''}"
                  f"⇒ binary")
    else:
        kind = KIND_TEXT
        reason = (f"自动探测：位域图 0 行、字节单位密度 {per_kilo:.1f}/千行"
                  f"（<{B2_PER_KILO}）⇒ text")

    return ProtocolKind(protocol=protocol, kind=kind, decided_by="auto",
                         reason=reason, evidence=ev, scanned_files=files)


def kind_artifact_path(protocol: str) -> Path:
    """判定结果的落盘路径：``derived/hub/<协议>/protocol_kind.json``。

    ★ 中枢重设计（2026-11-08）：协议类型判定是**中枢级**产物 ⇒ 落 hub/。
    """
    from core import paths
    # ★ 中枢重设计（2026-11-08）：协议类型判定是**中枢级**产物 ⇒ 落 hub/
    return paths.hub_root() / "protocol_kind.json"


def save_kind_artifact(kind: ProtocolKind) -> Path:
    """把判定结果**落盘**（可审计：论文可引「本协议判定为 binary，依据 …」）。"""
    p = kind_artifact_path(kind.protocol)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(kind.as_dict(), ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")
    return p


def load_kind_artifact(protocol: str) -> Optional[ProtocolKind]:
    """读回落盘的判定结果（渲染层等**下游阶段**用，避免各自重算）。"""
    p = kind_artifact_path(protocol)
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return None
    ev = tuple(KindEvidence(criterion=e.get("criterion", ""),
                            hits=int(e.get("hits", 0)),
                            samples=tuple(e.get("samples") or ()))
              for e in (d.get("evidence") or []))
    return ProtocolKind(protocol=d.get("protocol", protocol),
                         kind=d.get("kind", KIND_TEXT),
                         decided_by=d.get("decided_by", "auto"),
                         reason=d.get("reason", ""),
                         evidence=ev,
                         scanned_files=int(d.get("scanned_files", 0)))


__all__ = [
    "ProtocolKind", "detect_protocol_kind", "kind_artifact_path",
    "save_kind_artifact", "load_kind_artifact",
    "KIND_TEXT", "KIND_BINARY",
]
