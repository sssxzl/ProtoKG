# S4 语料发布准入闸（CI Gate）规格书

> 版本 v1（2026-10-31）· 架构师：高见远（Gao）
> **用途**：本文是**可直接交给实现者（QA-3 / 工程团队）的规格**。红线判据、阈值、退出码语义、三协议端点定义均已定死，实现者不需再做设计决策。
> **状态**：待 team-lead 审阈值 → 待实现。**本文不修改任何代码，脚本由实现者编写。**
> 背景与证据链见 `docs/RQ4_AFLNet实验设计.md` §12.4（污染缺陷）、§12.6.1（修复验证）、§12.5.4（准入闸构想）。

---

## 0. 为什么必须有这个闸（问题陈述）

ProtoRAG 语料在 2026-10-31 出现过一次**静默退化**：当前事实重生成的 RTSP 语料中

- **59.5%** 的种子（22/37）指向**非目标设备** `rtsp://10.11.26.98:554/isapi/...`（某 IP 摄像机）
- **46.5%** 的会话引用指向 live555 **不存在的会话**
- 目标主机正确率仅 **40.5%**

而**当时所有既有健康度指标一条都没红**（`dup_fact_ids=0` / `toc_sourced_outcomes=0` / 章节号 0 未命中全部照常通过）。
根因：`traffic` 源混入了两台设备的抓包，`scripts/seedgen.py` 的 URL 兜底条件不覆盖真实抓包 URL → 原样透传。

**已修复**（`core/fused/downstream/target_env.py:normalize_target_endpoint` + `scripts/seedgen.py:298,307`），修复后重生成：0 污染、目标主机正确率 100%、条数不变（54→54）。

**但修复本身不防止复发** —— 只要 `traffic` 源再混入非目标设备，同样的静默退化会重演。
⇒ 本闸的作用：**把「语料能否用于实验」变成机器可判定的、CI 阻断的判定**，而不是靠人眼抽查。

---

## 1. 三条红线（G1 / G2 / G5）

| 闸 | 名称 | 判据 | 阈值 | 阻断? |
|---|---|---|---|---|
| **G1** | 目标端点正确率 | 语料中出现的**每个网络端点**都必须属于该协议的**合法端点集合** | **违规端点数 = 0** | 是 |
| **G2** | 不可播会话占比 | 语料引用的**会话/资源名**必须 ⊆ `profile.environments.<env>.playable_resources` | **违规引用数 = 0** | 是 |
| **G5** | 语料契约一致性 | `seedgen` 产出条数 == `profile.seedgen.<group>.seeds`（协议级）或 `profile.seedgen.environments.<env>.focus_group.<group>.seeds`（环境级） | **完全相等** | 是 |

**G5 补充**：退出码必须与现有 `seedgen.py` 行为一致 —— 条数不符时 `seedgen.py` 以 **exit 3** 失败（实测）。本闸在 G5 失败时亦返回 **非 0**。

**为什么是 G1 / G2 / G5 三条（而不是一条）**：
- **G1 判「打给谁」**（端点维度）
- **G2 判「打什么会话」**（资源维度）
- **G5 判「产出是否符合声明的规模」**（契约维度）

三者**不可互相替代**：G2 能抓到 `isapi`（它不在可播列表里），但**抓不到「会话名合法、主机错」** —— 只有 G1 能覆盖该类。

---

## 2. ★ 关键：G1 必须按协议分别定义合法端点集合

**不能**用统一的「URL host == `profile.default_url` 的 host」实现。三协议实测：

| 协议 | `profile.default_url` | 已发表语料中实际出现的端点 | URL 形式 |
|---|---|---|---|
| RTSP | `rtsp://127.0.0.1:8554/` | `127.0.0.1:8554` | 请求行内 `rtsp://host:port/path` |
| SIP | `sip:127.0.0.1:5060` | `127.0.0.1:5060`（服务端目标）<br/>`127.0.0.1:5061`（客户端源端口） | **无 `://`**：`sip:host:port` 出现在 R-URI；`host:port` 出现在 Via/Contact |
| SMTP | **`''`（空）** | **无任何端点** | 语料是纯 SMTP 命令序列，**根本不含 host:port** |

