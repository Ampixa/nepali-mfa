from __future__ import annotations

import csv
import json
from pathlib import Path

from nepali_mfa.audit_alignment_baseline import main


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_audit_alignment_baseline_splits_review_and_pass(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {
                    "id": "good",
                    "source": "slr54",
                    "transcript": "नेपाल राम्रो छ",
                    "duration_sec": 2.0,
                    "oov_words": [],
                },
                {
                    "id": "bad",
                    "source": "youtube",
                    "transcript": "गलत मिलेन",
                    "duration_sec": 3.0,
                    "oov_words": ["मिलेन"],
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    failure = tmp_path / "failure.csv"
    with failure.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "slice_source",
                "source",
                "issue_bucket",
                "has_textgrid",
                "duration_sec",
                "oov_count",
                "oov_words",
                "transcript",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "bad",
                "slice_source": "youtube",
                "source": "youtube",
                "issue_bucket": "missing_textgrid",
                "has_textgrid": "False",
                "duration_sec": "3.0",
                "oov_count": "1",
                "oov_words": "मिलेन",
                "transcript": "गलत मिलेन",
            }
        )
    analysis = tmp_path / "analysis.csv"
    analysis.write_text(
        "file,begin,end,speaker,overall_log_likelihood,speech_log_likelihood,phone_duration_deviation,snr\n"
        "good,0,2,unknown,-10,-9,1,20\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"

    assert main([
        "--manifest",
        str(manifest),
        "--failure-audit-csv",
        str(failure),
        "--analysis-csv",
        str(analysis),
        "--out-dir",
        str(out),
    ]) == 0

    assert [row["id"] for row in read_jsonl(out / "machine_pass_candidates.jsonl")] == ["good"]
    assert [row["id"] for row in read_jsonl(out / "machine_review_candidates.jsonl")] == ["bad"]
    assert "missing_textgrid" in (out / "manual_review_template.tsv").read_text(encoding="utf-8")
    summary = json.loads((out / "baseline_summary.json").read_text(encoding="utf-8"))
    assert summary["machine_pass_rows"] == 1
    assert summary["machine_review_rows"] == 1
