"""tests/fused/test_build_hub_gate_order.py —— 质量闸顺序 + 幂等快照留存契约。

两个缺陷（2026-11-01 独立 QA 复核证实，QA 实测三协议快照全空）：

**P2-1「先清理、后校验」** ⇒ 质量闸阻断构建 = 把该协议的 rfc facts 删空
    旧顺序：清理 → 抽取 → 映射 → 质量闸 → 写盘
      闸不通过时旧产物已被删、新产物未写入 ⇒ 该协议 rfc facts 变成**空**，
      「质量闸阻断构建」的实际效果是**破坏知识库**而不是「保持原状并拒绝写入」。
    新顺序：抽取 → 映射 → **质量闸** → **清理** → 写盘
      闸不通过 ⇒ 旧产物原封不动 + 仍以 SystemExit（非 0 退出码）阻断。

**P1-4 幂等快照完全失效**
    旧实现：① 快照写入用 `os.replace`（**搬移**语义）⇒ 快照文件被搬到正式
      路径，`snapshots/<build_id>/` 目录**永远是空的**；
      ② `_clean_per_source` 直接 `rmtree` 整个源目录 ⇒ 连快照目录一起删掉。
      ⇒ 文档承诺的「可回滚到历史版本（F5）」根本没有实现。
    新实现：① 快照写入改**复制**语义（`shutil.copy2` + `os.replace` 原子切换
      正式路径）；② 清理时**保留** `facts/snapshots/` 目录。

本文件全部用**合成数据**（不依赖真实 kb/ 语料、不写 derived/ 真实产物），
因此可在不触碰实验语料的前提下稳定回归。
"""
from __future__ import annotations

import hashlib
import importlib
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

build_hub = importlib.import_module("scripts.build_hub")

#: 合成协议名（与真实 kb/ 无关，保证 hermetic）
PROTO = "fakeproto"


# ===========================================================================
# 合成件：Fact / norm / 质量报告
# ===========================================================================

def _make_fact(fact_id: str, name: str, protocol: str = PROTO):
    """造一个最小可用的 v2 Fact（definition aspect，text 类型值）。"""
    from core.fused.models import (
        Claim, ConditionAlways, Fact, FactKey, Subject, Value,
    )
    subject = Subject(type="method", name=name, qualifiers={}, path=[])
    fact_key = FactKey(protocol=protocol, version="1.0", subject=subject,
                       aspect="definition", condition=ConditionAlways())
    claim = Claim(claim_id="c_" + fact_id, fact_id=fact_id,
                  value=Value(type="text", data=f"{name} 的合成定义"),
                  epistemic_type="observed")
    return Fact(fact_id=fact_id, fact_key=fact_key, claims=(claim,),
                resolution=None, alignments=(), metadata=None)


def _fake_norms(protocol: str) -> list[dict]:
    """造 3 条合成 rfc norm（只用于驱动「抽取 → 映射」链路）。"""
    return [
        {
            "norm_id": f"{protocol}.method.{name.lower()}",
            "kind": "method",
            "name": name,
            "content": f"{name} 的合成内容",
            "kb_source_type": "rfc",
            "source": f"file:synthetic.txt#{i}",
            "protocol": protocol,
        }
        for i, name in enumerate(("SETUP", "PLAY", "TEARDOWN"), start=1)
    ]


def _failing_report(protocol: str, facts=None, norms=None):
    """质量闸**必然不通过**的报告（构造一个阻断项即可）。"""
    from core.fused.rfc_extractor import QualityReport
    rep = QualityReport(protocol=protocol,
                        norm_count=len(norms or []),
                        fact_count=len(facts or []))
    rep.blocking_issues.append("测试注入：质量闸强制不通过")
    return rep


def _passing_report(protocol: str, facts=None, norms=None):
    """质量闸**通过**的报告（无阻断项 ⇒ passed=True）。"""
    from core.fused.rfc_extractor import QualityReport
    return QualityReport(protocol=protocol,
                         norm_count=len(norms or []),
                         fact_count=len(facts or []))


# ===========================================================================
# 隔离环境：把 build_hub 的外部依赖全部指向 tmp_path
# ===========================================================================

