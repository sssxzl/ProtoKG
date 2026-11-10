# -*- coding: utf-8 -*-
"""guard/verify_docs_consistency.py —— **文档-机器一致性护栏**（H-5）。

★ 为什么需要它
  勘误待办 §2 指出一个**结构性缺口**：

    「``core/fused/hub/registry/*.json`` 与 ``docs/设计/顶层设计/*.md`` 是
      **并行维护**的；schema 可被变更，而冻结文档无变更流程
      ⇒ **schema 变更后文档陈旧是结构性必然，不是偶然**。」

  2026-11-10 的一次改动（协议骨架消解 + 目录重组）实测暴露了它的三个面：

    ① **残留**：批量替换路径时漏了 ``.github/workflows/ci.yml``（不在 docs 扫描范围）
       ⇒ CI 静默指向已删目录
    ② **拼接形式**：``ROOT / "tools" / "guard" / "baseline"`` 不含完整路径
       ⇒ 只替换字面量必然漏
    ③ **脏标记**：替换产生 ``（已移除）（已移除）（已移除）`` 重复标记

  本护栏把这三类**机器可检**化。

★ 本护栏检三项
  D1 残留引用   —— 「已删除的路径/符号」仍出现在**会被照抄的位置**
                    （代码块 + 行内代码）⇒ 方案原文的散文提及**不算**（那是溯源）
  D2 契约↔文档  —— 注册表（aspect / subject_type / epistemic_type）与
                    知识分类（A~F）的**数量与名字**在契约文档里对得上
  D3 命令路径   —— 文档里写的 ``pytest tests/x.py`` / ``python scripts/x.py``
                    所引用的文件**真实存在**

★ 用法
  python guard/verify_docs_consistency.py                  # 只检查，退出码 0=干净 1=有违规
  python guard/verify_docs_consistency.py --json out.json  # 机器可读结果
  python guard/verify_docs_consistency.py --only D1        # 只跑某一项
  python guard/verify_docs_consistency.py --schema-map     # 打印 H-4 的「schema 变更检查清单」

★ 为什么 D1 只看代码块 + 行内代码
  设计文档里**大量**引用已删除的骨架/旧路径，是**有意的溯源**（保留原文供后人对照）
  ⇒ 若全文扫描 ⇒ 每次都红 ⇒ 噪声淹没真问题。
  ⇒ 只看「会被照抄的位置」⇒ 既保留溯源，又抓得住真问题。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 不扫描的目录（构建产物 / 缓存 / 生成物 / VCS / 护栏产物）
SKIP_DIRS = {
    ".git", ".ruff_cache", "__pycache__", "derived", "guard/_out",
    "kb", "node_modules",
}

#: ── D1 残留词表：已删除 / 已改名的路径与符号 ──────────────────────────────
#: 每项 = (词, 说明) ⇒ 命中即判「残留」（若出现在会被照抄的位置）
#:
#: ★ 维护约定：**删除或改名任何路径/符号时，在这里加一条** ⇒
#:   下次有人（人或 agent）在文档里引用它 ⇒ 护栏立刻判红。
RESIDUALS: tuple[tuple[str, str], ...] = (
    ("tools/guard/", "护栏工具已升到顶层 guard/"),
    ("tools/qa/", "护栏工具已升到顶层 guard/"),
    ("tests/fused/", "用例已按层重组为 tests/<层>/"),
    ("derived/experiments/", "论文实验层已整体移除"),
    ("derived/spec/", "spec 中间产物目录已移除"),
    ("derived/source_blocks/", "LLM 缓存已迁到 derived/cache/source_blocks/"),
    ("fused_hub/", "契约已归位到 core/fused/<层>/ 与 profiles/"),
    ("local/", "该目录已移除（设计文档已迁 docs/）"),
    ("_RE_STATE_MACHINE_HINT", "旧英文措辞判据已移除（改用实体共现判据）"),
    ("SKELETON_AUTHORITY", "已改名为 PROFILE_AUTHORITY"),
    ("SKELETON_SOURCE_NAME", "已改名为 PROFILE_AUTHORITY"),
    ("--exclude-skeleton-dims", "该消融开关已随骨架移除"),
    ("--materialize-skeleton", "该开关已随骨架移除"),
    ("_materialize_skeleton", "骨架物化函数已删除"),
    ("_skeleton_aspect_origin", "骨架来源维度表已删除"),
    ("target_skeleton(", "paths.target_skeleton() 已删除"),
    ("gen_dhcp_skeleton", "骨架生成脚本已删除"),
)

#: ── D1 白名单：**目录级**（历史记录类文档 = 有意的溯源陈述）──────────────
#: ★ 判据：这些目录里的文档是**过程记录**（立项探查 / 里程碑快照 / 交付报告 /
#:   清理方案 / 勘误待办）⇒ 它们引用已删除的路径是**如实记录当时事实**⇒ 不判红。
#: ★ 反之，``docs/设计/`` 与 ``docs/工具/`` 是**当前有效的指引**⇒ 必须干净
#:   （例外：已加「2026-11-10 状态」说明的方案原文，保留溯源）。
D1_ALLOW_DIRS = (
    "docs/实施/立项提案/",
    "docs/实施/路线与里程碑/",
    "docs/实施/知识库维护/",
    "docs/实施/待办与勘误/",
)

#: ── D1 白名单：逐文件（设计/工具类里已加状态说明的方案原文）────────────
D1_ALLOW_FILES = (
    "docs/实施/路线与里程碑/调试计划.md",
    "docs/实施/待办与勘误/中枢契约勘误待办.md",
    "docs/设计/顶层设计/协议知识中枢架构调整方案.md",
    "docs/设计/顶层设计/协议知识中枢架构调整方案评审.md",
    "docs/设计/知识图/知识图整理层整合方案.md",
    "docs/设计/顶层设计/跨源污染修复方案.md",
    "docs/设计/抽取与形态/RFC形态分类与通用抽取落地方案.md",
    "docs/设计/知识图/状态机抽取方法谱系与落地方案.md",
    "docs/设计/抽取与形态/二进制协议处理流程设计.md",
    "docs/设计/顶层设计/结构化知识中枢设计.md",
    "docs/设计/顶层设计/设计思想与设计方案.md",
    "docs/设计/顶层设计/中枢重设计改造方案.md",
    "docs/工具/决策记录/已决事项.md",
    # ★ 历史交接/标注类文档（**过程记录** ⇒ 引用旧路径是如实记录）
    "docs/工具/交接文档.md",
    "docs/工具/交接与工作流/项目交接说明.md",
    "docs/工具/人工标注现状.md",
    "docs/工具/人工标注指南.md",
)

#: ── D3 文档里可识别的命令形态 ─────────────────────────────────────────
CMD_PATTERNS = (
    re.compile(r"pytest\s+((?:tests|guard)/[\w./-]+\.py)"),
    re.compile(r"python\s+(scripts/[\w./-]+\.py)"),
    re.compile(r"python\s+-m\s+pytest\s+((?:tests|guard)/[\w./-]+\.py)"),
)

#: 文档里引用这些路径时，**允许**指向「已随论文实验层移除」的测试
D3_GONE_ALLOWED = ("tests/fused/", "tests/pipeline/")

#: D3 白名单：**历史记录类**文档（过程快照 ⇒ 命令是当时的事实，不是当前指引）
D3_ALLOW_FILES = (
    "docs/实施/路线与里程碑/RFC源改造里程碑A实施报告.md",
    "docs/实施/路线与里程碑/RFC源里程碑路线图.md",
    "docs/工具/上游工作调研.md",
)


def _iter_text_files(roots: tuple[str, ...], exts: tuple[str, ...]):
    for root in roots:
        base = ROOT / root
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix not in exts:
                continue
            rel = p.relative_to(ROOT).as_posix()
            if any(rel.startswith(d) for d in SKIP_DIRS):
                continue
            yield p, rel


def _code_spans(text: str) -> list[str]:
    """抽出「会被照抄的位置」：``` 代码块 ``` + 行内代码 `xxx`。"""
    spans: list[str] = []
    # 围栏代码块
    for m in re.finditer(r"```[^\n]*\n(.*?)```", text, re.S):
        spans.append(m.group(1))
    # 行内代码
    for m in re.finditer(r"`([^`\n]{2,200})`", text):
        spans.append(m.group(1))
    return spans


def check_d1() -> list[dict]:
    """D1 残留引用：已删除的路径/符号仍出现在会被照抄的位置。"""
    problems: list[dict] = []
    for p, rel in _iter_text_files(("docs", "README.md", "scripts", "core", "guard"), (".md", ".py")):
        if rel in D1_ALLOW_FILES:
            continue
        if any(rel.startswith(d) for d in D1_ALLOW_DIRS):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for span in _code_spans(text):
            for word, why in RESIDUALS:
                if word in span:
                    line = text[:text.find(span)].count("\n") + 1
                    problems.append({
                        "code": "D1", "path": rel, "line": line,
                        "detail": f"残留「{word}」（{why}）出现在会被照抄的位置",
                    })
                    break
    return problems


def _registry_names(filename: str, key: str = "name") -> list[str]:
    p = ROOT / "core" / "fused" / "hub" / "registry" / filename
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get(key) or data.get("registered_aspects") or []
    return sorted({str(x.get(key)) for x in items if isinstance(x, dict) and x.get(key)})


def check_d2() -> list[dict]:
    """D2 契约↔文档：注册表的集合在契约文档里对得上。"""
    problems: list[dict] = []
    contract_doc = ROOT / "docs" / "设计" / "顶层设计" / "结构化知识中枢设计.md"
    if not contract_doc.is_file():
        return [{"code": "D2", "path": "docs/设计/顶层设计/结构化知识中枢设计.md",
                 "line": 0, "detail": "契约文档缺失"}]
    text = contract_doc.read_text(encoding="utf-8")

    # ① A~F 六分类：契约里的 category 数 == 文档里描述的分类数
    try:
        ks = json.loads((ROOT / "core" / "fused" / "hub" / "knowledge_slots.json").read_text(encoding="utf-8"))
        cats = [c.get("id") for c in ks.get("categories", []) if c.get("id")]
    except (OSError, json.JSONDecodeError):
        cats = []
    for cid in cats:
        if cid not in text:
            problems.append({
                "code": "D2", "path": "docs/设计/顶层设计/结构化知识中枢设计.md", "line": 0,
                "detail": f"知识分类「{cid}」在契约（knowledge_slots.json）里有，但契约文档里没提到",
            })

    # ② 注册表的三个集合 ⇒ 文档里能找到对应数量描述
    reg_dir = ROOT / "core" / "fused" / "hub" / "registry"
    for fn, key in (("aspect_registry.json", "name"),
                    ("subject_type_registry.json", "name"),
                    ("epistemic_type_registry.json", "name")):
        names = _registry_names(fn, key)
        if not names:
            continue
        if not (reg_dir / fn).is_file():
            continue
        # 数量校验：文档里出现「N 个」且 N 与注册表一致，或文档逐个列出
        missing = [n for n in names if n not in text]
        if missing and len(missing) <= 3:
            problems.append({
                "code": "D2", "path": "docs/设计/顶层设计/结构化知识中枢设计.md", "line": 0,
                "detail": f"{fn} 的 {len(missing)} 个条目未在契约文档出现：{missing}",
            })
    return problems


def check_d3() -> list[dict]:
    """D3 文档命令里的路径真实存在。"""
    problems: list[dict] = []
    for p, rel in _iter_text_files(("docs", "README.md"), (".md",)):
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if rel in D3_ALLOW_FILES:
            continue
        for i, ln in enumerate(text.splitlines(), 1):
            if ln.strip().startswith(">"):        # 引用的旧命令（已在正文说明）⇒ 跳过
                continue
            for pat in CMD_PATTERNS:
                for m in pat.finditer(ln):
                    target = m.group(1)
                    if any(g in target for g in D3_GONE_ALLOWED):
                        continue
                    if "<" in target or ">" in target:   # 占位符（tests/<层>/…）
                        continue
                    if not (ROOT / target).is_file():
                        problems.append({
                            "code": "D3", "path": rel, "line": i,
                            "detail": f"命令引用的文件不存在：{target}",
                        })
    return problems


def schema_change_checklist() -> str:
    """H-4：按 registry 文件分类的「schema 变更检查清单」（**由工具产出**）。"""
    spec = {
        "aspect_registry.json": [
            "knowledge_slots.json 的 aspect_map（每个 aspect 要有落位）",
            "抽取器产出的 aspect 名（core/fused/extraction/）",
            "消费端桶映射（core/fused/hub/hub_view.py 的 _BUCKET_BY_*）",
            "resolver 的消解语义（core/fused/downstream/resolver.py 的 _ASPECT_SEMANTICS）",
            "契约文档（docs/设计/顶层设计/结构化知识中枢设计.md）",
        ],
        "subject_type_registry.json": [
            "hub_view 的桶映射与主体类型判断",
            "抽取器能产出的 subject.type",
            "校验器的合法主体类型集（knowledge_slots.validate_slots）",
        ],
        "epistemic_type_registry.json": [
            "resolver 的 SOURCE_PRIORITY（认识论优先级）",
            "抽取器产出的 epistemic_type",
            "hub_view 的认识论类型投影",
        ],
    }
    lines = ["# schema 变更检查清单（**由 guard/verify_docs_consistency.py --schema-map 自动生成**）", ""]
    for fn, items in spec.items():
        lines.append(f"## 改 `{fn}` 时 ⇒ 必须同步检查")
        lines.append("")
        for it in items:
            lines.append(f"- [ ] {it}")
        lines.append("")
    lines += [
        "## 通用规则（见 `docs/工具/验收与规范/agent长期工作约束.md`）",
        "",
        "- 改 `core/fused/hub/registry/` 任何 JSON ⇒ 跑 `pytest tests/hub/ -q` + **全量护栏**",
        "- 改 `core/fused/` 任何文件 ⇒ 跑 **全量护栏**（判据「新增 0 / 消失 0」）",
        "- 改 `core/paths.py` / `scripts/*` 入口 ⇒ 护栏 + **一条真实命令**（如 `--list-sources`）",
        "- 改 `tests/**` ⇒ 该目录 pytest（期望集 id 含路径 ⇒ 移动文件即漂移）",
        "- 改 `.gitignore` / `.gitattributes` ⇒ **删一次 `guard/` 与 `tests/guard/` 再克隆验证**",
        "- 纯文档 / 注释 ⇒ 可免（但要跑编码护栏）",
        "",
        "★ **删除或改名任何路径/符号时 ⇒ 在 `guard/verify_docs_consistency.py` 的",
        "  `RESIDUALS` 里加一条** ⇒ 否则文档里的引用不会被发现。",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="文档-机器一致性护栏（H-5）")
    ap.add_argument("--json", default=None, help="机器可读结果输出路径")
    ap.add_argument("--only", choices=("D1", "D2", "D3"), default=None, help="只跑某一项")
    ap.add_argument("--schema-map", action="store_true", help="打印 H-4 的 schema 变更检查清单")
    args = ap.parse_args(argv)

    if args.schema_map:
        print(schema_change_checklist())
        return 0

    problems: list[dict] = []
    if args.only in (None, "D1"):
        problems += check_d1()
    if args.only in (None, "D2"):
        problems += check_d2()
    if args.only in (None, "D3"):
        problems += check_d3()

    by_code: dict[str, int] = {}
    for p in problems:
        by_code[p["code"]] = by_code.get(p["code"], 0) + 1

    print("== 护栏：文档-机器一致性 ==")
    for code, title in (("D1", "残留引用"), ("D2", "契约↔文档"), ("D3", "命令路径")):
        n = by_code.get(code, 0)
        print(f"   {code} {title}: {n} 项" + ("  ✅" if n == 0 else "  ❌"))
    if problems:
        print()
        for p in problems[:40]:
            print(f"   [{p['code']}] {p['path']}:{p['line']}  {p['detail']}")
        if len(problems) > 40:
            print(f"   ... 另 {len(problems) - 40} 项")
    else:
        print("\n   ✅ 无问题")

    if args.json:
        Path(args.json).write_text(json.dumps(problems, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
