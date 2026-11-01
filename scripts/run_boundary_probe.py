# -*- coding: utf-8 -*-
"""scripts/run_boundary_probe.py —— 边界探针端到端跑通（有漏洞库，源 B）。

流程：
  读漏洞 → classify → derive_boundary_param → generate_candidates
  → 序列化 .raw → scp 到虚拟机 → oracle 判定(重放检测崩溃)
  → probe_boundary 定位合法边界 → 输出合法边界种子。

★协议耦合说明（2026-10-21）：本脚本是【RTSP 专用】运行时辅助脚本——VM 地址/SSH 密钥、
端口 8560、触发 Session 值 000022B8、load_vuln_kb(protocol="rtsp") 都是 RTSP/live555
实验环境硬编码。换协议（SMTP/FTP）时 oracle 判定脚本与端口需改造。正确归宿：VM/端口/
oracle 脚本应配置化；当前仅 RTSP 边界探测实验使用，保持现状但明确边界。

用法:
    python scripts/run_boundary_probe.py [--out derived/seeds/rtsp_boundary]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fused.downstream.strategy import load_vuln_kb, classify_all, dedupe_reqs  # noqa: E402
from core.fused.downstream.boundary_probe import (  # noqa: E402
    derive_boundary_param, generate_candidates, derive_semantic_candidates,
    probe_boundary, emit_boundary_fact,
)
from core.fused.downstream.rag_seedgen import load_fact_views, assemble_bundle  # noqa: E402
from core.raw_writers import seedcorpus_to_raw  # noqa: E402
from core import paths  # noqa: E402

VM = "zxy@192.168.37.130"
SSH = ["ssh", "-i", str(Path.home() / ".ssh/vm_ubuntu_zxy"),
       "-o", "StrictHostKeyChecking=no", VM]
VM_TMP = "/tmp/boundary_candidates"
PORT = 8560


def oracle(vm_path: str, retries: int = 3) -> bool:
    """判定 VM 上的 .raw 是否合法（不崩溃）。True=合法，False=非法。"""
    r = subprocess.run(
        SSH + [f"python3 /tmp/oracle.py {vm_path} {PORT} {retries}"],
        capture_output=True, text=True, timeout=90)
    return r.stdout.strip() == "LEGAL"


def batch_oracle(vm_dir: str, retries: int = 3) -> dict[int, bool]:
    """批量判定 VM 上某个目录的所有 cand_*.raw，一次 ssh 返回 {idx: bool(合法)}。"""
    r = subprocess.run(
        SSH + [f"python3 /tmp/batch_oracle.py {vm_dir} {PORT} {retries}"],
        capture_output=True, text=True, timeout=600)
    out: dict[int, bool] = {}
    for line in r.stdout.strip().splitlines():
        if "\t" not in line:
            continue
        idx, verdict = line.split("\t")
        out[int(idx)] = (verdict.strip() == "LEGAL")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "derived/seeds/rtsp_boundary"))
    ap.add_argument("--semantic", action="store_true",
                    help="源 A：协议语义驱动边界（无需漏洞库，从状态机自环推导）")
    args = ap.parse_args()

    # 1. 生成边界候选（本地）
    candidates: list = []  # (req_or_None, param_or_None, label, seed)
    if args.semantic:
        bundle = assemble_bundle(load_fact_views())
        for label, seed in derive_semantic_candidates(bundle):
            candidates.append((None, None, label, seed))
        print(f"源 A（协议语义）边界候选: {len(candidates)} 个（无需漏洞库）")
    else:
        vulns = load_vuln_kb(protocol="rtsp")
        reqs = dedupe_reqs(classify_all(vulns))
        print(f"历史漏洞 {len(vulns)} 条 → 去重 {len(reqs)} 个漏洞模式")
        for req in reqs:
            param = derive_boundary_param(req)
            if param is None:
                continue
            for label, seed in generate_candidates(req):
                candidates.append((req, param, label, seed))
        print(f"源 B（漏洞知识）边界候选: {len(candidates)} 个")

    # 2. 序列化 + scp 到虚拟机（用 forward slash 路径，避免 Windows 路径传给 scp 出错）
    local_tmp = ROOT / "derived/seeds/bp_candidates"
    local_tmp.mkdir(parents=True, exist_ok=True)
    for f in local_tmp.glob("*.raw"):
        f.unlink()
    subprocess.run(SSH + [f"rm -rf {VM_TMP}; mkdir -p {VM_TMP}"], check=True)
    for i, (req, param, label, seed) in enumerate(candidates):
        raw = seedcorpus_to_raw(seed)
        (local_tmp / f"cand_{i}.raw").write_bytes(raw)
    key = str(Path.home() / ".ssh/vm_ubuntu_zxy").replace("\\", "/")
    for p in sorted(local_tmp.glob("*.raw")):
        rel = str(p).replace("\\", "/")
        subprocess.run(["scp", "-i", key, "-o", "StrictHostKeyChecking=no", "-q",
                        rel, f"{VM}:{VM_TMP}/"], check=True)

    # 3. 批量 oracle 判定 + 4. 定位合法边界（一次 ssh 判定全部候选）
    print("\n=== oracle 判定（合法=不崩 / 非法=崩）===")
    verdict_map = batch_oracle(VM_TMP)
    boundary_seeds: list = []
    verdicts: list = []  # (req, param, label, seed, ok)
    for i, (req, param, label, seed) in enumerate(candidates):
        ok = verdict_map.get(i, False)
        verdict = "LEGAL" if ok else "ILLEGAL"
        mark = "✅边界" if (ok and label == "legal") else ("⚠️越界" if (not ok and label == "illegal") else "")
        src = (req.action if req else param.dim if param else seed.description.split()[1])
        print(f"  [{src}] {label:8} → {verdict:8} {mark}  {seed.description}")
        verdicts.append((req, param, label, seed, ok))
        if ok and label == "legal":
            boundary_seeds.append(seed)

    print(f"\n定位到合法边界种子: {len(boundary_seeds)} 个")

    # 4.5 回写知识中枢：对「legal=合法 且 illegal=越界」的边界对，生成 legal_boundary fact
    facts: list = []
    facts_written = 0
    for j in range(0, len(verdicts) - 1, 2):
        (req_a, param_a, lab_a, seed_a, ok_a) = verdicts[j]
        (req_b, param_b, lab_b, seed_b, ok_b) = verdicts[j + 1]
        if lab_a != "legal" or lab_b != "illegal":
            continue
        if not (ok_a and not ok_b):  # 需 legal 合法 + illegal 越界 才算识别出边界
            continue
        method = next((m for m in seed_b.target_methods if m != "DESCRIBE"), "SETUP")
        if param_b is not None:  # 源 B
            dim, legal_d, illegal_d = param_b.dim, param_b.legal_desc, param_b.illegal_desc
        else:  # 源 A
            dim = "self-loop"
            legal_d, illegal_d = "single occurrence", "repeat occurrence"
        fact = emit_boundary_fact(method, dim, legal_d, illegal_d, trigger="Session=000022B8")
        facts.append(fact)
        facts_written += 1

    if facts_written:
        # 回写知识中枢：oracle 验证的 legal_boundary fact，带 protocol 维度写入
        # per_source/<protocol>/boundary_probe/facts/（供 load_fact_views/assemble_bundle
        # 消费）。覆盖写（每次探测得到完整边界集合，避免追加累积重复）。
        # 注意：boundary_probe 目录不在五源内，build_hub 的 _clean_per_source 只清五源，
        # 不会误清这里的运行时富化回写。
        bf_dir = paths.per_source_facts_dir("rtsp", "boundary_probe")
        bf_dir.mkdir(parents=True, exist_ok=True)
        bf_path = bf_dir / "boundary_probe.jsonl"
        with open(bf_path, "w", encoding="utf-8") as f:
            for fact in facts:
                f.write(json.dumps(fact, ensure_ascii=False) + "\n")
        print(f"回写知识中枢: {facts_written} 条 legal_boundary fact → {bf_path}")

    # 5. 落盘
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.raw"):
        f.unlink()
    written = []
    for i, seed in enumerate(boundary_seeds, start=1):
        safe = (seed.description
                .replace('boundary-candidate ', '').replace('semantic-boundary ', '')
                .replace(' ', '_').replace('(', '').replace(')', '')
                .replace('->', '_').replace('>', '').replace('<', ''))
        name = f"{i:02d}_{safe}.raw"
        (out / name).write_bytes(seedcorpus_to_raw(seed))
        written.append(name)
    print(f"落盘 {len(written)} 个合法边界种子到 {out}")
    for name in written[:5]:
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
