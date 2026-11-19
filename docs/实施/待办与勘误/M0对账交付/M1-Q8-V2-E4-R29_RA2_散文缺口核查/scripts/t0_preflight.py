# -*- coding: utf-8 -*-
"""T0 执行前核对：入口、7 块身份、Gold 跨度、缓存保护（0 次真实 LLM）。"""
from __future__ import annotations
import hashlib, json, os, pathlib, sys, tempfile
_cwd = pathlib.Path.cwd()
WT = _cwd if (_cwd / "kb").is_dir() else pathlib.Path(__file__).resolve().parents[6]
sys.path.insert(0, str(WT))
from core.fused.extraction import rfc_extractor as RX          # noqa: E402
from core.fused.extraction import prose_semantics as PS        # noqa: E402

ROOT = WT
DOCS = [("smtp", "rfc3207.txt"), ("smtp", "rfc4954.txt")]
GOLD = [("GK-B-smtp-rfc3207.txt-404-1", "rfc3207.txt", 404, 404),
        ("GK-B-smtp-rfc3207.txt-405-1", "rfc3207.txt", 405, 405),
        ("GK-B-smtp-rfc4954.txt-704-1", "rfc4954.txt", 704, 708)]


def sha_bytes(b): return hashlib.sha256(b).hexdigest()


def main() -> int:
    out = {"profile": {}, "blocks": [], "gold": [], "cache": {}}

    # A1 现状：smtp 未启用散文通道；两份文档均有确定性产出 ⇒ 旧触发条件会跳过
    for p in ("smtp", "rtsp", "dhcpv4"):
        f = ROOT / "profiles" / p / "rfc_config.json"
        cfg = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
        _rfc = cfg.get("rfc")
        out["profile"][p] = bool(_rfc.get("enable_prose_semantics")
                                 if isinstance(_rfc, dict)
                                 else cfg.get("enable_prose_semantics"))
    norm_docs = set()
    for n in RX.extract_rfc_norms("smtp", llm=None):
        s = n.get("source") or ""
        if "#@" in s:
            norm_docs.add(s.split("#@")[0].replace("file:", ""))
    skipped = [d for _, d in DOCS if d in norm_docs]
    out["current_path"] = {
        "prose_enabled_smtp": out["profile"]["smtp"],
        "docs_with_deterministic_output": sorted(norm_docs),
        "would_be_skipped_by_old_trigger": skipped,
    }

    # A2 隔离候选调度：按 F1 判据选出这两份文档的块（每 10k 字符一块）
    for proto, doc in DOCS:
        f = ROOT / "kb" / proto / "spec" / doc
        text = f.read_text(encoding="utf-8", errors="replace")
        src = sha_bytes(f.read_bytes())
        # 必须切满全文：max_blocks 不足会静默截断（本轮实证）
        _need = (len(text) // PS._MAX_BLOCK_CHARS) + 1
        blocks = PS._split_blocks(text, _need)
        out.setdefault("coverage", {})[doc] = {
            "chars": len(text),
            "block_chars": sum(len(b) for _, b in blocks),
            "ratio": round(sum(len(b) for _, b in blocks) / max(1, len(text)), 3),
            "blocks": len(blocks)}
        for start, btext in blocks:
            out["blocks"].append({
                "doc": doc, "start": start, "chars": len(btext),
                "src_sha256": src, "text_sha256": sha_bytes(btext.encode("utf-8")),
                "sig": PS._block_signature([{"doc": doc, "start": start,
                                             "text": btext, "src_sha256": src}])[:16],
            })

    # A3 Gold 跨度与块对应
    for gid, doc, lo, hi in GOLD:
        f = ROOT / "kb" / "smtp" / "spec" / doc
        lines = f.read_text(encoding="utf-8", errors="replace").split("\n")
        cover = [b for b in out["blocks"]
                 if b["doc"] == doc and b["start"] <= lo <= b["start"] + b["chars"]]
        out["gold"].append({"gold_id": gid, "doc": doc, "span": f"{lo}-{hi}",
                            "line_text": (lines[lo - 1].strip()[:80] if lo <= len(lines) else ""),
                            "covered_by_block": bool(cover),
                            "block_start": cover[0]["start"] if cover else None})

    # B 缓存保护：部分块 + 中途终止 ⇒ 不写 complete
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="t0pf_"))
    PS._cache_path = lambda p: tmp / f"{p}.prose.json"  # type: ignore
    os.environ["PROSE_BATCH_BLOCKS"] = "1"

    class Stub:
        model = ""
        def __init__(self): self.calls = 0
        def chat_json(self, *, system, user, temperature, max_tokens):
            self.calls += 1
            if self.calls >= 2:
                from core.fused.extraction.window_candidates import RunGuard
                raise RuntimeError("budget stop")
            return {"items": [{"doc": "a.txt", "entity": "E", "meaning": "m",
                               "span": 1, "action": "MUST"}]}

    blocks = [{"doc": "a.txt", "start": s, "text": f"P{s}", "src_sha256": "S"}
              for s in (1, 9, 17)]
    PS._extract_blocks("pf", blocks, llm=Stub())
    f = PS._doc_cache_file("pf", "a.txt")
    out["cache"]["partial_blocks_not_complete"] = (not f.is_file())
    os.environ.pop("PROSE_BATCH_BLOCKS", None)
    dst = pathlib.Path(os.environ.get("T0_OUT", "t0_preflight.json"))
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"preflight written: {dst} | blocks={len(out['blocks'])} "
          f"gold_covered={sum(1 for g in out['gold'] if g['covered_by_block'])}/3 "
          f"partial_cache_ok={out['cache']['partial_blocks_not_complete']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
