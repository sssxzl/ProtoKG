# R17 V2-next 当前策略与四策略差异报告

> ★ 影子验证 ｜★ 生产 V2 未改 ｜★ 0 次 LLM 调用

---

## 一、已验证事实

### 1.1 当前影子版本的准确算法与代码路径

★ 路径：`guard/_out/_n1c_v2/r16/v2_knowledge_gate_next.py`（★ 影子副本，★ 不接入生产）
★ 修改点：`classify_candidate` 内的跨句复核分支（第 329–353 行）。

```python
  329:     if _kk != NORMATIVE_RULE_CANDIDATE and _sents:
  330:         # ★ ★ V2-next 最小修复（R16）：★ 修复「逻辑行含 BCP14 ⇒ 跨句复核失效」
  331:         #   ★ 这一处机制缺陷。
  332:         # ★ 原实现把**整段逻辑行**交给 is_declarative_normative，★ 而该函数首行即
  333:         #   ★ 「含 BCP14 ⇒ return False」；★ 于是当逻辑行内任一句含强度词时，
  334:         #   ★ 跨句复核对**所有**候选都失效 ⇒ 含强度词但主体/动词不明的候选落 mixed。
  335:         # ★ 本实现的三条边界（★ 均为收紧，★ 不放宽）：
  336:         #   ① 判定输入：★ 整段逻辑行 → ★ 锚点句及紧邻句；
  337:         #   ② 触发条件：★ 锚点句与受限上下文均不含 BCP14（★ 含强度词时仍走原单句判据）；
  338:         #   ③ 升级条件：★ 锚点句本身须具备行为义务特征（★ 义务动词 + 协议主体），
  339:         #   ★ 避免把描述性过程句或小写 should 的叙述句一并升级。
  340:         _pi = _anchor_sentence_index(_sents, _pick)
  341:         _near, _nlo, _nhi = _near_context(_sents, _pi)
  342:         _anchor_sent = _sents[_pi] if 0 <= _pi < len(_sents) else ""
  343:         _near_has_bcp = any(_BCP14.search(_s) for _s in _near)
  344:         _anchor_behaviour = bool(_OBLIGATION_VERB.search(_anchor_sent)) \
  345:             and bool(_PROTOCOL_ACTOR.search(_anchor_sent))
  346:         if (not _near_has_bcp) and _anchor_behaviour:
  347:             _decl2, _r2 = is_declarative_normative(" ".join(_near))
  348:             if _decl2:
  349:                 _sk = _kk = NORMATIVE_RULE_CANDIDATE
  350:                 _elig = "eligible"
  351:                 _reason = ("★ 跨句复核（★ 受限上下文：★ 锚点句及紧邻句）：" + _r2)
  352:                 _sig["★ 陈述式规范句（跨句）"] = True
  353:                 _sig["★ 跨句复核范围（句索引）"] = f"{_nlo}-{_nhi - 1}"
  354:     _route = route_of(_kk, _elig)
  355:     # ★ 证据跨度（★ 只覆盖被判定的那一句，★ 保留原始证据）
  356:     _ev_line = anchor
  357:     if _pick:
  358:         for i in range(max(1, anchor - window), min(len(lines), anchor + window) + 1):
```

★ **三条边界**：
1. ★ 判定输入：★ 整段逻辑行 → 锚点句及紧邻句；
2. ★ 触发条件：★ 受限上下文含 BCP14 时**不**触发；
3. ★ 升级条件：★ 锚点句自身须具备行为义务特征（★ 义务动词 + 协议主体）。

### 1.2 ★★ 与 S1～S4 的关系（★ 逐条核对，★ 不以汇总准确率为依据）

| 策略 | 判定输入 | 含 BCP14 时 | 锚点须有行为义务特征 | 修复 | 反向误判 |
|---|---|---|---|---:|---:|
| S1 | 整段逻辑行 | ★ 继续去强度词判定 | 否 | 13 | 5 |
| S2 | 锚点句及紧邻句 | ★ 继续去强度词判定 | 否 | 6 | 3 |
| S3 | 锚点句及紧邻句 | ★ 不扩展 | 否 | 2 | 3 |
| S4 | 锚点句及紧邻句 | ★ 不扩展 | ★ 是 | 1 | 2 |
| **★ 当前影子版本** | ★ 锚点句及紧邻句 | ★ 不扩展 | ★ **是** | **3** | **0** |

★ 当前影子版本在三条边界上与 S4 一致；★ 但其实测「修复 3、反向 0」
★ 与 R16 记录的 S4「修复 1、反向 2」**不一致**。

★ **原因**（★ 本轮查实）：★ R16 的 S4 对照脚本在判定时**剥离了强度词**再判陈述式，
★ 而实际影子代码在边界②下**直接不触发**扩展，★ 两者语义不同。
★ **⇒ R16 的 S1～S4 对照数字与实际影子版本的对应关系有误，★ 本报告以实测为准。**

