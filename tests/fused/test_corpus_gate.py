# -*- coding: utf-8 -*-
"""tests/fused/test_corpus_gate.py —— 语料发布准入闸（scripts/corpus_gate.py）的行为契约。

闸门要拦的是**静默退化**：2026-10-31 实测坐实过一次——`traffic` 源混入非目标
IP 摄像机的抓包 URL，59.5%（22/37）的 RTSP 种子打向了错误主机，而**现有所有
健康度指标一条都不会红**。本文件把"闸门必须能拦住它"固化成可执行断言。

覆盖的三条红线：
  · **G1 目标主机正确率** —— 指向非目标 host:port 的种子占比超阈值 → 失败
  · **G2 不可播会话占比** —— 引用不可播资源名的种子占比超阈值 → 失败
  · **G5 契约一致性** —— focus_group 条数契约 vs 实际条数；strict 阻断 / 非 strict 告警

★ **全部用 ``tmp_path`` 构造合成语料与合成 profile**：不依赖真实 ``derived/``
  的实验产物（那些内容会随实验重生成而变，会让本文件变成"测实验产物"而不是
  "测闸门逻辑"）。
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
    STATUS_FAIL,
    STATUS_NA,
    STATUS_PASS,
    STATUS_WARN,
    Thresholds,
    detect_group,
    main,
    read_manifest,
    read_seed_texts,
    resolve_env,
    run_gate,
)

# ===========================================================================
# 合成语料 / 合成 profile 构造器
# ===========================================================================

#: 合成 profile 的默认 URL（= 目标端点，配置派生，禁止写死在闸门里）。
_TARGET_URL = "rtsp://127.0.0.1:8554/"

#: 合成 profile 的非目标端点（模拟污染源抓包里的 IP 摄像机）。
_WRONG_URL = "rtsp://10.11.26.98:554/isapi/streaming/channels/101"

#: 合成可播清单（模拟目标环境 live555 镜像里实际存在的 7 个会话）。
_PLAYABLE = ["mpeg1or2AudioVideoTest", "matroskaFileTest", "webmFileTest",
             "mp3AudioTest", "wavFileTest", "aacAudioTest", "ac3AudioTest"]


def make_profile(*, default_url: str = _TARGET_URL,
                 playable_resources_file: str | None = "playable.json",
                 focus_group_seeds: int = 3,
                 env_focus_group_seeds: int | None = None,
                 environments: dict | None = None) -> dict:
    """构造一份合成 profile（结构与真实 profile.json 对齐）。

    Args:
        default_url: 协议默认 URL（目标端点的配置来源）。
        playable_resources_file: 环境级可播清单文件名；None → 不声明可播清单。
        focus_group_seeds: 协议级 focus_group.B.seeds 契约。
        env_focus_group_seeds: 环境级 focus_group.B.seeds 覆盖（None → 不覆盖）。
        environments: 直接给定 environments 段（覆盖自动生成的）。

    Returns:
        profile 字典。
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
        "default_url": default_url,
        "raw_format": {
            "line_ending": "\r\n",
            "request_line": "{method} {url} {version}",
            "version": "RTSP/1.0",
        },
        "allowed_methods": ["OPTIONS", "DESCRIBE", "SETUP", "PLAY", "TEARDOWN"],
        "url_placeholders": {"<server>": "127.0.0.1:8554", "<stream>": "mp3AudioTest"},
        "seedgen": {
            "focus_group": {"B": {"dict": "base", "seeds": focus_group_seeds}},
            "environments": envs,
        },
    }


@pytest.fixture()
def playable_root(tmp_path, monkeypatch):
    """把 ``paths.targets_root()`` 重定向到 tmp_path，并返回该目录。

    清单文件按 ``target_env._resource_file_candidates`` 的查找顺序放置：
    ``<targets_root>/<protocol>/<file>`` 优先，再 ``<targets_root>/<file>``。
    """
    from core import paths as core_paths

    root = tmp_path / "targets"
    (root / "rtsp").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core_paths, "targets_root", lambda: root)
    return root


