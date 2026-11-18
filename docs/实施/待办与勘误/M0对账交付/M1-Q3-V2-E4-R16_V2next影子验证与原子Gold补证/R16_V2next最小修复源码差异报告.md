# R16 V2-next 最小修复源码差异报告

> ★ 生产 V2 未改动 ｜★ V2-next 为影子副本 ｜★ 0 次 LLM 调用

---

## 一、已验证事实

### 1.1 版本身份

| 项 | 值 |
|---|---|
| ★ 生产 V2 路径 | `docs\实施\待办与勘误\M0对账交付\M1-Q3-N2-B0-V2知识类型闸门\scripts\v2_knowledge_gate.py` |
| ★ 生产 V2 SHA256 | `81566fb71905e313bed67660e5d5ff788f3fbad46ccb145286e98457bd185047`（★ 本轮未改） |
| ★ V2-next 路径 | `guard\_out\_n1c_v2\r16\v2_knowledge_gate_next.py` |
| ★ V2-next SHA256 | `cc2a9b822e8f3f0c7a457296bb3efee85de2f89a8c4fe886cac05d1a4aedf22f` |
| ★ 差异行数 | 77 |
| ★ 回滚方式 | ★ 删除 V2-next 即可；★ 生产 V2 从未被写入 |

### 1.2 ★★ 根因（★ 与 R15 的 A 类归因不同）

★ **R15 把 12 条归为「A 对规范强度词依赖过强」，★ 本轮逐条取证后该归因不成立。**

| 取证结论 | 条数 |
|---|---:|
| ★ 原文确含 BCP14 但判据未识别（机制①：★ 关键词所在行非散文行） | 1 |
| ★ 窗口 ±3 行内无 BCP14（机制②） | 2 |
| ★ **非关键词识别问题** | **12** |

★ 进一步深探 15 条 mixed 样本后，★ 确认真实机制是：

> ★ `classify_candidate` 的跨句复核把**整段逻辑行**交给 `is_declarative_normative`，
> ★ 而该函数首行即「含 BCP14 ⇒ return False」。
> ★ 于是**只要逻辑行内任一句含强度词**，★ 跨句复核对**所有**候选都失效；
> ★ 候选随后落 `mixed_or_uncertain`。
> ★ 实测：★ 15 条中 **8 条**满足「_logical 含 BCP14 且去掉强度词后陈述式判定成立」。

★ **⇒ 问题不在「关键词没被识别」，★ 而在「关键词被识别后反而使判定失效」。**

### 1.3 三条修复边界（★ 均为收紧）

| # | 边界 | 内容 |
|---|---|---|
| ① | ★ 判定输入收紧 | ★ 整段逻辑行 → 锚点句及紧邻句 |
| ② | ★ 含 BCP14 时不扩展 | ★ 锚点句与受限上下文均不含强度词时才做扩展判定 |
| ③ | ★ 升级须锚点句自身具备行为义务特征 | ★ 义务动词 + 协议主体 |

★ **未改动**：★ 知识类型定义、★ 标签集合、★ 规则资格契约、★ 目标路由映射。

### 1.4 ★★ 四种策略的实测对照（★ 已接触 57 条，★ 诊断性）

| 策略 | 修复 | 反向误判 | 净收益 | 说明 |
|---|---:|---:|---:|---|
| S1 | 13 | 5 | 8 | ★ 整段逻辑行去强度词后判定（★ 原实现的方向） |
| S2 | 6 | 3 | 3 | ★ 锚点句及紧邻句去强度词后判定 |
| S3 | 2 | 3 | -1 | ★ S2 加「锚点句含 BCP14 则不扩展」 |
| S4 | 1 | 2 | -1 | ★ S2 加「锚点句自身须具备行为义务特征」 |

★ **四种策略全部存在反向误判**。★ 反向误判的内容一致：★ 把**描述性过程句**
★ （★ 如 DNS 查询过程、小写 should 的叙述句）★ 升级为规范义务。

