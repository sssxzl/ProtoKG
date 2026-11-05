# -*- coding: utf-8 -*-
"""F 阶段试点：RFC 源产「消息级必填头」（确定性、零 LLM、只读）。

★ 动机：`required_headers` 桶 **100% 来自骨架**（rtsp 8 条 / sip 14 条）⇒
  RFC 单源实验里这一维不是 RFC 源的；而必填头**直接决定报文是否被服务器接受**
  （缺 CSeq / Session / Transport 的 RTSP 请求会被直接拒）⇒ 对 fuzzing 效果
  的影响量级**大于状态名**。

★ 本试点测**确定性路线**是否可行：
  扫 RFC 里的**规范性句 + 头名**（MUST/SHALL ... header / field）⇒ 抽出头名
  ⇒ 与骨架版逐头对照覆盖率。

★ 关键设计（协议无关）：
  · 头名候选 = 规范里出现过的 `X-Header` / 已知头名（由**已知头集合**限定）
  · 句式：`(MUST|SHALL|REQUIRED) ... (include|contain|carry|have|has|with) ... <Header>`
    或 `<Header> ... MUST ...` ⇒ 两种方向都扫
  · **消息级**语义：出现在「请求/消息必须含」的条款 ⇒ 对所有方法生效

用法：E:/app/Anaconda3/python.exe local/_pilot_required_headers.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths                                      # noqa: E402
from core.fused.downstream import rag_seedgen as RS        # noqa: E402

#: 规范性关键词
_NORM = r"(?:MUST|SHALL|REQUIRED)"
#: 「含/带」类动词
_VERB = r"(?:include|includes|contain|contains|carry|carries|have|has|with|provide|provides)"

#: 句式 ①： MUST/SHALL ... (include|contain) ... <头名>
RE_A = re.compile(_NORM + r"[^.]{0,160}?" + _VERB + r"[^.]{0,80}?"
                  r"\b([A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+)\b")
#: 句式 ②： <头名> ... MUST/SHALL ...
RE_B = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+)\b[^.]{0,120}?"
                  + _NORM)
#: 句式 ③： MUST/SHALL ... <头名>（同句无动词，靠 header/field 词定位）
RE_C = re.compile(_NORM + r"[^.]{0,120}?\b([A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+)\b"
                  r"[^.]{0,40}?\b(?:header|field|line)\b")


def known_headers(protocol: str) -> set[str]:
    """该协议的已知头名集合（来自中枢的 headers 桶 ⇒ RFC 源抽的）。"""
    views = RS.load_fact_views(protocol)
    if not views:
        return set()
    b = RS.assemble_bundle(views, protocol)
    return {str(h).strip() for h in (b.get("headers") or {})}



# ── 节级路线：标题里的头名 + 节内的规范句（含指代句式）────────────────
#: 标题行：`12.10 CSeq` / `7.3 Header Fields`
RE_SEC_TITLE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(\S.*?)\s*$")
#: 标题里的头名候选（首词形如 `CSeq` / `Content-Length` / `Max-Forwards`）
RE_TITLE_HEADER = re.compile(r"^([A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)$")
#: 「指代 + 必填」句式（RFC 头字段章节的典型写法）
RE_MUST_PRESENT = re.compile(
    r"\b(?:MUST|SHALL|REQUIRED)\b[^.]{0,120}?"
    r"\b(?:be present|must be present|is required|are required|"
    r"be included|include|contain)\b", re.I)
#: 「所有请求」量词（消息级必填）
RE_ALL_REQUESTS = re.compile(
    r"\b(?:all|every|each)\s+(?:RTSP\s+|SIP\s+|HTTP\s+)?"
    r"(?:requests?|messages?|request headers?)\b", re.I)


def sections(text: str) -> list[tuple[str, str]]:
    """按「数字编号标题」切节 ⇒ [(标题, 节正文)]（协议无关）。"""
    lines = text.splitlines()
    out: list[tuple[str, list[str]]] = []
    cur_title, cur_body = None, []
    for ln in lines:
        m = RE_SEC_TITLE.match(ln.strip())
        if m and len(m.group(2)) < 60:
            if cur_title is not None:
                out.append((cur_title, cur_body))
            cur_title, cur_body = m.group(2), []
            continue
        if cur_title is not None:
            cur_body.append(ln)
    if cur_title is not None:
        out.append((cur_title, cur_body))
    return [(ti, "\n".join(b)) for ti, b in out]


def headers_by_section(text: str, known: set[str]) -> dict[str, list[str]]:
    """**节级**必填头：标题里的头名 + 节内的规范性必填句（可指代）。"""
    found: dict[str, list[str]] = {}
    for title, body in sections(text):
        m = RE_TITLE_HEADER.match(title.strip())
        if not m:
            continue
        name = m.group(1)
        if name not in known:
            continue
        if not RE_MUST_PRESENT.search(body):
            continue
        ev = [s.strip()[:150] for s in re.split(r"(?<=[.;])\s+", body)
              if RE_MUST_PRESENT.search(s)]
        # ★ **消息级**收紧：该节必须出现「所有请求/消息」量词
        #   （RFC 的头字段章节里，无条件必填的头都这么写；条件性的头不会）
        #   ⇒ 这一条同时过滤掉「响应头」「条件必填」的误报。
        if not RE_ALL_REQUESTS.search(body):
            continue
        if ev:
            found[name] = ev
    return found


def main() -> None:
    report: dict = {}
    for protocol in ("rtsp", "sip", "smtp"):
        known = known_headers(protocol)
        text = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")))
        # 句子级切分（句末标点）
        sents = re.split(r"(?<=[.;])\s+", text)
        found: dict[str, list[str]] = {}
        for s in sents:
            if not re.search(_NORM, s):
                continue
            names = set()
            for rx in (RE_A, RE_C):
                names |= {m.group(1) for m in rx.finditer(s)}
            names |= {m.group(1) for m in RE_B.finditer(s)}
            for n in names:
                if n in known:
                    found.setdefault(n, []).append(s.strip()[:150])

        # ★ 节级路线（确定性、协议无关）：标题里的头名 + 节内规范句
        sec_found = headers_by_section(text, known)
        for n, ev in sec_found.items():
            found.setdefault(n, []).extend(ev)

        # 骨架版（对照）
        prof = json.loads(
            paths.target_profile(protocol).read_text(encoding="utf-8"))
        skel = ((prof.get("seedgen") or {}).get("required_headers") or {})
        skel_heads = {h for hs in skel.values() for h in hs}

        print("=" * 80)
        print(f"{protocol}：RFC 源确定性抽到的必填头 {len(found)} 个 | "
              f"骨架版 {len(skel_heads)} 个")
        print(f"  已知头集合大小: {len(known)}")
        if found:
            print("  ★ RFC 源抽到:")
            for n, ev in sorted(found.items()):
                print(f"     {n:<22} (证据 {len(ev)} 句) 例: {ev[0][:88]}")
        if skel_heads:
            print(f"  骨架版头: {sorted(skel_heads)}")
        cov = len(set(found) & skel_heads) / len(skel_heads) if skel_heads else 0.0
        print(f"  ⇒ 覆盖率 {len(set(found) & skel_heads)}/{len(skel_heads)}"
              f" = {cov:.1%} | RFC 源独有 {sorted(set(found) - skel_heads)}")
        report[protocol] = {
            "known_headers": len(known),
            "found": {k: len(v) for k, v in sorted(found.items())},
            "skeleton_headers": sorted(skel_heads),
            "coverage": round(cov, 4),
            "rfc_only": sorted(set(found) - skel_heads),
            "skeleton_only": sorted(skel_heads - set(found)),
        }
        print()
    p = Path(__file__).resolve().parent / "_pilot_required_headers.json"
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已写入 {p}")


if __name__ == "__main__":
    main()