### 1.3 ★ 当前影子版本的真实修复对象（★ 与 R16 的表述不同）

★ 实测变化 **4 条**（★ R16 记录为 3 条，★ 漏记了 1 条对错不变者）：

| candidate_id | 协议 | V2 预测 | V2-next 预测 | Gold | 性质 |
|---|---|---|---|---|---|
| X-sip-rfc2543-08 | sip | normative_rule_candidate/eligible | protocol_descriptive_semantics/ineligible | non_protocol_metadata/not_applicable | ★ 变化但对错不变 |
| X-sip-rfc2543-09 | sip | normative_rule_candidate/eligible | protocol_descriptive_semantics/ineligible | protocol_descriptive_semantics/ineligible | ★ 修复 |
| X-sip-rfc2543-10 | sip | normative_rule_candidate/eligible | protocol_descriptive_semantics/ineligible | protocol_descriptive_semantics/ineligible | ★ 修复 |
| X-sip-rfc2543-11 | sip | normative_rule_candidate/eligible | protocol_descriptive_semantics/ineligible | protocol_descriptive_semantics/ineligible | ★ 修复 |

★ **三条修复均为「降级」**：★ `normative_rule_candidate` → `protocol_descriptive_semantics`。
★ **不是** R15 的 A 类「mixed → normative_rule_candidate」方向。

★ 成因（★ 逐条查实）：★ 这三条的锚点行是 DNS 查询过程的**描述性叙述句**
★ （★ 如「results of the query or queries are merged together and ordered based on priority」、
★ ★ 「the searching technique ... is used to select servers in order」、「the user goes to ...」）。
★ V2 原版因**整段逻辑行**被判为陈述式规范句而强制升级为规范义务；
★ 当前影子版本因锚点句缺协议主体而**不触发**扩展，★ 保留单句判据的描述性结果。

★ ⇒ **真正起作用的是边界③（★ 锚点句须具备行为义务特征），★ 而非 R16 报告所称的
★ 「修复含 BCP14 时跨句复核失效」。**

### 1.4 为何未产生反向误判

★ 当前影子版本只做**升级**，★ 而三条变化全是**降级**。
★ 原因：★ 降级发生在**不触发扩展**时（★ 保留单句判据），★ 升级须同时满足三条边界。
★ 实测触发跨句复核的候选仅 **3 条**，★ 且均未造成反向误判。

★ ★ **与 R15 的 A 类 12 条无对应关系**：★ 那 12 条在当前影子版本下**预测完全未变**
★ （★ 因为它们的受限上下文含 BCP14，★ 边界②使其不触发扩展）。

### 1.5 合成测试为何原 V2 与 V2-next 均为 11/15 且 0 变化

★ 合成样本共 15 条，★ 其中**没有一条同时满足**「受限上下文无 BCP14」且
★ 「锚点句具备行为义务特征」且「受限上下文判定为陈述式」。

★ 具体地：★ 含 MUST/SHOULD/MAY 的样本（SYN-01～07、14）★ 其上下文含 BCP14
★ ⇒ 边界②使其不触发扩展 ⇒ 判定与 V2 相同。
★ 无关键词的样本（SYN-08、12）★ 锚点句缺协议主体 ⇒ 边界③使其不触发扩展。
★ ⇒ **15 条全部不触发扩展 ⇒ 0 变化 ⇒ 两版都是 11/15。**

★ ★ **这说明合成样本对当前方案的区分力不足**：★ 它验证了「未引入新误判」，
★ ★ 但**未能验证「能否修复目标错误」**。★ 若要覆盖当前方案的有效路径，
★ ★ 需补一类样本：★ 「受限上下文无 BCP14、★ 锚点句含协议主体与行为动词、★ 但单句判据因主体/动词分散而落 mixed」。

### 1.6 哈希与回滚

| 项 | 值 |
|---|---|
| ★ 冻结 V2 SHA256 | `81566fb71905e313bed67660e5d5ff788f3fbad46ccb145286e98457bd185047` |
| ★ V2-next SHA256 | `cc2a9b822e8f3f0c7a457296bb3efee85de2f89a8c4fe886cac05d1a4aedf22f` |
| ★ 生产 V2 是否被改 | **否** |
| ★ 回滚方法 | ★ 删除 V2-next 影子文件即可；★ 生产 V2 从未被写入 |

## 二、限制

1. ★ 全部对照基于**已接触的 57 条**与合成样本，★ **不构成独立泛化证据**。
2. ★ R16 的 S1～S4 对照数字与实际影子版本的对应关系有误，★ 本报告以实测为准。
3. ★ 当前方案**未修复 R15 的 A 类 12 条**。

## 三、下一步

★ 若要覆盖当前方案的有效路径，★ 须补「锚点句有行为义务特征但单句判据落 mixed」的合成样本；
★ 后续验证 V2-next 必须使用新冻结、★ 未参与当前规则选择的 RFC 数据。
