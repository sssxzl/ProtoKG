docs/工具/agent_rules.md

定位：本文件是 agent 长期有效的固定约束。任何 session 开始工作前必须先读本文件。

一、kb 权限
kb/ 默认 read-only。任何写 kb/ 的操作必须先停下，汇报，等用户明确授权。授权只对当次指定动作有效，用完立即恢复 read-only。不得因授权过一次就默认长期有效。

二、失败即停
任何动作失败，立即停止，不继续后续动作，不自行修复。写清失败点、失败现象、已尝试的手段、你的判断。

三、不得自行假设
契约未写明、语义不明、两种实现都合理时，停下问用户，不自行选择。不得默认选第一个、不得默认选推荐选项、不得默认选最小改动。

四、越界审计
每个 Step 结束，写 audit 文件到 local/backup/step_<N>/audit.txt。audit 内容固定四项：
改动文件清单，每个文件改了什么、为什么。
是否超出本 Step 指令范围。超出的话列出超出项、你当时的判断依据、实际结果。
是否遇到未授权自动转换。例如 Step 3.1.3 落盘时把 83 处「加」自动转成「→」。
是否存在未落盘的判断。例如某处改了但没写入 audit。

### 量具自证原则（Measure Self-Validation）

本会话已出现三次「看似语料发现、实为量具缺陷」：

1. capture.pcapng 包数报 486–490 → 实际 55/56/57/58
2. 反向回滚重建报字节移动 → 校验脚本漏检
3. status 一致报 0/500 → `200 != "200"` 类型问题

三条模式：

- **探针脚本自身的量具正确性**必须在引为语料证据前先自证
- **首次观测异常**不得直接当作语料事实写入结论
- **量具缺陷** 与 **语料发现** 必须显式区分：前者须先修正再重测，后者才可作为证据

要求：

- 探针脚本首次运行结果若与预期严重不符，先自检量具（类型归一 / 通配符 / 编码 / 路径）
- 若发现量具缺陷：修正后重跑，最终结论以修正后为准
- 量具缺陷必须显式记录（不得静默修补）

五、决策点必须停
遇到下列情况必须停下汇报，不得继续：
契约缺条款、语义不明、两方案都可。
需要改冻结文档（六份 fused_* 或对应 JSON）。
需要改 core/ 下已冻结代码。
需要写 kb/ 或 derived/。
pytest 失败或 errors 不为 0。
kb/ fingerprint 发生变化。
发现前序 Step 有未记录的越界或未决项。

六、上下文优先读
每个 session 开始，按顺序读：
docs/工具/project_handoff.md。
docs/工具/agent_rules.md（本文件）。
docs/实施/project_taskbook.md。
docs/工具/decisions_pending.md。
docs/工具/decisions_resolved.md。
最近一个 local/backup/step_<N>/audit.txt。
相关契约文档（fused_hub/docs/ 下的对应文档）。
不读完这些，不开始执行。

七、共享产物的恢复纪律（源自 RQ4 回退事故）
本项目在 VM 与本机两侧各有一份**生产脚本**（VM `/home/zxy/rq4/scripts/` ↔ 本机 `scripts/`）。
两边必须**逐字节一致**，且 **VM 侧是权威副本**。本条给出唯一正确的操作姿势。

### 7.1 改脚本前：备份取在「改之前」
备份必须在改动**之前**取。若备份命令排在编辑命令之后，恢复回去的还是坏版本 —— 这正是
2026-10-30 RQ4 回退事故的根因（当时 cp 写在同一条命令链里，晚于 Python 编辑）。

推荐直接用「备份取在改之前」的写法：

```bash
cp scripts/rq4_collect.sh /tmp/pristine.sh    # ① 先备份（改动前）
python3 mutate.py                             # ② 再改
pytest ...                                     # ③ 验证
cp /tmp/pristine.sh scripts/rq4_collect.sh     # ④ 恢复（注意顺序）
```

### 7.2 恢复时：优先「直接从 VM 拉权威版」
VM 那份是 `mv` 原子替换过的，从未被污染，**它才是权威**。恢复首选：

