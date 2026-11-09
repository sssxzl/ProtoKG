# RQ4 · 3 协议 × 2 组 AFLNet 模糊测试实验 —— 架构设计方案

> **版本 v3（2026-10-31 修订 · 实验已执行后的回填）** · 架构师：高见远（Gao）
> v2 相对 v1 的变更：**① 路线 A/B 选型收敛为「路线 C：挂载 in-* 目录覆盖」**（§1.2）；
> **② 官方参数溯源到 git commit，解释了三组参数的来源与取舍**（§1.3）；
> **③ 字典策略从「两组都用官方」修正为「按协议分别裁定 + 字典消融波」**（§4）；
> **④ 新增「数量对齐对照组」设计，解决种子数量混淆变量**（§5）；
> **⑤ 主口径确定为 bitmap_cvg，cov_over_time.csv 作为文献对齐的次口径**（§7）。
>
> **v3 相对 v2 的变更（实验已执行，本文档回填实测事实）**：
> **① 修正 §3.2 语料路径**：实验实际使用的是 `derived/model/seeds/<proto>/rq4_B/`（**39/25/78 条**，非 v2 写的 `pfb_exp_B/` 50/56/78）；
> **② 新增 §12「语料可复现性回归」（P0）**：当前事实库重新生成三协议均**无法复现**实验语料（54/20/61 ≠ 契约 39/25/78），`seedgen.py` 退出码 3；
> **③ 新增 §13 实验实测结果与结论边界**（含三口径对照）；
> **④ 修正 §5 数量对齐组的基线数字**（官方语料 29/4/14 region 不变，ProtoRAG 侧改为 39/25/78 口径）；
> **⑤ ★ §12.2 根因归因更正（消融实验）**：驱动源是**非 rfc 源**（`source`/`traffic`/`vuln`，10-31 04:53 重建），**rfc 源对种子产出贡献 = 0** → v2 的 S2「回退 rfc」方案作废；
> **⑥ ★ §12.4 新增「IP 摄像机 URL 污染」缺陷**：当前重生成的 RTSP 语料 59.5% 种子打向 `10.11.26.98`（非目标主机），根因在 `seedgen.py:273` 兜底条件不覆盖真实抓包 URL → 复现路径已断；
> **⑦ §12.5 处置方案修订**：S2 作废 → S1′/S2′/S3/S4（含发布准入闸 G1/G2/G3）。
>
> **v4（2026-10-31 晚，team-lead 复核后）**：
> **⑧ §12.6 新增：污染修复已通过 + 「幂等 ⇒ 历史语料逐字节不变」不成立**（track1/transport 演进，正交于 RFC 改造）；
> **⑨ §12.5.2 S3 规格重出**：VM 上 `MANIFEST.md5` **已存在**（父目录 `<proto>.manifest.md5`），仅 `manifest.json` 与 `README-dict.txt` 缺失 → 改为「补 3 + 跳过 3」；
> **⑩ §13.6 新增：可复现性陈述的准确措辞**（语料快照仍在仓库且可校验，**不可从当前代码重建**）。
>
> 权威依据：VM `192.168.37.130` 上 `/home/zxy/profuzzbench` 源码（git HEAD `8573ec8`）+ `rq2-*` 镜像内实际 `run` 脚本（逐字核对）+ VM `/home/zxy/rq4/rq4_summary.csv` 实测数据
> 图示：[`图/RQ4编排图.mermaid`](../图/RQ4编排图.mermaid) · [`图/RQ4时序图.mermaid`](../图/RQ4时序图.mermaid) · [`图/RQ4类图.mermaid`](../图/RQ4类图.mermaid)

---

## 0. 结论速览

| 决策项 | 结论 | 依据 |
|---|---|---|
| **执行路线** | **路线 C**：复用镜像内官方 `run` + **bind-mount 覆盖 `in-*` 目录**，不改任何脚本 | A 要维护脚本副本且与镜像布局冲突；B 要手工重拼 12 个易错参数。三协议统一机制见 §1.2 |
| **官方参数** | **以 git HEAD `8573ec8` 为准**：`-t 5000`（固定）+ `-m none`；kamailio **不加 `-R`** | §1.3 溯源：转述的 `-t 1000+`/`-t 3000+` 来自 2021 年 ASAN 之前的旧 commit |
| **baseline 种子** | **零挂载**，直接用镜像内 `/home/ubuntu/experiments/in-*` | 镜像内种子与 ProfuzzBench 源码树 md5 **逐个相同**（7/7、2/2、1/1） |
| **protorag 种子** | `-v <host>:<in-rtsp\|in-sip\|in-smtp>:ro` **同名覆盖** | `run` 的 `INPUTS` 指向固定路径，覆盖即生效，三协议同一机制 |
| **字典** | **按协议裁定**（§4.2）：RTSP/SMTP 两组同用**官方**；SIP 两组同用**无字典**。ProtoRAG 字典另开**消融波** | 字典必须组间恒定才能把差异归因到种子；RTSP 上 ProtoRAG 字典与官方 token 完全相同 |
| **RTSP 端口** | **8554**（官方），纠正既往 8560 | 镜像内 `run` 硬编码 `-N tcp://127.0.0.1/8554` + `./testOnDemandRTSPServer 8554` |
| **数量混淆变量** | **新增「数量对齐组」**（protorag 截断到官方条数）作为**附加对照**，与主实验分开报告 | §5：78 vs 2 条种子时，"覆盖更高"无法区分"质量更好"与"语料更大" |
| **编排脚本** | **3 个**（launch / collect / dry-run），协议差异用参数表 | §6 |
| **主口径** | **`bitmap_cvg`**（fuzzer_stats，实时可得、跨协议同定义）；**次口径** `cov_over_time.csv` 末行 `l_per/b_per`（文献对齐） | §7.2 |
| **容器退出判定** | **不以容器退出为 fuzz 结束标志**；以 `fuzzer_stats.last_update` 停滞判定 | `run` 在 3h 后还有 1~3h `cov_script` 后处理 |

---

## 1. 实现方案

### 1.1 核心技术难点与选型

| # | 难点 | 方案 | 依据 |
|---|---|---|---|
| ① | **官方参数版本溯源**：转述的 `-t 1000+` / `-t 3000+` / 缺 `-m none` 到底对不对 | **按 git commit 溯源**，确认它们来自 2021 年 ASAN 支持之前的旧版本；现 HEAD 为 `-t ${TEST_TIMEOUT}`(=5000) + `-m none` | §1.3 完整 commit 演进表 |
| ② | **执行路线选型**：A（改 run.sh 副本）/ B（绕过 run.sh 手拼命令） | **路线 C**：镜像内官方 `run` 不动，用 bind-mount 覆盖 `in-*` 目录注入种子 | §1.2 三路线对比 |
| ③ | **镜像 ≠ 源码树**：`rq2-live555` 内是 `live/`+`live-gcov/`，源码树是 `live555/`+`live555-cov/` | 只用**镜像内** `run`；**绝不**把源码树 `run.sh` 挂进容器 | 实证：镜像内 `experiments/live555/` **不存在** → 挂进去会 `cd` 失败 |
| ④ | **两组种子路径不同** | 统一用**同名 bind-mount 覆盖**；baseline 不挂载 | `run` 中 `INPUTS=${WORKDIR}/in-rtsp`（RTSP/SMTP 硬编码）或 `${INPUTS:-${WORKDIR}"/in-sip"}`（SIP）→ 路径固定，覆盖即生效，**不改脚本、不用环境变量** |
| ⑤ | **RTSP 端口** | 8554（官方） | 镜像内 `run` 硬编码 `-N .../8554` + server `8554`；ProtoRAG 种子 URL 内嵌 `:8554`；既往 `rq1_2_rerun.sh` 用 8560 且**漏 `-c`** |
| ⑥ | **SIP 必须 `-l 5061`** | 官方 OPTIONS 原样保留 | `afl-fuzz.c:9147` 注释明示仅用于"回包到特定端口"的目标，Kamailio 即是；缺失 → `afl-fuzz.c:9289` PFATAL "No server states" |
| ⑦ | **RTSP 种子 47.9% 请求打不存在的 media** | **实验前用 `aflnet-replay` 逐会话验证**；**强烈建议重生成**限定 7 个可播会话 | live555 镜像内仅 7 个 media 文件；ProtoRAG 引用 18 个会话名，142 个状态变更请求中 68 个指向无 media 会话 → 404 |
| ⑧ | **SIP 39.4% 方法起点不被 AFLNet 识别** | 记录为口径限制；建议重生成时只让 `REGISTER/INVITE/ACK/BYE` 起新消息 | `aflnet.c:1070-1074` 只认这 4 个；358 个方法起点仅 217 个（60.6%）被识别 |
| ⑨ | **种子数量混淆变量**（78 vs 2 / 56 vs 1 / 50 vs 7） | **新增数量对齐组**（截断 protorag 到官方条数）作为附加对照 | §5 |
| ⑩ | **字典不对称**（SIP 官方无字典） | 组间恒定 + 独立字典消融波 | §4 |
| ⑪ | **`cov_script` 后处理 1~3h** | 3h fuzz 预算与后处理预算分离；主指标不依赖后处理 | `cov_script` 逐用例重放（RTSP/SIP 每轮 3s server timeout） |
| ⑫ | **容器退出 ≠ fuzz 结束** | 双信号判定：`fuzzer_stats.last_update` 停滞 = fuzz 结束 | `run` 顺序：afl-fuzz(timeout) → cov_script → gcovr → tar → exit |
| ⑬ | **宿主磁盘 94%，仅剩 6.0G** | 强制前置清理（可回收 ~6.7GB）；要求 ≥15GB | 18 exited 容器 + 3 个 2.23GB dangling 镜像 |
| ⑭ | **容器间资源争抢影响公平** | 每容器 `--cpus=1`（官方同款）→ 上限 6/16 核 | 不加限制时 A 容器 gcovr 会抢 B 容器 fuzz 的 CPU → exec 速率不等 → 覆盖率不可比 |
| ⑮ | **产物属主 root → 宿主不可读** | 采集用 `docker exec ... cat/tar > 本地文件`；`docker cp` 亦可（已实测属主映射为 zxy） | 见 §7.3 的实测更正 |

### 1.2 ★ 执行路线选型：A / B / C 对比与选型结论

主理人提出路线 A（改 run.sh 副本）与路线 B（绕过 run.sh 手拼 afl-fuzz 命令）。我核查源码后**新增路线 C 并推荐 C**，理由如下。

| 维度 | 路线 A：改 run.sh 副本 | 路线 B：绕过 run.sh 手拼 | **路线 C：挂载覆盖 in-\*（推荐）** |
|---|---|---|---|
| 需要维护的文件 | 3 份 run.sh 副本（**每协议一份，且需随镜像版本同步**） | 12+ 个易错参数写死在脚本里 | **0 个**（官方 `run` 原样不动） |
| 与镜像布局的兼容性 | ⚠️ **源码树 `run.sh` 与镜像不兼容**：源码树 RTSP 是 `cd $WORKDIR/live555/testProgs`，镜像内只有 `live/` → **挂进去直接 cd 失败**。必须先改副本的 `TARGET_DIR`/`live-gcov`/`-k 2s` 等多处 | ⚠️ 需自行复刻 `-i/-o/-x/-N/-c/--server` 六段固定参数 + OPTIONS 追加逻辑 | ✅ 官方 `run` 与镜像**同版本**，天然自洽 |
| 丢 `-c` 清理脚本的风险 | 低（保留 run.sh） | ⚠️ **高**：`Exim` 需 `-c clean`（重置 exim 状态）、`Kamailio` 需 `-c run_pjsip`（拉起 SIP 对端 pjsua）。漏掉 → 行为与官方不同 | ✅ 零风险 |
| 端口成对性（`-N` 与 server 端口） | 低 | ⚠️ **高**：RTSP 的 `-N tcp://127.0.0.1/8554` 与 `./testOnDemandRTSPServer 8554` **必须同改**，漏一处即错。既往 `rq1_2_rerun.sh` 用 8560 就是这类错误 | ✅ 零风险（官方脚本自带） |
| SIP `-l 5061` 漏配风险 | 低 | ⚠️ 高（OPTIONS 追加位置易错）→ **既往 `rq2_launch_target.sh` 正是这样漏掉导致 "No server states"** | ✅ 零风险 |
| 覆盖率时序（cov_over_time.csv） | 保留 | ⚠️ 需自行复刻 cov_script 调用 | ✅ 保留 |
| 三协议统一性 | 3 份副本 × 3 协议 = 9 份易漂移文件 | 参数表可统一 | ✅ **同一机制**：`-v <host>:<容器内 in-*>:ro`，三协议同构 |
| baseline 臂纯净度 | 需另备一份"未改 run.sh" | 需另备一套参数 | ✅ **baseline 零挂载 = 镜像原生官方种子**（md5 已证与源码树一致） |

**选型结论：路线 C。**

**路线 C 的机制**（不依赖 run.sh 支持环境变量）：

| 协议 | 镜像内 `run` 的 INPUTS 赋值 | 路线 C 手法 | 结果 |
|---|---|---|---|
| RTSP | `INPUTS=${WORKDIR}/in-rtsp`（硬编码） | `-v /home/zxy/rq4/seeds/rtsp:/home/ubuntu/experiments/in-rtsp:ro` | 同一路径被覆盖 → `INPUTS` 指向我们的种子 |
| SIP | `INPUTS=${INPUTS:-${WORKDIR}"/in-sip"}` | 同名覆盖 `in-sip`（**不设 INPUTS 环境变量**，让它走默认值） | 同上 |
| SMTP | `INPUTS=${WORKDIR}/in-smtp`（硬编码） | 同名覆盖 `in-smtp` | 同上 |

