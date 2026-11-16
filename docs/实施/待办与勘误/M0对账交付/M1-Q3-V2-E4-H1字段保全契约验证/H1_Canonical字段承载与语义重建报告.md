# H1 · Canonical 字段承载与语义重建报告

> ★ 只读核对（★ 沿 `core/fused/extraction/norm.py` 与 `normative_rule.py` 实际源码）

---

## 一、★ 散文规范规则的 canonical 承载（★ 已确认的契约）

```python
# core/fused/extraction/norm.py:513  prose_constraint_norm_to_facts
# ★ Rule Slot（★ 行为位置 ⇒ 进事实身份）
_quals = {"action": _action, "object": _object, "kind": RULE_KIND}
# ★ Assertion（★ 规范内容 ⇒ 进声明的值）
_payload = build_payload(subject=name, action=_action, object_=_object,
                         strength=n.get("strength"), polarity=n.get("polarity"),
                         condition=_condition, condition_status=...,
                         exception=..., scope=..., cross_ref=...,
                         cross_ref_status=...)
_txt = rule_text(_payload)          # ★ "[RULE:v1] " + 规范化 JSON
_subj = Subject(type="header", name=_subj_name, qualifiers=_quals)
_val  = Value(type="text", data=_txt)
```

---

## 二、★ 逐项承载核对（★ 用户 §五 的 7 问）

| # | 字段 | ★ canonical 承载位置 | ★ 是否参与 FactID | ★ 能否重建 |
|---|---|---|:---:|:---:|
| ① | ★ `normative_subject` | ★ **Rule Slot 的 subject.name**（★ `norm.py:548`）★ **用义务主体而非 entity** | ✔ 是 | ✔ |
| ② | ★ `action` / `object` | ★ **Rule Slot qualifiers** | ✔ 是 | ✔ |
| ③ | ★ `strength` / `polarity` | ★ **Assertion（★ `[RULE:v1]` JSON）** | ✖ **不参与** | ✔ |
| ④ | ★ `condition` / `exception` | ★ **Assertion**；★ 缺失时 status ⇒ **unknown**（★ **不默认 absent**） | ✖ | ✔ |
| ⑤ | ★ `evidence_span` | ★ `norm.source` + `span_line` + `evidence_quote/span` + claim provenance | ✖ | ✔ |
| ⑥ | ★ 多证据跨度 | ★ `evidence_aux` / `evidence_cross_chunk` / `evidence_degraded` | ✖ | ✔ |
| ⑦ | ★ 整体语义重建 | ★ ★ **`parse_rule_text(text)` ⇒ payload** | —— | ✔ |

---

## 三、★★ 关键缺口：★ 两个降级分支只存 `constraint` 文本

| 分支 | ★ 触发条件 | ★ Fact 内容 | ★ 丢失的语义 |
|---|---|---|---|
| ★ **分支1** | ★ `subject_status != "resolved"` | ★ `Value(text, str(constraint))` + `definition` aspect | ★ **action / object / strength / polarity / condition / exception / cross_ref / cross_ref_status** |
| ★ **分支2** | ★ action/object 缺失或为主体名占位 | ★ 同上 | ★ 同上 |
| ★ **正常路径** | ★ —— | ★ Rule Slot + Assertion | ★ **无丢失** |

⇒ ⇒ ★★★ **★ 语义保全的判据：★ 在降级分支中，★ `constraint` 文本里【可能仍含】强度与极性的语言表述
★ （★ 如 "Clients SHOULD NOT provide …"），★ 但【结构化字段】不可重建 ⇒ ★ 属【语义不完整】而非【语义错误】**

---

## 四、★ 与既有身份设计的相容性（★ 用户 §五 明确列出的约束）

| ★ 约束 | ★ 本方案是否触碰 |
|---|:---:|
| ★ 散文规范规则继续使用 `definition` aspect | ✖ 不触碰 |
| ★ 通过既有 Rule Slot / qualifiers 区分规范规则 | ✖ 不触碰 |
| ★ 使用 `[RULE:v1]` 标识规范规则内容 | ✖ 不触碰 |
| ★ strength/polarity 位于 Assertion，★ 不参与 FactID 身份 | ✖ 不触碰 |
| ★ 不新增 aspect | ✖ 不新增 |
| ★ 不建立第二套平行 FactID | ✖ 不建立 |

⇒ ⇒ ★★★ **★ ⇒ 任何修复都【不得】改变上表任一项**
