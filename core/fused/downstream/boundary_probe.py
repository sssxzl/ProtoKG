"""core/fused/downstream/boundary_probe.py —— 边界探针：主动寻找「合法边界」。

「合法边界」= 仍合法（目标服务器正常处理、不崩溃），但离非法（触发漏洞）最近的点，
使 fuzzer 只需 1~2 次变异即能触发漏洞。

双源（统一为边界参数）：
  源 A 协议语义驱动（无漏洞库也工作）：generic_danger 的自环/生命周期/字段取值域
  源 B 漏洞知识驱动（有漏洞库更精确）：classify_vuln 的 action + 触发流

本模块先实现源 B（有漏洞库）：从 action 推导边界参数 → 生成边界候选种子 →
用 oracle（重放判定合法/非法）定位合法边界。源 A（协议语义驱动，无需漏洞库）已实现, 见本文件 derive_semantic_candidates。
"""
from __future__ import annotations

from typing import Optional

from core.models import SeedCorpus, SeedMessage
from core.fused.vuln_pattern import BoundaryParam, _ACTION_BOUNDARY


def derive_boundary_param(req) -> Optional[BoundaryParam]:
    """从 VulnSeedReq.action 推导边界参数（源 B）。无对应 action 返回 None。"""
    return _ACTION_BOUNDARY.get(getattr(req, "action", ""))


# ===========================================================================
# 2. 边界候选生成（对每个 action 生成「合法端点」+「非法端点」候选种子）
# ===========================================================================

def _msg(method: str, url: str, headers: dict) -> SeedMessage:
    return SeedMessage(method=method, headers=headers, body="", url=url)


def _url_base(protocol: str) -> str:
    """从 profile.json 的 default_url 读 URL base（协议特定），缺省回退 RTSP。

    避免硬编码 `rtsp://127.0.0.1:8554`——换协议（如 SIP 的 sip:127.0.0.1:5060）
    时由 profile 提供，通用层零协议内置。
    """
    from core import paths
    import json
    prof = paths.target_profile(protocol)
    if prof.exists():
        try:
            data = json.loads(prof.read_text(encoding="utf-8")) or {}
            du = (data.get("default_url") or "").rstrip("/")
            if du:
                return du
        except (json.JSONDecodeError, OSError):
            pass
    return "rtsp://127.0.0.1:8554"


def _describe_msg(stream: str, cseq: int, url_base: str = "rtsp://127.0.0.1:8554") -> SeedMessage:
    return _msg("DESCRIBE", f"{url_base}/{stream}",
                {"CSeq": str(cseq), "Accept": "application/sdp"})


def _setup_msg(stream: str, track: int, cseq: int, with_session: bool,
               session: str = "{{session_id}}",
               url_base: str = "rtsp://127.0.0.1:8554") -> SeedMessage:
    h = {"CSeq": str(cseq),
         "Transport": "RTP/AVP;unicast;client_port=50000-50001"}
    if with_session:
        h["Session"] = session
    return _msg("SETUP", f"{url_base}/{stream}/track{track}", h)


# 真实触发 Session 值：对照实验证实 Session=000022B8(=8888, 崩溃栈 clientSessionId=8888)
# 是 matroska UAF 触发关键，占位符解析的 12345678 不触发。illegal 候选需用此真实值。
# 注：这是 RTSP 特定的漏洞触发值，序列型漏洞模式（double_setup 等）本身是 RTSP 特有。
_TRIGGER_SESSION = "000022B8"


def generate_candidates(req, stream: str = "matroskaFileTest",
                        protocol: str = "rtsp") -> list[tuple[str, SeedCorpus]]:
    """生成边界候选种子，返回 [(label, seed), ...]。

    label ∈ {"legal"(合法域), "illegal"(非法域)}。每个候选由 DESCRIBE 前缀 + 目标序列构成。
    只实现已映射的序列型 action（double_setup/uaf_seq/lifecycle_seq/interleave_seq），
    其余返回空列表（后续扩展）。

    protocol 用于从 profile 读 URL base（default_url），缺省回退 RTSP。

    ★技术债（2026-10-21，有意保留，非遗漏）：
    序列型 action（同 track 双 SETUP / transport 切换 / 重建会话）目前是 RTSP/live555
    特有漏洞模式，其消息结构（SETUP/TEARDOWN/DESCRIBE 方法、track{N} 命名、Transport/
    Session 头、触发 Session 值 _TRIGGER_SESSION）仍以 RTSP 为模板硬编码。
    —— 为什么现在不抽象成 profile DSL：当前只有 RTSP 有序列型漏洞，SMTP/FTP/SIP 全是
       字段型漏洞（走已协议化的 _field_action_candidates）。为唯一使用者建一套
       「序列型候选消息结构 DSL」属过度设计（YAGNI），且抽象的边界应由第二个真实
       使用场景决定，提前拍脑袋设计大概率抽象错方向。
    —— 何时升级：当任一条件成立时，把上述消息结构下沉到 profile.json 的 boundary_probe 段
       （url_template/methods/track_rule/trigger_session/transport）：
        ① 有第二个协议（如 FTP「重复登录」、SMTP「重放认证」）的漏洞库出现序列型 action；
        ② 论文/演示主打「边界探针跨协议迁移」，需要它脱离 RTSP 也能跑。
    当前残留风险已被两层兜底封住：_url_base 协议化 URL base + selector 的方法白名单过滤
    （SETUP/DESCRIBE/TEARDOWN 不在非 RTSP 协议的 methods 里，序列型候选会被整体过滤）。
    """
    ub = _url_base(protocol)
    a = getattr(req, "action", "")
    if a == "double_setup":
        legal = SeedCorpus(
            description="boundary-candidate double_setup legal(不同 track)",
            target_methods=["DESCRIBE", "SETUP", "SETUP"], generated_by="rule-based:boundary-probe",
            messages=[_describe_msg(stream, 1, ub), _setup_msg(stream, 1, 2, False, url_base=ub),
                      _setup_msg(stream, 2, 3, True, url_base=ub)],
        )
        illegal = SeedCorpus(
            description="boundary-candidate double_setup illegal(同 track)",
            target_methods=["DESCRIBE", "SETUP", "SETUP"], generated_by="rule-based:boundary-probe",
            messages=[_describe_msg(stream, 1, ub), _setup_msg(stream, 1, 2, False, url_base=ub),
                      _setup_msg(stream, 1, 3, True, session=_TRIGGER_SESSION, url_base=ub)],
        )
        return [("legal", legal), ("illegal", illegal)]

    if a in ("uaf_seq", "lifecycle_seq"):
        legal = SeedCorpus(
            description=f"boundary-candidate {a} legal(不重建)",
            target_methods=["DESCRIBE", "SETUP", "TEARDOWN"], generated_by="rule-based:boundary-probe",
            messages=[_describe_msg(stream, 1, ub), _setup_msg(stream, 1, 2, False, url_base=ub),
                      _msg("TEARDOWN", f"{ub}/{stream}/", {"CSeq": "3", "Session": "{{session_id}}"})],
        )
        illegal = SeedCorpus(
            description=f"boundary-candidate {a} illegal(重建)",
            target_methods=["DESCRIBE", "SETUP", "TEARDOWN", "SETUP"], generated_by="rule-based:boundary-probe",
            messages=[_describe_msg(stream, 1, ub), _setup_msg(stream, 1, 2, False, session=_TRIGGER_SESSION, url_base=ub),
                      _msg("TEARDOWN", f"{ub}/{stream}/", {"CSeq": "3", "Session": _TRIGGER_SESSION}),
                      _setup_msg(stream, 1, 4, True, session=_TRIGGER_SESSION, url_base=ub)],
        )
        return [("legal", legal), ("illegal", illegal)]

    if a == "interleave_seq":
        legal = SeedCorpus(
            description="boundary-candidate interleave_seq legal(不切换)",
            target_methods=["DESCRIBE", "SETUP"], generated_by="rule-based:boundary-probe",
            messages=[_describe_msg(stream, 1, ub),
                      _msg("SETUP", f"{ub}/{stream}/track1",
                           {"CSeq": "2", "Transport": "RTP/AVP/TCP;unicast;interleaved=0-1"})],
        )
        illegal = SeedCorpus(
            description="boundary-candidate interleave_seq illegal(切换)",
            target_methods=["DESCRIBE", "SETUP", "SETUP"], generated_by="rule-based:boundary-probe",
            messages=[_describe_msg(stream, 1, ub),
                      _msg("SETUP", f"{ub}/{stream}/track1",
                           {"CSeq": "2", "Transport": "RTP/AVP/TCP;unicast;interleaved=0-1"}),
                      _msg("SETUP", f"{ub}/{stream}/track1",
                           {"CSeq": "3", "Transport": "RTP/AVP;unicast;client_port=50000-50001",
                            "Session": _TRIGGER_SESSION})],
        )
        return [("legal", legal), ("illegal", illegal)]

    return []


