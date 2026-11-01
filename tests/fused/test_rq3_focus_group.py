# -*- coding: utf-8 -*-
"""tests/fused/test_rq3_focus_group.py —— seedgen 分组开关的行为契约。

固化 RQ3「种子聚焦」消融实验的核心不变式：

  · **向后兼容**：不加任何新开关时，输出与改造前**逐字节一致**
    （种子 50 条 + MD5 集合逐条相等 + 字典逐字节相等 + 不产出 manifest.json）
  · 四组配置：A=38 / B=50 / C=50 / D=50；B/C/D 的 MD5 集合相等
  · C 组字典是 base24 的**严格超集**（D→C 单变量的前提）
  · `--focus-group` 与任一原子开关**互斥**（退出码 2）
  · **不砍种子、不复制种子**（铁律）
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.fused.downstream.rag_seedgen import (  # noqa: E402
    load_fact_views, assemble_bundle, write_seeds, plan_seed_filenames,
)
from core.fused.downstream.selector import (  # noqa: E402
    dedupe_seeds, prioritize_seeds,
)
from core.fused.downstream.edge_cover import edge_cover  # noqa: E402
from core.fused.downstream.generic_danger import generic_danger  # noqa: E402
from scripts.seedgen import (  # noqa: E402
    FOCUS_GROUP_CONFIG, ALL_LAYERS, _resolve_config, _load_profile,
    _load_resources, _derive_vuln_boundary_candidates, _build_canonical_seed,
)
from core.models import SeedCorpus  # noqa: E402

#: 历史上用于 RQ1.2 的 ProtoRAG 语料（C 组与其 MD5 集合必须相等）
REFERENCE = ROOT / "derived" / "seeds" / "rtsp" / "live555_20261024_110155"

#: 镜像内基础字典的仓库内副本
BASE_DICT = ROOT / "fused_hub" / "targets" / "rtsp" / "rtsp_base.dict"

#: 镜像内基础字典的 MD5（实测值）
BASE_DICT_MD5 = "464351f88db6c3f0bdac0de01859316b"


# ===========================================================================
# 工具
# ===========================================================================

def _md5s(directory: Path) -> set[str]:
    """目录下所有 .raw 的 MD5 集合。"""
    return {hashlib.md5(f.read_bytes()).hexdigest()
            for f in sorted(directory.glob("*.raw"))}


def _md5_map(directory: Path) -> dict[str, str]:
    """目录下所有 .raw 的 `{文件名: MD5}`。"""
    return {f.name: hashlib.md5(f.read_bytes()).hexdigest()
            for f in sorted(directory.glob("*.raw"))}


def _seedgen(*args: str) -> subprocess.CompletedProcess:
    """调用 scripts/seedgen.py（子进程）。"""
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seedgen.py"), *args],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace")


class _Args:
    """_resolve_config 的最小参数替身。"""

    def __init__(self, **kw):
        self.layers = None
        self.no_vuln_boundary = False
        self.order = None
        self.no_sort = False
        self.dict = None
        self.dict_path = None
        self.focus_group = None
        self.focused = False
        self.max_seeds = None
        for k, v in kw.items():
            setattr(self, k, v)


def _build_seeds(protocol: str = "rtsp", layers=None) -> list:
    """按层组合生成种子（与 seedgen.main 的层逻辑一致）。"""
    layers = layers or list(ALL_LAYERS)
    profile = _load_profile(protocol)
    bundle = assemble_bundle(load_fact_views(protocol))
    transitions = bundle["transitions"]
    seeds: list = []
    if "edge_cover" in layers:
        seeds += edge_cover(transitions, bundle.get("required_headers"),
                            bundle.get("headers"),
                            bundle.get("message_instances"), protocol=protocol,
                            method_order=bundle.get("method_order"))
    if "generic_danger" in layers:
        seeds += generic_danger(transitions, bundle.get("headers"),
                                bundle.get("required_headers"), minimal=False,
                                precondition=bundle.get("precondition"),
                                session_header=bundle.get("session_header"),
                                message_instances=bundle.get("message_instances"),
                                protocol=protocol)
    if "vuln_boundary" in layers:
        seeds += _derive_vuln_boundary_candidates(bundle, profile, protocol)
    if "canonical" in layers:
        flow = (profile.get("seedgen") or {}).get("canonical_flow")
        if flow:
            c = _build_canonical_seed(bundle, flow, protocol)
            if c is not None:
                seeds.append(c)
    return seeds


# ===========================================================================
# 配置契约
# ===========================================================================

def test_focus_group_config_shape():
    """四组配置表的层组合 / 顺序 / 字典种类符合技术方案 §2.2。"""
    assert set(FOCUS_GROUP_CONFIG) == {"A", "B", "C", "D"}
    # A 不含③漏洞边界层
    assert "vuln_boundary" not in FOCUS_GROUP_CONFIG["A"]["layers"]
    assert set(FOCUS_GROUP_CONFIG["A"]["layers"]) == {
        "edge_cover", "generic_danger", "canonical"}
    # B/C/D 都含全部四层
    for g in ("B", "C", "D"):
        assert set(FOCUS_GROUP_CONFIG[g]["layers"]) == set(ALL_LAYERS)
    # 顺序：A/B 自然序，C/D 漏洞接近度序
    assert FOCUS_GROUP_CONFIG["A"]["order"] == "natural"
    assert FOCUS_GROUP_CONFIG["B"]["order"] == "natural"
    assert FOCUS_GROUP_CONFIG["C"]["order"] == "vuln-proximity"
    assert FOCUS_GROUP_CONFIG["D"]["order"] == "vuln-proximity"
    # 字典：A/B/D 基础字典，C 定向字典
    for g in ("A", "B", "D"):
        assert FOCUS_GROUP_CONFIG[g]["dict_kind"] == "base"
    assert FOCUS_GROUP_CONFIG["C"]["dict_kind"] == "targeted"
    # 期望条数
    assert FOCUS_GROUP_CONFIG["A"]["expect_seeds"] == 38
    for g in ("B", "C", "D"):
        assert FOCUS_GROUP_CONFIG[g]["expect_seeds"] == 50


def test_resolve_config_focus_groups():
    """--focus-group 展开为配置（不与原子开关混用）。"""
    for g in ("A", "B", "C", "D"):
        cfg, err = _resolve_config(_Args(focus_group=g))
        assert err is None
        assert cfg["focus_group"] == g
        assert cfg["layers"] == FOCUS_GROUP_CONFIG[g]["layers"]
        assert cfg["order"] == FOCUS_GROUP_CONFIG[g]["order"]
        assert cfg["dict_kind"] == FOCUS_GROUP_CONFIG[g]["dict_kind"]


@pytest.mark.parametrize("kwargs", [
    {"focus_group": "B", "no_sort": True},
    {"focus_group": "B", "no_vuln_boundary": True},
    {"focus_group": "B", "order": "natural"},
    {"focus_group": "B", "layers": "edge_cover"},
    {"focus_group": "B", "dict": "base"},
    {"focus_group": "B", "dict_path": "/tmp/x.dict"},
    {"focus_group": "B", "focused": True},
    {"focus_group": "B", "max_seeds": 10},
])
def test_resolve_config_mutual_exclusion(kwargs):
    """--focus-group 与原子开关互斥 → 返回错误（调用方以退出码 2 退出）。"""
    cfg, err = _resolve_config(_Args(**kwargs))
    assert cfg is None
    assert err and "互斥" in err


def test_resolve_config_atomic_switches():
    """原子开关的语义：层集合 / 顺序 / 字典种类。"""
    cfg, err = _resolve_config(_Args(no_vuln_boundary=True))
    assert err is None
    assert "vuln_boundary" not in cfg["layers"]
    assert cfg["order"] == "vuln-proximity"
    assert cfg["dict_kind"] == "protocol"

    cfg, err = _resolve_config(_Args(no_sort=True))
    assert err is None and cfg["order"] == "natural"

    cfg, err = _resolve_config(_Args(order="natural"))
    assert err is None and cfg["order"] == "natural"

    cfg, err = _resolve_config(_Args(layers="edge_cover,canonical"))
    assert err is None
    assert cfg["layers"] == ["edge_cover", "canonical"]

    cfg, err = _resolve_config(_Args(dict="targeted"))
    assert err is None and cfg["dict_kind"] == "targeted"

    cfg, err = _resolve_config(_Args(layers="bogus_layer"))
    assert cfg is None and "未知层" in err


# ===========================================================================
# 向后兼容（硬门槛）
# ===========================================================================

def test_default_output_unchanged(tmp_path):
    """★ 向后兼容回归：默认输出与历史产物逐字节一致（种子 + 字典）。"""
    if not REFERENCE.exists():
        pytest.skip("历史参考语料不存在")
    out = tmp_path / "reg"
    r = _seedgen("--protocol", "rtsp", "--danger", "--out", str(out))
    assert r.returncode == 0, r.stderr

    # 种子 50 条
    assert len(list(out.glob("*.raw"))) == 50
    # MD5 集合逐条相等
    assert _md5s(out) == _md5s(REFERENCE)
    # 文件名序列也相等（顺序未变）
    assert list(_md5_map(out)) == list(_md5_map(REFERENCE))
    # 字典逐字节相等
    assert (out / "rtsp.dict").read_bytes() == \
        (REFERENCE / "rtsp.dict").read_bytes()
    # 默认不产出 manifest.json
    assert not (out / "manifest.json").exists()


def test_default_dict_is_102_tokens(tmp_path):
    """默认字典仍是现状的 102 token（未变成定向字典）。"""
    out = tmp_path / "d"
    r = _seedgen("--protocol", "rtsp", "--danger", "--out", str(out))
    assert r.returncode == 0, r.stderr
    toks = [ln for ln in (out / "rtsp.dict").read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    assert len(toks) == 102


def test_base_dict_matches_image_md5():
    """仓库内基础字典副本与镜像内 rtsp.dict 逐字节相同（MD5 锁定）。"""
    assert BASE_DICT.exists()
    assert hashlib.md5(BASE_DICT.read_bytes()).hexdigest() == BASE_DICT_MD5


# ===========================================================================
# 四组行为
# ===========================================================================

@pytest.mark.parametrize("group,expect", [("A", 38), ("B", 50), ("C", 50),
                                           ("D", 50)])
def test_focus_group_seed_count(tmp_path, group, expect):
    """四组的种子条数：A=38 / B=50 / C=50 / D=50。"""
    out = tmp_path / group
    r = _seedgen("--protocol", "rtsp", "--focus-group", group,
                 "--out", str(out), "--manifest")
    assert r.returncode == 0, r.stderr
    assert len(list(out.glob("*.raw"))) == expect


#: 各协议聚焦组标定基准（种子数 + 字典 token 数，来自 profile.seedgen.focus_group）
_PROTOCOL_CALIBRATION = {
    "ftp":  {"A": (29, 32), "B": (29, 32), "C": (29, 49), "D": (29, 32)},
    "sip":  {"A": (15, 163), "B": (25, 163), "C": (25, 167), "D": (25, 163)},
    "smtp": {"A": (76, 24), "B": (78, 24), "C": (78, 25), "D": (78, 24)},
}

#: 目标环境（target environment）下的聚焦组标定基准。
#:
#: 环境级约束会改变种子内容（RTSP：目标环境只有 7 个媒体文件 → 只用 7 个可播会话；
#: SIP：AFLNet 分区器只认 4 个方法作消息起点 → 种子只用这 4 个方法构造），
#: 因此条数与字典 token 数都与「无环境约束」的默认标定不同。
#:
#: 来源：profile.seedgen.environments.<env>.focus_group（环境级标定优先于协议级）。
_TARGET_ENV_CALIBRATION = {
    ("rtsp", "rq2-live555"): {
        "A": (27, 24), "B": (39, 24), "C": (39, 114), "D": (39, 24),
    },
    ("sip", "rq2-kamailio"): {
        "A": (15, 163), "B": (25, 163), "C": (25, 167), "D": (25, 163),
    },
}


@pytest.mark.parametrize("protocol", ["ftp", "sip", "smtp"])
def test_focus_group_protocol_calibration(tmp_path, protocol):
    """★ 非 RTSP 协议走 profile 的协议级标定（不再硬套 RTSP 的 38/50）。

    每个协议 A/B/C/D 四组都能正常生成（退出码 0），且种子数与字典 token 数
    与 profile.seedgen.focus_group 的标定值一致。
    """
    for g, (seeds, dtok) in _PROTOCOL_CALIBRATION[protocol].items():
        out = tmp_path / f"{protocol}_{g}"
        r = _seedgen("--protocol", protocol, "--focus-group", g,
                     "--out", str(out))
        assert r.returncode == 0, f"{protocol}/{g}: {r.stderr}"
        assert len(list(out.glob("*.raw"))) == seeds, f"{protocol}/{g} 种子数"
        dict_file = out / f"{protocol}.dict"
        toks = [ln for ln in dict_file.read_text(encoding="utf-8").splitlines()
                if ln.strip()]
        assert len(toks) == dtok, f"{protocol}/{g} 字典 token 数"


def test_focus_group_profile_override_dict_kind():
    """协议级标定可覆盖 dict_kind：sip/smtp 的 A/B/D 用 protocol（无 base 字典）。"""
    profile = _load_profile("sip")
    fg = (profile.get("seedgen") or {}).get("focus_group")
    assert fg is not None
    assert fg["A"]["dict"] == "protocol"
    assert fg["B"]["dict"] == "protocol"
    assert fg["D"]["dict"] == "protocol"
    assert fg["C"]["dict"] == "targeted"


# ===========================================================================
# 目标环境（target environment）—— RQ4 实验前的两个阻断级种子缺陷修复
# ===========================================================================

@pytest.mark.parametrize("protocol,env", [("rtsp", "rq2-live555"),
                                          ("sip", "rq2-kamailio")])
def test_target_env_calibration(tmp_path, protocol, env):
    """★ 目标环境下的聚焦组标定（环境级标定优先于协议级）。

    环境级约束（RTSP 可播会话子集 / SIP 消息起点方法）改变了种子内容，
    因此条数与字典 token 数都与默认标定不同——标定值来自
    profile.seedgen.environments.<env>.focus_group。
    """
    for g, (seeds, dtok) in _TARGET_ENV_CALIBRATION[(protocol, env)].items():
        out = tmp_path / f"{protocol}_{env}_{g}"
        r = _seedgen("--protocol", protocol, "--focus-group", g,
                     "--target-env", env, "--out", str(out))
        assert r.returncode == 0, f"{protocol}/{env}/{g}: {r.stderr}"
        assert len(list(out.glob("*.raw"))) == seeds, \
            f"{protocol}/{env}/{g} 种子数"
        dict_file = out / f"{protocol}.dict"
        toks = [ln for ln in dict_file.read_text(encoding="utf-8").splitlines()
                if ln.strip()]
        assert len(toks) == dtok, f"{protocol}/{env}/{g} 字典 token 数"


def test_rtsp_target_env_only_uses_playable_sessions(tmp_path):
    """★ 缺陷 1 修复：RTSP 种子只引用目标环境**实际可播**的会话。

    回归背景：rq2-live555:latest 镜像的 live/testProgs/ 只有 7 个媒体文件，
    源码级清单里的另外 11 个会话服务端一律返 404（实测 47.9% 的状态变更请求打空）。
    修复后生成的种子不得再引用那些不可播的会话。
    """
    out = tmp_path / "rtsp_env"
    r = _seedgen("--protocol", "rtsp", "--focus-group", "B",
                 "--target-env", "rq2-live555", "--out", str(out))
    assert r.returncode == 0, r.stderr

    # 该环境可播的会话（来自 profile 声明的可播清单，非硬编码）
    from core.fused.downstream.target_env import playable_resource_names
    profile = _load_profile("rtsp")
    env_cfg = (profile.get("seedgen") or {}).get("environments", {})["rq2-live555"]
    playable = set(playable_resource_names(profile, "rtsp", env_cfg))
    assert playable, "可播清单不应为空"

    # 源码级清单（保留 18 个实例级知识，不受环境约束影响）
    from scripts.seedgen import _load_resources
    declared = set(_load_resources(profile, "rtsp"))
    assert len(declared) == 18, "源码级资源清单不应被环境约束改动"

    # 种子 URL 里出现的会话名必须全部可播
    seen: set = set()
    for raw in out.glob("*.raw"):
        text = raw.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if not line.startswith(("GET ", "DESCRIBE ", "SETUP ", "PLAY ",
                                    "PAUSE ", "TEARDOWN ", "OPTIONS ",
                                    "GET_PARAMETER ", "SET_PARAMETER ")):
                continue
            url = line.split(" ")[1] if " " in line else ""
            name = url.rstrip("/").split("/")[-1]
            if name.startswith("track"):
                name = url.rstrip("/").split("/")[-2]
            seen.add(name)
    assert seen, "未解析出任何会话名（种子格式变化？）"
    unplayable = seen - playable
    assert not unplayable, f"种子引用了目标环境不可播的会话: {sorted(unplayable)}"


def test_sip_target_env_only_boundary_methods_start_messages(tmp_path):
    """★ 缺陷 2 修复：SIP 种子的每条消息都以 AFLNet 识别的方法开头。

    回归背景：AFLNet 的 extract_requests_sip 只把 REGISTER/INVITE/ACK/BYE 识别为
    新消息起点，其余方法开头的消息会被并入前一条消息 → 消息边界被破坏。
    """
    out = tmp_path / "sip_env"
    r = _seedgen("--protocol", "sip", "--focus-group", "B",
                 "--target-env", "rq2-kamailio", "--out", str(out))
    assert r.returncode == 0, r.stderr

    profile = _load_profile("sip")
    env_cfg = (profile.get("seedgen") or {}).get("environments", {})["rq2-kamailio"]
    allowed = {m.upper() for m in (profile.get("seedgen") or {})["message_boundary_methods"]}
    assert allowed

    starts: set = set()
    for raw in out.glob("*.raw"):
        text = raw.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if " " not in line:
                continue
            method = line.split(" ", 1)[0].strip().upper()
            if method.isalpha() and method in {
                    "REGISTER", "INVITE", "ACK", "BYE", "CANCEL", "OPTIONS",
                    "SUBSCRIBE", "NOTIFY", "PUBLISH", "INFO", "REFER",
                    "MESSAGE", "PRACK", "UPDATE"}:
                starts.add(method)
    assert starts, "未解析出任何消息起点（种子格式变化？）"
    bad = starts - allowed
    assert not bad, f"种子含不被 AFLNet 识别为消息起点的方法: {sorted(bad)}"


def test_sip_excluded_methods_kept_as_state_machine_edges():
    """★ 知识保留：被排除的方法仍是状态机的边（不丢弃）。

    区分「状态机的边」与「消息起点」：OPTIONS/SUBSCRIBE/... 仍是合法的协议方法、
    仍是 bundle['transitions'] 里的一条边、仍进变异字典——只是不作为消息起点。
    """
    from core.fused.downstream.rag_seedgen import (
        load_fact_views, assemble_bundle,
    )
    bundle = assemble_bundle(load_fact_views("sip"))
    methods = {t[1] for t in bundle["transitions"]}
    for m in ("OPTIONS", "SUBSCRIBE", "PUBLISH", "CANCEL"):
        assert m in methods, f"{m} 应仍作为状态机边保留（知识保留）"

    # 但构造种子时它们不作为消息起点
    from core.fused.downstream.target_env import filter_transitions_by_boundary
    kept = filter_transitions_by_boundary(bundle["transitions"],
                                          ["REGISTER", "INVITE", "ACK", "BYE"])
    kept_methods = {t[1] for t in kept}
    assert "OPTIONS" not in kept_methods
    assert "REGISTER" in kept_methods
    # 过滤只影响构造视图，原始状态机不被修改
    assert len(bundle["transitions"]) > len(kept)


def test_default_path_unchanged_without_target_env(tmp_path):
    """★ 未选目标环境 → 不施加环境级约束（历史语料仍可逐字节复现）。

    这是「向后兼容」不变式的一部分：默认路径的行为与引入目标环境概念之前一致，
    RQ1.2/RQ3 历史语料的 MD5 集合不变。
    """
    out_a = tmp_path / "default"
    r = _seedgen("--protocol", "rtsp", "--focus-group", "B", "--out", str(out_a))
    assert r.returncode == 0, r.stderr
    assert len(list(out_a.glob("*.raw"))) == 50, "默认路径条数应保持 50"

    # 选目标环境 → 条数变化（可播会话子集生效）
    out_b = tmp_path / "env"
    r2 = _seedgen("--protocol", "rtsp", "--focus-group", "B",
                  "--target-env", "rq2-live555", "--out", str(out_b))
    assert r2.returncode == 0, r2.stderr
    assert len(list(out_b.glob("*.raw"))) == 39


def test_unknown_target_env_fails_fast(tmp_path):
    """★ 未知目标环境名 → 显式失败（退出码 2），不静默回退。"""
    r = _seedgen("--protocol", "rtsp", "--focus-group", "B",
                 "--target-env", "no-such-env", "--out", str(tmp_path / "x"))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "未知的目标环境" in (r.stdout + r.stderr)


def test_focus_group_a_is_prefix_of_b(tmp_path):
    """A 的 38 条与 B 的前 38 条逐字节相同（★ 仅自然序成立）。"""
    out_a, out_b = tmp_path / "A", tmp_path / "B"
    assert _seedgen("--protocol", "rtsp", "--focus-group", "A",
                     "--out", str(out_a)).returncode == 0
    assert _seedgen("--protocol", "rtsp", "--focus-group", "B",
                     "--out", str(out_b)).returncode == 0
    ma = _md5_map(out_a)
    mb = _md5_map(out_b)
    names_a = list(ma)
    names_b = list(mb)
    assert len(names_a) == 38
    assert names_a == names_b[:38]
    assert [ma[n] for n in names_a] == [mb[n] for n in names_b[:38]]


def test_focus_group_bcd_same_md5_set(tmp_path):
    """B / C / D 的 MD5 集合相等（仅顺序与字典不同）。"""
    outs = {}
    for g in ("B", "C", "D"):
        outs[g] = tmp_path / g
        assert _seedgen("--protocol", "rtsp", "--focus-group", g,
                         "--out", str(outs[g])).returncode == 0
    sb, sc, sd = (_md5s(outs[g]) for g in ("B", "C", "D"))
    assert sb == sc == sd
    assert len(sb) == 50


def test_focus_group_c_matches_rq12_corpus(tmp_path):
    """C 组的 MD5 集合 == RQ1.2 protorag 语料（连续性）。"""
    if not REFERENCE.exists():
        pytest.skip("历史参考语料不存在")
    out = tmp_path / "C"
    assert _seedgen("--protocol", "rtsp", "--focus-group", "C",
                     "--out", str(out)).returncode == 0
    assert _md5s(out) == _md5s(REFERENCE)


def test_focus_group_no_seed_duplication(tmp_path):
    """★ 铁律：组内 MD5 唯一（不复制同一条种子来「加权」）。"""
    for g, expect in (("A", 38), ("B", 50), ("C", 50), ("D", 50)):
        out = tmp_path / g
        assert _seedgen("--protocol", "rtsp", "--focus-group", g,
                         "--out", str(out)).returncode == 0
        m = _md5_map(out)
        assert len(m) == expect
        assert len(set(m.values())) == expect


def test_focus_group_a_has_no_vuln_boundary_layer(tmp_path):
    """A 组不含③漏洞边界层（其种子全部不是 boundary-probe 生成）。"""
    out = tmp_path / "A"
    assert _seedgen("--protocol", "rtsp", "--focus-group", "A",
                     "--out", str(out), "--manifest").returncode == 0
    manifest = json.loads((tmp_path / "A" / "manifest.json")
                          .read_text(encoding="utf-8"))
    assert manifest["seed_count"] == 38
    assert all(s["layer"] != "L3" for s in manifest["seeds"])
    assert all("boundary-probe" not in s["generated_by"]
               for s in manifest["seeds"])


def test_focus_group_bcd_have_vuln_boundary_layer(tmp_path):
    """B/C/D 含③漏洞边界层（L3）。"""
    for g in ("B", "C", "D"):
        out = tmp_path / g
        assert _seedgen("--protocol", "rtsp", "--focus-group", g,
                         "--out", str(out), "--manifest").returncode == 0
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        n_l3 = sum(1 for s in manifest["seeds"] if s["layer"] == "L3")
        assert n_l3 > 0, f"组 {g} 应含③层种子"


def test_focus_group_order_natural_vs_proximity(tmp_path):
    """natural 组保持生成序；vuln-proximity 组按漏洞接近度降序。"""
    out_b = tmp_path / "B"
    out_c = tmp_path / "C"
    assert _seedgen("--protocol", "rtsp", "--focus-group", "B",
                     "--out", str(out_b), "--manifest").returncode == 0
    assert _seedgen("--protocol", "rtsp", "--focus-group", "C",
                     "--out", str(out_c), "--manifest").returncode == 0
    mb = json.loads((out_b / "manifest.json").read_text(encoding="utf-8"))
    mc = json.loads((out_c / "manifest.json").read_text(encoding="utf-8"))
    scores_b = [s["score"] for s in mb["seeds"]]
    scores_c = [s["score"] for s in mc["seeds"]]
    assert scores_b != sorted(scores_b, reverse=True), "B 应为自然序（非降序）"
    assert scores_c == sorted(scores_c, reverse=True), "C 应为漏洞接近度降序"


def test_focus_group_score_histogram(tmp_path):
    """排序后 B/C/D 的 score 直方图 == {100:3, 95:3, 85:6, 60:15, 20:5, 10:18}。"""
    out = tmp_path / "C"
    assert _seedgen("--protocol", "rtsp", "--focus-group", "C",
                     "--out", str(out), "--manifest").returncode == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    hist: dict = {}
    for s in manifest["seeds"]:
        hist[s["score"]] = hist.get(s["score"], 0) + 1
    assert hist == {100: 3, 95: 3, 85: 6, 60: 15, 20: 5, 10: 18}


# ===========================================================================
# CLI 退出码
# ===========================================================================

@pytest.mark.parametrize("extra", [
    ["--no-sort"],
    ["--focused"],
    ["--max-seeds", "10"],
    ["--layers", "edge_cover"],
    ["--dict", "base"],
])
def test_cli_mutual_exclusion_exit_code_2(tmp_path, extra):
    """互斥组合 → 退出码 2（不是 0，也不是 1）。"""
    out = tmp_path / "x"
    r = _seedgen("--protocol", "rtsp", "--focus-group", "B",
                 "--out", str(out), *extra)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "互斥" in (r.stdout + r.stderr)


def test_cli_unknown_focus_group():
    """非法组名 → argparse 退出码 2。"""
    r = _seedgen("--protocol", "rtsp", "--focus-group", "Z")
    assert r.returncode == 2


# ===========================================================================
# plan_seed_filenames
# ===========================================================================

def test_plan_seed_filenames_width_two_for_small():
    """种子数 ≤ 99 时前缀宽度恒为 2（与历史产物逐字节一致）。"""
    seeds = _build_seeds()
    names = plan_seed_filenames(seeds)
    assert all(n[:2].isdigit() for n in names)
    assert names[0].startswith("01_")
    assert names[-1].startswith(f"{len(seeds):02d}_")


def test_plan_seed_filenames_width_adapts_over_99():
    """★ 种子数 > 99 时前缀宽度自适应（保证字母序 == 数值序）。"""
    dummy = SeedCorpus(protocol="rtsp", description="d",
                        target_methods=["DESCRIBE"], generated_by="x")
    names = plan_seed_filenames([dummy] * 150)
    assert names[0].startswith("001_")
    assert names[-1].startswith("150_")
    # 前缀宽度一致 → 字母序 == 数值序
    prefixes = [n[:3] for n in names]
    assert prefixes == sorted(prefixes)


def test_write_seeds_matches_plan(tmp_path):
    """write_seeds 的实际文件名与 plan_seed_filenames 完全一致（零漂移）。"""
    seeds = _build_seeds()
    written = write_seeds(seeds, tmp_path)
    planned = plan_seed_filenames(seeds)
    assert written == planned
