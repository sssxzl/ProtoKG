"""RTSP .raw 解析 + 协议无关的 seedcorpus_to_raw writer 入口.

历史:
  - 早期版本里 seedcorpus_to_raw 只支持 RTSP, 写死 "METHOD url RTSP/1.0" 格式.
  - 这导致 TCP/DNS 跑 pathgen 时, 即使 LLM 写对了 protocol 格式, writer 还是
    把所有 message 强转 RTSP 格式. 修复: 按 protocol 字段分发到对应 writer.

本文件职责:
  1. parse_rtsp_raw / raw_to_seedcorpus: RTSP .raw 解析 (反向, 给 RAG/AFLNet 集成用)
   (RTSP-specific, 但 raw_to_seedcorpus 是通用 reverse 接口)
  2. seedcorpus_to_raw: 协议无关的 .raw writer 入口, 按 protocol 派发
     - RTSP: _rtsp_to_raw (ProFuzzBench 兼容)
     - 其他: 读 KB expert_note/request_format.json → _generic_to_raw
            KB 缺失 → 返 b"" (caller path_writer 决定 skip)
     - Step 5: TCP/DNS/HTTP 硬编码 writer 已删除, 其他协议优先走 Profile 驱动, Profile 缺失才走 KB 兜底
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from .models import SeedCorpus, SeedMessage

log = logging.getLogger("protorag.raw_writers")


def _data_root(explicit: Optional[Path] = None) -> Path:
    """<project>/kb/  (data root)。优先级: explicit > PROTORAG_DATA_ROOT env > <项目根>/kb。

    2026-10-09 清理: 原在 core/stores.py, v1 退役后内联到此。
    """
    if explicit is not None:
        result = Path(explicit).resolve()
    else:
        import os
        env = os.environ.get("PROTORAG_DATA_ROOT")
        if env:
            result = Path(env).resolve()
        else:
            here = Path(__file__).resolve()
            project = here.parents[1]  # core/raw_writers.py -> core -> <project>/
            result = (project / "kb").resolve()
    return result


# RTSP 状态机 — v2.3.1 P0-3 改造: 从 KB loaded
# 之前硬编码 10 条 (line 33-44 删除), 改读 KB state_machine.json（该链路已于 2026-10-09 退役，现返回空 dict）。
# 见 _get_rtsp_transitions() (lru_cache) + _infer_state_path().
# KB 27 条 indexed + 6 wildcard, 比硬编码 10 条更全 (含 OPTIONS/DESCRIBE stateless).

# Session ID 占位符 (fuzzer 风格)
_SESSION_PLACEHOLDER = "{{session_id}}"


# v2.3.1 P0-3: KB transitions 懒加载 (lru_cache 一次 load, 永久不变).
# 替代之前硬编码 10 条 _RTSP_TRANSITIONS.
# flatten key: (from_state_upper, method_upper) -> to_state (PascalCase).
# wildcard 用 ("*", method_upper) 表示 "from any state" (优先级低于 indexed).
# to_state "$current" 表示 state 不变, 调用方需 skip.
from functools import lru_cache


@lru_cache(maxsize=1)
def _get_rtsp_transitions() -> dict:
    """（2026-10-09 退役）原从 KB ProtocolAdapter 读 transitions, flatten 成
    {(from_upper, method_upper): to_state}。

    v1 expert_note 读链路已退役：kb_adapter._load_kb 返回 None → from_protocol
    返 GenericAdapter（无 .transitions() 方法）。这里优雅降级返回空 dict，
    使 _infer_state_path 退回只含 "Init" 的路径，不再崩溃。
    v2 seedgen 通路（roadmap 4.3）建好后从 v2 中枢读回状态机。
    """
    return {}


def parse_rtsp_raw(text: str) -> list[SeedMessage]:  # RTSP-specific reverse parser
    """解析 RTSP .raw 文本为 SeedMessage 列表 (ProFuzzBench 兼容格式).

    Returns:
        list[SeedMessage]:按出现顺序的 messages
    """
    messages: list[SeedMessage] = []
    # 标准化换行符:把 \r\n 和 \r 都转成 \n,这样混合换行也能切
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    # 按 \n\n 切分(messages 间空行)
    raw_messages = re.split(r"\n\n+", normalized.strip())
    for raw in raw_messages:
        if not raw.strip():
            continue
        # 按 \n 切分行
        lines = raw.split("\n")
        if not lines:
            continue
        # 第一行是 request line: METHOD URI RTSP/1.0
        first_line = lines[0].strip()
        parts = first_line.split(" ", 2)
        if len(parts) < 2:
            continue
        method = parts[0].upper()
        # 解析 headers
        headers: dict[str, str] = {}
        for line in lines[1:]:
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            headers[key.strip()] = value.strip()
        messages.append(SeedMessage(method=method, headers=headers, body=""))
    return messages


def _infer_state_path(methods: list[str]) -> list[str]:
    """从 method 序列推断 RTSP 状态路径(Init → Ready → Playing → Init).

    v2.3.1 P0-3: 状态机来源已退役（_get_rtsp_transitions() 恒返回空 dict），当前退回仅含 "Init" 的路径。
    记录完整的状态转换序列,允许重复(如 TEARDOWN 回到 Init 也记录).
    连续 SETUP dedup: KB (Ready, SETUP) -> Ready, new_state == state, 不 append.
    wildcard "$current": state 不变, 不 append.
    """
    transitions = _get_rtsp_transitions()
    path = ["Init"]
    state = "Init"
    for m in methods:
        m_upper = m.upper()
        # 1. 查 indexed (state 特定)
        new_state = transitions.get((state.upper(), m_upper))
        # 2. 没命中查 wildcard ("*", m) 表示任意 state
        if new_state is None:
            new_state = transitions.get(("*", m_upper))
        # 3. skip 条件: 没匹配 / "$current" / dedup (new_state == state)
        if new_state is None or new_state == "$current" or new_state == state:
            continue
        state = new_state
        path.append(state)
    return path


def raw_to_seedcorpus(path: Path) -> SeedCorpus:
    """RTSP .raw 文件 → SeedCorpus (反向解析).

    Args:
        path: .raw 文件路径

    Returns:
        SeedCorpus:含解析的 messages + 推断的 state_path + target_methods
        Session header 会被替换成 {{session_id}} 占位符 (原 .raw 用真实值,
        fuzzer 跑时要替换成动态值,占位符更通用)。
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    messages = parse_rtsp_raw(text)  # RTSP-specific parse

    # Session ID 真实值 → {{session_id}} 占位符
    for msg in messages:
        if "Session" in msg.headers and msg.headers["Session"] != _SESSION_PLACEHOLDER:
            msg.headers["Session"] = _SESSION_PLACEHOLDER

    methods = [m.method for m in messages]
    state_path = _infer_state_path(methods)

    # seed_id 从文件名推断
    name = path.stem
    if name.startswith("rtsp_requests_"):
        seed_id = name[len("rtsp_requests_"):]
    elif name.startswith("rtsp_"):
        seed_id = name[len("rtsp_"):]
    else:
        seed_id = name

    return SeedCorpus(
        protocol="rtsp",
        seed_id=f"rtsp-{seed_id}",
        description=f"RTSP seed for {seed_id}",
        target_state_path=state_path,
        target_methods=methods,
        target_vuln_class="",
        generated_by="protorag:initial",
        messages=list(messages),  # 关键:把解析的 messages 加进去
    )