# ===========================================================================
# 3. 源 A：协议语义驱动的边界候选（无需漏洞库）
# ===========================================================================

def derive_semantic_candidates(bundle: dict, stream: str = "matroskaFileTest",
                               methods: tuple = ("SETUP",)) -> list[tuple[str, SeedCorpus]]:
    """源 A：从协议语义（状态机自环/生命周期）推导边界候选，不依赖漏洞库。

    核心思想：协议设计特征天然蕴含危险点——
      - 自环 X --M--> X：同一状态下重复方法 M 是 UAF/资源管理风险点。
        边界 = 单次 M（合法）vs 重复 M（可能越界）。
    用 oracle 验证后，即可在没有漏洞先验的情况下主动定位合法边界。

    Returns:
        list[(label, seed)]，label ∈ {"legal", "illegal"}。
    """
    transitions = bundle.get("transitions", []) or []
    candidates: list = []

    # 1. 自环重复边界：对每个方法自环 X --M--> X，生成「单次 M vs 重复 M」
    seen = set()
    for src, m, dst in transitions:
        if src != dst or m not in methods or m in seen:
            continue
        seen.add(m)
        legal = SeedCorpus(
            description=f"semantic-boundary self-loop {m} legal(单次)",
            target_methods=["DESCRIBE", m], generated_by="rule-based:boundary-probe-semantic",
            messages=[_describe_msg(stream, 1), _setup_msg(stream, 1, 2, False)],
        )
        illegal = SeedCorpus(
            description=f"semantic-boundary self-loop {m} illegal(重复)",
            target_methods=["DESCRIBE", m, m], generated_by="rule-based:boundary-probe-semantic",
            messages=[_describe_msg(stream, 1), _setup_msg(stream, 1, 2, False),
                      _setup_msg(stream, 1, 3, True, session=_TRIGGER_SESSION)],
        )
        candidates.append(("legal", legal))
        candidates.append(("illegal", illegal))

    # 2. 生命周期边界：进入边 A--M_in-->B 与离开边 B--M_out-->A 配对，
    #    生成「进入→离开（不重建）vs 进入→离开→再进入（重建）」候选
    seen_life = set()
    for a, m_in, b in transitions:
        if m_in not in methods:
            continue
        for b2, m_out, a2 in transitions:
            if b2 == b and a2 == a and m_out == "TEARDOWN":
                key = (a, b)
                if key in seen_life:
                    continue
                seen_life.add(key)
                legal = SeedCorpus(
                    description=f"semantic-boundary lifecycle {a}->{b} legal(不重建)",
                    target_methods=["DESCRIBE", m_in, m_out], generated_by="rule-based:boundary-probe-semantic",
                    messages=[_describe_msg(stream, 1), _setup_msg(stream, 1, 2, False),
                              _msg("TEARDOWN", f"rtsp://127.0.0.1:8554/{stream}/",
                                   {"CSeq": "3", "Session": "{{session_id}}"})],
                )
                illegal = SeedCorpus(
                    description=f"semantic-boundary lifecycle {a}->{b} illegal(重建)",
                    target_methods=["DESCRIBE", m_in, m_out, m_in], generated_by="rule-based:boundary-probe-semantic",
                    messages=[_describe_msg(stream, 1), _setup_msg(stream, 1, 2, False, session=_TRIGGER_SESSION),
                              _msg("TEARDOWN", f"rtsp://127.0.0.1:8554/{stream}/",
                                   {"CSeq": "3", "Session": _TRIGGER_SESSION}),
                              _setup_msg(stream, 1, 4, True, session=_TRIGGER_SESSION)],
                )
                candidates.append(("legal", legal))
                candidates.append(("illegal", illegal))

    return candidates


