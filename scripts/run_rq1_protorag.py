#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RQ1 测量：ProtoRAG 种子构造（build_hub + seedgen），统计 Time / Tokens / 种子数。

用法:
    E:/python/python.exe scripts/run_rq1_protorag.py [--seedgen-only]

产出:
    - 重新构建知识中枢（5 源 facts）
    - 生成初始种子（three-layer 三层选择器）
    - 打印: 各阶段 wall-clock 时间、LLM 调用次数、总 input/output tokens、种子数
    - 结果 JSON 落盘 derived/rq1_protorag_metrics.json
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---- 1. monkeypatch DeepSeekClient 以累计 tokens + 调用次数 + LLM 耗时 ----
import core.llm as llm_mod  # noqa: E402

_ACC = {"calls": 0, "in_tokens": 0, "out_tokens": 0, "llm_time_s": 0.0}

_orig_chat_json = llm_mod.DeepSeekClient.chat_json
_orig_chat_text = llm_mod.DeepSeekClient.chat_text


def _patched_chat_json(self, **kw):
    r = _orig_chat_json(self, **kw)
    m = getattr(self, "last_call_meta", {}) or {}
    _ACC["calls"] += 1
    _ACC["in_tokens"] += int(m.get("input_tokens", 0) or 0)
    _ACC["out_tokens"] += int(m.get("output_tokens", 0) or 0)
    _ACC["llm_time_s"] += float(m.get("elapsed_s", 0) or 0)
    return r


def _patched_chat_text(self, **kw):
    r = _orig_chat_text(self, **kw)
    _ACC["calls"] += 1
    return r


llm_mod.DeepSeekClient.chat_json = _patched_chat_json
llm_mod.DeepSeekClient.chat_text = _patched_chat_text


def main() -> int:
    seedgen_only = "--seedgen-only" in sys.argv
    # 从 argv 读 --protocol（默认 rtsp）
    protocol = "rtsp"
    for i, a in enumerate(sys.argv):
        if a == "--protocol" and i + 1 < len(sys.argv):
            protocol = sys.argv[i + 1]
            break

    out_dir = ROOT / "derived" / "model" / "seeds" / protocol / (
        "rq1_" + datetime.now().strftime("%Y%m%d_%H%M%S"))

    stages = {}

    # ---- 2. build_hub（五源抽取） ----
    if not seedgen_only:
        from scripts import build_hub
        t0 = time.time()
        rc = build_hub.main([
            "--sources", "rfc", "expert_note", "traffic", "vuln", "source",
            "--protocol", protocol,
            "--constraints", "--vuln-llm",
        ])
        stages["build_hub_s"] = round(time.time() - t0, 2)
        stages["build_hub_rc"] = rc
        print(f"\n[阶段] build_hub 耗时 {stages['build_hub_s']}s (rc={rc})",
              flush=True)

    # ---- 3. seedgen（三层选择器） ----
    from scripts import run_seedgen_e2e
    t1 = time.time()
    saved_argv = sys.argv
    sys.argv = ["run_seedgen_e2e.py", "--protocol", protocol,
                "--three-layer", "--out", str(out_dir)]
    try:
        rc2 = run_seedgen_e2e.main()
    finally:
        sys.argv = saved_argv
    stages["seedgen_s"] = round(time.time() - t1, 2)
    stages["seedgen_rc"] = rc2
    print(f"\n[阶段] seedgen 耗时 {stages['seedgen_s']}s (rc={rc2})", flush=True)

    # ---- 4. 统计种子数 ----
    n_seeds = len(list(out_dir.glob("*.raw"))) if out_dir.is_dir() else 0
    stages["seed_count"] = n_seeds

    # ---- 5. 汇总 ----
    total_s = stages.get("build_hub_s", 0) + stages["seedgen_s"]
    result = {
        "protocol": protocol,
        "out_dir": str(out_dir),
        "build_hub_s": stages.get("build_hub_s"),
        "seedgen_s": stages["seedgen_s"],
        "total_s": round(total_s, 2),
        "total_min": round(total_s / 60.0, 3),
        "llm_calls": _ACC["calls"],
        "input_tokens": _ACC["in_tokens"],
        "output_tokens": _ACC["out_tokens"],
        "total_tokens": _ACC["in_tokens"] + _ACC["out_tokens"],
        "llm_time_s": round(_ACC["llm_time_s"], 2),
        "seed_count": n_seeds,
    }

    metrics_path = ROOT / "derived" / f"rq1_protorag_metrics_{protocol}.json"
    metrics_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    print("\n" + "=" * 64)
    print("ProtoRAG RQ1 种子构造测量结果")
    print("=" * 64)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"metrics 已落盘: {metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