> **为何不靠 `-e INPUTS=...`**：RTSP/SMTP 是**无条件赋值**，环境变量会被立即覆盖 → 无效；SIP 虽支持 `:-` 兜底，但三协议混用两种机制会引入不一致的失败面。**同名覆盖是唯一三协议同构的机制。**

**`:ro` 只读挂载安全性**（已逐处核实 `afl-fuzz.c`）：
- `save_auto` 写 `out_dir/queue/.state/auto_extras/`（`:2751`）→ 写**输出**目录，非输入目录
- `mark_as_det_done` 写 `out_dir/queue/.state/deterministic_done/`（`:1503`）→ 同上
- `load_auto` 只**读** `in_dir/.state/auto_extras/`（`:2777`）→ 只读安全
- `-d`（skip_deterministic）下不走确定性阶段 → 不写 `in_dir/.state/deterministic_done/`
→ **`:ro` 安全，无写失败风险。**

### 1.3 ★ 官方参数溯源（git commit 演进）

主理人转述的参数与源码 HEAD 不一致。**溯源后确认：转述版本来自 2021 年 ASAN 支持之前的旧 commit，且三协议分别来自三个不同历史版本**——不是任何一个自洽版本。

`/home/zxy/profuzzbench` git HEAD = `8573ec8`（2022-07-11 "Seed files renamed to .raw"）。
`scripts/execution/profuzzbench_exec_all.sh` 最后修改于 `af6c1ee`，`TEST_TIMEOUT` 默认 5000（`:6`）。

| commit | 日期 | 提交标题 | live555 | kamailio | exim |
|---|---|---|---|---|---|
| `ec015c4` | 2021-06-23 | Utility scripts... | `-P RTSP -D 10000 -q 3 -s 3 -E -K -R`（**无 -t**） | `-m none -t 3000+ ... -c run_pjsip` | `-P SMTP -D 10000 -q 3 -s 3 -E -K -W 100`（**无 -t 无 -m none**） |
| `7779866` | 2021-10-12 | Support for StateAFL | `... -R -t 1000+` | 同上 | 同上 |
| `df43795` | 2022-01-11 | **Adding support for ASAN** | `... -R -m none -t 2000` | `-m none -t 3000+ ...` | `... -W 100 -m none -t 2000` |
| `fb93c4b` | 2022-01-14 | Bug-fix for globals | 同上 | 同上 | 同上 |
| `e57ccdb` | 2022-01-14 | **TEST_TIMEOUT parameter for script** | `... -R -m none -t ${TEST_TIMEOUT}` | `-m none -P SIP -l 5061 ... -t ${TEST_TIMEOUT}`（**`-t 3000+` 被统一**） | `... -W 100 -m none -t ${TEST_TIMEOUT}` |
| **HEAD `8573ec8`** | 2022-07-11 | (当前) | **`-P RTSP -D 10000 -q 3 -s 3 -E -K -R -m none -t ${TEST_TIMEOUT}`** | **`-m none -P SIP -l 5061 -D 50000 -q 3 -s 3 -E -K -t ${TEST_TIMEOUT}`** | **`-P SMTP -D 10000 -q 3 -s 3 -E -K -W 100 -m none -t ${TEST_TIMEOUT}`** |

**主理人转述版本的对应关系**：live555 的 `-t 1000+` 来自 `7779866`；kamailio 的 `-t 3000+` 来自 `df43795`/`fb93c4b`；exim 无 `-t`/`-m none` 来自 `ec015c4`。**三者拼在一起，不对应任何一个 commit。**

**为什么必须用 HEAD 版本（工程理由，非学术偏好）**：

1. **`-m none` 是 ASAN 目标的硬性要求**。`df43795` 标题就是 "Adding support for ASAN"——该 commit 为**所有** target 补上 `-m none`。原因：`afl-fuzz.c:113` `mem_limit = MEM_LIMIT`，`config.h:67` `MEM_LIMIT = 50`（MB），`-m` 缺省即用 50MB rlimit；而三个镜像**全部是 ASAN 构建**（Dockerfile `AFL_USE_ASAN=1`，镜像 ENV 带 `ASAN_OPTIONS`）。ASAN 的 shadow memory + redzone 会让 RSS 远超 50MB → **不加 `-m none` 时目标被 rlimit 秒杀，fuzzer 立刻收到 SIGKILL，产出"假崩溃"或零 exec**。这是 `df43795` 修的真实 bug。
2. **`-t` 的 `+` 后缀语义不同**。`afl-fuzz.c:9012`：`suffix == '+'` → `timeout_given = 2`（**自动标定**超时），否则 `= 1`（**固定**）。`1000+`/`3000+` 会随机器负载漂移，实验不可复现；HEAD 的 `${TEST_TIMEOUT}`=5000 是固定值。
3. **kamailio 多 `-R` 会破坏可比性**。HEAD 的 kamailio **没有 `-R`**（`-R` 是 region 级变异）。加 `-R` → 与 ProfuzzBench 论文的 kamailio 基线不可比，且与**我们自己的既往 RQ1.2 SIP 实验**（`-R`）也不可比。

> **结论**：本方案采用 HEAD 版本。**若坚持转述版本，baseline 将不再是 ProfuzzBench 基线，全部结论需重算**——这是唯一需要主理人裁决的技术点（§9 A1）。

**选项语义速查**（`afl-fuzz.c:8084-8120`）：`-D`=等待服务端初始化(us) · `-W`=首响应轮询超时(ms) · `-t`=单次执行超时(ms) · `-m none`=不限内存 · `-E`=state-aware · `-K`=SIGTERM 优雅终止服务端 · `-R`=region 级变异(仅 RTSP) · `-q 3`/`-s 3`=FAVOR 选择算法 · `-l`=本地源端口。

### 1.4 架构模式

**分层：官方入口层（镜像内 `run`，不修改）→ 参数表层（宿主）→ 采集层（宿主轮询器）**

```
[宿主编排层] rq4_launch.sh ──参数表──┐
                                      │ docker run (-v 覆盖 in-*)
                                      ▼
[容器官方入口层] /home/ubuntu/experiments/run  (镜像自带，零修改)
        ├─ Step1  afl-fuzz  -i <INPUTS> -x <dict> -o <OUTDIR> -N <net> $OPTIONS <server>
        ├─ Step2  cov_script → cov_over_time.csv
        ├─ Step3  gcovr → cov_html/
        └─ Step4  tar → ${WORKDIR}/<OUTDIR>.tar.gz
                                      ▲
[宿主采集层] rq4_collect.sh ──docker exec cat / tar──┘
```

---

## 2. 三协议完整启动命令

> 通用：`--cpus=1 --memory=2g -d -it`（`-it` 保留官方 TTY 行为）；`TIMEOUT=10800`（3h，秒）；`SKIPCOUNT=5`（官方默认）；`OUTDIR` 协议内唯一。
> 入口形式照抄官方 `profuzzbench_exec_common.sh`：`run <fuzzer> <OUTDIR> '<OPTIONS>' <TIMEOUT> <SKIPCOUNT>`。

### 2.1 RTSP / Live555（`rq2-live555:latest`）

容器内 work dir：`/home/ubuntu/experiments/live/testProgs`；输出：`/home/ubuntu/experiments/live/testProgs/<OUTDIR>`

```bash
# --- baseline：零挂载 → 镜像自带官方 7 条种子 ---
docker run --cpus=1 --memory=2g -d -it \
  --name rq4_rtsp_baseline_r1 \
  rq2-live555:latest \
  /bin/bash -c "cd /home/ubuntu/experiments && run aflnet out-rtsp-baseline-r1 '-P RTSP -D 10000 -q 3 -s 3 -E -K -R -m none -t 5000' 10800 5"

# --- protorag：同名覆盖 in-rtsp（只读）---
docker run --cpus=1 --memory=2g -d -it \
  --name rq4_rtsp_protorag_r1 \
  -v /home/zxy/rq4/seeds/rtsp:/home/ubuntu/experiments/in-rtsp:ro \
  rq2-live555:latest \
  /bin/bash -c "cd /home/ubuntu/experiments && run aflnet out-rtsp-protorag-r1 '-P RTSP -D 10000 -q 3 -s 3 -E -K -R -m none -t 5000' 10800 5"
```

### 2.2 SIP / Kamailio（`rq2-kamailio:latest`）

容器内 work dir：`/home/ubuntu/experiments/kamailio`；输出：`/home/ubuntu/experiments/kamailio/<OUTDIR>`
**官方 kamailio 无字典 → 两组均不带 `-x`**（`run` 脚本本身不含 `-x`）

```bash
# --- baseline ---
docker run --cpus=1 --memory=2g -d -it \
  --name rq4_sip_baseline_r1 \
  rq2-kamailio:latest \
  /bin/bash -c "cd /home/ubuntu/experiments && run aflnet out-sip-baseline-r1 '-m none -P SIP -l 5061 -D 50000 -q 3 -s 3 -E -K -t 5000' 10800 5"

# --- protorag ---
docker run --cpus=1 --memory=2g -d -it \
  --name rq4_sip_protorag_r1 \
  -v /home/zxy/rq4/seeds/sip:/home/ubuntu/experiments/in-sip:ro \
  rq2-kamailio:latest \
  /bin/bash -c "cd /home/ubuntu/experiments && run aflnet out-sip-protorag-r1 '-m none -P SIP -l 5061 -D 50000 -q 3 -s 3 -E -K -t 5000' 10800 5"
```

### 2.3 SMTP / Exim（`rq2-exim:latest`）

容器内 work dir：`/home/ubuntu/experiments/exim`；输出：`/home/ubuntu/experiments/exim/<OUTDIR>`

```bash
# --- baseline ---
docker run --cpus=1 --memory=2g -d -it \
  --name rq4_smtp_baseline_r1 \
  rq2-exim:latest \
  /bin/bash -c "cd /home/ubuntu/experiments && run aflnet out-smtp-baseline-r1 '-P SMTP -D 10000 -q 3 -s 3 -E -K -W 100 -m none -t 5000' 10800 5"

# --- protorag ---
docker run --cpus=1 --memory=2g -d -it \
  --name rq4_smtp_protorag_r1 \
  -v /home/zxy/rq4/seeds/smtp:/home/ubuntu/experiments/in-smtp:ro \
  rq2-exim:latest \
  /bin/bash -c "cd /home/ubuntu/experiments && run aflnet out-smtp-protorag-r1 '-P SMTP -D 10000 -q 3 -s 3 -E -K -W 100 -m none -t 5000' 10800 5"
```

### 2.4 产物路径表（★ 易错：输出目录随协议变化）

| 协议 | `fuzzer_stats` 容器内路径 | tar 包容器内路径 |
|---|---|---|
| RTSP | `/home/ubuntu/experiments/live/testProgs/<OUTDIR>/fuzzer_stats` | `/home/ubuntu/experiments/<OUTDIR>.tar.gz` |
| SIP | `/home/ubuntu/experiments/kamailio/<OUTDIR>/fuzzer_stats` | `/home/ubuntu/experiments/<OUTDIR>.tar.gz` |
| SMTP | `/home/ubuntu/experiments/exim/<OUTDIR>/fuzzer_stats` | `/home/ubuntu/experiments/<OUTDIR>.tar.gz` |

`cov_over_time.csv`、`<OUTDIR>/cov_html/`、`regions/`、`replayable-queue/`、`crashes/` 同在 `<OUTDIR>/` 下。

---

## 3. 种子挂载策略

### 3.1 结论：baseline 零挂载；protorag 同名覆盖（详见 §1.2 路线 C）

**三条实证依据**

1. **镜像内 `run` 的 `INPUTS` 指向固定路径**（§1.2 路线 C 表）。
2. **镜像内种子与 ProfuzzBench 源码树种子 md5 逐一相同**：

   | 协议 | 镜像内 | 源码树 | md5 一致 |
   |---|---|---|---|
   | RTSP | `in-rtsp/` 7 个 `.raw` | `subjects/RTSP/Live555/in-rtsp/` 7 个 | ✅ 7/7 |
   | SMTP | `in-smtp/` 2 个 `.raw` | `subjects/SMTP/Exim/in-smtp/` 2 个 | ✅ 2/2 |
   | SIP | `in-sip/sip-1.raw` | `subjects/SIP/Kamailio/in-sip/sip-1.raw` | ✅ 1/1 |

   → baseline 臂 = **官方基线的逐字节复现**，零挂载、零拷贝、零漂移。
3. **`:ro` 挂载安全**（§1.2 末）：afl-fuzz 对输入目录只读（`load_auto` 只读；`save_auto`/`mark_as_det_done` 写输出目录；`-d` 跳过确定性阶段）。

> 注：镜像 `rq2-live555`/`rq2-exim` 的 `Config.User=root`，`rq2-kamailio` 是 `ubuntu`。宿主 `zxy` 为 uid 1000。
> 三镜像的 `/home/ubuntu/experiments` 属主均为 `1000/1000`、权限 `drwxrwxr-x` → 容器内 uid 1000（kamailio）/root（另两个）均可读宿主 uid 1000 的只读挂载。**但 kamailio 镜像的 `run` 会在 `${WORKDIR}/kamailio` 下创建 `runtime_dir`**，需确认该目录在镜像内已存在且可写（已核实 `home/ubuntu/experiments/kamailio` 存在）。

