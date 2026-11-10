# CI 与验收说明（ProtoKG）

本文说明 ProtoKG 的 CI 集成层：有哪些 job、每个 job 验什么、闸门语义是什么、
本地怎么复现同样的验收结论、基线文件在哪、怎么更新、已知局限是什么。

> 配套文件
> - `.github/workflows/ci.yml` —— CI 定义（5 个 job）
> - `guard/run_guarded_pytest.py` —— 验收护栏脚本（闸门本体，本地与 CI 共用）
> - `guard/baseline/` —— 四份期望集基线（见 §3）

---

## 0. 真机运行记录（2026-11-02，GitHub Actions 实跑）

CI **不是「写完就算」** —— 它在真机 runner 上连跑 4 次，**抓出了 3 个真缺陷**。

| run | 提交 | 结果 | 抓到了什么 |
|---|---|---|---|
| 41355877501 | `6b0b54e` | ❌ 3 过 2 挂 | ① `numpy==2.5.4` 要求 Python ≥3.12，而 workflow 用 3.11 ⇒ **两个 pytest job 一个测试都没跑就红了** |
| 41356142634 | `835a37f` | ❌ 3 过 2 挂 | ② Ubuntu 上 ERROR 21 vs 基线 20 ⇒ 新增 `test_frozen_jsonl_is_lf_on_disk`：**CRLF 探针 fixture 的 teardown 遇 `__pycache__` 目录抛 `IsADirectoryError`**（本地 Windows 永远测不出来） |
| 41357183519 | `66d7a89` | ❌ 4 过 1 挂 | ③ Windows runner 控制台是 OEM 代码页 ⇒ 护栏脚本**第一行打印中文就抛 `UnicodeEncodeError`** ⇒ 脚本崩溃、**产物一个都没落盘**、日志里看不到任何闸门结论 |
| **41358327742** | **`0cc7455`** | ✅ **5/5 全绿** | — |

**最终 run 的实测数字（Ubuntu 与 Windows 完全一致）**：

```
== 护栏2：summary 行存在 ✅ 68 failed / 1302 passed / 20 errors / 10 skipped
== 抽取结果 ==
   FAILED 68 条   ERROR 20 条
   failed: 期望 68 / 实测 68 | 新增 0 / 消失 0
   errors: 期望 20 / 实测 20 | 新增 0 / 消失 0
== 结论：✅ 可采信 ==
```

> ★ **Windows 与 Linux 的失败集合逐条相同**（68/20）⇒ 验收结论**跨平台可复现**。
> ★ 本地完整环境（含 `derived/` 产物）是 37 failed / 1342 passed / 20 errors / 1 skipped；
> CI（干净 checkout，无 `derived/`）是 68 / 1302 / 20 / 10 ⇒ 差的那 31 条**全部**源于
> gitignored 的 `derived/` 中间产物缺失（**不是**跨平台差异）。

**这 3 个缺陷都是「本地三道护栏全绿」也发现不了的**：
① 依赖版本与解释器版本不匹配；② 只有 Linux 才会生成的 `__pycache__` 目录；
③ 只有 Windows 控制台代码页才会触发的编码崩溃。
⇒ **这就是「必须有 CI」的理由**，也是本仓把它当**验收闸门本体**而不是装饰的原因。

---

## 1. 一个必须先讲清楚的前提：CI 的闸门不是「零失败」

本仓当前有 **37 个预存失败**（详见 §4）。它们是**已知的、预存的研究契约脱节**，
不是某次改动引入的 bug。因此：

| 闸门语义 | 结果 | 是否可用 |
|---|---|---|
| 「所有测试必须全绿」 | **永远红**（37 个预存失败） | ❌ 失效 |
| 「**失败集合不漂移**」 | 允许已知失败，**新增失败即红** | ✅ 本 CI 采用 |

本 CI 的判据是：**相对本环境的已知失败集合，任何新增失败/错误都会让 job 变红；
旧的失败消失也会被报出来**（防止有人靠改测试或改基线把失败偷偷洗掉）。