```bash
ssh -i ~/.ssh/vm_ubuntu_zxy zxy@192.168.37.130 \
    "cat /home/zxy/rq4/scripts/rq4_collect.sh" > scripts/rq4_collect.sh
```

比本地备份更省事，也更可靠（不依赖备份是否取对了时机）。**但见 7.3 —— 拉下来必须复核字节。**

### 7.3 恢复后：md5 与行尾要**双重**复核（只看 md5 不够）
md5 相同**不代表**行尾相同 —— Windows 侧 Python 写文件会把 `\n` 转成 `\r\n`，
md5 会变但人眼看不出；而 CRLF 的 `.sh` 在 bash 里会让 `\r` 变成命令的一部分，
在 VM 上直接语法错误（`unexpected end of file`）。

**行尾一律用 Python 字节层判定**，不要用 shell `grep -c $'\r'` —— Git Bash 下
`$'\r'` 不按 ANSI-C 展开，会被当字面量匹配而**误报**（实测把纯 LF 文件报成几百行 CRLF）。

```bash
python -c "
import pathlib,hashlib
b = pathlib.Path('scripts/rq4_collect.sh').read_bytes()
print('md5 =', hashlib.md5(b).hexdigest())
print('CRLF =', b.count(b'\r\n'), ' loneCR =', b.count(b'\r') - b.count(b'\r\n'))
"
```

判定标准：md5 == VM 侧 md5 **且** CRLF == 0 **且** loneCR == 0。

### 7.4 改完：必须让护栏证明它真的变了
改完不能只看「pytest 绿」——**要先确认护栏在坏版本上会红**（变异测试），
否则无法区分「护栏有效」与「护栏根本没碰到这段代码」。
护栏必须打在**真实执行路径**上：测被调用的函数 ≠ 测调用点（详见 `tests/fused/test_analyze_compare_index.py` 的做法）。

#### 7.4.1 ★ 变异测试**在副本上做**，不要改生产脚本（2026-10-30 真实事故）

**旧做法（危险，已废弃）**：直接改生产脚本 → 跑测试 → 再改回来。
问题是**恢复是手动步骤**，中间必然留窗口期。实测：我在 17:08:25 注入变异、
17:16:50 才恢复，**中间 8 分钟** team-lead 读到了中间态 → 报出「5 failed」的假失败，
还差点导致两人互相覆盖。

**正确做法：副本上变异，生产脚本零改动**
```bash
# ① 复制到临时目录（生产脚本全程不动）
mkdir -p .tmp_mut && cp scripts/rq4_collect.sh .tmp_mut/mutant.sh
# ② 在**副本**上注入变异
python3 - <<'PY'
import pathlib
p = pathlib.Path('.tmp_mut/mutant.sh')
s = p.read_text(encoding='utf-8')
s = s.replace('原写法', '变异写法')
p.write_text(s, encoding='utf-8')
PY
# ③ 让护栏指向副本跑（护栏已支持 RQ4_COLLECT_SH 环境变量）
RQ4_COLLECT_SH="$(pwd)/.tmp_mut/mutant.sh" python -m pytest tests/fused/... -q
# ④ 确认变红后删掉副本即可 —— 生产脚本从未被改过，无需恢复
rm -rf .tmp_mut
```
护栏侧已支持该环境变量（`tests/fused/test_rq4_artifact_manifest.py` 与
`tests/fused/test_rq4_collect_cov_fix.py`，通过 `RQ4_COLLECT_SH` 指向被测脚本）；
**默认行为不变**（不设变量时仍是生产脚本）。

★ 好处：生产脚本 md5 全程不变 → 他人不可能读到中间态 → **并发编辑干扰彻底消失**。

### 7.5 同步到 VM：原子替换
VM 侧可能有进程正在读该脚本（bash 按字节偏移增量读取脚本文件）。
直接覆盖会读到半个脚本。必须 `cp → 临时名 → mv`：

