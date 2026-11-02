# -*- coding: utf-8 -*-
"""core/fused/traffic_extractor.py —— 从数据流量目录抽取 traffic norm（AutoSeeder 式）。

对应 LLM-Boofuzz 的「LLM 解析真实流量提取协议信息」，本模块做确定性 rule 部分：
读每个 run 的 client.log（完整会话文字）+ rtsp.csv（结构化方法序列），抽取 6 种
kind 的 traffic norm，喂给 traffic.py 的 traffic_norm_to_facts → observed fact。

6 种 kind（对齐 traffic.py 的解析器）:
  message        方法存在性（实际调用 ∪ 服务器声明 Public 头）→ method + existence
  state_machine  观测到的方法序列（实际调用顺序）             → 相邻方法对
  field          字段出现次数 + 取值样本                      → header + occurrence/value_enum
  outcome        响应码分布                                   → status + occurrence
  protocol       传输类型                                     → protocol + value_enum
  actor          端口                                         → actor + value_enum

脱敏：Authorization 的 username/nonce/response 替换为占位符，避免凭据泄露进 fact。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from core import paths

#: 通用 header 行正则（Key: value，多数文本协议通用，协议无关）
_RE_HEADER = re.compile(r"^([A-Za-z][A-Za-z-]*):\s*(.+)$")

#: 流量日志格式默认 schema（通用层零协议内置）。
#: 协议特定的日志格式（请求行/响应行/Public 头正则、日志文件名、csv 字段名）
#: 必须由 profile.json 的 traffic_schema 显式声明，换协议只换数据不换代码。
_DEFAULT_TRAFFIC_SCHEMA = {
    "log_files": [],           # 日志文件名（如 ["client.log", "rtsp.csv"]）
    "request_pattern": "",     # 请求行正则（如 "^Sending request:\\s+(\\w+)"）
    "public_pattern": "",      # 服务器声明方法头（如 "^Public:\\s*(.+)$"）
    "response_pattern": "",    # 响应行正则（如 "^RTSP/1\\.0\\s+(\\d+)"）
    "header_pattern": r"^([A-Za-z][A-Za-z-]*):\s*(.+)$",  # header 行（通用默认）
    "csv_fields": {},          # csv 字段名映射（如 {"method": "rtsp.method", "status": "rtsp.status"}）
}


def _load_traffic_schema(protocol: str) -> dict:
    """从 profile.json 读 traffic_schema，返回协议特定日志格式配置（通用层默认空）。

    profile.json 的 traffic_schema 结构（协议特定，通用层零内置）：
      "traffic_schema": {
        "log_files": ["client.log", "rtsp.csv"],
        "request_pattern": "^Sending request:\\\\s+(\\\\w+)",
        "public_pattern": "^Public:\\\\s*(.+)$",
        "response_pattern": "^RTSP/1\\\\.0\\\\s+(\\\\d+)",
        "csv_fields": {"method": "rtsp.method", "status": "rtsp.status"}
      }
    """
    cfg = dict(_DEFAULT_TRAFFIC_SCHEMA)
    cfg["log_files"] = []
    cfg["csv_fields"] = {}
    prof = paths.target_profile(protocol)
    if not prof.exists():
        return cfg
    try:
        import json
        data = json.loads(prof.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return cfg
    ts = data.get("traffic_schema")
    if not isinstance(ts, dict):
        return cfg
    for key in ("request_pattern", "public_pattern", "response_pattern",
                "header_pattern"):
        if ts.get(key):
            cfg[key] = str(ts[key])
    if isinstance(ts.get("log_files"), list):
        cfg["log_files"] = [str(x) for x in ts["log_files"]]
    if isinstance(ts.get("csv_fields"), dict):
        cfg["csv_fields"] = {str(k): str(v) for k, v in ts["csv_fields"].items()}
    return cfg


def _sanitize_auth(value: str) -> str:
    """Digest 认证脱敏：username/nonce/response → 占位符（realm 非敏感保留）。"""
    value = re.sub(r'username="[^"]*"', 'username="<user>"', value)
    value = re.sub(r'nonce="[^"]*"', 'nonce="<nonce>"', value)
    value = re.sub(r'response="[^"]*"', 'response="<response>"', value)
    return value


def _norm(run_id: str, kind: str, name: str, content: str,
          protocol: str, source: str, variant: str = "") -> dict:
    """构造一条 traffic norm（字段对齐 traffic.py 的解析器 + 溯源）。

    variant 用于区分同一 (kind, name) 下的多种 norm（如 field 的 occurrence 与
    samples 两条），避免 norm_id 冲突在去重时互相吞并。
    """
    norm_id = f"traffic.{kind}.{name}"
    if variant:
        norm_id += f".{variant}"
    return {
        "norm_id": norm_id,
        "kind": kind,
        "name": name,
        "content": content,
        "kb_source_type": "traffic_raw",
        "source": f"file:{source}#{run_id}",
        "protocol": protocol,
    }


def _compile_schema_re(schema: dict) -> dict:
    """把 schema 的 pattern 字符串编译成正则（空 pattern → None 表示不抽该行）。"""
    out: dict[str, Optional[re.Pattern]] = {}
    for key in ("request", "public", "response", "header"):
        pat = schema.get(f"{key}_pattern")
        out[key] = re.compile(pat) if pat else None
    return out


def _extract_client_log(log_path: Path, run_id: str, protocol: str,
                        schema: dict) -> list[dict]:
    """从文本日志抽取 message/state_machine/outcome/field norm（正则来自 schema）。"""
    re_ = _compile_schema_re(schema)
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    methods: list[str] = []          # 实际调用序列（按出现顺序）
    public: list[str] = []           # 服务器声明（Public 头等）
    status: dict[str, int] = {}      # 响应码 → 次数
    fields: dict[str, set] = {}      # 字段名 → 取值集合

    for line in text.splitlines():
        line = line.strip()
        if re_["request"]:
            m = re_["request"].match(line)
            if m:
                methods.append(m.group(1).upper())
                continue
        if re_["public"]:
            m = re_["public"].match(line)
            if m:
                public = [x.strip().upper() for x in m.group(1).split(",")
                          if x.strip()]
                continue
        if re_["response"]:
            m = re_["response"].match(line)
            if m:
                code = m.group(1)
                status[code] = status.get(code, 0) + 1
                continue
        if re_["header"]:
            m = re_["header"].match(line)
            if m:
                key, value = m.group(1), m.group(2).strip()
                if key.lower() == "authorization":
                    value = _sanitize_auth(value)
                fields.setdefault(key, set()).add(value)

    norms: list[dict] = []
    src = str(log_path)
    # message：实际调用 ∪ 服务器声明（方法存在性）
    all_methods = sorted(set(methods) | set(public))
    for method in all_methods:
        norms.append(_norm(
            run_id, "message", method,
            f"method={method} occurrences={methods.count(method)}",
            protocol, src))
    # state_machine：观测到的方法序列
    if len(methods) >= 2:
        seq = " → ".join(methods)
        norms.append(_norm(run_id, "state_machine", "methods",
                           f"observed transitions: {seq}", protocol, src))
    # outcome：响应码分布
    if status:
        dist = ", ".join(f"'{k}': {v}" for k, v in sorted(status.items()))
        norms.append(_norm(run_id, "outcome", "status",
                           f"status code distribution: {{{dist}}}", protocol, src))
    # field：出现次数 + 取值样本（样本截断 top-5 防膨胀）
    for key, values in fields.items():
        norms.append(_norm(run_id, "field", key,
                           f"{key} header occurrences={len(values)}",
                           protocol, src, variant="occ"))
        samples = ", ".join(repr(v) for v in sorted(values)[:5])
        norms.append(_norm(run_id, "field", key,
                           f"unique {key}s={len(values)} samples=[{samples}]",
                           protocol, src, variant="samples"))
    return norms


def _extract_csv(csv_path: Path, run_id: str, protocol: str,
                 schema: dict) -> list[dict]:
    """从结构化 csv 抽取方法序列 + 响应码（字段名来自 schema 的 csv_fields）。"""
    import csv as _csv
    csv_fields = schema.get("csv_fields") or {}
    mf = csv_fields.get("method", "")
    sf = csv_fields.get("status", "")
    methods: list[str] = []
    status: dict[str, int] = {}
    with csv_path.open(encoding="utf-8", errors="ignore") as fh:
        for row in _csv.DictReader(fh):
            if mf:
                m = (row.get(mf) or "").strip().upper()
                if m:
                    methods.append(m)
            if sf:
                s = (row.get(sf) or "").strip()
                if s:
                    status[s] = status.get(s, 0) + 1
    norms: list[dict] = []
    src = str(csv_path)
    for method in sorted(set(methods)):
        norms.append(_norm(run_id, "message", method,
                           f"method={method} occurrences={methods.count(method)}",
                           protocol, src))
    if len(methods) >= 2:
        norms.append(_norm(run_id, "state_machine", "methods",
                           f"observed transitions: {' → '.join(methods)}",
                           protocol, src))
    if status:
        dist = ", ".join(f"'{k}': {v}" for k, v in sorted(status.items()))
        norms.append(_norm(run_id, "outcome", "status",
                           f"status code distribution: {{{dist}}}", protocol, src))
    return norms


#: Wireshark 底层网络层（非应用层），packets.ndjson 的 layers 里跳过这些 key。
#: 其余层一律视为应用层（sip/ftp/smtp/dns/...），换协议零改动。
_BASE_LAYERS = {
    "frame", "eth", "ip", "ipv6", "ipv4", "udp", "tcp", "arp", "icmp",
    "icmpv6", "igmp", "data", "nbns", "llc", "sll", "raw", "null", "llc",
}

#: 无语义的 Wireshark 元字段后缀（flags/长度/校验和/序号等），不参与种子字段填充。
_SKIP_FIELD_SUFFIXES = (
    "flags", "length", "len", "checksum", "checksum_status", "seq", "fragment",
    "offset", "chksum", "bad", "stream", "raw", "payload",
)

#: 字段值最大长度（超长的 base64 body / 证书 / SDP 整段不作为单字段样本）
_MAX_FIELD_VALUE_LEN = 160


def _strip_layer_prefix(layer: str, field: str) -> str:
    """去掉 Wireshark 字段名里的应用层协议前缀（1~2 次）。

    Wireshark 显示过滤器字段名形如 ``sip_sip_Contact`` / ``ftp_ftp_request_command``
    （双前缀）或 ``smtp_req_command``（单前缀）。统一剥掉 ``<layer>_`` 前缀，得到
    种子侧可直接匹配的头字段名（Contact / request_command / req_command）。
    """
    name = field
    prefix = layer + "_"
    for _ in range(2):
        if name.startswith(prefix):
            name = name[len(prefix):]
        else:
            break
    return name


def _skip_field(layer: str, field: str, value) -> bool:
    """过滤无语义字段：非字符串值、空值、过长值、元字段后缀。"""
    if not isinstance(value, str) or not value.strip():
        return True
    if len(value) > _MAX_FIELD_VALUE_LEN:
        return True
    low = field.lower()
    if low.endswith(_SKIP_FIELD_SUFFIXES):
        return True
    # 纯数字/布尔类字段（Wireshark 会把很多元信息当字符串，过滤掉无字母的）
    return False


def _parse_packet_ndjson(path: Path, app_layer: str) -> dict[str, set]:
    """解析单个 packets.ndjson，返回 {规范化字段名: 取值集合}（协议无关）。

    Wireshark `tshark -T json` 导出的 ndjson 每行一个包，含 ``layers`` 嵌套对象；
    部分导出带 ``_source.layers`` 包裹。只收集 ``layers[app_layer]``（目标协议层）
    的字符串字段——抓包常混入同网段其他协议（nbns/ftp/smb/dhcp），必须按层隔离，
    否则字段桶被无关协议污染。
    """
    import json
    fields: dict[str, set] = {}
    with path.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('{"index"'):
                continue  # ES bulk 元数据行
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                continue
            layers = obj.get("layers")
            if not isinstance(layers, dict):
                layers = (obj.get("_source") or {}).get("layers")
            if not isinstance(layers, dict):
                continue
            ldata = layers.get(app_layer)
            if not isinstance(ldata, dict):
                continue
            for kname, value in ldata.items():
                if _skip_field(app_layer, kname, value):
                    continue
                norm_name = _strip_layer_prefix(app_layer, kname)
                if not norm_name or (norm_name == kname and len(norm_name) < 2):
                    continue
                # 过滤 Wireshark 分解字段（含下划线，如 from_tag/Via_branch/
                # contact_uri），只保留真正的头字段（无下划线，如 From/To/Via/
                # Call-ID）。否则分解字段把 headers 取值池/字典灌爆、稀释变异预算。
                if "_" in norm_name:
                    continue
                fields.setdefault(norm_name, set()).add(value)
    return fields


def _load_app_layer(protocol: str) -> str:
    """目标应用层名（packets.ndjson 里 layers 的 key）。默认 = 协议名，可经
    profile.traffic_schema.app_layer 覆盖（协议名 ≠ Wireshark 层名时用）。"""
    prof = paths.target_profile(protocol)
    if prof.exists():
        try:
            import json
            data = json.loads(prof.read_text(encoding="utf-8"))
            ts = data.get("traffic_schema") or {}
            if ts.get("app_layer"):
                return str(ts["app_layer"])
        except (json.JSONDecodeError, OSError):
            pass
    return protocol


def extract_packet_fields(protocol: str) -> list[dict]:
    """从 packets.ndjson 抽取应用层真实字段值（协议无关，P4-a）。

    遍历 ``kb/<protocol>/数据流量/**/*.ndjson``，把 Wireshark layers 里应用层的
    字符串字段抽成 field norm（与 client.log 的 field norm 同构），经
    traffic_norm_to_facts → header.value_enum 自动流入 headers 取值池，让种子字段
    用真实流量值（真实 To tag / Contact / SDP / 命令参数）而非源码模板占位值。

    协议无关：不硬编码任何协议字段名；换协议 = 知识库有 packets.ndjson 即自动生效，
    无需改代码。无 ndjson 的协议（如 rtsp）安全返回空。
    """
    traffic_dir = paths.kb_source_dir(protocol, "traffic")
    if not traffic_dir.is_dir():
        return []
    app_layer = _load_app_layer(protocol)
    norms: list[dict] = []
    for ndjson_path in sorted(traffic_dir.rglob("*.ndjson")):
        fields = _parse_packet_ndjson(ndjson_path, app_layer)
        if not fields:
            continue
        run_id = str(ndjson_path.parent.relative_to(traffic_dir)).replace("\\", "/")
        src = str(ndjson_path)
        for name, values in fields.items():
            samples = ", ".join(repr(v) for v in sorted(values)[:5])
            norms.append({
                # ★ norm_id 必须带 ``.samples`` 后缀：本函数下游的
                #   ``infer_traffic_fields()``（:424）按
                #   ``norm_id.endswith(".samples")`` 筛选「原始样本」形态的
                #   field norm 来喂 LLM 兜底。
                #   ⇒ 原先这里写 ``traffic.field.{name}``（**无后缀**）⇒
                #     筛选恒为假 ⇒ **LLM 兜底分支是死代码**
                #     （实测 rtsp 37 条 norm 里 field=16 但 .samples=0）
                #     ⇒ 无 API key 时字段推断恒返回 []。
                "norm_id": f"traffic.field.{name}.samples",
                "kind": "field",
                "name": name,
                "content": f"unique {name}s={len(values)} samples=[{samples}]",
                "kb_source_type": "traffic_raw",
                "authority": "traffic_packet",
                "source": f"file:{src}#{run_id}",
                "protocol": protocol,
            })
    return norms


def extract_traffic_norms(protocol: str) -> list[dict]:
    """遍历 kb/<protocol>/数据流量/ 的每个 run，抽取 traffic norm（按 traffic_schema）。

    以 schema 声明的日志文件（log_files）所在目录为一个 run（目录名作 run_id，
    用相对路径去歧义）。每个 run 优先用 log_files[0]（主日志），缺失时用后续兜底。
    """
    traffic_dir = paths.kb_source_dir(protocol, "traffic")
    if not traffic_dir.is_dir():
        return []
    schema = _load_traffic_schema(protocol)
    log_files = schema.get("log_files") or []
    if not log_files:
        return []
    # rglob 递归定位每个 run 的日志文件（目录可能嵌套多层）
    by_file: dict[str, dict] = {}
    for name in log_files:
        by_file[name] = {p.parent: p for p in traffic_dir.rglob(name)}
    run_dirs = sorted(set().union(*(set(d) for d in by_file.values())))
    norms: list[dict] = []
    for run_dir in run_dirs:
        run_id = str(run_dir.relative_to(traffic_dir)).replace("\\", "/")
        for name in log_files:
            p = by_file[name].get(run_dir)
            if p is None:
                continue
            if name.endswith(".csv"):
                norms.extend(_extract_csv(p, run_id, protocol, schema))
            else:
                norms.extend(_extract_client_log(p, run_id, protocol, schema))
            break  # 优先主日志文件
    # P4-a：从 packets.ndjson 抽取应用层真实字段值（协议无关），让种子字段用真实流量值
    norms.extend(extract_packet_fields(protocol))
    return norms


_PROMPT_TRAFFIC_FIELDS = """你是 {protocol} 协议分析专家。下面是从真实网络流量中观测到的字段名和取值样本。
请提取每个字段的语义（字段含义/用途）。