def write_seed(seed_dir: Path, index: int, urls: list[str],
               resources: list[str] | None = None) -> Path:
    """写一条合成 RTSP 种子（多条消息，每条消息一个请求行 URL）。

    Args:
        seed_dir: 种子目录。
        index: 种子序号（决定文件名）。
        urls: 各消息的请求行 URL（可含非目标端点 → 模拟污染）。
        resources: 各消息的资源名（默认从 URL 末段推导）。
    """
    seed_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i, url in enumerate(urls):
        lines.append(f"OPTIONS {url} RTSP/1.0")
        lines.append(f"CSeq: {i + 1}")
        lines.append("")
    path = seed_dir / f"{index:02d}_SYNTH.raw"
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return path


def seed_texts_from(seed_dir: Path):
    """读合成种子目录 → ``[(path, text)]``（与闸门内部同构）。"""
    files = sorted(Path(seed_dir).glob("*.raw"))
    return read_seed_texts(files)


# ===========================================================================
# G1 —— 目标主机正确率
# ===========================================================================

class TestG1:
    """G1：种子里的 URL 必须指向目标环境的服务端点。"""

    def test_detects_non_target_host(self, tmp_path):
        """合成语料含「打向非目标 IP 摄像机」的种子 → G1 必须检出并失败。"""
        profile = make_profile()
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])
        write_seed(seed_dir, 2, [_WRONG_URL])          # ← 污染
        write_seed(seed_dir, 3, [f"{_TARGET_URL}webmFileTest"])

        outcomes = run_gate("rtsp", seed_dir, profile)
        g1 = next(o for o in outcomes if o.gate == "G1")

        assert g1.status == STATUS_FAIL, g1.summary
        assert g1.blocking is True
        assert g1.details["wrong_target_seeds"] == 1
        assert g1.details["checkable_seeds"] == 3
        assert g1.details["wrong_target_ratio"] == pytest.approx(1 / 3)
        # 非目标端点分布必须点名，便于定位污染源
        assert "10.11.26.98:554" in g1.details["offending_endpoints"]

    def test_all_target_host_passes(self, tmp_path):
        """全部指向目标 host 的语料 → G1 必须通过。"""
        profile = make_profile()
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])
        write_seed(seed_dir, 2, [f"{_TARGET_URL}webmFileTest"])

        outcomes = run_gate("rtsp", seed_dir, profile)
        g1 = next(o for o in outcomes if o.gate == "G1")

        assert g1.status == STATUS_PASS, g1.summary
        assert g1.details["wrong_target_seeds"] == 0
        assert g1.details["target_endpoint"] == "127.0.0.1:8554"

    def test_port_must_match_exactly(self, tmp_path):
        """host 相同但端口不同 → 仍判为非目标（省略端口意味着走协议默认端口）。"""
        profile = make_profile()
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, ["rtsp://127.0.0.1:554/mp3AudioTest"])

        outcomes = run_gate("rtsp", seed_dir, profile)
        g1 = next(o for o in outcomes if o.gate == "G1")

        assert g1.status == STATUS_FAIL, g1.summary
        assert g1.details["wrong_target_seeds"] == 1

    def test_one_bad_url_in_many_poisons_whole_seed(self, tmp_path):
        """一条种子里只要有 1 个非目标 URL → 整条种子计为坏种子（不被稀释）。"""
        profile = make_profile()
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest",
                                 f"{_TARGET_URL}webmFileTest",
                                 _WRONG_URL])

        outcomes = run_gate("rtsp", seed_dir, profile)
        g1 = next(o for o in outcomes if o.gate == "G1")

        assert g1.status == STATUS_FAIL, g1.summary
        assert g1.details["wrong_target_seeds"] == 1
        assert g1.details["checkable_seeds"] == 1

    def test_threshold_is_configurable(self, tmp_path):
        """阈值可配置：把容忍度调到 100% 则同样的语料不再阻断。"""
        profile = make_profile()
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [_WRONG_URL])

        outcomes = run_gate("rtsp", seed_dir, profile,
                            thresholds=Thresholds(max_wrong_target_ratio=1.0))
        g1 = next(o for o in outcomes if o.gate == "G1")

        assert g1.status == STATUS_PASS, g1.summary

    def test_target_endpoint_comes_from_profile_not_hardcoded(self, tmp_path):
        """目标端点必须**从配置派生**：改 profile.default_url → 判定随之改变。"""
        profile = make_profile(default_url="rtsp://10.0.0.7:9999/")
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, ["rtsp://10.0.0.7:9999/mp3AudioTest"])

        outcomes = run_gate("rtsp", seed_dir, profile)
        g1 = next(o for o in outcomes if o.gate == "G1")

        assert g1.status == STATUS_PASS, g1.summary
        assert g1.details["target_endpoint"] == "10.0.0.7:9999"

    def test_opaque_uri_protocol_is_not_applicable(self, tmp_path):
        """opaque URI 协议（SIP 形态：domain 是逻辑实体标识）→ G1 显式 N/A。"""
        profile = make_profile(default_url="sip:127.0.0.1:5060")
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, ["sip:alice@sip.cybercity.dk"])

        outcomes = run_gate("sip", seed_dir, profile)
        g1 = next(o for o in outcomes if o.gate == "G1")

        assert g1.status == STATUS_NA, g1.summary
        assert g1.details["applicable"] is False
        assert "不决定路由" in g1.summary or "不决定请求目标" in g1.summary

    def test_explicit_config_switch_controls_applicability(self, tmp_path):
        """协议级开关 ``seedgen.target_endpoint_normalization`` 决定 G1 是否适用。

        这是**配置驱动**的判定：开关关闭 → 即使 URI 带 authority 也不适用
        （该协议的端点不决定请求目标）；开关开启 → 适用。
        """
        # 开关缺省 + 分层 URI → 兜底判定为适用
        profile = make_profile()
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])
        outcomes = run_gate("rtsp", seed_dir, profile)
        assert next(o for o in outcomes if o.gate == "G1").status == STATUS_PASS

        # 显式关闭开关 → 不适用（协议声明"端点不决定请求目标"）
        profile_off = make_profile()
        profile_off["seedgen"]["target_endpoint_normalization"] = False
        outcomes = run_gate("rtsp", seed_dir, profile_off)
        g1 = next(o for o in outcomes if o.gate == "G1")
        assert g1.status == STATUS_NA, g1.summary
        assert g1.details["reason"] == "endpoint_not_routing_bearing"

        # 显式开启开关 → 适用
        profile_on = make_profile()
        profile_on["seedgen"]["target_endpoint_normalization"] = True
        outcomes = run_gate("rtsp", seed_dir, profile_on)
        assert next(o for o in outcomes if o.gate == "G1").status == STATUS_PASS

    def test_protocol_without_url_field_is_not_applicable(self, tmp_path):
        """profile 的 request_line 模板无 ``{url}`` 占位（如 SMTP）→ G1 显式 N/A。"""
        profile = make_profile()
        profile["raw_format"]["request_line"] = "{method} {argument}"
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])

        outcomes = run_gate("smtp", seed_dir, profile)
        g1 = next(o for o in outcomes if o.gate == "G1")

        assert g1.status == STATUS_NA, g1.summary
        assert g1.details["reason"] == "no_url_field"


