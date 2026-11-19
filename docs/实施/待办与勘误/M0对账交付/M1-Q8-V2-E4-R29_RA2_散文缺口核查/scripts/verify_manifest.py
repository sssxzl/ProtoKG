# -*- coding: utf-8 -*-
"""校验交付清单：逐个重算哈希；再核对清单自哈希侧车文件。

清单本身与侧车文件都不进入 outputs（避免循环引用）。
"""
from __future__ import annotations
import hashlib, json, pathlib, sys

BASE = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = BASE / "R29_RA2_F2_输入输出SHA256清单.json"
SIDECAR = BASE / "R29_RA2_F2_清单自哈希.sha256"


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    if not MANIFEST.is_file():
        print("manifest missing"); return 2
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bad, checked = [], 0
    for name, meta in (data.get("outputs") or {}).items():
        p = BASE / name
        if not p.is_file():
            bad.append((name, "missing")); continue
        checked += 1
        if sha(p) != meta.get("sha256"):
            bad.append((name, "digest_mismatch"))
    side_ok = False
    if SIDECAR.is_file():
        first = SIDECAR.read_text(encoding="utf-8").split()[0]
        side_ok = (first == sha(MANIFEST))
    print(f"checked={checked} mismatches={len(bad)} sidecar_ok={side_ok}")
    for n, why in bad[:5]:
        print("  ", why, n)
    return 0 if (not bad and side_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