⇒ **SMTP 若按「host == default_url.host」实现，会 100% 误报**（default_url 为空）。
⇒ **SMTP 的 G1 必须定义为「不适用（skip）」**，而不是「0 违规」。

### 2.1 各协议 G1 合法端点集合（定死，实现者直接用）

| 协议 | 合法端点集合 | 端点抽取规则 | 违规示例 |
|---|---|---|---|
| **RTSP** | `{127.0.0.1:8554}` | 正则 `[a-zA-Z][a-zA-Z0-9+.-]*://(\[[0-9a-fA-F:]+\]\|[^:/]+):(\d+)` 取 `host:port`；**同时**匹配请求行首部的 `rtsp://host:port/...` | `10.11.26.98:554`（摄像机） |
| **SIP** | `{127.0.0.1:5060, 127.0.0.1:5061}` | **仅限 3 个路由相关位置**（见 §2.1.1）：<br/>① R-URI 主机（剥掉 `user@`）<br/>② `Via:` 的 **sent-by**（**剥掉 `;` 之后的所有参数**）<br/>③ `Contact:` URI 主机<br/>**明确排除** `From:`/`To:` | `213.192.59.75:5060` |
| **SMTP** | **{}（空集）→ G1 skip** | SMTP 语料无端点；**若**未来出现端点，则合法集合 = `{127.0.0.1:25}` | — |

**SIP 两个端口的角色（实现时勿混淆）**：依据官方 `run.sh` 的 `-N udp://127.0.0.1/5060`（服务端目标）与 `-l 5061`（fuzzer 本地源端口）：
- **5060** = Kamailio 服务端监听端口 → 出现在 **R-URI**（`REGISTER sip:127.0.0.1:5060 SIP/2.0`、`INVITE sip:127.0.0.1:5060 SIP/2.0`）
- **5061** = fuzzer 绑定的客户端源端口 → 出现在 **Via/Contact** 的 `sent-by`

**允许的「实例特定」值（不判违规）**：SIP 的 `From:`/`To:` 中的 user 部分可以是任意值（官方语料本身就用 `sip:35104723@sip.cybercity.dk`）—— **只检查 host:port，不检查 user 部分**。

#### 2.1.1 ★ SIP 的字段级抽取规则（**最容易误报的一处**，实测数据）

**已发表 `rq4_B` SIP 语料（25 条）实测分布**：

| 位置 | 抽取到的值 | 是否路由相关 | G1 判定 |
|---|---|---|---|
| R-URI 主机 | `sip:127.0.0.1:5060` ×78、`sip:127.0.0.1` ×6（无端口→补 5060）、`sip:bob` ×28（**无 host，只有 user**） | 是 | 前两者合法；`sip:bob` **无 host → 跳过，不判违规** |
| `Via` **sent-by** | `127.0.0.1:5061` ×102 | 是 | 合法 |
| `Contact` URI | `sip:127.0.0.1:5061` ×66 | 是 | 合法 |
| `Via` 的 **`branch=` 参数内** | `192.168.1.2` ×102（形如 `branch=z9hG4bKnp104984053-44ce4a41192.168.1.2`） | **否**（随机不透明串） | **必须排除，否则误报 102 次** |
| `From:`/`To:` | `sip:35104723@sip.cybercity.dk`、`sip:0097239287044@sip.cybercity.dk` | **否**（实例特定对端身份） | **必须排除**（官方语料本身就有） |

**★ 三条必须遵守的抽取规则**：
1. **`Via` 只取第一个 `;` 之前的部分**（sent-by），**`;` 之后全部丢弃** —— `branch`/`tag`/`rport` 里的 IP 是随机串，不是端点。
2. **R-URI 剥掉 `user@` 再取主机**；**无 host 的（如 `sip:bob`）直接跳过**，不得判违规。
3. **`From:`/`To:` 完全不参与 G1**。

**为什么 SIP 仍要做 G1（不能判「不适用」）**：
我实测 `derived/per_source/sip/traffic/facts/` **确实含外来主机**：
```
213.192.59.75   212.242.33.35   192.168.10.2   192.168.1.2   80.230.219.70   2.0.51.16
```
其中 **`sip:213.192.59.75` 出现在 R-URI 位置（4 次）** → **正是 G1 该抓的目标主机污染**。
⇒ 若把 SIP 判「不适用」，这类污染**永远抓不到**。

