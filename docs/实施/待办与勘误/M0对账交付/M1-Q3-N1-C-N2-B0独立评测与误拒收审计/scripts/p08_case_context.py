# -*- coding: utf-8 -*-
"""★ N2-B0-R：★ 恢复三条误拒案例的**完整 RFC 规范句 + 必要上下文 + 原始强度字段**。

★ §五 六问所需的事实基础（★ 只读，不调 LLM）。
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTD = ROOT / "guard/_out/n1c"
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"

FR = {}
for b in [json.loads(l) for l in
          (FREEZE / "frozen_blocks.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]:
    for i, it in enumerate(b["raw_items"]):
        FR[f"{b['document']}@{b['chunk_start']}#{i}"] = {**it,
                                                     "protocol": b["protocol"],
                                                     "document": b["document"],
                                                     "chunk_start": b["chunk_start"]}
spans = {json.loads(l)["sample_id"]: json.loads(l) for l in
         (ROOT / "guard/_out/n1r2/n1r2_span_ledger.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()}

CASES = ["rfc2326.txt@2030#5", "rfc5321.txt@5226#1", "rfc5321.txt@5226#2"]
_RE_BCP = re.compile(r"\b(MUST NOT|SHALL NOT|SHOULD NOT|MUST|SHALL|SHOULD|"
                     r"REQUIRED|RECOMMENDED|MAY NOT|MAY|OPTIONAL)\b")

out = {}
for cid in CASES:
    _o = FR[cid]
    _sp = spans[cid]
    _p = ROOT / f"kb/{_o['protocol']}/spec/{_o['document']}"
    _L = _p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    _rs = _sp["resolved_span"]
    _ctx = [{"line": i, "text": _L[i - 1]}
            for i in range(max(1, _rs - 12), min(len(_L), _rs + 12) + 1)]
    # ★ 窗口内所有含 BCP14 词的非空行（★ 用于「must 实际约束哪个主体/行为」）
    _bcp = [{"line": c["line"], "text": c["text"].strip(),
             "★ BCP14 词": _RE_BCP.findall(c["text"])}
            for c in _ctx if _RE_BCP.search(c["text"])]
    out[cid] = {
        "★ 协议/文档": f"{_o['protocol']}/{_o['document']}",
        "★ chunk": f"{_o['document']}@{_o['chunk_start']}",
        "★ raw_span / resolved_span / span_mode":
            f"{_sp['raw_span']} / {_rs} / {_sp['span_mode']}",
        "★ 锚点行原文": _L[_rs - 1],
        "★ 原始候选字段": {k: _o.get(k) for k in
                       ("entity", "normative_subject", "action", "object",
                        "strength", "meaning", "constraint")},
        "★ 原始 meaning（生成文本）": _o.get("meaning"),
        "★ 原始 constraint（生成文本）": _o.get("constraint"),
        "★ 上下文（锚点 ±12 行）": _ctx,
        "★ 窗口内含 BCP14 词的行": _bcp,
    }
    print(f"  ★★ {cid}")
    print(f"      strength={_o.get('strength')!r}｜action={_o.get('action')!r}"
          f"｜object={_o.get('object')!r}")
    print(f"      constraint（生成）={str(_o.get('constraint'))[:110]!r}")
    print(f"      锚点行 {_rs}: {_L[_rs-1].strip()[:100]!r}")
    print(f"      ★ 窗口内 BCP14 行：")
    for c in _bcp:
        print(f"          {c['line']}: {c['text'][:92]!r}  {c['★ BCP14 词']}")
    print()

(OUTD / "n2b0r_three_cases_context.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"  ⇒ {OUTD/'n2b0r_three_cases_context.json'}")
