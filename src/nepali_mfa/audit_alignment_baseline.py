#!/usr/bin/env python3
"""Summarize an MFA held-out baseline and create review/seed candidates."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return [
            {str(k): (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(f)
        ]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def write_tsv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, delimiter="\t", fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def row_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("utt_id") or row.get("file") or "").strip()


def row_source(row: dict[str, Any]) -> str:
    return str(row.get("slice_source") or row.get("source") or "unknown").strip() or "unknown"


def row_text(row: dict[str, Any]) -> str:
    for field in TEXT_FIELDS:
        value = str(row.get(field) or "").strip()
        if value:
            return value
    return ""


def parse_oov_words(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [item.strip() for item in text.replace(",", " ").split() if item.strip()]


def as_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def analysis_duration(analysis: dict[str, str]) -> float | None:
    begin = as_float(analysis.get("begin"))
    end = as_float(analysis.get("end"))
    if begin is None or end is None:
        return None
    return max(0.0, end - begin)


def best_duration(row: dict[str, Any], failure: dict[str, str] | None, analysis: dict[str, str]) -> float | None:
    for value in [
        row.get("duration_sec"),
        row.get("duration"),
        failure.get("duration_sec") if failure else None,
        analysis_duration(analysis),
    ]:
        parsed = as_float(value)
        if parsed is not None and parsed > 0:
            return parsed
    return None


def load_analysis(path: Path) -> dict[str, dict[str, str]]:
    rows = read_csv(path)
    return {row["file"]: row for row in rows if row.get("file")}


def enrich_manifest_rows(
    manifest_rows: list[dict[str, Any]],
    *,
    failure_by_id: dict[str, dict[str, str]],
    analysis_by_id: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pass_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    for row in manifest_rows:
        rid = row_id(row)
        failure = failure_by_id.get(rid)
        analysis = analysis_by_id.get(rid, {})
        out = dict(row)
        out["id"] = rid
        out["baseline_source"] = row_source(row)
        out["baseline_text"] = row_text(row)
        out["baseline_has_textgrid"] = failure.get("has_textgrid", "True") if failure else "True"
        out["baseline_issue_bucket"] = failure.get("issue_bucket", "") if failure else ""
        duration = best_duration(out, failure, analysis)
        if duration is not None:
            out["duration_sec"] = duration
        for key in [
            "overall_log_likelihood",
            "speech_log_likelihood",
            "phone_duration_deviation",
            "snr",
        ]:
            if key in analysis and analysis[key] != "":
                out[f"mfa_{key}"] = analysis[key]
        if failure:
            out["baseline_review_reason"] = "machine_flagged"
            review_rows.append(out)
        else:
            out["baseline_review_reason"] = "machine_pass"
            pass_rows.append(out)
    return pass_rows, review_rows


def review_template_rows(failure_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in failure_rows:
        out.append(
            {
                "id": row.get("id", ""),
                "label": "",
                "notes": "",
                "issue_bucket": row.get("issue_bucket", ""),
                "has_textgrid": row.get("has_textgrid", ""),
                "slice_source": row.get("slice_source", ""),
                "source": row.get("source", ""),
                "duration_sec": row.get("duration_sec", ""),
                "oov_count": row.get("oov_count", ""),
                "oov_words": row.get("oov_words", ""),
                "transcript": row.get("transcript", ""),
            }
        )
    return out


def oov_report_rows(manifest_rows: list[dict[str, Any]], failure_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    failure_ids = {row.get("id", "") for row in failure_rows}
    by_word: dict[str, Counter[str]] = {}
    totals = Counter()
    for row in manifest_rows:
        rid = row_id(row)
        bucket = "machine_flagged" if rid in failure_ids else "machine_pass"
        source = row_source(row)
        words = parse_oov_words(row.get("seed_lexicon_oov_words") or row.get("oov_words"))
        for word in words:
            by_word.setdefault(word, Counter())
            by_word[word]["total"] += 1
            by_word[word][bucket] += 1
            by_word[word][f"source:{source}"] += 1
            totals[word] += 1
    rows: list[dict[str, Any]] = []
    for word, count in totals.most_common():
        counts = by_word[word]
        top_sources = [
            (key.removeprefix("source:"), value)
            for key, value in counts.items()
            if key.startswith("source:")
        ]
        top_sources.sort(key=lambda item: item[1], reverse=True)
        rows.append(
            {
                "word": word,
                "total": counts["total"],
                "machine_pass": counts["machine_pass"],
                "machine_flagged": counts["machine_flagged"],
                "top_sources": " ".join(f"{name}:{value}" for name, value in top_sources[:5]),
            }
        )
    return rows


def build_summary(
    manifest_rows: list[dict[str, Any]],
    failure_rows: list[dict[str, str]],
    pass_rows: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    by_source = Counter(row_source(row) for row in manifest_rows)
    failure_by_source = Counter(row.get("slice_source") or row.get("source") or "unknown" for row in failure_rows)
    failure_by_bucket = Counter(row.get("issue_bucket") or "unknown" for row in failure_rows)
    pass_by_source = Counter(row.get("baseline_source") or "unknown" for row in pass_rows)
    review_by_source = Counter(row.get("baseline_source") or "unknown" for row in review_rows)
    pass_sec = sum(as_float(row.get("duration_sec")) or 0.0 for row in pass_rows)
    review_sec = sum(as_float(row.get("duration_sec")) or 0.0 for row in review_rows)
    total_sec = pass_sec + review_sec
    return {
        "manifest_rows": len(manifest_rows),
        "manifest_hours": round(total_sec / 3600.0, 6),
        "machine_pass_rows": len(pass_rows),
        "machine_pass_hours": round(pass_sec / 3600.0, 6),
        "machine_review_rows": len(review_rows),
        "machine_review_hours": round(review_sec / 3600.0, 6),
        "failure_audit_rows": len(failure_rows),
        "by_source": dict(sorted(by_source.items())),
        "machine_pass_by_source": dict(sorted(pass_by_source.items())),
        "machine_review_by_source": dict(sorted(review_by_source.items())),
        "failure_by_source": dict(sorted(failure_by_source.items())),
        "failure_by_bucket": dict(sorted(failure_by_bucket.items())),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--failure-audit-csv", type=Path, required=True)
    parser.add_argument("--analysis-csv", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest_rows = list(iter_jsonl(args.manifest))
    failure_rows = read_csv(args.failure_audit_csv)
    failure_by_id = {row["id"]: row for row in failure_rows if row.get("id")}
    analysis_by_id = load_analysis(args.analysis_csv)
    pass_rows, review_rows = enrich_manifest_rows(
        manifest_rows,
        failure_by_id=failure_by_id,
        analysis_by_id=analysis_by_id,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dir / "machine_pass_candidates.jsonl", pass_rows)
    write_jsonl(args.out_dir / "machine_review_candidates.jsonl", review_rows)
    write_tsv(
        args.out_dir / "manual_review_template.tsv",
        review_template_rows(failure_rows),
        [
            "id",
            "label",
            "notes",
            "issue_bucket",
            "has_textgrid",
            "slice_source",
            "source",
            "duration_sec",
            "oov_count",
            "oov_words",
            "transcript",
        ],
    )
    write_tsv(
        args.out_dir / "oov_report.tsv",
        oov_report_rows(manifest_rows, failure_rows),
        ["word", "total", "machine_pass", "machine_flagged", "top_sources"],
    )
    summary = build_summary(manifest_rows, failure_rows, pass_rows, review_rows)
    (args.out_dir / "baseline_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
