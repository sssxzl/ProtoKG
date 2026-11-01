# -*- coding: utf-8 -*-
"""scripts/corpus_gate.py —— 语料**发布准入闸**（CI gate，退出码非 0 即阻断）。

为什么需要它
------------
2026-10-31 实测坐实过一次**静默退化**：`traffic` 源的事实里混入了两台不同设备
的抓包（含非目标 IP 摄像机 ``rtsp://10.11.26.98:554/isapi/...``），而当时的
兜底条件 ``if not msg.url or "localhost/seed" in msg.url:`` 对真实抓包 URL
**不命中** → 原样透传 → 某份 RTSP 语料 **59.5%（22/37）的种子打向了错误主机**。

★ 关键教训：**现有所有健康度指标一条都不会红**（dup_fact_ids / toc_sourced_outcomes /
章节号命中全不受影响）—— 因为"打错主机"不是"弱种子"，是**坏种子**，而坏种子不
违反任何一条既有的结构不变式。故必须有一条**专门针对"种子指向哪里"的正确性闸**。

本脚本实现三条红线（编号沿用 docs/rq4_aflnet_exp_design.md §12.4.4）：

=========  =====================================================================
红线      判据
=========  =====================================================================
**G1**    目标主机正确率 —— 种子**请求行**的 URL host:port 必须指向目标环境的
          服务端点；指向非目标端点的种子占比 > 阈值 → 失败。
**G2**    不可播会话占比 —— 种子引用的会话/资源名必须 ⊆ 目标环境的**可播清单**
          （``target_env.playable_resource_names``）；引用不可播资源名的种子
          占比 > 阈值 → 失败。
**G5**    契约一致性 —— profile 声明的 ``seedgen.focus_group.<组>.seeds``
          （期望条数）与**实际生成的条数**必须一致；不一致 → **分级报告**
          （默认只告警；``--strict`` 参与阻断）。
=========  =====================================================================

设计约束（与本仓既有风格一致）
------------------------------
· **只读**：本脚本**不写任何文件**（不生成/删除/修改 kb/、derived/、fused_hub/ 下
  的任何内容），只读取已存在的语料目录并打印报告。CI 里作为纯检查项接入。
· **配置驱动、协议无关**：目标端点、可播清单、URL 字段位置、聚焦组契约**全部从
  profile 派生**（复用 ``core/fused/downstream/target_env.py`` 的既有函数，不重复
  实现 host 解析），换协议 = 加一份 profile.json，脚本零改动。
· **适用性显式声明**：每条红线都**显式**给出"适用/不适用 + 原因"——绝不静默跳过。
  典型：SIP 的 Request-URI 是 ``sip:user@host`` 形态，其 domain 是**逻辑实体标识、
  不决定路由**（历史结论，见 target_env.py 模块 docstring）→ **G1 对 SIP 不适用**。
· **可复算**：每条红线都打印「检查了什么 / 数据来源 / 判定依据 / 实测值 / 阈值 / 结论」。

用法
----
    python scripts/corpus_gate.py --protocol rtsp --seed-dir derived/seeds/rtsp/rq4_B
    python scripts/corpus_gate.py --protocol sip  --seed-dir derived/seeds/sip/rq4_B
    python scripts/corpus_gate.py --protocol smtp --seed-dir derived/seeds/smtp/rq4_B
    python scripts/corpus_gate.py --protocol rtsp --seed-dir derived/rq3/B/seeds --strict
    python scripts/corpus_gate.py --protocol rtsp --seed-dir <dir> --json   # CI 机器可读

退出码
------
* ``0`` —— 通过（无阻断级失败；G5 漂移在默认模式下只告警）
* ``1`` —— **阻断**（存在阻断级红线失败；``--strict`` 时 G5 漂移也参与阻断）
* ``2`` —— 用法/配置错误（语料目录缺失、profile 缺失、环境名未声明等）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import paths  # noqa: E402
from core.fused.downstream.target_env import (  # noqa: E402
    _split_url,          # 私有工具函数：复用它保证 URL 拆分口径与归一化修复一致
    effective_config,
    endpoint_normalization_enabled,
    playable_resource_names,
    select_environment,
    target_endpoint,
)

# ===========================================================================
# 默认阈值
# ===========================================================================

#: G1 默认阈值：**指向非目标端点的种子占比**上限。
#: 默认 0.0 —— 与 docs/rq4_aflnet_exp_design.md §12.4.4 的「命中率 = 100%」一致：
#: 打向错误主机的种子不是"弱种子"是"坏种子"，一条即阻断。阈值可配置。
DEFAULT_MAX_WRONG_TARGET_RATIO = 0.0

#: G2 默认阈值：**引用不可播资源名的种子占比**上限。
#: 默认 0.0 —— 同上（设计文档建议「= 0%」）。阈值可配置。
DEFAULT_MAX_UNPLAYABLE_RATIO = 0.0

#: 已知的历史**契约漂移**签名（协议, 组）→ (契约期望, 重生成实际)。
#: 来源：docs/rq4_aflnet_exp_design.md §12.1 与
#: docs/rfc_reform_a_implementation_report.md（"契约 rtsp 50 / sip 25 / smtp 78 与
#: 当前实际重生成 65/20/61 失配"）。这是**历史契约过期**（待用户决策），不是本闸门
#: 引入的回归 → 报告里显式标注为"已知漂移"。
KNOWN_DRIFT: dict[tuple[str, str], tuple[int, int]] = {
    ("rtsp", "B"): (50, 65),
    ("sip", "B"): (25, 20),
    ("smtp", "B"): (78, 61),
}

#: 状态常量。
STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_WARN = "WARN"
STATUS_NA = "N/A"


# ===========================================================================
# 数据结构
# ===========================================================================

@dataclass
class Thresholds:
    """三条红线的阈值（全部可配置）。"""

    #: G1：指向非目标 host:port 的**种子数占比**上限（ratio > 阈值 → 失败）。
    max_wrong_target_ratio: float = DEFAULT_MAX_WRONG_TARGET_RATIO
    #: G2：引用不可播资源名的**种子数占比**上限（ratio > 阈值 → 失败）。
    max_unplayable_ratio: float = DEFAULT_MAX_UNPLAYABLE_RATIO


@dataclass
class GateOutcome:
    """一条红线的判定结果（可复算：每项都带数据来源与实测值）。"""

    gate: str
    title: str
    status: str
    #: 是否参与阻断（退出码）。
    blocking: bool = False
    summary: str = ""
    #: 检查了什么。
    checked: str = ""
    #: 数据来源。
    sources: str = ""
    #: 判定依据。
    criteria: str = ""
    #: 实测值。
    measured: str = ""
    #: 阈值。
    threshold: str = ""
    #: 结构化明细（供 --json 消费）。
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        """是否构成阻断级失败。"""
        return self.status == STATUS_FAIL and self.blocking

    def to_dict(self) -> dict[str, Any]:
        """转成可 JSON 序列化的字典。"""
        return {
            "gate": self.gate,
            "title": self.title,
            "status": self.status,
            "blocking": self.blocking,
            "summary": self.summary,
            "checked": self.checked,
            "sources": self.sources,
            "criteria": self.criteria,
            "measured": self.measured,
            "threshold": self.threshold,
            "details": self.details,
        }


# ===========================================================================
# profile / 环境 / 分组 解析
# ===========================================================================

def load_profile(protocol: str, profile_path: Optional[Path] = None) -> dict:
    """读协议 profile（``fused_hub/targets/<protocol>/profile.json``）。

    Args:
        protocol: 协议名（小写）。
        profile_path: 显式 profile 路径（测试/临时场景用）；None → 标准位置。

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