**SMTP 判「不适用」的理由与 SIP 不同**：SMTP 是**明文协议**，语料是纯命令序列，**完全不含任何 host:port**（实测 78 条 grep 为空）→ 没有可比对的端点概念，判 skip 是**事实性**的，不是保守取舍。

### 2.2 G2 各协议合法会话集合

| 协议 | 合法会话集合来源 | 若 `playable_resources` 缺失 |
|---|---|---|
| RTSP | `profile.seedgen.environments.rq2-live555.playable_resources_file` → 读该 JSON 的会话名列表（当前 = 7 个：`mp3AudioTest` `mpeg1or2AudioVideoTest` `matroskaFileTest` `webmFileTest` `wavAudioTest` `aacAudioTest` `ac3AudioTest`） | **G2 skip**（不得静默通过；须在输出里标注 `skipped: no playable_resources`） |
| SIP | SIP 语料**不引用 live555 式会话名**（实测：R-URI/Contact/From/To 全是 URI，无会话名概念）→ **G2 skip** | — |
| SMTP | SMTP 语料**不引用会话名** → **G2 skip** | — |

> **G2 只对 RTSP 有实质判据**。这是事实，不是偷懒：SIP/SMTP 的协议本身无「会话/资源」概念。
> **但 G2 对 RTSP 有一个额外价值**：它同时能抓到 `isapi` 这类「既是会话名又是路径片段」的污染。

**会话名抽取规则（RTSP）**：从请求行取**主机后的第一个路径段** ——
`^(DESCRIBE|SETUP|PLAY|PAUSE|TEARDOWN|GET_PARAMETER|SET_PARAMETER|OPTIONS)\s+rtsp://[^/]+/([^/\s?]+)`
→ 捕获组 1 即会话名。

⚠️ **必须取第一个路径段，不能取末段**：`SETUP rtsp://host/<session>/track1` 的末段是 `track1`（不是会话名）。
**我已实测验证过这个坑**：用「取末段」的写法（`grep -oE '/[^ /]+$'`）会把 `mpeg1or2AudioVideoTest` 截成 `mpeg1o`、`matroskaFileTest` 截成 `mat` —— 产生**假违规**且掩盖真违规。

**已实测验证的抽取结果**（三份语料，同一规则）：

| 语料 | 抽出的会话名（次数） | G2 判定 |
|---|---|---|
| `rq4_B`（已发表、干净） | `mp3AudioTest`41 `mpeg1or2AudioVideoTest`23 `webmFileTest`22 `wavAudioTest`18 `aacAudioTest`16 `matroskaFileTest`16 `ac3AudioTest`11 | **全 7 个可播 → 违规 0** ✅ |
| `20261031_171135`（污染） | **`isapi`93** `mp3AudioTest`26 `vobTest`9 `mpeg1or2AudioVideoTest`9 `matroskaFileTest`3 `h264ESVideoTest`3 `oggFileTest`2 … | **违规 > 0** ✅ |
| `live555_20261024_110155`（旧） | 18 个不同会话名，含 `amrAudioTest` `dvVideoTest` `h264ESVideoTest` `h265ESVideoTest` `mpeg1or2ESVideoTest` `mpeg2TransportStream*` `mpeg4ESVideoTest` `oggFileTest` `opusFileTest` `vobTest` 等 **11 个不可播** | **违规 > 0** ✅ |

（G1 端点抽取同样实测：污染语料 `10.11.26.98:554` **93 次**违规，`127.0.0.1:8554` 64 次合法 ⇒ **A2 会 exit 1**。）

---

## 3. 输入 / 输出契约

### 3.1 输入

```
用法:
  python scripts/check_corpus_release_gate.py --protocol {rtsp|sip|smtp} --seed-dir <dir>
                              [--env rq2-live555] [--profile fused_hub/targets/<p>/profile.json]
                              [--group B] [--baseline <json>] [--json-out <file>]

默认:
  --env     取 profile.seedgen.environments 中唯一的键（若恰有一个）；否则报错要求显式指定
  --profile <repo>/fused_hub/targets/<protocol>/profile.json
  --group   B
```

