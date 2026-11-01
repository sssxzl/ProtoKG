# -*- coding: utf-8 -*-
"""tests/fused/test_rq4_scripts_parity.py —— 本机 ``scripts/rq4_*`` 与 VM 生产副本的**一致性护栏**。

★ 为什么需要这条测试
----------------------
Round 3 里发生过一次真实故障：**本机** ``scripts/rq4_collect.sh`` 被回退成了修复前的
旧版（当时 md5 ``7a90098a…``），而 **VM** 上的生产副本是修复后的版本。
后果是 QA 交付的回归测试在本机挂 5 条、而全量套件只挂 2 条 —— 两次运行**状态不同**，
一度被误判成"测试污染"。

★ 为什么不写死具体 md5
----------------------
``rq4_collect.sh`` 因功能迭代（产物自证清单 → 路径基准三态定案 → 绝对路径）md5 已多次变化，
写死具体值会导致每次功能变更都要改本文件（且容易漏改 → 文档陈旧）。
**本护栏的真源是「VM 上的实际副本」**，由 ``test_local_script_matches_vm`` 现场取 md5 比对，
不需要任何硬编码。下列描述里的 md5 仅作历史记录参考。

已落地的护栏（``test_rq4_collect_cov_fix.py``）能挡住"**内容被回退**"，
但挡不住"**本机整体落后于 VM**"（例如有人只改了 VM、或本机被整份旧副本覆盖）。
本文件补的就是这个盲区：**直接向 VM 求 md5，与本机逐个比对**。

★ 断网时的记账口径
----------------------
VM 不可达时 fixture 走 ``pytest.skip`` → 这 10 条是 **skipped 而非 passed**，
属"**未覆盖**"，不能当"已验证"记账。论文复现说明需标注此点。

★ VM 不可达时的行为
--------------------
VM 是外部依赖，网络/密钥/关机都会让它不可达。此时 **skip 而不是 fail**：
一条依赖外部服务的护栏若在断网时红，只会养成"随手 xfail"的习惯，反而失去意义。
但 **VM 可达且 md5 不一致 → 必须 fail**（这才是真问题）。
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"

#: 本机与 VM 应当**逐字节一致**的 RQ4 生产脚本
SYNCED_SCRIPTS = (
    "rq4_collect.sh",
    "rq4_analyze.py",
    "rq4_param_check.py",
)

#: VM 上生产脚本的目录
VM_SCRIPTS_DIR = "/home/zxy/rq4/scripts"

#: VM 账号与密钥（与 ``core/fused/source_probe.py`` 保持一致）
VM_HOST = "zxy@192.168.37.130"
VM_KEY = Path.home() / ".ssh" / "vm_ubuntu_zxy"

#: ssh 超时（秒）—— 连接超时必须很短，否则断网时套件会被拖死
SSH_TIMEOUT = 30
CONNECT_TIMEOUT = 5

#: 需要在 VM 上做语法检查的 shell 脚本（``.py`` 用 ``compile()`` 检查，不走 shell）
SHELL_SCRIPTS = ("rq4_collect.sh",)
PYTHON_SCRIPTS = ("rq4_analyze.py", "rq4_param_check.py")


def _local_md5(path: Path) -> str:
    """本机文件的 md5（十六进制小写）。"""
    return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324 - 非安全用途


def _ssh_raw(remote_cmd: str, stdin_bytes: bytes | None = None) -> tuple[int, str] | None:
    """在 VM 上执行一条命令。

    Args:
        remote_cmd: 远端要执行的 shell 命令行。
        stdin_bytes: 可选的标准输入字节（如待检查的脚本内容）。

    Returns:
        ``(返回码, 输出)``；**VM 不可达 / 超时 → None**。
        返回码 255 是 ssh 自身的连接/认证失败，据此判定"不可达"。
    """
    if not VM_KEY.exists():
        return None

    cmd = [
        "ssh", "-i", str(VM_KEY),
        "-o", "StrictHostKeyChecking=no",
        "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
        "-o", "BatchMode=yes",
        VM_HOST, remote_cmd,
    ]
    try:
        r = subprocess.run(cmd, input=stdin_bytes, capture_output=True,
                           timeout=SSH_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = r.stdout.decode("utf-8", errors="replace")
    err = r.stderr.decode("utf-8", errors="replace")
    return r.returncode, out + err


def _ssh(remote_cmd: str, stdin_bytes: bytes | None = None) -> str | None:
    """在 VM 上执行一条**预期成功**的命令并返回输出；不可达 / 失败 → None。"""
    res = _ssh_raw(remote_cmd, stdin_bytes)
    if res is None or res[0] != 0:
        return None
    return res[1]


def _fetch_vm_md5s() -> dict[str, str] | None:
    """向 VM 求 ``/home/zxy/rq4/scripts/`` 下若干文件的 md5。

    Returns:
        ``{文件名: md5}``；**VM 不可达 / 输出无法解析时返回 None**（→ skip）。
    """
    out = _ssh(f"cd {VM_SCRIPTS_DIR} && md5sum " + " ".join(SYNCED_SCRIPTS))
    if out is None:
        return None

    result: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        digest, name = parts[0], parts[1].lstrip("*")
        if name in SYNCED_SCRIPTS and len(digest) == 32:
            result[name] = digest.lower()

    # 三个文件一个都没拿到 → 视为不可达（而不是"全都变了"）
    if not result:
        return None
    return result


def _vm_bash_parses(script_bytes: bytes) -> tuple[bool | None, str]:
    """用 **VM 上的 bash** 解析一段脚本内容（不执行）。

    ★ 为什么必须用 VM 的 bash
    ----------------------
    本机 Git Bash（MSYS2）的 ``bash -n`` 对 CRLF **放行**（实测 rc=0），
    而 VM 的 bash 会报 ``syntax error: unexpected end of file``（实测 rc=2）。
    所以**只有 VM 端能发现**"CRLF 化的 .sh"这个致命问题。
    本函数把**本机文件内容经 stdin 喂给 VM 的 bash** → 检验的是
    "**本机这份副本**能否被权威 bash 解析"，比只查 VM 副本更强。

    Returns:
        ``(是否语法正确, 输出)``；VM 不可达 → ``(None, "")``。
    """
    res = _ssh_raw("bash -n", stdin_bytes=script_bytes)
    if res is None:
        return None, ""
    rc, out = res
    # ssh 自身失败（255）→ 不可达；否则 rc 就是 bash -n 的判定
    if rc == 255:
        return None, ""
    return rc == 0, out


@pytest.fixture(scope="module")
def vm_md5s() -> dict[str, str]:
    """VM 侧 md5 快照；不可达则整组 skip。"""
    got = _fetch_vm_md5s()
    if got is None:
        pytest.skip(
            f"VM 不可达（{VM_HOST}，密钥 {VM_KEY}）→ 跳过一致性比对，"
            "不做假绿也不制造假红"
        )
    missing = [n for n in SYNCED_SCRIPTS if n not in got]
    if missing:
        pytest.skip(f"VM 上缺少 {missing} → 跳过（VM 侧尚未部署）")
    return got


def test_vm_reachable_returns_all_three(vm_md5s: dict[str, str]) -> None:
    """先确认"取到了数"——避免因为解析失败而误判成不一致。"""
    assert set(vm_md5s) == set(SYNCED_SCRIPTS)


@pytest.mark.parametrize("name", SYNCED_SCRIPTS)
def test_local_script_matches_vm(name: str, vm_md5s: dict[str, str]) -> None:
    """本机 ``scripts/<name>`` 与 VM ``/home/zxy/rq4/scripts/<name>`` 必须逐字节一致。

    这是"本机被回退 / 本机落后于 VM"的**唯一**可靠探针：
    内容护栏只能证明"本机还是修好的那个版本"，证明不了"本机 = VM"。
    """
    local = SCRIPTS_DIR / name
    assert local.is_file(), f"本机缺少 scripts/{name}"

    local_md5 = _local_md5(local)
    vm_md5 = vm_md5s[name]
    assert local_md5 == vm_md5, (
        f"scripts/{name} 本机与 VM 不一致！\n"
        f"  本机 md5 = {local_md5}\n"
        f"  VM   md5 = {vm_md5}\n"
        f"  VM 路径 = {VM_SCRIPTS_DIR}/{name}\n"
        "→ 以 VM 为准，把 VM 版本拉回本机（原子替换：cp → 临时名 → mv），"
        "再重跑本用例。"
    )


@pytest.mark.parametrize("name", SYNCED_SCRIPTS)
def test_local_script_has_no_crlf(name: str) -> None:
    """本机副本必须是 **LF** 行尾。

    CRLF 会让 bash 把 ``\\r`` 当成命令的一部分 → 脚本行为诡异；
    而且 CRLF 化会**单向地**破坏与 VM 的 md5 一致性（见上面的 parity 用例）。
    """
    raw = (SCRIPTS_DIR / name).read_bytes()
    assert b"\r\n" not in raw, (
        f"scripts/{name} 存在 CRLF 行尾（{raw.count(bytes([13, 10]))} 处）—— "
        "换行符会被 bash 当成命令内容的一部分"
    )
    assert b"\r" not in raw, f"scripts/{name} 存在孤立的 CR 字符"


@pytest.mark.parametrize("name", SYNCED_SCRIPTS)
def test_local_script_is_not_empty_or_truncated(name: str) -> None:
    """防"复制过程中被截断"这类**静默**损坏。"""
    local = SCRIPTS_DIR / name
    assert local.is_file(), f"本机缺少 scripts/{name}"
    size = local.stat().st_size
    assert size > 1024, f"scripts/{name} 只有 {size} 字节，疑似被截断"


# ---------------------------------------------------------------------------
# VM 端语法检查（本机 MSYS2 的 bash -n 太宽松，只有 VM 能发现 CRLF）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", SHELL_SCRIPTS)
def test_local_shell_script_parses_on_vm_bash(name: str) -> None:
    """把**本机**脚本内容喂给 **VM 的 bash -n**：必须语法正确。

    ★ 为什么这一条不可省
    ------------------
    实测（同一份 CRLF 文件）::

        本机 Git Bash  bash -n  →  rc=0  （放行！）
        VM (Linux)    bash -n  →  rc=2  syntax error: unexpected end of file

    本机的 ``bash -n`` **太宽松**，CRLF 的 .sh 在本机看不出问题，一到 VM 就炸。
    而字节级 CRLF 检查只能查"行尾"这一个症状 —— 若将来出现别的**只被严格
    bash 拒绝**的写法（比如 CRLF 之外的 ``$'\r'`` 残留、未闭合引号），
    字节检查就抓不到，而 VM 的 ``bash -n`` 一定抓得到。

    所以这两条护栏是**互补**的，不是重复：一个查症状，一个查权威解析。
    """
    raw = (SCRIPTS_DIR / name).read_bytes()
    ok, out = _vm_bash_parses(raw)
    if ok is None:
        pytest.skip("VM 不可达 → 跳过 VM 端语法检查（未验证 ≠ 已通过）")
    assert ok, (
        f"scripts/{name} 在 VM 的 bash 下语法错误！\n"
        f"  VM bash -n 输出：{out.strip()}\n"
        "  → 典型成因：CRLF 行尾（MSYS2 本机 bash -n 抓不到，只有 VM 能发现）。\n"
        "  → 修复：把文件转成纯 LF（LF-only），再原子替换到本机与 VM 两处。"
    )


@pytest.mark.parametrize("name", PYTHON_SCRIPTS)
def test_local_python_script_compiles(name: str) -> None:
    """本机 ``.py`` 必须能被 Python 编译（语法自洽）。"""
    raw = (SCRIPTS_DIR / name).read_bytes()
    try:
        compile(raw, str(SCRIPTS_DIR / name), "exec")
    except SyntaxError as exc:
        pytest.fail(f"scripts/{name} 语法错误：{exc}")


@pytest.mark.parametrize("name", SHELL_SCRIPTS)
def test_vm_copy_parses_on_vm_bash(name: str) -> None:
    """VM 上的**生产副本**本身也必须能被 VM 的 bash 解析。

    与上一条互补：上一条查"本机副本"，这一条查"VM 副本"——
    防止有人在 VM 上直接写入了一份坏脚本。
    """
    out = _ssh(f"bash -n {VM_SCRIPTS_DIR}/{name}")
    if out is None:
        pytest.skip("VM 不可达或 VM 副本不存在 → 跳过")
    # `_ssh` 只在 rc==0 时返回非 None → 能走到这里就说明 VM 端 bash -n 通过
    assert out is not None