def resolve_env(profile: dict, manifest: dict,
                env_arg: Optional[str] = None) -> tuple[Optional[str], dict]:
    """选出目标环境，返回 ``(环境名, 环境配置)``。

    优先级：
      1. 命令行 ``--target-env``（显式意图最高）；
      2. 语料 ``manifest.json`` 的 ``seedgen.target_env``（**语料自身记录的环境**
         —— 最忠实：它就是当初生成这份语料时用的环境）；
      3. profile 的默认环境 ``seedgen.environment``（未声明 → 无环境）。

    Raises:
        KeyError: 显式指定的环境名未在 profile 中声明（拼写错误必须显式失败）。
    """
    manifest_env = str((manifest.get("seedgen") or {}).get("target_env") or "").strip()
    name = env_arg or (manifest_env or None)
    return select_environment(profile, name)


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
    # 目录名推断：RQ4 的 "rq4_B" / RQ3 的 "B" / 实验目录的 "..._focusB"
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

    这是**配置驱动**的：换协议不需要改脚本。
    """
    template = str((profile.get("raw_format") or {}).get("request_line") or "").strip()
    if not template:
        return None
    for idx, field_name in enumerate(template.split()):
        if "{url}" in field_name:
            return idx
    return None


# ===========================================================================
# 语料读取与 URL 抽取
# ===========================================================================

def iter_seed_files(seed_dir: Path) -> list[Path]:
    """列出语料目录下的 ``*.raw`` 种子文件（按名排序）。"""
    return sorted(Path(seed_dir).glob("*.raw"))


def read_seed_texts(seed_files: list[Path]) -> list[tuple[Path, str]]:
    """读取种子文件内容（utf-8，容错解码）。"""
    out: list[tuple[Path, str]] = []
    for path in seed_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        out.append((path, text))
    return out


def extract_request_urls(text: str, url_index: int) -> list[str]:
    """抽取一条种子文本里**所有消息的请求行 URL**。

    请求行的判定：第 0 个字段是**不含冒号的全大写方法名**（故 ``CSeq: 1`` /
    ``Via: ...`` 这类头部行不会被误判为请求行），且该行至少有 ``url_index + 1``
    个字段。

    Args:
        text: 种子文件全文。
        url_index: URL 在请求行中的字段下标（由 profile 模板决定）。

    Returns:
        URL 字符串列表（一条消息一个；顺序 = 出现顺序）。
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


#: 全文中**带 authority 的绝对 URL**（``scheme://host[:port]/...``）。
_ABSOLUTE_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s<>\"']+")


def extract_absolute_urls(text: str) -> list[str]:
    """抽取种子全文里所有**带 authority 的绝对 URL**（不限位置：请求行 / 头部 / 消息体）。

    G1 的语义是"语料里**所有** URL 的 host:port 都必须指向目标环境"——只查请求行
    会漏掉头部/消息体里指向别处的 URL。故 G1 用本函数做全集扫描，G2 的资源名抽取
    则仍以请求行为准（资源名由请求 URI 承载）。
    """
    return [m.group(0).rstrip(".,;") for m in _ABSOLUTE_URL_RE.finditer(text)]



def authority_of(url: str) -> Optional[str]:
    """取 URL 的 **authority**（``host[:port]``）；非分层 URI（无 ``//``）→ None。

    复用 ``target_env._split_url``，保证与种子端点归一化修复**同一套拆分口径**。
    """
    _scheme, netloc, _path = _split_url(url)
    if not netloc or "://" not in url:
        return None
    return netloc


def hostport_parts(netloc: str) -> tuple[str, str]:
    """把 ``host[:port]`` 拆成 ``(host, port)``；无端口 → port 为空串。

    兼容 IPv6 字面量（``[::1]:8554``）。
    """
    text = str(netloc or "").strip()
    if not text:
        return "", ""
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    if text.startswith("["):
        host, _, rest = text.partition("]")
        return host + "]", rest[1:] if rest.startswith(":") else ""
    host, sep, port = text.rpartition(":")
    if sep and port.isdigit():
        return host, port
    return text, ""


def endpoint_matches(url_authority: str, target_netloc: str) -> bool:
    """URL 的 authority 是否与目标端点**同 host 同 port**。

    host 大小写不敏感；端口必须**逐字相等**——URL 省略端口意味着走协议的默认端口
    （RTSP 是 554，与目标 8554 不同）→ 判为不匹配（这是真实缺陷，不该放过）。
    """
    url_host, url_port = hostport_parts(url_authority)
    tgt_host, tgt_port = hostport_parts(target_netloc)
    return url_host.lower() == tgt_host.lower() and url_port == tgt_port


def client_side_legal_hosts(profile: dict) -> set[str]:
    """从 ``seedgen.client_side`` 派生合法 host 集合（小写、**不含端口**）。

    SIP 的端点语义由 ``Via``/``Contact`` 头承载（``client_side.headers`` 声明），
    其合法 host 来自 ``server_addr``/``client_addr``（实测均为 ``127.0.0.1``）。
    SIP 的端口语义灵活（客户端源端口 5061 可动态分配），故 G1 对 SIP 按 **host**
    判定（非 host:port 严格相等）。
    """
    cs = (profile.get("seedgen") or {}).get("client_side") or {}
    hosts: set[str] = set()
    for key in ("server_addr", "client_addr"):
        raw = str(cs.get(key) or "").strip()
        if not raw:
            continue
        # 剥 scheme（sip:host:port / sip://host:port → host:port）
        if "://" in raw:
            raw = raw.split("://", 1)[1]
        elif raw.startswith(("sip:", "sips:")):
            raw = raw.split(":", 1)[1]
        host, _port = hostport_parts(raw)
        if host:
            hosts.add(host.lower())
    return hosts


