from __future__ import annotations

import json
from pathlib import Path

from nepali_mfa.apply_source_review_labels import main


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_apply_source_review_labels_promotes_keep_and_minor_to_clean_candidate(tmp_path: Path) -> None:
    manifest = tmp_path / "source_review_manifest.jsonl"
    manifest.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {"id": "keep1", "transcript": "ठिक छ", "duration_sec": 10},
                {"id": "minor1", "transcript": "सानो समस्या", "duration_sec": 20},
                {"id": "bg1", "transcript": "पछाडि आवाज", "duration_sec": 30},
                {"id": "textbad1", "transcript": "गलत पाठ", "duration_sec": 40},
                {"id": "open1", "transcript": "हेर्न बाकी", "duration_sec": 50},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    review = tmp_path / "source_review.tsv"
    review.write_text(
        "id\tsource\tslice_source\tduration_sec\toov_count\tlabel\tnotes\ttranscript\taudio_source\n"
        "keep1\tsushant\tsushant_source_reviewed_le30\t10\t0\tkeep\t\tठिक छ\t/a.wav\n"
        "minor1\tsushant\tsushant_source_reviewed_le30\t20\t0\tminor\tbreath cut\tसानो समस्या\t/b.wav\n"
        "bg1\tsushant\tsushant_source_reviewed_le30\t30\t0\tbackground_audio\troom bed\tपछाडि आवाज\t/c.wav\n"
        "textbad1\tsushant\tsushant_source_reviewed_le30\t40\t0\ttext_bad\twrong words\tगलत पाठ\t/d.wav\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"

    assert main(["--manifest", str(manifest), "--review-tsv", str(review), "--out-dir", str(out)]) == 0

    clean = read_jsonl(out / "mfa_clean_seed_candidate.jsonl")
    noisy = read_jsonl(out / "asr_noisy_background.jsonl")
    rejected = read_jsonl(out / "rejected.jsonl")
    needs_review = read_jsonl(out / "needs_review.jsonl")
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))

    assert [row["id"] for row in clean] == ["keep1", "minor1"]
    assert all(row["use_for_clean_mfa_seed_candidate"] is True for row in clean)
    assert [row["id"] for row in noisy] == ["bg1"]
    assert [row["id"] for row in rejected] == ["textbad1"]
    assert [row["id"] for row in needs_review] == ["open1"]
    assert summary["by_split"] == {
        "mfa_clean_seed_candidate": 2,
        "asr_noisy_background": 1,
        "rejected": 1,
        "needs_review": 1,
    }
    assert summary["hours_by_split"]["mfa_clean_seed_candidate"] == round(30 / 3600, 6)


def test_apply_source_review_labels_normalizes_common_background_alias(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps({"id": "x", "duration": 5}, ensure_ascii=False) + "\n", encoding="utf-8")
    review = tmp_path / "review.tsv"
    review.write_text("id\tlabel\tnotes\nx\tbg\tbed\n", encoding="utf-8")
    out = tmp_path / "out"

    assert main(["--manifest", str(manifest), "--review-tsv", str(review), "--out-dir", str(out)]) == 0

    noisy = read_jsonl(out / "asr_noisy_background.jsonl")
    assert noisy[0]["review_label"] == "background_audio"