# ============================================================================
# v2.1.5 A2 兼容性: 读 KB expert_note/request_format.json, 通用 .raw writer
# 适用: 未命中协议 Profile 且非 rtsp 的协议, 用 KB 模板渲染
# ============================================================================

@lru_cache(maxsize=16)
def _load_request_format_from_kb(protocol: str, *, data_root: Optional[Path] = None) -> Optional[dict]:
    """从 <data_root>/spec/<proto>/expert_note/request_format.json 读 request_format 字段.

    v2.1.5 新增 (陌生 KB 兼容性闭环). 跟 _load_kb_cached 风格统一 (lru_cache).
    v2.3.1 修复: 加 data_root 参数 (之前硬编码 Path("kb"), 跟 --data-root 解耦 → FK1 端到端 0 seeds written).

    Args:
        protocol: 协议名 (e.g. "FAKEPROTO", "RTSP"). 不区分大小写.
        data_root: KB 根目录 (含 spec/ 上层). None 时走 _data_root() 解析
                  (优先级: explicit > PROTORAG_DATA_ROOT env > <项目根>/kb).

    Returns:
        dict 格式:
            {
                "request_template": "{method} {headers}\\r\\n",
                "header_format": "{key}={value}",
                "header_separator": " "
            }
        或 None (KB 文件缺失 / 损坏 / 缺顶层 'request_format' 字段)

    Cache 行为:
        lru_cache(maxsize=16). key = (protocol, data_root).
        ⚠️ data_root=None 和 data_root=Path("/abs/path/to/kb") 是两个独立 cache key.
        同一进程多次调用, 不同 data_root 互不污染 (支持 pytest 串行多 data_root).
        KB 改动后需重启进程或调 cache_clear() 清全部 key.
        不加自动刷新机制 (复杂度不值得, KB 是手动管理).
    """
    if not protocol:
        return None
    if data_root is None:
        data_root = _data_root()
    path = data_root / "spec" / protocol.lower() / "expert_note" / "request_format.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        result = data.get("request_format")
        if result is None:
            log.warning("[request_format] %s 缺 'request_format' 顶层字段", path)
        return result
    except (json.JSONDecodeError, OSError) as e:
        log.warning("[request_format] %s 读失败: %s", path, e)
        return None


