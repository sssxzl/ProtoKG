# -*- coding: utf-8 -*-
"""seedcheck/model.py —— **种子校验层的数据模型**。

★ 为什么单独一个文件：V1~V6 六个检查器都要用同一套「违规 / 种子 / 报告」结构
  ⇒ 集中定义 ⇒ 避免各检查器各造一套 ⇒ 也便于单测。

★ 设计要点
  · **校验 ≠ 过滤**：除 V1（格式必假）外，其余检查一律只**打标**（level=edge_case）
    ⇒ 因为「违反协议」恰恰是 fuzzing 最有价值的输入面（可能触发解析缺陷）
    ⇒ 详见 docs/设计/种子校验层设计.md。
  · **可追溯**：每条违规都带 ``evidence``（判据来源：中枢维度 / 规范位置 / 事实名）
    ⇒ 否则使用者无法判断该不该修。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

#: 违规等级
LEVEL_COMPLIANT = "compliant"      # 合规（走正常路径）
LEVEL_EDGE = "edge_case"           # 协议越界（★ 高价值：故意的协议违反）
LEVEL_MALFORMED = "malformed"      # 格式非法（服务器必然拒 ⇒ 零价值 ⇒ 阻断）

#: 检查层（V1~V6）
LAYERS = ("V1", "V2", "V3", "V4", "V5", "V6")


@dataclass
class Violation:
    """一条违规。

    Attributes:
        layer: 所属检查层（V1~V6）。
        code: 机器可读代码（如 ``missing_required_header``）。
        message: 人读描述。
        seed: 出问题的种子文件名（无则为空）。
        target: 具体对象（方法名 / 头名 / 资源名 …）。
        evidence: **判据来源**（中枢维度名 / 事实 id / 规范位置）⇒ 可追溯。
    """
    layer: str
    code: str
    message: str
    seed: str = ""
    target: str = ""
    evidence: str = ""

    def key(self) -> tuple:
        return (self.layer, self.code, self.seed, self.target)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SeedRecord:
    """一条种子（= 一个 ``*.raw`` 文件）的校验结果。"""
    filename: str
    messages: list[dict] = field(default_factory=list)   # [{method, uri, version, headers{}}]
    raw_text: str = ""
    #: ★ 原始**字节**视图（**二进制协议**的长度判定需要 ⇒ 2026-11-12 E5）
    #:   ⇒ text 协议可为空；binary 协议必须填
    raw_bytes: bytes = b""
    level: str = LEVEL_COMPLIANT
    tags: list[str] = field(default_factory=list)         # 去重后的违规 code
    violations: list[Violation] = field(default_factory=list)

    def add(self, v: Violation) -> None:
        self.violations.append(v)
        if v.code not in self.tags:
            self.tags.append(v.code)
        # ★ 等级取「最严重」：malformed > edge_case > compliant
        if v.layer == "V1":
            self.level = LEVEL_MALFORMED
        elif v.layer in ("V2", "V3", "V4") and self.level == LEVEL_COMPLIANT:
            self.level = LEVEL_EDGE

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "level": self.level,
            "tags": list(self.tags),
            "violations": [v.to_dict() for v in self.violations],
        }


@dataclass
class Report:
    """一次校验的完整报告。"""
    protocol: str = ""
    seed_dir: str = ""
    target_env: str = ""
    layers_run: list[str] = field(default_factory=list)
    seeds: list[SeedRecord] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    violations: list[Violation] = field(default_factory=list)   # 全局（非种子级）
    llm: dict[str, Any] = field(default_factory=dict)

    # ---- 统计 ----
    def groups(self) -> dict[str, int]:
        out = {LEVEL_COMPLIANT: 0, LEVEL_EDGE: 0, LEVEL_MALFORMED: 0}
        for s in self.seeds:
            out[s.level] = out.get(s.level, 0) + 1
        return out

    def by_code(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in self.violations:
            out[v.code] = out.get(v.code, 0) + 1
        for s in self.seeds:
            for v in s.violations:
                out[v.code] = out.get(v.code, 0) + 1
        return out

    def to_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "seed_dir": self.seed_dir,
            "target_env": self.target_env,
            "layers_run": list(self.layers_run),
            "seed_count": len(self.seeds),
            "groups": self.groups(),
            "metrics": dict(self.metrics),
            "by_code": self.by_code(),
            "violations": [v.to_dict() for v in self.violations],
            "llm": dict(self.llm),
            "seeds": [s.to_dict() for s in self.seeds],
        }

    def write(self, out_dir: Path) -> tuple[Path, Path]:
        """写 JSON + 人读摘要 ⇒ 返回 (json 路径, txt 路径)。"""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        jp = out_dir / "seed_preflight.json"
        tp = out_dir / "seed_preflight.txt"
        jp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                      encoding="utf-8")
        tp.write_text(self.summary_text(), encoding="utf-8")
        return jp, tp

    def summary_text(self) -> str:
        """人读摘要（结论先行 + 分层统计 + 违规明细）。"""
        g = self.groups()
        lines: list[str] = []
        lines.append("== 种子校验（seedcheck）==")
        lines.append(f"  协议: {self.protocol or '(未知)'}  |  语料: {self.seed_dir}")
        lines.append(f"  目标环境: {self.target_env or '(未指定 ⇒ V3 跳过)'}")
        lines.append(f"  执行层: {', '.join(self.layers_run) or '(无)'}")
        lines.append(f"  种子: {len(self.seeds)} 条  ⇒ 合规 {g.get(LEVEL_COMPLIANT, 0)}"
                     f" / 越界 {g.get(LEVEL_EDGE, 0)} / 非法 {g.get(LEVEL_MALFORMED, 0)}")
        # 指标
        if self.metrics:
            lines.append("")
            lines.append("  ── 指标 ──")
            for k, v in self.metrics.items():
                lines.append(f"    {k}: {v}")
        # 违规统计
        codes = self.by_code()
        if codes:
            lines.append("")
            lines.append("  ── 违规统计 ──")
            for c, n in sorted(codes.items(), key=lambda kv: -kv[1]):
                lines.append(f"    {c:34s} {n}")
        # 明细（只列 seed 级，每种子最多 4 条）
        details = [v for s in self.seeds for v in s.violations]
        if details:
            lines.append("")
            lines.append("  ── 明细 ──")
            for s in self.seeds:
                if not s.violations:
                    continue
                lines.append(f"  [{s.level}] {s.filename}")
                for v in s.violations[:4]:
                    ev = f"  〔依据: {v.evidence}〕" if v.evidence else ""
                    lines.append(f"    ✗ {v.layer} {v.code}: {v.message}{ev}")
                if len(s.violations) > 4:
                    lines.append(f"    … 另 {len(s.violations) - 4} 条")
        # LLM
        if self.llm:
            lines.append("")
            lines.append("  ── LLM 语义审查（只报告）──")
            for k, v in self.llm.items():
                lines.append(f"    {k}: {v}")
        return "\n".join(lines) + "\n"
