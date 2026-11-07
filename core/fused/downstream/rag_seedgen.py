"""core/fused/downstream/rag_seedgen.py —— 知识中枢 → RAG → LLM → 种子。

这是 v2 中枢的「LLM RAG 消费通路」（第一步，全量分桶组装）。

定位
----
v2 中枢的 facts（<Subject, Aspect, Condition, Value, Epistemic, Evidence> 知识原子）
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

# ===========================================================================
# 1. 加载五源 facts（view dict）
# ===========================================================================

DEFAULT_FACTS_ROOT = paths.derived_root() / "per_source"


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
        paths.per_source_root(protocol)
    if not root.is_dir():
        return views
    # ★ 新布局优先
    aspect_dir = root / "facts"
    new_files = sorted(aspect_dir.glob("*.jsonl")) if aspect_dir.is_dir() else []
    if new_files:
        return _load_aspect_views(aspect_dir, new_files)
    for jsonl in sorted(root.glob("*/facts/*.jsonl")):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                views.append(json.loads(line))
            except json.JSONDecodeError:
                continue
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
        paths.per_source_root(protocol)
    path = root / "sources.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return doc if isinstance(doc, dict) else {}


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

def _normalize_state(s: str) -> str:
    """状态名归一化：全大写（source 源 INIT/READY）→ 首字母大写（expert_note 源
    Init/Ready），跨源状态机对齐，避免「Init vs INIT」造成状态机分裂。

    只对「全大写」做 title()，已首字母大写的保持原样。
    """
    if not s:
        return s
    return s.title() if s.isupper() else s


def _derive_method_order(method_sequences: list) -> list[str]:
    """从方法相邻对（traffic 观测）拓扑排序推导会话语序（P2b 拓扑序来源）。

    method_sequences: [(from_method, to_method), ...]，如
        [('OPTIONS','DESCRIBE'), ('DESCRIBE','SETUP'), ('SETUP','PLAY'), ...]
    返回拓扑序（越靠前越应优先出现）；环/未覆盖节点按字典序兜底。
    """
    from collections import defaultdict, deque
    nodes: set = set()
    edges: set = set()
    for a, b in method_sequences:
        a, b = str(a).strip().upper(), str(b).strip().upper()
        nodes.add(a)
        nodes.add(b)
        if a != b:  # 自环（如 DESCRIBE 401 重试）不影响顺序
            edges.add((a, b))
    indeg: dict[str, int] = {n: 0 for n in nodes}
    adj: dict[str, set] = defaultdict(set)
    for a, b in edges:
        if b not in adj[a]:
            adj[a].add(b)
            indeg[b] += 1
    queue = deque(sorted(n for n in nodes if indeg[n] == 0))
    order: list[str] = []
    while queue:
        n = queue.popleft()
        order.append(n)
        for m in sorted(adj[n]):
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    # 环兜底：剩余节点字典序追加
    order += sorted(n for n in nodes if n not in order)
    return order


def _load_profile_structure(protocol: str) -> dict:
    """从 profile.json 读客观结构知识（state_changing/required_headers/precondition/
    session_header/url_template），作为 bundle 结构事实的「协议配置」兜底源。

    这些客观结构事实原由 expert_note v2（9 维）承载，v3 改造后 expert_note 只留主观
    判断；客观结构知识迁到 profile.json（不被 build_hub 的 _clean_per_source 清理，
    也避免「会话语义 semantic.jsonl 被清空」的历史缺陷）。
    """
    from core import paths
    import json
    prof = paths.target_profile(protocol)
    if not prof.exists():
        return {}
    try:
        data = json.loads(prof.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return (data.get("seedgen") or {})


def _load_allowed_methods(protocol: str) -> set[str]:
    """从 profile.json 读 allowed_methods（命令白名单，协议实现方法子集）。

    用于过滤 source 源 AutoSeeder LLM 先验产出的垃圾方法名（中文功能词、带空格的
    "AUTH TLS"、非标准命令 CAP/ALIAS 等），保证 methods 桶只含协议真实命令。
    """
    from core import paths
    import json
    prof = paths.target_profile(protocol)
    if not prof.exists():
        return set()
    try:
        data = json.loads(prof.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    allowed = data.get("allowed_methods")
    if isinstance(allowed, list):
        return {str(m).strip().upper() for m in allowed if str(m).strip()}
    return set()


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


def _inject_vuln_self_loops(transitions: list, vuln_patterns: dict,
                            methods: set) -> list:
    """跨源传导（vuln → source）：补全源 source 状态机缺失的「自环」边。

    漏洞知识（vuln 源）揭示「某个方法可在同一状态下连续执行」——如 double_setup
    （同 track 连续两次 SETUP）意味着 SETUP 在 Ready 态有自环。而 source 源
    （AutoSeeder 源码状态机）往往只建模「进入」边（Init --SETUP--> Ready），漏掉
    「重复」边（Ready --SETUP--> Ready）。该缺口此前靠 LLM prompt 补全（不确定），
    正确归宿是：从 vuln_pattern 的 trigger_sequence 中「重复出现的方法」推导其
    目标态自环（X --M--> X），注入状态机——这是「接近但不触发」的合法危险边界。

    通用（协议无关）：只依赖 trigger_sequence 的方法重复性 + 状态机的目标态，
    不硬编码任何协议方法/状态名（如 SETUP/Ready）。方法的目标态取该方法的
    「状态改变」转移 dst（首次执行后进入的状态），保持 _normalize_state 已归一化。
    """
    if not vuln_patterns or not transitions:
        return transitions
    trans_set = set(transitions)
    # 方法 → 其「状态改变」转移的目标态（自环注入点）。transitions 已排序，确定性。
    target_state: dict[str, str] = {}
    for src, m, dst in transitions:
        if src != dst:
            target_state.setdefault(str(m).upper(), dst)
    for _subject, plist in vuln_patterns.items():
        for p in plist:
            if not isinstance(p, dict):
                continue
            seq = [str(m).strip().upper()
                   for m in (p.get("trigger_sequence") or []) if str(m).strip()]
            for m in seq:
                # 只注入「重复出现」的方法（重复 = 可在同一状态连续执行 = 自环）。
                if m not in methods or m not in target_state:
                    continue
                if seq.count(m) >= 2:
                    trans_set.add((target_state[m], m, target_state[m]))
    return sorted(trans_set)


# ===========================================================================
# 2.5 bundle 契约扩展 + 语义规则投影（B-8）
#
# 设计依据：docs/rfc_source_bcd_roadmap.md
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
BUNDLE_SCHEMA_VERSION = "2.0"

#: 旧 bundle（无 `bundle_schema_version` 键）的版本号 —— 读取方按 1.0 容忍。
BUNDLE_SCHEMA_VERSION_LEGACY = "1.0"

#: 响应类（`rfc_config.expected_response_classes` 的规范词表，实测 rtsp/sip/smtp
#: 三协议一致：`success` / `protocol_error` / `application_error` / `silence`）
#: → 状态码族。
#: ★ **词表外一律留空** —— 不臆造状态码（投影不带新信息）。
_EXPECTED_BEHAVIOR_CODES: dict[str, str] = {
    "success": "2xx",
    "protocol_error": "4xx",
    # 应用级错误（RTSP §11 的 4xx 族 / SIP 的 4xx 族，如 404 Not Found）
    "application_error": "4xx",
    # 无响应 ⇒ 无状态码
    "silence": "",
}

#: operator → (合法域模板, 非法域模板)。`{op}` = 操作数的渲染文本。
#: ★ 模板里**不含任何协议特定词** ⇒ 协议无关（rtsp/sip/smtp 通用）。
#: ★ 合法域 = **满足**约束的取值域；非法域 = **违反**约束的取值域。
#:   `absent` ⇒「该字段不得出现」⇒ **出现即非法**（illegal = 存在）。
_OPERATOR_DOMAINS: dict[str, tuple[str, str]] = {
    "le": ("<= {op}", "> {op}"),
    "ge": (">= {op}", "< {op}"),
    "lt": ("< {op}", ">= {op}"),
    "gt": ("> {op}", "<= {op}"),
    "eq": ("= {op}", "!= {op}"),
    "ne": ("!= {op}", "= {op}"),
    "in": ("属于 {op}", "不属于 {op}"),
    "range": ("介于 {op} 之间", "超出 {op} 区间"),
    "present": ("存在（必须出现）", "缺失（不得出现）"),
    "absent": ("缺失（不得出现）", "存在（出现即非法）"),
}

#: 可**确定性推断**处理期望的算子（存在性 / 取值约束）。
#: ★ 推断规则（协议无关）：客户端发出的报文违反「必须存在 / 取值须在域内」的
#:   约束 ⇒ 服务端应拒 ⇒ ``protocol_error``。
#: ★ 只推断 ``protocol_error``，**不推断** ``silence`` / ``application_error``
#:   —— 证据里没有区分这三者的依据，硬分会造出假精度（2026-11-07）。
_INFERABLE_OPERATORS = frozenset({
    "present", "eq", "ne", "in", "range", "ge", "le", "lt", "gt",
})

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
_REJECT_ABSENT_OPERATOR = True


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


def _as_operand_tuple(value: Any) -> tuple[str, ...]:
    """操作数归一为 `tuple[str, ...]`（JSON 形态可能是 list / str / None）。"""
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(v).strip() for v in value if str(v).strip())
    text = str(value).strip()
    return (text,) if text else ()


def _jsonable(value: Any) -> Any:
    """递归把 tuple 转成 list（bundle 要能被 `json.dumps` 落盘）。"""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _rule_to_plain(rule: Any) -> Optional[dict]:
    """把一条语义规则归一为 **bundle 形态**（两层嵌套 dict）。

    接受两种形态（**二选一，不猜**）：

      ① `SemanticRule` 本体 —— 用 `dataclasses.asdict` 展开，
         `evidence` / `constraint` 各成**一层**嵌套 dict（§3.6「两层嵌套」）；
      ② `dict` —— `dataclasses.asdict(SemanticRule)` 的产物，顶层含
         `rule_id` / `evidence` / `constraint` / `subject_type` /
         `subject_name` / `rule_state` / `supersedes` / `model_confidence` /
         `validated`，其中 `constraint` 是**嵌套一层**的 dict。

    ★ `KnowledgeCandidate` **投影不了**（结构上没有 `constraint` / `rule_state`
      字段）⇒ 返回 `None` ⇒ 调用方跳过（不猜、不投影）。
    ★ 无法识别 ⇒ 返回 `None`（调用方跳过）。
    """
    if isinstance(rule, dict):
        return _jsonable(rule)
    constraint = getattr(rule, "constraint", None)
    rule_state = getattr(rule, "rule_state", None)
    if constraint is None and rule_state is None:
        return None
    try:
        from dataclasses import asdict, is_dataclass
    except ImportError:      # pragma: no cover —— dataclasses 是标准库
        return None
    if is_dataclass(rule) and not isinstance(rule, type):
        return _jsonable(asdict(rule))
    # duck-typing 对象（非 dataclass）：逐字段取
    return {
        "rule_id": getattr(rule, "rule_id", "") or "",
        "evidence": _jsonable(getattr(rule, "evidence", None)),
        "constraint": _jsonable(constraint),
        "subject_type": getattr(rule, "subject_type", "") or "",
        "subject_name": getattr(rule, "subject_name", "") or "",
        "rule_state": rule_state or "",
        "supersedes": _jsonable(getattr(rule, "supersedes", ()) or ()),
        "model_confidence": getattr(rule, "model_confidence", None),
        "validated": bool(getattr(rule, "validated", False)),
    }


def _constraint_fields(rule_plain: dict) -> Optional[dict]:
    """取规则的可执行层字段（dict）。

    ★ `constraint is None` ⇒ 返回 `None`（**不投影**）——
      「不可转换」既不是知识候选也不是可执行规则，两桶都不收。
    ★ `constraint` 键**缺失**同样按 None 处理（不可验证的约束不投影）。
    """
    constraint = rule_plain.get("constraint")
    if not isinstance(constraint, dict):
        return None
    return constraint


def _render_operand(operator: str, operand: tuple[str, ...]) -> str:
    """操作数 → 自然语言片段（集合 / 区间 / 单值）。"""
    vals = list(operand)
    if not vals:
        return ""
    if operator == "range":
        if len(vals) >= 2:
            return f"[{vals[0]}, {vals[1]}]"
        return vals[0]
    if operator == "in":
        return "{" + ", ".join(vals) + "}"
    if len(vals) == 1:
        return vals[0]
    return ", ".join(vals)


def _render_domains(operator: str, operand: tuple[str, ...],
                    operand_source: str, operand_ref: Optional[str]) -> tuple[str, str]:
    """(operator, operand) → (合法域自然语言, 非法域自然语言)。

    ★ **反向渲染**（§3.6 选项 c）：operator/operand → 自然语言，供 LLM prompt
      读；**不引入新信息**。
    ★ 字段引用（`operand_source == "field_ref"`）⇒ 操作数不是常量而是另一个
      字段 ⇒ 渲染成「等于/不等于字段 X 的取值」。
    """
    legal_t, illegal_t = _OPERATOR_DOMAINS[operator]
    if operand_source == "field_ref" and operand_ref:
        ref = str(operand_ref).strip()
        if operator == "eq":
            return (f"等于字段 {ref} 的取值",
                    f"不等于字段 {ref} 的取值")
        if operator == "ne":
            return (f"不等于字段 {ref} 的取值",
                    f"等于字段 {ref} 的取值")
        return legal_t.format(op=ref), illegal_t.format(op=ref)
    op_text = _render_operand(operator, operand)
    return legal_t.format(op=op_text), illegal_t.format(op=op_text)


def _resolve_expected_behavior(constraint: dict,
                               operator: str) -> tuple[str, str]:
    """决定**处理期望**（P）的值与来源，返回 ``(expected_behavior, source)``。

    三档来源（**不猜、可审计**）：

      · ``evidence`` —— 规则里本来就有值（抽取期写入）。**注意**：实测已有值的
        9 条里，没有一条的证据原文规定了「违反后返回什么」，它们同样是按协议
        常识推断出来的 ⇒ 论文里只能称「推断」，不能称「规范直出」。
      · ``rule_corrected`` —— 原值与本条约束**语义矛盾**，按确定性规则改。
        唯一判据：`operator` 属存在/取值类（非 ``absent``）却说违反后
        ``success`` ⇒ 不可能（被违反的约束若仍成功，就不成其为约束）。
        实测命中 1 条（``SIP-Version``：原文 "MUST send upper-case"）。
      · ``rule_inferred`` —— 原值为空，按 `_INFERABLE_OPERATORS` 的确定性规则
        推断（客户端违反存在/取值约束 ⇒ 服务端应拒 ⇒ ``protocol_error``）。

    ★ 为什么要分档而不是直接填：把「推断」混进「抽取结果」会让
      `response_expectation` 的条数看起来像抽取能力，属于虚增指标。
      分档后指标可写「evidence 7 / rule_corrected 1 / rule_inferred 12」。
    """
    raw = str(constraint.get("expected_behavior") or "").strip()
    if raw:
        if raw == "success" and operator in _INFERABLE_OPERATORS:
            return "protocol_error", "rule_corrected"
        return raw, "evidence"
    if operator in _INFERABLE_OPERATORS:
        return "protocol_error", "rule_inferred"
    return "", ""


def _project_rule(rule: Any) -> Optional[tuple[str, dict, Optional[dict]]]:
    """投影**一条**规则 → (归组键, legal_boundary 条目, response_expectation 条目)。

    返回 `None` 表示**不投影**，理由只有五类（不猜、不臆造）：

      ① `rule_state != "authoritative"` —— candidate / revoked / feedback
         **不进权威桶**（与 `rule_store` 的四库隔离一致：反馈只影响调度，
         不进权威知识）；
      ② `constraint is None` —— 不可转换（不是知识候选，也不是可执行规则）；
      ③ operator 不在词表内 / 有参算子缺 operand —— **不可渲染**；
      ④ 归组键为空（既无 `target_field` 又无 `subject_name`）—— 无处安放；
      ⑤ `operator == "absent"` —— 语义不可靠会污染 prompt
         （见 `_REJECT_ABSENT_OPERATOR` 的实测依据，2026-11-07 新增）。
    """
    plain = _rule_to_plain(rule)
    if plain is None:
        return None
    # 过滤①：只投影权威规则
    if str(plain.get("rule_state") or "").strip() != "authoritative":
        return None
    # 过滤②：只投影有可执行层的规则
    constraint = _constraint_fields(plain)
    if constraint is None:
        return None
    operator = str(constraint.get("operator") or "").strip()
    if operator not in _OPERATOR_DOMAINS:
        return None
    # 过滤⑤（2026-11-07）：absent 语义不可靠 ⇒ 拒收（见常量处实测依据）
    if _REJECT_ABSENT_OPERATOR and operator == "absent":
        return None
    operand = _as_operand_tuple(constraint.get("operand"))
    if operator not in ("present", "absent") and not operand:
        return None
    operand_source = str(constraint.get("operand_source") or "constant").strip()
    raw_ref = constraint.get("operand_ref")
    operand_ref = str(raw_ref).strip() if raw_ref else None
    # 归组键：目标字段优先，缺省用 subject_name
    target_field = str(constraint.get("target_field") or "").strip()
    subject_name = str(plain.get("subject_name") or "").strip()
    group_key = target_field or subject_name
    if not group_key:
        return None

    legal, illegal = _render_domains(operator, operand, operand_source, operand_ref)
    expected_behavior, eb_source = _resolve_expected_behavior(constraint, operator)
    lb_entry = {
        "dim": group_key,
        "legal": legal,
        "illegal": illegal,
        "trigger": expected_behavior,
        # ★ 2026-11-07：处理期望的**来源**（evidence / rule_corrected /
        #   rule_inferred）⇒ 指标与论文可区分「抽取得来」与「按规则推断」。
        "expected_behavior_source": eb_source,
    }
    # 处理期望仍为空 ⇒ 不产出 response_expectation 条目
    # （与 `norm.constraint_norm_to_facts` 的既有口径一致：缺 P 时只出 C）。
    re_entry: Optional[dict] = None
    if expected_behavior:
        re_entry = {
            "violation": illegal,
            "expected_code": _EXPECTED_BEHAVIOR_CODES.get(expected_behavior, ""),
            "expected_behavior": expected_behavior,
            "expected_behavior_source": eb_source,
        }
    return group_key, lb_entry, re_entry


def _canonical_key(item: Any) -> str:
    """桶内条目的**去重键**（规范化 JSON；非 dict 用 repr 兜底）。"""
    try:
        return json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):       # pragma: no cover —— 理论不可达
        return repr(item)


def _dedup_entries(items: list) -> list:
    """按规范化 JSON 去重（**保留首次出现的位置与顺序** ⇒ 幂等的基础）。"""
    seen: set[str] = set()
    out: list = []
    for item in items:
        key = _canonical_key(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _merge_bucket(existing: Any, incoming: dict) -> dict:
    """把投影条目**追加**到既有桶（同名键合并），并按规范化 JSON 去重。

    ★ **合并语义**：`legal_boundary[field] = 既有 facts 条目 + 投影条目`
      —— 既有条目在前、投影条目在后，各自保持稳定序 ⇒
      · **幂等**：第二次投影产生的条目已在桶中 ⇒ 去重后**逐字节不变**；
      · **旧 facts 来源保留可用**：投影是**新增**来源而非替换 ⇒
        `boundary_probe` / `strategy` 的既有行为**零变化**。
    """
    base: dict = existing if isinstance(existing, dict) else {}
    out: dict[str, list] = {}
    for key in list(base.keys()):
        out[key] = _dedup_entries(list(base.get(key) or []))
    for key in sorted(incoming.keys()):
        merged = list(out.get(key) or []) + list(incoming.get(key) or [])
        out[key] = _dedup_entries(merged)
    return out


def project_semantic_rules(bundle: dict) -> dict:
    """把 `bundle["semantic_rules"]` **投影**进 `legal_boundary` /
    `response_expectation` 两个桶（§3.6 选项 c）。

    ── 输入形态 ──────────────────────────────────────────────────────────
    `bundle["semantic_rules"]` 是一个**列表**，每项为下列两种形态之一：

      ① `SemanticRule` 本体（`core.fused.semantic` 的 frozen dataclass）；
      ② `dict` —— `dataclasses.asdict(SemanticRule)` 的产物
         （顶层 `rule_id` / `evidence` / `constraint` / `subject_type` /
         `subject_name` / `rule_state` / ...，其中 `constraint` **嵌套一层**）。

    ── 投影映射规则 ──────────────────────────────────────────────────────
    对每条规则：

      · **过滤**：只投影 `rule_state == "authoritative"` 且
        `constraint is not None` 的规则（其余一律跳过，见 `_project_rule`）；
      · **归组键**：`constraint.target_field`，缺省用 `subject_name`
        （两者皆空 ⇒ 不投影）；
      · **legal_boundary 条目**：
        `{"dim": 归组键, "legal": 合法域, "illegal": 非法域,
          "trigger": constraint.expected_behavior}`
        —— `legal` / `illegal` 由 operator + operand **反向渲染**：
            le/ge/lt/gt/eq/ne ⇒ 数值比较式及其反面；
            in ⇒ 「属于 {a, b, c}」/「不属于 {a, b, c}」；
            range ⇒ 「介于 [lo, hi] 之间」/「超出 [lo, hi] 区间」；
            present ⇒ 「存在（必须出现）」/「缺失（不得出现）」；
            absent ⇒「缺失（不得出现）」/「存在（出现即非法）」
              （该字段**不得出现** ⇒ 出现即**非法**）。
      · **response_expectation 条目**：
        `{"violation": 非法域, "expected_code": 状态码族,
          "expected_behavior": 处理期望, "expected_behavior_source": 来源}`
        —— 处理期望由 `_resolve_expected_behavior()` 决定：
            有值 ⇒ `evidence`（或语义矛盾时改判 `rule_corrected`）；
            为空且算子属存在/取值类 ⇒ 确定性推断为 `protocol_error`
            （`rule_inferred`）；仍为空 ⇒ **不产出**本桶条目（缺 P 时只出 C）。
        `expected_code` 由响应类经**封闭词表**映射（词表外留空，不臆造）。

    ── 合并语义（幂等的关键）────────────────────────────────────────────
    投影结果**追加**到既有桶（同键合并），并按**规范化 JSON**去重（保留首次
    出现的位置与顺序）⇒ 对同一 bundle 连续调用两次，两桶**逐字节相同**。

    ── 旧 bundle 兼容 ───────────────────────────────────────────────────
    ★ 必须用 `bundle.get("semantic_rules") or []`（**不得** `bundle["semantic_rules"]`
      直接索引）—— 无该键的旧 bundle ⇒ 投影是**空操作**：不报错、不改任何桶。

    Args:
        bundle: bundle dict（**原地修改**）。

    Returns:
        同一个 bundle dict（便于链式调用）。
    """
    if not isinstance(bundle, dict):
        return bundle
    # ★ 旧 bundle 兼容：必须 `bundle.get(...) or []`，不得直接索引。
    rules = bundle.get("semantic_rules") or []
    if not rules:
        return bundle
    projected_lb: dict[str, list] = {}
    projected_re: dict[str, list] = {}
    for rule in rules:
        item = _project_rule(rule)
        if item is None:
            continue
        key, lb_entry, re_entry = item
        projected_lb.setdefault(key, []).append(lb_entry)
        if re_entry is not None:
            projected_re.setdefault(key, []).append(re_entry)
    if not projected_lb and not projected_re:
        # 无可投影内容 ⇒ 两桶**一个字节都不动**（保持空操作语义）。
        return bundle
    # 确定性排序：投影条目与 `semantic_rules` 的**输入顺序无关**。
    projected_lb = {k: sorted(v, key=_canonical_key)
                    for k, v in projected_lb.items()}
    projected_re = {k: sorted(v, key=_canonical_key)
                    for k, v in projected_re.items()}
    bundle["legal_boundary"] = _merge_bucket(
        bundle.get("legal_boundary"), projected_lb)
    bundle["response_expectation"] = _merge_bucket(
        bundle.get("response_expectation"), projected_re)
    return bundle


def load_semantic_rules(protocol: str = "rtsp") -> list[dict]:
    """读 **authoritative** 规则库 → bundle 形态（两层嵌套 dict）列表。

    ★ 走 `core.fused.downstream.rule_store` 的**四库隔离**：只读 `rules.jsonl`
      （candidate / revoked / feedback 三库**根本不在路径上**）⇒ 天然只投影
      权威规则，与 `project_semantic_rules` 的 `rule_state` 过滤**同口径**。
    ★ 库文件不存在 ⇒ 返回空列表（B 阶段前语义库尚未落地，**不是错误**）。
    """
    from .rule_store import library_path, load_rules
    path = library_path(protocol, "authoritative")
    if not path.is_file():
        return []
    out: list[dict] = []
    for rule in load_rules(path):
        plain = _rule_to_plain(rule)
        if plain is not None:
            out.append(plain)
    return out


def _resolve_semantic_rules(semantic_rules: Optional[list],
                            protocol: str) -> list[dict]:
    """决定 bundle 里的 `semantic_rules` 内容：显式传入优先，否则读权威库。"""
    if semantic_rules is None:
        semantic_rules = load_semantic_rules(protocol)
    out: list[dict] = []
    for rule in semantic_rules or []:
        plain = _rule_to_plain(rule)
        if plain is not None:
            out.append(plain)
    return out


#: ★ 批次 1.6 步 2：协议骨架在中枢里的 authority（骨架**不是**抽取源，
#:   而是跨实验复用的协议结构 ⇒ 组装期过滤时**恒允许**）。
SKELETON_AUTHORITY = "profile"

#: ★ 2026-11-05：**规范原生**状态机的 authority（直接抽自 RFC 文本）。
#:   ★ 已知：骨架的 ``target_state`` 实为 **source 源**派生（``skeleton.json``
#:     的 ``origin.source`` 含 ``target_state``）—— 追查出的思想源头是
#:     ``source_autoseeder.py`` 提示词里硬塞的 **SIP 式状态名范例**
#:     ⇒ 骨架的状态名**不一定**属于该协议的规范。
RFC_AUTHORITY = "rfc"

#: ★ P2-1（2026-11-06）：``required_headers`` 桶里表示「**所有方法**都要带」的键。
#:   RFC 源的 ``required_header_global`` 事实（rtsp→CSeq；sip→To/From/CSeq/
#:   Call-ID/Max-Forwards/Via）语义就是**消息级**必填头 ⇒ 收在这个键下，
#:   由 :func:`required_headers_for` 与方法级清单合并。
#:   ⚠ 用 ``"*"`` 而不是给每个方法复制一份：方法集是可变的（RFC/骨架/白名单都
#:     能改），复制会在「新增方法」时漏同步；单一真相 + 读取时合并更稳。
_GLOBAL_REQUIRED_KEY = "*"


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
_BUCKET_BY_KIND: dict[tuple[str, str], str] = {
    # ── method 主体 ──
    ("method", "state_changing"): "methods",
    ("method", "definition"): "methods",
    ("method", "existence"): "methods",
    ("method", "relation_to_other"): "required_headers",
    # ★ 批次 1.6 步 4：`required_headers` **物化进中枢**后的 aspect
    #   （由 profile.json 的必填头清单物化而来，authority=profile）
    ("method", "required_headers"): "required_headers",
    # ★ P2-1（2026-11-06）：RFC 源的**消息级**必填头（aspect 名就带 global）
    #   ⇒ 用 `"*"` 键并入同一个桶，表示「**所有方法**都要带」。
    #   修复前该 aspect **不在本表** ⇒ 抽出来的事实直接丢弃
    #   （实测 rtsp 1 条 / sip 6 条被丢），是条**死通道**。
    ("header", "required_header_global"): "required_headers",
    ("method", "security_property"): "security",
    ("method", "precondition"): "precondition",
    ("method", "session_header"): "session_header",
    ("method", "url_template"): "url_template",
    ("method", "legal_boundary"): "legal_boundary",
    ("method", "vuln_pattern"): "vuln_pattern",
    # ── header 主体 ──
    ("header", "syntax"): "headers",
    ("header", "definition"): "headers",
    ("header", "value_enum"): "headers",
    ("header", "occurrence"): "headers",
    ("header", "security_property"): "security",
    ("header", "legal_boundary"): "legal_boundary",
    ("header", "response_expectation"): "response_expectation",
    ("header", "vuln_pattern"): "vuln_pattern",
    # ── relation 主体 ──
    ("relation", "target_state"): "transitions",
    ("relation", "method_sequence"): "method_sequences",
    ("relation", "message_instance"): "message_instances",
    # ── status 主体 ──
    # ★ 2026-11-07：`("status", "occurrence")` **有意不映射**（不进任何桶）。
    #   实测中枢里有 13 条该组合的 fact（rtsp 2 / sip 5 / smtp 6），值是
    #   「状态码在 RFC 原文里出现几次」（如 200 → 5）。它不指导报文构造，
    #   下游无消费者 ⇒ 进 bundle 只会增加体积与误读风险。
    #   ⇒ 保持「白名单式映射」语义：没列进本表 = 有意不投影。
    ("status", "definition"): "statuses",
    # ★ `("status", "occurrence")` **刻意不在此表**：`assemble_bundle` 只处理
    #   `status` + `definition` ⇒ status/occurrence 事实**不进任何桶**
    #   （既有行为；真实骨架里实测有 13 条这样的事实 ⇒ 被丢弃）。
    #   本步**不改**这个行为（改了会动 bundle 内容 ⇒ 种子漂移）⇒ 只如实记录。
    # ── protocol / actor 主体 ──
    ("protocol", "value_enum"): "protocol",
    ("actor", "value_enum"): "actors",
}

#: ★ 批次 1.6 步 3：这些桶有 **profile.json 兜底**来源（facts 再叠加/覆盖）
#:   ⇒ 报告里「facts 派生」与「profile 兜底」**分列**，不混说。
_PROFILE_FALLBACK_BUCKETS: tuple[str, ...] = (
    "required_headers", "precondition", "session_header", "url_template",
)


def _dedupe_sorted(values: list) -> list:
    """去重 + 排序（**兼容不可哈希的值**）。

    ★ 为什么需要：中枢里多个桶的值是 **dict**（安全属性 / 前置方法 / URL 模板
      等结构化描述）⇒ 原来的 ``sorted(set(v))`` 会抛
      ``TypeError: unhashable type: 'dict'``。
      ⚠ 这是**首次入库即存在的历史缺陷**：当前单源态没有这些 aspect 的事实
        ⇒ 触发不到；一旦引入 vuln / expert_note 源就会崩。
    ★ 兼容策略：**值可哈希时走原路径**（``sorted(set(...))`` ⇒ 逐字节不变）；
      仅在会崩时改用「稳定 JSON 键」去重 + 排序。
    """
    try:
        return sorted(set(values))
    except TypeError:
        seen: set = set()
        kept: list = []
        for item in values:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True,
                             default=str)
            if key in seen:
                continue
            seen.add(key)
            kept.append(item)
        return sorted(kept, key=lambda t: json.dumps(t, ensure_ascii=False,
                                                     sort_keys=True,
                                                     default=str))


def _select_active_transitions(by_source: dict[str, list]) -> list:
    """从「各源的状态机」里选出**当前采用**的一套。

    ★★ 2026-11-05 修正（依据：``local/状态机消费口径对照实验报告.md``）：
      旧实现是「**骨架优先**」⇒ RTSP 采用协议骨架那 38 条边，而它的 6 个状态名
      （Idle/Registered/Confirmed/Invited/Paused/Terminated）在 RFC 2326 原文中
      **0/6 命中** —— 那是 ``source_autoseeder`` 提示词里硬塞的 **SIP 式范例**
      （``core/fused/source_autoseeder.py:182,203``）⇒ 双重危害：
        ① **污染 prompt**：LLM 照抄这些状态名生成种子；
        ② **校验器失效**：状态名对不上 ⇒ ``validate_seed`` 的 ``trans_by_from``
           取不到 from 态 ⇒「有知识才校验」分支**永不触发** ⇒ 状态机对 RTSP
           而言是**死知识**。
      实测（4 组 × 3 次 LLM + 外部真值 = RFC A.1+A.2 共 14 条边）：

        | 组                    | kept | 精确率 | 召回率 |
        | 现状(骨架 38)         |16.33 |  0.0%  |  0.0%  |
        | RFC 原生(14, 不裁)    |10.67 | 100.0%  | 93.3%  |
        | RFC 原生(14, 裁后12)  | 7.67 | 100.0%  | 98.3%  |
        | 两套合并(52)          | 2.00 |  0.0%  |  0.0%  |

      ⇒ **规范原生优先**，且**绝不合并两套**（合并 ⇒ LLM 在两套状态名间摇摆
        ⇒ 精确率/召回率双 0 ⇒ 是灾难）。

    ★ 规则（**协议无关**，靠 authority 优先级自动适配）：
      ① 有**规范原生**（authority=rfc = 直接抽自 RFC 文本）的那套 ⇒ 用它；
      ② 否则用**协议骨架**（authority=profile）；
      ③ 都没有 ⇒ 全部去重合并（兜底）。
      ⇒ 只有真正开了 ``enable_transitions`` **且** RFC 源确实抽到状态机的协议
        才会走第 ① 步（当前仅 rtsp）；其余协议（sip/smtp 尚无 RFC 源状态机）
        行为**逐字节不变**。

    ★ 连带影响（已实测，``edge_cover`` 纯确定性、零 LLM 成本）：
      rtsp 的 ``edge_cover`` 种子 5 → 3 条。看似变少，但**多出来的那 2 条状态
      路径含 Idle/Registered/… ⇒ 真实 RTSP 服务器根本没有这些状态 ⇒ 那 2 条
      种子在协议层面**不可实现** ⇒ 净收益为正。
      ``message_instances`` 的键含状态名 ⇒ 切到 RFC 后骨架那套实例查不到
      （字段实例退化；``RECORD`` 无实例 ⇒ 该边消息无字段，**已知缺陷**，
      全源模式下因 ``allowed_methods`` 不含 RECORD 会自动裁掉该边）。
    """
    for _auth in (RFC_AUTHORITY, SKELETON_AUTHORITY):
        _chosen = by_source.get(_auth) or []
        if _chosen:
            return sorted(set(_chosen))
    return sorted({t for rows in by_source.values() for t in rows})


def _align_message_instances(transitions: list, message_instances: dict,
                             *, allow_migrate: bool,
                             provenance: Optional[dict] = None,
                             instance_authority: Optional[dict] = None) -> dict:
    """把字段级实例对齐到**当前采用**的状态机转移上。

    ★ 为什么要对齐：``message_instances`` 的键是 ``(from, method, to)`` 三元组，
      其中 from/to 是**状态名** ⇒ 一旦状态机换了来源（RTSP 从骨架那套
      SIP 式状态名换成 RFC 原生那套），旧实例的键就再也命中不了
      ⇒ ``edge_cover`` 取不到字段模板 ⇒ 消息只能退回「必填头 + 中枢 headers
      取值池首值（池空则空串）」⇒ **同一字段在所有方法上取值相同**，且丢掉
      方法特有的字段组合（实测 rtsp 修复后 SETUP 才带上 Session、PLAY 才带上
      ``Range: npt=0.000-``、url 才有值）⇒ 字段级知识**静默失效**。
      ⇒ 必须让实例与采用的那套转移**同源**（不变量：实例键 ⊆ 转移键）。

    ★ 对齐规则：
      ① 原样命中的实例（键恰是采用的转移）⇒ **保留**；
      ② 未命中但**方法相同**的实例 ⇒ 按 method 迁移一份模板到该转移
         （字段取值本身是协议级合法值，与状态名无关 ⇒ 可迁移）；
      ③ 迁移后仍无实例的转移 ⇒ 留空（下游回退必填头 + 默认值）。

    ★ ``allow_migrate``（2026-11-06 修正：与 ``apply_allowed_methods`` **解耦**）：
      - True（默认）⇒ 执行 ②；
      - False ⇒ **只保留命中的**、未命中的剔除（纯净度极限模式，
        字段回退必填头 + 默认值）。

      ★ 为什么要解耦（实测 bug）：原实现写的是
        ``allow_migrate=apply_allowed_methods`` —— 把「**是否裁剪方法**」和
        「**是否搬迁字段实例**」两个**正交**语义绑在同一个旗标上。后果是
        **信息最多的模式拿到的字段知识最少**：
          · 默认路径（全源、不裁剪方法）⇒ ``allow_migrate=False``
            ⇒ 骨架实例键 ``Idle--SETUP-->Ready`` 与采用的转移
            ``Init--SETUP-->Ready`` 精确命中 **0** 条、又不许迁移
            ⇒ rtsp 的 ``message_instances`` **恒为 0**；
          · 严格单源（会裁剪方法）⇒ ``allow_migrate=True`` ⇒ 反而迁移出 12 条。
        实测（三协议 × 两模式）只有 rtsp 坏，且只在默认路径坏。

    ★ ``provenance``（出参，可选）：迁移出来的实例，字段值来自**另一个来源**
      的模板（通常是协议骨架 ``profile``）⇒ **必须标注**，否则外面会把骨架值
      当成本源的原生知识（在论文里就是「骨架值冒充 RFC」）。
      形如 ``{key: {"authority": 原模板来源, "origin": "exact"|"migrated",
                    "migrated_from": 原键或 None}}``；
      ``instance_authority``（入参）给 ``{key: authority}`` 用于回填原模板来源。
    """
    def _mark(key, auth_key, origin, migrated_from):
        if provenance is None:
            return
        provenance[key] = {
            "authority": (instance_authority or {}).get(auth_key, ""),
            "origin": origin,
            "migrated_from": migrated_from,
        }

    if not message_instances:
        return {}
    if not transitions:
        # ★ 没有状态机转移可对齐 ⇒ **原样保留**。
        #   否则「单独组装一条 message_instance 事实」时（transitions 桶为空）
        #   会被清空 ⇒ 破坏「每个 fact 组合只落到它该落的桶」的不变量
        #   （tests/fused/test_bundle_provenance.py::test_each_kind_lands_only_in_its_bucket）。
        for key in sorted(message_instances):
            _mark(key, key, "exact", None)
        return dict(message_instances)
    trans_set = {(str(s), str(m).strip().upper(), str(d))
                 for s, m, d in transitions}
    # 按 method 建模板索引（确定性：同方法多个实例取字典序最小键）
    by_method: dict[str, list] = {}
    for key in sorted(message_instances):
        by_method.setdefault(str(key[1]).strip().upper(), []).append(key)
    out: dict = {}
    for key in sorted(message_instances):
        k = (str(key[0]), str(key[1]).strip().upper(), str(key[2]))
        if k in trans_set:
            out[k] = message_instances[key]
            _mark(k, key, "exact", None)
    if allow_migrate:
        for k in sorted(trans_set):
            if k in out:
                continue
            cands = by_method.get(k[1]) or []
            if not cands:
                continue
            src_key = cands[0]
            out[k] = message_instances[src_key]
            _mark(k, src_key, "migrated", src_key)
    return out


def assemble_bundle(views: list[dict], protocol: str = "rtsp",
                    *, semantic_rules: Optional[list] = None,
                    source_set: Optional[Iterable[str]] = None,
                    apply_allowed_methods: bool = True,
                    include_skeleton_methods: bool = True,
                    allow_instance_migrate: bool = True) -> dict:
    """把 fact views 按 aspect 分桶成「种子生成知识」。

    产出:
      methods          method_name -> {state_changing, definition, existence,
                                       declared_by, observed_by}
      headers          header_name -> {syntax, values, occurrence, source_values}
      required_headers method_name -> [header_name]
      transitions      [(from_state, method, to_state)]  (state --method--> state)
      method_sequences [(from_method, to_method)]          (方法序列, traffic 观测)
      security         [(subject_type, subject_name, desc)]
      statuses         code -> definition
      protocol         protocol_name -> [values]
      actors           actor_name -> [ports]
      precondition     method_name -> [prerequisite_method, ...]  (会话语义：前置方法)
      session_header   method_name -> [{header, from_occurrence}, ...]  (会话语义：会话头)
      url_template     method_name -> pattern  (会话语义：URL 结构)
      available_sources 本次参与的事实来源集合（五源分工传导，P0）
      semantic_rules   [两层嵌套的语义规则 dict, ...]  (B-8：两层模型，**不进 facts.jsonl**)

    ★★ 批次 1.6 步 3：**溯源保留**（**只加顶层新键** ⇒ 既有桶结构逐字节不变
      ⇒ prompt 渲染不变 ⇒ 种子产物逐字节不变）：
      message_instance_provenance  {(from,m,to): {authority, origin, migrated_from}}
                       ⇒ 迁移来的字段模板**标明出处**（不冒充本源知识）
      by_source        桶级统计 {桶名: {源名: 事实条数}}
      bucket_fact_ids  桶 → 事实 id（有序）⇒ 桶里每条都能回指
      fact_index       事实 id → {authority, aspect, subject, bucket}（双向可追）
      bucket_origin    {桶名: {facts: bool, profile: bool}}
                       ⇒ 「facts 派生」与「profile 兜底」**分列**，不混说
      bundle_schema_version "2.0"  (B-8：bundle 契约版本；旧 bundle 无此键，读取方须容忍)

    ★ B-8（§3.6 选项 c）：`legal_boundary` / `response_expectation` 两桶在返回前
      由 `semantic_rules` **投影**填充（追加 + 去重 ⇒ 幂等）；既有 facts 来源
      **保留可用** ⇒ `boundary_probe` / `strategy` 零改动仍工作。

    ★★ D-6（可关闭的开关位，默认关闭 —— 见 `core/fused/llm_ensemble.py`）：

      「开关关闭」的准确语义是 **「不自动引入语义规则」** —— 关闭时本函数
      **不主动去读规则库**，消费路径（`load_semantic_rules` +
      `project_semantic_rules`）**0 次调用**，产物**不含** `semantic_rules` /
      `bundle_schema_version` 两个新键 ⇒ **与 B-8 之前的 bundle 逐字节一致**
      （默认路径不得被 B-8 悄悄改变）。

      而**显式传入** `semantic_rules=` 是**调用方的显式授权**（程序化 API
      层面的直接输入），**优先于开关**，照常投影 —— **不得**静默丢弃显式
      传入的规则（否则 B-8 已落库的契约会被破坏）。

      行为矩阵（开关 × 是否显式传参）：

      | 开关 | 显式传参 | `semantic_rules` 键 | `bundle_schema_version` 键 |
          | 调 `load_semantic_rules` | 投影两桶 |
      |------|----------|----------------------|--------------------------|
      | OFF  | 否       | **不存在**            | **不存在**               |
      |      |          | **不调用**            | **不投影**               |
      | OFF  | 是       | 存在（用传入值）      | 存在                     |
      |      |          | 不调用                | 投影                     |
      | ON   | 否       | 存在（自动装载）      | 存在                     |
      |      |          | 调用                  | 投影                     |
      | ON   | 是       | 存在（用传入值）      | 存在                     |
      |      |          | 不调用                | 投影                     |

      ★ 开关状态**每次调用时**判定（环境变量 + 进程内覆盖，见
        `llm_ensemble.semantic_rules_enabled()`），不在 import 时缓存。

    Args:
        views: fact view 列表（`load_fact_views()` 的产物）。
        protocol: 协议名；facts 里带 protocol 时以 facts 为准。
        semantic_rules: 显式给定语义规则（bundle 形态 dict 或 `SemanticRule`）；
            **缺省（None）= 未显式传参** ⇒ 听开关（OFF ⇒ 完全不引入；ON ⇒ 从
            **authoritative 规则库**读，`rule_store.load_rules`）；显式给定
            （含空列表）⇒ 调用方显式授权 ⇒ 照常装载 + 投影，不读规则库。
        source_set: ★ 批次 1.6 步 2 —— **本次参与的知识源集合**（来自中枢的
            ``sources.json``）。给定 ⇒ 组装期**按 claim 的 authority 过滤**：
            非集合内的 claim **直接不进桶**（不是「进去再标记」）。
            **缺省（None）= 不过滤** ⇒ 与本参数引入前**逐字节一致**。
            ★ 协议骨架（authority = ``profile``）**恒允许** —— 它是跨实验复用的
              协议结构（状态机 / 消息实例 / 方法存在性 / 头取值），
              **不是**某次抽取的源派生知识 ⇒ 单源调试时链路不断。
        apply_allowed_methods: 是否用 ``profile.allowed_methods``（源码侧命令白名单）
            对方法集做**裁剪**。缺省 True（与历史行为一致）。
        include_skeleton_methods: ★ P0-1 —— 是否允许骨架（authority = ``profile``）的
            ``existence`` 事实**新建** ``methods`` 桶条目（**并入**）。
            缺省 True（与历史行为逐字节一致）。

            ⚠ 为什么需要它：``apply_allowed_methods`` 只管**裁剪**（删掉 RFC 抽到、
              但不在源码白名单里的方法），**管不到并入** —— 骨架的 ``existence``
              事实经 ``_BUCKET_BY_KIND[("method","existence")]`` 直接落到 ``methods``
              ⇒ 会**注入**该 RFC 文档未定义的方法。实测：sip 被注入
              ``INFO``（RFC 2976）/ ``SUBSCRIBE``（RFC 3265），smtp 被注入
              ``AUTH``（RFC 4954）—— 都不在本次入库的那份 RFC 里。

            严格单源实验（``--sources rfc``）应传 False ⇒ 方法集只由 RFC 事实定义
            （实测 sip 8→6、smtp 11→10、rtsp 11→11 不变，因 rtsp 的骨架方法集
            本来就是 RFC 方法集的子集）。
            ★ 只挡**新建**条目：某方法若已有 RFC 侧的 ``definition`` 事实，
              骨架的 ``existence`` 仍会补 ``observed_by`` 等溯源字段（不丢知识）。

    五源分工传导（P0）：分桶时保留 provenance——
      - methods[*].declared_by：哪些源「声明」了该方法（definition/state_changing 等）
      - methods[*].observed_by：哪些源「实测观测到」该方法（existence + observed）
      - headers[*].source_values：各源各自给的字段取值（value_enum）
      - available_sources：所有出现过的 authority 集合（供降级决策）
    """
    methods: dict[str, dict] = {}
    headers: dict[str, dict] = {}
    # 客观结构知识：先从 profile.json 兜底（expert_note v3 后迁入），facts 再叠加/覆盖。
    # protocol 优先从 facts 的 fact_key.protocol 推导（避免 assemble_bundle(load_fact_views(p))
    # 丢协议后误读默认 rtsp 的 profile），无 facts 时回退显式 protocol 参数。
    for _v in views:
        _p = ((_v.get("fact_key") or {}).get("protocol"))
        if _p:
            protocol = _p
            break
    _struct = _load_profile_structure(protocol)
    _protocol_name = protocol  # 保存协议名（下方 protocol 变量被 protocol 桶 dict 覆盖）
    # ★ 批次 1.6 步 4：`required_headers` **物化进中枢** ⇒ 组装端**不再直读**
    #   profile.json 的这份知识。
    #   · 中枢里有物化事实（aspect=required_headers）⇒ **完全用 facts**；
    #   · 没有（兼容期：中枢未重建）⇒ 回退读 profile.json（不破链）。
    required_headers: dict[str, list] = {}
    _has_required_facts = False
    transitions: list = []
    # ★ 批次 2.1（P1）：每条转移的来源（用于「源派生优先、骨架兜底」规则）
    _transitions_auth: list = []
    method_sequences: list = []
    security: list = []
    statuses: dict[str, str] = {}
    protocol: dict[str, list] = {}
    actors: dict[str, list] = {}
    # ★★ 批次 2.5（F3）：**会话语义三段不再直读 profile.json** ⇒ 改为
    #   **只从中枢 facts 来**（三个 aspect 在 facts 分发里已有分支）
    #   ⇒ 走 claim 级 authority 过滤 ⇒ **RFC 单源实验里这三段自动为空**
    #   （专家知识不再混入）。它们由 ``build_hub`` 在**构建 expert_note 源时**
    #   物化进中枢（authority=expert_note）⇒「知识产出与谁构建它绑定」。
    preconditions: dict[str, list] = {}
    session_headers: dict[str, list] = {}
    url_templates: dict[str, str] = {}
    # ★ 批次 2.5（F3）：``state_changing`` 也**不再直读 profile**
    #   ⇒ 改为**从 facts 的 target_state 推导**（出现在具体状态转移里的方法
    #   ⇒ 规范知识）⇒ 随源集合自然变化，不再是专家知识旁路。
    _state_changing_from_facts: set[str] = set()
    legal_boundaries: dict[str, list] = {}
    response_expectations: dict[str, list] = {}  # 处理期望（SemFuzz 的 P）
    vuln_patterns: dict[str, list] = {}  # 漏洞模式（GLMFuzz 式，vuln 源）
    message_instances: dict = {}  # {(from, method, to): [(field, value), ...]}
    _mi_auth: dict = {}  # {(from, method, to): 模板来源 authority}
    available_sources: set = set()  # P0：参与的事实来源

    # ★ 批次 1.6 步 3：**溯源保留**（只加字段、不改旧字段 ⇒ 旧消费者零影响）
    #   by_source       桶级统计：{桶名: {源名: 事实条数}}
    #   bucket_fact_ids 桶 → 事实 id 的有序列表（桶里每条都能回指）
    #   fact_index      事实 id → {authority, aspect, subject, bucket}（双向可追）
    by_source: dict[str, dict[str, int]] = {}
    bucket_fact_ids: dict[str, list[str]] = {}
    fact_index: dict[str, dict] = {}

    # ★ 批次 1.6 步 2：**组装期源过滤**（双保险）。
    #   批次级「清空整个中枢」已保证中枢里只有本次的源；这里再加一道 ——
    #   「非本次源集合的 claim **根本不进桶**」（不是「进去再标记」）。
    #   source_set 缺省（None）⇒ **不过滤** ⇒ 与本参数引入前逐字节一致。
    _allowed: Optional[set] = None
    if source_set is not None:
        _allowed = {str(s).strip().lower() for s in source_set
                    if str(s).strip()}
        # ★ 协议骨架恒允许（跨实验复用的协议结构，不是源派生知识）
        _allowed.add(SKELETON_AUTHORITY)

    for v in views:
        fk = v.get("fact_key") or {}
        subj = fk.get("subject") or {}
        stype = subj.get("type", "")
        sname = subj.get("name", "")
        aspect = fk.get("aspect", "")
        claims = v.get("all_claims") or []
        if _allowed is not None:
            # ★ claim 级裁剪：不属于本次源集合的 claim **直接剔除**
            claims = [c for c in claims
                      if str(c.get("authority") or "").strip().lower() in _allowed]
            if not claims:
                continue
        # ★★ P0-1：严格单源（`include_skeleton_methods=False`）下，
        #   骨架（profile）的 method `existence` 事实**不得新建 `methods` 桶条目**。
        #   为什么必须挡在**这里**（by_source 登记之前）：
        #     · `apply_allowed_methods` 只做**裁剪**（删 RFC 有、白名单没有的），
        #       做不了**并入**；而 `("method","existence") → "methods"` 的映射
        #       会让骨架事实直接**注入** RFC 文档里没有的方法；
        #     · 因此必须在「进桶」之前拦，否则 `by_source` 台账会把「未采用」的
        #       事实记成「已采用」⇒ 溯源失真。
        #   只挡「新建」：已有条目（RFC 侧 `definition` 建过）仍允许补 `observed_by`。
        if (not include_skeleton_methods
                and stype == "method" and aspect == "existence"
                and sname not in methods
                and all(str(c.get("authority") or "").strip().lower()
                        == SKELETON_AUTHORITY for c in claims)):
            continue
        val = None
        main_auth = ""    # P0：主 claim 的来源
        main_epi = ""     # P0：主 claim 的认识论类型
        if claims:
            cv = claims[0].get("value") or {}
            val = cv.get("data")
            main_auth = claims[0].get("authority", "") or ""
            main_epi = claims[0].get("epistemic_type", "") or ""
            for c in claims:  # P0：收集所有参与来源
                a = c.get("authority", "")
                if a:
                    available_sources.add(a)

        # ★ 批次 1.6 步 3：登记这条事实的**桶归属**与**来源**（溯源）
        _bucket = _BUCKET_BY_KIND.get((stype, aspect))
        if _bucket:
            _src = main_auth or "(unknown)"
            _cnt = by_source.setdefault(_bucket, {})
            _cnt[_src] = _cnt.get(_src, 0) + 1
            _fid = ""
            for c in claims:
                if c.get("fact_id"):
                    _fid = str(c["fact_id"])
                    break
            if _fid:
                bucket_fact_ids.setdefault(_bucket, []).append(_fid)
                fact_index.setdefault(_fid, {
                    "authority": main_auth,
                    "aspect": aspect,
                    "subject_type": stype,
                    "subject_name": sname,
                    "bucket": _bucket,
                })

        if stype == "method" and aspect == "required_headers":
            # ★ 批次 1.6 步 4：物化进来的必填头清单。
            #   ★ **必须走独立分支**：若落到下面的 `methods.setdefault(sname, {})`
            #     ⇒ 会给 `methods` 桶**新增空条目** ⇒ methods 键集变化 ⇒
            #     prompt 渲染变化 ⇒ 种子漂移。
            _has_required_facts = True
            required_headers.setdefault(sname, []).extend(
                list((val or {}).get("headers") or []))
        elif stype == "header" and aspect == "required_header_global":
            # ★ P2-1：RFC 源的**消息级**必填头（`subject.type=header`，
            #   `subject.name` = 头名）⇒ 收进 `"*"` 键 = 「所有方法都要带」。
            #   与上面方法级分支分开，是因为主体类型不同（header vs method）：
            #   方法级事实的 `subject.name` 是**方法名**，它的头清单在 value 里；
            #   全局事实的 `subject.name` 是**头名**，value 也是头名（冗余自证）。
            _has_required_facts = True
            if sname:
                required_headers.setdefault(_GLOBAL_REQUIRED_KEY, []).append(sname)
        elif stype == "method":
            info = methods.setdefault(sname, {})
            if aspect == "state_changing":
                # P2a：累积所有 claim，遍历后统一用 resolver precedence 消解
                #（避免「后遍历覆盖先遍历」的隐性顺序依赖，observed/normative 优先级高）
                info.setdefault("_pending_state_changing", []).extend(
                    {"value": (c.get("value") or {}),
                     "epistemic_type": c.get("epistemic_type", ""),
                     "authority": c.get("authority", ""),
                     "claim_id": c.get("claim_id", "")}
                    for c in claims)
                if main_auth:
                    info.setdefault("declared_by", set()).add(main_auth)
            elif aspect == "definition":
                info["definition"] = val
                if main_auth:
                    info.setdefault("declared_by", set()).add(main_auth)
            elif aspect == "existence":
                info.setdefault("_pending_existence", []).extend(
                    {"value": (c.get("value") or {}),
                     "epistemic_type": c.get("epistemic_type", ""),
                     "authority": c.get("authority", ""),
                     "claim_id": c.get("claim_id", "")}
                    for c in claims)
                if main_epi == "observed" and main_auth:
                    info.setdefault("observed_by", set()).add(main_auth)
            elif aspect == "relation_to_other":
                tgt = (val or {}).get("target", {}) if isinstance(val, dict) else None
                tgt_name = tgt.get("name") if isinstance(tgt, dict) else None
                if tgt_name:
                    required_headers.setdefault(sname, []).append(tgt_name)
            elif aspect == "security_property":
                security.append(("method", sname, val))
            elif aspect == "precondition":
                preconditions.setdefault(sname, []).append(val)
            elif aspect == "session_header":
                session_headers.setdefault(sname, []).append(val)
            elif aspect == "url_template":
                url_templates[sname] = val
            elif aspect == "legal_boundary":
                legal_boundaries.setdefault(sname, []).append(val)
            elif aspect == "vuln_pattern":
                vuln_patterns.setdefault(sname, []).append(val)
        elif stype == "header":
            if aspect == "syntax":
                headers.setdefault(sname, {})["syntax"] = val
            elif aspect == "definition":
                headers.setdefault(sname, {})["definition"] = val
            elif aspect == "value_enum":
                info = headers.setdefault(sname, {})
                # P2a：取值池做 union（多源互补不冲突，并集合并而非覆盖）
                existing = set(info.get("values") or [])
                existing.update(list(val or []))
                info["values"] = sorted(existing)
                if main_auth:  # P0：各源取值
                    info.setdefault("source_values", {}).setdefault(
                        main_auth, set()).update(list(val or []))
            elif aspect == "occurrence":
                headers.setdefault(sname, {})["occurrence"] = val
            elif aspect == "security_property":
                security.append(("header", sname, val))
            elif aspect == "legal_boundary":
                legal_boundaries.setdefault(sname, []).append(val)
            elif aspect == "response_expectation":
                response_expectations.setdefault(sname, []).append(val)
            elif aspect == "vuln_pattern":
                vuln_patterns.setdefault(sname, []).append(val)
        elif stype == "relation":
            quals = subj.get("qualifiers", {}) or {}
            src = (quals.get("source") or {}).get("name", "")
            dst = (quals.get("target") or {}).get("name", "")
            method = (quals.get("method") or {}).get("name", "").strip().upper()
            if aspect == "target_state":
                # 状态机边（state --method--> state，rfc/source 源产出）：
                # 只保留具体转移（from/to 均为具体 state），丢弃 wildcard
                #（from="*" / to="$current" 的 stateless 语义已由具体转移覆盖）
                # 状态名归一化：跨源（Init vs INIT）对齐
                src = _normalize_state(src)
                dst = _normalize_state(dst)
                if src and src != "*" and dst and dst != "$current":
                    transitions.append((src, method, dst))
                    # ★ 批次 2.5（F3）：出现在**具体转移**里的方法 ⇒ 改变状态
                    #   ⇒ 由**规范状态机**推导，不再直读 profile 的
                    #   ``state_changing``（专家知识旁路）
                    if method:
                        _state_changing_from_facts.add(str(method).upper())
                    # ★ 批次 2.1（P1）：记录来源（用于「源派生优先、骨架兜底」）
                    _transitions_auth.append(
                        (claims[0].get("authority", "") if claims else ""))
            elif aspect == "method_sequence":
                # 方法序列边（method -> method 相邻对，traffic 源产出）：
                # 语义与状态机边显式区分（不再靠 source.type 隐式分流）
                method_sequences.append((src, dst))
            elif aspect == "message_instance":
                # 字段级实例（AutoSeeder 式）：每条转移带能触发的合法消息字段模板。
                # ★状态名同样做 _normalize_state，与 transitions 的 key 保持一致——
                # 否则 edge_cover/build_seed_from_edges 用归一化状态名（Init/Ready）
                # 查不到未归一化的 key（INIT/READY），字段级实例全链路失效。
                if src and dst and method and isinstance(val, dict):
                    fields = [(f.get("name"), f.get("value"))
                              for f in (val.get("fields") or [])
                              if isinstance(f, dict)]
                    _mi_key = (_normalize_state(src), method,
                               _normalize_state(dst))
                    message_instances[_mi_key] = fields
                    # ★ 记下模板来源：迁移到别的转移时必须能如实标注
                    _mi_auth[_mi_key] = (claims[0].get("authority", "")
                                         if claims else "")
        elif stype == "status":
            if aspect == "definition":
                statuses[sname] = val or ""
        elif stype == "protocol":
            if aspect == "value_enum":
                protocol.setdefault(sname, []).extend(list(val or []))
        elif stype == "actor":
            if aspect == "value_enum":
                actors.setdefault(sname, []).extend(list(val or []))

    # ★ 批次 1.6 步 4：`required_headers` 的**兼容期回退**。
    #   中枢里有物化事实 ⇒ 已由 facts 提供（**不读** profile.json 的这份知识）；
    #   没有 ⇒ 回退读 profile.json（中枢未重建时也不破链）。
    #   ★ 回退必须是**合并**而不是覆盖：facts 的 ``relation_to_other`` 会往
    #     required_headers **追加**头名 ⇒ 覆盖会把它抹掉
    #     ⇒ 与步 4 之前（profile 基线 + facts 追加）不等价。
    if not _has_required_facts:
        for _m, _hs in (_struct.get("required_headers") or {}).items():
            required_headers.setdefault(_m, []).extend(list(_hs))
    # profile 兜底的客观结构知识也计入可用源（供降级决策识别「有结构知识」）
    if required_headers or preconditions or url_templates:
        available_sources.add("profile")

    # ★ profile 兜底的存在性（**只取 profile 侧**，facts 叠加后仍要能分列）
    _profile_has: dict[str, bool] = {
        "required_headers": bool(_struct.get("required_headers"))
                            and not _has_required_facts,
        "precondition": bool(preconditions),
        "session_header": bool(session_headers),
        "url_template": bool(url_templates),
        "methods": bool(_state_changing_from_facts),
    }

    # ★★ 批次 2.3：**各源的状态机全部保留**，消解/择一留给**后期 LLM**。
    #   · `transitions_by_source`：按来源分组的**全量**（后期 LLM 判别的输入）
    #   · `transitions`：**当前采用**的一套 ⇒ 消费端行为与本期之前**逐字节一致**
    #
    #   ★ 为什么分开：用户的要求是「每个知识源获取的状态机信息都保存到中枢，
    #     后期让 LLM 依据规则判别」⇒ **保存**（中枢 facts + by_source 全量）与
    #     **使用**（消费端用哪套）是两件事 ⇒ 本期只做前者 + 预留后者接口。
    #   ★ 当前采用规则见 `_select_active_transitions()`：**规范原生（rfc）优先，
    #     协议骨架兜底**（2026-11-05 修正）。旧规则是「骨架优先」⇒ RTSP 采用了
    #     骨架那 38 条 SIP 式状态名的边（RFC 原文命中 0/6）⇒ 种子状态路径
    #     精确率 **0%**；改用 RFC 原生那 14 条 ⇒ 精确率 **100%**
    #     （依据：``local/状态机消费口径对照实验报告.md``）。
    #   ★ 后期 LLM 判别时**只需替换 `_select_active_transitions()`** 这一个函数。
    transitions_by_source: dict[str, list] = {}
    for _t, _a in zip(transitions, _transitions_auth):
        transitions_by_source.setdefault(_a or "(unknown)", []).append(_t)
    transitions = _select_active_transitions(transitions_by_source)

    # 去重（多源可能重复，保持稳定序）
    transitions = sorted(set(transitions))
    method_sequences = sorted(set(method_sequences))
    # ★ security / precondition 等桶的值可能是 **dict**（结构化描述）
    #   ⇒ `set()` 需要可哈希 ⇒ 原 `sorted(set(...))` 会抛 TypeError（历史缺陷，
    #     当前单源态触发不到；引入 vuln / expert_note 源就会崩）
    #   ⇒ 统一走 `_dedupe_sorted`（可哈希时**逐字节不变**）
    security = _dedupe_sorted(security)
    # 协议方法白名单过滤：source 源 LLM 先验会产出垃圾方法名（中文功能词、带空格的
    # "AUTH TLS"/"SITE CPFR"、非标准命令 CAP/ALIAS），用 profile.allowed_methods 过滤
    # methods 桶 + transitions 桶，保证后续种子生成只用协议真实命令。
    # ★★ **单源实验的信息泄漏**（批次 2.3 实测）：``profile.allowed_methods`` 是
    #   **人工撰写**、源自**源码实现**的方法子集（rtsp 8 个），而 RFC 源**确实**
    #   抽到了 11 个方法 ⇒ 差集 ``ANNOUNCE`` / ``RECORD`` / ``REDIRECT`` 是
    #   **真实 RTSP 方法**却被裁掉 ⇒ RFC 单源实验的「方法召回」被人为封顶。
    #   ⇒ ``apply_allowed_methods=False`` 可关闭该过滤（严格单源模式用）。
    _allowed_methods = (_load_allowed_methods(_protocol_name)
                        if apply_allowed_methods else set())
    if _allowed_methods:
        methods = {k: v for k, v in methods.items() if k in _allowed_methods}
        transitions = [t for t in transitions
                       if (t[1] if isinstance(t, tuple) and len(t) >= 2 else t)
                       in _allowed_methods]
    # 跨源传导（vuln → source）：漏洞模式揭示的「重复方法」自环边，源 source 源码
    # 状态机漏建模（如 double_setup 的 SETUP 自环），注入后 generic_danger / 边界探针
    # 才能自然产「重复方法」的合法危险种子（对齐「接近但不触发」原则）。
    transitions = _inject_vuln_self_loops(transitions, vuln_patterns, set(methods))
    # ★★ 2026-11-07（P0-1 补漏）：**transitions 也必须受「骨架闸」约束**。
    #   原实现里 `include_skeleton_methods` 只挡
    #   `_BUCKET_BY_KIND[("method","existence")]` 新建 `methods` 桶条目，
    #   **管不到 transitions** —— 而种子是 transitions 驱动的 ⇒ 严格单源下
    #   sip 仍有 8 个、smtp 仍有 4 个「methods 桶里没有」的方法在生成报文
    #   （实测：sip 14→6 个方法、smtp 15→11）。
    #
    #   判据（**协议无关**）：转移里的方法必须出现在**最终 methods 桶**里。
    #   桶本身已经是「按 allowed_methods 与本次源集合过滤后的方法集」，
    #   所以这里不需要再引入任何协议名或方法白名单。
    #   · rtsp 不受影响：它的 transitions 来自 rfc 且方法全在桶内；
    #   · 一旦某协议的 methods 桶为空（极端情况），本闸不生效（避免全清空）。
    _dropped_undefined: list = []
    _dropped_required_keys: list = []
    if not include_skeleton_methods and methods:
        _defined_m = {str(m).strip().upper() for m in methods}
        _dropped_undefined = sorted({
            (str(t[0]), str(t[1]).strip().upper(), str(t[2]))
            for t in transitions
            if str(t[1]).strip().upper() not in _defined_m})
        if _dropped_undefined:
            transitions = [t for t in transitions
                           if str(t[1]).strip().upper() in _defined_m]
        # ★ 2026-11-07（同一次审计的第 6 项）：`required_headers` 的**桶键**也要过闸。
        #   它是 {方法名: [头名]}，骨架方法即使已不在 `methods` 桶里，键仍留在桶中
        #   （实测 sip 严格单源：methods 6 个、桶里却有 15 个键，多出 INFO/MESSAGE/
        #   NOTIFY/PRACK/PUBLISH/REFER/SUBSCRIBE/UPDATE）。
        #   消费端按「实际报文的方法」查表 ⇒ 无害，但**桶级纯净度统计会失真**。
        #   判据与 transitions 闸同源（方法在不在 methods 桶里），不引入协议特例。
        #   `"*"`（消息级全局必填头）不是方法名 ⇒ **恒保留**。
        _extra_keys = sorted(
            str(k) for k in required_headers
            if str(k) != "*" and str(k).strip().upper() not in _defined_m)
        if _extra_keys:
            _dropped_required_keys = _extra_keys
            required_headers = {
                k: v for k, v in required_headers.items()
                if str(k) == "*" or str(k).strip().upper() in _defined_m}
    # ★ 2026-11-05：状态机换源后，字段级实例必须**同步对齐**到采用的那套转移
    #   （否则键命中不了 ⇒ `edge_cover` 取不到字段 ⇒ 消息字段值全空 ⇒
    #   字段级知识静默失效）。
    #   ★ 2026-11-06 修正（P1-1c）：`allow_migrate` 与 `apply_allowed_methods`
    #     **解耦**。原实现让两者共用一个旗标 ⇒ 默认路径（全源、不裁剪方法）
    #     反而禁止迁移 ⇒ rtsp 的骨架实例键（Idle--SETUP-->Ready）与采用的转移
    #     （Init--SETUP-->Ready）精确命中 0 条 ⇒ `message_instances` **恒为 0**
    #     ⇒ 消息退回「必填头 + 取值池首值（池空则空串）」，同字段全方法同值、
    #     方法特有字段组合全丢（实测）。
    #     解耦后默认允许迁移；迁移出来的实例**逐个标注出处**（provenance），
    #     字段值来自骨架就记 `authority=profile`，不冒充 RFC 原生知识。
    _mi_provenance: dict = {}
    message_instances = _align_message_instances(
        transitions, message_instances,
        allow_migrate=allow_instance_migrate,
        provenance=_mi_provenance,
        instance_authority=_mi_auth)
    # P2a：method 级 precedence 消解（接入 resolver 统一消解引擎）。
    # state_changing/existence 是「单值判定」aspect，多源冲突时按认识论优先级
    #（observed > normative/must > descriptive）取最高者，而非「后遍历覆盖先遍历」。
    # 单 claim 时 resolve_claims 返回 single（等价原 claims[0]），行为向后兼容。
    from .resolver import resolve_claims  # noqa: E402
    for _info in methods.values():
        _resolution = {}
        for _aspect, _pending_key in (("state_changing", "_pending_state_changing"),
                                      ("existence", "_pending_existence")):
            if _pending_key not in _info:
                continue
            _res = resolve_claims(_info[_pending_key], _aspect)
            _val_view = _res.get("value")
            _info[_aspect] = bool((_val_view or {}).get("data")) if _val_view else False
            # P2a 可追溯：把消解结果（消解方法 / 胜出源 / 采纳声称 / 被覆盖声称）存进
            # info.resolution，使「被覆盖声称可追溯」名副其实，支撑 RQ3 消融
            #（查冲突方法、冲突消解方法、被覆盖声称清单）。single（无冲突）也记录，
            # superseded 为空。
            _resolution[_aspect] = {
                "method": _res.get("method"),
                "authority": _res.get("authority"),
                "epistemic": _res.get("epistemic"),
                "basis_claim_ids": _res.get("basis_claim_ids", []),
                "superseded": _res.get("superseded", []),
            }
            del _info[_pending_key]
        if _resolution:
            _info["resolution"] = _resolution
    # 客观结构知识兜底：state_changing 从 profile 注入（fact 若显式给则已覆盖）。
    # 仅当 profile 声明了 state_changing 才注入（不臆断其他协议的改状态语义）；
    # 方法全集 = 已见 methods ∪ profile 声明集（保证 OPTIONS 等也判 False）。
    if _state_changing_from_facts:
        # ★ 只给**已在 methods 桶里的**方法补标记 ⇒ **不把**被白名单裁掉的
        #   方法（如 RECORD）**加回**（否则 profile.allowed_methods 过滤失效）
        for name in sorted(methods):
            info = methods[name]
            if "state_changing" not in info:
                info["state_changing"] = name in _state_changing_from_facts
    # P0：provenance set → sorted list（可序列化、稳定序）
    for info in methods.values():
        if "declared_by" in info:
            info["declared_by"] = sorted(info["declared_by"])
        if "observed_by" in info:
            info["observed_by"] = sorted(info["observed_by"])
    for info in headers.values():
        if "source_values" in info:
            info["source_values"] = {
                k: sorted(v) for k, v in info["source_values"].items()
            }
    # P4-b：traffic 源真实流量值覆盖 source 源 LLM 模板值。
    # message_instances 的字段值是 AutoSeeder LLM 从「源码」推测的协议先验模板
    #（alice/bob、from-xxx-1），而 traffic 源从 packets.ndjson 抽到了真实流量字段值
    #（真实 To tag / branch / Contact line 参数）。用 traffic 源真实值覆盖模板值，
    # 让种子字段用真实流量值而非占位模板（协议无关：traffic 源贡献了该字段即覆盖）。
    _traffic_real: dict[str, str] = {}
    for _name, _info in headers.items():
        _sv = _info.get("source_values") or {}
        _tv = _sv.get("traffic_packet") or set()
        if _tv:
            _traffic_real[_name] = sorted(_tv)[0]
    if _traffic_real:
        for _key, _fields in list(message_instances.items()):
            if not _fields:
                continue
            message_instances[_key] = [
                (fn, _traffic_real.get(fn, fv)) for fn, fv in _fields
            ]
            if _key in _mi_provenance:
                # 字段值被流量观测覆盖过 ⇒ provenance 里如实记一笔
                _mi_provenance[_key] = dict(_mi_provenance[_key],
                                           value_from="traffic")
    bundle = {
        "methods": methods,
        "headers": headers,
        "required_headers": {k: _dedupe_sorted(v)
                             for k, v in required_headers.items()},
        "transitions": transitions,
        "method_sequences": method_sequences,
        "security": security,
        "statuses": statuses,
        "protocol": {k: _dedupe_sorted(v) for k, v in protocol.items()},
        "actors": {k: _dedupe_sorted(v) for k, v in actors.items()},
        "precondition": {k: _dedupe_sorted(v) for k, v in preconditions.items()},
        "session_header": {k: [dict(x) for x in v] for k, v in session_headers.items()},
        "url_template": url_templates,
        "legal_boundary": {k: [dict(x) for x in v] for k, v in legal_boundaries.items()},
        "response_expectation": {k: [dict(x) for x in v]
                                 for k, v in response_expectations.items()},
        "vuln_pattern": {k: [dict(x) for x in v] for k, v in vuln_patterns.items()},
        "message_instances": message_instances,
        # ★ P1-1c（2026-11-06）：字段模板的**出处**（迁移来的标 profile）
        "message_instance_provenance": _mi_provenance,
        # ★ 2026-11-07：严格单源下被「骨架闸」剔除的转移（方法不在 methods 桶）
        #   ⇒ 审计可见，避免「纯净度提升」变成看不见的静默丢边
        "transitions_dropped_undefined": _dropped_undefined,
        # ★ 2026-11-07：同上，`required_headers` 里因「方法不在 methods 桶」被剔除的键
        "required_headers_dropped_undefined": _dropped_required_keys,
        "available_sources": sorted(available_sources),  # P0
        "method_order": _derive_method_order(method_sequences),  # P2b 拓扑序
        # ★★ 批次 2.3：**各源的状态机全量**（按来源分组）—— 后期 LLM 判别的输入
        #   （判别逻辑落点：`_select_active_transitions()`）
        "transitions_by_source": {k: sorted(set(v))
                                  for k, v in transitions_by_source.items()},
    }
    # ★★ 批次 1.6 步 3：**溯源保留**（**只加顶层新键** ⇒ 既有桶结构逐字节不变
    #   ⇒ prompt 渲染不变 ⇒ 种子产物逐字节不变；旧消费者零影响）。
    #   ① by_source：桶级统计 —— 每个桶里各源贡献多少条事实
    #   ② bucket_fact_ids：桶 → 事实 id（有序）⇒ 桶里每条都能回指
    #   ③ fact_index：事实 id → 来源/维度/主体 ⇒ 桶 → fact → authority 双向可追
    #   ④ bucket_origin：facts 派生 vs profile 兜底**分列**（不混说）
    bundle["by_source"] = {k: dict(sorted(v.items()))
                           for k, v in sorted(by_source.items())}
    bundle["bucket_fact_ids"] = {k: list(v)
                                 for k, v in sorted(bucket_fact_ids.items())}
    bundle["fact_index"] = dict(sorted(fact_index.items()))
    bundle["bucket_origin"] = {
        k: {"facts": bool(by_source.get(k)),
            "profile": bool(_profile_has.get(k))}
        for k in sorted(set(by_source) | set(_profile_has))
    }
    # ★★ D-6：语义规则参与生成的可关闭开关位（**默认关闭**）
    #   ① 显式传参 ⇒ 调用方**显式授权** ⇒ 优先于开关：照常装载 + 投影；
    #   ② 开关 ON + 未显式传参 ⇒ 自动读权威规则库 + 投影；
    #   ③ 开关 OFF + 未显式传参 ⇒ **完全不引入**：不写两个新键、**不读规则库**
    #      （`load_semantic_rules` 0 次调用）、**不投影** ⇒ 与 B-8 之前的 bundle
    #      **逐字节一致**（默认路径不得被 B-8 悄悄改变）。
    if semantic_rules is not None:
        # 显式传参（含空列表）⇒ 显式授权 ⇒ 照常投影（不读规则库）。
        bundle["semantic_rules"] = _resolve_semantic_rules(
            semantic_rules, _protocol_name)
        bundle["bundle_schema_version"] = BUNDLE_SCHEMA_VERSION
        project_semantic_rules(bundle)
    elif semantic_rules_enabled():
        # 开关 ON + 未显式传参 ⇒ 自动装载权威库 + 投影。
        bundle["semantic_rules"] = _resolve_semantic_rules(
            None, _protocol_name)
        bundle["bundle_schema_version"] = BUNDLE_SCHEMA_VERSION
        project_semantic_rules(bundle)
    # ③ 开关 OFF + 未显式传参 ⇒ 上面两个分支都不走 ⇒ bundle 保持 B-8 之前形态。

    try:
        from core import knowledge_channels as _kc
        bundle["knowledge_ledger"] = _kc.build_ledger(
            by_source, _protocol_name,
            source_set=set(source_set) if source_set is not None else None)
        # ★ 投影桶（legal_boundary / response_expectation）**不走 by_source**
        #   （它们由语义规则投影而来）⇒ 单独补进台账（归属 = rfc / L1）
        for _pb, _pv in (("legal_boundary", bundle.get("legal_boundary")),
                         ("response_expectation",
                          bundle.get("response_expectation"))):
            _n = sum(len(v) for v in (_pv or {}).values())
            _ent = bundle["knowledge_ledger"]["buckets"].setdefault(
                _pb, {"by_source": {}, "count": 0})
            _ent["count"] = _n
            _ent.pop("empty", None)
            if _n:
                _ent["by_source"] = {"rfc": {"count": _n, "class": "L1",
                                             "owner": "rfc", "allowed": True}}
            else:
                _ent["empty"] = True
    except Exception as _exc:      # noqa: BLE001 —— 台账不得影响主流程
        bundle["knowledge_ledger"] = {"error": str(_exc), "buckets": {},
                                      "violations": [], "violation_count": 0,
                                      "pure": None}
    return bundle


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
_VULN_FIELD_GUIDANCE = {
    "Transport": "SETUP 的 Transport 用多种合法取值：RTP/AVP;unicast;client_port=X-Y、"
                 "RTP/AVP/TCP;unicast;interleaved=0-1 等",
    "Transport header": "同 Transport：SETUP 用多种合法 Transport 取值",
    "Range": "PLAY 的 Range 用多种合法取值：npt=0.000-、npt=0.000-0.001、clock=绝对时间等",
    "Session": "Session 用合法但多样的值（不同 hex/数字串）",
    "track": "对多轨流的同一 track 生成连续两次 SETUP 的合法序列",
    "interleaved": "生成先 RTP/AVP/TCP interleaved SETUP、再普通 SETUP 的合法序列",
    "client_port": "Transport 的 client_port 用不同端口对，尝试多个端口对",
    "CSeq": "CSeq 用合法取值：正常递增，或相邻请求用相同值（测试重放）",
    "Authorization": "DESCRIBE/SETUP/PLAY 的 Authorization 用合法完整 Digest"
                     "（username/realm/nonce/uri/response 齐全），并尝试偏长 nonce / 长 username（≤256 字符）",
    "授权头": "同 Authorization：用合法完整 Digest",
    "认证字段": "同 Authorization：用合法完整 Digest",
    "Digest": "Digest 认证的 username/realm/nonce/uri/response 用合法完整取值组合",
    "nonce": "Digest 认证的 nonce 用合法 hex 串，尝试偏长取值（≤256 字符）",
    "response": "Digest 认证的 response 用合法 hex 串，尝试不同长度",
    "realm": "Digest 认证的 realm 用合法字符串，尝试偏长 realm（≤256 字符）",
    "uri": "Digest 认证的 uri 字段用合法 URL（与请求行一致），尝试边界路径",
    "username": "Digest 认证的 username 用合法字符串，尝试偏长 username（≤256 字符）",
    "Content-Length": "Content-Length 用合法取值：与实际 body 长度一致，或数值边界（0/较大整数）",
    "URL": "请求 URL 用合法但多样的结构（尾斜杠、track{N}、边界路径）",
    "header": "各头部字段用合法但多样的取值，覆盖取值池与数值边界",
}


def _render_vuln_guidance(security: list) -> str:
    """把漏洞信息翻译成「漏洞导向生成要求」。

    核心：种子必须合法，但优先覆盖历史漏洞相关的字段/序列/边界，
    让 fuzzer 的变异能在漏洞相关区域展开（而非平铺漏洞描述让 LLM 自由发挥）。
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
    for field in fields:
        if field in _VULN_FIELD_GUIDANCE:
            lines.append(f"    · {field}: {_VULN_FIELD_GUIDANCE[field]}")
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
{_render_vuln_guidance(bundle['security'])}
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
# 5. 轻量校验（用 v2 中枢知识，非 JointConstraint）
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
