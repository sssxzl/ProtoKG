# -*- coding: utf-8 -*-
"""ChatAFL 代理层「响应改写」纯函数模块（仅依赖标准库 json / re）。

背景：ChatAFL 内部的 LLM 调用有三条路径，其中「启动期增强（enrich_sequence）」与
「运行期 stall-chat（construct_prompt_stall）」两条路径的 prompt 无格式约束，
deepseek-chat（聊天风格）会返回带前言/代码围栏/Explanation 的散文。ChatAFL 拿到回答后
只做 format_request_message()（裸换行转 CRLF + 尾部补 CRLFCRLF），不做报文抽取，散文会
被原样写进 .raw 种子文件，污染 fuzzing 语料。

本模块在「响应回传 ChatAFL 之前」根据**请求**内容判定路径，对增强/stall 两条路径用
抽取器剥离散文、只保留纯 RTSP 报文，再回写 choices[0].message.content。

安全约束（务必遵守）：
1. 语法抽取路径（返回 COMMAND: ["..."] 格式）**绝不**套抽取器，必须原样透传。
2. 抽取失败时不崩溃、不返回半截脏数据；策略：置空 content（丢弃该条增强），
   ChatAFL 侧对空 content 已有 continue 保护会跳过写入。
3. 抽取器为纯函数，无任何共享可变状态，线程安全（可被 ThreadingHTTPServer 多线程并发调用）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# 常量：RTSP 方法全集 + 报文/头部正则
# ---------------------------------------------------------------------------

# ChatAFL 增强会产出 REDIRECT，故必须包含；顺序不影响正确性（`\\s+` 起到消歧作用）。
RTSP_METHODS = (
    "OPTIONS", "DESCRIBE", "SETUP", "PLAY", "PAUSE", "TEARDOWN",
    "GET_PARAMETER", "SET_PARAMETER", "ANNOUNCE", "RECORD", "REDIRECT",
)

# FTP 命令全集（RFC 959 + 扩展，与 profiles/ftp/profile.json 的
# allowed_methods 对齐；42 个）。顺序不影响正确性。
FTP_METHODS = (
    "USER", "PASS", "ACCT", "CWD", "CDUP", "QUIT", "REIN", "PORT", "PASV",
    "EPSV", "EPRT", "TYPE", "STRU", "MODE", "RETR", "STOR", "STOU", "APPE",
    "ALLO", "REST", "RNFR", "RNTO", "ABOR", "DELE", "RMD", "MKD", "PWD",
    "LIST", "NLST", "SYST", "STAT", "HELP", "NOOP", "FEAT", "OPTS", "AUTH",
    "PBSZ", "PROT", "MDTM", "SIZE", "MLSD", "MLST",
)

# SIP 方法全集（RFC 3261 标准化 14 方法，与 profiles/sip/profile.json 的
# allowed_methods 对齐）。kamailio/pjproject 通用，无 FTP 式「多实现并集」污染。
SIP_METHODS = (
    "INVITE", "ACK", "BYE", "CANCEL", "OPTIONS", "REGISTER", "SUBSCRIBE",
    "NOTIFY", "PUBLISH", "INFO", "REFER", "MESSAGE", "PRACK", "UPDATE",
)

# 报文首行：METHOD URI RTSP/1.0（大小写不敏感；group(1) 捕获方法名）。
_METHOD_RE = re.compile(
    r"^(" + "|".join(RTSP_METHODS) + r")\s+\S+\s+RTSP/1\.0\s*$",
    re.IGNORECASE,
)

# 头部行：仅接受 RTSP 标准头部白名单（HeaderName: value）。
# 不用 `^[A-Za-z][A-Za-z0-9_-]*\s*:` 的宽松匹配——会把裸的 Note: / Explanation: /
# Sure: / Here: 等散文行误判为头部行，混入抽取结果污染语料。
_HEADER_RE = re.compile(
    r"^(?:Accept|Accept-Encoding|Accept-Language|Authorization|Bandwidth|Blocksize|"
    r"Cache-Control|Conference|Connection|Content-Base|Content-Encoding|"
    r"Content-Language|Content-Length|Content-Location|Content-Type|CSeq|Date|"
    r"Expires|From|If-Modified-Since|Last-Modified|Location|Proxy-Authenticate|"
    r"Proxy-Require|Public|Range|Referer|Require|Retry-After|RTP-Info|Scale|Server|"
    r"Session|Speed|Transport|Unsupported|User-Agent|Vary|Via|WWW-Authenticate)\s*:",
    re.IGNORECASE,
)

# 代码围栏（``` 或 ```rtsp 等）。
_FENCE_PREFIX = "```"

# FTP 命令行：整行「命令 [参数]」，命令统一大写、参数保留原样。
# 用 `(?:\s+.*)?$` 而非 `\s*$`：要求命令与参数之间至少一个空格，避免
# 把 `USERanonymous` 这类粘连误判为合法命令。
_FTP_CMD_RE = re.compile(
    r"^(" + "|".join(FTP_METHODS) + r")(?:\s+.*)?$",
    re.IGNORECASE,
)

# SIP 请求行：METHOD sip-uri SIP/2.0（大小写不敏感；group(1) 捕获方法名）。
_SIP_METHOD_RE = re.compile(
    r"^(" + "|".join(SIP_METHODS) + r")\s+\S+\s+SIP/2\.0\s*$",
    re.IGNORECASE,
)

# SIP 头部行：仅接受 SIP 标准头部白名单（Header-Name: value）。
# 与 RTSP 同理，不用宽松的 `^[A-Za-z...]*:` 匹配——会误吞 Note:/Explanation:/Sure: 等散文。
_SIP_HEADER_RE = re.compile(
    r"^(?:Accept|Accept-Contact|Accept-Encoding|Accept-Language|Alert-Info|Allow|"
    r"Also|Authorization|Call-ID|Call-Info|Contact|Content-Disposition|"
    r"Content-Encoding|Content-Language|Content-Length|Content-Type|CSeq|Date|"
    r"Error-Info|Event|Expires|From|In-Reply-To|Max-Forwards|MIME-Version|"
    r"Min-Expires|Organization|P-Asserted-Identity|Priority|Proxy-Authenticate|"
    r"Proxy-Authorization|Proxy-Require|RAck|Reason|Record-Route|Refer-To|"
    r"Referred-By|Reject-Contact|Reply-To|Require|Retry-After|Route|RSeq|Server|"
    r"Session-Expires|Subject|Subscription-State|Supported|Timestamp|To|User-Agent|"
    r"Via|Warning|WWW-Authenticate)\s*:",
    re.IGNORECASE,
)

# SDP body 行：单小写字母 + '='（v=/o=/s=/c=/t=/m=/a= 等，RFC 4566）。
_SDP_LINE_RE = re.compile(r"^[a-z]=")

# ---------------------------------------------------------------------------
# 路径判别特征（取自 chat-llm.c 三处 prompt 的稳定字面量）
# ---------------------------------------------------------------------------

# 增强路径：construct_prompt_for_templates 无关；enrich_sequence 的 user prompt 含该句。
_ENRICH_MARKERS = ("the modified sequence of client requests is:",)

# stall-chat 路径：construct_prompt_stall 含这些字样。
_STALL_MARKERS = ("Communication History:", "next proper client request")

# 语法抽取路径：construct_prompt_for_templates 含 "Output ONLY" 与 "COMMAND:"。
# 该路径跳过改写（原样透传），判定优先级最高（最危险，绝不能破坏 COMMAND 格式）。
_GRAMMAR_MARKERS = ("Output ONLY", "COMMAND:")

# 路径标签
GRAMMAR = "grammar"          # 语法抽取：透传
ENRICH = "enrich"            # 启动期增强：抽取
STALL = "stall"              # 运行期 stall-chat：抽取
UNKNOWN = "unknown"          # 未知：透传（向后兼容）

# 改写动作标签
ACTION_PASSTHROUGH = "passthrough"
ACTION_REWRITTEN = "rewritten"
ACTION_EMPTIED = "emptied"


# ---------------------------------------------------------------------------
# 结果结构
# ---------------------------------------------------------------------------

@dataclass
class RewriteResult:
    """改写结果：body 为回传字节；其余字段用于观测/日志/统计。"""

    body: bytes = b""
    path: str = UNKNOWN
    action: str = ACTION_PASSTHROUGH
    original_content: str = ""
    rewritten_content: str = ""
    note: str = ""


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def _as_bytes(data) -> bytes:
    """把 str/bytearray/bytes 归一为 bytes（透传时尽量保持原字节不变）。"""
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, str):
        return data.encode("utf-8")
    return data  # 理论上不会到达


def _dump_bytes(obj) -> bytes:
    """JSON 序列化为 UTF-8 字节。"""
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _coerce_object(data):
    """把 bytes/str/dict 归一为 dict（无法解析则返回 None）。"""
    if isinstance(data, dict):
        return data
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8", "replace")
    if isinstance(data, str):
        try:
            obj = json.loads(data)
        except (ValueError, TypeError):
            return None
        return obj if isinstance(obj, dict) else None
    return None


def _content_to_text(content) -> str:
    """把 message.content（str 或 OpenAI 多段数组）转为纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    chunks.append(item["text"])
                elif isinstance(item.get("content"), str):
                    chunks.append(item["content"])
            elif isinstance(item, str):
                chunks.append(item)
        return "\n".join(chunks)
    return ""