```bash
cp new.sh /home/zxy/rq4/scripts/.tmp.sh && mv /home/zxy/rq4/scripts/.tmp.sh /home/zxy/rq4/scripts/rq4_collect.sh
```

### 7.6 一致性由 pytest 守，不靠人肉比对 md5
`tests/fused/test_rq4_scripts_parity.py` 直接向 VM 求 md5 与本机比对，
并把**本机脚本内容经 ssh stdin 喂给 VM 的 `bash -n`**（本机 MSYS2 的 `bash -n`
对 CRLF 放行，只有 VM 能发现）。VM 不可达时 skip（不等于已验证）。

### 7.7 终态数据的核验：两个独立实现互证 + 篡改注入验证
RQ4 终态数据的「未被篡改」结论，不能靠单一脚本的一次输出。
2026-10-30 容器被删除后，两个 agent 各自写了独立实现并交叉比对：

| 实现 | 位置 | 语言 |
|---|---|---|
| 工程师 | `local/rq4_tar_audit.sh` | bash |
| QA | `derived/experiments/rq4/qa/scripts/qa_tar_vs_plain.py` | python |

**结论：12/12 md5 全部一致（0 条不一致），command_line 逐字比对 6/6 一致。**

三条纪律：
1. **核验脚本必须支持「失败即非 0 退出」**（`rc != 0` 表示不一致），否则无法进 CI。
2. **必须做篡改注入验证**：在**副本**上改 1 字节，确认脚本真的会报错。
   （实测：改 `sip/protorag` 的 fuzzer_stats 1 字节 → rc 从 0 变 1 ✓）
   篡改测试**只在副本上做**，绝不碰真实数据目录。
3. **两个独立实现结论一致才算数**；若不一致，**以 tar 为准**并立刻排查谁读到了被改动的文件。

### 7.8 产物自证清单（采集时就留下证据）
`rq4_collect.sh` 采集时把各产物 md5 写入**旁挂清单** `${SUMMARY%.csv}.artifacts.md5`
（18 行 = 6 组 × 3 产物），格式与 md5sum 同构 → 日后可直接：

```bash
# 清单是绝对路径 → 在任意目录执行都可以（下面两行等价）
md5sum -c /home/zxy/rq4/rq4_summary.artifacts.md5
cd /home/zxy/rq4/out && md5sum -c /home/zxy/rq4/rq4_summary.artifacts.md5
```

★ 清单里的路径用**绝对路径**（`abs_f=$(cd "$(dirname "$f")" && pwd)/$(basename "$f")`）：
- 相对 `out_root` → 清单在 summary 目录、产物在 `out/` 下 → **不同源** → 实测 0/18 OK；
- 相对「清单所在目录」→ 生成时可用，但清单被**移动/复制**到别处即失效（实测复制到 `/home/zxy/rq4` 后 0/18 OK）；
- **绝对路径** → 在**任意 cwd** 执行 `md5sum -c` 都是 18/18 OK（已实测 `/home/zxy/rq4` 与 `/tmp` 两种）。
代价：换机器 / 换 `out_root` 后需重新采集以重建清单（采集时自动重建）。

★ **清单路径基准的验收方式**（team-lead 2026-10-30 复核要求，两条都必须过）：
```bash
# ① 默认 out_root，summary 写到 /tmp（不覆盖终态交付物）
cd /home/zxy/rq4 && bash scripts/rq4_collect.sh --offline /home/zxy/rq4/out --summary /tmp/v1.csv
cd /tmp && md5sum -c v1.artifacts.md5          # 必须 18/18 OK，rc=0

# ② 非默认 out_root → 清单路径必须跟随
bash scripts/rq4_collect.sh --offline /tmp/outroot_test --out-root /tmp/outroot_test --summary /tmp/v2.csv
cd /tmp && md5sum -c v2.artifacts.md5          # 必须 18/18 OK，rc=0
```
★ 护栏：`tests/fused/test_rq4_artifact_manifest.py` 里
`test_production_script_generates_manifest_that_passes_md5sum_check`
**真跑生产脚本 + 真跑 md5sum -c**（不是合成 fixture）——
合成 fixture 清单与产物同目录会**掩盖**生产代码里的路径计算错误（这正是那次事故的成因）。

