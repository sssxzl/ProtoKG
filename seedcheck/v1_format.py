# -*- coding: utf-8 -*-
"""seedcheck/v1_format.py —— **V1 格式必假**（按**报文形态**分三档判据）。

★ 为什么只有 V1 阻断
  · 「格式非法」⇒ 任何服务器**必然拒**（连解析都过不去）⇒ **零价值** ⇒ 丢弃。
  · 「协议越界」（V2~V4）⇒ 可能报错、可能崩溃 ⇒ ★ **高价值** ⇒ 只打标不丢弃。

★ ★ 为什么**分三档**（2026-11-12 跨协议实测）
  旧的 V1 是**一套「HTTP-like 请求」判据**（首行 ≥2 空格 / 头行有冒号 / 以空行结尾）
  ⇒ ⇒ 它**只适用于「请求型文本协议」**：
    · **smtp**（**命令型**：``EHLO x\\r\\n``）⇒ 实测 16 条种子**全部**被判「非法」
      （``no_terminator`` + ``bad_request_line`` ⇒ 误报）
    · **DHCPv4**（**二进制**）⇒ 判据完全不适用
  ⇒ ⇒ 现在按 ``Knowledge.message_shape`` 分三档：

  | 档 | 协议（实测） | 判据 |
  |---|---|---|
  | ``text_request`` | rtsp / sip | 5 条最小集：非空 / 可切块 / 首行 ≥2 字段 / 头行有冒号 / 以空行结尾 |
  | ``text_command`` | smtp | 每条命令**首词是命令名** / 命令名形态合法 / **以换行结尾**（**不要求空行结尾**） |
  | ``binary`` | DHCPv4 | 长度 ≥ **最小报文长度**（按 ``binary_fields`` 推导） |

★ ★ **判据来源全部是 profile 的 ``raw_format``** ⇒ **不硬编码协议名**
  · 档位判定：``Knowledge.message_shape``
  · 二进制的最小长度：``raw_format.binary_fields`` 的 offset+length 推导
"""
from __future__ import annotations

from .model import SeedRecord, Violation


def _split_messages(raw: str) -> list[str]:
    """按空行切报文块（兼容 CRLF / LF）。"""
    norm = raw.replace("\r\n", "\n")
    return [m for m in norm.split("\n\n") if m.strip()]


# ===========================================================================
# ① text_request（请求型文本协议）：5 条最小集
# ===========================================================================

def _check_text_request(seed: SeedRecord) -> list[Violation]:
    out: list[Violation] = []
    fn = seed.filename
    raw = seed.raw_text

    if not raw.strip():
        out.append(Violation("V1", "empty_file", "报文文件为空", fn, "",
                             "规则：非空"))
        return out

    norm = raw.replace("\r\n", "\n")
    if not norm.endswith("\n\n"):
        out.append(Violation("V1", "no_terminator",
                             "报文未以空行结尾（缺报文结束符）", fn, "",
                             "规则：以空行结尾"))

    blocks = _split_messages(raw)
    if not blocks:
        out.append(Violation("V1", "no_message", "切不出任何报文块", fn, "",
                             "规则：可按空行切块"))
        return out

    for i, blk in enumerate(blocks, 1):
        lines = [ln for ln in blk.split("\n") if ln.strip()]
        if not lines:
            out.append(Violation("V1", "empty_block", f"第 {i} 个报文块为空", fn, "",
                                 "规则：块非空"))
            continue
        head = lines[0].strip()
        if len(head.split(" ")) < 2:
            out.append(Violation(
                "V1", "bad_request_line",
                f"第 {i} 个报文的首行字段不足 2 个（期望「方法 URI 版本」）",
                fn, head[:60], "规则：首行 ≥2 个空格分隔字段"))
        for ln in lines[1:]:
            s = ln.strip()
            if s and ":" not in s:
                out.append(Violation(
                    "V1", "bad_header_line",
                    f"第 {i} 个报文的头行缺冒号", fn, s[:60],
                    "规则：头行含 ':'"))
                break        # 每个块只报一条，避免噪声
    return out


# ===========================================================================
# ② text_command（命令型文本协议，如 SMTP）
# ===========================================================================

