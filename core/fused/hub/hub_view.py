# -*- coding: utf-8 -*-
"""core/fused/hub_view.py —— **中枢视图层**（阶段 D1，2026-11-09 新增）。

★ **为什么要有这一层**（层次分明的原则）：
  改造前 ``assemble_bundle``（在中枢重构之前写的）住在**消费层**，
  却是**事实上的中枢门面** ⇒ 出现了「物理上在消费层、概念上属中枢层」的错位，
  并导致 **GraphRAG 整理层反向依赖消费层**（``build_graph`` import ``rag_seedgen``）。

★ **本层的职责（只此一件事）**：**读中枢 ⇒ 组装视图**。
  · ``build_view()``  ⇒ 中枢的**唯一门面**：
      - 16 个桶（``methods``/``headers``/``transitions``/…）—— **对外契约不变**
      - ``by_category``  —— 按**知识分类**（A~F）的视图（D1 新增）
      - ``entities``     —— 实体索引（``entity_id`` ⇒ 实体）（D1 新增）
  · 消费层只做**消费策略**（白名单 / 骨架方法 / 实例迁移）⇒ 职责分明。

★ **依赖方向（调整后）**：``④ GraphRAG`` 与 ``⑤ 消费层`` **并列**依赖本层
  ⇒ 互不依赖 ⇒ 无倒置。
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

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

BUNDLE_SCHEMA_VERSION = "2.0"

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

PROFILE_AUTHORITY = "profile"
#: ★ 阶段 E5：协议骨架已物理移除 ⇒ 「profile」authority 现在只承载
#:   **协议结构声明**（required_headers）⇒ 不再是跨源污染通道。

_GLOBAL_REQUIRED_KEY = "*"

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

          ★★ 2026-11-05 修正（依据：旧的状态机消费口径对照实验报告，**已随论文实验层移除**）：
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
    for _auth in (RFC_AUTHORITY, PROFILE_AUTHORITY):
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
        #   （tests/test_bundle_provenance.py::test_each_kind_lands_only_in_its_bucket）。
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

def project_semantic_rules(bundle: dict) -> dict:
    """把 `bundle["semantic_rules"]` **投影**进 `legal_boundary` /
    `response_expectation` 两个桶（§3.6 选项 c）。

    ── 输入形态 ──────────────────────────────────────────────────────────
    `bundle["semantic_rules"]` 是一个**列表**，每项为下列两种形态之一：

      ① `SemanticRule` 本体（`core.fused.semantic.semantic` 的 frozen dataclass）；
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

