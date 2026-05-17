#!/usr/bin/env python3
"""Build profile-tagged training rows for learned reverse G2P.

This prepares the serious training corpus: words are phonemized through a named
forward G2P profile, then stored as canonical ``phones -> akshara/text`` rows.
Raw lexicon phone columns are kept as provenance, but they are not the training
target for the learned model.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nepali_frontend.g2p import phonemizer as base_phonemizer

from nepali_mfa.akshara_codec import text_to_units
from nepali_mfa.paths import require_lexicon_paths


DEFAULT_PROFILES = ("spoken_nepali_linguistic",)
EXPERIMENTAL_PROFILES = ("real_nepali_tts",)
ALL_PROFILES = DEFAULT_PROFILES + EXPERIMENTAL_PROFILES


@dataclass(frozen=True)
class SourceWord:
    text: str
    normalized: str
    raw_phones: str = ""
    source: str = ""
    status: str = ""
    source_path: str = ""
    source_row: int = 0
    frequency: int | None = None


@dataclass
class ReverseG2PCorpusRow:
    text: str
    normalized: str
    profile: str
    canonical_phones: list[str]
    akshara_units: list[str]
    raw_phones: str = ""
    base_phones: list[str] = field(default_factory=list)
    source: str = ""
    status: str = ""
    forward_source: str = ""
    confidence: str = ""
    trace_rules: list[str] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    source_path: str = ""
    source_row: int = 0
    frequency: int | None = None

    def to_json_obj(self) -> dict[str, object]:
        obj = asdict(self)
        obj["canonical_phones_text"] = " ".join(self.canonical_phones)
        obj["akshara_units_text"] = " ".join(self.akshara_units)
        return obj


def has_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" or "\ua8e0" <= ch <= "\ua8ff" for ch in text)


def iter_lexicon_words(paths: Iterable[Path]) -> Iterable[SourceWord]:
    for path in paths:
        with path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row_no, row in enumerate(reader, start=2):
                text = str(row.get("text") or "").strip()
                if not text or not has_devanagari(text):
                    continue
                yield SourceWord(
                    text=text,
                    normalized=str(row.get("normalized") or text).strip() or text,
                    raw_phones=str(row.get("phones") or "").strip(),
                    source=str(row.get("source") or "").strip(),
                    status=str(row.get("status") or "").strip(),
                    source_path=str(path),
                    source_row=row_no,
                )


def iter_frequency_words(path: Path, *, limit: int = 0) -> Iterable[SourceWord]:
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        count = 0
        for row_no, row in enumerate(reader, start=2):
            text = str(row.get("word") or row.get("text") or row.get("token") or "").strip()
            if not text or not has_devanagari(text):
                continue
            try:
                frequency = int(row.get("count") or row.get("frequency") or 0)
            except ValueError:
                frequency = None
            yield SourceWord(
                text=text,
                normalized=text,
                source="word_frequency",
                status="generated_candidate",
                source_path=str(path),
                source_row=row_no,
                frequency=frequency,
            )
            count += 1
            if limit and count >= limit:
                break


def _trace_rules(decisions: Iterable[dict]) -> list[str]:
    rules: list[str] = []
    for decision in decisions:
        rule = str(decision.get("rule") or decision.get("type") or "").strip()
        if rule and rule not in rules:
            rules.append(rule)
    return rules


def phonemize_for_profile(text: str, profile: str):
    if profile == "spoken_nepali_linguistic":
        result = base_phonemizer.phonemize_word(text, style="spoken_nepali")
        return {
            "canonical_phones": list(result.phones),
            "base_phones": list(result.phones),
            "forward_source": result.source,
            "confidence": result.confidence,
            "decisions": [dict(d) for d in result.decisions],
        }
    if profile == "real_nepali_tts":
        from real_nepali import g2p as real_g2p

        result = real_g2p.phonemize_word(text)
        return {
            "canonical_phones": list(result.phones),
            "base_phones": list(result.base_phones),
            "forward_source": result.source,
            "confidence": result.confidence,
            "decisions": [dict(d) for d in result.decisions],
        }
    raise ValueError(f"unknown profile: {profile}")


def build_rows(
    words: Iterable[SourceWord],
    *,
    profiles: Iterable[str],
    dedupe: bool = True,
) -> list[ReverseG2PCorpusRow]:
    rows: list[ReverseG2PCorpusRow] = []
    seen: set[tuple[str, str, str]] = set()
    for word in words:
        akshara_units = text_to_units(word.text, punctuation="drop", normalize=False)
        if not akshara_units:
            continue
        for profile in profiles:
            result = phonemize_for_profile(word.text, profile)
            phones = result["canonical_phones"]
            if not phones:
                continue
            key = (profile, " ".join(phones), word.text)
            if dedupe and key in seen:
                continue
            seen.add(key)
            decisions = result["decisions"]
            rows.append(
                ReverseG2PCorpusRow(
                    text=word.text,
                    normalized=word.normalized,
                    profile=profile,
                    canonical_phones=phones,
                    akshara_units=akshara_units,
                    raw_phones=word.raw_phones,
                    base_phones=result["base_phones"],
                    source=word.source,
                    status=word.status,
                    forward_source=str(result["forward_source"]),
                    confidence=str(result["confidence"]),
                    trace_rules=_trace_rules(decisions),
                    decisions=decisions,
                    source_path=word.source_path,
                    source_row=word.source_row,
                    frequency=word.frequency,
                )
            )
    return rows


def write_jsonl(path: Path, rows: Iterable[ReverseG2PCorpusRow]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row.to_json_obj(), ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def write_tsv(path: Path, rows: Iterable[ReverseG2PCorpusRow]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "text",
        "normalized",
        "profile",
        "canonical_phones",
        "akshara_units",
        "raw_phones",
        "base_phones",
        "source",
        "status",
        "forward_source",
        "confidence",
        "trace_rules",
        "frequency",
        "source_path",
        "source_row",
    ]
    count = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, delimiter="\t", fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "text": row.text,
                    "normalized": row.normalized,
                    "profile": row.profile,
                    "canonical_phones": " ".join(row.canonical_phones),
                    "akshara_units": " ".join(row.akshara_units),
                    "raw_phones": row.raw_phones,
                    "base_phones": " ".join(row.base_phones),
                    "source": row.source,
                    "status": row.status,
                    "forward_source": row.forward_source,
                    "confidence": row.confidence,
                    "trace_rules": ",".join(row.trace_rules),
                    "frequency": "" if row.frequency is None else row.frequency,
                    "source_path": row.source_path,
                    "source_row": row.source_row,
                }
            )
            count += 1
    return count


def summarize(rows: list[ReverseG2PCorpusRow]) -> dict[str, object]:
    by_profile = Counter(row.profile for row in rows)
    by_forward_source = Counter(f"{row.profile}:{row.forward_source}" for row in rows)
    by_source = Counter(row.source or "unknown" for row in rows)
    ambiguous_phone_keys: Counter[str] = Counter()
    spellings_by_phone: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        key = (row.profile, " ".join(row.canonical_phones))
        spellings_by_phone.setdefault(key, set()).add(row.text)
    for (profile, phones), spellings in spellings_by_phone.items():
        if len(spellings) > 1:
            ambiguous_phone_keys[profile] += 1
    return {
        "rows": len(rows),
        "profiles": dict(sorted(by_profile.items())),
        "forward_sources": dict(sorted(by_forward_source.items())),
        "sources": dict(sorted(by_source.items())),
        "ambiguous_phone_sequences": dict(sorted(ambiguous_phone_keys.items())),
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lexicon", type=Path, action="append", default=[])
    ap.add_argument("--include-word-frequency", type=Path)
    ap.add_argument("--word-frequency-limit", type=int, default=0)
    ap.add_argument("--profile", action="append", choices=ALL_PROFILES, default=[])
    ap.add_argument("--out-jsonl", type=Path, required=True)
    ap.add_argument("--out-tsv", type=Path)
    ap.add_argument("--summary-json", type=Path)
    ap.add_argument("--no-dedupe", action="store_true")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    lexicons = require_lexicon_paths(args.lexicon)
    profiles = args.profile or list(DEFAULT_PROFILES)
    words = list(iter_lexicon_words(lexicons))
    if args.include_word_frequency:
        words.extend(
            iter_frequency_words(
                args.include_word_frequency,
                limit=args.word_frequency_limit,
            )
        )
    rows = build_rows(words, profiles=profiles, dedupe=not args.no_dedupe)
    write_jsonl(args.out_jsonl, rows)
    if args.out_tsv:
        write_tsv(args.out_tsv, rows)
    summary = summarize(rows)
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