# ===========================================================================
# 4. 边界探针：oracle 判定 + 定位合法边界
# ===========================================================================

def extract_session_candidates(protocol: str = "rtsp") -> list:
    """从真实流量模板自动提取 Session 候选值（触发值来源，替代硬编码）。

    思想来源：AFL dictionary 机制——触发值应从语料自动提取，而非手写。
    """
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    path = root / "fused_hub" / "targets" / f"{protocol}_request_templates.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    sessions: set = set()
    for info in (data.get("methods") or {}).values():
        examples = (info or {}).get("examples") or {}
        for v in examples.get("Session") or []:
            sessions.add(str(v))
    return sorted(sessions)


def search_trigger_value(req, oracle, stream: str = "matroskaFileTest") -> Optional[str]:
    """搜索触发值：从真实流量提取 Session 候选，oracle 验证哪个触发崩溃。

    思想来源：Delta Debugging（Zeller）——用 test()（即 oracle）+ 候选集定位「失败诱导」值，
    而非硬编码触发值。对每个候选 Session 值构造「同 track 双 SETUP」的非法候选，
    首个触发崩溃的值即该漏洞的触发值。
    """
    sessions = extract_session_candidates()
    for sess in sessions:
        illegal = SeedCorpus(
            description=f"trigger-search {getattr(req, 'action', '')} session={sess}",
            target_methods=["DESCRIBE", "SETUP", "SETUP"], generated_by="rule-based:boundary-probe",
            messages=[_describe_msg(stream, 1), _setup_msg(stream, 1, 2, False),
                      _setup_msg(stream, 1, 3, True, session=sess)],
        )
        if not oracle(illegal):  # 非法（崩溃）→ 这是触发值
            return sess
    return None

def binary_search_boundary(gen_seed, lo: int, hi: int, oracle):
    """对连续/有序维度做二分，定位「最大合法值」（最接近非法的合法边界）。

    思想来源：Delta Debugging（Zeller, ISSTA'2000 / TSE'2002）的 ddmin 二分思想。
    gen_seed(k) 生成参数为 k 的种子；oracle(seed) 判定合法(True)/非法(False)。
    返回 (边界值, 边界种子)；若 lo 本身就非法则返回 None。
    """
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        seed = gen_seed(mid)
        if oracle(seed):
            best = (mid, seed)
            lo = mid + 1  # 合法 → 试探更大的值
        else:
            hi = mid - 1  # 非法 → 回退更小的值
    return best


def derive_field_candidates(bundle: dict, stream: str = "matroskaFileTest") -> list:
    """源 A 第三类：字段取值域边界候选（数值字段的合法值 vs 边界值）。

    注意：字段边界值（0/-1/MAX/空）多为「覆盖边界」（覆盖更多取值，不崩溃），
    而非「崩溃边界」。oracle 判定后自然区分：判 ILLEGAL 的才是崩溃边界。
    """
    headers = bundle.get("headers") or {}
    candidates: list = []
    numeric_names = {"cseq", "content-length", "bandwidth", "blocksize",
                     "scale", "speed", "rtptime", "seq"}
    for name, info in headers.items():
        if name.lower() not in numeric_names:
            continue
        # 合法值 vs 边界值（MAX / 空）
        legal = SeedCorpus(
            description=f"semantic-boundary field {name} legal(正常值)",
            target_methods=["DESCRIBE"], generated_by="rule-based:boundary-probe-semantic",
            messages=[_describe_msg(stream, 1)],
        )
        illegal = SeedCorpus(
            description=f"semantic-boundary field {name} illegal(边界值 MAX)",
            target_methods=["DESCRIBE"], generated_by="rule-based:boundary-probe-semantic",
            messages=[_msg("DESCRIBE", f"rtsp://127.0.0.1:8554/{stream}",
                           {"CSeq": "2147483647", "Accept": "application/sdp"})],
        )
        candidates.append(("legal", legal))
        candidates.append(("illegal", illegal))
    return candidates


def _build_baseline(stream: str = "matroskaFileTest") -> SeedCorpus:
    """构造合法基线：完整多轨会话（DESCRIBE + SETUP track1 + SETUP track2 + PLAY + TEARDOWN）。

    基线是「确定合法」的完整会话，字段空间探测从它出发做变异。
    """
    return SeedCorpus(
        description="baseline full multi-track session",
        target_methods=["DESCRIBE", "SETUP", "SETUP", "PLAY", "TEARDOWN"],
        generated_by="rule-based:field-probe",
        messages=[
            _describe_msg(stream, 1),
            _setup_msg(stream, 1, 2, False),
            _setup_msg(stream, 2, 3, True),
            _msg("PLAY", f"rtsp://127.0.0.1:8554/{stream}/",
                 {"CSeq": "4", "Session": "{{session_id}}", "Range": "npt=0.000-"}),
            _msg("TEARDOWN", f"rtsp://127.0.0.1:8554/{stream}/",
                 {"CSeq": "5", "Session": "{{session_id}}"}),
        ],
    )