### 3.2 输出（JSON，schema 固定）

```json
{
  "schema_version": "1.0",
  "protocol": "rtsp",
  "env": "rq2-live555",
  "group": "B",
  "seed_dir": "E:/.../derived/seeds/rtsp/rq4_B",
  "seed_files": 39,
  "gates": {
    "G1": {
      "name": "target_endpoint_correctness",
      "applicable": true,
      "skipped_reason": null,
      "allowed_endpoints": ["127.0.0.1:8554"],
      "endpoints_found": {"127.0.0.1:8554": 150},
      "violations": [{"endpoint": "10.11.26.98:554", "occurrences": 93, "files": ["01_....raw"]}],
      "violation_count": 93,
      "threshold": 0,
      "pass": true
    },
    "G2": {
      "name": "playable_resource_ratio",
      "applicable": true,
      "skipped_reason": null,
      "allowed_resources": ["mp3AudioTest", "..."],
      "resources_found": {"mp3AudioTest": 20, "...": 10},
      "violations": [{"resource": "isapi", "occurrences": 37, "files": ["..."]}],
      "violation_count": 0,
      "threshold": 0,
      "pass": true
    },
    "G5": {
      "name": "corpus_contract_consistency",
      "applicable": true,
      "skipped_reason": null,
      "contract_source": "profile.seedgen.environments.rq2-live555.focus_group.B.seeds",
      "expected": 39,
      "actual": 39,
      "pass": true
    }
  },
  "overall_pass": true
}
```

**字段约定**：
- `applicable=false` 时 `skipped_reason` **必填**（如 `"smtp: corpus contains no network endpoints; G1 not applicable"` / `"sip: protocol has no session/resource concept"`）
- `violations[].files` 列出涉及的种子文件名（**最多列 20 个**，避免 JSON 爆炸；总数记在 `occurrences`）
- `endpoints_found` / `resources_found` 为 `{名称: 出现次数}`，供报告使用

### 3.3 退出码语义

| 退出码 | 含义 | CI 行为 |
|---|---|---|
| **0** | 三条适用红线全部通过（或不适用且已标注 skipped_reason） | 通过 |
| **1** | 至少一条红线**违规**（G1/G2 有 violation，或 G5 条数不等） | **阻断** |
| **2** | **用法/环境错误**（目录不存在、profile 读不到、env 不唯一且未指定、无法解析 playable_resources 等） | **阻断**（配置错不该静默通过） |

> **退出码 2 必须与 1 区分**：配置错误若返回 0 会让 CI 假绿；若返回 1 会掩盖真实违规。二者必须可区分。

---

## 4. 实现要点（给实现者）

1. **复用现有产物，不要重写解析器**：
   - `qa/probe_corpus_contract.py`（QA-3）→ 已有「产出条数 vs 契约」逻辑，G5 直接复用
   - `qa/check_playable_resources.py`（QA-3）→ 已有会话分布统计，G2 复用其会话抽取与 `playable_resources` 读取
   - G1 是**新增**的（端点抽取），但 RTSP 的会话抽取逻辑已存在于 `check_playable_resources.py`，可借鉴其正则
2. **端点抽取要覆盖「无 `://` 形式」**：SMTP 全无 URL；SIP 的 R-URI 是 `sip:host:port`（无 `://`）；Via/Contact 是裸 `host:port`。**只写 `://` 正则会漏掉 SIP**。
3. **端口缺省要处理**：SIP 的 `sip:127.0.0.1`（无端口）→ 按 5060 补；Via 的 `127.0.0.1`（无端口）→ 按 5061 补。
4. **文件读取用二进制 + 容忍 CRLF/LF**：语料是 CRLF，但解析时按行 strip。
5. **不要修改 `seedgen.py` 或 `target_env.py`**：本闸是**只读检查器**，不改生成逻辑。
6. **不要把 `applicable=false` 当作通过而静默**：必须在 JSON 里写 `skipped_reason`，并建议在 CI 日志里显式打印一行 `G1 skipped: <reason>`。
7. **`--baseline` 可选**：若提供历史基线 JSON，则额外输出各闸的 delta（便于发现「本来通过、现在退化」）。

---