# ===========================================================================
# G2 —— 不可播会话占比
# ===========================================================================

class TestG2:
    """G2：种子引用的会话/资源名必须在目标环境的可播清单内。"""

    def _profile_with_playable(self, playable_root):
        """构造 profile + 可播清单文件（清单放在重定向后的 targets_root 下）。"""
        (playable_root / "rtsp" / "playable.json").write_text(
            json.dumps({"playable": _PLAYABLE}), encoding="utf-8")
        return make_profile(playable_resources_file="playable.json")

    def test_detects_unplayable_resource(self, playable_root, tmp_path):
        """合成语料引用了不可播会话 → G2 必须检出。"""
        profile = self._profile_with_playable(playable_root)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])
        write_seed(seed_dir, 2, [f"{_TARGET_URL}vobTest"])      # ← 不可播
        write_seed(seed_dir, 3, [f"{_TARGET_URL}webmFileTest"])

        env_name, env_cfg = resolve_env(profile, {}, "synthetic-env")
        outcomes = run_gate("rtsp", seed_dir, profile,
                            env_name=env_name, env_cfg=env_cfg)
        g2 = next(o for o in outcomes if o.gate == "G2")

        assert g2.status == STATUS_FAIL, g2.summary
        assert g2.blocking is True
        assert g2.details["unplayable_seeds"] == 1
        assert g2.details["checkable_seeds"] == 3
        assert "vobTest" in g2.details["offending_resources"]

    def test_all_playable_passes(self, playable_root, tmp_path):
        """全部引用可播会话 → G2 必须通过。"""
        profile = self._profile_with_playable(playable_root)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])
        write_seed(seed_dir, 2, [f"{_TARGET_URL}webmFileTest"])

        env_name, env_cfg = resolve_env(profile, {}, "synthetic-env")
        outcomes = run_gate("rtsp", seed_dir, profile,
                            env_name=env_name, env_cfg=env_cfg)
        g2 = next(o for o in outcomes if o.gate == "G2")

        assert g2.status == STATUS_PASS, g2.summary
        assert g2.details["unplayable_seeds"] == 0
        assert g2.details["mode"] == "env"

    def test_threshold_is_configurable(self, playable_root, tmp_path):
        """G2 阈值可配置。"""
        profile = self._profile_with_playable(playable_root)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}vobTest"])

        env_name, env_cfg = resolve_env(profile, {}, "synthetic-env")
        outcomes = run_gate("rtsp", seed_dir, profile,
                            env_name=env_name, env_cfg=env_cfg,
                            thresholds=Thresholds(max_unplayable_ratio=1.0))
        g2 = next(o for o in outcomes if o.gate == "G2")

        assert g2.status == STATUS_PASS, g2.summary

    def test_not_applicable_without_playable_list(self, tmp_path):
        """profile 未声明可播清单 → G2 显式 N/A（不静默跳过）。"""
        profile = make_profile(playable_resources_file=None)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}vobTest"])

        outcomes = run_gate("rtsp", seed_dir, profile)
        g2 = next(o for o in outcomes if o.gate == "G2")

        assert g2.status == STATUS_NA, g2.summary
        assert g2.details["reason"] == "no_playable_list"

    def test_cross_check_mode_warns_but_does_not_block(self, playable_root,
                                                        tmp_path):
        """语料未绑定环境 → 交叉校验口径：告警但不阻断。"""
        profile = self._profile_with_playable(playable_root)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}vobTest"])

        outcomes = run_gate("rtsp", seed_dir, profile)
        g2 = next(o for o in outcomes if o.gate == "G2")

        assert g2.status == STATUS_WARN, g2.summary
        assert g2.blocking is False
        assert g2.details["mode"] == "cross-check"

    def test_cross_check_can_be_escalated(self, playable_root, tmp_path):
        """``--escalate-cross-check`` → 交叉校验口径升级为阻断。"""
        profile = self._profile_with_playable(playable_root)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}vobTest"])

        outcomes = run_gate("rtsp", seed_dir, profile,
                            escalate_cross_check=True)
        g2 = next(o for o in outcomes if o.gate == "G2")

        assert g2.status == STATUS_FAIL, g2.summary
        assert g2.blocking is True


