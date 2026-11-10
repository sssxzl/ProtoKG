# -*- coding: utf-8 -*-
"""更新 kb/历史漏洞：追加全网搜到的 LIVE555/testOnDemandRTSPServer 相关漏洞。

只写 kb/历史漏洞/RTSP-XXX.json，其余知识库一律不碰。
"""
import json
from pathlib import Path

OUT = Path(r"E:\科研\想法idea\ProtoKG\kb\历史漏洞")


def vuln(case_id, cve, title, desc, risk, cwe, method, field, condition):
    return {
        "case_id": case_id,
        "avd_id": cve,
        "scope": "seedgen",
        "confidence": "high" if field else "medium",
        "title_avd": title,
        "description_raw": desc,
        "risk_level_avd": risk,
        "cwe_avd": cwe,
        "trigger": {
            "method": {"value": method, "confidence": "confirmed" if method else "missing"},
            "field": {"value": field, "confidence": "confirmed" if field else "missing"},
            "condition": {"value": condition, "confidence": "confirmed"},
        },
        "trigger_requests": {"value": None, "confidence": "missing"},
        "mutation_hints": {"value": [], "confidence": "missing_from_source"},
        "provenance": {
            "description_raw": "confirmed",
            "title_avd": "confirmed",
            "risk_level_avd": "confirmed",
            "cwe_avd": "confirmed",
            "trigger_method": "confirmed" if method else "missing",
            "trigger_field": "confirmed" if field else "missing",
            "trigger_condition": "confirmed",
            "trigger_requests": "missing",
            "trigger_requests_note": "CVE 原文不含完整 RTSP request 序列",
            "mutation_hints": "missing_from_source",
        },
        "unmatched_avd": False,
        "avd_id_equivalent": None,
    }


