"""tests for core.models — SeedCorpus / SeedMessage round-trip（v1 数据类已退役）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.models import SeedCorpus, SeedMessage


def test_seed_corpus_round_trip():
    sc = SeedCorpus(
        protocol="rtsp",
        description="Basic playback",
        target_state_path=["Init", "Ready", "Playing"],
        target_methods=["PLAY"],
        messages=[
            SeedMessage(method="OPTIONS", headers={"CSeq": "1"}),
            SeedMessage(method="SETUP", headers={"CSeq": "3", "Transport": "RTP/AVP"}),
            SeedMessage(method="PLAY", headers={"CSeq": "4", "Session": "{{session_id}}"}),
        ],
        generated_by="llm-StubLLMClient",
    )
    d = sc.to_dict()
    sc2 = SeedCorpus.from_dict(d)
    assert len(sc2.messages) == 3
    assert sc2.messages[2].headers["Session"] == "{{session_id}}"


def test_seed_message_to_dict():
    m = SeedMessage(method="PLAY", headers={"CSeq": "4"}, body="")
    d = m.to_dict()
    assert d["method"] == "PLAY"
    assert d["headers"] == {"CSeq": "4"}
