# 三层语料库选择器设计（Three-Layer Seed Corpus Selector）

> 定位：解决「初始种子语料库」的**组合爆炸**与**漏洞依赖降级**两大矛盾。
> 本文档是 `multi_strategy_seedgen_design.md` 的深化——把「多导向」收敛为
> 一套**可独立降级的三层选择器**，作为种子生成的下一次重构目标。
>
> 落盘日期：2026-10-13（实验进行中，本文档不打断实验）。

---

## 一、动机：两个真实矛盾

### 矛盾 1 —— 状态路径的组合爆炸

若追求"覆盖所有合法状态排列组合"，会指数爆炸。RTSP 实测（4 状态 / 24 边）：

| 路径长度 | 从 Init 出发的路径数 |
|---|---|
| 3 条消息 | 336 |
| 4 条消息 | 2,576 |
| 5 条消息 | 19,728 |
| 6 条消息 | 150,944 |

再乘字段取值组合（Transport×Range×…），长度 5 即破百万；且状态机有自环，路径数严格无限。**穷举不可行。**

### 矛盾 2 —— 漏洞信息依赖导致的整体降级

`multi_strategy_seedgen_design.md` 的方案（2）把「危险序列」完全寄托于漏洞库
（`determine_strategies` 中 `security` 为空 → attack 路不激活）。若目标协议无漏洞
信息，种子生成退化为「纯正常会话」，**攻击性整体丧失**，违背"通用型协议知识中枢"
初衷。

---

## 二、核心思想

**把覆盖单位从「路径」降到「边」，再把「攻击性」从「漏洞依赖」中解耦。**

1. 状态机的**边**（转移）是有限的（RTSP 24 条），而路径是无限的。所以
   "不遗漏"的合理目标是**覆盖所有边**，而非穷举所有路径。
2. 「危险序列」拆成**通用危险**（由状态机拓扑 + 字段类型推导，协议无关）
   与**漏洞特定**（由漏洞库提供）两层。前者永远生效，后者有则叠加。
3. 由此得到三层，每层可独立降级，最终合并为一套**最优语料库选择器**。

---

## 三、三层架构总览

| 层 | 名称 | 覆盖目标 | 依赖 | 无漏洞时 | 生成方式 |
|---|---|---|---|---|---|
| ① | 结构覆盖层 | 状态机 24 条边 | 状态机 transitions | ✅ 生效 | 确定性图论（贪心边覆盖） |
| ② | 通用危险层 | 自环/生命周期/边界取值 | 状态机拓扑 + 字段类型 | ✅ 生效 | 规则推导（不依赖 LLM/漏洞） |
| ③ | 漏洞特定层 | 漏洞字段/序列/后果 | kb/历史漏洞 | ❌ 跳过 | 已有 `strategy.py` |

降级矩阵：

| 知识可用性 | 生效层 | 种子攻击性 |
|---|---|---|
| 只有 RFC（状态机） | ① + ② | 有（通用危险兜底） |
| RFC + 漏洞 | ① + ② + ③ | 最强 |
| 连 RFC 都没有 | 无 | 退化为 LLM 先验兜底 |

---

## 四、各层推导规则

### ① 结构覆盖层（最小边覆盖，确定性）

**输入**：`bundle["transitions"]`（`(from_state, method, to_state)` 三元组）。

**算法**（贪心 set cover）：

```
未覆盖边 = 全部 24 条边
种子列表 = []
while 未覆盖边 非空:
    从 Init 出发，贪心找一条「经过最多未覆盖边」的简单路径 P
    种子列表 += P
    未覆盖边 -= P 经过的边
```

**产出**：约 6 条「结构基线种子」。每条路径的边 → 消息序列（方法=边的 method，
字段从 `required_headers` + `headers` 取值池填充）。

**实测**（RTSP 24 边，贪心结果）：
- 种子 1：DESCRIBE→SETUP→PLAY→SETUP→PAUSE→OPTIONS→RECORD→SETUP→PAUSE→TEARDOWN（10 边）
- 种子 2~6：补剩余 14 边

**性质**：与漏洞、与 LLM 均无关，任何有状态机的协议都能产出。保证「结构不遗漏」。

---

### ② 通用危险层（结构启发式，规则推导）

**不依赖漏洞库**，从状态机拓扑 + 字段类型自动推导「通用危险模式」。

#### 2.1 自环重复（通用 UAF / 资源 / 断言模式）

- 从 transitions 找**自环** `X --M--> X`（from == to）。
- 对每个自环，生成「该边连续 2 次」的序列种子。
- RTSP 自环实例：
  - `Ready --SETUP--> Ready` → `SETUP + SETUP`（同 track 双 SETUP）
  - `Playing --PLAY--> Playing` → `PLAY + PLAY`（重复 PLAY）
  - `Playing --SETUP--> Playing`、`Recording --RECORD--> Recording` 等