def _generic_to_raw(seed: SeedCorpus, request_format: dict) -> bytes:
    """v2.1.5 协议无关 generic .raw writer (单行 line-oriented 格式).

    适用: FakeProto / 简单文本协议 (单行 CRLF + 空格分隔 key=value).
    不适用: RTSP / TCP / DNS / HTTP (走特化分支).

    Args:
        seed: SeedCorpus (含 messages + headers)
        request_format: KB request_format.json 里的 request_format 字段
            {
                "request_template": "{method} {headers}\\r\\n",
                "header_format": "{key}={value}",
                "header_separator": " "
            }

    Returns:
        bytes: 渲染后的 .raw bytes
        或 b"" (含未解析 {{xxx}} 占位符时, 兜底返空让 caller skip)

    v2.1.5 兜底: 检测未解析 {{xxx}} 占位符, 防 LLM 发明新占位符直接落盘
    """
    import re
    request_template = request_format["request_template"]
    header_format = request_format["header_format"]
    header_separator = request_format["header_separator"]

    out = bytearray()
    for msg in seed.messages:
        # 1. 渲染 headers → "target=world Id=1 Token=abc"
        header_strs = [
            header_format.format(key=k, value=v)
            for k, v in msg.headers.items()
        ]
        headers_str = header_separator.join(header_strs)

        # 2. 渲染 line (模板已含 \r\n)
        line = request_template.format(method=msg.method, headers=headers_str)

        # v2.1.5: 兜底检测 {{xxx}} 占位符 (LLM 发明用法, raw_writers.py 不解析)
        #   防止假占位符直接落盘到 .raw (AFLNet 看到 {{xxx}} 会困惑)
        if re.search(r"\{\{[a-zA-Z_]+\}\}", line):
            log.warning(
                "[_generic_to_raw] %s line 含未解析 {{xxx}} 占位符 (LLM 发明用法), 返 b'' 让 caller skip. line=%r",
                seed.protocol, line[:80],
            )
            return b""

        out += line.encode("utf-8")

    return bytes(out)


# ============================================================================
# 协议 Profile 驱动（换协议只换 fused_hub/targets/<protocol>/profile.json）
# ============================================================================

def _targets_root() -> Path:
    """fused_hub/targets 目录（协议 Profile 数据根）。统一复用 paths 避免双路径解析。"""
    from core import paths
    return paths.targets_root()


@lru_cache(maxsize=16)
def _load_profile(protocol: str) -> Optional[dict]:
    """读 <targets>/<protocol>/profile.json。缓存；换协议只换数据，不改代码。"""
    if not protocol:
        return None
    from core import paths
    path = paths.target_profile(protocol)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("[profile] %s 读失败: %s", path, e)
        return None


