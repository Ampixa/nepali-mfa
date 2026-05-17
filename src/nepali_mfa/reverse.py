"""Reverse G2P helpers for Nepali phones.

The project has strong forward G2P and lexicon coverage. This module adds a
reliable reverse lookup from phone sequences to likely orthographic spellings.

Core output is useful for:

- repairing lexicon OOVs discovered by ASR committee pipelines;
- generating candidate words for manual spelling review;
- bootstrap exports for downstream alignment tools.

The reverse index is intentionally lexicon-priority-based (first occurrence
from candidate data wins), then heuristically ranked.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from nepali_frontend import data

from nepali_mfa.paths import require_lexicon_paths

REPO_ROOT = Path(__file__).resolve().parents[2]

REVERSE_SOURCE_PRIORITY = {
    "gold": 0,
    "native_review": 1,
    "candidate": 2,
}


@dataclass
class ReverseCandidate:
    """A spelling candidate for a phone string."""

    spelling: str
    normalized: str
    phones: list[str]
    source: str
    status: str
    rank_score: float

    def as_dict(self) -> dict[str, str | float]:
        return {
            "spelling": self.spelling,
            "normalized": self.normalized,
            "phones": " ".join(self.phones),
            "source": self.source,
            "status": self.status,
            "rank_score": self.rank_score,
        }


def _iter_lexicon_rows(path: Path) -> Iterable[tuple[str, str, str, str, str]]:
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            phones = (r.get("phones") or "").strip()
            text = (r.get("text") or "").strip()
            normalized = (r.get("normalized") or "").strip()
            source = (r.get("source") or "").strip()
            status = (r.get("status") or "").strip()
            if not text or not phones:
                continue
            yield text, normalized, phones, source, status


def _normalize_phone_key(phones: str) -> tuple[str, ...]:
    return tuple(p for p in phones.split() if p)


def _is_valid_phone_sequence(phones: tuple[str, ...], *, strict: bool = True) -> bool:
    if not phones:
        return False
    if not strict:
        return True
    inv = data.phones()
    return all(p in inv for p in phones)


def _build_reverse_index(
    lexicon_paths: Iterable[Path],
    *,
    strict: bool,
    dedupe_spelling: bool,
) -> dict[tuple[str, ...], list[ReverseCandidate]]:
    seen_by_key: set[tuple[tuple[str, ...], str]] = set()
    index: dict[tuple[str, ...], list[ReverseCandidate]] = {}
    for path in lexicon_paths:
        for text, normalized, phones_text, source, status in _iter_lexicon_rows(path):
            phones = _normalize_phone_key(phones_text)
            if not _is_valid_phone_sequence(phones, strict=strict):
                continue
            if (phones, text) in seen_by_key and dedupe_spelling:
                continue
            seen_by_key.add((phones, text))

            status_key = status.lower() or "candidate"
            priority = REVERSE_SOURCE_PRIORITY.get(status_key, 3)
            # Rank preference:
            # 1) lexicon status priority,
            # 2) shorter spellings first,
            # 3) lexical tie-break.
            rank_score = priority * 100.0 + len(text)
            idx = index.setdefault(phones, [])
            idx.append(
                ReverseCandidate(
                    spelling=text,
                    normalized=normalized,
                    phones=list(phones),
                    source=source,
                    status=status_key,
                    rank_score=rank_score,
                )
            )
    for key, values in index.items():
        values.sort(key=lambda x: (x.rank_score, x.spelling))
    return index


def load_reverse_index(
    *,
    lexicon: Iterable[Path] | None = None,
    strict: bool = True,
    dedupe_spelling: bool = True,
) -> dict[tuple[str, ...], list[ReverseCandidate]]:
    """Load candidate lexicon files and build a reverse phone index."""
    paths = require_lexicon_paths(list(lexicon or []))
    return _build_reverse_index(paths, strict=strict, dedupe_spelling=dedupe_spelling)


def reverse_lookup(
    phones: str | Iterable[str],
    *,
    index: dict[tuple[str, ...], list[ReverseCandidate]] | None = None,
    top_k: int = 10,
) -> list[ReverseCandidate]:
    """Find orthographic candidates for a phone sequence."""
    if index is None:
        index = load_reverse_index()
    if isinstance(phones, str):
        key = _normalize_phone_key(phones)
    else:
        key = tuple(p.strip() for p in phones if str(p).strip())
    if not key:
        return []
    return index.get(key, [])[:top_k]


def export_reverse_index(
    index: dict[tuple[str, ...], list[ReverseCandidate]],
    out_json: Path,
) -> int:
    """Write reverse index as JSON for downstream tooling."""
    payload = {
        "entries": [
            {"phones": " ".join(k), "candidates": [c.as_dict() for c in candidates]}
            for k, candidates in sorted(index.items(), key=lambda kv: len(kv[0]))
        ]
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(payload["entries"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phones", required=True, help="space-separated phone string")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--lexicon", type=Path, action="append", default=[])
    ap.add_argument("--strict", action="store_true", default=True)
    ap.add_argument("--no-strict", dest="strict", action="store_false")
    ap.add_argument("--out-json", type=Path)
    args = ap.parse_args()

    index = load_reverse_index(lexicon=args.lexicon or None, strict=args.strict)
    candidates = reverse_lookup(args.phones, index=index, top_k=args.top_k)
    if args.out_json:
        export_reverse_index(index, args.out_json)
        print(f"wrote reverse index: {args.out_json}")
    if not candidates:
        print("[]")
        return 1
    print("[")
    for i, c in enumerate(candidates):
        comma = "," if i + 1 < len(candidates) else ""
        print(f"  {json.dumps(c.as_dict(), ensure_ascii=False)}{comma}")
    print("]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