def probe_field_space(baseline: SeedCorpus, bundle: dict, oracle) -> list:
    """更彻底的自动发现：不预设「边界在哪个维度」，而是从合法基线出发，
    对字段做定向变异，oracle 检测哪个变异触发崩溃。

    思想来源：Delta Debugging（Zeller）——只给 oracle 不给答案，让它自己找失败诱导输入。
    变异候选来自基线字段结构（track 同化 / Transport 切换 / Session 取值池），
    而非人工预设「track 是边界」。

    Returns:
        list[(dim, original, mutated_value, seed)] —— 触发崩溃的字段变异。
    """
    import copy
    crashes: list = []

    # 变异维度 1：track 同化 —— 把后续 SETUP 的 track 改成与第一个相同
    setups = [m for m in baseline.messages if m.method == "SETUP"]
    if len(setups) >= 2:
        for i in range(1, len(setups)):
            mutated = copy.deepcopy(baseline)
            idx = baseline.messages.index(setups[i])
            mutated.messages[idx].url = setups[0].url  # 同 track
            if not oracle(mutated):
                crashes.append(("track_number",
                                setups[i].url.split("/")[-1],
                                setups[0].url.split("/")[-1], mutated))

    # 变异维度 2：Transport 切换 —— interleaved ↔ unicast
    for i, m in enumerate(baseline.messages):
        if m.method != "SETUP":
            continue
        transport = m.headers.get("Transport", "")
        alt = ("RTP/AVP;unicast;client_port=50000-50001" if "interleaved" in transport
               else "RTP/AVP/TCP;unicast;interleaved=0-1")
        mutated = copy.deepcopy(baseline)
        mutated.messages[i].headers["Transport"] = alt
        if not oracle(mutated):
            crashes.append(("transport", transport[:24], alt[:24], mutated))

    # 变异维度 3：Session 触发值 —— 从真实流量取值池
    for sess in extract_session_candidates():
        mutated = copy.deepcopy(baseline)
        for m in mutated.messages:
            if "Session" in m.headers:
                m.headers["Session"] = sess
        if not oracle(mutated):
            crashes.append(("session", "{{session_id}}", sess, mutated))

    return crashes


def probe_boundary(candidates: list[tuple[str, SeedCorpus]], oracle) -> Optional[SeedCorpus]:
    """用 oracle 判定每个候选的合法/非法，返回「合法边界」种子。

    规则：在所有 oracle 判定为「合法」的候选中，选「最接近非法」的那个。
    对当前离散候选（legal/illegal 两个端点）：
      - illegal 端点若被 oracle 判为「非法」（崩溃）→ 说明非法域确实越界；
      - legal 端点被判为「合法」→ 它就是合法边界（离非法最近）。
    Returns:
        合法边界种子；若无合法候选返回 None。
    """
    verdicts = []
    for label, seed in candidates:
        ok = oracle(seed)  # True=合法(不崩), False=非法(崩)
        verdicts.append((label, seed, ok))

    legal_seeds = [s for l, s, ok in verdicts if ok]
    if not legal_seeds:
        return None
    # 离散场景：legal 端点即边界；若还有更细的候选，这里可扩展为「合法里最接近非法」的选择
    return legal_seeds[-1]