def extract_user_text(request_obj) -> str:
    """从请求体拼出所有 role=user 消息的文本，用于路径判别。"""
    if not isinstance(request_obj, dict):
        return ""
    messages = request_obj.get("messages")
    if not isinstance(messages, list):
        # 兼容极少数把 user 文本直接放顶层的请求
        for key in ("prompt", "user"):
            value = request_obj.get(key)
            if isinstance(value, str):
                return value
        return ""
    parts: list[str] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "user":
            continue
        text = _content_to_text(msg.get("content"))
        if text:
            parts.append(text)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 路径判别
# ---------------------------------------------------------------------------

def classify_request(request_obj) -> str:
    """根据请求体 user content 特征判定 ChatAFL 的三条 LLM 调用路径。

    返回 GRAMMAR / ENRICH / STALL / UNKNOWN 之一。
    - GRAMMAR：语法抽取，必须透传（不改写）。
    - ENRICH / STALL：需要抽取纯 RTSP 报文。
    - UNKNOWN：不匹配任何已知特征，透传（向后兼容）。
    """
    if not isinstance(request_obj, dict):
        return UNKNOWN
    user_text = extract_user_text(request_obj)
    if not user_text:
        return UNKNOWN
    # 语法抽取优先级最高：COMMAND: ["..."] 格式绝不能套抽取器。
    if any(marker in user_text for marker in _GRAMMAR_MARKERS):
        return GRAMMAR
    if any(marker in user_text for marker in _ENRICH_MARKERS):
        return ENRICH
    if any(marker in user_text for marker in _STALL_MARKERS):
        return STALL
    return UNKNOWN


