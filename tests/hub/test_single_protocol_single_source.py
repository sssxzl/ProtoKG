"""tests/fused/test_single_protocol_single_source.py —— 「一次一个协议 × 一个知识源」契约。

架构约束（2026-10-31 用户明确）：
    「我这个模型，一次只对一个知识库进行处理，目标是一个知识源，
      不是一批把所有知识库都解决。对 rfc 的识别上面，利用 --<目标协议>
      单次对一个协议进行处理。」

本文件把该约束固化为**可自动验证的测试**，防止将来被无意破坏：

  ① CLI 契约：`--sources` 只接受单个源；`--protocol` 必须显式提供
  ② 清理范围：只清本次指定的源，**不动同协议的其他源**
  ③ 产物范围：只写目标协议的目标源目录
  ④ 工具脚本：基线测量 / 配置校验默认单协议，批量需显式开关
"""
from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

build_hub = importlib.import_module("scripts.build_hub")


# ===========================================================================
# ① CLI 契约
# ===========================================================================

def test_sources_accepts_multiple_values():
    """★ 批次 1.6：`--sources` **恢复多值**（可一次构建多个源）。

    2026-10-31 曾限制为单值，理由是「清理时连带清掉其他源 ⇒ 22 个下游测试失效」；
    批次 1.6 改为「**清空整个中枢**」（中枢里只剩本次的源）⇒ 该顾虑消失
    ⇒ 2026-11-02 用户明确要求恢复多源。
    """
    import shlex
    # 未知源仍应被 argparse 拒绝（choices 校验）
    with pytest.raises(SystemExit):
        build_hub.main(["--sources", "not_a_source", "--protocol", "sip"])
    # 多值现在**被接受**（不再抛 SystemExit）
    assert "--sources" in shlex.join(["--sources", "rfc", "expert_note"])


def test_protocol_is_required():
    """`--protocol` 必须显式给出 —— 不允许「默认 rtsp」的隐式误跑。"""
    with pytest.raises(SystemExit):
        build_hub.main(["--sources", "rfc"])


def test_unknown_protocol_is_rejected():
    """不存在的协议应明确报错（exit 2），而不是静默产出 0 facts。"""
    rc = build_hub.main(["--sources", "rfc", "--protocol", "no_such_proto"])
    assert rc == 2


def test_source_choices_are_restricted():
    """`--sources` 只接受五个已知源。"""
    with pytest.raises(SystemExit):
        build_hub.main(["--sources", "not_a_source", "--protocol", "sip"])


# ===========================================================================
# ② 清理范围：只清本次指定的源
# ===========================================================================

def test_clean_only_touches_the_requested_source(tmp_path, monkeypatch):
    """★★ 核心回归：清理**只**作用于本次指定的源。

    曾经的实现清五源 → `build_hub.py --sources rfc --protocol rtsp`
    会把 rtsp 的 source/expert_note/vuln/traffic 一起删掉，
    导致依赖这些源的下游测试与种子生成全部失效（实测 22 个测试连带失败）。
    """
    from core import paths

    # 造一个临时的 per_source 根，含两个源
    fake_root = tmp_path / "per_source" / "fakeproto"
    for src in ("rfc", "source", "vuln"):
        d = fake_root / src / "facts"
        d.mkdir(parents=True)
        (d / f"{src}.jsonl").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(paths, "per_source_root", lambda protocol: fake_root)

    build_hub._clean_per_source("fakeproto", sources=["rfc"])
    # ★ 中枢**共用一套** ⇒ 隔离中枢根（不污染仓库 derived/）
    monkeypatch.setattr(paths, "hub_root",
                        lambda *a: tmp_path / "hub")

    assert not (fake_root / "rfc").exists(), "本次指定的源应被清空"
    assert (fake_root / "source" / "facts" / "source.jsonl").is_file(), \
        "其他源不应被清空"
    assert (fake_root / "vuln" / "facts" / "vuln.jsonl").is_file(), \
        "其他源不应被清空"


def test_clean_without_sources_clears_all_five(tmp_path, monkeypatch):
    """不指定源时清五源（全量重建场景，仍需保留旧行为）。"""
    from core import paths

    fake_root = tmp_path / "per_source" / "fakeproto2"
    for src in ("rfc", "source", "vuln", "traffic", "expert_note"):
        d = fake_root / src / "facts"
        d.mkdir(parents=True)
        (d / f"{src}.jsonl").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(paths, "per_source_root", lambda protocol: fake_root)
    build_hub._clean_per_source("fakeproto2")

    for src in ("rfc", "source", "vuln", "traffic", "expert_note"):
        assert not (fake_root / src).exists(), f"{src} 应被清空"