def _isolate(tmp_path, monkeypatch, *, gate=None, build_ids=None):
    """把 build_hub 用到的所有外部依赖重定向到 tmp_path。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch 夹具。
        gate: 质量闸替身（None ⇒ 用真实闸）。
        build_ids: build_id 替身（list ⇒ 依次返回其中的 id；None ⇒ 真实计算）。

    Returns:
        (per_source_root, facts_dir) —— 隔离后的产物目录。
    """
    from core import paths
    from core.fused import rfc_extractor as rx

    # 1) kb 根：只放一个协议目录，满足 main() 的「协议存在」校验
    kb_root = tmp_path / "kb"
    (kb_root / PROTO).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths, "kb_root", lambda: kb_root)
    monkeypatch.setattr(paths, "norms_path",
                        lambda p: tmp_path / "norms_absent.jsonl")

    # 2) 产物根：derived/per_source/<protocol>/
    ps_root = tmp_path / "per_source"
    monkeypatch.setattr(paths, "per_source_root",
                        lambda p: ps_root / str(p).lower())
    facts_dir = ps_root / PROTO / "rfc" / "facts"

    # 3) 抽取链路替身：合成 norms（不读真实 kb/RFC 原文）
    monkeypatch.setattr(rx, "extract_rfc_norms", _fake_norms)
    monkeypatch.setattr(rx, "_load_rfc_config",
                        lambda protocol: {"method_sections": ["12"]})
    if gate is not None:
        monkeypatch.setattr(rx, "rfc_quality_report", gate)
    if build_ids is not None:
        ids = list(build_ids)
        counter = {"i": 0}

        def _next_build_id(protocol, norms, cfg):
            bid = ids[min(counter["i"], len(ids) - 1)]
            counter["i"] += 1
            return bid

        monkeypatch.setattr(rx, "compute_build_id", _next_build_id)

    # 4) 映射链路替身：合成 Fact（不依赖 core.fused.norm 的具体实现）
    def _fake_map(norm):
        name = norm.get("name", "X")
        return [_make_fact("f_" + name.lower(), name)]

    monkeypatch.setattr(build_hub, "map_norm_to_facts", _fake_map)

    # 5) REPO_ROOT 指向 tmp_path —— main() 用它做 dest.relative_to(REPO_ROOT)
    monkeypatch.setattr(build_hub, "REPO_ROOT", tmp_path)

    return ps_root, facts_dir


def _md5(path: Path) -> str:
    """文件 MD5（32 位小写 hex）。"""
    return hashlib.md5(path.read_bytes()).hexdigest()


# ===========================================================================
# 缺陷 1（P2-1）：质量闸不通过时，旧产物必须原封不动
# ===========================================================================

def test_gate_failure_keeps_previous_facts_untouched(tmp_path, monkeypatch):
    """★★ 核心回归：质量闸阻断构建时，**旧 facts 文件仍在且内容未变**。

    旧实现「先清理、后校验」：闸不通过时旧产物已被 rmtree 掉、新产物未写入
    ⇒ 该协议的 rfc facts 变成**空**（知识库被破坏）。
    """
    ps_root, facts_dir = _isolate(tmp_path, monkeypatch,
                                  gate=_failing_report)

    # 预置「上一次构建」的产物
    facts_dir.mkdir(parents=True, exist_ok=True)
    old_file = facts_dir / "rfc.jsonl"
    old_content = '{"sentinel": "上一次构建的 facts，必须原封不动"}\n'
    old_file.write_text(old_content, encoding="utf-8")
    old_md5 = _md5(old_file)

    # 质量闸不通过 ⇒ 应以 SystemExit 阻断
    with pytest.raises(SystemExit) as excinfo:
        build_hub.main(["--sources", "rfc", "--protocol", PROTO])

    # 退出码非 0（SystemExit 带消息 ⇒ code 为该消息；此处只要求「非 0/非 None」）
    assert excinfo.value.code not in (0, None), \
        f"质量闸不通过时退出码应为非 0，实际 {excinfo.value.code!r}"

    # 旧产物仍在，且内容逐字节未变
    assert old_file.is_file(), "质量闸不通过时旧 facts 文件必须仍然存在"
    assert _md5(old_file) == old_md5, "质量闸不通过时旧 facts 内容不得被改动"
    assert old_file.read_text(encoding="utf-8") == old_content


def test_gate_failure_does_not_touch_other_sources(tmp_path, monkeypatch):
    """质量闸不通过时，**同协议的其他源**也不受任何影响。"""
    ps_root, facts_dir = _isolate(tmp_path, monkeypatch,
                                  gate=_failing_report)

    # 预置：rfc 源（旧产物）+ source 源（另一知识源）
    facts_dir.mkdir(parents=True, exist_ok=True)
    (facts_dir / "rfc.jsonl").write_text("rfc-old\n", encoding="utf-8")
    other = ps_root / PROTO / "source" / "facts"
    other.mkdir(parents=True, exist_ok=True)
    (other / "source.jsonl").write_text("source-old\n", encoding="utf-8")

    with pytest.raises(SystemExit):
        build_hub.main(["--sources", "rfc", "--protocol", PROTO])

    assert (facts_dir / "rfc.jsonl").is_file()
    assert (other / "source.jsonl").read_text(encoding="utf-8") == "source-old\n"


