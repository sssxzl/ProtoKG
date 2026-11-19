# T0-A Fact 错误分流根因与源码定位

## 一、第一现场

`core/fused/extraction/prose_semantics.py:1397-1404`：

```python
_is_placeholder = (not _act or not _obj
                   or (_act.lower() == ent.lower()
                       and _obj.lower() == ent.lower()))
# ★ ★ 主体未解析 ⇒ 不成规则
if _subject_status != "resolved":
    _is_placeholder = True                    # ← 根因
kind = ("prose_semantics" if _is_placeholder
        else ("prose_constraint" if con else "prose_semantics"))
```

## 二、四问四答

**1. 为什么 127/146 被判 unresolved？**

模型给的 `normative_subject` 是 `publicly-referenced SMTP server`（127）与 `server`（146），与原文实体 `SMTP server` 不完全一致，主体解析器判定无法对齐 ⇒ `subject_status=unresolved`。这个判定本身没错。

**2. 哪个条件让有 constraint/action/object 的条目落到 prose_semantics？**

就是上面那句 `if _subject_status != "resolved": _is_placeholder = True`。它把「主体未解析」直接并入「不是规范义务」，于是 `kind` 被强制成 `prose_semantics`，`con` 非空也不起作用。

**3. 主体未解析与「是否构成规范义务」是否被错误绑定？**

是。二者是两件事：主体能不能对上是谁在承担义务，与该条是否表达了一项义务（有 MUST/SHOULD、有动作、有对象）无关。原实现把后者让位给前者。

**4. 有没有安全保留主体限定的既有机制？**

有。`prose_constraint_norm_to_facts` 已有一条专门处理 unresolved 的分支，产出 `legal_boundary` 并保留文本；上一轮我又给它补了 `qualifiers(action/object)`。所以只要 kind 分流正确，主体不确定性可以原样保留，不需要猜主体、也不需要伪造 Rule Slot（该分支不产 `[RULE:v1]` payload）。

## 三、其他 unresolved 条目

| span | constraint | 分流后 |
|---|---|---|
| 313 | SHOULD also be provided | prose_constraint（legal_boundary） |
| 352 | MAY be used in conjunction with | prose_constraint（legal_boundary） |
| 155（对照，已 resolved） | MUST start TLS negotiation | 仍 prose_constraint |

313/352 与 127/146 同类：确有约束措辞，只是主体没对上。把它们一并归回约束类是**一致**处理，不是放宽。

## 四、修正

删除那两行强制降级，仅由「动作/对象缺失或占位」决定描述/规范分流：

```python
_is_placeholder = (not _act or not _obj
                   or (_act.lower() == ent.lower()
                       and _obj.lower() == ent.lower()))
kind = "prose_semantics" if _is_placeholder else ("prose_constraint" if con else "prose_semantics")
```

主体不确定性由 `prose_constraint` 的 unresolved 分支承担，FactID 算法、aspects、Schema 均未改。
