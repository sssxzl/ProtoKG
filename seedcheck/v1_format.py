# -*- coding: utf-8 -*-
"""seedcheck/v1_format.py —— **V1 格式必假**（协议无关最小集）。

★ 为什么只有 V1 阻断
  · 「格式非法」⇒ 任何服务器**必然拒**（连解析都过不去）⇒ **零价值** ⇒ 丢弃。
  · 「协议越界」（V2~V4）⇒ 可能报错、可能崩溃 ⇒ ★ **高价值** ⇒ 只打标不丢弃。

★ 为什么判据是「协议无关」的
  V1 只判「**任何**协议都不接受的形式」⇒ 对 RTSP / SIP / HTTP 全成立 ⇒ **零误差**。
  ⇒ 协议特有格式（URI scheme、方法名是否合法…）**不在 V1 判**
    ⇒ 那些交给 **V2（用中枢知识判）** ⇒ 判据来自知识 ⇒ 不硬编码。

★ 5 条判据
  1. 报文文件非空
  2. 能按空行切成 ≥1 个报文块
  3. 每个块的首行至少 2 个空格分隔的字段（方法名 URI 版本 —— HTTP-like 共性）
  4. 头行含 ``:``
  5. 报文以空行结尾（末行是空行）
"""
from __future__ import annotations

from .model import SeedRecord, Violation


def _split_messages(raw: str) -> list[str]:
    """按空行切报文块（兼容 CRLF / LF）。"""
    norm = raw.replace("\r\n", "\n")
    return [m for m in norm.split("\n\n") if m.strip()]


def check(seed: SeedRecord) -> list[Violation]:
    """V1 检查 ⇒ 返回违规列表（**每条都是阻断级**）。"""
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