def client_side_header_names(profile: dict) -> list[str]:
    """``seedgen.client_side.headers`` 声明的、承载端点语义的头名（如 Via/Contact）。"""
    cs = (profile.get("seedgen") or {}).get("client_side") or {}
    return [str(h) for h in (cs.get("headers") or [])]


def _sip_uri_host(uri: str) -> Optional[str]:
    """从 ``sip:user@host:port;params`` 抽 host（小写）；非 SIP URI / 无法解析 → None。"""
    u = str(uri or "").strip().strip("<>")
    if not u.startswith(("sip:", "sips:")):
        return None
    u = u.split(":", 1)[1]           # 去 scheme
    u = u.split(";", 1)[0]           # 去参数（;transport=udp 等）
    u = u.rsplit("@", 1)[-1]         # 去 userinfo
    host, _port = hostport_parts(u)  # 去端口
    return host.lower() if host else None


def extract_client_side_hosts(text: str, header_names: list[str]) -> list[str]:
    """从「端点语义位置」抽 host：请求行 R-URI + client_side 头（Via sent-by / Contact URI）。

    ★ 只从这三处抽取，**天然排除**：
      · ``Call-ID`` 里的 IP（如 ``105090259-446faf7a@192.168.1.2`` 的 192.168.1.2）；
      · ``branch=`` 随机串里的 IP（``z9hG4bK...192.168.1.2``）；
      · ``From``/``To`` 的逻辑域名（``sip.cybercity.dk``，官方语料自带、不决定路由）。
    这三类都不承载端点语义，纳入会误报。返回 host 列表（小写）。
    """
    names = {n.lower() for n in header_names}
    hosts: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # Via sent-by：`Via: SIP/2.0/UDP 127.0.0.1:5061;branch=...`
        m = re.match(r"^Via:\s*\S+\s+([^;\s]+)", s, re.IGNORECASE)
        if m and "via" in names:
            host, _p = hostport_parts(m.group(1))
            if host:
                hosts.append(host.lower())
            continue
        # Contact URI：`Contact: <sip:127.0.0.1:5061>`
        m = re.match(r"^Contact:\s*<?(sips?:[^;>\s]+)", s, re.IGNORECASE)
        if m and "contact" in names:
            host = _sip_uri_host(m.group(1))
            if host:
                hosts.append(host)
            continue
        # 请求行 R-URI：`METHOD sip:host SIP/2.0`（第二 token 是 R-URI）
        parts = s.split()
        if len(parts) >= 2 and parts[1].startswith(("sip:", "sips:")):
            host = _sip_uri_host(parts[1])
            if host:
                hosts.append(host)
    return hosts


def resource_candidate(url: str) -> Optional[str]:
    """取 URL 路径的**第一段**作为会话/资源名候选（与 ``normalize_seed_resource``
    同一口径：URL path 的第一段标识资源实例）。

    无路径 / 路径为空 → None。
    """
    _scheme, _netloc, path = _split_url(url)
    if not path:
        return None
    segments = [seg for seg in path.split("/") if seg]
    return segments[0] if segments else None


def protocol_uri_schemes(profile: dict) -> set[str]:
    """profile 声明的 URI scheme 集合（用于限定资源名抽取的适用范围）。"""
    schemes: set[str] = set()
    default_url = str(profile.get("default_url") or "").strip()
    if "://" in default_url:
        schemes.add(default_url.split("://", 1)[0].lower())
    scheme, _netloc = target_endpoint(profile)
    if scheme:
        schemes.add(scheme.lower())
    return schemes


def unique_playable_env(profile: dict) -> tuple[Optional[str], dict]:
    """找出 profile 中**唯一**声明了可播清单的目标环境。

    用途：语料未绑定目标环境（manifest 无 ``target_env``）时，仍可用它做**交叉
    校验**（"若按该环境生成，这些种子可播吗？"）。返回 ``(环境名, 环境配置)``；
    无 / 不唯一 → ``(None, {})``。

    ★ 这只是**交叉校验**：语料本身未受环境级约束时，"不可播"并不等于"坏种子"
    （它只是没按该环境收敛），故交叉校验的结果在报告里会明确标注口径。
    """
    envs = (profile.get("seedgen") or {}).get("environments") or {}
    hits = [(str(name), dict(cfg or {})) for name, cfg in envs.items()
            if (cfg or {}).get("playable_resources_file")]
    if len(hits) != 1:
        return (None, {})
    return hits[0]



# ===========================================================================
# 目标端点解析（G1 的判定基准）
# ===========================================================================

def resolve_endpoint_context(profile: dict, env_cfg: dict, env_name: Optional[str],
                              corpus_urls: list[str]) -> tuple[Optional[str], str, str]:
    """解析**目标服务端点**及其来源、URI 形态。

    数据来源优先级（全部来自配置，**禁止写死**）：
      1. 目标环境显式声明的端点——环境配置取自
         ``profile.seedgen.environments.<env>``（``target_env.select_environment``
         的返回值）；同时兼容 ``profile.environments.<env>`` 这一顶层布局；
      2. profile 的 ``default_url``（经 ``target_env.target_endpoint()``）；
      3. profile 的 ``url_placeholders["<server>"]``（``target_endpoint()`` 的兜底）。

    URI 形态（决定 G1 是否适用）：
      · ``hierarchical`` —— ``scheme://authority/...``，authority 即**路由端点**；
      · ``opaque``       —— ``scheme:opaque``（如 SIP 的 ``sip:user@host``），其
        domain 是**逻辑实体标识、不决定路由** → G1 不适用（历史结论）；
      · ``none``         —— profile 未声明任何端点 → G1 不适用。

    Returns:
        ``(host:port 或 None, 来源说明, URI 形态)``。
    """
    # 环境级端点声明：先看 seedgen.environments.<env>，再看顶层 environments.<env>
    env_sources: list[tuple[str, dict]] = []
    if env_cfg:
        env_sources.append(("profile.seedgen.environments.<env>", env_cfg))
    top_envs = profile.get("environments") or {}
    if env_name and isinstance(top_envs.get(env_name), dict):
        env_sources.append(("profile.environments.<env>", dict(top_envs[env_name])))

    for source_label, env_src in env_sources:
        for key in ("target_endpoint", "target_url", "default_url", "url", "server"):
            raw = str(env_src.get(key) or "").strip()
            if not raw:
                continue
            if "://" in raw:
                _scheme, netloc, _path = _split_url(raw)
                if netloc:
                    return (netloc, f"{source_label}.{key}", "hierarchical")
            elif ":" in raw:
                return (raw, f"{source_label}.{key}", "hierarchical")

    default_url = str(profile.get("default_url") or "").strip()
    if default_url:
        if "://" in default_url:
            _scheme, netloc = target_endpoint(profile)
            if netloc:
                return (netloc, "profile.default_url（经 target_endpoint()）",
                        "hierarchical")
        else:
            # 形如 sip:127.0.0.1:5060 —— 无 authority 分量。
            return (None, "profile.default_url（opaque URI，无 authority 分量）",
                    "opaque")

    _scheme, netloc = target_endpoint(profile)
    if netloc and any("://" in url for url in corpus_urls):
        return (netloc, "profile.url_placeholders['<server>']（经 target_endpoint()）",
                "hierarchical")
    return (None, "profile 未声明可路由端点", "none")


