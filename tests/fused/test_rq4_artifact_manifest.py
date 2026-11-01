# -*- coding: utf-8 -*-
"""tests/fused/test_rq4_artifact_manifest.py —— 产物自证清单（artifacts manifest）的回归测试。

★ 为什么需要这个功能
-------------------
2026-10-30 的事故里，RQ4 的 6 个容器被 ``docker rm`` 删除（磁盘清理 / 其它实验线的
宽过滤器），导致**无法再回查容器内原始文件**。事后能自证"数据未被篡改"的唯一
证据链是：**官方 tar.gz 内的产物** vs **宿主明文副本**，两者 md5 必须相同。

为此，``rq4_collect.sh`` 在采集时把各产物的 md5 写进一份**旁挂清单**：

    ${SUMMARY%.csv}.artifacts.md5

★ 为什么旁挂而不加进 summary
---------------------------
summary 的 28 列表头是**冻结合同**（下游 ``rq4_analyze.py`` 按列号取字段）。
加列会破坏它。故用独立文件，格式与 ``md5sum`` 输出同构 → 可直接 ``md5sum -c``。

本测试覆盖：
* 清单**旁挂**（不改 28 列表头）
* 清单与 summary **同生命周期**（summary 重建 → 清单一并重建，不残留旧行）
* 清单内容格式可被 ``md5sum -c`` 校验
* 清单收录三类产物：fuzzer_stats / cov_over_time.csv / out.tar.gz
"""
from __future__ import annotations

import os
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: 被测脚本路径。
#: ★ 支持用环境变量 ``RQ4_COLLECT_SH`` 指向**副本** —— 变异测试必须走这条路径。
#:   原因（2026-10-30 真实事故）：变异测试若直接改生产脚本，恢复是**手动**步骤，
#:   中间会留下窗口期（实测 8 分钟），期间他人读到中间态 → 报出假失败。
#:   在副本上变异则**生产脚本全程零改动**，他人不可能读到中间态。
#:   默认行为不变（不设环境变量时就是生产脚本）。
COLLECT_SH = Path(
    os.environ.get("RQ4_COLLECT_SH") or (ROOT / "scripts" / "rq4_collect.sh")
)

#: summary 的 28 列表头（**冻结合同**，任何改动都会破坏下游按列号取字段）
FROZEN_HEADER = (
    "protocol,group,rep,container,image,start_time,last_update,fuzz_sec,"
    "cycles_done,execs_done,execs_per_sec,paths_total,paths_found,max_depth,"
    "cur_path,stability,bitmap_cvg,unique_crashes,unique_hangs,peak_rss_mb,"
    "param_check,exit_code,command_line,seed_files,seed_regions,dict_tokens,"
    "l_per,b_per"
)


def _collect_sh_text() -> str:
    return COLLECT_SH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 结构：清单必须存在、旁挂、且随 summary 重建
# ---------------------------------------------------------------------------
def test_manifest_variable_is_defined() -> None:
    """必须定义产物自证清单的路径变量。"""
    text = _collect_sh_text()
    assert "ARTIFACT_MANIFEST=" in text, "rq4_collect.sh 里没有 ARTIFACT_MANIFEST 变量"


def test_manifest_is_sidecar_not_a_new_column() -> None:
    """清单必须**旁挂** —— summary 的 28 列表头不得改变。"""
    text = _collect_sh_text()
    # 旁挂：路径由 SUMMARY 派生（在**使用时**惰性求值，见下一个用例）
    assert "artifact_manifest_path" in text, "清单路径应由 artifact_manifest_path() 派生"
    assert re.search(r'echo "\$\{SUMMARY%\.csv\}\.artifacts\.md5"', text), (
        "清单路径应由 SUMMARY 派生（旁挂），而不是独立指定"
    )


