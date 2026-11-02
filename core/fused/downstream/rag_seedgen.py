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


def _project_rule(rule: Any) -> Optional[tuple[str, dict, Optional[dict]]]:
    """投影**一条**规则 → (归组键, legal_boundary 条目, response_expectation 条目)。

    返回 `None` 表示**不投影**，理由只有四类（不猜、不臆造）：

      ① `rule_state != "authoritative"` —— candidate / revoked / feedback
         **不进权威桶**（与 `rule_store` 的四库隔离一致：反馈只影响调度，
         不进权威知识）；
      ② `constraint is None` —— 不可转换（不是知识候选，也不是可执行规则）；
      ③ operator 不在词表内 / 有参算子缺 operand —— **不可渲染**；
      ④ 归组键为空（既无 `target_field` 又无 `subject_name`）—— 无处安放。
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
    expected_behavior = str(constraint.get("expected_behavior") or "").strip()
    lb_entry = {
        "dim": group_key,
        "legal": legal,
        "illegal": illegal,
        "trigger": expected_behavior,
    }
    # 无处理期望（expected_behavior 为空）⇒ 不产出 response_expectation 条目
    # （与 `norm.constraint_norm_to_facts` 的既有口径一致：缺 P 时只出 C）。
    re_entry: Optional[dict] = None
    if expected_behavior:
        re_entry = {
            "violation": illegal,
            "expected_code": _EXPECTED_BEHAVIOR_CODES.get(expected_behavior, ""),
            "expected_behavior": expected_behavior,
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
          "expected_behavior": constraint.expected_behavior}`
        —— `expected_behavior` 为空 ⇒ **不产出**本桶条目（缺 P 时只出 C）；
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


def assemble_bundle(views: list[dict], protocol: str = "rtsp",
                    *, semantic_rules: Optional[list] = None,
                    source_set: Optional[Iterable[str]] = None) -> dict:
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
    method_sequences: list = []
    security: list = []
    statuses: dict[str, str] = {}
    protocol: dict[str, list] = {}
    actors: dict[str, list] = {}
    preconditions: dict[str, list] = {
        m: list(ps) for m, ps in (_struct.get("precondition") or {}).items()
    }
    session_headers: dict[str, list] = {
        m: [dict(x) for x in rs]
        for m, rs in (_struct.get("session_header") or {}).items()
    }
    url_templates: dict[str, str] = dict(_struct.get("url_template") or {})
    _state_changing_profile = set(_struct.get("state_changing") or [])
    legal_boundaries: dict[str, list] = {}
    response_expectations: dict[str, list] = {}  # 处理期望（SemFuzz 的 P）
    vuln_patterns: dict[str, list] = {}  # 漏洞模式（GLMFuzz 式，vuln 源）
    message_instances: dict = {}  # {(from, method, to): [(field, value), ...]}
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
                    message_instances[(_normalize_state(src), method,
                                       _normalize_state(dst))] = fields
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
    if required_headers or preconditions or url_templates or _state_changing_profile:
        available_sources.add("profile")

    # ★ profile 兜底的存在性（**只取 profile 侧**，facts 叠加后仍要能分列）
    _profile_has: dict[str, bool] = {
        "required_headers": bool(_struct.get("required_headers"))
                            and not _has_required_facts,
        "precondition": bool(_struct.get("precondition")),
        "session_header": bool(_struct.get("session_header")),
        "url_template": bool(_struct.get("url_template")),
        "methods": bool(_state_changing_profile),
    }

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
    _allowed_methods = _load_allowed_methods(_protocol_name)
    if _allowed_methods:
        methods = {k: v for k, v in methods.items() if k in _allowed_methods}
        transitions = [t for t in transitions
                       if (t[1] if isinstance(t, tuple) and len(t) >= 2 else t)
                       in _allowed_methods]
    # 跨源传导（vuln → source）：漏洞模式揭示的「重复方法」自环边，源 source 源码
    # 状态机漏建模（如 double_setup 的 SETUP 自环），注入后 generic_danger / 边界探针
    # 才能自然产「重复方法」的合法危险种子（对齐「接近但不触发」原则）。
    transitions = _inject_vuln_self_loops(transitions, vuln_patterns, set(methods))
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
    if _state_changing_profile:
        for name in sorted(set(methods) | _state_changing_profile):
            info = methods.setdefault(name, {})
            if "state_changing" not in info:
                info["state_changing"] = name in _state_changing_profile
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
        "available_sources": sorted(available_sources),  # P0
        "method_order": _derive_method_order(method_sequences),  # P2b 拓扑序
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
        lines.append("  URL 结构:")
        for m, t in sorted(ut.items()):
            lines.append(f"    {m} → rtsp://<host>:<port>/{t}")
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
    for src, method, dst in transitions:
        trans_by_from.setdefault(src.upper(), set()).add((method.upper(), dst))

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
