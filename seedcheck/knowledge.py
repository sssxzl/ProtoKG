# -*- coding: utf-8 -*-
"""seedcheck/knowledge.py —— **判据适配层**（把中枢的知识整理成「校验器能查的表」）。

★ 设计原则（seedcheck 的第一原则）
  **校验器自己一条硬编码都不该有** ⇒ 判据全部来自中枢 ⇒ 协议知识一变，校验口径自动跟着变。
  ⇒ 因此本模块是**唯一**读中枢的地方；V1~V6 都只向它要判据。

★ 依赖边界（护栏会检查）
  · 只 import ``core.fused.hub``（读接口）⇒ **不 import ``core.fused.downstream``**
    ⇒ 避免反向耦合（校验层不该依赖被它校验的层）。
  · 只读，不写。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from core import paths
from core.fused.hub.hub_layout import read_classified
from core.fused.hub.hub_view import build_view


@dataclass
class Knowledge:
    """校验用的判据集合（全部来自中枢 + 协议档案）。"""
    protocol: str = ""
    bundle: dict = field(default_factory=dict)          # 中枢视图（hub_view.build_view）
    profile: dict = field(default_factory=dict)          # 协议档案 profile.json
    #: 方法 → 该方法的必填头集合
    required_headers: dict[str, list[str]] = field(default_factory=dict)
    #: 已知方法集合（中枢 existence + profile 声明）
    known_methods: set[str] = field(default_factory=set)
    #: 方法 → 前置方法列表
    precondition: dict[str, list[str]] = field(default_factory=dict)
    #: 方法 → 会话头规则 [{header, from_occurrence}]
    session_header: dict[str, list[dict]] = field(default_factory=dict)
    #: 方法 → URI 模板
    url_template: dict[str, str] = field(default_factory=dict)
    #: 头名 → 规范取值域（value_enum_spec）
    header_values: dict[str, list[str]] = field(default_factory=dict)
    #: ★ 头名（小写）→ 规范取值域（**大小写不敏感**索引）
    #:   ★ 2026-11-11 修正：中枢头名是 ``Transport``，而报文头名常被转成小写
    #:     ⇒ 直接用原 key 查会**取不到** ⇒ 取值域检查被静默跳过（真 bug）。
    header_values_ci: dict[str, list[str]] = field(default_factory=dict)
    #: 头名 → 语法（syntax）
    header_syntax: dict[str, str] = field(default_factory=dict)
    #: 状态机边集合 {(from_state, method, to_state)}
    fsm_edges: set[tuple] = field(default_factory=set)
    #: 资源名集合（该协议可用的资源实例，来自 profile.resources_file）
    resources: list[str] = field(default_factory=list)
    #: 环境 → 可播资源集合（若该环境声明了 playable_resources_file）
    env_resources: dict[str, list[str]] = field(default_factory=dict)
    #: 数据来源说明（写进报告，便于判读）
    notes: list[str] = field(default_factory=list)
    #: 中枢 ``methods`` 桶（方法 → 定义）⇒ **已知方法集**
    methods: dict = field(default_factory=dict)
    #: ★ **已知方法集**（命令型协议的判据）⇒ 由 ``methods`` 派生，亦可单独指定
    #:   （★ 普通字段而非 property ⇒ 便于测试与外部注入）
    known_methods: set = field(default_factory=set)
    #: ★ 协议档案的 ``raw_format`` 段（**V1 分判据的来源**）
    #:   · ``request_line`` 含 ``{version}`` ⇒ **请求型文本协议**（rtsp/sip）
    #:   · ``request_line`` = ``{method} {argument}`` ⇒ **命令型文本协议**（smtp）
    #:   · 有 ``binary_fields`` ⇒ **二进制协议**（DHCPv4）
    #: ⇒ ★ **全部从 profile 取 ⇒ 不硬编码协议名**
    raw_format: dict = field(default_factory=dict)

    @property
    def message_shape(self) -> str:
        """报文的形态（**三档**）⇒ V1 按它选判据。

        · ``"binary"``      —— 二进制协议（有 ``binary_fields``）
        · ``"text_command"`` —— 命令型文本协议（``request_line`` 无 ``{version}``）
        · ``"text_request"`` —— 请求型文本协议（默认）
        """
        rf = self.raw_format or {}
        if rf.get("binary_fields"):
            return "binary"
        rl = str(rf.get("request_line") or "")
        if "{version}" not in rl:
            return "text_command"
        return "text_request"

    def __post_init__(self) -> None:
        """自动派生大小写不敏感索引（避免手工构造时漏填 ⇒ 检查被静默跳过）。"""
        if not self.header_values_ci and self.header_values:
            self.header_values_ci = {str(k).lower(): v
                                    for k, v in self.header_values.items()}

    def domain_of(self, header: str) -> list[str]:
        """取某头的**规范取值域**（**大小写不敏感**）。

        ★ 2026-11-11：中枢头名是 ``Transport``，而报文头名常被转成小写
          ⇒ 用原 key 查会**取不到** ⇒ 取值域检查被**静默跳过**（真 bug）。
        ⇒ 这里**实时**做不敏感查找 ⇒ 不依赖任何预派生索引 ⇒ 不会漏。
        """
        h = str(header).strip()
        if not h:
            return []
        vals = self.header_values_ci.get(h.lower())
        if vals is None:
            vals = self.header_values.get(h)
        if vals is None:
            for kk, vv in self.header_values.items():
                if str(kk).lower() == h.lower():
                    vals = vv
                    break
        return list(vals or [])

    def has(self) -> bool:
        """中枢是否有数据。"""
        return bool(self.bundle)


def _load_profile(protocol: str) -> dict:
    p = paths.targets_root() / protocol.lower() / "profile.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_bundle(protocol: str) -> tuple[dict, list[str]]:
    """读中枢并组装视图 ⇒ 返回 (bundle, notes)。"""
    notes: list[str] = []
    hub = paths.hub_root()
    views = read_classified(hub, protocol)
    if not views:
        notes.append("中枢无本协议数据（先跑 build_hub.py）")
        return {}, notes
    bundle = build_view(views, protocol)
    notes.append(f"中枢视图：{len(views)} 条 fact → {len(bundle)} 个桶")
    return bundle, notes


def _collect_header_values(bundle: dict) -> dict[str, list[str]]:
    """headers 桶 → {头名: 规范取值域}（value_enum_spec 汇入 values 池）。"""
    out: dict[str, list[str]] = {}
    for name, info in (bundle.get("headers") or {}).items():
        vals = info.get("values") or []
        if vals:
            out[str(name)] = [str(v) for v in vals]
    return out


def _collect_header_syntax(bundle: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, info in (bundle.get("headers") or {}).items():
        syn = info.get("syntax")
        if syn:
            out[str(name)] = str(syn)
    return out


def _collect_fsm_edges(bundle: dict) -> set[tuple]:
    out: set[tuple] = set()
    for t in (bundle.get("transitions") or []):
        try:
            frm, meth, to = t[0], t[1], t[2]
        except (TypeError, IndexError):
            continue
        out.add((str(frm), str(meth), str(to)))
    return out


def _load_resources(protocol: str, profile: dict) -> list[str]:
    """协议档案声明的资源清单（``resources_file``）⇒ 资源名列表。"""
    res_file = profile.get("resources_file")
    if not res_file:
        return []
    for cand in (paths.targets_root() / protocol.lower() / res_file,
                 paths.targets_root() / res_file):
        if not cand.is_file():
            continue
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        return [str(s.get("name")) for s in (data.get("streams") or [])
                if s.get("name")]
    return []


def _load_env_resources(protocol: str, profile: dict) -> dict[str, list[str]]:
    """各环境的可播资源子集（``seedgen.environments.<env>.playable_resources_file``）。"""
    out: dict[str, list[str]] = {}
    envs = ((profile.get("seedgen") or {}).get("environments") or {})
    for env_name, env_cfg in envs.items():
        fn = (env_cfg or {}).get("playable_resources_file")
        if not fn:
            continue
        for cand in (paths.targets_root() / protocol.lower() / fn,
                     paths.targets_root() / fn):
            if not cand.is_file():
                continue
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            names = data.get("playable")
            if isinstance(names, list):
                out[str(env_name)] = [str(n).strip() for n in names if str(n).strip()]
                continue
            out[str(env_name)] = [str(i.get("name")).strip()
                                  for i in (data.get("streams") or [])
                                  if isinstance(i, dict) and i.get("name")]
            break
    return out


def load_knowledge(protocol: str) -> Knowledge:
    """加载某协议的**全部校验判据**。"""
    k = Knowledge(protocol=protocol)
    k.profile = _load_profile(protocol)
    k.raw_format = dict(k.profile.get("raw_format") or {})
    bundle, notes = _load_bundle(protocol)
    k.bundle = bundle
    k.notes.extend(notes)

    # 必填头：中枢 required_headers 桶（method → [header]）
    for meth, heads in (bundle.get("required_headers") or {}).items():
        k.required_headers[str(meth)] = [str(h) for h in (heads or [])]

    # 已知方法：中枢 methods 桶的键 + profile 声明的 allowed_methods
    for meth in (bundle.get("methods") or {}):
        k.known_methods.add(str(meth))
    for meth in ((k.profile.get("seedgen") or {}).get("allowed_methods") or []):
        k.known_methods.add(str(meth))

    k.precondition = {str(m): [str(x) for x in (v or [])]
                      for m, v in (bundle.get("precondition") or {}).items()}
    k.session_header = {str(m): [dict(x) for x in (v or [])]
                        for m, v in (bundle.get("session_header") or {}).items()}
    k.url_template = {str(m): str(v) for m, v in (bundle.get("url_template") or {}).items()}
    k.header_values = _collect_header_values(bundle)
    k.header_values_ci = {str(kk).lower(): vv for kk, vv in k.header_values.items()}
    # ★ 已知方法集（中枢 methods 桶）⇒ 命令型协议的「命令名是否已知」判据
    k.methods = dict(bundle.get("methods") or {})
    k.known_methods = set(k.methods.keys())
    k.header_syntax = _collect_header_syntax(bundle)
    k.fsm_edges = _collect_fsm_edges(bundle)
    k.resources = _load_resources(protocol, k.profile)
    k.env_resources = _load_env_resources(protocol, k.profile)

    if not k.required_headers:
        k.notes.append("中枢无必填头知识（required_headers 为空）")
    if not k.fsm_edges:
        k.notes.append("中枢无状态机边（transitions 为空）")
    if not k.resources:
        k.notes.append("协议档案未声明 resources_file ⇒ 无资源级判据")
    return k
