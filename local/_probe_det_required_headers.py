# -*- coding: utf-8 -*-
"""验证「消息级必填头」的确定性判据（v2：章节窗口截断，避免跨章节污染）。

A) 枚举式：`MUST ... contain the following header fields: X, Y, Z`（SIP §8.1.1）
B) 逐头式：头定义章节内 `<Head> ... MUST be present in all requests`（RTSP §12.17）

★ v1 的缺陷：逐头式窗口 `lines[i+1:i+26]` 会跨到下一个头的章节 ⇒
  Content-Length / Content-Language 等被「借」了 CSeq 的 MUST 句 ⇒ 假阳性。
  修正：窗口在**下一个章节标题**处截断。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

from core.fused.rfc_extractor import _rfc_source_headers, _load_rfc_config  # noqa: E402

ENUM_RE = re.compile(
    r"MUST[^.]{0,80}?contain\s+the\s+following\s+header\s+fields?\s*:\s*([^.;]{3,400})",
    re.IGNORECASE | re.DOTALL)
PERHEAD_RE = re.compile(
    r"MUST\s+be\s+present\s+in\s+all\s+(?:SIP\s+)?requests?", re.IGNORECASE)
HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\s+(\S[A-Za-z0-9-]*)\s*$")


def deterministic(protocol: str) -> dict:
    cfg = _load_rfc_config(protocol)
    known = _rfc_source_headers(protocol, cfg)
    lines = []
    for f in sorted((Path("kb") / protocol / "spec").glob("*.txt")):
        lines.extend(f.read_text(encoding="utf-8", errors="ignore").splitlines())
    full = "\n".join(lines)

    hits: dict[str, str] = {}
    # A) 枚举式
    for m in ENUM_RE.finditer(full):
        frag = m.group(1)
        for name in known:
            if re.search(r"\b" + re.escape(name) + r"\b", frag):
                hits.setdefault(name, "枚举式: " + " ".join(frag.split())[:150])
    # B) 逐头式（窗口在下一个章节标题处截断）
    for i, ln in enumerate(lines):
        m = HEADING_RE.match(ln.strip())
        if not m or m.group(1) not in known:
            continue
        name = m.group(1)
        body = []
        for j in range(i + 1, min(i + 40, len(lines))):
            if HEADING_RE.match(lines[j].strip()):
                break
            body.append(lines[j])
        blob = "\n".join(body)
        if PERHEAD_RE.search(blob):
            mm = PERHEAD_RE.search(blob)
            s = max(0, mm.start() - 120)
            hits.setdefault(name, "逐头式: " + " ".join(blob[s:mm.end() + 40].split())[:150])
    return {"known": sorted(known), "hits": hits}


for p in ["rtsp", "sip", "smtp"]:
    r = deterministic(p)
    print(f"\n=== {p} ===")
    print(f"确定性必填 ({len(r['hits'])}): {sorted(r['hits'])}")
    for k, v in sorted(r["hits"].items()):
        print(f"   [{k}] {v}")