def endpoint_applicability(profile: dict) -> tuple[bool, str]:
    """G1 对该协议**是否适用**，返回 ``(适用, 原因)``。

    判定**完全由配置驱动**（不硬编码协议名）：

    1. **协议级显式开关**（首选）——``profile.seedgen.target_endpoint_normalization``
       （经 ``target_env.endpoint_normalization_enabled()`` 读取）。
       该开关的含义是"本协议的 URI 端点**决定请求目标**"：
         · RTSP 开启 → Request-URI 的 host:port 决定请求打到哪 → **G1 适用**；
         · SIP 未开启 → URI domain 是逻辑实体标识、**不决定路由**（真正决定回包
           地址的是 ``Contact``/``Via``）→ **G1 不适用**。
       这是生成侧与校验侧**共用同一份语义声明**，故不会出现"生成时归一化了、
       校验时却不查"的口径裂缝。
       ★ 开关**显式声明**时以它为准（显式 false = 该协议明确声明"端点不决定
         请求目标"，不再走兜底）；**未声明**时才走下面的 URI 形态兜底。
    2. **URI 形态兜底**（开关缺省时）——``default_url`` 是否带 authority 分量：
       带（``scheme://host:port``）→ 适用；不带（``sip:host``）→ 不适用。
    """
    seedgen_cfg = (profile or {}).get("seedgen") or {}
    if "target_endpoint_normalization" in seedgen_cfg:
        if endpoint_normalization_enabled(profile):
            return (True, "profile.seedgen.target_endpoint_normalization=true"
                           "（本协议 URI 端点决定请求目标）")
        return (False, "profile.seedgen.target_endpoint_normalization=false"
                       "（本协议明确声明 URI 端点不决定请求目标）→ G1 不适用")
    default_url = str(profile.get("default_url") or "").strip()
    if default_url and "://" in default_url:
        return (True, "profile.default_url 为分层 URI（带 authority 分量）")
    if default_url:
        # ★ D2：opaque URI（如 SIP 的 sip:127.0.0.1:5060）—— 其 domain 不决定路由，
        #   但 profile 若声明了 `seedgen.client_side`（Via/Contact 承载端点语义），
        #   则 G1 仍适用：检查 Via/Contact/R-URI 的 host 是否指向合法端点。
        if client_side_legal_hosts(profile):
            return (True, "profile.seedgen.client_side 声明了端点"
                          "（Via/Contact 承载端点语义）→ G1 适用")
        return (False, "profile.seedgen.target_endpoint_normalization 未开启，"
                       "且 default_url 为 opaque URI（无 authority 分量）——"
                       "其 domain 是逻辑实体标识、不决定路由")
    return (False, "profile.seedgen.target_endpoint_normalization 未开启，"
                   "且 profile 未声明带 authority 的 default_url")



# ===========================================================================
# 红线 G1 —— 目标主机正确率
# ===========================================================================

def _check_g1_client_side(profile: dict, protocol: str,
                          seed_texts: list[tuple[Path, str]],
                          thresholds: Thresholds,
                          legal_hosts: set[str]) -> GateOutcome:
    """G1 的 **client_side 分支**（D2）：SIP 语料 Via/Contact/R-URI 的 host 必须 ∈ 合法集。

    与分层 URI 分支（RTSP，host:port 严格相等）不同，这里按 **host** 判定：
    SIP 的端口语义灵活（客户端源端口 5061 可动态分配），只校验 host 是否指向
    合法端点（如 127.0.0.1）。抽取位置**限定**请求行 R-URI + ``client_side.headers``
    声明的头（Via/Contact），天然排除 Call-ID 里的 IP、branch= 随机串、From/To 逻辑域名。
    """
    title = "G1 目标主机正确率"
    header_names = client_side_header_names(profile)
    wrong_files: list[str] = []
    checkable = 0
    offenders: Counter[str] = Counter()
    for path, text in seed_texts:
        hosts = extract_client_side_hosts(text, header_names)
        if not hosts:
            continue
        checkable += 1
        bad = [h for h in hosts if h not in legal_hosts]
        if bad:
            wrong_files.append(path.name)
            offenders.update(bad)

    ratio = (len(wrong_files) / checkable) if checkable else 0.0
    failed = ratio > thresholds.max_wrong_target_ratio
    details = {
        "applicable": True,
        "endpoint_kind": "client_side",
        "legal_hosts": sorted(legal_hosts),
        "header_names": header_names,
        "seed_files": len(seed_texts),
        "checkable_seeds": checkable,
        "wrong_target_seeds": len(wrong_files),
        "wrong_target_ratio": round(ratio, 6),
        "offending_hosts": dict(offenders.most_common(10)),
        "wrong_target_seed_files": wrong_files[:20],
    }
    measured = (f"可判定种子 {checkable}/{len(seed_texts)}；"
                f"含非合法 host 的种子 {len(wrong_files)} 个"
                f"（{ratio * 100:.2f}%）")
    if offenders:
        measured += f"；非合法 host 分布 {dict(offenders.most_common(5))}"
    return GateOutcome(
        gate="G1", title=title,
        status=STATUS_FAIL if failed else STATUS_PASS,
        blocking=True,
        summary=(f"失败：{len(wrong_files)} 个种子含非合法 host"
                 if failed else
                 f"通过：全部 {checkable} 个可判定种子的端点 host 均 ∈ {sorted(legal_hosts)}"),
        checked="种子中 Via/Contact/R-URI 的 host 是否 ∈ client_side 声明的合法端点",
        sources=(f"{len(seed_texts)} 个 .raw 种子文件；"
                 f"合法 host 来自 profile.seedgen.client_side"),
        criteria=("按种子计数：一条种子的任意端点 host 不在合法集即计为坏种子；"
                  "host 大小写不敏感、按 host 判定（不严格比端口）"),
        measured=measured,
        threshold=f"非合法 host 的种子占比 ≤ {thresholds.max_wrong_target_ratio:.2%}",
        details=details,
    )


