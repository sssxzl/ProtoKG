# -*- coding: utf-8 -*-
"""scripts/rq4_verify_seeds.py —— RQ4 种子语料结构自检（本地侧）。

在同步到 VM 之前，本地先自检一遍种子是否满足 RQ4 实验的前提：

  1. **CRLF 行尾**：AFLNet 的协议分区器按 ``\\r\\n`` 切消息（``extract_requests_sip``
     逐字节比对 0x0D 0x0A）。种子若被 Windows→Linux 传输时转成 LF，分区器会
     把整条种子当成一个 region → 状态机无法推进。
  2. **AFLNet 分区数**：复刻 ``aflnet.c`` 的分区逻辑（按协议），算出「有效分区数」，
     与「消息数」比对，确认消息边界没被破坏。
  3. **RTSP 会话可播性**：种子里引用的会话名必须都在目标环境的可播清单内
     （``rtsp_playable_streams.json``）——否则服务端返 404，47.9% 的状态变更请求打空。
  4. **SIP 方法可识别性**：每条消息必须以 AFLNet 识别的方法开头
     （REGISTER/INVITE/ACK/BYE），否则会被并入前一条消息。
  5. **条数与 MD5 清单**：与 ``MANIFEST.md5`` 逐条比对（scp 传输完整性）。

用法:
    python scripts/rq4_verify_seeds.py --seed-dir derived/seeds/rtsp/rq4_B
    python scripts/rq4_verify_seeds.py --all      # 校验 RQ4 三协议全部种子目录
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import paths  # noqa: E402

# ★ region 计数是"种子形状"的度量，必须与 AFLNet 真实分区器逐字节一致 →
#   统一实现放在 rq4_seed_profile.py（唯一真源），本文件与 rq4_collect.sh 共用，
#   避免两处实现漂移（历史教训：两处各写一遍分区逻辑，计数会悄悄对不上）。
from scripts.rq4_seed_profile import (  # noqa: E402
    AFLNET_SIP_BOUNDARY_METHODS,
    count_rtsp_regions,
    count_sip_regions,
)

#: 一条 SIP 报文的请求行首 token（用于判定"消息起点"）
_SIP_REQUEST_LINE = re.compile(
    r"^(REGISTER|INVITE|ACK|BYE|CANCEL|OPTIONS|SUBSCRIBE|NOTIFY|PUBLISH|INFO"
    r"|REFER|MESSAGE|PRACK|UPDATE)\s", re.MULTILINE)

#: RTSP 请求行首 token
_RTSP_REQUEST_LINE = re.compile(
    r"^(OPTIONS|DESCRIBE|SETUP|PLAY|PAUSE|TEARDOWN|GET_PARAMETER|SET_PARAMETER)\s",
    re.MULTILINE)


class VerifyError(Exception):
    """自检失败（携带可读的原因）。"""


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def check_crlf(path: Path) -> None:
    """★ 断言：种子用 CRLF 行尾（不含裸 LF）。"""
    data = _read_bytes(path)
    if b"\n" not in data:
        raise VerifyError(f"{path.name}: 无换行符（空文件？）")
    # 找所有 LF 前一个字节，必须是 CR
    bad = 0
    for i, byte in enumerate(data):
        if byte == 0x0A and (i == 0 or data[i - 1] != 0x0D):
            bad += 1
    if bad:
        raise VerifyError(
            f"{path.name}: {bad} 处裸 LF（行尾被转换）——AFLNet 分区器会失效")


def check_sip_boundary(path: Path) -> None:
    """★ 断言：每条 SIP 消息都以 AFLNet 识别的方法开头。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    starts = [m.group(1) for m in _SIP_REQUEST_LINE.finditer(text)]
    if not starts:
        raise VerifyError(f"{path.name}: 未解析出任何 SIP 消息起点")
    bad = sorted({m for m in starts if m not in AFLNET_SIP_BOUNDARY_METHODS})
    if bad:
        raise VerifyError(
            f"{path.name}: 含不被 AFLNet 识别为消息起点的方法 {bad}"
            f"（会被并入前一条消息，破坏消息边界）")


def check_sip_regions(path: Path) -> None:
    """★ 断言：AFLNet 分区数 == 消息数（消息边界未被破坏）。"""
    data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    messages = len(_SIP_REQUEST_LINE.findall(text))
    regions = count_sip_regions(data)
    if messages != regions:
        raise VerifyError(
            f"{path.name}: 消息数 {messages} != AFLNet 分区数 {regions}"
            f"（消息边界被破坏，变异预算会浪费在无法识别的方法上）")