### 7.9 并发编辑会让测试给出**误导性结论**（2026-10-30 实测踩到）
两个 agent 同时改同一个生产脚本时，一方的测试可能读到另一方编辑到一半的文件，
表现为「**单独跑通过、全量跑失败**」或「**同一命令两次结果不同**」。

实测经过：QA 与工程师同时改 `scripts/rq4_collect.sh`（清单路径方案从相对 → 相对清单目录 → 绝对），
期间工程师的护栏 3 条间歇性失败；待文件稳定后连跑 3 次全绿（647 passed）。

**处置纪律**：
1. 遇到「间歇性失败 / 两次跑结果不同」，**先查文件是否正在被外部改动**：
   ```bash
   stat -c %y scripts/rq4_collect.sh && md5sum scripts/rq4_collect.sh
   ```
   连采几次，若 mtime/md5 在变 → **不是代码缺陷，是并发编辑**，应先与对方协调再判。
2. **不要**把这类失败当成「代码坏了」去乱改 —— 那会引入真缺陷。
3. 判据：文件稳定后**连跑 ≥ 2 次**全绿，才算通过。
4. 这与 7.4（变异测试）是同一条纪律的两面：**护栏红**可能是代码坏了，也可能是**被测对象变了**；
   先确认被测对象的状态，再下结论。
5. ★ **根治办法**：按 7.4.1，变异测试**在副本上做**（`RQ4_COLLECT_SH` 指向副本），
   生产脚本全程零改动 → 这类「读到中间态」的干扰从根上消失。
   2026-10-30 实测：副本法跑出 5 failed（护栏正确变红），而生产脚本 md5 全程未变。

★ **不改 summary 的 28 列表头**（那是冻结合同，下游按列号取字段）。
★ 注意 **初始化顺序**：清单路径必须**惰性求值**（`artifact_manifest_path()`），
  不能在变量初始化时从 `SUMMARY` 派生 —— `--summary` 参数是在其之后才解析的，
  初始化时求值会把清单写到错误位置（已真实踩过）。


七、汇报格式固定
每个 Step 结束汇报，固定包含：
本步目标一句话。
动作汇总：每步 PASS 或 FAIL。
关键数值。
未决项。
下一步建议。
不超过 60 行。过长时写详细报告到 local/backup/step_<N>/detail.txt，汇报只给摘要。

八、pytest 规范
一律用 pytest -n auto。基线以最近一次全量结果为准。出现 failed 或 errors 立即停止。

### 何时必须跑测试

以下变更**必须**包含至少相关测试（不能只跑文档步骤）：

1. 修改 `fused_hub/schema/` 下任何 JSON 后，
   必须跑 `tests/fused/.../test_registry_*.py` 相关测试
   （至少 `test_candidate_layer.py` + `test_registry_loader.py`）

2. 修改 `core/fused/` 下任何文件后，
   必须跑相关单元测试（与该文件直接相关的 `test_*`）

3. 修改 `fused_hub/docs/` 下任何冻结文档后，
   必须跑 `test_final_contract_consistency.py` 与
   `test_runtime_contract_consistency.py`

4. 修改 `property_registry.json` / `fact.schema.json` /
   `condition.schema.json` / 其他 schema JSON 后，
   除相关单元测试外，**建议额外跑一次全量 pytest**
   （因 schema 变更影响面可能超过单一模块）

### 不跑 pytest 的授权边界

「不跑 pytest」授权**只应针对**：

- 纯文档步骤（仅改 `local/` 下设计文档）
- 只读勘察
- baseline 备份

**不应针对**：

- 任何 `fused_hub/` 下 JSON 变更
- 任何 `core/` 下代码变更
- 任何 `tests/` 变更

理由：D9 §6-Pre15 追加 property 后未跑 pytest，
漂移 7 步未被发现，直到 §6-Pre22 全量 pytest 才抓到。
纯计数断言过期虽无行为回归，但暴露流程缺陷。


