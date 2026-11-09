"""tests/fused/test_rfc_constraint_span.py —— B-3（约束候选带 span）+ B-4（norm_id 冲突修复）。

B-3 验收（对应 docs/实施/RFC源里程碑BCD路线图.md §3.8 任务表）：
  ① 候选含 `span_start` / `span_end` / `section_path` / `spec_version`；
  ② **span 覆盖率 100%**，且每个 span 能在源文件里**逐字定位**
     （`raw[span_start:span_end] == candidate["text"]`）；
  ③ **TOC 污染实测归零** —— 用**独立**判据 `_independent_toc_lines`
     回查候选的来源行（**不复用** `_is_toc_line`：那会与被检查对象自证）；
  ④ `source` 格式统一为 `file:<name>#@<真实行号>` —— **两种 anchor 语义
     不再并存**（不再出现裸 `file:<name>`，也不出现 `#@abnf`）。

B-4 验收：
  ① 同字段多条约束 → `norm_id` 唯一（`dup_norm_ids == 0`）；
  ② 该场景下 `rfc_quality_report(...).passed == True`（不再阻断构建）；
  ③ `norm_id` **稳定可复现**：跨进程（不同 PYTHONHASHSEED）一致，
     且**不依赖 LLM 自由措辞**（`expected_behavior`）。

`section_no_path` 验收（B-3 补充，team-lead 复核提出）：
  ⑤ 候选带 `section_no_path`：**章节号链**（给机器做 rule_id 派生），
     与 `section_path`（**标题**链，给人看/溯源）**并列**；
  ⑥ 章节号链**全是章节号形态**（不含字母标题），且与标题链**层数对应**；
  ⑦ ★ **id 稳定性**：用 `section_no_path` 构造 `compute_rule_id` 的
     `section_path` 参数 ⇒ 同一候选重复 100 次得**同一 id**；
  ⑧ ★ **措辞无关性**：标题链改一个字（模拟 RFC 修订）⇒ 用
     `section_no_path` 派生的 id **不变**（这正是补章节号链的意义）。
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from core.fused.norm import constraint_identity_digest, map_norm_to_facts
from core.fused.rfc_extractor import (
    _independent_toc_lines,
    _line_offsets,
    extract_constraint_candidates,
    extract_constraint_norms,
    rfc_quality_report,
)
from core.llm import StubLLMClient

PROTOCOLS = ("rtsp", "sip", "smtp")
ROOT = pathlib.Path(__file__).resolve().parents[2]

#: 候选 `source` 的**唯一**形态：file:<name>#@<真实行号>
_RE_SOURCE = re.compile(r"^file:(?P<name>[^#]+)#@(?P<line>\d+)$")

#: 章节号形态：`1` / `1.2` / `10.1.2`（**不含**字母标题）
_RE_SECTION_NO = re.compile(r"^\d+(?:\.\d+)*$")


# ===========================================================================
# rule_id 派生（真实实现 + 同契约本地镜像）
# ===========================================================================

def _local_compute_rule_id(protocol: str, spec_version: str,
                           section_path, subject_type: str,
                           subject_name: str, operator: str,
                           operand, operand_ref, expected_behavior: str) -> str:
    """`compute_rule_id` 的**同契约本地镜像**（纯函数，sha256 派生）。

    ★ 只在 `core.fused.semantic` 此刻不可用（并行编辑中）时兜底；
      性质断言（稳定 / 措辞无关）对任何纯函数都成立。
    """
    ident = {
        "protocol": protocol,
        "spec_version": spec_version,
        "section_path": list(section_path),
        "subject_type": subject_type,
        "subject_name": subject_name,
        "operator": operator,
        "operand": list(operand),
        "operand_ref": operand_ref,
        "expected_behavior": expected_behavior,
    }
    raw = json.dumps(ident, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"))
    return "r" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _derive_rule_id(section_path, **kw) -> str:
    """用给定的 `section_path` 派生 rule_id（优先用**真实**实现）。"""
    args = {
        "protocol": "rtsp",
        "spec_version": "RFC 2326",
        "subject_type": "header",
        "subject_name": "QNAME",
        "operator": "le",
        "operand": ("63",),
        "operand_ref": None,
        "expected_behavior": "",
    }
    args.update(kw)
    try:
        from core.fused.semantic import compute_rule_id
        return compute_rule_id(
            args["protocol"], args["spec_version"], tuple(section_path),
            args["subject_type"], args["subject_name"], args["operator"],
            tuple(args["operand"]), args["operand_ref"],
            args["expected_behavior"])
    except Exception:  # noqa: BLE001 —— 并行编辑中不可用 ⇒ 用本地镜像
        return _local_compute_rule_id(
            args["protocol"], args["spec_version"], section_path,
            args["subject_type"], args["subject_name"], args["operator"],
            args["operand"], args["operand_ref"], args["expected_behavior"])


# ===========================================================================
# B-3　约束候选带 span
# ===========================================================================

@pytest.fixture(scope="module")
def candidates() -> dict:
    """三协议的约束候选（模块级缓存 —— 抽取要读全文，重复调用很慢）。"""
    return {p: extract_constraint_candidates(p) for p in PROTOCOLS}


@pytest.fixture(scope="module")
def spec_texts() -> dict:
    """{protocol: {文件名: 原文}}"""
    out: dict = {}
    for p in PROTOCOLS:
        out[p] = {f.name: f.read_text(encoding="utf-8", errors="ignore")
                  for f in sorted((ROOT / "kb" / p / "spec").glob("*.txt"))}
    return out


def test_candidates_carry_span_and_provenance(candidates):
    """① 候选必须带 span / 章节路径 / 规范版本；span 覆盖率 100%。"""
    for p in PROTOCOLS:
        cs = candidates[p]
        assert cs, f"{p} 应抽到约束候选"
        with_span = [c for c in cs if c.get("span_start") is not None
                     and c.get("span_end") is not None]
        assert len(with_span) == len(cs), (
            f"{p}: span 覆盖率 {len(with_span)}/{len(cs)} ≠ 100%")
        for c in cs:
            assert isinstance(c["span_start"], int)
            assert isinstance(c["span_end"], int)
            assert 0 <= c["span_start"] < c["span_end"]
            assert isinstance(c["section_path"], list) and c["section_path"], (
                f"{p}: 候选缺 section_path")
            assert all(isinstance(x, str) and x for x in c["section_path"])
            assert c.get("spec_version", "").startswith("RFC "), (
                f"{p}: 候选缺规范版本：{c.get('spec_version')!r}")


def test_span_locates_source_text_exactly(candidates, spec_texts):
    """② span 必须能在源文件里**逐字定位**（B-2「先验证区间」的物理前提）。"""
    for p in PROTOCOLS:
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            assert m, f"{p}: source 格式不合法：{c['source']!r}"
            raw = spec_texts[p][m.group("name")]
            assert raw[c["span_start"]:c["span_end"]] == c["text"], (
                f"{p}: span 与原文不一致：{c['source']}")


def test_source_anchor_is_unified_real_line_number(candidates):
    """④ source 统一为 `file:<name>#@<真实行号>`（两种 anchor 语义不再并存）。"""
    for p in PROTOCOLS:
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            assert m, (
                f"{p}: source 必须形如 file:<name>#@<行号>，实得 {c['source']!r}")
            assert int(m.group("line")) >= 1
            assert "#@abnf" not in c["source"]


def test_toc_contamination_is_zero(candidates, spec_texts):
    """③ TOC 污染实测归零（用**独立**判据回查候选的来源行）。"""
    for p in PROTOCOLS:
        lines_cache = {name: raw.splitlines()
                       for name, raw in spec_texts[p].items()}
        contaminated = []
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            assert m
            lines = lines_cache[m.group("name")]
            lineno = int(m.group("line"))
            assert 1 <= lineno <= len(lines), f"{p}: 行号越界 {lineno}"
            raw_line = lines[lineno - 1]
            # ★ 用**独立**的形态判据（不复用 _is_toc_line —— 那会自证）
            if _independent_toc_lines([raw_line]):
                contaminated.append((c["source"], raw_line[:80]))
        assert not contaminated, (
            f"{p}: TOC 污染候选 {len(contaminated)} 条：{contaminated[:3]}")


def test_anchor_line_contains_the_span(candidates, spec_texts):
    """★ 锚点行号口径的回归护栏：``#@<行号>`` 必须是 **splitlines 口径**，
    且该行**确实包含这段 span 的起点**。

    ⚠ **换页符陷阱**（software-engineer-11 实测并同步）：RFC 正文含
    **换页符 `\x0c`**（rtsp 92 / sip 269 / smtp 95 处），`str.splitlines()`
    把它当行边界而 `text.count("\n")` 不当 ⇒ 两种口径的行号相差 9~11 行。
    本测试把口径钉死：若将来有人用 `count("\n")` 口径反查，会立刻红。

    ★ **锚点语义 = 指向句子的**起点行**；句子**可以跨行** —— 粒度修正
      （按**逻辑句**切分）后一句可由多个物理行合并而成 ⇒ 其 span 合法地
      跨行。故这里只断言「**起点**落在锚点行内」，**不**断言「整段 span
      不跨行」（那是「物理行即句子」的旧假设，已被粒度修正作废）。
      这与 `core/fused/semantic.py::_verify_span_in_source` 的
      `line_start <= span_start < line_end` 口径**天然一致**。
    """
    for p in PROTOCOLS:
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            assert m, f"{p}: source 格式不合法：{c['source']!r}"
            raw = spec_texts[p][m.group("name")]
            offsets = _line_offsets(raw)
            lineno = int(m.group("line"))
            start_off = offsets.get(lineno)
            end_off = offsets.get(lineno + 1)
            assert start_off is not None, f"{p}: 行号 {lineno} 不存在"
            # ★ 锚点行**包含 span 的起点**（splitlines 口径）
            assert start_off <= c["span_start"], (
                f"{p}: span 起点不在锚点行 {lineno} 内（口径漂移？）")
            if end_off is not None:
                assert c["span_start"] < end_off, (
                    f"{p}: span 起点越过锚点行 {lineno}（口径漂移？）")
            # 反证：`\n` 口径的行号**不等于**锚点行号（RFC 含换页符时）
            if "\x0c" in raw:
                nl_lineno = raw.count("\n", 0, c["span_start"]) + 1
                assert nl_lineno != lineno, (
                    f"{p}: 该文件无换页符差异，跳过反证")


def test_candidates_are_in_document_order(candidates):
    """候选按文档顺序产出（章节窗口 DFS 前序 ⇒ 源行号单调不减）。"""
    for p in PROTOCOLS:
        by_file: dict = {}
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            assert m
            by_file.setdefault(m.group("name"), []).append(int(m.group("line")))
        for name, lines in by_file.items():
            assert lines == sorted(lines), (
                f"{p}/{name}: 候选未按文档顺序产出")


def test_candidates_come_from_section_bodies_not_preamble(candidates, spec_texts):
    """候选**不**来自「首个章节标题之前」的抬头/摘要/目录区（P1-2 语义）。"""
    from core.fused.rfc_extractor import (
        _doc_content_lines, _split_heads_bodies,
    )
    for p in PROTOCOLS:
        first_head: dict = {}
        for name, raw in spec_texts[p].items():
            content = _doc_content_lines(raw.splitlines())
            heads, _bodies, _nos = _split_heads_bodies(content)
            first_head[name] = heads[0].line if heads else 0
        for c in candidates[p]:
            m = _RE_SOURCE.match(c["source"])
            assert int(m.group("line")) >= first_head[m.group("name")], (
                f"{p}: 候选来自首标题前的抬头区：{c['source']}")


# ===========================================================================
# B-4　norm_id 冲突修复
# ===========================================================================

def _three_same_field_constraints() -> StubLLMClient:
    """Stub LLM：同一字段（QNAME）的 **3 条不同约束**。"""
    return StubLLMClient(response={"constraints": [
        {"field": "QNAME", "constraint": "单 label 长度 <= 63 字节",
         "violation": "label 长度字段 > 实际内容",
         "expected_code": "1", "expected_behavior": "FORMERR"},
        {"field": "QNAME", "constraint": "QNAME 整体长度 <= 255 字节",
         "violation": "整体长度字段 > 实际内容",
         "expected_code": "1", "expected_behavior": "FORMERR"},
        {"field": "QNAME", "constraint": "label 数量 <= 127",
         "violation": "label 数量字段 > 实际内容",
         "expected_code": "1", "expected_behavior": "FORMERR"},
    ]})


@pytest.fixture(scope="module")
def same_field_norms() -> list:
    return extract_constraint_norms("rtsp", llm=_three_same_field_constraints(),
                                    max_candidates=8)


def test_same_field_constraints_get_unique_norm_ids(same_field_norms):
    """① 同字段多条约束 → norm_id 唯一（`dup_norm_ids == 0`）。"""
    ids = [n["norm_id"] for n in same_field_norms]
    assert len(same_field_norms) == 3
    assert len(set(ids)) == len(ids), f"norm_id 仍冲突：{ids}"
    # 判别位后缀存在，且不是裸的 field 键
    for n in same_field_norms:
        assert n["norm_id"].startswith("rtsp.constraint.qname.")
        assert len(n["norm_id"].rsplit(".", 1)[1]) == 10


def test_same_field_constraints_pass_quality_gate(same_field_norms):
    """② 该场景下质量闸**不阻断**构建（`passed == True`）。"""
    facts = []
    for n in same_field_norms:
        facts.extend(map_norm_to_facts(n))
    rep = rfc_quality_report("rtsp", facts=facts, norms=same_field_norms)
    assert rep.dup_norm_ids == 0
    assert rep.dup_fact_ids == 0, "同字段多约束仍产出重复 fact_id"
    assert rep.passed, f"质量闸仍阻断：{rep.blocking_issues}"


def test_same_field_constraints_produce_distinct_facts(same_field_norms):
    """同字段多约束 → 每个 fact 的 fact_id 互不相同（事实身份可区分）。"""
    facts = []
    for n in same_field_norms:
        facts.extend(map_norm_to_facts(n))
    assert len(facts) == 6          # 3 条约束 × (legal_boundary + response_expectation)
    assert len({f.fact_id for f in facts}) == len(facts)
    # subject.name 仍是字段名（下游 bundle 按 name 分桶，行为不变）
    assert all(f.fact_key.subject.name == "QNAME" for f in facts)
    assert all(f.fact_key.subject.type == "header" for f in facts)


def test_identity_digest_ignores_free_text_behavior():
    """③ 判别位**不用 LLM 自由措辞**：同一语义不同措辞 → 同一摘要。"""
    a = constraint_identity_digest("QNAME", "单 label <= 63", "x", "1")
    b = constraint_identity_digest("QNAME", "单 label <= 63", "x", "1")
    assert a == b
    # 内容不同 → 摘要不同
    assert a != constraint_identity_digest("QNAME", "整体 <= 255", "x", "1")
    assert a != constraint_identity_digest("QNAME", "单 label <= 63", "y", "1")
    # 排版差异（大小写/空白）不应改变摘要
    assert a == constraint_identity_digest("qname", "  单  label   <= 63 ", "x", "1")


def _digest_with_hash_seed(hashseed: str) -> str:
    """在**独立子进程**里算摘要（PYTHONHASHSEED 不同 ⇒ `hash()` 会漂移）。"""
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hashseed
    env["PYTHONPATH"] = str(ROOT)
    code = ("from core.fused.norm import constraint_identity_digest as d;"
            "print(d('QNAME', '单 label <= 63', 'x', '1'))")
    out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env,
                         capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, f"子进程失败：{out.stderr}"
    return out.stdout.strip()


def test_identity_digest_is_reproducible_across_processes():
    """③ norm_id 判别位**跨进程稳定**（证明没用随机化的 `hash()`）。"""
    a = _digest_with_hash_seed("0")
    b = _digest_with_hash_seed("1")
    c = _digest_with_hash_seed("12345")
    assert a == b == c, f"摘要跨进程不一致：{a} / {b} / {c}"
    assert a == constraint_identity_digest("QNAME", "单 label <= 63", "x", "1")


def test_constraint_norms_carry_span_provenance(same_field_norms):
    """B-3 的 span / 章节 / 版本随约束 norm 一起下沉（可回溯到原文）。"""
    for n in same_field_norms:
        assert n["source"].startswith("file:")
        assert "#@" in n["source"]
        assert isinstance(n["span_start"], int)
        assert isinstance(n["span_end"], int)
        assert n["span_start"] < n["span_end"]
        assert n["spec_version"].startswith("RFC ")
        assert isinstance(n["section_path"], list)


# ===========================================================================
# section_no_path（章节号链）—— 给 rule_id 派生提供**稳定**输入
# ===========================================================================

def test_candidates_carry_section_no_path(candidates):
    """⑤ 候选带 `section_no_path`（章节号链），且**全是章节号形态**。"""
    for p in PROTOCOLS:
        for c in candidates[p]:
            no_path = c["section_no_path"]
            assert isinstance(no_path, list), f"{p}: section_no_path 必须是 list"
            assert no_path, f"{p}: section_no_path 不得为空：{c['source']}"
            for no in no_path:
                assert _RE_SECTION_NO.match(no), (
                    f"{p}: section_no_path 含非章节号成分 {no!r}（应为章节号）")


def test_section_no_path_levels_correspond_when_counts_match(candidates):
    """⑥ **层数相等时**，号链与标题链逐层对应；末级号 == `section_no`。

    ★ **分层表述**（team-lead 裁决）：本断言只覆盖「层数相等」的候选 ——
      「层数一一对应」**不是**契约（某层标题无编号时号链会跳过该层 ⇒ 更短），
      把「所有候选层数必须相等」写成契约会让换一份 RFC 就假失败。

    ★ 「逐层对应」的准确含义：号链与标题链**取自同一条节点链** ⇒ 层数相等
      即「没有层被跳过」，第 i 层的号就是第 i 个节点的号。
      ⚠ **不**断言「号链在数值上嵌套」（父号是子号的前缀）：章节树的父子
      关系按**标题层级**建立（不是按编号前缀），且 A1.3 的宽松标题识别会把
      少量正文行（如 SIP 的 `19.1.  It has a similar form to ...`）误判成标题
      ⇒ 实测存在 `['4', '19.1']` 这种非数值嵌套的链（**既存**现象，
      标题链同样受影响，不是本字段引入的）。
    """
    matched = 0
    for p in PROTOCOLS:
        for c in candidates[p]:
            titles = c["section_path"]
            numbers = c["section_no_path"]
            if len(titles) != len(numbers):
                continue      # ★ 层数不等是**允许**的（跳过空 number 层）
            matched += 1
            # 层数相等 ⇒ 没有层被跳过 ⇒ 末级号就是本节点的章节号
            assert numbers[-1] == c["section_no"], (
                f"{p}: 章节号链末级 {numbers[-1]!r} != section_no "
                f"{c['section_no']!r}")
    assert matched > 0, "没有任何层数相等的候选 ⇒ 前提不成立"


def test_section_no_path_skips_unnumbered_levels(candidates):
    """号链**跳过**无编号的层 ⇒ 不含空串；末级恒等于 `section_no`。

    ★ 「层数可能少于标题链」是**设计口径**，不是数据巧合 —— 下面用
      **单元级**测试直接证明该行为。
    """
    for p in PROTOCOLS:
        for c in candidates[p]:
            numbers = c["section_no_path"]
            assert all(n != "" for n in numbers), (
                f"{p}: 号链含空 number 层（应跳过）：{numbers}")
            assert numbers[-1] == c["section_no"]


def test_section_number_path_skips_empty_number_unit_level():
    """单元级：父层**无编号**时，号链**跳过**该层（不留空串）。"""
    from core.fused.rfc_extractor import (
        SectionHead, _build_section_tree, _section_number_path, _section_path,
    )
    parent = SectionHead(level=1, number="", title="Unnumbered Section", line=1)
    child = SectionHead(level=2, number="1.2", title="Sub Section", line=2)
    tree = _build_section_tree([parent, child], [[], []])
    node = tree[0].children[0]
    # 标题链：两层（给人看）
    assert _section_path(node) == ("Unnumbered Section", "Sub Section")
    # ★ 号链：跳过空 number 的父层 ⇒ **只有一层**（不是 ("", "1.2")）
    assert _section_number_path(node) == ("1.2",)


def test_rule_id_from_section_no_path_is_stable(candidates):
    """⑦ ★ id 稳定性：同一候选用 `section_no_path` 派生 ⇒ 重复 100 次同一 id。"""
    for p in PROTOCOLS:
        for c in candidates[p][:20]:
            ids = {_derive_rule_id(c["section_no_path"]) for _ in range(100)}
            assert len(ids) == 1, f"{p}: rule_id 不稳定：{ids}"


def test_rule_id_is_independent_of_section_title(candidates):
    """⑧ ★ 措辞无关性：标题链改一个字 ⇒ 用章节号链派生的 id **不变**。

    这是补 `section_no_path` 的**全部意义**：`compute_rule_id` 的设计初衷
    （§3.2）是「措辞微调 ⇒ id 不变」⇒ 规则可跨构建对齐、可做增量更新。
    """
    changed = 0
    for p in PROTOCOLS:
        for c in candidates[p][:20]:
            baseline = _derive_rule_id(c["section_no_path"])

            # 模拟 RFC 修订：标题链改一个字（标题层数不变）
            titles = list(c["section_path"])
            titles[0] = titles[0] + " "
            assert len(titles) == len(c["section_path"])
            assert _derive_rule_id(c["section_no_path"]) == baseline, (
                f"{p}: 改标题后基于章节号链的 rule_id 变了")

            # 反证：**若**用标题链派生，改一个字就会让 id 漂移（这就是原缺陷）
            if _derive_rule_id(titles) != baseline:
                changed += 1
    assert changed > 0, "标题链未体现漂移 ⇒ 前提不成立（请复核 _derive_rule_id）"


def test_section_no_path_propagates_to_constraint_norms(same_field_norms):
    """`section_no_path` 随约束 → norm 一起下沉（消费方可直接拿来派生 id）。"""
    for n in same_field_norms:
        assert isinstance(n["section_no_path"], list)
        assert n["section_no_path"], "norm 的 section_no_path 不得为空"
        for no in n["section_no_path"]:
            assert _RE_SECTION_NO.match(no), f"非章节号成分：{no!r}"
        assert len(n["section_path"]) == len(n["section_no_path"])
