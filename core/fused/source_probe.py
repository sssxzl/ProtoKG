"""core/fused/source_probe.py —— 动态探测目标服务器的实例知识（流名）。

不预设资源清单、不依赖 LLM 先验：向目标服务器发 DESCRIBE 探测，服务器返回
「200 OK」即确认该流真实存在，返回真实流名列表（oracle 实测，防猜错/防幻觉）。

探测脚本跑在虚拟机端（一次性实验脚本，未纳入仓库）：起 testOnDemandRTSPServer →
逐个候选流名发 DESCRIBE → 输出返回 200 的真实流名 → 关服务器。

★协议耦合说明（2026-10-21）：本模块是【RTSP 专用】运行时辅助脚本——DESCRIBE 探测
语义、testOnDemandRTSPServer、候选流名都是 RTSP/live555 特有；VM 地址/SSH 密钥也
是硬编码的本地实验环境。换协议（SMTP/FTP）时本探测失效。正确归宿：探测消息结构
应下沉 profile（raw_format + 资源清单），VM/SSH 应配置化；当前仅被
scripts/run_seedgen_e2e.py 的 RTSP 实验路径使用，保持现状但明确边界。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

VM = "zxy@192.168.37.130"
SSH = ["ssh", "-i", str(Path.home() / ".ssh/vm_ubuntu_zxy"),
       "-o", "StrictHostKeyChecking=no", VM]


def probe_streams(host: str = VM) -> list[str]:
    """动态探测目标服务器真实流名（复用虚拟机端 /tmp/probe_streams.py）。

    返回服务器确认存在（DESCRIBE 返回 200）的流名列表；失败返回空列表。
    """
    r = subprocess.run(
        SSH + ["python3 /tmp/probe_streams.py"],
        capture_output=True, text=True, timeout=120)
    streams = [l.strip() for l in r.stdout.splitlines() if l.startswith("  ")]
    return [s for s in streams if s]
