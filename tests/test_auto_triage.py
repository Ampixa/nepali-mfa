from __future__ import annotations

import csv
import json
from pathlib import Path

from nepali_mfa.auto_triage import main


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_auto_triage_splits_silver_review_and_reject(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {"id": "silver", "transcript": "नेपाल राम्रो छ", "duration_sec": 5.0, "oov_words": []},
                {"id": "artifact", "transcript": "[सङ्गीत] नेपाल राम्रो छ", "duration_sec": 5.0},
                {"id": "too_long", "transcript": "नेपाल राम्रो छ", "duration_sec": 45.0},
                {"id": "human_bg", "transcript": "नेपाल राम्रो छ", "duration_sec": 6.0},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    review = tmp_path / "review.tsv"
    review.write_text("id\tlabel\tnotes\nhuman_bg\tbackground_audio\tbed\n", encoding="utf-8")
    asr = tmp_path / "asr.csv"
    with asr.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "cer", "wer"])
        writer.writeheader()
        writer.writerow({"id": "silver", "cer": "0.02", "wer": "0.08"})
        writer.writerow({"id": "artifact", "cer": "0.01", "wer": "0.02"})
        writer.writerow({"id": "too_long", "cer": "0.01", "wer": "0.02"})
    out = tmp_path / "out"

    assert main([
        "--manifest",
        str(manifest),
        "--review-tsv",
        str(review),
        "--asr-scores-csv",
        str(asr),
        "--out-dir",
        str(out),
    ]) == 0

    silver = read_jsonl(out / "auto_silver_clean.jsonl")
    bronze = read_jsonl(out / "auto_bronze_asr.jsonl")
    rejected = read_jsonl(out / "auto_rejected.jsonl")
    needs_review = read_jsonl(out / "needs_review.jsonl")
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))

    assert [row["id"] for row in silver] == ["silver"]
    assert [row["id"] for row in bronze] == ["human_bg"]
    assert [row["id"] for row in rejected] == ["artifact"]
    assert [row["id"] for row in needs_review] == ["too_long"]
    assert summary["by_split"] == {
        "auto_silver_clean": 1,
        "auto_bronze_asr": 1,
        "auto_rejected": 1,
        "needs_review": 1,
    }
    assert summary["top_reasons"]["bracketed_non_speech"] == 1


def test_auto_triage_uses_mfa_failure_as_bronze_or_review(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps({"id": "mfa_risky", "transcript": "यो मिलेको छ", "duration_sec": 4.0}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    failure = tmp_path / "failure.csv"
    failure.write_text("id\tissue_bucket\nmfa_risky\tlow_snr\n", encoding="utf-8")
    out = tmp_path / "out"

    assert main([
        "--manifest",
        str(manifest),
        "--failure-audit-csv",
        str(failure),
        "--review-risk",
        "60",
        "--out-dir",
        str(out),
    ]) == 0

    bronze = read_jsonl(out / "auto_bronze_asr.jsonl")
    assert [row["id"] for row in bronze] == ["mfa_risky"]
    assert bronze[0]["use_for_asr_training"] is True
    assert bronze[0]["use_for_clean_mfa_seed_candidate"] is False
