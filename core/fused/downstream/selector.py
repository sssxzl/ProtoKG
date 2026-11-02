"""core/fused/downstream/selector.py —— 三层语料库选择器编排 + 降级。

对齐 local/three_layer_seedgen_design.md §五：
      ① 结构覆盖（永远）  edge_cover
      ② 通用危险（永远）  generic_danger
      ③ 漏洞特定（有漏洞 + llm 才叠加）  strategy.classify_all/dedupe_reqs/generate_attack_seeds

    三层结果合并后按「方法序列 + 全部头部取值」签名去重（保留首次出现），
    返回合并后的 list[SeedCorpus]。

    注意：签名必须包含头部取值——层② generic_danger 的边界取值种子正是靠
    「同方法序列 + 不同字段值」区分边界的（CSeq 的 0/-1/2147483647/空、
    Transport 的 RTP/AVP / RTP/AVP/TCP / RTP/AVP/UDP），若只按方法序列去重
    会把边界多样性压扁（设计 §四-② 的边界取值层 2.3 已移除, 边界多样性现由层③漏洞边界候选与定向字典承载）。
"""
from __future__ import annotations

from typing import Optional

from core.models import SeedCorpus

from .edge_cover import edge_cover
from .generic_danger import generic_danger
from .boundary_probe import derive_vuln_pattern_candidates
from .action_seq import ACTION_SEQ_GENERATED_BY
from .strategy import classify_all, dedupe_reqs, generate_attack_seeds

# 序列型漏洞 action（精简模式保留），对应状态机「边序列」类漏洞（UAF/断言/重放），
# 是 live555 崩溃（matroska UAF）的主要来源。字段型漏洞（long_value/empty_edge 等）
# 在精简模式下砍掉，以集中变异预算。
_SEQUENCE_ACTIONS = {
    "double_setup", "uaf_seq", "interleave_seq", "lifecycle_seq",
    "assert_seq", "multi_session", "abs_time_seek", "replay_seq",
}


def _seed_signature(seed: SeedCorpus) -> tuple:
    """(方法序列, 全部头部取值) 完整签名——只折叠完全相同的种子。"""
    return (
        tuple(m.method.upper() for m in seed.messages),
        tuple((k, v) for m in seed.messages for k, v in sorted(m.headers.items())),
    )


def dedupe_seeds(seeds: list) -> list:
    """按完整签名去重（方法序列 + 头部取值），保留首次出现。"""
    seen: set = set()
    out: list = []
    for s in seeds:
        sig = _seed_signature(s)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(s)
    return out


