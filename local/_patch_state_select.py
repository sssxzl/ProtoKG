# -*- coding: utf-8 -*-
"""byte-patch：状态机择一改为「规范原生优先、骨架兜底」。

按铁律 #5：read_bytes → 唯一匹配断言 → write_bytes。
★ 用文本（UTF-8）而非字节转义写补丁内容，避免转义出错。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "fused" / "downstream" / "rag_seedgen.py"

OLD1 = 'SKELETON_AUTHORITY = "profile"\n'

NEW1 = '''SKELETON_AUTHORITY = "profile"

#: ★ 2026-11-05：**规范原生**状态机的 authority（直接抽自 RFC 文本）。
#:   ★ 已知：骨架的 ``target_state`` 实为 **source 源**派生（``skeleton.json``
#:     的 ``origin.source`` 含 ``target_state``）—— 检查出的思想源头是
#:     ``source_autoseeder.py`` 提示词里硬塞的 **SIP 式状态名范例**
#:     ⇒ 它的状态名不一定属于该协议的规范。
RFC_AUTHORITY = "rfc"
'''

OLD2 = '''def _select_active_transitions(by_source: dict[str, list]) -> list:
    """从「各源的状态机」里选出**当前采用**的一套（本期 = 协议骨架那套）。
'''

NEW2 = '''def _select_active_transitions(by_source: dict[str, list]) -> list:
    """从「各源的状态机」里选出**当前采用**的一套。

    ★★ 2026-11-05 修正（依据：``local/状态机消费口径对照实验报告.md``）：
      旧实现是「**骨架优先**」⇒ RTSP 采用协议骨架那 38 条边，而它的 6 个状态名
      （Idle/Registered/Confirmed/Invited/Paused/Terminated）在 RFC 2326 原文中
      **0/6 命中** —— 那是 ``source_autoseeder`` 提示词里硬塞的 **SIP 式范例**
      （``core/fused/source_autoseeder.py:182,203``）⇒ 双重危害：
        ① **污染 prompt**：LLM 照抄这些状态名生成种子；
        ② **校验器失效**：状态名对不上 ⇒ ``validate_seed`` 的 ``trans_by_from``
           取不到 from 态 ⇒「有知识才校验」分支**永不触发** ⇒ 状态机对 RTSP
           而言是**死知识**。
      实测（4 组 × 3 次 LLM + 外部真值 = RFC A.1+A.2 共 14 条边）：

        | 组                    | kept | 精确率 | 召回率 |
        | 现状(骨架 38)         |16.33 |  0.0%  |  0.0%  |
        | RFC 原生(14, 不裁)    |10.67 | 100.0%  | 93.3%  |
        | RFC 原生(14, 裁后12)  | 7.67 | 100.0%  | 98.3%  |
        | 两套合并(52)          | 2.00 |  0.0%  |  0.0%  |

      ⇒ **规范原生优先**，且**绝不合并两套**（合并 ⇒ LLM 在两套状态名间摇摆
        ⇒ 精确率/召回率双 0 ⇒ 是灾难）。

    ★ 规则（**协议无关**，靠 authority 优先级自动适配）：
      ① 有**规范原生**（authority=rfc = 直接抽自 RFC 文本）的那套 ⇒ 用它；
      ② 否则用**协议骨架**（authority=profile）；
      ③ 都没有 ⇒ 全部去重合并（兜底）。
      ⇒ 只有真正开了 ``enable_transitions`` **且** RFC 源确实抽到状态机的协议
        才会走第 ① 步（当前仅 rtsp）；其余协议（sip/smtp 尚无 RFC 源状态机）
        行为**逐字节不变**。

    ★ 连带影响（已实测，``edge_cover`` 纯确定性、零 LLM 成本）：
      rtsp 的 ``edge_cover`` 种子 5 → 3 条。看似变少，但**多出来的那 2 条状态
      路径含 Idle/Registered/… ⇒ 真实 RTSP 服务器根本没有这些状态 ⇒ 那 2 条
      种子在协议层面**不可实现** ⇒ 净收益为正。
      ``message_instances`` 的键含状态名 ⇒ 切到 RFC 后骨架那套实例查不到
      （字段实例退化；``RECORD`` 无实例 ⇒ 该边消息无字段，**已知缺陷**，
      全源模式下因 ``allowed_methods`` 不含 RECORD 会自动裁掉该边）。
    """
'''

OLD3 = '''    chosen = by_source.get(SKELETON_AUTHORITY) or []
    if not chosen:
        chosen = [t for rows in by_source.values() for t in rows]
    return sorted(set(chosen))'''

NEW3 = '''    for _auth in (RFC_AUTHORITY, SKELETON_AUTHORITY):
        _chosen = by_source.get(_auth) or []
        if _chosen:
            return sorted(set(_chosen))
    return sorted({t for rows in by_source.values() for t in rows})'''


def main() -> None:
    raw = TARGET.read_bytes()
    text = raw.decode("utf-8")
    for name, old, new in (("常量", OLD1, NEW1),
                           ("docstring", OLD2, NEW2),
                           ("函数体", OLD3, NEW3)):
        cnt = text.count(old)
        if cnt != 1:
            print(f"!! 补丁「{name}」匹配数 = {cnt}（应为 1）⇒ 中止", file=sys.stderr)
            raise SystemExit(1)
        text = text.replace(old, new, 1)
        print(f"  补丁「{name}」已应用")
    TARGET.write_bytes(text.encode("utf-8"))
    print(f"已写入 {TARGET}")
    ast.parse(TARGET.read_text(encoding="utf-8"))
    print("语法自检通过")


if __name__ == "__main__":
    main()