def check_rtsp_sessions(path: Path, playable: set[str]) -> None:
    """★ 断言：RTSP 种子只引用目标环境**实际可播**的会话。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    used = set()
    for line in text.splitlines():
        m = _RTSP_REQUEST_LINE.match(line)
        if not m:
            continue
        parts = line.split(" ")
        if len(parts) < 2:
            continue
        url = parts[1]
        segs = [s for s in url.rstrip("/").split("/") if s]
        # URL 形如 rtsp://host:8554/<stream>[/trackN]
        stream = segs[-1] if segs else ""
        if stream.startswith("track"):
            stream = segs[-2] if len(segs) >= 2 else ""
        if stream:
            used.add(stream)
    if not used:
        raise VerifyError(f"{path.name}: 未解析出任何会话名")
    bad = sorted(used - playable)
    if bad:
        raise VerifyError(
            f"{path.name}: 引用了目标环境不可播的会话 {bad}（服务端返 404）")


def check_rtsp_regions(path: Path) -> None:
    """★ 断言：RTSP 的 AFLNet 分区数 == 消息数。

    RTSP 版分区器只看 ``\\r\\n\\r\\n`` 终结符（不检查方法名），所以正常种子
    应当 1 条消息 = 1 个 region。若不等，说明种子里的空行分隔被破坏。
    """
    data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    messages = len(_RTSP_REQUEST_LINE.findall(text))
    regions = count_rtsp_regions(data)
    if messages != regions:
        raise VerifyError(
            f"{path.name}: 消息数 {messages} != AFLNet 分区数 {regions}"
            f"（消息分隔被破坏）")


def check_manifest(seed_dir: Path) -> bool:
    """★ 断言：与 MANIFEST.md5 逐条比对（scp 传输完整性）。

    MANIFEST.md5 由 rq4_sync_seeds.ps1 在**同步时**生成（本地算一份 + 远端算一份
    互相比对）。若目录里还没有该文件（例如同步前的本地自检），跳过本项并返回 False
    ——不视为失败，但会在输出里标明"未校验"。

    ★ 清单文件的位置：按设计放在种子目录**之外**（``<seed_dir>.manifest.md5``）。
      原因：AFLNet 的 ``read_testcases()`` 用 ``scandir()`` 遍历 ``-i`` 目录，会把
      **所有常规非空文件**都当成测试用例读进来（只跳过 ``README.txt``）——
      清单若在目录里，会被当成一个"种子"读进 AFLNet，污染种子集。
      为兼容早期把清单放在目录内的历史布局，两处都找，但**目录内的清单本身
      就是缺陷**（由调用方另行清理）。
    """
    candidates = [
        seed_dir.parent / f"{seed_dir.name}.manifest.md5",   # 新布局（目录外）
        seed_dir / "MANIFEST.md5",                          # 历史布局（目录内）
    ]
    manifest = next((p for p in candidates if p.exists()), None)
    if manifest is None:
        return False
    entries = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        entries[parts[1].strip().lstrip("*")] = parts[0].strip()
    if not entries:
        raise VerifyError(f"MANIFEST.md5 无有效条目: {manifest}")
    for name, expected in entries.items():
        f = seed_dir / name
        if not f.exists():
            raise VerifyError(f"MANIFEST 列出但文件缺失: {name}")
        actual = hashlib.md5(f.read_bytes()).hexdigest()
        if actual != expected:
            raise VerifyError(
                f"{name}: MD5 不符（传输损坏）expected={expected} actual={actual}")
    return True


def verify_dir(seed_dir: Path, protocol: str) -> dict:
    """校验一个种子目录，返回统计摘要。"""
    raws = sorted(seed_dir.glob("*.raw"))
    if not raws:
        raise VerifyError(f"{seed_dir}: 无 .raw 种子")

    # ★ 种子目录纯净性：只允许 .raw。
    #   AFLNet 的 read_testcases() 用 scandir() 遍历 -i 目录，把**所有常规非空文件**
    #   都当测试用例读进来（只跳过 README.txt）→ MANIFEST.md5 / *.dict 落在目录里
    #   会污染种子集，两组对比就不成立。
    extra = sorted(p.name for p in seed_dir.iterdir()
                   if p.is_file() and p.suffix != ".raw")
    if extra:
        raise VerifyError(
            f"{seed_dir}: 存在非 .raw 文件 {extra}"
            f"（会被 AFLNet 当种子读进去，污染种子集）")

    playable: set[str] = set()
    if protocol == "rtsp":
        from core.fused.downstream.target_env import playable_resource_names
        profile = json.loads(paths.target_profile("rtsp").read_text(encoding="utf-8"))
        env_cfg = (profile.get("seedgen") or {}).get("environments", {}) \
            .get("rq2-live555", {})
        playable = set(playable_resource_names(profile, "rtsp", env_cfg) or [])

    sessions: set[str] = set()
    total_messages = 0
    total_regions = 0
    for raw in raws:
        check_crlf(raw)
        if protocol == "sip":
            check_sip_boundary(raw)
            check_sip_regions(raw)
            data = raw.read_bytes()
            text = data.decode("utf-8", errors="replace")
            total_messages += len(_SIP_REQUEST_LINE.findall(text))
            total_regions += count_sip_regions(data)
        elif protocol == "rtsp":
            check_rtsp_sessions(raw, playable)
            check_rtsp_regions(raw)
            for line in raw.read_text(encoding="utf-8", errors="replace").splitlines():
                m = _RTSP_REQUEST_LINE.match(line)
                if not m:
                    continue
                parts = line.split(" ")
                if len(parts) < 2:
                    continue
                segs = [s for s in parts[1].rstrip("/").split("/") if s]
                stream = segs[-1] if segs else ""
                if stream.startswith("track"):
                    stream = segs[-2] if len(segs) >= 2 else ""
                if stream:
                    sessions.add(stream)
    manifest_checked = check_manifest(seed_dir)
    return {
        "protocol": protocol,
        "dir": str(seed_dir),
        "seed_files": len(raws),
        "sessions": sorted(sessions),
        "messages": total_messages,
        "regions": total_regions,
        "manifest_checked": manifest_checked,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ4 种子语料结构自检")
    ap.add_argument("--seed-dir", default=None, help="单个种子目录")
    ap.add_argument("--protocol", default=None,
                    help="协议名（rtsp/sip/smtp），不指定则从目录名推断")
    ap.add_argument("--all", action="store_true",
                    help="校验 RQ4 三协议全部种子目录")
    ap.add_argument("--root", default="derived/seeds",
                    help="--all 时的种子根目录")
    args = ap.parse_args()

    targets: list[tuple[str, Path]] = []
    if args.all:
        root = Path(args.root)
        for proto in ("rtsp", "sip", "smtp"):
            d = root / proto
            if d.exists():
                targets.append((proto, d))
    elif args.seed_dir:
        d = Path(args.seed_dir)
        proto = args.protocol
        if proto is None:
            for cand in ("rtsp", "sip", "smtp"):
                if cand in d.parts:
                    proto = cand
                    break
        if proto is None:
            print("!! 无法推断协议名，请用 --protocol 指定", file=sys.stderr)
            return 2
        targets.append((proto, d))
    else:
        ap.print_help()
        return 2

    if not targets:
        print("!! 没有待校验的种子目录", file=sys.stderr)
        return 2

    failed = 0
    summaries = []
    for proto, d in targets:
        print(f"=== 校验 {proto}: {d} ===")
        try:
            summary = verify_dir(d, proto)
        except VerifyError as exc:
            print(f"  ✗ {exc}")
            failed += 1
            continue
        print(f"  ✓ 种子文件 {summary['seed_files']} 个，CRLF 正常")
        if proto == "sip":
            print(f"  ✓ 消息起点全部可被 AFLNet 识别"
                  f"（消息 {summary['messages']} / 分区 {summary['regions']}）")
        elif proto == "rtsp":
            print(f"  ✓ 引用会话 {summary['sessions']}（均在可播清单内）")
        if summary["manifest_checked"]:
            print("  ✓ MANIFEST.md5 逐条 MD5 一致")
        else:
            print("  - MANIFEST.md5 尚未生成（同步时生成并校验）")
        summaries.append(summary)

    print()
    print("=" * 60)
    if failed:
        print(f"自检失败：{failed}/{len(targets)} 个目录不合格")
        return 1
    print(f"自检通过：{len(targets)}/{len(targets)} 个目录合格")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