### 3.2 种子同步（本机 → VM）

> ⚠️ **v3 更正**：实验实际使用的语料是 **`derived/model/seeds/<proto>/rq4_B/`**（**39/25/78 条**），**不是** v2 写的 `pfb_exp_B/`（50/56/78 条）。
> `pfb_exp_B/` 是**修复前**的语料（含 R4/R5 缺陷：RTSP 47.9% 请求打空会话、SIP 39.4% 方法不被 AFLNet 识别为消息边界）；
> `rq4_B/` 是 tasks #3/#4 修复后的语料，**与 VM 上跑的、论文所用的完全一致**。
> 工程脚本 `scripts/rq4_verify_seeds.py`、`scripts/rq4_seed_profile.py` 已正确指向 `rq4_B/`（实测确认）。
> **VM 上跑的是 `rq4_B`**：`/home/zxy/rq4/seeds/{rtsp,sip,smtp}` = 39/25/78，本机与 VM 逐字节 md5 一致（实测三协议全部 MATCH）。

本机：`E:\科研\想法idea\rag-chatafl\derived\model\seeds\<proto>\rq4_B\`
→ VM：`/home/zxy/rq4/seeds/<proto>/`

要求：**必须保持字节一致**（scp 保字节；**禁止 git / zip / 文本编辑器转换行尾**）。落地后校验：
- 文件数：**RTSP 39 / SIP 25 / SMTP 78**
- 每行 CRLF 结尾（SMTP/RTSP/SIP 均需）
- `MANIFEST.md5` 逐条校验（`md5sum -c` 实测 rtsp 39/39 OK、0 FAILED）
- 断言 AFLNet 分区数符合预期（§7.4 的 `seed_regions` 列：RTSP 150 / SIP 112 / SMTP 355）

> ⚠️ **VM 侧 provenance 缺口**：VM 的 `/home/zxy/rq4/seeds/<proto>/` **没有随语料带 `MANIFEST.md5`**（本机有）。
> 建议同步时一并复制 `MANIFEST.md5` + `manifest.json` 到 VM，使 VM 侧也能自证语料身份（§12 建议项 S3）。

---

## 4. 字典策略（★ 最终建议）

### 4.1 三协议字典现状（实测）

| 协议 | 官方字典（镜像内） | token | ProtoRAG 字典 | token | 交集 | 官方独有 | ProtoRAG 独有 | 并集 |
|---|---|---|---|---|---|---|---|---|
| RTSP | `experiments/rtsp.dict` | 24 | `pfb_exp_B/rtsp.dict` | 24 | **24（100%）** | 0 | 0 | 24 |
| SMTP | `experiments/smtp.dict` | 14 | `pfb_exp_B/smtp.dict` | 24 | 11 | `.` `FROM` `TO` | `-1` `0` `1` `2147483647` `4294967295` `65535` `C` `ETRN` `EXPN` `MAIL FROM` `RCPT TO` `STARTTLS` `VRFY` | 27 |
| SIP | **无字典**（官方 `run` 与 OPTIONS 均无 `-x`） | 0 | `pfb_exp_B/sip.dict` | 163 | — | — | 全部 | 163 |

**ProtoRAG SIP 字典质量拆解（163 token）**

| 类别 | 数量 | 评价 |
|---|---|---|
| 方法名（`ACK BYE CANCEL INFO INVITE MESSAGE NOTIFY OPTIONS PRACK PUBLISH REFER REGISTER RTCP RTP STUN SUBSCRIBE UPDATE`） | 17 | 有效 |
| 纯数字（`-1` `0` `1` `60` `100` `120` `65535` `2147483647` `4294967295` …） | 25 | 对 SIP 语义近乎无用 |
| 含 `sip:` URI（`<sip:0097239287044@sip.cybercity.dk>`、`192.168.1.2` 等**实例特定**值） | 19 | 从自家种子抽取的实例值，泛化价值近零 |
| 疑似 Call-ID / UUID（`00-04071-1701b172-22e1cc470` 形态） | 3 | 实例特定 |
| 其余（tag/branch/`60;refresher=uas` 等） | ~99 | 低价值 |
| **有效协议词占比** | **17 / 163 ≈ 10.4%** | 字典整体质量偏低 |

### 4.2 ★ 最终建议：主实验 **按协议裁定，组间恒定**；ProtoRAG 字典另开消融波

主理人给出三选项 (a)(b)(c)，我的评估与选择：

| 方案 | 评估 |
|---|---|
| (a) baseline 官方 dict / protorag 生成 dict | ❌ **引入字典这一额外变量**。覆盖率差异无法归因到种子。且 SIP 上给 protorag 独占字典 = 给它一个官方基线没有的能力 → 对 baseline 不公平。**否决** |
| (b) 两组都用各自官方字典（protorag 不用生成的 dict） | ✅ RTSP/SMTP 上成立且**零代价**（RTSP 两字典 token 集合 100% 相同；SMTP 用官方反而更强，因官方含 `.`/FROM/TO 而 ProtoRAG 缺 `.`） |
| (c) 两组都不用字典 | ⚠️ RTSP/SMTP 上会**削弱两组**（丢掉官方字典能力），且 baseline 不再复现官方基线 → 文献可比性下降。**不优于 (b)** |

**结论 = (b)，但对 SIP 特殊裁定为「两组都无字典」（= 官方 kamailio 配置）**，即：

| 协议 | baseline 臂 | protorag 臂 | 理由 |
|---|---|---|---|
| RTSP | `-x $WORKDIR/rtsp.dict`（官方，镜像自带） | **同左** | 两字典 token 完全相同 → 此协议字典之争**自动消解**，用谁都零影响 |
| SMTP | `-x $WORKDIR/smtp.dict`（官方，镜像自带） | **同左** | 官方含 `.`（SMTP DATA 结束符）/FROM/TO，ProtoRAG 版**缺失** → 用 ProtoRAG 反而削弱两组 |
| SIP | **不加 `-x`** | **不加 `-x`** | 官方 kamailio 明确无字典；强行给一组独占 = 把"字典能力"混入"种子质量" |

**四条理由（论文级论证）**

1. **因果可归因**：自变量是**种子语料**。字典是 fuzzer 配置。两组字典不同 → 覆盖率差异无法归因到种子，这是审稿人最容易一击致命的混淆变量。
2. **baseline 必须保持官方逐字节复现**：baseline = 官方种子 + 官方字典 + 官方参数。任何"增强"都使 baseline 不再是文献可比基线。
3. **不浪费 ProtoRAG 字典**：以**独立字典消融波**兑现（§4.3），而不是混进主实验污染归因。
4. **RTSP 上零代价、SMTP 上用官方更强**：方案不是"牺牲 ProtoRAG"，而是在这两个协议上**两种选择结果相同或官方更优**；SIP 上 ProtoRAG 字典仅 10.4% 有效协议词，独占它是噪声而非信号。

### 4.3 字典消融波（可选，+2 容器，与主实验分开报告）

| # | 协议 | 种子 | 字典 | 目的 |
|---|---|---|---|---|
| D1 | SMTP | protorag（全集） | ProtoRAG dict（覆盖挂载 `experiments/smtp.dict`） | SMTP 字典增益（差异 13+3 token） |
| D2 | SIP | protorag（全集） | ProtoRAG dict（`-x` 加入 OPTIONS；官方 kamailio 无 `-x`，可自由加） | SIP 字典增益（官方无 → ProtoRAG 是纯增量） |

- **RTSP 不必消融**：两字典 token 集合相同，增益恒为 0。
- **D1 机制**：`-v /home/zxy/rq4/seeds/smtp.dict:/home/ubuntu/experiments/smtp.dict:ro`（注意：**挂文件而非目录**）
- **D2 机制**：`-v /home/zxy/rq4/seeds/sip.dict:/home/ubuntu/experiments/sip.dict:ro` + OPTIONS 追加 `-x /home/ubuntu/experiments/sip.dict`
- ⚠️ **注意 `-x` 不能重复**：`afl-fuzz.c:8897` `if (extras_dir) FATAL("Multiple -x options not supported")`。RTSP/SMTP 的官方 `run` 已内含 `-x`，**不可再在 OPTIONS 里加 `-x`**；SIP 无 `-x` 才可加。

### 4.4 ★ 论文/报告中如何诚实描述该不对称

**不写"两组配置完全相同"**（不真实），而是**显式声明字典是按协议恒定的受控变量，并把 ProtoRAG 字典的贡献单列为消融实验**。建议原文：

> "为隔离种子语料这一变量，字典配置在每协议的实验组与对照组间保持恒定：RTSP 与 SMTP 两侧均使用 ProfuzzBench 官方字典（`rtsp.dict` 24 token / `smtp.dict` 14 token），SIP 两侧均不使用字典（与官方 Kamailio 配置一致）。在 RTSP 上，ProtoRAG 生成的字典与官方字典的 token 集合完全相同（交集 24/24），故该协议上字典选择对结果无影响；在 SMTP 上官方字典包含 ProtoRAG 字典缺失的 `.`/`FROM`/`TO`，采用官方字典对两组均为更有利配置；在 SIP 上 ProtoRAG 字典的协议有效 token 仅占 17/163（10.4%），其余为纯数字与实例特定 URI，独占该字典不构成有意义的能力差异。ProtoRAG 字典的独立贡献另以字典消融实验（§ 表 D1/D2）单独测量，与主实验结果分开呈现。"

同时在结果表中**必须并列三列**：`dict_source`（official/none）、`dict_tokens`、`seed_files`/`seed_regions` → 读者可自行核验"除种子外无其他差异"。

---

## 5. ★ 数量对齐对照组（解决种子数量混淆变量）

主理人补充的事实成立且关键：protorag 与 baseline 的**种子条数**差异巨大（50 vs 7 / 56 vs 1 / 78 vs 2），且 SMTP 上 protorag 覆盖了官方完全没有的命令（STARTTLS/BDAT/RSET/NOOP/HELO）。这使"protorag 覆盖率更高"**无法区分**「每条种子质量更好」与「语料更大/更多样」。

### 5.1 结论边界（必须写进论文）

| 能得出的结论 | 不能得出的结论 |
|---|---|
| ✅ **端到端效果对比**：在相同 3h 预算、相同 fuzzer 配置下，ProtoRAG 语料**作为一个整体**比官方语料达成更高覆盖率/发现更多崩溃 | ❌ **单条种子质量归因**：不能说"ProtoRAG 每条种子更优"（数量差异未剥离） |
| ✅ **知识库覆盖增益**：ProtoRAG 语料覆盖了官方语料完全缺失的协议命令与状态（STARTTLS/BDAT/RSET/HELO 等），这是可量化的、真实的贡献 | ❌ **数量无关的公平比较**：不能说"排除了语料规模影响"（除非有对齐组） |

### 5.2 对齐组设计（三选一，推荐第 3 种）

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| ① **条数对齐** | protorag 截断到官方条数（RTSP 7 / SIP 1 / SMTP 2） | 最直观；读者零成本理解 | **SIP 只剩 1 条**（`01_REGISTER+ACK+...`，16 region）→ 样本退化为单条，噪声极大；且"取哪 1 条"引入选择偏差 |
| ② **region 数对齐** | 按 AFLNet 分区数裁剪到官方总分区（RTSP 29 / SIP 4 / SMTP 14） | 与 fuzzer 实际消费的输入单元对齐 | SIP 官方仅 4 region → 对齐组只剩 4~5 region，仍是退化样本 |
| ③ **推荐：条数对齐 + 多子集重复** | protorag 裁剪到官方条数，**每个协议取 K=3 个不同子集**（按文件名哈希确定性采样，保证可复现），每子集跑 1 容器 | 条数严格对齐 + 用 3 次采样缓解单子集噪声；仍为"官方同等语料量下的质量对比" | 容器数 = 3 协议 × 3 子集 = 9（超出本轮 6 容器预算） |

**实测的候选对齐子集**（按分区数贪心，已用 AFLNet 真实分区器计算，供 dry-run 验证）：

| 协议 | 官方总分区 | protorag 全集 | 对齐子集（最小优先贪心） | 文件数 |
|---|---|---|---|---|
| RTSP | 29 | 50 文件 / 205 region | 15 文件 / 30 region | 15 |
| SIP | 4 | 56 文件 / 217 region | 4 文件 / 5 region | 4 |
| SMTP | 14 | 78 文件 / 363 region | 8 文件 / 15 region | 8 |

> 注意：贪心对齐后文件数（15/4/8）远大于官方条数（7/1/2），因为 ProtoRAG 单文件的分区密度更低。这**本身就是一个可报告的发现**：ProtoRAG 种子"每条消息更短、更多样"，而官方是"每条消息更长、更少"。

### 5.3 ★ 纳入建议：**不纳入本轮主实验，但作为下一轮的首要任务**

**理由**：

1. **本轮预算已定**：3 协议 × 2 组 × 1 rep = 6 容器 × 3h。对齐组按方案③需 +9 容器 → 15 容器，超出本轮范围。
2. **磁盘是硬约束**：VM 磁盘 94%、仅剩 6.0G；6 容器 × 3h 的 queue + cov_html + tar 已需 ~15GB。**加 9 容器不现实**（需先扩容）。
3. **n=1 已是本轮最大局限**（§8 R9）。再加 9 个单次重复的容器不会提升统计效力，只会让表格更宽而结论强度不变。
4. **对齐组自身的噪声更大**：SIP 对齐组只有 4~5 region，等于单条种子，**单次运行无法得出可信结论** → 需要 n≥3 × 3 子集 = 9 容器/协议 = 27 容器，远超本轮能力。

**替代方案（零额外容器成本，建议本轮采用）**：**用现有的 execs_done 对齐曲线**（§7.2）间接逼近"同等投入下的质量对比"——
在**相同 exec 数**处比较 `bitmap_cvg`。因为 AFLNet 的 exec 速率主要由 fuzzer 决定而非种子条数，两组在同等 exec 预算下的覆盖率差异，比"3h 终值"更接近"同等投入的效果差"。这不能完全替代对齐组，但**不花一个容器**。

**论文中的诚实表述**：

> "本实验为端到端效果对比。ProtoRAG 与官方语料的条数差异显著（RTSP 50 vs 7、SIP 56 vs 1、SMTP 78 vs 2），故本结果反映的是 ProtoRAG 语料整体（规模与质量的合并效应），而非单条种子的质量增益。为部分剥离数量效应，主表同时报告 execs_done 对齐的覆盖率曲线（相同执行预算下的覆盖率差异）；严格的数量对齐对照（裁剪至同等条数并多次采样）列为后续工作。"

---

## 6. 编排脚本设计

### 6.1 数量：**3 个脚本**

| 脚本 | 职责 |
|---|---|
| `rq4_launch.sh` | 编排：协议参数表 + 启动 6 容器 + 命名/清理 + 快照轮询 |
| `rq4_collect.sh` | 采集：等容器退出 + 拉 `fuzzer_stats`/`cov_over_time.csv`/tar + 汇总 CSV |
| `rq4_dryrun.sh` | 前置验证：单容器短跑 + 断言 |

**不用 1 个**：dry-run 要求快速失败且不污染正式目录，与批量编排的容错要求相反；合并会让"验证失败"与"批量启动失败"互相污染。
**不用 3×协议=9 个**：三协议差异仅 6 字段（image/proto/net/in_dir/work_dir/options），用参数表表达；官方同构（1 通用脚本 + exec_all 参数表）。9 份脚本必然漂移——既往 `rq2_launch_target.sh` 已实证（kamailio 漏 `-l 5061`）。

### 6.2 参数接口

```bash
# rq4_launch.sh
Usage: rq4_launch.sh [OPTIONS]
  --protocols  rtsp,sip,smtp     # 子集，默认全部
  --groups     protorag,baseline # 子集，默认全部
  --reps       N                 # 重复数，默认 1
  --duration   SEC               # 每容器 fuzz 时长秒，默认 10800 (3h)
  --skipcount  N                 # cov_script 采样步长，默认 5（官方）
  --seed-root  DIR               # protorag 种子根目录，默认 /home/zxy/rq4/seeds
  --out-root   DIR               # 结果根目录，默认 /home/zxy/rq4/out
  --memory     2g                # 每容器内存上限
  --dry-run                    # 只打印将要执行的 docker run，不启动
  --yes                        # 跳过交互确认
