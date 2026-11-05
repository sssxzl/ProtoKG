# -*- coding: utf-8 -*-
"""C′-2 前置实验：**强制 method 落在白名单内**，能不能救回 SIP 的图腿转移？

背景（§1.3 已实测）：
  SIP §17 的 ASCII 图边标签全是事件/响应（`1xx` / `Timer A fires` / `300-699`），
  ⇒ 质量闸判据②必然拦下，14 条全废。

C′-2（输出契约加 Allowed commands 字段）的假设是：
  把「允许的方法名」写进提示词，LLM 就会给出**真方法**。
本实验验证这个假设在 SIP 图上是否成立，两种契约强度各跑一遍：

  V1（严，带反编造条款）：只能从白名单选；图中若只是响应/事件，method 留空。
  V2（宽，只给白名单）：只能从白名单选，**不**提示「可留空」。

判据：
  - V1 若大量留空 ⇒ LLM 确认「图上没有方法」⇒ C′-2 救不了 SIP，结论为负；
  - V2 若填满白名单但状态/边对不上 ⇒ 是**编造**，比不填更危险（闸失去保护作用）。

只读，不写任何产物。
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from core.fused import rfc_extractor as RX  # noqa: E402
from core.llm import DeepSeekClient  # noqa: E402

LINES = open("kb/sip/spec/rfc3261.txt", encoding="utf-8",
             errors="ignore").read().splitlines()

FIGS = {
    "Figure5-INVITE-client": (7246, 7283),
    "Figure7-INVITE-server": (7610, 7743),
}

KNOWN = RX._rfc_source_methods("sip", RX._load_rfc_config("sip"))

V1 = """你是协议规范分析助手。下面是 {protocol} 协议 RFC 规范中的一段
**状态机图示（ASCII）**。

请抽取状态转移，输出 JSON：
{{"transitions": [{{"from": "<源状态>", "method": "<触发方法>", "to": "<目标状态>"}}]}}

★ 硬约束：
1. `method` 只能取自这个允许集合（Allowed commands）：{allowed}
2. **不要编造**。如果某条边的触发条件在图上是**响应码 / 计时器 / 事件**
   （例如 `1xx`、`2xx`、`300-699`、`Timer A fires`、`Transport Err.`），
   那不是方法 ⇒ 该条的 `method` 必须填空字符串 ""，不要为了填满而猜。
3. 状态名用图上的原文。

文本：
{text}
"""

V2 = """你是协议规范分析助手。下面是 {protocol} 协议 RFC 规范中的一段
**状态机图示（ASCII）**。

请抽取状态转移，输出 JSON：
{{"transitions": [{{"from": "<源状态>", "method": "<触发方法>", "to": "<目标状态>"}}]}}

★ 硬约束：`method` 只能取自这个允许集合（Allowed commands）：{allowed}
状态名用图上的原文。

文本：
{text}
"""

llm = DeepSeekClient()
print(f"SIP 白名单（{len(KNOWN)}）: {sorted(KNOWN)}\n")

for vname, tpl in (("V1-严/反编造", V1), ("V2-宽/只给白名单", V2)):
    for fname, (a, b) in FIGS.items():
        text = "\n".join(LINES[a - 1:b])
        try:
            r = llm.chat_json(
                system="你输出 JSON。",
                user=tpl.format(protocol="SIP", allowed=", ".join(sorted(KNOWN)),
                                text=text),
                temperature=0.0, max_tokens=2000)
        except Exception as exc:  # noqa: BLE001
            print(f"[{vname}][{fname}] LLM 失败: {exc}")
            continue
        trs = (r or {}).get("transitions") or []
        blank = sum(1 for t in trs if not str(t.get("method", "")).strip())
        inwl = sum(1 for t in trs
                   if str(t.get("method", "")).strip().upper() in KNOWN)
        print(f"[{vname}][{fname}] 抽出 {len(trs)} 条 ｜ 留空 {blank} ｜ "
              f"命中白名单 {inwl} ｜ 闸后预计 {inwl}")
        for t in trs[:12]:
            m = str(t.get("method", "")).strip()
            flag = "✔" if m.upper() in KNOWN else ("∅" if not m else "✘")
            print(f"    {flag} {t.get('from')} --{m or '(空)'}--> {t.get('to')}")
        print()
