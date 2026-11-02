# -*- coding: utf-8 -*-
"""tests/fused/test_corpus_gate_ratio.py —— G2 **比率口径** + 分层统计 + G5 scope 标签。

★ 为什么要有比率口径（QA 的 F-4 修正）：
  ``violation_count`` 是**绝对配对计数**、**不是比率** ⇒ 基准层本就有 N 条
  不可播会话时，追加一批**全部可播**的 ⑤ 种子 ⇒ 绝对数**持平**（看着像「没改善」）
  ⇒ 但**比率**会明显下降（分母变大、分子不变）。
  ⇒ 闸门必须**同时**给出绝对数与比率，并**按层拆分**（基准层 / ⑤ 变异层），
    这样「⑤ 的贡献」在闸门报告里**直接可见**。

★ P2-7：G5 的 ``scope`` 标签必须与 ``actual`` 的**实际口径**一致
  （原实现在「manifest 有 entries 但 layer 全空」时 actual 用**总数**、
  scope 却写成 ``base-layers-only`` ⇒ 标签与口径矛盾）。
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.corpus_gate import check_g2, check_g5

ROOT = Path(__file__).resolve().parents[2]


def _rtsp_profile() -> dict:
    return json.loads((ROOT / "fused_hub" / "targets" / "rtsp" / "profile.json")
                      .read_text(encoding="utf-8"))


def _seed_text(session: str) -> str:
    return (f"SETUP rtsp://127.0.0.1:8554/{session}/track1 RTSP/1.0\r\n"
            f"CSeq: 1\r\n\r\n")


def _manifest(layers: list[str]) -> dict:
    return {"seeds": [{"filename": f"{i:02d}_s.raw", "layer": lay}
                      for i, lay in enumerate(layers, start=1)]}


class TestG2RatioAndLayers:
    """★ G2 的比率口径与分层统计。"""

    def _run(self, sessions: list[str], layers: list[str]):
        profile = _rtsp_profile()
        env_cfg = ((profile.get("seedgen") or {}).get("environments")
                   or {}).get("rq2-live555") or {}
        texts = [(Path(f"{i:02d}_s.raw"), _seed_text(s))
                 for i, s in enumerate(sessions, start=1)]
        return check_g2(profile, "rtsp", texts, env_cfg, 0,
                        manifest=_manifest(layers))

    def test_ratio_is_reported(self):
        """★ 比率字段必须存在且等于 违规数/种子数。"""
        res = self._run(["mpeg1or2AudioVideoTest", "vobTest"], ["L1", "L1"])
        assert "violation_ratio" in res
        assert res["seed_count"] == 2
        assert res["violation_count"] == 1
        assert abs(res["violation_ratio"] - 0.5) < 1e-6

    def test_by_layer_splits_base_and_mutation(self):
        """★ 分层统计：⑤ 层与基准层的违规数必须分开记。"""
        res = self._run(["vobTest", "mpeg1or2AudioVideoTest"], ["L1", "L5"])
        by = res["by_layer"]
        assert by["base"]["seed_count"] == 1
        assert by["base"]["violation_count"] == 1
        assert by["mutation"]["seed_count"] == 1
        assert by["mutation"]["violation_count"] == 0, \
            "⑤ 层（全可播）不得有违规"
        assert by["mutation"]["violation_ratio"] == 0.0

    def test_mutation_layer_can_carry_violations(self):
        """⑤ 层若**也**引用了不可播会话，必须被**如实记进**⑤ 层。"""
        res = self._run(["vobTest", "oggFileTest"], ["L5", "L5"])
        assert res["by_layer"]["mutation"]["violation_count"] == 2

    def test_ratio_drops_when_only_playable_seeds_are_added(self):
        """★ 绝对数持平、比率下降 —— 这正是「36%→87%」在比率口径下的形态。"""
        base = self._run(["vobTest", "mpeg1or2AudioVideoTest"], ["L1", "L1"])
        both = self._run(["vobTest", "mpeg1or2AudioVideoTest",
                          "mp3AudioTest"], ["L1", "L1", "L5"])
        assert base["violation_count"] == both["violation_count"], \
            "绝对数应持平"
        assert both["violation_ratio"] < base["violation_ratio"], \
            "比率应下降（分母变大、分子不变）"

    def test_no_manifest_still_reports_ratio(self):
        """★ 无 manifest（回退口径）⇒ 比率仍须可用（分层退化为全算基准层）。"""
        profile = _rtsp_profile()
        env_cfg = ((profile.get("seedgen") or {}).get("environments")
                   or {}).get("rq2-live555") or {}
        texts = [(Path("01_s.raw"), _seed_text("vobTest"))]
        res = check_g2(profile, "rtsp", texts, env_cfg, 0, manifest=None)
        assert res["violation_ratio"] == 1.0
        assert res["by_layer"]["base"]["seed_count"] == 1


class TestG5ScopeConsistency:
    """★ P2-7：``scope`` 标签必须与 ``actual`` 的口径一致。"""

    def _run(self, manifest, seed_count: int):
        profile = _rtsp_profile()
        files = [Path(f"f{i}.raw") for i in range(seed_count)]
        return check_g5(profile, "rtsp", "B", files, manifest, "rq2-live555",
                        strict=False)

    def test_scope_all_seeds_when_no_layer_info(self):
        """manifest 缺失 ⇒ 口径是**总数** ⇒ scope 必须是 ``all-seeds``。"""
        res = self._run(None, 5)
        assert res["actual"] == 5
        assert res["scope"] == "all-seeds"

    def test_scope_all_seeds_when_layers_all_blank(self):
        """★ P2-7：entries 存在但 layer 全空 ⇒ 口径是**总数** ⇒ 标签不得写基准层。"""
        res = self._run({"seeds": [{"filename": "a.raw", "layer": ""},
                                   {"filename": "b.raw", "layer": ""}]}, 2)
        assert res["actual"] == 2, "回退口径应算总数"
        assert res["scope"] == "all-seeds", \
            f"scope 必须与 actual 口径一致，实际 {res['scope']!r}"

    def test_scope_base_layers_only_when_layer_info_present(self):
        """layer 信息齐全 ⇒ 口径是**基准层** ⇒ scope = ``base-layers-only``。"""
        res = self._run({"seeds": [{"filename": "a.raw", "layer": "L1"},
                                   {"filename": "b.raw", "layer": "L5"}]}, 2)
        assert res["actual"] == 1, "基准层条数 = 总数 - ⑤ 层"
        assert res["scope"] == "base-layers-only"
        assert res["mutation_count"] == 1