# ===========================================================================
# G5 —— 契约一致性（focus_group 条数）
# ===========================================================================

class TestG5:
    """G5：profile 声明的 focus_group.<组>.seeds 必须等于实际生成条数。"""

    def test_contract_mismatch_warns_without_strict(self, tmp_path):
        """条数与契约不符 → 非 strict 模式只告警（不阻断）。"""
        profile = make_profile(focus_group_seeds=5)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])
        write_seed(seed_dir, 2, [f"{_TARGET_URL}webmFileTest"])

        outcomes = run_gate("rtsp", seed_dir, profile, group="B")
        g5 = next(o for o in outcomes if o.gate == "G5")

        assert g5.status == STATUS_WARN, g5.summary
        assert g5.blocking is False
        assert g5.details["expected_effective"] == 5
        assert g5.details["actual"] == 2
        assert g5.details["drift"] is True
        # 必须打印期望 vs 实际
        assert "期望 5" in g5.measured and "实际 2" in g5.measured

    def test_contract_mismatch_blocks_with_strict(self, tmp_path):
        """条数与契约不符 → strict 模式必须失败。"""
        profile = make_profile(focus_group_seeds=5)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])
        write_seed(seed_dir, 2, [f"{_TARGET_URL}webmFileTest"])

        outcomes = run_gate("rtsp", seed_dir, profile, group="B", strict=True)
        g5 = next(o for o in outcomes if o.gate == "G5")

        assert g5.status == STATUS_FAIL, g5.summary
        assert g5.blocking is True

    def test_contract_match_passes(self, tmp_path):
        """条数与契约一致 → 通过（strict 下也通过）。"""
        profile = make_profile(focus_group_seeds=2)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])
        write_seed(seed_dir, 2, [f"{_TARGET_URL}webmFileTest"])

        outcomes = run_gate("rtsp", seed_dir, profile, group="B", strict=True)
        g5 = next(o for o in outcomes if o.gate == "G5")

        assert g5.status == STATUS_PASS, g5.summary
        assert g5.details["drift"] is False

    def test_environment_override_wins(self, tmp_path):
        """环境级 focus_group 覆盖协议级 → 生效契约取环境级（与 seedgen 一致）。"""
        profile = make_profile(focus_group_seeds=50, env_focus_group_seeds=2)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])
        write_seed(seed_dir, 2, [f"{_TARGET_URL}webmFileTest"])

        env_name, env_cfg = resolve_env(profile, {}, "synthetic-env")
        outcomes = run_gate("rtsp", seed_dir, profile, env_name=env_name,
                            env_cfg=env_cfg, group="B", strict=True)
        g5 = next(o for o in outcomes if o.gate == "G5")

        assert g5.status == STATUS_PASS, g5.summary
        assert g5.details["expected_effective"] == 2
        assert g5.details["expected_protocol_level"] == 50

    def test_unknown_group_is_not_applicable(self, tmp_path):
        """无法判定聚焦组 → G5 显式 N/A。"""
        profile = make_profile(focus_group_seeds=5)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])

        outcomes = run_gate("rtsp", seed_dir, profile, group=None)
        g5 = next(o for o in outcomes if o.gate == "G5")

        assert g5.status == STATUS_NA, g5.summary
        assert g5.details["reason"] == "unknown_group"


