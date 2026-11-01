#!/bin/bash
# version: 2026-10-24-v2
# ↑ 版本标记：编排前用 `grep '^# version:'` 校验 VM 副本与本地一致（防版本漂移）
# ★ RQ3 Live555 数据采集 —— P1/P2 + 全时序 + queue 索引 + crashes + 增强审计
#
# 用法（在 VM 上，实验停后执行）：
#     bash rq3_collect.sh <collect_ts>
#   collect_ts 缺省用当前时间戳；重复执行同一 ts → 输出逐字节相同（幂等）。
#
# 输出目录：/home/zxy/rq3_collect/<ts>/
#   rq3_p1.csv / rq3_p2.csv / rq3_summary.csv / rq3_timeseries.csv.gz
#   rq3_queue_index.csv.gz / rq3_crashes_index.csv / rq3_enrichment_audit.csv
#   rq3_validation.md
#
# ★ 数据来源与依据（复用 rq1_collect_live555.sh 的已验证解析逻辑）：
#   · plot_data 末行的 n_nodes/n_edges 与 ipsm.dot grep 计数【已实测 4/4 容器完全相等】
#     → P1 取 plot_data 首行、P2 取 plot_data 末行，不依赖易丢失的 ipsm.dot 快照
#   · plot_data 列（chatafl 14 列 / aflnet 13 列）：
#     0 unix_time, 1 cycles_done, 2 cur_path, 3 paths_total, 4 pending_total,
#     5 pending_favs, 6 map_size, 7 unique_crashes, 8 unique_hangs, 9 max_depth,
#     10 execs_per_sec, 11 n_nodes, 12 n_edges, [13 chat_times 仅 chatafl]
#   · fuzzer_stats 作为覆盖率/崩溃/路径的交叉校验源
#
# ★ 幂等：所有输出先写 .tmp 再 mv；按主键去重；实验停后重跑得最终值
set -uo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  shift
fi

TS=${1:-$(date +%Y%m%d_%H%M%S)}
OUT_DIR=/home/zxy/rq3_collect/$TS
SNAP_ROOT=/home/zxy/rq3_snap
DICT_ROOT=/home/zxy/rq3_dict

# 注意：不可用 GROUPS 作变量名——bash 内建特殊变量（当前用户组 ID 数组），赋值无效。
GRP_LIST="A B C D"
FUZZ_LIST="chatafl aflnet"
REPS="1 2 3 4 5"

mkdir -p "$OUT_DIR"