def _render_from_profile(seed: SeedCorpus, profile: dict, url: str) -> bytes:
    """按 profile.raw_format 渲染 .raw 字节流（协议无关）。

    raw_format 字段:
      line_ending          换行符 (默认 \\r\\n)
      request_line         请求行模板, 占位符 {method}/{url}/{version}/{argument}
      version              协议版本 (如 RTSP/1.0, 空则无版本)
      header_line          头部行模板, 占位符 {key}/{value} (空串 = 协议无头部, 跳过)
      trailing_blank_line  每条消息后是否追加空行 (消息分隔)
      command_extra        {COMMAND: 附加文本} 行命令协议的命令附加内容 (如 SMTP DATA 的
                           消息体 + "." 结束符), 渲染在命令行之后

    行命令协议 (如 SMTP) 用 request_line="{method} {argument}" + header_line=""：
      渲染成 "MAIL FROM:<sender@example.com>\\r\\n"，argument 为空时自动去掉尾部空格。
    """
    fmt = profile.get("raw_format", {})
    line_ending = fmt.get("line_ending", "\r\n")
    request_line = fmt.get("request_line", "{method} {url} {version}")
    version = fmt.get("version", "")
    header_line = fmt.get("header_line", "{key}: {value}")
    # ★ 2026-11-07（B2）：**实体头行模板** —— 实体内容（如 SMTP DATA 之后的
    #   邮件）的头段模板。缺省**继承** ``header_line``；
    #   命令协议可设 ``header_line=""``（命令本身无头）但
    #   ``entity_header_line="{key}: {value}"``（消息内容有头，
    #   依据 RFC 5321 §2.3.9「message content includes the message header
    #   section」）。
    entity_header_line = fmt.get("entity_header_line") or header_line
    trailing_blank = fmt.get("trailing_blank_line", True)
    command_extra = fmt.get("command_extra", {}) or {}

    out = bytearray()
    for msg in seed.messages:
        method = msg.method.upper()
        msg_url = (getattr(msg, "url", "") or "").strip() or url
        # 非 rtsp 协议：把 LLM 先验误生成的 rtsp:// URL 替换成 profile 的 default_url
        if profile.get("protocol") != "rtsp" and msg_url.startswith("rtsp://"):
            msg_url = profile.get("default_url") or msg_url
        argument = (getattr(msg, "argument", "") or "").strip()
        rl = request_line.format(method=method, url=msg_url,
                                 version=version, argument=argument)
        rl = rl.rstrip()  # argument/version 为空时去掉请求行尾部空格
        out += (rl + line_ending).encode("utf-8")
        # ★ 2026-11-07（B2）：**头必须在 command_extra 之前**输出。
        #   理由：`command_extra` 是**信体内容**（如 SMTP DATA 的邮件正文 + "."），
        #   而 RFC 5321 §2.3.9 规定「message content includes the **message header
        #   section** and the possibly structured message body」⇒ 邮件头属于
        #   message content 的一部分，**必须在正文之前**。
        #   旧实现把 extra 排在头之前 ⇒ 信体头会落在正文**后面** ⇒ 非法邮件。
        # ★ B2：区分「命令头」与「实体头」的渲染模板 ——
        #   命令头走 ``header_line``；实体头走 ``entity_header_line``。
        #   两者通常相同（继承），但命令协议会设 ``header_line=""`` 而
        #   实体内容仍有头段 ⇒ 必须分开。
        _cmd_hdr_tpl = header_line
        _ent_hdr_tpl = entity_header_line
        if _cmd_hdr_tpl and msg.headers:
            for key, value in msg.headers.items():
                value = _resolve_all_placeholders(value)
                hl = _cmd_hdr_tpl.format(key=key, value=value)
                out += (hl + line_ending).encode("utf-8")
        elif _ent_hdr_tpl and msg.headers:
            # ★ 命令无头部行语法、但消息内容有头段 ⇒ 用实体头模板渲染
            for key, value in msg.headers.items():
                value = _resolve_all_placeholders(value)
                hl = _ent_hdr_tpl.format(key=key, value=value)
                out += (hl + line_ending).encode("utf-8")
        extra = command_extra.get(method, "")
        if extra:
            out += (extra + line_ending).encode("utf-8")
        if msg.body:
            body = _resolve_all_placeholders(msg.body)
            out += (line_ending + body + line_ending).encode("utf-8")
        if trailing_blank:
            out += line_ending.encode("utf-8")
    return bytes(out)


# ============================================================================
# seedcorpus_to_raw: 协议无关入口, 按 protocol 字段派发到对应 writer
# ============================================================================