★ ⇒ ★ **跨句复核是双刃机制**：★ 它把「无强度词但有行为义务」的句子纳入规则通道，
★ ★ 也把「描述性过程句」一并纳入。★ **单独收紧判定范围无法同时提升两侧**。

### 1.5 最终版（★ 当前 V2-next）的实测

| 指标 | V2 | V2-next | 变化 |
|---|---:|---:|---|
| 类型正确 | 18/57 | 21/57 | +3 |
| 资格正确 | 29/57 | 32/57 | +3 |
| 路由正确 | 18/57 | 21/57 | +3 |
| 合成样本符合期望 | 11/15 | 11/15 | 0 |
| 合成样本预测变化 | —— | —— | **0 条** |

★ 最终版：★ **修复 3 条、★ 反向误判 0 条、★ 合成样本 0 变化**。
★ 它修的是「描述性句被误升为规范义务」这一侧，★ **未修 R15 的 A 类 12 条**。

### 1.6 源码差异（★ 完整 unified diff 见附注）

```
--- v2_knowledge_gate.py
+++ v2_knowledge_gate_next.py
@@ -1,4 +1,6 @@
 # -*- coding: utf-8 -*-
+# ★ V2-next（R16 影子副本）：★ 基于冻结 V2 判据，★ 仅含一处最小修复。
+# ★ ★ 生产 V2 不受影响；★ V2-next 不得接入生产路径。
 """★ N2-B0-V2：★ **知识类型与来源作用域闸门**（★ 离线影子，★ 不接入生产）。
 
 ★ ★ 核心原则（★ 用户指定）：
@@ -71,6 +73,28 @@
 # ★ ⑤ 义务动词（★ 行为动词）
 _OBLIGATION_VERB = re.compile(
     r"\b(must|shall|should|may|required to|has to|ought to)\b", re.I)
+
+# ★ V2-next（R16）：★ 跨句复核的受限上下文辅助。
+# ★ 不改变任何既有匹配逻辑；★ 只用于跨句复核的判定输入构造。
+_NEAR_SENTENCE_SPAN = 1          # ★ 锚点句左右各取 1 句
+
+
+def _anchor_sentence_index(sents, pick):
+    """★ 找出 _pick 所在句的索引（★ 找不到则返回 0）。"""
+    if not pick:
+        return 0
+    _t = str(pick).strip()
+    for _i, _s in enumerate(sents):
+        if str(_s).strip() == _t:
+            return _i
+    return 0
+
+
+def _near_context(sents, pick_i):
+    """★ 取锚点句及紧邻句。"""
+    _lo = max(0, pick_i - _NEAR_SENTENCE_SPAN)
+    _hi = min(len(sents), pick_i + _NEAR_SENTENCE_SPAN + 1)
+    return sents[_lo:_hi], _lo, _hi
 # ★ ⑥ ABNF 产生式
 _ABNF_ASSIGN = re.compile(r"^\s*[A-Za-z][A-Za-z0-9._-]*\s*(::=|=|:=)\s*")
 _ABNF_CONT = re.compile(r"^\s*[|;]")
@@ -302,13 +326,31 @@
     _sk, _kk, _elig, _reason, _sig = classify_sentence(
         _target, _ctx, _meta_zone)
     # ★ ★ **陈述式规范句的跨句复核**（★ 条件/主体常在相邻句 ⇒ ★ 在逻辑行上再判一次）
-    if _kk != NORMATIVE_RULE_CANDIDATE and _logical:
-        _decl2, _r2 = is_declarative_normative(_logical)
-        if _decl2:
-            _sk = _kk = NORMATIVE_RULE_CANDIDATE
-            _elig = "eligible"
-            _reason = ("★ 跨句复核（★ 完整逻辑行）：" + _r2)
-            _sig["★ 陈述式规范句（跨句）"] = True
+    if _kk != NORMATIVE_RULE_CANDIDATE and _sents:
+        # ★ ★ V2-next 最小修复（R16）：★ 修复「逻辑行含 BCP14 ⇒ 跨句复核失效」
+        #   ★ 这一处机制缺陷。
+        # ★ 原实现把**整段逻辑行**交给 is_declarative_normative，★ 而该函数首行即
+        #   ★ 「含 BCP14 ⇒ return False」；★ 于是当逻辑行内任一句含强度词时，
+        #   ★ 跨句复核对**所有**候选都失效 ⇒ 含强度词但主体/动词不明的候选落 mixed。
+        # ★ 本实现的三条边界（★ 均为收紧，★ 不放宽）：
+        #   ① 判定输入：★ 整段逻辑行 → ★ 锚点句及紧邻句；
+        #   ② 触发条件：★ 锚点句与受限上下文均不含 BCP14（★ 含强度词时仍走原单句判据）；
+        #   ③ 升级条件：★ 锚点句本身须具备行为义务特征（★ 义务动词 + 协议主体），
+        #   ★ 避免把描述性过程句或小写 should 的叙述句一并升级。
+        _pi = _anchor_sentence_index(_sents, _pick)
+        _near, _nlo, _nhi = _near_context(_sents, _pi)
+        _anchor_sent = _sents[_pi] if 0 <= _pi < len(_sents) else ""
+        _near_has_bcp = any(_BCP14.search(_s) for _s in _near)
+        _anchor_behaviour = bool(_OBLIGATION_VERB.search(_anchor_sent)) \
+            and bool(_PROTOCOL_ACTOR.search(_anchor_sent))
+        if (not _near_has_bcp) and _anchor_behaviour:
+            _decl2, _r2 = is_declarative_normative(" ".join(_near))
+            if _decl2:
+                _sk = _kk = NORMATIVE_RULE_CANDIDATE
+                _elig = "eligible"
+                _reason = ("★ 跨句复核（★ 受限上下文：★ 锚点句及紧邻句）：" + _r2)
+                _sig["★ 陈述式规范句（跨句）"] = True
+                _sig["★ 跨句复核范围（句索引）"] = f"{_nlo}-{_nhi - 1}"
     _route = route_of(_kk, _elig)
     # ★ 证据跨度（★ 只覆盖被判定的那一句，★ 保留原始证据）
     _ev_line = anchor
```