def check_g1(profile: dict, protocol: str, seed_texts: list[tuple[Path, str]],
             env_cfg: dict, env_name: Optional[str],
             thresholds: Thresholds) -> GateOutcome:
    """G1：种子请求行的 URL host:port 是否指向目标环境的服务端点。

    判定口径：按**种子**计数——一条种子只要有**任意一个**指向非目标 host:port 的
    URL，该种子即计入"坏种子"（避免"一个种子里 9 个 URL 对、1 个错"被稀释）。

    适用性（**配置驱动**，见 :func:`endpoint_applicability`）：
      ① profile 的 ``raw_format.request_line`` 声明了 ``{url}`` 字段（否则该协议
         无 URL 概念，如 SMTP 命令行协议）；
      ② 协议级开关 ``seedgen.target_endpoint_normalization`` 开启（或 URI 形态
         兜底判定为分层 URI）——即"本协议的 URI 端点决定请求目标"。
         SIP 未开启该开关且其 ``sip:user@host`` 形态的 domain 是逻辑实体标识、
         不决定路由 → **显式标注不适用及原因**。
    """
    title = "G1 目标主机正确率"
    url_index = request_url_index(profile)
    if url_index is None:
        return GateOutcome(
            gate="G1", title=title, status=STATUS_NA,
            summary="不适用：profile.raw_format.request_line 未声明 {url} 字段"
                    "（该协议无 URL 概念，URL 不承载端点信息）",
            checked="请求行 URL 的 host:port 是否指向目标环境服务端点",
            sources="profile.raw_format.request_line",
            criteria="模板中不含 {url} 占位 → 该协议不通过 URL 表达端点",
            measured="不适用", threshold="不适用",
            details={"applicable": False, "reason": "no_url_field"},
        )

    applicable, applicability_reason = endpoint_applicability(profile)
    corpus_urls = [url for _path, text in seed_texts
                   for url in extract_absolute_urls(text)]
    target_netloc, endpoint_source, uri_form = resolve_endpoint_context(
        profile, env_cfg, env_name, corpus_urls)

    if not applicable:
        return GateOutcome(
            gate="G1", title=title, status=STATUS_NA,
            summary="不适用：" + applicability_reason,
            checked="请求行 URL 的 host:port 是否指向目标环境服务端点",
            sources=("profile.seedgen.target_endpoint_normalization；"
                     "profile.default_url"),
            criteria=("本协议 URI 端点不决定请求目标时，host:port 无路由语义 → "
                      "该红线不适用"),
            measured="不适用", threshold="不适用",
            details={"applicable": False, "reason": "endpoint_not_routing_bearing",
                     "applicability_reason": applicability_reason},
        )

    # ★ D2：client_side 端点检查（SIP 的 Via/Contact 承载端点语义，host 判定）。
    cs_hosts = client_side_legal_hosts(profile)
    if cs_hosts and uri_form != "hierarchical":
        return _check_g1_client_side(profile, protocol, seed_texts,
                                     thresholds, cs_hosts)

    if uri_form != "hierarchical" or not target_netloc:
        reason = {
            "opaque": "目标端点是 opaque URI（无 authority 分量）——其 domain 是逻辑"
                      "实体标识、不决定路由（SIP 历史结论）→ G1 不适用",
            "none": "profile 未声明可路由的目标端点 → G1 不适用",
        }.get(uri_form, "目标端点不可解析 → G1 不适用")
        return GateOutcome(
            gate="G1", title=title, status=STATUS_NA,
            summary="不适用：" + reason,
            checked="请求行 URL 的 host:port 是否指向目标环境服务端点",
            sources=f"profile.default_url；{endpoint_source}",
            criteria="目标端点必须是分层 URI（scheme://authority）才承载路由语义",
            measured="不适用", threshold="不适用",
            details={"applicable": False, "reason": uri_form,
                     "endpoint_source": endpoint_source},
        )

    if not corpus_urls:
        return GateOutcome(
            gate="G1", title=title, status=STATUS_NA,
            summary="不适用：语料中未解析出任何请求行 URL（无从判定）",
            checked="请求行 URL 的 host:port 是否指向目标环境服务端点",
            sources=f"{len(seed_texts)} 个种子文件",
            criteria="语料中至少含一条请求行 URL 才可判定",
            measured="URL 数 = 0", threshold="不适用",
            details={"applicable": False, "reason": "no_urls_in_corpus"},
        )

    wrong_files: list[str] = []
    checkable = 0
    offenders: Counter[str] = Counter()
    for path, text in seed_texts:
        authorities = []
        for url in extract_absolute_urls(text):
            authority = authority_of(url)
            if authority:
                authorities.append(authority)
        if not authorities:
            continue
        checkable += 1
        bad = [a for a in authorities if not endpoint_matches(a, target_netloc)]
        if bad:
            wrong_files.append(path.name)
            offenders.update(bad)

    ratio = (len(wrong_files) / checkable) if checkable else 0.0
    failed = ratio > thresholds.max_wrong_target_ratio
    details = {
        "applicable": True,
        "seed_files": len(seed_texts),
        "checkable_seeds": checkable,
        "wrong_target_seeds": len(wrong_files),
        "wrong_target_ratio": round(ratio, 6),
        "target_endpoint": target_netloc,
        "endpoint_source": endpoint_source,
        "uri_form": uri_form,
        "offending_endpoints": dict(offenders.most_common(10)),
        "wrong_target_seed_files": wrong_files[:20],
    }
    measured = (f"可判定种子 {checkable}/{len(seed_texts)}；"
                f"指向非目标端点的种子 {len(wrong_files)} 个"
                f"（{ratio * 100:.2f}%）")
    if offenders:
        measured += f"；非目标端点分布 {dict(offenders.most_common(5))}"
    return GateOutcome(
        gate="G1", title=title,
        status=STATUS_FAIL if failed else STATUS_PASS,
        blocking=True,
        summary=(f"失败：{len(wrong_files)} 个种子指向非目标端点 {target_netloc}"
                 if failed else
                 f"通过：全部 {checkable} 个可判定种子均指向目标端点 {target_netloc}"),
        checked="种子中所有带 authority 的绝对 URL（请求行/头部/消息体）的 host:port"
                " 是否等于目标端点",
        sources=(f"{len(seed_texts)} 个 .raw 种子文件；目标端点来自 {endpoint_source}"),
        criteria=("按种子计数：一条种子含任意一个非目标 authority 即计为坏种子；"
                  "host 大小写不敏感、端口必须逐字相等"),
        measured=measured,
        threshold=f"非目标端点种子占比 ≤ {thresholds.max_wrong_target_ratio:.2%}",
        details=details,
    )


