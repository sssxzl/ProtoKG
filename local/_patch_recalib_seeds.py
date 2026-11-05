# -*- coding: utf-8 -*-
"""byte-patch：rtsp 种子数期望值重标定（状态机择一修正后）。

★ 依据（实测，非估算）：
  协议级  A 32 / B 37 / C 37 / D 37   （原 86/91/91/91）
  env 级  A 32 / B 37 / C 37 / D 37   （原 75/80/80/80）
  ⇒ 减少来自基准层：edge_cover 5→2、generic_danger 25→8
    （状态机从骨架那 38 条换成 RFC 原生那 12 条 ⇒ 确定性层能构造的边更少）。
  ⇒ 其中**去掉了 9 条非法种子**（真值判定：Init 态下的 PAUSE×5、Ready 态下的
    PAUSE×3、Init 态下的 PLAY×1）⇒ 确定性层方法序列合法率 70% → 100%。
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "fused_hub" / "targets" / "rtsp" / "profile.json"

# ── env 级（第 56–82 行）──────────────────────────────────────────
OLD_ENV_A = '''            "dict": "base",
            "seeds": 75,
            "dict_tokens": 24'''
NEW_ENV_A = '''            "dict": "base",
            "seeds": 32,
            "dict_tokens": 24'''

OLD_ENV_BC = '''            "dict": "base",
            "seeds": 80,
            "dict_tokens": 24'''
NEW_ENV_BC = '''            "dict": "base",
            "seeds": 37,
            "dict_tokens": 24'''

OLD_ENV_C = '''            "dict": "targeted",
            "seeds": 80,
            "dict_tokens": 212'''
NEW_ENV_C = '''            "dict": "targeted",
            "seeds": 37,
            "dict_tokens": 212'''

OLD_NOTE = ('        "focus_group_note": "★ 批次 2.5 F9 + 2026-11-04 重标定（扩池 + ABNF '
            '派生字段 + P 侧受控类别 ⇒ ③层 +2 条约束边界候选）：env 档（可播会话子集）'
            '独立标定（协议级 86/91/91/91，env 级见本处）"')
NEW_NOTE = ('        "focus_group_note": "★ 2026-11-05 重标定（状态机择一改为'
            '「规范原生优先」）：骨架那 38 条 SIP 式状态名的边 ⇒ 换成 RFC 原生那 12 条'
            ' ⇒ 确定性层可构造的边更少（edge_cover 5→2、generic_danger 25→8）⇒ '
            '协议级与 env 级均降为 32/37/37/37。★ 其中去掉了 **9 条非法种子**'
            '（真值 = RFC 2326 A.1+A.2：Init 态下的 PAUSE×5、Ready 态下的 PAUSE×3、'
            'Init 态下的 PLAY×1）⇒ 确定性层方法序列合法率 70% → 100%。'
            '★ 规模下降的补偿路径：⑤ 变异层（LLM 字段级 action-sequence）可作为'
            '「性能优先」下的正当 LLM 用法。env 档（可播会话子集）独立标定"')

# ── 协议级（第 188–200 行）────────────────────────────────────────
OLD_PROTO_A = '''        "dict": "base",
        "seeds": 86,
        "dict_tokens": 24'''
NEW_PROTO_A = '''        "dict": "base",
        "seeds": 32,
        "dict_tokens": 24'''

OLD_PROTO_BCD = '''        "dict": "base",
        "seeds": 91,
        "dict_tokens": 24'''
NEW_PROTO_BCD = '''        "dict": "base",
        "seeds": 37,
        "dict_tokens": 24'''

OLD_PROTO_C = '''        "dict": "targeted",
        "seeds": 91,
        "dict_tokens": 223'''
NEW_PROTO_C = '''        "dict": "targeted",
        "seeds": 37,
        "dict_tokens": 223'''


def main() -> None:
    text = TARGET.read_bytes().decode("utf-8")
    # ★ 先做「协议级」（在 env 级之后出现）—— 用 replace 次数区分：
    #   env 级用 4 空格缩进，协议级用 8 空格缩进 ⇒ 字符串本身已区分开。
    for name, old, new, cnt in (
            ("协议级 A", OLD_PROTO_A, NEW_PROTO_A, 1),
            ("协议级 B/D", OLD_PROTO_BCD, NEW_PROTO_BCD, 2),
            ("协议级 C", OLD_PROTO_C, NEW_PROTO_C, 1),
            ("env 级 A", OLD_ENV_A, NEW_ENV_A, 1),
            ("env 级 B/D", OLD_ENV_BC, NEW_ENV_BC, 2),
            ("env 级 C", OLD_ENV_C, NEW_ENV_C, 1),
            ("标定说明", OLD_NOTE, NEW_NOTE, 1)):
        found = text.count(old)
        if found != cnt:
            print(f"!! 补丁「{name}」匹配数 = {found}（应为 {cnt}）⇒ 中止", file=sys.stderr)
            raise SystemExit(1)
        text = text.replace(old, new)
        print(f"  补丁「{name}」已应用（{cnt} 处）")
    TARGET.write_bytes(text.encode("utf-8"))
    # 自检：JSON 合法 + 读回数值
    d = json.loads(TARGET.read_text(encoding="utf-8"))
    fg = d["seedgen"]["focus_group"]
    env = d["seedgen"]["environments"]["rq2-live555"]["focus_group"]
    print("协议级:", {k: v["seeds"] for k, v in fg.items()})
    print("env 级:", {k: v["seeds"] for k, v in env.items()})


if __name__ == "__main__":
    main()
