# -*- coding: utf-8 -*-
"""response_rewriter 的单元测试（纯函数，脱离网络，不调用 DeepSeek）。

运行方式（任选其一，均无需第三方依赖）：
    python tests/test_response_rewriter.py
    E:/app/Anaconda3/python.exe tests/test_response_rewriter.py
    pytest tests/test_response_rewriter.py

覆盖：增强散文响应、stall 响应、语法抽取 COMMAND 响应（应原样透传）、无合法报文、
空 content、多请求序列、含代码围栏、折叠续行、REDIRECT、大小写不敏感、CRLF 规范化。
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.response_rewriter import (  # noqa: E402
    ENRICH, STALL, GRAMMAR, UNKNOWN,
    PROTO_RTSP, PROTO_FTP, PROTO_SIP, PROTO_UNKNOWN,
    ACTION_PASSTHROUGH, ACTION_REWRITTEN, ACTION_EMPTIED,
    classify_request, detect_protocol,
    extract_rtsp_messages, extract_ftp_messages, extract_sip_messages,
    rewrite_response,
)


# ---------------------------------------------------------------------------
# 样例数据
# ---------------------------------------------------------------------------

# 增强路径散文响应（前言 + 代码围栏 + 三段报文 + Explanation）
ENRICH_PROSE = """Here is the modified sequence of client requests with the SETUP request added in the proper location:

```
DESCRIBE rtsp://127.0.0.1:8554/mp3AudioTest RTSP/1.0
CSeq: 1
Accept: application/sdp

SETUP rtsp://127.0.0.1:8554/mp3AudioTest/track1 RTSP/1.0
CSeq: 2
Transport: RTP/AVP;unicast;client_port=8000-8001

PLAY rtsp://127.0.0.1:8554/mp3AudioTest RTSP/1.0
CSeq: 3
Session: 123456
```

**Explanation:**
- **DESCRIBE** is sent first to retrieve the session description...
"""

ENRICH_EXPECTED = (
    "DESCRIBE rtsp://127.0.0.1:8554/mp3AudioTest RTSP/1.0\n"
    "CSeq: 1\n"
    "Accept: application/sdp\n"
    "\n"
    "SETUP rtsp://127.0.0.1:8554/mp3AudioTest/track1 RTSP/1.0\n"
    "CSeq: 2\n"
    "Transport: RTP/AVP;unicast;client_port=8000-8001\n"
    "\n"
    "PLAY rtsp://127.0.0.1:8554/mp3AudioTest RTSP/1.0\n"
    "CSeq: 3\n"
    "Session: 123456"
)

# stall-chat 散文响应（单条下一个请求）
STALL_PROSE = """The next request should be a TEARDOWN to close the session:

```
TEARDOWN rtsp://127.0.0.1:8554/mp3AudioTest RTSP/1.0
CSeq: 4
Session: 123456
```