# ---------------------------------------------------------------------------
# RTSP 报文抽取器
# ---------------------------------------------------------------------------

def extract_rtsp_messages(text: str) -> str:
    """从散文/带围栏的 LLM 回答中抽取纯 RTSP 报文序列。

    规则：
    - 一行匹配「METHOD URI RTSP/1.0」视为一个报文块的开始（方法名统一大写，URI 保持原样）。
    - 块内接受头部行（Header: value）与以空格/tab 开头的折叠续行。
    - 代码围栏行（``` 或 ```rtsp）一律忽略，且不打断当前块。
    - 其它行（前言/Explanation/列表项等）视为散文，结束当前块并忽略。
    - 多个报文块之间只保留**一个空行**。

    返回用 '\\n' 连接的报文序列（不含尾部换行）。换行规范化（\\n→\\r\\n 与尾部补
    \\r\\n\\r\\n）交给 ChatAFL 的 format_request_message。抽取不到任何合法报文时返回 ""。
    """
    if not isinstance(text, str) or not text:
        return ""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[list[str]] = []
    cur: list[str] | None = None

    def close_block() -> None:
        """结束当前块：去掉尾部空行，非空则入 blocks。"""
        nonlocal cur
        if cur is not None:
            while cur and cur[-1] == "":
                cur.pop()
            if cur:
                blocks.append(cur)
            cur = None

    for raw in lines:
        stripped = raw.strip()
        # 1) 代码围栏：忽略，且不打断当前块（容忍块内夹缝围栏）。
        if stripped.startswith(_FENCE_PREFIX):
            continue
        # 2) 报文首行：结束上一个块，开启新块（方法名统一大写，URI 保留原始大小写）。
        method_match = _METHOD_RE.match(stripped)
        if method_match:
            close_block()
            method = method_match.group(1).upper()
            cur = [method + stripped[method_match.end(1):]]
            continue
        if cur is None:
            # 3) 块外：忽略散文。
            continue
        if stripped == "":
            # 4) 块内空行：候选分隔（结束块时会去尾）。
            cur.append("")
            continue
        if _HEADER_RE.match(stripped) or raw.startswith(" ") or raw.startswith("\t"):
            # 5) 头部行 / 折叠续行：保留（用 stripped 去掉首尾空白）。
            cur.append(stripped)
            continue
        # 6) 其它行：散文，结束当前块。
        close_block()

    close_block()

    return "\n\n".join("\n".join(block) for block in blocks)


