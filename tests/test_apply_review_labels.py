from __future__ import annotations

import json
from pathlib import Path

from nepali_mfa.apply_review_labels import main


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_apply_mfa_review_labels_splits_and_repairs_numbers(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {"id": "keep1", "transcript": "नेपाल राम्रो छ"},
                {"id": "bg1", "transcript": "बोली स्पष्ट छ"},
                {"id": "num1", "transcript": "एक हजार नौ सय पन्चानब्बे सालमा भयो"},
                {"id": "bad1", "transcript": "गलत पाठ"},
                {"id": "align1", "transcript": "सही पाठ"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    review = tmp_path / "review.tsv"
    review.write_text(
        "id\tlabel\tnotes\tissue_bucket\thas_textgrid\n"
        "keep1\tkeep\t\tlow_snr\t1\n"
        "bg1\tbackground_audio\tmusic bed\tlow_snr\t1\n"
        "num1\tnumber_mismatch\tyear style\tlow_speech_ll\t1\n"
        "bad1\ttext_bad\twrong words\tmissing_textgrid\t0\n"
        "align1\talignment_bad\ttext ok\tmissing_textgrid\t0\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"

    assert main([
        "--manifest", str(manifest),
        "--review-tsv", str(review),
        "--out-dir", str(out),
        "--repair-year-style",
    ]) == 0

    mfa_seed = read_jsonl(out / "mfa_clean_seed.jsonl")
    noisy = read_jsonl(out / "asr_noisy_background.jsonl")
    candidate = read_jsonl(out / "asr_reviewed_candidate.jsonl")
    rejected = read_jsonl(out / "rejected.jsonl")
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))

    assert [row["id"] for row in mfa_seed] == ["keep1", "num1"]
    assert mfa_seed[1]["transcript"] == "उन्नाइस सय पन्चानब्बे सालमा भयो"
    assert mfa_seed[1]["mfa_review"]["number_repaired"] is True
    assert [row["id"] for row in noisy] == ["bg1"]
    assert [row["id"] for row in candidate] == ["align1"]
    assert [row["id"] for row in rejected] == ["bad1"]
    assert summary["number_repairs"] == 1


def test_apply_mfa_review_labels_unlabeled_goes_to_review(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps({"id": "x", "text": "नमस्ते"}, ensure_ascii=False) + "\n", encoding="utf-8")
    review = tmp_path / "review.tsv"
    review.write_text("id\tlabel\tnotes\n", encoding="utf-8")
    out = tmp_path / "out"

    assert main(["--manifest", str(manifest), "--review-tsv", str(review), "--out-dir", str(out)]) == 0

    needs_review = read_jsonl(out / "needs_review.jsonl")
    assert needs_review[0]["review_label"] == "unlabeled"
    assert needs_review[0]["use_for_asr_training"] is False


def test_apply_mfa_review_labels_backfills_duration_from_analysis(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps({"id": "x", "text": "नमस्ते", "duration_sec": 0}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    review = tmp_path / "review.tsv"
    review.write_text("id\tlabel\tnotes\nx\tbackground_audio\tbed audio\n", encoding="utf-8")
    analysis = tmp_path / "analysis.csv"
    analysis.write_text(
        "file,begin,end,speaker,overall_log_likelihood,speech_log_likelihood,phone_duration_deviation,snr\n"
        "x,1.5,4.25,unknown,-10,-8,1,12\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"

    assert main([
        "--manifest",
        str(manifest),
        "--review-tsv",
        str(review),
        "--analysis-csv",
        str(analysis),
        "--out-dir",
        str(out),
    ]) == 0

    noisy = read_jsonl(out / "asr_noisy_background.jsonl")
    assert noisy[0]["duration_sec"] == 2.75
