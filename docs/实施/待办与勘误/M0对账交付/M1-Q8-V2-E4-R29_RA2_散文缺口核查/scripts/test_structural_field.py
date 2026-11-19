# -*- coding: utf-8 -*-
"""D4 字段映射回归（8 项，零网络）。"""
from __future__ import annotations
import pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from core.fused.extraction import norm as NM
from core.fused.extraction.norm import parse_field_content


def norm(name, content, src, proto="DHCPv4"):
    return {"kind": "field", "name": name, "content": content,
            "kb_source_type": "rfc", "protocol": proto, "source": src,
            "channel": "structural"}


def facts(n):
    return NM.map_norm_to_facts(n)


def aspects(fs):
    return sorted({f.fact_key.aspect for f in fs})


def main() -> int:
    C = []
    d4 = norm("siaddr", "4 | optional: IP address of next server to use in bootstrap",
              "file:rfc2131.txt#@541")
    fs = facts(d4)
    C.append(("D4 同时产出 syntax + definition", aspects(fs) == ["definition", "syntax"]))
    C.append(("D4 syntax pattern = 4",
              any(f.fact_key.aspect == "syntax" and f.claims[0].value.data == "4" for f in fs)))
    defs = [f.claims[0].value.data for f in fs if f.fact_key.aspect == "definition"]
    C.append(("D4 definition 含 next server / bootstrap",
              defs and "next server" in defs[0] and "bootstrap" in defs[0]))

    no_sem = norm("x", "4", "file:a#@1")
    C.append(("无语义段 ⇒ 不产 definition",
              aspects(facts(no_sem)) == ["syntax"]))

    punct = norm("y", "8 | optional: a, b; c (d) — e",
                 "file:a#@2")
    pv = [f.claims[0].value.data for f in facts(punct) if f.fact_key.aspect == "definition"]
    C.append(("标点与空格不被截断", pv and pv[0].endswith("e")))

    other = norm("hlen", "1 | optional: Hardware address length",
                 "file:rfc2131.txt#@526")
    of = facts(other)
    C.append(("同类字段走同一规则（非 siaddr 硬编码）",
              aspects(of) == ["definition", "syntax"]))

    C.append(("不同字段不合并",
              {f.fact_id for f in fs}.isdisjoint({f.fact_id for f in of})))

    again = facts(norm("siaddr", "4 | optional: IP address of next server to use in bootstrap",
                       "file:rfc2131.txt#@541"))
    C.append(("重复运行身份一致",
              [f.fact_id for f in again] == [f.fact_id for f in fs]))

    h2 = norm("request-line",
              "method SP request-target SP HTTP-version CRLF | optional: HTTP 请求行由方法、请求目标、协议版本依次以单个空格分隔组成",
              "file:rfc9112.txt#@261", proto="http")
    hf = facts(h2)
    C.append(("H2 syntax 身份不变（f2_f5d4a14e…）",
              any(f.fact_id.startswith("f2_f5d4a14e") for f in hf)))

    ok = all(v for _, v in C)
    for n, v in C:
        print(("PASS " if v else "FAIL ") + n)
    print("结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
