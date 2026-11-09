# -*- coding: utf-8 -*-
"""DEPRECATED（2026-10-19）：已被 source_autoseeder.py（AutoSeeder 协议无关 query 检索）替代。

core/fused/protocol_patterns.py —— 协议状态机信号 pattern（协议 Profile 层）。

借鉴 ProtocolGPT 的 code_filter 思路：为每个协议硬编码「状态机信号」的正则，
用于从协议实现源码中定位状态机相关文件、消息处理函数、状态变量。

⚠️ 分层原则（重要）：
  - 本文件属于「协议 Profile 配置层」，与 core/fused/hub/registry、targets 同类；
  - 本文件【不属于】结构化知识中枢（derived/per_source、derived/spec/rtsp/norms）；
  - 因此「清空结构化知识中枢」时，本文件不受影响，不会被清理。

★ 协议范围（2026-10-31 kb 收敛至 3 协议后同步收敛）
  本表只保留**存活协议** rtsp / sip / smtp 的 pattern；
  已下线协议（dns / dtls / ftp / ssh / tls）的条目一并移除 ——
  它们对应的 kb 源、目标环境与语料都已删除，pattern 留着就是**无人消费的僵尸知识**，
  还会让读者误以为这些协议仍受支持（本项目的协议范围权威声明在 `kb/` 与
  `profiles/` 两处，不在本文件）。
  ★ 移除是**安全的**：`get_pattern()` 用 `.get(key, DEFAULT_PATTERN)` 兜底，
    传入已下线协议只会拿到通用兜底 pattern（**不抛异常**）；唯一 import 者
    `source_fsm.py` 只取 `get_pattern` 函数（不依赖具体条目）→ import 不受影响；
    且本表全仓库**零外部调用方、零测试引用**。
  ⇒ 未来若要恢复某协议，加回对应条目即可，无需改引擎。
  ⇒ 若将来做「配置层收敛」，正确做法是**整文件连同 `source_fsm.py` 退役**，
    而不是留一个 DEPRECATED 孤岛再逐条削字典。

设计（历史）: 协议无关的引擎（source_fsm.py）调用 get_pattern(protocol) 读取本配置，
按协议提取状态机信号，替代 source_fsm.py 里写死的通用正则。
换协议只改这里的 pattern，不改引擎。
"""
from __future__ import annotations

#: 协议 -> 状态机信号 pattern（存活协议：rtsp / sip / smtp）
#:   method_handler : 消息处理函数名正则（捕获组 = 消息类型/方法名）
#:   state_vars     : 状态变量名正则（状态线索）
#:   fsm_marker     : 状态机相关文件标记（用于过滤文件，ProtocolGPT code_filter 思路）
PROTOCOL_PATTERNS: dict[str, dict] = {
    # ---- RTSP / Live555（精确，已实测验证）----
    "rtsp": {
        "name": "Live555 (RTSP)",
        "method_handler": r"handleCmd_(\w+)",
        # 会话/流状态载体（RTSPClientSession 成员，源码实测存在）：
        #   fStreamStates/fNumStreamStates = 每 track 流状态；fOurServerMediaSession = 会话是否建立；
        #   fLastSessionId/fOurSessionId = SETUP 后的会话 ID；fCurrentCSeq = 有状态会话请求序号
        "state_vars": r"\bf(?:StreamStates|NumStreamStates|OurServerMediaSession|LastSessionId|OurSessionId|CurrentCSeq)\b",
        "fsm_marker": r"(?:handleCmd_|StreamStates|OurServerMediaSession)",
    },
    # ---- SIP / Kamailio（通用约定）----
    "sip": {
        "name": "Kamailio (SIP)",
        "method_handler": r"(?:handle|process)_(\w+)",
        "state_vars": r"\b\w*(?:state|State)\w*\b",
        "fsm_marker": r"(?:state|transaction|dialog)",
    },
    # ---- SMTP / Exim（通用约定）----
    "smtp": {
        "name": "Exim (SMTP)",
        "method_handler": r"(?:smtp|handle|process)_(\w+)",
        "state_vars": r"\b(?:smtp_state|\w*state)\b",
        "fsm_marker": r"(?:smtp|state)",
    },
}

#: 未知协议时的默认兜底 pattern（通用状态机命名约定）
DEFAULT_PATTERN: dict = {
    "name": "unknown",
    "method_handler": r"(?:handle|process|do)_(\w+)",
    "state_vars": r"\b\w*(?:state|State)\w*\b",
    "fsm_marker": r"(?:state|fsm|machine)",
}


def get_pattern(protocol: str) -> dict:
    """按协议名取状态机信号 pattern；未知/已下线协议返回默认兜底。

    ★ 已下线协议（dns/dtls/ftp/ssh/tls）走 `DEFAULT_PATTERN` 兜底，**不抛异常**
      （`.get()` 语义）—— 调用方无需为"协议不存在"写分支。
    """
    key = (protocol or "").lower()
    return PROTOCOL_PATTERNS.get(key, DEFAULT_PATTERN)


def list_protocols() -> list[str]:
    """列出已硬编码的协议名（= 存活协议：rtsp / sip / smtp）。"""
    return sorted(PROTOCOL_PATTERNS.keys())
