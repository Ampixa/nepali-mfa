#!/usr/bin/env python3
"""Select a balanced human-review batch from auto-triaged rows."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

from nepali_mfa.apply_review_labels import as_float, iter_jsonl, write_jsonl


def duration_sec(row: dict[str, Any]) -> float:
    return as_float(row.get("duration_sec")) or as_float(row.get("duration")) or 0.0


def source_key(row: dict[str, Any]) -> str:
    return str(row.get("slice_source") or row.get("source") or "unknown").strip() or "unknown"


def reason_key(row: dict[str, Any]) -> str:
    reasons = row.get("auto_triage", {}).get("reasons", [])
    if isinstance(reasons, list) and reasons:
        return str(reasons[0])
    return str(row.get("quality_tier") or row.get("review_decision") or "unknown")


def stratum_key(row: dict[str, Any], mode: str) -> str:
    if mode == "source":
        return source_key(row)
    if mode == "reason":
        return reason_key(row)
    if mode == "source_reason":
        return f"{source_key(row)}::{reason_key(row)}"
    return "all"


def is_review_candidate(row: dict[str, Any]) -> bool:
    decision = str(row.get("review_decision") or "").strip()
    tier = str(row.get("quality_tier") or "").strip()
    if decision == "review":
        return True
    return "review" in tier


def round_robin(rows: list[dict[str, Any]], *, limit_rows: int, max_hours: float, mode: str, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    buckets: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for row in rows:
        buckets[stratum_key(row, mode)].append(row)
    for bucket_rows in buckets.values():
        items = list(bucket_rows)
        rng.shuffle(items)
        bucket_rows.clear()
        bucket_rows.extend(items)

    selected: list[dict[str, Any]] = []
    selected_sec = 0.0
    keys = sorted(buckets)
    while keys:
        progressed = False
        for key in list(keys):
            if limit_rows and len(selected) >= limit_rows:
                return selected
            if not buckets[key]:
                keys.remove(key)
                continue
            row = buckets[key].popleft()
            row_sec = duration_sec(row)
            if max_hours and selected_sec + row_sec > max_hours * 3600 and selected:
                return selected
            selected.append(row)
            selected_sec += row_sec
            progressed = True
        if not progressed:
            break
    return selected


def summarize(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(rows)
    return {
        "rows": len(items),
        "hours": round(sum(duration_sec(row) for row in items) / 3600.0, 6),
        "by_source": dict(Counter(source_key(row) for row in items)),
        "by_reason": dict(Counter(reason_key(row) for row in items).most_common(30)),
        "by_quality_tier": dict(Counter(str(row.get("quality_tier") or "") for row in items)),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--limit-rows", type=int, default=1000)
    parser.add_argument("--max-hours", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--stratify", choices=["source", "reason", "source_reason", "none"], default="source_reason")
    parser.add_argument("--include-all", action="store_true", help="Sample from all rows, not only rows needing review.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = list(iter_jsonl(args.manifest))
    candidates = rows if args.include_all else [row for row in rows if is_review_candidate(row)]
    selected = round_robin(
        candidates,
        limit_rows=args.limit_rows,
        max_hours=args.max_hours,
        mode=args.stratify,
        seed=args.seed,
    )
    selected_ids = {str(row.get("id") or "") for row in selected}
    remainder = [row for row in candidates if str(row.get("id") or "") not in selected_ids]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dir / "review_batch.jsonl", selected)
    write_jsonl(args.out_dir / "review_remainder.jsonl", remainder)
    summary = {
        "input_manifest": str(args.manifest),
        "candidate_rows": len(candidates),
        "candidate_hours": round(sum(duration_sec(row) for row in candidates) / 3600.0, 6),
        "selected": summarize(selected),
        "remainder": summarize(remainder),
        "stratify": args.stratify,
        "seed": args.seed,
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
