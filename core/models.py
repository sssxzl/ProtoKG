"""ProtoRAG 数据模型 —— 生成的种子（输出层）。

2026-10-09 清理：v1 的 ProtocolNorm / StateMachine / Transition / FieldConstraint /
VulnSeed / RetrievalBundle / NORM_KINDS / NORM_FACETS 已退役（对应代码已随 v1 架构
退役删除，2026-10-09）。现仅保留 v2 通路需要的 SeedMessage / SeedCorpus。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict


@dataclass
class SeedMessage:
    """会话种子里的单条消息。"""
    method: str                           # "PLAY" / "MAIL"
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    url: str = ""                         # 该消息的 URL（空则用种子级 url），
    # 用于多轨媒体 track1/track2 等不同 URL 的消息
    # 占位符:Session/CSeq 等可填 {{session_id}}/{{cseq}} 运行时替换
    # LLM 生成时就用占位符,真正执行时由 fuzzer 解析
    argument: str = ""                    # 行命令协议的命令参数（如 SMTP 的
    # "FROM:<sender@example.com>"），URL 类协议留空。空则渲染裸命令。

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SeedMessage":
        return cls(
            method=d.get("method", ""),
            headers=dict(d.get("headers", {})),
            body=d.get("body", ""),
            url=d.get("url", ""),
            argument=d.get("argument", ""),
        )


@dataclass
class SeedCorpus:
    """一个完整的会话种子(有序 message 列表)。"""
    seed_id: str = field(default_factory=lambda: f"seed-{uuid.uuid4().hex[:8]}")
    protocol: str = ""
    description: str = ""                # 人类可读的描述
    target_state_path: list[str] = field(default_factory=list)
    target_methods: list[str] = field(default_factory=list)
    target_vuln_class: str = ""
    messages: list[SeedMessage] = field(default_factory=list)
    generated_by: str = ""               # "llm-deepseek" | "rule-based" | ...
    selected_url: str = ""               # 种子级资源 URL（目标实例知识），
    # 消息级 url 为空时用此值；raw_writer 会优先取 selected_url

    def to_dict(self) -> dict:
        return {
            "seed_id": self.seed_id,
            "protocol": self.protocol,
            "description": self.description,
            "target_state_path": list(self.target_state_path),
            "target_methods": list(self.target_methods),
            "target_vuln_class": self.target_vuln_class,
            "messages": [m.to_dict() for m in self.messages],
            "generated_by": self.generated_by,
            "selected_url": self.selected_url,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SeedCorpus":
        return cls(
            seed_id=d.get("seed_id", ""),
            protocol=d.get("protocol", ""),
            description=d.get("description", ""),
            target_state_path=list(d.get("target_state_path", [])),
            target_methods=list(d.get("target_methods", [])),
            target_vuln_class=d.get("target_vuln_class", ""),
            messages=[SeedMessage.from_dict(m)
                      for m in d.get("messages", [])],
            generated_by=d.get("generated_by", ""),
            selected_url=d.get("selected_url", ""),
        )


__all__ = ["SeedMessage", "SeedCorpus"]
