from __future__ import annotations

import json
from pathlib import Path

from nepali_mfa.select_review_batch import main


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_select_review_batch_balances_sources_and_reasons(tmp_path: Path) -> None:
    manifest = tmp_path / "auto_triaged_all.jsonl"
    rows = [
        {
            "id": "a1",
            "source": "a",
            "duration_sec": 10,
            "review_decision": "review",
            "quality_tier": "auto_needs_review",
            "auto_triage": {"reasons": ["high_asr_cer"]},
        },
        {
            "id": "a2",
            "source": "a",
            "duration_sec": 10,
            "review_decision": "review",
            "quality_tier": "auto_needs_review",
            "auto_triage": {"reasons": ["high_asr_cer"]},
        },
        {
            "id": "b1",
            "source": "b",
            "duration_sec": 10,
            "review_decision": "review",
            "quality_tier": "auto_needs_review",
            "auto_triage": {"reasons": ["bracketed_non_speech"]},
        },
        {
            "id": "silver",
            "source": "b",
            "duration_sec": 10,
            "review_decision": "accept_silver",
            "quality_tier": "auto_silver_asr_mfa",
            "auto_triage": {"reasons": ["all_available_checks_passed"]},
        },
    ]
    manifest.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    out = tmp_path / "out"

    assert main([
        "--manifest",
        str(manifest),
        "--out-dir",
        str(out),
        "--limit-rows",
        "2",
        "--stratify",
        "source_reason",
        "--seed",
        "1",
    ]) == 0

    batch = read_jsonl(out / "review_batch.jsonl")
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))

    assert len(batch) == 2
    assert {row["source"] for row in batch} == {"a", "b"}
    assert "silver" not in {row["id"] for row in batch}
    assert summary["candidate_rows"] == 3
    assert summary["selected"]["rows"] == 2


def test_select_review_batch_can_limit_by_hours(tmp_path: Path) -> None:
    manifest = tmp_path / "rows.jsonl"
    manifest.write_text(
        "\n".join(
            json.dumps({
                "id": f"x{i}",
                "duration_sec": 20,
                "review_decision": "review",
                "quality_tier": "auto_needs_review",
            })
            for i in range(5)
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"

    assert main([
        "--manifest",
        str(manifest),
        "--out-dir",
        str(out),
        "--limit-rows",
        "5",
        "--max-hours",
        str(40 / 3600),
    ]) == 0

    batch = read_jsonl(out / "review_batch.jsonl")
    assert len(batch) == 2
