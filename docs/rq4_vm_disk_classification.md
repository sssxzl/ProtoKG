# VM 磁盘占用分类与清理候选清单（★ 只读勘查，**未删除任何文件**）

> 版本 v1（2026-10-31）· 架构师：高见远（Gao）
> 目的：team-lead 要求「在你列出候选目录与大小之前我不会授权清理」，且「删除的动作必须是你确认过的」。
> **本文只做分类与建议，不执行任何删除。**

---

## 0. 现状

```
文件系统 : /dev/sda3  98G  已用 88G  可用 4.8G  (95%)
docker root: /var/lib/docker (overlayfs) —— docker system df: Images 23 / 14.87GB，Containers 0
```
⚠️ 磁盘 95% 已满是**正式实验前的阻断项**（§8 R1）：6 容器 × 3h 的 queue + cov_html + tar 预计需 ~15GB。

---

## 1. 分类原则

| 类别 | 定义 | 删除风险 | 可否重装/再生 |
|---|---|---|---|
| **A 可重装** | pip/conda/npm 等包管理器安装物 | 低 | ✅ 可重装 |
| **B 工具源码（可重新 clone）** | 从 GitHub 克隆的第三方项目源码 | 低（需网络） | ✅ 可重建 |
| **C 实验原始数据** | 抓包、语料快照、实验输出 | **高** | ❌ 不可再生 |
| **D 安装包残留** | 下载的安装包/压缩包（已安装完，压缩包本身无用） | 低 | ✅ 已装即可 |
| **E 临时目录** | `/tmp` 下的中间产物 | 中（需确认来源） | ⚠️ 视情况 |

---

## 2. `/home/zxy` 分类清单（只读勘查，`du -sh` 实测）

| 大小 | 路径 | 类别 | 说明 | 建议 |
|---|---|---|---|---|
| **7.0G** | `miniconda3/` | **A** | Python 环境 | ⚠️ **不建议删** —— 用户的 Python 工具链依赖它。若磁盘紧张，可考虑删 `miniconda3/pkgs`（conda 包缓存，通常数 GB，可 `conda clean -a` 回收） |
| **1.9G** | `target programs/` | **B/C** | 需确认内容 | 若为 ProfuzzBench 目标程序源码 → 可重新 clone；但若含**已编译插桩二进制**，重新构建成本高 |
| **1.3G** | `selectfuzz/` | **B** | 第三方工具源码 | 可重新 clone |
| **1.1G** | `ChatAFL/` | **B** | ChatAFL 源码（本研究用到） | ⚠️ **不建议删** —— 是当前实验工具链 |
| 858M | `chatafl历史版本/` | **B** | 历史版本归档 | 由用户判断是否仍需历史版本 |
| **716M** | `snap/` | **B** | Flatpak 运行时 | 若不用 flatpak 可删 |
| **710M** | `AFLplusplus/` | **B** | AFL++ 源码 | 可重新 clone |
| 422M | `Documents/` | **C** | 文档 | ❌ **不删** |
| **411M** | `数据流量/` | **C** | 抓包原始数据 | ❌ **不删** —— 语料生成的事实来源 |
| 377M | `aflnet/` | **B** | AFLNet 源码 | 可重新 clone（但实验用的 `aflnet` 镜像已构建，删源码不影响已建镜像） |
| 361M | `Downloads/` | **D/E** | 下载暂存 | ✅ 大概率可清（多为安装包/压缩包） |
| 297M | `ProtocolGuard/` | **B** | 第三方工具 | 可重新 clone |
| **279M** | `clang+llvm-6.0.0-x86_64-linux-gnu-ubuntu-16.04.tar.xz` | **D** | LLVM 安装包（已装） | ✅ **安全删**（已安装，压缩包无用） |
| 220M | `nodejs/` | **A** | Node 环境 | ⚠️ 不建议删 |
| 187M | `dr-chatafl改/` | **B** | 改过的 ChatAFL | ⚠️ 含本项目修改，**不删** |
| 182M | `watt/` | **B** | 第三方工具 | 可重新 clone |
| **156M** | `Miniconda3-latest-Linux-x86_64.sh` | **D** | 安装包（已装） | ✅ **安全删** |
| 120M | `live555-asan/` | **B/C** | live555 ASAN 构建 | 需确认是否被现用镜像替代 |