# ===========================================================================
# 退出码（CI 契约）
# ===========================================================================

class TestExitCode:
    """退出码：0 = 通过；1 = 阻断；2 = 用法/配置错误。"""

    def _write_profile_file(self, tmp_path, profile: dict) -> Path:
        path = tmp_path / "profile.json"
        path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
        return path

    def test_exit_zero_when_all_pass(self, tmp_path):
        profile = make_profile(focus_group_seeds=1)
        profile_path = self._write_profile_file(tmp_path, profile)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(profile_path), "--group", "B"])
        assert code == 0

    def test_exit_one_when_g1_fails(self, tmp_path):
        profile = make_profile(focus_group_seeds=1)
        profile_path = self._write_profile_file(tmp_path, profile)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [_WRONG_URL])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(profile_path), "--group", "B"])
        assert code == 1

    def test_exit_one_when_g5_fails_in_strict(self, tmp_path):
        profile = make_profile(focus_group_seeds=9)
        profile_path = self._write_profile_file(tmp_path, profile)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(profile_path), "--group", "B",
                     "--strict"])
        assert code == 1

    def test_exit_zero_when_g5_drift_without_strict(self, tmp_path):
        """G5 漂移在非 strict 模式下**不阻断**（已知历史漂移，待用户决策）。"""
        profile = make_profile(focus_group_seeds=9)
        profile_path = self._write_profile_file(tmp_path, profile)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(profile_path), "--group", "B"])
        assert code == 0

    def test_exit_two_when_seed_dir_missing(self, tmp_path):
        code = main(["--protocol", "rtsp",
                     "--seed-dir", str(tmp_path / "nope")])
        assert code == 2

    def test_exit_two_when_profile_missing(self, tmp_path):
        profile_path = tmp_path / "missing.json"
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(profile_path)])
        assert code == 2

    def test_exit_two_when_env_name_unknown(self, tmp_path):
        profile = make_profile()
        profile_path = self._write_profile_file(tmp_path, profile)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])

        code = main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
                     "--profile", str(profile_path),
                     "--target-env", "no-such-env"])
        assert code == 2

    def test_json_output_is_machine_readable(self, tmp_path, capsys):
        profile = make_profile(focus_group_seeds=1)
        profile_path = self._write_profile_file(tmp_path, profile)
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])

        main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
              "--profile", str(profile_path), "--group", "B", "--json"])
        payload = json.loads(capsys.readouterr().out)

        assert [g["gate"] for g in payload["gates"]] == ["G1", "G2", "G5"]
        assert payload["blocked"] is False


