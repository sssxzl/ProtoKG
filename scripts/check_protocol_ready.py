# -*- coding: utf-8 -*-
"""scripts/check_protocol_ready.py —— **协议接入两阶段状态检查**。

★ 为什么要它：协议接入是**两阶段**的，两阶段依赖**不同的目录**：

    阶段 I · 知识接入（外部提供）  kb/<协议>/<源>/         ⇒ ②抽取 ③中枢 ④知识图
    阶段 II · 测试接入（项目侧）   profiles/<协议>/         ⇒ ⑤种子生成

  ⇒ 「知识库来了但档案还没准备」是**正常中间态**，不是错误。
  ⇒ 本脚本把「当前处在哪个阶段、缺什么、怎么补」**一次说清**，避免用户在
    深处遇到 FileNotFoundError 才发现少东西。

用法::

    python scripts/check_protocol_ready.py --protocol rtsp
    python scripts/check_protocol_ready.py --protocol http --json

退出码：0 = 两阶段都就绪；1 = 有缺失（按提示补）；2 = 参数错误。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths  # noqa: E402

#: 五源目录名（与 kb/<协议>/ 下的约定一致）
SOURCE_DIRS = ("spec", "协议实现源码", "数据流量", "历史漏洞", "expert_note")

#: 阶段 II 的必需文件（缺任一 ⇒ ⑤种子生成跑不了）
REQUIRED_PROFILE_FILES = ("profile.json",)

#: profile.json 里**必须人工**的字段（自动推断不出来）
MANUAL_FIELDS = {
    "url_placeholders": "目标服务的资源路径（私有协议必需）",
    "resources_file": "可用资源清单（流名/文件名列表）",
    "boundary_probe": "黑盒行为参数（端口范围 / 传输切换串）",
}


def _kb_sources(protocol: str) -> dict:
    root = paths.kb_root() / protocol.lower()
    out = {}
    if not root.is_dir():
        return out
    for d in SOURCE_DIRS:
        p = root / d
        n = sum(1 for f in p.rglob("*") if f.is_file()) if p.is_dir() else 0
        out[d] = n
    return out


def _profile_info(protocol: str) -> dict:
    prof = paths.target_profile(protocol)
    info = {"exists": prof.is_file(), "path": str(prof), "missing_manual": []}
    if not prof.is_file():
        return info
    try:
        data = json.loads(prof.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        info["error"] = "profile.json 解析失败"
        return info
    for f, why in MANUAL_FIELDS.items():
        if not data.get(f):
            info["missing_manual"].append({"field": f, "why": why})
    info["keys"] = sorted(k for k in data if not k.startswith("_"))
    return info


def check(protocol: str) -> dict:
    """返回两阶段状态。"""
    proto = protocol.lower()
    sources = _kb_sources(protocol)
    have_kb = sum(1 for v in sources.values() if v > 0)
    prof = _profile_info(protocol)
    prof_dir = paths.targets_root() / proto
    rfc_cfg = (prof_dir / "rfc_config.json").is_file()

    stage1 = {
        "name": "知识接入",
        "dir": str(paths.kb_root() / proto),
        "ready": have_kb > 0,
        "sources": sources,
        "source_count": have_kb,
        "note": "②抽取 → ③中枢 → ④知识图 均可进行" if have_kb else
                "kb/<协议>/ 下没有任何源文件 ⇒ ②③④ 都跑不了",
    }
    stage2 = {
        "name": "测试接入",
        "dir": str(prof_dir),
        "ready": prof["exists"] and rfc_cfg,
        "profile_exists": prof["exists"],
        "rfc_config_exists": rfc_cfg,
        "missing_manual": prof.get("missing_manual", []),
        "note": "⑤种子生成可进行" if (prof["exists"] and rfc_cfg) else
                "缺 profiles/<协议>/ 下的档案 ⇒ ⑤种子生成跑不了"
                "（跑 scripts/onboard_protocol.py --protocol %s 可自动生成八成）" % proto,
    }
    return {
        "protocol": proto,
        "stage1_knowledge": stage1,
        "stage2_testing": stage2,
        "fully_ready": stage1["ready"] and stage2["ready"],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="协议接入两阶段状态检查")
    ap.add_argument("--protocol", required=True, help="协议名（如 rtsp / sip / smtp / dhcpv4）")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args(argv)

    r = check(args.protocol)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["fully_ready"] else 1

    p = args.protocol.lower()
    print(f"=== 协议接入状态：{p} ===\n")

    s1, s2 = r["stage1_knowledge"], r["stage2_testing"]
    mark1 = "✅" if s1["ready"] else "❌"
    print(f"{mark1} 阶段 I · 知识接入  ——  {s1['dir']}")
    if s1["source_count"]:
        for k, v in s1["sources"].items():
            print(f"       {'✔' if v else '·'} {k:14s} {v:5d} 文件")
    print(f"     ⇒ {s1['note']}\n")

    mark2 = "✅" if s2["ready"] else "❌"
    print(f"{mark2} 阶段 II · 测试接入  ——  {s2['dir']}")
    print(f"       {'✔' if s2['profile_exists'] else '✘'} profile.json")
    print(f"       {'✔' if s2['rfc_config_exists'] else '✘'} rfc_config.json")
    if s2.get("missing_manual"):
        print("     ⚠ 以下字段**必须人工**（自动推断不出来）：")
        for m in s2["missing_manual"]:
            print(f"       · {m['field']:20s} {m['why']}")
    print(f"     ⇒ {s2['note']}\n")

    if r["fully_ready"]:
        print("✅ 两阶段都就绪 ⇒ 全链路可跑：")
        print(f"   python scripts/build_hub.py --protocol {p} --sources rfc")
        print(f"   python scripts/build_graph.py --protocol {p}")
        print(f"   python scripts/seedgen.py --protocol {p} --max-seeds 5")
        return 0
    if not s1["ready"]:
        print("❌ 阶段 I 未就绪 ⇒ 请先准备 kb/<协议>/ 下的知识源")
    else:
        print("⚠ 阶段 II 未就绪 ⇒ 知识链路可跑，种子生成暂不可跑")
        print(f"   建议：python scripts/onboard_protocol.py --protocol {p}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
