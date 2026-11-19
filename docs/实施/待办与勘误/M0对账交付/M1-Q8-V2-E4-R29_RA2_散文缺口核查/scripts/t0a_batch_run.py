# -*- coding: utf-8 -*-
"""按批跑散文抽取：每批独立落 result/guard/原始响应哈希（原子写）。"""
from __future__ import annotations
import json, os, pathlib, sys, time, hashlib

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from core.fused.extraction import prose_semantics as PS
import t0a_adapter as AC


def _w(p: pathlib.Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_suffix(p.suffix + ".tmp")
    t.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    t.replace(p)


def run_batch(protocol: str, doc: str, start: int, end: int, out: pathlib.Path,
              client, batch: int) -> dict:
    src = ROOT / "kb" / protocol / "spec" / doc
    text = src.read_text(encoding="utf-8", errors="replace")
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    L = text.split("\n")
    blocks = [{"doc": doc, "start": start, "text": "\n".join(L[start - 1:end]), "src_sha256": sha}]
    PS._MAX_TOKENS = 8000
    os.environ["PROSE_NO_RETRY"] = "1"
    os.environ["PROSE_BATCH_BLOCKS"] = str(batch)
    PS._cache_path = lambda p: out / "cache" / f"{p}.prose.json"

    t0 = time.strftime("%Y-%m-%dT%H:%M:%S")
    res = {"protocol": protocol, "doc": doc, "block_range": [start, end],
           "batch": batch, "prompt_version": PS.PROSE_SEMANTICS_PROMPT_VERSION,
           "prompt_sha256": hashlib.sha256(PS._PROMPT.encode()).hexdigest(),
           "model": AC.MODEL, "max_tokens": AC.MAX_TOKENS, "started_at": t0}
    try:
        ns, st = PS._extract_blocks(protocol, blocks, llm=client)
        res.update(status="completed", norms=len(ns),
                   usage={"in": st.get("input_tokens"), "out": st.get("output_tokens")},
                   failures=st.get("failures"), finish_reason="stop")
        (out / "norms").mkdir(parents=True, exist_ok=True)
        _w(out / "norms" / f"b{start}-{end}.json", ns)
    except AC.FinishReasonError as exc:
        res.update(status="response_truncated", error=str(exc), finish_reason="length")
    except Exception as exc:                      # noqa: BLE001
        res.update(status="request_failed", error=f"{type(exc).__name__}: {exc}",
                   usage={"in": None, "out": None})
    res["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _w(out / "evidence" / f"b{start}-{end}.json", res)
    return res


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", required=True); ap.add_argument("--doc", required=True)
    ap.add_argument("--start", type=int, required=True); ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--batch", type=int, default=2)
    a = ap.parse_args()
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("no key", file=sys.stderr); raise SystemExit(2)
    r = run_batch(a.protocol, a.doc, a.start, a.end, pathlib.Path(a.out),
                  AC.T0AClient(key), a.batch)
    print(json.dumps({k: r.get(k) for k in ("status", "norms", "usage", "finish_reason")},
                     ensure_ascii=False))
    raise SystemExit(0 if r["status"] == "completed" else 1)
