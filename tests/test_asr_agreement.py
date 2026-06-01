from __future__ import annotations

import csv
import json
from pathlib import Path

from nepali_mfa.asr_agreement import clean_for_scoring, main, score_pair


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_score_pair_normalizes_punctuation_and_markers() -> None:
    score = score_pair(">> नेपाल राम्रो छ ।", "नेपाल राम्रो छ")

    assert score["cer"] == 0
    assert score["wer"] == 0
    assert clean_for_scoring("[सङ्गीत] नेपाल") == "नेपाल"


def test_asr_agreement_writes_scores_for_multiple_hypotheses(tmp_path: Path) -> None:
    reference = tmp_path / "reference.jsonl"
    reference.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {"id": "good", "transcript": "नेपाल राम्रो छ"},
                {"id": "bad", "transcript": "नेपाल राम्रो छ"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    hyp1 = tmp_path / "whisper.jsonl"
    hyp1.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {"id": "good", "text": "नेपाल राम्रो छ"},
                {"id": "bad", "text": "गलत पाठ छ"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    hyp2 = tmp_path / "chirp.tsv"
    with hyp2.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, delimiter="\t", fieldnames=["id", "prediction"])
        writer.writeheader()
        writer.writerow({"id": "good", "prediction": "नेपाल राम्रो छ"})
        writer.writerow({"id": "bad", "prediction": "नेपाल गलत छ"})
    out = tmp_path / "out"

    assert main([
        "--reference",
        str(reference),
        "--hypothesis",
        str(hyp1),
        "--hypothesis",
        str(hyp2),
        "--out-dir",
        str(out),
    ]) == 0

    rows = read_jsonl(out / "asr_agreement_scores.jsonl")
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))

    assert rows[0]["id"] == "good"
    assert rows[0]["asr_agreement_pass"] is True
    assert rows[0]["cer"] == 0
    assert rows[1]["id"] == "bad"
    assert rows[1]["asr_agreement_pass"] is False
    assert rows[1]["cer"] > 0
    assert summary["rows"] == 2
    assert summary["rows_all_models_pass"] == 1