def build_view(views: list[dict], protocol: str = "rtsp",
                *,
                semantic_rules: Optional[list] = None,
                    source_set: Optional[Iterable[str]] = None,
                    apply_allowed_methods: bool = True,
                    include_skeleton_methods: bool = True,
                    allow_instance_migrate: bool = True) -> dict:
    """把 fact views 组装成**中枢视图**（阶段 D1）。

    产出:
      methods          method_name -> {state_changing, definition, existence,
                                       declared_by, observed_by}
      headers          header_name -> {syntax, values, source_values}
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

    ★★ D-6（可关闭的开关位，默认关闭 —— 见 `core/fused/semantic/llm_ensemble.py`）：

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
    ★ 协议骨架已于阶段 E5（2026-11-10）**物理移除** ⇒ profile（协议档案）现在
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
    from core.fused.semantic.llm_ensemble import semantic_rules_enabled
    from core.fused.downstream.resolver import resolve_claims
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
        # ★★ 阶段 E1：**不再无条件放行协议骨架** ⇒ 纯度闸对**所有源**真正生效。
        #   骨架（authority=profile）现在与其他源**一视同仁**：
        #   要它进中枢，就把它**显式写进 source_set**
        #   （见 scripts/seedgen.py:resolve_source_set —— 它会并入中枢声明的
        #     skeleton.source）⇒ 台账可见、闸行为与声明一致。

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
        # ★★ P0-1（**阶段 E5 后已成死分支**）：严格单源下 profile 的 method
        #   `existence` 事实**不得新建 `methods` 桶条目**。
        #   ★ 骨架已物理移除 ⇒ profile 只产 required_headers ⇒ **不再有 existence 事实**
        #   ⇒ 该条件永不满足（保留作防御：若将来 profile 再产 existence 仍生效）。
        #   为什么必须挡在**这里**（by_source 登记之前）：
        #     · `apply_allowed_methods` 只做**裁剪**（删 RFC 有、白名单没有的），
        #       做不了**并入**；而 `("method","existence") → "methods"` 的映射
        #       会让骨架事实直接**注入** RFC 文档里没有的方法；
        #     · 因此必须在「进桶」之前拦，否则 `by_source` 台账会把「未采用」的
        #       事实记成「已采用」⇒ 溯源失真。
        #   只挡「新建」：已有条目（RFC 侧 `definition` 建过）仍允许补 `observed_by`。
        #   ★ 2026-11-10：profile 的 existence 事实已归零 ⇒ 上述闸**不再被触发**。
        if (not include_skeleton_methods
                and stype == "method" and aspect == "existence"
                and sname not in methods
                and all(str(c.get("authority") or "").strip().lower()
                        == PROFILE_AUTHORITY for c in claims)):
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
            elif aspect in ("value_enum", "value_enum_spec", "value_enum_observed"):
                info = headers.setdefault(sname, {})
                # P2a：取值池做 union（多源互补不冲突，并集合并而非覆盖）
                existing = set(info.get("values") or [])
                existing.update(list(val or []))
                info["values"] = sorted(existing)
                if main_auth:  # P0：各源取值
                    info.setdefault("source_values", {}).setdefault(
                        main_auth, set()).update(list(val or []))
            # ★ 2026-11-11：删除「实测频次」（occurrence）⇒ 不再投影到 headers 桶
            elif aspect == "binary_layout":
                # ★ 2026-11-07：二进制协议的**字段布局**
                #   （offset/length/order/encoding，来自 RFC 的位域图）
                headers.setdefault(sname, {})["binary_layout"] = val
            elif aspect == "option_layout":
                # ★ 2026-11-07：二进制协议的**TLV 选项布局**（code/length）
                headers.setdefault(sname, {})["option_layout"] = val
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
            if aspect in ("value_enum", "value_enum_spec", "value_enum_observed"):
                protocol.setdefault(sname, []).extend(list(val or []))
        elif stype == "actor":
            if aspect in ("value_enum", "value_enum_spec", "value_enum_observed"):
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
    #     ★ 阶段 E5：骨架已物理移除 ⇒ 那 38 条（SIP 式状态名，RFC 原文命中 0/6）已随之消失
    #     ⇒ 现在采用的是 **RFC 原生状态机**（rtsp 14 条：Init/Ready/Playing/Recording）
    #     精确率 **0%**；改用 RFC 原生那 14 条 ⇒ 精确率 **100%**
    #     （依据：旧的状态机消费口径对照实验报告，**已随论文实验层移除**）。
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
    #     ★ 阶段 E5：骨架删除后**全仓已无 message_instance 事实** ⇒ 恒为 0 的原因
    #       变成「没有实例来源」（而非本段描述的键不匹配）；举例键在旧骨架里本就不存在
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
    from core.fused.downstream.resolver import resolve_claims  # noqa: E402
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
        # ★ 2026-11-07（B2）：**实体头** —— 只该命令的**消息内容**里要带的头
        #   （如 SMTP DATA 的邮件头 Date/From/To）。
        #   ★ 与「命令头」`required_headers` **分开**：前者是消息内容的一部分
        #   （RFC 5321 §2.3.9「message content includes the message header
        #   section」），后者是协议请求行的头。
        #   ★ 来自 profile 的 `raw_format.entity_headers`（配置层，不是 facts 桶）。
        #   ★ 用 `_protocol_name`（保存的协议名）—— `protocol` 变量在此已被
        #   「protocol 桶 dict」覆盖（见上方注释）。
        "entity_headers": _entity_headers_from_profile(_protocol_name),
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
    # ★★ **阶段 D1：附加两个视图**（追加在末尾 ⇒ 不影响既有键序）
    #   · ``by_category``：按**知识分类**（A~F）组织
    #   · ``entities``：实体索引（``entity_id`` ⇒ 实体）
    try:
        from core.fused.hub.knowledge_slots import locate as _locate
        _bc: dict = {}
        for _f in views:
            _fk = _f.get("fact_key") or {}
            _loc = _locate(str(_fk.get("aspect") or ""),
                           str((_fk.get("subject") or {}).get("type") or ""))
            if not _loc:
                continue
            _cat, _slot = _loc
            _sub = _bc.setdefault(_cat, {}).setdefault(_slot, {})
            _nm = str((_fk.get("subject") or {}).get("name") or "")
            if _nm and _nm not in _sub:
                _sub[_nm] = _f
        bundle["by_category"] = _bc
    except Exception:                                   # noqa: BLE001
        bundle["by_category"] = {}
    try:
        _ents: dict = {}
        for _f in views:
            _eid = str(_f.get("entity_id") or "")
            if not _eid:
                continue
            _e = _ents.setdefault(_eid, {"entity_id": _eid, "aspects": []})
            _fk2 = _f.get("fact_key") or {}
            _a2 = str(_fk2.get("aspect") or "")
            if _a2 and _a2 not in _e["aspects"]:
                _e["aspects"].append(_a2)
            _nm2 = str((_fk2.get("subject") or {}).get("name") or "")
            if _nm2:
                _e["name"] = _nm2
                _e["type"] = str((_fk2.get("subject") or {}).get("type") or "")
        bundle["entities"] = _ents
        # ★★ **name → entity_id 索引**（阶段 D2：图与中枢对齐用）
        #   图节点的 ``name`` 与中枢实体的 ``name`` 同名 ⇒ 同一实体
        #   （类型名不同：图用 entity/message/state，中枢用 method/header/…）
        #   ⇒ **按名字对齐**（类型只作辅助）。
        _byname: dict = {}
        for _eid, _e in _ents.items():
            _nm3 = str(_e.get("name") or "")
            if _nm3 and _nm3 not in _byname:
                _byname[_nm3] = _eid
        bundle["entity_by_name"] = _byname
    except Exception:                                   # noqa: BLE001
        bundle["entities"] = {}
        bundle["entity_by_name"] = {}
    return bundle

def _entity_headers_from_profile(protocol: str) -> dict:
    """读 profile 的 ``raw_format.entity_headers`` ⇒ ``{方法名: [头名, ...]}``。

    ★ 2026-11-07（B2）：**实体头**（只该命令的消息内容里要带的头）。
      典型场景：SMTP 的 ``DATA`` 命令之后是**邮件内容**，其头部段按
      RFC 5322 要求要含 ``Date`` / ``From`` / ``To``（§3.6 逐头定义）
      —— 但这些头**不是 SMTP 命令的头** ⇒ 不能混进 ``required_headers``。

    ★ 协议无关：判据只看 ``profile.raw_format.entity_headers`` 这个**配置段**，
      不认协议名 ⇒ 新协议要带实体头时，在自己的 profile 里声明即可。
    """
    try:
        from core import paths as _paths
        import json as _json
        _p = _paths.target_profile(protocol)
        if not _p.is_file():
            return {}
        _d = _json.loads(_p.read_text(encoding="utf-8")) or {}
        _raw = (_d.get("raw_format") or {}).get("entity_headers") or {}
        if not isinstance(_raw, dict):
            return {}
        out: dict[str, list] = {}
        for _m, _hs in _raw.items():
            if isinstance(_hs, str):
                _hs = [_hs]
            if not isinstance(_hs, list):
                continue
            _lst = [str(h).strip() for h in _hs if str(h).strip()]
            if _lst:
                out[str(_m).strip().upper()] = _lst
        return out
    except (OSError, ValueError):
        return {}

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

def load_semantic_rules(protocol: str = "rtsp") -> list[dict]:
    """读 **authoritative** 规则库 → bundle 形态（两层嵌套 dict）列表。

    ★ 走 `core.fused.downstream.rule_store` 的**四库隔离**：只读 `rules.jsonl`
      （candidate / revoked / feedback 三库**根本不在路径上**）⇒ 天然只投影
      权威规则，与 `project_semantic_rules` 的 `rule_state` 过滤**同口径**。
    ★ 库文件不存在 ⇒ 返回空列表（B 阶段前语义库尚未落地，**不是错误**）。
    """
    from core import paths
    from core.fused.downstream.rule_store import library_path, load_rules
    # ★★ **阶段 C4**：**优先读中枢**（唯一真源）⇒ 降级读旧四库路径
    from core.fused.semantic.semantic_lift import read_lifted
    _lifted = read_lifted(paths.hub_root(), protocol)
    if _lifted:
        out = []
        for f in _lifted:
            plain = _lifted_fact_to_plain(f)
            if plain is not None:
                out.append(plain)
        if out:
            return out
    from core.fused.downstream.rule_store import library_path, load_rules
    path = library_path(protocol, "authoritative")
    if not path.is_file():
        return []
    out: list[dict] = []
    for rule in load_rules(path):
        plain = _rule_to_plain(rule)
        if plain is not None:
            out.append(plain)
    return out

RFC_AUTHORITY = "rfc"

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
    # ★ 2026-11-07：二进制协议的**布局**（字段布局 / TLV 选项布局）
    #   ⇒ 也落进 headers 桶 ⇒ 下游零改动（字段被 known_fields 认识）。
    ("header", "binary_layout"): "headers",
    ("header", "option_layout"): "headers",
    ("header", "definition"): "headers",
    ("header", "value_enum_spec"): "headers",
    ("header", "value_enum_observed"): "headers",
    ("header", "security_property"): "security",
    ("header", "legal_boundary"): "legal_boundary",
    ("header", "response_expectation"): "response_expectation",
    ("header", "vuln_pattern"): "vuln_pattern",
    # ── relation 主体 ──
    ("relation", "target_state"): "transitions",
    ("relation", "method_sequence"): "method_sequences",
    ("relation", "message_instance"): "message_instances",
    # ── status 主体 ──
    # ★ 2026-11-11：`occurrence`（实测频次）**已整体删除**（不再注册为 aspect）
    #   ⇒ 「状态码出现几次」这类观测不再进中枢（它不指导报文构造）。
    ("status", "definition"): "statuses",
    # ── protocol / actor 主体 ──
    ("protocol", "value_enum_spec"): "protocol",
    ("protocol", "value_enum_observed"): "protocol",
    ("actor", "value_enum_spec"): "actors",
    ("actor", "value_enum_observed"): "actors",
}

_EXPECTED_BEHAVIOR_CODES: dict[str, str] = {
    "success": "2xx",
    "protocol_error": "4xx",
    # 应用级错误（RTSP §11 的 4xx 族 / SIP 的 4xx 族，如 404 Not Found）
    "application_error": "4xx",
    # 无响应 ⇒ 无状态码
    "silence": "",
}

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

_REJECT_ABSENT_OPERATOR = True

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

def _lifted_fact_to_plain(fact: dict) -> Optional[dict]:
    """中枢里提升出的语义 fact ⇒ bundle 形态（与旧四库**逐字段同构**）。

    ★ **复用 ``_rule_to_plain``**（提升时保存了完整规则）⇒
      输出与旧四库路径**完全一致** ⇒ 消费端零改动。
    """
    rule = fact.get("semantic_rule")
    if isinstance(rule, dict):
        return _rule_to_plain(rule)
    # ★ 兜底：没有完整规则 ⇒ 用 claim 里的 constraint 组装
    cl = (fact.get("all_claims") or [])
    if not cl:
        return None
    c = cl[0]
    data = ((c.get("value") or {}).get("data"))
    if not isinstance(data, dict):
        return None
    fk = fact.get("fact_key") or {}
    subj = fk.get("subject") or {}
    return {
        "rule_id": str(c.get("claim_id") or ""),
        "subject_type": str(subj.get("type") or ""),
        "subject_name": str(subj.get("name") or ""),
        "constraint": data,
        "evidence": {},
    }

_INFERABLE_OPERATORS = frozenset({
    "present", "eq", "ne", "in", "range", "ge", "le", "lt", "gt",
})

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