# ===========================================================================
# 红线 G2 —— 不可播会话占比
# ===========================================================================

def check_g2(profile: dict, protocol: str, seed_texts: list[tuple[Path, str]],
             env_cfg: dict, env_name: Optional[str],
             thresholds: Thresholds,
             escalate_cross_check: bool = False) -> GateOutcome:
    """G2：种子引用的会话/资源名是否 ⊆ 目标环境的可播清单。

    可播清单来源：``target_env.playable_resource_names(profile, protocol, env_cfg)``
    （即 profile 的 ``seedgen.environments.<env>.playable_resources_file``）。

    适用性与口径（**分级**，不静默跳过）：
      · **env 绑定口径**（语料 manifest 记录了 ``target_env``，或 ``--target-env``
        显式指定）→ 该环境的可播清单就是这份语料的**契约** → 违规判**阻断级失败**；
      · **交叉校验口径**（语料未绑定环境，但 profile 里**唯一**一个环境声明了可播
        清单）→ "若按该环境部署，这份语料可播吗？" → 默认判**告警**（不阻断）：
        语料本身未受环境级约束，"不可播"是**部署配对问题**而非语料生成缺陷
        （历史语料为保持逐字节可复现，刻意不加环境约束）。``--escalate-cross-check``
        可把它升级为阻断；
      · 两者都不成立 → **不适用**，并显式说明原因。
    """
    title = "G2 不可播会话占比"
    mode = "env"
    scope_note = ""
    if not (env_cfg or {}).get("playable_resources_file"):
        cross_name, cross_cfg = unique_playable_env(profile)
        if cross_name and cross_cfg.get("playable_resources_file"):
            mode = "cross-check"
            scope_note = (f"（语料未绑定目标环境 → 按 profile 中唯一声明可播清单的"
                          f"环境 {cross_name} 做交叉校验）")
            env_cfg = cross_cfg
        else:
            return GateOutcome(
                gate="G2", title=title, status=STATUS_NA,
                summary="不适用：profile 未声明目标环境的可播清单"
                        "（environments.<env>.playable_resources_file 缺失 → "
                        "该协议无「可播会话」概念）",
                checked="种子引用的会话/资源名是否 ⊆ 目标环境可播清单",
                sources="profile.seedgen.environments",
                criteria="无 playable_resources_file → 无可播清单可对照",
                measured="不适用", threshold="不适用",
                details={"applicable": False, "reason": "no_playable_list"},
            )

    try:
        playable = playable_resource_names(profile, protocol, env_cfg)
    except (FileNotFoundError, ValueError) as exc:
        return GateOutcome(
            gate="G2", title=title, status=STATUS_NA,
            summary=f"不适用：可播清单不可用（{exc}）",
            checked="种子引用的会话/资源名是否 ⊆ 目标环境可播清单",
            sources="profile.seedgen.environments.<env>.playable_resources_file",
            criteria="清单文件必须存在且可解析",
            measured="不适用", threshold="不适用",
            details={"applicable": False, "reason": "playable_list_unavailable"},
        )

    if not playable:
        return GateOutcome(
            gate="G2", title=title, status=STATUS_NA,
            summary="不适用：可播清单为空",
            checked="种子引用的会话/资源名是否 ⊆ 目标环境可播清单",
            sources="profile.seedgen.environments.<env>.playable_resources_file",
            criteria="清单为空 → 无可播清单可对照",
            measured="不适用", threshold="不适用",
            details={"applicable": False, "reason": "empty_playable_list"},
        )

    url_index = request_url_index(profile)
    if url_index is None:
        return GateOutcome(
            gate="G2", title=title, status=STATUS_NA,
            summary="不适用：协议无请求行 URL 字段（会话名不由 URL 承载）",
            checked="种子引用的会话/资源名是否 ⊆ 目标环境可播清单",
            sources="profile.raw_format.request_line",
            criteria="模板中不含 {url} 占位 → 无 URL 可解析资源名",
            measured="不适用", threshold="不适用",
            details={"applicable": False, "reason": "no_url_field"},
        )

    allowed = {str(name) for name in playable}
    schemes = protocol_uri_schemes(profile)
    wrong_files: list[str] = []
    checkable = 0
    offenders: Counter[str] = Counter()
    for path, text in seed_texts:
        candidates: list[str] = []
        for url in extract_request_urls(text, url_index):
            if "://" not in url:
                continue
            if schemes and url.split("://", 1)[0].lower() not in schemes:
                continue
            candidate = resource_candidate(url)
            if candidate:
                candidates.append(candidate)
        if not candidates:
            continue
        checkable += 1
        bad = sorted({c for c in candidates if c not in allowed})
        if bad:
            wrong_files.append(path.name)
            offenders.update(bad)

    ratio = (len(wrong_files) / checkable) if checkable else 0.0
    over = ratio > thresholds.max_unplayable_ratio
    blocking = mode == "env" or escalate_cross_check
    failed = over and blocking
    warned = over and not blocking
    details = {
        "applicable": True,
        "mode": mode,
        "target_env": env_name,
        "seed_files": len(seed_texts),
        "checkable_seeds": checkable,
        "unplayable_seeds": len(wrong_files),
        "unplayable_ratio": round(ratio, 6),
        "playable_resources": sorted(allowed),
        "offending_resources": dict(offenders.most_common(10)),
        "unplayable_seed_files": wrong_files[:20],
    }
    measured = (f"可判定种子 {checkable}/{len(seed_texts)}；"
                f"引用不可播资源名的种子 {len(wrong_files)} 个"
                f"（{ratio * 100:.2f}%）")
    if offenders:
        measured += f"；不可播资源分布 {dict(offenders.most_common(5))}"
    if warned:
        summary = (f"告警：{len(wrong_files)} 个种子引用了不可播资源名{scope_note}"
                   f"（交叉校验口径，不阻断）")
        status = STATUS_WARN
    elif failed:
        summary = f"失败：{len(wrong_files)} 个种子引用了目标环境不可播的资源名"
        status = STATUS_FAIL
    else:
        summary = (f"通过：全部 {checkable} 个可判定种子引用的资源名均在可播清单内"
                   + scope_note)
        status = STATUS_PASS
    return GateOutcome(
        gate="G2", title=title, status=status, blocking=blocking,
        summary=summary,
        checked="每个种子请求行 URL 路径第一段（会话/资源名）是否 ∈ 可播清单",
        sources=(f"{len(seed_texts)} 个 .raw 种子文件；可播清单 "
                 f"({len(allowed)} 项) 来自 "
                 f"playable_resource_names(profile, {protocol}, env_cfg)"),
        criteria=("按种子计数：引用任意一个不可播资源名即计为坏种子；"
                  + ("env 绑定口径 → 违规阻断" if mode == "env"
                     else "交叉校验口径 → 违规仅告警"
                     + ("（--escalate-cross-check 已升级为阻断）"
                        if escalate_cross_check else ""))),
        measured=measured,
        threshold=f"不可播种子占比 ≤ {thresholds.max_unplayable_ratio:.2%}",
        details=details,
    )


