# -*- coding: utf-8 -*-
"""★ N0.1：★ 用 AST 核实 `prose_semantics.py` 的重复定义（★ 不凭文本重复判断）。

★ 核实项：
  ① 所有同名函数定义的位置与数量
  ② ★ **运行时真正生效的函数**（★ 最后一个定义覆盖前面的）
  ③ 历史定义之间的**实现差异**
  ④ ★ P0.6～P0.9 的修复**分别位于哪个定义**
  ⑤ PROSE_KIND_REVIEW / PROSE_BLOCK_SELECTION 在**生效路径**中是否可用
  ⑥ 删除历史定义是否影响引用、模块初始化或测试
"""
import ast
import collections
import hashlib
import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
P = ROOT / "core/fused/extraction/prose_semantics.py"

src = P.read_text(encoding="utf-8")
tree = ast.parse(src)

# ★ ① 同名定义
defs = collections.defaultdict(list)
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        defs[node.name].append(node)
    elif isinstance(node, ast.ClassDef):
        defs[node.name].append(node)
dups = {k: v for k, v in defs.items() if len(v) > 1}
print("  ★ ① 同名重复定义：")
for k, v in sorted(dups.items()):
    print(f"      {k}: {len(v)} 处 @ 行 {[n.lineno for n in v]}")

# ★ 模块级重复（docstring / import 段）
_mod_dups = collections.Counter()
for node in tree.body:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        _mod_dups["import"] += 1
    elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
            and isinstance(node.value.value, str):
        _mod_dups["docstring"] += 1
print(f"  ★ 模块级：docstring {list(ast.get_docstring(tree) or '')[:0] and '' or ''}"
      f"｜顶层 import 语句 {_mod_dups['import']} 条｜字符串表达式 {_mod_dups['docstring']} 处")

# ★ ② 运行时生效的函数
mod = importlib.import_module("core.fused.extraction.prose_semantics")
print()
print("  ★ ② 运行时生效对象：")
for name in sorted(dups):
    _obj = getattr(mod, name, None)
    _last = dups[name][-1]
    _code = ast.unparse(_last)
    _h = hashlib.sha256(_code.encode()).hexdigest()[:12]
    print(f"      {name}: 运行时行号={getattr(_obj, '__code__', None) and _obj.__code__.co_firstlineno}"
          f"｜最后一个定义行={_last.lineno}｜★ 同一⇒ {getattr(_obj,'__code__',None) and _obj.__code__.co_firstlineno == _last.lineno}"
          f"｜代码 sha={_h}")

# ★ ③ 各定义体差异
print()
print("  ★ ③ 历史定义之间的实现差异：")
for name, nodes in sorted(dups.items()):
    if name != "_collect_blocks":
        continue
    _h = []
    for n in nodes:
        _c = ast.unparse(n)
        _h.append((n.lineno, len(_c), hashlib.sha256(_c.encode()).hexdigest()[:10]))
    for i, (ln, ln_len, hh) in enumerate(_h):
        _tag = "★ 生效" if i == len(_h) - 1 else f"历史{i+1}"
        print(f"      定义{i+1} @行{ln:<5d} 体长 {ln_len:6d} sha {hh}  {_tag}")
    _uniq = len({x[2] for x in _h})
    print(f"      ★ 不同实现版本数 = {_uniq}")

# ★ ④ P0.6～P0.9 的修复位于哪个定义
print()
print("  ★ ④ P0.6～P0.9 修复的位置：")
MARKS = {
    "P0.6 句界证据 build_evidence": "_build_evidence(",
    "P0.6 span_quote_window": "_span_quote_window(",
    "P0.7-A 归属核验": "_resolve_subject_attribution(",
    "P0.8 类型复核开关": "def _kind_review_enabled(",
    "P0.8 类型复核构造": "def _build_kind_review(",
    "P0.9 块选择模式": "def _block_selection_mode(",
    "P0.9 块选择分支": "select_block_density(_all",
    "P0.9 block_starts 参数": "block_starts: Optional[list]",
}
for label, mark in MARKS.items():
    _locs = []
    for i, n in enumerate(dups.get("_collect_blocks", [])):
        _seg = ast.unparse(n)
        if mark in _seg:
            _locs.append(i + 1)
    _top = mark in src
    print(f"      {label:32s} ⇒ 位于 _collect_blocks 定义 {_locs or '（不在其中）'}"
          f"｜模块顶层: {_top}")

# ★ ⑤ 生效路径可用性
print()
print("  ★ ⑤ 生效路径中的两个开关：")
import os
os.environ["PROSE_KIND_REVIEW"] = "1"
os.environ["PROSE_BLOCK_SELECTION"] = "block_density"
importlib.reload(mod)
print(f"      PROSE_KIND_REVIEW    ⇒ _kind_review_enabled() = {mod._kind_review_enabled()}")
print(f"      PROSE_BLOCK_SELECTION ⇒ _block_selection_mode() = {mod._block_selection_mode()!r}")
os.environ.pop("PROSE_KIND_REVIEW", None)
os.environ.pop("PROSE_BLOCK_SELECTION", None)
importlib.reload(mod)
print(f"      默认关闭：kind={mod._kind_review_enabled()}｜selection={mod._block_selection_mode()!r}")

# ★ ⑥ 引用关系
print()
print("  ★ ⑥ 外部引用：")
import subprocess
for nm in sorted(dups):
    _r = subprocess.run(
        ["grep", "-rn", "--include=*.py", nm, str(ROOT / "core"), str(ROOT / "tests")],
        capture_output=True, text=True)
    _lines = [l for l in _r.stdout.splitlines() if "prose_semantics.py" not in l]
    print(f"      {nm}: 外部引用 {len(_lines)} 处")
    for l in _lines[:6]:
        print(f"          {l.replace(str(ROOT), 'ROOT')}")
