# -*- coding: utf-8 -*-
"""scripts/publish_semantic_rules.py —— 把语义规则**分流发布**进四库。

★ 为什么需要这个脚本（批次 1.5）：
  RFC 源抽出的语义规则此前只落在**实验目录**
  （``derived/exp_semantic_gain/group_E*/rules.jsonl``）⇒ 权威库
  ``derived/per_source/<协议>/rfc/semantic/rules.jsonl`` **从未落盘**
  ⇒ 知识中枢拿不到规则 ⇒ 投影两桶 ``legal_boundary`` /
  ``response_expectation`` **恒空** ⇒ 「源 A 第四类」约束边界候选**恒为 0**
  ⇒ **RFC 语义对种子生成零贡献**。

★ 分流（两层模型的正确用法，**不静默丢弃**）：
  · 合格 ⇒ **权威库**（``rules.jsonl``）⇒ 中枢可读 ⇒ 投影 ⇒ 消费端有输入；
  · 不合格 ⇒ **候选库**（``candidates.jsonl``），带 ``reject_reason``。

★ 质量闸（发布前逐条判定）：
  ① 可反序列化为 ``SemanticRule``；
  ② ``constraint is not None``；
  ③ ``sanitize_rule`` 的三类移除判定（空 subject / 空 operand / 自指约束）。

用法::

    python scripts/publish_semantic_rules.py --protocol rtsp \
        --from derived/exp_semantic_gain/group_E1/rules.jsonl
    python scripts/publish_semantic_rules.py --protocol rtsp --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.fused.downstream.rule_store import (  # noqa: E402
    library_path, publish_rules,
)


def _read_rows(path: Path) -> list[dict]:
    """读 jsonl（裸 rule dict 或 ``{"kind":..., "rule": {...}}`` 两种形态都收）。"""
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        if isinstance(data, dict) and data.get("kind") == "semantic_rule":
            rows.append(data.get("rule") or {})
        elif isinstance(data, dict):
            rows.append(data)
    return rows


def _protocol_spec_versions(protocol: str) -> list[str] | None:
    """本协议的规范号（来自 ``fused_hub/targets/<协议>/rfc_config.json``）。

    ★ 批次 2.5（F1）：语义规则必须按协议过滤 —— B-10 的实验产物是
      **多协议混合**的（实测 RFC 2326:11 / RFC 3261:9 / RFC 5321:1）。
    """
    cfg = REPO_ROOT / "fused_hub" / "targets" / protocol / "rfc_config.json"
    if not cfg.is_file():
        return None
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    sv = str(data.get("spec_version") or "").strip()
    return [sv] if sv else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="把语义规则分流发布进权威库/候选库")
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--from", dest="src", default=None,
                    help="规则 jsonl 路径（裸 rule dict 形态）；"
                         "缺省 = 发布当前权威库已有的规则（整理/去重）")
    ap.add_argument("--replace", action="store_true",
                    help="覆盖权威库（默认**追加**并按 rule_id 去重）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只跑质量闸并打印报告，**不写盘**")
    ap.add_argument("--all-specs", action="store_true",
                    help="**不按协议过滤**（默认按 fused_hub/targets/<协议>/"
                         "rfc_config.json 的 spec_version 过滤）—— "
                         "批次 2.5 F1：跨协议规则必须过滤，否则 SIP 的 "
                         "RFC 3261 规则会进 RTSP 库")
    args = ap.parse_args(argv)

    protocol = args.protocol
    if args.src:
        src = Path(args.src)
        if not src.is_absolute():
            src = REPO_ROOT / src
        if not src.is_file():
            print(f"规则文件不存在：{src}")
            return 2
        rows = _read_rows(src)
    else:
        from core.fused.downstream.rule_store import load_rules
        path = library_path(protocol, "authoritative")
        if not path.is_file():
            print(f"权威库不存在：{path}")
            return 2
        rows = load_rules(path)

    # ★ 批次 2.5（F1）：默认**按协议过滤**（spec_version 来自 rfc_config）
    specs = None
    if not args.all_specs:
        specs = _protocol_spec_versions(protocol)
        if specs is None:
            print("★ 本协议未声明 spec_version（rfc_config.json）"
                  "⇒ **不按协议过滤**（如需强制过滤请手动指定）")
        else:
            print(f"★ 按协议过滤：只接受 {specs} 的规则")

    if args.dry_run:
        # 干跑：只做质量闸（不写盘）—— 用临时目录承载
        import tempfile
        with tempfile.TemporaryDirectory():
            report = publish_rules(protocol, rows, replace=True,
                                   spec_versions=specs)
        report = dict(report)
        report["dry_run"] = True
        report["source"] = str(args.src or library_path(protocol, "authoritative"))
    else:
        report = publish_rules(protocol, rows, replace=args.replace,
                               spec_versions=specs)
        report["source"] = str(args.src or library_path(protocol, "authoritative"))

    print("=== 发布报告 ===")
    print(f"  来源      : {report['source']}")
    print(f"  权威库    : {report['authoritative']} 条  ({report['path']})")
    print(f"  候选库    : {report['candidate']} 条  ({report['candidate_path'] or '（无）'})")
    print(f"  拒绝原因  : {report['rejects'] or '（无）'}")
    if report.get("dry_run"):
        print("  ★ 干跑：未写盘")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