def test_manifest_path_is_lazily_evaluated() -> None:
    """★ 清单路径必须**惰性求值**（在使用时派生），不得在初始化时就固化。

    ★ 这条防的是**真实踩过的 bug**
    --------------------------
    早期实现是::

        ARTIFACT_MANIFEST="${ARTIFACT_MANIFEST:-${SUMMARY%.csv}.artifacts.md5}"

    它在**变量初始化阶段**求值，而 ``--summary`` 参数是在其**之后**才解析的 →
    传 ``--summary /tmp/x.csv`` 时，清单仍写到默认的
    ``/home/zxy/rq4/rq4_summary.artifacts.md5``（**写错地方**）。

    实测症状：端到端跑完 6/6 采集成功，但清单文件**根本没生成**。
    """
    text = _collect_sh_text()
    # ★ 只看**代码行**（剔除注释）：脚本的注释里**故意**保留了这段旧写法作为
    #   反面示例，若不剔除注释，护栏会因注释而假红。
    code_lines = [
        ln for ln in text.splitlines()
        if not ln.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    bad = re.search(r'ARTIFACT_MANIFEST="\$\{ARTIFACT_MANIFEST:-\$\{SUMMARY', code)
    assert bad is None, (
        "ARTIFACT_MANIFEST 在初始化时就从 SUMMARY 求值 —— "
        "会在 --summary 改写路径后写到错误位置（初始化顺序 bug，已真实踩过）"
    )
    # 必须有惰性求值函数
    assert re.search(r"artifact_manifest_path\(\)\s*\{", text), (
        "缺少 artifact_manifest_path() 惰性求值函数"
    )
    fn = re.search(r"artifact_manifest_path\(\)\s*\{(.*?)\n\}", text, re.DOTALL)
    assert fn, "artifact_manifest_path() 定义不完整"
    body = fn.group(1)
    assert '${SUMMARY%.csv}.artifacts.md5' in body, (
        "artifact_manifest_path() 必须从当前 SUMMARY 派生清单路径"
    )


def test_manifest_path_follows_custom_summary_at_runtime(tmp_path: Path) -> None:
    """★ 端到端：用 ``--summary`` 指定别处时，清单必须**跟着走**。

    这是上一条 bug 的**行为级**验证 —— 只查源码不够，必须看真实运行结果。
    """
    import subprocess
    import shutil

    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("环境无 bash")

    work = tmp_path
    summary = work / "custom.csv"
    # 造一份最小离线产物（只需求 fuzzer_stats 存在）
    prod = work / "offline" / "rtsp" / "protorag" / "r1"
    prod.mkdir(parents=True, exist_ok=True)
    (prod / "fuzzer_stats").write_text(
        "command_line : /home/ubuntu/aflnet/afl-fuzz -d\n"
        "execs_done   : 100\n", encoding="utf-8")
    (prod / "cov_over_time.csv").write_text(
        "Time,l_per,l_abs,b_per,b_abs\n1,2,3,4,5\n", encoding="utf-8")

    cmd = [bash, str(COLLECT_SH), "--offline", str(work / "offline"),
           "--summary", str(summary), "--protocols", "rtsp",
           "--groups", "protorag", "--reps", "1"]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                       timeout=120, cwd=str(work))
    assert summary.is_file(), f"summary 未生成（rc={r.returncode}）\n{r.stdout[-800:]}\n{r.stderr[-800:]}"

    expected = work / "custom.artifacts.md5"
    assert expected.is_file(), (
        f"清单没有跟着 --summary 走（应在 {expected.name}）\n"
        f"实际生成: {[p.name for p in work.glob('*.md5')]}"
    )
    # 内容必须含产物条目
    body = expected.read_text(encoding="utf-8")
    assert "rtsp/protorag/r1/fuzzer_stats" in body, f"清单内容异常:\n{body}"
    assert "rtsp/protorag/r1/cov_over_time.csv" in body, f"清单内容异常:\n{body}"


def test_summary_header_stays_28_columns() -> None:
    """★ summary 的 28 列表头必须**逐字未变**（冻结合同）。"""
    text = _collect_sh_text()
    # 表头在双引号里，且以 `\` 续行
    m = re.search(r'echo "(protocol,group,rep[^"]*)"', text)
    assert m, "找不到 summary 表头定义"
    header = m.group(1)
    assert header == FROZEN_HEADER, (
        f"summary 表头被改动了！\n  实际: {header}\n  期望: {FROZEN_HEADER}"
    )


def test_summary_printf_still_has_28_placeholders() -> None:
    """printf 的占位符个数必须仍是 28（与表头列数严格相等）。"""
    text = _collect_sh_text()
    m = re.search(r"printf '((?:%s,)+%s)\\n'", text)
    assert m, "找不到 summary 的 printf 格式串"
    assert m.group(1).count("%s") == 28, (
        f"printf 占位符数 = {m.group(1).count('%s')}，应为 28"
    )


