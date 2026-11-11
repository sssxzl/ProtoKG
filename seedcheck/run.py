# -*- coding: utf-8 -*-
"""seedcheck/run.py —— **种子校验层入口**（编排 V1~V6 + 出报告）。

★ 定位（与代码审查分开）
  · ``guard/``   ⇒ **代码审查**（查代码/契约/文档；改代码后跑）
  · ``seedcheck/`` ⇒ **产物审查**（查种子质量；生成种子后跑）
  ⇒ 两者**互不依赖**，且 ``seedcheck`` **不 import** ``core.fused.downstream``
    （护栏会检查这条 ⇒ 防止反向耦合）。

★ 用法
  python seedcheck/run.py --protocol rtsp --seed-dir derived/seeds/rtsp/<ts>
  python seedcheck/run.py --protocol rtsp --seed-dir <dir> --target-env rq2-live555
  python seedcheck/run.py --protocol rtsp --seed-dir <dir> --llm --model deepseek-chat

★ 退出码
  0 ⇒ 无 V1（格式必假）违规
  1 ⇒ 有 V1 违规（格式非法 ⇒ 种子不可用）
  ★ V2~V6 的问题**只报告不阻断**（详见 docs/设计/种子校验层设计.md）。
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

#: 让 `python seedcheck/run.py` 直接跑（把仓库根加进 sys.path）
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from seedcheck import v1_format, v5_diversity            # noqa: E402
from seedcheck.knowledge import load_knowledge  # noqa: E402
from seedcheck.model import Report, SeedRecord  # noqa: E402

#: 报文目录名（与 seedgen 一致）
SEED_EXT = ".raw"


def parse_seed_file(path: Path) -> SeedRecord:
    """读一个 ``*.raw`` ⇒ 解析成 SeedRecord（messages 结构化）。"""
    raw = path.read_text(encoding="utf-8", errors="replace")
    rec = SeedRecord(filename=path.name, raw_text=raw)
    norm = raw.replace("\r\n", "\n")
    for blk in [b for b in norm.split("\n\n") if b.strip()]:
        lines = [ln for ln in blk.split("\n") if ln.strip()]
        if not lines:
            continue
        head = lines[0].strip()
        parts = head.split(" ")
        meth = parts[0] if parts else ""
        uri = parts[1] if len(parts) > 1 else ""
        version = parts[2] if len(parts) > 2 else ""
        headers: dict[str, str] = {}
        for ln in lines[1:]:
            s = ln.strip()
            if ":" in s:
                k, v = s.split(":", 1)
                headers[k.strip()] = v.strip()
        rec.messages.append({"method": meth, "uri": uri,
                             "version": version, "headers": headers})
    return rec


def load_manifest(seed_dir: Path) -> dict:
    mp = seed_dir / "manifest.json"
    if not mp.is_file():
        return {}
    try:
        return json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


#: 语料目录名的时间戳格式（``YYYYmmdd_HHMMSS``）⇒ 只有它算「一次构建的产物」
_SEED_DIR_STAMP = re.compile(r"^\d{8}_\d{6}$")


def latest_seed_dir(protocol: str) -> Path | None:
    """该协议最新一次的语料目录。

    ★ 2026-11-11 修复：**只认时间戳格式的目录**（``YYYYmmdd_HHMMSS``）
      ⇒ 旧实现按名字排序取最后一个 ⇒ ASCII ``_``(0x5F) > ``2``(0x32)
      ⇒ **非时间戳目录**（如探针用的 ``_probe``）会排到最后 ⇒ 被误当成「最新」
      ⇒ 实测：用户刚跑完 205304，seedcheck 却校验了 ``_probe``（22 条）。
    ⇒ 时间戳目录的**字典序 = 时间序** ⇒ 取最大者即可。
    """
    root = _ROOT / "derived" / "seeds" / protocol.lower()
    if not root.is_dir():
        return None
    dirs = sorted((d for d in root.iterdir()
                   if d.is_dir() and _SEED_DIR_STAMP.match(d.name)),
                  key=lambda d: d.name)
    return dirs[-1] if dirs else None


def collect_seeds(seed_dir: Path) -> list[SeedRecord]:
    return [parse_seed_file(p) for p in sorted(seed_dir.glob(f"*{SEED_EXT}"))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="种子校验层（seedcheck）")
    ap.add_argument("--protocol", default=None,
                    help="协议名（默认从 manifest 读）")
    ap.add_argument("--seed-dir", default=None,
                    help="语料目录（默认取该协议最新一次）")
    ap.add_argument("--target-env", default=None,
                    help="目标环境名（用于 V3 环境适配）")
    ap.add_argument("--out-dir", default=None,
                    help="报告输出目录（默认 seedcheck/_out/<协议>/<时间戳>）")
    ap.add_argument("--llm", action="store_true",
                    help="同时跑 V6（LLM 语义审查，只报告）")
    ap.add_argument("--api-key", default=None, help="LLM 凭据（等价 LLM_API_KEY）")
    ap.add_argument("--model", default=None, help="LLM 模型名（等价 LLM_MODEL）")
    ap.add_argument("--base-url", default=None, help="LLM endpoint（等价 LLM_BASE_URL）")
    ap.add_argument("--no-warn", action="store_true",
                    help="只算指标，不因阈值告警而失败")
    ap.add_argument("--json", default=None, help="额外写一份 JSON 到指定路径")
    args = ap.parse_args(argv)

    # ---- 定位语料目录 ----
    seed_dir = Path(args.seed_dir) if args.seed_dir else None
    manifest: dict = {}
    protocol = args.protocol or ""
    if seed_dir is None:
        if not protocol:
            print("!! 需要 --protocol 或 --seed-dir")
            return 2
        seed_dir = latest_seed_dir(protocol)
        if seed_dir is None:
            print(f"!! 协议 {protocol} 没有语料目录（先跑 seedgen.py）")
            return 2
    manifest = load_manifest(seed_dir)
    if not protocol:
        protocol = str(manifest.get("protocol") or "")
    if not protocol:
        print("!! 无法确定协议（manifest 无 protocol 字段 ⇒ 请显式 --protocol）")
        return 2

    report = Report(protocol=protocol, seed_dir=str(seed_dir),
                    target_env=args.target_env or "")
    report.layers_run = ["V1", "V5"]

    # ---- 读判据（中枢 + 协议档案）----
    k = load_knowledge(protocol)
    report.notes = list(k.notes)

    # ---- 载入种子 ----
    seeds = collect_seeds(seed_dir)
    report.seeds = seeds

    # ---- V1 格式必假（唯一阻断级）----
    malformed = 0
    for s in seeds:
        for v in v1_format.check(s):
            s.add(v)
            report.violations.append(v)
            if v.code != "empty_file":
                malformed += 1

    # ---- V5 多样性（本次运行统计 + 阈值告警）----
    #  ★ 层覆盖从 manifest 读 ⇒ 必须**先**写 layers 再算指标（否则 layer_coverage=0）
    layers = [str(x) for x in ((manifest.get("seedgen") or {}).get("layers") or [])]
    report.metrics["layers"] = layers
    v5_diversity.compute_metrics(seeds, report)
    for v in v5_diversity.check(seeds, report):
        report.violations.append(v)

    # ---- V2/V3/V4（判据来自中枢 ⇒ 只打标）----
    if not args.no_warn or True:      # ★ 这几层总是跑（只是不阻断）
        try:
            from seedcheck import v2_knowledge, v3_env, v4_fsm
        except ImportError:
            v2_knowledge = v3_env = v4_fsm = None
        if v2_knowledge is not None:
            report.layers_run += ["V2"]
            for s in seeds:
                for v in v2_knowledge.check(s, k):
                    s.add(v)
                    report.violations.append(v)
            # ★ 取值域不匹配：已降级为**统计**（不判违规）⇒ 写进 metrics
            #   ★ 原因：中枢的 value_enum_spec 是**示例集合**而非封闭取值域
            #     ⇒ 对实例型值（会话 id / branch / 端口）必然误报
            _vm = list(getattr(v2_knowledge, "_VALUE_MISMATCH", []) or [])
            if _vm:
                by_head = collections.Counter(x[1] for x in _vm)
                report.metrics["value_domain_mismatch"] = {
                    "count": len(_vm),
                    "by_header": dict(by_head.most_common()),
                    "note": ("★ 降级项：不判违规（中枢的取值域是**示例集合**而非封闭域；"
                             "且缺头模式知识）⇒ 只统计"),
                }
        if v3_env is not None:
            report.layers_run += ["V3"]
            for s in seeds:
                for v in v3_env.check(s, k, args.target_env):
                    s.add(v)
                    report.violations.append(v)
        if v4_fsm is not None:
            report.layers_run += ["V4"]
            fsm_stats: dict = {}
            for s in seeds:
                for v in v4_fsm.check(s, k, fsm_stats):
                    s.add(v)
                    report.violations.append(v)
            # ★ V4 产的是**知识完备度统计**（哪些方法未被状态机覆盖）⇒ 不是违规
            if fsm_stats.get("fsm_uncovered_methods"):
                report.metrics["fsm_uncovered_methods"] = fsm_stats["fsm_uncovered_methods"]

    # ---- V6（LLM，只报告）----
    if args.llm:
        report.layers_run += ["V6"]
        try:
            from seedcheck import v6_llm
            report.llm = v6_llm.review(seeds, k, args)
        except Exception as exc:                       # noqa: BLE001
            report.llm = {"error": f"{type(exc).__name__}: {exc}"}

    # ---- 写报告 ----
    import datetime as _dt
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else \
        (_ROOT / "seedcheck" / "_out" / protocol.lower() / ts)
    jp, tp = report.write(out_dir)
    if args.json:
        Path(args.json).write_text(json.dumps(report.to_dict(), ensure_ascii=False,
                                              indent=2), encoding="utf-8")

    print(report.summary_text())
    print(f"报告: {jp}")
    print(f"      {tp}")
    if malformed:
        print(f"\n!! V1 格式非法 {malformed} 处 ⇒ 种子不可用（退出码 1）")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
