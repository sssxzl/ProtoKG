"""core/fused/downstream/rag_seedgen.py —— 知识中枢 → RAG → LLM → 种子。

这是 中枢的「LLM RAG 消费通路」（第一步，全量分桶组装）。

定位
----
中枢的 facts（<Subject, Aspect, Condition, Value, Epistemic, Evidence> 知识原子）
是**结构化知识图谱**（Knowledge-based GraphRAG 范式），不需要向量检索。
本模块把 facts 按 aspect 分桶组装成「种子生成知识」，渲染成 prompt，调 LLM
生成种子，再用中枢知识做轻量校验。

两步走（对齐前沿方法）:
  第一步（本模块）: 全量分桶组装（~200 原子整包喂），验证「知识能指导 LLM
    生成合法种子」。第二步（subgraph 检索 + ReAct 迭代 refine）已实现, 见本文件后段。
  第二步（已实现, 见本文件 retrieve_subgraph / generate_seeds_react）: 按目标 method/state 做结构化 subgraph 检索（GraphRAG），
    生成→校验→带错重生成的 ReAct loop（Self-RAG / Corrective RAG）。

参考前沿方法: RAG-ReAct (arXiv 2502.15727)、MultiFuzz (AICCSA 2025)、
GraphRAG 综述 (ACM TOIS 2025)、Agentic RAG / Self-RAG。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Optional

from core import paths
from core.fused.llm_ensemble import semantic_rules_enabled



# ★★ 阶段 D1（2026-11-09）：**组装逻辑上移到中枢视图层**
#   （core/fused/hub_view.py）⇒ 「读中枢 ⇒ 组装视图」归中枢层，
#   消费层只保留**消费策略**（白名单 / 骨架方法 / 实例迁移）。
#   ★ 下列名字**从视图层再导出** ⇒ 既有 import 路径**全部不变**（零改动）。
from core.fused.hub_view import (          # noqa: E402
    BUNDLE_SCHEMA_VERSION,
    RFC_AUTHORITY,
    SKELETON_AUTHORITY,
    _BUCKET_BY_KIND,
    _EXPECTED_BEHAVIOR_CODES,
    _GLOBAL_REQUIRED_KEY,
    _INFERABLE_OPERATORS,
    _OPERATOR_DOMAINS,
    _REJECT_ABSENT_OPERATOR,
    _align_message_instances,
    _as_operand_tuple,
    _canonical_key,
    _constraint_fields,
    _dedup_entries,
    _dedupe_sorted,
    _derive_method_order,
    _entity_headers_from_profile,
    _inject_vuln_self_loops,
    _jsonable,
    _lifted_fact_to_plain,
    _load_allowed_methods,
    _load_profile_structure,
    _merge_bucket,
    _normalize_state,
    _project_rule,
    _render_domains,
    _render_operand,
    _resolve_expected_behavior,
    _resolve_semantic_rules,
    _rule_to_plain,
    _select_active_transitions,
    build_view,
    load_semantic_rules,
    project_semantic_rules,
)


def assemble_bundle(views: list[dict], protocol: str = "rtsp",
                   *,
                   semantic_rules: Optional[list] = None,
                   source_set: Optional[Iterable[str]] = None,
                   apply_allowed_methods: bool = True,
                   include_skeleton_methods: bool = True,
                   allow_instance_migrate: bool = True) -> dict:
    """**消费层的入口**：组装中枢视图 + 施加**消费策略**。

    ★ 阶段 D1（2026-11-09）：组装逻辑已上移到**中枢视图层**
      （``core/fused.hub_view.build_view``）⇒ 这里只做**消费层特有的策略**：
      · ``apply_allowed_methods``    —— 是否用 ``profile.allowed_methods`` 白名单
      · ``include_skeleton_methods`` —— 是否并入骨架（authority=profile）的方法
      · ``allow_instance_migrate``  —— 是否允许实例迁移
    ★ **函数签名与返回结构保持不变** ⇒ 既有调用点**零改动**。
    ★ 视图层额外提供 ``by_category`` / ``entities``（D1 新增，追加在末尾）。
    """
    return build_view(
        views, protocol,
        semantic_rules=semantic_rules,
        source_set=source_set,
        apply_allowed_methods=apply_allowed_methods,
        include_skeleton_methods=include_skeleton_methods,
        allow_instance_migrate=allow_instance_migrate,
    )

# ===========================================================================
# 1. 加载五源 facts（view dict）
# ===========================================================================

DEFAULT_FACTS_ROOT = paths.model_root() / "per_source"


#: ★ 批次 1.6 步 1：中枢 aspect 布局的**顺序索引**（相对 aspect 目录）。
ASPECT_ORDER_INDEX = "_index/order.jsonl"


def _load_aspect_order(aspect_dir: Path) -> dict[str, list[int]]:
    """读 aspect 布局的顺序索引 ``{文件名: [全局下标, ...]}``。

    ★ 为什么必须有它：源文件里的 aspect 是**交错**的 ⇒ 「某条事实在全局序列
      中的位置」不可从事实字段还原（fact_id 是哈希）⇒ 读取端若只按
      「aspect 文件名序」拼接，``methods``/``headers`` 的**键插入序**就会变
      ⇒ 下游种子编号漂移（实测 rtsp 58 条种子 MD5 全变）。
    """
    index_path = aspect_dir / ASPECT_ORDER_INDEX
    order: dict[str, list[int]] = {}
    if not index_path.is_file():
        return order
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = row.get("file")
        positions = row.get("positions")
        if name and isinstance(positions, list):
            order[name] = positions
    return order


def _filter_protocol(views: list[dict], protocol: str) -> list[dict]:
    """按 ``fact_key.protocol`` **过滤**事实（中枢共用一套 ⇒ 必需）。

    ★ 无 protocol 字段的记录（占位/测试数据）**保留**。
    ★ 该协议**没有**记录 ⇒ 返回空（**不要回落到其它协议**）。
    """
    _want = str(protocol or '').strip().lower()
    if not _want:
        return views
    return [v for v in views
            if (not str(((v.get('fact_key') or {}).get('protocol')
                 or '')).strip().lower())
            or str(((v.get('fact_key') or {}).get('protocol')
                   or '')).strip().lower() == _want]

def load_fact_views(protocol: str = "rtsp",
                    facts_root: Optional[Path] = None) -> list[dict]:
    """读中枢的 fact view。

    ★ 批次 1.6 步 1（中枢布局改 aspect）：**新布局优先、旧布局降级**。

    - 新布局 ``derived/per_source/<protocol>/facts/<aspect>.jsonl``
      —— 中枢按 **aspect**（知识维度）统一存放；「源」退化为事实内部的
      ``all_claims[].authority`` 字段，不再是目录层级。
    - 旧布局 ``derived/per_source/<protocol>/*/facts/*.jsonl``
      —— 按源分目录（协议 × 源二维解耦）；**保留**作回退保险。

    两种布局**不会**互相重复读到：旧 glob ``*/facts/*.jsonl`` 需要三层路径
    （源目录 / facts / 文件），而新布局只有两层（facts / 文件）⇒ 不命中。

    ★ 存在新布局时**只读新布局**（它是本次中枢的权威视图）；新布局缺失或为空
      ⇒ 自动降级读旧布局（不破坏既有产物）。

    ★★ 新布局的**顺序**由 ``facts/_index/order.jsonl`` 还原 ⇒ 与旧布局的
      **全局遍历序完全一致** ⇒ 下游 bundle 的键插入序不变 ⇒ 种子逐字节不变。
      索引缺失时按「aspect 文件名序」拼接（降级，不崩）。
    """
    views: list[dict] = []
    root = Path(facts_root) / protocol.lower() if facts_root else \
        paths.hub_root()
    # ★★★ **阶段 C：按知识分类的布局优先**（2026-11-09）
    #   新：derived/hub/<分类>/<文件>.jsonl（A~F 六个知识分类）
    #   旧：derived/hub/facts/<aspect>.jsonl（批次 1.6 的 aspect 布局）
    #   更旧：<各源根>/*/facts/*.jsonl（按源分目录）
    if root.is_dir():
        from core.fused.hub_layout import read_classified
        _cls = read_classified(root, protocol)
        if _cls:
            return _filter_protocol(_cls, protocol)
        aspect_dir = root / "facts"
        new_files = (sorted(aspect_dir.glob("*.jsonl"))
                     if aspect_dir.is_dir() else [])
        if new_files:
            views = _load_aspect_views(aspect_dir, new_files)
            # ★ ★ **按协议过滤**（2026-11-08 中枢重设计）：中枢**共用一套**
            #   （不按协议分目录）⇒ 读取端**必须**按 protocol 过滤
            #   ⇒ 否则会把别的协议的知识当成本次的（跨协议污染）。
            #   ★ 无 protocol 字段的记录（占位/测试数据）**保留**。
            return _filter_protocol(views, protocol)
    # ★ **降级路径**：读**各源**的中间产物（``<各源根>/*/facts/*.jsonl``）
    #   ⇒ 中枢共用一套后，各源目录仍在 ``per_source/<协议>/<源>/facts/``
    #   ⇒ 降级时用 ``per_source_root``（不是 hub_root）。
    _src_root = paths.per_source_root(protocol)
    for jsonl in sorted(_src_root.glob("*/facts/*.jsonl")):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                views.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    # ★ 降级路径也要**按协议过滤**（各源目录里可能有别的协议的残留）
    _want2 = str(protocol or "").strip().lower()
    if _want2:
        return [v for v in views
                if (not str(((v.get("fact_key") or {}).get("protocol")
                     or "")).strip().lower())
                or str(((v.get("fact_key") or {}).get("protocol")
                        or "")).strip().lower() == _want2]
    return views
    return views


def load_source_manifest(protocol: str = "rtsp",
                         facts_root: Optional[Path] = None) -> dict:
    """读中枢的**本次源集合清单**（``sources.json``）—— **唯一权威**。

    ★ 批次 1.6 步 5：消费端据它判断「本次参与了哪些源」；
      组装侧与消费端**都**只看这个清单 ⇒ 源集合只有一个真相来源。
    ★ 缺失 / 解析失败 ⇒ 返回 ``{}`` ⇒ 调用方按「**不过滤**」处理（兼容期：
      中枢尚未按批次 1.6 的流程重建）。
    """
    root = Path(facts_root) / protocol.lower() if facts_root else \
        paths.hub_root()
    path = root / "sources.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(doc, dict):
        return {}
    # ★ ★ **多协议兼容**（2026-11-08 中枢重设计）：中枢**共用一套**
    #   ⇒ ``sources.json`` 顶层有 ``protocols: {<协议>: {...}}``
    #   ⇒ 取本协议的那一段（缺失则回落到顶层字段）。
    _want = str(protocol or "").strip().lower()
    _ps = doc.get("protocols")
    if isinstance(_ps, dict) and _want:
        _one = _ps.get(_want)
        if isinstance(_one, dict):
            return _one
    return doc


def _load_aspect_views(aspect_dir: Path, files: list[Path]) -> list[dict]:
    """读新布局的 fact view，并按顺序索引**还原全局遍历序**。"""
    order = _load_aspect_order(aspect_dir)
    items: list[tuple[Optional[int], int, dict]] = []
    seq = 0
    for jsonl in files:
        positions = order.get(jsonl.name) or []
        idx = 0
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                view = json.loads(line)
            except json.JSONDecodeError:
                continue
            pos = positions[idx] if idx < len(positions) else None
            items.append((pos, seq, view))
            idx += 1
            seq += 1
    # 有下标的按下标排；无下标的（索引缺失/不匹配）稳定排在其后
    known = [it for it in items if it[0] is not None]
    unknown = [it for it in items if it[0] is None]
    known.sort(key=lambda it: (it[0], it[1]))
    return [it[2] for it in known] + [it[2] for it in unknown]


# ===========================================================================
# 2. 分桶组装（全量，第一步）
# ===========================================================================









def _output_format_example(protocol: str) -> str:
    """按 profile 的 raw_format 生成协议化的 LLM 输出格式示例（JSON 片段）。

    行命令协议（ftp/smtp，request_line 含 {argument} 不含 {url}）用 method+argument；
    头部协议（rtsp/sip，request_line 含 {url}）用 method+url+headers+body。
    避免硬编码 RTSP 示例污染其他协议。
    """
    from core import paths
    import json
    prof = paths.target_profile(protocol)
    rf: dict = {}
    if prof.exists():
        try:
            rf = (json.loads(prof.read_text(encoding="utf-8")) or {}).get("raw_format") or {}
        except (json.JSONDecodeError, OSError):
            rf = {}
    request_line = rf.get("request_line", "")
    if "{url}" in request_line:
        return (
            '{"description": "...", "url": "<完整URL>", "state_path": ["Init", ...], '
            '"messages": [\n'
            '    {"method": "<方法1>", "url": "<完整URL>", "headers": {"<必填头>": "值"}, "body": ""}\n'
            '  ]}'
        )
    return (
        '{"description": "...", "state_path": ["Init", ...], "messages": [\n'
        '    {"method": "<命令1>", "argument": "<参数>"},\n'
        '    {"method": "<命令2>", "argument": "<参数>"}\n'
        '  ]}'
    )




# ===========================================================================
# 2.5 bundle 契约扩展 + 语义规则投影（B-8）
#
# 设计依据：docs/实施/路线与里程碑/RFC源里程碑路线图.md
#   · §3.6（选项 c：「影子实现升级为两层模型，`legal_boundary` 桶保留但由两层
#     模型投影填充」）—— 语义规则走 bundle 的**独立键** `semantic_rules`，
#     不进 `facts.jsonl`（`models.py` 的 fact_id 派生链零影响）；
#   · §3.8 任务表 B-8（文档任务号 B7）。
#
# ★ 投影是**单向、纯函数、可测**的：
#     semantic_rules[i] ──project──► legal_boundary[subject] += {dim,legal,illegal,trigger}
#                                └─► response_expectation[subject] += {violation,expected_code,expected_behavior}
#   `legal`/`illegal` 由 operator/operand **反向渲染**回自然语言（供 LLM prompt
#   读），`trigger` 由 `expected_behavior` 填 ⇒ **投影产物不带新信息**。
#
# ★ 三条硬约束（缺一不可）：
#   ① **幂等** —— 同一 bundle 连续投影两次 ⇒ 两桶逐字节相同；
#   ② **旧 bundle 兼容** —— 无 `semantic_rules` 键 ⇒ 投影是**空操作**；
#   ③ **旧 facts 来源保留** —— 投影是**新增**来源（追加 + 去重），不替换
#      既有 facts 条目 ⇒ `boundary_probe` / `strategy` 零改动仍工作。
# ===========================================================================

#: 当前 bundle 契约版本（新增 `semantic_rules` 键之后的版本号）。

#: 旧 bundle（无 `bundle_schema_version` 键）的版本号 —— 读取方按 1.0 容忍。
BUNDLE_SCHEMA_VERSION_LEGACY = "1.0"

#: 响应类（`rfc_config.expected_response_classes` 的规范词表，实测 rtsp/sip/smtp
#: 三协议一致：`success` / `protocol_error` / `application_error` / `silence`）
#: → 状态码族。
#: ★ **词表外一律留空** —— 不臆造状态码（投影不带新信息）。

#: operator → (合法域模板, 非法域模板)。`{op}` = 操作数的渲染文本。
#: ★ 模板里**不含任何协议特定词** ⇒ 协议无关（rtsp/sip/smtp 通用）。
#: ★ 合法域 = **满足**约束的取值域；非法域 = **违反**约束的取值域。
#:   `absent` ⇒「该字段不得出现」⇒ **出现即非法**（illegal = 存在）。

#: 可**确定性推断**处理期望的算子（存在性 / 取值约束）。
#: ★ 推断规则（协议无关）：客户端发出的报文违反「必须存在 / 取值须在域内」的
#:   约束 ⇒ 服务端应拒 ⇒ ``protocol_error``。
#: ★ 只推断 ``protocol_error``，**不推断** ``silence`` / ``application_error``
#:   —— 证据里没有区分这三者的依据，硬分会造出假精度（2026-11-07）。

#: ★ 2026-11-07：``operator == "absent"`` 的规则在**当前抽取链路上语义不可靠**
#:   ⇒ 投影层**拒收**（不进 legal_boundary / response_expectation）。
#:
#:   实测依据：权威规则库里 ``absent`` 只有 3 条，**3/3 全部错位**——
#:     · ``Accept``（RFC 3261 §Bodies/Message Body Type）原文是
#:       「**若**远端要求不带 multipart 的 Accept，则必须发非 multipart 的
#:       session description」⇒ 条件约束，被抽成「Accept 不得出现」；
#:     · ``From``（RFC 5322 §Originator Fields）原文是「From **不应包含**不属于
#:       作者的邮箱」⇒ 内容约束，被抽成「From 不得出现」（From 还是必填头）；
#:     · ``Reply-To``（RFC 5322 同节）原文是「**没有** Reply-To 时回复默认发给
#:       From」⇒ 缺省行为描述，被抽成「Reply-To 不得出现」。
#:   这三条会经 `_render_constraints()` 原样进 prompt，标题还写着「生成时字段
#:   取值须落在合法域」⇒ 等于教 LLM「SIP 报文不要带 From」，属**知识污染**。
#:
#:   ⇒ 放开条件：抽取器能区分「字段禁止」与「内容约束 / 条件描述」之后
#:     （届时应补一条 `absent` 的正例测试再改回 False）。


def get_bundle_schema_version(bundle: dict) -> str:
    """读 bundle 的契约版本。

    ★ **读取方必须容忍旧 bundle**：无 `bundle_schema_version` 键 ⇒ 返回
      `"1.0"`（不抛异常、不猜版本）。
    """
    if not isinstance(bundle, dict):
        return BUNDLE_SCHEMA_VERSION_LEGACY
    raw = bundle.get("bundle_schema_version")
    text = str(raw).strip() if raw is not None else ""
    return text or BUNDLE_SCHEMA_VERSION_LEGACY































#: ★ 批次 1.6 步 2：协议骨架在中枢里的 authority（骨架**不是**抽取源，
#:   而是跨实验复用的协议结构 ⇒ 组装期过滤时**恒允许**）。

#: ★ 2026-11-05：**规范原生**状态机的 authority（直接抽自 RFC 文本）。
#:   ★ 已知：骨架的 ``target_state`` 实为 **source 源**派生（``skeleton.json``
#:     的 ``origin.source`` 含 ``target_state``）—— 追查出的思想源头是
#:     ``source_autoseeder.py`` 提示词里硬塞的 **SIP 式状态名范例**
#:     ⇒ 骨架的状态名**不一定**属于该协议的规范。

#: ★ P2-1（2026-11-06）：``required_headers`` 桶里表示「**所有方法**都要带」的键。
#:   RFC 源的 ``required_header_global`` 事实（rtsp→CSeq；sip→To/From/CSeq/
#:   Call-ID/Max-Forwards/Via）语义就是**消息级**必填头 ⇒ 收在这个键下，
#:   由 :func:`required_headers_for` 与方法级清单合并。
#:   ⚠ 用 ``"*"`` 而不是给每个方法复制一份：方法集是可变的（RFC/骨架/白名单都
#:     能改），复制会在「新增方法」时漏同步；单一真相 + 读取时合并更稳。


def required_headers_for(headers_map: dict, method: str) -> list[str]:
    """某方法的**实际必填头** = 全局（``"*"``）+ 方法级，去重保序。

    ★ 为什么需要这个函数：``required_headers`` 桶里有两类键 ——
      方法名（方法级清单）与 ``"*"``（消息级/全局清单）。
      消费端若只 ``.get(method)`` 就会**漏掉全局必填头**
      （实测 rtsp 的 CSeq、sip 的 To/From/CSeq/Call-ID/Max-Forwards/Via）。

    Args:
        headers_map: ``bundle["required_headers"]``（``{方法名或 "*": [头名…]}``）。
        method: 方法名（大小写不敏感）。

    Returns:
        去重后的头名列表（全局在前、方法级在后）。
    """
    if not headers_map:
        return []
    key = str(method or "").strip().upper()
    # 方法名匹配**大小写不敏感**：桶里的键可能是 profile 给的原样写法
    # （`setup` / `Setup`），而调用方拿到的是 `message.method`（多为大写）。
    specific: list = []
    for _k, _v in headers_map.items():
        if str(_k) == _GLOBAL_REQUIRED_KEY:
            continue
        if str(_k).strip().upper() == key:
            specific.extend(_v or [])
    out: list[str] = []
    for _name in list(headers_map.get(_GLOBAL_REQUIRED_KEY) or []) + specific:
        _n = str(_name or "").strip()
        if _n and _n not in out:
            out.append(_n)
    return out


#: ★ 批次 1.6 步 3：``(subject_type, aspect)`` → **中枢桶名**。
#:   用于「桶级溯源统计」（`bundle["by_source"]`）。
#:   ★ 由 `tests/fused/test_bundle_provenance.py` **逐组合验证**
#:     （每个组合单独组装 ⇒ 落在且只落在指定桶）⇒ 映射表错了测试就红。

#: ★ 批次 1.6 步 3：这些桶有 **profile.json 兜底**来源（facts 再叠加/覆盖）
#:   ⇒ 报告里「facts 派生」与「profile 兜底」**分列**，不混说。
_PROFILE_FALLBACK_BUCKETS: tuple[str, ...] = (
    "required_headers", "precondition", "session_header", "url_template",
)










# ===========================================================================
# 3. 渲染 prompt
# ===========================================================================

def _render_methods(methods: dict) -> str:
    if not methods:
        return "(无方法知识)"
    out = []
    for name, info in sorted(methods.items()):
        flags = []
        if info.get("state_changing"):
            flags.append("改状态")
        if info.get("existence"):
            flags.append("实测观测到")
        suffix = f"（{' / '.join(flags)}）" if flags else ""
        out.append(f"  {name}{suffix}")
    return "\n".join(out)


def _render_transitions(transitions: list) -> str:
    if not transitions:
        return "(无状态机知识)"
    return "\n".join(f"  {src} --{m}--> {dst}"
                     for src, m, dst in transitions)


def _render_required(required: dict) -> str:
    if not required:
        return "(无必填字段知识)"
    return "\n".join(f"  {m} 必填: {', '.join(hs)}"
                     for m, hs in sorted(required.items()))


def _render_values(headers: dict) -> str:
    out = []
    for name, info in sorted(headers.items()):
        if info.get("values"):
            out.append(f"  {name}: {info['values']}")
    return "\n".join(out) if out else "(无取值池知识)"


def _render_security(security: list) -> str:
    if not security:
        return "(无安全关注)"
    return "\n".join(f"  [{stype}] {sname}: {(desc or '')[:160]}"
                     for stype, sname, desc in security)


# 漏洞字段 → 「合法覆盖指引」（种子必须合法，但优先覆盖漏洞相关取值/序列/边界）
#: 漏洞字段 → 「合法覆盖指引」（种子必须合法，但优先覆盖漏洞相关取值/序列/边界）
#:
#: ★ 2026-11-07（A2）：拆成两部分 ——
#:   ① `_VULN_FIELD_GUIDANCE_GENERIC`：**跨协议通用**的词（Digest 的字段名、
#:      CSeq、URL、header…）。这些在哪个协议都成立 ⇒ 留在代码里。
#:   ② `_VULN_FIELD_GUIDANCE_PROTOCOL`：**协议特定**的词（``Transport`` / ``Range`` /
#:      ``track`` / ``interleaved`` / ``client_port``，以及 **HTTP Digest 认证**那组
#:      ``Authorization`` / ``Digest`` / ``nonce`` / ``realm`` / ``uri`` / ``username``）——
#:      它们的取值语法是 RTSP/HTTP 专属的，硬编码会让新协议拿到 RTSP 语义
#:      （如给 SIP 注入「RTP/AVP;unicast;client_port」这种它根本不认识的取值，
#:      或给 SMTP 注入「Digest 认证的 nonce」这种它没有的概念）
#:      ⇒ 下沉到 ``profile.vuln.field_guidance``。
#:
#:   ★ 合并规则：protocol 特定项**覆盖**同名通用项；profile 未声明 ⇒ 用通用缺省。
#:     新协议若不声明 ``field_guidance``，就只拿到通用指引（而不是 RTSP 的）。
_VULN_FIELD_GUIDANCE_GENERIC = {
    "CSeq": "CSeq 用合法取值：正常递增，或相邻请求用相同值（测试重放）",
    "Content-Length": "Content-Length 用合法取值：与实际 body 长度一致，或数值边界（0/较大整数）",
    "URL": "请求 URL 用合法但多样的结构（尾斜杠、边界路径）",
    "header": "各头部字段用合法但多样的取值，覆盖取值池与数值边界",
}

#: ★ 协议特定的漏洞字段指引 —— **默认空**（不内置任何协议的知识）。
#:   各协议在自己的 ``profile.json`` 的 ``vuln.field_guidance`` 段声明。
_VULN_FIELD_GUIDANCE_PROTOCOL: dict = {}


def _vuln_field_guidance(protocol: str = "") -> dict:
    """该协议的「漏洞字段 → 合法覆盖指引」映射（**通用 + 协议特定**）。

    ★ 协议特定项来自 ``profile.json`` 的 ``vuln.field_guidance``（A2，2026-11-07）；
      通用项是内置缺省。**协议特定项覆盖同名通用项**。
    """
    out = dict(_VULN_FIELD_GUIDANCE_GENERIC)
    _key = str(protocol or "").strip().lower()
    proto_specific = _VULN_FIELD_GUIDANCE_PROTOCOL.get(_key)
    if not proto_specific:
        try:
            from core.fused.downstream.protocol_flags import load_profile_section
            proto_specific = load_profile_section(_key, "vuln", "field_guidance")
        except Exception:       # pragma: no cover —— 配置缺失/读盘失败都退回通用缺省
            proto_specific = None
    if isinstance(proto_specific, dict):
        out.update({str(k): str(v) for k, v in proto_specific.items() if v})
    return out


def _render_vuln_guidance(security: list, protocol: str = "") -> str:
    """把漏洞信息翻译成「漏洞导向生成要求」。

    核心：种子必须合法，但优先覆盖历史漏洞相关的字段/序列/边界，
    让 fuzzer 的变异能在漏洞相关区域展开（而非平铺漏洞描述让 LLM 自由发挥）。

    ★ 2026-11-07（A2）：加 ``protocol`` 参数 —— 指引按协议取，
      新协议不再继承 RTSP 的字段取值语义。
    """
    if not security:
        return "(无漏洞信息)"
    fields = sorted({sname for stype, sname, _ in security if stype == "header"})
    methods = sorted({sname for stype, sname, _ in security if stype == "method"})

    lines = ["[漏洞导向生成要求（种子必须合法，但优先覆盖历史漏洞相关字段与序列）]"]
    if methods:
        lines.append(f"  漏洞相关方法（优先覆盖其状态路径）: {', '.join(methods)}")
    if fields:
        lines.append(f"  漏洞相关字段（用多种合法取值覆盖）: {', '.join(fields)}")
    _guidance = _vuln_field_guidance(protocol)
    for field in fields:
        if field in _guidance:
            lines.append(f"    · {field}: {_guidance[field]}")
    lines.append("  要求：除正常会话种子外，生成针对上述字段/序列的「合法边界种子」，"
                 "覆盖漏洞相关取值空间与序列模式；单个字段值 ≤256 字符（禁止超长 AAAA 填充）。")
    return "\n".join(lines)


def _render_constraints(bundle: dict) -> str:
    """渲染 rfc 源抽出的字段约束（legal_boundary 构造约束 C + response_expectation 处理期望 P）。

    借鉴 SemFuzz：rfc 源把「构造约束 C（合法域/非法域）」与「处理期望 P（违反后响应）」
    抽成 legal_boundary / response_expectation 两个桶。喂给 LLM，让它生成「满足合法域、
    接近边界但不越界」的种子（而非直接违反约束——违反留给 fuzzer 变异探索）。
    """
    lb = bundle.get("legal_boundary") or {}
    re_ = bundle.get("response_expectation") or {}
    if not lb and not re_:
        return "(无字段约束知识)"
    lines = ["[字段约束（来自 RFC 规范：合法域/非法域，生成时字段取值须落在合法域、接近边界但不越界）]"]
    for field in sorted(set(lb) | set(re_)):
        for b in (lb.get(field) or []):
            if not isinstance(b, dict):
                continue
            legal = str(b.get("legal", "") or "").strip()
            illegal = str(b.get("illegal", "") or "").strip()
            trigger = str(b.get("trigger", "") or "").strip()
            if not legal and not illegal:
                continue
            seg = f"  {field}: 合法「{legal}」" if legal else f"  {field}:"
            if illegal:
                seg += f" | 非法「{illegal}」"
            if trigger:
                seg += f" → {trigger}"
            lines.append(seg)
    return "\n".join(lines)


def _render_resources(resources: Optional[list]) -> str:
    """渲染目标资源清单（实例级知识，来自 source/traffic 抽取）。"""
    if not resources:
        return "(无资源清单)"
    lines = []
    for r in resources:
        name = r.get("name", "")
        tracks = r.get("tracks", 1)
        fmt = r.get("format", "")
        lines.append(f"  {name}（{tracks} 轨 · {fmt}）")
    return "\n".join(lines)


def _render_request_templates(templates: Optional[dict]) -> str:
    """渲染真实请求模板（提取自真实流量 pcap，请求真实性依据）。"""
    if not templates:
        return ""
    methods = templates.get("methods", {})
    if not methods:
        return ""
    lines = ["[真实请求模板（提取自真实流量，必须严格参照 URL 结构与头部集合）]"]
    for method in sorted(methods):
        t = methods[method]
        urls = " 或 ".join(t.get("url_patterns", []))
        headers = "、".join(t.get("headers", []))
        lines.append(f"  {method}: URL={urls}；头部={headers}")
        ex = t.get("examples", {})
        for hk in ("Accept", "Range", "Transport", "Session"):
            if hk in ex and ex[hk]:
                lines.append(f"       {hk} 取值例: {ex[hk][0]}")
    return "\n".join(lines)


def _url_scheme_prefix(bundle: dict) -> str:
    """从 bundle 实例 URL 里推导 URL **scheme 前缀**（``rtsp://`` / ``sip:`` / ...）。

    ★ 为什么要这个（2026-11-07 修）：`_render_session_semantics()` 原来把
      ``rtsp://<host>:<port>/`` **写死在渲染模板里** ⇒ 任何其它协议只要有
      ``url_template`` 就会被渲染成 rtsp 形态。实测：

          sip 补上 url_template 后 →  ``INVITE → rtsp://<host>:<port>/{user}@{server}``

      这是**错误知识直接进 LLM prompt**（sip 的请求行会变成 rtsp://）。

    ★ 判据**协议无关**：不查协议名，只从 ``message_instances`` 里出现过的 url
      值取 scheme。取不到（如命令类协议没有 url 字段）⇒ 返回空串 ⇒ 调用方
      **不渲染该段**（宁缺勿错）。
    """
    _pat = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*:(?://)?)")
    for _fields in (bundle.get("message_instances") or {}).values():
        for _n, _v in (_fields or []):
            if str(_n or "").strip().lower() != "url" or not _v:
                continue
            _m = _pat.match(str(_v))
            if _m:
                return _m.group(1)
    return ""




def _render_session_semantics(bundle: dict) -> str:
    """渲染会话语义区段（precondition / session_header / url_template，来自知识中枢）。

    这些规则此前硬编码在 prompt 的「硬性规则 5/6」里，现已沉淀为知识中枢 facts，
    由 assemble_bundle 分桶后在此渲染，供 LLM 路径与规则路径共享。
    """
    pre = bundle.get("precondition") or {}
    sh = bundle.get("session_header") or {}
    ut = bundle.get("url_template") or {}
    if not pre and not sh and not ut:
        return "(无会话语义知识)"
    lines = ["[会话语义（来自知识中枢）]"]
    if pre:
        lines.append("  前置方法（生成含该方法的消息前，先发前置方法）:")
        for m, prereqs in sorted(pre.items()):
            lines.append(f"    {m} 前置 {'/'.join(prereqs)}")
    if sh:
        lines.append("  会话头（方法第 N 次出现起携带该头，用 {{session_id}} 占位）:")
        for m, rules in sorted(sh.items()):
            for r in rules:
                lines.append(f"    {m} 第 {r.get('from_occurrence', 1)} 次出现起带 {r.get('header')} 头")
    if ut:
        # ★ 2026-11-07：前缀不再写死 rtsp，改从实例 URL 推导（协议无关）。
        #   authority 占位只对 **authority-based URI** 加（scheme 以 `//` 结尾，
        #   如 `rtsp://` / `http://`）；`sip:` 这种 opaque URI 不加
        #   ⇒ rtsp 渲染结果与改动前**逐字一致**，sip 不会拼出 `sip:<host>:<port>/`。
        _pref = _url_scheme_prefix(bundle)
        if _pref:
            _authority = "<host>:<port>/" if _pref.endswith("//") else ""
            lines.append("  URL 结构:")
            for m, t in sorted(ut.items()):
                lines.append(f"    {m} → {_pref}{_authority}{t}")
    return "\n".join(lines)


def render_seed_prompt(bundle: dict, *, protocol: str,
                       target_state_path: Optional[list[str]] = None,
                       target_methods: Optional[list[str]] = None,
                       target_vuln_class: str = "",
                       n_seeds: int = 20,
                       resources: Optional[list] = None,
                       request_templates: Optional[dict] = None) -> tuple[str, str]:
    """渲染 (system, user) prompt，section 来自分桶知识 + 资源清单 + 真实请求模板。"""
    system = f"你是 {protocol} 协议 fuzz 测试专家，基于给定的协议知识生成合法测试用例。"
    user = f"""[协议方法]
{_render_methods(bundle['methods'])}

[状态机转移]
{_render_transitions(bundle['transitions'])}

[必填字段]
{_render_required(bundle['required_headers'])}

[字段取值池]
{_render_values(bundle['headers'])}

{_render_session_semantics(bundle)}

{_render_constraints(bundle)}

[安全关注（来自历史漏洞）]
{_render_security(bundle['security'])}
"""
    if bundle.get("security"):
        user += f"""
{_render_vuln_guidance(bundle['security'], protocol)}
"""
    if resources:
        user += f"""
[目标资源清单（URL 必须用这些流名，尽量覆盖全部）]
{_render_resources(resources)}
"""
    if request_templates:
        user += f"""
{_render_request_templates(request_templates)}
"""
    user += f"""
[生成目标]
- 协议: {protocol}
- 覆盖状态路径: {target_state_path or ['any']}
- 目标 method: {target_methods or ['any']}
- 漏洞关注: {target_vuln_class or '(无特定目标)'}

[输出要求]
返回一个 JSON 对象（不要用 markdown 代码块包裹），格式（完整会话示例）:
{{"seeds": [
{_output_format_example(protocol)}
]}}
共生成 {n_seeds} 个会话种子，每个是完整有序 message 列表。

硬性规则:
1. method 必须在 [协议方法] 里
2. 状态转移要合法（参考 [状态机转移]）
3. 必填字段不能少（参考 [必填字段]）
4. 取值优先从 [字段取值池] 选，数值字段用边界值(0/-1/MAX/空串/超长)
5. 会话语义严格参照 [会话语义（来自知识中枢）] 区段：前置方法不可省略、会话头按第 N 次出现规则携带、URL 结构按模板
6. 不同种子尽量用不同流名，覆盖尽量多的媒体格式"""
    return system, user


# ===========================================================================
# 4. 生成 + parse
# ===========================================================================

def parse_seed_response(resp: Any, protocol: str,
                        target_state_path: list[str],
                        target_methods: list[str]) -> list:
    """把 LLM 的 JSON 响应解析成 list[SeedCorpus]。"""
    from core.models import SeedCorpus, SeedMessage

    if isinstance(resp, dict) and "seeds" in resp:
        items = resp["seeds"]
    elif isinstance(resp, list):
        items = resp
    elif isinstance(resp, dict):
        items = [resp]
    else:
        return []

    seeds: list = []
    for item in items:
        if not isinstance(item, dict):
            continue
        seed = SeedCorpus(
            protocol=protocol,
            description=str(item.get("description", "")),
            target_state_path=list(item.get("state_path", target_state_path)),
            target_methods=list(item.get("methods", target_methods)),
            generated_by="hub-rag-v2",
            selected_url=str(item.get("url", "")),
        )
        for m in item.get("messages", []):
            if not isinstance(m, dict):
                continue
            seed.messages.append(SeedMessage.from_dict(m))
        if seed.messages:
            seeds.append(seed)
    return seeds


# ===========================================================================
# 5. 轻量校验（用 中枢知识，非 JointConstraint）
# ===========================================================================

def validate_seed(seed, bundle: dict) -> list[str]:
    """用中枢知识做轻量校验：方法白名单 + 必填头 + 状态转移。

    返回 error 字符串列表（空 = 合法）。这是 ReAct 迭代 refine 的判据。
    """
    errs: list[str] = []
    methods = set(bundle["methods"].keys())
    required = bundle["required_headers"]
    transitions = bundle["transitions"]
    trans_by_from: dict = {}
    #: ★ 2026-11-05：**状态改变方法**集合 = 出现在状态机转移里的方法。
    #:   RFC 的状态转移表（A.1/A.2）只列改变状态的方法（RTSP：SETUP / PLAY /
    #:   PAUSE / RECORD / TEARDOWN）；DESCRIBE / OPTIONS / GET_PARAMETER /
    #:   SET_PARAMETER 是**状态无关**方法 —— RTSP 允许在会话进行中随时发。
    #:   ⇒ 状态转移校验**只覆盖状态改变方法**，否则会把含 DESCRIBE/OPTIONS 的
    #:   **合法**种子误判为非法（实测：漏洞导向的合法攻击种子被整条丢弃）。
    state_changing_methods: set = set()
    for src, method, dst in transitions:
        trans_by_from.setdefault(src.upper(), set()).add((method.upper(), dst))
        if method:
            state_changing_methods.add(method.upper())

    current = (seed.target_state_path[0] if seed.target_state_path else "Init")
    for i, m in enumerate(seed.messages):
        method = m.method.upper()
        if method and method not in {x.upper() for x in methods}:
            errs.append(f"msg[{i}] 未知方法 {m.method!r}")
        req = required.get(m.method, []) or required.get(method, [])
        have = {k.upper() for k in m.headers}
        for h in req:
            if h.upper() not in have:
                errs.append(f"msg[{i}] {m.method} 缺必填头 {h!r}")
        # 状态转移校验（有知识才校验；未知状态不强制）
        if method not in state_changing_methods:
            # 状态无关方法（DESCRIBE/OPTIONS/…）⇒ 不做状态转移校验
            continue
        allowed = trans_by_from.get(current.upper(), set())
        if allowed:
            # 同一状态同方法可能有多个出边（如 DESCRIBE 从 Init 可到 Init/Ready）。
            # 优先自环（stateless 方法状态不变），否则取字典序最小目标态 —— 保证确定性，
            # 避免 next() 在 set 上取到不同元素导致校验结果随哈希序抖动。
            cands = sorted(d for mm, d in allowed if mm == method)
            if not cands:
                errs.append(
                    f"msg[{i}] {m.method} 在状态 {current!r} 不合法 "
                    f"(允许 {sorted(allowed)})")
            else:
                nxt = next((d for d in cands if d == current), cands[0])
                if nxt != current:
                    current = nxt
    return errs


# ===========================================================================
# 6. 生成入口
# ===========================================================================

def generate_seeds(bundle: dict, llm, *, protocol: str = "rtsp",
                   target_state_path: Optional[list[str]] = None,
                   target_methods: Optional[list[str]] = None,
                   target_vuln_class: str = "",
                   n_seeds: int = 20,
                   validate: bool = True,
                   resources: Optional[list] = None,
                   request_templates: Optional[dict] = None) -> list:
    """知识中枢 → prompt → LLM → 种子（可选的轻量校验过滤）。"""
    system, user = render_seed_prompt(
        bundle, protocol=protocol,
        target_state_path=target_state_path or [],
        target_methods=target_methods or [],
        target_vuln_class=target_vuln_class, n_seeds=n_seeds,
        resources=resources, request_templates=request_templates)
    try:
        resp = llm.chat_json(system=system, user=user,
                             temperature=0.3, max_tokens=8000)
    except Exception:
        return []
    seeds = parse_seed_response(resp, protocol,
                                target_state_path or [],
                                target_methods or [])
    if validate:
        kept = []
        for s in seeds:
            if not validate_seed(s, bundle):
                kept.append(s)
        return kept
    return seeds


# ===========================================================================
# 第二步（1/3）：结构化 subgraph 检索（GraphRAG）
# ===========================================================================

def retrieve_subgraph(bundle: dict, *,
                      target_methods: Optional[list[str]] = None,
                      target_state_path: Optional[list[str]] = None,
                      k_hops: int = 2) -> dict:
    """从全量 bundle 按目标 method/state 取 k-hop 相关子图（结构化导航，非向量检索）。

    边类型:
      required_headers  method -> header         （必填头）
      transitions       state --method--> state  （状态转移，连 state 与 method）

    从目标 method/state 出发做 BFS：method 边连到必填头 + 转移两端 state；
    state 边连到出发的转移 + 其 method。无目标 → 返回全量 bundle（等价第一步）。
    """
    target_methods = {m.upper() for m in (target_methods or []) if m}
    target_states = {s for s in (target_state_path or []) if s}
    if not target_methods and not target_states:
        return bundle

    related_methods = set(target_methods)
    related_states = set(target_states)
    related_headers: set = set()
    related_transitions: set = set()

    frontier_methods = set(target_methods)
    frontier_states = set(target_states)

    for _ in range(max(1, k_hops)):
        next_methods: set = set()
        next_states: set = set()
        for m in frontier_methods:
            related_headers.update(bundle["required_headers"].get(m, []))
        for src, method, dst in bundle["transitions"]:
            if method in frontier_methods:
                related_transitions.add((src, method, dst))
                next_states.add(src)
                next_states.add(dst)
            if src in frontier_states:
                related_transitions.add((src, method, dst))
                next_methods.add(method)
                next_states.add(dst)
        frontier_methods = next_methods - related_methods
        frontier_states = next_states - related_states
        related_methods |= next_methods
        related_states |= next_states
        if not frontier_methods and not frontier_states:
            break

    return {
        "methods": {m: v for m, v in bundle["methods"].items()
                    if m in related_methods},
        "headers": {h: v for h, v in bundle["headers"].items()
                    if h in related_headers},
        "required_headers": {m: hs for m, hs in bundle["required_headers"].items()
                             if m in related_methods},
        "transitions": sorted(related_transitions),
        "method_sequences": bundle["method_sequences"],
        "security": [s for s in bundle["security"]
                     if s[1] in related_methods or s[1] in related_headers],
        "statuses": bundle["statuses"],
        "protocol": bundle["protocol"],
        "actors": bundle["actors"],
    }


# ===========================================================================
# 第二步（2/3）：ReAct 迭代 refine（Self-RAG / Corrective RAG）
# ===========================================================================

def generate_seeds_react(bundle: dict, llm, *, protocol: str = "rtsp",
                         target_state_path: Optional[list[str]] = None,
                         target_methods: Optional[list[str]] = None,
                         target_vuln_class: str = "",
                         n_seeds: int = 20,
                         max_rounds: int = 3,
                         resources: Optional[list] = None,
                         request_templates: Optional[dict] = None) -> list:
    """生成 → 校验 → 失败带错重生成（ReAct loop）。

    每轮把上一轮校验错误拼进 prompt，让 LLM 修正。max_rounds 兜底防死循环。
    全部通过（或无错误）时提前返回。
    """
    system, user = render_seed_prompt(
        bundle, protocol=protocol,
        target_state_path=target_state_path or [],
        target_methods=target_methods or [],
        target_vuln_class=target_vuln_class, n_seeds=n_seeds,
        resources=resources, request_templates=request_templates)
    seeds: list = []
    last_good: list = []
    for _round in range(max(1, max_rounds)):
        try:
            resp = llm.chat_json(system=system, user=user,
                                 temperature=0.3, max_tokens=8000)
        except Exception:
            break
        parsed = parse_seed_response(resp, protocol,
                                     target_state_path or [],
                                     target_methods or [])
        if not parsed:
            continue  # 解析失败（LLM 输出不可解析），重试下一轮而非误判通过
        seeds = parsed
        bad = {i: validate_seed(s, bundle) for i, s in enumerate(seeds)}
        bad = {i: errs for i, errs in bad.items() if errs}
        if not bad:
            return seeds
        last_good = [s for i, s in enumerate(seeds) if i not in bad]
        feedback = "\n".join(
            f"种子[{i}]: " + "；".join(errs)
            for i, errs in sorted(bad.items()))
        user = user + "\n\n[上一轮校验错误，请严格修正]\n" + feedback
    return last_good or seeds


# ===========================================================================
# 第二步（3/3）：.raw 落盘
# ===========================================================================

def plan_seed_filenames(seeds: list, *, base_count: Optional[int] = None
                         ) -> list[str]:
    """规划 .raw 文件名（与 write_seeds 的命名规则完全一致，供 manifest 复用）。

    ★ 宽度自适应：种子数 > 99 时改用 3 位/4 位，保证「文件名字母序 == 排序下标序」
      （AFL 用 scandir(alphasort) 入队，前缀宽度不一致会破坏字母序↔数值序对应）。
      n ≤ 99 时宽度恒为 2 → 与历史产物逐字节一致（向后兼容）。

    ★★ P2-5：宽度必须由**基准层条数**决定，**不能**由「总条数」决定。
      ⑤（action-seq 变异层）是**纯追加** ⇒ 总条数变大 ⇒ 超过 99 时宽度会从
      2 位变 3 位 ⇒ **基准层的文件名整体从 ``01_`` 变成 ``001_``**
      （实测 smtp/B：ON 态 61 → 131 条）⇒ 内容 md5 不变但**文件名变了**
      ⇒ 任何按文件名索引的历史产物/脚本会失配。
      ⇒ 修法：``base_count`` 给出基准层条数 ⇒ 宽度按它算（基准层文件名与
        OFF 态**逐字节相同**）；⑤ 层用**独立编号空间**（``M`` 前缀，
        宽度取「够放下总条数」的那个）⇒ AFL 的 ``scandir(alphasort)`` 仍是
        「基准层在前、⑤ 层在后」，组内等宽 ⇒ 字母序 == 数值序。

    Args:
        seeds:      待落盘的 SeedCorpus 列表（顺序即落盘顺序）。
        base_count: 基准层（前 N 条）条数；``None`` ⇒ 全部按基准层处理
                    （**向后兼容**：行为与旧实现完全一致）。

    Returns:
        与 seeds 等长的文件名列表。
    """
    n_base = len(seeds) if base_count is None else int(base_count)
    width = 2 if n_base <= 99 else len(str(n_base))
    # ⑤ 层独立编号空间的宽度：必须够放下**总条数**（否则组内字母序 ≠ 数值序）
    mut_width = max(width, len(str(len(seeds))))
    names: list = []
    for i, s in enumerate(seeds, start=1):
        methods = "+".join(s.target_methods) or \
            "+".join(m.method for m in s.messages[:5]) or "seed"
        # 截断超长方法序列：①边覆盖种子方法序列可达 18+ 个，完整拼进文件名会
        # 超过文件系统上限（Linux 单文件名 255 字节），导致 afl-fuzz 落盘时报
        # "File name too long"。截断到 80 字符并加省略号。
        if len(methods) > 80:
            methods = methods[:77] + "..."
        # 文件名带上流名（目标资源），便于识别覆盖了哪个媒体格式
        stream = (s.selected_url or "").rstrip("/").split("/")[-1]
        stream = stream if stream and stream != "track1" else ""
        if base_count is not None and i > base_count:
            prefix = f"M{i:0{mut_width}d}"
        else:
            prefix = f"{i:0{width}d}"
        names.append(f"{prefix}_{stream}_{methods}.raw" if stream
                     else f"{prefix}_{methods}.raw")
    return names


def write_seeds(seeds: list, out_dir, *, url: Optional[str] = None,
                base_count: Optional[int] = None) -> list:
    """把 SeedCorpus 列表落盘成 ProFuzzBench .raw，返回写入的文件名列表。

    ★ ``base_count``：基准层条数（见 :func:`plan_seed_filenames` 的 P2-5 说明）。
    """
    from core.raw_writers import seedcorpus_to_raw
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list = []
    names = plan_seed_filenames(seeds, base_count=base_count)
    for name, s in zip(names, seeds):
        raw = seedcorpus_to_raw(s, url=url) if url else seedcorpus_to_raw(s)
        if not raw:
            continue
        (out / name).write_bytes(raw)
        written.append(name)
    return written