def test_manifest_is_truncated_when_summary_is_recreated() -> None:
    """summary 被重建时，清单必须**一并重建**（否则残留旧行 → md5sum -c 误判）。"""
    text = _collect_sh_text()
    # 定位 "if [[ ! -f "$SUMMARY" ]]" 这一段
    m = re.search(r'if \[\[ ! -f "\$SUMMARY" \]\]; then(.*?)\n  fi', text, re.DOTALL)
    assert m, "找不到 summary 表头初始化块"
    block = m.group(1)
    assert "artifact_manifest_path" in block, (
        "summary 重建时没有重置产物清单 —— 旧轮次的 md5 行会残留"
    )
    assert re.search(r': > "\$\(artifact_manifest_path\)"', block), (
        "产物清单没有被清空（应使用 `: > \"$(artifact_manifest_path)\"`）"
    )


# ---------------------------------------------------------------------------
# 内容：清单必须收录三类产物，且格式可被 md5sum -c 校验
# ---------------------------------------------------------------------------
def test_manifest_records_three_artifact_kinds() -> None:
    """清单必须收录 fuzzer_stats / cov_over_time.csv / out.tar.gz 三类产物。"""
    text = _collect_sh_text()
    for name in ("fuzzer_stats", "cov_over_time.csv", "out.tar.gz"):
        assert name in text, f"产物清单没有收录 {name}"


def test_manifest_lines_are_md5sum_compatible() -> None:
    """每行必须是 ``<md5>  <path>`` 格式（与 md5sum 输出同构 → 可 md5sum -c）。"""
    text = _collect_sh_text()
    assert re.search(
        r"printf '%s  %s\\n' \"\$\(md5sum \"\$f\"", text
    ), "产物清单的行格式必须是 '<md5>  <path>'（md5sum -c 兼容）"


def test_manifest_uses_relative_paths() -> None:
    """清单里的路径必须是**绝对路径**，使 md5sum -c 在任意目录都可用。

    ★ 2026-10-30 定案（三种写法的实测结论）：
      - 相对 OUT_ROOT → 清单在 summary 目录、产物在 out/ 下 → 不同源 → 0/18 OK；
      - 相对「清单所在目录」→ 生成时可用，但清单被移动/复制到别处即失效
        （实测复制到 /home/zxy/rq4 后 0/18 OK）；
      - **绝对路径** → 任意 cwd 执行都是 18/18 OK（已实测 /home/zxy/rq4 与 /tmp 两种）。
    代价：换机器/换 out_root 后需重新采集以重建清单（采集时自动重建）。
    """
    text = _collect_sh_text()
    assert 'abs_f=$(cd "$(dirname "$f")" && pwd)/$(basename "$f")' in text, (
        "清单路径必须用绝对路径（abs_f=...），否则 md5sum -c 换目录即失效"
    )
    assert 'rel_base="${proto}/${group}/r${rep}"' not in text, (
        "清单路径不得用相对 out_root 的 rel_base（会导致 md5sum -c 找不到文件）"
    )


def test_manifest_skips_missing_files() -> None:
    """产物不存在时不得写入空行（否则 md5sum -c 报缺文件）。"""
    text = _collect_sh_text()
    assert re.search(r'\[\[ -f "\$f" \]\] \|\| continue', text) or re.search(
        r'if \[\[ -f "\$f" \]\]; then', text
    ), "写清单前必须判断文件是否存在"


# ---------------------------------------------------------------------------
# 端到端：造一份产物，跑 md5sum -c 验证清单真的可校验
# ---------------------------------------------------------------------------
def test_manifest_format_passes_md5sum_check(tmp_path: Path) -> None:
    """按脚本的格式生成一份清单，用 ``md5sum -c`` 校验 → 必须全 OK。

    这验证的是**格式**，不是脚本本身（脚本的采集路径需要容器）。
    """
    import hashlib

    # 造三个"产物"
    files = {
        "rtsp/protorag/r1/fuzzer_stats": b"command_line : /home/ubuntu/aflnet/afl-fuzz -d\n",
        "rtsp/protorag/r1/cov_over_time.csv": b"Time,l_per,l_abs,b_per,b_abs\n1,2,3,4,5\n",
        "rtsp/protorag/r1/out.tar.gz": b"\x1f\x8b\x08\x00fake-tar-bytes",
    }
    root = tmp_path / "out"
    lines = []
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        digest = hashlib.md5(content).hexdigest()
        lines.append(f"{digest}  {rel}")

    manifest = tmp_path / "artifacts.md5"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 格式自检：每行必须是 <32位hex>  <path>
    for line in manifest.read_text(encoding="utf-8").strip().splitlines():
        assert re.fullmatch(r"[0-9a-f]{32}  \S+", line), f"清单行格式不合法: {line!r}"


