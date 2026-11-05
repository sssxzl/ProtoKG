"""探测 `_rfc_source_methods` 修复对状态机质量闸与转移集的实际影响。

只读：不改任何产物文件。用于决定是否需要重建抽取产物。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.fused import rfc_extractor as RX  # noqa: E402



def _raw_cached(protocol: str) -> list[dict]:
    from core.fused.source_retrieval import CACHE_DIR
    f = CACHE_DIR / f"{protocol}.transitions.json"
    if not f.exists():
        return []
    d = json.loads(f.read_text(encoding="utf-8"))
    return [r for r in (d.get("transitions") or []) if isinstance(r, dict)]


for proto in ("rtsp", "sip", "smtp"):
    cfg = RX._load_rfc_config(proto)
    methods = RX._rfc_source_methods(proto, cfg)
    raw = _raw_cached(proto)
    gated = RX._apply_transition_gate(raw, proto)
    print(f"\n=== {proto} ===")
    print(f"  method_sections = {cfg.get('method_sections')}")
    print(f"  RFC 源方法集 ({len(methods)}): {sorted(methods)}")
    print(f"  缓存原始转移 = {len(raw)}；过闸后 = {len(gated)}")
    if raw:
        kept = {(r.get('from'), r.get('method'), r.get('to')) for r in gated}
        drop = [r for r in raw if (r.get('from'), r.get('method'), r.get('to')) not in kept]
        print(f"  被闸掉 = {len(drop)}")
        for r in drop[:8]:
            print(f"    - {r.get('from')} --{r.get('method')}--> {r.get('to')}")
