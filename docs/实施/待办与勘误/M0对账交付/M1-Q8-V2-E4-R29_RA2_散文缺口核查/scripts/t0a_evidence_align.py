# -*- coding: utf-8 -*-
"""T0-A 第二阶段：为已抽取命题回填原文 quote 并确定性定位（不改命题）。"""
from __future__ import annotations
import json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from core.fused.extraction.prose_semantics import locate_quote  # noqa: E402
import t0a_adapter as AC                                        # noqa: E402

STAGE2_PROMPT_VERSION = "evidence-align-v1"
PROMPT = """你是 RFC 原文校对员。下面给出 RFC 全文（含行号）和一组已抽取的命题。
任务：为每个命题找出**支持它的原文句子**，逐字复制为 evidence_quote。

要求：
1. quote 必须是上面原文中**逐字出现**的英文句子，可跨行；不要翻译、不要改写、不要拼接不相邻的句子。
2. 若原文没有能支持该命题的句子，返回 status="not_found"，不要编造。
3. 若一个命题需要多处原文才能支持，返回 status="multi_source"，不要强拼。
4. 行号只作参考，可以忽略；判断依据是原文内容。
5. 只输出 JSON。

格式：
{"items":[{"id":"<命题 id>","status":"ok|not_found|multi_source","evidence_quote":"<逐字原文>"}]}
"""


def numbered(text: str) -> str:
    return "\n".join(f"{i:4d}| {ln}" for i, ln in enumerate(text.split("\n"), 1))


def align(items: list[dict], text: str, client, batch: int = 8) -> list[dict]:
    """items: [{id, proposition, model_span}]；返回每条的定位结果。"""
    out = []
    for i in range(0, len(items), batch):
        part = items[i:i + batch]
        body = "\n".join(f"- id={x['id']} | 建议行号={x.get('model_span')} | 命题：{x['proposition']}"
                         for x in part)
        user = f"{PROMPT}\n\n===== RFC 原文 =====\n{numbered(text)}\n\n===== 命题 =====\n{body}"
        payload = AC.build_payload("你是 RFC 原文校对员。只输出 JSON。", user)
        AC.assert_payload_ok(payload)
        data = client.chat_json_for(system="你是 RFC 原文校对员。只输出 JSON。",
                                    user=user, temperature=0.1,
                                    max_tokens=AC.MAX_TOKENS)
        got = {str(x.get("id")): x for x in (data.get("items") or [])}
        for x in part:
            r = got.get(str(x["id"]), {})
            q = str(r.get("evidence_quote") or "").strip()
            st = str(r.get("status") or "missing")
            if st != "ok" or not q:
                out.append({**x, "status": st if st != "ok" else "missing",
                            "quote": q, "verified_span": None, "match": "not_attempted"})
                continue
            s, e, m = locate_quote(text.split("\n"), q)
            out.append({**x, "status": "ok", "quote": q,
                        "verified_span": [s, e] if s else None, "match": m})
    return out