# ===========================================================================
# 红线 G5 —— 契约一致性（focus_group 条数）
# ===========================================================================

def check_g5(profile: dict, protocol: str, group: Optional[str],
             seed_files: list[Path], manifest: dict, env_name: Optional[str],
             strict: bool) -> GateOutcome:
    """G5：profile 声明的 ``focus_group.<组>.seeds`` 与实际生成条数是否一致。

    期望值取**生效契约**（``target_env.effective_config``：环境级 focus_group 覆盖
    协议级）——这正是 ``seedgen.py`` 生成时实际使用的契约；同时打印协议级原值以便
    对照（两者不同时说明"环境级重标定"）。

    严重级别：默认只**告警**（WARN，不阻断）；``--strict`` 时升级为阻断级失败。
    """
    title = "G5 契约一致性（focus_group 条数）"
    if not group:
        return GateOutcome(
            gate="G5", title=title, status=STATUS_NA,
            summary="不适用：无法判定语料所属的聚焦组（manifest 无记录且目录名无法推断）",
            checked="profile 声明的 focus_group.<组>.seeds == 实际生成条数",
            sources="manifest.json；目录名",
            criteria="必须能确定聚焦组",
            measured="不适用", threshold="不适用",
            details={"applicable": False, "reason": "unknown_group"},
        )

    proto_fg = ((profile.get("seedgen") or {}).get("focus_group") or {}).get(group)
    if not isinstance(proto_fg, dict) or proto_fg.get("seeds") is None:
        return GateOutcome(
            gate="G5", title=title, status=STATUS_NA,
            summary=f"不适用：profile 未声明 focus_group.{group}.seeds 契约",
            checked="profile 声明的 focus_group.<组>.seeds == 实际生成条数",
            sources="profile.seedgen.focus_group",
            criteria="契约必须存在才可比较",
            measured="不适用", threshold="不适用",
            details={"applicable": False, "reason": "no_contract", "group": group},
        )

    effective = effective_config(profile, env_name)
    eff_fg = (effective.get("focus_group") or {}).get(group) or {}
    expected_effective = eff_fg.get("seeds")
    expected_protocol = proto_fg.get("seeds")
    actual = len(seed_files)

    manifest_count = manifest.get("seed_count")
    known = KNOWN_DRIFT.get((protocol, group))
    drift = (expected_effective is not None and actual != expected_effective)

    details: dict[str, Any] = {
        "applicable": True,
        "group": group,
        "expected_effective": expected_effective,
        "expected_protocol_level": expected_protocol,
        "actual": actual,
        "manifest_seed_count": manifest_count,
        "target_env": env_name,
        "drift": drift,
        "known_drift": bool(known),
    }

    if not drift:
        note = ""
        if expected_protocol != expected_effective:
            note = (f"（协议级契约 {expected_protocol} 被环境级 "
                    f"{env_name or '(无)'} 重标定为 {expected_effective}）")
        return GateOutcome(
            gate="G5", title=title, status=STATUS_PASS,
            blocking=False,
            summary=f"通过：聚焦组 {group} 实际 {actual} 条 == 契约 {expected_effective}"
                    + note,
            checked="profile 声明的 focus_group.<组>.seeds 与实际生成条数是否一致",
            sources=(f"{len(seed_files)} 个 .raw 种子文件；契约来自 profile.seedgen"
                     f".focus_group（生效值含环境级覆盖）"),
            criteria="实际条数 == 生效契约条数",
            measured=f"期望 {expected_effective} vs 实际 {actual}"
                     + (f"（manifest.seed_count={manifest_count}）"
                        if manifest_count is not None else ""),
            threshold="期望 == 实际（严格相等）",
            details=details,
        )

    label = "新引入的契约漂移"
    if known and actual == known[1] and expected_protocol == known[0]:
        label = "★ 已知历史契约漂移（契约过期，待用户决策；非本闸门引入的回归）"

    status = STATUS_FAIL if strict else STATUS_WARN
    return GateOutcome(
        gate="G5", title=title, status=status, blocking=strict,
        summary=f"{label}：聚焦组 {group} 契约 {expected_effective} vs 实际 {actual}"
                + ("（--strict：阻断）" if strict else "（默认仅告警，不阻断）"),
        checked="profile 声明的 focus_group.<组>.seeds 与实际生成条数是否一致",
        sources=(f"{len(seed_files)} 个 .raw 种子文件；契约来自 profile.seedgen"
                 f".focus_group（生效值含环境级覆盖）"),
        criteria="实际条数 == 生效契约条数（生效值 = 环境级覆盖后的值）",
        measured=(f"期望 {expected_effective} vs 实际 {actual}"
                  + (f"（manifest.seed_count={manifest_count}）"
                     if manifest_count is not None else "")
                  + (f"；协议级契约 {expected_protocol}" if expected_protocol !=
                     expected_effective else "")),
        threshold="期望 == 实际（严格相等）"
                  + ("；--strict 下失败即阻断" if strict else "；非 strict 下仅告警"),
        details=details,
    )