This will terminate the streaming session."""

STALL_EXPECTED = (
    "TEARDOWN rtsp://127.0.0.1:8554/mp3AudioTest RTSP/1.0\n"
    "CSeq: 4\n"
    "Session: 123456"
)

# 请求体（含各路径的判别特征）
ENRICH_REQUEST = {
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": (
        "The following is one sequence of client requests:\n"
        "DESCRIBE rtsp://127.0.0.1:8554/x RTSP/1.0\r\nCSeq: 1\r\n\r\n"
        "Please add the SETUP client requests in the proper locations, "
        "and the modified sequence of client requests is:"
    )}],
}

STALL_REQUEST = {
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": (
        "The next proper client request that can affect the server's state are:\n"
        "Desired format of real client requests:\n"
        "Communication History:\n"
        "DESCRIBE rtsp://127.0.0.1:8554/x RTSP/1.0\r\nCSeq: 1\r\n\r\n"
    )}],
}

GRAMMAR_REQUEST = {
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": (
        "For the RTSP protocol, the DESCRIBE client request template is:\n"
        "DESCRIBE: [\"DESCRIBE <<VALUE>>\\r\\n\"]\n"
        "Output ONLY the templates, one per line, in the format COMMAND: [\"...\"]. "
        "Do not use markdown code fences, do not add any explanation or preamble."
    )}],
}

UNKNOWN_REQUEST = {"messages": [{"role": "user", "content": "hello world"}]}


def _resp(content):
    """构造 DeepSeek 风格响应字节。"""
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


# ---------------------------------------------------------------------------
# 抽取器单元测试
# ---------------------------------------------------------------------------

class TestExtractRtspMessages(unittest.TestCase):
    def test_enrich_prose_extracted(self):
        self.assertEqual(extract_rtsp_messages(ENRICH_PROSE), ENRICH_EXPECTED)

    def test_stall_prose_extracted(self):
        self.assertEqual(extract_rtsp_messages(STALL_PROSE), STALL_EXPECTED)

    def test_multi_block_only_one_blank_line(self):
        text = (
            "OPTIONS rtsp://h/ RTSP/1.0\n"
            "CSeq: 1\n"
            "\n"
            "DESCRIBE rtsp://h/ RTSP/1.0\n"
            "CSeq: 2\n"
        )
        expected = (
            "OPTIONS rtsp://h/ RTSP/1.0\nCSeq: 1\n\n"
            "DESCRIBE rtsp://h/ RTSP/1.0\nCSeq: 2"
        )
        self.assertEqual(extract_rtsp_messages(text), expected)

    def test_messages_without_blank_separator_split(self):
        text = "OPTIONS rtsp://h/ RTSP/1.0\nCSeq: 1\nDESCRIBE rtsp://h/ RTSP/1.0\nCSeq: 2\n"
        expected = "OPTIONS rtsp://h/ RTSP/1.0\nCSeq: 1\n\nDESCRIBE rtsp://h/ RTSP/1.0\nCSeq: 2"
        self.assertEqual(extract_rtsp_messages(text), expected)

    def test_redirect_method_and_case_insensitive(self):
        out = extract_rtsp_messages("```\nredirect rtsp://h/ RTSP/1.0\nCSeq: 9\n```")
        self.assertEqual(out, "REDIRECT rtsp://h/ RTSP/1.0\nCSeq: 9")

    def test_crlf_normalized(self):
        out = extract_rtsp_messages("OPTIONS rtsp://h/ RTSP/1.0\r\nCSeq: 1\r\n")
        self.assertEqual(out, "OPTIONS rtsp://h/ RTSP/1.0\nCSeq: 1")

    def test_folded_continuation_line_kept(self):
        text = "SET_PARAMETER rtsp://h/ RTSP/1.0\nCSeq: 3\n a: b\n"
        self.assertEqual(
            extract_rtsp_messages(text),
            "SET_PARAMETER rtsp://h/ RTSP/1.0\nCSeq: 3\na: b",
        )

    def test_no_valid_message_returns_empty(self):
        self.assertEqual(extract_rtsp_messages("I'm sorry, I cannot generate that."), "")
        self.assertEqual(extract_rtsp_messages(""), "")
        self.assertEqual(extract_rtsp_messages("```\njust prose\n```"), "")

    def test_trailing_prose_ignored(self):
        # 真实 deepseek-chat 输出以 **Explanation:** 结尾（以 * 开头，不匹配头部正则，被忽略）
        text = "OPTIONS rtsp://h/ RTSP/1.0\nCSeq: 1\n\n**Explanation:** this is fine.\n"
        self.assertEqual(extract_rtsp_messages(text), "OPTIONS rtsp://h/ RTSP/1.0\nCSeq: 1")

    def test_bare_note_line_not_mixed_in(self):
        # 裸 Note: 散文行（字母开头+冒号）不再被误判为 RTSP 头部
        text = (
            "DESCRIBE rtsp://h/ RTSP/1.0\n"
            "CSeq: 1\n"
            "\n"
            "Note: In a real RTSP session, the typical order...\n"
        )
        self.assertEqual(
            extract_rtsp_messages(text),
            "DESCRIBE rtsp://h/ RTSP/1.0\nCSeq: 1",
        )

    def test_bare_explanation_line_not_mixed_in(self):
        # 裸 Explanation: 散文行不再被误判为 RTSP 头部
        text = (
            "DESCRIBE rtsp://h/ RTSP/1.0\n"
            "CSeq: 1\n"
            "\n"
            "Explanation: this is the rationale...\n"
        )
        self.assertEqual(
            extract_rtsp_messages(text),
            "DESCRIBE rtsp://h/ RTSP/1.0\nCSeq: 1",
        )

    def test_fence_then_explanation_without_blank_not_mixed_in(self):
        # 围栏 ``` 后紧跟 Explanation:（无空行分隔）不应混入
        text = (
            "```\n"
            "DESCRIBE rtsp://h/ RTSP/1.0\n"
            "CSeq: 1\n"
            "```\n"
            "Explanation: this is a note\n"
        )
        self.assertEqual(
            extract_rtsp_messages(text),
            "DESCRIBE rtsp://h/ RTSP/1.0\nCSeq: 1",
        )

    def test_whitelisted_headers_still_kept(self):
        # 白名单内的合法头部仍要正常保留（Transport / CSeq / Session / User-Agent）
        text = (
            "SETUP rtsp://h/ RTSP/1.0\n"
            "CSeq: 2\n"
            "Transport: RTP/AVP/TCP;unicast;interleaved=0-1\n"
            "Session: 123456\n"
            "User-Agent: Live555 Streaming Media v2021.08.24\n"
            "\n"
        )
        expected = (
            "SETUP rtsp://h/ RTSP/1.0\n"
            "CSeq: 2\n"
            "Transport: RTP/AVP/TCP;unicast;interleaved=0-1\n"
            "Session: 123456\n"
            "User-Agent: Live555 Streaming Media v2021.08.24"
        )
        self.assertEqual(extract_rtsp_messages(text), expected)

    def test_whitelisted_header_case_insensitive(self):
        # 白名单正则 re.IGNORECASE：小写 transport: 也需被识别为合法头部
        out = extract_rtsp_messages(
            "SETUP rtsp://h/ RTSP/1.0\n"
            "cseq: 1\n"
            "transport: RTP/AVP;unicast\n"
        )
        self.assertEqual(
            out,
            "SETUP rtsp://h/ RTSP/1.0\ncseq: 1\ntransport: RTP/AVP;unicast",
        )


# ---------------------------------------------------------------------------
# 路径判别单元测试
# ---------------------------------------------------------------------------

class TestClassifyRequest(unittest.TestCase):
    def test_grammar(self):
        self.assertEqual(classify_request(GRAMMAR_REQUEST), GRAMMAR)

    def test_enrich(self):
        self.assertEqual(classify_request(ENRICH_REQUEST), ENRICH)

    def test_stall(self):
        self.assertEqual(classify_request(STALL_REQUEST), STALL)

    def test_unknown(self):
        self.assertEqual(classify_request(UNKNOWN_REQUEST), UNKNOWN)

    def test_non_dict_returns_unknown(self):
        self.assertEqual(classify_request("not a dict"), UNKNOWN)
        self.assertEqual(classify_request(None), UNKNOWN)


# ---------------------------------------------------------------------------
# 改写入口单元测试
# ---------------------------------------------------------------------------

class TestRewriteResponse(unittest.TestCase):
    def test_enrich_rewritten(self):
        result = rewrite_response(ENRICH_REQUEST, _resp(ENRICH_PROSE))
        self.assertEqual(result.path, ENRICH)
        self.assertEqual(result.action, ACTION_REWRITTEN)
        content = json.loads(result.body)["choices"][0]["message"]["content"]
        self.assertEqual(content, ENRICH_EXPECTED)

    def test_stall_rewritten(self):
        result = rewrite_response(STALL_REQUEST, _resp(STALL_PROSE))
        self.assertEqual(result.path, STALL)
        self.assertEqual(result.action, ACTION_REWRITTEN)
        content = json.loads(result.body)["choices"][0]["message"]["content"]
        self.assertEqual(content, STALL_EXPECTED)

    def test_grammar_passthrough_unchanged(self):
        raw = _resp('OPTIONS: ["OPTIONS rtsp://x RTSP/1.0\\r\\n"]')
        result = rewrite_response(GRAMMAR_REQUEST, raw)
        self.assertEqual(result.path, GRAMMAR)
        self.assertEqual(result.action, ACTION_PASSTHROUGH)
        self.assertEqual(result.body, raw)

    def test_unknown_passthrough_unchanged(self):
        raw = _resp("some arbitrary prose")
        result = rewrite_response(UNKNOWN_REQUEST, raw)
        self.assertEqual(result.path, UNKNOWN)
        self.assertEqual(result.action, ACTION_PASSTHROUGH)
        self.assertEqual(result.body, raw)

    def test_no_valid_message_emptied(self):
        result = rewrite_response(ENRICH_REQUEST, _resp("I cannot generate that."))
        self.assertEqual(result.path, ENRICH)
        self.assertEqual(result.action, ACTION_EMPTIED)
        content = json.loads(result.body)["choices"][0]["message"]["content"]
        self.assertEqual(content, "")

    def test_empty_content_passthrough(self):
        raw = _resp("")
        result = rewrite_response(ENRICH_REQUEST, raw)
        self.assertEqual(result.action, ACTION_PASSTHROUGH)
        self.assertEqual(result.body, raw)

    def test_non_json_response_passthrough(self):
        raw = b"<html>502 bad gateway</html>"
        result = rewrite_response(ENRICH_REQUEST, raw)
        self.assertEqual(result.action, ACTION_PASSTHROUGH)
        self.assertEqual(result.body, raw)

    def test_response_missing_choices_passthrough(self):
        raw = json.dumps({"error": {"message": "rate limit"}}).encode()
        result = rewrite_response(ENRICH_REQUEST, raw)
        self.assertEqual(result.action, ACTION_PASSTHROUGH)
        self.assertEqual(result.body, raw)

    def test_unparseable_request_passthrough(self):
        raw = _resp("whatever")
        result = rewrite_response(b"not json", raw)
        self.assertEqual(result.path, UNKNOWN)
        self.assertEqual(result.action, ACTION_PASSTHROUGH)
        self.assertEqual(result.body, raw)


# ---------------------------------------------------------------------------
# FTP 抽取器 + 协议检测（FTP 行命令协议）
# ---------------------------------------------------------------------------

# FTP 增强散文响应（前言 + 代码围栏 + FTP 命令 + Explanation）
FTP_ENRICH_PROSE = """Sure! Here is the modified sequence of client requests:

```
USER anonymous
PASS user@example.com
PWD
CWD /pub
TYPE I
PORT 127,0,0,1,14,178
RETR readme.txt
QUIT
```

**Explanation:** the ACCT request is added after login for account information.
"""

FTP_ENRICH_EXPECTED = (
    "USER anonymous\n"
    "PASS user@example.com\n"
    "PWD\n"
    "CWD /pub\n"
    "TYPE I\n"
    "PORT 127,0,0,1,14,178\n"
    "RETR readme.txt\n"
    "QUIT"
)

# FTP enrich 请求（sequence 内嵌 FTP 命令，无 RTSP/1.0 特征）
FTP_ENRICH_REQUEST = {
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": (
        "The following is one sequence of client requests:\n"
        "USER ubuntu\r\nPASS ubuntu\r\nPWD\r\nQUIT\r\n"
        "Please add the ACCT client requests in the proper locations, "
        "and the modified sequence of client requests is:"
    )}],
}


class TestExtractFtpMessages(unittest.TestCase):
    def test_ftp_prose_extracted(self):
        self.assertEqual(extract_ftp_messages(FTP_ENRICH_PROSE),
                         FTP_ENRICH_EXPECTED)

    def test_ftp_ignores_prose_lines(self):
        # 散文里即使有 "the user" / "a list" 这类单词，也不应被整行误判
        prose = "Sure! here is the user\nUSER bob\nhere is a list\nLIST\n"
        self.assertEqual(extract_ftp_messages(prose), "USER bob\nLIST")

    def test_ftp_lowercase_normalized(self):
        self.assertEqual(extract_ftp_messages("user alice\npass secret\n"),
                         "USER alice\nPASS secret")

    def test_ftp_no_argument_command(self):
        self.assertEqual(extract_ftp_messages("PWD\nSYST\nQUIT\n"),
                         "PWD\nSYST\nQUIT")

    def test_ftp_glued_command_rejected(self):
        # 命令与参数无空格粘连（USERanonymous）不应被当成合法命令
        self.assertEqual(extract_ftp_messages("USERanonymous\nUSER alice\n"),
                         "USER alice")

    def test_ftp_empty_returns_empty(self):
        self.assertEqual(extract_ftp_messages("No valid command here."), "")
        self.assertEqual(extract_ftp_messages(""), "")

    def test_ftp_fence_ignored(self):
        self.assertEqual(extract_ftp_messages("```ftp\nUSER a\n```\n"),
                         "USER a")


class TestDetectProtocol(unittest.TestCase):
    def test_detect_ftp(self):
        self.assertEqual(detect_protocol(FTP_ENRICH_REQUEST), PROTO_FTP)

    def test_detect_ftp_with_escaped_sequence(self):
        # chatafl 真实请求：sequence 经 json_object_to_json_string 转义后，
        # 报文换行是字面量 \\r\\n（反斜杠 r 反斜杠 n），非真实换行。
        req = {"messages": [{"role": "user", "content": (
            "The following is one sequence of client requests:\n"
            "MLSD\\r\\n"
            "Please add the STOR, SYST client requests in the proper locations, "
            "and the modified sequence of client requests is:"
        )}]}
        self.assertEqual(detect_protocol(req), PROTO_FTP)

    def test_detect_rtsp(self):
        self.assertEqual(detect_protocol(ENRICH_REQUEST), PROTO_RTSP)

    def test_detect_unknown(self):
        self.assertEqual(detect_protocol(UNKNOWN_REQUEST), PROTO_UNKNOWN)

    def test_rtsp_signature_priority(self):
        # 同时含 RTSP 特征与 FTP 命令时，RTSP 特征优先
        req = {"messages": [{"role": "user", "content": (
            "OPTIONS rtsp://127.0.0.1:8554/x RTSP/1.0\r\nUSER bob\r\n"
        )}]}
        self.assertEqual(detect_protocol(req), PROTO_RTSP)


class TestRewriteResponseFtp(unittest.TestCase):
    def test_ftp_enrich_rewritten(self):
        result = rewrite_response(FTP_ENRICH_REQUEST, _resp(FTP_ENRICH_PROSE))
        self.assertEqual(result.path, ENRICH)
        self.assertEqual(result.action, ACTION_REWRITTEN)
        content = json.loads(result.body)["choices"][0]["message"]["content"]
        self.assertEqual(content, FTP_ENRICH_EXPECTED)

    def test_ftp_no_valid_command_emptied(self):
        result = rewrite_response(FTP_ENRICH_REQUEST, _resp("I cannot do that."))
        self.assertEqual(result.path, ENRICH)
        self.assertEqual(result.action, ACTION_EMPTIED)
        content = json.loads(result.body)["choices"][0]["message"]["content"]
        self.assertEqual(content, "")

    def test_rtsp_path_unchanged_after_ftp_addition(self):
        # RTSP 路径回归：加 FTP 抽取器后 RTSP 增强仍走 RTSP 抽取器
        result = rewrite_response(ENRICH_REQUEST, _resp(ENRICH_PROSE))
        self.assertEqual(result.action, ACTION_REWRITTEN)
        content = json.loads(result.body)["choices"][0]["message"]["content"]
        self.assertEqual(content, ENRICH_EXPECTED)


# ---------------------------------------------------------------------------
# SIP 测试（Kamailio 种子有效性实验前置：chatafl 增强需走 SIP 抽取器）
# ---------------------------------------------------------------------------

SIP_ENRICH_REQUEST = {"messages": [{"role": "user", "content": (
    "The following is one sequence of client requests:\n"
    "REGISTER sip:127.0.0.1 SIP/2.0\\r\\n"
    "Via: SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK-1\\r\\n"
    "Please add the INVITE, BYE client requests in the proper locations, "
    "and the modified sequence of client requests is:"
)}]}

SIP_ENRICH_PROSE = """Here is the modified sequence of client requests with the INVITE request added:

```
REGISTER sip:127.0.0.1 SIP/2.0
Via: SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK-1
From: <sip:30@127.0.0.1>;tag=1
To: <sip:30@127.0.0.1>
Call-ID: 1@127.0.0.1
CSeq: 1 REGISTER
Contact: <sip:30@127.0.0.1:5061>
Max-Forwards: 70
Content-Length: 0

INVITE sip:33@127.0.0.1 SIP/2.0
Via: SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK-2
From: <sip:30@127.0.0.1>;tag=1
To: <sip:33@127.0.0.1>
Call-ID: 1@127.0.0.1
CSeq: 2 INVITE
Max-Forwards: 70
Content-Type: application/sdp
Content-Length: 90

v=0
o=user1 5 2 IN IP4 127.0.0.1
s=-
m=audio 6000 RTP/AVP 8
```

**Explanation:** REGISTER first, then INVITE with SDP body.
"""

SIP_ENRICH_EXPECTED = (
    "REGISTER sip:127.0.0.1 SIP/2.0\n"
    "Via: SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK-1\n"
    "From: <sip:30@127.0.0.1>;tag=1\n"
    "To: <sip:30@127.0.0.1>\n"
    "Call-ID: 1@127.0.0.1\n"
    "CSeq: 1 REGISTER\n"
    "Contact: <sip:30@127.0.0.1:5061>\n"
    "Max-Forwards: 70\n"
    "Content-Length: 0\n"
    "\n"
    "INVITE sip:33@127.0.0.1 SIP/2.0\n"
    "Via: SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK-2\n"
    "From: <sip:30@127.0.0.1>;tag=1\n"
    "To: <sip:33@127.0.0.1>\n"
    "Call-ID: 1@127.0.0.1\n"
    "CSeq: 2 INVITE\n"
    "Max-Forwards: 70\n"
    "Content-Type: application/sdp\n"
    "Content-Length: 90\n"
    "\n"
    "v=0\n"
    "o=user1 5 2 IN IP4 127.0.0.1\n"
    "s=-\n"
    "m=audio 6000 RTP/AVP 8"
)


class TestExtractSipMessages(unittest.TestCase):
    def test_sip_prose_extracted(self):
        self.assertEqual(extract_sip_messages(SIP_ENRICH_PROSE), SIP_ENRICH_EXPECTED)

    def test_sip_ignores_prose_lines(self):
        prose = "Sure! Here it is:\nINVITE sip:bob@127.0.0.1 SIP/2.0\nTo: <sip:bob@127.0.0.1>\nHope this helps."
        out = extract_sip_messages(prose)
        self.assertIn("INVITE sip:bob@127.0.0.1 SIP/2.0", out)
        self.assertNotIn("Sure", out)
        self.assertNotIn("Hope", out)

    def test_sip_lowercase_method_normalized(self):
        # 方法名统一大写；版本号/URI 保留原始大小写（与 RTSP 抽取器行为一致）
        out = extract_sip_messages("invite sip:a@127.0.0.1 sip/2.0\nTo: <sip:a@127.0.0.1>\n")
        self.assertTrue(out.startswith("INVITE sip:a@127.0.0.1"))

    def test_sip_sdp_body_kept(self):
        out = extract_sip_messages(
            "INVITE sip:a@127.0.0.1 SIP/2.0\nContent-Length: 30\n\nv=0\no=u 1 1 IN IP4 127.0.0.1\nm=audio 6000 RTP/AVP 8\n")
        self.assertIn("v=0", out)
        self.assertIn("m=audio", out)

    def test_sip_empty_returns_empty(self):
        self.assertEqual(extract_sip_messages("No SIP message here."), "")
        self.assertEqual(extract_sip_messages(""), "")

    def test_sip_fence_ignored(self):
        out = extract_sip_messages("```sip\nOPTIONS sip:a@127.0.0.1 SIP/2.0\n```\n")
        self.assertIn("OPTIONS sip:a@127.0.0.1 SIP/2.0", out)


class TestDetectProtocolSip(unittest.TestCase):
    def test_detect_sip(self):
        self.assertEqual(detect_protocol(SIP_ENRICH_REQUEST), PROTO_SIP)

    def test_detect_sip_rtsp_priority(self):
        # 同时含 RTSP 与 SIP 特征时 RTSP 优先（RTSP 先判，且两者版本号互斥）
        req = {"messages": [{"role": "user", "content": (
            "OPTIONS rtsp://127.0.0.1:8554/x RTSP/1.0\n"
            "INVITE sip:a@127.0.0.1 SIP/2.0\n"
        )}]}
        self.assertEqual(detect_protocol(req), PROTO_RTSP)


class TestRewriteResponseSip(unittest.TestCase):
    def test_sip_enrich_rewritten(self):
        result = rewrite_response(SIP_ENRICH_REQUEST, _resp(SIP_ENRICH_PROSE))
        self.assertEqual(result.path, ENRICH)
        self.assertEqual(result.action, ACTION_REWRITTEN)
        content = json.loads(result.body)["choices"][0]["message"]["content"]
        self.assertEqual(content, SIP_ENRICH_EXPECTED)

    def test_sip_no_valid_message_emptied(self):
        result = rewrite_response(SIP_ENRICH_REQUEST, _resp("I cannot produce that."))
        self.assertEqual(result.path, ENRICH)
        self.assertEqual(result.action, ACTION_EMPTIED)
        content = json.loads(result.body)["choices"][0]["message"]["content"]
        self.assertEqual(content, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