def select_seeds(bundle: dict, resources: Optional[list] = None,
                 request_templates: Optional[dict] = None,
                 vulns: Optional[list] = None,
                 llm=None, protocol: str = "rtsp",
                 max_seeds: Optional[int] = None,
                 attack_batch: Optional[int] = 4,
                 max_rounds: int = 2,
                 minimal: bool = False) -> list:
    """三层编排：①+② 永远生效，③ 有漏洞且 llm 可用才叠加。

    Args:
        bundle:            assemble_bundle() 产物（transitions/methods/headers/...）
        resources:         目标资源清单（透传给漏洞层）
        request_templates: 真实请求模板（透传给漏洞层）
        vulns:             list[VulnRecord]；空/None 时跳过漏洞层（降级不失效）
        llm:               有 vulns 时才使用的 LLM 客户端
        protocol:          协议名（默认 rtsp，供漏洞层 prompt 用）
        max_seeds:         可选上限（设计 §六-4「去重后种子总数可控」）。None 不截断；
                          非 None 时按 ①→②→③ 优先级顺序截断前 N 条。
        attack_batch:      ③ 漏洞层分批大小（真实 LLM 下一次性生成全部模式会超
                           max_tokens，需分批）。None 表示不分批。
        max_rounds:        ③ 漏洞层 ReAct 迭代上界（透传 generate_attack_seeds）。
        minimal:           精简模式：② 只保留序列型危险种子（SETUP 自环/生命周期/
                           CSeq 边界），③ 只保留序列型漏洞（double_setup/uaf_seq/
                           interleave_seq 等），砍掉字段型漏洞。用于把变异预算集中
                           到关键序列路径（实验教训：种子过多稀释变异预算）。
    """
    seeds: list = []
    transitions = bundle.get("transitions", [])
    required_headers = bundle.get("required_headers")
    headers = bundle.get("headers")
    message_instances = bundle.get("message_instances") or {}

    # ① 结构覆盖（永远）
    seeds += edge_cover(transitions, required_headers, headers,
                        message_instances, protocol=protocol,
                        method_order=bundle.get("method_order"))
    # ② 通用危险（永远）：会话语义（前置方法/会话头）由知识中枢 bundle 驱动
    seeds += generic_danger(transitions, headers, required_headers,
                            minimal=minimal,
                            precondition=bundle.get("precondition"),
                            session_header=bundle.get("session_header"),
                            message_instances=message_instances,
                            protocol=protocol)
    # ③ 漏洞特定（序列型漏洞模式）：从 bundle 的 vuln_pattern 桶规则生成边界候选
    #   （GLMFuzz 式，不调 LLM、不依赖 load_vuln_kb 读 JSON——直接消费已抽取的漏洞模式）。
    #   已映射 action（double_setup/uaf_seq/lifecycle_seq/interleave_seq）产 legal/illegal
    #   边界对；字段型 action（long_value/empty_edge 等）由下方 LLM 导向覆盖。
    #   过滤非白名单方法的候选（漏洞数据 boundary 可能硬编码 RTSP 的 SETUP/TEARDOWN）。
    #   默认流名从 profile url_placeholders 的 <stream> 读（协议特定），缺省回退 RTSP（默认流名兜底, 换协议应在 profile 显式声明 url_placeholders）。
    from core import paths as _paths
    import json as _json
    _prof = _paths.target_profile(protocol)
    _stream = "matroskaFileTest"
    if _prof.exists():
        try:
            _pd = _json.loads(_prof.read_text(encoding="utf-8")) or {}
            _stream = ((_pd.get("url_placeholders") or {}).get("<stream>")
                       or _stream)
        except (_json.JSONDecodeError, OSError):
            pass
    _vuln_cands = derive_vuln_pattern_candidates(bundle, stream=_stream,
                                                 protocol=protocol)
    _valid_methods = set(bundle["methods"].keys())
    _vuln_cands = [(lb, s) for lb, s in _vuln_cands
                   if all(m.method in _valid_methods for m in s.messages)]
    seeds += [s for _label, s in _vuln_cands]
    # ③ 漏洞特定（字段型/LLM 导向）：有漏洞库且 llm 非空才叠加（生成合法边界种子）
    if vulns and llm is not None:
        reqs = dedupe_reqs(classify_all(vulns, protocol=protocol))
        # 用 bundle 方法白名单过滤漏洞需求的垃圾方法（中文功能词、带空格的
        # "SITE CPFR"、非标准 CAP 等），避免 LLM 按垃圾方法生成种子。
        _valid_methods = set(bundle["methods"].keys())
        _clean_reqs = []
        for r in reqs:
            _methods = [m for m in r.methods if m in _valid_methods]
            if _methods:
                r.methods = _methods
                _clean_reqs.append(r)
        reqs = _clean_reqs
        if minimal:
            reqs = [r for r in reqs if r.action in _SEQUENCE_ACTIONS]
        if attack_batch and len(reqs) > attack_batch:
            for start in range(0, len(reqs), attack_batch):
                batch = reqs[start:start + attack_batch]
                seeds += generate_attack_seeds(
                    bundle, llm, batch, protocol=protocol,
                    resources=resources, request_templates=request_templates,
                    max_rounds=max_rounds)
        else:
            seeds += generate_attack_seeds(
                bundle, llm, reqs, protocol=protocol,
                resources=resources, request_templates=request_templates,
                max_rounds=max_rounds)

    merged = dedupe_seeds(seeds)
    # 行命令协议（ftp/smtp）：过滤掉 LLM 先验误生成的含 URL 种子（如 MLSD rtsp://...）。
    # 头部协议（rtsp/sip）的消息本应带 URL，不过滤。
    from core import paths
    import json as _json
    _prof = paths.target_profile(protocol)
    _rf = {}
    _default_url = ""
    if _prof.exists():
        try:
            _pd = _json.loads(_prof.read_text(encoding="utf-8")) or {}
            _rf = _pd.get("raw_format") or {}
            _default_url = _pd.get("default_url") or ""
        except (_json.JSONDecodeError, OSError):
            _rf = {}
    if "{url}" not in _rf.get("request_line", ""):
        merged = [s for s in merged if not any(getattr(m, "url", "") for m in s.messages)]
    elif protocol != "rtsp" and _default_url:
        # 非 rtsp 头部协议（如 sip）：source 源 LLM 先验会塞 rtsp:// URL，
        # 统一替换成 profile 的 default_url（如 sip:127.0.0.1:5060）。
        for s in merged:
            for m in s.messages:
                if getattr(m, "url", "") and str(m.url).startswith("rtsp://"):
                    m.url = _default_url
    if max_seeds is not None and len(merged) > max_seeds:
        return merged[:max_seeds]
    return merged


