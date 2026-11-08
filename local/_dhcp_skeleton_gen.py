"""生成 DHCPv4 的 ``skeleton.json``（协议骨架资产）。

★ **不改任何生产代码** —— 本脚本只**生成资产文件**
  （``fused_hub/targets/dhcpv4/skeleton.json``），build_hub 会照常把它物化进中枢。

★ 骨架内容全部**来自 RFC 2131 §3.1 的 ASCII 时序图**（kb/dhcpv4/spec/rfc2131.txt
  第 788–830 行），逐条对应：

    Server          Client          Server
                  v               v               v
      _____________/|\____________  |
     |/DHCPDISCOVER | DHCPDISCOVER  |
                  |\             |  ____________/ |
                  | \________    | /DHCPOFFER     |
                  | DHCPOFFER\   |/               |
                  |           \  |                |
                  |     Selects configuration     |
                  | _____________/|\____________  |
                  |/ DHCPREQUEST  |  DHCPREQUEST\ |
                  |               |     Commits configuration
                  |               | _____________/|
                  |               |/ DHCPACK      |
                  |               |               |
                  |    Initialization complete    |
                  |               |               |
                  |      Graceful shutdown        |
                  |               | |\ ____________ |
                  |               | DHCPRELEASE  \|
                  |               |               |        Discards lease

⇒ 状态机边（4 条主路径 + 1 条异常路径）：
    INIT   --DHCPDISCOVER--> SELECTING
    SELECTING --DHCPOFFER--> OFFERED
    OFFERED --DHCPREQUEST--> REQUESTING
    REQUESTING --DHCPACK--> BOUND
    REQUESTING --DHCPNAK-->  INIT   （地址冲突，RFC 2131 §3.1 步骤 4）
    BOUND   --DHCPRELEASE--> INIT   （优雅关闭，§3.1 末段）

★ 为什么需要骨架（实测结论）：
  DHCP 的 36 份 RFC 里**一次都没出现 "state machine"** 字样 ⇒
  `_RE_STATE_MACHINE_HINT`（= ``state\\s+machines?``）命中 0 ⇒
  LLM 状态机通道**无从下手** ⇒ transitions = 0 ⇒ seedgen 报
  「无状态机转移，无法生成种子」。
  ⇒ 骨架是**唯一**能提供 transitions 的来源（rtsp/sip/smtp 同理）。
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROTO = "dhcpv4"

# ---- ① 状态机边（from RFC 2131 §3.1 ASCII 时序图）----
TRANSITIONS = [
    ("INIT", "DHCPDISCOVER", "SELECTING"),
    ("SELECTING", "DHCPOFFER", "OFFERED"),
    ("OFFERED", "DHCPREQUEST", "REQUESTING"),
    ("REQUESTING", "DHCPACK", "BOUND"),
    ("REQUESTING", "DHCPNAK", "INIT"),
    ("BOUND", "DHCPRELEASE", "INIT"),
]

# ---- ② 报文实例（每条边上的报文字段；来自 RFC 2131 §4.1 / RFC 951 报文格式）----
# DHCP 是**二进制**协议 ⇒ 字段是 BOOTP 头字段，不是文本头。
# 这里给「字段名 + 值」，值取自 RFC 的默认值/示例。
INSTANCE_FIELDS = {
    "DHCPDISCOVER": [("op", "1"), ("htype", "1"), ("hlen", "6"),
                     ("hops", "0"), ("xid", "0x3903F326"),
                     ("secs", "0"), ("flags", "0x8000"),
                     ("ciaddr", "0.0.0.0"), ("yiaddr", "0.0.0.0"),
                     ("siaddr", "0.0.0.0"), ("giaddr", "0.0.0.0"),
                     ("chaddr", "00:11:22:33:44:55"),
                     ("magic_cookie", "0x63825363")],
    "DHCPOFFER": [("op", "2"), ("htype", "1"), ("hlen", "6"),
                  ("hops", "0"), ("xid", "0x3903F326"),
                  ("secs", "0"), ("flags", "0x8000"),
                  ("ciaddr", "0.0.0.0"), ("yiaddr", "192.168.1.10"),
                  ("siaddr", "0.0.0.0"), ("giaddr", "0.0.0.0"),
                  ("chaddr", "00:11:22:33:44:55"),
                  ("magic_cookie", "0x63825363")],
    "DHCPREQUEST": [("op", "1"), ("htype", "1"), ("hlen", "6"),
                    ("hops", "0"), ("xid", "0x3903F326"),
                    ("secs", "0"), ("flags", "0x8000"),
                    ("ciaddr", "0.0.0.0"), ("yiaddr", "0.0.0.0"),
                    ("siaddr", "0.0.0.0"), ("giaddr", "0.0.0.0"),
                    ("chaddr", "00:11:22:33:44:55"),
                    ("magic_cookie", "0x63825363")],
    "DHCPACK": [("op", "2"), ("htype", "1"), ("hlen", "6"),
                ("hops", "0"), ("xid", "0x3903F326"),
                ("secs", "0"), ("flags", "0x8000"),
                ("ciaddr", "0.0.0.0"), ("yiaddr", "192.168.1.10"),
                ("siaddr", "0.0.0.0"), ("giaddr", "0.0.0.0"),
                ("chaddr", "00:11:22:33:44:55"),
                ("magic_cookie", "0x63825363")],
    "DHCPNAK": [("op", "2"), ("htype", "1"), ("hlen", "6"),
                ("hops", "0"), ("xid", "0x3903F326"),
                ("secs", "0"), ("flags", "0x8000"),
                ("ciaddr", "0.0.0.0"), ("yiaddr", "0.0.0.0"),
                ("siaddr", "0.0.0.0"), ("giaddr", "0.0.0.0"),
                ("chaddr", "00:11:22:33:44:55"),
                ("magic_cookie", "0x63825363")],
    "DHCPRELEASE": [("op", "1"), ("htype", "1"), ("hlen", "6"),
                    ("hops", "0"), ("xid", "0x3903F326"),
                    ("secs", "0"), ("flags", "0x0000"),
                    ("ciaddr", "192.168.1.10"), ("yiaddr", "0.0.0.0"),
                    ("siaddr", "0.0.0.0"), ("giaddr", "0.0.0.0"),
                    ("chaddr", "00:11:22:33:44:55"),
                    ("magic_cookie", "0x63825363")],
}


#: BOOTP 固定头字段（RFC 951 §3 + RFC 2131 §4.1）—— 名称与 RFC 一致
BOOTP_FIELDS = {
    "op": "1 octet (1=BOOTREQUEST, 2=BOOTREPLY)",
    "htype": "1 octet (hardware address type)",
    "hlen": "1 octet (hardware address length)",
    "hops": "1 octet (relay agent hops)",
    "xid": "4 octets (transaction id)",
    "secs": "2 octets (seconds since client began address acquisition)",
    "flags": "2 octets (broadcast flag + reserved)",
    "ciaddr": "4 octets (client IP address)",
    "yiaddr": "4 octets (your IP address)",
    "siaddr": "4 octets (server IP address)",
    "giaddr": "4 octets (relay agent IP address)",
    "chaddr": "16 octets (client hardware address)",
    "sname": "64 octets (server host name)",
    "file": "128 octets (boot file name)",
    "magic_cookie": "4 octets (99.130.83.99)",
    "options": "variable (option code + length + data)",
}

#: 取值枚举（供 ⑤ 层值域变异；来源 = RFC 2131 §4.1 / RFC 951）
_VALUE_ENUM = {
    "op": ["1", "2"],
    "htype": ["1", "6"],
    "hlen": ["6", "16"],
    "hops": ["0", "1"],
    "secs": ["0", "1", "65535"],
    "flags": ["0x0000", "0x8000"],
    "ciaddr": ["0.0.0.0", "192.168.1.10"],
    "yiaddr": ["0.0.0.0", "192.168.1.10", "192.168.1.20"],
    "siaddr": ["0.0.0.0", "192.168.1.1"],
    "giaddr": ["0.0.0.0", "192.168.1.2"],
    "chaddr": ["00:11:22:33:44:55", "ff:ff:ff:ff:ff:ff"],
    "magic_cookie": ["0x63825363"],
}


def _subj(t: str, name: str) -> dict:
    return {"type": t, "name": name, "qualifiers": {}, "path": []}


def _fid(protocol: str, fk: dict) -> str:
    from core.fused.canonical import canonical_serialize, compute_fact_id
    return compute_fact_id(fk)


def _cid(claim_value: dict, epistemic: str) -> str:
    from core.fused.canonical import canonical_serialize
    raw = canonical_serialize(claim_value) + epistemic.encode("utf-8")
    return "c2_" + hashlib.sha256(raw).hexdigest()[:16]


def build() -> dict:
    facts: list[dict] = []

    # ---- 状态机边 ----
    for frm, mth, to in TRANSITIONS:
        qual = {"source": _subj("state", frm),
                "target": _subj("state", to),
                "method": _subj("method", mth)}
        fk = {"protocol": PROTO, "version": "1.0",
              "subject": {"type": "relation", "name": "transitions_to",
                          "qualifiers": qual, "path": []},
              "aspect": "target_state",
              "condition": {"type": "always"}}
        fid = _fid(PROTO, fk)
        val = {"type": "text", "data": to}
        facts.append({
            "fact_key": fk, "resolution": None,
            "all_claims": [{
                "claim_id": _cid(val, "descriptive"),
                "fact_id": fid, "value": val,
                "epistemic_type": "descriptive",
                "authority": "profile",
                "evidence_summary": [
                    "profile:profile.transitions_to.%s.%s.%s" % (frm, mth, to)],
                "confidence": None,
            }],
        })

    # ---- 报文实例（每条边）----
    for frm, mth, to in TRANSITIONS:
        fields = INSTANCE_FIELDS.get(mth, [])
        qual = {"source": _subj("state", frm),
                "target": _subj("state", to),
                "method": _subj("method", mth)}
        fk = {"protocol": PROTO, "version": "1.0",
              "subject": {"type": "relation", "name": "transitions_to",
                          "qualifiers": qual, "path": []},
              "aspect": "message_instance",
              "condition": {"type": "always"}}
        fid = _fid(PROTO, fk)
        # ★ value 必须是 **dict** 且含 ``fields`` 列表
        #   （rag_seedgen 的 message_instance 分支要求
        #    ``isinstance(val, dict)`` ∧ ``val["fields"]`` 是
        #    ``[{"name":..., "value":...}]``）⇒ 用 text 字符串会**静默丢失**实例。
        val = {"type": "struct",
               "data": {"fields": [{"name": k, "value": v}
                                   for k, v in fields]}}
        facts.append({
            "fact_key": fk, "resolution": None,
            "all_claims": [{
                "claim_id": _cid(val, "descriptive"),
                "fact_id": fid, "value": val,
                "epistemic_type": "descriptive",
                "authority": "profile",
                "evidence_summary": [
                    "profile:profile.message_instance.%s.%s.%s" % (frm, mth, to)],
                "confidence": None,
            }],
        })

    # ---- ③ BOOTP 头字段（进 headers 桶 ⇒ `_known` 认识它们）----------------
    #   ★ 为什么必须加：`_apply_instance_fields` 的 `known_fields` 来自
    #     **headers 桶**（`{k.lower() for k in headers}`）⇒ 若 BOOTP 字段
    #     （op/htype/xid/…）不在 headers 桶里 ⇒ 实例字段**全部**被当
    #     「未知字段」⇒ 走 argument 分支 ⇒ 报文头全丢、argument 变成 op 的值。
    #   ★ DHCP 是**二进制**协议 ⇒ 字段是 BOOTP 固定头字段（不是文本头）。
    #     依据：RFC 951（BOOTP 报文格式）+ RFC 2131 §4.1。
    for _fname, _fsyntax in BOOTP_FIELDS.items():
        fk = {"protocol": PROTO, "version": "1.0",
              "subject": {"type": "header", "name": _fname,
                          "qualifiers": {}, "path": []},
              "aspect": "syntax",
              "condition": {"type": "always"}}
        fid = _fid(PROTO, fk)
        val = {"type": "text", "data": _fsyntax}
        facts.append({
            "fact_key": fk, "resolution": None,
            "all_claims": [{
                "claim_id": _cid(val, "descriptive"),
                "fact_id": fid, "value": val,
                "epistemic_type": "descriptive",
                "authority": "profile",
                "evidence_summary": ["profile:profile.header.syntax.%s" % _fname],
                "confidence": None,
            }],
        })
        # 取值枚举（value_enum）⇒ 供 ⑤ 层做值域变异
        _vals = _VALUE_ENUM.get(_fname)
        if _vals:
            fk2 = {"protocol": PROTO, "version": "1.0",
                   "subject": {"type": "header", "name": _fname,
                               "qualifiers": {}, "path": []},
                   "aspect": "value_enum",
                   "condition": {"type": "always"}}
            fid2 = _fid(PROTO, fk2)
            val2 = {"type": "text", "data": _vals}
            facts.append({
                "fact_key": fk2, "resolution": None,
                "all_claims": [{
                    "claim_id": _cid(val2, "descriptive"),
                    "fact_id": fid2, "value": val2,
                    "epistemic_type": "descriptive",
                    "authority": "profile",
                    "evidence_summary": [
                        "profile:profile.header.value_enum.%s" % _fname],
                    "confidence": None,
                }],
            })

    return {
        "protocol": PROTO,
        "note": ("DHCPv4 协议骨架（2026-11-07 首轮接入手工提炼）。"
                 "★ 全部内容来自 **RFC 2131 §3.1 的 ASCII 时序图**"
                 "（kb/dhcpv4/spec/rfc2131.txt）+ RFC 951 的 BOOTP 报文格式。"
                 "★ **为什么必须手工**：36 份 DHCP RFC 里**一次都没出现 "
                 "\"state machine\" 字样** ⇒ LLM 状态机通道命中 0 ⇒ "
                 "transitions=0 ⇒ 无法生成种子（骨架是唯一来源）。"
                 "★ DHCP 是**二进制**协议：实例字段是 BOOTP 头字段"
                 "（op/htype/hlen/xid/flags/ciaddr/…/magic_cookie），"
                 "不是文本头 ⇒ 落盘走 raw_writers 的「其他」分支。"),
        "aspects": ["target_state", "message_instance", "syntax", "value_enum"],
        "origin": {"source": ["message_instance", "target_state"],
                   "traffic": [],
                   "profile": ["syntax", "value_enum"]},
        "fact_count": len(facts),
        "facts": facts,
    }


def main() -> int:
    sk = build()
    out = ROOT / "fused_hub" / "targets" / PROTO / "skeleton.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="").write(
        json.dumps(sk, ensure_ascii=False, indent=2) + "\n")
    print("  ✓ 已生成 %s（%d 条 facts）" % (out, sk["fact_count"]))
    print("     状态机边: %d | 报文实例: %d" % (
        len(TRANSITIONS), len(TRANSITIONS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