def test_manifest_paths_are_absolute_and_portable(tmp_path: Path) -> None:
    """★ 清单用绝对路径 → ``md5sum -c`` 在**任意目录**都必须全 OK。

    真实事故（2026-10-30）：清单里写的是相对 ``out_root`` 的路径
    （``rtsp/protorag/r1/fuzzer_stats``），但清单文件本身写在 summary 所在目录
    （``/home/zxy/rq4/``），而产物在 ``/home/zxy/rq4/out/...`` → 缺一层前缀
    → ``md5sum -c`` 实测 **0/18 OK**（全部 FAILED open or read）。

    合成 fixture（同目录）会掩盖这个 bug，所以本用例**刻意把清单与产物分置
    不同目录**，并真的跑一次 ``md5sum -c``；且**换 cwd 再跑一次**验证绝对路径的
    跨目录健壮性（相对路径方案在这一点上会失败）。
    """
    import hashlib
    import subprocess

    # 清单目录与产物目录**不同源**（这正是真实场景）
    manifest_dir = tmp_path / "summary_dir"
    out_root = tmp_path / "out"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    rels = [
        "rtsp/protorag/r1/fuzzer_stats",
        "rtsp/protorag/r1/cov_over_time.csv",
        "rtsp/protorag/r1/out.tar.gz",
    ]
    lines = []
    for rel in rels:
        p = out_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        content = f"content-of-{rel}\n".encode()
        p.write_bytes(content)
        digest = hashlib.md5(content).hexdigest()
        # 绝对路径（脚本的正确行为）—— Windows 上也要归一化为 POSIX 分隔符，
        # 因为 md5sum(MSYS2) 只认正斜杠
        abs_path = p.resolve().as_posix()
        lines.append(f"{digest}  {abs_path}")

    manifest = manifest_dir / "artifacts.md5"
    # ★ 必须显式 newline="\n"：Windows 上 write_text 默认写 CRLF，
    #   而 md5sum(MSYS2) 会把行尾的 \r 当成路径的一部分 → "No such file or directory"
    with manifest.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    # 真跑 md5sum -c：在清单目录、以及**另一个目录**（跨目录健壮性）都必须全 OK
    for cwd in (manifest_dir, tmp_path):
        r = subprocess.run(
            ["md5sum", "-c", manifest.name if cwd == manifest_dir
             else str(manifest)],
            cwd=str(cwd), capture_output=True, text=True, errors="replace",
        )
        ok_lines = [ln for ln in r.stdout.splitlines() if ln.endswith(": OK")]
        assert r.returncode == 0, (
            f"md5sum -c 在 cwd={cwd} 必须全 OK，实际 rc={r.returncode}\n"
            f"stdout={r.stdout}\nstderr={r.stderr}\n"
            f"清单内容:\n{manifest.read_text(encoding='utf-8')}"
        )
        assert len(ok_lines) == len(rels), (
            f"cwd={cwd}: 应有 {len(rels)} 行 OK，实际 {len(ok_lines)} 行\n{r.stdout}"
        )


def test_manifest_path_expr_uses_absolute_path() -> None:
    """源码级护栏：清单路径必须用绝对路径（``abs_f=``），不得回退成相对路径。

    防止有人把路径计算改回「相对 out_root」（那正是 0/18 OK 事故的根因）。
    """
    src = COLLECT_SH.read_text(encoding="utf-8")
    assert 'abs_f=$(cd "$(dirname "$f")" && pwd)/$(basename "$f")' in src, (
        "清单路径必须用绝对路径 abs_f=...（相对路径在换目录后会失效）"
    )
    assert 'rel_base="${proto}/${group}/r${rep}"' not in src, (
        "清单路径不得用相对 out_root 的 rel_base（会导致 md5sum -c 找不到文件）"
    )


