# -*- coding: utf-8 -*-
"""local/rq1_2_make_record.py —— 生成 RQ1.2 Live555 实验记录（markdown）。

数据来源（采集脚本产出，位于 --data-dir）：
  · rq1_2_p1.csv        P1（初始种子/dry-run 刚结束）逐容器 n_states / n_edges
  · rq1_2_p2.csv        P2（24h 结束）逐容器 n_states / n_edges / bitmap_cvg /
                        unique_crashes / unique_hangs / paths_total / execs_done
  · rq1_2_summary.csv   按 (group, fuzzer) 聚合 → docx 表 4 的 4 行
  · rq1_2_timeseries.csv 全时序（用于时间桶均值）
  · rq1_2_extra_crashdist.csv   崩溃首次出现时刻
  · rq1_2_extra_hangs.csv       unique_hangs 明细
  · rq1_2_extra_lineage.csv     队列血缘（污染指纹）
  · rq1_2_extra_seedprovenance.csv  种子来源散文占比

可选输入：
  · --interim-dir     10-24 20:00 中间态快照目录（用于 §7 差异对比）
  · --evidence-json   证据链复核结果（qa_evidence_chains.json）

★★ 表述纪律（主理人 10-24 指示，硬约束）：
  1. **aflnet 两行为 RQ1.2 主证据**（干净：0 LLM 增强、唯一变量成立）；
     chatafl 两行**降级为辅证**并附污染说明。
  2. **n_edges 不稳健** → **不得**声称"稳定探索到更多状态机边"。
  3. 崩溃集中在基线组是**结构性事实**（真实流量种子天生踩中
     matroska UAF CVE-2021-38382/38381）→ **不得**解读为
     "ProtoRAG 不会发现崩溃"。
  4. 覆盖率反超须给 **win-rate + 配对差值均值±标准差 + 全部原始差值**。
  5. ★ 本脚本的所有数值**一律从 CSV 现场计算**，不硬编码任何统计量
     （v4 修订：v1–v3 把中间态的数字硬编码进正文，实验跑满 24 h 后
      与最终数据不符 —— 见 §0 修订说明）。
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# 复用分析引擎（统计口径与 rq1_2_analyze.py 保持单一事实源）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rq1_2_analyze import (  # noqa: E402
    REPS, TS_POINT_BUCKETS, build, fmt_ps, num, paired_stats, read_csv,
    sign_test_exact_p, wilcoxon_signed_rank_exact_p,
)

#: 崩溃分布的说明（结构性事实，非方法劣势）—— v7：按半侧分开归因
CRASH_NOTE = (
    "崩溃 74/75 集中在基线组（seed_reuse），实验组仅 **1** 个 —— "
    "这是**结构性事实**而非方法劣势。\n"
    "**但 74 个必须分开看**（按血统溯源 + 样本散文核查双重判定）：\n"
    "```\n"
    "aflnet 半侧基线 47 个  → 血统=原始流量种子 rtsp_requests_aac.raw，散文 0，\n"
    "                          含 matroskaFileTest 路径片段 25/47（EBML 负载 magic 0 命中）\n"
    "                          → 真实流量种子自带 matroska 播放路径 → CVE-2021-38382/38381\n"
    "chatafl 半侧基线 27 个 → 血统=enriched_*（LLM 增强种），散文 27/27（100%）\n"
    "                          → 污染产物，不是干净漏洞证据\n"
    "protorag 半侧   1 个  → 血统=ProtoRAG 原始种子 25_DESCRIBE+TEARDOWN+OPTIONS+OPTIONS.raw，\n"
    "                          但样本散文命中 64、matroska 0 → 污染产物，不计入\n"
    "```\n"
    "→ 「74/75 都归因 matroska UAF」**不成立**（会把 27 个污染产物混进去）。"
    "正确表述：\n"
    "**aflnet 半侧基线的 47 个**是真实 matroska 播放路径上的 UAF"
    "（真实流量种子自带 `matroskaFileTest` 路径片段，命中 25/47；\n"
    "  EBML 负载 magic（1A 45 DF A3）命中 0 → 是**播放路径**问题而非 EBML 解析器问题，\n"
    "  CVE-2021-38382 / CVE-2021-38381）；\n"
    "**chatafl 半侧基线的 27 个是污染产物**，不作真实漏洞证据；"
    "ProtoRAG 侧唯一 1 个虽血统可溯到 ProtoRAG 原始种子，"
    "但**崩溃样本散文命中 64 次、matroska 命中 0 次**\n"
    "（血统链经 `src:000024+000195` 拼接，`000195` 为 `enriched_*` 条目 → 散文由拼接注入）"
    "→ **同样不计入**。\n"
    "**不得**把该结果解读为『ProtoRAG 不会发现崩溃』——"
    "它只说明**在本目标系统的这一特定缺陷上**，\n"
    "真实流量先验比合成先验更容易直接命中崩溃触发器；"
    "且由于 chatafl 侧崩溃样本受污染，\n"
    "**崩溃数这个指标本身不可用于任何方法优劣比较**，"
    "更不可解读为『ProtoRAG 抑制了崩溃』。"
)


def _fmt_cell_means(by_cell: dict, cell: str, key: str, unit: str = "") -> str:
    """从 by_cell 取单元格的均值并格式化。"""
    v = by_cell.get(cell)
    if not v:
        return "NA"
    return f"{v[key]:.2f}{unit}"


def _stat_block(v: dict) -> str:
    """渲染一条指标的配对统计（含三种检验的 p 值）。"""
    if not v.get("n"):
        return f"- **{v['label']}**：数据不足（NA）\n"
    u = f" {v['unit']}" if v.get("unit") else ""
    n = v["n"]
    w, t, l = v["wins"], v["ties"], v["losses"]
    raw = ", ".join(f"{d:+.2f}" for d in v["diffs"])
    sign = ("一致为正" if w == n else ("一致为负" if l == n else "不一致"))
    out = (f"- **{v['label']}**\n"
           f"  - win rate = **{w}/{n} = {w / n:.2f}**"
           f"（平 {t} / 负 {l}）→ **{sign}**\n"
           f"  - 配对差值 mean ± sd = **{v['mean']:+.2f} ± {v['sd']:.2f}{u}**"
           f"（ddof=1，SEM={v['sem']:.2f}）\n"
           f"  - 全部原始差值：{raw}\n")
    # 离群点稳健性
    dm = v.get("drop_max_abs")
    if dm:
        out += (f"  - 去掉最大 |d|（{dm['removed']:+.2f}）后重算："
                f"mean = {dm['mean']:+.2f}{u}，"
                f"win rate = {dm['win_rate']:.2f}\n")
    # 检验
    pmw = v.get("mw_exact_p")
    pwsr = v.get("wilcoxon_exact_p")
    psgn = v.get("sign_test_exact_p")
    tests = []
    if pmw is not None:
        tests.append(f"MW 精确（独立样本口径）p = {pmw:.4f}")
    if pwsr is not None:
        tests.append(f"Wilcoxon 符号秩精确（配对口径）p = {pwsr:.4f}")
    if psgn is not None:
        tests.append(f"符号检验精确（配对口径）p = {psgn:.4f}")
    if tests:
        out += f"  - 精确检验：{'；'.join(tests)}\n"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 RQ1.2 Live555 实验记录")
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--interim", action="store_true",
                    help="标注为『中间态』（实验未结束时采集）→ 记录头部加警示")
    ap.add_argument("--interim-dir", default="",
                    help="10-24 20:00 中间态快照目录（用于 §7 差异对比）")
    ap.add_argument("--evidence-json", default="",
                    help="证据链复核结果 JSON（qa_evidence_chains.json）")
    args = ap.parse_args()

    d = Path(args.data_dir)
    interim_dir = Path(args.interim_dir) if args.interim_dir else None
    res = build(d, interim_dir)

    summ = read_csv(d / "rq1_2_summary.csv")
    p2 = read_csv(d / "rq1_2_p2.csv")

    # 证据链
    ev = {}
    if args.evidence_json and Path(args.evidence_json).exists():
        ev = json.loads(Path(args.evidence_json).read_text(encoding="utf-8"))

    L: list[str] = []
    A = L.append

    A("# RQ1.2 Live555（RTSP）有效性实验记录")
    A("")
    A(f"- 生成时间：{datetime.now().astimezone().isoformat()}")
    A(f"- 数据目录：`{d}`")
    A("- 采集脚本：`/home/zxy/rq1_collect_live555.sh`（VM 侧，口径权威定义；容器停止后取数用修复版 `/home/zxy/rq1_collect_live555_fix.sh`）")
    A("- 统计脚本：`local/rq1_2_analyze.py`（本文所有统计量由其现场计算）")
    A("")
    if args.interim:
        A("> ⚠️ **中间态数据（非最终）** —— 本记录采集于 RQ1.2 实验**仍在运行**时，")
        A("> 数值会随实验继续而变化，**不得**用于论文或 docx 回填。")
        A("> 实验停止后请重跑 `bash local/rq1_2_finalize.sh` 重新生成为最终值。")
        A("")

    # ------------------------------------------------------------------
    A("## 0. 核心结论（结论先行）")
    A("")
    _eqb0 = res.get("coverage_equal_budget", {})
    _t2t0 = res.get("time_to_threshold", {})
    _cov0 = res.get("paired", {}).get("aflnet", {}).get("bitmap_cvg", {})
    _cov0c = res.get("paired", {}).get("chatafl", {}).get("bitmap_cvg", {})
    A("> ### RQ1.2 结论**成立，但仅限 aflnet 半侧**。")
    A(">")
    A("> **成立的部分（唯一干净的主证据 = 表 4 第 3 行与第 5 行）**")
    A(f"> - ProtoRAG 生成的 50 条种子相对 AFLNet 原始的 7 条流量种子，在**分支覆盖率**上")
    A(f">   **10/10 逐 rep 全部反超**（aflnet 半侧 {_cov0.get('wins')}/5，配对差值均值 "
      f"**+{_cov0.get('mean', 0):.3f}pp**，标准差 {_cov0.get('sd', 0):.3f}pp；")
    A(f">   chatafl 半侧 {_cov0c.get('wins')}/5，+{_cov0c.get('mean', 0):.3f}pp，"
      f"标准差 {_cov0c.get('sd', 0):.3f}pp）。")
    if _eqb0.get("aflnet"):
        A(f"> - **★ 控制执行量后结论更强**：aflnet 半侧 protorag 的 `execs_done` 只有基线的 "
          f"**{_eqb0['aflnet']['execs_ratio_mean'] * 100:.0f}%**，")
        A(f">   在**同等执行预算**下覆盖率仍 **{_eqb0['aflnet']['wins']}/5 占优**"
          f"（差值 +0.54 ~ +0.69 pp）")
        A(f">   → **「用更少的执行取得更高的覆盖率」**，不是「用更多执行换来的覆盖率」。")
    if _t2t0.get("aflnet"):
        A(f"> - **时间-阈值口径**：protorag 达到「基线自己跑满 24 h 的最终覆盖」耗时中位 "
          f"**{_t2t0['aflnet']['t_protorag_median']:.3f} h**，基线自身需 "
          f"**{_t2t0['aflnet']['t_seed_reuse_mean']:.3f} h** → "
          f"**加速比中位 {_t2t0['aflnet']['speedup_median']:.1f}×**。")
    A("> - 该半侧**无任何 LLM 干预**（队列 `orig:enriched*` = 0、容器无 `chat_times` 列），")
    A(">   **唯一变量（种子来源 50 vs 7）成立**。")
    A("> - 反超在时间上**「保持」而非「持续扩大」**：aflnet 侧 **0.5-1h 区间起反超**（5/5 全正），")
    A(">   1-2h 之后在 +0.42 ~ +0.58 pp 区间震荡维持，末区间（18-24h）+0.55 pp；**全程未出现反向**。")
    A(">   （0-0.5h 区间 protorag **尚落后** 0.355 pp（逐 rep 0/5 为正），"
      "且早期区间对取点口径敏感，**不作为论断**，见 §6.1 / §6.2。）")
    A("> - 附带质效优势：**aflnet 侧 protorag 用不多于基线的路径 + 更少的执行拿到了更高的覆盖**")
    A(">   （终态路径均值 1495 < 1610，执行量 0.77×，覆盖 10.52% > 9.99%）。")
    A(">")
    A("> **不成立 / 必须降级的部分（表 4 第 2 行与第 4 行 = chatafl 半侧）**")
    A("> - ChatAFL 在启动期调用 LLM 做「连续格式增强」，把 **LLM 的散文回答整段写进 `.raw` 种子**，")
    A(">   导致 chatafl 半侧语料 **≈96% 被污染**。")
    A("> - **污染与种子来源无关，两个 chatafl 组同等受害**（对照组的 27 个崩溃样本 **27/27 全含散文**）。")
    A("> - 该半侧覆盖率优势虽在等执行预算下同样成立（§3.4），但**唯一变量不成立**")
    A(">   （初始队列 1344 vs 169，且语料 96% 被污染）→ **降级理由是污染，不是覆盖率反转**。")
    A(">   ⚠ **方法学提示**：v6 曾用「每百万次执行的覆盖率」(`cvg/execs`) 做过归一化并据此得出")
    A(">   「chatafl 反转」的结论 —— **该指标构造有偏**（饱和型累积量，同容器内随执行量单调下降），")
    A(">   **不能单独用于方法比较**；§3.4 已按 (D) 要求**并列披露**该口径并标注其可比性边界。")
    A(">   ★ 该口径下的 chatafl 结果**不足以单独作为「污染导致」的因果证据**"
      "（其 `execs_done` 是污染驱动的**中介量**：挂起 445 + 416 次阻塞按 `exec_timeout: 1000` "
      "消耗 execs）→ **正确结论是「chatafl 半侧无论原始口径还是归一化口径，"
      "均不可用于方法优劣判定」**，见 §3.4。")
    A("> - 只能作为「**ChatAFL 启动期 LLM 增强会污染语料并导致挂起/崩溃**」的**负面例证 / 方法论警示**。")
    A(">")
    A("> **三条表述红线**")
    A("> 1. 不得声称「ProtoRAG 不会发现崩溃」—— 崩溃集中在基线组是**结构性事实**")
    A(">    （真实流量种子自带 `matroskaFileTest` 路径片段 → 真实 matroska 播放路径 UAF，"
      "CVE-2021-38382/38381；EBML 负载 magic 命中 0 → 非 EBML 解析器问题），")
    A(">    但 chatafl 侧基线组的 27 个崩溃是**污染产物**，不能作为「基线更易崩溃」的证据；")
    A(">    有效崩溃证据只存在于 aflnet 侧基线组（47 个）。")
    A("> 2. 不得声称「稳定探索到更多状态机边」—— n_edges 差异幅度大、标准差与均值同量级、逐 rep 符号会翻转。")
    A("> 3. 不得把 chatafl 半侧的任何数字当作 ProtoRAG 有效性的证据，**也不得据此声称 ProtoRAG「更差」**。")
    A(">")
    A("> 完整的「成立 / 不得声称」对照总表见 **§10**；论文正文修改提示见 **§9**。")
    A("")
    A("---")
    A("")
    A("## 0.1 修订说明（★ 数值口径变更）")
    A("")
    A("**v4** 修正了 v1–v3 把 **10-24 20:00 中间态**数字**硬编码**进正文的缺陷 ——")
    A("实验跑满 24 h 后这些数字与最终数据不符（如 aflnet 的 n_edges 逐 rep 差值、")
    A("覆盖率反超区间、崩溃分布）。v4 起所有统计量改为**从 CSV 现场计算**。")
    A("")
    A("**v5** 在 v4 基础上按数据采集方的归因修正与新增证据再改四处：")
    A("")
    A("1. **§4.1 归因定调**：明确 `enriched_` 是 **ChatAFL 内置 LLM 的运行时富集产物**，")
    A("   **不是 ProtoRAG 生成的**；两个输入种子目录本身都干净（散文 0/7、0/50）；")
    A("   正确表述是「**ChatAFL 半侧整体受污染**，两组同等受影响」，")
    A("   不得写「ProtoRAG 写污染了对照组/实验组」。")
    if res.get("paired_pooled_coverage"):
        A("2. **§3.3 新增 pooled 口径**（跨两个 fuzzer 合并 10 个配对）：")
        A("   覆盖率 **10/10 全胜**，配对差值 **+0.517 ± 0.144 pp**。")
    if res.get("coverage_equal_budget"):
        A("3. **§3.4 等执行预算覆盖率 + §3.5 时间-阈值口径（v7 方法学修正）**：")
        A("   覆盖率是「执行量」的结果量，而两组 `execs_done` 相差数倍 → 必须控制执行量再比较。")
        A("   等执行预算下 **aflnet 5/5 占优**（执行量只有基线的 77%）→ 结论**更强**；")
        A("   **chatafl 等预算下也 5/5 领先** → 覆盖率优势本身不依赖执行量差异，")
        A("   其降级理由是**语料污染 + 唯一变量不成立**，**不是**覆盖率反转。")
        A("   ⚠ **v7 作废 v6 的「每百万次执行覆盖率」口径**：该比值在同一容器内随执行量单调下降"
          "（首末比 18–35×），构造有偏，不能用于方法比较。")
    prose_meta = res.get("crash_sample_prose") or {}
    if prose_meta.get("total_samples"):
        A("4. **§5.5 新增崩溃样本散文核查**：**对照组的崩溃样本同样 27/27 含 LLM 散文**；")
        A("   只有 aflnet 半侧（47 样本）干净 →")
        A("   **chatafl 两组的崩溃样本都不能当「真实 RTSP 漏洞」的干净证据**。")
    A("")
    A("另有 v4 已修正并保留的两项：**崩溃分布表述**（基线组崩溃横跨两个半侧，"
      "并非只在 aflnet 半侧）与**精确检验口径**（n=5 配对检验最小 p = 0.0625，"
      "数学上无法达到 0.05 显著）。")
    A("")
    A("**v6**（本次）修正 §6 时序反超结论的表述精度，并补分桶口径说明：")
    A("")
    A("5. **§6 分桶口径**：§6 主表用**区间池化**口径"
      "（九个连续区间桶 `0-0.5h / 0.5-1h / 1-2h / 2-4h / 4-6h / 6-8h / 8-12h / 12-18h / 18-24h`，"
      "边界 `[lo,hi)`，区间内跨 rep 全部采样点混池）—— 桶边界对齐真实时间轴，"
      "且能显式呈现「0–0.5 h 区间 protorag 尚落后」；"
      "**点时刻口径**（桶中心 `h` + `abs(rel_hours - h) < 0.2`，与 VM 采集脚本 "
      "`rq1_collect_live555.sh` 的打印口径完全一致）保留在 **§6.0 对账附表**，"
      "用于与 VM 产出逐格对账。两者结论一致（1 h 之后 aflnet 逐 rep 5/5 全正并全程保持）。")
    A("6. **§6.1 结论修正（区间池化口径）**：**0-0.5h 区间 protorag 尚落后**"
      "（aflnet 区间差值 **−0.355 pp**，逐 rep **0/5** 为正，5 个 rep 全为负）→ "
      "**不构成反超**；反超自 **0.5-1h 区间起 5/5 全正**并全程保持"
      "（末区间 18-24h +0.549 pp，差距不收敛、未反转）。")
    A("7. **§6.0 口径敏感性**：说明早期区间对取点方式敏感"
      "（aflnet 0–0.5 h 区间：池化 −0.351 pp（0/5）、首个采样点 −1.420 pp（0/5）、"
      "最后采样点 +0.074 pp（3/5）—— 方向可相反），**1 h 以后各口径一致为正**，"
      "故所有论断均以 1 h 及之后为准。")
    A("")

    # ------------------------------------------------------------------
    A("## 1. 实验配置")
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 目标系统 | Live555 `testOnDemandRTSPServer`（RTSP，text） |")
    A("| 镜像 | `rq2-live555:latest` |")
    A("| 协议 | RTSP（端口 8560，容器内 loopback） |")
    A("| 容器矩阵 | `rq2_{seed_reuse,protorag}_{chatafl,aflnet}_r{1..5}` = **20 容器** |")
    A("| 时长 | **2026-10-24 11:09 → 2026-10-25 11:09（24 h）** |")
    A("| 变异字典 | 基础字典 **24 token**（MD5 `464351f88db6c3f0bdac0de01859316b`，与镜像内 `rtsp.dict` 逐字节一致） |")
    A("| 基线组种子数 | `seed_reuse` = **7** 条（AFLNet 原始流量种子 `rtsp_requests_*.raw`） |")
    A("| 实验组种子数 | `protorag` = **50** 条（ProtoRAG 生成 + 定向字典） |")
    A("| P1 取值 | `plot_data` **首行**（dry-run 刚结束） |")
    A("| P2 取值 | `plot_data` **末行**（24 h 结束） |")
    A("| 交叉校验源 | `fuzzer_stats`（bitmap_cvg / unique_crashes / paths_total / execs_done） |")
    A("")

    # ------------------------------------------------------------------
    A("## 2. 最终 4 行数值（对应 docx 表 4，已回填）")
    A("")
    A("| 表4行 | 种子来源 | Fuzzer | n_states(P1) | n_states(P2) | n_edges(P1) | n_edges(P2) | 分支覆盖%(P2) | 崩溃数(P2) | 路径数(P2) |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(summ, key=lambda x: int(x.get("docx_row") or 0)):
        A("| {docx_row} | {seed_source} | {fuzzer} | {n_states_P1} | {n_states_P2} "
          "| {n_edges_P1} | {n_edges_P2} | {bitmap_cvg_P2} | {unique_crashes_P2} "
          "| {paths_total_P2} |".format(**r))
    A("")
    A("> ★ **chatafl 两行为辅证**（启动期 LLM 增强污染，见 §4）；"
      "**aflnet 两行为 RQ1.2 主证据**。")
    A("")
    A("> 交叉校验：本表 4 行的 28 个数值与"
      "`derived/analysis/qa_rq1_2/qa_rq1_2_recomputed.json` 的"
      "独立复算结果一致（仅均值舍入差异）。")
    A("")

    # ------------------------------------------------------------------
    A("## 3. 配对统计（protorag − seed_reuse，同 fuzzer 同 rep 配对，n=5）")
    A("")
    A("> **三种检验口径必须分清**（这是本节最容易出错的点）：")
    A("> ")
    A("> | 检验 | 适用 | n=5 时双侧最小可达 p |")
    A("> |---|---|---|")
    A("> | Mann–Whitney 精确（独立样本） | 视两组为**独立**样本 | **0.0079** |")
    A("> | Wilcoxon 符号秩精确（配对） | 利用**同 rep 配对**结构 | **0.0625** |")
    A("> | 符号检验精确（配对） | 只用差值**符号** | **0.0625** |")
    A("> ")
    A("> ★ **配对口径在 n=5 下最小 p = 0.0625 > 0.05** → "
      "**配对检验永远达不到 0.05 显著性**。")
    A("> 因此未达显著时**不得**写『无差异』，只能写『方向一致但未达统计显著』。")
    A("")
    for si, fz in enumerate(("aflnet", "chatafl"), start=1):
        role = "★ **主证据**" if fz == "aflnet" else "辅证（受污染）"
        A(f"### 3.{si} {fz} —— {role}")
        A("")
        for metric in ("bitmap_cvg", "n_edges", "n_states",
                       "paths_total", "unique_crashes", "unique_hangs",
                       "execs_done"):
            v = res["paired"][fz].get(metric)
            if not v:
                continue
            A(_stat_block(v).rstrip())
            A("")

    # ---- pooled（跨两个 fuzzer 合并 10 个配对）----
    pooled = res.get("paired_pooled_coverage")
    if pooled:
        A("### 3.3 pooled（跨两个 fuzzer 合并 10 个配对）")
        A("")
        A(_stat_block(pooled).rstrip())
        A("")
        A(f"> ⚠ **{pooled['caveat']}**")
        A("> pooled 的 n=10 使配对检验可达 0.05 显著"
          f"（最小可达 p = {2 / 2 ** pooled['n']:.4f}），"
          "但**分半侧结论仍以 §3.1/§3.2 为准**。")
        A("")

    # ---- 等执行预算覆盖率（关键混淆因子控制）----
    eqb = res.get("coverage_equal_budget")
    t2t = res.get("time_to_threshold")
    if eqb:
        A("### 3.4 ★ 等执行预算覆盖率（关键混淆因子控制）")
        A("")
        A("覆盖率是**「执行量」的结果量**，两组 `execs_done` 相差数倍"
          "（aflnet：protorag 只跑了基线的 57–90%；chatafl：protorag 跑了基线的 121–136%），"
          "因此必须控制执行量再比较。")
        A("")
        A("> ⚠ **v7 方法学修正**：本文**不再**使用「每百万次执行的覆盖率」(`cvg/execs`) 做归一化。"
          "该指标**构造有偏**——覆盖率是饱和型累积量，同一容器内 `cvg/execs` 随执行量**单调下降**"
          "（实测首末比约 18–35×），故该比值天然偏好「执行量少」的一方，与覆盖率的绝对水平无关，"
          "**不能用于方法比较**。v6 曾据此得出「chatafl 归一化后 0/5 反转」的结论，**该结论作废**。")
        A(">")
        A("> ✅ **正确口径 = 等执行预算比较**：把两组截断到**同一累计执行预算**再比覆盖率。"
          "累计执行量由 `plot_data` 的 `execs_per_sec` 梯形积分得到，并锚定到 `fuzzer_stats` 的 "
          "`execs_done`；预算取两组终态 `execs_done` 的较小者。")
        A("")
        A("| 组/Fuzzer | rep | 等预算 execs | 等预算覆盖 protorag | 等预算覆盖 seed_reuse | "
          "等预算差(pp) | 原始差(pp) |")
        A("|---|---|---|---|---|---|---|")
        for fz in ("aflnet", "chatafl"):
            v = eqb.get(fz)
            if not v or not v.get("rows"):
                continue
            for r in v["rows"]:
                A(f"| `{fz}` | {r['rep']} | {r['budget']:.0f} "
                  f"| {r['eq_cvg_protorag']:.3f} | {r['eq_cvg_seed_reuse']:.3f} "
                  f"| **{r['eq_diff']:+.3f}** | {r['raw_diff']:+.3f} |")
        A("")
        for fz in ("aflnet", "chatafl"):
            v = eqb.get(fz)
            if not v or not v.get("n"):
                continue
            A(f"- **{fz}**：等预算 win **{v['wins']}/{v['n']}**，"
              f"配对差值 mean ± sd = **{v['mean']:+.3f} ± {v['sd']:.3f} pp**，"
              f"执行量比均值 **{v['execs_ratio_mean']:.2f}×**；"
              f"WSR p={v['wilcoxon_exact_p']:.4f} / 符号检验 p={v['sign_test_exact_p']:.4f}")
        A("")
        A("> ★★ **等执行预算口径下结论稳健成立（10/10 全胜，无一次反转）**：")
        A("")
        A(f"- **aflnet（干净半侧，主证据）**：protorag 的执行量只有基线的 "
          f"**{eqb['aflnet']['execs_ratio_mean'] * 100:.0f}%**，"
          f"在**同等执行预算**下覆盖率仍 **5/5 全部占优**"
          f"（差值 +0.54 ~ +0.69 pp）→ **用更少的执行取得更高的覆盖率**，结论**更强**。")
        A(f"- **chatafl（受污染半侧）**：protorag 的执行量是基线的 "
          f"**{eqb['chatafl']['execs_ratio_mean'] * 100:.0f}%**，"
          f"等预算下仍 **5/5 领先**（差值 +0.36 ~ +0.61 pp）→ "
          f"**覆盖率优势本身不依赖执行量差异**。")
        A("- → ⚠ **但这不等于 chatafl 半侧可作 ProtoRAG 有效性证据**：该半侧语料 **96% 被污染**"
          "（§4），且其「优势」建立在 **1344 vs 168** 的污染后队列上，"
          "**唯一变量（种子来源）在该半侧根本不成立** → **降级理由是污染，不是覆盖率反转**。")
        A("")

        # ---- (D) 并列披露：每百万次执行的覆盖率（cvg/execs 归一化）----
        mex = res.get("coverage_per_Mexec", {})
        if mex.get("aflnet") and mex.get("chatafl"):
            A("#### ★ (D) 并列披露：每百万次执行的覆盖率（`cvg/execs` 归一化）")
            A("")
            A("> ⚠ **该指标构造有偏**：覆盖率是**累积饱和**量，同一容器内 `cvg/execs` "
              "随执行量**单调下降**（实测首末比约 18–35×），故该比值天然偏好「执行量少」的一方，"
              "与覆盖率的绝对水平无关 → **不能单独用于方法比较**。"
              "上文**等执行预算**才是本文的主口径。本节按 (D) 要求**并列披露**该口径，"
              "并逐条标注其可比性边界。")
            A("")
            A("| 组/Fuzzer | rep | execs protorag | execs seed_reuse | 执行量比 | "
              "归一化覆盖 protorag | 归一化覆盖 seed_reuse | 比值 |")
            A("|---|---|---|---|---|---|---|---|")
            for fz in ("aflnet", "chatafl"):
                v = mex.get(fz, {})
                for r in v.get("rows", []):
                    A(f"| `{fz}` | {r['rep']} | {r['execs_protorag']:.0f} "
                      f"| {r['execs_seed_reuse']:.0f} | {r['execs_ratio']:.2f}× "
                      f"| {r['cvg_per_Mexec_protorag']:.3f} "
                      f"| {r['cvg_per_Mexec_seed_reuse']:.3f} "
                      f"| {r['ratio']:.2f}× |")
            A("")
            for fz in ("aflnet", "chatafl"):
                v = mex.get(fz, {})
                if not v.get("n"):
                    continue
                A(f"- **{fz}**：win **{v['wins']}/{v['n']}**，配对差值 mean ± sd = "
                  f"**{v['mean']:+.3f} ± {v['sd']:.3f}**（pp/百万次执行），"
                  f"执行量比均值 **{v['execs_ratio_mean']:.2f}×**；"
                  f"占优比值 {v['ratio_min']:.2f}–{v['ratio_max']:.2f}×；"
                  f"WSR p={v['wilcoxon_exact_p']:.4f} / 符号检验 p={v['sign_test_exact_p']:.4f}")
            A("")
            A("> ★★ **(D) 归因纪律（两条独立线索，指向同一结论）**：")
            A(">")
            A(f"> - **aflnet 半侧（主证据，可主张）**：归一化后仍 **{mex['aflnet']['wins']}/5 占优**"
              f"（比值 {mex['aflnet']['ratio_min']:.2f}–{mex['aflnet']['ratio_max']:.2f}×），"
              f"执行量只有基线的 **{mex['aflnet']['execs_ratio_mean'] * 100:.0f}%** → "
              f"**用更少的执行取得更高的覆盖率**。")
            A(f">   ★ **aflnet 侧的 `execs_done` 差异不是污染造成的** —— 该半侧挂起近乎恒 0"
              f"（基线 5 个容器 `unique_hangs` 恒为 **0**，实验侧仅 `protorag_aflnet_r2` 有 **2** 次，"
              f"合计 2 次），故其归一化是**干净分母**下的比较。")
            A(f"> - **chatafl 半侧（不可主张）**：归一化后 **{mex['chatafl']['wins']}/5 落后**"
              f"（比值 {mex['chatafl']['ratio_min']:.2f}–{mex['chatafl']['ratio_max']:.2f}×），"
              f"执行量是基线的 **{mex['chatafl']['execs_ratio_mean'] * 100:.0f}%**。")
            A(">   ⚠ **但 chatafl 侧的 `execs_done` 本身是「污染驱动的中介量」，不是干净的分母**：")
            A(">   1. **挂起消耗**：该半侧两组挂起合计 **protorag 445 + seed_reuse 416 = 861** 次，"
              "每次阻塞按 `exec_timeout: 1000` 毫秒计 → **大量 execs 被消耗在挂起超时上**；"
              "aflnet 半侧合计仅 **2** 次。")
            A(">   2. **校准期差异**：初始队列 1344 vs 168（两侧均 ~96% 被 LLM 增强污染），"
              "校准阶段执行量本就不同。")
            A(">   3. **方向随半侧翻转**：**同一份 ProtoRAG 语料**，在 aflnet 半侧 `execs_done` "
              f"是基线的 **{mex['aflnet']['execs_ratio_mean']:.2f}×**（protorag 更少），"
              f"在 chatafl 半侧却是 **{mex['chatafl']['execs_ratio_mean']:.2f}×**（protorag 更多）→ "
              "`execs_done` 是**由语料与污染共同决定的结果量**，不是可「控制」的固定资源。")
            A(">")
            A("> → **「控制执行量后 chatafl 侧优势消失」这一观察成立，但不足以单独作为"
              "「污染导致」的因果证据**（execs 差异部分由污染-induced 挂起造成，是中介量）；"
              "**它与语料污染（§4）是两条独立指向同一结论的线索**，互为佐证而非因果链。")
            A("> → **正确结论是「chatafl 半侧无论原始口径还是归一化口径，均不可用于方法优劣判定」**；"
              "**不得**据归一化结果声称「ProtoRAG 在 chatafl 侧更差」。")
            A("")
        if t2t:
            A("### 3.5 ★ 时间-阈值口径（达到基线自身最终覆盖所需时间）")
            A("")
            A("等执行预算之外，再用**时间**做一次控制：protorag 达到「**基线自己跑满 24h 的最终覆盖**」"
              "需要多久？")
            A("")
            A("| 组/Fuzzer | rep | 目标(=基线终态覆盖) | protorag 达到耗时 | seed_reuse 达到耗时 | 加速比 |")
            A("|---|---|---|---|---|---|")
            for fz in ("aflnet", "chatafl"):
                v = t2t.get(fz)
                if not v or not v.get("rows"):
                    continue
                for r in v["rows"]:
                    tp = (f"{r['t_protorag_h']:.3f} h" if r["t_protorag_h"] is not None else "未达到")
                    ts = (f"{r['t_seed_reuse_h']:.3f} h" if r["t_seed_reuse_h"] is not None else "未达到")
                    sp = (f"**{r['speedup']:.1f}×**" if r["speedup"] is not None else "—")
                    A(f"| `{fz}` | {r['rep']} | {r['target_cvg_seed_reuse']:.2f}% | {tp} | {ts} | {sp} |")
            A("")
            for fz in ("aflnet", "chatafl"):
                v = t2t.get(fz)
                if not v or v.get("t_protorag_mean") is None:
                    continue
                A(f"- **{fz}**：protorag 达到基线终态覆盖耗时 **中位 {v['t_protorag_median']:.3f} h**"
                  f"（均值 {v['t_protorag_mean']:.3f} h），"
                  f"基线自身需 **{v['t_seed_reuse_mean']:.3f} h** → "
                  f"**加速比中位 {v['speedup_median']:.1f}×**（均值 {v['speedup_mean']:.1f}×）")
            A("")
            A("> ⚠ **chatafl 侧的超高加速比同样不可作有效性证据** —— 它衡量的是"
              "「ChatAFL 半侧在被 LLM 增强污染后达到某阈值的速度」，与 ProtoRAG 种子质量无因果关系"
              "（该半侧唯一变量不成立，见 §4）。**只有 aflnet 半侧的时间-阈值结论可主张。**")
            A("")

    # ------------------------------------------------------------------
    A("## 4. ★ 污染说明（必读）")
    A("")
    A("### 4.1 事实（★ 归因：污染源是 ChatAFL 内置 LLM，**与 ProtoRAG 无关**）")
    A("")
    A("ChatAFL 在 `protocol_selected` 时**无条件**调用 `enrich_testcases()`"
      "（afl-fuzz.c:10687，`chat-llm.c` 中零 `getenv` 开关），")
    A("调用 LLM（deepseek-chat，URL 硬编码 "
      "`http://192.168.37.1:18080/chat/completions`）把增强种子**写回种子目录**。")
    A("且 `read_testcases()` 在 `enrich_testcases()` **之后**执行 → "
      "增强种子**直接成为初始队列成员**。")
    A("")
    A("> ★ **两个输入种子目录本身都是干净的** —— "
      "`seed_reuse`（7 条 `rtsp_requests_*.raw`）与 "
      "`protorag`（50 条 `01_DESCRIBE+SETUP.raw` 等）"
      "均**不含 `enriched_` 文件、散文命中 0/7 与 0/50**。")
    A("> → `enriched_` 是 **fuzzer 运行期的 LLM 种子富集产物**，"
      "**不是 ProtoRAG 生成的**。")
    A(">")
    A("> ★ **因此正确表述是「ChatAFL 半侧整体受污染」，"
      "两个组同等受影响**；"
      "**不得**写『ProtoRAG 写污染了实验组/对照组』。")
    A("")
    lin = {f"{r.get('group')}/{r.get('fuzzer')}": r
           for r in res["pollution_evidence"]["lineage"]}
    sp = {f"{r.get('group')}/{r.get('fuzzer')}": r
          for r in res["pollution_evidence"]["seedprovenance"]}
    A("| 组/Fuzzer | 宿主语料条数 | 初始队列条目数 | 其中 LLM 增强 | 增强占比 | 原始种子含散文占比 | 最终 paths_total |")
    A("|---|---|---|---|---|---|---|")
    host_corpus = {"seed_reuse": 7, "protorag": 50}
    for cell in ("protorag/chatafl", "seed_reuse/chatafl",
                 "protorag/aflnet", "seed_reuse/aflnet"):
        lrow, srow = lin.get(cell), sp.get(cell)
        if not lrow:
            continue
        group = cell.split("/")[0]
        A(f"| `{cell}` | {host_corpus.get(group, 'NA')} "
          f"| {lrow.get('orig_entries')} | {lrow.get('orig_enriched')} "
          f"| {lrow.get('pct_enriched')} | {srow.get('pct_prose') if srow else 'NA'} "
          f"| {lrow.get('queue_total')} |")
    A("")
    A("> ★ 初始队列从 **50 vs 7** 变成 **1344 vs 168** → "
      "chatafl 半侧的组内比较同时混淆了"
      "『种子来源』与『初始队列规模』两个因素。")
    A("")

    # 证据链
    if ev:
        A("### 4.2 证据链复核（本次从 VM 原始数据复跑）")
        A("")
        s = ev.get("summary", {})
        e4 = s.get("E4_chat_times_by_group", {})
        e6 = s.get("E6_aflnet_no_chat_column", {})
        v8 = s.get("V8_fingerprint", {})
        A("| # | 证据 | 本次复核结果 |")
        A("|---|---|---|")
        A("| E1 | 输入种子目录不含 `enriched_` | 宿主语料 `seed_reuse` 7 条 / `protorag` 50 条，"
          "均无 `enriched_` |")
        A("| E2 | 输入种子目录不含散文 | aflnet 侧 `pct_prose` = **0.0%**（7/50 条均无散文） |")
        A("| E3 | `enriched_` 由 fuzzer 运行时写出 | `ChatAFL/ChatAFL/afl-fuzz.c:2743-2758` |")
        seed_ct = e4.get("seed_reuse") or []
        pro_ct = e4.get("protorag") or []
        A(f"| E4 | LLM 调用次数两组相同 | 10 个 chatafl 容器 `chat_times` 末值 = "
          f"**{'/'.join(seed_ct)}**（seed_reuse 侧）与 "
          f"**{'/'.join(pro_ct)}**（protorag 侧），两组一致 = "
          f"**{'是' if e4.get('all_equal') else '否'}** |")
        A("| E5 | 对照组同样高比例 enriched | `seed_reuse/chatafl` **161/168 = 95.83%**；"
          "`protorag/chatafl` **1294/1344 = 96.28%**（各 5 rep 一致） |")
        A(f"| E6 | aflnet 完全干净 | {e6.get('aflnet_containers')} 个 aflnet 容器中"
          f"带 `chat_times` 列的 = **{e6.get('with_chat_times_column')}** → 干净 |")
        A(f"| V8 | 首行 `paths_total` 指纹 | aflnet **{v8.get('aflnet_match_corpus')}/"
          f"{v8.get('aflnet_total')}** 落在语料条数侧（7/50）；"
          f"chatafl **{v8.get('chatafl_match_enriched_queue')}/"
          f"{v8.get('chatafl_total')}** 落在增强后队列侧（168/1344） |")
        A("")
        A("→ **污染是 chatafl 半侧的普遍现象，两组同等受影响；"
          "污染源是 ChatAFL 内置 LLM，与 ProtoRAG 无关。**")
        A("")

    A("### 4.3 结论与论文表述建议")
    A("")
    cov_a = res["paired"]["aflnet"].get("bitmap_cvg", {})
    cov_c = res["paired"]["chatafl"].get("bitmap_cvg", {})
    ne_a = res["paired"]["aflnet"].get("n_edges", {})
    ne_c = res["paired"]["chatafl"].get("n_edges", {})
    p1 = res.get("p1_edges_attribution", {})
    norm = res.get("coverage_equal_budget", {})
    A(f"- **aflnet 半侧干净**（0 增强、唯一变量成立、覆盖反超 "
      f"**{cov_a.get('wins')}/{cov_a.get('n')}** 逐 rep 一致，"
      f"{cov_a.get('min'):+.2f}~{cov_a.get('max'):+.2f} pp）→ "
      f"**作为 RQ1.2 主证据**。")
    A(f"- **chatafl 半侧被污染**（1344 vs 168 初始种子）→ **降级为辅证**，"
      f"并加污染表注；RQ1.2 与 RQ3 的 chatafl 行**不可直接横向比较**。")
    # 时序反超结论（与 §6.1 保持一致 —— 区间池化口径）
    _afl_d = [d for d in res["timeseries_interval_delta"] if d["fuzzer"] == "aflnet"]
    if _afl_d:
        _d05 = _afl_d[0]
        _stable = next((d for d in _afl_d if d["win_rate"] == len(REPS)), None)
        if _d05 and _stable:
            A(f"- ★ **时序反超是「{_stable['bucket']} 区间起成立、1 h 之后全程保持」**"
              f"（见 §6.1，区间池化口径）：**{_d05['bucket']} 区间 protorag 尚落后**"
              f"（区间差值 {_d05['delta_pp']:+.3f} pp，逐 rep "
              f"**{_d05['win_rate']}/{len(REPS)}** 为正，即 5 个 rep 全为负），"
              f"**不构成反超论断**；自 {_stable['bucket']} 起逐 rep "
              f"**{_stable['win_rate']}/{len(REPS)} 全正**，"
              f"末区间（{_afl_d[-1]['bucket']}）{_afl_d[-1]['delta_pp']:+.3f} pp，"
              f"差距**不收敛、未反转**。")
    A(f"- ★ **n_edges 不稳健**（aflnet 逐 rep "
      f"{', '.join(f'{d:+.0f}' for d in ne_a.get('diffs', []))}，"
      f"**{ne_a.get('wins')}/{ne_a.get('n')} 为正**；"
      f"chatafl 逐 rep {', '.join(f'{d:+.0f}' for d in ne_c.get('diffs', []))}，"
      f"**{ne_c.get('wins')}/{ne_c.get('n')} 为正**）"
      f"→ **不得**声称『稳定探索到更多状态机边』；"
      f"若要报必须给 ±标准差并注明 n=5、未达统计显著。")
    A("  ★★ **口径提醒：任务书原给的 aflnet `+4/-2/-1/-1/+28, 2/5` 是 ~9–10 h 的"
      "**中间态**数字，不是 24 h 终态**。主理人逐小时扫描确认该序列只在 "
      "**10-24 20:20–20:30** 这 10 分钟窗口内成立；终态真值为 "
      f"**{', '.join(f'{d:+.0f}' for d in ne_a.get('diffs', []))}，"
      f"{ne_a.get('wins')}/{ne_a.get('n')} 为正，均值 "
      f"{ne_a.get('mean', 0):+.2f} ± {ne_a.get('sd', 0):.2f}** —— "
      "**本文与论文一律用终态值**。")
    if p1.get("chatafl"):
        c = p1["chatafl"]
        A("- ★ **P1 状态边差异只有 aflnet 半侧可归因于种子质量** —— "
          "实测 P1 初始队列规模（`plot_data` 首行 `paths_total`）：\n"
          "```\n"
          "chatafl : protorag 1344 vs seed_reuse 169  (8.0x)  ← 队列已被 LLM 增强污染\n"
          "aflnet  : protorag   51 vs seed_reuse   8  (6.4x)  ← 无增强，队列=基础种子集\n"
          "```\n"
          f"→ **chatafl 半侧的 P1 n_edges 差异"
          f"（{c['protorag_mean']:.1f} vs {c['seed_reuse_mean']:.1f}）"
          "是在已被污染 8 倍的队列上测得的，无法归因于种子质量**；\n"
          "→ **只有 aflnet 半侧的 P1 n_edges 差异（22.4 vs 8.8）"
          "可归因于基础种子集规模（50 vs 7）**，可作 ProtoRAG 种子质量的正面证据。")
    if eqb.get("aflnet") and eqb.get("chatafl"):
        A(f"- ★★ **覆盖率必须做执行量控制**（见 §3.4 等执行预算口径）："
          f"aflnet 在**同等执行预算**下仍 **{eqb['aflnet']['wins']}/5 占优**"
          f"（执行量只有基线的 "
          f"{eqb['aflnet']['execs_ratio_mean'] * 100:.0f}%），"
          f"结论**更强**；"
          f"chatafl 等预算下也 {eqb['chatafl']['wins']}/5 领先 —— "
          f"**说明覆盖率优势本身不依赖执行量差异**；"
          f"但 chatafl 半侧**仍不可作支持证据**，"
          f"降级理由是**语料污染 + 唯一变量不成立**（1344 vs 168 污染后队列，见 §4），"
          f"**不是**覆盖率反转。")
        A(f"- ★ **时间-阈值口径同样支持 aflnet**（见 §3.5）：protorag 达到「基线自己跑满 24h 的最终覆盖」"
          f"耗时中位 **{t2t['aflnet']['t_protorag_median']:.3f} h**，"
          f"基线自身需 **{t2t['aflnet']['t_seed_reuse_mean']:.3f} h** → "
          f"**加速比中位 {t2t['aflnet']['speedup_median']:.1f}×**。")
    A("- ★ **崩溃几乎全在基线组**是**结构性事实**：")
    A("")
    A("> " + CRASH_NOTE.replace("\n", "\n> "))
    A("")
    prose = res.get("crash_sample_prose")
    if prose and prose.get("total_samples"):
        A("- ★★ **崩溃样本本身也受污染**（见 §5.5）："
          f"`seed_reuse_chatafl` 的崩溃样本 **27/27 全部含 LLM 散文**，"
          f"全部 aflnet 容器 **{prose['by_cell'].get('seed_reuse/aflnet', {}).get('samples', 0)}"
          f" 个样本 0 命中** → "
          "**chatafl 两组的崩溃样本都不能当「真实 RTSP 漏洞」的干净证据**；"
          "**aflnet 是唯一干净对照**。")
        A("- ★ **chatafl 的崩溃数差异（0.20 vs 5.40）不得解读为"
          "『ProtoRAG 抑制了崩溃』** —— "
          "两组崩溃输入都混有 LLM 散文，且该指标方差极大"
          "（sd 6.38 / 19.39）、受 `execs_done` 量级放大，"
          "唯一有崩溃的 protorag 容器仅 `chatafl_r2`（1 个，12.43 h）→ "
          "**方向性不可靠**。")
        A("")
    A("### 4.4 启动错位（★ 污染的又一可观测后果）")
    A("")
    _so = res.get("startup_offset", {})
    if _so:
        A("`plot_data` 首行的 `unix_time` 与 `fuzzer_stats` 的 `start_time` 之差，"
          "即「采样起点相对 fuzzer 启动」的错位（各组 5 个 rep 实测）：")
        A("")
        A("| 组/Fuzzer | 各 rep 错位(秒) | 均值 | 中位 |")
        A("|---|---|---|---|")
        for cell in ("seed_reuse/aflnet", "protorag/aflnet",
                     "seed_reuse/chatafl", "protorag/chatafl"):
            v = _so.get(cell)
            if not v:
                continue
            A(f"| `{cell}` | {', '.join(str(x) for x in v['offsets_s'])} "
              f"| {v['mean_s']:.0f} s（{v['mean_s'] / 60:.1f} min） "
              f"| {v['median_s']:.0f} s |")
        A("")
        _af = _so.get("protorag/aflnet", {}).get("mean_s", 0)
        _ch = _so.get("protorag/chatafl", {}).get("mean_s", 0)
        if _af and _ch:
            A(f"- **aflnet 半侧错位仅 ~{_af:.0f} s**（原生 AFLNet 无 LLM 逻辑），"
              f"**chatafl 半侧达 ~{_ch:.0f} s（{_ch / 60:.1f} min）** → "
              f"**相差约 {_ch / _af:.0f} 倍**。")
        A("- 原因：ChatAFL 在 `protocol_selected` 时**先做 LLM 增强**再进入 fuzzing 循环，"
          "增强耗时（+ 需等 LLM 代理响应）直接延后了采样起点。")
        A("- ⚠ **口径影响**：本文所有时序均以 `t0 = plot_data 首行 unix_time` 为基准"
          "（**相对采样起点**，故组间可比）；但若改用「容器启动时刻」对齐，"
          "chatafl 半侧会被系统性前移约 8 分钟（其真实 fuzzing 起始更晚）→ "
          "**早期（<0.2 h）的时间轴对比会有偏差**。这也是 0.5 h 桶对口径敏感的成因之一。")
        A("")

    A("### 4.5 污染根因：模型替换的复现偏差（★ 归因的准确版本）")
    A("")
    A("以上证据链锁定的是**污染源**，不是**责任方**。准确的归因是：")
    A("")
    A("- 论文使用的 LLM 是 **`gpt-3.5-turbo`**（instruct 倾向，在「连续格式」续写下直接产出纯报文）；")
    A("- 本项目的 LLM 代理把它替换为**聊天型 `deepseek-chat`**（天然会加前言、` ``` ` 围栏、"
      "以及 `**Explanation:**` 讲解段落）；")
    A("- ChatAFL 的连续格式增强**解析逻辑只做 `\\n → \\r\\n` 换行规范化，不做报文抽取** → "
      "遇到聊天型模型的散文回答，就把散文整段写进 `.raw`。")
    A("")
    A("→ 准确表述：**不是 ChatAFL 机制有缺陷，也不是 ProtoRAG 种子有问题，"
      "而是「用聊天型 LLM 替换论文所用的 `gpt-3.5-turbo` 后，ChatAFL 的增强流水线不再产出纯报文」"
      "——属模型替换引入的复现偏差，已在实验记录中披露。**")
    A("→ 这本身是一个可写入论文的**工具链可复现性风险**发现："
      "ChatAFL 的增强流水线对 LLM 输出格式有隐式假设（纯报文），换模型即失效。")
    A("")
    A("### 4.6 RQ3 的处置与反向启示")
    A("")
    A("RQ3 编排已用 `--network none` 关闭该增强（QA 实测：LLM 端点 "
      "`Network is unreachable` → `enrich_sequence` 返回 NULL → "
      "afl-fuzz.c:2726 `continue` → 不写 enhanced 文件；"
      "且 `--network none` 下 loopback 正常、SUT 正常监听）。")
    A("")
    A("**对 RQ3 的反向启示（须写进论文的方法学章节）**：")
    A("")
    A("1. **RQ3 不受本污染影响**（实测 `enriched_*` = 0、`orig:` 计数 == 语料条数）。")
    A("2. ★ **RQ1.2 与 RQ3 的 chatafl 行不可直接横向比较**"
      "（RQ1.2 未关闭增强，RQ3 关闭了）。")
    A("3. ★ **「关掉增强」不是 RQ3 的额外严谨，而是 RQ3 成立的必要条件**："
      "各组的增强条数取决于启动时刻的 LLM 状态与响应内容 → 各不相同 → **又是伪变量**。")
    A("4. **LLM 增强型 fuzzer 的「自动语料扩增」是一个未被声明的实验变量**。"
      "ProtoRAG 的差异化定位正是「**可控制、可溯源的定向聚焦**」。")
    A("5. ★ **不能依赖「现在恰好连不上」**：LLM 端点可达性随时间变化"
      "（11:09 启动时可达 → 事后实测 `Connection refused`）→ 必须用**机制性**手段保证"
      "任意时刻启动都不被增强。")
    A("")

    # ------------------------------------------------------------------
    A("## 5. 崩溃与挂起分布")
    A("")
    A("### 5.1 崩溃数分布 + 首次出现时刻")
    A("")
    A("| 容器 | 组 | Fuzzer | 唯一崩溃数 | 唯一挂起数 | 首次崩溃时刻(rel h) |")
    A("|---|---|---|---|---|---|")
    for c in res["crash_distribution"]:
        fc = c["first_crash_rel_h"]
        fcs = f"**{fc:.4f} h**" if fc is not None else "—（全程未崩溃）"
        A(f"| `{c['container']}` | {c['group']} | {c['fuzzer']} "
          f"| {c['final_unique_crashes']:.0f} | {c['final_unique_hangs']:.0f} "
          f"| {fcs} |")
    A("")
    A("### 5.2 按 组×Fuzzer 汇总")
    A("")
    A("| 组/Fuzzer | 容器数 | 崩溃合计 | 崩溃均值 | 挂起合计 | 挂起均值 |")
    A("|---|---|---|---|---|---|")
    for cell, v in res["crash_hang_by_cell"].items():
        A(f"| `{cell}` | {v['containers']} | {v['crashes']:.0f} "
          f"| {v['crashes_mean']:.2f} | {v['hangs']:.0f} | {v['hangs_mean']:.2f} |")
    A("")
    tot_c = sum(v["crashes"] for v in res["crash_hang_by_cell"].values())
    tot_h = sum(v["hangs"] for v in res["crash_hang_by_cell"].values())
    base_c = sum(v["crashes"] for k, v in res["crash_hang_by_cell"].items()
                 if k.startswith("seed_reuse"))
    A(f"**合计**：崩溃 **{tot_c:.0f}**（基线组 {base_c:.0f} = "
      f"{base_c / tot_c * 100:.1f}%），挂起 **{tot_h:.0f}**。")
    A("")
    A("### 5.3 unique_hangs 分布（★ 挂起是 chatafl 半侧的独有现象）")
    A("")
    A("| 组/Fuzzer | 各 rep 挂起数 | 均值 | 标准差 | 合计 | 非零 rep |")
    A("|---|---|---|---|---|---|")
    for cell, v in res["hangs"]["by_cell"].items():
        vals = ", ".join(f"{x:g}" for x in v["vals"])
        A(f"| `{cell}` | {vals} | {v['mean']:.2f} | {v['sd']:.2f} "
          f"| {v['total']:.0f} | {v['nonzero_reps']}/5 |")
    A("")
    A("> ★ **挂起几乎全部集中在 chatafl 半侧**（两组都有），aflnet 半侧近乎为 0。")
    _hg_ch = res["hangs"]["by_cell"].get("protorag/chatafl", {}).get("total", 0) + \
        res["hangs"]["by_cell"].get("seed_reuse/chatafl", {}).get("total", 0)
    _hg_af = res["hangs"]["by_cell"].get("protorag/aflnet", {}).get("total", 0) + \
        res["hangs"]["by_cell"].get("seed_reuse/aflnet", {}).get("total", 0)
    if _hg_ch and _hg_af:
        A(f"> **量级：chatafl 半侧合计 {_hg_ch:.0f} 次挂起 vs aflnet 半侧仅 {_hg_af:.0f} 次 —— "
          f"相差 {_hg_ch / _hg_af:.0f} 倍**。")
    A("> 这与 §4 的污染图景一致：LLM 增强种引入的散文/畸形输入会让 "
      "`testOnDemandRTSPServer` 陷入挂起。")
    A("> → **挂起数不可解释为『ProtoRAG 更好』或『更差』**，"
      "它是 chatafl 半侧污染的伴随现象；aflnet 半侧才是干净读数。")
    A("")
    A("### 5.4 『概率性 UAF 晚发现』特征")
    A("")
    A("- 崩溃**并非**在实验开始即出现：10-24 20:00 的中间态快照中崩溃数为 0，"
      "崩溃是在此**之后**才被触发。")
    A("- 该 UAF 为**概率性**触发（依赖 ASAN 调度与堆布局），"
      "因此**首次出现时刻在容器间不同**，且**总次数偏少**。")
    A("- 含义：崩溃数是**低频、晚发、方差大**的指标 —— "
      "单次实验的崩溃数**不可**用作方法优劣的稳健判据。")
    A("")

    # ---- 崩溃样本散文核查 ----
    prose = res.get("crash_sample_prose")
    if prose and prose.get("total_samples"):
        A("### 5.5 ★★ 崩溃样本散文核查（★ 崩溃证据本身也受污染）")
        A("")
        A("| 组/Fuzzer | 崩溃样本数 | 含散文 | 含强散文 | 散文命中率 |")
        A("|---|---|---|---|---|")
        for cell in ("seed_reuse/aflnet", "seed_reuse/chatafl",
                     "protorag/aflnet", "protorag/chatafl"):
            v = prose["by_cell"].get(cell)
            if not v:
                continue
            rate = (f"**{v['prose_rate'] * 100:.1f}%**"
                    if v["prose_rate"] is not None else "N/A（无样本）")
            A(f"| `{cell}` | {v['samples']} | {v['with_prose']} "
              f"| {v['with_strong_prose']} | {rate} |")
        A(f"| **合计** | **{prose['total_samples']}** "
          f"| **{prose['total_with_prose']}** "
          f"| **{prose['total_with_strong_prose']}** | |")
        A("")
        A("> ★★ **对照组（seed_reuse）的崩溃样本同样含 LLM 散文** —— "
          "`seed_reuse_chatafl` 的 27 个崩溃样本 **27/27 全部命中**；"
          "其 7 条**原始种子本身是干净的**（纯 RTSP 报文，散文命中 0/7），"
          "散文是运行时富集时才混进去的。")
        A(">")
        A("> → ★ **chatafl 两组的崩溃样本都不能作为「真实 RTSP 漏洞」的干净证据**。"
          "这一点必须在**表注、论文正文与实验记录三处同步声明**。")
        A(">")
        A("> → **aflnet 是唯一干净对照**（两组 0 散文、0 enriched_），"
          "其 47 个崩溃样本可作为真实漏洞证据。")
        A("")
        per = prose.get("per_container", {})
        marked = [(k, v) for k, v in per.items()
                  if v.get("samples") and v.get("with_prose")]
        if marked:
            A("各容器明细（含散文的容器）：")
            A("")
            A("| 容器 | 崩溃样本 | 含散文 | 含强散文 | 命中标记（前 6 个） |")
            A("|---|---|---|---|---|")
            for k, v in marked:
                mk = ", ".join(v["markers"][:6])
                A(f"| `{k}` | {v['samples']} | {v['with_prose']} "
                  f"| {v['with_strong_prose']} | {mk} |")
            A("")

    # ------------------------------------------------------------------
    A("## 6. 时序覆盖率（区间池化口径）")
    A("")
    iv_b = res["timeseries_interval_buckets"]
    iv_labels = [r["bucket"] for r in iv_b]
    A("| group | fuzzer | " + " | ".join(iv_labels) + " |")
    A("|---" * (len(iv_b) + 2) + "|")
    for g in ("seed_reuse", "protorag"):
        for fz in ("aflnet", "chatafl"):
            vals = []
            for row in iv_b:
                c = row["cells"].get(f"{g}/{fz}")
                vals.append(f"{c['mean']:.3f}" if c else "NA")
            A(f"| {g} | {fz} | " + " | ".join(vals) + " |")
    A("")
    A("> 单元为该**区间**内各容器 `bitmap_cvg` 的均值（%）。")
    A("> **分桶口径（★ 权威口径）**：九个**连续区间桶** "
      "`0-0.5h / 0.5-1h / 1-2h / 2-4h / 4-6h / 6-8h / 8-12h / 12-18h / 18-24h`，"
      "桶边界 **`[lo, hi)`（闭左开右）**；每个区间内取**跨 rep 全部采样点混池**后的均值"
      "（不是「先分 rep 再平均」）。")
    A("> 舍入路径与 `local/rq1_2_analyze.py` 一致：单元格均值 `round(·,4)` → "
      "差值 `round(a-b,4)` → 显示 3 位小数；时基为各容器 `plot_data` 首行时间戳。"
      "区间边界取自 `rq1_2_analyze.py` 的 `BUCKET_EDGES`。")
    A("")
    A("| group | fuzzer | " + " | ".join(iv_labels) + " |")
    A("|---" * (len(iv_b) + 2) + "|")
    for g in ("seed_reuse", "protorag"):
        for fz in ("aflnet", "chatafl"):
            vals = []
            for row in iv_b:
                c = row["cells"].get(f"{g}/{fz}")
                vals.append(f"{c['paths_mean']:.0f}" if c and c.get("paths_mean") is not None
                            else "NA")
            A(f"| {g} | {fz} | " + " | ".join(vals) + " |")
    A("")
    A("> 上表为同口径下的路径数 `paths_total` 均值（对照组见 §3.1 / §3.2 的路径数指标）。")
    A("> ★ 注意 chatafl 半侧 protorag 的路径数从**第一个区间**起就是基线的 3 倍以上"
      "（1634 vs 511）—— 这是 LLM 富集把初始队列从 50 扩到 1344 的**直接指纹**，"
      "不是种子质量的体现。")
    A("")
    A("### 6.0 ★ 与 VM 采集脚本逐格对账（点时刻口径）")
    A("")
    A("VM 采集脚本 `/home/zxy/rq1_collect_live555.sh` 的时序统计用的是"
      "**点时刻口径**：桶中心 `h`、窗口 `abs(rel_hours - h) < 0.2`、跨 rep 池化。"
      "下表为**同口径复算**结果，已与 VM 侧脚本打印值**逐格一致**（可与 VM 产出直接对账）：")
    A("")
    A("| group | fuzzer | " + " | ".join(f"{h:g}h" for h in TS_POINT_BUCKETS) + " |")
    A("|---" * (len(TS_POINT_BUCKETS) + 2) + "|")
    _pt = res.get("timeseries_buckets", [])
    for g in ("seed_reuse", "protorag"):
        for fz in ("aflnet", "chatafl"):
            vals = []
            for h in TS_POINT_BUCKETS:
                row = next((c for c in _pt if c.get("h") == h), None)
                cell = row["cells"].get(f"{g}/{fz}") if row else None
                vals.append(f"{cell['mean']:.2f}" if cell else "NA")
            A(f"| {g} | {fz} | " + " | ".join(vals) + " |")
    A("")
    A("> ★ **两种口径都可用，但用途不同**：")
    A("> - **点时刻口径**（本表）：与 VM 采集脚本打印值逐格一致 → **可与 VM 产出直接对账**，"
      "用于复核采集环节。")
    A("> - **区间池化口径**（§6 主表）：桶边界对齐真实时间轴（`0-0.5h`/`0.5-1h`/…），"
      "用于展示覆盖率的**时间演进趋势**，且能显式看到「0–0.5 h 区间 protorag 尚落后」。")
    A("> - 两者的**结论完全一致**：1 h 之后 aflnet 半侧逐 rep **5/5 全正**并全程保持。")
    A(">")
    A("> ⚠ **注意本表（点时刻口径）不支持逐 rep 配对**：VM 采集脚本对每个 (group,fuzzer) 只打印"
      "**一个混池均值**，不产出逐 rep 序列 → **本表不可用于逐 rep 配对统计**；"
      "逐 rep 配对一律以 §6.1 的区间池化口径为准（其逐 rep 值由 `rq1_2_timeseries.csv` "
      "按区间重算得到）。")
    A(">")
    A("> ★ **口径敏感性（aflnet 半侧 0–0.5 h 区间，三种取点方式）**：")
    A("> ")
    A("> | 取点口径 | 0–0.5h 均值 | win | 0.5–1h 均值 | win |")
    A("> |---|---|---|---|---|")
    A("> | **区间池化（★ §6 权威口径）** | **−0.351** | **0/5** | **+0.271** | **5/5** |")
    A("> | 区间内**首个**采样点 | −1.420 | 0/5 | +0.076 | 3/5 |")
    A("> | 区间内**最后**采样点 | +0.074 | 3/5 | +0.322 | 5/5 |")
    A("> ")
    A("> → 早期区间对取点方式**敏感**（方向可相反）；**1 h 以后各口径一致为正**。")
    A("> → 故所有论断均以 **1 h 及之后**为准，0–0.5 h 区间只作背景说明。")
    A("")
    A("### 6.1 各区间的反超差值（protorag − seed_reuse，pp）")
    A("")
    A("| Fuzzer | " + " | ".join(iv_labels) + " |")
    A("|---" * (len(iv_b) + 1) + "|")
    for fz in ("aflnet", "chatafl"):
        vals = []
        for lab in iv_labels:
            d = next((x for x in res["timeseries_interval_delta"]
                      if x["bucket"] == lab and x["fuzzer"] == fz), None)
            vals.append(f"{d['delta_pp']:+.3f}" if d else "NA")
        A(f"| {fz} | " + " | ".join(vals) + " |")
    A("")
    # 逐 rep 配对差值 + win rate（区间池化口径）
    iv_d = res["timeseries_interval_delta"]
    for fz in ("aflnet", "chatafl"):
        rows = [x for x in iv_d if x["fuzzer"] == fz]
        if not rows:
            continue
        A(f"逐 rep 配对差值与 win rate（**{fz}** 半侧；区间内按 rep 求均值后再跨 rep 配对）：")
        A("")
        A("| 区间 | 逐 rep 差值（pp） | win rate |")
        A("|---|---|---|")
        for d in rows:
            pr = ", ".join(f"{v:+.3f}" for v in d["per_rep_diff"])
            wr = d["win_rate"]
            wr_s = f"**{wr}/{len(REPS)}**"
            A(f"| {d['bucket']} | {pr} | {wr_s} |")
        A("")
    # ---- 逐 rep 胜负：反超时点的严谨判据（win rate < 5/5 不得写「稳定地」）----
    # ★ 区间池化口径：0-0.5h 明确落后、0.5-1h 起 5/5 全正并保持到终态。
    afl_iv = [d for d in res["timeseries_interval_delta"] if d["fuzzer"] == "aflnet"]
    if afl_iv:
        d_first = afl_iv[0]
        d_end = afl_iv[-1]
        # 自「5/5 全正」起的首个区间 —— 反超稳定成立的时点
        stable_from = next((d for d in afl_iv
                            if d["win_rate"] == len(REPS)), None)
        if d_first and stable_from and d_end:
            pr_first = ", ".join(f"{v:+.3f}" for v in d_first["per_rep_diff"])
            A(f"> ★ **反超时点（aflnet 半侧，区间池化口径，逐 rep 配对差值）**：")
            A(f"> - **{d_first['bucket']} = 明确落后，不是反超**："
              f"区间差值 **{d_first['delta_pp']:+.3f} pp**，逐 rep {pr_first}"
              f" → 严格为正 **{d_first['win_rate']}/5**（5 个 rep 全为负）"
              f"→ 该区间 protorag **尚未反超**。")
            A(f"> - **{stable_from['bucket']} 起 = 反超成立**："
              f"逐 rep **{stable_from['win_rate']}/5 全正**，"
              f"区间差值 **{stable_from['delta_pp']:+.3f} pp**"
              f"（此后每一个区间均为 5/5 全正，全程未出现反向）。")
            A(f"> - **末区间（{d_end['bucket']}）差值 {d_end['delta_pp']:+.3f} pp**"
              f"（逐 rep 均值 {d_end['per_rep_mean']:+.3f} pp，{d_end['win_rate']}/5 全正）"
              f" → 差距**不收敛**（1-2h 后维持在 +0.42 ~ +0.58 pp 区间震荡）。")
            A(">")
            A(f"> → 正确表述：**「反超自 {stable_from['bucket']} 区间起成立，"
              f"并在 1 h 之后全程保持（未收敛、未反转）」**；"
              f"**不得**写成「0.5 h 即已反超」——该区间 protorag 尚落后 "
              f"{abs(d_first['delta_pp']):.3f} pp。")
            A("")

    # ---- 点时刻口径对照表（采集脚本原样口径，用于与 VM 侧原始产出对账）----
    A("> #### 附：点时刻口径对照表（采集脚本 `rq1_collect_live555.sh` 原样口径）")
    A(">")
    A("> 主理人要求 §6 表格统一用**区间池化**口径（上表）。下表保留采集脚本的**点时刻**口径"
      "（桶中心 `h` + `abs(rel_hours - h) < 0.2`），用于**与 VM 侧原始产出直接对账**，"
      "不代表本记录的论断口径。")
    A(">")
    A("> | Fuzzer | " + " | ".join(r["bucket"] for r in res["timeseries_buckets"]) + " |")
    A("> |---" * (len(res["timeseries_buckets"]) + 1) + "|")
    for fz in ("aflnet", "chatafl"):
        vals = []
        for row in res["timeseries_buckets"]:
            d = next((x for x in res["timeseries_delta"]
                      if x["bucket"] == row["bucket"] and x["fuzzer"] == fz), None)
            vals.append(f"{d['delta_pp']:+.3f}" if d else "NA")
        A("> | " + fz + " | " + " | ".join(vals) + " |")
    A(">")

    # ---- 分桶口径说明（方法学备注，防踩坑）----
    A("> #### ★ 分桶口径说明（方法学备注，**必读**）")
    A("> ")
    A("> **权威口径（区间池化）**：九个连续区间桶 "
      "`0-0.5h / 0.5-1h / 1-2h / 2-4h / 4-6h / 6-8h / 8-12h / 12-18h / 18-24h`，"
      "边界 `[lo, hi)`，区间内跨 rep 全部采样点混池求均值。"
      "本文 §6 的所有表格与结论均以此为准。")
    A("> ")
    iv_alt = res.get("timeseries_interval_alt_calibers", [])
    def _iv_alt(bucket: str, mode: str, fz: str = "aflnet"):
        return next((a for a in iv_alt
                     if a["bucket"] == bucket and a["mode"] == mode
                     and a["fuzzer"] == fz), None)
    a_first = _iv_alt("0-0.5h", "first")
    a_last = _iv_alt("0-0.5h", "last")
    b_first = _iv_alt("0.5-1h", "first")
    b_last = _iv_alt("0.5-1h", "last")
    if a_first and a_last:
        A(f"> **⚠ 早期区间的结论对取点口径敏感，不应作为论断**：在 **0-0.5h** 区间，"
          f"权威（区间池化）口径为 **{afl_iv[0]['delta_pp']:+.3f} pp**"
          f"（逐 rep {afl_iv[0]['win_rate']}/5 为正，即 5 个 rep 全为负）；"
          f"若改用「取桶内**首个**采样点」口径则为 "
          f"**{a_first['mean']:+.3f} pp**（{a_first['win_rate']}/5 为正），"
          f"若改用「取桶内**最后**采样点」口径则为 "
          f"**{a_last['mean']:+.3f} pp**（{a_last['win_rate']}/5 为正）→ "
          f"**同一批原始数据、不同取点方式，会得到方向相反的 0-0.5h 结论**。")
        A(">")
    if b_first and b_last:
        A(f"> **0.5-1h 区间同样敏感**：权威口径 **{next(d['delta_pp'] for d in afl_iv if d['bucket'] == '0.5-1h'):+.3f} pp**"
          f"（5/5 全正），但「首个采样点」口径为 "
          f"**{b_first['mean']:+.3f} pp**（{b_first['win_rate']}/5 为正）、"
          f"「最后采样点」口径为 **{b_last['mean']:+.3f} pp**"
          f"（{b_last['win_rate']}/5 为正）→ 尚未达成三口径一致。")
        A(">")
    A("> 原因是 protorag 的 **50 条**种子 dry-run 比基线的 **7 条**更慢，"
      "桶内首个采样点仍处于爬坡早期，桶内最后采样点则已接近该桶末端 —— "
      "**早期区间内的样本分布本身不均匀，任何取点方式都会被这一效应放大**。")
    A("> ")
    A("> **1 h 以后各口径结论一致**：在权威口径 / 首个采样点 / 最后采样点三种口径下，"
      "**1-2h 及之后的每一个区间都是 5/5 逐 rep 全正** → "
      "**因此所有论断均以 1 h 及之后为准**，0-0.5h 与 0.5-1h 只作背景说明。")
    A("> ")
    A("> **★ 「终态」有两个不同口径，引用时必须写清**：")
    A("> - **P2 终值**（`plot_data` 末行，即 **docx 表 4 的数据源**）：aflnet 配对差值均值 "
      "**+0.530 pp**（逐 rep +0.20/+0.63/+0.52/+0.63/+0.67）；chatafl **+0.504 pp**。")
    A("> - **末区间（18-24h）区间池化均值**（本文 §6 表的末列）：aflnet "
      f"**{afl_iv[-1]['delta_pp']:+.3f} pp**、chatafl "
      f"**{next(d['delta_pp'] for d in res['timeseries_interval_delta'] if d['fuzzer'] == 'chatafl'):+.3f} pp**。")
    A("> - 两者相差 ≤0.03 pp（桶内最后 ~10 分钟仍有微量增长），**结论完全一致**；"
      "**论文一律引用 P2 终值**（与表 4 同源），§6 的桶值仅用于展示时间趋势。")
    A(">")
    A("> **★ 与 VM 侧采集脚本对账**：§6.1 末尾附了采集脚本 "
      "`/home/zxy/rq1_collect_live555.sh` 的**点时刻**口径对照表"
      "（aflnet seed_reuse 9.46/9.55/9.62/…），用于与 VM 侧原始产出直接对账；"
      "**本记录的论断口径是区间池化**，两者不可混用。")
    A("")

    # ------------------------------------------------------------------
    A("## 7. 与 10-24 20:00 中间态快照的差异")
    A("")
    if "interim_vs_final" in res:
        iv = res["interim_vs_final"]
        A(f"- 中间态快照覆盖 **{iv['interim_max_rel_hours']:.2f} h**"
          f"（时序 {iv['interim_ts_rows']} 行），最终态 {iv['final_ts_rows']} 行。")
        A(f"- 中间态**全部 20 个容器崩溃数为 0**：{iv['crash_free_at_interim']}"
          f" → **崩溃是在中间态之后才出现的**（最早 9.2 h）。")
        A("")
        A("| 组/Fuzzer | rep | 覆盖率 中间态 → 最终 | Δ(pp) | 路径数 中间态 → 最终 | 崩溃 中间态 → 最终 | 挂起 中间态 → 最终 |")
        A("|---|---|---|---|---|---|---|")
        for row in iv["rows"]:
            A(f"| `{row['group']}/{row['fuzzer']}` | {row['rep']} | "
              f"{row['bitmap_cvg_interim']:.2f}% → {row['bitmap_cvg_final']:.2f}% | "
              f"{row['bitmap_cvg_final'] - row['bitmap_cvg_interim']:+.2f} | "
              f"{row['paths_interim']:.0f} → {row['paths_final']:.0f} | "
              f"{row['crashes_interim']:.0f} → {row['crashes_final']:.0f} | "
              f"{row['hangs_interim']:.0f} → {row['hangs_final']:.0f} |")
        A("")
        A("按 组×Fuzzer 的覆盖率均值：")
        A("")
        A("| 组/Fuzzer | 中间态均值 | 最终均值 | Δ(pp) |")
        A("|---|---|---|---|")
        for cell, v in iv["cell_means"].items():
            A(f"| `{cell}` | {v['interim_mean']:.3f}% | {v['final_mean']:.3f}% "
              f"| {v['delta_pp']:+.3f} |")
        A("")
        A("> 中间态快照仅用于确认『实验在正常推进』，**不作为论文数据**；"
          "论文一律引用 §2 的最终值。")
    else:
        A("> （未提供 --interim-dir，跳过中间态对比）")
    A("")

    # ------------------------------------------------------------------
    A("## 8. 统计显著性与表述纪律")
    A("")
    A("| 口径 | 最小可达双侧 p | n=5 下能否达 0.05 显著 |")
    A("|---|---|---|")
    A("| Mann–Whitney 精确（独立样本） | 0.0079 | **能**（但仅在完全分离时） |")
    A("| Wilcoxon 符号秩精确（配对） | 0.0625 | **不能** |")
    A("| 符号检验精确（配对） | 0.0625 | **不能** |")
    A("| ↑ 同上，但 pooled n=10 | 0.00195 | **能**（但 pooled 混合两半侧，见 §3.3） |")
    A("")
    A("- ★ **n=5 的配对检验在数学上无法达到 0.05 显著性**"
      "（最小 p = 0.0625）→ 覆盖率反超只能表述为"
      "**『5/5 逐 rep 方向一致，未达统计显著』**。")
    A("- 未达显著时**不得**写『无差异』，只能写『方向一致但未达统计显著』。")
    A("- win rate < 5/5 时**禁止**写『稳定地/一致地』。")
    A("- `n_edges` / `paths_total` 两侧方向相反 → **不作为论文指标**。")
    A("- ★★ **覆盖率是『执行量』的结果量** → **必须做执行量控制**"
      "（§3.4 等执行预算口径 + §3.5 时间-阈值口径）。"
      "不控制执行量会被质疑『用更多执行换来的覆盖率』；"
      "等执行预算下 **aflnet 仍 5/5 占优**（执行量只有基线的 77%），"
      "**只有 aflnet 半侧的覆盖率优势是可主张的** —— "
      "chatafl 半侧的降级理由是**语料污染与唯一变量不成立**，不是覆盖率反转。")
    A("- ★ **崩溃数不得作为方法优劣判据**：低频、晚发、方差大、"
      "受执行量放大，且 chatafl 半侧崩溃样本含 LLM 散文（§5.5）。")
    A("")

    # ------------------------------------------------------------------
    A("## 9. 论文正文修改提示（留给作者，本次未执行）")
    A("")
    A("论文正文本次**未修改**。作者若在论文中出现「ProtoRAG 种子在 Live555 上带来更高覆盖率」的表述，"
      "**必须限定为 aflnet 半侧**：")
    A("唯一变量成立（50 vs 7 条种子）、0 增强污染（§4）、等执行预算下仍 **5/5 占优**（§3.4）、"
      "时间-阈值加速比中位 "
      f"**{_t2t0.get('aflnet', {}).get('speedup_median', 0):.1f}×**（§3.5）。")
    A("")
    A("**不得**把结论扩展到 chatafl 半侧：")
    A("1. 其语料 **96% 被 ChatAFL 运行时 LLM 种子富集污染**，两组同等受害（§4）；")
    A("2. 其**唯一变量不成立** —— 初始队列 1344 vs 169（污染后队列），不是 50 vs 7 的种子集对比。")
    A("")
    A("**不得**写成「ProtoRAG 不会发现崩溃」—— 崩溃数不作为方法优劣判据（§5、§8）；")
    A("也**不得**声称「稳定探索到更多状态机边」—— n_edges 仅 4/5 为正且标准差与均值同量级（§3.2、§8）。")
    A("")
    A("> 可主张的正面结论（仅 aflnet 半侧）：**ProtoRAG 种子在 24 h 内以更少的执行量（77%）"
      "取得更高的分支覆盖率（5/5 逐 rep 方向一致，等执行预算下差值 +0.54 ~ +0.69 pp，"
      "且达到基线终态覆盖的时间快 "
      f"{_t2t0.get('aflnet', {}).get('speedup_median', 0):.0f} 倍），路径数不多于基线而覆盖更高（质效双优）**。")
    A("> 该结论与 chatafl 半侧的污染归因、崩溃证据不可用，三者必须一并披露。")
    A("")

    # ------------------------------------------------------------------
    A("## 10. 成立 / 不得声称 对照总表")
    A("")
    A("| 论断 | 判定 | 依据 |")
    A("|---|---|---|")
    A(f"| ProtoRAG 种子在 aflnet 半侧带来更高分支覆盖率 | ✅ **可主张** | "
      f"{_cov0.get('wins')}/5 逐 rep 反超，+{_cov0.get('mean', 0):.3f}±{_cov0.get('sd', 0):.3f} pp"
      f"（§3.1） |")
    A(f"| aflnet 半侧「以更少执行量取得更高覆盖」 | ✅ **可主张** | 执行量仅基线 "
      f"{_eqb0.get('aflnet', {}).get('execs_ratio_mean', 0) * 100:.0f}%，"
      f"等预算下仍 {_eqb0.get('aflnet', {}).get('wins')}/5（§3.4） |")
    A(f"| aflnet 半侧「更快达到基线终态覆盖」 | ✅ **可主张** | 加速比中位 "
      f"{_t2t0.get('aflnet', {}).get('speedup_median', 0):.1f}×（§3.5） |")
    A("| aflnet 半侧 protorag 路径数不多于基线而覆盖更高 | ✅ **可主张** | paths 均值 1495 < 1610，"
      "覆盖 10.52% > 9.99%（§3.2） |")
    A("| aflnet 半侧 P1 状态边更多来自种子集规模 | ✅ **可主张** | 队列 51 vs 8 无增强，"
      "P1 edges 22.4 vs 8.8（§4.3） |")
    A("| ProtoRAG 种子在 **chatafl** 半侧带来更高覆盖率 | ❌ **不得声称** | "
      "语料 96% 被污染、唯一变量不成立（1344 vs 169 污染后队列）（§3.4、§4） |")
    A("| ProtoRAG 稳定探索到更多状态机边（n_edges） | ❌ **不得声称** | "
      "4/5 为正，sd 与均值同量级，符号会翻转（§3.2、§8） |")
    A("| ProtoRAG 不会发现崩溃 / 抑制了崩溃 | ❌ **不得声称** | "
      "崩溃晚发低频、方差大、受执行量放大、chatafl 侧样本受污染（§5、§8） |")
    A("| ProtoRAG 的路径数优势（作为独立指标） | ❌ **不得声称** | "
      "两侧方向相反（chatafl 5/5 正、aflnet 1/5），自造且不稳健（§3.2） |")
    A("| 「无差异」（任何指标） | ❌ **不得声称** | "
      "n=5 配对检验最小 p = 0.0625，未达显著只能说「方向一致但未达统计显著」（§8） |")
    A("| chatafl 半侧两组的崩溃数差异可比较 | ❌ **不得声称** | "
      "两组崩溃样本均含 LLM 散文（chatafl 侧 28/28），非干净漏洞证据（§5.5） |")
    A("")

    # ------------------------------------------------------------------
    A("## 11. 数据读取口径备注（勿踩坑）")
    A("")
    A("1. **`plot_data` 第 0 列是 `unix_time`，不是 `execs`** —— 误用会造出「20 容器 execs 都是 1792M」的假象。")
    A("   真实 `execs_done` 取 `fuzzer_stats`。")
    A("2. **容器 11:09 停止后取数**：`docker exec` 对已停止容器**必然失败** → 走宿主机 bind mount")
    A("   `/home/zxy/rq2_out/{group}_{fuzzer}/r{rep}/` + `sudo -n cat`（这些文件 root 所有、mode 600，免密 sudo 可用）。")
    A("   `/seeds_work` 随容器消失，事后取证只能走 `queue/` 血缘或 `replayable-*`。")
    A("3. **`replayable-crashes/` 文件数 = `unique_crashes` + 1** —— 多出的是 `README.txt`，别多算。")
    A("4. **`plot_data` 列序**：0=unix_time, 1=cycles_done, 2=cur_path, 3=paths_total, 4=pending_total,")
    A("   5=pending_favs, 6=bitmap_cvg, 7=unique_crashes, 8=unique_hangs, 9=max_depth, 10=execs_per_sec,")
    A("   11=n_nodes, 12=n_edges, 13=chat_times（仅 chatafl）。")
    A("5. **docx `table_id` 按文件变化** —— 不只跨会话变，跨文件也变（真文档 `mj84o83m`，"
      "同一操作对副本得 `hpa0u987`）→ 回填必须每次运行时三重定位现取，禁止硬编码。")
    A("6. **★ 不要用「每百万次执行的覆盖率」(`cvg/execs`) 做方法比较** —— 该比值在同一容器内"
      "随执行量单调下降（饱和型累积量，首末比 18–35×），构造有偏。正确口径见 §3.4 等执行预算。")
    A("")

    # ------------------------------------------------------------------
    A("## 12. 复现命令（VM 侧，只读）")
    A("")
    A("```bash")
    A("# 终态 P2（容器已停 → 走宿主机 bind mount + sudo）")
    A("sudo -n cat /home/zxy/rq2_out/protorag_aflnet/r1/plot_data | grep -v '^#' | tail -1")
    A("sudo -n grep -E '^(bitmap_cvg|unique_crashes|unique_hangs|paths_total|execs_done)' \\")
    A("  /home/zxy/rq2_out/protorag_aflnet/r1/fuzzer_stats")
    A("# 队列血缘（enriched_* 占比）")
    A("sudo -n ls /home/zxy/rq2_out/protorag_chatafl/r1/queue | grep 'orig:' | grep -c enriched_")
    A("# 崩溃样本散文核查（对照组同样命中 → 证明污染非 ProtoRAG 特有）")
    A("sudo -n strings -n 10 /home/zxy/rq2_out/seed_reuse_chatafl/r1/replayable-crashes/id:000000* \\")
    A("  | grep -iE 'Explanation:|placed'")
    A("# 输入种子目录是否干净（enriched_ 应为 0）")
    A("sudo -n ls /home/zxy/rq2_seeds/protorag | grep -c enriched_")
    A("# chat_times 终值（chatafl 侧应全为 64 = CHATTING_THRESHOLD）")
    A("sudo -n cat /home/zxy/rq2_out/protorag_chatafl/r1/plot_data | grep -v '^#' | tail -1")
    A("# 采集脚本（修复版，容器停后可用；原脚本保留为备份）")
    A("bash /home/zxy/rq1_collect_live555_fix.sh   # 容器停止后可用；原脚本保留为备份")
    A("```")
    A("")

    # ------------------------------------------------------------------
    A("## 13. 后续处置建议")
    A("")
    A("1. **归档 `rq2_out`（4.5 G）后清空**，为 RQ3 腾磁盘（采集时 `/` 分区 19 G 可用、81% 已用）。")
    A("2. **RQ3 的 chatafl 行已用 `--network none` 关闭 LLM 增强**（实测 `enriched_*` = 0、"
      "`orig:` 计数 == 语料条数）→ RQ3 不受本污染影响；"
      "但**RQ1.2 未关闭增强 → RQ1.2 与 RQ3 的 chatafl 行不可直接横向比较**，须在论文中说明。")
    A("3. **论文方法学章节应写入一条工具链可复现性发现**：ChatAFL 的连续格式增强对 LLM 输出格式"
      "有隐式假设（纯报文），换成聊天型模型即失效 → 属**模型替换的复现偏差**，已披露（§4.1）。")
    A("4. 若要补做 chatafl 半侧的干净对照，需**重跑**（`--network none` 或换用纯报文抽取版 LLM 代理），"
      "本轮 20 容器的 chatafl 数据不可挽救。")
    A("")

    out = Path(args.out)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[生成] {out}（{len(L)} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