# ---------------------------------------------------------------------------
# FTP 报文抽取器
# ---------------------------------------------------------------------------

def extract_ftp_messages(text: str) -> str:
    """从散文/带围栏的 LLM 回答中抽取纯 FTP 命令序列。

    规则：
    - 一行匹配「命令 [参数]」（命令 ∈ FTP_METHODS，大小写不敏感）视为 FTP 命令，
      命令统一大写、参数保留原样。
    - 代码围栏行（``` 或 ```ftp）一律忽略。
    - 其它行（前言 / Explanation / 列表项 / "Sure! Here is..." 等散文）忽略。
    - FTP 是无头部、无版本号的行命令协议，命令间无需空行分隔，因此直接逐行过滤。

    返回用 '\\n' 连接的命令序列（不含尾部换行）。抽取不到任何合法命令时返回 ""。
    换行规范化（\\n→\\r\\n 与尾部补 \\r\\n\\r\\n）交给 ChatAFL 的 format_request_message。
    """
    if not isinstance(text, str) or not text:
        return ""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cmds: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith(_FENCE_PREFIX):
            continue
        m = _FTP_CMD_RE.match(stripped)
        if m:
            cmds.append(m.group(1).upper() + stripped[m.end(1):])
    return "\n".join(cmds)


# ---------------------------------------------------------------------------
# SIP 报文抽取器
# ---------------------------------------------------------------------------