def seedcorpus_to_raw(seed: SeedCorpus, *, url: str = "rtsp://localhost/seed",
                      target_host: str = "127.0.0.1",
                      target_port: str = "8554",
                      resource: str = "/test",
                      data_root: Optional[Path] = None) -> bytes:
    """把 SeedCorpus 转成对应协议的 .raw bytes.

    按 protocol 字段派发:
      - RTSP:  文本格式 "METHOD <url> RTSP/1.0\\r\\nKey: Val\\r\\n\\r\\n"
      - TCP:   binary flag 字节流 (SYN=0x02 / FIN=0x01 / RST=0x04 / ACK=0x10)
      - DNS:   binary DNS message (header 12 bytes + QNAME + QTYPE/QCLASS)
      - HTTP:  文本格式 "METHOD <url> HTTP/1.1\\r\\nKey: Val\\r\\n\\r\\n"
      - 其他:  读 KB expert_note/request_format.json → _generic_to_raw
             KB 缺失 → 返 b"" (caller path_writer 决定 skip, 不假写 RTSP)

    v2.3.1: 加 data_root 参数 (透传给 _load_request_format_from_kb).
            不传时 None → _data_root() 解析 (env 或 <项目根>/kb 兜底).
            用于 seedgen 跑 --data-root tests/fixtures/kb 等非默认路径场景.

    P1-A6 修复: url / body 含 {{target_host}}/{{target_port}}/{{resource}} 占位符时,
    落盘时自动 replace 为实际 target_host/target_port/resource (默认 127.0.0.1:8554/test).
    这让 LLM 写 seed 时用通用占位符, fuzzing 时按目标 server 替换.

    Args:
        seed: 完整的 SeedCorpus (含 messages + headers)
        url: RTSP/HTTP 用, 占位符 URL (可含 {{target_host}} 等占位符)
        target_host: 默认 "127.0.0.1" (P1-A6 落盘时的实际目标)
        target_port: 默认 "8554" (RTSP 默认端口)
        resource:    默认 "/test" (RTSP 资源路径)

    Returns:
        bytes: 协议对应格式的字节流 (可被 AFLNet 直接消费)
    """
    proto = (seed.protocol or "rtsp").lower()
    # seed.selected_url 优先级 (目标实例资源 URL)；空则用 caller 传的 url 参数
    selected = getattr(seed, "selected_url", "") or ""
    if selected:
        url = selected
    # P1-A6: 替换 url 占位符
    url = _resolve_placeholders(url, target_host, target_port, resource)
    # 优先走协议 Profile 驱动（换协议只换 profile.json，RTSP 不再特化）
    profile = _load_profile(seed.protocol)
    if profile is not None:
        # ★ 2026-11-07：二进制协议走**字节布局**渲染（文本协议**零改动**）。
        #   判据 = profile 里有 ``raw_format.binary_fields``（**纯数据**判据，
        #   不认协议名）⇒ 不需要额外的「协议类型」开关。
        #   ★ 与 `core/kinds` 的协议类型判定**互补**：这里是「能不能按布局渲染」，
        #     kinds 是「这个协议是什么类型」——两者都在 profile 这一层汇合。
        _raw_fmt = profile.get("raw_format") or {}
        if _raw_fmt.get("binary_fields"):
            from core.raw_writers_binary import render_binary_from_profile
            return render_binary_from_profile(seed, profile)
        return _render_from_profile(seed, profile, url)
    if proto == "rtsp":
        return _rtsp_to_raw(seed, url=url)
    # tcp/dns/http 专用 writer 已删除; Profile 缺失时走 KB 兜底 (request_format.json, 现库中已无此文件)

    # v2.1.5 兜底改: 读 KB request_format → _generic_to_raw
    #   之前: _rtsp_to_raw (硬编码 RTSP 格式, 污染陌生协议)
    #   现在: KB 缺 request_format → log WARNING + 返 b"" (caller skip)
    # v2.3.1: 透传 data_root, 让非默认 KB 路径能正常加载
    rf = _load_request_format_from_kb(seed.protocol, data_root=data_root)
    if rf is None:
        log.warning(
            "[seedcorpus_to_raw] %s KB 缺 request_format.json, 返 b"" "
            "(不再 fallback _rtsp_to_raw, 避免假 RTSP 风格污染陌生协议)",
            seed.protocol,
        )
        return b""
    return _generic_to_raw(seed, rf)