护栏脚本的退出码即闸门信号：

| 退出码 | 含义 | CI 行为 |
|---|---|---|
| `0` | 护栏全过 + 失败集合未漂移 | job 绿 |
| `1` | 护栏被触发（树在动 / 无 summary 行 / 抽取口径不一致 / **集合漂移**） | **job 红** |
| `2` | 用法/环境错误（仓库根不对、解释器缺失、路径不存在） | **job 红** |

---

## 2. CI 的 job 列表

`.github/workflows/ci.yml` 共 5 个 job，触发条件 `push` / `pull_request` /
`workflow_dispatch`（可手动触发）。

| # | job | 平台 | 验什么 | 闸门语义 |
|---|---|---|---|---|
| 1 | `static-checks` | Ubuntu | `guard/` 的 ruff lint + **全仓语法可解析**（`core/` `scripts/` `tests/` `guard/`） | 任一检查失败 ⇒ 红 |
| 2 | `byte-contract` | Windows | **字节契约**：`.gitattributes` 里 `-text` 保护的 `*.dict` / `*.raw` / `*.sip`，工作区字节必须 == 入库 blob 字节 | 任一文件字节不一致 ⇒ 红 |
| 3 | `guarded-pytest` | Ubuntu | 全量 pytest 的**失败集合相对 CI 基线不漂移**（主闸门） | 漂移 ⇒ 红 |
| 4 | `guarded-pytest-windows` | Windows | 同上，但在 Windows 上跑（**先归一化 LF**），验证两个平台结论一致 | 漂移 ⇒ 红 |
| 5 | `corpus-gate-smoke` | Ubuntu | `scripts/corpus_gate.py`（语料发布准入闸）**有调用方且能被 CI 执行**，且**闸门有牙齿** | 见下 |

### 2.1 为什么 Windows 与 Ubuntu 都要跑

**行尾归一化已在仓库层解决（2026-11-02，`beadb38`）**：
`.gitattributes` 现在有 `* text=auto eol=lf` ⇒ **代码 / 文档 / 测试在所有平台检出都是 LF**
⇒ 同一份提交在 Windows 与 Linux 上工作区字节一致 ⇒ 两个平台的失败集合可比。

实测（干净 clone，`git clone` 后 `git ls-files --eol` 统计）：

| 范围 | CRLF | LF | 说明 |
|---|---|---|---|
| 非 kb/ | **0** | 386 | ⇒ 跨平台一致 ✅ |
| kb/（研究素材） | 6440 | 58 | 保持**平台默认**，抽取输入字节不变（见下） |

> ★ **为什么 kb/ 必须排除**：`kb/*/历史漏洞/*.json` 与 `kb/*/expert_note/*.json`
> 是**五源之一（历史漏洞 / expert_note）的抽取输入** ⇒ 它们的字节进入 fact 的 `value`
> 与 `evidence_id`/`claim_id` 的摘要输入 ⇒ **改行尾 ⇒ 改 fact_id ⇒ 整座知识中枢指纹全变**
> ⇒ kb/ 显式 `text=auto -eol`（回落到平台默认，保持现状行为）。

**Windows job 仍保留显式归一化步骤**（`core.autocrlf=false` + `core.eol=lf` +
`git checkout-index --all --force`），作为**双保险**：
`.gitattributes` 只管 checkout，而 `checkout-index` 对已存在文件的 stat 缓存会跳过重写，
显式归一化可确保 runner 上无论何种来源的工作区都归一。

同时 job 2 单独验证「即使有人重新开启 autocrlf，受保护文件的字节也不变」。

> 📌 **一处已更正的早期断言**：本节原先写「CRLF 物化 ⇒ 多出 10 条行尾断言失败
> （`test_scripts_syntax::test_shell_scripts_use_lf_line_endings` 等）」。
> **该断言未能复现** —— 2026-11-02 实测：CRLF 工作区（本机，208 个 CRLF 文件）与
> LF 干净 clone 两边**都没有** `test_scripts_syntax` / `test_rq4_*` 类失败
> （前者的 37 条失败里无一条是行尾断言；后者的 68 条里同样为 0）。
> ⇒ 那条「多 10 条」的说法缺乏证据，**已删除**；Windows job 的归一化步骤
> 保留为预防性措施，其注释也已同步更正。