## 5. 验收标准（实现者自查 + QA 复验）

| # | 用例 | 期望 |
|---|---|---|
| A1 | 对 `derived/seeds/rtsp/rq4_B`（已发表、干净） | **exit 0**；G1 违规 0；G2 违规 0；G5 expected=39 actual=39 |
| A2 | 对 `derived/seeds/rtsp/20261031_171135`（**已知污染**） | **exit 1**；G1 违规 ≈93 次 `10.11.26.98:554`；G2 违规含 `isapi` |
| A3 | 对 `derived/seeds/rtsp/live555_20261024_110155`（旧的 47.9% 不可播语料） | **exit 1**；G2 违规 > 0（不可播会话） |
| A4 | 对 `derived/seeds/sip/rq4_B`（无 URL 的语料） | **exit 0**；G1 `applicable=false` + `skipped_reason` 非空；G2 skip；**不得**因无 URL 而误报 |
| A5 | 对 `derived/seeds/smtp/rq4_B`（无 URL、`default_url` 为空） | **exit 0**；G1 skip 且 **skipped_reason 必须提到 `default_url` 为空**（防将来有人把 SMTP 当适用） |
| A5b | 对 `derived/seeds/sip/rq4_B`（**无 `://` 形式**的端点） | **exit 0**；G1 必须正确识别 `sip:127.0.0.1:5060`（R-URI）与 `127.0.0.1:5061`（Via/Contact）为**合法**，不得误报 |
| A5c | 对 `derived/seeds/sip/rq4_B` | G2 **skip**（SIP 无会话概念），且 `skipped_reason` 非空 |
| A6 | 对当前事实**重新生成**的 RTSP/B（54 条，已修复） | **exit 1**（G5 契约 39≠54）→ **证明 G5 能抓到契约漂移** |
| A7 | 对不存在的目录 | **exit 2** |
| A8 | 同一输入连跑两次 | 输出一致（确定性） |

**A2/A3 是本闸的核心价值证明**：**必须用真实污染语料验证**，不能只测干净语料。

**A2/A3/A5/A5b 我已用真实语料预先跑通**（用与规格相同的抽取规则实测，见 §2.2 表格），因此上述期望值不是推测，而是已验证的基线：
- A2：`20261031_171135` → G1 违规 **93**（`10.11.26.98:554`）、G2 违规含 `isapi` **93** → **exit 1**
- A3：`live555_20261024_110155` → G2 违规 **11 个不可播会话**
- A1：`rq4_B` → G1 违规 0、G2 违规 0 → **exit 0**
- A5：SMTP 语料中 **0 个端点**（实测 grep 为空）→ G1 skip 成立

---

## 6. CI 接入建议

```
# 建议挂载点：语料生成之后、实验之前（语料是实验的输入，不是产物）
gate:
  python scripts/check_corpus_release_gate.py --protocol rtsp --seed-dir derived/seeds/rtsp/rq4_B
  python scripts/check_corpus_release_gate.py --protocol sip  --seed-dir derived/seeds/sip/rq4_B
  python scripts/check_corpus_release_gate.py --protocol smtp --seed-dir derived/seeds/smtp/rq4_B
  # 任一非 0 → 阻断
```

**产出汇入 `qa/baseline_unified.json`**（QA-3 已有该管道），使「语料可发布性」与「pytest 基线」「事实库健康度」在同一处可查。

**建议同时接入 `scripts/seedgen.py` 的调用点**：生成后立即跑本闸，避免「污染语料先落盘、事后才发现」。

---

## 7. 与后续工作的关系

| 后续项 | 对本闸的依赖 |
|---|---|
| **S5 数量对齐组**（protorag 裁剪到官方条数 × K=3 子集） | **强依赖**：对齐子集必须先过 G1/G2，否则是拿「坏种子」做数量对齐，结论直接失效（§13.5 第 6 条） |
| **S1′**（修污染 → 冻结事实 → 重生成 → 重跑 6 容器） | 本闸是**重跑前的放行检查**；重跑后的新语料也必须过闸 |
| **S2′**（回退非 rfc 源事实） | 同上；且本闸能验证「回退后语料是否变干净」 |

⇒ **本闸必须先于 S5**（与 team-lead 的排序一致）。
