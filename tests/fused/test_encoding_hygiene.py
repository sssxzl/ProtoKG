# -*- coding: utf-8 -*-
"""tests/fused/test_encoding_hygiene.py —— **编码卫生护栏**（防乱码复发）。

★ 背景（批次 2.5 收尾）
  发现部分 UTF-8 文本在读写或解码环节被按错误字符集解析，产生 mojibake
  （典型症状：U+FFFD 替换符、``\u00c3\u00a9`` 双重编码、``\u00e6\u2014\u00b6`` 错位、
  U+26B6 之类的孤立符号）。实测根因有两类：

  ① **读时用错字符集**（我们弄坏的，可逆还原）
     文件以 latin-1/cp1252 读入、再以 UTF-8 写出 ⇒ 字节层面
     ``b"\\xc3\\x83\\xc2\\xa1"``（= ``Mih\\u00c3\\u00a1ly``）⇒ 可按 UTF-8 往返还原。
     ★ 实测 kb/ 第三方源码首次入库时即已损坏
       （``Mih\\u00e1ly M\\u00e9sz\\u00e1ros`` → ``Mih\\u00c3\\u00a1ly M\\u00c3\\u00a9sz\\u00c3\\u00a1ros``）。

  ② **上游原生混合编码**（不是我们的缺陷，不可臆测替换）
     kamailio 是 2000 年代老代码库，源码/测试/文档大量 latin-1 注释与作者名。
     ⇒ 「无法确定原文」⇒ **登记豁免、只报告不改**（见
     ``tools/qa/baseline/encoding_known_issues.txt``）。

★ 本测试锁四条不变式
  E1 无 mojibake      —— 仓库文本不得含**可还原**的乱码残留
  E2 无非法 UTF-8     —— 仓库文本须能整体按 UTF-8 解码（豁免清单除外）
  E3 无混合行尾       —— 同一文件不得 CRLF 与裸 LF 混用（跨平台换行不一致）
  E4 读写显式编码     —— 文本读写调用必须显式 ``encoding="utf-8"``
                        （Windows 默认走 locale 编码 cp936 ⇒ 换机器就炸）

★ 与护栏的关系
  实际检查逻辑在 ``tools/qa/verify_encoding.py``（可独立跑、可 ``--fix``）；
  本测试是它的**pytest 封装**⇒ 进 ``run_guarded_pytest.py`` 的失败集合比对
  ⇒ 任何新增乱码都会让护栏变红。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "tools" / "qa" / "verify_encoding.py"


def _run_verifier() -> dict:
    """跑编码护栏，返回其 JSON 结果（失败则抛 AssertionError 带明细）。"""
    assert VERIFIER.is_file(), f"编码护栏脚本缺失: {VERIFIER}"
    out = ROOT / "local" / "encoding_guard_result.json"
    proc = subprocess.run(
        [sys.executable, str(VERIFIER), "--json", str(out)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
    )
    if not out.is_file():
        raise AssertionError(
            f"编码护栏未产出结果文件（rc={proc.returncode}）\n"
            f"stdout: {proc.stdout[-2000:]}\nstderr: {proc.stderr[-2000:]}")
    import json
    data = json.loads(out.read_text(encoding="utf-8"))
    data["_returncode"] = proc.returncode
    data["_stdout"] = proc.stdout
    return data


def test_encoding_hygiene_no_violations():
    """★ 仓库无编码违规（E1 mojibake / E2 非法 UTF-8 / E3 混合行尾 / E4 缺 encoding）。

    ★ 上游原生 latin-1 文件已在 ``tools/qa/baseline/encoding_known_issues.txt``
      登记豁免（可审计）⇒ 不算违规，但会被护栏**列出**。
    """
    data = _run_verifier()
    real = [v for v in data["violations"] if not v["code"].endswith("-exempt")]
    assert not real, (
        f"编码违规 {len(real)} 项：\n"
        + "\n".join(f"  [{v['code']}] {v['path']} — {v['detail']}" for v in real[:20])
        + f"\n（完整清单见 {ROOT / 'local' / 'encoding_guard_result.json'}）\n"
        + "修复命令：python tools/qa/verify_encoding.py --fix"
    )


def test_encoding_guard_covers_kb_third_party():
    """★ kb/ 第三方源码的乱码已被登记豁免（**不是**默默放过）。

    ⇒ 校验「可还原的 mojibake」在 kb/ 里为 0：那是我们拷贝时弄坏的，必须修。
    ⇒ 「上游原生 latin-1」允许存在，但必须**登记**在豁免清单里。
    """
    known = (ROOT / "tools" / "qa" / "baseline" / "encoding_known_issues.txt")
    assert known.is_file(), f"豁免清单缺失: {known}"
    listed = set()
    for line in known.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        listed.add(line.split("\t")[0].strip())

    data = _run_verifier()
    kb_mojibake = [v for v in data["violations"]
                   if v["path"].startswith("kb/") and v["code"] == "E1"]
    assert not kb_mojibake, (
        "kb/ 下仍有**可还原**的 mojibake（属我们拷贝时损坏，必须还原）：\n"
        + "\n".join(f"  {v['path']} — {v['detail']}" for v in kb_mojibake))

    kb_e2 = [v for v in data["violations"]
             if v["path"].startswith("kb/") and v["code"] == "E2"]
    for v in kb_e2:
        assert v["path"] in listed, (
            f"kb/ 的上游原生非 UTF-8 文件未登记豁免: {v['path']}\n"
            f"（要么修复，要么在 tools/qa/baseline/encoding_known_issues.txt 登记原因）")


def test_own_code_uses_explicit_utf8():
    """★ 我们自己维护的代码（core/ scripts/ tools/ tests/）**零**编码违规。

    ⇒ kb/ 第三方素材可豁免；**我们的**代码不行。
    """
    data = _run_verifier()
    ours = [v for v in data["violations"]
            if not v["code"].endswith("-exempt")
            and (v["path"].startswith("core/") or v["path"].startswith("scripts/")
                 or v["path"].startswith("tools/") or v["path"].startswith("tests/"))]
    assert not ours, (
        f"自有代码编码违规 {len(ours)} 项：\n"
        + "\n".join(f"  [{v['code']}] {v['path']} — {v['detail']}" for v in ours[:20]))
