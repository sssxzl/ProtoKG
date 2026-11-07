# -*- coding: utf-8 -*-
"""core/fused/rfc_extractor_binary.py —— **二进制协议**的 RFC 抽取通道（2026-11-07 新增）。

★ 与文本抽取（:mod:`core.fused.rfc_extractor`，5351 行）**并列**、互不依赖。
  文本侧有 8 个通道（A0/A0b/A0c/E/F/D/G/H/H′）；二进制侧有 2 个：

  **通道 B1**：**位域图 / 定长字段表** ⇒ 字段的**布局**
      （名 / 字节长度 / 偏移 / 顺序）⇒ aspect = ``header/binary_layout``
  **通道 B2**：**选项定义** ⇒ 选项的 **TLV 布局**
      （code / 名称 / 长度）⇒ aspect = ``header/option_layout``

★ 为什么布局要进中枢（而不是只留在 profile）：
  布局是**知识**（来自 RFC）⇒ 应当可溯源、可被论文引用、可被下游读。
  ★ 两个新 aspect 都落进 **``headers`` 桶** ⇒ **下游零改动**
    （`_apply_instance_fields` 的 `known_fields` 来自 headers 桶
      ⇒ 字段被认识 ⇒ 不会再被当「未知字段」丢进 argument）。

★ **纯确定性**：布局抽取不需要 LLM ⇒ 可复现、零成本、无幻觉。
"""
from __future__ import annotations

from typing import Any, Optional

from core.fused.rfc_forms_binary import (extract_bitfield_blocks,
                                          extract_fixed_fields,
                                          extract_option_tables)

#: 二进制布局的 aspect 名
ASPECT_BINARY_LAYOUT = "binary_layout"
ASPECT_OPTION_LAYOUT = "option_layout"


def _norm(kind: str, name: str, content: str, protocol: str,
          source: str, section: str) -> dict[str, Any]:
    """构造二进制通道的 norm（结构与文本侧 :func:`rfc_extractor._norm` 一致）。"""
    return {
        "norm_id": f"{protocol}.{kind}.{name.lower().replace(' ', '_')}",
        "kind": kind,
        "name": name,
        "content": content,
        "protocol": protocol,
        "kb_source_type": "rfc",
        # ★ source 已含 ``file:`` 前缀（抽取层给的）⇒ 这里**不要再包一层**
        #   （第一版写成 ``f"file:{source}#"`` ⇒ 落盘变成 ``file:file:xxx``）
        "source": f"{source}#{section}",
        "section": section,
    }


def extract_binary_layouts(protocol: str) -> list[dict]:
    """抽**字段布局**（位域图 + 定长字段表）⇒ ``header/binary_layout`` norms。

    ★ 偏移（offset）由**位域图的字段顺序累加**得出 ⇒ 不需要人工写。
      实测 RFC 2131 §4.1 的位域图累加 = 240 字节（BOOTP 固定头长度）✅。

    Returns:
        ``[{"name": 字段名, "content": "offset=…;length=…;order=…", ...}, ...]``
    """
    from core import paths
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    if not spec_dir.is_dir():
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for f in sorted(spec_dir.glob("*.txt")):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        for blk in extract_bitfield_blocks(lines):
            offset = 0
            for fld in blk.fields:
                nm = fld.name.strip()
                if not nm or nm.lower() in seen:
                    continue
                seen.add(nm.lower())
                out.append({
                    "name": nm,
                    "content": (f"offset={offset};length={fld.length};"
                                f"order={fld.order};encoding=octet"),
                    "protocol": protocol,
                    "source": f"file:{f.name}",
                    "line_no": fld.line_no,
                })
                offset += fld.length
        # 定长字段表（补位域图没覆盖的字段）
        for fld in extract_fixed_fields(lines):
            nm = fld.name.strip()
            if not nm or nm.lower() in seen:
                continue
            seen.add(nm.lower())
            out.append({
                "name": nm,
                "content": f"length={fld.length};encoding=octet",
                "protocol": protocol,
                "source": f"file:{f.name}",
                "line_no": fld.line_no,
            })
    return out


def extract_option_layouts(protocol: str) -> list[dict]:
    """抽**选项布局**（TLV 定义）⇒ ``header/option_layout`` norms。

    ★ 支持两种形态（汇总表 / 独立小节），见
      :func:`core.fused.rfc_forms_binary.extract_option_tables`。
    """
    from core import paths
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    if not spec_dir.is_dir():
        return []
    out: list[dict] = []
    seen: set[int] = set()
    for f in sorted(spec_dir.glob("*.txt")):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        for opt in extract_option_tables(lines):
            if opt.code in seen:
                continue
            seen.add(opt.code)
            _len = f";length={opt.length}" if opt.length is not None else ""
            out.append({
                "name": opt.name,
                "content": f"code={opt.code}{_len};encoding=tlv",
                "protocol": protocol,
                "source": f"file:{f.name}",
                "line_no": opt.line_no,
                "code": opt.code,
            })
    return out


def extract_binary_norms(protocol: str) -> list[dict]:
    """二进制源的**全部**通道 ⇒ norm 列表。

    ★ 通道 B1（字段布局）+ 通道 B2（选项布局）。
    """
    norms: list[dict] = []
    for row in extract_binary_layouts(protocol):
        norms.append(_norm("binary_layout", row["name"], row["content"],
                           protocol, row["source"],
                           f"@{row['line_no']}"))
    for row in extract_option_layouts(protocol):
        norms.append(_norm("option_layout", row["name"], row["content"],
                           protocol, row["source"],
                           f"@{row['line_no']}"))
    return norms


__all__ = [
    "ASPECT_BINARY_LAYOUT", "ASPECT_OPTION_LAYOUT",
    "extract_binary_layouts", "extract_option_layouts", "extract_binary_norms",
]