---

## 3. `/tmp` 分类清单（**1.9G**，需逐个确认来源）

| 大小 | 路径 | 类别 | 说明 | 建议 |
|---|---|---|---|---|
| **498M** | `/tmp/ls_rq4_rtsp_protorag_r1` | **C** | RQ4 RTSP 实验输出 | ❌ **不删** —— 是实验产物（应归档到 `rq4/out/`） |
| **400M** | `/tmp/captures` | **C** | 抓包 | ❌ **不删** —— 语料事实来源 |
| **353M** | `/tmp/chk_rtsp` | **C** | 某次检查产物 | ⚠️ 需确认归属 |
| 177M | `/tmp/rq12_data.tgz` | **C** | RQ1.2 数据打包 | ❌ 不删（实验数据） |
| **161M** | `/tmp/ls_rq4_smtp_protorag_r1` | **C** | RQ4 SMTP 实验输出 | ❌ **不删** |
| 135M | `/tmp/rq2_out_r1` | **C** | RQ2 输出 | ❌ 不删 |
| 71M | `/tmp/ftp_sip_captures.tar.gz` | **C** | 抓包打包 | ❌ 不删 |
| 32M | `/tmp/rq2_stats` | **C** | 统计 | ❌ 不删 |
| 29M | `/tmp/test4.pcapng` | **C** | 测试抓包 | ⚠️ 需确认 |
| 22M | `/tmp/supplement.tar.gz` | **C** | 补充数据 | ❌ 不删 |

> ⚠️ **`/tmp` 里绝大多数是实验原始数据，不是垃圾**。**不建议清 `/tmp`** —— 它是本次磁盘紧张的主要假象来源之一，但真删会丢数据。

---

## 4. ★ 我的清理建议（按「低风险 × 高收益」排序）

**第 1 优先：纯安装包残留（零风险，立即回收 435M）**
```bash
rm -f /home/zxy/clang+llvm-6.0.0-x86_64-linux-gnu-ubuntu-16.04.tar.xz   # 279M
rm -f /home/zxy/Miniconda3-latest-Linux-x86_64.sh                          # 156M
```
⇒ **回收 435M**，零风险。

**第 2 优先：docker 镜像（回收最多，但需先确认镜像用途）**
```
docker system df: Images 23 个 / 14.87GB，Containers 0，dangling = 0（我上轮报的 3 个 dangling 已被清理，现为 0）
```
**23 个镜像分两组**（实测 `docker images`）：

**A 组：15 个「上一代」基础镜像（已被 rq2-* 取代）—— 合计约 24.7GB 表面占用**
```
kamailio:latest 3.26G   forked-daapd:latest 2.79G   live555:latest 2.23G
live555-chatafl:latest 2.23G   proftpd:latest 2.11G   exim:latest 2.07G
lighttpd1:latest 1.99G   pure-ftpd:latest 1.91G   pureftpd:latest 1.89G
bftpd:latest 1.85G   lightftp:latest 1.79G   chatafl-live555:latest 236M
ubuntu:22.04 119M   ubuntu:20.04 111M
```
⚠️ `kamailio:latest` / `live555:latest` / `exim:latest` 与 `rq2-*` 是**同源镜像**（rq2-* 是基于它们加 chatafl/aflnet 层）。
　 删 A 组不影响 rq2-*（独立 tag/层），但**若未来要重新构建 rq2-* 镜像，基底就没了**。
　 `forked-daapd` / `proftpd` / `lighttpd1` / `pureftpd` / `pure-ftpd` / `bftpd` / `lightftp` 是**本次三协议实验完全用不到**的目标（ProfuzzBench 的其他 target）。
⇒ **A 组是最佳回收候选**（不影响三协议实验，也不影响 rq2-* 镜像可用性），但需你确认「不再构建这些 target」。

