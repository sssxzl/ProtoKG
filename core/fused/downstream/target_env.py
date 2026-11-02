# -*- coding: utf-8 -*-
"""core/fused/downstream/target_env.py —— 目标环境（target environment）解析与约束。

背景
----
本模块解决 RQ4 实验前实测发现的两个**阻断级种子缺陷**，它们的共同根因是：
「**协议/源码级知识**」与「**目标部署环境级事实**」被混为一谈。

缺陷 1 · RTSP 引用目标环境不存在的会话（47.9% 的状态变更请求打空）
    `fused_hub/targets/rtsp_streams.json` 里的 18 个会话名是从
    `testOnDemandRTSPServer.cpp` 源码里提取的 **streamName 定义**——这是**源码级**
    事实（目标程序"认识"这些名字）。但 AFLNet 镜像 `rq2-live555:latest` 的
    `live/testProgs/` 目录下仅 7 个媒体文件（清单见 fused_hub/targets/rtsp/rtsp_playable_streams.json 的 media_files），
    其余 11 个会话服务端一律返 404。→「源码认识」≠「该环境能播」。

缺陷 2 · SIP 39.4% 的消息起点不被 AFLNet 识别
    SIP 的全部方法（OPTIONS/SUBSCRIBE/PUBLISH/...）都是**合法协议方法**（协议级
    知识，应完整保留）。但 AFLNet 的 SIP 分区器（`aflnet.c` 的
    `extract_requests_sip`）只把 `REGISTER`/`INVITE`/`ACK`/`BYE` 当作**新消息起点**，
    其余方法开头的消息会被**并入前一条消息** → 消息边界被破坏，变异预算浪费在
    这些方法上。

缺陷 3 · RTSP 种子打向抓包里的**非目标设备**（静默退化）
    `traffic` 源是**混合抓包**：同一份 `traffic.jsonl` 里既有 live555 的
    `rtsp://127.0.0.1:8554/mp3AudioTest/track1`，也有**别的设备**（如某 IP 摄像机
    `rtsp://10.11.26.98:554/isapi/streaming/channels/101`）。若种子**原样透传**抓包
    里的 Request-URI，就会打向目标环境根本不存在的设备 —— 实测某份语料 37 个种子中
    22 个（59.5%）指向该摄像机。
    ⇒ 种子 URL 的**端点**必须由**目标侧**（profile）推导，而不是照抄源侧抓包值。
    ★ **是否做端点改写由 profile 的协议级开关决定**（`seedgen.endpoint_normalization`，
      RTSP 显式置 `true`；SIP 不声明该项 ⇒ 关闭）：
      · RTSP：Request-URI 里的 host:port **决定请求目标**，端点错了就 404 ⇒ 需改写；
      · SIP：URI 的 domain 是**逻辑实体标识**，不决定请求路由（真正决定回包地址的
        是 `Contact`/`Via`），改写会破坏消息语义并丢掉 userinfo ⇒ **不做端点改写**
        （SIP URI 必须**逐字节不变**）。
    ★ 注意「**改写**」与「**检测**」是两件事：SIP 的 traffic 源确实含外来主机
      （`sip:213.192.59.75`），需要被**检出**——但检出属于语料准入闸门
      （`scripts/corpus_gate.py`）的职责，**不在本模块**（本模块只管改写）。

设计原则（与本仓既有风格一致）
------------------------------
  · **知识保留**：源码级知识文件（`rtsp_streams.json`）**不删改**——它对其他部署环境
    （完整的 live555 构建）仍有价值。环境级事实单独放在 profile 声明的目标环境里。
  · **profile 驱动、协议无关**：本模块不含任何协议名/方法名/会话名常量，全部从
    `profile.json` 读取。换协议 = 加一份 profile 配置，代码零改动。
  · **两级正交**：
      - `playable_resources_file` —— 该环境下**实际可播/可用**的资源实例子集
        （环境级事实；与源码级资源清单取交集后生效）。
      - `message_boundary_methods` —— 该环境下**允许作为消息起点**的方法
        （harness 级事实：fuzzer 的协议分区器只认这些方法作新消息）。
  · **默认环境不改变历史行为**：profile 未显式声明 `seedgen.environment` 时，
    `select_environment` 返回 `(None, {})` → 环境级约束全部不生效 → 历史语料
    （RQ1.2 / RQ3 语料）仍可逐字节复现。这是刻意选择：RQ3 的 C 组语料必须与
    RQ1.2 语料 MD5 集合相等（连续性硬不变式），改默认行为会破坏已发表的实验。
    ★ **例外**：端点归一化（`normalize_target_endpoint`）是**协议级**的（依据
      `profile.default_url` + `profile.seedgen.endpoint_normalization` 开关），
      因为"请求目标必须指向本 profile 描述的服务"是协议自身的语义，与具体目标
      环境无关；开关只对**显式声明开启**（或由 profile 声明的**层级式**目标端点
      推导得出）的协议生效，对现存历史语料它是**幂等**的（它们的 URL 本就指向
      `default_url`），故不破坏连续性不变式。

★ 两级约束的正交性为什么重要（"知识保留" vs "不作为消息起点"）
--------------------------------------------------------------
被排除的方法（如 SIP 的 OPTIONS/SUBSCRIBE）**不丢弃**，它们仍是：
  · `bundle["transitions"]` 里的一条**状态机边**（知识保留：状态机仍完整，
    可用于覆盖率分析、漏洞模式推导、字典生成）；
  · `bundle["methods"]` 里的一个方法条目（知识保留）；
  · 变异字典里的一个 token（知识保留：fuzzer 仍可朝这些方法变异）。
它们只是**不作为消息起点**——即不参与「构造一条种子消息序列」的边遍历。
换句话说：**状态机的边 ≠ 消息起点**；前者是知识，后者是 fuzzer 的传输语义。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from core import paths

__all__ = [
    "list_environments",
    "select_environment",
    "effective_config",
    "playable_resource_names",
    "restrict_resources",
    "boundary_methods",
    "filter_transitions_by_boundary",
    "environment_calibration",
    "target_endpoint",
    "allowed_endpoints",
    "endpoint_default_ports",
    "normalize_target_endpoint",
    "normalize_target_endpoint_in_text",
    "normalize_seed_resource",
    "endpoint_normalization_enabled",
]


# ===========================================================================
# 1. 目标环境选择
# ===========================================================================

def _seedgen_cfg(profile: dict) -> dict:
    """取 profile 的 seedgen 段（协议配置维度）。"""
    return (profile or {}).get("seedgen") or {}


def list_environments(profile: dict) -> list[str]:
    """profile 声明的目标环境名列表（未声明 → 空 list）。

    未声明 `seedgen.environments` 的协议 → 行为与引入本概念前**完全一致**
    （无环境 = 无环境级约束）。
    """
    envs = _seedgen_cfg(profile).get("environments") or {}
    return sorted(str(k) for k in envs)


def select_environment(profile: dict,
                       env_name: Optional[str] = None
                       ) -> tuple[Optional[str], dict]:
    """选出目标环境，返回 `(环境名, 环境配置)`。

    选择优先级：
      1. 显式传入的 `env_name`（CLI `--target-env`）；
      2. profile 的 `seedgen.environment`（该协议的默认目标环境）。

    ★ **未指定且 profile 未声明默认环境 → 不施加任何环境级约束**
      （返回 `(None, {})`）。这是刻意的保守默认：环境级约束会改变种子内容，
      静默套用会让"历史语料可复现"这一硬不变式失效。

    Raises:
        KeyError: 显式指定了 profile 未声明的环境名（拼写错误必须显式失败）。
    """
    envs = _seedgen_cfg(profile).get("environments") or {}
    name = env_name or _seedgen_cfg(profile).get("environment")
    if not name:
        return (None, {})
    if name not in envs:
        raise KeyError(
            f"未知的目标环境 {name!r}（profile 声明了: {sorted(envs)}）")
    return (str(name), dict(envs.get(name) or {}))


def effective_config(profile: dict,
                     env_name: Optional[str] = None) -> dict:
    """合并协议级 seedgen 约束与环境级覆盖，返回**生效配置**。

    合并规则：
      · 普通键：环境级**覆盖**协议级（更具体的环境约束优先）；
      · `focus_group`：**逐组**合并（环境级只覆盖它声明的组，其余组沿用协议级）；
      · `_environment`：生效环境名（None = 未选环境，行为与历史一致）。

    Args:
        profile: 协议 profile 字典。
        env_name: 显式指定的环境名；None → 用 profile 的默认环境。

    Returns:
        生效配置字典（键与 `profile.seedgen` 同级 + `_environment`）。
    """
    cfg = dict(_seedgen_cfg(profile))
    name, env_cfg = select_environment(profile, env_name)
    if env_cfg:
        proto_fg = dict(cfg.get("focus_group") or {})
        for key, value in env_cfg.items():
            if key == "focus_group":
                merged = dict(proto_fg)
                merged.update(dict(value or {}))
                cfg["focus_group"] = merged
            else:
                cfg[key] = value
    cfg["_environment"] = name
    return cfg


# ===========================================================================
# 2. 可播资源（环境级）
# ===========================================================================

def _resource_file_candidates(protocol: str, filename: str) -> list[Path]:
    """资源清单文件的候选路径：协议子目录优先，再兜底 targets 根目录。

    与 `scripts/seedgen.py::_load_resources` 的历史查找顺序保持一致
    （`fused_hub/targets/rtsp_streams.json` 是历史遗留的协议前缀命名）。
    """
    return [
        paths.targets_root() / protocol.lower() / filename,
        paths.targets_root() / filename,
    ]


def playable_resource_names(profile: dict, protocol: str,
                            env_cfg: dict) -> Optional[list[str]]:
    """读目标环境声明的「可播资源名」清单。

    Returns:
        资源名列表；`None` 表示该环境未声明可播资源（= 不做环境级限定）。

    Raises:
        FileNotFoundError: 环境声明了清单文件但文件不存在——**必须显式失败**，
            静默回退到"不限制"会悄悄生成一批打 404 的种子（正是本模块要修的缺陷）。
        ValueError: 清单文件存在但无法解析。
    """
    filename = (env_cfg or {}).get("playable_resources_file")
    if not filename:
        return None
    for candidate in _resource_file_candidates(protocol, str(filename)):
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(
                f"目标环境可播资源清单读失败: {candidate} ({exc})") from exc
        names = data.get("playable")
        if isinstance(names, list):
            return [str(n).strip() for n in names if str(n).strip()]
        # 兼容 `streams: [{"name": ...}, ...]` 写法
        out: list[str] = []
        for item in data.get("streams") or []:
            if isinstance(item, dict) and item.get("name"):
                out.append(str(item["name"]).strip())
        return out
    raise FileNotFoundError(
        f"目标环境声明的可播资源清单不存在: {filename!r}"
        f"（查找路径: "
        f"{', '.join(str(p) for p in _resource_file_candidates(protocol, str(filename)))}）")


def restrict_resources(resources: list, playable: Optional[list[str]]) -> list:
    """把**源码级**资源实例清单限定到目标环境的**可播子集**。

    保持声明顺序与元数据（tracks 等），只做筛除。被筛掉的实例**不是被删除**——
    它们仍留在 `rtsp_streams.json` 里（源码级知识，对其他环境有效）。

    Args:
        resources: 源码级资源名列表（已按 tracks 排序）。
        playable:  目标环境可播资源名列表；None → 原样返回（不限定）。

    Returns:
        限定后的资源名列表。
    """
    if playable is None:
        return list(resources)
    allow = {str(n) for n in playable}
    return [r for r in resources if str(r) in allow]


# ===========================================================================
# 3. 消息起点方法（harness 级）
# ===========================================================================

def boundary_methods(env_cfg: dict) -> Optional[list[str]]:
    """目标环境下**允许作为消息起点**的方法白名单；None = 不限制。

    语义（协议无关）：fuzzer 的协议分区器只把这些方法识别为「新消息起点」，
        以它们开头的方法能形成独立消息；其余方法开头的消息会被并入前一条消息。
    """
    methods = (env_cfg or {}).get("message_boundary_methods")
    if not methods:
        return None
    return [str(m).strip().upper() for m in methods if str(m).strip()]


def filter_transitions_by_boundary(transitions: list,
                                   methods: Optional[list[str]]) -> list:
    """按「消息起点方法」过滤**用于构造种子消息序列**的转移边。

    ★ 只过滤**种子构造**用的边：`bundle["transitions"]` 里的完整状态机**不受影响**
      （被排除的方法仍是状态机的一条边 → 知识保留），它们也不会从变异字典里消失。
      区别只在：被排除的方法不能**起始**一条消息。

    Args:
        transitions: [(from_state, method, to_state), ...]
        methods:      允许的消息起点方法；None → 原样返回。

    Returns:
        过滤后的转移边列表。
    """
    if methods is None:
        return list(transitions)
    allow = {str(m).strip().upper() for m in methods}
    return [t for t in transitions
            if str(t[1]).strip().upper() in allow]


# ===========================================================================
# 4. 种子 URL 的目标侧归一化（缺陷 3：抓包混入非目标设备）
# ===========================================================================

def target_endpoint(profile: dict) -> tuple[str, str]:
    """取 profile 声明的**目标服务端点** `(scheme, host:port)`。

    数据来源（协议级，不依赖具体目标环境）：
      · `profile.default_url`（如 ``rtsp://127.0.0.1:8554/``）——首选；
      · `profile.url_placeholders["<server>"]`（如 ``127.0.0.1:8554``）——兜底。

    ★ 兜底分支**同样受端点归一化开关约束**（`endpoint_normalization_enabled`）：
      兜底值只有 ``host:port``、**没有 scheme**，若在开关关闭的协议上使用它，
      改写出来的 URL 会**连 scheme 都没了**（如 SIP 退化成 ``127.0.0.1:5060/...``），
      比不改写更糟。开关关闭 ⇒ 本协议不做端点改写 ⇒ 兜底端点一律不提供。

    Returns:
        `(scheme, host:port)`；profile 未声明 → `("", "")`（= 不做端点归一化）。
    """
    default_url = str((profile or {}).get("default_url") or "").strip()
    if default_url:
        scheme, netloc, _ = _split_url(default_url)
        if netloc:
            return scheme, netloc
    if not endpoint_normalization_enabled(profile):
        return "", ""       # 开关关闭 ⇒ 不用「无 scheme」的兜底端点
    ph = (profile or {}).get("url_placeholders") or {}
    server = str(ph.get("<server>") or "").strip()
    if server:
        return "", server
    return "", ""


def _split_url_parts(url: str) -> tuple[str, str, str, str, str]:
    """把 URL 拆成 `(scheme, host:port, path, query, fragment)`。

    兼容两种形态：
      · ``scheme://host:port/path``（RTSP 等"URL 决定请求目标"的协议）
      · ``scheme:user@host:port``（SIP URI —— **没有 ``//``**）

    ★ **query / fragment 单独返回**（不丢）：改写端点时必须原样带回，
      否则 ``?a=1`` / ``#frag`` 会被**静默丢弃**（数据损坏）。

    ★ **裸相对路径**（既无 ``://``、也无 ``scheme:`` 前缀，如 ``mp3AudioTest``）
      判为**非绝对 URL** → `("", "", "", "", "")` ⇒ 调用方原样返回。
      否则它会被误当成 ``host``，改写后**资源名整个消失**。

    解析失败（无 host）→ `("", "", "", "", "")`。
    手写拆分而非 urllib.parse：种子里的 URL 允许含占位符与中文，
    urllib 对畸形输入的宽容度反而会掩盖问题。
    """
    text = str(url or "").strip()
    if not text:
        return "", "", "", "", ""
    scheme = ""
    rest = text
    if "://" in text:
        scheme, rest = text.split("://", 1)
        scheme = scheme.lower()
    else:
        # 无 "//"：若形如 "scheme:..." 则取前缀作 scheme（SIP URI）
        head, sep, tail = text.partition(":")
        if sep and head.isalpha() and head.lower() not in ("", "http", "https"):
            scheme = head.lower()
            rest = tail
        elif not sep and "/" not in text:
            # 裸相对路径（无 scheme、无 "/"）—— 不是绝对 URL
            return "", "", "", "", ""
    # 拆出 fragment / query（保留原文，改写时原样带回）
    fragment = ""
    query = ""
    if "#" in rest:
        rest, frag = rest.split("#", 1)
        fragment = "#" + frag
    if "?" in rest:
        rest, q = rest.split("?", 1)
        query = "?" + q
    slash = rest.find("/")
    netloc = rest if slash < 0 else rest[:slash]
    path = "" if slash < 0 else rest[slash:]
    # netloc 里可能带 userinfo（user:pass@host）
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    return scheme, netloc, path, query, fragment


def _split_url(url: str) -> tuple[str, str, str]:
    """把 URL 拆成 `(scheme, host:port, path)`（不含 query / fragment）。

    ★ 兼容入口：`_split_url_parts` 的三元组视图，供只需要
    scheme/netloc/path 的调用方使用（如 `scripts/corpus_gate.py`）。
    """
    scheme, netloc, path, _query, _fragment = _split_url_parts(url)
    return scheme, netloc, path


#: profile 里声明「端点归一化开关」的键名（`seedgen` 段内）。
#: 规范键 = ``endpoint_normalization``；``target_endpoint_normalization`` 是
#: 早期实现用过的名字，作为**兼容别名**保留（规范键优先）。
_ENDPOINT_NORMALIZATION_KEYS = ("endpoint_normalization",
                                "target_endpoint_normalization")

#: 资源路径末段的「编号子记号」形态（如 ``track1`` / ``trackID=1``）。
#: 用于**保留原 URL 的路径形态**（RTSP 的 SETUP 是 ``/{stream}/track{N}``）。
_TRACK_SUFFIX_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z]*)(?P<sep>[^A-Za-z0-9]*)(?P<num>\d+)$")


def endpoint_normalization_enabled(profile: dict) -> bool:
    """该协议是否启用「种子 URL 端点归一化」（协议级开关）。

    ★ 为什么要有这个显式开关（而不是"看起来像 URL 就归一化"）：
      不同协议的 URI 语义不同 ——
        · RTSP：Request-URI 里的 host:port + path **决定请求目标**，
          必须指向本 profile 描述的服务 ⇒ 端点错了就 404 ⇒ **需要归一化**；
        · SIP：URI 的 domain 是**逻辑实体标识**，不决定路由（真正决定回包地址的是
          `Contact`/`Via`，由 profile 的 `seedgen.client_side` 机制单独改写）；
          把 domain 改成目标服务地址反而**破坏了消息语义**（还会丢掉 userinfo）
          ⇒ **不得归一化**（SIP URI 必须**逐字节不变**）。

    判定顺序（协议无关、全部来自 profile，**代码零协议硬编码**）：
      1. **显式开关**（规范键 ``seedgen.endpoint_normalization``，兼容别名
         ``seedgen.target_endpoint_normalization``）——存在即以其为准
         （RTSP 显式置 ``true``；SIP / SMTP **不写该项** ⇒ 缺省关闭）。
      2. **缺省推导**：未声明开关时，按 profile 声明的**目标端点形态**推导 ——
         · 声明了**层级式**目标 URL（``default_url`` 含 ``://``，即带 authority
           分量）→ 端点决定请求路由 → **启用**；
         · 声明了**非层级式**目标 URI（如 SIP 的 ``sip:127.0.0.1:5060``）→ 其
           domain 是逻辑实体标识 → **禁用**；
         · 未声明 ``default_url`` 但声明了 ``url_placeholders["<server>"]``
           → 端点由此声明 → **启用**；都没有 → **禁用**。

    ★ 第 2 条是**缺省行为**（对 SIP / SMTP / FTP 都得到"关闭"），第 1 条让
      每个协议都能**显式、可审计**地声明自己的行为。
    """
    cfg = (profile or {}).get("seedgen") or {}
    for key in _ENDPOINT_NORMALIZATION_KEYS:
        if key in cfg:
            return bool(cfg[key])
    # 缺省推导：按 profile 声明的目标端点形态判断
    default_url = str((profile or {}).get("default_url") or "").strip()
    if default_url:
        return "://" in default_url
    ph = (profile or {}).get("url_placeholders") or {}
    return bool(str(ph.get("<server>") or "").strip())


# ===========================================================================
# 合法端点集合（**共用**给 corpus_gate 与下游种子生成）
#
# ★ 为什么放这里：`scripts/corpus_gate.py` 的 G1 与 `core/fused/downstream/action_seq.py`
#   的取值白名单**必须用同一套判据** ⇒ 抽到 core 一份、两边 import，
#   **不要复制第二份**（口径漂移过一次就够）。
# ===========================================================================


def allowed_endpoints(profile: dict, env_cfg: dict) -> tuple[set[str], list[str]]:
    """派生该协议的**合法端点集合**（``host:port``），返回 ``(集合, 来源说明)``。

    数据来源（**全部来自配置，禁止写死**）：
      1. 目标环境显式声明的端点（``target_endpoint`` / ``target_url`` /
         ``default_url`` / ``url`` / ``server``）；
      2. profile 的 ``default_url``（经 ``target_env.target_endpoint()``）；
      3. profile 的 ``seedgen.client_side``：``server_addr``（服务端目标）与
         ``client_addr``（客户端源端口）—— SIP 的两个端口分别出现在 R-URI 与
         Via/Contact，**必须都允许**，否则误报。

    实测（真实 profile）：
      · RTSP → ``{127.0.0.1:8554}``
      · SIP  → ``{127.0.0.1:5060, 127.0.0.1:5061}``（5060=R-URI 服务端，
        5061=客户端源端口，出现在 Via/Contact）
      · SMTP → ``{}``（无端点概念 → G1 不适用）
    """
    endpoints: set[str] = set()
    sources: list[str] = []

    def _add(value: str, source: str) -> None:
        text = str(value or "").strip()
        if not text:
            return
        if "://" in text:
            _scheme, netloc, _path = _split_url(text)
            text = netloc
        text = text.rsplit("@", 1)[-1].strip("<>")
        if ":" in text and text.rsplit(":", 1)[1].isdigit():
            endpoints.add(text)
            sources.append(source)

    for key in ("target_endpoint", "target_url", "default_url", "url", "server"):
        _add((env_cfg or {}).get(key), f"profile.seedgen.environments.<env>.{key}")

    _scheme, netloc = target_endpoint(profile)
    _add(netloc, "profile.default_url（经 target_endpoint()）")

    client_side = (profile.get("seedgen") or {}).get("client_side") or {}
    _add(client_side.get("server_addr"), "profile.seedgen.client_side.server_addr")
    _add(client_side.get("client_addr"), "profile.seedgen.client_side.client_addr")

    return endpoints, sources


def endpoint_default_ports(profile: dict) -> tuple[str, str]:
    """返回 ``(服务端默认端口, 客户端默认端口)``（无则空串）。

    用于端口缺省时的补齐（SIP 的 ``sip:127.0.0.1`` → 5060；Via 的 ``127.0.0.1``
    → 5061）。
    """
    server_port = ""
    client_port = ""
    _scheme, netloc = target_endpoint(profile)
    if ":" in netloc and netloc.rsplit(":", 1)[1].isdigit():
        server_port = netloc.rsplit(":", 1)[1]
    client_side = (profile.get("seedgen") or {}).get("client_side") or {}
    for value in (client_side.get("server_addr"), client_side.get("client_addr")):
        text = str(value or "").strip()
        if ":" in text and text.rsplit(":", 1)[1].isdigit():
            port = text.rsplit(":", 1)[1]
            if not server_port:
                server_port = port
            if not client_port:
                client_port = port
    return server_port, client_port

#: 文本里的**层级式 URL**（`scheme://authority`）—— authority 到
#: `/`、`?`、`#`、`;`、引号、空白、`<`、`>` 为止。
#:
#: ★ 为什么需要它：`normalize_target_endpoint` 只处理**整个 URL 字符串**，
#:   而真实抓包的**头部里**也嵌着 URI，例如
#:   ``Authorization: Digest ... uri="rtsp://10.11.26.98:554/isapi/..."``、
#:   ``Content-Base: rtsp://10.11.26.98:554/isapi/.../``、
#:   ``Rtp-Info: url=rtsp://10.11.26.98:554/isapi/.../trackID=1;seq=4276``。
#:   只归一化消息级 url ⇒ 这些**头部里的外网端点会原样留在 `.raw` 字节里**
#:   ⇒ 种子打向目标环境不存在的设备（服务端返 404，**所有健康度指标都不会红**
#:   ⇒ 静默退化），且 `corpus_gate` 的 G1 会判违规。
_RE_HIER_URL_IN_TEXT = re.compile(
    r"([A-Za-z][A-Za-z0-9+.\-]*://)([^\s/?#;\"'<>]+)")

#: ★ 批次 1.5 改动 5（R-4）：**完整**的层级式 URL（含 path/query）。
#:   ``_RE_HIER_URL_IN_TEXT`` 只匹配到 ``scheme://authority``
#:   ⇒ 端点归一化**碰不到资源段** ⇒ 头部里的 URI 资源段原样保留。
_RE_HIER_URL_FULL_IN_TEXT = re.compile(
    r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s/?#;\"'<>]+(?:/[^\s;\"'<>]*)?")

#: ★ 批次 1.5 改动 5（R-4）：**完整**的层级式 URL（含 path/query）。
#:   ``_RE_HIER_URL_IN_TEXT`` 只匹配到 ``scheme://authority``
#:   ⇒ 端点归一化**碰不到资源段** ⇒ 头部里的 URI 资源段原样保留。
_RE_HIER_URL_FULL_IN_TEXT = re.compile(
    r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s/?#;\"'<>]+(?:/[^\s;\"'<>]*)?")


def normalize_target_endpoint_in_text(text: str, profile: dict) -> str:
    """把**任意文本**里出现的层级式 URL 的**端点**归一化到 profile 声明的目标服务。

    ★ 与 `normalize_target_endpoint` 的关系：
      - 协议级开关（`endpoint_normalization_enabled`）**完全继承** ⇒
        SIP / SMTP 等开关关闭的协议**逐字节不变**（它们的 URI domain 是逻辑实体标识，
        改写会破坏消息语义）；
      - **幂等**（关键不变量）：对本就指向 `default_url` 的文本**原样返回**
        ⇒ 现存历史语料（RQ1.2 / RQ3）不受影响，连续性硬不变式得以保持；
      - 只处理**层级式** URL（`scheme://authority`）—— 非层级式 URI
        （`sip:user@host`）的 authority 不是路由端点，改写没有意义。

    Args:
        text:    任意文本（头值、参数串等）。
        profile: 协议 profile（读 `default_url` / 开关）。

    Returns:
        归一化后的文本；开关关闭或找不到层级式 URL 时**原样返回**。
    """
    if not text or not endpoint_normalization_enabled(profile):
        return text          # ★ 协议级开关关闭 ⇒ 逐字节原样返回

    def _repl(m: re.Match) -> str:
        return normalize_target_endpoint(m.group(0), profile)

    return _RE_HIER_URL_IN_TEXT.sub(_repl, str(text))


def normalize_target_resource_in_text(text: str,
                                         allowed_resources: Optional[list[str]],
                                         fallback_resource: str = "") -> str:
    """把文本里层级式 URL 的**资源段**归一化到目标环境允许的集合。

    ★ 与 :func:`normalize_target_endpoint_in_text`（**只换 authority**）互补：
      端点归一化解决「打向**哪台机器**」，资源段归一化解决「打**哪一路会话**」。
    ★ R-4（P1）：``Authorization: Digest ... uri="rtsp://host/isapi/…/101"``
      与请求行的会话名**失配** ⇒ 服务端算 Digest 用**请求行** ⇒ **返 401**
      ⇒ 该种子零价值（且 G2 只扫请求行 ⇒ **看不见**这个问题）。
    ★ **幂等**：对已可播的 URL 原样返回（``normalize_seed_resource`` 的既有语义）。
    ★ **协议无关**：非层级式 URI（``sip:user@host``）不匹配 ⇒ 原样保留。
    """
    if not text or not allowed_resources:
        return text

    def _repl(m: re.Match) -> str:
        return normalize_seed_resource(m.group(0), allowed_resources,
                                      fallback_resource)

    return _RE_HIER_URL_FULL_IN_TEXT.sub(_repl, str(text))


def normalize_target_endpoint(url: str, profile: dict) -> str:
    """把种子 URL 的**端点**归一化到 profile 声明的目标服务。

    ★ 为什么必须做（缺陷 3）：
      `traffic` 源是混合抓包，含**非目标设备**的 Request-URI
      （实测某 IP 摄像机 ``rtsp://10.11.26.98:554/isapi/...``）。
      种子若原样透传，就会打向目标环境根本不存在的设备 —— 服务端返 404，
      **且所有健康度指标都不会红**（静默退化）。

    ★ **协议级开关**（`endpoint_normalization_enabled`）：开关关闭的协议
      （SIP / SMTP 等）**原样返回 url（逐字节不变）** —— 它们的 URI domain 是
      逻辑实体标识，改写会破坏消息语义并丢掉 userinfo。

    ★ 幂等性（关键不变量）：
      对 URL 本就指向 `default_url` 的种子，本函数**原样返回**（逐字节不变）。
      ⇒ 现存历史语料（RQ1.2 / RQ3）不受影响，连续性硬不变式得以保持。

    ★ 只改写**层级式 URL**（``scheme://authority/...``）：非层级式 URI
      （``sip:user@host``）的 authority 不是路由端点，改写它没有意义。

    Args:
        url:    种子里的 URL。
        profile: 协议 profile（读 `default_url` / `url_placeholders` / 开关）。

    Returns:
        归一化后的 URL；无法判定目标端点时原样返回。
    """
    if not url:
        return url
    if not endpoint_normalization_enabled(profile):
        return url          # ★ 协议级开关关闭 ⇒ 逐字节原样返回
    scheme, netloc, path, query, fragment = _split_url_parts(url)
    if not netloc or not scheme:
        return url
    if "://" not in url:
        return url          # 非层级式 URI（sip:user@host）⇒ 不改写
    tgt_scheme, tgt_netloc = target_endpoint(profile)
    if not tgt_netloc or netloc == tgt_netloc:
        return url
    # 端点（scheme + host:port）整体换成本 profile 描述的目标服务：
    # profile 是目标服务的**权威描述**，故 scheme 也以它为准（抓包的 scheme
    # 属于源侧事实）。path 不动（资源名归「资源归一化」管）；
    # query / fragment **原样带回**（不得静默丢弃）。
    out_scheme = tgt_scheme or scheme
    prefix = f"{out_scheme}://" if out_scheme else ""
    return f"{prefix}{tgt_netloc}{path}{query}{fragment}"


def _resource_path_shape(path: str, segments: list[str]) -> str:
    """取原 URL 的**路径形态尾巴**（RTSP 的 URL 模板形态，协议无关）。

    RTSP 的 URL 模板只有三种形态（见 `fused_hub/targets/rtsp_request_templates.json`
    与 `profile.seedgen.url_template`）：
      · ``/{stream}``            —— OPTIONS / DESCRIBE
      · ``/{stream}/track{N}``   —— SETUP
      · ``/{stream}/``           —— PLAY / TEARDOWN / PAUSE ...

    所以改写不可播资源时，只需保留这两条**形态标记**：
      · 末段是「编号子记号」（``track1`` / ``trackID=1``）→ 保留为
        ``track{N}`` 形态（去掉源侧的 ``ID=`` 写法，统一成目标侧的命名）；
      · 路径以 ``/`` 结尾 → 保留尾斜杠（PLAY / TEARDOWN 的形态标记）。

    Returns:
        形态尾巴（``""`` / ``"/"`` / ``"/track{N}"``）。
    """
    if len(segments) < 2:
        return ""            # 只有资源段本身 ⇒ 无形态尾巴
    last = segments[-1]
    match = _TRACK_SUFFIX_RE.match(last)
    if match:
        name = match.group("name")
        if len(name) > 2 and name[-2:].lower() == "id":
            name = name[:-2]     # trackID=1 → track1（目标侧的命名形态）
        return f"/{name}{match.group('num')}"
    if path.endswith("/"):
        return "/"
    return ""


def normalize_seed_resource(url: str, allowed_resources: Optional[list[str]],
                             fallback_resource: str = "") -> str:
    """把种子 URL 的**资源段**归一化到目标环境允许的集合。

    语义（协议无关）：URL path 的**第一段**标识资源实例。若它不在
    `allowed_resources`（目标环境实际可播/可用的资源）内，说明该 URL 指向的是
    **源侧抓包里的别的东西**（如摄像机的 ``/isapi/streaming/channels/101``），
    目标环境根本不认识 → 换成 `fallback_resource`（该种子已分配的可播资源）。

    ★ 只在第一段**不可播**时改写；已可播的 URL 原样返回（幂等）。
    ★ **保留原 URL 的路径形态**（`_resource_path_shape`）：目标侧 URL 模板有
      ``/{stream}`` / ``/{stream}/track{N}`` / ``/{stream}/`` 三种形态，
      形态信息承载着**方法语义**（SETUP 的 track、PLAY 的尾斜杠）。
      早期实现把路径其余部分**整体丢弃**，导致 35/54 条种子由「2 个不同 URL」
      塌成「1 个」——URL 多样性退化（distinct URL 集合/种子 0.259 → 0.204，
      已发表健康语料基线为 0.564）。
      源侧的多级路径（如 ``/isapi/streaming/channels/101``）本身对目标环境无意义
      （会 404），故只保留**形态标记**、丢弃其余中间段。

    ★ query / fragment **原样带回**（不得静默丢弃）。

    Args:
        url:               种子 URL。
        allowed_resources: 目标环境允许的资源名；None/空 → 不做改写。
        fallback_resource: 改写时使用的资源名（为空则不改写）。

    Returns:
        改写后的 URL（无法判定时原样返回）。
    """
    if not url or not allowed_resources:
        return url
    scheme, netloc, path, query, fragment = _split_url_parts(url)
    if not path:
        return url
    segments = [s for s in path.split("/") if s]
    if not segments:
        return url
    if segments[0] in {str(r) for r in allowed_resources}:
        return url           # 已可播 → 幂等，不动
    if not fallback_resource:
        return url
    shape = _resource_path_shape(path, segments)
    prefix = f"{scheme}://{netloc}" if scheme else netloc
    return f"{prefix}/{fallback_resource}{shape}{query}{fragment}"


# ===========================================================================
# 5. 环境级标定
# ===========================================================================

def environment_calibration(env_cfg: dict) -> dict:
    """取目标环境的聚焦组标定覆盖值（`{"A": {...}, ...}`）；无 → 空 dict。

    环境级标定**优先于**协议级 `seedgen.focus_group`（更具体的约束优先）。
    """
    return dict((env_cfg or {}).get("focus_group") or {})