# 12 个 LIVE555/testOnDemandRTSPServer 直接相关漏洞
items = [
    vuln("RTSP-038", "CVE-2023-37117",
         "Live555 2023.05.10 SETUP 堆释放后使用(CVE-2023-37117)",
         "Live555 Streaming Media 版本 2023.05.10 在处理 SETUP 请求时存在堆释放后使用(heap-use-after-free)漏洞,攻击者可发送特制 SETUP 请求触发,造成远程代码执行或拒绝服务。该版本恰为 testOnDemandRTSPServer 实验所用版本。",
         "严重", "CWE-416 (释放后使用)",
         ["SETUP"], None, "处理 SETUP 请求时堆释放后使用"),
    vuln("RTSP-039", "CVE-2021-38382",
         "Live555 Matroska/Ogg 两次 SETUP 同 track 释放后使用(CVE-2021-38382)",
         "Live555 1.08 及之前版本对 Matroska 和 Ogg 文件处理不当,对同一 track 连续发送两次 RTSP SETUP 命令会触发 use-after-free 导致服务崩溃。",
         "中危", "CWE-416 (释放后使用)",
         ["SETUP"], ["track"], "对 Matroska/Ogg 同一 track 连续两次 SETUP"),
    vuln("RTSP-040", "CVE-2021-38381",
         "Live555 MPEG-1/2 两次 SETUP 同 track 释放后使用(CVE-2021-38381)",
         "Live555 1.08 及之前版本对 MPEG-1/2 文件处理不当,对同一 track 连续发送两次 RTSP SETUP 命令会触发 use-after-free 导致服务崩溃。",
         "中危", "CWE-416 (释放后使用)",
         ["SETUP"], ["track"], "对 MPEG-1/2 同一 track 连续两次 SETUP"),
    vuln("RTSP-041", "CVE-2026-38998",
         "Live555 SocketDescriptor::tcpReadHandler1 释放后使用(CVE-2026-38998)",
         "Live555 Streaming Media 2026.02.26 版本在 liveMedia/RTPInterface.cpp 的 SocketDescriptor::tcpReadHandler1 函数存在释放后使用,攻击者发送一系列特制 RTSP 与 HTTP 请求可触发拒绝服务。涉及 RTP/RTCP-over-TCP(interleaved)通道处理。",
         "中危", "CWE-416 (释放后使用)",
         ["SETUP", "PLAY"], ["Transport"], "interleaved SETUP 后一系列 RTSP+HTTP 请求触发 UAF"),
    vuln("RTSP-042", "CVE-2026-41470",
         "Live555 RTSP Session token 重放授权绕过(CVE-2026-41470)",
         "Live555 2026.04.22 之前版本,RTSP 会话命令处理存在授权绕过:攻击者获取有效 Session token 后,可从第二个未认证 TCP 连接发送 PLAY/TEARDOWN 命令,导致虚拟函数调用错误崩溃或中断合法流。",
         "高危", "CWE-306 (关键功能缺失认证)",
         ["PLAY", "TEARDOWN"], ["Session"], "用有效 Session token 从第二连接发 PLAY/TEARDOWN"),
    vuln("RTSP-043", "CVE-2026-1200",
         "Live555 increaseBufferTo 分段错误(CVE-2026-1200)",
         "live555 1.13 版本在执行 increaseBufferTo 函数(GroupsockHelper.cpp:522)时存在分段错误,可由特制 SETUP 请求经 OnDemandServerMediaSubsession::getStreamParameters 触发,可能导致远程代码执行。",
         "中危", "CWE-787 (越界写入)",
         ["SETUP"], None, "SETUP 触发 increaseBufferTo 分段错误"),
    vuln("RTSP-044", "CVE-2020-24027",
         "Live555 PLAY 绝对时间 seek 缓冲区溢出(CVE-2020-24027)",
         "liblivemedia 的 RTSP 服务器组件在处理带绝对时间 seek 的特制 RTSP PLAY 命令时存在缓冲区溢出,攻击者可远程执行代码。涉及 PLAY 的 Range 头绝对时间(clock=)参数。",
         "严重", "CWE-120 (缓冲区溢出)",
         ["PLAY"], ["Range"], "PLAY 带绝对时间 seek(Range: clock=...)"),
    vuln("RTSP-045", "CVE-2021-38380",
         "Live555 大量 MP3 请求递归栈溢出(CVE-2021-38380)",
         "Live555 1.08 及之前版本对同一 MP3 流的巨量请求处理不当,导致递归和栈缓冲区越界读取,攻击者可借此发起拒绝服务。",
         "高危", "CWE-125 (越界读取)",
         ["SETUP", "PLAY"], None, "对同一 MP3 流发送大量请求"),
    vuln("RTSP-046", "CVE-2025-65405",
         "Live555 ADTSAudioFileSource 释放后使用(CVE-2025-65405)",
         "Live555 2018.09.02 版本的 ADTSAudioFileSource::samplingFrequency 函数存在释放后使用,Matroska demuxer 在 RTSP SETUP 过程中触发堆释放后使用导致服务器崩溃。",
         "高危", "CWE-416 (释放后使用)",
         ["SETUP"], None, "Matroska 流 SETUP 触发 ADTS demuxer 释放后使用"),
    vuln("RTSP-047", "CVE-2025-65406",
         "Live555 MatroskaFile::createRTPSinkForTrackNumber 堆溢出(CVE-2025-65406)",
         "Live555 2018.09.02 版本的 MatroskaFile::createRTPSinkForTrackNumber 函数存在堆溢出,攻击者提供特制 MKV 文件可触发拒绝服务。",
         "中危", "CWE-122 (堆缓冲区溢出)",
         ["SETUP"], ["track"], "Matroska 流 SETUP 触发 createRTPSinkForTrackNumber 堆溢出"),
    vuln("RTSP-048", "CVE-2025-65404",
         "Live555 getSideInfo2 缓冲区溢出(CVE-2025-65404)",
         "Live555 2018.09.02 版本的 getSideInfo2 函数存在缓冲区溢出,攻击者发送特制 MP3 流可触发拒绝服务。",
         "中危", "CWE-120 (缓冲区溢出)",
         ["SETUP", "PLAY"], None, "MP3 流触发 getSideInfo2 缓冲区溢出"),
    vuln("RTSP-049", "CVE-2019-7314",
         "Live555 RTP/RTCP-over-RTSP 释放后使用(CVE-2019-7314)",
         "Live555 的 liblivemedia 库在 RTP/RTCP-over-RTSP(interleaved)建立后终止 RTSP 流时存在释放后使用,可导致 RTSP 服务器崩溃。",
         "严重", "CWE-416 (释放后使用)",
         ["SETUP", "TEARDOWN"], ["Transport"], "RTP/RTCP-over-RTSP(interleaved)setup 后终止流"),
]

for it in items:
    path = OUT / f"{it['case_id']}.json"
    path.write_text(json.dumps(it, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {it['case_id']}: {it['avd_id']} - {it['title_avd']}")
print(f"\n共追加 {len(items)} 个漏洞，现有 {len(list(OUT.glob('RTSP-*.json')))} 个文件")
