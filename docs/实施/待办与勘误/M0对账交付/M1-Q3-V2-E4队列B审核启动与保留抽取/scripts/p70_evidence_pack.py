# -*- coding: utf-8 -*-
"""★ V2-E4 §二：★ 生成队列 B 的**只读 RFC 原文证据包**。

★ ★ 用户明确要求：★「禁止让审核者只看无原文的空白模板进行判断」
★ ⇒ ★ 本包提供：★ 按 snippet_id 的完整原文行（★ 带行号）＋ 前后文 ＋ 章节 ＋ 哈希
★ ★ **不含**：★ V0/V1/V2 预测 ｜★ 历史模型状态 ｜★ 片段是否生成过候选 ｜★ 历史人工标签
"""
import hashlib
import html
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[4]
D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
     / "M1-Q3-V2-E3队列B盲审发放与保留来源预案")
E4 = ROOT / "guard/_out/_n1c_v2/e4"
E4.mkdir(parents=True, exist_ok=True)
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4队列B审核启动与保留抽取")
DELIV.mkdir(parents=True, exist_ok=True)

_base = [json.loads(l) for l in
         (D / "V2-E3_原文与证据不可编辑字段基线.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()]
_base.sort(key=lambda r: r["snippet_id"])

CTX = 10          # ★ 前后文各 10 行
_pack = []
_html = []
_html.append("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>V2-E4 队列 B 只读证据包（54 条片段）</title>
<style>
body{font-family:Consolas,"Microsoft YaHei",monospace;margin:24px;color:#1a1a1a;line-height:1.5}
h1{font-size:20px}h2{font-size:15px;margin:24px 0 6px;padding:6px 10px;background:#eef3fa;border-left:4px solid #3a6ea5}
.meta{color:#555;font-size:12px;margin-bottom:4px}
table.ln{border-collapse:collapse;width:100%;margin:6px 0 10px}
table.ln td{padding:1px 8px;font-size:12.5px;vertical-align:top}
td.no{width:52px;color:#888;text-align:right;background:#f6f6f6;user-select:none}
tr.ev td{background:#fff6d8;font-weight:600}
tr.ctx td{color:#333}
.hint{background:#fffbe6;border:1px solid #e0c97a;padding:10px 14px;margin:14px 0;font-size:13px}
</style></head><body>
<h1>V2-E4 · 队列 B 只读 RFC 原文证据包</h1>
<div class="hint">
<b>给审核者：</b>本包是<b>只读</b>的 RFC 原文证据（含行号）。<br>
① 请用 <code>V2-E3_队列B_审核者X_Excel友好编辑模板.csv</code> 填写标注（该模板不含原文，故须对照本包）。<br>
② 本包<b>不含</b>任何模型预测、历史标签或「是否已生成候选」信息。<br>
③ 一个片段可发现 <b>0 / 1 / 多条</b>原子知识；多条时在原子知识表中<b>新增行</b>（序号改 -2、-3 …），不要覆盖。<br>
④ 原文未明确给出强度时写 <code>unknown</code>；<code>SHOULD NOT</code> ⇒ <code>strength=SHOULD</code> 且 <code>polarity=negative</code>。
</div>
""")

for b in _base:
    _p = ROOT / f'kb/{b["protocol"]}/spec/{b["document"]}'
    _L = _p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    _lo, _hi = b["★ 证据跨度（行号）"]
    _ctx = []
    for _i in range(max(1, _lo - CTX), min(len(_L), _hi + CTX) + 1):
        _ctx.append({"line": _i, "text": _L[_i - 1],
                     "★ 是否证据行": _lo <= _i <= _hi})
    _pack.append({
        "snippet_id": b["snippet_id"], "protocol": b["protocol"],
        "document": b["document"], "rfc_sha256": b["rfc_sha256"],
        "★ 章节类型": b["★ 章节类型"],
        "★ 证据跨度（行号）": [_lo, _hi],
        "★ 证据原文": b["★ 证据原文"],
        "★ 证据原文 sha256": b["★ 证据原文 sha256"],
        "★ 上下文行": _ctx,
        "★ 上下文范围": [max(1, _lo - CTX), min(len(_L), _hi + CTX)],
    })
    _html.append(f"""<h2>{html.escape(b['snippet_id'])}</h2>
<div class="meta">协议 {html.escape(b['protocol'])} ｜ 文档 {html.escape(b['document'])} ｜
章节类型 {html.escape(b['★ 章节类型'])} ｜ 证据行 <b>{_lo}–{_hi}</b> ｜
rfc_sha256 <code>{b['rfc_sha256'][:16]}…</code> ｜ 证据 sha256 <code>{b['★ 证据原文 sha256'][:16]}…</code></div>
<table class="ln">""")
    for c in _ctx:
        _cls = "ev" if c["★ 是否证据行"] else "ctx"
        _html.append(f'<tr class="{_cls}"><td class="no">{c["line"]}</td>'
                     f'<td>{html.escape(c["text"]) or "&nbsp;"}</td></tr>')
    _html.append("</table>")

_html.append("</body></html>")

_jl = DELIV / "V2-E4_队列B只读证据包.jsonl"
_jl.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in _pack) + "\n",
               encoding="utf-8")
_hp = DELIV / "V2-E4_队列B只读证据包.html"
_hp.write_text("\n".join(_html), encoding="utf-8")

_h = {
    "★ 只读证据包 jsonl": hashlib.sha256(_jl.read_bytes()).hexdigest(),
    "★ 只读证据包 html": hashlib.sha256(_hp.read_bytes()).hexdigest(),
    "★ 片段数": len(_pack),
    "★ 上下文行数": CTX,
}
(DELIV / "V2-E4_队列B只读证据包哈希.json").write_text(
    json.dumps(_h, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"  ★ 只读证据包：{len(_pack)} 条｜jsonl {_h['★ 只读证据包 jsonl'][:16]}"
      f"｜html {_h['★ 只读证据包 html'][:16]}")
print(f"  ★ 每个片段含 ±{CTX} 行上下文；★ 无模型预测/历史标签")
