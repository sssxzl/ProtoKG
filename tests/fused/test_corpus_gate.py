# -*- coding: utf-8 -*-
"""tests/fused/test_corpus_gate.py —— 语料发布准入闸（scripts/corpus_gate.py）的行为契约。

闸门要拦的是**静默退化**：2026-10-31 实测坐实过一次——`traffic` 源混入非目标
IP 摄像机的抓包 URL，59.5%（22/37）的 RTSP 种子打向了错误主机，而**现有所有
健康度指标一条都不会红**。本文件把"闸门必须能拦住它"固化成可执行断言。

覆盖的三条红线（判据见 docs/实验/RQ4_S4语料发布准入闸规格.md）：
  · **G1 目标端点正确率** —— 每个网络端点必须属于该协议的**合法端点集合**
  · **G2 不可播会话占比** —— 引用的会话名必须 ⊆ `playable_resources`
  · **G5 契约一致性** —— 产出条数 vs profile 契约；strict 阻断 / 非 strict 告警

★ **全部用 ``tmp_path`` 构造合成语料与合成 profile**：不依赖真实 ``derived/``
  的实验产物（那些内容会随实验重生成而变，会让本文件变成"测实验产物"而不是
  "测闸门逻辑"）。真实语料的验收用例由 ``qa/verify_corpus_gate_acceptance.py``
  在仓外承担。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.corpus_gate import (  # noqa: E402
    DEFAULT_MAX_VIOLATIONS,
    GATE_NAMES,
    SCHEMA_VERSION,
    detect_group,
    extract_endpoints,
    extract_sessions,
    main,
    read_manifest,
    render_report,
    resolve_env,
    run_gate,
)

# ===========================================================================
# 合成 profile / 合成语料 构造器
# ===========================================================================

#: 合成 RTSP profile 的默认 URL（= 目标端点，配置派生，禁止写死在闸里）。
_TARGET_URL = "rtsp://127.0.0.1:8554/"

#: 非目标端点（模拟污染源抓包里的 IP 摄像机）。
_CAMERA = "10.11.26.98:554"

#: 合成可播清单（模拟目标环境 live555 镜像里实际存在的 7 个会话）。
_PLAYABLE = ["mpeg1or2AudioVideoTest", "matroskaFileTest", "webmFileTest",
             "mp3AudioTest", "wavFileTest", "aacAudioTest", "ac3AudioTest"]


def make_rtsp_profile(*, focus_group_seeds: int = 3,
                      env_focus_group_seeds: int | None = None,
                      playable_resources_file: str | None = None,
                      environments: dict | None = None) -> dict:
    """构造一份合成 RTSP profile（结构与真实 profile.json 对齐）。

    ★ ``playable_resources_file`` 默认**不声明**：声明了就必须真的有那个文件，
      否则闸会按"可播清单不可解析"退化成配置错误（exit 2）——这是正确行为，
      但与"只想测 G1"的用例无关。G2 的用例显式传 ``"playable.json"``。
    """
    envs = environments
    if envs is None:
        env_cfg: dict = {"description": "合成目标环境"}
        if playable_resources_file:
            env_cfg["playable_resources_file"] = playable_resources_file
        if env_focus_group_seeds is not None:
            env_cfg["focus_group"] = {"B": {"dict": "base",
                                            "seeds": env_focus_group_seeds}}
        envs = {"synthetic-env": env_cfg}
    return {
        "protocol": "rtsp",
        "default_url": _TARGET_URL,
        "raw_format": {
            "line_ending": "\r\n",
            "request_line": "{method} {url} {version}",
            "version": "RTSP/1.0",
        },
        "allowed_methods": ["OPTIONS", "DESCRIBE", "SETUP", "PLAY", "TEARDOWN",
                            "GET_PARAMETER", "SET_PARAMETER"],
        "seedgen": {
            "focus_group": {"B": {"dict": "base", "seeds": focus_group_seeds}},
            "environments": envs,
        },
    }


def make_sip_profile() -> dict:
    """构造一份合成 SIP profile（opaque URI 形态 + client_side）。"""
    return {
        "protocol": "sip",
        "default_url": "sip:127.0.0.1:5060",
        "raw_format": {
            "line_ending": "\r\n",
            "request_line": "{method} {url} {version}",
            "version": "SIP/2.0",
        },
        "allowed_methods": ["REGISTER", "INVITE", "ACK", "BYE"],
        "seedgen": {
            "focus_group": {"B": {"dict": "protocol", "seeds": 1}},
            "environments": {"synthetic-env": {"description": "合成目标环境"}},
            "client_side": {
                "server_addr": "127.0.0.1:5060",
                "client_addr": "127.0.0.1:5061",
                "headers": ["Via", "Contact"],
            },
        },
    }


def make_smtp_profile() -> dict:
    """构造一份合成 SMTP profile（明文命令协议，无 URL 概念）。"""
    return {
        "protocol": "smtp",
        "default_url": "",
        "raw_format": {
            "line_ending": "\r\n",
            "request_line": "{method} {argument}",
            "version": "",
        },
        "allowed_methods": ["EHLO", "MAIL", "RCPT", "DATA", "QUIT"],
        "seedgen": {
            "focus_group": {"B": {"dict": "protocol", "seeds": 1}},
            "environments": {},
        },
    }


def write_rtsp_seed(seed_dir: Path, index: int, urls: list[str]) -> Path:
    """写一条合成 RTSP 种子（多条消息，每条消息一个请求行 URL）。"""
    seed_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i, url in enumerate(urls):
        lines.append(f"OPTIONS {url} RTSP/1.0")
        lines.append(f"CSeq: {i + 1}")
        lines.append("")
    path = seed_dir / f"{index:02d}_SYNTH.raw"
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return path


def write_sip_seed(seed_dir: Path, index: int, ruri: str,
                   via: str = "127.0.0.1:5061",
                   contact: str = "sip:127.0.0.1:5061") -> Path:
    """写一条合成 SIP 种子（含 Via / Contact / From / To / Call-ID）。"""
    seed_dir.mkdir(parents=True, exist_ok=True)
    body = (
        f"REGISTER {ruri} SIP/2.0\r\n"
        f"CSeq: 1 REGISTER\r\n"
        f"Call-ID: 105090259-446faf7a@192.168.1.2\r\n"
        f"Contact: <{contact}>\r\n"
        f'From: "arik" <sip:35104723@sip.cybercity.dk>;tag=175a1dd\r\n'
        f"To: <sip:0097239287044@sip.cybercity.dk>\r\n"
        f"Via: SIP/2.0/UDP {via};branch=z9hG4bKnp104984053-44ce4a41192."
        f"168.1.2;rport\r\n"
        f"Max-Forwards: 70\r\n"
        f"\r\n"
    )
    path = seed_dir / f"{index:02d}_SYNTH.raw"
    path.write_bytes(body.encode("utf-8"))
    return path


def write_smtp_seed(seed_dir: Path, index: int) -> Path:
    """写一条合成 SMTP 种子（纯命令序列，无 URL）。"""
    seed_dir.mkdir(parents=True, exist_ok=True)
    body = "EHLO client.example.com\r\nMAIL FROM:<sender@example.com>\r\nQUIT\r\n"
    path = seed_dir / f"{index:02d}_SYNTH.raw"
    path.write_bytes(body.encode("utf-8"))
    return path


@pytest.fixture()
def playable_root(tmp_path, monkeypatch):
    """把 ``paths.targets_root()`` 重定向到 tmp_path。

    ★ ``target_env.playable_resource_names`` 按 ``paths.targets_root()`` 解析清单
      文件位置（协议子目录优先，再兜底 targets 根目录）——那是**真实仓库路径**。
      测试不能往 ``fused_hub/`` 里写东西（只读实验产物区），故用 monkeypatch。
    """
    from core import paths as core_paths

    root = tmp_path / "targets"
    (root / "rtsp").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core_paths, "targets_root", lambda: root)
    return root


def _write_playable(playable_root: Path, names: list[str]) -> None:
    """把可播清单写到重定向后的 targets_root 下（协议子目录优先）。"""
    (playable_root / "rtsp" / "playable.json").write_text(
        json.dumps({"playable": names}), encoding="utf-8")


# ===========================================================================
# G1 —— 目标端点正确率
# ===========================================================================

class TestG1:
    """G1：语料里的每个网络端点都必须属于合法端点集合。"""

    def test_detects_non_target_endpoint(self, tmp_path):
        """合成语料含「打向非目标 IP 摄像机」的种子 → G1 必须检出并失败。"""
        profile = make_rtsp_profile()
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])
        write_rtsp_seed(seed_dir, 2, [f"rtsp://{_CAMERA}/isapi/streaming/channels/101"])
        write_rtsp_seed(seed_dir, 3, ["rtsp://127.0.0.1:8554/webmFileTest"])

        report = run_gate("rtsp", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["pass"] is False
        assert g1["violation_count"] == 1
        assert g1["violations"][0]["endpoint"] == _CAMERA
        assert g1["violations"][0]["occurrences"] == 1
        assert g1["violations"][0]["files"] == ["02_SYNTH.raw"]
        assert report["overall_pass"] is False

    def test_all_target_endpoint_passes(self, tmp_path):
        """全部指向目标端点的语料 → G1 必须通过。"""
        profile = make_rtsp_profile()
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])
        write_rtsp_seed(seed_dir, 2, ["rtsp://127.0.0.1:8554/webmFileTest"])

        report = run_gate("rtsp", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["pass"] is True
        assert g1["violation_count"] == 0
        assert g1["allowed_endpoints"] == ["127.0.0.1:8554"]
        assert g1["endpoints_found"] == {"127.0.0.1:8554": 2}

    def test_allowed_endpoints_come_from_profile(self, tmp_path):
        """合法端点集合必须**从配置派生**（禁止写死）。"""
        profile = make_rtsp_profile()
        profile["default_url"] = "rtsp://10.0.0.7:9999/"
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://10.0.0.7:9999/mp3AudioTest"])

        report = run_gate("rtsp", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["pass"] is True
        assert g1["allowed_endpoints"] == ["10.0.0.7:9999"]

    def test_port_must_match_exactly(self, tmp_path):
        """host 相同但端口不同 → 仍判为非目标（省略端口意味着走协议默认端口）。"""
        profile = make_rtsp_profile()
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:554/mp3AudioTest"])

        report = run_gate("rtsp", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["pass"] is False
        assert g1["violations"][0]["endpoint"] == "127.0.0.1:554"

    def test_one_bad_url_among_many_is_a_violation(self, tmp_path):
        """一条种子里只要有 1 个非目标端点 → 整条种子计为违规。"""
        profile = make_rtsp_profile()
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest",
                                      "rtsp://127.0.0.1:8554/webmFileTest",
                                      f"rtsp://{_CAMERA}/isapi/x"])

        report = run_gate("rtsp", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["pass"] is False
        assert g1["violation_count"] == 1
        assert g1["violations"][0]["files"] == ["01_SYNTH.raw"]

    def test_threshold_is_configurable(self, tmp_path):
        """阈值可配置：容忍度调高后同样的语料不再阻断。"""
        profile = make_rtsp_profile()
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, [f"rtsp://{_CAMERA}/isapi/x"])

        report = run_gate("rtsp", seed_dir, profile, max_violations=1)
        assert report["gates"]["G1"]["pass"] is True
        assert report["overall_pass"] is True

    def test_default_threshold_is_zero(self):
        """默认阈值 = 0 违规（打错主机一条即阻断）。"""
        assert DEFAULT_MAX_VIOLATIONS == 0

    def test_smtp_is_skipped_with_explicit_reason(self, tmp_path):
        """SMTP：语料端点数 = 0 且 default_url 为空 → G1 显式 skip 并说明原因。"""
        profile = make_smtp_profile()
        seed_dir = tmp_path / "seeds"
        write_smtp_seed(seed_dir, 1)

        report = run_gate("smtp", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["applicable"] is False
        assert g1["skipped_reason"]
        assert "default_url" in g1["skipped_reason"]
        assert "端点数 = 0" in g1["skipped_reason"]
        # 不适用 ≠ 失败
        assert g1["pass"] is True

    def test_skip_reason_is_distinguishable_from_pass(self, tmp_path):
        """「不适用」必须与「通过」可区分（否则 CI 假绿）。"""
        profile = make_smtp_profile()
        seed_dir = tmp_path / "seeds"
        write_smtp_seed(seed_dir, 1)

        report = run_gate("smtp", seed_dir, profile)
        text = render_report(report)

        assert "SKIPPED（不适用）" in text
        assert "不适用 ≠ 通过" in text


# ===========================================================================
# G1 —— SIP 的字段级抽取规则（误报重灾区）
# ===========================================================================

class TestG1SipFieldRules:
    """SIP：端点只从 R-URI / Via sent-by / Contact 三处抽取。"""

    def test_r_uri_via_contact_are_legal(self, tmp_path):
        """R-URI(5060) / Via(5061) / Contact(5061) 都是合法端点 → 0 违规。"""
        profile = make_sip_profile()
        seed_dir = tmp_path / "seeds"
        write_sip_seed(seed_dir, 1, "sip:127.0.0.1:5060")

        report = run_gate("sip", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["pass"] is True
        assert g1["violation_count"] == 0
        assert g1["allowed_endpoints"] == ["127.0.0.1:5060", "127.0.0.1:5061"]
        assert g1["endpoints_found"] == {"127.0.0.1:5060": 1, "127.0.0.1:5061": 2}

    def test_call_id_from_to_and_branch_params_are_excluded(self, tmp_path):
        """★ Call-ID / From / To / branch 参数里的 IP **不得**被判违规。

        官方语料本身就带 ``Call-ID: ...@192.168.1.2``、``From: <sip:...@sip.cybercity.dk>``、
        ``branch=...192.168.1.2`` —— 朴素"抓所有 IP"的写法会误报上百次。
        """
        profile = make_sip_profile()
        seed_dir = tmp_path / "seeds"
        write_sip_seed(seed_dir, 1, "sip:127.0.0.1:5060")

        report = run_gate("sip", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["violation_count"] == 0, g1["violations"]
        assert "192.168.1.2" not in json.dumps(report)

    def test_foreign_host_in_r_uri_is_a_violation(self, tmp_path):
        """R-URI 指向外来主机 → 必须判违规（这正是 SIP 不能判「不适用」的原因）。"""
        profile = make_sip_profile()
        seed_dir = tmp_path / "seeds"
        write_sip_seed(seed_dir, 1, "sip:213.192.59.75")

        report = run_gate("sip", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["pass"] is False
        assert g1["violations"][0]["endpoint"] == "213.192.59.75:5060"

    def test_foreign_host_in_via_is_a_violation(self, tmp_path):
        """Via sent-by 指向外来主机 → 必须判违规。"""
        profile = make_sip_profile()
        seed_dir = tmp_path / "seeds"
        write_sip_seed(seed_dir, 1, "sip:127.0.0.1:5060", via="10.11.26.98:5061")

        report = run_gate("sip", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["pass"] is False
        assert g1["violations"][0]["endpoint"] == "10.11.26.98:5061"

    def test_double_slash_form_is_tolerated(self, tmp_path):
        """★ ``sip://host:port`` 双斜杠畸形形态必须**容忍**（不能漏检也不能误报）。

        已知退化：当前重新生成的 SIP 语料里出现 10 次 ``sip://127.0.0.1:5060``。
        """
        profile = make_sip_profile()
        seed_dir = tmp_path / "seeds"
        write_sip_seed(seed_dir, 1, "sip://127.0.0.1:5060")

        report = run_gate("sip", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["pass"] is True
        assert g1["endpoints_found"]["127.0.0.1:5060"] == 1

    def test_hostless_uri_is_skipped_not_violation(self, tmp_path):
        """``sip:bob``（只有 user、无 host）→ 跳过，不判违规。"""
        profile = make_sip_profile()
        seed_dir = tmp_path / "seeds"
        write_sip_seed(seed_dir, 1, "sip:bob")

        report = run_gate("sip", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["pass"] is True
        assert g1["violation_count"] == 0

    def test_missing_port_is_completed_from_config(self, tmp_path):
        """``sip:127.0.0.1``（无端口）→ 按服务端端口 5060 补齐。"""
        profile = make_sip_profile()
        seed_dir = tmp_path / "seeds"
        write_sip_seed(seed_dir, 1, "sip:127.0.0.1")

        report = run_gate("sip", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["pass"] is True
        assert g1["endpoints_found"]["127.0.0.1:5060"] == 1


# ===========================================================================
# G2 —— 不可播会话占比
# ===========================================================================

class TestG2:
    """G2：语料引用的会话/资源名必须 ⊆ 可播清单。"""

    def test_detects_unplayable_resource(self, playable_root, tmp_path):
        """合成语料引用了不可播会话 → G2 必须检出。"""
        _write_playable(playable_root, _PLAYABLE)
        profile = make_rtsp_profile(playable_resources_file="playable.json")
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])
        write_rtsp_seed(seed_dir, 2, ["rtsp://127.0.0.1:8554/vobTest"])
        write_rtsp_seed(seed_dir, 3, ["rtsp://127.0.0.1:8554/webmFileTest"])

        env_name, env_cfg = resolve_env(profile, {}, "synthetic-env")
        report = run_gate("rtsp", seed_dir, profile, env_name=env_name,
                          env_cfg=env_cfg)
        g2 = report["gates"]["G2"]

        assert g2["pass"] is False
        assert g2["violation_count"] == 1
        assert g2["violations"][0]["resource"] == "vobTest"
        assert g2["violations"][0]["files"] == ["02_SYNTH.raw"]
        assert report["overall_pass"] is False

    def test_all_playable_passes(self, playable_root, tmp_path):
        """全部引用可播会话 → G2 必须通过。"""
        _write_playable(playable_root, _PLAYABLE)
        profile = make_rtsp_profile(playable_resources_file="playable.json")
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])
        write_rtsp_seed(seed_dir, 2, ["rtsp://127.0.0.1:8554/webmFileTest"])

        env_name, env_cfg = resolve_env(profile, {}, "synthetic-env")
        report = run_gate("rtsp", seed_dir, profile, env_name=env_name,
                          env_cfg=env_cfg)
        g2 = report["gates"]["G2"]

        assert g2["pass"] is True
        assert g2["violation_count"] == 0
        assert g2["allowed_resources"] == sorted(_PLAYABLE)

    def test_session_name_is_first_path_segment_not_last(self, playable_root,
                                                          tmp_path):
        """★ 会话名取**主机后第一个路径段**，不是末段。

        ``SETUP rtsp://host/<session>/track1`` 的末段是 ``track1``（track，不是
        会话名）—— 用末段会产生假违规**并**掩盖真违规。
        """
        _write_playable(playable_root, _PLAYABLE)
        profile = make_rtsp_profile(playable_resources_file="playable.json")
        seed_dir = tmp_path / "seeds"
        seed_dir.mkdir(parents=True, exist_ok=True)
        (seed_dir / "01_SYNTH.raw").write_bytes(
            b"SETUP rtsp://127.0.0.1:8554/mpeg1or2AudioVideoTest/track1 "
            b"RTSP/1.0\r\nCSeq: 1\r\n\r\n")

        env_name, env_cfg = resolve_env(profile, {}, "synthetic-env")
        report = run_gate("rtsp", seed_dir, profile, env_name=env_name,
                          env_cfg=env_cfg)
        g2 = report["gates"]["G2"]

        assert g2["pass"] is True
        assert g2["resources_found"] == {"mpeg1or2AudioVideoTest": 1}

    def test_sip_is_skipped(self, tmp_path):
        """SIP 无会话概念 → G2 显式 skip 并说明原因。"""
        profile = make_sip_profile()
        seed_dir = tmp_path / "seeds"
        write_sip_seed(seed_dir, 1, "sip:127.0.0.1:5060")

        env_name, env_cfg = resolve_env(profile, {}, "synthetic-env")
        report = run_gate("sip", seed_dir, profile, env_name=env_name,
                          env_cfg=env_cfg)
        g2 = report["gates"]["G2"]

        assert g2["applicable"] is False
        assert g2["skipped_reason"]
        assert g2["pass"] is True

    def test_threshold_is_configurable(self, playable_root, tmp_path):
        """G2 阈值可配置。"""
        _write_playable(playable_root, _PLAYABLE)
        profile = make_rtsp_profile(playable_resources_file="playable.json")
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/vobTest"])

        env_name, env_cfg = resolve_env(profile, {}, "synthetic-env")
        report = run_gate("rtsp", seed_dir, profile, env_name=env_name,
                          env_cfg=env_cfg, max_violations=1)
        assert report["gates"]["G2"]["pass"] is True


# ===========================================================================
# G1 / G2 互补性（QA-4 提出的高价值固化点）
# ===========================================================================

class TestG1G2Complementarity:
    """★ G1 与 G2 互补、不可互相替代——必须用测试固化。

    「外来 host + **合法**资源名」这一形态：G2（资源名口径）**100% 漏掉**，
    G1（端点口径）**100% 抓住**。若有人把 G1 的口径改窄（例如只查路径段），
    G2 不会兜底 → 污染会静默回来。
    """

    def test_foreign_host_with_legal_resource(self, playable_root, tmp_path):
        """外来 host + 合法可播资源名 → G1 必须 FAIL（即使 G2 PASS）。"""
        _write_playable(playable_root, _PLAYABLE)
        profile = make_rtsp_profile(playable_resources_file="playable.json")
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, [f"rtsp://{_CAMERA}/mpeg1or2AudioVideoTest"])
        write_rtsp_seed(seed_dir, 2, [f"rtsp://{_CAMERA}/matroskaFileTest"])

        env_name, env_cfg = resolve_env(profile, {}, "synthetic-env")
        report = run_gate("rtsp", seed_dir, profile, env_name=env_name,
                          env_cfg=env_cfg)

        assert report["gates"]["G1"]["pass"] is False      # G1 抓住
        assert report["gates"]["G2"]["pass"] is True       # G2 漏掉（合法资源名）
        assert report["overall_pass"] is False


# ===========================================================================
# G5 —— 契约一致性（focus_group 条数）
# ===========================================================================

class TestG5:
    """G5：产出条数必须等于 profile 声明的契约条数。"""

    def test_contract_mismatch_warns_without_strict(self, tmp_path):
        """条数与契约不符 → 非 strict 模式只告警（不阻断）。"""
        profile = make_rtsp_profile(focus_group_seeds=5)
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])
        write_rtsp_seed(seed_dir, 2, ["rtsp://127.0.0.1:8554/webmFileTest"])

        report = run_gate("rtsp", seed_dir, profile, group="B")
        g5 = report["gates"]["G5"]

        assert g5["pass"] is False
        assert g5["expected"] == 5
        assert g5["actual"] == 2
        assert g5["warning"]
        # 默认不阻断
        assert report["overall_pass"] is True

    def test_contract_mismatch_blocks_with_strict(self, tmp_path):
        """条数与契约不符 → strict 模式必须阻断。"""
        profile = make_rtsp_profile(focus_group_seeds=5)
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])
        write_rtsp_seed(seed_dir, 2, ["rtsp://127.0.0.1:8554/webmFileTest"])

        report = run_gate("rtsp", seed_dir, profile, group="B", strict=True)
        g5 = report["gates"]["G5"]

        assert g5["pass"] is False
        assert report["overall_pass"] is False

    def test_contract_match_passes(self, tmp_path):
        """条数与契约一致 → 通过（strict 下也通过）。"""
        profile = make_rtsp_profile(focus_group_seeds=2)
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])
        write_rtsp_seed(seed_dir, 2, ["rtsp://127.0.0.1:8554/webmFileTest"])

        report = run_gate("rtsp", seed_dir, profile, group="B", strict=True)
        assert report["gates"]["G5"]["pass"] is True
        assert report["overall_pass"] is True

    def test_environment_contract_wins_over_protocol_level(self, tmp_path):
        """环境级 focus_group 覆盖协议级 → 契约来源标注为环境级路径。"""
        profile = make_rtsp_profile(focus_group_seeds=50,
                                    env_focus_group_seeds=2)
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])
        write_rtsp_seed(seed_dir, 2, ["rtsp://127.0.0.1:8554/webmFileTest"])

        env_name, env_cfg = resolve_env(profile, {}, "synthetic-env")
        report = run_gate("rtsp", seed_dir, profile, env_name=env_name,
                          env_cfg=env_cfg, group="B", strict=True)
        g5 = report["gates"]["G5"]

        assert g5["pass"] is True
        assert g5["expected"] == 2
        assert g5["contract_source"] == (
            "profile.seedgen.environments.synthetic-env.focus_group.B.seeds")

    def test_protocol_level_contract_when_no_environment(self, tmp_path):
        """profile 无 environments 段（如 SMTP）→ 契约来源是协议级路径。"""
        profile = make_smtp_profile()
        seed_dir = tmp_path / "seeds"
        write_smtp_seed(seed_dir, 1)

        report = run_gate("smtp", seed_dir, profile, group="B")
        g5 = report["gates"]["G5"]

        assert g5["contract_source"] == "profile.seedgen.focus_group.B.seeds"
        assert g5["expected"] == 1
        assert g5["actual"] == 1

    def test_unknown_group_is_skipped(self, tmp_path):
        """无法判定聚焦组 → G5 显式 skip。"""
        profile = make_rtsp_profile()
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])

        report = run_gate("rtsp", seed_dir, profile, group=None)
        g5 = report["gates"]["G5"]

        assert g5["applicable"] is False
        assert g5["skipped_reason"]
        assert g5["pass"] is True


# ===========================================================================
# JSON 输出契约（规格书 §3.2，字段级固定）
# ===========================================================================

class TestJsonContract:
    """JSON 报告的字段必须**固定**（CI 管道可能消费它）。"""

    def test_top_level_fields(self, tmp_path):
        profile = make_rtsp_profile()
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])

        report = run_gate("rtsp", seed_dir, profile, group="B")

        assert report["schema_version"] == SCHEMA_VERSION
        assert set(report) >= {"schema_version", "protocol", "env", "group",
                               "seed_dir", "seed_files", "gates", "overall_pass"}
        assert report["seed_files"] == 1
        assert set(report["gates"]) == {"G1", "G2", "G5"}

    def test_gate_field_names_are_fixed(self, tmp_path):
        profile = make_rtsp_profile()
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])

        report = run_gate("rtsp", seed_dir, profile, group="B")

        g1 = report["gates"]["G1"]
        assert g1["name"] == GATE_NAMES["G1"]
        assert set(g1) >= {"name", "applicable", "skipped_reason",
                           "allowed_endpoints", "endpoints_found", "violations",
                           "violation_count", "threshold", "pass"}
        g2 = report["gates"]["G2"]
        assert g2["name"] == GATE_NAMES["G2"]
        assert set(g2) >= {"name", "applicable", "skipped_reason",
                           "allowed_resources", "resources_found", "violations",
                           "violation_count", "threshold", "pass"}
        g5 = report["gates"]["G5"]
        assert g5["name"] == GATE_NAMES["G5"]
        assert set(g5) >= {"name", "applicable", "skipped_reason",
                           "contract_source", "expected", "actual", "pass"}

    def test_skipped_gate_has_reason_and_pass(self, tmp_path):
        """``applicable=false`` 时 ``skipped_reason`` 必填（否则 CI 假绿）。"""
        profile = make_smtp_profile()
        seed_dir = tmp_path / "seeds"
        write_smtp_seed(seed_dir, 1)

        report = run_gate("smtp", seed_dir, profile, group="B")
        for gate in ("G1", "G2"):
            data = report["gates"][gate]
            assert data["applicable"] is False
            assert data["skipped_reason"]
            assert data["pass"] is True

    def test_violation_files_capped_at_20(self, tmp_path):
        """``violations[].files`` 最多 20 个（避免 JSON 爆炸）。"""
        profile = make_rtsp_profile()
        seed_dir = tmp_path / "seeds"
        for i in range(25):
            write_rtsp_seed(seed_dir, i + 1, [f"rtsp://{_CAMERA}/isapi/x"])

        report = run_gate("rtsp", seed_dir, profile)
        g1 = report["gates"]["G1"]

        assert g1["violation_count"] == 25
        assert len(g1["violations"][0]["files"]) == 20


# ===========================================================================
# 退出码（CI 契约：0 / 1 / 2 三态）
# ===========================================================================

class TestExitCode:
    """退出码：0 = 通过；1 = 阻断；2 = 配置错误。"""

    def _profile_file(self, tmp_path, profile: dict) -> Path:
        path = tmp_path / "profile.json"
        path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
        return path

    def test_exit_zero_when_all_pass(self, tmp_path):
        profile = make_rtsp_profile(focus_group_seeds=1)
        profile_path = self._profile_file(tmp_path, profile)
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(profile_path), "--group", "B"])
        assert code == 0

    def test_exit_one_when_g1_violates(self, tmp_path):
        profile = make_rtsp_profile(focus_group_seeds=1)
        profile_path = self._profile_file(tmp_path, profile)
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, [f"rtsp://{_CAMERA}/isapi/x"])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(profile_path), "--group", "B"])
        assert code == 1

    def test_exit_one_when_g5_drift_with_strict(self, tmp_path):
        profile = make_rtsp_profile(focus_group_seeds=9)
        profile_path = self._profile_file(tmp_path, profile)
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(profile_path), "--group", "B",
                     "--strict"])
        assert code == 1

    def test_exit_zero_when_g5_drift_without_strict(self, tmp_path):
        """G5 漂移在非 strict 模式下**不阻断**（已知历史漂移，待用户决策）。"""
        profile = make_rtsp_profile(focus_group_seeds=9)
        profile_path = self._profile_file(tmp_path, profile)
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(profile_path), "--group", "B"])
        assert code == 0

    def test_exit_two_when_seed_dir_missing(self, tmp_path):
        code = main(["--protocol", "rtsp", "--seed-dir", str(tmp_path / "nope")])
        assert code == 2

    def test_exit_two_when_profile_missing(self, tmp_path):
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(tmp_path / "missing.json")])
        assert code == 2

    def test_exit_two_when_env_name_unknown(self, tmp_path):
        profile = make_rtsp_profile()
        profile_path = self._profile_file(tmp_path, profile)
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(profile_path), "--env", "no-such-env"])
        assert code == 2

    def test_exit_two_when_env_ambiguous(self, tmp_path):
        """profile 声明多个环境且未显式指定 → 配置错误（不是违规）。"""
        profile = make_rtsp_profile(environments={
            "env-a": {"playable_resources_file": "playable.json"},
            "env-b": {"playable_resources_file": "playable.json"},
        })
        profile_path = self._profile_file(tmp_path, profile)
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(profile_path)])
        assert code == 2

    def test_json_output_is_machine_readable(self, tmp_path, capsys):
        profile = make_rtsp_profile(focus_group_seeds=1)
        profile_path = self._profile_file(tmp_path, profile)
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])

        main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
              "--profile", str(profile_path), "--group", "B", "--json"])
        payload = json.loads(capsys.readouterr().out)

        assert payload["schema_version"] == SCHEMA_VERSION
        assert set(payload["gates"]) == {"G1", "G2", "G5"}
        assert payload["overall_pass"] is True


# ===========================================================================
# 只读性 + 环境/分组解析
# ===========================================================================

class TestReadOnly:
    """闸门是**纯检查项**：不得修改 kb/ / derived/ / fused_hub/ 下任何文件。"""

    def test_gate_does_not_modify_anything(self, tmp_path):
        profile = make_rtsp_profile(focus_group_seeds=1)
        profile_path = tmp_path / "profile.json"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        seed_dir = tmp_path / "seeds"
        seed = write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])

        before = {p: p.stat().st_mtime_ns for p in
                  sorted(seed_dir.rglob("*")) if p.is_file()}
        before[profile_path] = profile_path.stat().st_mtime_ns

        main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
              "--profile", str(profile_path), "--group", "B"])

        after = {p: p.stat().st_mtime_ns for p in
                 sorted(seed_dir.rglob("*")) if p.is_file()}
        after[profile_path] = profile_path.stat().st_mtime_ns

        assert before == after
        assert set(before) == set(after)
        assert seed.exists()

    def test_no_new_files_created(self, tmp_path):
        profile = make_rtsp_profile(focus_group_seeds=1)
        profile_path = tmp_path / "profile.json"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])

        listing_before = sorted(p.name for p in tmp_path.iterdir())
        main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
              "--profile", str(profile_path), "--group", "B"])
        listing_after = sorted(p.name for p in tmp_path.iterdir())

        assert listing_before == listing_after

    def test_refuses_to_write_report_into_protected_dirs(self, tmp_path):
        """``--json-out`` 不得写进 kb/ derived/ fused_hub/。"""
        profile = make_rtsp_profile(focus_group_seeds=1)
        profile_path = tmp_path / "profile.json"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(profile_path), "--group", "B",
                     "--json-out", str(ROOT / "derived" / "gate_report.json")])
        assert code == 2
        assert not (ROOT / "derived" / "gate_report.json").exists()


class TestEnvAndGroupResolution:
    """环境/分组解析：数据来源优先级必须稳定。"""

    def test_env_prefers_manifest_over_unique_profile_env(self, tmp_path):
        profile = make_rtsp_profile()
        seed_dir = tmp_path / "seeds"
        write_rtsp_seed(seed_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])
        (seed_dir / "manifest.json").write_text(
            json.dumps({"seedgen": {"target_env": "synthetic-env"}}),
            encoding="utf-8")

        manifest = read_manifest(seed_dir)
        name, _cfg = resolve_env(profile, manifest)
        assert name == "synthetic-env"

    def test_env_falls_back_to_unique_profile_env(self, tmp_path):
        """★ 无 manifest 时退回 profile 的**唯一**环境。

        违约语料恰恰没有 manifest（seedgen 条数自检失败即退出、不写 manifest）
        ⇒ 无此兜底会退回协议级契约，把"环境级 39"错报成"契约 50"。
        """
        profile = make_rtsp_profile()
        name, _cfg = resolve_env(profile, {})
        assert name == "synthetic-env"

    def test_group_detected_from_manifest(self, tmp_path):
        seed_dir = tmp_path / "seeds"
        seed_dir.mkdir()
        (seed_dir / "manifest.json").write_text(
            json.dumps({"seedgen": {"focus_group": "B"}}), encoding="utf-8")

        assert detect_group(seed_dir, read_manifest(seed_dir)) == "B"

    def test_group_detected_from_dir_name(self, tmp_path):
        seed_dir = tmp_path / "rq4_B"
        seed_dir.mkdir()
        assert detect_group(seed_dir, {}) == "B"

    def test_group_detected_from_parent_dir_name(self, tmp_path):
        """RQ3 布局：<group>/seeds/*.raw，组名在父目录名里。"""
        seed_dir = tmp_path / "B" / "seeds"
        seed_dir.mkdir(parents=True)
        assert detect_group(seed_dir, {}) == "B"


# ===========================================================================
# 抽取器单元测试
# ===========================================================================

class TestExtractors:
    """抽取器的边界行为（口径的最小可验证单元）。"""

    def test_extract_sessions_ignores_non_request_lines(self):
        profile = make_rtsp_profile()
        text = ("CSeq: 1\r\n"
                "OPTIONS rtsp://127.0.0.1:8554/mp3AudioTest RTSP/1.0\r\n")
        assert extract_sessions(text, profile) == ["mp3AudioTest"]

    def test_extract_endpoints_hierarchical(self):
        profile = make_rtsp_profile()
        text = "OPTIONS rtsp://127.0.0.1:8554/x RTSP/1.0\r\n"
        endpoints = extract_endpoints(text, profile, 1)
        assert endpoints == [("127.0.0.1:8554", "url-authority")]

    def test_extract_endpoints_opaque_ignores_non_client_headers(self):
        profile = make_sip_profile()
        text = ("REGISTER sip:127.0.0.1:5060 SIP/2.0\r\n"
                "From: <sip:999@evil.example.org>\r\n")
        endpoints = extract_endpoints(text, profile, 1)
        assert [ep for ep, _pos in endpoints] == ["127.0.0.1:5060"]


# ===========================================================================
# 端到端：真实脚本入口
# ===========================================================================

def test_script_runs_as_subprocess_and_returns_exit_code(tmp_path):
    """脚本作为子进程运行：正常语料 → exit 0；污染语料 → exit 1。"""
    profile = make_rtsp_profile(focus_group_seeds=1)
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    good_dir = tmp_path / "good"
    write_rtsp_seed(good_dir, 1, ["rtsp://127.0.0.1:8554/mp3AudioTest"])
    bad_dir = tmp_path / "bad"
    write_rtsp_seed(bad_dir, 1, [f"rtsp://{_CAMERA}/isapi/x"])

    script = ROOT / "scripts" / "corpus_gate.py"

    good = subprocess.run(
        [sys.executable, str(script), "--protocol", "rtsp",
         "--seed-dir", str(good_dir), "--profile", str(profile_path),
         "--group", "B"],
        capture_output=True, text=True, cwd=str(ROOT))
    assert good.returncode == 0, good.stdout + good.stderr
    assert "总判定：通过" in good.stdout

    bad = subprocess.run(
        [sys.executable, str(script), "--protocol", "rtsp",
         "--seed-dir", str(bad_dir), "--profile", str(profile_path),
         "--group", "B"],
        capture_output=True, text=True, cwd=str(ROOT))
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert "总判定：阻断" in bad.stdout
