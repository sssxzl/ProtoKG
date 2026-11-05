# -*- coding: utf-8 -*-
"""F 阶段试点（LLM 路线）：RFC 源产「消息级必填头」（真调 LLM，只读）。

★ 为什么必须是 LLM（实测依据）：确定性路线在「必填头」这个**语义**上不可靠 ——
  句子级路线分不清「请求头 / 响应头」「无条件 / 条件必填」；
  节级路线加上「所有请求」量词后覆盖率反而下降且误报仍在
  （实测见 local/_pilot_required_headers.json）。
  ⇒ 必填头需要**读上下文**才能判定 ⇒ 与「结构化约束」那条线同一机制。

★ 本试点测：LLM 从 RFC 原文抽「**所有请求都必须携带**的头」，
  与骨架版逐头对照（覆盖率 / 误报率）⇒ 给出「该不该落地 LLM 通道」的数据。

★ 判据设计（协议无关）：
  · 输出必须是**协议真实头名**（注入已知头名列表约束）
  · 只收**消息级**（所有请求）必填 ⇒ 响应头/条件必填一律排除
  · 每条给出 RFC 证据句 ⇒ 可溯源

用法：E:/app/Anaconda3/python.exe local/_pilot_required_headers_llm.py [协议...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths                                      # noqa: E402
from core.fused import rfc_forms as RF                     # noqa: E402
from core.fused.downstream import rag_seedgen as RS        # noqa: E402
from core.llm import DeepSeekClient                        # noqa: E402

PROMPT = """你是协议规范分析助手。下面是 {protocol} 协议 RFC 规范中的相关章节。

请判断：该协议的**每一个请求报文**都必须携带哪些头部字段？

只输出 JSON：
{{"required_headers": [{{"name": "<头名>", "evidence": "<RFC 原句>"}}]}}

规则：
1. 只收**所有请求都必带**的头（例如消息序号、会话标识、传输参数这类协议级必带项）。
2. ★ **不要**收：
   - 只在**响应**里出现的头（响应码、认证挑战等）；
   - **条件性**必填的头（"仅当……时 MUST"）；
   - 内容协商类可选头（Accept*、Content-Type 等可选项）；
   - 方法专属的头（只对某一个方法必带）。
3. `name` 必须**原样照抄**下面列表里的头名（不要自造、不要改大小写）：
   {allowed}
4. `evidence` 给出 RFC 原句（可截断到 160 字）。
5. 判不出就返回空列表。

{body}
"""


def known_headers(protocol: str) -> set[str]:
    views = RS.load_fact_views(protocol)
    if not views:
        return set()
    b = RS.assemble_bundle(views, protocol)
    return {str(h).strip() for h in (b.get("headers") or {})}


def candidate_blocks(protocol: str) -> list[dict]:
    """候选：头字段章节 + 规范性条款块（形态层切块，协议无关）。"""
    out = []
    for f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        for b in RF.split_form_blocks(lines):
            if b.kind in ("table", "normative"):
                out.append({"kind": b.kind, "text": b.text,
                            "src": f"{f.name}#@{b.line_start}"})
    return out


def main() -> None:
    protocols = sys.argv[1:] or ["rtsp", "sip"]
    llm = DeepSeekClient()
    report: dict = {}
    for protocol in protocols:
        known = known_headers(protocol)
        prof = json.loads(
            paths.target_profile(protocol).read_text(encoding="utf-8"))
        skel = ((prof.get("seedgen") or {}).get("required_headers") or {})
        skel_heads = {h for hs in skel.values() for h in hs}
        blocks = candidate_blocks(protocol)
        found: dict[str, list[str]] = {}
        for b in blocks:
            allowed = ", ".join(sorted(known))
            try:
                r = llm.chat_json(
                    system="你输出 JSON。",
                    user=PROMPT.format(protocol=protocol.upper(),
                                        allowed=allowed,
                                        body=b["text"][:7000]),
                    temperature=0.0, max_tokens=2000)
            except Exception as exc:  # noqa: BLE001
                print(f"    [LLM 失败] {exc}", file=sys.stderr)
                continue
            if not isinstance(r, dict):
                continue
            for it in (r.get("required_headers") or []):
                if not isinstance(it, dict):
                    continue
                n = str(it.get("name", "")).strip()
                if n and n in known:
                    found.setdefault(n, []).append(
                        str(it.get("evidence", ""))[:160])
        cov = len(set(found) & skel_heads) / len(skel_heads) if skel_heads else 0.0
        extra = sorted(set(found) - skel_heads)
        print("=" * 80)
        print(f"{protocol}：候选块 {len(blocks)} ⇒ LLM 抽出必填头 {len(found)} 个")
        print(f"  骨架版 {len(skel_heads)} 个：{sorted(skel_heads)}")
        print(f"  ★ 覆盖率 {len(set(found) & skel_heads)}/{len(skel_heads)} = {cov:.1%}")
        print(f"  RFC 源独有（待人工核）: {extra}")
        for n in sorted(found):
            ev = found[n][0].replace(chr(10), " ")[:110]
            print(f"    {n:<20} ← {ev}")
        report[protocol] = {
            "skeleton_headers": sorted(skel_heads),
            "found": {k: v[:2] for k, v in sorted(found.items())},
            "coverage": round(cov, 4),
            "rfc_only": extra,
        }
        print()
    p = Path(__file__).resolve().parent / "_pilot_required_headers_llm.json"
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已写入 {p}")


if __name__ == "__main__":
    main()
