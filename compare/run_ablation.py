# -*- coding: utf-8 -*-
"""compare/run_ablation.py —— B/C 路知识表示消融统一入口。

用法:
    python compare/run_ablation.py --mode shallow_kb            # B 路：浅层知识库
    python compare/run_ablation.py --mode vector_rag            # C 路：向量 RAG
    python compare/run_ablation.py --mode shallow_kb --no-llm   # Stub 空跑（测流程）

A 路（ProtoRAG 可溯源知识表示）沿用 scripts/run_seedgen_e2e.py，不在本脚本内。

三路保证可比：同一份五源知识（kb/ + derived/per_source）、同一个 DeepSeek、
同一份 LLM 参数（compare/config.py）、同一个 .raw 落盘逻辑。唯一变量 = 知识表示层。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from compare.config import (  # noqa: E402
    MODES, MODE_SHALLOW, MODE_VECTOR_RAG,
    PROTOCOL, N_SEEDS, LLM_TEMPERATURE, LLM_MAX_TOKENS,
    FACTS_ROOT, KB_ROOT, out_dir,
)
from compare.shallow_kb import ShallowKB  # noqa: E402
from compare.vector_rag import VectorRAG  # noqa: E402
from core.llm import DeepSeekClient, StubLLMClient  # noqa: E402
from core.fused.downstream.rag_seedgen import (  # noqa: E402
    parse_seed_response, write_seeds,
)
from scripts.run_seedgen_e2e import load_resources, load_request_templates  # noqa: E402


def build_rep(mode: str, protocol: str, resources, request_templates):
    if mode == MODE_SHALLOW:
        return ShallowKB(protocol, FACTS_ROOT, resources, request_templates)
    if mode == MODE_VECTOR_RAG:
        return VectorRAG(protocol, KB_ROOT, resources, request_templates)
    raise ValueError(f"未知 mode: {mode}（可选 {MODES}）")


def main() -> int:
    ap = argparse.ArgumentParser(description="B/C 路知识表示消融统一入口")
    ap.add_argument("--mode", required=True, choices=MODES,
                    help="shallow_kb(B) / vector_rag(C)")
    ap.add_argument("--protocol", default=PROTOCOL)
    ap.add_argument("--n-seeds", type=int, default=N_SEEDS)
    ap.add_argument("--out", default=None,
                    help="输出目录（默认 compare/out/<mode>/<protocol>/<时间戳>/）")
    ap.add_argument("--no-llm", action="store_true",
                    help="用 StubLLM 空跑，只测流程不调真实 LLM")
    args = ap.parse_args()

    resources = load_resources(args.protocol)
    request_templates = load_request_templates(args.protocol)
    print(f"[0] 资源清单 {len(resources)} 流名 / 请求模板 {'有' if request_templates else '无'}")

    rep = build_rep(args.mode, args.protocol, resources, request_templates)
    print(f"[1] 知识表示: {rep.name}")
    rep.prepare()
    n_chunks = len(getattr(rep, "chunks", []))
    print(f"[2] 表示构建完成（chunks={n_chunks}）")

    task = {
        "protocol": args.protocol,
        "n_seeds": args.n_seeds,
        "resources": resources,
        "request_templates": request_templates,
    }
    system, user = rep.render_prompt(task)
    print(f"[3] prompt 渲染完成（system {len(system)} 字 / user {len(user)} 字）")

    if args.no_llm:
        llm = StubLLMClient({"seeds": []})
    else:
        llm = DeepSeekClient()
    resp = llm.chat_json(system=system, user=user,
                         temperature=LLM_TEMPERATURE, max_tokens=LLM_MAX_TOKENS)
    seeds = parse_seed_response(resp, args.protocol, [], [])
    print(f"[4] 生成 {len(seeds)} 条种子")

    out = Path(args.out) if args.out else out_dir(args.mode, args.protocol)
    written = write_seeds(seeds, out)
    print(f"[5] 落盘 {len(written)} 个 .raw 到 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
