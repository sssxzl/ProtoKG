# -*- coding: utf-8 -*-
"""S2 试点：图腿 + 散文腿（真调 LLM，只读，不改生产代码）。

★ 目的（"让模型更优、效果更好"的可量化定义）：
  现状 SIP/SMTP 的状态机 **100% 来自骨架**，而骨架的状态名多数**不在 RFC 原文**
  （实测 sip 4/8=50%、smtp 2/9=22%）⇒ 这两个协议的状态机维度**不是 RFC 单源的**。
  ⇒ 本试点测：形态层的**图腿**（ASCII 状态图）与**散文腿**（规范性条款）能否
     从 RFC 原文抽到**状态名命中率高、且 method 可驱动**的状态机。

★ 与既有工作一致的三处设计（均有文献依据）：
  ① 形态分派（表格腿已落地）—— StatePre §3.2.1/3.2.2 的结构化 vs 推断二分
  ② artifact：ASCII 图**原样**进 prompt —— PROSPER Artifact Miner
  ③ 输出契约含 allowed_commands + 触发条件种类（command/event）——
     StatePre Listing 3；PSMBENCH 的 action/event disambiguation

★ 判据（与门禁 v2「状态名来源」档一致）：
  · 状态名 RFC 原文命中率（分协议）
  · method ∈ RFC 源已知方法集的比例（可驱动性）
  · 事件型 method 的比例（不可驱动，但要单独标注）

用法：E:/app/Anaconda3/python.exe local/_pilot_s2_form_legs.py [协议...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths                                      # noqa: E402
from core.fused import rfc_forms as RF                     # noqa: E402
from core.llm import DeepSeekClient                        # noqa: E402

#: 契约：触发条件种类 + 允许命令集
PROMPT = """你是协议规范分析助手。下面是 {protocol} 协议 RFC 规范中的{what}。

请抽取其中**明确写出的**状态转移，输出 JSON：
{{"transitions": [{{"from": "<源状态名>", "method": "<触发条件>", "to": "<目标状态名>",
                    "kind": "command" | "event",
                    "allowed_commands": ["该状态下允许发送的方法"]}}]}}

规则：
1. 只抽规范里**明确写出**的转移，不要推测、不要补充 RFC 之外的常识。
2. `from` / `to` 的状态名**照抄规范里的写法**（不要改名、不要归一化大小写）。
3. ★ `method` 填该转移的**触发条件**：
   - 若是**该协议的方法/命令名** ⇒ `kind="command"`；
   - 若是**响应码 / 计时器 / 事件 / 信号** ⇒ `kind="event"`（照抄规范写法）。
4. `allowed_commands` 填该状态（或该转移后状态）下**规范明确允许发送**的方法；
   规范没写就留空数组。
5. 抽不到就返回 {{"transitions": []}}。

{extra}
{body}
"""


def rfc_methods(protocol: str) -> set[str]:
    """从 RFC 源抽「已知方法集」（数据驱动，不硬编码协议名）。

    ★ 做法：读 rfc_config 的 method_sections ⇒ 取这些章节里的**全大写 token**
      （排除 RFC 自身的关键字）⇒ 作为「该协议真实方法集」。
    """
    cfg = json.loads(
        paths.target_profile(protocol).parent.joinpath("rfc_config.json")
        .read_text(encoding="utf-8"))
    secs = cfg.get("method_sections") or []
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    out: set[str] = set()
    kw = {"MUST", "SHALL", "SHOULD", "MAY", "REQUIRED", "OPTIONAL", "NOT",
          "RFC", "TCP", "UDP", "IP", "HTTP", "ID", "URI", "URL", "ACK", "OK"}
    for f in sorted(spec_dir.glob("*.txt")):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        for i, ln in enumerate(lines):
            s = ln.strip()
            m = re.match(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z][A-Z_]{1,15})\b", s)
            if not m:
                continue
            num, name = m.group(1), m.group(2)
            if secs and not any(num == x or num.startswith(x + ".")
                               for x in secs):
                continue
            if name in kw:
                continue
            out.add(name)
    return out


def candidates(protocol: str, kinds: tuple[str, ...]) -> list[dict]:
    out = []
    for f in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        for b in RF.split_form_blocks(lines):
            if b.kind in kinds:
                out.append({"kind": b.kind, "text": b.text,
                            "src": f"{f.name}#@{b.line_start}"})
    return out


def main() -> None:
    protocols = sys.argv[1:] or ["rtsp", "sip", "smtp"]
    llm = DeepSeekClient()
    report: dict = {}
    for protocol in protocols:
        methods = rfc_methods(protocol)
        text_all = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")))
        cands = candidates(protocol, ("diagram", "normative"))
        by_kind: dict[str, list[dict]] = {"diagram": [], "normative": []}
        for c in cands:
            by_kind[c["kind"]].append(c)
        rows: list[dict] = []
        for kind, cs in by_kind.items():
            for c in cs:
                extra = ("\n该协议已知方法/命令（kind=command 的 method 必须取自此表）："
                         + ", ".join(sorted(methods))) if methods else ""
                what = ("ASCII 状态图（请原样阅读图中的节点与箭头标签）"
                        if kind == "diagram" else "规范性条款段落")
                try:
                    r = llm.chat_json(
                        system="你输出 JSON。",
                        user=PROMPT.format(protocol=protocol.upper(), what=what,
                                            extra=extra, body=c["text"][:7000]),
                        temperature=0.0, max_tokens=2500)
                except Exception as exc:  # noqa: BLE001
                    print(f"    [LLM 失败] {exc}", file=sys.stderr)
                    continue
                if not isinstance(r, dict):
                    continue
                for tr in (r.get("transitions") or []):
                    if isinstance(tr, dict):
                        tr["_kind"] = kind
                        tr["_src"] = c["src"]
                        rows.append(tr)
        states = sorted({str(r.get("from", "")).strip() for r in rows}
                        | {str(r.get("to", "")).strip() for r in rows})
        states = [s for s in states if s]
        hit = [s for s in states if s in text_all]
        mths = sorted({str(r.get("method", "")).strip() for r in rows})
        cmd_like = [m for m in mths if m.upper() in methods]
        ev = [m for m in mths if m.upper() not in methods]
        kinds_decl = {}
        for r in rows:
            k = str(r.get("kind", "")).strip() or "?"
            kinds_decl[k] = kinds_decl.get(k, 0) + 1
        print("=" * 78)
        print(f"{protocol}: 候选 diagram {len(by_kind['diagram'])} 块 / "
              f"normative {len(by_kind['normative'])} 块 ⇒ 抽出 {len(rows)} 条转移")
        print(f"   状态名 {len(states)} 个，RFC 原文命中 {len(hit)}/{len(states)}"
              f" = {len(hit)/len(states):.0%}" if states else "   无状态")
        print(f"   method {len(mths)} 个：属已知方法 {len(cmd_like)} / 事件或其它 {len(ev)}")
        if ev:
            print(f"   事件/未知 method: {ev[:10]}")
        print(f"   kind 分布（自报）: {kinds_decl}")
        report[protocol] = {
            "candidates": {k: len(v) for k, v in by_kind.items()},
            "n_transitions": len(rows), "states": states,
            "state_hit": len(hit), "state_hit_rate": round(len(hit)/len(states), 4) if states else 0,
            "methods": mths, "command_like": cmd_like, "event_like": ev,
            "kind_declared": kinds_decl,
        }
    p = Path(__file__).resolve().parent / "_pilot_s2_form_legs.json"
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {p}")


if __name__ == "__main__":
    main()