# ===========================================================================
# 只读性 + 环境/分组解析
# ===========================================================================

class TestReadOnly:
    """闸门是**纯检查项**：不得修改 kb/ / derived/ / fused_hub/ 下任何文件。"""

    def test_gate_does_not_modify_anything(self, tmp_path):
        profile = make_profile(focus_group_seeds=1)
        profile_path = tmp_path / "profile.json"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        seed_dir = tmp_path / "seeds"
        seed = write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])

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
        profile = make_profile(focus_group_seeds=1)
        profile_path = tmp_path / "profile.json"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])

        listing_before = sorted(p.name for p in tmp_path.iterdir())
        main(["--protocol", "rtsp", "--seed-dir", str(seed_dir),
              "--profile", str(profile_path), "--group", "B"])
        listing_after = sorted(p.name for p in tmp_path.iterdir())

        assert listing_before == listing_after


class TestEnvAndGroupResolution:
    """环境/分组解析：数据来源优先级必须稳定。"""

    def test_env_prefers_manifest_over_profile_default(self, tmp_path):
        profile = make_profile()
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])
        (seed_dir / "manifest.json").write_text(
            json.dumps({"seedgen": {"target_env": "synthetic-env"}}),
            encoding="utf-8")

        manifest = read_manifest(seed_dir)
        name, _cfg = resolve_env(profile, manifest)
        assert name == "synthetic-env"

    def test_group_detected_from_manifest(self, tmp_path):
        profile = make_profile()
        seed_dir = tmp_path / "seeds"
        write_seed(seed_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])
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
# 端到端：真实脚本入口
# ===========================================================================

def test_script_runs_as_subprocess_and_returns_exit_code(tmp_path):
    """脚本作为子进程运行：正常语料 → exit 0；污染语料 → exit 1。"""
    profile = make_profile(focus_group_seeds=1)
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    good_dir = tmp_path / "good"
    write_seed(good_dir, 1, [f"{_TARGET_URL}mp3AudioTest"])
    bad_dir = tmp_path / "bad"
    write_seed(bad_dir, 1, [_WRONG_URL])

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


# ===========================================================================
# D2：SIP client_side 端点检查（Via/Contact 承载端点语义）
# ===========================================================================

def _sip_profile_with_client_side() -> dict:
    """构造一份带 ``seedgen.client_side`` 的合成 SIP profile（对齐真实 profile）。"""
    return {
        "protocol": "sip",
        "default_url": "sip:127.0.0.1:5060",
        "raw_format": {
            "line_ending": "\r\n",
            "request_line": "{method} {url} {version}",
            "version": "SIP/2.0",
        },
        "seedgen": {
            "client_side": {
                "server_addr": "127.0.0.1:5060",
                "client_addr": "127.0.0.1:5061",
                "headers": ["Via", "Contact"],
            },
        },
    }


