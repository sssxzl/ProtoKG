"""conftest — shared pytest root for ProtoKG tests.

2026-10-09 清理：v1 代码已退役，原 _ensure_registry_builtins（依赖 v1 的
core.classifier / core.extractors / core.registry）与 kb_driven_spec_graph
（依赖 v1 的 core.spec_graph）均已删除。现仅保留 sys.path 设置，让
tests/fused/ 能 `import core.fused.*`。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
