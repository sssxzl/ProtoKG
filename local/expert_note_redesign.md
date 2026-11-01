# kb/expert_note 重新设计 —— expert_note schema v3（专家判断导向）

> 日期：2026-10-20。本文件是 expert_note 的**设计真源（v3）**，取代 2026-10-09 的 v2 设计。
> 触发：用户澄清 expert_note 的原始意图——「人对协议的认识和总结，有自己的视角，主观性偏大」，
> 而非「客观知识的重复搬运」。

---

## 1. 定位纠偏（v2 → v3 的核心变化）

**v2 定位（已废弃）**：expert_note = 专家提炼的、结构化的、带溯源的高质量协议知识，是「规范的结构化提炼 + 实战经验补充」。

**v3 定位（本版）**：

> **expert_note = 专家对协议的「判断和引导」，回答的不是「协议是什么」，而是「哪里危险、怎么进入深层、该往哪使劲」。**
> 它允许主观、允许有立场、允许不全——它的价值恰恰在于**其他四源（客观源）给不了的判断**。

一句话：expert_note 是「**老师的辅导笔记**」，不是「第二本教科书」。

## 2. 五源分工（用类比钉死边界）

| 源 | 类比 | 回答的问题 | 性质 | 允许主观？ |
|---|---|---|---|---|
| rfc | 教科书 | 协议「应该怎样」 | 客观、全面、抽象 | 否 |
| source | 某学生作业 | 这个实现「实际怎么写」 | 客观、具体、可能有错 | 否 |
| traffic | 考场录像 | 实际观测到「什么行为」 | 客观、真实、有偏 | 否 |
| vuln | 错题本 | 哪里「已经出过事」 | 客观、片面、事后 | 否 |
| **expert_note** | **辅导笔记** | **「哪里易错、该往哪使劲」** | **主观、有立场、事前** | **是** |

**关键边界**：客观事实（方法列表、状态机、状态码、字段语法、取值池）**一律归 rfc/source/traffic 源**，
expert_note **不再重复**这些。expert_note 只放「客观源给不了的判断」。

## 3. expert_note 该装什么（4 类「只有专家视角」的内容）

### ① hotspots —— 风险预判 / 热点（无 CVE 也要写）
专家凭对协议解析复杂度的理解，预判「哪个字段/方法最容易出 bug」，**即使还没有历史 CVE**。
这是 vuln 源给不了的（vuln 只讲「已经出过事」，hotspot 讲「容易出事」）。

### ② depth_keys —— 进入深层状态的钥匙（覆盖率的关键）
专家知道「要走到深层状态，必须满足什么前置路径」。fuzz 能不能打深，取决于此。
这是 rfc 有但分散、source 难抽、traffic 不全的那部分「会话语义」。

### ③ design_weaknesses —— 协议设计级弱点（区别于实现 bug）
专家看出「协议设计本身就有隐患」的地方，区别于 vuln 管的「某行代码写错」。
例：DNS 缓存投毒的根子是「16 位 ID + 端口熵不足」的设计问题，不是实现 bug。

### ④ implicit_constraints —— 隐含约束 / 变异建议
RFC 没明说、源码难抽、但专家知道的「隐藏规则」和「该用哪类变异去撞」。

**共同点**：这 4 类回答的都是「**哪里危险、怎么进去、往哪使劲**」——全是判断和引导，不是事实陈述。

## 4. 新 schema（4 维度 + meta）

外层统一：`{ "schema_version": 3, "protocol": "<p>", "<维度键>": [...] }`

### `hotspots.json` —— 风险预判
```json
{
  "hotspots": [
    {
      "id": "dns_qname_compress",
      "target_type": "field",          // field | method | state
      "subject": "QNAME",
      "why": "label 压缩指针解析最易越界（解析器核心路径）",
      "priority": "high",              // high | medium | low
      "mutation_hint": "构造压缩指针自引用 / 越界偏移 / 截断的 label"
    }
  ]
}
```

### `depth_keys.json` —— 进入深层状态的钥匙
```json
{
  "depth_keys": [
    {
      "id": "dns_cache",
      "target_state": "缓存命中",
      "path": ["QUERY(触发转发)", "伪造权威响应"],
      "why": "要触发缓存逻辑，必须先让服务器转发查询再收到可接受的伪造响应"
    }
  ]
}
```

### `design_weaknesses.json` —— 设计级弱点
```json
{
  "design_weaknesses": [
    {
      "id": "dns_cache_poisoning",
      "name": "缓存投毒",
      "root_cause": "16 位 ID + 源端口熵不足，可被 birthday 攻击",
      "exploitable": true,
      "exploit_hint": "伪造响应需猜中 ID + 源端口"
    }
  ]
}
```

### `implicit_constraints.json` —— 隐含约束 / 变异建议
```json
{
  "implicit_constraints": [
    {
      "id": "dns_qname_label_len",
      "field": "QNAME label 长度",
      "constraint": "单 label ≤ 63 字节，域名总长 ≤ 255 字节",
      "violation_mutation": "label 长度字段 ≠ 实际内容长度（经典越界点）"
    }
  ]
}
```