# P1-A6: 占位符替换工具
PLACEHOLDER_HOST = "{{target_host}}"
PLACEHOLDER_PORT = "{{target_port}}"
PLACEHOLDER_RESOURCE = "{{resource}}"
PLACEHOLDER_RESOURCE_BRACED = "{{{resource}}}"  # P1-A9 path 渲染出来是 4 个花括号
PLACEHOLDER_PATH = "{{path}}"
PLACEHOLDER_PATH_BRACED = "{{{path}}}"

# v2.1.3: runtime 占位符 hardcode 默认值（写盘前可执行性前置）
#   - 所有 {{xxx}} runtime 占位符在 .raw 写盘前 hardcode 成实际值
#   - AFLNet 原版不替换占位符, 字面值 12345678 / 8000 等能让 RTSP server 直接接受
#   - 用户可后续加 fuzzer 端占位符替换 (超出 ProtoRAG 仓库范围)
import re
import base64 as _b64

DEFAULT_SESSION_ID = "12345678"
DEFAULT_AUTO_LENGTH = "0"
DEFAULT_PORT_RANGE = "8000-8001"
DEFAULT_RESOURCE = "/test.264"
DEFAULT_TRANSPORT = f"RTP/AVP;unicast;client_port={DEFAULT_PORT_RANGE}"


def _resolve_all_placeholders(text: str) -> str:
    """v2.1.3: 写盘前 hardcode 全 runtime 占位符 → AFLNet 原版可直接执行.

    覆盖的 runtime 占位符 (实测 trigger.requests 出现过的全集):
      {{session_id}} / {{session_id_<N>}}   → "12345678"
        (server 不检查 client Session 值, hardcode 不破坏协议合法性)
      {{auto_length}}                       → "0" (无 body 时 Content-Length)
      {{payload_<N>b}} / {{payload_<N>b_raw}} / {{payload_<N>b_b64}}
                                          → "A" * N / "B" * N / base64("A"*N)
      {{payload_int_overflow}}              → "4294967295" (INT_MAX 边界)
      {{payload_hexstream}}                 → "0x00" * 50
      {{long_payload_<N>}}                  → "A" * N
      {{playlist_url_<N>}}                  → "/playlist_<N>.m3u"
      {{repeat_<N>}}                        → "<N>" (字面数字)

    P1-A6 url 占位符 ({{target_host}}/{{target_port}}/{{resource}}) 由
    _resolve_placeholders() 单独处理 (需要 data_root 配置).
    """
    if not text:
        return text

    def _payload_bytes(n: int) -> str:
        return "A" * n

    def _payload_raw(n: int) -> str:
        return "B" * n

    def _payload_b64(n: int) -> str:
        # base64 of "A"*n, decoded back to string
        return _b64.b64encode(b"A" * n).decode("ascii")

    out = text
    # Session 类 (保留 N)
    out = re.sub(r"\{\{session_id_\d+\}\}", DEFAULT_SESSION_ID, out)
    out = out.replace("{{session_id}}", DEFAULT_SESSION_ID)
    # Content-Length 自增
    out = out.replace("{{auto_length}}", DEFAULT_AUTO_LENGTH)
    # Transport port range (RTSP-001 setup header)
    out = out.replace("{{port_range}}", DEFAULT_PORT_RANGE)
    # payload 字节大小 (3 变体)
    out = re.sub(r"\{\{payload_(\d+)b_raw\}\}", lambda m: _payload_raw(int(m.group(1))), out)
    out = re.sub(r"\{\{payload_(\d+)b_b64\}\}", lambda m: _payload_b64(int(m.group(1))), out)
    out = re.sub(r"\{\{payload_(\d+)b\}\}", lambda m: _payload_bytes(int(m.group(1))), out)
    # payload 语义 (overflow / hexstream / long)
    out = out.replace("{{payload_int_overflow}}", "4294967295")
    out = out.replace("{{payload_hexstream}}", "0x00" * 50)
    out = re.sub(r"\{\{long_payload_(\d+)\}\}", lambda m: "A" * int(m.group(1)), out)
    # playlist URL
    out = re.sub(r"\{\{playlist_url_(\d+)\}\}", lambda m: f"/playlist_{m.group(1)}.m3u", out)
    # repeat 次数
    out = re.sub(r"\{\{repeat_(\d+)\}\}", lambda m: m.group(1), out)

    # v2.1.3: URL/host/port 占位符 (LLM 可能漏在 headers/body 里)
    # 默认值用 caller 已经传过的, 此处用 placeholder 表示"由 caller 替换"
    # 但 raw_writers 落盘时必须 hardcode, 否则兜底 reject
    # 默认值: 127.0.0.1:8554/test（RTSP 默认地址, P1-A6 标定值）
    out = out.replace("{{target_host}}", "127.0.0.1")
    out = out.replace("{{target_port}}", "8554")
    out = out.replace("{{resource}}", "/test")

    # 尖括号占位符（LLM 现场生成字段值时用的模板变量，非 {{xxx}} 花括号体系）
    # 如 Session: <sessionId>、Range: npt=<resumeTime>-、Content-Length: <sdpLength>
    out = out.replace("<sessionId>", DEFAULT_SESSION_ID)
    out = out.replace("<session_id>", DEFAULT_SESSION_ID)
    out = out.replace("<resumeTime>", "0.000")
    out = out.replace("<resume_time>", "0.000")
    out = out.replace("<sdpLength>", "0")
    out = out.replace("<sdp_length>", "0")

    # 兜底检查: 任何未匹配的 {{xxx}} 仍存在 → raise (避免静默吞错)
    leftover = re.findall(r"\{\{[^}]+\}\}", out)
    if leftover:
        raise ValueError(f"unknown runtime placeholder(s) {leftover} in text={text!r}")

    return out


