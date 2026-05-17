#!/usr/bin/env python3
"""Merge MFA dashboard review labels into tiered training manifests."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from nepali_mfa.text_repair import rewrite_1900s_cardinal_phrase_to_year_style


TEXT_FIELDS = ("transcript", "text", "reference_text", "normalized_text")


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            if isinstance(row, dict):
                yield row


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def load_review_tsv(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if "id" not in (reader.fieldnames or []):
            raise ValueError(f"{path} must contain an id column")
        out: dict[str, dict[str, str]] = {}
        for row in reader:
            row_id = (row.get("id") or "").strip()
            if not row_id:
                continue
            out[row_id] = {k: (v or "").strip() for k, v in row.items()}
        return out


def load_analysis_csv(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        out: dict[str, dict[str, str]] = {}
        for row in reader:
            row_id = (row.get("file") or row.get("id") or "").strip()
            if row_id:
                out[row_id] = {k: (v or "").strip() for k, v in row.items()}
        return out


def text_field_for(row: dict[str, Any], preferred: str) -> str | None:
    if preferred != "auto":
        return preferred if preferred in row else None
    for field in TEXT_FIELDS:
        if str(row.get(field) or "").strip():
            return field
    return None


def reviewed_tier(label: str, *, repaired: bool) -> tuple[str, bool, bool, str]:
    """Return quality tier, use_asr, use_mfa_seed, decision."""
    if label == "keep":
        return "clean", True, True, "accept"
    if label == "minor":
        return "clean_minor", True, False, "accept_asr_only"
    if label == "background_audio":
        return "noisy_background_verified", True, False, "accept_asr_noisy"
    if label == "number_mismatch":
        if repaired:
            return "clean_repaired_number", True, True, "accept_after_repair"
        return "needs_number_repair", False, False, "review"
    if label == "alignment_bad":
        return "mfa_failed_text_audio_ok", True, False, "accept_asr_mfa_reject"
    if label == "text_bad":
        return "reject_text_bad", False, False, "reject"
    if label == "audio_bad":
        return "reject_audio_bad", False, False, "reject"
    if label == "unsure":
        return "review_unsure", False, False, "review"
    return "review_unlabeled", False, False, "review"


def repair_number_text(text: str) -> tuple[str, bool]:
    repaired = rewrite_1900s_cardinal_phrase_to_year_style(text)
    return repaired, repaired != text


def enrich_row(
    row: dict[str, Any],
    *,
    review: dict[str, str] | None,
    analysis: dict[str, str] | None,
    text_field: str,
    repair_year_style: bool,
) -> dict[str, Any]:
    out = dict(row)
    row_id = str(out.get("id") or "")
    label = (review or {}).get("label", "").strip()
    notes = (review or {}).get("notes", "").strip()
    issue_bucket = (review or {}).get("issue_bucket", "").strip()
    slice_source = (review or {}).get("slice_source", "").strip()
    has_textgrid = (review or {}).get("has_textgrid", "").strip()

    chosen_text_field = text_field_for(out, text_field)
    original_text = str(out.get(chosen_text_field) or "") if chosen_text_field else ""
    repaired = False
    if label == "number_mismatch" and repair_year_style and chosen_text_field:
        next_text, repaired = repair_number_text(original_text)
        if repaired:
            out[f"{chosen_text_field}_before_review_repair"] = original_text
            out[chosen_text_field] = next_text
            if chosen_text_field != "transcript" and "transcript" in out and out["transcript"] == original_text:
                out["transcript"] = next_text
            if chosen_text_field != "text" and "text" in out and out["text"] == original_text:
                out["text"] = next_text
            if (
                chosen_text_field != "reference_text"
                and "reference_text" in out
                and out["reference_text"] == original_text
            ):
                out["reference_text"] = next_text

    quality_tier, use_asr, use_mfa_seed, decision = reviewed_tier(label, repaired=repaired)
    out["review_label"] = label or "unlabeled"
    out["quality_tier"] = quality_tier
    out["use_for_asr_training"] = use_asr
    out["use_for_clean_mfa_seed"] = use_mfa_seed
    out["review_decision"] = decision
    out["mfa_review"] = {
        "id": row_id,
        "label": label or "unlabeled",
        "notes": notes,
        "issue_bucket": issue_bucket,
        "slice_source": slice_source,
        "has_textgrid": has_textgrid,
        "number_repaired": repaired,
    }
    if analysis:
        out["mfa_metrics"] = {
            key: value
            for key, value in analysis.items()
            if key
            in {
                "overall_log_likelihood",
                "speech_log_likelihood",
                "phone_duration_deviation",
                "snr",
                "begin",
                "end",
            }
        }
    return out


def split_name(row: dict[str, Any]) -> str:
    if row["use_for_clean_mfa_seed"]:
        return "mfa_clean_seed"
    if row["use_for_asr_training"] and row["quality_tier"] == "noisy_background_verified":
        return "asr_noisy_background"
    if row["use_for_asr_training"]:
        return "asr_reviewed_candidate"
    if row["review_decision"] == "reject":
        return "rejected"
    return "needs_review"


def build_outputs(
    manifest_path: Path,
    reviews: dict[str, dict[str, str]],
    analyses: dict[str, dict[str, str]],
    *,
    text_field: str,
    repair_year_style: bool,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    splits: dict[str, list[dict[str, Any]]] = {
        "mfa_clean_seed": [],
        "asr_noisy_background": [],
        "asr_reviewed_candidate": [],
        "rejected": [],
        "needs_review": [],
    }
    for row in iter_jsonl(manifest_path):
        row_id = str(row.get("id") or "")
        enriched = enrich_row(
            row,
            review=reviews.get(row_id),
            analysis=analyses.get(row_id),
            text_field=text_field,
            repair_year_style=repair_year_style,
        )
        rows.append(enriched)
        splits[split_name(enriched)].append(enriched)

    summary = {
        "input_manifest": str(manifest_path),
        "rows": len(rows),
        "review_rows": len(reviews),
        "matched_review_rows": sum(1 for row in rows if row["review_label"] != "unlabeled"),
        "by_label": dict(Counter(row["review_label"] for row in rows)),
        "by_quality_tier": dict(Counter(row["quality_tier"] for row in rows)),
        "by_split": {name: len(value) for name, value in splits.items()},
        "number_repairs": sum(1 for row in rows if row["mfa_review"]["number_repaired"]),
    }
    return rows, splits, summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review-tsv", type=Path, required=True)
    parser.add_argument("--analysis-csv", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--text-field", default="auto")
    parser.add_argument("--repair-year-style", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    reviews = load_review_tsv(args.review_tsv)
    analyses = load_analysis_csv(args.analysis_csv)
    rows, splits, summary = build_outputs(
        args.manifest,
        reviews,
        analyses,
        text_field=args.text_field,
        repair_year_style=args.repair_year_style,
    )

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