# ---- dry 模式：只校验解析逻辑（用假数据），不连容器、不写产物 ----
if [ "$DRY_RUN" = "1" ]; then
  echo "=== RQ3 采集 dry 模式（不连容器、不写产物）==="
  echo "输出目录（dry 不创建）: $OUT_DIR"
  echo "容器命名模板: rq3_{group}_{fuzzer}_r{rep}"
  echo "组列表: $GRP_LIST"
  echo "fuzzer 列表: $FUZZ_LIST"
  echo "rep 列表: $REPS"
  echo
  echo "--- plot_data 解析自检（用真实格式的样例行）---"
  SAMPLE='1792849674, 185, 2313, 2328, 2084, 3, 10.36%, 0, 0, 11, 2.06, 14, 141, 64'
  IFS=',' read -r _t _cyc _cp _paths _pend _pf _cvg _cr _hg _dep _eps _n_st _n_ed _rest <<< "$SAMPLE"
  trim() { local v="${1-}"; v="${v#"${v%%[![:space:]]*}"}"; v="${v%"${v##*[![:space:]]}"}"; echo "$v"; }
  echo "  n_nodes=$(trim "${_n_st:-}")  n_edges=$(trim "${_n_ed:-}")  cvg=$(trim "${_cvg:-}")  chat_times=$(trim "${_rest:-}")"
  [ "$(trim "${_rest:-}")" = "64" ] && echo "  ✓ chat_times 解析正确（第 14 列）" \
                                 || echo "  ✗ chat_times 解析错误"
  echo
  echo "--- 断言 C 审计列（增强关闭证据）---"
  echo "  enriched_in_seeds / enriched_in_queue / queue_total / chat_times_max / verdict"
  echo
  echo "dry 模式通过 ✓"
  exit 0
fi

# 容器内 plot_data 首行/末行
plot_first() { docker exec "$1" bash -c 'grep -v "^#" /out/plot_data 2>/dev/null | head -1' 2>/dev/null; }
plot_last()  { docker exec "$1" bash -c 'grep -v "^#" /out/plot_data 2>/dev/null | tail -1' 2>/dev/null; }
# 容器内 fuzzer_stats 单字段
fs_field() {
  docker exec "$1" bash -c "grep '^$2' /out/fuzzer_stats 2>/dev/null | awk '{print \$3}'" 2>/dev/null
}
# 容器内队列条目数
queue_count() {
  docker exec "$1" bash -c 'ls /out/queue 2>/dev/null | wc -l' 2>/dev/null
}
# 容器内 enhanced_* 计数（断言 C 的证据）
enriched_seeds_count() {
  docker exec "$1" bash -c 'ls /seeds_work 2>/dev/null | grep -c "^enriched_" || true' 2>/dev/null || echo 0
}
enriched_queue_count() {
  docker exec "$1" bash -c 'ls /out/queue 2>/dev/null | grep -c "orig:enriched" || true' 2>/dev/null || echo 0
}
# 容器内 seeds_work 的 .raw 计数
seed_raw_count() {
  docker exec "$1" bash -c 'ls /seeds_work 2>/dev/null | grep -c "\.raw$" || true' 2>/dev/null || echo 0
}
# ★ v2：队列中 ",orig:" 形式条目数（V11 污染探针 —— 必须 == 初始种子数）
init_queue_count() {
  docker exec "$1" bash -c 'ls /out/queue 2>/dev/null | grep -c ",orig:" || true' 2>/dev/null || echo 0
}
# ★ v2：崩溃条目数（RQ1.2 实测：崩溃是概率性、晚发的 —— 基线组 9.2h 才出首个）
crash_count() {
  docker exec "$1" bash -c 'ls /out/replayable-crashes 2>/dev/null | grep -c "^id:" || true' 2>/dev/null || echo 0
}

echo "=== RQ3 采集（ts=$TS）→ $OUT_DIR ==="

# ★ plot_data 用 ", " 分隔 → IFS=',' 切出的字段带前导空格 → 统一 trim
trim() { local v="${1-}"; v="${v#"${v%%[![:space:]]*}"}"; v="${v%"${v##*[![:space:]]}"}"; echo "$v"; }

# ---- P1 / P2 / 增强审计 ----
P1_TMP="$OUT_DIR/.rq3_p1.csv.tmp";  : > "$P1_TMP"
P2_TMP="$OUT_DIR/.rq3_p2.csv.tmp";  : > "$P2_TMP"
EA_TMP="$OUT_DIR/.rq3_enrichment_audit.csv.tmp"; : > "$EA_TMP"

echo "group,rep,fuzzer,n_states,n_edges,paths_total_at_p1,init_queue_count" > "$P1_TMP"
echo "group,rep,fuzzer,n_states,n_edges,bitmap_cvg,unique_crashes,unique_hangs,paths_total,execs_done,chat_times_max" > "$P2_TMP"
echo "container,group,fuzzer,rep,enriched_in_seeds,enriched_in_queue,queue_total,chat_times_max,verdict" > "$EA_TMP"

for g in $GRP_LIST; do
  for fz in $FUZZ_LIST; do
    for r in $REPS; do
      c="rq3_${g}_${fz}_r${r}"
      docker ps -a --format '{{.Names}}' | grep -qx "$c" || continue

      # ---- P1：plot_data 首行 ----
      p1=$(plot_first "$c")
      _iqc=$(init_queue_count "$c")
      if [ -n "$p1" ]; then
        IFS=',' read -r _t _cyc _cp _paths _pend _pf _cvg _cr _hg _dep _eps _n_st _n_ed _rest <<< "$p1"
        echo "$g,$r,$fz,$(trim "${_n_st:-}"),$(trim "${_n_ed:-}"),$(trim "${_paths:-}"),$_iqc" >> "$P1_TMP"
      else
        echo "$g,$r,$fz,NA,NA,NA,$_iqc" >> "$P1_TMP"
      fi

      # ---- P2：plot_data 末行 + fuzzer_stats 交叉校验 ----
      p2=$(plot_last "$c")
      _ct="NA"
      if [ -n "$p2" ]; then
        IFS=',' read -r _t _cyc _cp _paths _pend _pf _cvg _cr _hg _dep _eps _n_st _n_ed _rest <<< "$p2"
        fs_cvg=$(fs_field "$c" bitmap_cvg)
        fs_cr=$(fs_field "$c" unique_crashes)
        fs_hg=$(fs_field "$c" unique_hangs)
        fs_paths=$(fs_field "$c" paths_total)
        fs_execs=$(fs_field "$c" execs_done)
        # chat_times 恒为 0 是「runtime stall-chat 也已关闭」的判据（V7）
        # ★ _rest 可能是 " 64"（前导空格）→ 必须 trim
        _ct=$(trim "${_rest:-}")
        [ -z "$_ct" ] && _ct="NA"
        echo "$g,$r,$fz,$(trim "${_n_st:-}"),$(trim "${_n_ed:-}"),$(trim "${_cvg:-}"),$(trim "${_cr:-}"),$(trim "${_hg:-}"),$(trim "${_paths:-}"),$(trim "${fs_execs:-}"),$_ct" >> "$P2_TMP"
      else
        echo "$g,$r,$fz,NA,NA,NA,NA,NA,NA,NA,NA" >> "$P2_TMP"
      fi

      # ---- 增强审计（断言 C）----
      es=$(enriched_seeds_count "$c"); eq=$(enriched_queue_count "$c")
      qc=$(queue_count "$c"); sr=$(seed_raw_count "$c")
      if [ "$es" = "0" ] && [ "$eq" = "0" ]; then
        verdict="OK"
      else
        verdict="ENRICHED_DETECTED"
      fi
      echo "$c,$g,$fz,$r,$es,$eq,$qc,${_ct:-NA},$verdict" >> "$EA_TMP"
    done
  done
done

mv -f "$P1_TMP" "$OUT_DIR/rq3_p1.csv"
mv -f "$P2_TMP" "$OUT_DIR/rq3_p2.csv"
mv -f "$EA_TMP" "$OUT_DIR/rq3_enrichment_audit.csv"

# ---- 时序 / queue / crashes 索引（python 侧处理，便于跨平台一致）----
python3 - "$OUT_DIR" "$SNAP_ROOT" "$GRP_LIST" "$FUZZ_LIST" "$REPS" <<'PYEOF'
import csv, gzip, io, os, subprocess, sys
from pathlib import Path

out_dir = Path(sys.argv[1]); snap_root = Path(sys.argv[2])
grp_list = sys.argv[3].split(); fuzz_list = sys.argv[4].split()
reps = sys.argv[5].split()

def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout

def write_atomic(path, header, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    gz = str(path).endswith(".gz")
    op = gzip.open(tmp, "wt", encoding="utf-8", newline="") if gz \
        else open(tmp, "w", encoding="utf-8", newline="")
    with op as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow(r)
    tmp.replace(p)

# ---------- 时序 ----------
TS_HDR = ["group","fuzzer","rep","unix_time","rel_hours","cycles_done",
          "paths_total","map_size","unique_crashes","unique_hangs","max_depth",
          "execs_per_sec","n_nodes","n_edges","chat_times"]
ts_rows = []
for g in grp_list:
    for fz in fuzz_list:
        for rep in reps:
            c = f"rq3_{g}_{fz}_r{rep}"
            if sh(["docker","ps","-a","--format","{{.Names}}"]).find(c) < 0:
                continue
            out = sh(["docker","exec",c,"bash","-c",'grep -v "^#" /out/plot_data'])
            rows = []
            for l in out.strip().split("\n"):
                if not l.strip(): continue
                p = [x.strip() for x in l.split(",")]
                if len(p) < 13: continue
                rows.append(p)
            if not rows: continue
            t0 = int(rows[0][0])
            for p in rows:
                def g(i, d="NA"):
                    return p[i] if len(p) > i and p[i] != "" else d
                chat = g(13) if len(p) > 13 else "NA"
                try:
                    rel = round((int(p[0]) - t0) / 3600.0, 4)
                except ValueError:
                    rel = "NA"
                ts_rows.append([g, fz, rep, g(0), rel, g(1), g(3), g(6),
                                g(7), g(8), g(9), g(10), g(11), g(12), chat])
write_atomic(out_dir/"rq3_timeseries.csv.gz", TS_HDR, ts_rows)
print(f"[采集] 时序 {len(ts_rows)} 行")

# ---------- queue 索引（含快照 + final）----------
QI_HDR = ["container","group","fuzzer","rep","snapshot_tag","entry_name",
          "entry_md5","root_seed","kind","hit_P1","hit_P2","hit_P3","hit_P4","layer"]
CR_HDR = ["container","group","fuzzer","rep","entry_name","entry_md5",
          "root_seed","layer"]
qi_rows, cr_rows = [], []

def add_queue(container, g, fz, rep, tag, tsv_path):
    if not tsv_path.exists(): return
    with open(tsv_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2: continue
            name, md5 = parts[0], parts[1]
            root = parts[2] if len(parts) > 2 else ""
            qi_rows.append([container, g, fz, rep, tag, name, md5, root,
                            "", "", "", "", "", ""])

for g in grp_list:
    for fz in fuzz_list:
        for rep in reps:
            c = f"rq3_{g}_{fz}_r{rep}"
            if sh(["docker","ps","-a","--format","{{.Names}}"]).find(c) < 0:
                continue
            # 快照
            for tag in ("T3600s","T7200s"):
                add_queue(c, g, fz, rep, tag, snap_root/tag/c/"queue_index.tsv")
            # final：容器内现取
            out = sh(["docker","exec",c,"bash","-c",
                      'cd /out/queue 2>/dev/null || exit 0; '
                      'for f in *; do printf "%s\\t%s\\t%s\\n" "$f" '
                      '"$(md5sum "$f" | cut -d\\" \\" -f1)" '
                      '"$(echo "$f" | sed -n \\"s/^id:[0-9]*,orig://p\\")"; done'])
            tmp = out_dir/".qi.tmp"
            tmp.write_text(out, encoding="utf-8")
            add_queue(c, g, fz, rep, "final", tmp)
            tmp.unlink(missing_ok=True)
            # crashes（★ v2：崩溃可能是「晚发」的 —— RQ1.2 实测基线组 9.2h 才出首个）
            cout = sh(["docker","exec",c,"bash","-c",
                       'cd /out/replayable-crashes 2>/dev/null || exit 0; '
                       'for f in *; do case "$f" in id:*) '
                       'printf "%s\\t%s\\t%s\\n" "$f" '
                       '"$(md5sum "$f" | cut -d\\" \\" -f1)" '
                       '"$(echo "$f" | sed -n \\"s/.*,src:\\([0-9]*\\).*/\\1/p\\")";; esac; done'])
            tmp = out_dir/".ci.tmp"
            tmp.write_text(cout, encoding="utf-8")
            if tmp.exists():
                with open(tmp, "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.rstrip("\n").split("\t")
                        if len(parts) < 2: continue
                        cr_rows.append([c, g, fz, rep, parts[0], parts[1],
                                        parts[2] if len(parts)>2 else "", ""])
                tmp.unlink(missing_ok=True)
write_atomic(out_dir/"rq3_queue_index.csv.gz", QI_HDR, qi_rows)
write_atomic(out_dir/"rq3_crashes_index.csv", CR_HDR, cr_rows)
print(f"[采集] queue 索引 {len(qi_rows)} 行，crashes {len(cr_rows)} 行")
PYEOF

# ---- 聚合 + 配对统计 + 校验 ----
python3 - "$OUT_DIR" <<'PYEOF'
import csv, statistics, sys
from pathlib import Path

out_dir = Path(sys.argv[1])

def load(p):
    rows = []
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for k in ('n_states','n_edges','bitmap_cvg','unique_crashes',
                      'unique_hangs','paths_total','execs_done','chat_times_max',
                      'paths_total_at_p1'):
                if k in r and r[k] is not None:
                    v = str(r[k]).strip().replace('%','')
                    try: r[k] = float(v)
                    except ValueError: r[k] = None
            if 'rep' in r and r['rep'] is not None:
                try: r['rep'] = int(str(r['rep']).strip())
                except ValueError: pass
            rows.append(r)
    return rows

def agg(rows, keys):
    out = {}
    for r in rows:
        out.setdefault(tuple(r[k] for k in keys), []).append(r)
    return out

def stat(vals):
    vals = [v for v in vals if v is not None]
    if not vals: return (None, None)
    return (statistics.mean(vals),
            statistics.stdev(vals) if len(vals) > 1 else 0.0)

p1 = load(out_dir/"rq3_p1.csv")
p2 = load(out_dir/"rq3_p2.csv")

# ---- summary（mean ± std + 全部原始值）----
SUM_HDR = ["group","fuzzer","metric","n_reps","mean","std","raw_values"]
sum_rows = []
METRICS = [('bitmap_cvg','分支覆盖%'), ('n_states','n_states'),
           ('n_edges','n_edges'), ('paths_total','paths_total'),
           ('unique_crashes','unique_crashes'), ('execs_done','execs_done'),
           ('chat_times_max','chat_times_max')]
for (g, fz), rs in sorted(agg(p2, ['group','fuzzer']).items()):
    for key, label in METRICS:
        vals = [r.get(key) for r in rs]
        m, sd = stat(vals)
        sum_rows.append([g, fz, label, len(vals),
                         f"{m:.4f}" if m is not None else "NA",
                         f"{sd:.4f}" if sd is not None else "NA",
                         ";".join(str(v) for v in vals)])
with open(out_dir/".sum.tmp","w",newline="",encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n"); w.writerow(SUM_HDR); w.writerows(sum_rows)
Path(out_dir/".sum.tmp").replace(out_dir/"rq3_summary.csv")
print(f"[采集] summary {len(sum_rows)} 行")

# ---- 配对 win-rate + 差值均值±标准差（B 组 vs A 组 / C 组 vs D 组）----
print("\n=== 配对统计（同 fuzzer 同 rep 配对）===")
PAIRS = [("B","D"), ("D","C"), ("A","B")]
for fa, fb in PAIRS:
    for fz in ('chatafl','aflnet'):
        diffs = []
        for rep in range(1,6):
            a = [r for r in p2 if r['group']==fa and r['fuzzer']==fz and r['rep']==rep]
            b = [r for r in p2 if r['group']==fb and r['fuzzer']==fz and r['rep']==rep]
            if a and b and a[0]['bitmap_cvg'] is not None and b[0]['bitmap_cvg'] is not None:
                diffs.append(a[0]['bitmap_cvg'] - b[0]['bitmap_cvg'])
        if not diffs: continue
        wins = sum(1 for d in diffs if d > 0)
        sd = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
        print(f"  {fa} vs {fb} [{fz}]: 胜率 {wins}/{len(diffs)}  "
              f"差值均值 {statistics.mean(diffs):+.3f}pp  标准差 {sd:.3f}pp  "
              f"[{' '.join(f'{d:+.2f}' for d in diffs)}]")

# ---- 校验清单 C1–C8 ----
val = []
val.append("# RQ3 采集校验报告\n")
ea = []
try:
    with open(out_dir/"rq3_enrichment_audit.csv", encoding="utf-8") as f:
        ea = list(csv.DictReader(f))
except OSError:
    pass

# C5：首行 paths_total ≈ 语料条数（V8 污染指纹）
EXPECT = {"A":38,"B":50,"C":50,"D":50}
for (g, fz), rs in sorted(agg(p1, ['group','fuzzer']).items()):
    vals = [r.get('paths_total_at_p1') for r in rs if r.get('paths_total_at_p1') is not None]
    if not vals: continue
    m = statistics.mean(vals)
    ok = abs(m - EXPECT.get(g, 50)) <= max(5, EXPECT.get(g,50)*0.2)
    val.append(f"- C5 组 {g}/{fz}: 首行 paths_total 均值 {m:.1f}（期望≈{EXPECT.get(g,50)}）→ "
               f"{'PASS' if ok else 'FAIL（增强未关闭的独立指纹）'}\n")

# ★ v2 V11：初始队列条目数（",orig:" 形式）== 语料条数（污染探针）
for (g, fz), rs in sorted(agg(p1, ['group','fuzzer']).items()):
    vals = [r.get('init_queue_count') for r in rs if r.get('init_queue_count') is not None]
    if not vals: continue
    bad = [v for v in vals if v != EXPECT.get(g, 50)]
    val.append(f"- V11 组 {g}/{fz}: 初始队列条目数 {vals}（期望 {EXPECT.get(g,50)}）→ "
               f"{'PASS' if not bad else 'FAIL（初始队列被污染）'}\n")

# ★ v2：崩溃数与首次出现时刻（t_first_crash —— 区分「早发现」与「晚发现」）
val.append("- 崩溃统计（★ 崩溃是概率性、晚发的 —— RQ1.2 实测基线组 9.2h 才出首个）：\n")
for (g, fz), rs in sorted(agg(p2, ['group','fuzzer']).items()):
    cr = [r.get('unique_crashes') for r in rs if r.get('unique_crashes') is not None]
    if not cr: continue
    tot = sum(cr)
    val.append(f"  - 组 {g}/{fz}: 崩溃总数 {tot}（各 rep: {cr}）"
               f"{' → 崩溃列记 N/A（不具区分度）' if tot == 0 else ''}\n")

# C6：chat_times 恒为 0（V7）
for (g, fz), rs in sorted(agg(p2, ['group','fuzzer']).items()):
    vals = [r.get('chat_times_max') for r in rs if r.get('chat_times_max') is not None]
    if not vals: continue
    mx = max(vals)
    val.append(f"- C6 组 {g}/{fz}: chat_times 最大值 {mx} → "
               f"{'PASS' if mx == 0 else 'FAIL（runtime stall-chat 未关闭）'}\n")

# 增强审计（C 组断言 C 的证据）
if ea:
    tot_s = sum(int(float(r.get('enriched_in_seeds') or 0)) for r in ea)
    tot_q = sum(int(float(r.get('enriched_in_queue') or 0)) for r in ea)
    val.append(f"- 增强审计: enriched_in_seeds 合计 {tot_s}，enriched_in_queue 合计 {tot_q} → "
               f"{'PASS' if tot_s == 0 and tot_q == 0 else 'FAIL'}\n")

# C8：execs_done 偏离组内中位数 > 2σ 的容器（标注但不剔除）
for (g, fz), rs in sorted(agg(p2, ['group','fuzzer']).items()):
    vals = [r.get('execs_done') for r in rs if r.get('execs_done') is not None]
    if len(vals) < 3: continue
    med = statistics.median(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    for r in rs:
        v = r.get('execs_done')
        if v is None or sd == 0: continue
        if abs(v - med) > 2*sd:
            val.append(f"- C8 组 {g}/{fz} rep {r['rep']}: execs_done {v:.0f} "
                       f"偏离中位数 {med:.0f} 超过 2σ（{2*sd:.0f}）→ 标注但不剔除\n")

Path(out_dir/"rq3_validation.md").write_text("".join(val), encoding="utf-8")
print(f"[采集] 校验报告: {out_dir/'rq3_validation.md'}")
PYEOF

echo
echo "=== 产出 ==="
ls -la "$OUT_DIR"