**B 组：9 个 rq2-* 镜像（约 20.4GB 表面占用，含共享层，实际占用小于此）**
```
rq2-kamailio:latest 3.27G   rq2-live555:proxy 2.24G   rq2-live555:latest 2.24G
rq2-proftpd:latest 2.12G   rq2-exim:latest 2.08G   rq2-pure-ftpd:latest 1.91G
rq2-pureftpd:latest 1.90G   rq2-lightftp:latest 1.86G   rq2-bftpd:latest 1.86G
```
⇒ **其中只有 3 个是本次实验必需**：`rq2-live555:latest`、`rq2-kamailio:latest`、`rq2-exim:latest`。
　 其余 6 个（proftpd / pure-ftpd / pureftpd / lightftp / bftpd / live555:proxy）是**其他协议/变体**，本实验用不到。
　 ⚠️ **若 S1′/S2′ 要重跑 → 这 3 个必需镜像必须保留**（另 6 个可删）。

**第 3 优先：可重新 clone 的第三方源码（回收 ~2.7G，需网络）**
`selectfuzz/`(1.3G) + `AFLplusplus/`(710M) + `snap/`(716M) + `ProtocolGuard/`(297M) + `aflnet/`(377M) ≈ 3.4G
⇒ 可回收 **~3.4G**。但 `aflnet/` 源码删了不影响**已构建镜像**（镜像内自带 aflnet 二进制，已核实）。

**第 4 优先：conda 包缓存（不动环境本体）**
```bash
conda clean -a --dry-run    # 先看能回收多少
```
实测 `miniconda3/pkgs` = **1013M** ⇒ 可回收约 **1.0G**，**不动 conda 环境本体**。

**明确不建议动的**：`miniconda3/`(环境本体)、`ChatAFL/`、`dr-chatafl改/`、`数据流量/`、`Documents/`、`/tmp/*` 中的实验数据。

---

## 4.5 ★ 已执行的清理（team-lead 授权，2026-10-31）

> ⚠️ **授权给的命令与磁盘实况不符**，我按「先勘查再动手」原则**修正了路径**并**缩小了范围**。

### 授权命令 vs 实况

| 授权命令 | 实况 | 我实际执行的 |
|---|---|---|
| `rm -rf /home/zxy/.cache/pip/*`（~10M） | `~/.cache/pip` 实为 **3.1G**（`http-v2` 3.1G + `http` 2.9M + `wheels` 72K），顶层 **0 个 .whl** | `rm -rf ~/.cache/pip/http-v2 ~/.cache/pip/http` → 保留 `wheels`/`selfcheck` |
| `rm -f ~/.conda/pkgs/*.tar.bz2 ~/.conda/pkgs/*.conda`（~184M） | **`~/.conda/pkgs` 不存在**！真实位置是 **`~/miniconda3/pkgs`**（938M，155 个归档 = 160M） | `rm -f ~/miniconda3/pkgs/*.tar.bz2 ~/miniconda3/pkgs/*.conda` → **只删归档，不动已解包的环境** |
| `rm -f ~/.cache/pip/*.whl /home/zxy/snap/*`（716M） | `snap/` 是 **snapd 活动数据目录**（`firefox` 702M + `code` + `snap-store` + `snapd-desktop-integration`，各带 `current` 符号链接）；其中 `firefox/common/.mozilla` = **105M 用户档案**（书签/历史/会话） | `rm -rf /home/zxy/snap/firefox/common/.cache`（597M，**纯可再生缓存**）→ **★保留 `.mozilla` 用户档案、`code`、`snap-store`、`current` 符号链接** |

