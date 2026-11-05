# -*- coding: utf-8 -*-
"""状态机升级方案 · 阶段 C 的决定性 A/B（真调 LLM，只读）。

★ 检验对象：`docs/架构调整方案.md` 第二部分 阶段 C ——
  「LLM 抽取 prompt 升级：从『只抽规范里明确写出的转移、不要推测』
    改为『从文本推断状态与转移』」

★ 为什么必须实测：允许推断 = **主动引入幻觉**。而本项目已有的实测证据显示
  「宁缺勿滥 / 不许推断」在 RFC 单源场景下是必要的。
  ⇒ 拿 SMTP（方案声称「从 0 到有」的关键协议）做 A/B，看两种 prompt 的产出。

★ 候选定位：**按方案阶段 A 的口径**（章节标题 + 状态/会话/事务/阶段关键词）
  —— 复用章节树等价物（按 RFC 章节号切分），取整节为语义块。

★ 判据（决定能不能驱动种子生成）：
  ① 状态名在 RFC 原文命中率（纯度）；
  ② `method` 字段是该协议真实命令的比例（可驱动报文生成）；
  ③ 转移条数。

用法：E:/app/Anaconda3/python.exe local/_pilot_infer_vs_strict.py [协议]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths                                      # noqa: E402
from core.llm import DeepSeekClient                         # noqa: E402

REAL_METHODS: dict[str, set[str]] = {
    "rtsp": {"OPTIONS", "DESCRIBE", "ANNOUNCE", "SETUP", "PLAY", "PAUSE",
             "TEARDOWN", "GET_PARAMETER", "SET_PARAMETER", "RECORD", "REDIRECT"},
    "sip": {"REGISTER", "INVITE", "ACK", "CANCEL", "BYE", "OPTIONS", "SUBSCRIBE",
            "NOTIFY", "MESSAGE", "INFO", "REFER", "PRACK", "UPDATE", "PUBLISH"},
    "smtp": {"HELO", "EHLO", "MAIL", "RCPT", "DATA", "RSET", "NOOP", "VRFY",
             "EXPN", "HELP", "QUIT", "STARTTLS", "AUTH"},
}

#: 方案阶段 A 的关键词集（状态/会话/事务/阶段）
CHAPTER_KEYWORDS = re.compile(
    r"\b(state|session|transaction|phase|stage|machine|diagram|command|reply|"
    r"procedure|flow|model)\b", re.IGNORECASE)

#: 方案阶段 C 的 prompt：**允许推断**
PROMPT_INFER = """你是协议规范分析助手。下面文本来自 {protocol} 协议的 RFC 规范章节。

请从文本中**推断**该协议的会话状态机，输出 JSON：
{{"transitions": [{{"from": "<源状态名>", "method": "<触发命令/方法名>", "to": "<目标状态名>"}}]}}

要求：
1. 即使规范没有直接写出转移表，也可以**根据文本描述推断**状态与转移。
2. `method` 用该协议自己的命令/方法名（如 SMTP 的 HELO/MAIL/RCPT/DATA/QUIT）。
3. 状态名用简洁的英文命名（如 Greeting / Mail / Data）。
4. 抽不到就返回 {{"transitions": []}}。

章节标题：{title}

文本：
{text}
"""

#: 严格版（本项目已实测：method 必须是真实方法 + 只抽明确写出的）
PROMPT_STRICT = """你是协议规范分析助手。下面文本来自 {protocol} 协议的 RFC 规范章节。

请抽取其中**明确写出的状态转移**，输出 JSON：
{{"transitions": [{{"from": "<源状态名>", "method": "<触发方法名>", "to": "<目标状态名>"}}]}}

规则：
1. 只抽**规范里明确写出**的转移，不要推测、不要补充 RFC 之外的常识。
2. ★ `method` 必须是**该协议自己的请求方法名 / 命令名**（该协议报文里真实存在的方法）。
   - 若某条转移的触发条件**不是方法**（而是响应码、计时器、事件、信号），
     **不要抽这一条**（它无法用来生成报文）。
3. 状态名**照抄规范里的写法**，不要归一化大小写、不要改名、不要自造。
4. 抽不到就返回 {{"transitions": []}}。

章节标题：{title}

文本：
{text}
"""


def split_chapters(protocol: str) -> list[dict]:
    """按 RFC 章节号切分（等价于方案阶段 A 的「复用章节树」）。"""
    spec_dir = paths.kb_source_dir(protocol, "rfc")
    out = []
    for f in sorted(spec_dir.glob("*.txt")):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        heads = []
        for i, ln in enumerate(lines):
            s = ln.strip()
            # 正文里的章节标题（排除 TOC 行：含大量点号）
            if re.match(r"^\d+(\.\d+)*\.?\s+\S", s) and len(s) < 80 \
                    and "..." not in s and not s.startswith(("RFC ", "Schulzrinne")):
                heads.append((i, s))
        for k, (i, title) in enumerate(heads):
            end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
            if not CHAPTER_KEYWORDS.search(title):
                continue
            body = "\n".join(lines[i:end]).strip()
            if len(body) < 200:
                continue
            out.append({"title": title, "text": body[:8000],
                        "file": f.name, "line": i + 1})
    return out


def run(protocol: str, chaps: list[dict], template: str, llm) -> dict:
    rows, states = [], set()
    for c in chaps:
        try:
            r = llm.chat_json(system="你输出 JSON。",
                              user=template.format(protocol=protocol.upper(),
                                                   title=c["title"], text=c["text"]),
                              temperature=0.0, max_tokens=2500)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(r, dict):
            continue
        for tr in (r.get("transitions") or []):
            if isinstance(tr, dict):
                rows.append(tr)
                states.add(str(tr.get("from", "")).strip())
                states.add(str(tr.get("to", "")).strip())
    return {"rows": rows, "states": sorted(s for s in states if s)}


def main() -> None:
    protocol = sys.argv[1] if len(sys.argv) > 1 else "smtp"
    chaps = split_chapters(protocol)
    real = REAL_METHODS.get(protocol, set())
    text_all = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in sorted(paths.kb_source_dir(protocol, "rfc").glob("*.txt")))
    llm = DeepSeekClient()
    print("=" * 80)
    print(f"阶段 C 的 A/B  协议={protocol}  命中章节 {len(chaps)} 个")
    for c in chaps[:12]:
        print(f"    {c['title'][:60]:<62} {len(c['text']):>6} 字符")
    print("=" * 80)
    out = {}
    for tag, tpl in (("方案C·允许推断", PROMPT_INFER),
                     ("严格·只抽明写+方法驱动", PROMPT_STRICT)):
        res = run(protocol, chaps, tpl, llm)
        ms = sorted({str(r.get("method", "")).strip() for r in res["rows"]})
        ok = [m for m in ms if m.upper() in real]
        hit = [s for s in res["states"] if s in text_all]
        print(f"\n── {tag}")
        print(f"   转移 {len(res['rows'])} 条 / 状态 {len(res['states'])} 个")
        print(f"   状态名 RFC 原文命中: {len(hit)}/{len(res['states'])}"
              + (f"  {hit}" if hit else ""))
        print(f"   method {len(ms)} 个 → 真实命令 {len(ok)} 个"
              + (f"  {ok}" if ok else ""))
        if ms:
            print(f"   method 全表: {ms[:14]}")
        out[tag] = {"n_trans": len(res["rows"]), "states": res["states"],
                    "state_hit": len(hit), "methods": ms, "real_methods": ok}
    p = Path(__file__).resolve().parent / f"_pilot_infer_vs_strict_{protocol}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {p}")


if __name__ == "__main__":
    main()
