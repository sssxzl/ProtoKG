# -*- coding: utf-8 -*-
"""scripts/corpus_gate.py —— 语料**发布准入闸**（CI gate，退出码非 0 即阻断）。

为什么需要它
------------
2026-10-31 实测坐实过一次**静默退化**：``traffic`` 源的事实里混入了两台不同设备
的抓包（含非目标 IP 摄像机 ``rtsp://10.11.26.98:554/isapi/...``），而当时的兜底
条件 ``if not msg.url or "localhost/seed" in msg.url:`` 对真实抓包 URL **不命中**
→ 原样透传 → 某份 RTSP 语料 **59.5%（22/37）的种子打向了错误主机**。

★ 关键教训：**现有所有健康度指标一条都不会红**（dup_fact_ids / toc_sourced_outcomes /
章节号命中全不受影响）—— 因为"打错主机"不是"弱种子"，是**坏种子**，而坏种子不
违反任何一条既有的结构不变式。故必须有一条**专门针对"种子指向哪里"的正确性闸**。

三条红线（判据见 docs/rq4_s4_corpus_release_gate_spec.md）
---------------------------------------------------------
=========  =====================================================================
红线      判据
=========  =====================================================================
**G1**    目标端点正确率 —— 语料中出现的**每个网络端点**都必须属于该协议的
          **合法端点集合**；违规端点数 > 阈值 → 失败。
**G2**    不可播会话占比 —— 语料引用的**会话/资源名**必须 ⊆ 目标环境的**可播
          清单**；违规引用数 > 阈值 → 失败。
**G5**    契约一致性 —— ``seedgen`` 产出条数必须 == profile 声明的契约条数；
          不一致 → **分级报告**（默认只告警；``--strict`` 参与阻断）。
=========  =====================================================================

★ G1 / G2 是**正确性闸**（无条件阻断）；G5 是**契约闸**（默认只告警）。
  理由：契约漂移有时是预期的（如 S1′ 重生成后条数合法变化 → 硬阻断会挡正常
  流程），而"打错主机"永远不是。

设计约束（与本仓既有风格一致）
------------------------------
· **只读**：本脚本**不写任何文件**（不生成/删除/修改 kb/、derived/、fused_hub/ 下
  的任何内容），只读取已存在的语料目录并打印报告。CI 里作为纯检查项接入。
· **配置驱动、协议无关**：合法端点集合、可播清单、端点抽取位置、会话名抽取规则
  **全部从 profile 派生**（复用 ``core/fused/downstream/target_env.py`` 的既有函
  数，不重复实现 URL 拆分），换协议 = 加一份 profile.json，脚本零改动。
· **适用性显式声明**：每条红线都**显式**给出"适用/不适用 + skipped_reason"——
  绝不静默跳过（「不适用」与「通过」在报告里必须**可区分**，否则 CI 假绿）。
· **可复算**：每条红线都打印「检查了什么 / 数据来源 / 判定依据 / 实测值 / 阈值 / 结论」。

用法
----
    python scripts/corpus_gate.py --protocol rtsp --seed-dir derived/seeds/rtsp/rq4_B
    python scripts/corpus_gate.py --protocol sip  --seed-dir derived/seeds/sip/rq4_B
    python scripts/corpus_gate.py --protocol smtp --seed-dir derived/seeds/smtp/rq4_B
    python scripts/corpus_gate.py --protocol rtsp --seed-dir derived/seeds/rtsp/rq4_B --json
    python scripts/corpus_gate.py --protocol rtsp --seed-dir <dir> --strict
    python scripts/corpus_gate.py --protocol rtsp --seed-dir <dir> --json-out report.json

退出码
------
* ``0`` —— 通过（无阻断级失败；G5 漂移在默认模式下只告警）
* ``1`` —— **阻断**（G1/G2 有违规；``--strict`` 时 G5 漂移也阻断）
* ``2`` —— 用法/环境错误（语料目录缺失、profile 缺失/不可读、环境名未声明或不唯一、
  可播清单不可解析等）—— **必须与 1 区分**：返 0 会让 CI 假绿，返 1 会掩盖真违规。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import paths  # noqa: E402
from core.fused.downstream.target_env import (  # noqa: E402
    _split_url,          # 私有工具函数：复用它保证 URL 拆分口径与归一化修复一致
    allowed_endpoints,   # ★ 合法端点集合：已上移到 core（与 action_seq 共用一份）
    endpoint_default_ports,
    playable_resource_names,
)

#: JSON 输出的 schema 版本（与 docs/rq4_s4_corpus_release_gate_spec.md §3.2 一致）。
SCHEMA_VERSION = "1.0"

#: G1 / G2 的默认阈值：**违规数 = 0**（打错主机 / 引用不可播会话都是坏种子）。
DEFAULT_MAX_VIOLATIONS = 0

#: ``violations[].files`` 最多列出的种子文件名数（避免 JSON 爆炸；总数记在
#: ``occurrences``）。
MAX_VIOLATION_FILES = 20

#: 闸名 → JSON 里的 ``name`` 字段（规格书 §3.2 固定）。
GATE_NAMES = {
    "G1": "target_endpoint_correctness",
    "G2": "playable_resource_ratio",
    "G5": "corpus_contract_consistency",
}

#: 带 authority 的绝对 URL（``scheme://host[:port]/...``）。
_ABSOLUTE_URL_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9+.\-]*://(\[[0-9A-Fa-f:.]+\]|[^:/@\s]+)(?::(\d{1,5}))?")


# ===========================================================================
# profile / 环境 / 分组 解析
# ===========================================================================

def load_profile(protocol: str, profile_path: Optional[Path] = None) -> dict:
    """读协议 profile（``fused_hub/targets/<protocol>/profile.json``）。

    Args:
        protocol: 协议名（小写）。
        profile_path: 显式 profile 路径；None → 标准位置。

    Returns:
        profile 字典；文件不存在或解析失败 → 空 dict（调用方负责报错）。
    """
    path = Path(profile_path) if profile_path else paths.target_profile(protocol)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def read_manifest(seed_dir: Path) -> dict:
    """读语料目录的 ``manifest.json``（溯源信息）；不存在/损坏 → 空 dict。

    ★ 兜底：RQ3 的布局是 ``<group>/manifest.json`` + ``<group>/seeds/*.raw``
      （manifest 在**父目录**），RQ4 的布局是 ``rq4_B/manifest.json`` + 同目录
      ``*.raw``。故父目录也查一次。
    """
    for base in (Path(seed_dir), Path(seed_dir).parent):
        path = base / "manifest.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and data:
            return data
    return {}


def profile_environments(profile: dict) -> dict:
    """profile 声明的目标环境表（``seedgen.environments``）。"""
    return dict((profile.get("seedgen") or {}).get("environments") or {})


def resolve_env(profile: dict, manifest: dict,
                env_arg: Optional[str] = None) -> tuple[Optional[str], dict]:
    """选出目标环境，返回 ``(环境名, 环境配置)``。

    优先级：
      1. 命令行 ``--env``（显式意图最高）；
      2. 语料 ``manifest.json`` 的 ``seedgen.target_env``（**语料自身记录的环境**
         —— 最忠实：它就是当初生成这份语料时用的环境）；
      3. profile 声明的**唯一**环境（规格书 §3.1 的默认口径）。

    ★ 第 3 条很重要：**违约的语料恰恰没有 manifest**（``seedgen.py`` 在条数
      自检失败时先退出、不写 manifest）⇒ 若无此兜底，闸会退回**协议级**契约，
      把"环境级重标定 39"错报成"契约 50"（误导性的期望值）。

    Raises:
        KeyError: 显式指定的环境名未在 profile 中声明（拼写错误必须显式失败）。
        ValueError: profile 声明了多个环境且未显式指定（无法判定 → 配置错误）。
    """
    envs = profile_environments(profile)
    manifest_env = str((manifest.get("seedgen") or {}).get("target_env") or "").strip()
    name = env_arg or (manifest_env or None)
    if not name:
        if len(envs) == 1:
            name = next(iter(envs))
        elif len(envs) > 1:
            raise ValueError(
                f"profile 声明了多个目标环境 {sorted(envs)}，无法判定；"
                f"请用 --env 显式指定")
        else:
            return (None, {})
    if name not in envs:
        raise KeyError(
            f"未知的目标环境 {name!r}（profile 声明了: {sorted(envs)}）")
    return (str(name), dict(envs.get(name) or {}))


def detect_group(seed_dir: Path, manifest: dict,
                 group_arg: Optional[str] = None) -> Optional[str]:
    """判定语料所属的**聚焦组**（A/B/C/D），返回组名或 None。

    优先级：命令行 ``--group`` → manifest 的 ``seedgen.focus_group`` / ``group``
    → 目录名尾部推断（``rq4_B`` → ``B``、``..._focusB`` → ``B``、``B`` → ``B``）。
    """
    if group_arg:
        return group_arg
    seedgen_cfg = manifest.get("seedgen") or {}
    for key in ("focus_group", "group"):
        value = seedgen_cfg.get(key) or manifest.get(key)
        if value:
            return str(value).strip().upper()
    for candidate in (Path(seed_dir).name, Path(seed_dir).parent.name):
        match = re.search(r"(?:^|[^A-Za-z])([A-D])$", candidate)
        if match:
            return match.group(1).upper()
    return None


def request_url_index(profile: dict) -> Optional[int]:
    """从 profile 的 ``raw_format.request_line`` 模板解析出 **URL 字段位置**。

    模板形如 ``"{method} {url} {version}"`` → URL 是请求行的第 2 个空白分隔字段
    （下标 1）。命令行协议（如 SMTP 的 ``"{method} {argument}"``）**没有** ``{url}``
    字段 → 返回 None（该协议无 URL 概念 → 相关红线不适用）。
    """
    template = str((profile.get("raw_format") or {}).get("request_line") or "").strip()
    if not template:
        return None
    for idx, field_name in enumerate(template.split()):
        if "{url}" in field_name:
            return idx
    return None


def uri_form(profile: dict) -> str:
    """profile 声明的目标 URI 形态。

    · ``hierarchical`` —— ``scheme://authority/...``：authority 即**路由端点**
      （RTSP）→ 端点从 URL 的 authority 抽取；
    · ``opaque``       —— ``scheme:opaque``（如 SIP 的 ``sip:user@host``）：URI 的
      domain 本身是**逻辑实体标识**，但**端点仍要检查**（只是抽取位置不同：请求行
      R-URI + 客户端自有地址的头部）；
    · ``none``         —— profile 未声明目标 URI（如 SMTP）→ 无端点概念。
    """
    default_url = str(profile.get("default_url") or "").strip()
    if not default_url:
        return "none"
    return "hierarchical" if "://" in default_url else "opaque"


# ===========================================================================
# 合法端点集合（配置派生）
# ===========================================================================





# ===========================================================================
# 端点抽取
# ===========================================================================

def _is_hostlike(text: str) -> bool:
    """判断字符串是否**像网络主机名/地址**（用于区分 ``sip:bob`` 这类"只有 user"的
    URI）。规则：含 ``.`` 或 ``:``，或是 ``localhost``。"""
    value = str(text or "").strip()
    if not value:
        return False
    return "." in value or ":" in value or value.lower() == "localhost"


def _normalize_hostport(authority: str, default_port: str) -> Optional[str]:
    """把 authority（可能带 userinfo / 可能缺端口）规范成 ``host:port``。

    * 剥掉 ``user@``（只检查 host:port，不检查 user 部分——官方 SIP 语料本身就有
      ``sip:35104723@sip.cybercity.dk`` 这类实例特定对端）；
    * 缺端口时用 ``default_port`` 补齐；
    * 不像主机名的（如 ``bob``）→ None（**跳过，不判违规**）。
    """
    text = str(authority or "").strip().strip("<>")
    if not text:
        return None
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    text = text.strip()
    if not text:
        return None
    if text.startswith("["):                      # IPv6 字面量
        host, _, rest = text.partition("]")
        host = host + "]"
        port = rest[1:] if rest.startswith(":") and rest[1:].isdigit() else ""
        return f"{host}:{port or default_port}" if (port or default_port) else host
    if ":" in text:
        host, _, port = text.rpartition(":")
        if port.isdigit():
            return f"{host}:{port}"
        return text
    if not _is_hostlike(text):
        return None
    return f"{text}:{default_port}" if default_port else text


def extract_request_urls(text: str, url_index: int) -> list[str]:
    """抽取一条种子文本里**所有消息的请求行 URL**。

    请求行的判定：第 0 个字段是**不含冒号的全大写方法名**（故 ``CSeq: 1`` /
    ``Via: ...`` 这类头部行不会被误判为请求行），且该行至少有 ``url_index + 1``
    个字段。
    """
    urls: list[str] = []
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) <= url_index:
            continue
        method = tokens[0]
        if not method or ":" in method or not method.isupper():
            continue
        url = tokens[url_index]
        if "://" not in url and not re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*:", url):
            continue
        urls.append(url)
    return urls


def extract_endpoints(text: str, profile: dict,
                      url_index: Optional[int]) -> list[tuple[str, str]]:
    """抽取一条种子文本里的**全部网络端点**，返回 ``[(host:port, 位置)]``。

    ★ 抽取位置**按 URI 形态分流**（配置派生，非协议名硬编码）：

    · ``hierarchical``（``scheme://authority/...``，如 RTSP）—— 端点即 URL 的
      authority，全文扫描（请求行 / 头部 / 消息体都算）。

    · ``opaque``（``scheme:opaque``，如 SIP）—— **只查 3 个路由相关位置**：
      ① 请求行 **R-URI** 的主机（剥掉 ``user@``；无 host 的跳过）；
      ② **客户端自有地址的头部**（``profile.seedgen.client_side.headers`` 声明，
         实测 SIP = ``["Via", "Contact"]``）——**只取 ``;`` 之前的 sent-by**
         （``branch=``/``tag=``/``rport=`` 里的 IP 是随机不透明串，不是端点）。

      ★ **明确排除** ``From:`` / ``To:``（实例特定对端身份，官方语料本身就有）、
        ``Call-ID`` 之类事务标识符、以及所有 ``client_side.headers`` 之外的头部；
        也**不抓全文 IP**（否则 ``branch=`` 里的 ``192.168.1.2`` 会误报上百次）。
    """
    form = uri_form(profile)
    server_port, client_port = endpoint_default_ports(profile)
    client_headers = {
        str(h).strip().lower()
        for h in ((profile.get("seedgen") or {}).get("client_side") or {}
                  ).get("headers") or []
    }
    found: list[tuple[str, str]] = []

    if form == "hierarchical":
        for match in _ABSOLUTE_URL_RE.finditer(text):
            host = match.group(1)
            port = match.group(2) or server_port
            endpoint = _normalize_hostport(f"{host}:{port}" if port else host,
                                           server_port)
            if endpoint:
                found.append((endpoint, "url-authority"))
        return found

    if form == "opaque":
        # ① R-URI（请求行的 URL 字段）—— 容忍 `sip:` 与 `sip://` 双斜杠两种形态
        if url_index is not None:
            for url in extract_request_urls(text, url_index):
                _scheme, netloc, _path = _split_url(url)
                endpoint = _normalize_hostport(netloc, server_port)
                if endpoint:
                    found.append((endpoint, "r-uri"))
        # ② 客户端自有地址的头部（Via / Contact）
        for line in text.splitlines():
            name, sep, value = line.partition(":")
            if not sep:
                continue
            if name.strip().lower() not in client_headers:
                continue
            # 只取第一个 ';' 之前的部分（sent-by）—— ';' 之后是 branch/tag/rport
            head = value.split(";", 1)[0]
            for token in head.split():
                _scheme, netloc, _path = _split_url(token.strip("<>"))
                endpoint = _normalize_hostport(netloc, client_port)
                if endpoint:
                    found.append((endpoint, "client-header"))
        return found

    return found


def extract_sessions(text: str, profile: dict) -> list[str]:
    """抽取一条种子文本里引用的**会话/资源名**（G2 用）。

    ★ 规则（规格书 §2.2）：从**请求行**取**主机后的第一个路径段**——
    ``SETUP rtsp://host/<session>/track1`` 的末段是 ``track1``（那是 track，不是
    会话名），第一段才是会话名。

    方法名清单来自 ``profile.allowed_methods``，scheme 来自 profile 的
    ``default_url`` ⇒ **不硬编码协议**。
    """
    methods = [str(m).strip().upper() for m in (profile.get("allowed_methods") or [])
               if str(m).strip()]
    default_url = str(profile.get("default_url") or "").strip()
    scheme = default_url.split("://", 1)[0] if "://" in default_url else ""
    if not methods or not scheme:
        return []
    pattern = re.compile(
        r"^(?:" + "|".join(re.escape(m) for m in methods) + r")\s+"
        + re.escape(scheme) + r"://[^/\s]+/([^/\s?]+)", re.MULTILINE)
    return pattern.findall(text)


# ===========================================================================
# 三条红线
# ===========================================================================

def _skip(gate: str, reason: str, **extra: Any) -> dict:
    """构造一条「不适用」的红线结果（``skipped_reason`` 必填）。

    ★ ``"pass"`` 键**由本函数默认填入**（不适用 ⇒ 不算失败）。
      原因：``pass`` 是 Python 保留字，**不能**作函数调用的关键字实参
      （``f(pass=True)`` 是 SyntaxError），而 ``f("pass": True)`` 也不是合法的
      调用语法（那是 dict 字面量语法）⇒ 调用处无法安全地传这个键。
      统一由本函数兜底，调用处只传普通键。
    """
    result: dict[str, Any] = {
        "name": GATE_NAMES[gate],
        "applicable": False,
        "skipped_reason": reason,
        "pass": True,
    }
    result.update(extra)
    return result


def check_g1(profile: dict, protocol: str, seed_texts: list[tuple[Path, str]],
             env_cfg: dict, max_violations: int) -> dict:
    """G1：语料中出现的每个网络端点都必须属于该协议的合法端点集合。"""
    url_index = request_url_index(profile)
    allowed, _endpoint_sources = allowed_endpoints(profile, env_cfg)

    # 先抽端点（用于判定"语料里到底有没有端点"——SMTP 的 skip 依据）
    per_file: list[tuple[Path, list[str]]] = []
    all_endpoints: list[str] = []
    for path, text in seed_texts:
        endpoints = [ep for ep, _pos in
                     extract_endpoints(text, profile, url_index)]
        per_file.append((path, endpoints))
        all_endpoints.extend(endpoints)

    if not allowed:
        if all_endpoints:
            reason = (f"{protocol}: profile 未声明任何目标端点（default_url 为空），"
                      f"无法派生合法端点集合 → G1 不适用"
                      f"（但语料中检出 {len(all_endpoints)} 个端点，需人工确认）")
        else:
            reason = (f"{protocol}: 语料中不含任何网络端点（端点数 = 0），"
                      f"且 profile.default_url 为空 → G1 不适用"
                      f"（SMTP 是明文协议，连接目标在 TCP 层决定，不以 URL 表达）")
        return _skip("G1", reason, allowed_endpoints=[], endpoints_found={},
                     violations=[], violation_count=0, threshold=max_violations)

    if not all_endpoints:
        return _skip("G1", f"{protocol}: 语料中不含任何网络端点（端点数 = 0）"
                            f" → G1 不适用（无可比对的端点）",
                     allowed_endpoints=sorted(allowed), endpoints_found={},
                     violations=[], violation_count=0, threshold=max_violations)

    endpoints_found = Counter(all_endpoints)
    violations: Counter[str] = Counter()
    violation_files: dict[str, list[str]] = {}
    for path, endpoints in per_file:
        bad = sorted({endpoint for endpoint in endpoints if endpoint not in allowed})
        if bad:
            for endpoint in bad:
                violations[endpoint] += 1
                violation_files.setdefault(endpoint, []).append(path.name)

    violation_list = [
        {
            "endpoint": endpoint,
            "occurrences": count,
            "files": violation_files.get(endpoint, [])[:MAX_VIOLATION_FILES],
        }
        for endpoint, count in violations.most_common()
    ]
    violation_count = sum(violations.values())
    return {
        "name": GATE_NAMES["G1"],
        "applicable": True,
        "skipped_reason": None,
        "allowed_endpoints": sorted(allowed),
        "endpoints_found": dict(endpoints_found.most_common()),
        "violations": violation_list,
        "violation_count": violation_count,
        "threshold": max_violations,
        "pass": violation_count <= max_violations,
    }


def check_g2(profile: dict, protocol: str, seed_texts: list[tuple[Path, str]],
             env_cfg: dict, max_violations: int) -> dict:
    """G2：语料引用的会话/资源名必须 ⊆ 目标环境的可播清单。"""
    try:
        playable = playable_resource_names(profile, protocol, env_cfg)
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError(
            f"可播资源清单不可用（profile.seedgen.environments.<env>."
            f"playable_resources_file）：{exc}") from exc

    if not playable:
        return _skip("G2", f"{protocol}: 协议无「会话/资源」概念，"
                            f"profile 未声明可播清单 → G2 不适用",
                     allowed_resources=[], resources_found={}, violations=[],
                     violation_count=0, threshold=max_violations)

    allowed = {str(name) for name in playable}
    per_file: list[tuple[Path, list[str]]] = []
    all_sessions: list[str] = []
    for path, text in seed_texts:
        sessions = extract_sessions(text, profile)
        per_file.append((path, sessions))
        all_sessions.extend(sessions)

    if not all_sessions:
        return _skip("G2", f"{protocol}: 语料中未解析出任何会话名 → G2 不适用"
                            f"（无可比对的会话引用）",
                     allowed_resources=sorted(allowed), resources_found={},
                     violations=[], violation_count=0, threshold=max_violations)

    resources_found = Counter(all_sessions)
    violations: Counter[str] = Counter()
    violation_files: dict[str, list[str]] = {}
    for path, sessions in per_file:
        bad = sorted({name for name in sessions if name not in allowed})
        if bad:
            for name in bad:
                violations[name] += 1
                violation_files.setdefault(name, []).append(path.name)

    violation_list = [
        {
            "resource": name,
            "occurrences": count,
            "files": violation_files.get(name, [])[:MAX_VIOLATION_FILES],
        }
        for name, count in violations.most_common()
    ]
    violation_count = sum(violations.values())
    return {
        "name": GATE_NAMES["G2"],
        "applicable": True,
        "skipped_reason": None,
        "allowed_resources": sorted(allowed),
        "resources_found": dict(resources_found.most_common()),
        "violations": violation_list,
        "violation_count": violation_count,
        "threshold": max_violations,
        "pass": violation_count <= max_violations,
    }


def check_g5(profile: dict, protocol: str, group: Optional[str],
             seed_files: list[Path], manifest: dict, env_name: Optional[str],
             strict: bool) -> dict:
    """G5：产出条数 == profile 声明的契约条数。

    期望值来源（**分协议级 vs 环境级**，规格书 §1 / §5）：
      · 环境级 ``profile.seedgen.environments.<env>.focus_group.<组>.seeds``
        （RTSP / SIP）；
      · 协议级 ``profile.seedgen.focus_group.<组>.seeds``（SMTP —— profile **没有**
        ``environments`` 段，取错字段会拿到 undefined）。

    严重级别：默认只**告警**；``--strict`` 时升级为阻断级失败。
    """
    if not group:
        return _skip("G5", "无法判定语料所属的聚焦组（manifest 无记录、目录名无法"
                            "推断、且未显式 --group）→ G5 不适用",
                     contract_source=None, expected=None, actual=len(seed_files))

    proto_fg = ((profile.get("seedgen") or {}).get("focus_group") or {}).get(group)
    env_fg: dict = {}
    if env_name:
        env_cfg = (profile_environments(profile).get(env_name) or {})
        env_fg = (env_cfg.get("focus_group") or {}).get(group) or {}

    if env_fg.get("seeds") is not None:
        expected = env_fg["seeds"]
        contract_source = (f"profile.seedgen.environments.{env_name}."
                           f"focus_group.{group}.seeds")
    elif isinstance(proto_fg, dict) and proto_fg.get("seeds") is not None:
        expected = proto_fg["seeds"]
        contract_source = f"profile.seedgen.focus_group.{group}.seeds"
    else:
        return _skip("G5", f"profile 未声明 focus_group.{group}.seeds 契约 → G5 不适用",
                     contract_source=None, expected=None, actual=len(seed_files))

    actual = len(seed_files)
    passed = expected == actual
    result: dict[str, Any] = {
        "name": GATE_NAMES["G5"],
        "applicable": True,
        "skipped_reason": None,
        "contract_source": contract_source,
        "expected": expected,
        "actual": actual,
        "pass": passed,
    }
    if not passed:
        # 分级：默认只告警（契约漂移有时是预期的），--strict 才阻断。
        result["warning"] = (
            f"契约漂移：期望 {expected} != 实际 {actual}"
            f"（{'阻断' if strict else '默认仅告警，不阻断'}）")
    return result


# ===========================================================================
# 闸门编排
# ===========================================================================

def run_gate(protocol: str, seed_dir: Path, profile: dict,
             env_name: Optional[str] = None, env_cfg: Optional[dict] = None,
             group: Optional[str] = None,
             max_violations: int = DEFAULT_MAX_VIOLATIONS,
             strict: bool = False, manifest: Optional[dict] = None) -> dict:
    """跑全部红线，返回规格书 §3.2 定义的 JSON 报告。"""
    seed_dir = Path(seed_dir)
    manifest = manifest if manifest is not None else read_manifest(seed_dir)
    if env_cfg is None:
        env_name, env_cfg = resolve_env(profile, manifest, env_name)
    seed_files = sorted(seed_dir.glob("*.raw"))
    seed_texts = [(path, path.read_text(encoding="utf-8", errors="replace"))
                   for path in seed_files]

    gates = {
        "G1": check_g1(profile, protocol, seed_texts, env_cfg, max_violations),
        "G2": check_g2(profile, protocol, seed_texts, env_cfg, max_violations),
        "G5": check_g5(profile, protocol, group, seed_files, manifest, env_name,
                       strict),
    }
    blocking_failed = any(not gates[g]["pass"] for g in ("G1", "G2"))
    if strict:
        blocking_failed = blocking_failed or not gates["G5"]["pass"]
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol": protocol,
        "env": env_name,
        "group": group,
        "seed_dir": str(seed_dir),
        "seed_files": len(seed_files),
        "gates": gates,
        "overall_pass": not blocking_failed,
    }


# ===========================================================================
# 报告渲染
# ===========================================================================

def render_report(report: dict) -> str:
    """渲染人类可读报告。

    ★ 「不适用」必须与「通过」**可区分**：skip 的红线打印 ``G<n> skipped: <原因>``，
      避免 CI 日志里把"没查"误读成"查过且通过"（CI 假绿）。
    """
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("ProtoRAG 语料发布准入闸（corpus release gate）")
    lines.append("=" * 72)
    lines.append(f"协议        : {report.get('protocol')}")
    lines.append(f"语料目录    : {report.get('seed_dir')}")
    lines.append(f"目标环境    : {report.get('env') or '(未选 —— 无环境级约束)'}")
    lines.append(f"聚焦组      : {report.get('group') or '(未判定)'}")
    lines.append(f"种子文件数  : {report.get('seed_files')}")

    for gate in ("G1", "G2", "G5"):
        data = report["gates"][gate]
        lines.append("")
        if not data.get("applicable", True):
            lines.append(f"--- {gate} {data['name']} ---")
            lines.append("  结论       : SKIPPED（不适用）")
            lines.append(f"  原因       : {data['skipped_reason']}")
            lines.append("  ⚠ 不适用 ≠ 通过（本闸未对该语料做出判定）")
            continue
        lines.append(f"--- {gate} {data['name']} ---")
        if gate == "G1":
            lines.append("  检查了什么 : 语料中出现的每个网络端点是否属于合法端点集合")
            lines.append(f"  合法端点集 : {data['allowed_endpoints']}")
            lines.append(f"  实测端点   : {data['endpoints_found']}")
            lines.append(f"  违规       : {data['violations']}")
        elif gate == "G2":
            lines.append("  检查了什么 : 语料引用的会话/资源名是否 ⊆ 可播清单")
            lines.append(f"  可播清单   : {data['allowed_resources']}")
            lines.append(f"  实测会话   : {data['resources_found']}")
            lines.append(f"  违规       : {data['violations']}")
        else:
            lines.append("  检查了什么 : seedgen 产出条数是否等于 profile 契约条数")
            lines.append(f"  契约来源   : {data.get('contract_source')}")
            lines.append(f"  实测值     : 期望 {data.get('expected')} vs "
                         f"实际 {data.get('actual')}")
        lines.append(f"  违规数     : {data.get('violation_count', 0)}")
        lines.append(f"  阈值       : ≤ {data.get('threshold', 0)}")
        if data.get("warning"):
            lines.append(f"  ⚠ 告警     : {data['warning']}")
        lines.append(f"  结论       : [{'PASS' if data.get('pass') else 'FAIL'}]"
                     f" {'通过' if data.get('pass') else '失败（阻断）'}")

    lines.append("")
    lines.append("-" * 72)
    lines.append(f"总判定：{'通过' if report['overall_pass'] else '阻断（红线违规）'}")
    lines.append("-" * 72)
    return "\n".join(lines)


# ===========================================================================
# CLI
# ===========================================================================

def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。"""
    parser = argparse.ArgumentParser(
        description="ProtoRAG 语料发布准入闸（G1 目标端点正确率 / G2 不可播会话占比"
                    "/ G5 契约一致性）；退出码 0 通过 / 1 阻断 / 2 配置错误。"
                    "**只读**：不修改任何文件。")
    parser.add_argument("--protocol", required=True,
                        help="协议名（如 rtsp / sip / smtp）")
    parser.add_argument("--seed-dir", required=True,
                        help="语料目录（含 *.raw 种子文件）")
    parser.add_argument("--profile", default=None,
                        help="profile.json 路径（默认 fused_hub/targets/<protocol>/profile.json）")
    parser.add_argument("--env", "--target-env", dest="env", default=None,
                        metavar="NAME",
                        help="目标环境名（默认取语料 manifest 记录，再退回 profile "
                             "声明的唯一环境）")
    parser.add_argument("--group", default=None, metavar="A|B|C|D",
                        help="聚焦组（默认取 manifest 记录，再退回目录名推断）")
    parser.add_argument("--max-violations", type=int, default=DEFAULT_MAX_VIOLATIONS,
                        help="G1/G2 的违规数上限"
                             f"（默认 {DEFAULT_MAX_VIOLATIONS}）")
    parser.add_argument("--strict", action="store_true",
                        help="G5 契约漂移也参与阻断（默认只告警）")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 输出报告（CI 机器可读）")
    parser.add_argument("--json-out", default=None, metavar="FILE",
                        help="把 JSON 报告写到文件（不会写入 kb/ derived/ fused_hub/）")
    parser.add_argument("--baseline", default=None, metavar="FILE",
                        help="历史基线 JSON；提供时额外输出各闸的 delta")
    return parser


def _guard_output_path(path: Path) -> None:
    """禁止把报告写进 kb/ derived/ fused_hub/（闸是只读检查器）。"""
    resolved = path.resolve()
    for protected in ("kb", "derived", "fused_hub"):
        root = (REPO_ROOT / protected).resolve()
        if resolved == root or root in resolved.parents:
            raise ValueError(
                f"拒绝写入受保护目录 {protected}/（闸是只读检查器）：{resolved}")


def main(argv: Optional[list[str]] = None) -> int:
    """CLI 入口。

    Returns:
        0 = 通过；1 = 阻断；2 = 用法/环境错误。
    """
    args = build_parser().parse_args(argv)
    protocol = str(args.protocol).lower()
    seed_dir = Path(args.seed_dir).expanduser()
    if not seed_dir.is_absolute():
        seed_dir = (Path.cwd() / seed_dir).resolve()

    if not seed_dir.is_dir():
        print(f"!! 语料目录不存在: {seed_dir}", file=sys.stderr)
        return 2

    profile = load_profile(protocol, Path(args.profile) if args.profile else None)
    if not profile:
        print(f"!! profile 缺失或不可解析: protocol={protocol} "
              f"path={args.profile or paths.target_profile(protocol)}",
              file=sys.stderr)
        return 2

    manifest = read_manifest(seed_dir)
    try:
        env_name, env_cfg = resolve_env(profile, manifest, args.env)
    except (KeyError, ValueError) as exc:
        print(f"!! {exc}", file=sys.stderr)
        return 2

    group = detect_group(seed_dir, manifest, args.group)
    try:
        report = run_gate(protocol, seed_dir, profile, env_name=env_name,
                          env_cfg=env_cfg, group=group,
                          max_violations=int(args.max_violations),
                          strict=bool(args.strict), manifest=manifest)
    except ValueError as exc:
        print(f"!! {exc}", file=sys.stderr)
        return 2

    if args.baseline:
        try:
            baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"!! 基线文件不可读: {exc}", file=sys.stderr)
            return 2
        report["baseline_delta"] = {
            gate: report["gates"][gate].get("violation_count", 0)
            - (baseline.get("gates", {}).get(gate, {}) or {}).get(
                "violation_count", 0)
            for gate in ("G1", "G2", "G5")
        }

    if args.json_out:
        out_path = Path(args.json_out).expanduser()
        try:
            _guard_output_path(out_path)
        except ValueError as exc:
            print(f"!! {exc}", file=sys.stderr)
            return 2
        try:
            if out_path.parent and not out_path.parent.exists():
                out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        except OSError as exc:
            print(f"!! 报告写入失败: {exc}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_report(report))

    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