def emit_boundary_fact(method: str, dim: str, legal_desc: str, illegal_desc: str,
                       trigger: str, authority: str = "boundary_probe",
                       protocol: str = "rtsp") -> dict:
    """把探测到的合法边界转成 legal_boundary fact（回写知识中枢，形成闭环）。

    探测结果 → 知识原子（subject=method, aspect=legal_boundary, value={dim,legal,illegal,trigger}），
    后续种子生成可直接复用，无需重新探测。protocol 写入 fact_key（换协议回写正确协议）。
    """
    import hashlib
    import json
    subject = {"type": "method", "name": method, "qualifiers": {}, "path": []}
    fact_key = {"protocol": protocol, "version": "1.0", "subject": subject,
                "aspect": "legal_boundary", "condition": {"type": "always"}}
    value = {"type": "struct", "data": {"dim": dim, "legal": legal_desc,
                                        "illegal": illegal_desc, "trigger": trigger}}
    fact_id = "f2_" + hashlib.md5(
        json.dumps(fact_key, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    claim_id = "c2_" + hashlib.md5(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    claim = {"claim_id": claim_id, "fact_id": fact_id, "value": value,
             "epistemic_type": "observed", "authority": authority, "scope": None,
             "evidence_summary": [f"{authority}:{method}.legal_boundary.{dim}"],
             "confidence": None}
    return {"fact_key": fact_key, "resolution": None, "all_claims": [claim]}


def generate_dict(bundle: dict, resources: Optional[list] = None) -> str:
    """从知识中枢自动生成 AFL 字典（增强版，替代硬编码 rtsp.dict）。

    字典 token 来源（思想来源：AFL dictionary 机制 + GitHub Security Lab 字典富集）：
      1. 方法名（bundle["methods"]）
      2. 字段取值池（bundle["headers"].values）—— Transport/Session/CSeq 等真实取值
      3. URL 模板 → track1/track2（同 track 双 SETUP 触发 UAF 的关键 token）
      4. Session 触发值 + "Session: X" 组合
      5. 流名（资源清单）
      6. 边界知识补充 token：interleaved=0-1 / client_port / 字段边界值
    """
    tokens: set = set()
    # 1. 方法名
    for m in bundle.get("methods", {}):
        tokens.add(str(m))
    # 2. 字段取值池
    for name, info in (bundle.get("headers") or {}).items():
        for v in (info.get("values") or []):
            v = str(v)
            if v and len(v) <= 64:
                tokens.add(v)
    # 3. URL 模板 → track1/track2（同 track 双 SETUP 的关键）
    if "track" in str(bundle.get("url_template", {}).get("SETUP", "")):
        tokens.add("track1")
        tokens.add("track2")
    # 4. Session 触发值 + 组合
    for sess in extract_session_candidates():
        tokens.add(sess)
        tokens.add(f"Session: {sess}")
    tokens.add("Session")
    # 5. 流名（资源清单）
    for r in (resources or []):
        name = r.get("name")
        if name:
            tokens.add(name)
    # 6. 边界知识补充 token（transport 切换 + 字段边界值）
    for t in ("interleaved=0-1", "client_port=50000-50001",
              "RTP/AVP/TCP;unicast;interleaved=0-1",
              "CSeq", "0", "-1", "2147483647"):
        tokens.add(t)
    # 过滤垃圾 token：含未解析占位符的、过长的
    tokens = {t for t in tokens if "{{" not in t and 0 < len(t) <= 48}
    return "\n".join(f'"{t}"' for t in sorted(tokens)) + "\n"


def generate_dict_minimal(bundle: dict, resources: Optional[list] = None) -> str:
    """生成精简增强字典：只保留「关键触发 token」+ 基础协议 token，去掉噪音。

    实验教训（2026-10-15）：63 token 的增强字典稀释了关键 token 的被选概率，
    导致崩溃发现反而不如 24 token 的 rtsp.dict。精简版聚焦「同 track 双 SETUP /
    transport 切换 / 触发 Session 值」这几个触发 UAF 的关键 token。
    """
    # 关键触发 token（同 track 双 SETUP UAF 的核心）
    tokens = {
        # 方法（RTSP 核心方法）
        "DESCRIBE", "SETUP", "PLAY", "TEARDOWN", "PAUSE", "OPTIONS",
        "GET_PARAMETER", "SET_PARAMETER",
        # 触发 UAF 的关键 token（track 同化 + transport 切换 + Session 值）
        "track1", "track2",
        "interleaved=0-1", "client_port=50000-50001",
        "RTP/AVP", "RTP/AVP/TCP", "RTP/AVP/UDP",
        "RTP/AVP/TCP;unicast;interleaved=0-1",
        "Session", "000022B8", "Session: 000022B8",
        # 基础协议 token
        "RTSP/1.0", "Transport", "CSeq", "Accept", "application/sdp",
        "Range", "Range: npt=0.000-", "127.0.0.1",
        # 漏洞流
        "matroskaFileTest",
    }
    # 从真实流量模板补 Session 候选值
    for sess in extract_session_candidates():
        tokens.add(sess)
    # 过滤（保留安全字符，避免含 {{ 或超长）
    tokens = {t for t in tokens if "{{" not in t and 0 < len(t) <= 48}
    return "\n".join(f'"{t}"' for t in sorted(tokens)) + "\n"


def generate_dict_balanced(bundle: dict, resources: Optional[list] = None) -> str:
    """折中字典：精简字典（关键触发 token）+ 少量覆盖性 token。

    实验教训（2026-10-16）：精简字典(30) 崩溃 +29%、发现效率 3.2 倍，但覆盖率 -0.13%
    （因缺 rtsp.dict 里的其他流名 token）。折中版在精简字典基础上补回「少量」覆盖性
    流名（wav/ac3/webm），期望覆盖率回升而不牺牲关键 token 浓度（30→约 35）。
    """
    tokens = {
        # 精简字典的关键触发 token（同 track 双 SETUP UAF 核心）
        "DESCRIBE", "SETUP", "PLAY", "TEARDOWN", "PAUSE", "OPTIONS",
        "GET_PARAMETER", "SET_PARAMETER",
        "track1", "track2",
        "interleaved=0-1", "client_port=50000-50001",
        "RTP/AVP", "RTP/AVP/TCP", "RTP/AVP/UDP",
        "RTP/AVP/TCP;unicast;interleaved=0-1",
        "Session", "000022B8", "Session: 000022B8",
        "RTSP/1.0", "Transport", "CSeq", "Accept", "application/sdp",
        "Range", "Range: npt=0.000-", "127.0.0.1",
        "matroskaFileTest",
        # 覆盖性 token（补回覆盖率）：rtsp.dict 的其他流名 + User-Agent
        "wavAudioTest", "ac3AudioTest", "webmFileTest", "User-Agent",
    }
    for sess in extract_session_candidates():
        tokens.add(sess)
    tokens = {t for t in tokens if "{{" not in t and 0 < len(t) <= 48}
    return "\n".join(f'"{t}"' for t in sorted(tokens)) + "\n"


def derive_constraint_candidates(bundle: dict, stream: str = "matroskaFileTest") -> list:
    """源 A 第四类：从 rfc 源抽取的字段约束（legal_boundary）推导边界候选。

    借鉴 SemFuzz：rfc 源抽出的「构造约束」（legal_boundary，{dim,legal,illegal,trigger}）
    天然给出「合法域 vs 非法域」。据此生成「满足约束（合法）vs 违反约束（非法）」候选：
      - 合法候选：正常消息（字段用合法值）
      - 非法候选：字段用「明显非法值」（超长字符串，违反长度约束）

    oracle 判定后：非法候选被判「越界」（崩溃）→ 该字段确实是崩溃边界；
    被判「合法」（服务器正常拒绝）→ 该约束只是「覆盖边界」而非「崩溃边界」。
    """
    boundaries = bundle.get("legal_boundary") or {}
    candidates: list = []
    for field, blist in boundaries.items():
        for b in blist:
            if not isinstance(b, dict):
                continue
            legal_desc = b.get("legal", "")
            illegal_desc = b.get("illegal", "")
            if not legal_desc or not illegal_desc:
                continue
            # 合法候选：正常 DESCRIBE（字段满足约束）
            legal = SeedCorpus(
                description=f"constraint-boundary {field} legal(满足约束)",
                target_methods=["DESCRIBE"], generated_by="rule-based:boundary-probe-constraint",
                messages=[_describe_msg(stream, 1)],
            )
            # 非法候选：字段用超长值（违反长度约束的通用方式）
            illegal = SeedCorpus(
                description=f"constraint-boundary {field} illegal(违反约束)",
                target_methods=["DESCRIBE"], generated_by="rule-based:boundary-probe-constraint",
                messages=[_msg("DESCRIBE", f"rtsp://127.0.0.1:8554/{stream}",
                               {"CSeq": "1", "Accept": "application/sdp",
                                field: "A" * 300})],
            )
            candidates.append(("legal", legal))
            candidates.append(("illegal", illegal))
    return candidates


# ===========================================================================
# 5. 漏洞模式（vuln_pattern）驱动的边界候选 + 定向字典 token（GLMFuzz 式）
# ===========================================================================

class _PatternReq:
    """轻量 req 适配：让 generate_candidates 能从 vuln_pattern 的 action 直接调用。"""

    def __init__(self, action: str):
        self.action = action
        self.case_id = ""


# 字段型 action → 字段边界值（触发「字段型」漏洞的字段取值，对齐 strategy._ACTION_GUIDANCE）
# 仅覆盖「字段值语义明确」的 action；语义复杂的（abs_time_seek/many_params/multi_session）
# 走 LLM 版（mutation_hint 引导）。
_FIELD_ACTION_EDGE = {
    "long_value": "A" * 128,               # 长但语法合法（128 字符，<256）
    "empty_edge": "",                      # 空值/最小合法值
    "int_edge": "2147483647",              # 整数边界 MAX
    "path_edge": "../",                    # 路径边界
    "inject_edge": "'; DROP TABLE--",      # 注入字符
}


def _field_action_candidates(pattern: dict, stream: str, protocol: str = "rtsp") -> list:
    """字段型漏洞模式 → 边界候选（字段值边界，非消息序列）。

    合法候选 = 方法不带该字段（正常值）；非法候选 = 方法带该字段 + 边界值（超长/空/MAX）。
    oracle 判定后：非法候选触发崩溃 → 该字段确是崩溃边界；否则只是覆盖边界。
    """
    field = pattern.get("trigger_field", "")
    action = pattern.get("action", "")
    edge_val = _FIELD_ACTION_EDGE.get(action)
    if not field or edge_val is None:
        return []
    method = (pattern.get("trigger_sequence") or ["DESCRIBE"])[0]
    # 按协议 raw_format 决定消息结构：头部协议用 url/headers，行命令协议用 argument
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
        # stream 为空（非 RTSP 协议）时不拼 /stream，避免 SIP 的 URL 被
        # RTSP 媒体名（matroskaFileTest）污染成 sip:host/matroskaFileTest。
        url = _url_base(protocol)
        if stream:
            url = f"{url}/{stream}"
        legal = SeedCorpus(
            protocol=protocol,
            description=f"vuln-field {action} {field} legal(正常值)",
            target_methods=[method], generated_by="rule-based:boundary-probe-vuln-field",
            messages=[_msg(method, url, {"CSeq": "1"})],
        )
        illegal = SeedCorpus(
            protocol=protocol,
            description=f"vuln-field {action} {field} illegal(边界值)",
            target_methods=[method], generated_by="rule-based:boundary-probe-vuln-field",
            messages=[_msg(method, url, {"CSeq": "1", field: edge_val})],
        )
    else:
        legal = SeedCorpus(
            protocol=protocol,
            description=f"vuln-field {action} {field} legal(正常值)",
            target_methods=[method], generated_by="rule-based:boundary-probe-vuln-field",
            messages=[SeedMessage(method=method, argument="")],
        )
        illegal = SeedCorpus(
            protocol=protocol,
            description=f"vuln-field {action} {field} illegal(边界值)",
            target_methods=[method], generated_by="rule-based:boundary-probe-vuln-field",
            messages=[SeedMessage(method=method, argument=str(edge_val))],
        )
    return [("legal", legal), ("illegal", illegal)]


def _llm_field_candidates(pattern: dict, bundle: dict, llm,
                          protocol: str = "rtsp") -> list:
    """字段型漏洞（字段值语义复杂 / 无 trigger_field）用 mutation_hint 引导 LLM 生成。

    复用 strategy.generate_attack_seeds：把漏洞模式转成 VulnSeedReq（guidance 用
    mutation_hint），LLM 生成「合法但接近边界」的种子（生成后经 validate_seed 校验）。
    """
    from .strategy import VulnSeedReq, generate_attack_seeds
    req = VulnSeedReq(
        case_id="", cwe=pattern.get("cwe", ""),
        methods=list(pattern.get("trigger_sequence") or []),
        fields=[pattern["trigger_field"]] if pattern.get("trigger_field") else [],
        action=pattern.get("action", ""),
        guidance=pattern.get("mutation_hint", "") or "覆盖该漏洞相关字段的边界取值",
        streams=list(pattern.get("streams") or []),
    )
    seeds = generate_attack_seeds(bundle, llm, [req], protocol=protocol)
    # generate_attack_seeds 产出的都是「合法边界种子」（接近漏洞边界但不触发）
    return [("legal", s) for s in seeds]


def derive_vuln_pattern_candidates(bundle: dict,
                                   stream: str = "matroskaFileTest",
                                   llm=None, protocol: str = "rtsp") -> list:
    """从 bundle 的 vuln_pattern 桶生成边界候选（漏洞模式 → 边界种子，GLMFuzz 式）。

    分两类：
      - 序列型（有 boundary）：复用 generate_candidates 的 legal/illegal 候选，按 action 去重；
      - 字段型（无 boundary）：规则版（long_value/empty_edge 等有明确字段值语义）产
        「正常值 vs 边界值」候选对，按 (action, trigger_field) 去重；语义复杂/无
        trigger_field 的字段型在 llm 传入时用 mutation_hint 引导 LLM 生成。

    Returns:
        [(label, SeedCorpus), ...]
    """
    patterns = bundle.get("vuln_pattern") or {}
    candidates: list = []
    seen: set = set()
    for _subject, plist in patterns.items():
        for p in plist:
            if not isinstance(p, dict):
                continue
            action = p.get("action", "")
            if not action:
                continue
            if action in _ACTION_BOUNDARY:  # 序列型（有边界参数）：按 action 去重
                if action in seen:
                    continue
                seen.add(action)
                candidates.extend(generate_candidates(
                    _PatternReq(action), stream, protocol=protocol))
            else:  # 字段型：按 (action, trigger_field) 去重
                key = (action, p.get("trigger_field", ""))
                if key in seen:
                    continue
                seen.add(key)
                field_cands = _field_action_candidates(p, stream, protocol)
                if field_cands:
                    candidates.extend(field_cands)
                elif llm is not None:  # 规则版覆盖不了 → mutation_hint 引导 LLM
                    candidates.extend(_llm_field_candidates(p, bundle, llm, protocol))
    return candidates


def vuln_pattern_dict_tokens(bundle: dict) -> set:
    """从 vuln_pattern 桶提取定向变异字典 token。

    提取 trigger_sequence 方法名 + trigger_field + 触发流名，让 fuzzer 的随机变异
    有偏地向漏洞方向展开（对齐 GLMFuzz 的「定向变异」本地化为种子语料）。

    注: 本函数保留 trigger_field; 最终字典组装处 generate_protocol_dict 才刻意
    排除 trigger_field（描述性文本，非有效 token）——见本文件 789-791 行。
    """
    tokens: set = set()
    for _subject, plist in (bundle.get("vuln_pattern") or {}).items():
        for p in plist:
            if not isinstance(p, dict):
                continue
            for m in (p.get("trigger_sequence") or []):
                tokens.add(str(m))
            tf = p.get("trigger_field", "")
            if tf:
                tokens.add(str(tf))
            for s in (p.get("streams") or []):
                tokens.add(str(s))
    return {t for t in tokens if t and "{{" not in t and 0 < len(t) <= 48}


def _is_dict_token(t: str) -> bool:
    """判断是否为有效字典 token：排除中文描述、引号、#（源码注释）、括号、占位符、
    超长、纯空白。这些是 LLM 抽取源码/漏洞时的描述性文本与注释片段，不是协议 token。"""
    if not t or len(t) > 48 or "{{" in t or not t.strip():
        return False
    for ch in t:
        if '\u4e00' <= ch <= '\u9fff':
            return False
        if ch in '（）()"\'#':
            return False
    return True


def generate_protocol_dict(bundle: dict, protocol: str = "rtsp",
                           resources: Optional[list] = None) -> str:
    """协议无关的定向变异字典：从 bundle + vuln_pattern 桶自动提取协议特定的
    方法名、字段名、取值池、漏洞触发 token 与通用边界值。

    区别于 generate_dict_minimal（RTSP 硬编码 track/Session/interleaved），本函数零
    协议硬编码：rtsp 的 SETUP/DESCRIBE/track、smtp 的 EHLO/MAIL/RCPT、ftp 的
    RETR/STOR/PASV、sip 的 INVITE/REGISTER 都随知识中枢自动变化。trigger_field 里的
    中文/括号描述性文本由 _is_dict_token 过滤，只保留真实协议 token。
    """
    tokens: set = set()
    # 1. 方法名（协议特定）
    for m in bundle.get("methods", {}):
        tokens.add(str(m))
    # 2. 字段名 + 取值池（协议特定）
    for name, info in (bundle.get("headers") or {}).items():
        if _is_dict_token(str(name)):
            tokens.add(str(name))
        for v in (info.get("values") or []):
            if _is_dict_token(str(v)):
                tokens.add(str(v))
    # 3. 漏洞触发 token：vuln_pattern 的 trigger_sequence 方法名 + streams（协议特定）。
    #    ★不含 trigger_field —— 它是 LLM 抽取漏洞时写的描述性文本（中文/英文短语/
    #    源码注释），不是有效字典 token，混入会污染 fuzzer 的变异方向。
    for _subject, plist in (bundle.get("vuln_pattern") or {}).items():
        for p in plist:
            if not isinstance(p, dict):
                continue
            for m in (p.get("trigger_sequence") or []):
                if _is_dict_token(str(m)):
                    tokens.add(str(m))
            for s in (p.get("streams") or []):
                if _is_dict_token(str(s)):
                    tokens.add(str(s))
    # 4. url_template 的 track 编号（{stream}/track{N} → track1/track2，多轨会话的
    #    同 track 双 SETUP 是 UAF 关键，编号从 URL 模板推导而非硬编码）
    for tmpl in (bundle.get("url_template") or {}).values():
        if "track" in str(tmpl).lower():
            tokens.add("track1")
            tokens.add("track2")
            break
    # 5. 资源实例名（多资源覆盖，如 RTSP 的流名）
    for r in (resources or []):
        name = r.get("name") if isinstance(r, dict) else r
        if _is_dict_token(str(name)):
            tokens.add(str(name))
    # 6. 通用字段边界值（覆盖边界 + 崩溃边界试探）
    tokens |= {"0", "1", "-1", "2147483647", "4294967295", "65535"}
    tokens = {t for t in tokens if _is_dict_token(t)}
    return "\n".join(f'"{t}"' for t in sorted(tokens)) + "\n"


# ===========================================================================
# 定向变异字典（C 组）：基础字典的**严格超集**构造
# ===========================================================================

#: 触发 Session 的字段名前缀（用于生成 "Session: <值>" 形式的组合 token）
_SESSION_HEADER = "Session"

#: 传输参数里**客户端可控**的参数名（协议无关的语义分类）。
#:
#: 只有客户端能设置的参数才适合作为变异目标：server_port 由服务端分配，
#: ssrc 每个会话都不同（会话作用域），放进固定字典只会稀释命中率。
_CLIENT_CONTROLLED_PARAMS = ("client_port", "interleaved", "port")

#: 传输参数 → 边界区间的归一化取值（协议无关的固定边界值）
_BOUNDARY_RANGES = {
    "interleaved": "0-1",
    "client_port": "50000-50001",
    "port": "50000-50001",
}


def _client_transport_params(bundle: dict) -> set:
    """从 bundle 的 Transport 头部取值里提取**客户端可控**的参数级 token。

    协议无关：任何协议的 Transport 字段都形如 "scheme;param=value;param=value"，
    按 ';' 拆开后逐段过滤，只保留客户端可控的参数（client_port / interleaved /
    port）。服务端分配或会话作用域的参数（server_port / ssrc）排除在外。
    """
    out: set = set()
    for name, info in (bundle.get("headers") or {}).items():
        if "transport" not in str(name).lower():
            continue
        for v in (info.get("values") or []):
            for part in str(v).split(";"):
                p = part.strip()
                if "=" not in p:
                    continue
                key = p.split("=", 1)[0].strip().lower()
                if key not in _CLIENT_CONTROLLED_PARAMS:
                    continue
                if _is_dict_token(p):
                    out.add(p)
    return out


def _vuln_trigger_fields(bundle: dict) -> set:
    """从 vuln_pattern 桶提取漏洞触发字段名（协议无关，全部过 _is_dict_token）。"""
    out: set = set()
    for _subject, plist in (bundle.get("vuln_pattern") or {}).items():
        for p in plist:
            if not isinstance(p, dict):
                continue
            tf = p.get("trigger_field", "")
            if tf and _is_dict_token(str(tf)):
                out.add(str(tf))
    return out


def _boundary_tokens(bundle: dict) -> set:
    """漏洞触发维度里**边界参数形式**的 token（协议无关派生）。

    从 bundle 的 Transport 取值里识别客户端可控的参数（interleaved /
    client_port / port），并把取值区间归一化到一组固定边界区间
    （interleaved=0-1 / client_port=50000-50001），覆盖「Transport 切换」
    与「client_port 边界」两个触发维度。
    """
    out: set = set()
    for name, info in (bundle.get("headers") or {}).items():
        if "transport" not in str(name).lower():
            continue
        for v in (info.get("values") or []):
            for part in str(v).split(";"):
                p = part.strip()
                if "=" not in p:
                    continue
                key = p.split("=", 1)[0].strip().lower()
                if key in _BOUNDARY_RANGES:
                    out.add(f"{key}={_BOUNDARY_RANGES[key]}")
    return out


def _profile_transport_tokens(protocol: str) -> set:
    """从 profile 读取协议特有的 Transport 组合串（方案 α：差异下沉到 profile）。

    协议差异（如 RTSP 的 "RTP/AVP;unicast;client_port=50000-50001"）不写死在
    本模块，而是放在 `fused_hub/targets/<proto>/profile.json` 的
    `boundary_probe.transport_tokens` 字段 —— 换协议 = 加一份 profile.json。
    profile 未声明时返回空集合（此时仅用协议无关派生部分）。
    """
    from core import paths
    p = paths.target_profile(protocol)
    if not p.exists():
        return set()
    try:
        import json
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    cfg = (data.get("boundary_probe") or {})
    return {str(t) for t in (cfg.get("transport_tokens") or [])
            if _is_dict_token(str(t))}


def generate_targeted_dict(bundle: dict,
                           protocol: str = "rtsp",
                           resources: Optional[list] = None,
                           *,
                           base_tokens: Optional[set] = None,
                           include_trigger_fields: bool = True,
                           compact: bool = False) -> str:
    """定向变异字典（C 组）：**严格包含**基础字典 + 全部漏洞触发维度 token。

    与 generate_protocol_dict 的关系：本函数是它的**超集构造**，不是替代。

    · base_tokens：基础字典 token 集合（默认从 fused_hub/targets/<proto>/
      <proto>_base.dict 读取；仓库内副本与镜像内 rtsp.dict 逐字节相同，
      MD5 由编排预检锁定）。为 None 时自动读取。
    · include_trigger_fields：是否并入 vuln_pattern 的 trigger_field
      （RTSP 实测 9 个：Authorization/Digest/Range/Session/Transport/
      client_port/interleaved/nonce/track，全部通过 _is_dict_token）。
    · compact：True 时只输出「基础字典 + 关键 token」（C′ 预案）。

    ★ 关键设计（对应 RQ3 的 D→C 单变量要求）：定向字典相对基础字典**只增不减**，
      因此 C 组相对 D 组的唯一差异 = 「多了若干定向 token」，D→C 仍是单变量。

    返回 AFL 字典文本（每行一个 "token"），已按字典序排序。
    """
    tokens: set = set()
    # 1. 协议定向 token（方法名 / 字段名 / 取值池 / 漏洞触发 token / 资源名）
    for line in generate_protocol_dict(bundle, protocol, resources).splitlines():
        t = line.strip().strip('"')
        if t:
            tokens.add(t)
    # 2. 基础字典（★ 保证定向字典是基础字典的严格超集）
    if base_tokens is None:
        base_tokens = load_base_dict_tokens(protocol)
    for t in base_tokens:
        if _is_dict_token(t):
            tokens.add(t)
    # 3. Session 触发值（从真实流量模板自动抽取，非硬编码）
    sessions = extract_session_candidates(protocol)
    for s in sessions:
        if _is_dict_token(s):
            tokens.add(s)
        combo = f"{_SESSION_HEADER}: {s}"
        if _is_dict_token(combo):
            tokens.add(combo)
    # 4. 传输维度（协议无关派生 + profile 下沉的协议特有组合串）
    tokens |= _client_transport_params(bundle)
    tokens |= _boundary_tokens(bundle)
    tokens |= _profile_transport_tokens(protocol)
    # 5. 漏洞触发字段名
    if include_trigger_fields:
        tokens |= _vuln_trigger_fields(bundle)

    if compact:
        tokens = _compact_targeted_tokens(tokens, base_tokens, sessions, bundle,
                                          protocol)

    tokens = {t for t in tokens if _is_dict_token(t)}
    return "\n".join(f'"{t}"' for t in sorted(tokens)) + "\n"


def _compact_targeted_tokens(tokens: set, base_tokens: set, sessions: list,
                             bundle: dict, protocol: str) -> set:
    """C′ 精简档：基础字典 + 关键触发 token（高关键密度，用于稀释风险对冲）。

    关键 token 集合 = {track1, track2, 触发 Session 值, "Session: <值>",
    interleaved 边界, client_port 边界, Transport 切换组合串}，
    全部来自 bundle / profile，不写死协议字面量（track 号由 url_template 派生）。
    """
    key: set = set()
    for tmpl in (bundle.get("url_template") or {}).values():
        if "track" in str(tmpl).lower():
            key.add("track1")
            key.add("track2")
            break
    for s in sessions:
        # 只保留 "Session: <值>" 组合形式：它直接产出可用的头部行，
        # 裸值单独作为 token 的边际价值低（且稀释关键 token 密度）。
        key.add(f"{_SESSION_HEADER}: {s}")
    key |= _boundary_tokens(bundle)
    # Transport 切换维度的组合串（协议特有部分仍从 profile 取）
    for t in _profile_transport_tokens(protocol):
        if "interleaved=" in t:
            key.add(t)
    return set(base_tokens) | {t for t in key if _is_dict_token(t)}



def load_base_dict_tokens(protocol: str = "rtsp") -> set:
    """读取仓库内的基础字典副本 `fused_hub/targets/<proto>/<proto>_base.dict`。

    该文件是镜像内基础字典（/home/ubuntu/experiments/rtsp.dict）的逐字节副本，
    MD5 由编排预检与 DICT_FROZEN.json 锁定。文件缺失时返回空集合
    （调用方应显式报错，不静默降级）。
    """
    from core import paths
    p = paths.targets_root() / protocol.lower() / f"{protocol.lower()}_base.dict"
    if not p.exists():
        return set()
    text = p.read_text(encoding="utf-8")
    return {ln.strip().strip('"') for ln in text.splitlines() if ln.strip()}


__all__ = ["BoundaryParam", "derive_boundary_param", "generate_candidates",
           "derive_semantic_candidates", "probe_boundary", "emit_boundary_fact",
           "extract_session_candidates", "search_trigger_value",
           "binary_search_boundary", "derive_field_candidates",
           "probe_field_space", "derive_constraint_candidates",
           "derive_vuln_pattern_candidates", "vuln_pattern_dict_tokens",
           "_build_baseline", "generate_dict", "generate_protocol_dict",
           "generate_dict_minimal", "generate_dict_balanced",
           "generate_targeted_dict", "load_base_dict_tokens"]
