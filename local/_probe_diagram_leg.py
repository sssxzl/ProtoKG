# -*- coding: utf-8 -*-
"""A′ 图腿可行性验证：把 SIP 的 ASCII 状态图（Figure 5/6/7）喂给现有提示词，
看抽出的 method 是否落在「该协议真实方法集」内。

判据（MEMORY.md 已记）：
    RFC 状态机能否**驱动种子生成**，取决于转移表的「触发列」是不是**方法名**。
    RTSP A.1/A.2 ✔ / SIP §17 ✘（触发列是事件/响应码/计时器）。

若不编译就做图腿，等于给质量闸送人头（抽出来也全被过滤）。
"""
import sys

sys.path.insert(0, ".")

from core.fused import rfc_extractor as RX  # noqa: E402

LINES = open("kb/sip/spec/rfc3261.txt", encoding="utf-8",
             errors="ignore").read().splitlines()


def seg(a: int, b: int) -> str:
    return "\n".join(LINES[a - 1:b])


FIGS = {
    "Figure5-INVITE-client": (7246, 7283),
    "Figure6-nonINVITE-client": (7425, 7573),
    "Figure7-INVITE-server": (7610, 7743),
}

cfg = RX._load_rfc_config("sip")
known = RX._rfc_source_methods("sip", cfg)
print(f"SIP 真实方法集（{len(known)}）: {sorted(known)}\n")

from core.llm import DeepSeekClient  # noqa: E402
llm = DeepSeekClient()

for name, (a, b) in FIGS.items():
    text = seg(a, b)
    print(f"===== {name}（行 {a}-{b}，{b - a + 1} 行）=====")
    try:
        r = llm.chat_json(
            system="你输出 JSON。",
            user=RX._PROMPT_TRANSITION.format(protocol="SIP", text=text),
            temperature=0.0, max_tokens=2000)
    except Exception as exc:  # noqa: BLE001
        print(f"  [LLM 失败] {exc}")
        continue
    trs = (r or {}).get("transitions") or []
    print(f"  抽出 {len(trs)} 条：")
    real = 0
    for t in trs:
        m = str(t.get("method", "")).strip()
        ok = m.upper() in known
        real += 1 if ok else 0
        print(f"    {t.get('from')} --{m}--> {t.get('to')}"
              f"   {'✔ 方法' if ok else '✘ 非方法'}")
    print(f"  ⇒ method ∈ 真实方法集: {real}/{len(trs)}\n")