### 2.2 `corpus-gate-smoke` 的两个断言

`scripts/corpus_gate.py` 此前**零调用方** —— 它是本项目最重要的质量红线之一
（G1 客户端 host 污染 / G2 不可播会话 / G5 契约一致性），却没有自动化在跑它。

真实语料在 `derived/seeds/`（gitignored），且
`derived/seeds/rtsp/live555_20261024_110155` 是**真实抓包语料**、无法在 CI 重建，
所以 workflow **现场生成一份最小 RTSP 语料**（39 个 `.raw`，端点 `127.0.0.1:8554`、
会话 `mp3AudioTest`、聚焦组 B —— 恰好命中 rtsp profile 的 G1/G2/G5 三条判据），
然后断言两件事：

1. **干净 fixture → 退出码 0**，G1/G2/G5 全部 PASS；
2. **污染 fixture → 退出码 1**（把 host 换成非目标主机 `10.11.26.98:554`，
   复刻 2026-10-31 坐实过的静默退化场景）⇒ G1 必须报出违规并阻断。

第 2 条是「闸门有牙齿」的证明：**若污染语料也能放过，G1 就是摆设。**

该 job **不装任何第三方包** —— `corpus_gate.py` 只依赖标准库 + 本仓 `core/`。

---

## 3. 基线文件在哪、分别管什么

全部在 `guard/baseline/`：

| 文件 | 行数 | 用途 | 用它的场景 |
|---|---|---|---|
| `expected_b_class_failed_ids.txt` | **37** | 预存 FAILED 集（**带完整路径**） | 本机 / 完整环境（有 `derived/` 产物） |
| `baseline_errors_pre_cleanup.txt` | **20** | 预存 ERROR 集（**只有函数名**） | 同上 |
| `ci_expected_failed_ids.txt` | **68** | CI 环境的 FAILED 集 | GitHub Actions（全新 checkout） |
| `ci_expected_errors.txt` | **20** | CI 环境的 ERROR 集 | 同上 |

### 3.1 为什么 FAILED / ERROR 两份基线的行格式不同

这是**刻意**的，不是笔误：

- pytest 的 FAILED 摘要行是 `FAILED tests/test_x.py::test_y` ⇒ 抽取时**带完整路径**；
- ERROR 在 `--tb=no` 下只有短摘要形态 `ERROR tests/...::test_y - msg`，
  而本仓的 ERROR 清单按**函数名**记录（`test_build_succeeds`）⇒ **不带路径**。

⇒ 两份基线的行格式必须与 pytest 的输出形态一一对应。**不要"顺手统一"**，
那会让比对恒为漂移。

### 3.2 为什么需要两份 FAILED 基线（37 与 68）

**失败集合依赖运行环境，不是纯代码属性。** 实测（2026-11-02，同一份代码）：

| 环境 | failed | passed | skipped | errors |
|---|---|---|---|---|
| 本机工作区（有 `derived/` 产物） | **37** | 1252 | 1 | 20 |
| 全新 checkout（无 `derived/` 产物） | **68** | 1179 | 4 | 20 |

