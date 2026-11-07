# -*- coding: utf-8 -*-
"""core/raw_writers_binary.py —— **二进制协议**的 .raw 渲染（2026-11-07 新增）。

★ 为什么需要：
  ``core/raw_writers.py`` 的 ``_render_from_profile`` 只有**两个文本行模板**
  （``request_line`` / ``header_line``）⇒ 二进制协议（如 DHCPv4）落盘出来是
  ``DHCPDISCOVER\\r\\n``（14 字节）—— **不是合法报文**，对 fuzzer 无效。
  ⇒ 二进制协议需要按**字节布局**渲染：定长字段（offset/length/endian）+
  变长选项（TLV 序列）。

★ **协议无关**：全部布局来自 ``profile.raw_format.binary_fields`` /
  ``binary_options``（**纯数据**）⇒ 换协议只换 profile，不改代码。
  DNS / QUIC / 将来的其它二进制协议都能用同一套。

★ 渲染顺序：
    ① 定长字段区（按 ``offset`` 排 ⇒ 定长区自动补零/补 padding）
    ② magic cookie（若布局里有）
    ③ 选项区（TLV 序列：``code(1) + len(1) + data``，末尾 255 结束）
"""
from __future__ import annotations

import ipaddress
import logging
import struct
from typing import Any, Optional

from .models import SeedCorpus

log = logging.getLogger("protorag.raw_writers_binary")


# ===========================================================================
# 值编码（type → bytes）
# ===========================================================================

def _encode_value(value: Any, ftype: str, length: int,
                  byte_order: str) -> bytes:
    """把一个字段值编码成定长字节。

    ★ 支持的 ``type``（**固定词表**，可校验）：
        ``uint8`` / ``uint16`` / ``uint32`` / ``uint64``
        ``ipv4``      4 字节点分十进制
        ``ipv4_list`` 逗号分隔的多个 ipv4
        ``mac``       6 字节 MAC（``aa:bb:cc:dd:ee:ff`` 或 ``aabb.ccdd.eeff``）
        ``bytes``     十六进制串（``0x...``）或原文
        ``string``    ASCII 原文（不足补零，超长截断）
    """
    if value is None:
        return b"\x00" * length
    s = str(value).strip()
    if not s:
        return b"\x00" * length

    if ftype in ("uint8", "uint16", "uint32", "uint64"):
        try:
            n = int(s, 0) if s.lower().startswith("0x") else int(s)
        except ValueError:
            n = 0
        fmt = {"uint8": "B", "uint16": "H", "uint32": "I", "uint64": "Q"}[ftype]
        prefix = ">" if byte_order == "network" else "<"
        try:
            return struct.pack(prefix + fmt, n)
        except struct.error:
            return b"\x00" * length

    if ftype == "ipv4":
        try:
            return ipaddress.IPv4Address(s).packed
        except (ipaddress.AddressValueError, ValueError):
            return b"\x00" * 4

    if ftype == "ipv4_list":
        out = bytearray()
        for part in s.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out += ipaddress.IPv4Address(part).packed
            except (ipaddress.AddressValueError, ValueError):
                out += b"\x00" * 4
        return bytes(out)[:length].ljust(length, b"\x00")

    if ftype == "mac":
        h = s.replace(":", "").replace("-", "").replace(".", "")
        if len(h) < 12:
            h = h.ljust(12, "0")
        try:
            return bytes.fromhex(h[:12])
        except ValueError:
            return b"\x00" * 6

    if ftype == "bytes":
        if s.lower().startswith("0x"):
            try:
                return bytes.fromhex(s[2:])
            except ValueError:
                return b"\x00" * length
        return s.encode("utf-8", "ignore")[:length]

    # string / 未知
    return s.encode("utf-8", "ignore")[:length].ljust(length, b"\x00")


# ===========================================================================
# 选项（TLV）编码
# ===========================================================================

def _encode_options(options: list[dict], values: dict[str, Any],
                    byte_order: str) -> bytes:
    """把选项渲染成 TLV 序列：``code(1) + len(1) + data``，末尾 ``255``。

    ★ 协议无关：``code`` 与 ``type`` 来自 profile 的 ``binary_options``。
    ★ 变长选项的 ``len`` 字节 = **数据长度**（不含 code/len 自身），
      依据 RFC 2132 §2「the value of the length octet does not include the
      two octets specifying the tag and length」。
    """
    out = bytearray()
    for opt in options or []:
        name = str(opt.get("name") or "").strip()
        if not name:
            continue
        code = int(opt.get("code", 0))
        ftype = str(opt.get("type") or "bytes")
        raw = values.get(name)
        if raw is None:
            continue
        if isinstance(raw, (list, tuple)):
            data = bytearray()
            for item in raw:
                data += _encode_value(item, ftype, int(opt.get("length", 0) or 0),
                                      byte_order)
        else:
            data = _encode_value(raw, ftype, int(opt.get("length", 0) or 0),
                                  byte_order)
        out.append(code & 0xFF)
        out.append(len(data) & 0xFF)
        out += data
    out.append(0xFF)                      # End Option
    return bytes(out)


# ===========================================================================
# 主入口
# ===========================================================================

def _parse_layout(text: str) -> dict[str, Any]:
    """解析布局串 ``offset=0;length=1;order=0;encoding=octet`` ⇒ dict。"""
    out: dict[str, Any] = {}
    for part in str(text or "").split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k in ("offset", "length", "order", "code"):
            try:
                out[k] = int(v)
            except ValueError:
                pass
        else:
            out[k] = v
    return out


def render_binary_from_profile(seed: SeedCorpus, profile: dict) -> bytes:
    """按**二进制布局**渲染 .raw 字节流。

    ★ 布局来源（**优先级从高到低**）：
      ① **知识中枢**的 ``binary_layout`` / ``option_layout``
         （来自 RFC 的位域图 / 选项表 ⇒ **可溯源、不必手写**）；
      ② ``profile.raw_format.binary_fields`` / ``binary_options``（手写兜底）。

    ★ 报文里的字段值从 ``msg.headers`` 取（**中枢 headers 桶**的知识），
      与文本路径同源 ⇒ **下游零改动**。
    """
    fmt = (profile or {}).get("raw_format") or {}
    byte_order = str(fmt.get("byte_order") or "network").lower()

    # ① profile 布局（**渲染用的权威布局**）
    fields = list(fmt.get("binary_fields") or [])
    options = list(fmt.get("binary_options") or [])
    if not fields:
        return b""

    # 定长区总长 = 最大 offset+length
    total = 0
    for f in fields:
        try:
            end = int(f.get("offset", 0)) + int(f.get("length", 1))
        except (TypeError, ValueError):
            continue
        total = max(total, end)

    out = bytearray()
    for msg in seed.messages:
        values = dict(getattr(msg, "headers", {}) or {})
        buf = bytearray(total)
        for f in fields:
            name = str(f.get("name") or "").strip()
            if not name:
                continue
            try:
                off = int(f.get("offset", 0))
                ln = int(f.get("length", 1))
            except (TypeError, ValueError):
                continue
            data = _encode_value(values.get(name), str(f.get("type") or "bytes"),
                                 ln, byte_order)
            buf[off:off + len(data)] = data[:ln]
        out += buf
        if options:
            out += _encode_options(options, values, byte_order)
    return bytes(out)


__all__ = ["render_binary_from_profile", "_encode_value", "_encode_options"]