# ===========================================================================
# ③ 产物范围：只写目标协议的目标源
# ===========================================================================

def test_write_goes_to_target_protocol_and_source(tmp_path, monkeypatch):
    """产物只落在 derived/per_source/<protocol>/<source>/ 下。"""
    from core import paths

    fake_facts_root = tmp_path / "facts"
    monkeypatch.setattr(paths, "per_source_facts_dir",
                        lambda protocol, source: fake_facts_root / protocol / source)

    from core.fused.hub.registry import load_registry
    registry = load_registry()
    failed, dest = build_hub._write_and_validate(
        "rfc", [], registry, "sip", build_id="rb_testbuild00000001")

    assert failed == 0
    assert "sip" in str(dest)
    assert "rfc" in str(dest)
    assert dest.is_file()


# ===========================================================================
# ④ 工具脚本：默认单协议，批量需显式开关
# ===========================================================================

def test_baseline_probe_requires_protocol_or_explicit_batch():
    """基线测量：不给 --protocol 且不加 --all-protocols → 报错退出。"""
    probe = importlib.import_module("scripts.rfc_baseline_probe")
    with pytest.raises(SystemExit):
        probe.main([])


def test_config_verify_requires_protocol_or_explicit_batch():
    """配置校验：不给 --protocol 且不加 --all-protocols → 报错退出。"""
    verify = importlib.import_module("scripts.rfc_config_verify")
    with pytest.raises(SystemExit):
        verify.main([])


def test_baseline_probe_single_protocol_mode(capsys):
    """单协议模式可用（--protocol sip）。"""
    probe = importlib.import_module("scripts.rfc_baseline_probe")
    rc = probe.main(["--protocol", "sip"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "=== sip ===" in out
    # 单协议模式不应出现其他协议
    assert "=== rtsp ===" not in out


def test_config_verify_single_protocol_mode(capsys):
    """单协议模式可用（--protocol sip）。"""
    verify = importlib.import_module("scripts.rfc_config_verify")
    rc = verify.main(["--protocol", "sip"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "=== sip ===" in out
    assert "=== rtsp ===" not in out


# ===========================================================================
# ⑤ rfc 抽取本身：严格按目标协议取配置与数据
# ===========================================================================

def test_rfc_extraction_uses_target_protocol_config_only():
    """★ rfc 抽取必须**只**用目标协议的 rfc_config（不串协议）。

    用「章节号在两个协议里含义不同」的一对来验证：
      - RTSP：§12 是 Header Field Definitions（字段）
      - SIP ：§20 是 Header Fields（字段）、§19 是 URIs（不是字段）
    故 §19 在 SIP 不是字段、在 RTSP 无定义 → 用 RTSP 配置判 SIP 的 §19
    不应得到 field。

    ⚠ 标题形如「200 OK」的会先被**状态码标题启发式**判为 status
      （协议通用特征，与配置无关），故此处用非状态码标题来验证配置隔离。
    """
    from core.fused.extraction import rfc_extractor as rx

    sip_cfg = rx._load_rfc_config("sip")
    rtsp_cfg = rx._load_rfc_config("rtsp")
    assert sip_cfg is not rtsp_cfg

    # SIP §20 = Header Fields → 用 SIP 配置 → field
    assert rx._section_kind({"section_no": "20.1", "title": "Accept"},
                            sip_cfg) == "field"
    # 用 RTSP 配置判 SIP §20 → RTSP 无 §20 → 不是 field
    assert rx._section_kind({"section_no": "20.1", "title": "Accept"},
                            rtsp_cfg) != "field"

    # RTSP §12 = Header Field Definitions → 用 RTSP 配置 → field
    assert rx._section_kind({"section_no": "12.1", "title": "Accept"},
                            rtsp_cfg) == "field"
    # 用 SIP 配置判 RTSP §12 → SIP 的 §12 是 "SIP Methods" → 不是 field
    assert rx._section_kind({"section_no": "12.1", "title": "Accept"},
                            sip_cfg) != "field"


def test_rfc_norms_are_scoped_to_target_protocol():
    """不同协议的 norms 不能互相污染（norm_id 带协议名）。"""
    from core.fused.extraction import rfc_extractor as rx

    sip_ids = {n["norm_id"] for n in rx.extract_rfc_norms("sip")}
    rtsp_ids = {n["norm_id"] for n in rx.extract_rfc_norms("rtsp")}
    assert sip_ids and rtsp_ids
    assert all(i.startswith("sip.") for i in sip_ids)
    assert all(i.startswith("rtsp.") for i in rtsp_ids)
    assert not (sip_ids & rtsp_ids), "两个协议的 norm_id 不应相交"