# ===========================================================================
# 漏洞接近度打分 + 聚焦排序（协议无关，基于 generated_by 标记）
# ===========================================================================
#
# 实验教训（2026-10-13 / 2026-10-23 两轮对照实证）：
#   - 崩溃发现奖励「种子离漏洞触发点近 + 变异预算集中」，而非「种子多 / 种子合法」。
#   - 50 条种子（结构覆盖 + 通用危险 + 漏洞边界候选 + 黄金路径）摊薄了单种子变异
#     预算（~950 次 vs 基线 7 条 ~25400 次，差 27 倍），导致覆盖率反超但崩溃落后。
#   - 五源知识若全用在「守正」（让种子合法完整），漏洞导向层的「出奇」种子会被稀释。
#
# 打分目标：让 fuzzer 优先变异「离漏洞触发边界最近」的种子（边界候选 legal 端 > 序列型
# 危险 > 结构覆盖），max_seeds 截断时保留高分种子，把变异预算集中到关键路径。
#
# 分数只依赖 generated_by 标记（协议无关、不硬编码方法名），换协议仍成立。

#: generated_by 标签 → 基础漏洞接近度分（越高越接近漏洞边界）
_VULN_PROXIMITY_BASE = {
    "rule-based:boundary-probe": 100,            # 序列型漏洞边界候选（GLMFuzz 式，最接近触发）
    "rule-based:boundary-probe-vuln-field": 85,  # 字段型漏洞边界
    "rule-based:boundary-probe-semantic": 80,    # 协议语义边界（源 A，无漏洞库）
    "rule-based:boundary-probe-constraint": 75,  # rfc 约束边界
    "rule-based:field-probe": 70,                # 字段空间探测基线
    "rule-based:generic-danger": 60,             # 通用危险（序列型自环/生命周期见下细分）
    "rule-based:edge-cover": 20,                 # 结构覆盖（守正，保证覆盖完整性）
    "rule-based:canonical-session": 10,          # 黄金路径（守正）
}

#: 通用危险里「序列型」（自环重复 / 生命周期）危险分更高——它们是 UAF/资源类漏洞的直接来源
_GENERIC_DANGER_SEQUENCE_BONUS = {"self-loop", "lifecycle"}


