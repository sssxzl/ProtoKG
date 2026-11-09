# -*- coding: utf-8 -*-
"""scripts/seed_oracle_filter.py —— P3：oracle 种子质量过滤。

用真实服务器回放每条种子，按「响应状态计数」过滤掉「入口即 404 / 无响应」的无效
片段种子，让变异预算集中到能真正走通状态机的会话种子上。

⚠ **职责边界**：本脚本是**种子有效性过滤器**；执行结果三轴判定在
`core/fused/downstream/response_oracle.py`（协议结果 × 传输结果 × 进程健康）。
二者是**两个职责**，不要混淆：本脚本只判响应码、不判进程健康与传输结果。

背景（归因 2026-10-28）：protorag 的 24 条种子里多数以 INVITE/UPDATE/BYE 开头，
kamailio 的 registrar 路由只对 REGISTER 返回响应，其余方法入口即静默丢弃/404，
AFLNet 报 No server states、覆盖率极低。P0 已把片段种子强制前置 REGISTER，本脚本
在 P0 之后再做一次「动态」质量把关：真实回放、按响应码丢弃仍然无效的种子。

原理（SIP/UDP）：
  - 种子 .raw 的 Via 头已由 seedgen 改写到客户端监听端口（127.0.0.1:5061），
    服务端把响应发回该端口；本脚本绑定该端口、把消息逐条发给服务端、收响应码。
  - 首消息（会话入口）若收不到响应、或收到 404/405（not here / method not allowed），
    判定入口无效 → 丢弃该种子。

用法:
    python scripts/seed_oracle_filter.py \
        --seed-dir derived/model/seeds/sip/<时间戳> \
        --server 127.0.0.1:5060 --listen 5061 --protocol sip \
        --out derived/model/seeds/sip/<时间戳>_oracle_filtered

    # 不落盘、只看报告（干跑）：
    python scripts/seed_oracle_filter.py --seed-dir <dir> --dry-run

协议无关扩展点：SIP 之外（RTSP/HTTP）暂只回放首请求并按「是否收到响应」判定，
后续可按协议补充响应码正则。
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: SIP 响应码正则（响应行形如 "SIP/2.0 200 OK"）
_SIP_RESPONSE_RE = re.compile(rb"SIP/2\.0\s+(\d{3})")

#: 入口无效的响应码（kamailio registrar 对非 REGISTER 入口返回 404 Not here /
#: 405 Method Not Allowed；480 等表示呼叫状态机未建立）
_DEFAULT_DROP_CODES = {"404", "405"}

#: 每条消息发送后等待响应的窗口（秒）
_RECV_TIMEOUT = 0.15


def _parse_sip_messages(raw: bytes) -> list[bytes]:
    """按空行切分 SIP .raw 为消息列表（统一换行为 \\n，逐条 strip）。"""
    parts = raw.replace(b"\r\n", b"\n").split(b"\n\n")
    return [p.strip() for p in parts if p.strip()]


def _message_wire_bytes(msg: bytes) -> bytes:
    """把解析出的消息还原为 SIP 线格式（CRLF 行尾 + 结尾空行）。"""
    return msg.replace(b"\n", b"\r\n") + b"\r\n\r\n"


def _collect_responses(sock: socket.socket, timeout: float) -> list[str]:
    """在超时窗口内尽量收齐响应，返回 SIP 响应码列表（按到达顺序）。"""
    codes: list[str] = []
    deadline = time.time() + timeout
    sock.settimeout(0.02)
    while time.time() < deadline:
        try:
            data, _addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError:
            break
        if not data:
            continue
        for m in _SIP_RESPONSE_RE.finditer(data):
            codes.append(m.group(1).decode("ascii"))
    return codes


def _replay_seed(sock: socket.socket, server: tuple, messages: list[bytes],
                 timeout: float) -> list[list[str]]:
    """逐条发送消息并收集各自响应码，返回 [消息0的响应码, 消息1的响应码, ...]。"""
    per_msg_codes: list[list[str]] = []
    for msg in messages:
        sock.sendto(_message_wire_bytes(msg), server)
        per_msg_codes.append(_collect_responses(sock, timeout))
    return per_msg_codes


def _filter_seed(raw: bytes, sock: socket.socket, server: tuple,
                 drop_codes: set, timeout: float) -> tuple[bool, list[list[str]]]:
    """判定一条种子是否有效。

    Returns:
        (keep, per_msg_codes)：keep 表示保留；per_msg_codes 为逐消息响应码。
    """
    messages = _parse_sip_messages(raw)
    if not messages:
        return False, []
    per_msg_codes = _replay_seed(sock, server, messages, timeout)
    first = per_msg_codes[0] if per_msg_codes else []
    if not first:
        return False, per_msg_codes  # 入口无响应
    if first[0] in drop_codes:
        return False, per_msg_codes  # 入口即 404/405
    return True, per_msg_codes


def main() -> int:
    ap = argparse.ArgumentParser(description="P3：oracle 种子质量过滤（真实服务器回放）")
    ap.add_argument("--seed-dir", required=True, help="待过滤的种子目录（含 .raw）")
    ap.add_argument("--server", default="127.0.0.1:5060",
                    help="目标服务器 host:port（默认 127.0.0.1:5060）")
    ap.add_argument("--listen", default=5061, type=int,
                    help="客户端监听端口（收响应，须与种子 Via 的 sent-by 一致）")
    ap.add_argument("--protocol", default="sip", help="协议（决定响应码正则）")
    ap.add_argument("--timeout", default=_RECV_TIMEOUT, type=float,
                    help="每条消息的响应等待窗口（秒）")
    ap.add_argument("--out", default=None,
                    help="过滤后种子输出目录（不传则只产出报告不落盘）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只判定不落盘（等价于不传 --out）")
    args = ap.parse_args()

    seed_dir = Path(args.seed_dir)
    if not seed_dir.is_dir():
        print(f"!! 种子目录不存在: {seed_dir}", file=sys.stderr)
        return 2
    raw_files = sorted(seed_dir.glob("*.raw"))
    if not raw_files:
        print(f"!! {seed_dir} 下无 .raw 种子", file=sys.stderr)
        return 2

    host, _, port_s = args.server.partition(":")
    try:
        server = (host, int(port_s))
    except ValueError:
        print(f"!! --server 格式应为 host:port，得到 {args.server!r}", file=sys.stderr)
        return 2

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", args.listen))
    except OSError as e:
        print(f"!! 绑定监听端口 {args.listen} 失败: {e}", file=sys.stderr)
        sock.close()
        return 2

    keep_files: list[str] = []
    drop_files: list[str] = []
    report: dict = {"server": args.server, "listen": args.listen,
                    "total": len(raw_files), "keep": 0, "drop": 0, "seeds": []}
    try:
        for rf in raw_files:
            raw = rf.read_bytes()
            keep, codes = _filter_seed(raw, sock, server,
                                       _DEFAULT_DROP_CODES, args.timeout)
            entry = {"file": rf.name, "keep": keep,
                     "responses": [[c for c in mc] for mc in codes]}
            report["seeds"].append(entry)
            if keep:
                keep_files.append(rf.name)
                report["keep"] += 1
            else:
                drop_files.append(rf.name)
                report["drop"] += 1
                first_codes = codes[0] if codes else []
                tag = first_codes[0] if first_codes else "(无响应)"
                print(f"  ✗ {rf.name}: 入口响应={tag} → 丢弃")
    finally:
        sock.close()

    print(f"过滤完成: 保留 {report['keep']} / 丢弃 {report['drop']} "
          f"（共 {report['total']} 条）")

    out_dir = None
    if args.out and not args.dry_run:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in keep_files:
            (out_dir / name).write_bytes((seed_dir / name).read_bytes())
        print(f"已落盘 {len(keep_files)} 条到 {out_dir}")

    report_path = seed_dir / "oracle_filter_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"报告: {report_path}")
    if out_dir is not None:
        print(f"过滤后目录: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
