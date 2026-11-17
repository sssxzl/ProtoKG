# R12 跨协议 Gold 最终冻结候选与差异说明

> ★ 依 R11 人工审核结果生成 v3 候选 ｜★ v1 与 v2 均保留未覆盖
> ★ 本轮 0 次 LLM 调用；★ 未执行正式指标

---

## 一、已验证事实

### 1.1 R11 审核结果

| Gold ID | 是否独立 | 与其他 Gold 重复 | 审核者 | 日期 |
|---|---|---|---|---|
| SMTP-ATOM-X-smtp-rfc3461-04-a | 是 | 否 | A | 2026-11-18 |
| SMTP-ATOM-X-smtp-rfc3461-04-b | **否** | 是（★ 与候选 3461-05 的原子重复） | A | 2026-11-18 |
| SMTP-ATOM-X-smtp-rfc6531-01-a | 是 | 否 | A | 2026-11-18 |
| SMTP-ATOM-X-smtp-rfc6531-01-b | **否** | 是（★ 与 a 条完全同质，★ 仅术语名不同） | A | 2026-11-18 |

★ 48 个待填格全部填写，★ 每条均有独立命题文本、主体、动作、对象、强度、极性、
★ 必要条件、重复判定、证据理由、审核者与日期。

### 1.2 审核的两处论证要点

**SC-05-b（ORCPT）**：★ 原文第 1092 行「and/or ORCPT parameter MAY be used」，
★ 而候选集中已有 X-smtp-rfc3461-05（跨度 1092、对象 ORCPT parameter、强度 MAY）。
★ 二者同一命题，★ 再单列会把 ORCPT 的 MAY 许可计入两次。
★ SC-05 的正确处理是「1 条改写 + 0 条新增」：★ 3461-04 收窄为 ENVID，★ 3461-05 保持 ORCPT。

**SC-06-b（UTF-8 character）**：★ 原文用「The terms X or Y are used to refer to …」
★ 的 or 结构，★ X 与 Y 是同一概念的两种叫法，★ 不是两个独立事实。
★ 保留 a 条（以「UTF-8 string」为主条目），★ 把「UTF-8 character」记为别名。

★ **两条排除均按「不得为凑数保留」执行**，★ 未为保持 65 条总数而强行保留。

### 1.3 审核指出的两处 Gold 缺陷（已修正）

| Gold ID | 字段 | v2 值 | v3 候选值 |
|---|---|---|---|
| SMTP-ATOM-X-smtp-rfc3461-04-a | 强度 | unknown | MAY |
| SMTP-ATOM-X-smtp-rfc3461-04-a | 极性 | （空） | positive |
| SMTP-ATOM-X-smtp-rfc6531-01-a | 规则资格 | eligible | **ineligible** |
| SMTP-ATOM-X-smtp-rfc6531-01-a | 强度 | unknown | not_applicable |
| SMTP-ATOM-X-smtp-rfc6531-01-a | 极性 | （空） | not_applicable |

★ 6531-01-a 的资格修正使其与 C 仲裁的 ineligible 一致（★ 描述性语义不入规则通道）。

### 1.4 版本谱系

| 版本 | 文件 | SHA256 | 状态 |
|---|---|---|---|
| v1 | R10_跨协议Gold冻结基线.jsonl | `bbce8979138605160f9af1c1c72a8c6c3b4750f31f808e9f03e2548f4b2a57eb` | ★ 冻结，★ 未覆盖 |
| v2 | R11_跨协议Gold冻结基线_v2候选.jsonl | `0f9ab8350da73359153473aeb9428001f45441828482583a1d0fed8f4f6cc38b` | ★ 候选，★ 未覆盖 |
| v3 | R12_跨协议Gold冻结基线_v3候选.jsonl | `eb66b74533c93b931e58db73cf4b2c36268f6e2fd885042bcb9ee1cc3f4ea570` | ★ 候选，★ 待审批 |

### 1.5 v3 的构成

| 项 | v2 | v3 |
|---|---:|---:|
| 候选级 | 57 | **57** |
| 原子级 | 8 | **6** |
| 合计 | 65 | **63** |

★ 六条原子知识：

| Gold ID | 类型 | 资格 | 路由 | 强度 | 来源 |
|---|---|---|---|---|---|
| RTSP-ATOM-X-rtsp-rfc7826-03-1 | normative_rule_candidate | eligible | rule_channel | MUST | A、B、C |
| RTSP-ATOM-X-rtsp-rfc7826-05-1 | protocol_registry_or_enumeration | eligible | structured_channel | unknown | C |
| SMTP-ATOM-X-smtp-rfc3461-03-1 | normative_rule_candidate | eligible | rule_channel | unknown | C |
| SMTP-ATOM-X-smtp-rfc3461-04-a | normative_rule_candidate | eligible | rule_channel | MAY | A |
| SMTP-ATOM-X-smtp-rfc6531-01-a | protocol_descriptive_semantics | ineligible | descriptive_channel | not_applicable | A |
| SMTP-ATOM-X-smtp-rfc8098-03-1 | normative_rule_candidate | eligible | rule_channel | unknown | C |

## 二、限制

1. ★ 本次人工审核**仅覆盖 SC-05 与 SC-06 的四条**；★ 其余三条原子知识
   （★ 7826-03-1、7826-05-1、3461-03-1、8098-03-1）★ 强度仍记 unknown、★ 极性为空，
   ★ **未经边界复核**，★ 其字段级准确性未验证。
2. ★ R10-P1 仍为事后补充规则，★ 相关指标须标注为事后分析。
3. ★ 评估脚本仍未冻结，★ 正式指标不得启动。

## 三、下一步

1. ★ 审批 v3 候选并冻结（★ 本轮不自行冻结）。
2. ★ 冻结评估脚本、输入、指标定义、标签映射与匹配规则并登记 SHA256。
3. ★ 一次性执行正式指标，★ 分协议报告并披露事后规则影响。

## 四、状态

R12 跨协议 Gold 最终冻结候选已生成，待审批冻结；V2 正式指标计算待执行。
