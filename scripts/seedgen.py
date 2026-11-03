# -*- coding: utf-8 -*-
"""scripts/seedgen.py —— 统一种子生成入口（协议 × 源二维解耦的下游层）。

按 protocol 读 fused_hub/targets/<protocol>/profile.json 的 seedgen 配置，走统一的
「规则种子生成」工厂：
  ① 结构覆盖（edge_cover，永远，协议无关）
  ② 通用危险（generic_danger，profile.seedgen.danger 或 --danger）
  ③ 漏洞边界候选（derive_vuln_pattern_candidates，序列型漏洞模式，永远；不调 LLM，
     从 vuln_pattern 桶规则生成「合法—非法」边界对种子，让漏洞知识真正参与生成）
  ④ 黄金路径（profile.seedgen.canonical_flow，可选，如 SMTP 的 EHLO→MAIL→RCPT→DATA→QUIT）
   ⑤ 字段级 action-sequence 变异（**批次 1 / SemFuzz 迁移项 A**；由
      ``profile.seedgen.action_seq.enabled`` 开关位控制，**默认关闭** ⇒ 关闭时
      **批次 1 的改动不引入任何产物变化**（回滚手段必须成立））

★ 关于「回滚态逐字节一致」的**口径**（QA 第三轮 K-3，务必照此表述）
  正确说法：**「批次 1 的改动不引入任何产物变化（开关 OFF 时）」** —— 即与
  **批次 1 自身的基线**逐字节一致。
  ⚠ **不要**说成「与批次 1 之前（``0046d6f``）逐字节一致」：批次 1.5
    （``955e325``，改了 ``core/fused/downstream/boundary_probe.py`` 的 ③ 层候选
    生成）**已合法改变基准层** ⇒ QA 实测 rtsp/B 关闭态 **65 → 70 条**
    （多出 4 条 DESCRIBE）⇒ 那个「之前」不是可回滚到的目标。
    逐 commit 归因（QA 实测，rtsp/B 关闭态条数）：
    ``0046d6f`` 65 → ``470775a`` 65 → ``39ef9ef`` 65 → ``ae7dd1c`` 65 →
    ``955e325`` **70** → ``de7d5f9`` 70 ⇒ **批次 1 自己的 commit 逐字节一致**，
    65 → 70 发生在**批次 1.5**，与批次 1 无关。

★ ⑤ 与前四条的本质区别：前四条是「**从零构造**」，⑤ 是「**在真实抓包种子上做
  字段级变异**」（底料 = 已发表的真实语料 / kb 真实抓包；LLM 只产出抽象动作序列，
  由确定性引擎执行 —— SemFuzz 的硬约束）。

协议差异全部下沉到 profile.json（对齐 Fuzz4All 的「配置驱动」），本脚本零协议硬编码：
换协议 = 加一份 profile.json，一个脚本都不用新增。

用法:
    python scripts/seedgen.py --protocol smtp
    python scripts/seedgen.py --protocol rtsp --danger
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import paths  # noqa: E402
from core.fused.downstream.rag_seedgen import (  # noqa: E402
    load_fact_views, assemble_bundle, write_seeds, load_semantic_rules,
    load_source_manifest,
)
from core.fused.downstream.edge_cover import (  # noqa: E402
    edge_cover, build_message,
)
from core.fused.downstream.generic_danger import generic_danger  # noqa: E402
from core.fused.downstream.boundary_probe import (  # noqa: E402
    derive_constraint_candidates, derive_vuln_pattern_candidates,
    generate_protocol_dict, generate_targeted_dict, load_base_dict_tokens,
)
from core.fused.downstream.selector import (  # noqa: E402
    dedupe_seeds, prioritize_seeds,
)
from core.fused.downstream.action_seq import (  # noqa: E402
    ACTION_SEQ_GENERATED_BY, ActionLedger, apply_actions,
    load_real_base_seeds, plan_actions,
)
from core.fused.downstream.seed_manifest import (  # noqa: E402
    build_manifest, write_manifest,
)
from core.fused.downstream.target_env import (  # noqa: E402
    boundary_methods, effective_config, endpoint_normalization_enabled,
    filter_transitions_by_boundary, normalize_seed_resource,
    normalize_target_endpoint, normalize_target_endpoint_in_text,
    normalize_target_resource_in_text,
    playable_resource_names, restrict_resources,
)
from core.models import SeedCorpus  # noqa: E402


#: 全部可用的生成分层（--layers 的取值域）
ALL_LAYERS: tuple[str, ...] = ("edge_cover", "generic_danger", "vuln_boundary",
                               "canonical")

#: ⑤ 字段级 action-sequence 变异层的名字。
#:
#: ★ **不进 ALL_LAYERS**：⑤ 由 ``profile.seedgen.action_seq.enabled`` 开关位
#:   控制（不是 CLI 层开关）——不进 ALL_LAYERS ⇒ ①~④ 的层集合、manifest 的
#:   ``layers`` 字段在关闭时**不受批次 1 影响**（与批次 1 的基线逐字节一致 ——
#:   回滚手段必须成立；口径见模块 docstring 的「回滚态逐字节一致」一段）。
ACTION_SEQ_LAYER_NAME = "action_seq"

#: RQ3 聚焦组配置表（技术方案 §2.2 实现契约）。
#:
#: A 守正：①+②+④（不含③漏洞边界层）、自然序、基础字典
#: B 漏洞导向：①+②+③+④、自然序、基础字典
#: C 完整聚焦：①+②+③+④、漏洞接近度序、定向字典
#: D 解耦组：①+②+③+④、漏洞接近度序、基础字典
#:
#: ★ C 与 D 的种子集合完全相同，仅「顺序 + 字典」不同 → D→C 是纯净单变量。
#:
#: ★★ **本表只是兜底**：协议级标定的**唯一权威**在
#:   ``fused_hub/targets/<协议>/profile.json`` 的 ``seedgen.focus_group``
#:   （指定 ``--target-env`` 时则用 ``seedgen.environments.<env>.focus_group``）
#:   ⇒ 见 `main()` 里读 `seedgen_cfg.get("focus_group")` 的那段。
#:   ★ 2026-11-03 两次按实测**重新标定**：
#:     ① 批次 2.0（P0，RFC 源补齐字段取值）⇒ 52/58/58/58
#:     ② 批次 2.4（⑤ 层 action_seq 开启）⇒ **55/85/61/61**
#:        （字典 token 24/24/226/24 不变；⑤ 层是**追加**的 L5 变异种子）。
FOCUS_GROUP_CONFIG: dict = {
    "A": dict(layers=["edge_cover", "generic_danger", "canonical"],
              order="natural", dict_kind="base",
              expect_seeds=55, expect_dict_tokens=24),
    "B": dict(layers=["edge_cover", "generic_danger", "vuln_boundary", "canonical"],
              order="natural", dict_kind="base",
              expect_seeds=85, expect_dict_tokens=24),
    "C": dict(layers=["edge_cover", "generic_danger", "vuln_boundary", "canonical"],
              order="vuln-proximity", dict_kind="targeted",
              expect_seeds=61, expect_dict_tokens=217),
    "D": dict(layers=["edge_cover", "generic_danger", "vuln_boundary", "canonical"],
              order="vuln-proximity", dict_kind="base",
              expect_seeds=61, expect_dict_tokens=24),
}


def _fail(msg: str) -> int:
    """参数校验失败：打印到 stderr 并以退出码 2 结束。

    退出码 2 是「参数用法错误」的约定（与 argparse 的用法错误一致），
    便于脚本侧区分「实验失败」与「用错参数」。
    """
    print(f"!! 参数错误: {msg}", file=sys.stderr)
    return 2



def _load_profile(protocol: str) -> dict:
    """读 fused_hub/targets/<protocol>/profile.json（协议维度配置）。"""
    p = paths.target_profile(protocol)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _load_resources(profile: dict, protocol: str,
                    env_cfg: Optional[dict] = None) -> list:
    """读 profile.resources_file 声明的资源实例清单（如 RTSP 的流名列表），返回
    流名列表，多轨(tracks 大)在前——多轨资源通常覆盖更多状态（多 track 会话）。

    协议无关：resources_file 缺失、文件不存在或无 streams 字段时返回空（表示该协议
    无「多资源实例」概念，如 SMTP/FTP 是命令序列协议，保持单占位符行为）。

    ★ 目标环境限定（可选）：profile.seedgen.environments.<env>.playable_resources_file
      声明了该环境下**实际可播/可用**的资源实例子集（环境级事实）。传入 env_cfg 时
      取交集——源码级清单（rtsp_streams.json 的 18 个）不删改，仅在本环境下收敛到
      可播子集（见 core/fused/downstream/target_env.py 的设计说明）。
    """
    res_file = profile.get("resources_file")
    if not res_file:
        return []
    # 先试协议子目录（fused_hub/targets/<protocol>/<res_file>），再兜底 targets 根目录
    # （历史遗留：rtsp_streams.json 曾放在 fused_hub/targets/ 根目录，带协议前缀）。
    candidates = [paths.targets_root() / protocol / res_file,
                  paths.targets_root() / res_file]
    data = None
    for p in candidates:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = None
            if data is not None:
                break
    if data is None:
        return []
    streams = [(s.get("name"), int(s.get("tracks", 1) or 1))
               for s in data.get("streams", []) if s.get("name")]
    # 多轨流优先（tracks 降序，sort 稳定保留原声明顺序）
    streams.sort(key=lambda nt: -nt[1])
    names = [n for n, _ in streams]
    # ★ 目标环境可播子集限定（协议无关：由 profile 的环境配置驱动）
    if env_cfg:
        playable = playable_resource_names(profile, protocol, env_cfg)
        names = restrict_resources(names, playable)
    return names


def _build_canonical_seed(bundle: dict, canonical_flow: list,
                          protocol: str,
                          transitions: Optional[list] = None) -> Optional[SeedCorpus]:
    """按 profile.seedgen.canonical_flow 构造黄金路径种子（字段级实例填充参数）。

    在 transitions 里沿 canonical_flow 找一条连通边序列（回溯搜索），命中即用其
    message_instance 的命令参数；找不到连通路径则放弃（返回 None）。

    ★ 用回溯而非贪心：贪心按字母序取第一条出边会走错（如 SIP 的 INVITE 有
    Idle→Open 与 Idle→Pending，字母序选 Open，但 ACK 只能从 Pending 出发），导致
    黄金路径构建失败、种子缺 REGISTER（触发服务端响应的方法），AFLNet 报
    No server states。回溯从任意状态匹配首方法，再逐边递进，找到即返回。

    ★ transitions 参数：目标环境可用「消息起点方法」限定种子构造用的边（见
      core/fused/downstream/target_env.py）。限定后只有能被 fuzzer 独立识别为
      新消息的方法才可能出现在黄金路径里——canonical_flow 若含被排除方法，
      本函数返回 None（不生成违规种子）。
    """
    trans = sorted({(s, m, d) for s, m, d in
                    (transitions if transitions is not None
                     else bundle["transitions"])})
    insts = bundle.get("message_instances") or {}

    def search(idx: int, state, path: list):
        if idx == len(canonical_flow):
            return path
        cmd = str(canonical_flow[idx]).strip().upper()
        for edge in trans:
            s, m, d = edge
            if m != cmd:
                continue
            if state is not None and s != state:
                continue
            result = search(idx + 1, d, path + [edge])
            if result is not None:
                return result
        return None

    path = search(0, None, [])
    if path is None:
        return None

    messages = []
    for i, (s, m, d) in enumerate(path, start=1):
        messages.append(build_message(
            m, required_headers=bundle.get("required_headers"),
            headers=bundle.get("headers"), cseq=i,
            instance_fields=insts.get((s, m, d)),
            cseq_with_method=(protocol == "sip")))
    return SeedCorpus(
        protocol=protocol,
        description="canonical session: " + " -> ".join(canonical_flow),
        target_state_path=[m.method for m in messages],
        target_methods=[m.method for m in messages],
        messages=messages,
        generated_by="rule-based:canonical-session",
    )


def _derive_vuln_boundary_candidates(bundle: dict, profile: dict,
                                     protocol: str,
                                     boundary: Optional[list] = None) -> list:
    """③ 漏洞边界候选（序列型漏洞模式，GLMFuzz 式，不调 LLM）。

    从 bundle 的 vuln_pattern 桶规则生成「合法—非法」边界对种子（double_setup/
    uaf_seq/interleave_seq 等序列型 action），过滤掉白名单外方法的候选，让历史漏洞
    知识真正参与种子生成——这是 seedgen.py 补齐「出奇」能力的关键一层。

    ★ P4-c 去协议门控（2026-10-29）：不再 `protocol != "rtsp"` 直接返回空。
      - 序列型候选（generate_candidates 里 RTSP 硬编码的 DESCRIBE/SETUP/TEARDOWN）
        产出的种子，其方法不在非 RTSP 协议白名单里，会被下方 valid_methods 过滤掉
        （技术债注释里的「方法白名单兜底」）。
      - 字段型候选（_field_action_candidates）已按 raw_format 协议化：头部协议用
        url+headers、行命令协议用 argument，对 SIP/FTP/SMTP 等字段型漏洞自然生效。
      这样漏洞导向层对所有协议可用，不再一刀切禁用。

    ★ boundary（消息起点方法白名单，harness 级）：候选种子的**每一条消息**都必须
      是能起始消息的方法，否则该候选会被 fuzzer 的分区器并入前一条消息 → 边界破坏。
      被排除的方法（OPTIONS/SUBSCRIBE/...）的**漏洞知识仍在 bundle["vuln_pattern"] 里**
      （知识保留），只是不产出以它们开头的种子。
    """
    stream = ((profile.get("url_placeholders") or {}).get("<stream>")
              or ("" if protocol != "rtsp" else "matroskaFileTest"))
    # ★★ 批次 1.5：把「源 A 第四类」（**RFC 语义规则投影出的 legal_boundary**
    #   → 「满足约束 vs 违反约束」的边界候选）**并入 ③ 层**。
    #   ★ 此前它**只被测试调用、生产代码从不调用** ⇒ 即使 legal_boundary 有内容
    #     （规则发布进权威库之后），约束边界种子**永远产不出来**
    #     ⇒ 「RFC 语义 → 知识中枢 → 消费」链路的**最后一跳缺失**。
    #   ★ 与漏洞模式候选（源 B）**并列**：前者来自 RFC 规范，后者来自漏洞库。
    cands = derive_vuln_pattern_candidates(bundle, stream=stream,
                                           protocol=protocol)
    cands += derive_constraint_candidates(bundle, stream=stream,
                                           protocol=protocol)
    valid_methods = set(bundle["methods"].keys())
    allow = ({str(m).strip().upper() for m in boundary} if boundary else None)
    out: list = []
    for _label, s in cands:
        if not all(m.method in valid_methods for m in s.messages):
            continue
        if allow is not None and not all(
                str(m.method).strip().upper() in allow for m in s.messages):
            continue
        out.append(s)
    return out


# ===========================================================================
# ⑤ 字段级 action-sequence 变异（批次 1：SemFuzz 迁移项 A）
# ===========================================================================

def _action_seq_enabled(profile: dict) -> bool:
    """⑤ 路径的**开关位**：``profile.seedgen.action_seq.enabled``。

    ★ **默认关闭**（键缺失 ⇒ False）⇒ 关闭时**批次 1 的改动不引入任何产物变化**
      （与批次 1 的基线逐字节一致 —— 这是回滚手段，必须成立；
      口径见模块 docstring：不要说成「与批次 1 之前逐字节一致」）。
    """
    cfg = ((profile.get("seedgen") or {}).get("action_seq") or {})
    return bool(cfg.get("enabled", False))


def _build_action_seq_seeds(bundle: dict, profile: dict, protocol: str,
                            *, group: Optional[str] = None,
                            ledger: Optional[ActionLedger] = None,
                            env_cfg: Optional[dict] = None,
                            strict_source_only: bool = False,
                            source_set: Optional[list] = None
                            ) -> tuple[list, dict]:
    """⑤ 在**真实抓包种子**上做字段级变异，返回 ``(种子列表, 溯源信息)``。

    底料来源（优先级，见 ``core/fused/downstream/action_seq.py``）：
      ① ``derived/seeds/<protocol>/<组>/*.raw``（已发表的语料）
      ② ``kb/<protocol>/数据流量/**`` 里的真实抓包
      ③ 都取不到 ⇒ **本协议不产出 ⑤ 种子**（如实报告，**不造假**）

    ★ **不调 LLM**：本脚本既有四条路径都是规则驱动，⑤ 同样保持**确定性可复现**
      （需要 LLM 兜底时走 ``action_seq.plan_actions(..., llm=...)``）。
    ★ 协议差异全部下沉到 profile（底料解析、字段取值池都由 profile/bundle 驱动）。
    """
    base_seeds, source = load_real_base_seeds(
        protocol, profile, group=group,
        strict_source_only=strict_source_only, source_set=source_set)
    info = {
        "source": source,
        "base_count": len(base_seeds),
        "mutated_count": 0,
        "reject_reasons": {},
    }
    if not base_seeds:
        return [], info
    out: list = []
    zero_mutation = 0
    # ★ P2-6：零变异**区分成因**（此前只有一个笼统计数，无法判断是「规则给不出」
    #   还是「规则给出的动作全被拒」⇒ 两者指向完全不同的改进方向）。
    zero_no_rule = 0          # 规则/兜底**根本没给出**任何动作
    zero_all_rejected = 0     # 规则给出了动作，但**全部被校验拒绝**
    for base in base_seeds:
        ledger_before = len(ledger) if ledger is not None else 0
        seq = plan_actions(base, bundle, protocol=protocol, profile=profile,
                           ledger=ledger)
        # ★ 零变异（**没有任何动作实际生效**）的种子**直接丢弃**。
        #   理由：`apply_actions` 对零变异**不改** `generated_by`/`description`
        #   （P1-4：不得把没变的东西标成 ⑤ 层）⇒ 于是它的 `generated_by`
        #   仍是底料原值 ⇒ `seed_layer()` 判不出 L5 ⇒ **落成 L0/unknown**
        #   ⇒ 混进「基准层」统计（实测 smtp/B 基准层 61 → 68，多出 7 条 L0）。
        #   而零变异的 ⑤ 种子**本身也没有价值**（既没改任何字段，也不是 ⑤ 层）
        #   ⇒ 丢弃是唯一自洽的选择。
        if not seq.actions:
            zero_mutation += 1
            # ★ P2-6：区分「无规则命中」与「规则动作全被拒」——后者看**本次调用**
            #   的台账增量（ledger 是全局累计的，故先记基线）。
            if ledger is not None and len(ledger) > ledger_before:
                zero_all_rejected += 1
            else:
                zero_no_rule += 1
            continue
        # ★ P2-2：把**必填头表**传给执行器 ⇒ 「删必填头」在**执行期**也会被拒
        #   （`plan_actions` 的清洗期已拒过一次，这里是**纵深防御**：
        #   万一将来有别的调用方绕过 `plan_actions` 直接 `apply_actions`，
        #   「删必填头」仍然被拒并记账，而不是静默生效）。
        mutated = apply_actions(
            base, seq, ledger=ledger, profile=profile,
            required_headers=(bundle or {}).get("required_headers") or None)
        # ★ R-3：⑤ 种子**立刻**走完整的后处理链（收敛在
        #   `_postprocess_action_seq_seeds` 一个函数里，不在别处分叉）。
        mutated = _postprocess_action_seq_seeds([mutated], bundle, profile,
                                                 protocol, env_cfg)
        out.extend(mutated)
    info["mutated_count"] = len(out)
    info["zero_mutation_skipped"] = zero_mutation
    info["zero_no_rule"] = zero_no_rule
    info["zero_all_rejected"] = zero_all_rejected
    if ledger is not None:
        info["reject_reasons"] = ledger.reason_counts()
    return out, info


def _postprocess_action_seq_seeds(seeds: list, bundle: dict, profile: dict,
                                  protocol: str,
                                  env_cfg: Optional[dict] = None) -> list:
    """⑤（action-seq 变异层）种子的**完整**后处理链（与基准层**同款**）。

    ★★ 为什么必须收敛成**一个函数**（QA 的结构性建议）：
      R-1（漏 ``_rewrite_client_headers``）与 R-3（漏 ``_prepend_session_prologue``）
      **连续两次**是同一类根因 ——「⑤ 在流程末尾追加 ⇒ 分叉调用 ⇒ 漏步骤」
      ⇒ 分散调用必然还会漏第三次。
      ⇒ **⑤ 的后处理只允许从这里走**（新增步骤必须加在这里，不得在别处分叉）。

    顺序（与基准层一致，且步骤间有依赖）：
      1. ``_prepend_session_prologue`` —— **插消息**（有状态协议；
         SIP 的 REGISTER 是 registrar 路由上唯一返回响应的无状态自环
         ⇒ 不插 REGISTER 的 INVITE/BYE 会被 kamailio 静默丢弃）
      2. ``_render_seq_headers`` —— ``{seq}`` 占位替换（prologue 消息也带占位）
      3. ``_apply_url_placeholders`` —— 端点/资源归一化
      4. ``_rewrite_client_headers`` —— 响应回传地址改写（Via/Contact）

    ★ 对**基准层零影响**（本函数只作用于 ⑤ 种子）。
    """
    if not seeds:
        return seeds
    seeds = _prepend_session_prologue(seeds, bundle, profile)
    seeds = _render_seq_headers(seeds)
    seeds = _apply_url_placeholders(seeds, profile, protocol, env_cfg)
    seeds = _rewrite_client_headers(seeds, profile, protocol)
    return seeds


def _append_action_seq_seeds(seeds: list, action_seeds: list) -> list:
    """把 ⑤（action-seq 变异层）种子**追加**到基准层之后。

    ★ P0-4（语义修正）：**开启 ⑤ 不得裁剪任何既有层**。
      原实现在 ⑤ 开启时按 profile 契约条数**裁剪总数**且「⑤ 优先保留」
      ⇒ 实测 rtsp/B `91 → 50`，① 结构覆盖 6 + ③ 漏洞边界 18 **被丢弃**；
      且总数被凑到契约 ⇒ **掩盖了批次 1 之前就存在的契约漂移**
      （QA 实测 4/12 组 G5 关系 drift→ok）。

    ★ 新语义：**契约条数是「基准层」的约定**，而基准层的条数是**既有行为**
      （⑤ 关闭时**不裁剪**，该漂移照旧由 G5 报出）⇒ ⑤ 开启时也**不得裁剪**
      ⇒ 基准层条数在 OFF / ON 两种状态下**完全相同**（这是批次 1 的验收项）。
    ★ 契约漂移**照旧由 G5 报出**（该漂移仍漂移，**不许被掩盖**）：
      `scripts/corpus_gate.py::check_g5` 已改为**只查基准层**条数。
    """
    if not action_seeds:
        return seeds
    return list(seeds) + list(action_seeds)


def _apply_url_placeholders(seeds: list, profile: dict, protocol: str,
                           env_cfg: Optional[dict] = None) -> list:
    """把 LLM 生成的 url 占位符（<server>/<stream>/<user> 等）替换成真实地址，并给
    未命中实例（url 为空）的消息补 default_url + 流名（避免 fallback 成 localhost/seed）。

    多资源覆盖（协议无关）：profile.resources_file 声明了多个资源实例（如 RTSP 的
    流名）时，① canonical 黄金路径种子对每个流展开一条（保证每个流都有一条完整
    会话，覆盖该流的完整状态机）；② 其余种子按流轮转分发。避免「所有种子单流」导致
    状态/代码覆盖单一。无 resources_file 的协议（SMTP/FTP 是命令序列协议）保持单
    占位符替换行为不变。

    ★ 目标环境限定：env_cfg 声明了「该环境实际可播的资源实例子集」时，展开与轮转
      都只用该子集（见 core/fused/downstream/target_env.py）——否则生成的种子会
      引用服务端根本播不出的会话（实测 47.9% 的状态变更请求返 404）。

    ★★ 目标侧归一化（缺陷 3）：种子 URL 的**端点**与**资源段**必须由目标侧推导，
      不得照抄源侧抓包值。`traffic` 源是**混合抓包**（实测同一份 traffic.jsonl 里
      既有 live555 的 127.0.0.1:8554，也有别的设备如某 IP 摄像机的
      rtsp://10.11.26.98:554/isapi/streaming/channels/101）——原样透传会让
      59.5% 的种子打向目标环境不存在的设备（服务端返 404，且**所有健康度指标
      都不会红**，属静默退化）。归一化分两级：
        · 端点（协议级，依据 profile.default_url）→ 换成本 profile 描述的服务；
        · 资源段（环境级，依据可播清单）→ 换成该种子已分配的可播资源。
      两级都是**幂等**的：对本就正确的 URL 原样返回 ⇒ 历史语料逐字节不变。
      ⇒ SIP 不适用：SIP 的 URI domain 是逻辑实体标识、不决定路由（Contact 头才是
        回包地址），照抄抓包 domain 无害且其 From/To 的真实 domain 反而有语义价值。

    返回替换后的种子列表（多资源展开时会比输入更长）。
    """
    ph = (profile.get("url_placeholders") or {})
    default_url = profile.get("default_url", "") or ""
    stream = ph.get("<stream>", "") or ""
    streams = _load_resources(profile, protocol, env_cfg)
    # 目标环境允许的资源集合（受 playable 清单限定；未声明环境时 = 源码级全量）
    allowed_resources = list(streams) if streams else None
    # 端点归一化是**协议级显式开关**（profile.seedgen.target_endpoint_normalization）：
    #   RTSP 的 Request-URI 决定请求目标 → 需要归一化；
    #   SIP 的 URI domain 是逻辑实体标识、不决定路由 → **不得**归一化
    #   （改写会破坏消息语义并丢掉 userinfo）。
    do_endpoint = endpoint_normalization_enabled(profile)

    def _replace(seed: SeedCorpus, cur_stream: str) -> None:
        for msg in seed.messages:
            # 未命中实例（url 空）或仍是默认占位时，用 default_url + 流名兜底
            if not msg.url or "localhost/seed" in msg.url:
                if default_url:
                    msg.url = default_url.rstrip("/") + ("/" + cur_stream if cur_stream else "")
            # ★<stream> 单独用「当前种子分配的流」替换（多流轮转/展开），其余占位符走 ph
            if cur_stream:
                msg.url = msg.url.replace("<stream>", cur_stream)
            for k, v in ph.items():
                if k != "<stream>":
                    msg.url = msg.url.replace(k, v)
            # ★ 目标侧归一化（必须在所有占位符替换之后 —— 此刻才是最终 URL 形态）
            if do_endpoint:
                msg.url = normalize_target_endpoint(msg.url, profile)
            msg.url = normalize_seed_resource(msg.url, allowed_resources, cur_stream)
            # ★★ 目标侧归一化**也必须覆盖头部里嵌的 URI**（P0-1 根因修复）：
            #   真实抓包的头部里嵌着端点，例如
            #     Authorization: Digest ... uri="rtsp://10.11.26.98:554/isapi/..."、
            #     Content-Base: rtsp://10.11.26.98:554/isapi/.../、
            #     Rtp-Info: url=rtsp://10.11.26.98:554/isapi/.../trackID=1;seq=4276
            #   只归一化消息级 url ⇒ 这些**外网端点原样留在 .raw 字节里**
            #   ⇒ 种子打向目标环境不存在的设备（服务端返 404，**所有健康度指标都不会红**
            #   ⇒ 静默退化），且 `corpus_gate` 的 G1 判违规。
            #   ★ **对既有基准层天然是 no-op**：头部里没有层级式 URL、或端点本就等于
            #     target 时**原样返回**（幂等）⇒ 基准层语料**逐字节不变**
            #     ⇒ 批次 1 的「回滚态（关闭时不引入产物变化）」依然成立。
            if msg.headers:
                for _hk, _hv in list(msg.headers.items()):
                    _new_hv = _hv
                    if do_endpoint:
                        _new_hv = normalize_target_endpoint_in_text(
                            _new_hv, profile)
                    # ★ 批次 1.5 改动 5（R-4）：头部里嵌的 URI **资源段**
                    #   也归一化 ⇒ 与请求行的会话名一致
                    #   ⇒ Digest/认证类头部不再与服务端**失配**（原会返 401）。
                    #   ★ 与端点归一化**独立**（端点归一化是协议级开关；
                    #     资源段归一化是**环境级**事实：目标环境只播某些会话）。
                    _new_hv = normalize_target_resource_in_text(
                        _new_hv, allowed_resources, cur_stream)
                    if _new_hv != _hv:
                        msg.headers[_hk] = _new_hv
        # 种子级 url（selected_url）也替换
        if seed.selected_url:
            if cur_stream:
                seed.selected_url = seed.selected_url.replace("<stream>", cur_stream)
            for k, v in ph.items():
                if k != "<stream>":
                    seed.selected_url = seed.selected_url.replace(k, v)
            if do_endpoint:
                seed.selected_url = normalize_target_endpoint(seed.selected_url, profile)
            seed.selected_url = normalize_seed_resource(
                seed.selected_url, allowed_resources, cur_stream)

    if not streams:
        # 无多资源清单：单占位符替换（原行为）
        for seed in seeds:
            _replace(seed, stream)
        return seeds

    # 多资源：canonical 全流展开 + 其余轮转
    out: list = []
    remaining: list = []
    for seed in seeds:
        if seed.generated_by == "rule-based:canonical-session":
            for s in streams:
                clone = SeedCorpus.from_dict(seed.to_dict())
                _replace(clone, s)
                clone.description = f"{seed.description} [stream={s}]"
                out.append(clone)
        else:
            remaining.append(seed)
    for i, seed in enumerate(remaining):
        _replace(seed, streams[i % len(streams)])
        out.append(seed)
    return out


def _rewrite_client_headers(seeds: list, profile: dict, protocol: str) -> list:
    """把「响应回传地址」头部（Via/Contact 等）的 host:port 改写到客户端（fuzzer）
    监听端口，而非服务器端口。

    背景（SIP/UDP）：服务端把响应发回 Via 头 sent-by 地址，AFLNet 用 `-l <port>`
    绑定该端口接收响应。若 Via/Contact 写服务器端口，响应发错地方，fuzzer 收不到，
    AFLNet 报「No server states have been detected」。Profile 通过 seedgen.client_side
    声明服务器/客户端地址对，本函数对头部做 server_addr→client_addr 重写（仅头部，
    不动 Request-URI url）。

    协议无关：无 client_side 声明的协议原样返回。
    """
    cfg = (profile.get("seedgen") or {}).get("client_side") or {}
    server = cfg.get("server_addr") or ""
    client = cfg.get("client_addr") or ""
    if not server or not client:
        return seeds
    # 仅重写「响应回传地址」头部（Via 是 sent-by，Contact 是客户端可达地址）
    resp_headers = {h.lower() for h in cfg.get("headers", ["Via", "Contact"])}
    # 真实流量值的 host 是公网/内网 IP 或域名（如 sip.cybercity.dk、192.168.1.2），
    # 不在 server_addr 白名单里，需用通用 host:port 正则重写为客户端监听地址，否则
    # 服务端把响应发回公网地址，fuzzer 收不到（P4-b：真实字段落地必要步骤）。
    # 正则匹配「IP:port 或 域名:port」，排除纯单词 scheme（如 sip:212）误匹配。
    host_port = re.compile(
        r"(?:(?:\d{1,3}\.){3}\d{1,3}|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+):\d{1,5}")
    for seed in seeds:
        for msg in seed.messages:
            for k, v in list(msg.headers.items()):
                if k.lower() not in resp_headers:
                    continue
                if server and server in v:
                    msg.headers[k] = v.replace(server, client)
                else:
                    # 只替换第一个 host:port（Via sent-by / Contact 主地址）
                    msg.headers[k] = host_port.sub(client, v, count=1)
    return seeds


def _renumber_cseq(seed: SeedCorpus) -> None:
    """把一条种子所有消息的 CSeq 头重排为 1..N（SIP 渲染为「序号 + 方法」）。

    仅在前置 prologue 改变消息条数后调用；对原本就递增的种子幂等。

    ★ P0-3：**action_seq 种子跳过重编号**。
      它的 CSeq 可能是**刻意的变异意图**（如「重放上一条的 CSeq 制造重放」），
      统一重编号会把该意图**静默抹掉**。
      QA 实测：SIP C/D 组 **22/23（96%）** 的 CSeq 变异被抹
      （触发源是 prologue 插入，不是 `MAX_PLAN_ACTIONS`）。
      ⇒ 判据用 `generated_by`（不新增字段 ⇒ 不改序列化 ⇒ 不影响任何既有字节）。
    """
    if (seed.generated_by or "").strip() == ACTION_SEQ_GENERATED_BY:
        return          # ★ 变异意图优先于「序号连续」
    for i, msg in enumerate(seed.messages, start=1):
        for k in list(msg.headers):
            if k.lower() == "cseq":
                msg.headers[k] = (f"{i} {msg.method}"
                                  if seed.protocol == "sip" else str(i))


def _shift_cseq_by_one(seed: SeedCorpus) -> None:
    """把所有消息的 CSeq 序号**整体 +1**（保留「序号 + 方法」形态）。

    ★ 为什么需要它（R-3 的配套）：``_prepend_session_prologue`` 会在最前插入一条
      ``CSeq: 1 <入口方法>`` 的消息 ⇒ 原有消息的序号必须**让位**，
      否则新旧序号**冲突**（两条 ``CSeq: 1``）。
    ★ 为什么是**平移**而不是 ``_renumber_cseq`` 的**重排**：
      重排会把 ``cseq-replay`` 的变异（本条序号 == 下一条序号）**静默抹掉**
      （P0-3：实测 SIP C/D 组 22/23 = 96% 的 CSeq 变异被抹）
      ⇒ 平移只改**绝对值**、**相对关系不变** ⇒ 重放形态**保留**。
    """
    for msg in seed.messages:
        for k in list(msg.headers):
            if k.lower() != "cseq":
                continue
            parts = str(msg.headers[k]).split()
            if not parts:
                continue
            try:
                number = int(parts[0])
            except (TypeError, ValueError):
                continue
            parts[0] = str(number + 1)
            msg.headers[k] = " ".join(parts)


def _prepend_session_prologue(seeds: list, bundle: dict, profile: dict) -> list:
    """P0：有状态协议——每条种子强制以「会话入口」方法开头（如 SIP 的 REGISTER）。

    profile.seedgen.session_prologue 声明入口方法；若种子首消息不是入口方法，则在其
    最前插入入口方法对应的状态机边（优先 (Idle --entry--> Idle) 无状态自环边，SIP 的
    REGISTER 是 registrar 路由上唯一返回响应的无状态自环；兜底取该方法的任意边），
    把「片段种子」变成能走通状态机的会话。插入后重排 CSeq 序号。

    背景（归因）：protorag 的 24 条种子里多数以 INVITE/UPDATE/BYE 开头，入口即
    kamailio 静默丢弃（非 REGISTER 不进 registrar 路由），导致 AFLNet 覆盖极低。
    """
    prologue = (profile.get("seedgen") or {}).get("session_prologue") or []
    if not prologue:
        return seeds
    entry_method = str(prologue[0]).strip().upper()
    if not entry_method:
        return seeds
    trans = sorted({(s, m, d) for s, m, d in bundle.get("transitions", [])})
    for seed in seeds:
        first = seed.messages[0].method.strip().upper() if seed.messages else ""
        if first == entry_method:
            continue
        # 优先无状态自环边（入口方法在入口态上自环），兜底任意同方法边
        entry_edge = next(
            ((s, m, d) for s, m, d in trans
             if m.strip().upper() == entry_method and s == d), None)
        if entry_edge is None:
            entry_edge = next(
                ((s, m, d) for s, m, d in trans
                 if m.strip().upper() == entry_method), None)
        if entry_edge is None:
            continue
        s, m, d = entry_edge
        inst = (bundle.get("message_instances") or {}).get((s, m, d))
        prologue_msg = build_message(
            m, required_headers=bundle.get("required_headers"),
            headers=bundle.get("headers"), cseq=1,
            instance_fields=inst,
            cseq_with_method=(seed.protocol == "sip"))
        # ★ R-3：⑤（action-seq）种子插 prologue 前，先把**原有**消息的 CSeq
        #   序号整体 +1，给新插入的 ``CSeq: 1 <入口方法>`` **让位**（否则序号冲突）。
        #   ★ 用**平移**而不是 ``_renumber_cseq`` 的重排 ⇒ ``cseq-replay`` 的
        #     「本条序号 == 下一条序号」形态**保留**（重排会把它抹掉 ⇒ P0-3 回归）。
        is_action_seq = (seed.generated_by or "").strip() == ACTION_SEQ_GENERATED_BY
        if is_action_seq:
            _shift_cseq_by_one(seed)
        seed.messages = [prologue_msg] + seed.messages
        seed.target_methods = [prologue_msg.method] + list(seed.target_methods)
        seed.target_state_path = [s] + list(seed.target_state_path)
        seed.description = f"{seed.description} [prologue:{entry_method}]"
        if not is_action_seq:
            _renumber_cseq(seed)
    return seeds


def _render_seq_headers(seeds: list) -> list:
    """P1：把 default_headers 中的 {seq} 占位替换为逐消息递增序号，使字段格式真实
    且唯一（branch=z9hG4bK-1/2/...、tag=1/2/...、Call-ID=1@.../2@...）。

    只处理单花括号 {seq}，与 raw_writers 的 {{xxx}} 双花括号运行时占位符体系正交、
    互不干扰（后者由落盘时统一 resolve）。
    """
    for seed in seeds:
        for i, msg in enumerate(seed.messages, start=1):
            for k, v in list(msg.headers.items()):
                if "{seq}" in v:
                    msg.headers[k] = v.replace("{seq}", str(i))
    return seeds


def _resolve_config(args) -> tuple[Optional[dict], Optional[str]]:
    """解析生效配置：返回 (focus_cfg, error_msg)。

    ★ `--focus-group` 与任一原子开关互斥（不做「后者覆盖前者」的隐式行为），
    冲突一律以退出码 2 报错。
    """
    atomic_used: list[str] = []
    if args.layers is not None:
        atomic_used.append("--layers")
    if args.no_vuln_boundary:
        atomic_used.append("--no-vuln-boundary")
    if args.order is not None:
        atomic_used.append("--order")
    if args.no_sort:
        atomic_used.append("--no-sort")
    if args.dict is not None:
        atomic_used.append("--dict")
    if args.dict_path is not None:
        atomic_used.append("--dict-path")

    if args.focus_group is not None:
        if atomic_used:
            return (None, f"--focus-group 与 {', '.join(atomic_used)} 互斥"
                         "（请只用一个入口，避免隐式覆盖）")
        if args.focused:
            return (None, "--focus-group 与 --focused 互斥"
                         "（--focused 会改写层②内容并可能截断，一次引入三个变化）")
        if args.max_seeds is not None:
            return (None, "--focus-group 与 --max-seeds 互斥"
                         "（聚焦 ≠ 砍种子；全程全量种子）")
        cfg = dict(FOCUS_GROUP_CONFIG[args.focus_group])
        cfg["focus_group"] = args.focus_group
        return (cfg, None)

    # 原子开关模式：层集合
    if args.layers is not None:
        layers = [x.strip() for x in args.layers.split(",") if x.strip()]
        bad = [x for x in layers if x not in ALL_LAYERS]
        if bad:
            return (None, f"--layers 含未知层: {', '.join(bad)}"
                         f"（可用: {', '.join(ALL_LAYERS)}）")
        # 去重且保持 ALL_LAYERS 的稳定顺序
        layers = [x for x in ALL_LAYERS if x in layers]
    else:
        layers = list(ALL_LAYERS)
    if args.no_vuln_boundary:
        layers = [x for x in layers if x != "vuln_boundary"]

    # 原子开关模式：顺序
    if args.no_sort:
        order = "natural"
    elif args.order is not None:
        order = args.order
    else:
        order = "vuln-proximity"

    # 原子开关模式：字典
    if args.dict_path is not None:
        dict_kind = "path"
    elif args.dict is not None:
        dict_kind = args.dict
    else:
        dict_kind = "protocol"

    return (dict(layers=layers, order=order, dict_kind=dict_kind,
                 focus_group=None, expect_seeds=None, expect_dict_tokens=None),
            None)


def _write_dictionary(out: Path, protocol: str, dict_kind: str,
                      bundle: dict, profile: dict,
                      resources: list) -> Optional[Path]:
    """按字典种类产出 `<out>/<protocol>.dict`，返回写入路径（none → None）。

    | kind          | 内容                                                       |
    |---------------|------------------------------------------------------------|
    | none          | 不产出字典（编排时由调用方指定 -x）                          |
    | base          | 复制仓库内 `<proto>_base.dict`（镜像内基础字典的逐字节副本）  |
    | protocol      | `generate_protocol_dict(...)`（现状 102 token）               |
    | targeted      | `generate_targeted_dict(...)`（定向字典，严格超集 base）      |
    | targeted-compact | `generate_targeted_dict(..., compact=True)`（C′ 预案）     |
    | path          | 逐字节复制 `--dict-path` 指定的文件                          |
    """
    if dict_kind == "none":
        return None
    dict_path = out / f"{protocol}.dict"
    if dict_kind == "path":
        src = Path(profile.get("_dict_path"))
        if not src.exists():
            raise FileNotFoundError(f"--dict-path 指定的文件不存在: {src}")
        dict_path.write_bytes(src.read_bytes())
        return dict_path
    if dict_kind == "base":
        base_tokens = load_base_dict_tokens(protocol)
        if not base_tokens:
            raise FileNotFoundError(
                f"找不到基础字典 {protocol}_base.dict，无法产出 --dict base")
        text = "\n".join(f'"{t}"' for t in sorted(base_tokens)) + "\n"
        dict_path.write_text(text, encoding="utf-8")
        return dict_path
    if dict_kind == "protocol":
        text = generate_protocol_dict(bundle, protocol=protocol, resources=resources)
        # default_headers 里的 {seq} 占位在种子里已解析为逐消息序号，字典须归一化
        # 为具体值（"1" 与首消息一致），否则变异字典会注入无意义的 "{seq}" 字面量。
        text = text.replace("{seq}", "1")
        dict_path.write_text(text, encoding="utf-8")
        return dict_path
    if dict_kind in ("targeted", "targeted-compact"):
        text = generate_targeted_dict(
            bundle, protocol=protocol, resources=resources,
            base_tokens=load_base_dict_tokens(protocol),
            include_trigger_fields=True,
            compact=(dict_kind == "targeted-compact"))
        text = text.replace("{seq}", "1")
        dict_path.write_text(text, encoding="utf-8")
        return dict_path
    raise ValueError(f"未知字典种类: {dict_kind}")


def resolve_source_set(protocol: str,
                       cli_sources: list | None = None) -> tuple[list[str], str]:
    """★ 批次 1.6 步 5：解析「本次消费的知识源集合」。

    Returns:
        ``(source_set, 来源说明)``。

    规则：
      · ``cli_sources`` 给了 ⇒ 用它（调用方**显式授权**，覆盖中枢声明）；
      · 否则 ⇒ 用中枢 ``sources.json`` 的 ``source_set``（**唯一权威**）；
      · 中枢没声明清单（兼容期：中枢尚未按批次 1.6 流程重建）
        ⇒ 返回空列表 ⇒ 调用方按「**不过滤**」处理（保持旧行为）。
    """
    if cli_sources:
        picked = [str(s).strip() for s in cli_sources if str(s).strip()]
        return picked, "命令行 --sources（显式覆盖中枢声明）"
    manifest = load_source_manifest(protocol)
    declared = [str(s).strip() for s in (manifest.get("source_set") or [])
                if str(s).strip()]
    return declared, "中枢 sources.json 声明"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="统一种子生成入口（协议 × 源二维解耦）")
    ap.add_argument("--protocol", default="rtsp")
    ap.add_argument("--out", default=None,
                    help="输出目录（默认 derived/seeds/<protocol>/<时间戳>/）")
    ap.add_argument("--danger", action="store_true",
                    help="追加 ② 通用危险层种子")
    ap.add_argument("--focused", action="store_true",
                    help="聚焦模式（实验教训：种子过多会摊薄变异预算、稀释漏洞导向层）："
                         "① 通用危险层走 minimal 精简（只留序列型自环/生命周期）；"
                         "② 全部种子按漏洞接近度降序排序（漏洞边界候选排最前）；"
                         "③ 可用 --max-seeds 截断，把变异预算集中到离漏洞触发点近的种子。")
    ap.add_argument("--max-seeds", type=int, default=None,
                    help="聚焦模式下截断前 N 条种子（漏洞接近度高分优先；默认不截断）")

    # ★ RQ3 新增：分组单一入口
    ap.add_argument("--focus-group", choices=["A", "B", "C", "D"], default=None,
                    help="RQ3 聚焦组单一入口（防误用）。不传则保持现有行为。")
    # ★ RQ3 新增：原子开关（仅当 --focus-group 未指定时可用）
    ap.add_argument("--layers", default=None,
                    help="逗号分隔的启用层，默认全部："
                         "edge_cover,generic_danger,vuln_boundary,canonical")
    ap.add_argument("--no-vuln-boundary", action="store_true",
                    help="关闭③漏洞边界候选层（--layers 的快捷方式）")
    ap.add_argument("--order", choices=["natural", "vuln-proximity"], default=None,
                    help="种子顺序；默认（不传）为 vuln-proximity（与现状一致）")
    ap.add_argument("--no-sort", action="store_true",
                    help="关闭排序，保持生成顺序（--order natural 的快捷方式）")
    ap.add_argument("--dict",
                    choices=["none", "base", "protocol", "targeted",
                             "targeted-compact"],
                    default=None,
                    help="变异字典来源；默认（不传）为 protocol（102 token，与现状一致）")
    ap.add_argument("--dict-path", default=None,
                    help="显式指定字典文件路径（覆盖 --dict 的自动产物）")
    ap.add_argument("--manifest", action="store_true",
                    help="落盘 manifest.json（种子溯源：层/分数/排名/MD5/模式标签）")
    ap.add_argument("--target-env", default=None, metavar="NAME",
                    help="目标环境名（profile.seedgen.environments 中声明）。"
                         "用于施加环境级约束：可播资源子集（RTSP：目标环境只有 7 个"
                         "媒体文件，其余会话服务端返 404）+ 消息起点方法白名单"
                         "（SIP：AFLNet 分区器只认 REGISTER/INVITE/ACK/BYE）。"
                         "不指定且 profile 未声明默认环境 → 不施加环境级约束"
                         "（历史语料仍可逐字节复现）。")
    # ★ 批次 1.6 步 5（D-5 解法）：消费端的**过滤口**（**双保险**）。
    #   缺省 = 中枢 `sources.json` 声明的源集合（唯一权威）⇒ 消费端只消费
    #   本次参与的源；显式传参 = 调用方的**显式授权**（覆盖中枢声明）。
    ap.add_argument("--sources", nargs="+", default=None, metavar="SRC",
                    help="★ 批次 1.6 步 5：本次消费的知识源（**双保险**）。"
                         "缺省 = 中枢 sources.json 声明的源集合；"
                         "显式传参则覆盖中枢声明（调用方显式授权）。")
    ap.add_argument("--strict-source-only", action="store_true",
                    help="★ 批次 2.3：**严格单源模式** —— 关掉所有"
                         "「绕过 source_set」的跨源旁路："
                         "① ⑤ 层底料排除 vuln_boundary（vuln 源）种子，"
                         "traffic ∉ 源集合时禁用真实抓包兜底；"
                         "② 不启用 profile.allowed_methods 白名单"
                         "（它是**源码侧**人工白名单，会裁掉 RFC 抽到的真实方法）。"
                         "★ 默认**关闭** ⇒ 不改变既有产物字节。")
    args = ap.parse_args()

    cfg, err = _resolve_config(args)
    if err:
        return _fail(err)

    protocol = args.protocol.lower()
    profile = _load_profile(protocol)
    # ★ 目标环境选择（环境级事实：可播资源 / 消息起点方法）。
    #   未显式指定且 profile 未声明默认环境 → 不施加任何环境级约束（行为与历史一致，
    #   历史语料仍可逐字节复现）。见 core/fused/downstream/target_env.py。
    try:
        env_cfg = effective_config(profile, args.target_env)
    except KeyError as exc:
        return _fail(str(exc))
    env_name = env_cfg.pop("_environment", None)
    seedgen_cfg = env_cfg
    if args.dict_path is not None:
        profile = dict(profile)
        profile["_dict_path"] = args.dict_path

    focus_group = cfg.get("focus_group")
    is_focus = focus_group is not None

    # ★ 协议级聚焦组标定：profile.seedgen.focus_group 覆盖 FOCUS_GROUP_CONFIG
    #   里 RTSP 标定的 dict_kind / expect_seeds / expect_dict_tokens。
    #   换协议 = 在 profile 里加一份 focus_group 标定，脚本零改动。
    #   未标定的协议回退到 FOCUS_GROUP_CONFIG 默认值（RTSP 标定）。
    if is_focus:
        fg_cfg = (seedgen_cfg.get("focus_group") or {}).get(focus_group) or {}
        if fg_cfg.get("dict") is not None:
            cfg["dict_kind"] = fg_cfg["dict"]
        if fg_cfg.get("seeds") is not None:
            cfg["expect_seeds"] = fg_cfg["seeds"]
        if fg_cfg.get("dict_tokens") is not None:
            cfg["expect_dict_tokens"] = fg_cfg["dict_tokens"]

    layers = list(cfg["layers"])
    order = cfg["order"]
    dict_kind = cfg["dict_kind"]

    # ★ 消息起点方法白名单（harness 级事实）：只有这些方法能起始一条消息。
    #   被排除的方法**不丢弃**——它们仍是状态机的一条边（bundle["transitions"] 完整保留）、
    #   仍在变异字典里（知识保留），只是不参与「构造种子消息序列」的边遍历。
    boundary = boundary_methods(seedgen_cfg)
    if boundary:
        print(f"目标环境: {env_name or '(未选)'} | "
              f"消息起点方法: {boundary}")

    if args.out is None:
        args.out = str(paths.seeds_dir(protocol)
                       / datetime.now().strftime("%Y%m%d_%H%M%S"))

    views = load_fact_views(protocol)
    if not views:
        print(f"!! 无 facts（协议 {protocol}），请先运行 "
              f"build_hub.py --sources <源> --protocol {protocol}")
        return 1
    # ★ 批次 1.5：消费端**显式装载**语义规则并显式传参。
    #   ★ 契约（bundle 2.0）：「显式传入 ``semantic_rules=``」= 调用方的
    #     **显式授权**，**优先于 D-6 开关** ⇒ 规则**一定**被装载并投影。
    #   ★ **不改 D-6 的默认值**（不变量 I5.4：D-6 OFF 且未显式传参 ⇒ bundle
    #     不含 ``semantic_rules``/``bundle_schema_version`` ⇒ 与 B-8 之前
    #     逐字节一致）⇒ 默认路径**不被悄悄改变**。
    #   ★ 效果：RFC 源抽出的语义规则 ⇒ 投影出 ``legal_boundary`` /
    #     ``response_expectation`` ⇒ 「源 A 第四类」约束边界候选**从 0 变非 0**。
    semantic_rules = load_semantic_rules(protocol)
    # ★ 批次 1.6 步 5：消费端**据中枢清单**确定本次参与的源，并打印清单。
    #   · 缺省 = 中枢 `sources.json` 的 `source_set`（**唯一权威**）
    #   · `--sources` 显式传参 = 调用方**显式授权**（覆盖中枢声明）
    #   · 中枢没声明清单（兼容期）⇒ 不过滤（保持旧行为）
    source_set, _src_origin = resolve_source_set(protocol, args.sources)
    print(f"本次知识来源清单: {source_set or '(中枢未声明 ⇒ 不过滤)'}  ← {_src_origin}")
    _manifest = load_source_manifest(protocol)
    if _manifest:
        print(f"  中枢构建: build_ids={_manifest.get('build_ids')} "
              f"built_at={_manifest.get('built_at')}")
    bundle = assemble_bundle(views, semantic_rules=semantic_rules,
                              source_set=source_set or None,
                              apply_allowed_methods=not args.strict_source_only)
    if semantic_rules:
        print(f"语义规则: 装载 {len(semantic_rules)} 条 → "
              f"legal_boundary {sum(len(v) for v in (bundle.get('legal_boundary') or {}).values())} 条 / "
              f"response_expectation {sum(len(v) for v in (bundle.get('response_expectation') or {}).values())} 条")
    # 注入 profile.seedgen.default_headers 到 headers 桶（兜底默认头值）。
    # 某些协议的方法（如 SIP 的 REGISTER 是 Idle→Idle 自环）AutoSeeder 只抽到
    # 少量字段实例、headers 桶也为空，导致必填头（Via/From/To/Contact/Max-Forwards）
    # 渲染为空、报文畸形。注入默认头值兜底，保证每条消息头完整。
    #
    # P4-b：真实流量值优先——default_headers 的 {seq} 占位值只作兜底，仅当该字段
    # 没有真实值（traffic/source 均未贡献）时才注入；否则保留真实值（真实 To tag /
    # Contact / Call-ID 等）在 values 首位，让种子字段用真实流量值而非模板占位。
    def_headers = (seedgen_cfg or {}).get("default_headers") or {}
    if def_headers:
        bucket = bundle.setdefault("headers", {})
        for _name, _val in def_headers.items():
            _info = bucket.setdefault(_name, {})
            _vals = _info.setdefault("values", [])
            # 已有非占位真实值 → 不注入兜底占位值
            has_real = any("{seq}" not in str(v) for v in _vals)
            if has_real:
                continue
            if _val not in _vals:
                _vals.insert(0, _val)
    # 五源分工传导（P0）：打印可用源 + 方法白名单
    from core.fused.downstream.source_availability import (
        available_sources, whitelist_methods,
    )
    srcs = available_sources(bundle)
    whitelist = whitelist_methods(bundle, profile)
    print(f"分桶: methods={sorted(bundle['methods'])}")
    print(f"  可用知识源: {sorted(srcs) or '(无)'}")
    print(f"  方法白名单({len(whitelist)}): {whitelist}")
    print(f"  transitions={len(bundle['transitions'])} 条, "
          f"message_instances={len(bundle.get('message_instances') or {})} 条")

    transitions = bundle["transitions"]
    if not transitions:
        print("!! 无状态机转移，无法生成种子")
        return 1
    if not whitelist:
        print("!! 方法白名单为空（所有知识源均未提供方法），无法生成种子")
        return 1
    # 防御性过滤：去掉白名单外的方法的转移（多源融合时由白名单约束）
    transitions = [t for t in transitions if t[1] in whitelist]
    if not transitions:
        print("!! 白名单过滤后无状态机转移，无法生成种子")
        return 1

    # ★ 消息起点方法过滤（harness 级）：只保留「能起始一条消息」的方法的转移边，
    #   用于**构造种子消息序列**。
    #   ★ bundle["transitions"] 本身不被修改 → 被排除的方法（OPTIONS/SUBSCRIBE/...）
    #     仍是状态机的一条边（知识保留），也仍进变异字典；只是不作为消息起点。
    #   ★ 这与「丢弃这些方法」有本质区别：丢弃会让状态机出现断边、覆盖率统计失真，
    #     而这里只是改变「消息起点」这一 fuzzer 传输语义角色。
    seed_transitions = filter_transitions_by_boundary(transitions, boundary)
    if boundary and len(seed_transitions) != len(transitions):
        dropped = sorted({t[1] for t in transitions} - {t[1] for t in seed_transitions})
        print(f"  消息起点过滤: 保留 {len(seed_transitions)}/{len(transitions)} 条转移边, "
              f"不作为消息起点的方法: {dropped}")
    transitions = seed_transitions
    if not transitions:
        print("!! 消息起点方法过滤后无可用转移，无法生成种子")
        return 1

    seeds = []
    # ① 结构覆盖（协议无关）
    if "edge_cover" in layers:
        ec = edge_cover(transitions, bundle.get("required_headers"),
                        bundle.get("headers"),
                        bundle.get("message_instances"), protocol=protocol,
                        method_order=bundle.get("method_order"))
        seeds += ec
        print(f"① 结构覆盖: {len(ec)} 条种子")
    else:
        print("① 结构覆盖: 跳过（层未启用）")

    # ② 通用危险
    # ★ 分组模式强制开启层②（否则 RTSP profile 的 seedgen.danger=false 会让
    #   B/C/D 少 15 条种子——层② generic_danger 的净贡献, 实测 50→35 条,
    #   破坏与 RQ1.2 语料的连续性）
    # ★ 分组模式强制 minimal=False（--focused 与 --focus-group 互斥，
    #   此处显式写死并断言，避免未来有人改回去引入第二个变量）
    if is_focus:
        assert args.focused is False, "分组模式下 --focused 必须为 False"
        danger_on = True
        danger_minimal = False
    else:
        danger_on = bool(args.danger or seedgen_cfg.get("danger"))
        danger_minimal = bool(args.focused)
    if danger_on and "generic_danger" in layers:
        d = generic_danger(transitions, bundle.get("headers"),
                           bundle.get("required_headers"),
                           minimal=danger_minimal,
                           precondition=bundle.get("precondition"),
                           session_header=bundle.get("session_header"),
                           message_instances=bundle.get("message_instances"),
                           protocol=protocol)
        seeds += d
        print(f"② 通用危险: {len(d)} 条种子"
              f"{'（minimal 精简）' if danger_minimal else ''}")
    else:
        print("② 通用危险: 跳过（层未启用）")

    # ③ 漏洞边界候选（序列型漏洞模式，永远，不调 LLM；让漏洞知识参与生成）
    if "vuln_boundary" in layers:
        vuln_cands = _derive_vuln_boundary_candidates(bundle, profile, protocol,
                                                      boundary=boundary)
        seeds += vuln_cands
        print(f"③ 漏洞边界候选: {len(vuln_cands)} 条种子")
    else:
        print("③ 漏洞边界候选: 跳过（层未启用）")

    # ④ 黄金路径
    canonical_flow = seedgen_cfg.get("canonical_flow")
    if "canonical" in layers and canonical_flow:
        # ★ 传入**过滤后**的转移边：黄金路径的消息也必须是「能起始消息」的方法，
        #   否则 canonical_flow 里若含被排除方法会生成一条边界不合法的种子。
        canon = _build_canonical_seed(bundle, canonical_flow, protocol,
                                      transitions=transitions)
        if canon is not None:
            seeds.append(canon)
            print(f"黄金路径: {' -> '.join(str(c) for c in canonical_flow)}")
    elif "canonical" in layers:
        print("黄金路径: 跳过（profile 未声明 canonical_flow）")

    # ⑤ 字段级 action-sequence 变异（批次 1：SemFuzz 迁移项 A）
    #   ★ 由 profile.seedgen.action_seq.enabled 控制（**默认关闭** ⇒ 关闭时
    #     **批次 1 的改动不引入任何产物变化** —— 回滚手段必须成立）。
    #   ★ 底料 = **真实抓包种子**（已发表语料 / kb 真实抓包），不是从零构造。
    #   ★ 不调 LLM（确定性）；LLM 兜底在 action_seq.plan_actions(llm=...) 里。
    action_seq_ledger = ActionLedger()
    action_seq_info: dict = {}
    action_seq_seeds: list = []
    if _action_seq_enabled(profile):
        action_seq_seeds, action_seq_info = _build_action_seq_seeds(
            bundle, profile, protocol, group=focus_group,
            ledger=action_seq_ledger, env_cfg=env_cfg,
            strict_source_only=args.strict_source_only,
            source_set=source_set or None)
        # ★ 追加动作**延后到基准层去重之后**（见下方 `_append_action_seq_seeds` 调用）：
        #   若 ⑤ 先加入再统一去重，⑤ 与基准层的**近重复**会被判重 ⇒
        #   基准层里被判重的那条被 ⑤ 的副本顶替 ⇒ **基准层集合发生变化**
        #   （实测 rtsp/B 基准层 65 → 66、smtp/B 61 → 73）
        #   ⇒ 违反「ON 时基准层条数与 OFF 完全相同」。
        # ★ R-1 / R-3 的结构性修复：⑤ 的**全部**后处理已收敛到
        #   `_postprocess_action_seq_seeds` 一个函数里（prologue → {seq} →
        #   端点/资源归一化 → 响应回传地址重写）。
        #   ★ 历史教训：R-1（漏 `_rewrite_client_headers`）与
        #     R-3（漏 `_prepend_session_prologue`）**连续两次**同根因
        #     ——「⑤ 在流程末尾追加 ⇒ 分叉调用 ⇒ 漏步骤」⇒ 这里**不再分叉**。
        #   ★ 这里**只**做去重（去重应在**最终内容**上做）。
        if action_seq_seeds:
            action_seq_seeds = dedupe_seeds(action_seq_seeds)
        print(f"⑤ 字段级 action-sequence 变异: {len(action_seq_seeds)} 条种子"
              f"（底料来源: {action_seq_info.get('source') or '（无）'}, "
              f"底料条数: {action_seq_info.get('base_count', 0)}）")
        if len(action_seq_ledger):
            print(f"   拒绝动作 {len(action_seq_ledger)} 条: "
                  f"{action_seq_ledger.reason_counts()}")
    else:
        print("⑤ 字段级 action-sequence 变异: 跳过"
              "（profile.seedgen.action_seq.enabled 未开启）")

    # ★ 去重**只在基准层内**做；⑤ 在此之后**纯追加**（不参与去重）。
    #   理由见上方注释：⑤ 若参与去重，会顶替基准层里的近重复种子
    #   ⇒ 基准层集合变化 ⇒ 违反「ON 时基准层条数与 OFF 完全相同」。
    seeds = dedupe_seeds(seeds)
    print(f"去重后: {len(seeds)} 条")

    # P0：会话前置（有状态协议片段种子强制以入口方法开头，如 SIP 的 REGISTER）
    seeds = _prepend_session_prologue(seeds, bundle, profile)
    # P1：default_headers 的 {seq} 占位替换为逐消息递增序号（字段格式真实且唯一）
    seeds = _render_seq_headers(seeds)

    # URL 占位符替换 + 多资源覆盖（协议无关，读 profile.url_placeholders + resources_file）
    # ★ env_cfg 传入 → 目标环境可播资源子集限定生效（RTSP 缺陷修复）
    seeds = _apply_url_placeholders(seeds, profile, protocol, env_cfg)
    print(f"多资源覆盖后: {len(seeds)} 条")

    # 响应回传地址重写（SIP 等头部协议的 Via/Contact host:port → 客户端监听端口）
    seeds = _rewrite_client_headers(seeds, profile, protocol)

    # 排序：natural = 保持生成序（不调用 prioritize_seeds）；vuln-proximity = 降序
    if order == "natural":
        print(f"顺序: 自然序（保持生成序，{len(seeds)} 条）")
    elif args.focused:
        # --focused 保留原有语义：minimal 精简 + 排序 + 可选截断
        seeds = prioritize_seeds(seeds, max_seeds=args.max_seeds)
        print(f"聚焦排序后: {len(seeds)} 条（漏洞接近度降序"
              f"{'，已按 --max-seeds 截断' if args.max_seeds else ''}）")
    else:
        seeds = prioritize_seeds(seeds)
        print(f"漏洞接近度排序后: {len(seeds)} 条（全量，漏洞边界候选排前）")

    # ★ P0-4（语义修正）：**开启 ⑤ 不得改变基准层的条数**。
    #   原实现在 ⑤ 开启时调用 `_converge_to_contract` ⇒ **顺带把基准层也收敛了**
    #   （实测 rtsp/A 基准层 52 → 38）⇒ 「开关注入了额外行为变化」，
    #   违反「ON 时基准层条数与 OFF 完全相同」这条验收。
    #   ⇒ 现在：**不做任何收敛** —— ⑤ 种子纯追加，基准层一条不动。
    #   契约漂移**照旧由 G5 报出**（该漂移仍漂移，**不许被掩盖**）：
    #   G5 已改为只查**基准层**条数，与 OFF 态的判定关系完全一致。
    if action_seq_seeds:
        before = len(seeds)
        seeds = _append_action_seq_seeds(seeds, action_seq_seeds)
        print(f"⑤ 追加: {before} → {len(seeds)} 条"
              f"（基准层 {before} 条不变，⑤ {len(action_seq_seeds)} 条纯追加）")

    out = Path(args.out)
    # ★ P2-5：文件名宽度按**基准层条数**算（⑤ 是纯追加，总条数变大不应改动
    #   基准层的文件名）⇒ ⑤ 层另用 ``M`` 前缀的独立编号空间。
    base_count = len(seeds) - len(action_seq_seeds)
    written = write_seeds(seeds, out, base_count=base_count)
    print(f"落盘: {len(written)} 个 .raw 到 {out}")

    # 种子数自检（防止层③被意外跳过这类静默错误）
    # ★ D3：不符合时**不立即退出**，先写完字典与 manifest（溯源）再返回 3 ——
    #   否则「条数不符」的语料没有 manifest.json，闸门（corpus_gate）无法判出
    #   它的构建环境（env 级还是协议级），会退回协议级契约报出误导性的期望值。
    expect_seeds = cfg.get("expect_seeds")
    seeds_mismatch = False
    if expect_seeds is not None and len(written) != expect_seeds:
        seeds_mismatch = True
        print(f"!! 种子数不符: 期望 {expect_seeds}，实际 {len(written)}"
              "（分组配置与实际生成不一致）", file=sys.stderr)

    # 定向变异字典
    # ★ env_cfg 传入 → 目标环境可播资源子集限定对字典同样生效（字典里的会话名
    #   token 与种子 URL 里的会话名保持一致，避免字典提示出不可播的会话）。
    resources = _load_resources(profile, protocol, env_cfg)
    dict_path = _write_dictionary(out, protocol, dict_kind, bundle, profile,
                                  resources)
    dict_info: dict = {"path": "", "token_count": 0, "md5": ""}
    if dict_path is not None:
        import hashlib
        text = dict_path.read_text(encoding="utf-8")
        tokens = [ln for ln in text.splitlines() if ln.strip()]
        dict_info = {
            "path": dict_path.name,
            "token_count": len(tokens),
            "md5": hashlib.md5(dict_path.read_bytes()).hexdigest(),
        }
        print(f"字典: {len(tokens)} 个 token 到 {dict_path}")
        # ★ 字典 token 数自检（非阻断：仅警告，供标定与一致性排查）
        expect_dict_tokens = cfg.get("expect_dict_tokens")
        if expect_dict_tokens is not None and len(tokens) != expect_dict_tokens:
            print(f"!! 字典 token 数不符: 期望 {expect_dict_tokens}，"
                  f"实际 {len(tokens)}（分组配置与实际生成不一致）",
                  file=sys.stderr)

    # manifest（种子溯源：层/分数/排名/MD5/模式标签）
    # ★ 分组模式**默认产出** manifest —— T6 变异命中率归因完全依赖它，
    #   若需靠外部脚本记得加 --manifest，极易漏（漏了 → 归因失效）。
    #   非分组模式保持原行为：仅在显式 --manifest 时产出（向后兼容）。
    if args.manifest or is_focus:
        # ★ ⑤ 路径的溯源：只有**开启**时才进 manifest ⇒ 关闭时 manifest
        #   **不受批次 1 影响**（回滚手段必须成立）。
        manifest_layers = list(layers)
        if _action_seq_enabled(profile):
            manifest_layers.append(ACTION_SEQ_LAYER_NAME)
        manifest_cfg = {
            "focus_group": focus_group,
            "layers": manifest_layers,
            "order": order,
            "dict_kind": dict_kind,
            "danger_minimal": danger_minimal,
            "max_seeds": args.max_seeds,
            # ★ 目标环境溯源：环境级约束直接决定种子内容，必须随 manifest 落盘，
            #   否则同一份语料无法区分「按哪个环境生成的」。
            "target_env": env_name or "",
            "playable_resources": (list(playable_resource_names(
                profile, protocol, env_cfg)) if env_cfg
                and env_cfg.get("playable_resources_file") else []),
            "message_boundary_methods": list(boundary) if boundary else [],
        }
        if _action_seq_enabled(profile):
            manifest_cfg["action_seq"] = dict(action_seq_info)
        manifest = build_manifest(seeds, out, protocol=protocol,
                                  group=focus_group, seedgen_cfg=manifest_cfg,
                                  dictionary=dict_info, base_count=base_count)
        mpath = write_manifest(manifest, out / "manifest.json")
        print(f"manifest: {manifest['seed_count']} 条 → {mpath}")

    for name in written[:5]:
        raw = (out / name).read_bytes().decode("utf-8", errors="replace")
        print(f"  --- {name} ---")
        print("  " + repr(raw)[:220])
        print()

    print("=" * 64)
    print(f"完成。种子目录: {out}")
    print("=" * 64)
    if seeds_mismatch:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
