# -*- coding: utf-8 -*-
"""source_autoseeder 提示词改造 · 对照试点（只读，不改生产代码）。

★ 动因：`core/fused/source_autoseeder.py:202-204` 的状态锚点提示词里**硬塞了
  SIP 的状态名范例**（Idle/Registered/Invited/Confirmed）+ SIP 的语义举例
  （空闲/已注册/通话建立/通话中/通话结束）⇒ LLM 给 **RTSP** 也编出同一套
  ⇒ 骨架那 38 条边的 6 个状态名在 RFC 2326 原文 **0/6 命中**。

★ 前提核实（已做）：live555 的 RTSP 实现源码里**没有任何规范会话状态名**
  （Init/Ready/Playing/Recording 零命中；全部命中是 Initialize/isInitial401
  这类无关词）⇒ **源码逆向本质上无法产出规范原生状态名**
  ⇒ 修根因的收益上限 = 「不再套用 SIP 的假名」，不是「产出规范名」。

★ 本试点测两件事：
  ① 旧提示词的真实产出（绕过缓存重跑）—— 复现 SIP 式状态名；
  ② 新提示词（协议无关 + 「状态名必须来自代码里真实出现的标识」+「宁缺勿滥」）
     的真实产出 —— 看是否摆脱 SIP 式命名、以及会不会产出 0 条。

用法：E:/app/Anaconda3/python.exe local/_pilot_source_prompt.py [协议]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths                                      # noqa: E402
from core.fused.source_retrieval import retrieve_state_relevant_code  # noqa: E402
from core.llm import DeepSeekClient                         # noqa: E402

#: 新版状态锚点（协议无关 + 宁缺勿滥）
NEW_ANCHOR = (
    "请围绕上述方法枚举该协议的**会话状态**，要求：\n"
    "1) 状态名必须**从代码片段里真实出现的状态标识**推导（枚举名 / 成员变量名 /\n"
    "   字符串常量 / 状态切换分支的标签）；代码片段里找不到状态标识时，\n"
    "   **不要臆造状态名**（宁缺勿滥 ⇒ 可以不产出状态）。\n"
    "2) **不要套用其它协议的状态名**（例如不要用 SIP 的 Idle/Registered/Trying/\n"
    "   Unauthorized，除非它们确实出现在本代码片段里）。\n"
    "3) 状态名用**本协议自身**的术语，不要用响应码（200/401/404）当状态名。\n"
    "4) 若代码里有多个层次的状态（连接级 / 会话级），只取**会话级**那一层。"
)

#: 中间版锚点（**给来源约束，不给任何具体名字**）
#: ★ 提示词设计经验：给 LLM 任何具体名字（正例或反例）都可能被照抄
#:   ⇒ 「宁缺勿滥」版实测产出崩塌（1 个状态且是整句话）；
#:   ⇒ 正确做法是约束**来源**（代码里的标识 / 本协议自己的术语），
#:     而不是列举名字。
MID_ANCHOR = (
    "请围绕上述方法枚举该协议的**会话状态**，要求：\n"
    "1) 状态名应从**代码片段里出现的状态标识**，或**该协议方法的会话阶段**推导\n"
    "   （例如按该协议自己的请求/方法来命名阶段）；\n"
    "2) **必须使用本协议自身的术语**，不要借用其它协议的状态命名习惯；\n"
    "3) 不要用响应码（200/401/404）当状态名；\n"
    "4) 状态名用**单个词或一个词组**（如 Streaming / SessionEstablished /\n"
    "   Teardown），**不要用整句话**当状态名；\n"
    "5) 状态数量控制在 4~12 个，按会话推进顺序排列。"
)


def run(protocol: str, prompt_text: str, llm) -> dict:
    src_dir = paths.kb_source_dir(protocol, "source")
    blocks = retrieve_state_relevant_code(src_dir, protocol)
    out = {"states": [], "methods": [], "transitions": []}
    for b in blocks:
        try:
            r = llm.chat_json(
                system="你输出 JSON。",
                user=prompt_text.format(
                    protocol=protocol.upper(),
                    message_hint="",
                    states="（无）", methods="（无）",
                    code_block=b.get("text", "")[:6000]),
                temperature=0.0, max_tokens=3000)
        except Exception as exc:  # noqa: BLE001
            print(f"    [LLM 失败] {exc}", file=sys.stderr)
            continue
        if not isinstance(r, dict):
            continue
        out["states"].extend(r.get("states") or [])
        out["methods"].extend(r.get("methods") or [])
        out["transitions"].extend(r.get("transitions") or [])
    return out


def summarize(tag: str, res: dict, text: str) -> None:
    states = sorted({str(s.get("name", "")).strip()
                     for s in res["states"] if isinstance(s, dict)})
    trans = res["transitions"]
    hit = [s for s in states if s and s in text]
    print(f"\n── {tag}")
    print(f"   状态 {len(states)} 个: {states}")
    print(f"   转移 {len(trans)} 条")
    print(f"   状态名在 RFC 原文命中: {len(hit)}/{len(states)}  {hit}")
    return states


def main() -> None:
    protocol = sys.argv[1] if len(sys.argv) > 1 else "rtsp"
    d = paths.kb_source_dir(protocol, "rfc")
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                     for p in sorted(d.glob("*.txt")))
    llm = DeepSeekClient()

    from core.fused import source_autoseeder as SA
    old_prompt = SA._PROMPT_BLOCK_ANALYSIS
    # ★ 旧版：把硬编码的 SIP 状态锚点插进去（复现现状）
    old_anchor = SA._load_state_anchor(protocol)
    old_full = old_prompt.replace("{message_hint}", old_anchor)

    print("=" * 76)
    print(f"source_autoseeder 提示词对照试点  协议={protocol}")
    print("=" * 76)
    old_res = run(protocol, old_full, llm)
    old_states = summarize("旧提示词（现状：硬编码 SIP 状态名范例）", old_res, text)

    new_full = old_prompt.replace("{message_hint}", NEW_ANCHOR)
    new_res = run(protocol, new_full, llm)
    new_states = summarize("新提示词（协议无关 + 宁缺勿滥）", new_res, text)

    mid_full = old_prompt.replace("{message_hint}", MID_ANCHOR)
    mid_res = run(protocol, mid_full, llm)
    mid_states = summarize("中间版（给来源约束，不给名字清单）", mid_res, text)

    print()
    print("=" * 76)
    print("对照")
    print("=" * 76)
    print(f"  旧状态名集合: {old_states}")
    print(f"  严版状态名集合: {new_states}")
    print(f"  中间版状态名集合: {mid_states}")
    for tag, st in (("旧", old_states), ("严版", new_states),
                    ("中间版", mid_states)):
        hit = [s for s in st if s and s in text]
        print(f"  {tag}: {len(st)} 个状态, RFC 命中 {len(hit)}/{len(st)}"
              f" = {len(hit) / len(st):.0%}" if st else f"  {tag}: 无")
    out = {
        "protocol": protocol,
        "old": {"states": old_states, "n_transitions": len(old_res["transitions"])},
        "strict": {"states": new_states, "n_transitions": len(new_res["transitions"])},
        "mid": {"states": mid_states, "n_transitions": len(mid_res["transitions"])},
    }
    p = Path(__file__).resolve().parent / f"_pilot_source_prompt_{protocol}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {p}")


if __name__ == "__main__":
    main()
