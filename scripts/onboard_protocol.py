# -*- coding: utf-8 -*-
"""scripts/onboard_protocol.py —— **协议自动接入**（从规范生成档案草稿）。

★ 解决什么：一个**从来没公开过**的协议（但有规范文档），不需要人从头写
  ``profiles/<协议>/profile.json`` ⇒ 本脚本从 ``kb/<协议>/spec/`` 自动推断
  **八成**字段，剩 3 项必须人工（见 :data:`MANUAL_FIELDS`）。

★ 为什么可行：``allowed_methods`` / ``transport`` / ``encoding`` 等「协议是什么」
  的信息，**本来就该由抽取层从规范得出** ⇒ 现在的档案只是把结果**缓存**下来
  ⇒ 循环依赖（先有档案才能抽 → 档案又来自抽取）被打破。

用法::

    python scripts/onboard_protocol.py --protocol http            # 生成草稿
    python scripts/onboard_protocol.py --protocol http --dry-run  # 只看不写
    python scripts/onboard_protocol.py --protocol http --force    # 覆盖已有

退出码：0 = 生成成功；1 = 缺少规范输入；2 = 参数错误。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths  # noqa: E402

#: 必须人工的字段（自动推断不出来 ⇒ 草稿里留 null + TODO）
MANUAL_FIELDS = {
    "url_placeholders": "目标服务的资源路径（如 <server> → 真实地址、<stream> → 流名）",
    "resources_file": "可用资源清单文件名（如 rtsp_streams.json）",
    "boundary_probe": "黑盒行为参数（transport_tokens / client_port 范围）",
}

#: 规范里找方法定义章节的标题模式（按优先级）
METHOD_SECTION_PATTERNS = (
    r"method\s+definitions?",
    r"command\s+definitions?",
    r"(?:operations?|requests?|methods?)\s+(?:and|&)\s+(?:responses?|replies)",
    r"protocol\s+operations?",
    r"message\s+formats?",
    r"request\s+syntax",
    r"(?:the\s+)?method\s+(?:and|&)\s+response",
    r"response\s+codes?",
    r"requests?\s*$",
    r"syntax",
)

#: 从章节标题里认方法名（大写单词 / 全大写 token）
_METHOD_NAME_RE = re.compile(r"^\s*([A-Z][A-Z0-9_-]{1,23})\s*$")

#: 传输方式关键词
_TRANSPORT_HINTS = (
    (r"\bTCP\b", "tcp"), (r"\bUDP\b", "udp"), (r"\bSCTP\b", "sctp"),
)

#: 二进制协议的判据（位图 / 长度前缀）
_BINARY_HINTS = (
    r"\d+\s*bits?", r"bit\s*mask", r"length\s*prefix", r"fixed[- ]size\s+header",
)


def _spec_files(protocol: str) -> list[Path]:
    root = paths.kb_root() / protocol.lower() / "spec"
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file())


def _read_text(paths_: list[Path]) -> str:
    chunks = []
    for p in paths_:
        try:
            chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(chunks)


def _guess_transport(text: str) -> str | None:
    for pat, val in _TRANSPORT_HINTS:
        if re.search(pat, text, re.I):
            return val
    return None


def _guess_encoding(text: str) -> str | None:
    binary = sum(1 for h in _BINARY_HINTS if re.search(h, text, re.I))
    return "binary" if binary >= 2 else "text"


def _find_method_sections(lines: list[str]) -> list[tuple[int, str, str]]:
    """返回 (行号, 章节标题, 章节正文) —— 按已知标题模式匹配。"""
    out = []
    for pat in METHOD_SECTION_PATTERNS:
        rx = re.compile(rf"^\s*(?:\d+(?:\.\d+)*\s*)?(.*{pat}.*)$", re.I)
        for i, ln in enumerate(lines):
            m = rx.match(ln)
            if not m:
                continue
            title = m.group(1).strip()
            if len(title) > 80:
                continue
            # ★ 跳过**目录行**（点线引导：``* 10 Method Definitions .... 29``）
            if re.search(r"\.{3,}|\u2026", title):
                continue
            # ★ 收紧**标题**判据（正文行不算标题）：
            #   · 短（≤ 60 字符）
            #   · 不以句读结尾（正文才这样）
            #   · 词数 ≤ 8
            #   · 不含小写连接词（``the``/``and``/``of``…⇒ 正文特征）
            if len(title) > 60 or title.endswith((".", ",", ";", ":")):
                continue
            if len(title.split()) > 8:
                continue
            if re.search(r"\b(the|and|of|to|in|are|is|that|this|for|with)\b",
                         title, re.I):
                continue
            body = "\n".join(lines[i + 1: i + 400])
            out.append((i, title, body))
        if out:
            break
    return out


def _guess_methods(sections: list[tuple[int, str, str]]) -> list[str]:
    """从方法定义章节正文里认方法名（出现频次 ≥ 2 的全大写 token）。"""
    counts: dict[str, int] = {}
    for _, _, body in sections:
        for tok in re.findall(r"\b[A-Z][A-Z0-9_]{1,23}\b", body):
            counts[tok] = counts.get(tok, 0) + 1
    # 排除常见的非方法词
    # ★ 噪声词表：协议名本身 + 传输/编码/协议层的常见缩写 + 规范术语
    skip = {"RFC", "HTTP", "TCP", "UDP", "IP", "ID", "URI", "URL", "MUST", "SHOULD",
            "MAY", "REQUIRED", "OPTIONAL", "GET", "POST", "PUT", "HEAD", "DELETE",
            "SECTION", "CHAPTER", "STATUS", "OK", "ERROR", "NOTE", "ALL", "ANY",
            "RTSP", "RTP", "RTCP", "SDP", "AVP", "AVP/UDP", "GMT", "SP", "CRLF",
            "IETF", "RFC2326", "AND", "OR", "THE", "FOR", "NOT", "MAYNOT",
            "IN", "IP4", "IP6", "IPv4", "IPv6", "TCP", "IS", "AS", "IT", "OF", "TO"}
    cand = [(k, v) for k, v in counts.items()
            if k not in skip and v >= 2 and not k.startswith("_")]
    cand.sort(key=lambda kv: -kv[1])
    return [k for k, _ in cand[:24]]


def _guess_raw_format(text: str, methods: list[str]) -> dict:
    """从规范里猜请求行模板（保守：只认明确的「Request-Line = Method SP Request-URI SP Version」）。"""
    m = re.search(r"Request-Line\s*=\s*Method\s+SP\s+([A-Za-z\-]+)\s+SP\s+([A-Za-z\-]+)",
                  text, re.I)
    if m:
        return {
            "line_ending": "\\r\\n",
            "request_line": f"{{method}} {{url}} {{{m.group(2).lower()}}}",
        }
    if re.search(r"\{method\}\s*\{url\}", text):
        return {"line_ending": "\\r\\n", "request_line": "{method} {url} {version}"}
    return {"line_ending": "\\r\\n", "request_line": "{method} {url} {version}"}


def _guess_version(text: str, protocol: str = "") -> str | None:
    """★ 优先匹配**本协议**的版本（避免把规范里引用的 HTTP/1.1 当成协议版本）。"""
    if protocol:
        m = re.search(rf"\b{re.escape(protocol.upper())}/\d+\.\d+", text, re.I)
        if m:
            return m.group(0)
    # ★ 排除规范里**引用**的其它协议版本（HTTP/1.1 之类）
    m = re.search(r"\b(?!HTTP/)[A-Z]{2,6}/\d+\.\d+", text)
    return m.group(0) if m else None


def _from_extractor(protocol: str) -> tuple[list[str], list[str]]:
    """复用**抽取层**拿到精确的方法集与章节（启发式的替代品）。

    ★ 抽取层已有「23 种 RFC 内容形态判据」⇒ 方法集比纯文本启发式**准得多**。
    ⇒ 抽取失败时返回空 ⇒ 调用方回退到启发式。
    """
    try:
        from core.fused.extraction.rfc_extractor import extract_rfc_norms
        norms = extract_rfc_norms(protocol) or []
    except Exception:            # noqa: BLE001 —— 抽取层不可用 ⇒ 走启发式
        return [], []
    methods: list[str] = []
    sections: list[str] = []
    for n in norms:
        name = str(n.get("name") or "").strip()
        if not name or name in methods:
            continue
        # ★ 只收**方法**：norms 里还有字段名（Status-Line/Accept）、状态码（488）、
        #   章节名（Tags）等 ⇒ 按判据排除：
        #   · 全大写且不含小写 ⇒ 形如方法
        #   · 纯数字（状态码）⇒ 排除
        #   · 含 ``-``/``_`` 的多为字段名 ⇒ 排除（除非全大写且像方法）
        if name.isdigit():
            continue
        if not name.isupper():
            continue
        if "-" in name and "_" not in name:
            continue
        methods.append(name)
        sp = n.get("section_path") or n.get("section") or []
        if isinstance(sp, str):
            sp = [sp]
        for s in sp:
            s = str(s).strip()
            if not s or s in sections:
                continue
            # ★ 排除行号形态（``@352``）与纯数字
            if s.startswith("@") or s.isdigit():
                continue
            # ★ 排除**正文行**：含多个全大写词连排（如 ``DHCPDISCOVER DHCPREQUEST``）
            #   或含小写连接词 ⇒ 是正文不是标题
            if len(s.split()) > 6:
                continue
            if len(re.findall(r"\b[A-Z]{3,}\b", s)) >= 2:
                continue
            if re.search(r"\b(the|and|of|to|in|are|is|that|this|for|with|client)\b",
                         s, re.I):
                continue
            sections.append(s)
    return methods, sections


def build_draft(protocol: str) -> dict:
    """生成 profile.json 草稿。"""
    files = _spec_files(protocol)
    text = _read_text(files)
    lines = text.split("\n")
    sections = _find_method_sections(lines)
    methods = _guess_methods(sections)

    # ★★ 优先复用**抽取层**（它有 23 种 RFC 内容形态判据 ⇒ 方法集更准）
    #    ⇒ 启发式只作兜底（抽取层失败/无产物时）
    exact_methods, exact_sections = _from_extractor(protocol)
    if exact_methods:
        methods = exact_methods
    if exact_sections:
        sections = [(0, s, "") for s in exact_sections]

    draft = {
        "protocol": protocol.lower(),
        "note": "★ 本文件由 scripts/onboard_protocol.py 从 kb/<协议>/spec/ 自动生成"
                "（协议接入阶段 II 的「接入参数」部分）⇒ 剩余 TODO 项必须人工补。",
        "_自动推断": {
            "spec 文件数": len(files),
            "识别到的方法定义章节": [t for _, t, _ in sections],
            "识别到的方法数": len(methods),
            "置信度说明": "方法名靠「全大写 token 频次」启发式 ⇒ 建议人工复核",
        },
        # ── 接入参数（自动推断）──
        "transport": _guess_transport(text) or None,
        "encoding": _guess_encoding(text),
        "allowed_methods": methods or None,
        "raw_format": _guess_raw_format(text, methods),
        "message_schema": {"hint": "★ TODO：消息实例必须含哪些字段（从规范的必填头推）"},
        "rfc": {
            "sections": [t for _, t, _ in sections] or None,
            "version": _guess_version(text, protocol),
        },
        "traffic_schema": None,
        "vuln": {"enabled": False},
        "knowledge_channels": {},
        # ── 投放配置（必须人工）──
        "default_url": None,
        "url_placeholders": None,
        "resources_file": None,
        "templates_file": None,
        "boundary_probe": None,
        "seedgen": {"canonical_flow": None},
    }
    draft["_TODO_必须人工"] = {
        f: why for f, why in MANUAL_FIELDS.items()
    }
    return draft


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="从规范自动生成协议档案草稿")
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    ap.add_argument("--force", action="store_true", help="覆盖已有档案")
    args = ap.parse_args(argv)

    proto = args.protocol.lower()
    files = _spec_files(proto)
    if not files:
        print(f"❌ 阶段 I 未就绪：kb/{proto}/spec/ 下没有规范文件")
        print(f"   ⇒ 先放知识源（规范），再跑本脚本")
        return 1

    draft = build_draft(proto)
    out_dir = paths.targets_root() / proto
    out_file = out_dir / "profile.json"

    print(f"=== 协议档案草稿：{proto} ===")
    print(f"  规范文件 {len(files)} 个")
    auto = draft["_自动推断"]
    print(f"  方法定义章节：{auto['识别到的方法定义章节'] or '未识别'}")
    print(f"  方法候选（{auto['识别到的方法数']}）：{(draft['allowed_methods'] or [])[:10]}")
    print(f"  transport={draft['transport']}  encoding={draft['encoding']}  "
          f"version={draft['rfc']['version']}")
    print("\n  ⚠ 必须人工补（TODO）：")
    for f, why in MANUAL_FIELDS.items():
        print(f"    · {f:20s} {why}")

    if args.dry_run:
        print("\n（--dry-run：未写文件）")
        return 0
    if out_file.exists() and not args.force:
        print(f"\n⚠ 已存在 {out_file}（未覆盖；要覆盖请加 --force）")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"\n✅ 已生成 {out_file}")
    print(f"   补完 3 项 TODO 后即可：")
    print(f"     python scripts/check_protocol_ready.py --protocol {proto}")
    print(f"     python scripts/seedgen.py --protocol {proto} --max-seeds 5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
