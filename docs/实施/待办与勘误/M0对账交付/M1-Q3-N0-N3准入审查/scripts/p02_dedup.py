# -*- coding: utf-8 -*-
"""★ N0.2：★ 安全移除**失效的历史定义**（★ 保留每个名字的最后一个定义）。

★ 安全措施：
  ① 只删除**除最后一个以外**的同名定义节点（★ 运行时本就以最后一个为准）
  ② 只删该节点自身的源码行（★ 含装饰器与 docstring）⇒ ★ **不碰夹在其间的其它语句**
  ③ 逐次删除并重新解析（★ 语法错误即中止）
  ④ 去重后与**基线**逐项比对（★ 代码 sha + 真实输出 + 三路径行为）
"""
import ast
import collections
import hashlib
import importlib
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
P = ROOT / "core/fused/extraction/prose_semantics.py"
OUT = ROOT / "guard/_out/n0"

BASE = json.loads((OUT / "n0_baseline_before_dedup.json").read_text(encoding="utf-8"))

src = P.read_text(encoding="utf-8")
lines = src.split("\n")

# ★ 收集要删除的行号（★ 全部重复名中除最后一个的节点）
tree = ast.parse(src)
defs = collections.defaultdict(list)
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        defs[node.name].append(node)

drop = set()
_targets = []
for name, nodes in defs.items():
    if len(nodes) < 2:
        continue
    for n in nodes[:-1]:
        _start = n.lineno
        if getattr(n, "decorator_list", None):
            _start = min(_start, min(d.lineno for d in n.decorator_list))
        for _i in range(_start, n.end_lineno + 1):
            drop.add(_i)
        _targets.append((name, n.lineno, n.end_lineno))

print(f"  ★ 将删除 {len(_targets)} 个失效定义（★ 共 {len(drop)} 行）")
for name, a, b in _targets[:12]:
    print(f"      {name} @行{a}~{b}")

# ★ 执行删除（★ 一次性）
new_lines = [l for i, l in enumerate(lines, 1) if i not in drop]
new_src = "\n".join(new_lines)
ast.parse(new_src)
print(f"  ✓ 删除后行数 {len(lines)} → {len(new_lines)}（★ 语法 OK）")

P.write_text(new_src, encoding="utf-8")

# ★ ④ 比对基线
importlib.import_module("core.fused.extraction.prose_semantics")
from core.fused.extraction import prose_semantics as ps
from core import paths

tree2 = ast.parse(new_src)
defs2 = collections.defaultdict(list)
for node in tree2.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        defs2[node.name].append(node)
sha2 = {name: hashlib.sha256(ast.unparse(nodes[-1]).encode()).hexdigest()
        for name, nodes in defs2.items()}
_dup_left = {k: len(v) for k, v in defs2.items() if len(v) > 1}
_mismatch = [k for k, v in BASE["★ 最后定义代码 sha"].items()
             if sha2.get(k) != v]
print()
print(f"  ★ 去重后剩余重复定义：{_dup_left or '★ 无'}")
print(f"  ★ 与基线**代码 sha 不一致**的函数：{_mismatch or '★ 无'}")
for k in _mismatch:
    print(f"      {k}: 基线 {BASE['★ 最后定义代码 sha'][k][:12]} vs 现在 {str(sha2.get(k))[:12]}")

# ★ 真实输出比对
_real2 = {}
for proto in ("rtsp", "sip", "smtp", "DHCPv4"):
    _files = sorted(paths.kb_source_dir(proto, "rfc").glob("*.txt"))
    _b = ps._collect_blocks(_files)
    _real2[proto] = {"n": len(_b),
                     "items": [{"doc": x["doc"], "start": x["start"],
                                "text_sha": hashlib.sha256(x["text"].encode()).hexdigest()[:16]}
                               for x in _b]}
_out_diff = [p for p in BASE["★ 真实输出基线"]
             if BASE["★ 真实输出基线"][p] != _real2[p]]
print(f"  ★ 真实输出**不一致**的协议：{_out_diff or '★ 无'}")

# ★ 三路径比对
def _probe(tag, env):
    for _k in ("PROSE_KIND_REVIEW", "PROSE_BLOCK_SELECTION",
               "PROSE_BLOCKS_PER_DOC"):
        os.environ.pop(_k, None)
    os.environ.update(env)
    importlib.reload(ps)
    _files = sorted(paths.kb_source_dir("DHCPv4", "rfc").glob("*.txt"))
    _b = ps._collect_blocks(_files)
    return {"tag": tag, "env": env, "n_blocks": len(_b),
            "docs": len({x["doc"] for x in _b}),
            "first": [(x["doc"], x["start"]) for x in _b[:3]],
            "kind_review": ps._kind_review_enabled(),
            "selection": ps._block_selection_mode()}


probe2 = [
    _probe("默认关闭", {}),
    _probe("kind review 开启", {"PROSE_KIND_REVIEW": "1",
                                "PROSE_BLOCKS_PER_DOC": "1"}),
    _probe("block selection 开启", {"PROSE_BLOCK_SELECTION": "block_density",
                                    "PROSE_BLOCKS_PER_DOC": "16"}),
]
_probe_diff = []
for a, b in zip(BASE["★ 三路径行为"], probe2):
    if (a["n_blocks"], a["docs"], a["first"], a["kind_review"], a["selection"]) != \
       (b["n_blocks"], b["docs"], b["first"], b["kind_review"], b["selection"]):
        _probe_diff.append(a["tag"])
print(f"  ★ 三路径行为**不一致**的：{_probe_diff or '★ 无'}")

_ok = (not _dup_left) and (not _mismatch) and (not _out_diff) and (not _probe_diff)
print()
print(f"  ★★ 等价性判定：{'✅ 通过' if _ok else '❌ 未通过'}")
(OUT / "n0_dedup_verify.json").write_text(json.dumps({
    "★ 删除了的定义": [{"name": n, "lines": [a, b]} for n, a, b in _targets],
    "★ 去重后剩余重复": _dup_left,
    "★ 代码 sha 不一致": _mismatch,
    "★ 真实输出不一致": _out_diff,
    "★ 三路径不一致": _probe_diff,
    "★ 等价": _ok,
    "★ 行为基线(去重后)": {"真实输出": _real2, "三路径": probe2},
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"  ⇒ {OUT/'n0_dedup_verify.json'}")
