# -*- coding: utf-8 -*-
"""scripts/rq3_build_corpus.py —— RQ3 四组语料组装 + 一致性断言 + 字典冻结。

职责（技术方案 §1.2 步骤契约 S2）：
  1. 调用 `scripts/seedgen.py --focus-group X` 生成 A/B/C/D 四组种子
     （每组独立落盘到 `derived/rq3/<g>/seeds/`，含 manifest.json）；
  2. 生成/拷贝冻结字典到 `derived/rq3/dict/`（base24 / targeted123 / compact32）；
  3. **执行 §2.5.3 的 A1–A10 全部断言**（任一失败 → 非零退出，不发布语料）；
  4. 写 `derived/rq3/groups.json`（编排脚本的唯一输入）；
  5. 写 `derived/rq3/dict/DICT_FROZEN.json`（字典冻结记录，论文附录引用）。

用法:
    E:/app/Anaconda3/python.exe scripts/rq3_build_corpus.py
    E:/app/Anaconda3/python.exe scripts/rq3_build_corpus.py --check-only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local"))

from core import paths  # noqa: E402

import rq3_common as C  # noqa: E402

#: 历史上用于 RQ1.2 的 ProtoRAG 语料（C 组与其 MD5 集合必须相等 → A7）
REFERENCE_CORPUS = ROOT / "derived" / "seeds" / "rtsp" / "live555_20261024_110155"

#: 四个聚焦组
GROUPS = ("A", "B", "C", "D")

#: 断言结果收集器
class Assertions:
    """断言收集器：记录每条断言的通过/失败与实测值。"""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def check(self, code: str, desc: str, ok: bool, detail: str = "") -> bool:
        """记录一条断言；返回 ok 本身（便于链式）。"""
        self.rows.append({"code": code, "desc": desc, "ok": bool(ok),
                          "detail": detail})
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {code} {desc}" + (f" — {detail}" if detail else ""))
        return bool(ok)

    @property
    def failed(self) -> list[dict]:
        """失败的断言行。"""
        return [r for r in self.rows if not r["ok"]]

    def summary(self) -> str:
        """人类可读的汇总文本。"""
        lines = ["# RQ3 语料一致性断言报告", "",
                 f"- 生成时间: {datetime.now().astimezone().isoformat()}",
                 f"- 断言总数: {len(self.rows)}",
                 f"- 通过: {len(self.rows) - len(self.failed)}",
                 f"- 失败: {len(self.failed)}", "",
                 "| 编号 | 断言 | 结果 | 实测 |", "|---|---|---|---|"]
        for r in self.rows:
            lines.append(f"| {r['code']} | {r['desc']} | "
                         f"{'PASS' if r['ok'] else 'FAIL'} | {r['detail']} |")
        return "\n".join(lines) + "\n"


def _md5_of(path: Path) -> str:
    """文件 MD5。"""
    return hashlib.md5(path.read_bytes()).hexdigest()


def _run_seedgen(group: str, out_dir: Path, manifest: bool = True) -> int:
    """调用 seedgen.py 生成一组种子（子进程，隔离参数解析副作用）。

    Args:
        group: 聚焦组名。
        out_dir: 输出目录。
        manifest: 是否落 manifest.json。

    Returns:
        子进程退出码。
    """
    cmd = [sys.executable, str(ROOT / "scripts" / "seedgen.py"),
           "--protocol", "rtsp", "--focus-group", group,
           "--out", str(out_dir)]
    if manifest:
        cmd.append("--manifest")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print(proc.stdout or "")
        print(proc.stderr or "", file=sys.stderr)
    return proc.returncode


def _generate_dicts(cfg: dict) -> dict:
    """生成全部冻结字典到 `derived/rq3/dict/`。

    产出：
      · rtsp_base.dict      —— 基础字典（24 token，MD5 与镜像内一致）
      · c_targeted.dict     —— C 组定向字典（123 token）
      · c_compact.dict      —— C′ 预案精简字典（32 token）

    Returns:
        `{字典种类: 文件路径}`。
    """
    from core.fused.downstream.boundary_probe import (
        generate_targeted_dict, generate_protocol_dict, load_base_dict_tokens,
    )
    from core.fused.downstream.rag_seedgen import load_fact_views, assemble_bundle
    from scripts.seedgen import _load_profile, _load_resources

    protocol = cfg["protocol"]
    profile = _load_profile(protocol)
    bundle = assemble_bundle(load_fact_views(protocol))
    resources = _load_resources(profile, protocol)

    out_dir = C.dict_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict = {}

    # 基础字典：直接复制仓库内副本（逐字节，MD5 = 镜像内）
    base_src = paths.targets_root() / protocol / f"{protocol}_base.dict"
    if not base_src.exists():
        raise FileNotFoundError(f"缺少基础字典: {base_src}")
    base_dst = out_dir / "rtsp_base.dict"
    shutil.copyfile(base_src, base_dst)
    result["base"] = base_dst

    # C 组定向字典
    tgt_dst = out_dir / "c_targeted.dict"
    tgt_dst.write_text(generate_targeted_dict(
        bundle, protocol=protocol, resources=resources,
        base_tokens=load_base_dict_tokens(protocol),
        include_trigger_fields=True, compact=False), encoding="utf-8")
    result["targeted"] = tgt_dst

    # C′ 预案精简字典
    cmp_dst = out_dir / "c_compact.dict"
    cmp_dst.write_text(generate_targeted_dict(
        bundle, protocol=protocol, resources=resources,
        base_tokens=load_base_dict_tokens(protocol),
        include_trigger_fields=True, compact=True), encoding="utf-8")
    result["targeted-compact"] = cmp_dst

    # 协议字典（现状 102 token，仅作对照，不进实验）
    proto_dst = out_dir / "rtsp_protocol.dict"
    proto_dst.write_text(generate_protocol_dict(
        bundle, protocol=protocol, resources=resources), encoding="utf-8")
    result["protocol"] = proto_dst

    return result


def _freeze_dicts(cfg: dict, dict_files: dict) -> dict:
    """写 DICT_FROZEN.json：记录每个字典的 token 数 + MD5（防内容漂移）。

    编排预检每次启动前核对本文件里的 MD5；不一致 → 拒绝启动。
    """
    records = []
    for kind, p in sorted(dict_files.items()):
        tokens = [ln for ln in p.read_text(encoding="utf-8").splitlines()
                  if ln.strip()]
        records.append({
            "kind": kind,
            "path": str(p.relative_to(ROOT)).replace("\\", "/"),
            "token_count": len(tokens),
            "md5": _md5_of(p),
            "generated_at": datetime.now().astimezone().isoformat(),
        })
    payload = {
        "schema_version": "1.0",
        "protocol": cfg["protocol"],
        "base_md5": cfg["base_dict_md5"],
        "dictionaries": records,
    }
    C.write_json(C.dict_frozen_path(), payload)
    return payload


def _assert_corpus(cfg: dict, groups: dict, dict_files: dict) -> Assertions:
    """执行 §2.5.3 的 A1–A10 全部断言。

    Args:
        cfg: RQ3 配置。
        groups: `{组名: 种子目录}`。
        dict_files: `{字典种类: 文件路径}`。

    Returns:
        断言收集器。
    """
    a = Assertions()
    manifests: dict = {}
    for g in GROUPS:
        mpath = C.group_manifest_path(g)
        if mpath.exists():
            manifests[g] = C.read_json(mpath)

    # ---- A1: manifest 条数 == 语料条数 == 期望条数 ----
    for g in GROUPS:
        raw_files = sorted(groups[g].glob("*.raw"))
        n_manifest = len(manifests.get(g, {}).get("seeds", []))
        expect = cfg["groups"][g]["expect_seeds"]
        a.check(f"A1.{g}", f"{g} 组 manifest/语料/期望条数一致",
                len(raw_files) == n_manifest == expect,
                f"raw={len(raw_files)} manifest={n_manifest} expect={expect}")

    # ---- A2: manifest 的每个 md5 == 实测 md5 ----
    for g in GROUPS:
        ok = True
        bad: list = []
        for entry in manifests.get(g, {}).get("seeds", []):
            p = groups[g] / entry["filename"]
            if not p.exists() or _md5_of(p) != entry["md5"]:
                ok = False
                bad.append(entry["filename"])
        a.check(f"A2.{g}", f"{g} 组 manifest 的 MD5 与实测一致", ok,
                "全部一致" if ok else f"不一致: {bad[:5]}")

    # ---- A3: manifest 的每个 filename 真实存在 ----
    for g in GROUPS:
        missing = [e["filename"] for e in manifests.get(g, {}).get("seeds", [])
                   if not (groups[g] / e["filename"]).exists()]
        a.check(f"A3.{g}", f"{g} 组 manifest 的文件名全部存在", not missing,
                "全部存在" if not missing else f"缺失: {missing[:5]}")

    # ---- A4: A 的 md5 序列 == B 的 md5 序列前 38 项（自然序限定）----
    a_md5 = [e["md5"] for e in manifests.get("A", {}).get("seeds", [])]
    b_md5 = [e["md5"] for e in manifests.get("B", {}).get("seeds", [])]
    a.check("A4", "A 的 md5 序列 == B 的前 38 项（自然序限定）",
            len(a_md5) == 38 and a_md5 == b_md5[:38],
            f"A={len(a_md5)} B[:38] 匹配" if a_md5 == b_md5[:38] else "不匹配")

    # ---- A5: A 的文件名序列 == B 的前 38 个文件名 ----
    a_name = [e["filename"] for e in manifests.get("A", {}).get("seeds", [])]
    b_name = [e["filename"] for e in manifests.get("B", {}).get("seeds", [])]
    a.check("A5", "A 的文件名序列 == B 的前 38 个文件名",
            a_name == b_name[:38],
            "完全相同" if a_name == b_name[:38] else "不同")

    # ---- A6: B / C / D 的 md5 集合两两相等 ----
    sets = {g: {e["md5"] for e in manifests.get(g, {}).get("seeds", [])}
            for g in ("B", "C", "D")}
    ok = sets["B"] == sets["C"] == sets["D"]
    a.check("A6", "B / C / D 的 md5 集合两两相等", ok,
            f"各 {len(sets['B'])}/{len(sets['C'])}/{len(sets['D'])} 个")

    # ---- A7: C 的 md5 集合 == RQ1.2 protorag 语料 ----
    if REFERENCE_CORPUS.exists():
        ref = {hashlib.md5(f.read_bytes()).hexdigest()
               for f in REFERENCE_CORPUS.glob("*.raw")}
        a.check("A7", "C 的 md5 集合 == RQ1.2 protorag 语料（50 条）",
                ref == sets["C"], f"ref={len(ref)} C={len(sets['C'])}")
    else:
        a.check("A7", "C 的 md5 集合 == RQ1.2 protorag 语料（50 条）", False,
                f"参考语料不存在: {REFERENCE_CORPUS}")

    # ---- A8: 每组语料文件名的前 60 字符全局唯一 ----
    for g in GROUPS:
        names = [e["filename"] for e in manifests.get(g, {}).get("seeds", [])]
        pref = [n[:60] for n in names]
        a.check(f"A8.{g}", f"{g} 组文件名前 60 字符唯一",
                len(set(pref)) == len(pref),
                f"最大长度 {max((len(n) for n in names), default=0)}")

    # ---- A9: 字典 token 数与 MD5 ----
    base_tok = C.dict_token_count(dict_files["base"])
    base_md5 = _md5_of(dict_files["base"])
    tgt_tok = C.dict_token_count(dict_files["targeted"])
    a.check("A9.base", "基础字典 24 token 且 MD5 == 镜像内 base24",
            base_tok == 24 and base_md5 == cfg["base_dict_md5"],
            f"tokens={base_tok} md5={base_md5}")
    a.check("A9.targeted", "定向字典 123 token",
            tgt_tok == cfg["dict_kinds"]["targeted"]["token_count"],
            f"tokens={tgt_tok}")
    # ★ 严格超集断言：C 字典 ⊇ base24（D→C 单变量的前提）
    base_set = C.dict_tokens(dict_files["base"])
    tgt_set = C.dict_tokens(dict_files["targeted"])
    a.check("A9.superset", "定向字典是基础字典的严格超集",
            base_set < tgt_set,
            f"base={len(base_set)} targeted={len(tgt_set)} "
            f"新增={len(tgt_set - base_set)}")

    # ---- A10: 组内 md5 唯一 ----
    for g in GROUPS:
        mds = [e["md5"] for e in manifests.get(g, {}).get("seeds", [])]
        a.check(f"A10.{g}", f"{g} 组 md5 组内唯一",
                len(set(mds)) == len(mds), f"{len(set(mds))}/{len(mds)}")

    return a


def build(check_only: bool = False) -> int:
    """构建四组语料 + 字典 + 断言 + groups.json。

    Args:
        check_only: True 时只跑断言与报告，不重新生成语料。

    Returns:
        0 = 全部通过；非 0 = 有断言失败或生成失败。
    """
    cfg = C.load_config()
    print(f"配置: protocol={cfg['protocol']} image={cfg['image']}")
    print(f"参考语料: {REFERENCE_CORPUS}")

    groups_dir: dict = {}
    for g in GROUPS:
        d = C.group_seed_dir(g, create=True)
        groups_dir[g] = d

    if not check_only:
        # 1) 逐组生成（每组一次 seedgen 调用，保证组间互不影响）
        for g in GROUPS:
            print(f"\n=== 生成组 {g}（{cfg['groups'][g]['label']}）===")
            rc = _run_seedgen(g, groups_dir[g])
            if rc != 0:
                print(f"!! 组 {g} 生成失败（退出码 {rc}）", file=sys.stderr)
                return 4
            # seedgen 会把字典写在语料目录里；统一挪到 derived/rq3/dict/
            stray = groups_dir[g] / f"{cfg['protocol']}.dict"
            if stray.exists():
                stray.unlink()
            # manifest 提升到组目录（derived/rq3/<g>/manifest.json），
            # 语料目录只保留 .raw —— 布局对齐技术方案 §11.1。
            m_src = groups_dir[g] / "manifest.json"
            m_dst = C.group_manifest_path(g)
            if m_src.exists():
                shutil.move(str(m_src), str(m_dst))

    # 2) 字典生成 + 冻结
    print("\n=== 生成冻结字典 ===")
    dict_files = _generate_dicts(cfg)
    for kind, p in sorted(dict_files.items()):
        n = C.dict_token_count(p)
        print(f"  {kind:<18} {n:>4} token  md5={_md5_of(p)}  → {p.name}")

    frozen = _freeze_dicts(cfg, dict_files)

    # 3) 断言
    print("\n=== 一致性断言 A1–A10 ===")
    a = _assert_corpus(cfg, groups_dir, dict_files)
    report = C.RQ3_ROOT / "assertions_report.md"
    report.write_text(a.summary(), encoding="utf-8")
    print(f"\n断言报告: {report}")

    if a.failed:
        print(f"\n!! {len(a.failed)} 条断言失败 → 不发布语料",
              file=sys.stderr)
        for r in a.failed:
            print(f"   FAIL {r['code']} {r['desc']} — {r['detail']}",
                  file=sys.stderr)
        return 5

    # 4) groups.json（编排脚本的唯一输入）
    groups_payload = {
        "schema_version": "1.0",
        "protocol": cfg["protocol"],
        "generated_at": datetime.now().astimezone().isoformat(),
        "image": cfg["image"],
        "container_template": "rq3_{group}_{fuzzer}_r{rep}",
        "groups": {},
        "dictionaries": {r["kind"]: r for r in frozen["dictionaries"]},
    }
    for g in GROUPS:
        gcfg = cfg["groups"][g]
        m = C.read_json(C.group_manifest_path(g))
        groups_payload["groups"][g] = {
            "group": g,
            "label": gcfg["label"],
            "layers": gcfg["layers"],
            "order": gcfg["order"],
            "dict_kind": gcfg["dict_kind"],
            "dict_file": gcfg["dict_file"],
            "dict_tokens": C.dict_token_count(
                dict_files["targeted" if gcfg["dict_kind"] == "targeted"
                           else "base"]),
            "expect_seeds": gcfg["expect_seeds"],
            "seed_count": m["seed_count"],
            "seed_md5_set": sorted({e["md5"] for e in m["seeds"]}),
            "seed_files": [e["filename"] for e in m["seeds"]],
            "manifest": f"derived/rq3/{g}/manifest.json",
            "in_paper_table18": gcfg["in_paper_table18"],
        }
    C.write_json(C.groups_json_path(), groups_payload)
    print(f"\ngroups.json: {C.groups_json_path()}")

    # 5) 汇总
    print("\n" + "=" * 72)
    print("RQ3 语料构建完成")
    print("=" * 72)
    for g in GROUPS:
        gi = groups_payload["groups"][g]
        print(f"  {g} {gi['label']:<14} 种子 {gi['seed_count']:>3} 条  "
              f"字典 {gi['dict_tokens']:>3} token ({gi['dict_kind']})  "
              f"顺序 {gi['order']}")
    print(f"  断言: {len(a.rows)} 条全部通过")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ3 四组语料组装 + 一致性断言")
    ap.add_argument("--check-only", action="store_true",
                    help="只跑断言与报告，不重新生成语料")
    args = ap.parse_args()
    return build(check_only=args.check_only)


if __name__ == "__main__":
    raise SystemExit(main())