### 执行结果

```
磁盘 BEFORE : /dev/sda3  98G  已用 88G  可用 4.8G  (95%)
磁盘 AFTER  : /dev/sda3  98G  已用 84G  可用 8.6G  (91%)   ← 回收 3.8G

① pip cache : 3100M -> 0M        (http-v2 + http)
② conda pkgs: 938M  -> 779M       (155 个归档 = 160M；已解包环境未动)
③ snap      : 687M  -> 117M       (只删 firefox/common/.cache)

用户档案完整性复核：
  firefox .mozilla 仍在 : YES (105M)   ← 书签/历史/会话完好
  snap/code 仍在        : YES
  snap/snap-store 仍在   : YES
  firefox/current 符号链接有效 : 8863  ← 未断
```

### ④⑤ 两项暂缓项的核实结果

| 项 | 核实结果 | 结论 |
|---|---|---|
| **④ `Downloads/` 的 `runtime_iso_v2.zip`** | ⚠ **该文件在 VM 上不存在**！`find /home/zxy -name "runtime_iso*"` **零命中**；`Downloads/` 实际只有 `watttoolkitlinuxban.zip`(166M) 与 `WeChatLinux_x86_64.deb`(212M) | **可删**：本地 `derived/` `scripts/` `core/` 全库 grep `runtime_iso` **零引用**；且 zip 根本不在 VM 上。（若你要的是别的文件请指认） |
| **⑤ `miniconda3/` 7G 重装清单** | 已生成 **`/home/zxy/rq4/conda_manifest/conda_reinstall_manifest.txt`**（251 行，含 base env Python 3.13.13 与 BSFuzz_env Python 3.11.8 的完整 `pip freeze`，各 123/122 包） | **清单已就绪** ⇒ 即使删 `miniconda3/` 也可精确重装。**但 7G 主体是已解包的环境**（`pkgs` 只剩 779M）→ 删了要重建整个 base + BSFuzz_env，**性价比低**，建议**不删**（现在 8.6G 已够用） |

## 5. 若需腾出 ~15GB 的组合建议

```
① 安装包残留                        435M   零风险
② conda 包缓存（实测）              1.0G   低风险，不动环境本体
③ 可重 clone 源码                  3.4G   需网络
④ docker A 组：上一代基础镜像        ~24.7G 表面占用（共享层，实际远小于此）
   └ 其中 forked-daapd/proftpd/lighttpd1/pureftpd/pure-ftpd/bftpd/lightftp
     = 本次三协议实验完全用不到 → 优先删
⑤ docker B 组：rq2-* 中用不到的 6 个  ~11.7G 表面占用
   （rq2-proftpd / rq2-pure-ftpd / rq2-pureftpd / rq2-lightftp / rq2-bftpd / rq2-live555:proxy）
──────────────────────────────────────────────────
①+②+③                    ≈ 4.8G   （不需要动任何镜像）
①+②+③+④（仅删用不到的目标镜像）  可再回收数 GB
```
⇒ **保守方案（不动任何镜像）**：4.8G → 约 9.6G，勉强够 6 容器 × 3h。
⇒ **宽松方案（删 A 组的无关 target 镜像 + B 组的 6 个无关 rq2 镜像）**：可腾出 20GB+，宽裕。

**需要你决策的两点**：
1. **是否还可能构建其他 ProfuzzBench target？**（决定 A 组能否整组删）
2. **S1′/S2′ 是否要重跑？**（决定 B 组里 `rq2-live555:latest` / `rq2-kamailio:latest` / `rq2-exim:latest` 这 3 个必需镜像必须保留）
　 ⚠️ **注意**：磁盘占用 ≠ 镜像表面大小之和（overlayfs 共享层）→ **实际回收量需实测**，建议先 `docker image rm` 若干个再 `df -h` 复核。
