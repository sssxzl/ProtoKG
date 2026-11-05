# -*- coding: utf-8 -*-
"""RFC 状态机候选定位 · 扩展规则可行性试点（真调 LLM，只读）。

★ 用户质疑：「rtsp 用同样操作能纯 RFC，sip/smtp 换个协议参数不就行了？」
  ⇒ 核实结论：**操作层面可复用，卡点是候选定位规则太窄**：
    ① `core/fused/rfc_extractor.py::_RE_STATE_MACHINE_HINT` 只匹配
       「state machine(s)」字样 ⇒ SIP 只定位到 §17 **事务**状态机（触发列是
       事件/响应码 ⇒ 抽出的 method 是 `Timer F`/`2xx` ⇒ 驱动不了报文生成），
       而 SIP 真正方法驱动的**对话状态机**（early/confirmed/established/
       terminated dialog）被漏掉；SMTP 则是「state **table**」措辞 ⇒ **完全没定位到**。
    ② RFC 5321 §2.3.6 明写 "Buffer and State Table"；RFC 3207/4954 明写
       "the initial state (the state in SMTP after a server issues a 220 …)"。

★ 本试点验证两件事（每协议一次 LLM 调用）：
  A. **扩展定位**能否把 SIP 对话状态机 / SMTP 状态表纳入候选；
  B. 抽出的 `method` 字段**是不是该协议的真实方法/命令**（决定能否驱动报文生成）。

★ 判据：method ∈ 该协议真实方法集 ⇒ 可驱动报文生成（对照 RTSP 的成功经验）。

用法：E:/app/Anaconda3/python.exe local/_pilot_state_locator.py [协议...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths                                      # noqa: E402
from core.llm import DeepSeekClient                         # noqa: E402

#: 真实方法/命令集（用于判据，不进提示词）
REAL_METHODS: dict[str, set[str]] = {
    "rtsp": {"OPTIONS", "DESCRIBE", "ANNOUNCE", "SETUP", "PLAY", "PAUSE",
             "TEARDOWN", "GET_PARAMETER", "SET_PARAMETER", "RECORD", "REDIRECT"},
    "sip": {"REGISTER", "INVITE", "ACK", "CANCEL", "BYE", "OPTIONS", "SUBSCRIBE",
            "NOTIFY", "MESSAGE", "INFO", "REFER", "PRACK", "UPDATE", "PUBLISH",
            "SUBSCRIBE"},
    "smtp": {"HELO", "EHLO", "MAIL", "RCPT", "DATA", "RSET", "NOOP", "VRFY",
             "EXPN", "HELP", "QUIT", "STARTTLS", "AUTH"},
}

#: 扩展定位：state machine / state table / state diagram / 状态机
EXT_HINT = re.compile(
    r"state\s*(machine|table|diagram|transition)s?\b", re.IGNORECASE)

#: 对话状态（SIP 这类「状态是名词化的会话实体」的协议）
DIALOG_HINT = re.compile(
    r"\b(early|confirmed|established|terminated)\s+dialog\b", re.IGNORECASE)

CONTEXT_LINES = 60

#: 新提示词：★ 关键约束 = method 必须是**该协议的方法/命令名**
PROMPT = """你是协议规范分析助手。下面文本来自 {protocol} 协议的 RFC 规范，其中描述了
**状态机**（可能是状态转移表、状态图，或散在正文里的状态转移叙述）。

请抽取其中**明确写出的状态转移**，输出 JSON：
{{"transitions": [{{"from": "<源状态名>", "method": "<触发方法名>", "to": "<目标状态名>"}}]}}

规则：
1. 只抽**规范里明确写出**的转移，不要推测、不要补充 RFC 之外的常识。
2. ★ `method` 必须是**该协议自己的请求方法名 / 命令名**（该协议报文里真实存在的方法）。
   - 若某条转移的触发条件**不是方法**（而是响应码、计时器、事件、信号），
     **不要抽这一条**（它无法用来生成报文）。
3. 状态名**照抄规范里的写法**，不要归一化大小写、不要改名、不要自造。
4. 抽不到就返回 {{"transitions": []}}。

文本：
{text}
"""


def locate(protocol: str) -> list[dict]:
    """扩展定位：state machine/table/diagram + 对话状态行。"""
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    out = []
    for f in sorted(spec_dir.glob("*.txt")):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        hits = [i for i, ln in enumerate(lines)
                if EXT_HINT.search(ln) or DIALOG_HINT.search(ln)]
        if not hits:
            continue
        groups: list[list[int]] = []
        for i in hits:
            if groups and i - groups[-1][-1] < 20:
                groups[-1].append(i)
            else:
                groups.append([i])
        for g in groups:
            lo, hi = max(0, g[0] - CONTEXT_LINES), min(len(lines), g[-1] + CONTEXT_LINES)
            text = "\n".join(lines[lo:hi]).strip()
            if text:
                out.append({"text": text, "source": f"{f.name}#@{lo+1}"})
    return out


def main() -> None:
    protocols = sys.argv[1:] or ["rtsp", "sip", "smtp"]
    llm = DeepSeekClient()
    report: dict = {}
    print("=" * 80)
    print("RFC 状态机候选定位 · 扩展规则可行性试点")
    print("=" * 80)
    for protocol in protocols:
        cands = locate(protocol)
        real = REAL_METHODS.get(protocol, set())
        all_rows, all_states = [], []
        for c in cands:
            try:
                r = llm.chat_json(system="你输出 JSON。",
                                  user=PROMPT.format(protocol=protocol.upper(),
                                                     text=c["text"][:7000]),
                                  temperature=0.0, max_tokens=2500)
            except Exception as exc:  # noqa: BLE001
                print(f"    [LLM 失败] {exc}", file=sys.stderr)
                continue
            if not isinstance(r, dict):
                continue
            for tr in (r.get("transitions") or []):
                if isinstance(tr, dict):
                    all_rows.append(tr)
        methods = sorted({str(r.get("method", "")).strip() for r in all_rows})
        states = sorted({str(r.get(k, "")).strip() for r in all_rows
                         for k in ("from", "to")})
        ok_methods = [m for m in methods if m.upper() in real]
        # RFC 原文命中率
        text_all = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")))
        hit = [s for s in states if s and s in text_all]
        print(f"\n── {protocol}")
        print(f"   候选段落 {len(cands)} 个 → 抽出转移 {len(all_rows)} 条")
        print(f"   状态名 {len(states)} 个，RFC 原文命中 {len(hit)}/{len(states)}")
        print(f"   method {len(methods)} 个，其中**真实方法/命令** {len(ok_methods)} 个")
        if methods:
            print(f"   method 列表: {methods}")
        if ok_methods:
            print(f"   ✓ 可用（方法驱动）的转移: "
                  f"{sum(1 for r in all_rows if str(r.get('method','')).upper() in real)} 条")
        report[protocol] = {
            "n_candidates": len(cands), "n_transitions": len(all_rows),
            "states": states, "rfc_hit_states": hit,
            "methods": methods, "real_methods_used": ok_methods,
        }
    p = Path(__file__).resolve().parent / "_pilot_state_locator.json"
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {p}")


if __name__ == "__main__":
    main()
