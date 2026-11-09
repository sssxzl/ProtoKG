# -*- coding: utf-8 -*-
"""从 kb/数据流量 的真实 pcapng 抽取「真实请求模板」。

背景：种子质量的核心是「请求真实性」（能否真正触达深层代码路径），而
真实请求的完整形态（PLAY 带 Range 头、URL 尾斜杠、SETUP 用 /trackN 等）
蕴含于真实流量，既不在 RFC 中，也不在 LLM 先验里。

本脚本：
  1. 遍历 kb/数据流量/*/capture.pcapng（fallback clean.pcapng）
  2. 从二进制中提取明文 RTSP 请求（METHOD url RTSP/1.0 + headers）
  3. 按 method 聚合「请求模板」：URL 结构、完整 header 集合、典型取值
  4. 产出 profiles/rtsp_request_templates.json

产出供 rag_seedgen.render_seed_prompt 注入，引导 LLM 生成贴近真实报文的种子。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAFFIC_DIR = ROOT / "kb" / "数据流量"
OUT = ROOT / "profiles" / "rtsp_request_templates.json"

# 请求行 + headers 提取
REQ_RE = re.compile(r"([A-Z]+) (rtsp://[^\r\n]+) RTSP/1\.0")

# 合法 RTSP method 白名单（过滤 pcap 中报文前污染字节导致的 ADESCRIBE 等）
RTSP_METHODS = {
    "OPTIONS", "DESCRIBE", "SETUP", "PLAY", "PAUSE", "TEARDOWN",
    "GET_PARAMETER", "SET_PARAMETER", "ANNOUNCE", "RECORD",
    "REDIRECT", "REGISTER",
}


def extract_requests(data: str) -> list[tuple[str, str, list[tuple[str, str]]]]:
    """从 pcapng 文本提取 (method, url, [(header, value), ...]) 列表。"""
    out = []
    for m in REQ_RE.finditer(data):
        method = m.group(1)
        if method not in RTSP_METHODS:
            continue  # 过滤污染 method（前缀字节）
        url = m.group(2)
        start = m.end()
        end = data.find("\r\n\r\n", start)
        if end == -1:
            end = start + 300
        headers = []
        for line in data[start:end].split("\r\n"):
            line = line.strip()
            if ":" in line:
                k, _, v = line.partition(":")
                headers.append((k.strip(), v.strip()))
        out.append((method, url, headers))
    return out


def abstract_url(url: str) -> str | None:
    """把具体 URL 抽象成 pattern：{stream}、{stream}/、{stream}/track{N}。

    仅保留标准流名结构（Live555 目标服务的 /<流名>[/trackN]），
    海康 /isapi、somasexy /soma 等非标准路径返回 None（丢弃）。
    """
    m = re.match(r"^[^/]+://[^/]+(/.*)$", url)
    path = m.group(1) if m else url
    m = re.match(r"^/([^/]+)/track(\d+)$", path)
    if m:
        return "/{stream}/track{N}"
    m = re.match(r"^/([^/]+)/$", path)
    if m:
        return "/{stream}/"
    m = re.match(r"^/([^/]+)$", path)
    if m:
        return "/{stream}"
    return None  # 非标准 URL，丢弃


def main() -> int:
    pcap_files = sorted(TRAFFIC_DIR.glob("**/capture.pcapng"))
    if not pcap_files:
        pcap_files = sorted(TRAFFIC_DIR.glob("**/clean.pcapng"))
    print(f"发现 {len(pcap_files)} 个 pcapng")

    # method -> {url_patterns:set, headers:OrderedDict(header->set(values)), captures:int}
    methods: dict[str, dict] = defaultdict(
        lambda: {"url_patterns": set(), "headers": OrderedDict(),
                 "captures": 0})

    for pcap in pcap_files:
        try:
            data = pcap.read_bytes().decode("latin-1")
        except OSError:
            continue
        reqs = extract_requests(data)
        if not reqs:
            continue
        for method, url, headers in reqs:
            entry = methods[method]
            pat = abstract_url(url)
            if pat:
                entry["url_patterns"].add(pat)
            for hk, hv in headers:
                entry["headers"].setdefault(hk, set()).add(hv)
            entry["captures"] += 1

    # 组装输出
    result: dict = {
        "protocol": "rtsp",
        "source": "kb/数据流量 pcap 真实流量",
        "note": ("从真实抓包提取的请求模板：URL 结构与完整 header 集合（含可选头如 "
                 "Range/Accept）。种子生成必须参照此模板，保证请求真实性以触达深层路径。"),
        "methods": {},
    }
    for method in sorted(methods):
        e = methods[method]
        headers = list(e["headers"].keys())
        examples = {}
        for hk, vals in e["headers"].items():
            examples[hk] = sorted(vals)[:3]
        result["methods"][method] = {
            "url_patterns": sorted(e["url_patterns"]),
            "headers": headers,
            "examples": examples,
            "captures": e["captures"],
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"产出 {len(methods)} 个方法的请求模板 -> {OUT}")
    for m in sorted(methods):
        e = methods[m]
        print(f"  {m:12s} url={sorted(e['url_patterns'])} "
              f"headers={list(e['headers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
