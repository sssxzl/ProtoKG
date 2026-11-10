# -*- coding: utf-8 -*-
"""core/fused/downstream/response_oracle.py —— 执行结果的**三轴结果模型**与反馈闭环。

**为什么必须拆成三轴**（改进v2 问题⑦ / 评审 T4）：
把「一次模糊测试回放的结果」压成单一标签（成功/失败/崩溃）会丢掉三件互相独立的
事实，从而产生运行级误判：

  · **协议层**（``ProtocolOutcome``）—— 服务端在协议语义上如何回应：正常响应 /
    协议层错误 / 协议层成功但应用层拒绝 / 静默丢弃。**只有这一层谈得上「语义偏离」**。
  · **传输层**（``TransportOutcome``）—— 连接发生了什么：收到响应 / TCP RST /
    主动断开 / 超时。★ **RST 不是 crash**：很多协议允许对非法输入直接关闭连接。
  · **进程层**（``ProcessHealth``）—— 目标进程是否健在。★ **只有这一层能证明崩溃**；
    而且 ``exited`` 还要进一步区分「异常退出」与「正常收尾退出」（如收到 QUIT 后退出）。

**本模块内容**（C 阶段 C-1~C-4）：
  · C-1：三个 ``str, Enum`` 的取值集合与 ``docs/实施/路线与里程碑/RFC源知识抽取改造方案.md`` §3.5
    （:646-666）**逐项相等**，由 ``tests/test_response_oracle.py`` 断言防漂移。
  · C-2/C-3/C-4：``close_loop()`` 的**判定顺序**（UNKNOWN+TIMEOUT 最先 → crash →
    reset/close → 语义偏离）。

**判定顺序不可调换**：原实现把 ``proto != expected`` 排在 inconclusive 之前，
会让 ``health=UNKNOWN`` + ``trans=TIMEOUT`` 的超时被误判成「语义偏离」——而超时的
原因未知（丢包 / 负载 / 静默丢弃 / 状态不匹配 / 真死锁），**不能断言偏离**。

**语义偏离比对依赖 B 阶段的 ``ExecutableConstraint.expected_behavior``**：本模块用
``close_loop(..., expected=...)`` **显式传入**期望值；**「无期望」有两种等价表示**——
``None``（调用方未提供）与 ``""``（B 阶段 ``try_convert`` 的 convert-C7 特例产出，
缺处理期望时 ``expected_behavior == ""``，不是 None、不猜一个）—— 两者都 ⇒ **跳过**
语义偏离判定（与 §3.4 的 C7 特例一致：``expected_behavior`` 缺失不阻断转换）。

**职责边界（不要混淆）**：本模块是「执行结果 → 语义反馈」的 oracle；
``scripts/seed_oracle_filter.py`` 是**种子有效性过滤器**（逐种子回放、按响应码丢弃
入口即无效的种子），二者是**两个职责**，不是同一个东西。
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

__all__ = [
    "ProtocolOutcome",
    "TransportOutcome",
    "ProcessHealth",
    "PROTOCOL_OUTCOME_VALUES",
    "TRANSPORT_OUTCOME_VALUES",
    "PROCESS_HEALTH_VALUES",
    "ExecResult",
    "Feedback",
    "FEEDBACK_KINDS",
    "classify_protocol_outcome",
    "classify_transport_outcome",
    "probe_process_health",
    "close_loop",
]


class ProtocolOutcome(str, Enum):
    """协议层结果：服务端在协议语义上如何回应。"""

    SUCCESS = "success"                 # 符合期望的正常响应
    PROTOCOL_ERROR = "protocol_error"   # 协议层错误响应（4xx/5xx 等）
    APPLICATION_ERROR = "application_error"  # 协议层成功但应用层拒绝
    SILENCE = "silence"                 # 无响应但不拒绝（协议允许丢弃）


class TransportOutcome(str, Enum):
    """传输层结果：连接发生了什么。"""

    RESPONSE = "response"
    RESET = "reset"                     # ★ TCP RST —— **不是 crash**
    CLOSE = "close"                     # 主动断开
    TIMEOUT = "timeout"


class ProcessHealth(str, Enum):
    """进程健康：只有这里能证明崩溃。"""

    ALIVE = "alive"
    EXITED = "exited"                   # 进程退出
    RESTARTED = "restarted"             # 异常重启
    SANITIZER_FAILURE = "sanitizer_failure"   # ASAN/UBSAN 报告
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# 各轴取值集合（**由枚举派生**，不硬编码字符串 → 结构上不可能与枚举漂移）。
# 供下游断言使用（如「rfc_config 的 expected_response_classes 必须是协议层子集」）。
# ---------------------------------------------------------------------------

#: 协议层结果的取值集合。
PROTOCOL_OUTCOME_VALUES: frozenset[str] = frozenset(m.value for m in ProtocolOutcome)

#: 传输层结果的取值集合。
TRANSPORT_OUTCOME_VALUES: frozenset[str] = frozenset(m.value for m in TransportOutcome)

#: 进程健康状态的取值集合。
PROCESS_HEALTH_VALUES: frozenset[str] = frozenset(m.value for m in ProcessHealth)

#: 反馈类别（闭合词表）：``close_loop`` 只可能产出这 5 种 kind。
FEEDBACK_KINDS: frozenset[str] = frozenset({
    "inconclusive",
    "crash",
    "target_exited_normally",
    "connection_aborted",
    "semantic_deviation",
})


# ---------------------------------------------------------------------------
# 输入 / 输出契约
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecResult:
    """一次回放的执行结果 —— 三轴判定的**输入契约**。

    ★ 设计原则：**有证据就用证据；没有证据就落到「未知」**，绝不把「没观察到」
      当成「正常」。每条轴都留了一个**显式入口**（``protocol_outcome`` /
      ``transport_event`` / ``health_probe``）：调用方有确证时直接给，否则走从
      可观测信号推断的兜底路径。

    本类字段全部**可选**且有默认值 ⇒ 没填的字段表示「无证据」，而不是「否」。
    """

    # ---- 协议层 ----
    protocol_outcome: Optional[str] = None   # 显式协议层结果（优先于一切推断）
    response: Optional[bytes] = None         # 收到的响应报文（None = 无响应）
    status_code: Optional[int] = None        # 协议状态码（RTSP/SIP/SMTP 同构）

    # ---- 传输层 ----
    transport_event: Optional[str] = None    # 显式传输事件（response/reset/close/timeout）
    timed_out: bool = False
    peer_reset: bool = False
    peer_closed: bool = False

    # ---- 进程层 ----
    health_probe: Optional[str] = None       # 显式进程健康探测结果
    exit_code: Optional[int] = None          # 目标进程退出码（None = 未观察到退出）
    sanitizer_report: Optional[str] = None   # ASAN/UBSAN 报告文本（非空 = 有报告）
    restarted: bool = False                  # 目标进程被外部重启
    terminated_by_request: bool = False      # 退出是否由本次请求收尾导致（如收到 QUIT）


@dataclass(frozen=True)
class Feedback:
    """回流给上游的反馈信号（``close_loop`` 的产物）。

    ★ ``protocol`` / ``transport`` / ``health`` 三轴**总是**被填满（即使某个分支
      用不到它们），便于下游统一归因；``expected`` / ``actual`` 只在语义相关分支
      有值；``reproducible`` 为 ``None`` 表示**未做复现探测**（≠ 不可复现）。
    """

    kind: str                                # 见 FEEDBACK_KINDS
    expected: Optional[str] = None           # 期望的协议层结果（裸字符串）
    actual: Optional[str] = None             # 实际的协议层结果（裸字符串）
    protocol: Optional[str] = None           # 协议层结果（ProtocolOutcome）
    transport: Optional[str] = None          # 传输层结果（TransportOutcome）
    health: Optional[str] = None             # 进程健康（ProcessHealth）
    violated: Optional[str] = None           # 违规点唯一标识（rule_id）
    seed: Any = None                         # 原种子对象（透传）
    reproducible: Optional[bool] = None      # 是否可复现（None = 未知）


# ---------------------------------------------------------------------------
# 读取工具：让三轴判定吃下 dataclass / 对象 / dict 三种调用方
# ---------------------------------------------------------------------------


def _read(source: Any, name: str, default: Any = None) -> Any:
    """读对象的属性；**兼容 dict 形态**（同名键）。

    三轴判定要能吃下两类调用方：``ExecResult`` dataclass 与回放器直接吐出的裸
    dict。统一走 duck typing，调用方不必强制构造 ``ExecResult``。

    Args:
        source: 数据源（对象 / Mapping / None）。
        name: 属性名（dict 形态下即键名）。
        default: 取不到时的默认值。

    Returns:
        取到的值，或 ``default``。
    """
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _coerce(value: Any, enum_cls: type[Enum], field: str) -> Enum:
    """把显式取值转成枚举成员；**非法取值直接报错**（契约违例不静默吞掉）。

    Args:
        value: 待转换的取值（枚举成员或字符串皆可）。
        enum_cls: 目标枚举类。
        field: 字段名（用于报错信息定位）。

    Returns:
        对应的枚举成员。

    Raises:
        ValueError: 取值不在该枚举的取值集合里。
    """
    try:
        return enum_cls(value)
    except ValueError as exc:
        legal = sorted(m.value for m in enum_cls)
        raise ValueError(f"{field} 非法取值 {value!r}；合法取值：{legal}") from exc


def _normalize_expected(expected: Any) -> Optional[str]:
    """归一 ``expected`` 为协议层取值的**裸字符串**；「无期望」统一归一为 ``None``。

    ★ **「无处理期望」有两种表示，语义完全等价**：

      · ``None`` —— 调用方未提供期望；
      · ``""``  —— B 阶段 ``try_convert`` 的 **convert-C7 特例**产出（缺处理期望时
        ``ExecutableConstraint.expected_behavior == ""``，**不是 None、不猜一个**）。

      两者都 ⇒ **跳过**语义偏离判定。若不归一，B-2 产出的 ``""`` 会落进
      「非法取值」分支抛 ``ValueError``（跨路语义不对齐，B-8 消费 bundle 时必爆）。

    ★ 不用 ``str(枚举成员)``：``(str, Enum)`` 的 ``__str__`` 返回
      ``"ProtocolOutcome.SUCCESS"`` 而不是 ``"success"``（Python 3.11+ 行为），
      会静默破坏比对。统一取 ``.value``。

    Args:
        expected: 期望的协议层结果（字符串或 ``ProtocolOutcome`` 成员）；
            ``None`` / ``""`` / 纯空白 ⇒ 「无期望」。

    Returns:
        归一后的裸字符串，或 ``None``（无期望）。

    Raises:
        ValueError: ``expected`` 非空且不是合法的协议层取值
            （如 ``"timeout"``/``"crash"``）—— **红线：这些不是协议层期望，必须报错**。
    """
    if expected is None:
        return None
    value = expected.value if isinstance(expected, Enum) else str(expected)
    if not value.strip():
        # ""（B-2 的 convert-C7 特例）/ 纯空白 ⇒ 「无处理期望」，与 None 等价
        return None
    if value not in PROTOCOL_OUTCOME_VALUES:
        legal = sorted(PROTOCOL_OUTCOME_VALUES)
        raise ValueError(
            f"expected 非法取值 {expected!r}；合法取值：{legal}"
            f"（timeout/crash 属传输轴与进程健康轴，不是协议层期望）"
        )
    return value


# ---------------------------------------------------------------------------
# 三轴分类
# ---------------------------------------------------------------------------


def classify_protocol_outcome(result: Any) -> ProtocolOutcome:
    """判**协议层**结果：服务端在协议语义上如何回应。

    判定顺序：
      1. 调用方显式给了 ``protocol_outcome`` → 直接采信（协议方言差异由调用方裁定）。
      2. 有状态码 → 按数字段分档：2xx 成功 / 4xx 协议错误 / 5xx 应用错误。
      3. 没有状态码、也拿不到响应 → ``SILENCE``。
      4. 状态码缺失或落在 1xx/3xx 等**无法单凭状态码判定「符合期望」**的区间
         → 保守归入 ``SILENCE``（该轴的语义是「未被拒绝」）：**宁可漏报，也不误报**。

    ★ RTSP / SIP / SMTP 的状态码同构（RTSP 走 HTTP 语义、SIP 3xx/4xx/5xx、
      SMTP 2xx/4xx/5xx），故 2xx/4xx/5xx 分档对三协议都成立。

    Args:
        result: 执行结果（``ExecResult`` 或同构对象 / dict）。

    Returns:
        协议层结果。
    """
    explicit = _read(result, "protocol_outcome")
    if explicit is not None:
        return _coerce(explicit, ProtocolOutcome, "protocol_outcome")

    status_code = _read(result, "status_code")
    if status_code is None:
        return ProtocolOutcome.SILENCE
    if 200 <= status_code < 300:
        return ProtocolOutcome.SUCCESS
    if 400 <= status_code < 500:
        return ProtocolOutcome.PROTOCOL_ERROR
    if 500 <= status_code < 600:
        return ProtocolOutcome.APPLICATION_ERROR
    return ProtocolOutcome.SILENCE


def classify_transport_outcome(result: Any) -> TransportOutcome:
    """判**传输层**结果：连接发生了什么。

    ★ 兜底顺序刻意把「超时」放在最后：只有在**确实没拿到任何信号**时才认定超时，
      因为超时会把后续判定推向 ``inconclusive``（不误报），是最安全的兜底。

    Args:
        result: 执行结果（``ExecResult`` 或同构对象 / dict）。

    Returns:
        传输层结果。
    """
    explicit = _read(result, "transport_event")
    if explicit is not None:
        return _coerce(explicit, TransportOutcome, "transport_event")
    if _read(result, "timed_out", False):
        return TransportOutcome.TIMEOUT
    if _read(result, "peer_reset", False):
        return TransportOutcome.RESET
    if _read(result, "peer_closed", False):
        return TransportOutcome.CLOSE
    if _read(result, "response") is not None or _read(result, "status_code") is not None:
        return TransportOutcome.RESPONSE
    return TransportOutcome.TIMEOUT


def probe_process_health(result: Any) -> ProcessHealth:
    """探**进程健康**：只有这一轴能证明崩溃。

    ★ 没有独立证据时一律 ``UNKNOWN``（**不**假设存活、**不**假设崩溃）——
      ``UNKNOWN`` 会把判定推向 ``inconclusive``，正是问题⑦要的保守方向。

    Args:
        result: 执行结果（``ExecResult`` 或同构对象 / dict）。

    Returns:
        进程健康状态。
    """
    explicit = _read(result, "health_probe")
    if explicit is not None:
        return _coerce(explicit, ProcessHealth, "health_probe")
    if _read(result, "sanitizer_report"):
        return ProcessHealth.SANITIZER_FAILURE
    if _read(result, "restarted", False):
        return ProcessHealth.RESTARTED
    if _read(result, "exit_code") is not None:
        return ProcessHealth.EXITED
    if _read(result, "response") is not None or _read(result, "status_code") is not None:
        return ProcessHealth.ALIVE
    return ProcessHealth.UNKNOWN


def _is_abnormal_exit(result: Any) -> bool:
    """判 ``EXITED`` 是**异常退出**还是**正常收尾退出**（问题⑦第二半）。

    判为异常的三个条件（**或**关系，任一成立即异常，顺序即优先级）：
      1. 有 sanitizer 报告（ASAN/UBSAN）—— 铁证。
      2. 退出码非 0 —— 目标自己报了错。
      3. 退出**不是**由本次请求收尾导致 —— 例如收到 QUIT 后正常退出也是 EXITED，
         但那是**正常**退出，不能算 crash。

    ★ 与文档 §3.5 的判据「退出码非 0 / 有 sanitizer 报告 / 非请求收尾导致」一致。
      ``terminated_by_request`` 缺省为 False（=「没有证据表明退出由请求收尾导致」）
      ⇒ 缺该证据时按条件 3 判异常。

    Args:
        result: 执行结果。

    Returns:
        True = 异常退出（可进 crash 路径）；False = 正常收尾退出。
    """
    if _read(result, "sanitizer_report"):
        return True
    exit_code = _read(result, "exit_code")
    if exit_code is not None and exit_code != 0:
        return True
    if not _read(result, "terminated_by_request", False):
        return True
    return False


def _probe_reproducible(
        reproduce: Optional[Callable[[Any], Any]],
        seed: Any,
) -> Optional[bool]:
    """调用可选复现器；**未提供复现器 ⇒ None（未知）**，不编造「不可复现」。

    Args:
        reproduce: 复现器（里程碑 C6）；``None`` 表示当前无复现能力。
        seed: 传给复现器的种子对象。

    Returns:
        True / False / None（None = 未探测）。
    """
    if reproduce is None:
        return None
    outcome = reproduce(seed)
    ok = _read(outcome, "ok")
    if ok is None:
        return bool(outcome)
    return bool(ok)


# ---------------------------------------------------------------------------
# 反馈闭环：判定顺序（顺序即语义）
# ---------------------------------------------------------------------------


def close_loop(
        seed: Any,
        result: Any,
        expected: Optional[str] = None,
        reproduce: Optional[Callable[[Any], Any]] = None,
) -> Optional[Feedback]:
    """把执行结果回流成可用的反馈信号（三轴判定，**顺序即语义**）。

    ★ **判定顺序**（改进v2 问题⑦的核心，**不可调换**）：

      ① ``health=UNKNOWN`` 且 ``trans=TIMEOUT`` ⇒ ``inconclusive`` —— **最先**。
         超时的原因未知（丢包 / 负载 / 静默丢弃 / 状态不匹配 / 真死锁），
         **不能断言语义偏离**。原实现里 ``proto != expected`` 排在 inconclusive 之前，
         会把这类超时误判成「语义偏离」。
      ② crash 路径 —— 只认**独立的进程健康证据**：``RESTARTED`` / ``SANITIZER_FAILURE``
         直接 crash；``EXITED`` 必须先经 :func:`_is_abnormal_exit` 判别，异常才 crash，
         正常收尾 ⇒ ``target_exited_normally``。
      ③ ``trans ∈ {RESET, CLOSE}`` ⇒ ``connection_aborted``（**不是** crash）——
         很多协议允许对非法输入直接关闭连接。
      ④ 语义偏离 —— 仅当 ``expected`` **已知**且与实际协议层结果不符时。
      ⑤ 都不命中 ⇒ 返回 ``None``（符合预期 / 无需反馈）。

    Args:
        seed: 种子对象（duck typed；读 ``violation_of`` 作为违规点标识）。
        result: 执行结果（``ExecResult`` 或同构对象 / dict）。
        expected: 期望的**协议层**结果（如 ``"success"``）。
            ★ **「无期望」有两种等价表示**：``None``（调用方未提供）与 ``""``
            （B 阶段 ``try_convert`` 的 convert-C7 特例产出）—— 两者都 ⇒
            **跳过**语义偏离判定（只走传输层 / 进程健康判定），内部统一归一为 ``None``。
            这与 §3.4 的 C7 特例一致：``expected_behavior`` 缺失**不阻断**转换，
            缺「处理期望」时该规则只能用于「构造违规种子」，不能用于「判定 oracle 预期」。
            **本参数是 expected 的唯一来源**（不回退去读 ``seed.expected_class``），
            否则「``expected=None`` ⇒ 跳过」这条契约会被种子的属性破坏。
        reproduce: 可选的复现器（里程碑 C6）。传 ``None`` ⇒ ``reproducible`` 记为
            ``None``（**未知**，不编造「不可复现」）；传了则调用 ``reproduce(seed)``，
            取返回值的 ``.ok``（无 ``.ok`` 时取其真值）。

    Returns:
        ``Feedback``；符合预期且无异常时返回 ``None``。

    Raises:
        ValueError: ``expected`` 不是合法的协议层取值（如 ``"timeout"``/``"crash"``）。
    """
    proto = classify_protocol_outcome(result)
    trans = classify_transport_outcome(result)
    health = probe_process_health(result)
    expected_value = _normalize_expected(expected)

    violated = _read(seed, "violation_of")
    violated_id = None if violated is None else str(violated)

    # ---- ① 进程健康未知 + 传输超时 → **最先判定为不确定** ----
    #   ★ 问题⑦：原顺序里 `proto != expected` 在 inconclusive 之前，
    #   导致 health=UNKNOWN & trans=TIMEOUT 的超时被误判成「语义偏离」。
    if health is ProcessHealth.UNKNOWN and trans is TransportOutcome.TIMEOUT:
        return Feedback(kind="inconclusive", expected=expected_value,
                        actual=proto.value, protocol=proto, transport=trans,
                        health=health, violated=violated_id, seed=seed)

    # ---- ② crash 路径：必须有**独立证据**，且 EXITED 需判别退出原因 ----
    #   ★ 问题⑦：EXITED 不能不加区分地当崩溃 —— 目标正常退出（如收到 QUIT 后退出）
    #   也是 EXITED。必须结合退出码 / 退出原因 / 目标生命周期判断。
    if health in (ProcessHealth.RESTARTED, ProcessHealth.SANITIZER_FAILURE):
        return Feedback(kind="crash",
                        reproducible=_probe_reproducible(reproduce, seed),
                        protocol=proto, transport=trans, health=health,
                        violated=violated_id, seed=seed)
    if health is ProcessHealth.EXITED:
        if _is_abnormal_exit(result):
            return Feedback(kind="crash",
                            reproducible=_probe_reproducible(reproduce, seed),
                            protocol=proto, transport=trans, health=health,
                            violated=violated_id, seed=seed)
        return Feedback(kind="target_exited_normally", reproducible=None,
                        protocol=proto, transport=trans, health=health,
                        violated=violated_id, seed=seed)

    # ---- ③ 传输异常但进程健康 → 只是**候选**，不是崩溃 ----
    if trans in (TransportOutcome.RESET, TransportOutcome.CLOSE):
        return Feedback(kind="connection_aborted", reproducible=None,
                        protocol=proto, transport=trans, health=health,
                        violated=violated_id, seed=seed)

    # ---- ④ 语义偏离：期望与实际协议结果不符（此时健康已知且非超时）----
    if expected_value is not None and proto.value != expected_value:
        return Feedback(kind="semantic_deviation", expected=expected_value,
                        actual=proto.value, protocol=proto, transport=trans,
                        health=health, violated=violated_id, seed=seed)

    return None   # 符合预期 → 无反馈