def extract_sip_messages(text: str) -> str:
    """从散文/带围栏的 LLM 回答中抽取纯 SIP 报文序列。

    SIP 是文本头部协议：请求行「METHOD sip-uri SIP/2.0」+ 头部 + 空行 + 可选 SDP body。
    规则（与 RTSP 抽取器同构）：
    - 一行匹配「METHOD URI SIP/2.0」视为报文块开始（方法名统一大写，URI 保持原样）。
    - 块内接受头部行（SIP 头部白名单）与 SDP body 行（v=/o=/s=/c=/t=/m=/a=）。
    - 代码围栏行（``` 或 ```sip）一律忽略，且不打断当前块。
    - 其它行（前言/Explanation/列表项等）视为散文，结束当前块并忽略。
    - 多个报文块之间只保留一个空行。

    返回用 '\\n' 连接的报文序列（不含尾部换行）。换行规范化（\\n→\\r\\n 与尾部补
    \\r\\n\\r\\n）交给 ChatAFL 的 format_request_message。抽取不到任何合法报文时返回 ""。
    """
    if not isinstance(text, str) or not text:
        return ""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[list[str]] = []
    cur: list[str] | None = None

    def close_block() -> None:
        nonlocal cur
        if cur is not None:
            while cur and cur[-1] == "":
                cur.pop()
            if cur:
                blocks.append(cur)
            cur = None

    for raw in lines:
        stripped = raw.strip()
        # 1) 代码围栏：忽略，且不打断当前块。
        if stripped.startswith(_FENCE_PREFIX):
            continue
        # 2) 请求行：结束上一个块，开启新块（方法名统一大写，URI 保留原始大小写）。
        m = _SIP_METHOD_RE.match(stripped)
        if m:
            close_block()
            method = m.group(1).upper()
            cur = [method + stripped[m.end(1):]]
            continue
        if cur is None:
            # 3) 块外：忽略散文。
            continue
        if stripped == "":
            # 4) 块内空行：候选分隔（头部/body 边界，结束块时会去尾）。
            cur.append("")
            continue
        if _SIP_HEADER_RE.match(stripped) or raw.startswith(" ") or raw.startswith("\t"):
            # 5) 头部行 / 折叠续行：保留。
            cur.append(stripped)
            continue
        if _SDP_LINE_RE.match(stripped):
            # 6) SDP body 行（v=/o=/s=/c=/t=/m=/a=）：保留。
            cur.append(stripped)
            continue
        # 7) 其它行：散文，结束当前块。
        close_block()

    close_block()

    return "\n\n".join("\n".join(block) for block in blocks)


# ---------------------------------------------------------------------------
# 协议检测（选择 RTSP / FTP 抽取器）
# ---------------------------------------------------------------------------

# 协议标签
PROTO_RTSP = "rtsp"
PROTO_FTP = "ftp"
PROTO_SIP = "sip"
PROTO_UNKNOWN = "unknown"

# RTSP 报文特征：版本号 / URI scheme（FTP 命令协议无这两者）。
_RTSP_SIGNATURE_RE = re.compile(r"RTSP/1\.0|rtsp://", re.IGNORECASE)

# SIP 报文特征：版本号 SIP/2.0（请求行固定字面量，最特异）。
_SIP_SIGNATURE_RE = re.compile(r"SIP/2\.0", re.IGNORECASE)


def detect_protocol(request_obj) -> str:
    """根据请求体 user content 检测协议（rtsp / sip / ftp / unknown）。

    ChatAFL 的 prompt 协议无关，但 enrich/stall 的 user content 里嵌入了当前协议的
    真实报文序列（sequence / examples）：
    - RTSP 报文含 `RTSP/1.0` 版本号或 `rtsp://` URI。
    - SIP 报文含 `SIP/2.0` 版本号（请求行 METHOD uri SIP/2.0）。
    - FTP 报文是「命令 [参数]」行命令（无版本号 / URI）。
    据此判定协议，用于选择对应的报文抽取器。判定顺序：RTSP/SIP 特征优先（更特异），
    再检测 FTP 命令，均不命中返回 unknown（向后兼容走 RTSP 抽取器）。

    注意：ChatAFL 用 json_object_to_json_string 转义 sequence，故请求体里的报文换行
    是字面量 `\\r\\n`（反斜杠 r 反斜杠 n），而非真实换行。检测前先规范化为真实换行。
    """
    user_text = extract_user_text(request_obj)
    if not user_text:
        return PROTO_UNKNOWN
    if _RTSP_SIGNATURE_RE.search(user_text):
        return PROTO_RTSP
    if _SIP_SIGNATURE_RE.search(user_text):
        return PROTO_SIP
    # 字面转义符 → 真实换行（兼容 JSON 转义的 sequence 与真实换行两种来源）
    normalized = (user_text
                  .replace("\\r\\n", "\n")
                  .replace("\\n", "\n")
                  .replace("\\r", "\n"))
    for line in normalized.splitlines():
        if _FTP_CMD_RE.match(line.strip()):
            return PROTO_FTP
    return PROTO_UNKNOWN


