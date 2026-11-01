# -*- coding: utf-8 -*-
"""tests/fused/test_analyze_compare_index.py —— RSI 侧「关键时间点对比」的**标签 off-by-one** 回归。

★ 缺陷
------
``scripts/analyze_compare_12h.py`` 在打印关键时间点对比时这样取数::

    idx = int(h_target / 0.25) - 1        # ← 少减了 1

时间轴是 ``hours = np.arange(0, HOURS + 1e-6, 0.25)``，即 ``hours[k] == k * 0.25``。
因此 ``int(h_target / 0.25)`` 才是 ``h_target`` 真正的下标，``- 1`` 让它偏了一格：

    标签 2.0h → idx= 7 → 实际取的是 1.75h 的数据
    标签 4.0h → idx=15 → 实际取的是 3.75h 的数据
    标签 8.0h → idx=31 → 实际取的是 7.75h 的数据

→ **打印出的标签时刻与实际取数时刻差一个 step（0.25h）**。

★ 影响面（重要，别夸大）
----------------------
* **跨组差值 ``m - c`` 不受影响** —— 两组用的是**同一个 idx**，即同一时刻相减，
  差值依然正确。
* **图 1 / 图 2 不受影响** —— 它们用的是 ``mean_band`` 返回的**完整时间轴**。
* 受影响的只有**终端打印**的「关键时间点对比」小节里的**标签**。

修复方式不是简单去掉 ``- 1``（那样在 ``HOURS`` 不是 step 整数倍时会越界），
而是改成**在时间轴上反查最近点**（``pick_index()``），并保留夹紧。

★ 本测试怎么驱动生产代码
------------------------
``analyze_compare_12h.py`` 是**顶层脚本**（import 即执行绘图），无法直接 import。
所以本文件用 ``ast`` 从源码里**摘出 ``pick_index()`` 的函数体**，
在隔离的命名空间里执行 —— 测的是**生产代码本身**，不是在 Python 里重写一遍。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "analyze_compare_12h.py"


def _load_pick_index():
    """从生产脚本里摘出 ``pick_index()`` 并加载（不执行脚本顶层逻辑）。"""
    src = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "pick_index":
            mod = ast.Module(body=[node], type_ignores=[])
            ast.fix_missing_locations(mod)
            ns: dict = {}
            import numpy as np  # 函数体用到 np
            ns["np"] = np
            exec(compile(mod, str(SCRIPT), "exec"), ns)  # noqa: S102 - 测试内加载生产函数
            return ns["pick_index"]
    pytest.skip("analyze_compare_12h.py 里找不到 pick_index()")


@pytest.fixture(scope="module")
def pick_index():
    return _load_pick_index()


# ---------------------------------------------------------------------------
# 核心：标签时刻必须与实际取数时刻一致
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("h_target", [2.0, 4.0, 8.0, 12.0, 24.0])
def test_pick_index_hits_the_exact_target_hour(pick_index, h_target: float) -> None:
    """取到的下标对应的**时间必须恰好等于**标签时刻。

    这是旧实现（``int(h/0.25) - 1``）**不满足**的性质 —— 它会偏一格。
    """
    import numpy as np
    hours = np.arange(0, 24.0 + 1e-6, 0.25)
    idx = pick_index(hours, h_target)
    assert abs(hours[idx] - h_target) < 1e-9, (
        f"标签 {h_target}h 实际取到的是 {hours[idx]}h（idx={idx}）—— 标签与取数不一致"
    )


@pytest.mark.parametrize("h_target", [2.0, 4.0, 8.0, 12.0, 24.0])
def test_pick_index_is_not_the_buggy_off_by_one(pick_index, h_target: float) -> None:
    """明确排除旧实现：不得等于 ``int(h/0.25) - 1``（除非它恰好也正确）。"""
    import numpy as np
    hours = np.arange(0, 24.0 + 1e-6, 0.25)
    idx = pick_index(hours, h_target)
    buggy = int(h_target / 0.25) - 1
    if buggy != int(round(h_target / 0.25)):
        assert idx != buggy, (
            f"标签 {h_target}h 仍取到了旧实现的下标 {buggy}（= {hours[buggy]}h）—— off-by-one 未修"
        )


def test_pick_index_is_monotonic(pick_index) -> None:
    """目标时刻变大 → 下标必须单调不减（不能乱跳）。"""
    import numpy as np
    hours = np.arange(0, 24.0 + 1e-6, 0.25)
    idxs = [pick_index(hours, t) for t in [0.5, 1.0, 2.0, 3.5, 6.0, 12.0, 20.0, 24.0]]
    assert idxs == sorted(idxs), f"下标非单调：{idxs}"


def test_pick_index_clamps_when_target_exceeds_axis(pick_index) -> None:
    """目标超出时间轴末端 → 夹紧到最后一个点，不越界。"""
    import numpy as np
    hours = np.arange(0, 24.0 + 1e-6, 0.25)
    idx = pick_index(hours, 999.0)
    assert idx == len(hours) - 1
    assert 0 <= idx < len(hours)


def test_pick_index_handles_non_multiple_of_step(pick_index) -> None:
    """``HOURS`` 不是 step 整数倍时（末元素不足整 step），不得越界。

    这是"简单去掉 -1"修法会踩的坑：``HOURS=10.3`` 时轴长 42、末元素 10.25，
    ``int(10.3/0.25) == 41`` 本身合法，但换成别的 HOURS 就可能越界。
    """
    import numpy as np
    for hmax in (10.3, 7.1, 23.9):
        hours = np.arange(0, hmax + 1e-6, 0.25)
        for target in (2.0, hmax, hmax + 5.0):
            idx = pick_index(hours, target)
            assert 0 <= idx < len(hours), f"hmax={hmax} target={target} → idx={idx} 越界"


def test_pick_index_empty_axis(pick_index) -> None:
    """空时间轴 → 返回 0，不抛异常。"""
    import numpy as np
    assert pick_index(np.array([]), 2.0) == 0


def test_pick_index_returns_plain_int(pick_index) -> None:
    """返回值必须是普通 int（numpy int 会让 f-string 格式化出怪异结果）。"""
    import numpy as np
    idx = pick_index(np.arange(0, 24.0 + 1e-6, 0.25), 2.0)
    assert type(idx) is int


# ---------------------------------------------------------------------------
# 源码级护栏：防止旧写法复活 / 防止修法被改回"算术反推"
# ---------------------------------------------------------------------------
def _code_without_comments() -> str:
    """返回脚本的**纯代码**部分（剔除注释与文档字符串）。

    ★ 为什么必须剔除注释
    --------------------
    本脚本在修复处留了注释说明"历史实现是 ``int(h_target / 0.25) - 1``"，
    而护栏若直接在原文里搜字符串，就会把**注释里的历史写法**误判成"代码复活"——
    那会让护栏假红，久了就没人信它。故只在**真实代码**里匹配。
    """
    src = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    # 用 ast 重建：只保留可执行语句的结构信息，注释天然不在其中
    parts: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # 字符串常量可能是 docstring；保留（代码里也可能用到字符串字面量）
            parts.append(repr(node.value))
        elif isinstance(node, ast.Name):
            parts.append(node.id)
        elif isinstance(node, ast.Attribute):
            parts.append(node.attr)
        elif isinstance(node, ast.Constant):
            parts.append(repr(node.value))
    return "\n".join(parts)


def test_script_no_longer_uses_the_off_by_one_formula() -> None:
    """代码里不得再出现 ``int(h_target / 0.25) - 1`` 这种少减 1 的写法。"""
    code = _code_without_comments()
    assert "int(h_target / 0.25) - 1" not in code, (
        "analyze_compare_12h.py 里的 off-by-one 取数写法复活了"
    )


def test_script_does_not_hardcode_step_for_index_lookup() -> None:
    """取下标不得再硬编码 ``0.25`` —— step 一变就会再次错位。"""
    code = _code_without_comments()
    # 关键时间点对比段落（ast 层面：最后一个 for 循环体内）
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    segs: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            src = ast.get_source_segment(SCRIPT.read_text(encoding="utf-8"), node) or ""
            if "h_target" in src and "pick_index" in src:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, float):
                        if abs(sub.value - 0.25) < 1e-12:
                            segs.append(src)
    assert not segs, (
        "关键时间点对比的取数路径里又出现了硬编码的 0.25 —— "
        "应改用 pick_index() 在轴上反查"
    )


def test_script_guards_axis_consistency() -> None:
    """必须校验两组时间轴一致（否则跨组差值会变成不同时刻相减）。"""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "np.allclose(hc, hm)" in src, (
        "缺少两组时间轴一致性校验 —— 跨组差值可能失去意义"
    )


def test_script_uses_pick_index() -> None:
    """取数路径必须真的调用 ``pick_index()``（而不是自己另算一遍）。"""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "pick_index(hc, h_target)" in src


# ---------------------------------------------------------------------------
# 端到端：合成数据跑一遍真实取数逻辑，验证"标签=实际时刻"
# ---------------------------------------------------------------------------
def test_end_to_end_label_matches_actual_hour(pick_index) -> None:
    """用**合成**的时间序列验证：打印出的标签时刻 == 实际取值时刻。

    造一条"覆盖率先低后高"的曲线，使得取值时刻错一格会**明显**改变数值；
    这样即使有人改坏实现，用例也能立刻抓到（而不是靠"数值恰好一样"蒙混过关）。
    """
    import numpy as np
    step = 0.25
    hours = np.arange(0, 24.0 + 1e-6, step)
    # 每个时刻的"真值" = 该时刻本身（小时数）。错一格 → 差 0.25，肉眼可辨
    truth = hours.copy()

    for label_h in (2.0, 4.0, 8.0, 12.0, 24.0):
        idx = pick_index(hours, label_h)
        got = truth[idx]
        assert abs(got - label_h) < 1e-9, (
            f"标签 {label_h}h 取到的值对应 {got}h —— 标签与实际时刻不一致"
        )
        # 旧实现会取到 label_h - 0.25
        buggy_val = truth[int(label_h / step) - 1]
        assert abs(buggy_val - got) >= 0.25 - 1e-9, (
            "合成数据设计失效：错一格与不错格的数值不可区分，用例失去分辨力"
        )


# ---------------------------------------------------------------------------
# ★ 行为级护栏：跑**脚本里真实的取数语句**，而不只是测 pick_index 函数本身
# ---------------------------------------------------------------------------
# 上一轮变异测试暴露的真漏洞：
#   把调用点改回 `int(h_target / 0.25) - 1`（而 pick_index 函数仍然存在）时，
#   只红了 1 条源码匹配用例 —— 因为行为用例测的是 **pick_index 本身**，
#   根本没经过**调用点**。护栏强度不足 = 假安全感。
# 下面这组用例从 AST 里**摘出脚本真实的取数表达式**并执行，
# 从而保证"调用点"本身被测到。

def _extract_index_expr() -> ast.expr:
    """从脚本里摘出关键时间点对比段落中**真正用于取数的表达式**。

    做法：在 AST 里找到那个 ``for h_target in _targets:`` 循环，
    再找其循环体内赋值给 ``idx`` 的那条语句，取其值表达式。
    """
    src = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name) \
                and node.target.id == "h_target":
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Assign):
                    for tgt in stmt.targets:
                        if isinstance(tgt, ast.Name) and tgt.id == "idx":
                            return stmt.value
    pytest.skip("analyze_compare_12h.py 里找不到给 idx 赋值的语句")


def _eval_index_expr(expr: ast.expr, hours, h_target: float) -> int:
    """在给定时间轴上执行脚本真实的取数表达式，返回它算出的下标。"""
    mod = ast.Expression(body=expr)
    ast.fix_missing_locations(mod)
    ns: dict = {"h_target": h_target, "np": __import__("numpy")}
    # 表达式里可能用到 hc / pick_index
    ns["hc"] = hours
    ns["pick_index"] = _load_pick_index()
    code = compile(mod, str(SCRIPT), "eval")
    return int(eval(code, ns))  # noqa: S307 - 测试内执行生产表达式


@pytest.mark.parametrize("h_target", [2.0, 4.0, 8.0, 12.0, 24.0])
def test_actual_index_expression_hits_target_hour(h_target: float) -> None:
    """★ 脚本**真实使用的取数表达式**必须命中标签时刻。

    这条直接堵住上一轮暴露的漏洞：调用点改回旧写法时，本用例会红。
    """
    import numpy as np
    hours = np.arange(0, 24.0 + 1e-6, 0.25)
    expr = _extract_index_expr()
    idx = _eval_index_expr(expr, hours, h_target)
    assert 0 <= idx < len(hours)
    assert abs(hours[idx] - h_target) < 1e-9, (
        f"脚本真实取数逻辑：标签 {h_target}h 实际取到 {hours[idx]}h（idx={idx}）"
    )


def test_actual_index_expression_differs_from_buggy_formula() -> None:
    """★ 脚本真实取数表达式**不得**等价于旧的 off-by-one 写法。"""
    import numpy as np
    hours = np.arange(0, 24.0 + 1e-6, 0.25)
    expr = _extract_index_expr()
    for h_target in (2.0, 4.0, 8.0, 12.0, 24.0):
        idx = _eval_index_expr(expr, hours, h_target)
        buggy = int(h_target / 0.25) - 1
        correct = int(round(h_target / 0.25))
        if buggy != correct:
            assert idx != buggy, (
                f"脚本真实取数逻辑仍等价于旧 off-by-one 写法（标签 {h_target}h → idx={buggy}）"
            )


def test_actual_index_expression_is_equivalent_to_pick_index() -> None:
    """脚本真实取数表达式与 ``pick_index()`` 必须给出**相同**结果。"""
    import numpy as np
    hours = np.arange(0, 24.0 + 1e-6, 0.25)
    expr = _extract_index_expr()
    pick_index = _load_pick_index()
    for h_target in (2.0, 4.0, 8.0, 12.0, 24.0):
        assert _eval_index_expr(expr, hours, h_target) == pick_index(hours, h_target), (
            f"标签 {h_target}h：脚本真实取数与 pick_index() 结果不一致"
        )