## 5. 下游映射（怎么传导到种子生成）

| 维度 | v2 中枢映射 | 种子生成作用 |
|---|---|---|
| hotspots | method/header → `security_property`（epistemic=descriptive, authority=expert_note）| 漏洞导向的**预判**（比 vuln 更前瞻）|
| depth_keys | method → `precondition` / 黄金路径 | 引导种子**先走深层前置路径** |
| design_weaknesses | protocol → `security_property`（设计级）| 设计级变异的 rationale |
| implicit_constraints | header → `legal_boundary` / mutation hint | 定向变异（长度不一致、自引用等）|

> 注：这 4 维需要新增/复用 aspect，落地时与 `core/fused/expert_note.py` 的映射同步改。

## 6. 与客观源的边界（防重复）

| 内容 | 归属 | 为什么 |
|---|---|---|
| 方法列表 / state_changing | rfc + source | 客观事实，可自动抽取 |
| 状态机 | source（AutoSeeder 推断）| 客观事实，可自动推断 |
| 状态码 / 字段语法 | rfc | 规范原文 |
| 取值池 | traffic | 实测观测 |
| 已发生漏洞的触发 | vuln | 历史 CVE |
| **风险预判 / 深层钥匙 / 设计弱点 / 隐含约束** | **expert_note** | **只有专家判断能给** |

## 7. 示范样例：DNS（专家视角）

```json
{
  "schema_version": 3,
  "protocol": "dns",
  "hotspots": [
    {"id": "dns_qname_compress", "target_type": "field", "subject": "QNAME",
     "why": "压缩指针解析是 DNS 最经典的越界点：指针偏移若指向自己或越界，label 解压会无限循环或越界读",
     "priority": "high",
     "mutation_hint": "压缩指针自引用 / 指向报文外 / 截断 label"},
    {"id": "dns_rdlength_mismatch", "target_type": "field", "subject": "RDLENGTH",
     "why": "RDLENGTH 声明长度与实际 RDATA 不一致是 RR 解析越界的高发点",
     "priority": "high",
     "mutation_hint": "RDLENGTH > 实际剩余字节 / RDLENGTH = 0 但 RDATA 非空"},
    {"id": "dns_dnssec_validation", "target_type": "method", "subject": "DNSSEC 校验",
     "why": "RRSIG/NSEC 校验路径长、状态多，实现极易在边界条件出错",
     "priority": "high",
     "mutation_hint": "伪造 RRSIG 覆盖范围 / 畸形 NSEC bitmap"}
  ],
  "depth_keys": [
    {"id": "dns_cache_hit", "target_state": "缓存命中",
     "path": ["QUERY(转发)", "伪造权威响应"],
     "why": "缓存逻辑只有在服务器转发查询并收到可接受响应后才走到，浅层直连查询打不到"},
    {"id": "dns_dnssec_path", "target_state": "DNSSEC 校验",
     "path": ["QUERY(DO=1)", "RRSIG 响应"],
     "why": "要触发 DNSSEC 校验必须先在查询里置 DO 位并收到带 RRSIG 的响应"}
  ],
  "design_weaknesses": [
    {"id": "dns_cache_poisoning", "name": "缓存投毒",
     "root_cause": "16 位 ID + 源端口熵不足，birthday 攻击可枚举",
     "exploitable": true,
     "exploit_hint": "伪造响应需猜中 ID + 源端口"}
  ],
  "implicit_constraints": [
    {"id": "dns_label_len", "field": "QNAME label 长度",
     "constraint": "单 label ≤ 63 字节，域名总长 ≤ 255 字节",
     "violation_mutation": "label 长度字段 ≠ 实际内容长度"},
    {"id": "dns_compress_ptr", "field": "压缩指针偏移",
     "constraint": "必须指向前方（小于当前位置），禁止自引用",
     "violation_mutation": "自引用指针 / 前向越界指针"},
    {"id": "dns_edns_udp_size", "field": "EDNS0 OPT size",
     "constraint": "传统 UDP 512 字节限制，超过需 EDNS0 协商",
     "violation_mutation": "超大报文 + 未协商 EDNS0"}
  ]
}
```

## 8. 落地建议

1. **设计定稿**：本文档（v3）确认后，再动 `kb/<protocol>/expert_note/` 与 `expert_note.py`。
2. **迁移成本**：现有 8 协议的 9 维 v2 expert_note 需重做为 4 维 v3（客观维度删掉，只留判断）。
3. **映射同步**：`core/fused/expert_note.py` 的 `_DIMENSION_MAPPERS` 从 7 维改为 4 维，新增
   `hotspots/depth_keys/design_weaknesses/implicit_constraints` 的映射（部分需新增 aspect）。
4. **主观性管理**：hotspot 的 `why`/`priority` 是主观判断，需 `provenance` 标注「专家主观判断」，
   与 rfc/source 的「客观事实」区分开（对齐 v2 中枢的 epistemic_type）。

---

*v3 设计 · 2026-10-20 · 待用户确认后进入实施（改 kb/expert_note + expert_note.py）*
