# -*- coding: utf-8 -*-
"""Windows 单平台 CI：基线文件 fail-closed 语义的回归测试。

背景：`run_guarded_pytest.py` 原先在期望集文件不存在时打印「跳过比对」并继续，
等于 CI 上少了一道门。现在改为：文件缺失即返回 2（BASELINE_MISSING）；
文件存在但只有注释 = 合法的空集合。

这些用例只测解析与判定，不重启整套 pytest 框架。
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = ROOT / "guard" / "run_guarded_pytest.py"

_spec = importlib.util.spec_from_file_location("run_guarded_pytest", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)


def _write(p: pathlib.Path, text: str) -> pathlib.Path:
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def test_comment_only_file_is_empty_set(tmp_path):
    """只有注释 = 合法空集合（表示任何新增都判漂移）。"""
    f = _write(tmp_path / "e.txt", "# 期望 0 条\n# 说明：文件必须存在\n")
    loaded, missing = mod._resolve_baselines([("errors", f)])
    assert missing == []
    assert loaded["errors"] == []


def test_ids_file_parsed_and_comments_skipped(tmp_path):
    f = _write(tmp_path / "f.txt",
               "# 注释\nb::t2\na::t1\n\n# 尾注\na::t1\n")
    loaded, missing = mod._resolve_baselines([("failed", f)])
    assert missing == []
    assert loaded["failed"] == ["a::t1", "b::t2"]      # 去重 + 排序


def test_missing_file_is_reported_not_skipped(tmp_path):
    """缺失必须进 missing 清单，而不是被静默跳过。"""
    f = tmp_path / "nope.txt"
    loaded, missing = mod._resolve_baselines([("failed", f)])
    assert loaded == {}
    assert len(missing) == 1
    assert missing[0][0] == "failed"
    assert missing[0][1].endswith("nope.txt")


def test_partial_missing_records_only_absent(tmp_path):
    ok = _write(tmp_path / "ok.txt", "x::t\n")
    loaded, missing = mod._resolve_baselines(
        [("failed", ok), ("errors", tmp_path / "gone.txt")])
    assert loaded == {"failed": ["x::t"]}
    assert [m[0] for m in missing] == ["errors"]


def test_ci_required_baselines_exist_and_nonempty():
    """CI 依赖的两份基线必须真实存在；windows 的失败集合不能是空文件。"""
    win = ROOT / "guard/baseline/ci_expected_failed_ids_windows.txt"
    err = ROOT / "guard/baseline/ci_expected_errors.txt"
    assert win.is_file(), "windows 基线缺失会让 guarded-pytest 直接失败"
    assert err.is_file(), "errors 基线缺失会让 guarded-pytest 直接失败"
    assert len(mod._read_expected(win)) > 0, "windows 基线不应为空集合"
    assert mod._read_expected(err) == [], "errors 基线语义是「期望 0 条」"


def test_runner_reports_baseline_missing_verdict(tmp_path):
    """结果 JSON 的 verdict 常量与预期一致（防手改字符串）。"""
    src = _SCRIPT.read_text(encoding="utf-8")
    assert '"BASELINE_MISSING"' in src
    assert "return 2" in src