# ===========================================================================
# 闸门编排
# ===========================================================================

def run_gate(protocol: str, seed_dir: Path, profile: dict,
             env_name: Optional[str] = None, env_cfg: Optional[dict] = None,
             group: Optional[str] = None, thresholds: Optional[Thresholds] = None,
             strict: bool = False, manifest: Optional[dict] = None,
             escalate_cross_check: bool = False) -> list[GateOutcome]:
    """跑全部红线，返回各红线的判定结果（顺序固定 G1 → G2 → G5）。"""
    thresholds = thresholds or Thresholds()
    seed_dir = Path(seed_dir)
    manifest = manifest if manifest is not None else read_manifest(seed_dir)
    if env_cfg is None:
        env_name, env_cfg = resolve_env(profile, manifest, env_name)
    seed_files = iter_seed_files(seed_dir)
    seed_texts = read_seed_texts(seed_files)
    return [
        check_g1(profile, protocol, seed_texts, env_cfg, env_name, thresholds),
        check_g2(profile, protocol, seed_texts, env_cfg, env_name, thresholds,
                 escalate_cross_check=escalate_cross_check),
        check_g5(profile, protocol, group, seed_files, manifest, env_name, strict),
    ]


# ===========================================================================
# 报告渲染
# ===========================================================================

def render_report(outcomes: list[GateOutcome], protocol: str, seed_dir: Path,
                  env_name: Optional[str], group: Optional[str]) -> str:
    """渲染人类可读报告：每条红线都打印「检查了什么/数据来源/判定依据/实测值/阈值/结论」。"""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("ProtoRAG 语料发布准入闸（corpus release gate）")
    lines.append("=" * 72)
    lines.append(f"协议        : {protocol}")
    lines.append(f"语料目录    : {seed_dir}")
    lines.append(f"目标环境    : {env_name or '(未选 —— 无环境级约束)'}")
    lines.append(f"聚焦组      : {group or '(未判定)'}")
    for outcome in outcomes:
        lines.append("")
        lines.append(f"--- {outcome.gate} {outcome.title} ---")
        lines.append(f"  检查了什么 : {outcome.checked}")
        lines.append(f"  数据来源   : {outcome.sources}")
        lines.append(f"  判定依据   : {outcome.criteria}")
        lines.append(f"  实测值     : {outcome.measured}")
        lines.append(f"  阈值       : {outcome.threshold}")
        lines.append(f"  结论       : [{outcome.status}] {outcome.summary}")
    blocking = [o for o in outcomes if o.failed]
    warnings = [o for o in outcomes if o.status == STATUS_WARN]
    lines.append("")
    lines.append("-" * 72)
    if blocking:
        lines.append(f"总判定：阻断（{', '.join(o.gate for o in blocking)} 未通过）")
    else:
        lines.append("总判定：通过（无阻断级红线失败）")
    if warnings:
        lines.append(f"告警（不阻断）：{', '.join(o.gate for o in warnings)}")
    lines.append("-" * 72)
    return "\n".join(lines)


# ===========================================================================
# CLI
# ===========================================================================

def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器。"""
    parser = argparse.ArgumentParser(
        description="ProtoRAG 语料发布准入闸（G1 目标主机正确率 / G2 不可播会话占比"
                    "/ G5 契约一致性）；退出码非 0 即阻断。**只读**：不修改任何文件。")
    parser.add_argument("--protocol", required=True,
                        help="协议名（如 rtsp / sip / smtp）")
    parser.add_argument("--seed-dir", required=True,
                        help="语料目录（含 *.raw 种子文件）")
    parser.add_argument("--profile", default=None,
                        help="profile.json 路径（默认 fused_hub/targets/<protocol>/profile.json）")
    parser.add_argument("--target-env", default=None, metavar="NAME",
                        help="目标环境名（默认取语料 manifest 记录的 target_env，"
                             "再退回 profile 默认环境）")
    parser.add_argument("--group", default=None, metavar="A|B|C|D",
                        help="聚焦组（默认取 manifest 记录，再退回目录名推断）")
    parser.add_argument("--max-wrong-target-ratio", type=float,
                        default=DEFAULT_MAX_WRONG_TARGET_RATIO,
                        help="G1 阈值：指向非目标端点的种子占比上限"
                             f"（默认 {DEFAULT_MAX_WRONG_TARGET_RATIO}）")
    parser.add_argument("--max-unplayable-ratio", type=float,
                        default=DEFAULT_MAX_UNPLAYABLE_RATIO,
                        help="G2 阈值：引用不可播资源名的种子占比上限"
                             f"（默认 {DEFAULT_MAX_UNPLAYABLE_RATIO}）")
    parser.add_argument("--strict", action="store_true",
                        help="G5 契约漂移也参与阻断（默认只告警）")
    parser.add_argument("--escalate-cross-check", action="store_true",
                        help="G2 的「交叉校验口径」（语料未绑定目标环境）也升级为阻断")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 输出报告（CI 机器可读）")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI 入口。

    Returns:
        0 = 通过；1 = 阻断；2 = 用法/配置错误。
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
        env_name, env_cfg = resolve_env(profile, manifest, args.target_env)
    except KeyError as exc:
        print(f"!! {exc}", file=sys.stderr)
        return 2

    group = detect_group(seed_dir, manifest, args.group)
    thresholds = Thresholds(
        max_wrong_target_ratio=float(args.max_wrong_target_ratio),
        max_unplayable_ratio=float(args.max_unplayable_ratio),
    )
    outcomes = run_gate(protocol, seed_dir, profile, env_name=env_name,
                        env_cfg=env_cfg, group=group, thresholds=thresholds,
                        strict=bool(args.strict), manifest=manifest,
                        escalate_cross_check=bool(args.escalate_cross_check))

    if args.json:
        payload = {
            "protocol": protocol,
            "seed_dir": str(seed_dir),
            "target_env": env_name,
            "group": group,
            "strict": bool(args.strict),
            "thresholds": {
                "max_wrong_target_ratio": thresholds.max_wrong_target_ratio,
                "max_unplayable_ratio": thresholds.max_unplayable_ratio,
            },
            "gates": [o.to_dict() for o in outcomes],
            "blocked": any(o.failed for o in outcomes),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_report(outcomes, protocol, seed_dir, env_name, group))

    return 1 if any(o.failed for o in outcomes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