def _resolve_placeholders(text: str,
                           target_host: str, target_port: str,
                           resource: str) -> str:
    """P1-A6: url/body 含占位符时替换成实际目标.

    支持的占位符:
      {{target_host}}     → target_host 参数
      {{target_port}}     → target_port 参数
      {{resource}}        → resource 参数 (e.g. "/test.264")
      {{{{resource}}}}     → resource (4 花括号是从 user prompt 渲染出来时的字面)
      {{path}}            → resource (HTTP 用)
      {{{{path}}}}         → resource (HTTP 4 花括号)
    """
    if not text:
        return text
    text = text.replace(PLACEHOLDER_HOST, target_host)
    text = text.replace(PLACEHOLDER_PORT, str(target_port))
    text = text.replace(PLACEHOLDER_RESOURCE_BRACED, resource)
    text = text.replace(PLACEHOLDER_RESOURCE, resource)
    text = text.replace(PLACEHOLDER_PATH_BRACED, resource)
    text = text.replace(PLACEHOLDER_PATH, resource)
    return text


def _rtsp_to_raw(seed: SeedCorpus, *, url: str = "rtsp://localhost/seed") -> bytes:
    """RTSP .raw writer (ProFuzzBench 兼容格式, 给 AFLNet/AFL 消费).

    格式:
        METHOD <url> RTSP/1.0\\r\\n
        Key1: Value1\\r\\n
        Key2: Value2\\r\\n
        \\r\\n
        (下条 message)

    v2.1.3: 写盘前调 _resolve_all_placeholders() hardcode runtime 占位符
      (session_id / auto_length / payload 类 / repeat 等), 让 AFLNet 原版
      不依赖 fuzzer 端占位符替换器就能直接执行.
    """
    out = bytearray()
    for i, msg in enumerate(seed.messages):
        method = msg.method.upper()
        # request line (消息级 url 优先，用于多轨 track1/track2 不同 URL)
        msg_url = (getattr(msg, "url", "") or "").strip() or url
        out += f"{method} {msg_url} RTSP/1.0\r\n".encode("utf-8")
        # headers(按原始 key 顺序, v2.1.3: hardcode runtime 占位符)
        for key, value in msg.headers.items():
            value = _resolve_all_placeholders(value)
            out += f"{key}: {value}\r\n".encode("utf-8")
        # body (v2.1.3: hardcode runtime 占位符)
        if msg.body:
            body = _resolve_all_placeholders(msg.body)
            out += b"\r\n"  # body 前空行
            out += body.encode("utf-8")
            out += b"\r\n"
        # message separator
        out += b"\r\n"
    return bytes(out)


__all__ = [
    "parse_rtsp_raw",  # RTSP-specific reverse parser
    "raw_to_seedcorpus",  # 通用 reverse (含 RTSP)
    "seedcorpus_to_raw",  # 通用 forward
    "_infer_state_path",  # RTSP-specific
    "_get_rtsp_transitions",  # RTSP-specific (KB loaded)
    "_rtsp_to_raw",
]