## 二、★ 保留的未解决问题

★ **R15 的 39 条知识类型错误分为**：★ A 类 12 条、★ B 类 6 条、★ C 类 16 条、★ E 类 5 条待定。
★ **本轮方案一不应被表述为已解决全部 39 条。**

★ 特别是 **5 条 E 类（Gold 与 V2 分类契约不一致）★ 继续保持 unresolved 状态**：
★ 本轮未改变 `strength=unknown` 的契约。

★ **`strength=unknown` 的语义分歧**：★ 「规范强度未知」与「知识类型不确定」是两个不同概念，
★ ★ 本轮**明确区分**了二者（★ 判据信号中分别记录），★ **但未改变该契约**。

★ **R14 首次事后评估结果及 106 条跨指标错误记录保持冻结。**

## 三、限制

1. ★ 全部对照基于**已接触的 57 条**，★ 只能作为诊断证据，★ **不构成独立泛化结果**。
2. ★ 最终版只净增 3 条，★ 相对 S1 的 +8 明显保守；★ 保守的理由是零反向误判。
3. ★ 本轮未创建 V2-next 的正式版本号与预注册，★ 待审批。

## 四、下一步

★ 若批准修复：★ ① 确定采用哪一策略（★ 当前影子副本为最保守的最终版）；
★ ② 冻结 V2-next 的版本号、标签映射、投影规则与匹配规则并登记 SHA256；
★ ③ 按《R15_新协议独立验证设计.md》准备**未参与本轮调试**的新 RFC 样本与独立人工 Gold；
★ ④ 一次性执行并报告。

★ **★ 本轮未证明 V2-next 具有泛化能力。**