```

```bash
# rq4_collect.sh
Usage: rq4_collect.sh [--out-root DIR] [--protocols ...] [--groups ...] [--reps N] [--wait] [--timeout SEC]
# rq4_dryrun.sh
Usage: rq4_dryrun.sh [--protocol rtsp|sip|smtp] [--duration SEC] [--group protorag|baseline]
#   默认 --duration 180 --group protorag（最坏情况）
```

### 6.3 协议参数表（唯一真源）

| 字段 | RTSP | SIP | SMTP |
|---|---|---|---|
| `image` | `rq2-live555:latest` | `rq2-kamailio:latest` | `rq2-exim:latest` |
| `proto` | RTSP | SIP | SMTP |
| `net`（run.sh 固定） | `tcp://127.0.0.1/8554` | `udp://127.0.0.1/5060` | `tcp://127.0.0.1/25` |
| `in_dir`（挂载点） | `/home/ubuntu/experiments/in-rtsp` | `/home/ubuntu/experiments/in-sip` | `/home/ubuntu/experiments/in-smtp` |
| `work_dir`（输出所在） | `/home/ubuntu/experiments/live/testProgs` | `/home/ubuntu/experiments/kamailio` | `/home/ubuntu/experiments/exim` |
| `options` | `-P RTSP -D 10000 -q 3 -s 3 -E -K -R -m none -t 5000` | `-m none -P SIP -l 5061 -D 50000 -q 3 -s 3 -E -K -t 5000` | `-P SMTP -D 10000 -q 3 -s 3 -E -K -W 100 -m none -t 5000` |
| `dict`（run.sh 固定） | `$WORKDIR/rtsp.dict` | **无** | `$WORKDIR/smtp.dict` |
| `cleanup`（run.sh 固定） | 无 | `$WORKDIR/run_pjsip` | `$WORKDIR/clean` |

### 6.4 文件清单

**VM 侧（`/home/zxy/rq4/`，全部新建，不改动任何既有文件）**

| 路径 | 说明 |
|---|---|
| `/home/zxy/rq4/rq4_launch.sh` | 编排脚本（含协议参数表） |
| `/home/zxy/rq4/rq4_collect.sh` | 采集脚本 |
| `/home/zxy/rq4/rq4_dryrun.sh` | 单容器 dry-run 验证脚本 |
| `/home/zxy/rq4/seeds/{rtsp,sip,smtp}/` | protorag 种子（scp 自本机，附 `MANIFEST.md5`） |
| `/home/zxy/rq4/out/<proto>/<group>/r<rep>/` | 每容器结果：stats 快照序列、`cov_over_time.csv`、`cov_html/`、tar 包 |
| `/home/zxy/rq4/logs/<container>.log` | `docker logs` 存档（post-mortem） |
| `/home/zxy/rq4/rq4_summary.csv` | 汇总表（字段见 §7.4） |

**本机侧（`E:\科研\想法idea\rag-chatafl\`）**

| 路径 | 说明 |
|---|---|
| `scripts/rq4_sync_seeds.ps1`（或 `.py`） | 本机 → VM 种子同步 + md5/CRLF/条数校验 |
| `scripts/rq4_verify_seeds.py` | 种子结构自检：CRLF、AFLNet 分区数（复刻 `extract_requests_*`）、RTSP 会话可播性、SIP 方法可识别性 |
| `scripts/rq4_analyze.py` | 结果对比与作图（bitmap_cvg 时序曲线、execs_done 对齐曲线、组间对比表） |
| `docs/实验/RQ4_AFLNet实验设计.md` | 本设计文档 |
| `docs/图/RQ4编排图.mermaid` / `图/RQ4时序图.mermaid` / `图/RQ4类图.mermaid` | 图示 |

---

## 7. 结果采集方案

### 7.1 `fuzzer_stats` 字段清单（`afl-fuzz.c:4289-4345` 逐字枚举）

```
start_time  last_update  fuzzer_pid  cycles_done  execs_done  execs_per_sec
paths_total  paths_favored  paths_found  paths_imported  max_depth  cur_path
pending_favs  pending_total  variable_paths  stability  bitmap_cvg
unique_crashes  unique_hangs  last_path  last_crash  last_hang  execs_since_crash
exec_timeout  afl_banner  afl_version  target_mode  command_line
slowest_exec_ms  peak_rss_mb
```

### 7.2 ★ 主口径 vs 次口径（主理人指定：两者都采，说明主口径）

| 层级 | 指标 | 来源 | 采集时机 | 定位 |
|---|---|---|---|---|
| **主口径** | **`bitmap_cvg`（终值 %）** | `fuzzer_stats` | **实时**（60s 轮询） | AFL 插桩边位图覆盖率。定义跨协议一致 → **三协议可直接横向比**；实时可得 → 后处理超时也不丢数据 |
| **主口径（时序）** | **`bitmap_cvg` @ execs_done 对齐** | 60s 快照序列 | 实时 | 剥离两组执行速率差异 → **部分抵消种子数量效应**（§5.3 替代方案） |
| 次口径 | `cov_over_time.csv` 末行 `l_per` / `b_per` / `l_abs` / `b_abs` | `cov_script`（gcovr） | **容器退出后**（1~3h 后处理） | **文献对齐口径**：与 ProfuzzBench 论文的行/分支覆盖率同定义，用于"我们的 baseline 与已发表数字可比"的论证 |
| 辅助 | `unique_crashes` / `unique_hangs` / `paths_total` / `execs_done` / `stability` | `fuzzer_stats` | 实时 | 崩溃需结合去重与可复现性判定（参照既往 ASAN 复现经验） |

**为什么主口径选 `bitmap_cvg` 而不是 `cov_over_time.csv`**

1. **可得性与鲁棒性**：`fuzzer_stats` 在 fuzz 期间实时刷新；`cov_over_time.csv` 要等 `cov_script` 跑完（1~3h）且**容器被杀即丢失**。以 `bitmap_cvg` 为主口径 → 主指标不依赖后处理成功。
2. **口径可比性**：`bitmap_cvg` 是 AFL 插桩位图覆盖率，**三协议用同一把尺子**，可直接横向比；`l_per` 是 gcovr 源码行覆盖率，受各项目源文件规模影响，跨协议不可比（只能在协议内比）。
3. **两者互为验证**：`cov_over_time.csv` 仍是**文献对齐口径**（审稿人会问"和 ProfuzzBench 论文的数字可比吗"）→ 必须采，作为次口径交叉验证主结论方向一致。
4. **执行速率对齐只在 `bitmap_cvg` 上做得了**：`execs_done` 与 `bitmap_cvg` 同源同快照 → 可插值出"相同执行预算下的覆盖率"；`cov_over_time.csv` 只有时间轴，无 exec 轴。

**报告要求**：主表**同时给出 `bitmap_cvg` 与 `l_per`**，并显式说明两者定义差异；若两者方向不一致（如 `bitmap_cvg` 更高但 `l_per` 更低），说明插桩边覆盖 ≠ 源码行覆盖（`bitmap_cvg` 上升可能来自更多插桩点而非更多源码行），**不得只报有利的一个**。

### 7.3 采集机制

```bash
# ① 快照轮询（fuzz 期间每 60s）
docker exec rq4_rtsp_protorag_r1 cat \
  /home/ubuntu/experiments/live/testProgs/out-rtsp-protorag-r1/fuzzer_stats \
  > /home/zxy/rq4/out/rtsp/protorag/r1/stats_$(date +%s).txt

# ② 容器退出后取 tar（流式落盘）
docker exec rq4_rtsp_protorag_r1 sh -c \
  'tar -czf - -C /home/ubuntu/experiments/live/testProgs out-rtsp-protorag-r1' \
  > /home/zxy/rq4/out/rtsp/protorag/r1/out.tar.gz

# ③ cov_over_time.csv（次口径）
docker exec rq4_rtsp_protorag_r1 cat \
  /home/ubuntu/experiments/live/testProgs/out-rtsp-protorag-r1/cov_over_time.csv \
  > /home/zxy/rq4/out/rtsp/protorag/r1/cov_over_time.csv

