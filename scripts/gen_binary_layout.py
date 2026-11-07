"""从**知识中枢**生成二进制布局段 ⇒ 写回 ``profile.raw_format``。

★ 为什么要这个脚本（2026-11-07）：
  「布局」是**知识**（来自 RFC 的位域图 / 选项表）⇒ 它已经在中枢里
  （aspect = ``binary_layout`` / ``option_layout``）。
  但**渲染**需要的是**渲染格式**（offset/length/type/code 的机器可读数组），
  放在 ``profile.raw_format`` 里最合适（与文本协议的 raw_format 对称）。

⇒ 本脚本 = 「中枢知识 → 渲染配置」的**单向同步**：
   · 读中枢的布局事实（可溯源到 RFC 行号）；
   · 写回 profile 的 ``binary_fields`` / ``binary_options``；
   · **不覆盖**手写的 ``type``（类型是渲染细节，RFC 里没有）。

★ 用法：
    E:/app/Anaconda3/python.exe scripts/gen_binary_layout.py --protocol dhcpv4
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: 字段名 → 渲染类型（RFC 里没有类型信息 ⇒ 这里是**渲染侧**的类型映射）
#: ★ 协议无关：按**字段名的语义**归类，不认协议名。
_TYPE_BY_NAME = {
    "op": "uint8", "htype": "uint8", "hlen": "uint8", "hops": "uint8",
    "xid": "uint32", "secs": "uint16", "flags": "uint16",
    "ciaddr": "ipv4", "yiaddr": "ipv4", "siaddr": "ipv4", "giaddr": "ipv4",
    "chaddr": "mac", "sname": "bytes", "file": "bytes",
    "magic_cookie": "uint32",
}

#: 选项名 → 渲染类型（按名称语义）
_OPT_TYPE_BY_NAME = {
    "subnet_mask": "ipv4", "router": "ipv4_list",
    "domain_name_servers": "ipv4_list", "host_name": "string",
    "requested_ip": "ipv4", "lease_time": "uint32",
    "server_identifier": "ipv4", "parameter_request_list": "bytes",
}


def _parse_layout(text: str) -> dict:
    out: dict = {}
    for part in str(text or "").split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k, v = k.strip(), v.strip()
        if k in ("offset", "length", "order", "code"):
            try:
                out[k] = int(v)
            except ValueError:
                pass
        else:
            out[k] = v
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", default="dhcpv4")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    proto = args.protocol

    from core import paths
    from core.fused.downstream import rag_seedgen as RS

    bundle = RS.assemble_bundle(RS.load_fact_views(proto), proto)
    headers = bundle.get("headers") or {}

    fields = []
    for name, info in headers.items():
        if not isinstance(info, dict):
            continue
        _bl = info.get("binary_layout")
        if not _bl:
            continue
        d = _parse_layout(_bl)
        # ★ 只认**位域图**给的 offset（``order`` 字段是位域图独有的）——
        #   定长字段通道（散文里的 "N octets"）**没有权威 offset**
        #   ⇒ 若混进来会挤占位置（实测 ``vend`` 抢在 magic cookie 前
        #   ⇒ magic cookie 被推到 @300，而正确位置是 @236）。
        if "offset" not in d or "order" not in d:
            continue
        fields.append({
            "name": name,
            "offset": d.get("offset", 0),
            "length": d.get("length", 1),
            "type": _TYPE_BY_NAME.get(name.lower(), "bytes"),
        })
    fields.sort(key=lambda f: f["offset"])

    # ★ **补位域图没画的固定字段**（真实缺口，实测踩到）：
    #   RFC 2131 §4.1 的位域图画到 ``file``（128 字节）就结束了，
    #   但真正的报文还有 **magic cookie（4 字节 @236）** ——
    #   它在 RFC 2132 §2 里单独规定（「the first four octets of the
    #   vendor information field have been assigned to the magic cookie」），
    #   **不在位域图里** ⇒ 只靠位域图 ⇒ 渲染出的 cookie 是 00000000（非法）。
    # ⇒ 判据（协议无关）：中枢 headers 桶里有该字段的 **syntax**
    #   （说明 RFC 描述了它）但**没有 binary_layout**（说明位域图没画）
    #   ⇒ 按「固定头末尾」追加。
    # ★ magic cookie 的位置（真实语义，实测踩到）：
    #   RFC 1542 的位域图里 @236 是 ``vend``（vendor 区，64 字节），
    #   而 RFC 2132 §2 规定「the **first four octets** of the vendor
    #   information field have been assigned to the magic cookie」
    #   ⇒ **magic cookie 在 vend 内部**（@236，长度 4），**不是** @300。
    #   ⇒ 判据：取「vend（vendor 区）」的 offset 作为 cookie 的 offset。
    _vend = next((f for f in fields if f["name"].lower() == "vend"), None)
    _cookie_at = _vend["offset"] if _vend else None
    for _name in ("magic_cookie",):
        _info = headers.get(_name)
        if not isinstance(_info, dict):
            continue
        if any(f["name"] == _name for f in fields):
            continue
        _syn = str(_info.get("syntax") or "")
        _m = re.search(r"(\d+)\s+(?:octet|byte)", _syn, re.IGNORECASE)
        if not _m or _cookie_at is None:
            continue
        fields.append({"name": _name, "offset": _cookie_at,
                       "length": int(_m.group(1)),
                       "type": _TYPE_BY_NAME.get(_name, "bytes")})
    fields.sort(key=lambda f: f["offset"])

    options = []
    for name, info in headers.items():
        if not isinstance(info, dict):
            continue
        _ol = info.get("option_layout")
        if not _ol:
            continue
        d = _parse_layout(_ol)
        options.append({
            "name": name,
            "code": d.get("code", 0),
            "type": _OPT_TYPE_BY_NAME.get(name.lower().replace(" ", "_"), "bytes"),
            "length": d.get("length", 0),
        })
    options.sort(key=lambda o: o["code"])

    print(f"[布局] {proto}：字段 {len(fields)} 个 / 选项 {len(options)} 个")
    for f in fields[:6]:
        print(f"    {f['name']:16s} offset={f['offset']:4d} length={f['length']:4d} "
              f"type={f['type']}")
    if args.dry_run:
        return 0

    pp = paths.target_profile(proto)
    data = json.loads(pp.read_text(encoding="utf-8"))
    fmt = data.setdefault("raw_format", {})
    fmt["byte_order"] = fmt.get("byte_order") or "network"
    fmt["binary_fields"] = fields
    fmt["binary_options"] = options
    data["note"] = (data.get("note", "") +
                     " ★ 2026-11-07：binary_fields/binary_options 由 "
                     "`scripts/gen_binary_layout.py` 从**中枢**（RFC 位域图/选项表）"
                     "自动生成 ⇒ 布局来源可溯源。")
    pp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8")
    print(f"[布局] 已写回 {pp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
