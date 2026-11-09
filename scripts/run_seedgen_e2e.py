# -*- coding: utf-8 -*-
"""真 LLM 端到端验证：知识中枢 → RAG → DeepSeek → 初始种子 → .raw 落盘。

支持目标资源清单（实例级知识）：从 fused_hub/targets/<protocol>_streams.json
读流名清单，让 LLM 生成的每个种子用不同流名，覆盖所有媒体格式。

支持漏洞导向（P0）：从 kb/历史漏洞/*.json 读结构化 trigger，经 classify_vuln
翻译成「合法边界种子」需求，走攻击种子路生成针对性边界种子（绝对合法，
仅覆盖漏洞相关字段/序列/边界）。

用法:
    python scripts/run_seedgen_e2e.py [--protocol rtsp] [--no-react] [--attack]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fused.downstream.rag_seedgen import (  # noqa: E402
    load_fact_views, assemble_bundle, generate_seeds, generate_seeds_react, write_seeds,
)
from core.fused.downstream.strategy import (  # noqa: E402
    load_vuln_kb, classify_all, classify_vuln, dedupe_reqs, determine_strategies,
    generate_attack_seeds,
)
from core.fused.vuln_pattern import crash_streams  # noqa: E402
from core.fused.downstream.selector import select_seeds  # noqa: E402
from core.llm import DeepSeekClient  # noqa: E402

TARGETS_DIR = ROOT / "fused_hub" / "targets"


def load_resources(protocol: str) -> list[dict]:
    """读目标资源清单（实例级知识，如 RTSP 流名）。

    过滤掉会导致目标服务器崩溃的流（按协议 profile 的 vuln.crash_streams），
    避免正常种子路也生成 dry run 崩溃的种子（之前需手动移走 amr/aac/ac3）。
    """
    path = TARGETS_DIR / f"{protocol}_streams.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    streams = data.get("streams", [])
    crash = crash_streams(protocol)  # 协议特定的崩溃流（profile 配置，缺省回退 RTSP）
    return [s for s in streams if s.get("name") not in crash]


def load_request_templates(protocol: str) -> dict | None:
    """读真实请求模板（提取自真实流量 pcap，请求真实性依据）。"""
    path = TARGETS_DIR / f"{protocol}_request_templates.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# 危险模式（规则种子 description 里的标识）→ 漏洞 action 集合
_DANGER_PATTERN_ACTIONS = {
    "self_loop": {"double_setup", "interleave_seq", "assert_seq", "replay_seq"},
    "lifecycle": {"uaf_seq", "lifecycle_seq"},
}


def _build_danger_streams(vulns: list, protocol: str = "rtsp") -> dict:
    """从漏洞知识提取「危险模式 → 触发流」映射，用于给规则种子智能分配流名。

    如 double_setup 漏洞（RTSP-039/040）的触发流是 matroska/ogg/mpeg1or2，
    则自环种子（SETUP+SETUP）应优先用这些流，而非默认流。
    """
    result: dict = {"self_loop": [], "lifecycle": []}
    if not vulns:
        return result
    for v in vulns:
        req = classify_vuln(v, protocol=protocol)
        for pattern, actions in _DANGER_PATTERN_ACTIONS.items():
            if req.action in actions:
                for s in req.streams:
                    if s and s not in result[pattern]:
                        result[pattern].append(s)
    return result


def _stream_for_seed(seed, danger_streams: dict, default_stream: str) -> str:
    """按种子的危险模式选流名（自环/生命周期优先用漏洞触发流，其余用默认流）。"""
    desc = (seed.description or "").lower()
    if "self-loop" in desc and danger_streams.get("self_loop"):
        return danger_streams["self_loop"][0]
    if "lifecycle" in desc and danger_streams.get("lifecycle"):
        return danger_streams["lifecycle"][0]
    return default_stream


def _apply_stream_urls(seed, stream: str, host: str = "127.0.0.1", port: str = "8554"):
    """把 LLM 现场生成的 url 里的占位符替换成真实服务器地址 + 探测流名。

    会话语义结构（SETUP 的 /track{N}、尾斜杠方法的 / 结尾）已由 source_autoseeder
    的 LLM 在生成实例时现场给出，这里【不再硬编码任何 URL 结构】，只做实例级替换：
    <server> → host:port、<stream> → 流名。
    """
    server = f"{host}:{port}"
    base = f"rtsp://{server}/{stream}"
    seed.selected_url = base
    for msg in seed.messages:
        if msg.url:
            msg.url = (msg.url
                       .replace("<server>", server)
                       .replace("<stream>", stream)
                       .replace("rtsp://server", f"rtsp://{server}"))
        else:
            # 实例未生成 url 时回退裸流名（交给 fuzzer 变异探索结构）
            msg.url = base
    return seed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-seeds", type=int, default=0,
                    help="种子数（默认=资源清单流名数）")
    ap.add_argument("--protocol", default="rtsp")
    ap.add_argument("--out", default=None,
                    help="输出目录（默认 derived/seeds/rtsp/<时间戳>/，每次自动新建子文件夹避免混批）")
    ap.add_argument("--no-react", action="store_true",
                    help="不用 ReAct，直接 generate_seeds")
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--attack", action="store_true",
                    help="启用漏洞导向攻击种子路（P0：生成合法边界种子）")
    ap.add_argument("--attack-only", action="store_true",
                    help="只生成攻击种子（跳过正常覆盖种子路）")
    ap.add_argument("--three-layer", action="store_true",
                    help="用三层语料库选择器生成种子（①边覆盖+②通用危险+③漏洞）")
    ap.add_argument("--stream", default="mp3AudioTest",
                    help="规则种子（①②层）使用的默认流名（默认 mp3AudioTest）")
    ap.add_argument("--minimal", action="store_true",
                    help="精简模式：只保留序列型关键种子（砍边界/字段型漏洞），集中变异预算")
    args = ap.parse_args()

    # 默认每次生成自动建带时间戳的子文件夹，避免不同批次种子混在一起
    if args.out is None:
        _base = ROOT / "derived" / "seeds" / args.protocol
        args.out = str(_base / datetime.now().strftime("%Y%m%d_%H%M%S"))

    print("=" * 64)
    print("ProtoKG 真 LLM 端到端验证（含目标资源清单 + 漏洞导向）")
    print("=" * 64)

    # 0. 加载目标资源清单 + 真实请求模板 + 历史漏洞
    resources = load_resources(args.protocol)
    request_templates = load_request_templates(args.protocol)
    vulns = load_vuln_kb(protocol=args.protocol)
    print(f"[0] 目标资源清单: {len(resources)} 个流名；"
          f"请求模板: {'有' if request_templates else '无'}；"
          f"历史漏洞: {len(vulns)} 条")
    if resources:
        for r in resources:
            print(f"      - {r['name']}（{r['tracks']} 轨 · {r['format']}）")

    # 1. 加载 facts
    views = load_fact_views(args.protocol)
    print(f"[1] 加载 facts: {len(views)} 条")
    if not views:
        print("!! 无 facts，请先运行 scripts/build_hub.py")
        return 1

    # 2. 分桶
    bundle = assemble_bundle(views)
    print("[2] 分桶结果:")
    print(f"    methods          : {len(bundle['methods'])} -> {sorted(bundle['methods'])}")
    print(f"    headers          : {len(bundle['headers'])}")
    print(f"    required_headers : {len(bundle['required_headers'])}")
    print(f"    transitions      : {len(bundle['transitions'])}")
    print(f"    security         : {len(bundle['security'])}")

    # 2.5 多导向自适应判定
    strategies = determine_strategies(bundle, resources, request_templates, vulns)
    print(f"[2.5] 导向判定: normal={strategies['normal']} "
          f"attack={strategies['attack']} constraints={strategies['constraints']}")
    attack_active = "vulnerability_guided" in strategies["attack"]
    if (args.attack or args.attack_only) and not attack_active:
        print("!! 无漏洞数据，跳过攻击路")
    attack_active = attack_active and (args.attack or args.attack_only)

    llm = DeepSeekClient()
    print(f"[3] LLM: model={llm.model}")

    seeds: list = []
    # 3c. 三层语料库选择器（①边覆盖 + ②通用危险 + ③漏洞，可选替代两路方案）
    if args.three_layer:
        seeds = select_seeds(
            bundle, resources=resources, request_templates=request_templates,
            vulns=vulns, llm=llm, protocol=args.protocol,
            attack_batch=4, max_rounds=args.max_rounds, minimal=args.minimal)
        # 给规则种子（①②层，无流名）智能分配流名 URL：自环/生命周期优先用漏洞触发流
        danger_streams = _build_danger_streams(vulns, protocol=args.protocol)
        # 单源码源（无漏洞知识）时，动态探测目标服务器真实流名（替代默认单流 mp3，不预设资源清单）
        probed_streams: list = []
        if not vulns:
            try:
                from core.fused.source_probe import probe_streams
                probed_streams = probe_streams() or []
                if probed_streams:
                    print(f"[4c.1] 动态探测到 {len(probed_streams)} 个流名: {probed_streams}")
            except Exception as e:  # noqa: BLE001
                print(f"[4c.1] 动态探测失败，回退默认流 {args.stream}: {e}")
        n_rule = 0
        for s in seeds:
            if (s.generated_by or "").startswith("rule-based"):
                stream = _stream_for_seed(s, danger_streams, args.stream)
                # 单源码源时，用探测到的流名轮询分配（覆盖多流，含漏洞流 matroska）
                if probed_streams and stream == args.stream:
                    stream = probed_streams[n_rule % len(probed_streams)]
                _apply_stream_urls(s, stream)
                n_rule += 1
        n_attack = sum(1 for s in seeds if "attack" in (s.generated_by or ""))
        print(f"[4c] 三层选择器: {len(seeds)} 条 "
              f"（规则 {n_rule} 条 + 漏洞 {n_attack} 条）")
        if not seeds:
            print("!! 未生成任何有效种子，请检查 LLM 输出。")
            return 1
        out = Path(args.out)
        written = write_seeds(seeds, out)
        print(f"[5c] 落盘: {len(written)} 个 .raw 到 {out}")
        for name in written[:3]:
            p = out / name
            raw = p.read_bytes().decode("utf-8", errors="replace")
            print(f"    --- {name} ---")
            print("    " + raw.replace("\r\n", " | ")[:300])
            print()
        print("=" * 64)
        print(f"完成。种子目录: {out}")
        print("=" * 64)
        return 0

    # 3a. 正常种子路（覆盖导向，P1×P3×P4，受 P2 约束）
    if not args.attack_only:
        n_seeds = args.n_seeds or (len(resources) if resources else 20)
        BATCH = 6
        print(f"[3a] 正常种子路: 目标 {n_seeds} 条（分批 {BATCH}/批）")
        all_seeds = []
        for start in range(0, n_seeds, BATCH):
            bn = min(BATCH, n_seeds - start)
            batch_resources = resources[start:start + bn] if resources else None
            kwargs = dict(protocol=args.protocol, n_seeds=bn,
                          resources=batch_resources,
                          request_templates=request_templates)
            if args.no_react:
                s = generate_seeds(bundle, llm, **kwargs)
            else:
                s = generate_seeds_react(bundle, llm,
                                         max_rounds=args.max_rounds, **kwargs)
            print(f"    批次 {start // BATCH + 1}: 生成 {len(s)} 条")
            all_seeds.extend(s)
        seeds.extend(all_seeds)
        print(f"[4a] 正常种子: {len(all_seeds)} 条")
    else:
        print("[3a] 跳过正常种子路（--attack-only）")

    # 3b. 攻击种子路（漏洞导向 P0，受 P2 约束）
    if attack_active:
        reqs = dedupe_reqs(classify_all(vulns, protocol=args.protocol))
        print(f"[3b] 攻击种子路: {len(vulns)} 条漏洞 → {len(reqs)} 个去重漏洞模式 → 合法边界种子")
        ATK_BATCH = 4
        attack_seeds = []
        for start in range(0, len(reqs), ATK_BATCH):
            batch_reqs = reqs[start:start + ATK_BATCH]
            s = generate_attack_seeds(
                bundle, llm, batch_reqs, protocol=args.protocol,
                resources=resources, request_templates=request_templates,
                max_rounds=args.max_rounds)
            print(f"    批次 {start // ATK_BATCH + 1}: {len(batch_reqs)} 模式 → {len(s)} 条")
            attack_seeds.extend(s)
        print(f"[4b] 攻击种子: {len(attack_seeds)} 条（通过中枢知识校验）")
        seeds.extend(attack_seeds)
    else:
        print("[3b] 跳过攻击种子路（未启用 --attack 或无漏洞数据）")

    if not seeds:
        print("!! 未生成任何有效种子，请检查 LLM 输出或 n_seeds 大小。")
        return 1

    # 4. 落盘（每个种子用自己的 selected_url，即各自流名）
    out = Path(args.out)
    written = write_seeds(seeds, out)
    print(f"[5] 落盘: {len(written)} 个 .raw 到 {out}")

    # 5. 检查流名覆盖
    covered = set()
    for s in seeds:
        if s.selected_url:
            covered.add(s.selected_url)
    if resources:
        names = {r["name"] for r in resources}
        missed = names - {u.split("/")[-1].rstrip("/") for u in covered
                          if u.split("/")[-1] and not u.endswith("/track")}
        print(f"[6] 流名覆盖: {len(covered)} 个不同 URL，资源清单共 {len(names)} 个流名")

    # 6. 打印前 3 个样本
    for name in written[:3]:
        p = out / name
        raw = p.read_bytes().decode("utf-8", errors="replace")
        print(f"    --- {name} ---")
        print("    " + raw.replace("\r\n", " | ")[:300])
        print()

    # 7. 正常 / 攻击种子统计
    n_attack = sum(1 for s in seeds if "attack" in (s.generated_by or ""))
    print(f"[7] 种子构成: 正常 {len(seeds) - n_attack} 条 + 攻击 {n_attack} 条")

    print("=" * 64)
    print(f"完成。种子目录: {out}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