def _check_text_command(seed: SeedRecord, known_methods: set | None = None
                        ) -> list[Violation]:
    """命令型协议的格式必假。

    ★ 与请求型协议的**关键差异**
      · **不要求空行结尾**（命令序列用 CRLF 分隔即可）
      · **不要求首行 ≥2 字段**（``QUIT`` 这种无参命令只有一个词）
      · **要求**：命令的**首词是命令名**（字母/数字/连字符组成）
      · **要求**：以换行结尾
    """
    out: list[Violation] = []
    fn = seed.filename
    raw = seed.raw_text

    if not raw.strip():
        out.append(Violation("V1", "empty_file", "报文文件为空", fn, "",
                             "规则：非空"))
        return out

    norm = raw.replace("\r\n", "\n")
    if not (raw.endswith("\r\n") or raw.endswith("\n")):
        out.append(Violation("V1", "no_line_ending",
                             "报文未以换行结尾（命令序列需 CRLF 分隔）", fn, "",
                             "规则：以 CRLF 结尾"))

    lines = [ln for ln in norm.split("\n") if ln.strip()]
    if not lines:
        out.append(Violation("V1", "no_message", "切不出任何命令行", fn, "",
                             "规则：至少一条命令"))
        return out

    known = {str(m).upper() for m in (known_methods or set())}
    for i, ln in enumerate(lines, 1):
        cmd = ln.split(" ", 1)[0].strip()
        if not cmd:
            continue
        # ★ 2026-11-12（E5）：**信体/消息头**（``Name: value`` 形态）
        #   ⇒ 不是命令 ⇒ **不判命令名**
        #   ★ 例：SMTP 的 ``DATA`` 之后是邮件头（``Subject: …``）
        #     ⇒ 旧实现把它当命令判 ⇒ 报 ``bad_command_word``（实测 3 条误报）
        #   ⇒ 判据：含冒号 **且** 冒号前是合法头名 ⇒ 视为消息头 ⇒ 跳过
        if ":" in ln:
            _h = ln.split(":", 1)[0].strip()
            if _h and all(c.isalnum() or c in "-_." for c in _h):
                continue        # ★ 消息头 ⇒ 不是命令
        if not all(c.isalnum() or c in "-_." for c in cmd):
            out.append(Violation(
                "V1", "bad_command_word",
                f"第 {i} 条命令的命令名形态非法：{cmd[:40]}",
                fn, cmd[:40], "规则：命令名为字母/数字/连字符"))
            continue
        # 已知性（**有已知命令集时才判** ⇒ 缺判据不判 ⇒ 不误报）
        if known and cmd.upper() not in known:
            out.append(Violation(
                "V1", "unknown_command",
                f"第 {i} 条命令的命令名 {cmd} 不在已知命令集里",
                fn, cmd[:40], "依据：existence（method 主体）"))
    return out


# ===========================================================================
# ③ binary（二进制协议，如 DHCPv4）
# ===========================================================================

def _binary_min_len(binary_fields: list) -> int:
    """按 ``binary_fields`` 推导**最小报文长度**（各字段 offset+length 的最大值）。"""
    mx = 0
    for f in (binary_fields or []):
        try:
            end = int(f.get("offset", 0)) + int(f.get("length", 0))
        except (TypeError, ValueError, AttributeError):
            continue
        mx = max(mx, end)
    return mx


def _check_binary(seed: SeedRecord, binary_fields: list | None = None
                  ) -> list[Violation]:
    """二进制协议的格式必假。

    ★ 判据（**全部由 profile 的 binary_fields 推导** ⇒ 不硬编码）
      ① 报文非空
      ② 长度 ≥ **最小报文长度**（按 binary_fields 的 offset+length 推导）
    """
    out: list[Violation] = []
    fn = seed.filename
    raw = seed.raw_text

    if not raw.strip():
        out.append(Violation("V1", "empty_file", "报文文件为空", fn, "",
                             "规则：非空"))
        return out

    data = getattr(seed, "raw_bytes", None)
    if not data:
        # ★ 没有字节视图 ⇒ **不判长度**（避免用字符数误判二进制 ⇒ 误报）
        return out

    min_len = _binary_min_len(binary_fields or [])
    if min_len and len(data) < min_len:
        out.append(Violation(
            "V1", "too_short",
            f"二进制报文长度 {len(data)} < 最小长度 {min_len}",
            fn, "", "依据：profile.raw_format.binary_fields"))
    return out


# ===========================================================================
# 入口
# ===========================================================================

def check(seed: SeedRecord, k=None) -> list[Violation]:
    """V1 检查 ⇒ 违规列表（**每条都是阻断级**）。

    Args:
        seed: 种子记录。
        k: ``Knowledge``（提供 ``message_shape`` / ``raw_format`` / 已知方法集）
            ⇒ **缺省时**按「请求型文本协议」处理（向后兼容）。
    """
    shape = (getattr(k, "message_shape", None) or "text_request")
    if shape == "binary":
        return _check_binary(
            seed, (getattr(k, "raw_format", None) or {}).get("binary_fields"))
    if shape == "text_command":
        known = set()
        methods = getattr(k, "known_methods", None)
        if methods:
            known = {str(m) for m in methods}
        return _check_text_command(seed, known)
    return _check_text_request(seed)
