# -*- coding: utf-8 -*-
"""R29-RA1/D1 反向测试：在影子抽取器上跑 8 类负例与正例。"""
from __future__ import annotations
import sys, pathlib, re

WT = pathlib.Path(__file__).resolve().parents[6]  # 影子 worktree 根
sys.path.insert(0, str(WT))
from core.fused.extraction import rfc_extractor as RX  # noqa: E402


def probe(lines):
    return RX._extract_abnf_productions([(i + 1, t) for i, t in enumerate(lines)])


def main() -> int:
    checks = []

    # 1 目录行（点引导）不抽
    got = probe(["   npt-range ........ 42", "   foo = %x41"])
    checks.append(("目录行不抽", all(p["name"] != "npt-range" for p in got)))

    # 2 示例伪产生式（散文里的等号）不抽
    got = probe(["For example, set timeout = 30 seconds before running."])
    checks.append(("散文等号不抽", got == []))

    # 3 跨行续写完整保留
    got = probe(["   atext = ALPHA / DIGIT /",
                 '           "!" / "#" /',
                 '           "$"'])
    ok = bool(got) and got[0]["name"] == "atext" and '"$"' in got[0]["rhs"]
    checks.append(("跨行续写完整", ok))

    # 4 同上但续行是 ;; 注释 ⇒ 不被并进右部
    got = probe(["   auth-param = \"AUTH=\" xtext",
                 "                 ;; 注释行",
                 "                 ;; 第二行"])
    ok = bool(got) and got[0]["rhs"] == '"AUTH=" xtext'
    checks.append(("注释不并入右部", ok))

    # 5 代码行（C 示例）不抽
    got = probe(["   hash = loadb_mx_tbl  [ hash ^ key[ --i ] ]; return( hash );"])
    checks.append(("代码行不抽", got == []))

    # 6 现有字段/方法同名不重复（真实语料，全协议）
    dup = 0
    for proto in ("smtp", "rtsp", "DHCPv4"):
        ns = RX.extract_rfc_norms(proto, llm=None)
        others = {n["name"].lower() for n in ns if n.get("kind") != "syntax_production"}
        dup += sum(1 for n in ns if n.get("kind") == "syntax_production"
                   and n["name"].lower() in others)
    checks.append(("与既有知识无同名重复", dup == 0))

    # 7 辅助产生式被保留（npt-time 是 npt-range 的引用目标）
    ns = RX.extract_rfc_norms("rtsp", llm=None)
    names = {n["name"] for n in ns if n.get("kind") == "syntax_production"}
    checks.append(("辅助产生式保留", {"npt-range", "npt-time"} <= names))

    # 8 新建 Norm 不产出 Fact（映射未接线，防止悄悄改契约）
    from core.fused.extraction import norm as NM
    sp = [n for n in ns if n.get("kind") == "syntax_production"]
    facts = sum(len(NM.map_norm_to_facts(n)) for n in sp)
    checks.append(("未映射到 Canonical（0 Fact）", facts == 0))

    ok = all(v for _, v in checks)
    for name, v in checks:
        print(("PASS " if v else "FAIL ") + name)
    print("结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
