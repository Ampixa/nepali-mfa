#!/usr/bin/env python3
"""Apply source-review dashboard labels to candidate-clean manifests."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from nepali_mfa.apply_review_labels import as_float, iter_jsonl, load_review_tsv, write_jsonl


LABEL_ALIASES = {
    "bg": "background_audio",
    "bg_audio": "background_audio",
    "background": "background_audio",
    "background_music": "background_audio",
    "clean": "keep",
    "ok": "keep",
    "bad_text": "text_bad",
    "bad_audio": "audio_bad",
}


def normalize_label(label: str) -> str:
    value = label.strip().lower()
    return LABEL_ALIASES.get(value, value)


def source_review_tier(label: str) -> tuple[str, bool, bool, str]:
    """Return quality tier, use_asr, use_clean_mfa_seed_candidate, decision."""
    if label == "keep":
        return "clean_source_keep", True, True, "accept_clean_candidate"
    if label == "minor":
        return "clean_source_minor", True, True, "accept_clean_candidate"
    if label == "background_audio":
        return "noisy_background_verified", True, False, "accept_asr_noisy"
    if label == "text_bad":
        return "reject_text_bad", False, False, "reject"
    if label == "audio_bad":
        return "reject_audio_bad", False, False, "reject"
    if label == "unsure":
        return "review_unsure", False, False, "review"
    if not label or label == "unlabeled":
        return "review_unlabeled", False, False, "review"
    return f"review_unknown_label_{label}", False, False, "review"


def source_duration(row: dict[str, Any]) -> float:
    return as_float(row.get("duration_sec")) or as_float(row.get("duration")) or 0.0


def enrich_source_row(row: dict[str, Any], review: dict[str, str] | None) -> dict[str, Any]:
    out = dict(row)
    label = normalize_label((review or {}).get("label", ""))
    notes = (review or {}).get("notes", "").strip()
    quality_tier, use_asr, use_clean, decision = source_review_tier(label)

    out["review_label"] = label or "unlabeled"
    out["quality_tier"] = quality_tier
    out["use_for_asr_training"] = use_asr
    out["use_for_clean_mfa_seed_candidate"] = use_clean
    out["review_decision"] = decision
    out["source_review"] = {
        "id": str(out.get("id") or ""),
        "label": label or "unlabeled",
        "notes": notes,
        "source": (review or {}).get("source", "").strip(),
        "slice_source": (review or {}).get("slice_source", "").strip(),
    }
    return out


def split_name(row: dict[str, Any]) -> str:
    if row["use_for_clean_mfa_seed_candidate"]:
        return "mfa_clean_seed_candidate"
    if row["quality_tier"] == "noisy_background_verified":
        return "asr_noisy_background"
    if row["review_decision"] == "reject":
        return "rejected"
    return "needs_review"


def build_outputs(
    manifest_path: Path,
    reviews: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    splits: dict[str, list[dict[str, Any]]] = {
        "mfa_clean_seed_candidate": [],
        "asr_noisy_background": [],
        "rejected": [],
        "needs_review": [],
    }
    matched_review_ids: set[str] = set()

    for row in iter_jsonl(manifest_path):
        row_id = str(row.get("id") or "")
        review = reviews.get(row_id)
        if review is not None:
            matched_review_ids.add(row_id)
        enriched = enrich_source_row(row, review)
        rows.append(enriched)
        splits[split_name(enriched)].append(enriched)

    summary = {
        "input_manifest": str(manifest_path),
        "rows": len(rows),
        "review_rows": len(reviews),
        "matched_review_rows": len(matched_review_ids),
        "unmatched_review_rows": len(set(reviews) - matched_review_ids),
        "by_label": dict(Counter(row["review_label"] for row in rows)),
        "by_quality_tier": dict(Counter(row["quality_tier"] for row in rows)),
        "by_split": {name: len(value) for name, value in splits.items()},
        "hours_by_split": {
            name: round(sum(source_duration(row) for row in value) / 3600, 6)
            for name, value in splits.items()
        },
    }
    return rows, splits, summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review-tsv", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    reviews = load_review_tsv(args.review_tsv)
    rows, splits, summary = build_outputs(args.manifest, reviews)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dir / "reviewed_all.jsonl", rows)
    for name, split_rows in splits.items():
        write_jsonl(args.out_dir / f"{name}.jsonl", split_rows)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