九、路径与命名
所有备份到 local/backup/step_<N>/。N 与 Step 编号一致。
每个 Step 目录下有 before/ 子目录放改动前快照。
fingerprint 文件命名 kb_fingerprint_before.txt 与 kb_fingerprint_after.txt。

十、长期审计准则
落盘用户提供的文本时，发现明显有误或有歧义，先写入汇报请用户裁定，不边写边改。
遇到文本排版残留（如被压平的箭头、被误转的字符），视为格式问题而非契约内容，但依然先停后改，不自动处理。
任何改动前先声明“这是格式修复”还是“这是契约变更”，让用户区分。

十一、源隔离
调试某一知识源（rfc、expert_note、traffic、vuln、source 五源之一）时，只允许改该源相关的文件。禁止改动其他源的任何文件。

允许改：

该源的 extractor 代码（core/extractors/ 下对应该源的文件）

该源在 norms.jsonl 中的条目

derived/model/per_source/<该源>/ 下的产物

禁止改：

其他源的 extractor 代码

其他源在 norms.jsonl 中的条目

derived/model/per_source/<其他源>/ 下的产物

derived/model/spec/rtsp/ 下与本次操作无关的文件

若发现其他源的文件被意外修改（例如测试误写、fixture teardown 失败），不自动修。停下汇报，等指令。

补充判据（源隔离的常见破口）：

- 跑 pytest 前先确认目标测试不会写真实 derived/。测试若靠「先快照再恢复」来保护
  真实目录，等于测试期间仍在写真实目录；teardown 失败或并发执行就会留下污染。
  正确做法是把测试的 output_root 指向 tmp_path，**全程不碰真实路径**。
- 重跑 norms.jsonl 的抽取时，只允许改目标源的条目；其余源的行必须逐字节不变。
  合并前先验证行数不变、非目标源行零差异、变动行的非 content 字段零差异
  （典型陷阱：ProtocolNorm.added_at 缺省取 now_iso()，重跑会被刷新成新时间戳）。
- 指纹类证据只在同一种生成方式下可比。换了写入方式（如 Out-File -Encoding utf8
  会写 BOM 并用 CRLF）得到的哈希差异是测量偏差，不是数据变化，不要据此报「数据被改」。

## 十二、自主执行协议（2026-10-08 新增）

本协议定义 workbuddy 的自主权边界。

### 12.1 可自决（不需停下）

- **Step 级任务的执行细节**：读哪些文件、用哪些脚本、跑哪些测试
- **实测与预期不符时的诊断**：先做只读勘察，报告事实
- **格式修复**：笔误、路径写错、字段名写错（不改语义）
- **审计与登记**：写 audit、加 backlog 条目
- **roadmap_next.md 的维护**：勾销完成项、写下一步

### 12.2 必须停（不许自决）

- **Layer 级设计裁定**（如 Layer 1 范围甲乙、落盘方案）
- **任何写 `kb/`、`derived/` 的操作**（除明确授权的 Step）
- **改冻结文档**（`fused_hub/docs/` 下 `fused_*`）
- **改 `core/fused/` 下 v1 模块**
- **前序 Step 发现未登记的越界或未决项**
- **实测与预期严重不符（差 > 1 或结论相反）**
- **两个方案都合理、契约未写、语义不明**
- **pytest failed 或 errors != 0**
- **`kb/` fingerprint 变化**

### 12.3 停下时的汇报格式

```
待裁定项：一句话
选项：A / B / C
每个选项：描述 + 代价
我的推荐 + 理由（一句话）
```

不许只说「失败了」，不许「我建议 X」而不给其他选项。

### 12.4 与用户的关系

- 用户是**裁定者**，不是**任务分发者**
- workbuddy 自己从 `实施/roadmap_next.md` 取任务，不等人喂
- 只在 12.2 情况下停下问
- 停下的频率越高，说明 roadmap 越不清晰——此时应停下讨论 roadmap，而不是硬推