差的 31 条**全部**源于 `derived/` 是 gitignored 的中间产物
（`.gitignore` 明写「derived/* … 可由 kb/ 重建」），**不是代码缺陷**。
典型例子：`test_compat.py::test_at_least_120_succeed` 读 `derived/hub/facts/`（早期遗留 131 facts），
`test_rq3_focus_group.py::test_focus_group_c_matches_rq12_corpus` 读
`derived/seeds/rtsp/live555_20261024_110155`（**真实抓包语料**，无法重建）。

**ERROR 集合在两种环境下完全相同（20 条，漂移 0）** —— ERROR 侧与环境无关。

⇒ 两份基线**不可互换**：拿 68 的去比本机、或拿 37 的去比 CI，都会报出大量漂移，
而那是**环境不匹配**，不是回归。

---

## 4. 已知局限：37 个预存失败分别是什么、为什么不修

### 4.1 分布

| 文件 | 条数 |
|---|---|
| `（该批 RQ3 语料契约测试已随论文实验层移除）` | 22 |
| `tests/test_rq3_manifest.py` | 6 |
| `tests/test_rq3_dict.py` | 3 |
| `tests/test_rag_seedgen.py` | 2 |
| `tests/test_rag_seedgen_step2.py` | 2 |
| `tests/downstream/test_edge_cover.py` | 1 |
| `tests/test_strategy.py` | 1 |
| **合计** | **37** |

**31 / 37 集中在 RQ3 语料契约**（focus_group + manifest + dict）。

### 4.2 三类根因（全部是「研究契约脱节」，不是代码 bug）

**① 种子条数与 profile 声明的契约不符**（占比最大）

```
test_rq3_focus_group.py:255  种子数不符: 期望 50，实际 65（分组配置与实际生成不一致）
test_rq3_focus_group.py:255  种子数不符: 期望 38，实际 52
test_rq3_focus_group.py:330  rtsp/rq2-live555/A: 种子数不符: 期望 27，实际 41
test_rq3_manifest.py:207      种子数不符: 期望 50，实际 65
```

即：`profiles/<proto>/profile.json` 里 `seedgen.focus_group.<组>.seeds`
声明的条数，与 `scripts/seedgen.py` 实际生成的条数对不上。
这是**实验契约与实现之间的漂移** —— 要么改 profile 声明、要么改生成逻辑，
**两者都会改变研究语料的语义**（分组大小直接影响 RQ3 的对比实验设计）。

**② 字典 token 数与冻结记录不符**

```
test_rq3_dict.py:96    assert 114 == 102      （协议字典：实测 114 token，冻结记录 102）
test_rq3_dict.py:129   assert 136 == 123
test_rq3_focus_group.py:235  assert 114 == 102
```

即 `（已随论文实验层移除）rq3/dict/DICT_FROZEN.json` 冻结的 token 数与当前字典内容对不上。
**冻结记录是论文附录引用的凭证**，改它需要同步论文；改字典会改变
所有已生成语料的字节内容（进而让 A1–A10 断言的 md5 基准失效）。

**③ manifest 记录数与实际语料不符**

```
test_rq3_manifest.py:225  assert 3 == 0        （manifest 里多出 3 条记录）
test_rq3_focus_group.py:470 / 488 / 500 ...  assert 3 == 0
```

manifest 是语料的溯源凭证，多出的 3 条记录需要人工判断是「生成器多写了」
还是「语料确实包含这 3 条但 manifest 没删干净」—— **不能靠改测试绕过**。

### 4.3 为什么现在不修

1. **改任一侧都会改变研究语料的语义**。分组条数、字典字节、manifest 记录数
   三者互相咬合（`scripts/rq3_build_corpus.py` 的 A1–A10 断言就是为守住这个咬合关系而写的）。
   单点改动会把「已知且被记录的偏差」变成「未被记录的偏差」—— 那比现在这 37 条更危险。
2. **论文口径依赖冻结值**。`DICT_FROZEN.json` 的 token 数被论文附录引用，
   改动需要同步论文与实验记录，超出本轮范围。
3. **它们已被完整记录、且被 CI 锁住**。这正是本 CI 存在的意义：
   既然暂时不修，就必须让「它们的存在」变成**显式、可审计、不可悄悄变化**的事实。
   基线文件就是这个锁。

⇒ **处理这 37 条的正确姿势不是改测试，而是按 §5.2 的流程显式更新基线**，
并在更新时说明「这批失败确实是预存契约脱节，而非新 bug」。

---

## 5. 本地怎么复现 CI 的验收结论

### 5.1 Windows（本机开发环境）

用项目约定的解释器 `E:/app/Anaconda3/python.exe`（**不要用 `python`** ——
那是 WorkBuddy 自带的 3.13，与项目依赖不一致）：

```bash
cd "E:/科研/想法idea/ProtoKG"
E:/app/Anaconda3/python.exe guard/run_guarded_pytest.py
```

期望：**退出码 0**，`37 failed / 1252 passed / 20 errors / 1 skipped`，
失败/错误集合漂移 **0 / 0**。

> 仓库根默认由脚本位置推断（`guard/` 上两级），**不硬编码绝对路径**；
> 需要时用 `--repo-root <目录>` 覆盖。

### 5.2 Linux / CI 等价（干净 checkout）

```bash
# 1) 干净 checkout（模拟 CI 的全新环境）
git -c core.autocrlf=false clone "E:/科研/想法idea/ProtoKG" /tmp/ci_local
cd /tmp/ci_local

# 2) 最小依赖（实测 pytest + numpy 即足够）
python3 -m venv .venv && . .venv/bin/activate
pip install "pytest==8.4.2" "numpy==2.5.4"

# 3) 跑护栏，用 **CI 基线**
python guard/run_guarded_pytest.py \
  --repo-root "$PWD" \
  --out-dir "$PWD/_ci_artifacts" \
  --expect-failed "$PWD/guard/baseline/ci_expected_failed_ids.txt" \
  --expect-errors "$PWD/guard/baseline/ci_expected_errors.txt"
```

期望：**退出码 0**，`68 failed / 1179 passed / 20 errors / 4 skipped`，漂移 **0 / 0**。

### 5.3 单独跑基线比对（不跑测试）

```bash
E:/app/Anaconda3/python.exe -m pytest tests/ -q -p no:cacheprovider --tb=no -rfE
```

`-rfE` 是**合并形式**（f=失败、E=错误），两个报告都出。
**务必注意**：pytest 的 `-r` 是**覆盖**语义而非追加 ——
写成 `-rf -rE` ⇒ 生效的只有 `-rE` ⇒ **FAILED 行根本不输出** ⇒
抽取恒为空集 ⇒ 失败集合比对变成拿空集在比 ⇒ **永远判定「无漂移」**。
这是一个看起来在把关、实际什么都不拦的假闸。

### 5.4 其他检查

```bash
# ruff（只查闸门工具 guard/；全仓有 114 个既存告警，不在本次改动范围）
E:/app/Anaconda3/python.exe -m ruff check guard/

# 语法扫描（范围限定 core/scripts/tests/tools —— 见下方「为什么必须限定」）
E:/app/Anaconda3/python.exe -c "
import ast, pathlib, sys
bad = []; n = 0
for d in ('core', 'scripts', 'tests', 'tools'):
    for p in pathlib.Path(d).rglob('*.py'):
        if '__pycache__' in str(p): continue
        n += 1
        try:
            ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p))
        except SyntaxError as e:
            bad.append(f'{p}: {e}')
print(f'scanned {n} python files under core/scripts/tests/tools')
for b in bad: print('SYNTAX ERROR:', b)
sys.exit(1 if bad else 0)
"

# 字节契约（工作区字节 == 入库 blob 字节）
for f in profiles/rtsp/rtsp_base.dict profiles/ftp/ftp_base.dict; do
  echo "$f $(git cat-file blob HEAD:$f | md5sum) $(md5sum $f)"
done

# corpus_gate 冒烟
# ★ 2026-11：corpus_gate.py 已随论文实验层整体移除 ⇒ 该冒烟步骤不再适用
```

---

## 6. 怎么更新基线（正确流程）

> ⚠ **基线不是「让 CI 变绿」的旋钮。** 随手更新基线 = 把回归洗成「已知失败」。

### 6.1 什么时候可以更新

**只有**当失败集合的变化**确实**来自「预存契约脱节的状态推进」，
而不是「新引入的 bug」时，才可以更新。判断方法：

1. 跑一次护栏脚本，看它报出的 `新增` / `消失` 清单；
2. 对**每一条**新增失败，**单独**跑它并读完整断言输出，确认它是
   「契约期望值 vs 实际值」型偏差（如同 `assert 114 == 102`、
   `种子数不符: 期望 50，实际 65`），**而不是** `TypeError` / `AttributeError`
   / `ImportError` 这类**代码错误**型失败；
3. 对**每一条**消失的失败，确认它是被**修好**了（而不是被 skip 掉了）。
   ⚠ 特别注意：pytest 的 `skip` **不算失败**，一条失败被改成 skip 会让它
   从 FAILED 集合里消失 ⇒ 护栏会报「消失」⇒ 这是好事，会被拦下来让你确认。

### 6.2 更新流程

```bash
# 1) 先看漂移（不要跳过这步）
E:/app/Anaconda3/python.exe guard/run_guarded_pytest.py
#    → 读 "新增 N / 消失 M" 清单，逐条按 §6.1 判断

# 2) 确认无新 bug 后，重新采集基线
E:/app/Anaconda3/python.exe -c "
import re, sys
from pathlib import Path
out = Path('guard/_guarded_raw.txt').read_text(encoding='utf-8', errors='replace')
failed = sorted(set(re.findall(r'^FAILED\s+(\S+)', out, re.M)))
errors = sorted({x.split('::')[-1] for x in re.findall(r'^ERROR\s+(\S+)', out, re.M)})
Path('guard/baseline/expected_b_class_failed_ids.txt').write_text('\n'.join(failed) + '\n', encoding='utf-8')
Path('guard/baseline/baseline_errors_pre_cleanup.txt').write_text('\n'.join(errors) + '\n', encoding='utf-8')
print(f'failed={len(failed)} errors={len(errors)}')
"

# 3) 换环境时要更新**另一份**（CI 基线）
#    在干净 checkout 里重跑，采集 ci_expected_failed_ids.txt / ci_expected_errors.txt

# 4) 复跑确认漂移归零
E:/app/Anaconda3/python.exe guard/run_guarded_pytest.py
```

### 6.3 更新基线时必须做的事

- **在 commit message / PR 描述里写清楚**：改了哪几条基线、每条的根因、
  为什么判定为「预存契约脱节」而非新 bug；
- **不要改 `tests/` 下的任何测试文件**来让 CI 变绿 —— 那是在销毁闸门本身；
- 改完基线**必须复跑护栏脚本**确认漂移归零。

---

## 7. 已知局限（诚实清单）

| # | 局限 | 影响 | 现状 |
|---|---|---|---|
| 1 | **37 个预存失败仍在** | CI 长期处于「带已知失败运行」状态 | 已用基线锁住，见 §4 |
| 2 | **CI 基线（68）与本机基线（37）不同** | 换环境必须换基线 | 已分文件存放并文档化，见 §3.2 |
| 3 | **`derived/` 中间产物不入库** | 31 条测试在 CI 上因缺产物而失败 | 已确认为环境差异而非回归；`kb/` 已入库，`build_hub.py` 可重建大部分（`source` 源需 `DEEPSEEK_API_KEY`） |
| 4 | **`derived/hub/facts/`（早期遗留 40MB）与 `live555_20261024_110155`（真实抓包语料）无法重建** | 这部分测试在 CI 上必然失败 | 已计入 CI 基线 |
| 5 | **Ubuntu 真机未实测** | 「Ubuntu 等价」结论基于「干净 LF checkout + 最小 venv」的 Windows 实测 | 本机 Docker Desktop 需 WSL2，被环境安全策略拦截，无法起容器 |
| 6 | **ruff 只查 `guard/`** | `core/` `scripts/` `tests/` 的 114 个既存 lint 告警不被 CI 拦 | 那些文件不在本次改动范围，动它们会污染 diff |
| 7 | **`corpus_gate` 冒烟用合成 fixture** | 不覆盖真实语料的全部形态 | 真实语料是真实抓包、无法在 CI 重建；冒烟的职责是证明「闸门可执行且有牙齿」 |
| 8 | **`kb/*/数据流量/*/client.log` 未入库**（被 `*.log` 规则排除） | traffic 源的 LLM 兜底测试在 CI 上失败 | 已计入 CI 基线 |
| 9 | **全仓 `ast.parse` 语法扫描不可能通过** | 用户原命令 `pathlib.Path('.').rglob('*.py')` 会扫到两个硬障碍 | 已改为限定范围，见下 |

### 7.1 为什么语法扫描必须限定范围（用户原命令实测失败）

用户给出的命令：

```bash
E:/app/Anaconda3/python.exe -c "import ast,pathlib; [ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('.').rglob('*.py') if '__pycache__' not in str(p)]"
```

**实测失败**（两个独立原因，都不是本次改动引入的）：

1. **BOM**：`core/raw_writers.py` 带 UTF-8 BOM。用 `encoding='utf-8'` 读会把 BOM
   当成 U+FEFF 字符留在源码开头 ⇒
   `SyntaxError: invalid non-printable character U+FEFF`。
   ⇒ 必须用 `encoding='utf-8-sig'`（自动剥离 BOM）。
2. **vendored 素材**：`kb/` 下有研究素材（kamailio 的 Python 2 示例源码），
   用 Python 3 的 `ast.parse` 解析必然失败
   （`print res` ⇒ `SyntaxError: Missing parentheses in call to 'print'`）。
   ⇒ 扫描范围必须限定在 `core/` `scripts/` `tests/` `guard/`
   —— 即**本仓自己的代码**，研究素材不纳入语法门。

限定版实测：`scanned 153 python files under core/scripts/tests/tools` → **0 错误，退出码 0**。
CI 的 `static-checks` job 用的就是这个版本。

---

## 8. 闸门有效性验证（反向验证）

「闸门能检出回归」不能只靠断言，必须实测。2026-11-02 的验证记录：

| 验证 | 方法 | 结果 |
|---|---|---|
| **注入回归必被检出** | 在干净 checkout 的 `tests/downstream/test_edge_cover.py` 追加一条必然失败的测试 | 护栏脚本报出「新增 1 / 消失 0」⇒ **退出码 1** ⇒ job 红 |
| **基线不匹配必被检出** | 用本机基线（37）去比 CI 环境（实测 68） | 报出大量新增/消失 ⇒ **退出码 1** |
| **字节契约破裂必被检出** | `.dict` 的工作区字节被改成与 blob 不同 | 报 `BYTE CONTRACT VIOLATED` ⇒ job 红 |
| **corpus_gate 污染语料必被阻断** | 把 fixture 的 host 换成 `10.11.26.98:554` | G1 报出 39 处违规 ⇒ **退出码 1** |

⇒ 四道闸门都经过「故意破坏 → 必须变红」的正反双向验证，不是「跑通了就算数」。

---

## 9. 附：护栏脚本的四道检查

`guard/run_guarded_pytest.py` 的全部语义（本地与 CI 完全一致）：

1. **护栏1 —— 树静止**：跑前/跑后各取一次源码 mtime 快照；
   diff 非空 ⇒ 本次结果**不可采信**（并发编辑污染）。
   实测教训：同一棵树连跑三次得 38 → 46 → 37。
2. **护栏2 —— summary 行必须存在**：pytest 被 kill 在打印 summary 之前时，
   `grep '^FAILED'` 拿到**空集**，与「真的 0 失败」在 grep 层面无法区分
   ⇒ 无 summary 行 ⇒ 判「本次运行无效」，**不得当成 0 失败**。
3. **护栏3 —— 集合逐行比对**：FAILED / ERROR 集合与期望基线比对，
   **新增与消失都要报**（消失也要报 ⇒ 防止靠改测试把失败洗掉）。
4. **护栏4 —— 抽取口径自检**：summary 说有 N 条失败、但只抽到 M 条
   ⇒ **抽取口径坏了** ⇒ 此时「与期望集比对」是拿残集在比，结论无效
   ⇒ 直接判**不可采信**。