- 原理：对同一对象重复同一操作，是 UAF / 资源管理 / 可达断言类漏洞的通用触发
  形态，无需知道具体 CVE。

#### 2.2 生命周期序列（通用 UAF 模式）

- 找「进入→离开→再进入」的环：`A --建--> B`，`B --拆--> A`，再 `A --建--> B`。
- RTSP 实例：`SETUP → TEARDOWN → SETUP`（建立会话→终止→重建）。
- 识别规则：状态机中「离开某状态的边」+「回到某状态的边」配对（如
  `Ready --TEARDOWN--> Init` 与 `Init --SETUP--> Ready` 配对 → 生命周期）。
- 原理：对象销毁后再重建/再引用，是 UAF 的通用形态。

#### 2.3 边界取值（通用溢出 / 空指针模式）

按字段类型（由 `headers` 桶的 syntax 推断）选边界值：

| 字段类型判据 | 边界取值 | 对应漏洞类 |
|---|---|---|
| syntax 含 `DIGIT`（CSeq/Content-Length/Bandwidth/Blocksize/Scale/Speed） | `0 / -1 / 2147483647 / 空` | 整数溢出/下溢 |
| 有 `values` 枚举池（Accept/Transport/Session/Content-Type） | 遍历每个枚举值 | 输入验证缺失 |
| syntax = `value`（Authorization/Location/From 等自由串） | `空串 / 超长串(≤256)` | 空指针/缓冲区溢出 |
| 可重复参数（Transport 的 client_port 等） | 填多个参数对 | 栈缓冲溢出 |

**性质**：协议无关——任何协议只要有「数值字段/枚举字段/字符串字段」，都能
套用同一套边界推导。

---

### ③ 漏洞特定层（漏洞导向，已有）

即 `core/fused/downstream/strategy.py` 的现有实现：
- `load_vuln_kb` → 结构化 trigger
- `classify_vuln` → CWE + 条件关键词 → 15 种合法边界动作 + 触发流提取
- `generate_attack_seeds` → 漏洞导向合法边界种子

本层是「精确到字段/序列/后果」的增量增强，有漏洞才叠加。

---

## 五、实现设计

```
core/fused/downstream/
├── edge_cover.py        # ① 新增：状态机最小边覆盖（贪心 set cover）
├── generic_danger.py    # ② 新增：自环/生命周期/边界取值的规则推导
├── vuln_specific.py     # ③ 重构：从 strategy.py 剥离的漏洞特定层
└── selector.py          # 新增：三层合并 + 降级编排（determine_strategies 升级）
```

### selector.py 编排逻辑

```
def select_seeds(bundle, resources, request_templates, vulns):
    seeds = []
    # ① 结构覆盖（永远）
    seeds += edge_cover(bundle["transitions"], bundle["required_headers"], bundle["headers"])
    # ② 通用危险（永远）
    seeds += generic_danger(bundle["transitions"], bundle["headers"])
    # ③ 漏洞特定（有漏洞才叠加）
    if vulns:
        seeds += vuln_specific(bundle, vulns, resources, request_templates)
    # 去重 + 写盘
    return write_seeds(dedupe(seeds))
```

### 与现有代码的关系

- ③ 直接复用 `strategy.py`（`classify_vuln`/`generate_attack_seeds`），仅抽出到
  `vuln_specific.py` 或保留原名；
- ①② 是新增的**确定性/规则**模块，不调 LLM，天然可测；
- `determine_strategies` 从「normal/attack 二分」升级为「三层永远①+②、按需③」。

---

## 六、验收标准

1. **边覆盖完备**：① 产出的种子覆盖状态机全部边（RTSP 24/24），种子数 ≤ 10。
2. **降级不失效**：`vulns=[]` 时，② 仍产出 ≥1 条自环重复 + ≥1 条生命周期 + 若干
   边界取值种子（攻击性不丢失）。
3. **确定性**：①② 不调 LLM，同输入必同输出（可单测断言精确序列）。
4. **叠加不冲突**：③ 有漏洞时与①②合并，去重后种子总数可控（目标 ≤ 60）。
5. **测试**：`tests/fused/test_edge_cover.py`、`test_generic_danger.py` 覆盖推导
   规则；全量 pytest 不回归。

---

## 七、待办（实现顺序）

1. 落 `edge_cover.py`（① 贪心边覆盖）+ 测试
2. 落 `generic_danger.py`（② 自环/生命周期/边界）+ 测试
3. 抽 `vuln_specific.py`（③ 复用 strategy.py）+ 测试
4. 落 `selector.py`（三层编排 + 降级）+ 端到端
5. 用 RTSP 跑通，验证「无漏洞也产出攻击种子」+「有漏洞最强」
6. 与 12h 实验数据对照，评估三层选择器相对当前「正常+攻击」的改进
