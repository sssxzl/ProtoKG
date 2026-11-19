# -*- coding: utf-8 -*-
"""T0-A 预检：生成 t0a_evidence.json（零 LLM 调用，可复算）。

产出内容：
  · 六块的起止行 / 字符 / 文本哈希 / 块指纹 / 来源 SHA256
  · 两条 Gold（-30-1、-30-2）的原文与块归属
  · 全文重建一致性（len("\\n".join(blocks)) == len(text)）
  · 完整请求的离线 Token 计数（tiktoken cl100k_base，非供应商 tokenizer，注明近似）
  · 两批调用计划（5 + 1）
用法：python t0a_preflight.py [--out t0a_evidence.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

_CWD = pathlib.Path.cwd()
ROOT = _CWD if (_CWD / "kb").is_dir() else pathlib.Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT))

from core.fused.extraction import prose_semantics as PS  # noqa: E402

DOC = "rfc3207.txt"
PROTO = "smtp"
GOLDS = [("GK-B-smtp-rfc3207.txt-30-1", 30, 33),
         ("GK-B-smtp-rfc3207.txt-30-2", 33, 35)]
SYSTEM_MSG = "你是协议规范分析员。只输出 JSON。"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def count_tokens(text: str) -> int | None:
    """tiktoken cl100k_base 计数；不可用时返回 None（调用方标 unavailable）。"""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:            # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="t0a_evidence.json")
    args = ap.parse_args()

    f = ROOT / "kb" / PROTO / "spec" / DOC
    raw = f.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\n")

    max_blocks = (len(text) // PS._MAX_BLOCK_CHARS) + 1
    blocks = PS._split_blocks(text, max_blocks)
    recon = "\n".join(b for _, b in blocks)

    out = {
        "doc": DOC, "protocol": PROTO,
        "bytes": len(raw), "src_sha256": sha(raw),
        "chars": len(text), "lines": len(lines),
        "max_block_chars": PS._MAX_BLOCK_CHARS,
        "block_count": len(blocks),
        "recon_chars": len(recon),
        "recon_identical": recon == text,
        "blocks": [],
        "gold": [],
        "prompt": {},
        "batches": [],
    }

    for st, bt in blocks:
        out["blocks"].append({
            "start": st, "end": st + bt.count("\n"), "chars": len(bt),
            "text_sha256": sha(bt.encode("utf-8")),
            "sig": PS._block_signature([{"doc": DOC, "start": st, "text": bt,
                                         "src_sha256": out["src_sha256"]}])[:16],
        })

    for gid, lo, hi in GOLDS:
        cov = [b for b in out["blocks"] if b["start"] <= lo <= b["end"]]
        out["gold"].append({
            "gold_id": gid, "span": f"{lo}-{hi}",
            "text": " ".join(lines[lo - 1:hi])[:200],
            "block_start": cov[0]["start"] if cov else None,
            "block_end": cov[0]["end"] if cov else None,
            "covered": bool(cov),
        })

    hdr = len("\n\n===== [文档 rfc3207.txt]（起始行号 9999）=====\n")
    out["prompt"] = {"system_chars": len(SYSTEM_MSG),
                     "user_prompt_chars": len(PS._PROMPT),
                     "block_header_chars": hdr}

    # 两批：5 + 1
    idx = list(range(len(blocks)))
    for name, part in (("batch1", idx[:5]), ("batch2", idx[5:])):
        body = "".join(
            f"\n\n===== [文档 {DOC}]（起始行号 {blocks[i][0]}）=====\n{blocks[i][1]}"
            for i in part)
        user = PS._PROMPT + body
        n = count_tokens(SYSTEM_MSG + user)
        out["batches"].append({
            "name": name, "blocks": [blocks[i][0] for i in part],
            "block_chars": sum(len(blocks[i][1]) for i in part),
            "request_chars": len(SYSTEM_MSG) + len(user),
            "tokens": n,
            "token_method": "tiktoken/cl100k_base（近似，非供应商 tokenizer）" if n else "unavailable",
        })

    tot = [b["tokens"] for b in out["batches"]]
    out["token_total"] = sum(t for t in tot if t) if all(tot) else None
    out["token_threshold"] = 7500
    out["threshold_ok"] = (out["token_total"] is not None
                           and out["token_total"] <= out["token_threshold"])

    dst = pathlib.Path(args.out)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written {dst} | blocks={out['block_count']} "
          f"recon_identical={out['recon_identical']} "
          f"gold_covered={sum(1 for g in out['gold'] if g['covered'])}/2 "
          f"tokens={out['token_total']} (<= {out['token_threshold']}: {out['threshold_ok']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
