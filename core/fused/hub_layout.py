# -*- coding: utf-8 -*-
"""core/fused/hub_layout.py —— 中枢的**知识分类落位**（阶段 C，2026-11-09 新增）。

★ 阶段 C 的目标：**中枢按「知识分类」存储**，而不是按 aspect 存储。
  旧布局（批次 1.6）：``derived/hub/facts/<aspect>.jsonl``（16 个 aspect 文件）
  新布局（阶段 C）  ：``derived/hub/<分类>/<文件>.jsonl``（6 个分类）

      A_structure/structure.jsonl      有什么
      B_interaction/interaction.jsonl  怎么连
      C_constraints/constraints.jsonl  必须 / 不许怎样
      D_construction/construction.jsonl 怎么写出来
      E_observation/observation.jsonl  实际什么样
      F_security/security.jsonl        哪里可能出错

★ **落位依据** = ``fused_hub/schema/knowledge_slots.json`` 的 ``aspect_map``
  （aspect → (category, slot)）⇒ **不改抽取器**，只重排已有事实。

★★ **顺序契约（本模块能保持「种子逐字节不变」的关键）**：
  分类文件内的记录**按全局位置排序**（``index/order.jsonl`` 记全局下标）
  ⇒ 读取端按全局位置排序后，**遍历序与旧布局逐字节一致**
  ⇒ ``methods``/``headers`` 的**键插入序**不变 ⇒ 种子编号不漂移。
  （★ 这是批次 1.6 的教训：顺序变了 ⇒ rtsp 58 条种子 MD5 全变。）

★ **按协议替换**（中枢共用一套 ⇒ 一次只装一个协议，但护栏需要多协议共存）：
  写入时只**替换本协议**的记录，其它协议的记录原样保留。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional

from core.fused.knowledge_slots import category_file, category_ids, locate

#: 顺序索引文件名（放在 ``derived/hub/index/order.jsonl``）
ORDER_INDEX_NAME = "order.jsonl"


def index_path(hub_root: Path) -> Path:
    """顺序索引路径 ``derived/hub/index/order.jsonl``。"""
    return hub_root / "index" / ORDER_INDEX_NAME


def classify(record: dict[str, Any]) -> tuple[str, str]:
    """把一条 fact 判定到 ``(category, slot)``。

    ★ 用 ``fact_key.aspect`` + ``fact_key.subject.type`` 查
      ``knowledge_slots.aspect_map``；``by_entity_type`` 的动态槽位
      由 ``subject.type`` 决定（如 definition@method ⇒ A.methods）。
    ★ 查不到 ⇒ 归到 ``C_constraints``（**保守兜底**：约束类最通用）
      且不丢数据（槽位名用 aspect 名）。
    """
    fk = record.get("fact_key") or {}
    aspect = str(fk.get("aspect") or "")
    stype = str((fk.get("subject") or {}).get("type") or "")
    loc = locate(aspect, stype)
    if loc:
        return loc
    # ★ 兜底：未知 aspect ⇒ C_constraints/<aspect>
    return ("C_constraints", aspect or "unknown")


def collect(records: Iterable[tuple[Any, str, dict[str, Any]]]
            ) -> tuple[dict[str, list[tuple[int, str, dict]]], dict[str, list[int]]]:
    """收集要落盘的记录。

    Args:
        records: ``(全局下标, record)`` 的序列。

    Returns:
        ``(by_category, positions)``
        · ``by_category``: ``{category: [(全局下标, 原始行, record), ...]}``
        · ``positions``: ``{category: [全局下标, ...]}``（升序）
    """
    by_cat: dict[str, list[tuple[int, str, dict]]] = {}
    pos: dict[str, list[int]] = {}
    for order, line, view in records:
        cat, _slot = classify(view)
        by_cat.setdefault(cat, []).append((order, line, view))
        pos.setdefault(cat, []).append(order)
    for c in by_cat:
        by_cat[c].sort(key=lambda t: t[0])      # ★ 按全局位置排序
        pos[c].sort()
    return by_cat, pos


#: fact 级 ``epistemic``（四档）← claim 级 ``epistemic_type``（细粒度）的映射
_EPI_MAP = {
    "must": "normative",
    "normative": "normative",
    "normative_unspecified": "normative",
    "descriptive": "informative",
    "observed": "observed",
    "inferred": "inferred",
}


def _fact_epistemic(view: dict[str, Any]) -> str:
    """fact 级 ``epistemic``（normative / informative / observed / inferred）。

    ★ 由 claim 级 ``epistemic_type``（细粒度）**归并** ⇒ 两级并存：
      claim 级保留原始判据（must/descriptive/…）⇒ 既有口径**不受影响**。
    """
    _best = ""
    _rank = {"normative": 3, "informative": 2, "observed": 1,
              "inferred": 0}
    for c in (view.get("all_claims") or []):
        _e = _EPI_MAP.get(str(c.get("epistemic_type") or "").strip().lower())
        if _e and (_rank.get(_e, -1) > _rank.get(_best, -1)):
            _best = _e
    return _best or "informative"


def _fact_resolution(view: dict[str, Any]) -> Optional[dict[str, Any]]:
    """由 ``all_claims`` 推导 ``resolution``（C2：必填 ⇒ 不再是 ``null``）。

    ★ 单 claim ⇒ ``single_source``；多 claim ⇒ ``consensus``（取第一个为 winner）。
    """
    claims = view.get("all_claims") or []
    if not claims:
        return None
    if len(claims) == 1:
        _strategy = "single_source"
        _reason = "唯一 claim"
    else:
        _strategy = "consensus"
        _reason = f"{len(claims)} 个 claim，取首个为 winner"
    _cid = str((claims[0] or {}).get("claim_id") or "")
    return {
        "strategy": _strategy,
        "decided": None,
        "winners": {"value": _cid} if _cid else {},
        "reason": _reason,
    }


def _fact_entity(view: dict[str, Any]) -> Optional[dict[str, Any]]:
    """fact 级 ``entity``（entity_id + 类型 + 名称 + participants）。

    ★ 关系型 fact ⇒ participants = [source / via / target]（端点也带 entity_id）。
    """
    from core.fused.hub_entities import fact_entity_id
    fk = view.get("fact_key") or {}
    subj = fk.get("subject") or {}
    _eid = fact_entity_id(view)
    if not _eid:
        return None
    _out = {
        "entity_id": _eid,
        "type": str(subj.get("type") or ""),
        "name": str(subj.get("name") or ""),
        "aliases": [],
    }
    _quals = subj.get("qualifiers") or {}
    if str(subj.get("type") or "").strip().lower() == "relation":
        _parts = []
        for _role, _key in (("source", "source"), ("via", "method"),
                          ("target", "target")):
            _d = _quals.get(_key) or {}
            _nm = str(_d.get("name") or "")
            if not _nm:
                continue
            _peid = entity_id_of(fk.get("protocol"),
                                  _d.get("type"), _nm)
            _parts.append({"role": _role, "entity_id": _peid,
                           "name": _nm})
        if _parts:
            _out["participants"] = _parts
    return _out


def entity_id_of(protocol: Any, etype: Any, name: Any) -> str:
    """（薄封装）实体 id 生成 —— 避免 hub_layout 直接依赖 hub_entities 的内部。
    """
    from core.fused.hub_entities import entity_id
    return entity_id(str(protocol or ""), str(etype or ""),
                   str(name or ""))

def _upgrade_record(line: str, view: dict[str, Any]) -> str:
    """**阶段 C2**：把 fact 升级成 v2 记录结构。

    ★ **纯增量**（既有字段一律不动）：
      · 追加 ``entity``   = {entity_id, type, name, participants[]}
      · 追加 ``epistemic`` = 四档（由 claim 级 epistemic_type 归并）
      · ``resolution`` 由 ``null`` 补成实际内容（单/多 claim 两种策略）
    ★ **字符串级替换**（不是整体重新序列化）⇒ 除被替换的字段外，
      原有字节**完全不变** ⇒ 顺序契约与内容等价性都不受影响。
    """
    _s = line.rstrip()
    if not _s.endswith("}"):
        return line
    _add = []
    _ent = _fact_entity(view)
    if _ent is not None:
        _add.append('"entity": ' + json.dumps(_ent, ensure_ascii=False))
        # ★ 顶层也保留 ``entity_id``（C3 契约：fact 引用实体主表）
        _eid = str(_ent.get("entity_id") or "")
        if _eid and '"entity_id"' not in _s:
            _add.append('"entity_id": ' + json.dumps(_eid, ensure_ascii=False))
    _add.append('"epistemic": '
                + json.dumps(_fact_epistemic(view), ensure_ascii=False))
    _res = _fact_resolution(view)
    if _res is not None:
        _null = chr(34) + "resolution" + chr(34) + ": null"
        if _null in _s:
            _s = _s.replace(_null,
                             chr(34) + "resolution" + chr(34) + ": "
                             + json.dumps(_res, ensure_ascii=False), 1)
    if not _add:
        return _s
    return _s[:-1] + ", " + ", ".join(_add) + "}"

def _with_entity_id(line: str, view: dict[str, Any]) -> str:
    """给 fact 行**追加** ``entity_id``（C3：fact 引用实体主表）。

    ★ **字符串插入**（不是重新序列化）⇒ 原有字节**完全不变**
      ⇒ 只多一个字段 ⇒ 顺序契约与内容等价性都不受影响。
    """
    from core.fused.hub_entities import fact_entity_id
    _eid = fact_entity_id(view)
    if not _eid or "\"entity_id\"" in line:
        return line
    _s = line.rstrip()
    if not _s.endswith('}'):
        return line
    return _s[:-1] + ', ' + chr(34) + 'entity_id' + chr(34) + ': ' \
           + json.dumps(_eid, ensure_ascii=False) + '}'

def _write_entity_table(hub_root: Path,
                       by_cat: dict[str, list[tuple[int, str, dict]]],
                       protocol: str) -> int:
    """写**实体主表** ``index/entities.jsonl``（C3）。

    ★ 实体主表是**跨分类的唯一索引** ⇒ 同一实体在 A/B/C 分类里出现时，
      它们指向**同一个** ``entity_id`` ⇒ 事实/关系/规则/图可对齐。
    ★ 保留其它协议的实体（中枢共用一套 ⇒ 多协议共存）。
    """
    from core.fused.hub_entities import build_entity_index
    hub_root = Path(hub_root)
    pk = str(protocol or "").strip().lower()
    d = hub_root / "index"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / "entities.jsonl"
    # 已有实体（其它协议的）⇒ 保留
    _old: list[dict] = []
    if dest.is_file():
        for ln in dest.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                e = json.loads(ln)
            except json.JSONDecodeError:
                continue
            _kp = str(e.get("protocol") or "").strip().lower()
            if _kp and _kp != pk:
                _old.append(e)
    # 本协议的实体（从**落盘的事实**构建 ⇒ 与 fact 里的引用一致）
    _facts: list[dict] = []
    for _cat in sorted(by_cat):
        for _o, _ln, _v in by_cat[_cat]:
            _facts.append(_v)
    _ents, _detail = build_entity_index(_facts)
    _all = _old + _ents
    _all.sort(key=lambda e: str(e.get("entity_id") or ""))
    with dest.open("w", encoding="utf-8", newline="") as fh:
        for e in _all:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return len(_all)

def write_classified(hub_root: Path,
                     records: Iterable[tuple[Any, str, dict[str, Any]]],
                     protocol: str = "",
                     ) -> dict[str, int]:
    """把事实按**知识分类**落盘（阶段 C 的落位器）。

    Args:
        hub_root: 中枢根（``derived/hub/``）。
        records: ``(全局下标, 原始行字符串, record)`` 序列。
            ★ **全局下标必须是「旧布局的遍历序」** ⇒ 落位后按它排序
            就能还原原序 ⇒ 种子编号不漂移。
        protocol: 本次写入的协议（用于**按协议替换**）。

    Returns:
        ``{category: 条数}``。
    """
    hub_root = Path(hub_root)
    pk = str(protocol or "").strip().lower()
    typed = [(int(o), str(ln), v) for o, ln, v in records]
    by_cat, _pos = collect(typed)

    # ★ ★ **按协议分块**（2026-11-09 阶段 C）：
    #   分类文件内 = [其它协议的块…] + [本协议的块]
    #   ★ **块内**保持各自的全局位置序 ⇒ **单协议时与旧布局逐字节一致**；
    #   ★ **多协议时**每个协议的**内部顺序**也不变 ⇒ 种子不漂移。
    _blocks: dict[str, list[list[str]]] = {}
    for cat in category_ids():
        d = hub_root / cat
        if not d.is_dir():
            continue
        for jf in sorted(d.glob("*.jsonl")):
            byp: dict[str, list[str]] = {}
            for ln in jf.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    v = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                _kp = str((((v.get("fact_key") or {}).get("protocol"))
                           or "")).strip().lower()
                if _kp and _kp != pk:
                    byp.setdefault(_kp, []).append(ln)   # ★ 别的协议 ⇒ 保留
            _blocks[jf.name] = [v for _k, v in sorted(byp.items())]

    written: dict[str, int] = {}
    index_rows: list[dict] = []
    for cat in sorted(by_cat):
        items = by_cat[cat]
        if not items:
            continue
        rel = category_file(cat)
        dest = hub_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        _others = _blocks.get(dest.name) or []
        with dest.open("w", encoding="utf-8", newline="") as fh:
            for blk in _others:
                for ln in blk:
                    fh.write(ln + "\n")
            for _o, ln, _v in items:
                fh.write(_upgrade_record(ln, _v) + "\n")
        written[cat] = len(items)
        index_rows.append({"file": rel,
                           "positions": [o for o, _l, _v in items],
                           "kept_blocks": [[len(b)] for b in _others],
                           "count": len(items),
                           "protocol": pk})

    # ★ 顺序索引（读端据此还原**全局遍历序** ⇒ 种子逐字节不变）
    #   ★ **累积**：保留**其它协议**的行（中枢共用一套 ⇒ 多协议共存）
    #     ⇒ 否则后构建的协议会覆盖前一个的��置 ⇒ 顺序错乱。
    ip = index_path(hub_root)
    ip.parent.mkdir(parents=True, exist_ok=True)
    _old_rows: dict[str, dict] = {}
    if ip.is_file():
        for ln in ip.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            f = str(r.get("file") or "")
            _rp = str(r.get("protocol") or "")
            if f and _rp != pk:
                # ★ key 含协议 ⇒ **同一文件可有多行**（每协议一行）
                _old_rows[(f, _rp)] = r          # ★ 别的协议 ⇒ 保留
    _all_rows = list(_old_rows.values()) + index_rows
    with ip.open("w", encoding="utf-8", newline="") as fh:
        for row in _all_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    # ★ **实体主表**（C3）：``index/entities.jsonl`` —— 中枢的**跨分类唯一索引**
    #   ⇒ 事实/关系/规则/图全部引用同一 ``entity_id`` ⇒ 四套视图可对齐。
    _write_entity_table(hub_root, by_cat, pk)
    return written


def read_classified(hub_root: Path, protocol: str = "") -> list[dict]:
    """读**分类布局**的事实（按全局位置排序 ⇒ 与旧布局顺序一致）。

    Args:
        hub_root: 中枢根。
        protocol: 本次要读的协议（**只给它有全局位置的块**赋位置 ⇒
            其它协议的块位置未知 ⇒ 排在后面（稳定序））。
    """
    hub_root = Path(hub_root)
    files: list[Path] = []
    for cat in category_ids():
        d = hub_root / cat
        if d.is_dir():
            files += sorted(d.glob("*.jsonl"))
    if not files:
        return []
    # ★ index 记：``positions`` = 本协议的全局下标；
    #   ``kept_blocks`` = 前面保留的**其它协议块**的条数（按块序）。
    #   ⇒ 读端按「块序 + 块内位置」还原 ⇒ **每个协议的内部顺序都不变**。
    # ★ index：**每 (文件, 协议) 一行** ⇒ 同文件可有多行（多协议共存）
    order: dict[tuple[str, str], dict[str, Any]] = {}
    by_file: dict[str, list[dict[str, Any]]] = {}
    ip = index_path(hub_root)
    if ip.is_file():
        for ln in ip.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                continue
            f = str(row.get("file") or "")
            if not f:
                continue
            rp = str(row.get("protocol") or "")
            order[(f, rp)] = row
            by_file.setdefault(f, []).append(row)
    items: list[tuple[Optional[int], int, dict]] = []
    seq = 0
    for jf in files:
        rel = str(jf.relative_to(hub_root)).replace("\\", "/")
        # ★ 该文件的**块序** = index 里该文件的行序（写入序）
        #   每块 = {protocol, kept_blocks(前面几块), positions(本块全局下标)}
        rows = by_file.get(rel) or []
        want = str(protocol or "").strip().lower()
        lines = [ln for ln in jf.read_text(encoding="utf-8").splitlines()
                  if ln.strip()]
        _ki = 0
        for row in rows:
            _rp = str(row.get("protocol") or "").strip().lower()
            _ps = [int(x) for x in (row.get("positions") or [])]
            # ★ 本协议的块：按全局下标赋位置；其它协议的块：位置未知
            _mine = (_rp == want)
            _idx = 0
            _cnt = (row.get("count")
                    or (sum(int((b or [0])[0])
                           for b in (row.get("kept_blocks") or [])) or 0))
            for _ in range(int(_cnt or 0)):
                if _ki >= len(lines):
                    break
                try:
                    view = json.loads(lines[_ki])
                except json.JSONDecodeError:
                    _ki += 1
                    continue
                if _mine:
                    pos = _ps[_idx] if _idx < len(_ps) else None
                    _idx += 1
                    items.append((pos, seq, view))
                # ★ 别的协议的块 ⇒ **跳过**（中枢共用一套 ⇒ 必须按协议隔离）
                seq += 1
                _ki += 1
        # ★ 剩余未归属的行（索引缺失）⇒ 只保留本协议的（位置未知，排后）
        for line in lines[_ki:]:
            try:
                view = json.loads(line)
            except json.JSONDecodeError:
                continue
            _kp = str((((view.get("fact_key") or {}).get("protocol"))
                       or "")).strip().lower()
            if want and _kp and _kp != want:
                continue
            items.append((None, seq, view))
            seq += 1
    known = [it for it in items if it[0] is not None]
    unknown = [it for it in items if it[0] is None]
    known.sort(key=lambda it: (it[0], it[1]))
    unknown.sort(key=lambda it: it[1])
    return [it[2] for it in known + unknown]


__all__ = ["ORDER_INDEX_NAME", "index_path", "classify", "collect",
           "write_classified", "read_classified"]