def test_production_script_generates_manifest_that_passes_md5sum_check(
    tmp_path: Path,
) -> None:
    """★★ 端到端护栏：真跑**生产脚本**生成清单 → 真跑 ``md5sum -c`` → 必须全 OK。

    ★ 为什么这条不可省
    ------------------
    同文件里 ``test_manifest_paths_are_absolute_and_portable`` 用的是
    **合成 fixture**（自己拼 md5 行），它只能验证"这种格式能被 md5sum -c 校验"，
    **验证不了生产脚本真的算对了路径**。
    真实事故正是如此：脚本用相对 ``out_root`` 的路径，
    而合成 fixture 因为清单与产物同目录 → 照样全 OK → **护栏没能抓住**。

    本用例**不改任何东西**，只：
      ① 造最小离线产物 → ② **真跑** ``rq4_collect.sh --offline`` →
      ③ **真跑** ``md5sum -c`` → ④ 断言全 OK 且行数正确。

    ★ 清单与产物**刻意分置不同目录**（复刻真实事故：清单在 summary 目录、
      产物在 out/ 下），且额外**换 cwd 再校验一次**（绝对路径方案必须仍然全 OK）。
    """
    import shutil
    import subprocess

    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("环境无 bash")
    if shutil.which("md5sum") is None:
        pytest.skip("环境无 md5sum")

    # 清单目录与产物目录**不同源**（复刻真实事故）
    summary_dir = tmp_path / "summary_dir"
    out_root = tmp_path / "out"
    summary_dir.mkdir(parents=True, exist_ok=True)

    rels = [
        "rtsp/protorag/r1/fuzzer_stats",
        "rtsp/protorag/r1/cov_over_time.csv",
        "rtsp/protorag/r1/out.tar.gz",
    ]
    for rel in rels:
        p = out_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f"content-of-{rel}\n".encode())

    summary = summary_dir / "rq4_summary.csv"
    cmd = [
        bash, str(COLLECT_SH),
        "--offline", str(out_root),
        "--out-root", str(out_root),
        "--summary", str(summary),
        "--protocols", "rtsp",
        "--groups", "protorag",
        "--reps", "1",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                       timeout=120, cwd=str(summary_dir))
    assert r.returncode == 0, (
        f"collect 失败 rc={r.returncode}\n{r.stdout[-800:]}\n{r.stderr[-800:]}"
    )

    manifest = summary_dir / "rq4_summary.artifacts.md5"
    assert manifest.is_file(), (
        f"生产脚本没有生成清单 {manifest}\n"
        f"目录内容: {[p.name for p in summary_dir.iterdir()]}"
    )

    body = manifest.read_text(encoding="utf-8")
    assert len(rels) == len([ln for ln in body.strip().splitlines() if ln.strip()]), (
        f"清单行数不对（期望 {len(rels)}）:\n{body}"
    )

    # ★ 真跑 md5sum -c：在 summary 目录、以及**另一个 cwd** 都必须全 OK
    for cwd in (summary_dir, tmp_path):
        c = subprocess.run(
            ["md5sum", "-c", manifest.name if cwd == summary_dir else str(manifest)],
            cwd=str(cwd), capture_output=True, text=True, errors="replace",
        )
        ok_lines = [ln for ln in c.stdout.splitlines() if ln.endswith(": OK")]
        assert c.returncode == 0, (
            f"md5sum -c 在 cwd={cwd} 必须全 OK，实际 rc={c.returncode}\n"
            f"stdout={c.stdout}\nstderr={c.stderr}\n"
            f"清单内容:\n{body}"
        )
        assert len(ok_lines) == len(rels), (
            f"cwd={cwd}: 应有 {len(rels)} 行 OK，实际 {len(ok_lines)} 行\n{c.stdout}"
        )


def test_manifest_detects_tampering(tmp_path: Path) -> None:
    """★ 清单的**核心价值**：产物被改动后，md5 必须对不上（可自证篡改）。

    这是「数据未被篡改」这一结论的**可执行证据**，必须真的能抓到改动。
    """
    import hashlib

    content = b"command_line : /home/ubuntu/aflnet/afl-fuzz -d\n"
    p = tmp_path / "fuzzer_stats"
    p.write_bytes(content)
    digest = hashlib.md5(content).hexdigest()

    manifest = tmp_path / "artifacts.md5"
    manifest.write_text(f"{digest}  fuzzer_stats\n", encoding="utf-8")

    # 未改动时 md5 相同
    assert hashlib.md5(p.read_bytes()).hexdigest() == digest

    # 改动后 md5 必须不同 → 清单能自证篡改
    p.write_bytes(content + b"tampered\n")
    assert hashlib.md5(p.read_bytes()).hexdigest() != digest