def _write_sip_seed(seed_dir: Path, index: int, r_uri: str,
                    via_host: str = "127.0.0.1:5061",
                    contact_host: str = "127.0.0.1:5061",
                    extra_headers: list[str] | None = None) -> Path:
    """写一条合成 SIP 种子（请求行 R-URI + Via/Contact + 可选额外头）。"""
    seed_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"REGISTER {r_uri} SIP/2.0",
        "CSeq: 1 REGISTER",
        f"Via: SIP/2.0/UDP {via_host};branch=z9hG4bK-test",
        f"Contact: <sip:{contact_host}>",
    ]
    for h in (extra_headers or []):
        lines.append(h)
    lines.append("")
    path = seed_dir / f"{index:02d}_SYNTH.raw"
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return path


def test_sip_client_side_g1_applicable_and_passes_loopback(tmp_path):
    """★ D2：带 client_side 的 SIP → G1 适用（不再 N/A），全回环 → PASS。"""
    profile = _sip_profile_with_client_side()
    seed_dir = tmp_path / "seeds"
    _write_sip_seed(seed_dir, 1, "sip:127.0.0.1:5060")

    outcomes = run_gate("sip", seed_dir, profile)
    g1 = next(o for o in outcomes if o.gate == "G1")

    assert g1.status == STATUS_PASS, g1.summary
    assert g1.details["applicable"] is True
    assert g1.details["endpoint_kind"] == "client_side"


def test_sip_client_side_g1_detects_foreign_host(tmp_path):
    """★ D2 的核心价值：SIP 语料 R-URI 指向外来主机 → G1 必须 FAIL。"""
    profile = _sip_profile_with_client_side()
    seed_dir = tmp_path / "seeds"
    # 外来主机（SIP traffic 源实测含 213.192.59.75 这类非目标设备）
    _write_sip_seed(seed_dir, 1, "sip:213.192.59.75")

    outcomes = run_gate("sip", seed_dir, profile)
    g1 = next(o for o in outcomes if o.gate == "G1")

    assert g1.status == STATUS_FAIL, g1.summary
    assert "213.192.59.75" in g1.details["offending_hosts"]


def test_sip_client_side_excludes_callid_and_branch(tmp_path):
    """★ D2 不误报：Call-ID 里的 IP、branch= 随机串里的 IP 不承载端点语义。"""
    profile = _sip_profile_with_client_side()
    seed_dir = tmp_path / "seeds"
    # Call-ID 含 192.168.1.2；branch 随机串含 192.168.1.2 —— 都不该判错主机
    _write_sip_seed(
        seed_dir, 1, "sip:127.0.0.1:5060",
        extra_headers=[
            "Call-ID: 105090259-446faf7a@192.168.1.2",
            'From: "arik" <sip:35104723@sip.cybercity.dk>;tag=1',
            "To: <sip:0097239287044@sip.cybercity.dk>",
        ])

    outcomes = run_gate("sip", seed_dir, profile)
    g1 = next(o for o in outcomes if o.gate == "G1")

    assert g1.status == STATUS_PASS, g1.summary
    assert not g1.details.get("offending_hosts")


def test_sip_without_client_side_still_not_applicable(tmp_path):
    """无 client_side 的 SIP（opaque URI）仍应 N/A（不回归到旧行为）。"""
    profile = {
        "protocol": "sip",
        "default_url": "sip:127.0.0.1:5060",
        "raw_format": {
            "line_ending": "\r\n",
            "request_line": "{method} {url} {version}",
            "version": "SIP/2.0",
        },
    }
    seed_dir = tmp_path / "seeds"
    _write_sip_seed(seed_dir, 1, "sip:alice@sip.cybercity.dk")

    outcomes = run_gate("sip", seed_dir, profile)
    g1 = next(o for o in outcomes if o.gate == "G1")
    assert g1.status == STATUS_NA, g1.summary