字段及样本：
{fields}

只输出 JSON（不要解释），格式：
{{"fields": [{{"name": "...", "definition": "一句话语义"}}]}}"""


def infer_traffic_fields(protocol: str, llm=None, max_fields: int = 40) -> list[dict]:
    """LLM 兜底：从流量观测字段提取语义（对齐 LLM-Boofuzz 的「LLM 解析真实流量提取协议信息」）。

    rule（正则）已抽字段的 occurrence/samples（统计），本函数用 LLM 补字段语义
    （definition），弥补「rule 只做统计、不懂字段含义」的不足。llm 缺省用
    DeepSeekClient，测试可传 StubLLMClient；LLM 失败降级跳过（不影响 rule 统计）。
    """
    if llm is None:
        from core.llm import DeepSeekClient
        llm = DeepSeekClient()
    norms = extract_traffic_norms(protocol)
    if not norms:
        return []
    # 收集字段名 + 取值样本（field norm 的 samples variant）
    fields: dict[str, set] = {}
    for n in norms:
        if n["kind"] != "field" or not n["norm_id"].endswith(".samples"):
            continue
        m = re.search(r"samples=\[(.*)\]", n["content"])
        if not m:
            continue
        try:
            import ast
            vals = ast.literal_eval("[" + m.group(1) + "]")
            fields.setdefault(n["name"], set()).update(str(v) for v in vals)
        except (ValueError, SyntaxError):
            continue
    if not fields:
        return []
    lines = []
    for name, vals in sorted(fields.items()):
        sample = ", ".join(sorted(vals)[:5])
        lines.append(f"{name}（样本：{sample}）")
        if len(lines) >= max_fields:
            break
    text = "\n".join(lines)
    try:
        r = llm.chat_json(
            system="你输出 JSON。",
            user=_PROMPT_TRAFFIC_FIELDS.format(protocol=protocol.upper(), fields=text),
            temperature=0.2, max_tokens=3000)
    except Exception:
        return []
    if not isinstance(r, dict):
        return []
    out: list[dict] = []
    for item in (r.get("fields") or []):
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        definition = (item.get("definition") or "").strip()
        if not name or not definition:
            continue
        out.append({
            "norm_id": f"traffic.field.{name}.semantic",
            "kind": "field",
            "name": name,
            "content": f"{name} definition={definition}",
            "kb_source_type": "traffic_raw",
            "source": "llm:traffic-field",
            "protocol": protocol,
        })
    return out


__all__ = ["extract_traffic_norms", "infer_traffic_fields"]