def test_clean_runs_after_quality_gate(tmp_path, monkeypatch):
    """★★ 顺序契约：闸在**清理之前**判定（抽取→映射→闸→清理→写盘）。"""
    order: list[str] = []

    def _gate(protocol, facts=None, norms=None):
        order.append("gate")
        return _failing_report(protocol, facts=facts, norms=norms)

    original_clean = build_hub._clean_per_source

    def _spy_clean(protocol, sources=None):
        order.append("clean")
        return original_clean(protocol, sources=sources)

    _isolate(tmp_path, monkeypatch, gate=_gate)
    monkeypatch.setattr(build_hub, "_clean_per_source", _spy_clean)

    with pytest.raises(SystemExit):
        build_hub.main(["--sources", "rfc", "--protocol", PROTO])

    assert order == ["gate"], \
        f"闸不通过时不得触发清理，实际调用序列 {order}"


def test_gate_failure_exit_code_is_nonzero_at_process_level(tmp_path):
    """进程级验证：质量闸不通过 ⇒ **退出码非 0**（CLI 契约）。

    ⚠ 闸在**写盘之前**就抛 SystemExit，故本子进程**不会**写任何产物
      （清理也在闸之后），对 derived/ 无副作用。
    """
    runner = tmp_path / "runner.py"
    runner.write_text(textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(REPO_ROOT)!r})
        from core.fused import rfc_extractor as rx

        def _failing(protocol, facts=None, norms=None):
            rep = rx.QualityReport(protocol=protocol)
            rep.blocking_issues.append("injected-failure")
            return rep

        rx.rfc_quality_report = _failing
        rx.extract_rfc_norms = lambda protocol: []
        from scripts import build_hub
        build_hub.main(["--sources", "rfc", "--protocol", "rtsp"])
    """), encoding="utf-8")

    proc = subprocess.run([sys.executable, str(runner)],
                          cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert proc.returncode != 0, \
        f"质量闸不通过时进程退出码应为非 0，实际 {proc.returncode}"
    assert "质量闸" in (proc.stdout + proc.stderr)


# ===========================================================================
# 缺陷 2（P1-4）：幂等快照必须留存且非空
# ===========================================================================

def test_snapshot_file_is_written_and_not_empty(tmp_path, monkeypatch):
    """一次构建后，`snapshots/<build_id>/rfc.jsonl` 必须**存在且非空**。

    旧实现用 `os.replace(snap_file, dest)`（**搬移**语义）⇒ 快照文件被搬到
    正式路径，`snapshots/<build_id>/` 目录永远是空的。
    """
    _, facts_dir = _isolate(tmp_path, monkeypatch,
                            gate=_passing_report,
                            build_ids=["rb_snapshot000000001"])

    rc = build_hub.main(["--sources", "rfc", "--protocol", PROTO])
    assert rc == 0

    snap_file = facts_dir / "snapshots" / "rb_snapshot000000001" / "rfc.jsonl"
    assert snap_file.is_file(), "快照文件应存在"
    assert snap_file.stat().st_size > 0, "快照文件不应为空"
    # 快照内容 == 正式产物内容
    assert snap_file.read_text(encoding="utf-8") == \
        (facts_dir / "rfc.jsonl").read_text(encoding="utf-8")


def test_two_builds_keep_two_complete_snapshots(tmp_path, monkeypatch):
    """★★ 核心回归：连续两次构建（不同 build_id）⇒ 留存**两份**非空快照。

    旧实现两个缺陷叠加 ⇒ 快照目录恒空、历史快照无法留存，回滚（F5）失效。
    """
    _, facts_dir = _isolate(tmp_path, monkeypatch,
                            gate=_passing_report,
                            build_ids=["rb_build0000000001",
                                       "rb_build0000000002"])

    assert build_hub.main(["--sources", "rfc", "--protocol", PROTO]) == 0
    first = facts_dir / "snapshots" / "rb_build0000000001" / "rfc.jsonl"
    assert first.is_file() and first.stat().st_size > 0, "第一份快照应非空"

    assert build_hub.main(["--sources", "rfc", "--protocol", PROTO]) == 0
    second = facts_dir / "snapshots" / "rb_build0000000002" / "rfc.jsonl"
    assert second.is_file() and second.stat().st_size > 0, "第二份快照应非空"

    # 两份快照都在，且内容与当时的 facts 一致（此处两次同输入 ⇒ 内容相同）
    snaps = sorted((facts_dir / "snapshots").glob("*/rfc.jsonl"))
    assert len(snaps) == 2, f"应留存两份快照，实际 {len(snaps)}: {snaps}"
    assert _md5(snaps[0]) == _md5(snaps[1])
    assert _md5(snaps[0]) == _md5(facts_dir / "rfc.jsonl")


def test_snapshot_content_matches_facts_of_that_build(tmp_path, monkeypatch):
    """快照内容 == 该次构建落盘的 facts 内容（可回滚的前提）。"""
    _, facts_dir = _isolate(tmp_path, monkeypatch,
                            gate=_passing_report,
                            build_ids=["rb_content00000001"])

    build_hub.main(["--sources", "rfc", "--protocol", PROTO])

    snap = facts_dir / "snapshots" / "rb_content00000001" / "rfc.jsonl"
    live = facts_dir / "rfc.jsonl"
    assert _md5(snap) == _md5(live)
    # 快照里的 fact 数量与落盘一致（3 条合成 fact）
    lines = [ln for ln in snap.read_text(encoding="utf-8").splitlines() if ln]
    assert len(lines) == 3, f"快照应含 3 条 fact，实际 {len(lines)}"


def test_clean_preserves_snapshot_dir(tmp_path, monkeypatch):
    """★★ `_clean_per_source` 清理时必须**保留** `facts/snapshots/`。"""
    ps_root, facts_dir = _isolate(tmp_path, monkeypatch)

    # 造一个「有快照 + 有其它产物」的源目录
    facts_dir.mkdir(parents=True, exist_ok=True)
    (facts_dir / "rfc.jsonl").write_text("old\n", encoding="utf-8")
    (facts_dir / "current_build_id.txt").write_text("rb_x\n", encoding="utf-8")
    snap = facts_dir / "snapshots" / "rb_keepme00000001"
    snap.mkdir(parents=True)
    (snap / "rfc.jsonl").write_text("snapshot-payload\n", encoding="utf-8")
    # 源目录下其它内容也应被清掉
    extra = ps_root / PROTO / "rfc" / "other"
    extra.mkdir(parents=True)
    (extra / "x.txt").write_text("x\n", encoding="utf-8")

    build_hub._clean_per_source(PROTO, sources=["rfc"])

    # 快照保留
    assert snap.is_dir(), "清理后 snapshots/ 目录必须保留"
    assert (snap / "rfc.jsonl").read_text(encoding="utf-8") == "snapshot-payload\n"
    # 其它产物清空
    assert not (facts_dir / "rfc.jsonl").exists()
    assert not (facts_dir / "current_build_id.txt").exists()
    assert not extra.exists()


def test_clean_without_snapshot_removes_whole_source_dir(tmp_path, monkeypatch):
    """无快照时清理行为不变：整个源目录被删除（向后兼容既有契约）。"""
    ps_root, facts_dir = _isolate(tmp_path, monkeypatch)

    facts_dir.mkdir(parents=True, exist_ok=True)
    (facts_dir / "rfc.jsonl").write_text("old\n", encoding="utf-8")

    build_hub._clean_per_source(PROTO, sources=["rfc"])

    assert not (ps_root / PROTO / "rfc").exists()


def test_current_build_id_is_recorded(tmp_path, monkeypatch):
    """current_build_id.txt 记录本次 build_id（回溯入口）。"""
    _, facts_dir = _isolate(tmp_path, monkeypatch,
                            gate=_passing_report,
                            build_ids=["rb_recorded0000001"])

    build_hub.main(["--sources", "rfc", "--protocol", PROTO])

    marker = facts_dir / "current_build_id.txt"
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8").strip() == "rb_recorded0000001"


def test_non_rfc_source_does_not_inherit_rfc_build_id(tmp_path, monkeypatch):
    """幂等键不得跨源串味：source 源不应复用上一次 rfc 的 build_id。"""
    from core import paths
    _, facts_dir = _isolate(tmp_path, monkeypatch,
                            gate=_passing_report,
                            build_ids=["rb_rfcbuild0000001"])

    build_hub.main(["--sources", "rfc", "--protocol", PROTO])
    assert (facts_dir / "snapshots" / "rb_rfcbuild0000001").is_dir()

    # 换成 source 源（无 build_id ⇒ 直接写，不产生快照目录）
    src_dir = paths.per_source_facts_dir(PROTO, "source")
    rc = build_hub.main(["--sources", "source", "--protocol", PROTO])
    assert rc == 0
    assert not (src_dir / "snapshots").exists(), \
        "非 rfc 源不应继承 rfc 的 build_id 而产生快照"
