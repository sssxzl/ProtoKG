# H2A · 回归测试与版本哈希

> ★ 基线：★ 提交 `3c9a1d2` ｜★ **零生产改动**｜★ **0 次 LLM 调用**

---

## 一、★ 回归测试（★ 15 个，全通过）

★ 文件：`tests/extraction/test_h2a_scheme_a.py`
★ 覆盖：★ sidecar 不触碰生产对象 ｜★ 字段适用性 ｜★ **unmeasured ≠ 0** ｜★ ambiguous/unresolved 不伪造哈希
★ ｜★ 重复执行可区分 ｜★ V0/V1/V2 哈希不变 ｜★ FactID 不变 ｜★ 21 aspects 不变
★ ｜★ strength/polarity 不进 qualifiers ｜★ 中枢与 Seed 逐字节一致 ｜★ Gold 四态 ｜★ 仲裁有效性 ｜★ 97 闭合

---

## 二、★ 护栏结果

```
5 failed / 1610 passed / 227 skipped
★ 新增 0 / 消失 0
★ 编码卫生：✅ 达标
★ 正式中枢 derived/hub/：★ 逐字节一致
★ 正式种子 derived/seeds/：★ 逐字节一致
```

### 2.1 ★★ 两个既有测试的断言更新（★ 如实记录）

| 测试 | 变更 | ★ 原因 |
|---|---|---|
| ★ `test_arbitration_template_has_required_audit_fields` | ★ `len == 54` ⇒ ★ **`len >= 54` 且覆盖全部基线 snippet_id** | ★ 审核者已填写；★ 一片段多条知识 ⇒ 复制行（★ 97 行） |
| ★ `test_excel_template_excludes_raw_text` | ★ 同上 | ★ 同上（★ 128 行） |

★ ⇒ ★★ **校验强度未被削弱**（★ 反而增加了「覆盖全部基线」的要求）

---

## 三、★ 版本哈希

| 文件 | SHA256 |
|---|---|
| ★ H2A 回归测试 | `a4a0d4c68e264da0283297ef7bc9f5e412a97570629199f0c9f42b391a59ac68` |
| ★ M1-Q3-V2-E4-B1队列B人工真值验收/B1_H1H2H3分离匹配预注册方案.md | `17e4ba7c481b38be4af4dffbaf54c5118bfc4bdf7629eb848168999dd6e16c94` |
| ★ M1-Q3-V2-E4-B1队列B人工真值验收/B1_人工审核回收与编码验收.md | `8b68ade026219aeb86c959cc4c406831852d7f529d9e3c2fbad7b4aebcc54876` |
| ★ M1-Q3-V2-E4-B1队列B人工真值验收/B1_人工真值冻结清单.jsonl | `b99467a4d806910f78b11ef2278ed0e28eab12ee4906e6fdc137787c6bc2cd23` |
| ★ M1-Q3-V2-E4-B1队列B人工真值验收/B1_冻结哈希与未决项.md | `009059bf49a8f758b9886033a3fcc5f907b5c5b8230e039598cc996af3572835` |
| ★ M1-Q3-V2-E4-B1队列B人工真值验收/B1_原子知识对齐台账.jsonl | `b99467a4d806910f78b11ef2278ed0e28eab12ee4906e6fdc137787c6bc2cd23` |
| ★ M1-Q3-V2-E4-B1队列B人工真值验收/B1_双人一致性与分歧报告.md | `1a5069fba915327ebd10844b32c2761c9695a0a7369ce049fe4ba94b330b22e6` |
| ★ M1-Q3-V2-E4-B1队列B人工真值验收/B1_独立评测准入报告.md | `a54b191040d4f9db8dab9f92e56e19552a1adc85def72c267d0d486c3c470b37` |
| ★ M1-Q3-V2-E4-B1队列B人工真值验收/B1_第三方仲裁有效性检查.md | `6d62abcfefb6b29aa011897ab79be870e8d54bd6041b1609fd4aa41787bbe78f` |
| ★ M1-Q3-V2-E4-H2A方案A兼容性证明/H2A_13条降级路径语义证据链.jsonl | `d1e03eba364b069e7235ecf8cadec3da8b754232bd489efa6fcdf77779b1e9a4` |
| ★ M1-Q3-V2-E4-H2A方案A兼容性证明/H2A_回归测试与版本哈希.md | `00bd808e6ae205e82d4758223951cafec003461b23180e966c19adb3b03f8c27` |
| ★ M1-Q3-V2-E4-H2A方案A兼容性证明/H2A_字段级统计勘误.md | `e9c3a6e8ab1937a05f49989918a2817dfb53f3292e052bee42cdea951a518854` |
| ★ M1-Q3-V2-E4-H2A方案A兼容性证明/H2A_影子Sidecar示例.jsonl | `ba715bd2eda49161a62cf1c47e735bcc7aa985eba057c305e3d5a0d6438256de` |
| ★ M1-Q3-V2-E4-H2A方案A兼容性证明/h2_b1_acceptance.json | `95dc46d3cff43651e9dc4ed09d85cf9c7fff859c54814ceadce1adb645b2a5ff` |
| ★ M1-Q3-V2-E4-H2A方案A兼容性证明/h2a_compat_proof.json | `ab7a20aa3b470d12baf6e02fb3d562ffc0368618f1e7f2ead1693f894b903d2e` |
| ★ M1-Q3-V2-E4-H2A方案A兼容性证明/h2a_stats_audit.json | `33bb3334fbf3a83ffc66ff2d675e66495d1ad0b5b25e163d213e786aaec30c7c` |

---

## 四、★ 状态

> ★★ **「V2-E4-H2A 方案 A 最小兼容实现及证明完成，生产接入待审」**