# ---------------------------------------------------------------------------
# 响应改写入口
# ---------------------------------------------------------------------------

def _get_response_content(response_obj) -> str:
    """从 DeepSeek 响应体取 choices[0].message.content（结构异常返回 ""）。"""
    if not isinstance(response_obj, dict):
        return ""
    choices = response_obj.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _set_response_content(response_obj, content: str) -> None:
    """回写 choices[0].message.content（调用方保证结构完整）。"""
    response_obj["choices"][0]["message"]["content"] = content


def rewrite_response(request_body, response_body) -> RewriteResult:
    """代理层响应改写入口：根据请求路径，对 DeepSeek 响应做条件改写。

    参数可传 bytes/str/dict（bytes 需为 UTF-8 JSON）。

    处理策略：
    - 请求不可解析 / 未知路径 / 语法抽取路径 → 原样透传。
    - 增强 / stall 路径 → 按协议（RTSP/FTP）抽取纯报文回写 content。
    - 抽取失败（无合法报文）→ 置空 content（丢弃该条，ChatAFL 侧 continue 保护）。
    - 响应不可解析 / content 本就为空 → 原样透传。

    返回 RewriteResult（body 为回传字节）。
    """
    req_obj = _coerce_object(request_body)
    if req_obj is None:
        return RewriteResult(
            body=_as_bytes(response_body), path=UNKNOWN,
            action=ACTION_PASSTHROUGH, note="request unparseable",
        )

    path = classify_request(req_obj)

    # 仅增强 / stall 需要改写；语法抽取与未知路径一律透传。
    if path not in (ENRICH, STALL):
        return RewriteResult(
            body=_as_bytes(response_body), path=path,
            action=ACTION_PASSTHROUGH, note=f"path={path}: passthrough",
        )

    resp_obj = _coerce_object(response_body)
    if resp_obj is None:
        return RewriteResult(
            body=_as_bytes(response_body), path=path,
            action=ACTION_PASSTHROUGH, note="response unparseable, passthrough",
        )

    original = _get_response_content(resp_obj)
    if not original:
        return RewriteResult(
            body=_as_bytes(response_body), path=path,
            action=ACTION_PASSTHROUGH, original_content="",
            note="empty content, passthrough",
        )

    # 按协议选择抽取器（RTSP 报文 vs SIP 报文 vs FTP 命令）。
    protocol = detect_protocol(req_obj)
    if protocol == PROTO_FTP:
        cleaned = extract_ftp_messages(original)
    elif protocol == PROTO_SIP:
        cleaned = extract_sip_messages(original)
    else:
        cleaned = extract_rtsp_messages(original)

    if not cleaned:
        # 失败安全：置空 content，让 ChatAFL 因空 content 跳过写入。
        _set_response_content(resp_obj, "")
        return RewriteResult(
            body=_dump_bytes(resp_obj), path=path, action=ACTION_EMPTIED,
            original_content=original, rewritten_content="",
            note=f"no valid {protocol} message, content emptied",
        )

    _set_response_content(resp_obj, cleaned)
    return RewriteResult(
        body=_dump_bytes(resp_obj), path=path, action=ACTION_REWRITTEN,
        original_content=original, rewritten_content=cleaned,
        note=f"rewritten ok (protocol={protocol})",
    )


__all__ = [
    "GRAMMAR", "ENRICH", "STALL", "UNKNOWN",
    "PROTO_RTSP", "PROTO_FTP", "PROTO_SIP", "PROTO_UNKNOWN",
    "ACTION_PASSTHROUGH", "ACTION_REWRITTEN", "ACTION_EMPTIED",
    "RewriteResult", "classify_request", "extract_user_text",
    "detect_protocol", "extract_rtsp_messages", "extract_ftp_messages",
    "extract_sip_messages", "rewrite_response",
]