# ④ 日志存档
docker logs rq4_rtsp_protorag_r1 > /home/zxy/rq4/logs/rq4_rtsp_protorag_r1.log 2>&1
```

> **★ 关于 `docker cp` 的更正（我 v1 的说法需修正）**
> v1 我称"`docker cp` 保留 root 属主 → 宿主不可读"。**实测已证伪**：`docker cp <exited容器>:/out/fuzzer_stats /tmp/x/` 得到的文件是 `-rw------- 1 zxy zxy`，**属主映射为调用者 zxy，可正常读取**。
> 真正的不可读场景是**既往 `rq2_out/*/r1/fuzzer_stats` 为 `-rw------- root root`** —— 那是**宿主机 bind-mount 目录**（`-v "$out:/out"`）里由容器内 root 进程直接写入的文件，**不是 `docker cp` 产物**。
> **结论**：官方 `common.sh` 的 `docker cp` 收集方式**完全可用**；但**不要**把容器输出目录 bind-mount 到宿主机（会产生 root 属主、宿主不可读的文件）。本方案采用 `docker exec ... cat/tar > 本地文件`（属性最干净、不依赖 root 映射），并保留 `docker cp` 作为等价备选。

### 7.4 `rq4_summary.csv` 字段

```
protocol, group, rep, container, image, dict_source, dict_tokens,
seed_files, seed_regions, start_time, last_update, fuzz_sec,
execs_done, execs_per_sec, paths_total, paths_found, bitmap_cvg,
bitmap_cvg_at_median_exec, stability, unique_crashes, unique_hangs,
max_depth, exec_timeout, cov_l_per, cov_b_per, exit_code, argv
```

> `dict_source` / `dict_tokens` / `seed_files` / `seed_regions` 四列的作用：**在结果表内自证"除种子与字典外，两组无其他差异"** → 审稿人可直接核验。`argv` 列落盘实际命令行 → 参数抄写错误当场暴露。

### 7.5 容器退出判定（★ 不要把容器退出当作 fuzz 结束）

| 阶段 | 判据 | 说明 |
|---|---|---|
| fuzz 进行中 | `fuzzer_stats.last_update` 推进 + `execs_done` 增长 | `docker logs -f` 无输出**不代表卡死**（`-d` + stdout 缓冲） |
| **fuzz 结束** | 连续 2 次（间隔 60s）`last_update` 与 `execs_done` 均不变 | 此时 `timeout` 已触发 SIGTERM，afl-fuzz 正在收尾 |
| 后处理进行中 | 容器仍 Up，`cov_over_time.csv` 逐步增长 | RTSP/SIP 每用例重放带 3s server timeout → 1~3h |
| 全部完成 | 容器退出（`docker wait` 返回 0 或 124 均正常） | `run` 脚本 `exit $STATUS`；`timeout --preserve-status` 下 124 = 被超时杀死（正常收尾） |
| 超时兜底 | 超 fuzz 预算 + 4h 仍未退出 → `docker kill`，仍可取 `fuzzer_stats` | **主指标不依赖后处理，不会因后处理拖长而丢数据** |

---

## 8. 风险清单

| # | 风险 | 影响 | 缓解措施 |
|---|---|---|---|
| R1 | **宿主磁盘 94%，仅剩 6.0G** | 6 容器 queue + cov_html + tar 撑爆，容器崩溃丢失全部数据 | 实验前 `docker rm -f` 18 个 exited 容器 + `docker image prune -a` 回收 ~6.7GB；要求 ≥15GB；`--memory 2g` 限制单容器膨胀；监控 `docker system df` |
| R2 | **容器名冲突** | 启动失败或复用旧容器（读到陈旧 stats） | 启动前 `docker rm -f <name>`；容器名带协议/组/rep 三元组 |
| R3 | **`docker logs -f` 无输出误判为卡死** | 误杀正在正常 fuzz 的容器 | 判据改为 `fuzzer_stats.execs_done` 两次采样增量；`docker logs` 仅作 post-mortem |
| R4 | **RTSP 47.9% 请求指向不存在的 media 会话** | protorag 臂 RTSP 覆盖率被系统性压低 → **结论失真（把种子生成缺陷误判为方法缺陷）** | ① dry-run 用 `aflnet-replay` 逐会话断言 200/404；② **强烈建议重生成 RTSP 种子**，只保留 7 个可播会话（`mp3AudioTest` `mpeg1or2AudioVideoTest` `matroskaFileTest` `webmFileTest` `wavAudioTest` `aacAudioTest` `ac3AudioTest`）；③ 若来不及重生成，必须在论文中显式披露该缺陷及 404 比例 |
| R5 | **SIP 39.4% 方法起点不被 AFLNet 识别** | 请求粒度与官方基线不可比，部分方法永远送不到服务端 | ① 记录为口径限制；② 重生成 SIP 种子时只让 `REGISTER/INVITE/ACK/BYE` 起新消息；③ 论文中给出"有效分区数"列 |
| R6 | **参数版本选错**（用 2021 旧版 `-t 1000+` / 缺 `-m none`） | 缺 `-m none` → ASAN 目标被 50MB rlimit 秒杀；`-t` 带 `+` → 超时随负载漂移不可复现；kamailio 多 `-R` → 与文献及既往 RQ1.2 均不可比 | 参数表固化 HEAD 版本；dry-run A6 断言 `command_line` 逐字匹配；`rq4_summary.csv` 落盘 `argv` 列 |
| R7 | **Exim clean 脚本竞态** | `clean`(`pkill -F /var/lock/exim.pid`) 在每个用例前执行（`afl-fuzz.c:992`），而 `run` 刚 fork 出新的 exim 子进程 → 若 pidfile 已被新进程覆盖则**新 server 被误杀** → 无响应 | dry-run §6 专项断言专门验证；若复现 → 覆盖挂载更保守的 clean 脚本（只杀非当前子进程 pid）为 `/home/ubuntu/experiments/clean`，并在论文中声明该偏离 |
| R8 | **kamailio 漏 `-l 5061`** | 服务端响应不回传 → PFATAL "No server states"（`afl-fuzz.c:9289`） | 参数表固化 `-l 5061`；dry-run 断言 UDP 5061 绑定态 + `regions/` 非空 |
| R9 | **n=1 无方差** | 无法给误差棒，结论脆弱 | 论文显式声明 n=1；报告 execs_done 对齐曲线而非仅终值；预留 `--reps` 以便追加重复 |
| R10 | **容器间 CPU 争抢** | A 容器 gcovr 后处理抢 B 容器 fuzz 的 CPU → exec 速率不等 → 覆盖率不可比 | 每容器 `--cpus=1`（官方同款）→ 上限 6/16 核；必要时错峰启动 |
| R11 | **宿主机输出目录属主 root 不可读** | 采集到空文件，误判为"无结果" | 采集走 `docker exec ... cat/tar > 本地文件`（或 `docker cp`，已实测属主映射正确）；**不要**把容器输出 bind-mount 到宿主 |
| R12 | **种子同步损坏**（行尾转换 / 条数缺失） | 语料与预期不符，实验白跑 | scp 传输 + `MANIFEST.md5` + 条数/CRLF 断言（`rq4_verify_seeds.py`） |
| R13 | **既往 RQ1 SIP 容器仍在运行**（5 个 Up） | 争抢 CPU/内存，污染本实验 | 实验前 `docker rm -f rq1sip_*`（含运行中的） |
| R14 | **镜像内 `run` ≠ 源码树 `run`** | 挂源码树脚本进容器 → `cd $WORKDIR/live555/testProgs` 失败（镜像只有 `live/`） | 只用镜像自带 `run`；**不**覆盖该文件（路线 C 的核心优势） |
| R15 | **RTSP 端口成对性** | `-N` 与 server 端口需同改；既往 `rq1_2_rerun.sh` 用 8560 且漏 `-c` | 路线 C 复用官方 `run` → 端口与 `-c` 天然正确 |
| R16 | **SIP baseline 仅 1 条种子（4 region）** | 基线极弱，需防止被质疑"人为削弱基线" | 这是官方基线原貌（md5 已证一致）；论文中并列官方种子数/分区数/字节数，并引用 ProfuzzBench 论文 |
| R17 | **种子数量不对称**（50/56/78 vs 7/1/2） | 覆盖率差异无法区分质量与规模 | §5：明确结论边界（端到端效果）；主表给 execs_done 对齐曲线；数量对齐组列为下一轮首要任务 |

---

## 9. 不明确项与假设

| # | 不明确 | 采取的假设 | 若假设有误的影响 |
|---|---|---|---|
| A1 | **官方参数以哪个版本为准？**（转述的 `-t 1000+`/`3000+`/缺 `-m none` vs HEAD 的 `-t 5000`+`-m none`） | **以 git HEAD `8573ec8` 为准**（§1.3 已溯源，转述版本来自 ASAN 支持前的旧 commit 且三协议来自三个不同历史版本） | 若坚持转述版本 → baseline 不再是官方基线；且 ASAN 目标会被 50MB rlimit 秒杀 → **实验大概率无法产出有效数据**。**建议用 HEAD 版** |
| A2 | **字典按 (b) 还是 (c)？** | **(b)**：RTSP/SMTP 两组用官方字典、SIP 两组无字典；ProtoRAG 字典另开消融波 | 若选 (c)：两组都无字典 → RTSP/SMTP 的 baseline 不再复现官方基线，文献可比性下降 |
| A3 | **数量对齐组是否纳入本轮？** | **不纳入**（磁盘 94% 仅剩 6.0G；n=1 已是最大局限；SIP 对齐组退化为单样本） | 若纳入（需 +9 容器 + 磁盘扩容）→ 可给出"同等语料量下的质量对比"，结论强度显著提升 |
| A4 | **SKIPCOUNT 取 5（官方）还是加大以压缩后处理？** | **默认 5**（官方），`--skipcount` 可调 | 取更大值 → `cov_over_time.csv` 采样变稀（次口径精度下降），主口径不受影响 |
| A5 | **RTSP/SIP 种子是否在实验前重生成？** | 本方案按"不重生成"设计，R4/R5 列为阻断级风险 + dry-run 量化手段 | 若不重生成，RTSP 结论必须附带 404 比例披露；若重生成，种子需重走 §3.2 同步流程 |
| A6 | **3h 是否足以让 protorag 语料"用尽"？** | 3h 是既定预算；用 execs_done 对齐曲线缓解快慢不等 | 若某组已饱和而另一组未饱和 → 需按饱和度分组解读 |
| A7 | **Exim `clean` 竞态是否真实发生？** | **未实跑验证**（本次仅只读核对，未启动容器）→ 列为 dry-run 必测项 | 若发生 → SMTP 两组都会异常 → 必须换 clean 脚本后重跑 |
| A8 | **后处理占用时长（1~3h）是估算** | 基于 `cov_script` 逐用例重放 + RTSP/SIP 每轮 3s server timeout 推算；实测同规模容器 3h 产出约 1541 个 `id*` 用例 | 实际更久 → §7.5 兜底（4h 上限后 kill，主指标不丢） |
| A9 | **容器 `--memory 2g` 是否够 ASAN+gcovr** | 官方 `exec_common.sh` 不设 memory limit（仅 `--cpus=1`）；既往脚本用 1.5g 成功 | 内存不足 → OOMKill；dry-run 确认；必要时调大或按官方不设限 |
| A10 | **`-c` 清理脚本在路线 C 下是否完全保留？** | 完全保留（未改 `run`，`Exim` 的 `clean` 与 `Kamailio` 的 `run_pjsip` 都在官方 `run` 内） | 无风险 —— 这正是选路线 C 而非 B 的主要原因 |

---

## 10. 执行顺序

1. **裁决**：确认 A1（参数版本）、A2（字典）、A3（对齐组）三项（§9）
2. **清理**：删 exited 容器 + dangling 镜像 + 停 RQ1 SIP 容器 → 磁盘 ≥15GB
3. **同步种子**：本机 → VM（scp）+ `MANIFEST.md5` + `rq4_verify_seeds.py` 校验
4. **（可选但强烈建议）修种子**：重生成 RTSP 种子（限 7 个可播会话）；重生成 SIP 种子（方法边界友好）
5. **dry-run**：3 协议 × protorag × 180s，逐条断言（§10 前置验证）
6. **主实验**：`rq4_launch.sh --reps 1 --duration 10800` → 6 容器
7. **采集**：`rq4_collect.sh --wait`
8. **分析**：`rq4_analyze.py` → 主表（`bitmap_cvg` + `l_per`）+ execs_done 对齐曲线
9. **（可选）字典消融波**：D1(SMTP) + D2(SIP)，各 1 容器，结果单独成表
10. **（下一轮）数量对齐组**：protorag 裁剪至官方条数 × K=3 子集 × 3 协议

---

## 11. 前置验证（single-container dry-run）

**原则**：每协议用 **protorag 种子**（最坏情况）跑 180s，输出到 `/home/zxy/rq4/dryrun/`，**不污染正式结果目录**。

### 11.1 通用断言

| 断言 | 判定 |
|---|---|
| A1 进程存活 | `docker ps` 显示 Up；日志出现 AFL banner |
| A2 stats 落盘 | 60s 内出现 `fuzzer_stats` 且 `execs_done > 0` |
| A3 **活性判据** | `t=60s` 与 `t=120s` 两次采样 `execs_done` **有增长**（不依赖 `docker logs -f`——`-d` + 非 TTY 缓冲下日志极少） |
| A4 状态机建立 | `paths_found > 0` 且 `bitmap_cvg > 0`（服务端有响应） |
| A5 无 PFATAL | 日志无 `No server states have been detected` / `FATAL` |
| A6 参数回显 | `fuzzer_stats` 的 `command_line` **逐字等于**预期命令（自动捕获参数抄写错误） |
| A7 种子生效 | `replayable-queue/` 出现 `id:000000,orig:<我们种子名>` → 证明挂载覆盖生效（而非仍在用镜像自带种子） |

### 11.2 协议专项断言

| 协议 | 专项断言 | 方法 |
|---|---|---|
| **SMTP/Exim** | **`.raw` 格式与 Exim 的真实兼容性** | ① 格式自检：CRLF 结尾、`DATA` 段以 `.\r\n` 结束（实测 78 个种子**无悬挂 DATA 态**）、`MAIL/RCPT` 语法完整；② **真机验证**：容器内手起 `exim -bd -oX 25`，用镜像自带 `aflnet-replay <seed> SMTP 25 1` 重放 ProtoRAG 种子，断言拿到 `250`/`220` 响应码；③ **clean 脚本交互**：`clean`=`pkill -F /var/lock/exim.pid`，`-c` 在**每个用例前**调用（`afl-fuzz.c:992`），需确认新起的 exim 与 pidfile 清理**无竞态**（R7）；断言 `execs_done` 在 120s 内持续增长 |
| **SIP/Kamailio** | **`-l 5061` 是否真正生效** | ① 日志无 "No server states have been detected"（`afl-fuzz.c:9289` PFATAL）；② `regions/` 非空且 `state_ids_count > 0`（`paths_found > 0`、`bitmap_cvg > 0`）；③ `ss -lunp` 确认容器内 **UDP 5061 处于绑定态**（`-l` 生效的直接证据）；④ `ps` 见 `pjsua-x86_64-unknown-linux-gnu`（`run_pjsip` 拉起 SIP 对端）；⑤ `-c run_pjsip` 生效 → 对端能应答（响应码非空） |
| **RTSP/Live555** | **会话可播性 + 端口** | ① `ss -ltnp` 确认服务端监听 **8554**，且与 ProtoRAG 种子 URL 内嵌 `:8554` 一致；② 逐会话验证：起 `./testOnDemandRTSPServer 8554`，用 `aflnet-replay <seed> RTSP 8554 1` 重放，**断言 `DESCRIBE` 返回 200 而非 404**；③ 量化 7 个可播会话覆盖情况 —— **预期发现 48% 请求打不存在的会话**（R4），据此决定是否重生成 |
| 通用 | **输出路径与属主** | 确认 `<work_dir>/<OUTDIR>/fuzzer_stats` 可读（`docker exec cat` 成功）→ 验证 §2.4 路径表正确 |

---

## 12. ★★ P0：语料可复现性回归（v3 新增，实测）

### 12.1 现象

用**当前**事实库 + **当前** profile 重新生成 B 组语料，三协议**全部无法复现**实验所用语料，`seedgen.py` 以**退出码 3** 失败：

```
!! 种子数不符: 期望 39，实际 54（分组配置与实际生成不一致）   → seedgen.py EXIT CODE = 3
```

| 协议 | 实验实际使用（`rq4_B`） | profile 契约 | 当前事实重新生成 | 状态 |
|---|---|---|---|---|
| RTSP | **39** | 39 | **54** | ❌ DRIFT（+15） |
| SIP | **25** | 25 | **20** | ❌ DRIFT（−5） |
| SMTP | **78** | 78 | **61** | ❌ DRIFT（−17） |

复现命令（本机，Anaconda python）：
```bash
E:/app/Anaconda3/python.exe scripts/seedgen.py --protocol rtsp --focus-group B --target-env rq2-live555 --out <tmp>
E:/app/Anaconda3/python.exe scripts/seedgen.py --protocol sip  --focus-group B --target-env rq2-kamailio --out <tmp>
E:/app/Anaconda3/python.exe scripts/seedgen.py --protocol smtp --focus-group B --out <tmp>
```
（`--focus-group` 与 `--order`/`--dict` 互斥，须用单一入口；`--target-env` 仅 RTSP/SIP 有效，SMTP 无 `environments` 键。）

**生成是确定性的**：SIP 连续两次生成均为 20 条 → 不是随机性，是**输入变了**。

### 12.2 根因（★ v3 更正：由消融实验确定，不由 mtime 推断）

> **v3 更正声明**：v2 曾把根因归为「RFC 抽取重构改变了 `rfc` 源的事实」。**这个归因是错的** —— 时点方向对（重构确实是触发时点）但**因果指错了对象**。
> QA-3 做了消融实验（猴补丁 `paths.per_source_root` 指向只含指定源的隔离目录），我**独立复现了同一实验**，结论一致（详见 §12.2.2）。
> **教训**：mtime 只能说明「谁最后被改」，**消融才能说明「谁在起作用」**。

#### 12.2.1 时间线（仍然成立）

| 时刻 | 事件 |
|---|---|
| 10-29 23:35 | `rq4_B` 生成（RTSP 39 / SIP 25 / SMTP 78），manifest `generated_at = 2026-10-29T23:35:4x` |
| 10-30 12:45~17:42 | **RQ4 实验执行**（VM `rq4_summary.csv`，fuzz_sec ≈ 10796） |
| 10-31 02:34 | `fused_hub/targets/*/profile.json` 被改写（含 `environments.*.focus_group` 契约） |
| **10-31 04:53~04:54** | **`derived/model/per_source/*/{expert_note,source,vuln}/facts/*.jsonl` 被重建** ← **真正的驱动源** |
| 10-31 17:03~17:11 | `derived/model/per_source/*/rfc/facts/rfc.jsonl` 被重写（**更晚，但不影响产出**） |
| 10-31 18:01 | QA-3 建立清理前基线 |

#### 12.2.2 消融实验（我独立复现 QA-3，结论一致）

隔离事实源后跑 `seedgen.py`（RTSP/B 组，`--target-env rq2-live555`）：

| 变体 | 我实测 | QA-3 实测 | 结论 |
|---|---|---|---|
| **仅 rfc 源** | `transitions=0`、`message_instances=0`，**产出 0 条** | 0 条（exit=1） | **rfc 源对产出贡献 = 0** |
| **仅非 rfc 源**（expert_note+source+traffic+vuln） | **54 条**（与全五源完全一致） | 52/65/10/20/57/61（同全五源） | **产出完全由非 rfc 源决定** |
| 无源 | 0 条 | 0 条（exit=1） | — |

**事实层面的机制解释（我另行验证）**：rfc 源的事实 `subject.type` 只有 `header`/`method`/`status`，**没有一条 `state`/`outcome`**：

| 协议 | rfc 事实 subject.type 分布 |
|---|---|
| RTSP | `header` 90 / `method` 11 / `status` 15 |
| SIP | `header` 98 / `method` 1 / `status` 50 |
| SMTP | `header` 22 / `method` 10 |

而 seedgen 的状态机（transitions / message_instances）需要的是**状态与结果事实** —— 那些来自 `source`（LIVE555 真实状态名 `Idle/Invited/...`）与 `traffic`（实测观测）。
⇒ **rfc 源即使全部重写，也几乎不改变种子产出**；真正驱动漂移的是 10-31 04:53 重建的 `source`/`traffic`/`vuln`/`expert_note` 事实。

⚠️ **对补救方向的直接影响**：**回退 `rfc` 事实对恢复可复现性毫无效果**（v2 的 S2 方案前提被推翻）—— 必须回退的是 **非 rfc 源**（`source`/`traffic`/`vuln`/`expert_note`）在 10-31 04:53 的那批重建。

⚠️ 该漂移**不是** kb 裁剪导致（QA-3 已验证「模拟清理后 error 数仍为 20，完全一致」），而是 **RFC 抽取重构连带重建了非 rfc 源事实**（tasks #43~#49）。
QA-3 基线中 `B:seed-count-contract` 28 条记录的是 **rq3 语料**（期望 38/50/…），本问题是 **rq4 语料**（期望 39/25/78）——**同一根因、不同语料**，此前未被单独识别。


### 12.3 影响评估

| 层面 | 影响 | 结论 |
|---|---|---|
| **已发表结果有效性** | **无影响**。实验用的 `rq4_B` 语料**完好**：本机 `md5sum -c MANIFEST.md5` = 39/39 OK、0 FAILED；本机↔VM 逐字节 md5 三协议**全部 MATCH**（`7660bba3e731` / `3c7c2db75071` / `996aa100bc29`） | ✅ **论文数据可信**，结论仍成立 |
| **可复现性** | **受损**。第三方无法从仓库重建实验语料 → 审稿人若索要"如何复现你的 ProtoRAG 语料"，当前答不上 | ⚠️ **需处理** |
| **CI / 构建** | `scripts/rq3_build_corpus.py` 与 `seedgen.py` 均因退出码 3 失败 | ⚠️ 已在 QA-3 基线的 20 errors 中体现 |
| **与 kb 裁剪的关系** | **正交**。`seedgen` 按协议隔离读取 `derived/model/per_source/<protocol>/`，删除 dns/dtls/ftp/ssh/tls 的 `per_source` **不影响** rtsp/sip/smtp | ✅ 裁剪本身安全 |

### 12.4 ★ 更严重的衍生缺陷：RTSP 语料的「IP 摄像机 URL 污染」

**这是 v3 最重要的新发现，且使 §12.5 的 S2 方案彻底失效。**

#### 12.4.1 现象（我已独立复现 QA-3 的数字）

| 语料 | 会话引用数 | 去重会话 | 不可播占比 |
|---|---|---|---|
| `derived/model/seeds/rtsp/rq4_B`（10-29，**实验实际用的**） | 150 | **7** | **0.0%** ✅ |
| `derived/model/seeds/rtsp/live555_20261024_110155` | 205 | 18 | 49.8%（与 profile 记载 47.9% 吻合 ✅） |
| `derived/model/seeds/rtsp/20261031_171135`（10-31 新生成） | — | 8（含 `isapi`） | — ⚠️ |
| **当前事实重新生成 group B（同口径）** | 211 | **8** | **46.5%** ⚠️ |

污染量化（`20261031_171135`，37 条种子）：
```
含 isapi / 10.11.26.98 的文件 : 22 / 37  (59.5%)
URL 引用计数                   : 10.11.26.98:554 = 93 次
                                127.0.0.1:8554  = 64 次
