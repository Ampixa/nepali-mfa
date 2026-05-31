from __future__ import annotations

import json
from pathlib import Path

from nepali_mfa.build_source_review_dashboard import main


def test_build_source_review_dashboard_filters_source_and_links_audio(tmp_path: Path) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"not-a-real-wav")
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {
                    "id": "keep-me",
                    "source": "podcast",
                    "slice_source": "podcast_source_reviewed_le30",
                    "audio_mfa": str(audio),
                    "transcript": "नमस्ते",
                    "duration_sec": 1.25,
                    "oov_words": ["नमस्ते"],
                },
                {
                    "id": "skip-me",
                    "source": "youtube",
                    "audio_mfa": str(audio),
                    "transcript": "छोड",
                    "duration_sec": 2.0,
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "dashboard"

    assert main([
        "--manifest",
        str(manifest),
        "--out-dir",
        str(out),
        "--source",
        "podcast",
        "--dataset",
        "podcast_test",
    ]) == 0

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["rows_matching_source"] == 1
    assert summary["rows_review"] == 1
    data = (out / "data.js").read_text(encoding="utf-8")
    assert "keep-me" in data
    assert "skip-me" not in data
    assert (out / "audio" / "keep-me.wav").is_symlink()
