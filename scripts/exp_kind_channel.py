"""E-1 对照实验：**类别判定通道**（章节号 vs 内容）的逐条比对。

★ 批次 2 / S2（GraphRAG 改造）。目的：为「清除旧通道」提供**干净归因**的数据。

★ 实验设计（严格控制变量）：
  ┌────────────┬──────────────────────────────────────────┐
  │ 自变量     │ 类别判定通道：``config``（旧） / ``content``（新）│
  │ 因变量     │ ① fact 集合（逐条差集）                     │
  │            │ ② 方法集 / 字段集 / 状态码集                │
  │            │ ③ 误抽数 / 漏抽数（人工判定后统计）           │
  │ 协议       │ rtsp / sip / smtp（回归）+ dhcpv4（新协议）   │
  │ 混杂变量   │ ① LLM 通道随机性 ⇒ **禁用 LLM 通道**        │
  │            │ ② 章节号配置本身的正确性 ⇒ 逐协议标注        │
  │            │ ③ kb 内容 ⇒ 完全相同                         │
  └────────────┴──────────────────────────────────────────┘

★ **归因边界**：
  ✅ 可归因：「同一 kb + 同一抽取逻辑 + 只换判据来源」下的 fact 集合差异；
  ❌ **不能**归因：「内容判据更好」这个**总体结论** —— 只测了 4 个协议，
     且其中 3 个是**已知正确**的（方法集已人工确认过）。

★ 用法：
    E:/app/Anaconda3/python.exe scripts/exp_kind_channel.py
    E:/app/Anaconda3/python.exe scripts/exp_kind_channel.py --protocol rtsp
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: 三个文本协议的「人工确认过的真方法集」（★ 用于算漏抽/误抽）
KNOWN_METHODS: dict[str, set[str]] = {
    "rtsp": {"ANNOUNCE", "DESCRIBE", "GET_PARAMETER", "OPTIONS", "PAUSE",
             "PLAY", "RECORD", "REDIRECT", "SETUP", "SET_PARAMETER",
             "TEARDOWN"},
    "sip": {"ACK", "BYE", "CANCEL", "INVITE", "OPTIONS", "REGISTER"},
    "smtp": {"AUTH", "DATA", "EHLO", "EXPN", "HELP", "MAIL", "NOOP", "QUIT",
             "RCPT", "RSET", "STARTTLS", "VRFY"},
    # ★ DHCPv4 的**全部 8 个消息类型**（RFC 2131 §3.1 表 2 + §4.3.x）：
    #   客户端 5 个：DHCPDISCOVER / DHCPREQUEST / DHCPDECLINE / DHCPRELEASE /
    #                DHCPINFORM
    #   服务器 3 个：DHCPOFFER / DHCPACK / DHCPNAK
    #   ★ 服务器 3 个在 RFC 里**只有散文与时序图**、**没有独立小节**
    #     ⇒ 标题式抽取（config 通道）拿不到 ⇒ 它们是**内容通道的补全**，不是误抽。
    "dhcpv4": {"DHCPDECLINE", "DHCPDISCOVER", "DHCPINFORM", "DHCPRELEASE",
               "DHCPREQUEST", "DHCPOFFER", "DHCPACK", "DHCPNAK"},
}

#: 人工确认的「真头字段集」（部分协议，用于算字段漏抽）
KNOWN_HEADERS: dict[str, set[str]] = {
    "rtsp": {"Accept", "Authorization", "Content-Base", "Content-Length",
             "Content-Type", "CSeq", "Date", "Range", "Session", "Transport",
             "User-Agent", "WWW-Authenticate"},
}


def _run_channel(protocol: str, channel: str) -> dict:
    """用指定通道跑一遍抽取 ⇒ 返回 fact 摘要。

    ★ **不改生产代码**：用 monkeypatch 把 ``_section_kind`` 换成新通道。
    """
    from core.fused import rfc_extractor as RX
    from core.fused import rfc_classifier as RC

    orig = RX._section_kind
    if channel == "content":
        def patched(window, cfg, src_name=None):
            # ★ 新通道：内容判据优先；**完全不调旧通道**（连 L-D 兜底也不用）
            #   ⇒ 保证两条通道**判据完全独立**（否则对照实验不干净）
            k = RC._classify_by_form(window)
            if k:
                return k
            k = RC._classify_by_title(window)
            if k:
                return k
            k = RC._classify_by_prose(window)
            if k:
                return k
            return None
        RX._section_kind = patched
    try:
        norms = RX.extract_rfc_norms(protocol)
    finally:
        RX._section_kind = orig

    methods, fields, statuses, outcomes = set(), set(), set(), set()
    by_kind = collections.Counter()
    for n in norms:
        k = n.get("kind")
        by_kind[k] += 1
        name = (n.get("name") or "").strip()
        if k == "method":
            methods.add(name.upper())
        elif k == "field":
            fields.add(name)
        elif k == "outcome":
            statuses.add(name)
    return {
        "norm_count": len(norms),
        "by_kind": dict(by_kind),
        "methods": sorted(methods),
        "fields": sorted(fields),
        "statuses": sorted(statuses),
        "norm_ids": sorted({n["norm_id"] for n in norms}),
    }


def _diff(a: set, b: set) -> tuple[list, list]:
    return sorted(a - b), sorted(b - a)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    protos: list[str] = []
    if args.all:
        protos = ["rtsp", "sip", "smtp", "dhcpv4"]
    elif args.protocol:
        protos = [args.protocol]
    else:
        ap.error("需要 --protocol 或 --all")

    report: dict[str, dict] = {}
    for p in protos:
        cfg_run = _run_channel(p, "config")
        content_run = _run_channel(p, "content")

        m_lost, m_new = _diff(set(cfg_run["methods"]), set(content_run["methods"]))
        f_lost, f_new = _diff(set(cfg_run["fields"]), set(content_run["fields"]))
        n_lost, n_new = _diff(set(cfg_run["norm_ids"]), set(content_run["norm_ids"]))

        # 与「人工确认的真值」比 ⇒ 算漏抽/误抽
        km = KNOWN_METHODS.get(p)
        truth = {
            "config": {
                "missed": sorted(km - set(cfg_run["methods"])) if km else [],
                "false_positive": sorted(set(cfg_run["methods"]) - km) if km else [],
            },
            "content": {
                "missed": sorted(km - set(content_run["methods"])) if km else [],
                "false_positive": sorted(set(content_run["methods"]) - km) if km else [],
            },
        }
        report[p] = {
            "norm_count": {"config": cfg_run["norm_count"],
                           "content": content_run["norm_count"]},
            "by_kind": {"config": cfg_run["by_kind"],
                        "content": content_run["by_kind"]},
            "methods": {"config": cfg_run["methods"], "content": content_run["methods"]},
            "methods_diff": {"lost_in_content": m_lost, "new_in_content": m_new},
            "fields_diff": {"lost_in_content": f_lost, "new_in_content": f_new},
            "norm_ids_diff": {"lost_in_content_count": len(n_lost),
                              "new_in_content_count": len(n_new)},
            "truth_check": truth,
        }

        print(f"=== {p} ===")
        print(f"  norms: config {cfg_run['norm_count']} / content "
              f"{content_run['norm_count']}")
        print(f"  方法集差异: 丢 {len(m_lost)} / 增 {len(m_new)}")
        if m_lost:
            print(f"     丢: {m_lost[:12]}")
        if m_new:
            print(f"     增: {m_new[:12]}")
        print(f"  字段集差异: 丢 {len(f_lost)} / 增 {len(f_new)}")
        if f_lost:
            print(f"     丢: {f_lost[:10]}")
        if f_new:
            print(f"     增: {f_new[:10]}")
        if km:
            for ch in ("config", "content"):
                t = truth[ch]
                print(f"  [{ch:7s}] 漏抽 {len(t['missed'])} {t['missed'][:8]} | "
                      f"误抽 {len(t['false_positive'])} {t['false_positive'][:8]}")
        print()

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"[报告] 已写 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
