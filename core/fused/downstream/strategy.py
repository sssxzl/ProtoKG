"""core/fused/downstream/strategy.py —— 多导向自适应种子生成（漏洞导向 P0）。

对齐 local/multi_strategy_seedgen_design.md §六 + 论文 4.4/4.5。

核心原则（隐患 2/3/6，用户反复强调）：
    初始种子必须**绝对合法**，不是畸形触发种子。
    漏洞信息只用于「引导合法种子覆盖漏洞相关字段 / 序列 / 边界」——
    给 fuzzer 在漏洞代码附近一个合法立足点，让它的变异能朝触发方向展开，
    而不是直接生成会让目标崩溃的畸形报文。

本模块职责：
  1. load_vuln_kb       读 kb/历史漏洞/*.json 的**结构化** trigger（method/field/
                        condition/cwe），比 security 桶（只有 description_raw 文本）
                        信息更丰富、更可翻译。
  2. classify_vuln      把每条漏洞翻译成「合法边界种子需求」VulnSeedReq
                        （method + field + action + 合法边界指引）。
  3. determine_strategies 按知识中枢实际有哪些源，自适应判定激活的导向。
  4. render_attack_prompt 把漏洞需求渲染成「漏洞导向」生成 prompt。
  5. generate_attack_seeds 走「生成 → 校验 → 带错重生成」产出**合法**攻击种子。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.fused.vuln_pattern import (
    classify_action, extract_stream_hints, normalize_field,
)

# ===========================================================================
# 0. 数据根（kb/历史漏洞 目录）
# ===========================================================================

def _data_root() -> Path:
    """<project>/kb。统一走 paths.kb_root()（不再手算 parents[3]，避免双路径并存）。"""
    from core import paths
    return paths.kb_root()


def _vuln_dir(data_root: Optional[Path] = None) -> Path:
    """旧单协议路径 kb/历史漏洞（仅 load_vuln_kb 未传 protocol 时向后兼容）。

    新结构统一走 paths.kb_source_dir(protocol, "vuln")（kb/<protocol>/历史漏洞）。
    """
    if data_root is not None:
        root = Path(data_root)
    else:
        root = _data_root()
    return root / "历史漏洞"


# ===========================================================================
# 1. 数据模型
# ===========================================================================

@dataclass
class VulnRecord:
    """一条历史漏洞的结构化记录（从 kb/历史漏洞/*.json 抽取）。"""
    case_id: str
    avd_id: str
    cwe: str
    risk: str
    methods: list[str] = field(default_factory=list)   # trigger.method.value
    fields: list[str] = field(default_factory=list)     # trigger.field.value（归一化）
    condition: str = ""                                 # trigger.condition.value
    description: str = ""                               # description_raw


@dataclass
class VulnSeedReq:
    """一条漏洞 → 一个「合法边界种子」生成需求。"""
    case_id: str
    cwe: str
    methods: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    action: str = "default"                             # 动作类型（见 _ACTION_GUIDANCE）
    guidance: str = ""                                  # 合法边界覆盖指引（喂 LLM）
    streams: list[str] = field(default_factory=list)    # 漏洞触发流（资源清单流名，过滤崩溃流）


# ===========================================================================
# 2. 加载：读 kb/历史漏洞/*.json
# ===========================================================================

def load_vuln_kb(data_root: Optional[Path] = None,
                 protocol: Optional[str] = None) -> list[VulnRecord]:
    """读结构化漏洞记录（49 条）。

    协议×源二维解耦：protocol 给定时读 kb/<protocol>/历史漏洞/；否则回退
    data_root（向后兼容旧单协议路径 kb/历史漏洞）。目录缺失/空时返回 []。

    Returns:
        list[VulnRecord] 按 case_id 排序。
    """
    if protocol:
        from core import paths
        d = paths.kb_source_dir(protocol, "vuln")
    else:
        d = _vuln_dir(data_root)
    if not d.is_dir():
        return []
    out: list[VulnRecord] = []
    for f in sorted(d.glob("*.json")):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        trig = raw.get("trigger", {}) or {}
        mval = (trig.get("method") or {}).get("value") or []
        fval = (trig.get("field") or {}).get("value") or []
        methods = [m for m in (mval if isinstance(mval, list) else [mval]) if m]
        fields = [normalize_field(x) for x in (fval if isinstance(fval, list) else [fval])
                  if x and normalize_field(x)]
        out.append(VulnRecord(
            case_id=str(raw.get("case_id", f.stem)),
            avd_id=str(raw.get("avd_id", "")),
            cwe=str(raw.get("cwe_avd", "") or ""),
            risk=str(raw.get("risk_level_avd", "") or ""),
            methods=[m.upper() for m in methods],
            fields=sorted(set(fields)),
            condition=str((trig.get("condition") or {}).get("value") or ""),
            description=str(raw.get("description_raw", "") or ""),
        ))
    out.sort(key=lambda v: v.case_id)
    return out


# 动作 → 合法边界覆盖指引（LLM prompt 用，占位符 {fields} 后填）
_ACTION_GUIDANCE = {
    "empty_edge": "字段 {fields} 用「最小合法值」边界（如空参数列表 / client_port=0-0 / 最短 Session token），"
                  "使 fuzzer 能向空值/缺失方向变异",
    "long_value": "字段 {fields} 用「长但语法合法」的值（约 128~256 字符的 hex 串/字符串，"
                  "不要用超长 AAAA 填充），使 fuzzer 能向溢出方向变异",
    "int_edge": "数值字段 {fields} 用边界值（0 / 1 / 2^31-1 / 最大值）覆盖整数溢出边界",
    "uaf_seq": "生成「SETUP → TEARDOWN」的会话建立与终止合法序列（勿在 TEARDOWN 后再 SETUP——释放后使用留给 fuzzer 变异探索；传输方式会话内保持一致，不做 interleaved 与非 interleaved 的切换）",
    "lifecycle_seq": "生成「建立会话 → 终止会话」的生命周期合法序列（勿重建会话——重建后引用已释放资源会触发释放后使用，留给 fuzzer 变异探索）",
    "assert_seq": "生成「多次重复 SETUP 与 PLAY」的合法序列（触发可达断言路径）",
    "many_params": "SETUP 的 Transport 用「多个 client_port 参数对」（3~5 对）的合法请求",
    "replay_seq": "生成「连续两条相同 CSeq」或「反复发送认证请求」的合法序列（测试重放/认证限制）",
    "path_edge": "uri / stream 用边界路径（如 ../、%2e%2e、重复斜杠等合法字符）的合法请求",
    "auth_edge": "生成「携带 Digest 认证头」与「不带认证头」两种边界的合法请求",
    "inject_edge": "字段 {fields} 用含特殊字符但语法合法的值",
    "double_setup": "生成「对不同 track 分别 SETUP」的多轨合法序列（如 track1、track2；勿对同一 track 连续两次 SETUP——这会直接触发释放后使用，同 track 双 SETUP 留给 fuzzer 变异探索）",
    "interleave_seq": "生成「使用 RTP/AVP/TCP interleaved 传输的 SETUP」合法序列（会话内传输方式保持一致，勿做 interleaved 与非 interleaved 的切换——切换会直接触发目标崩溃，应留给 fuzzer 变异去探索）",
    "abs_time_seek": "生成 PLAY 带「Range: clock=绝对时间」的合法 seek 序列",
    "multi_session": "生成「用有效 Session token 从第二个连接发 PLAY/TEARDOWN」的合法序列",
    "default": "覆盖该方法的完整状态路径，字段用多种合法取值",
}


def classify_vuln(v: VulnRecord, protocol: str = "rtsp") -> VulnSeedReq:
    """把一条漏洞翻译成「合法边界种子」需求。

    action 识别（触发条件关键词 + CWE 编号 → action）复用
    core.fused.vuln_pattern.classify_action（唯一真源）；本函数只补 guidance
    （合法边界覆盖指引）与触发流提取。

    protocol 透传给 extract_stream_hints：触发流映射来自 profile 的 vuln 段
    （协议特定），换协议必须传目标协议，否则退化为 RTSP 流名映射。

    返回 VulnSeedReq，其 guidance 是可喂给 LLM 的一行覆盖指引。
    """
    text = f"{v.condition} {v.description}"
    action = classify_action(v.cwe, v.condition, v.description)

    guidance = _ACTION_GUIDANCE.get(action, _ACTION_GUIDANCE["default"])
    if "{fields}" in guidance:
        f = "、".join(v.fields) if v.fields else "（未指明字段：任选一个合法头部字段）"
        guidance = guidance.replace("{fields}", f)

    # 提取漏洞「触发流」（condition 里常写 "Matroska/Ogg 同一 track..." 等）
    streams = extract_stream_hints(text, protocol=protocol)

    return VulnSeedReq(
        case_id=v.case_id,
        cwe=v.cwe or "(无 CWE)",
        methods=v.methods,
        fields=v.fields,
        action=action,
        guidance=guidance,
        streams=streams,
    )


def classify_all(vulns: list[VulnRecord], protocol: str = "rtsp") -> list[VulnSeedReq]:
    """批量分类，保持稳定序（按 case_id）。protocol 透传 classify_vuln。"""
    return [classify_vuln(v, protocol=protocol) for v in vulns]


def dedupe_reqs(reqs: list[VulnSeedReq]) -> list[VulnSeedReq]:
    """按 (action, methods, fields, streams) 去重漏洞需求，合并 case_id。

    多条 CVE 常共享同一漏洞模式（如多个「认证头超长溢出」），去重后
    每个「漏洞模式」只产一个合法边界种子，避免 49 条 CVE 逐条生成导致
    prompt 过长 / 种子冗余。合并的 case_id 保留在返回需求的 case_id 字段
    （分号连接），用于种子溯源。

    streams 纳入 key：同 action 但不同触发流（如 Matroska vs MP3 的双 SETUP）
    是不同漏洞模式，不能合并——这正是「触发流丢失」缺陷的修复点。
    """
    grouped: dict[tuple, list[VulnSeedReq]] = {}
    for r in reqs:
        key = (r.action, tuple(r.methods), tuple(r.fields), tuple(r.streams))
        grouped.setdefault(key, []).append(r)
    out: list[VulnSeedReq] = []
    for _, grp in grouped.items():
        grp = sorted(grp, key=lambda x: x.case_id)
        merged = VulnSeedReq(
            case_id=";".join(g.case_id for g in grp),
            cwe=grp[0].cwe,
            methods=grp[0].methods,
            fields=grp[0].fields,
            action=grp[0].action,
            guidance=grp[0].guidance,
            streams=grp[0].streams,
        )
        out.append(merged)
    out.sort(key=lambda r: r.case_id)
    return out


# ===========================================================================
# 4. 导向判定（自适应）
# ===========================================================================

def determine_strategies(bundle: dict,
                         resources: Optional[list] = None,
                         request_templates: Optional[dict] = None,
                         vulns: Optional[list[VulnRecord]] = None) -> dict:
    """按知识中枢实际有哪些源，返回激活的导向（对齐 design §三）。

    Returns:
        {"normal": [...], "attack": [...], "constraints": [...]}
          - constraints: 贯穿约束（traffic_guided，有请求模板即启用）
          - normal:      覆盖目标（instance/structure/state_machine）
          - attack:      独立策略（vulnerability_guided，有漏洞即启用）
    """
    strategies: dict = {"normal": [], "attack": [], "constraints": []}
    if request_templates:
        strategies["constraints"].append("traffic_guided")
    if resources:
        strategies["normal"].append("instance_guided")
    if bundle.get("methods") and bundle.get("required_headers"):
        strategies["normal"].append("structure_guided")
    if bundle.get("transitions"):
        strategies["normal"].append("state_machine_guided")
    if vulns:
        strategies["attack"].append("vulnerability_guided")
    return strategies


# ===========================================================================
# 5. 渲染漏洞导向 prompt + 生成攻击种子
# ===========================================================================

def _render_reqs(reqs: list[VulnSeedReq]) -> str:
    """把漏洞需求列表渲染成「漏洞导向生成要求」区段。"""
    if not reqs:
        return "(无漏洞需求)"
    lines = ["（种子必须绝对合法，仅以下述合法边界覆盖漏洞相关字段/序列/边界）"]
    for r in reqs:
        methods = "+".join(r.methods) if r.methods else "any"
        stream_hint = ""
        if r.streams:
            stream_hint = f"；流名必须用 {'/'.join(r.streams)}"
        lines.append(
            f"  [{r.case_id} · {r.cwe}] 方法={methods} → {r.guidance}{stream_hint}")
    return "\n".join(lines)


def _render_url_rule(protocol: str) -> str:
    """按协议 raw_format 返回 URL/参数约束（头部协议用 URL，行命令协议用 argument）。"""
    from core import paths
    import json
    prof = paths.target_profile(protocol)
    rf: dict = {}
    if prof.exists():
        try:
            rf = (json.loads(prof.read_text(encoding="utf-8")) or {}).get("raw_format") or {}
        except (json.JSONDecodeError, OSError):
            rf = {}
    if "{url}" in rf.get("request_line", ""):
        return "URL 结构按模板，URL/流名必须用真实流名，边界值只放头部字段、绝不放进 URL/流名"
    return "命令参数（argument）按协议语义填真实值（用户名/路径/文件名），边界值只放参数、不破坏命令结构"


def render_attack_prompt(bundle: dict, reqs: list[VulnSeedReq], *,
                         protocol: str,
                         resources: Optional[list] = None,
                         request_templates: Optional[dict] = None) -> tuple[str, str]:
    """渲染漏洞导向的 (system, user) prompt。复用分桶知识 + 追加漏洞需求。

    与 render_seed_prompt 的区别：生成目标段改为「按漏洞需求生成合法边界种子」，
    硬性规则保持一致（方法白名单 / 状态转移 / 必填头 / 请求模板真实性）。
    """
    from .rag_seedgen import (
        _render_methods, _render_transitions, _render_required,
        _render_values, _render_request_templates, _render_session_semantics,
        _render_security, _render_vuln_guidance, _render_constraints,
        _output_format_example,
    )
    system = (f"你是 {protocol} 协议 fuzz 测试专家，基于历史漏洞信息生成"
              f"「绝对合法」的边界种子（不是畸形触发报文）。")
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

[安全关注（来自历史漏洞与专家判断）]
{_render_security(bundle['security'])}

[漏洞导向生成要求]
{_render_reqs(reqs)}
"""
    if bundle.get("security"):
        user += f"""
{_render_vuln_guidance(bundle['security'])}
"""
    if request_templates:
        user += f"""
{_render_request_templates(request_templates)}
"""
    user += f"""
[生成目标]
- 协议: {protocol}
- 每个漏洞需求生成 1 个「合法边界会话种子」，覆盖该需求指定的方法与字段边界
- 所有消息必须满足协议结构（方法/状态转移/必填头）与真实请求模板

[输出要求]
返回一个 JSON 对象（不要用 markdown 代码块包裹），格式:
{{"seeds": [
  {_output_format_example(protocol)}
]}}
共生成 {len(reqs)} 个边界种子（每个漏洞需求至少 1 个）。

硬性规则（与正常种子完全一致，缺一不可）:
1. method 必须在 [协议方法] 里
2. 状态转移要合法（参考 [状态机转移]）
3. 必填字段不能少（参考 [必填字段]）
4. 取值优先从 [字段取值池] 选，数值字段用边界值(0/-1/MAX/空串/超长)
5. 会话语义严格参照 [会话语义（来自知识中枢）] 区段：前置方法不可省略、会话头按第 N 次出现规则携带；{_render_url_rule(protocol)}
6. 种子必须**绝对合法**——只覆盖漏洞相关字段/序列/边界，不写会让目标崩溃的畸形值
7. 单个字段值长度 ≤ 256 字符（禁止生成 AAAA... 等超长填充串；长度边界由 fuzzer 变异探索，种子只需「合法且偏长」）"""
    if resources:
        user += """
8. 流名约束：漏洞需求若标注了「流名必须用 X」，必须用该流名；流名只允许用安全流，**禁止用 amrAudioTest / aacAudioTest / ac3AudioTest**（这三个流会导致目标服务器崩溃）"""
    return system, user


def generate_attack_seeds(bundle: dict, llm, reqs: list[VulnSeedReq], *,
                          protocol: str = "rtsp",
                          resources: Optional[list] = None,
                          request_templates: Optional[dict] = None,
                          max_rounds: int = 2) -> list:
    """漏洞导向攻击种子：生成 → 校验 → 带错重生成（复用 validate_seed）。

    只保留通过知识中枢校验的**合法**种子；解析失败/校验失败进入下一轮带错重生成。
    """
    from .rag_seedgen import parse_seed_response, validate_seed

    if not reqs:
        return []
    system, user = render_attack_prompt(bundle, reqs, protocol=protocol,
                                        resources=resources,
                                        request_templates=request_templates)
    seeds: list = []
    for _round in range(max(1, max_rounds)):
        try:
            resp = llm.chat_json(system=system, user=user,
                                 temperature=0.3, max_tokens=8000)
        except Exception:
            continue  # JSON 解析失败（如截断），带错重试下一轮而非直接放弃
        parsed = parse_seed_response(resp, protocol, [], [])
        if not parsed:
            continue
        bad = {i: validate_seed(s, bundle) for i, s in enumerate(parsed)}
        bad = {i: e for i, e in bad.items() if e}
        good = [s for i, s in enumerate(parsed) if i not in bad]
        if good:
            seeds = good
        if not bad:
            break
        feedback = "\n".join(
            f"种子[{i}]: " + "；".join(errs) for i, errs in sorted(bad.items()))
        user = user + "\n\n[上一轮校验错误，请严格修正]\n" + feedback
    # 标记为攻击种子，便于溯源
    for s in seeds:
        s.generated_by = "hub-rag-v2:attack"
        if s.target_vuln_class == "":
            s.target_vuln_class = ";".join(r.case_id for r in reqs)
    return seeds


__all__ = [
    "VulnRecord",
    "VulnSeedReq",
    "load_vuln_kb",
    "classify_vuln",
    "classify_all",
    "dedupe_reqs",
    "determine_strategies",
    "render_attack_prompt",
    "generate_attack_seeds",
]