def vuln_proximity_score(seed: SeedCorpus) -> int:
    """漏洞接近度打分（协议无关）。

    返回 [0, 100] 的分数，越高表示种子越接近「漏洞触发边界」。判定依据：
      - generated_by 标记（各层种子生成来源）；
      - description 里的 legal/illegal 关键词（边界候选的合法端 > 非法端，
        因非法端可能 dry-run 崩溃被 fuzzer 拒绝，合法端才是「离非法最近仍合法」的
        理想种子，对齐「接近但不触发」原则）；
      - 通用危险的序列型（自环/生命周期）加成。
    """
    gb = seed.generated_by or ""
    base = _VULN_PROXIMITY_BASE.get(gb, 0)
    desc = (seed.description or "").lower()

    if gb == "rule-based:boundary-probe":
        # legal 边界端（不同 track / 不重建 / 不切换）是理想种子；
        # illegal 端（同 track / 重建 / 切换 + 触发值）可能 dry-run 崩，略降。
        return 100 if "illegal" not in desc else 95
    if gb == "rule-based:generic-danger":
        # 序列型危险（self-loop / lifecycle）> 其他通用危险
        if any(kw in desc for kw in _GENERIC_DANGER_SEQUENCE_BONUS):
            return 60
        return 40
    return base


def prioritize_seeds(seeds: list, max_seeds: Optional[int] = None) -> list:
    """按漏洞接近度降序排序（稳定，同分保持原序），可选截断前 N 条。

    排序后「漏洞边界候选 → 序列型危险 → 结构覆盖」依次排列，fuzzer 优先变异前序
    （高价值）种子；max_seeds 截断时丢弃低分的结构覆盖/黄金路径种子，把变异预算
    集中到离漏洞触发点近的种子。

    Args:
        seeds:     待排序的种子列表。
        max_seeds: 可选上限，None 不截断；非 None 时保留前 N 条（高分优先）。
    """
    ranked = sorted(seeds, key=vuln_proximity_score, reverse=True)
    if max_seeds is not None and len(ranked) > max_seeds:
        return ranked[:max_seeds]
    return ranked


def seed_layer(seed: SeedCorpus) -> tuple[str, str]:
    """判定种子所属的生成分层，返回 `(layer, layer_name)`。

    层归属是 RQ3 变异命中率「③ 层归因」口径（MHR_B）的唯一依据，
    与 manifest 落盘的 `layer` / `layer_name` 字段严格一致。

    | generated_by                             | layer | layer_name      |
    |-----------------------------------------|-------|-----------------|
    | `rule-based:edge-cover`                 | L1    | edge_cover      |
    | `rule-based:generic-danger`             | L2    | generic_danger  |
    | `rule-based:canonical-session`          | L4    | canonical       |
    | `rule-based:boundary-probe*`            | L3    | vuln_boundary   |
    | `rule-based:action-seq`                 | L5    | action_seq      |
    | 其他                                     | L0    | unknown         |

    Args:
        seed: 待判定的种子。

    Returns:
        (layer, layer_name) 二元组；未识别的来源归 L0 / unknown。
    """
    gb = (seed.generated_by or "").strip()
    if gb == "rule-based:edge-cover":
        return ("L1", "edge_cover")
    if gb == "rule-based:generic-danger":
        return ("L2", "generic_danger")
    if gb == "rule-based:canonical-session":
        return ("L4", "canonical")
    if gb.startswith("rule-based:boundary-probe"):
        return ("L3", "vuln_boundary")
    # ★ P1-3：第 5 层（字段级 action-sequence 变异）。
    #   不加这一条 ⇒ 该层的种子**全部落成 L0/unknown**
    #   （QA 实测 L0 条数 == L5 条数，100%），而 manifest 顶层又宣称有第 5 层
    #   ⇒ 「顶层宣称与实际不一致」⇒ ③ 层归因（MHR_B）直接失效
    #   （selector.py 自述：层归属是 MHR_B 的**唯一依据**）。
    if gb == ACTION_SEQ_GENERATED_BY:
        return ("L5", "action_seq")
    return ("L0", "unknown")


__all__ = ["select_seeds", "dedupe_seeds", "vuln_proximity_score",
           "prioritize_seeds", "seed_layer"]
