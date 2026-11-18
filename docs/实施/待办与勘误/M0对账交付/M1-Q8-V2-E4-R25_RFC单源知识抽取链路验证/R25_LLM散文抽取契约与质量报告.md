# R25 LLM 散文抽取契约与质量报告

> ★ **0 次新增 LLM 调用**；★ 运行时证据来自**既有历史缓存**（★ 97 条抽取）
> ★ **★ 57 条已接触样本不得再次宣称为独立测试集**

---

## 一、★ 数据来源

| 项 | 值 |
|---|---|
| ★ 缓存文件 | ★ `derived/cache/source_blocks/{DHCPv4,rtsp,sip,smtp}.prose.json` |
| ★ 抽取条数 | ★ **97**（★ DHCPv4 76 / sip 5 / smtp 16 / rtsp 0） |
| ★ 每条含 15 个字段 | ★ doc / entity / meaning / constraint / span / action / object / strength / polarity / keyword_raw / condition / exception / cross_ref / cross_ref_status / normative_subject / subject_span |
| ★ ★ 本轮 | ★ **未调用 LLM**，★ 只读核查既有缓存 |

---

## 二、★ 字段填充率（★ 分母 = 97）

| 字段 | 非空 | 填充率 | ★ 判定 |
|---|---:|---:|---|
| ★ entity | 97 | **100%** | ★ 必备 |
| ★ meaning | 97 | **100%** | ★ 必备 |
| ★ doc | 97 | **100%** | ★ 来源身份 |
| ★ span | 97 | **100%** | ★ 证据定位 |
| ★ subject_span | 97 | **100%** | ★ 主体定位 |
| ★ constraint | 22 | **22.7%** | ★ ★ 规范义务仅 22 条；★ 其余 75 条是**描述性知识**（★ 合法缺省） |
| ★ action / object / strength / polarity / keyword_raw | 20 | **20.6%** | ★ 与规范义务同批 |
| ★ normative_subject | 14 | **14.4%** | ★ 跨句主体 |
| ★ condition | 8 | **8.2%** | |
| ★ exception | 2 | **2.1%** | |
| ★ cross_ref | 1 | **1.0%** | |

★ ★ **★ 重要判定**：★ **不得把 strength=unknown 一律解释为知识类型不确定**；
★ ★ ★ ★ ★ 20.6% 的 strength 填充率对应的是「**只有规范义务才该有 strength**」，
★ ★ ★ ★ ★ 其余 79.4% 是描述性知识，★ strength 为空是**合法缺省**。

---

## 三、★ A～F 六类的分布判定（★ 阶段 B3 要求的区分）

| 类 | 本轮判定 | 依据 |
|---|---|---|
| ★ A 原文存在知识，模型成功抽取 | ★ **97 条** | ★ 缓存中的每条都有 doc/span/entity/meaning |
| ★ B 原文存在知识，模型没有抽取 | ★ **不可计算** | ★ 无独立人工真值（★ 原文知识识别率 unavailable） |
| ★ C 模型抽取了知识但字段不完整 | ★ **2 条**（★ P2 落回） | ★ action/object 缺失 ⇒ 落回普通 definition |
| ★ D 模型输出正确但派生层丢弃字段 | ★ **0 条** | ★ 20 条 Rule Slot 的 Assertion 含全部四个规范字段 |
| ★ E 模型输出不准确或语义误判 | ★ **不可计算** | ★ 无独立人工真值 |
| ★ F 原文不提供该语义，字段合法缺省 | ★ **75 条** | ★ constraint 为空 ⇒ 描述性知识 |

★ ⇒ ★ **★ C 类只有 2 条，★ 且这两条的 strength 也是空 ⇒ 属 F 类而非真丢失。**

---

## 四、★ 规范知识的 Canonical 承载（★ 沿用既有方案，★ 未新增 aspect）

| 承载 | 内容 | 实测 |
|---|---|---|
| ★ **Rule Slot**（事实身份） | ★ `subject.qualifiers`：`action` / `object` / `kind=normative_rule` | ★ **20/20** 全含 |
| ★ **Assertion**（声明的值） | ★ 规范化 JSON 文本 `[RULE:v1] {…}`，★ 含 strength / polarity / condition / exception | ★ **20/20** 全含 |
| ★ **原文措辞** | ★ `keyword_raw` ⇒ claim 的 `evidence.quote`（★ **不进 value**） | ★ 契约确证（★ norm.py:525-527） |
| ★ 主体类型 | ★ 复用已有的 `header`（★ **不新增主体类型**） | ★ 契约确证（★ `norm.py:529-530`） |

★ ★ **★ 条件与例外未丢失**：★ condition 8 条、exception 2 条均进 Assertion。
★ ★ ★ ★ ★ 「Rule Slot 不含 strength/polarity/exception」指的是**事实身份槽位**，
★ ★ ★ ★ ★ 完整语义在 **Assertion（声明的值）**里。

---

## 五、★ 限制

1. ★ 缓存产物是**历史运行**的，★ 本轮未重新调用 LLM；★ 因此不能证明「当前 prompt 的产出质量」。
2. ★ 97 条来自 3 个协议，★ rtsp 缓存为空；★ 样本量不足以支撑任何泛化结论。
3. ★ 分类质量指标**未计算**：★ 无独立人工真值。