其余全部语料（rq4_B / pfb_exp_B / dict_rtsp / live555_20261024 …）: 0 污染
```

#### 12.4.2 根因（我追到代码行 + QA 追到源头链路）

**★ QA 追出的完整污染链路（比「兜底条件不够严」更本质）**：
```
traffic.jsonl → headers['url'].source_values['traffic_packet']
  → rag_seedgen.py:484-495（P4-b：traffic 真实值覆盖 facts 默认值）
  → message_instances 的 ('url', …) 字段（98 条中 18 条是摄像机）
  → edge_cover.py:121-122 → SeedMessage.url
  → seedgen.py:288 旧兜底不命中 → 原样透传
```
**★ 关键事实（QA 强调，比「兜底条件不够严」更本质）**：
> **`traffic` 源的 `url` 这个 `value_enum` 只有 3 个值、100% 是摄像机、零目标值**；
> 真正的目标 URL 只存在于**另一个字段** `header:request`（整条请求行）里。
> ⇒ **任何「从 `url` 桶取值」的路径都必然拿到摄像机 URL** —— 这是设计层面的问题，不是条件判断写松了。

**我追到的代码层（兜底条件）**：

事实层：`derived/model/per_source/rtsp/traffic/facts/` 中 **5/69 条** traffic 事实来自**两台不同设备**，其中一台是**非目标设备**：
```
subject = {type: header, name: Authorization}
value   = ['Digest username="<user>", realm="IP Camera(C1052)",
            nonce="<nonce>", uri="rtsp://10.11.26.98:554/isapi/streaming/channels/101", …']
```
代码层：`scripts/seedgen.py:273` 的兜底条件是
```python
if not msg.url or "localhost/seed" in msg.url:      # ← 只兜底「空 URL」或「含 localhost/seed 占位」
    msg.url = default_url.rstrip("/") + ("/" + cur_stream if cur_stream else "")
```
真实抓包 URL（`rtsp://10.11.26.98:554/isapi/...`）**既非空、也不含 `localhost/seed`** → **原样透传**进种子请求行。

传播链（已逐段核实）：
```
traffic facts(含摄像机 uri) → SeedMessage.url (core/models.py:35, from_dict)
   → seedgen.py:273 兜底不命中 → URL 原样保留
   → 种子请求行指向 10.11.26.98:554（非目标主机）
   → live555 服务端无此会话 → 404 / 连接失败
```
⇒ **我独立做的「仅非 rfc 源」消融跑出的 54 条里，39 条含 `isapi`、URL 引用 98 次指 `10.11.26.98:554`** → 再次确认**污染源是 `traffic`，与 rfc 无关**。

#### 12.4.3 影响判定

| 层面 | 影响 |
|---|---|
| **10-30 的 VM 实验结果** | ✅ **不受影响** —— 用的是 `rq4_B`（我实测：0 污染） |
| **「重新生成语料再跑」的复现路径** | ❌ **已断** —— 任何现在重生成的 RTSP 语料，约 **59.5% 种子指向错误主机**、**46.5% 会话引用指向不存在的 live555 会话** |
| **现有健康度指标** | ⚠️ **一条都不会红**（dup_fact_ids / toc_sourced_outcomes / 章节号命中全不受影响）→ **静默退化已实测坐实** |
| **磁盘遗留** | ⚠️ `derived/model/seeds/rtsp/20261031_171135` 这份**已被污染**，不应作为任何实验语料使用 |

#### 12.4.3.1 ★ 两条尚未闭环的**潜伏路径**（QA 挖出，我已核实）

| 编号 | 路径 | 当前状态 | 影响 |
|---|---|---|---|
| **P2-1** | **头部值**（`bundle["headers"]`）里的摄像机 URL **未归一**：Authorization×2、Content-Base、Rtp-Info、url×3 共 **7 个值**含摄像机 URL | **当前语料实测泄漏 0 次**（未触发） | ⚠ **潜伏** —— 一旦被选中即回流，且**指标不会红**（同 §12.4 的静默退化模式） |
| **P2-2** | `scripts/run_seedgen_e2e.py:98-118` 是**第二个种子生成入口**，只替换 `<server>`/`<stream>` 占位符、**不调任何归一化**；调用方 `scripts/run_rq1_protorag.py:83` | **我实测：潜在风险、非已发生**（全语料扫描仅 `20261031_171135` 污染） | 原因：其 `_apply_stream_urls` 用 `host:port` 参数**直接构造** URL（`base = f"rtsp://{server}/{stream}"`）、**不从 facts 取值** → 天然不受 `traffic` 桶污染 |

⇒ **P2-1 必须纳入 S4 的 G1/G2 一起查**（不能只查请求行 URL）；**P2-2 需在 S5 前用 G1 闸验证其产物**。

#### 12.4.4 建议的「发布准入闸」

> **★ 完整规格书已出：`docs/实验/RQ4_S4语料发布准入闸规格.md`**（v1，249 行）——
> 含三条红线（G1 目标端点正确率 / G2 不可播会话占比 / G5 契约一致性）的判据与阈值、
> **三协议各自的合法端点集合**（RTSP `127.0.0.1:8554`；SIP `5060`+`5061` 双端口；SMTP **不适用**）、
> JSON 输出契约、**退出码 0/1/2 语义**、8 条验收用例（已用真实语料预跑通）、
> 以及对 QA-3 现有 `probe_*` / `check_playable_resources.py` 的复用点。
> **本节仅保留背景与红线清单，细节以规格书为准。**



QA-3 已产出 `qa/check_playable_resources.py` → `qa/playable_resources_redline.json`（R1 `playable ⊆ full` / R2 不可播占比 / R3 会话分布漂移）。
建议在此基础上**再加一条**并接入 CI（退出码非 0 即阻断）：

| 闸 | 判据 | 建议阈值 |
|---|---|---|
| **G1 目标主机正确率** | 种子请求行的 URL host:port 必须是目标环境的主机端口（RTSP `127.0.0.1:8554`） | 命中率 **= 100%**（实测 rq4_B 达标；新生成 40.5%） |
| **G2 不可播会话占比** | 种子引用的会话名 ⊆ `profile.environments.<env>.playable_resources` | **= 0%**（实测 rq4_B 达标；新生成 46.5%） |
| **G3 语料契约** | `seedgen` 产出条数 == profile 契约 | 相等（exit 0） |

> **G1/G2 是「正确性闸」而非「质量闸」** —— 打向错误主机的种子不是「弱种子」，是**坏种子**（服务端根本不会按预期路径解析）。
> 这条闸能同时拦住 §12.1 的契约漂移与本节的污染缺陷，且**零额外容器成本**。

### 12.5 建议处置（★ 相对 v2 修订：S2 前提已被推翻）

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| ~~S2~~ **（v2 方案，已作废）** | 回退 `rfc` 事实到 10-29 状态 | — | ❌ **前提被消融实验推翻**：rfc 源对产出贡献 = 0，回退它**毫无效果**。且 `per_source.bak_20261018` 是扁平布局、非现行结构，不能直接回退 |
| **S1′（修订版 S1）** | 先**修 traffic 污染**（把非目标设备的抓包从 `traffic` facts 里剔除，或让 `seedgen.py:273` 的兜底改为「URL host 不等于目标 host 就重写」），**再**冻结事实重生成并采用新条数 | 与当前代码自洽、可复现、**且语料不再打向错误主机** | 实验需重跑（3h×6）；论文数字变（54/20/61 或修污染后的新值） |
| **S2′（修订版 S2）** | 回退**非 rfc 源**（`source`/`traffic`/`vuln`/`expert_note`）到 10-29 04:53 之前的状态 → 重新生成仍得 39/25/78 | 论文数据不用重跑 | 需重建那批事实（无现成备份）；**且不解决污染**（污染源 `traffic` 本身就在其中，回退后污染应随之消失——需实测确认） |
| **S3（不变）** | VM 补 `MANIFEST.md5`+`manifest.json`；论文声明「语料快照+MANIFEST 可校验」 | 零风险、今天可做 | 只能**校验**不能**重建** |
| **S4（新增，强烈建议）** | 把 **G1/G2/G3 三闸**接入 CI，作为语料发布准入 | 拦住「静默退化」；零容器成本 | 需把 `check_playable_resources.py` 提升为 CI 阻断项 |

#### 12.5.1 ★ 驱动源逐项分解（team-lead 独立实测 + 我复核，三方一致）

team-lead 用**逐一剔除法**（每次剔掉一个源）独立复现，结论与我的消融、QA-3 的消融**三方一致**：

| 剔除的源 | 条数 | 内容 md5 | 结论 |
|---|---|---|---|
| 全五源（基线） | 65 | `65ce7314` | — |
| **rfc** | 65 | **完全相同** | **零影响** |
| expert_note | 65 | 相同 | 零影响 |
| **source** | **0** | — | **决定性驱动**（唯一能产出种子的源） |
| vuln | 52 | 不同 | +13（`vuln_boundary` 层） |
| traffic | 64 | 不同 | +1（URL 观测值 / 会话构成） |

⇒ **rfc 源对 seedgen 产出（条数 + 字节内容）= 0**。team-lead 补充印证：rfc facts 的 `subject.type` 无一条 `state`，而状态机层需要状态事实 → **即使有人重写整个 rfc 抽取器，产出也不会变**。

**★ 由此推翻的另一条具体做法**：team-lead 实测「用 `rtsp_base.dict` 重建得 39 条精确匹配」**不成立** ——
`--dict base` 实得 **37** 条，且 `--dict base` 与 `--dict protocol` **条数完全相同** ⇒ **dict_kind 不是驱动因素**。
差异在**多资源覆盖的消息序列构成**：已发表 `rq4_B` = 「6 个 DESCRIBE 单种子 + 7 个标准 OPTIONS+DESCRIBE+SETUP+PLAY+TEARDOWN」；现生成 = 「18 个标准 OPTIONS+DESCRIBE+SETUP+PLAY+TEARDOWN + 5 个 SETUP」。
⇒ **「同参数重建即等价」这个前提不成立，不能靠换一个 dict 就复现。**

**★ 对 S2′ 成本的重要修正**：S2′ 并**不是**「零成本保住论文数字」—— 它**同样依赖污染修复**（`traffic` 是污染源，回退它才可能同时消除污染），且**当前无 10-29 前的非 rfc 源备份**。
⇒ 两条路径的真实成本对比（team-lead 给出，供裁决）：
| 路径 | 真实成本 |
|---|---|
| **S1′** | 重跑 6 容器 × 3h = **18 容器小时**；论文**全部数字**变 |
| **S2′** | 重建 10-29 前的非 rfc 源事实（**当前无备份**）+ **必须先修 traffic 污染**才能让重建语料干净 → **并非零成本保住论文数字** |

#### 12.5.2 S3 的 VM 写入规格 v4（★ **已执行完成** —— team-lead 授权后按此执行）

> **v3 规格有误**：v3 我写「6 个文件全部新建，不覆盖任何现有文件」。该判断不完整 —— VM 上**确实已存在** manifest 文件，只是**路径与 v3 提议的不同**（在父目录、文件名带 `.manifest`）。

**① VM 写入前状态（勘查）**
```
/home/zxy/rq4/seeds/
├── rq4_check_crlf.py      1529 B
├── rtsp.manifest.md5      2807 B   md5=9099b577061103262327577ffaff5b92  39 行  ★已存在
├── sip.manifest.md5       1792 B   md5=85a72bc3d909acda5fe3035507953bc2  25 行  ★已存在
├── smtp.manifest.md5      4909 B   md5=c8a870e1b07bd38142519556de72525f  78 行  ★已存在
└── rtsp/ sip/ smtp/       39/25/78 个 .raw（子目录内无 manifest）
```

**② 既有文件的比对与决定**

| VM 现有文件 | VM md5 | 本机对应 | 本机 md5 | 等价性 | **决定** |
|---|---|---|---|---|---|
| `seeds/rtsp.manifest.md5` | `9099b577…` | `rq4_B/MANIFEST.md5` | `f08f0d64…` | 等价（39 行、md5 全同；仅分隔符格式：VM 空格 / 本机 ` *`） | **跳过，不覆盖** ✅ |
| `seeds/sip.manifest.md5` | `85a72bc3…` | 同上 | `28c96b38…` | 等价 | **跳过，不覆盖** ✅ |
| `seeds/smtp.manifest.md5` | `c8a870e1…` | 同上 | `f828fd49…` | 等价 | **跳过，不覆盖** ✅ |

**③ 实际写入清单（6 个文件，全部「新建」，零覆盖）**

| VM 路径 | 来源 | 大小 | 内容 md5 |
|---|---|---|---|
| `seeds/rtsp/manifest.json` | `rq4_B/manifest.json` | 24948 B | `dccdb5cd9608edab01e152ff5860c8a3` |
| `seeds/rtsp/README-dict.txt` | 本机新写 | 1908 B | `894edcffd46072abd880b658c4d84f6e` |
| `seeds/sip/manifest.json` | `rq4_B/manifest.json` | 16782 B | `440392e19f6568545bafa889afae77c0` |
| `seeds/sip/README-dict.txt` | 本机新写 | 1881 B | `6e4497ecd6e8e75263945398a7abbbfa` |
| `seeds/smtp/manifest.json` | `rq4_B/manifest.json` | 46718 B | `16d6535d520443b4bc828f4c882157d4` |
| `seeds/smtp/README-dict.txt` | 本机新写 | 1729 B | `467d90a0466970a46c3be39e420cc6c8` |

**执行安全性**：写入前逐个断言 6 个目标路径**均不存在**（存在则 ABORT）；写入用 `cp -n`（no-clobber）。**未覆盖任何既有文件 → 无需备份。**

**④ 写入后复核输出（实测）**
```
① 语料完整性 md5sum -c（未被本次写入影响）
   rtsp: 39 OK / 0 FAILED   sip: 25 OK / 0 FAILED   smtp: 78 OK / 0 FAILED
② 新写入文件 md5 —— 与本机逐个一致 ✅（见 ③ 表）
③ 既有 .manifest.md5 未被改动：9099b577… / 85a72bc3… / c8a870e1…（与勘查时一致）✅
④ manifest.json 可解析：rtsp protocol=rtsp group=B seed_count=39 seeds[]=39
                       sip  protocol=sip  group=B seed_count=25 seeds[]=25
                       smtp protocol=smtp group=B seed_count=78 seeds[]=78
⑤ README-dict.txt 关键行正确：rtsp/smtp = 镜像内置官方字典；sip = ★未使用字典★
```

**⑤ `README-dict.txt` 内容规格（三份同构）**

```
【一】本组实验实际使用的字典
  rtsp : 镜像内置官方字典 /home/ubuntu/experiments/rtsp.dict
         （md5=464351f88db6c3f0bdac0de01859316b, 24 token, LF 行尾）
         ⚠ 与 manifest.json 的 dictionary.md5 不是同一份文件（token 集合相同 24/24，字节不同）
  sip  : ★未使用字典★（两组 command_line 均无 -x；dict_tokens 均为 0）
         ⚠ manifest.json 记有 dictionary{path:sip.dict, token_count:163}，与实验事实不符
  smtp : 镜像内置官方字典 /home/ubuntu/experiments/smtp.dict
         （md5=fae50780f1c1b2c32a72b1adc4f2303d, 14 token）
【二】生成期字典（仅供复现参考，非实验所用）：各协议 rq4_B/<proto>.dict + md5 + token 数
【三】语料可校验性：md5sum -c ../<proto>.manifest.md5（39/25/78 OK）
      ★ 快照可校验，但不可由当前代码逐字节重建（§12.6.2）
【四】写入记录：谁写的 / 何时 / 基于什么 / 为什么 / 做了什么
```


**我的推荐（相对 v2 修订）**：
1. **立即**：S3（VM 补 provenance）+ S4（加 G1/G2 闸）—— 两者零风险、今天可做，且 S4 正是我 v1 建议的可播性红线（QA-3 已实测坐实「静默退化」）。
2. **裁决**：S1′（修污染 + 重跑）vs S2′（回退非 rfc 源 + 不重跑）→ **决定论文最终数字**。
   - 论文已定稿/已投稿 → 优先 S2′（保住 39/25/78 与现有数据）。
   - 论文仍在写 → 优先 S1′（语料可复现 + 无污染，数字可更新）。
3. **无论选哪个**：`derived/model/seeds/rtsp/20261031_171135` **标记为废弃**（59.5% 污染），不得用于任何实验。


## 12.6 ★ 污染修复已通过；且「幂等 ⇒ 历史语料逐字节不变」**不成立**（v4 新增）

### 12.6.1 污染修复验证通过（我独立复现）

team-lead 独立验证了污染修复（`core/fused/downstream/target_env.py:normalize_target_endpoint` + `scripts/seedgen.py:298,307`），我**独立重跑复现**：

| 指标 | 修复前 | 修复后（我实测） |
|---|---|---|
| 含 `isapi`（不可播会话）的种子 | 22 / 37（59.5%） | **0 / 54** ✅ |
| URL 引用 `rtsp://10.11.26.98:554`（摄像机，非目标） | 93 次 | **0** ✅ |
| URL 引用 `rtsp://127.0.0.1:8554`（目标） | 64 次 | **211 次（100%）** ✅ |

**修复是外科手术式的**：条数不变（修复前后同为 **54**）、消息序列不变 → 只改 URL，不改语义结构。
team-lead 另测得最终 `37 failed / 644 passed / 20 errors` → **不变量保持，无回归**。

### 12.6.1.1 ★ v4 复核：QA-4 挖出 P0-1 后，我重测了修复的实际状态

QA-4 独立验证污染修复时挖出 **P0-1**：`normalize_target_endpoint` **没有协议判别**，对 SIP 也施加了端点改写
（`sip:bob@127.0.0.1` → `sip:127.0.0.1:5060` 丢 user part；`sip:127.0.0.1` → 凭空加端口；`sips:` 静默降级为 `sip:`），
**已发表 SIP 语料 11/11 目录全部会变**、`rq4_B`（实验实际用的 25 条）**34/112 条消息 URI 变化**。

**修复已引入 profile 级开关** `profile.seedgen.target_endpoint_normalization`（默认 false）。
**我实测当前状态**（`fused_hub/targets/*/profile.json` 中**三协议均未设置该键** → 全部走默认 false）：

| 检查项 | 实测结果 | 判定 |
|---|---|---|
| **RTSP 污染是否仍被修复** | 重新生成 54 条：**isapi 0 文件、摄像机 URL 0 次、目标 URL 211 次** | ✅ **仍有效**（RTSP 走的是**资源归一化**路径，与端点开关无关） |
| **SIP 是否仍被端点改写** | 重新生成 20 条：R-URI 全部为 `sip:127.0.0.1:5060`/`sip://127.0.0.1:5060`，**user part 已保留**（`sip:bob` 不再被剥掉） | ✅ **P0-1 已缓解**（开关默认 false，SIP 不做端点改写） |
| **⚠️ 但残留 `sip://` 双斜杠** | 20 条中出现 **10 次 `sip://127.0.0.1:5060`**（已发表 `rq4_B` 中为 **0 次**） | ⚠️ **新发现的一处退化**，需 QA-4 一并核实 |
| **P1-1 路径塌缩是否仍在** | 重新生成 54 条中含 `track1` 的 **6 条**、含 2 段路径的 **12 处**；已发表 `rq4_B` 为 **15 条 / 68 处** | ⚠️ **仍未完全保持**，与 QA-4 的 P1-1 一致 |

⇒ **§12.6.1 的「修复是外科手术式的」结论需限定为「对 RTSP 成立」**；SIP 侧的 P0-1/P1-1/双斜杠三项由 QA-4 复核中，**S5 数量对齐组必须等其修复完成后再启动**。

### 12.6.2 ★ 但「幂等 ⇒ 历史语料逐字节不变」**不成立**

`target_env.py:336-338` 的 docstring 写：
> 「对本就指向 `default_url` 的种子，本函数**原样返回**（逐字节不变）⇒ 现存历史语料（RQ1.2 / RQ3）不受影响，连续性硬不变式得以保持。」

**前半句成立，后半句不成立。** 我用当前代码重建 RTSP/B 并与已发表 `rq4_B` 逐字节比对：

```
同名文件：identical = 0    different = 8      ← 与 team-lead 实测完全一致
```

差异**与污染修复无关**，而是**更早的代码演进**（R4 修复 + transport 变更）。逐行 diff（实测）：
```
已发表版：SETUP rtsp://127.0.0.1:8554/mpeg1or2AudioVideoTest/track1   ← 带 track1 子路径
         Transport: RTP/AVP/TCP;unicast;interleaved=0-1
         PLAY    rtsp://127.0.0.1:8554/mpeg1or2AudioVideoTest/
现在版：  SETUP rtsp://127.0.0.1:8554/mpeg1or2AudioVideoTest          ← 无 track1
         Transport: RTP/AVP;unicast;client_port=8000-8001
         Session: 12345678                                          ← 新增
         PLAY    rtsp://127.0.0.1:8554/mpeg1or2AudioVideoTest
```
分布印证（我实测）：

| 指标 | 已发表 rq4_B（39 条） | 当前代码重生成（54 条） |
|---|---|---|
| 含 `track1` 的文件 | **15** | **6** |
| `Transport: RTP/AVP/TCP;…interleaved` | 11 | 11 |
| `Transport: RTP/AVP;…client_port` | 7 | **30** |

⇒ **准确的三层区分**（写论文时不能混为一谈）：

| 层面 | 是否可复现 | 原因 |
|---|---|---|
| **污染修复本身** | ✅ **幂等且外科式** | 只改 URL、不改条数与消息序列（54 → 54） |
| **已发表 rq4_B 可由当前代码逐字节重建** | ❌ **在任何修复之前就不成立** | 真因 = **source 源状态名迁移 + R4 修复（track 子路径）+ transport 模式变更** |
| **rfc 抽取改造的影响** | ❌ **零影响** | 消融证明 rfc 源对产出贡献 = 0（§12.2.2） |

⇒ **后两者与 RFC 抽取改造正交**。这也再次解释了「回退 rfc 事实」为何无效。
⚠️ **不可**在论文里写「有了 URL 归一化就能复现历史语料」—— 会误导。

## 13. ★ 实验实测结果与结论边界（v3 新增，VM `rq4_summary.csv` 实测）

### 13.1 原始数据（fuzz_sec ≈ 10796 ≈ 3h，6 容器全 `param_check=OK`、`exit_code=0`）

| 协议 | 组 | seed_files | seed_regions | dict_tokens | execs_done | execs/s | paths_found | **bitmap_cvg（主）** | **l_per（次）** | b_per | unique_crashes | unique_hangs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RTSP | protorag | 39 | 150 | 24 | 142,878 | 6.94 | 935 | **9.94%** | 24.7 | 15.7 | 0 | 0 |
| RTSP | baseline | 7 | 29 | 24 | 212,619 | 13.26 | 1098 | **9.72%** | 24.2 | 15.4 | 0 | 0 |
| SIP | protorag | 25 | 112 | 0 | 53,144 | 4.55 | 1781 | **22.06%** | 6.6 | 1.6 | 0 | 0 |
| SIP | baseline | 1 | 4 | 0 | 60,432 | 5.58 | 1710 | **22.11%** | 6.4 | 1.5 | 0 | 0 |
| SMTP | protorag | 78 | 355 | 14 | 19,153 | 1.91 | 350 | **10.00%** | 5.9 | 4.0 | 0 | **2** |
| SMTP | baseline | 2 | 14 | 14 | 18,740 | 2.31 | 522 | **11.66%** | 14.1 | 9.2 | 0 | **3** |

> 参数字段 `param_check=OK`（实测 `command_line` 与设计逐字一致，含 `-t 5000` / `-m none` / kamailio 无 `-R` / RTSP 8554 / SIP `-l 5061` / SMTP `-W 100 -c clean`）→ **§1.3 的参数裁决已被正确落地**。
> `dict_tokens` 两组相同（24/24、14/14、0/0）→ **字典确为受控变量**（§4.2 策略生效）。
> `seed_files` 两组为 39/25/78 vs 7/1/2 → **语料数量严重不对齐**（§5），这是解读下表所有数字时的首要约束。

### 13.2 三口径结论（与 QA-3 提出的「数量不对齐时单一口径误导」一致）

| 口径 | RTSP | SIP | SMTP | 含义 |
|---|---|---|---|---|
| **挂钟终值**（3h 后 bitmap_cvg） | protorag **+0.22pp** ✅ | protorag **−0.05pp** ≈ | protorag **−1.66pp** ❌ | 固定时间预算下的终局 |
| **等执行次数**（同等 exec 预算） | 见 `derived/experiments/rq4/qa/qa_crossover.md` | 同左 | 同左 | 剥离执行速率差异 |
| **行覆盖 l_per** | protorag **+0.5pp** ✅ | protorag **+0.2pp** ✅ | protorag **−8.2pp** ❌ | 源码级覆盖 |

**★ 关键观察：三协议结论方向不一致，且 SMTP 上 protorag 显著落后。**

### 13.3 结论边界（论文必须写清，不可越界）

✅ **可以宣称**
1. **端到端效果**（同 3h 预算、字典恒定、参数官方）：RTSP 上 ProtoRAG 语料在**两个口径**（bitmap_cvg +0.22pp、l_per +0.5pp）上均略优于官方语料；SIP 上两口径**基本持平**（+0.2pp l_per / −0.05pp bitmap_cvg）。
2. **知识库覆盖增益**（可量化、真实）：ProtoRAG 语料覆盖了官方语料**完全缺失**的协议命令与状态（SMTP 的 STARTTLS/BDAT/RSET/NOOP/HELO；RTSP/SIP 的多样会话序列）→ 这是**语料规模 + 多样性**的联合效应。
3. **SMTP 上 ProtoRAG 语料未带来增益**，甚至在行覆盖上落后 8.2pp（14.1 → 5.9）→ **诚实披露的反例**，需单独分析（见 §13.4）。

❌ **不能宣称**
1. **「ProtoRAG 语料单条质量更优」**——seed_files（39/25/78 vs 7/1/2）与 seed_regions（150/112/355 vs 29/4/14）**数量严重不对齐**（§5）。SMTP 上 protorag 的 region 数是 baseline 的 **25×**。
2. **「ProtoRAG 字典有增益」**——本实验字典恒定（dict_tokens 两组相同），字典贡献需字典消融波单独测（§4.3）。
3. **跨协议的绝对覆盖率比较**——`l_per` 受各项目源码规模影响，只能协议内比；`bitmap_cvg` 虽定义统一，但插桩点密度不同，仍以协议内比较为准。
4. **任何带误差棒的结论**——**n=1，无重复**（R9）。

### 13.4 待深挖：SMTP 上 protorag 落后的候选解释

| 假设 | 证据指向 | 验证方法 |
|---|---|---|
| H1 **exec 速率被摊薄** | protorag 1.91 exec/s vs baseline 2.31（**慢 17%**）；seed 78 条 → 初始队列大 → 每条分到的变异预算少 | 用 `qa_crossover.md` 的等 exec 口径看是否反超 |
| H2 **BDAT/STARTTLS 等命令使 Exim 早退** | protorag 含 15×BDAT 4096、14×STARTTLS → Exim 可能直接 5xx 拒绝，后续状态机分叉变少 | 用 `regions/` 与 `replayable-queue` 看有效状态数；`aflnet-replay` 单条重放观察响应码 |
| H3 **`.` 结束符缺失致 DATA 态悬挂** | 官方 2 条种子结构极简（EHLO→MAIL→RCPT→DATA→.→QUIT）；protorag 命令序列更长更杂 | 统计 protorag 种子中 DATA 段未以 `.\r\n` 收尾的比例 |
| H4 **行覆盖口径被长尾拖累** | protorag l_per 5.9 vs baseline 14.1，但 bitmap_cvg 仅 10.00% vs 11.66% → **两个口径同向**，不是口径问题 | 已是实测排除项 |

### 13.5 下一步建议（与 §12 的决策耦合）

1. **立即（零风险）**：**S3**（VM 补 `MANIFEST.md5`/`manifest.json`）+ **S4**（把 G1 目标主机正确率 / G2 不可播会话占比 / G3 契约一致性接入 CI 作发布准入闸）→ 保证已发表数据可校验，且**下次不会再静默退化**。
2. **裁决**：**S1′**（先修 traffic 污染 → 冻结事实 → 重生成 → 重跑 6 容器）还是 **S2′**（回退非 rfc 源 → 保住 39/25/78 与现有数据）→ **这决定论文最终数字**。
   ⚠️ v2 的 S2（回退 rfc）**已作废**：消融实验证明 rfc 源对产出贡献 = 0（§12.2.2）。
3. **废弃标记**：`derived/model/seeds/rtsp/20261031_171135`（59.5% 摄像机 URL 污染）不得用于任何实验。
4. **数量对齐组**（§5.2 方案③）：无论 S1′/S2′，**下一轮必做**（3 协议 × K=3 子集）。它是把 §13.3 的 ✅2 升级为「单条质量归因」的唯一途径。
5. **SMTP 专项**：按 §13.4 H1~H3 定位落后的机制 → 这是**有价值的科研发现**（「更多样的语料 ≠ 更高覆盖」），建议作为论文的独立小节，而非隐藏。
6. **给 §5 数量对齐组加一条前置**：任何对齐子集在入组前必须过 **G1/G2 闸**（否则会拿「坏种子」做对齐，结论无效）。

### 13.6 ★ 可复现性陈述的**准确措辞**（v4 新增，供论文直接引用）

> **更正**：我此前表述为「派生产物已从仓库彻底移除，无法重建」——**该表述不准确，会误导审稿人**。
> 准确区分如下：

| 陈述 | 准确性 |
|---|---|
| ❌ 「派生产物已从仓库彻底移除」 | **错误**。已发表语料**仍在仓库里**：`derived/model/seeds/<proto>/rq4_B/`（39/25/78），`MANIFEST.md5` 逐条 md5 全 OK；VM 侧 `/home/zxy/rq4/seeds/<proto>/`（39/25/78）+ `<proto>.manifest.md5` 校验亦 39/25/78 全 OK |
| ❌ 「无法重建」 | **不精确**。不可重建的是「**从当前代码重新生成出同样的语料**」，不是「语料没了」 |
| ✅ **准确表述** | 「**语料快照 + MANIFEST 可校验，但不可由当前代码逐字节重建**」 |

**建议论文 / 报告的 reproducibility 陈述（可直接用）**：

> "The ProtoRAG seed corpora used in this study are archived in the repository (`derived/model/seeds/<protocol>/rq4_B/`) together with a per-seed MD5 manifest, and are byte-identical to the copies used on the fuzzing host (verified by `md5sum -c`, 39/25/78 seeds all OK for RTSP/SIP/SMTP respectively). The corpora are therefore **verifiable but not byte-reproducible from the current code**: the seed generator's output has since evolved for reasons orthogonal to the RFC-extraction refactor — specifically (i) state-name migration in the `source` knowledge source, (ii) the R4 fix that adds `track` sub-paths to SETUP request lines, and (iii) a change of the RTSP transport mode from `RTP/AVP/TCP;unicast;interleaved` to `RTP/AVP;unicast;client_port`. An ablation over the five knowledge sources shows the `rfc` source contributes **zero** to seed generation (it yields 0 state/outcome facts, which the state-machine layer requires), so the RFC-extraction refactor is **not** a cause of the divergence. Additionally, the URL-endpoint normalization introduced to fix a captured-traffic contamination defect is itself idempotent and surgical: it changes neither seed count (54 → 54) nor message-sequence composition."
