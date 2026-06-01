#!/usr/bin/env python3
"""Compute ASR agreement scores against source transcripts."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from nepali_mfa.apply_review_labels import iter_jsonl, write_jsonl


ID_FIELDS = ("id", "utt_id", "file", "audio_id")
TEXT_FIELDS = ("transcript", "text", "reference_text", "normalized_text")
HYP_TEXT_FIELDS = ("hypothesis", "prediction", "transcript", "text", "normalized_text")
BRACKET_NOISE_RE = re.compile(r"[\[\(（][^\]\)）]{1,80}[\]\)）]")
MARKER_RE = re.compile(r"(?:^|\s)(?:>{2,}|≫+|»+)\s*")
PUNCT_RE = re.compile(r"[।,;:!?\"'“”‘’`~@#$%^&*_+=|\\/<>…·\-]+")
WHITESPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[\u0900-\u097F]+|[A-Za-z']+|\d+")


def clean_for_scoring(text: str, *, keep_bracket_text: bool = False) -> str:
    text = unicodedata.normalize("NFC", text or "")
    if not keep_bracket_text:
        text = BRACKET_NOISE_RE.sub(" ", text)
    text = MARKER_RE.sub(" ", text)
    text = text.replace("\u200b", " ")
    text = PUNCT_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip().lower()


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(clean_for_scoring(text))


def chars(text: str) -> list[str]:
    return [ch for ch in clean_for_scoring(text).replace(" ", "")]


def edit_distance(a: list[str], b: list[str]) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, item_a in enumerate(a, 1):
        current = [i]
        for j, item_b in enumerate(b, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (0 if item_a == item_b else 1),
                )
            )
        previous = current
    return previous[-1]


def rate(reference: list[str], hypothesis: list[str]) -> float:
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return edit_distance(reference, hypothesis) / len(reference)


def row_id(row: dict[str, Any], preferred: str = "id") -> str:
    for field in (preferred, *ID_FIELDS):
        value = str(row.get(field) or "").strip()
        if value:
            return value
    return ""


def row_text(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = str(row.get(field) or "").strip()
        if value:
            return value
    return ""


def iter_table(path: Path) -> Iterable[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        yield from iter_jsonl(path)
        return
    sample = path.read_text(encoding="utf-8")[:4096]
    delimiter = "\t" if sample and "\t" in sample.splitlines()[0] else ","
    with path.open(encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f, delimiter=delimiter)


def load_rows(path: Path, *, id_field: str, text_fields: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in iter_table(path):
        rid = row_id(row, id_field)
        if not rid:
            continue
        text = row_text(row, text_fields)
        out[rid] = {**row, "_score_id": rid, "_score_text": text}
    return out


def safe_name(path: Path) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", path.stem).strip("_").lower()
    return value or "asr"


def score_pair(reference: str, hypothesis: str) -> dict[str, float | int | str]:
    ref_chars = chars(reference)
    hyp_chars = chars(hypothesis)
    ref_words = tokens(reference)
    hyp_words = tokens(hypothesis)
    return {
        "cer": rate(ref_chars, hyp_chars),
        "wer": rate(ref_words, hyp_words),
        "char_edits": edit_distance(ref_chars, hyp_chars),
        "char_total": len(ref_chars),
        "word_edits": edit_distance(ref_words, hyp_words),
        "word_total": len(ref_words),
        "normalized_reference": clean_for_scoring(reference),
        "normalized_hypothesis": clean_for_scoring(hypothesis),
    }


def aggregate_model_scores(scores: list[dict[str, Any]]) -> dict[str, Any]:
    if not scores:
        return {}
    char_edits = sum(int(score["char_edits"]) for score in scores)
    char_total = sum(int(score["char_total"]) for score in scores)
    word_edits = sum(int(score["word_edits"]) for score in scores)
    word_total = sum(int(score["word_total"]) for score in scores)
    return {
        "rows": len(scores),
        "cer": char_edits / max(char_total, 1),
        "wer": word_edits / max(word_total, 1),
        "char_edits": char_edits,
        "char_total": char_total,
        "word_edits": word_edits,
        "word_total": word_total,
    }


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--hypothesis", type=Path, action="append", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--id-field", default="id")
    parser.add_argument("--reference-text-field", default="")
    parser.add_argument("--hypothesis-text-field", default="")
    parser.add_argument("--max-cer", type=float, default=0.15)
    parser.add_argument("--max-wer", type=float, default=0.30)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ref_fields = (args.reference_text_field,) if args.reference_text_field else TEXT_FIELDS
    hyp_fields = (args.hypothesis_text_field,) if args.hypothesis_text_field else HYP_TEXT_FIELDS
    refs = load_rows(args.reference, id_field=args.id_field, text_fields=ref_fields)
    hyp_sets = [
        (safe_name(path), load_rows(path, id_field=args.id_field, text_fields=hyp_fields))
        for path in args.hypothesis
    ]

    rows: list[dict[str, Any]] = []
    per_model_scores: dict[str, list[dict[str, Any]]] = {name: [] for name, _ in hyp_sets}
    for rid, ref in refs.items():
        reference = str(ref.get("_score_text") or "")
        out: dict[str, Any] = {
            "id": rid,
            "reference": reference,
            "normalized_reference": clean_for_scoring(reference),
        }
        available = 0
        pass_count = 0
        best_cer: float | None = None
        best_wer: float | None = None
        worst_cer: float | None = None
        worst_wer: float | None = None
        for name, hyps in hyp_sets:
            hyp = hyps.get(rid)
            if not hyp:
                out[f"{name}_missing"] = True
                continue
            available += 1
            score = score_pair(reference, str(hyp.get("_score_text") or ""))
            per_model_scores[name].append(score)
            cer = float(score["cer"])
            wer = float(score["wer"])
            out[f"{name}_cer"] = round(cer, 6)
            out[f"{name}_wer"] = round(wer, 6)
            out[f"{name}_hypothesis"] = hyp.get("_score_text") or ""
            out[f"{name}_normalized_hypothesis"] = score["normalized_hypothesis"]
            pass_count += int(cer <= args.max_cer and wer <= args.max_wer)
            best_cer = cer if best_cer is None else min(best_cer, cer)
            best_wer = wer if best_wer is None else min(best_wer, wer)
            worst_cer = cer if worst_cer is None else max(worst_cer, cer)
            worst_wer = wer if worst_wer is None else max(worst_wer, wer)
        out["asr_models_available"] = available
        out["asr_models_passing"] = pass_count
        out["cer"] = round(worst_cer if worst_cer is not None else 1.0, 6)
        out["wer"] = round(worst_wer if worst_wer is not None else 1.0, 6)
        out["best_cer"] = round(best_cer if best_cer is not None else 1.0, 6)
        out["best_wer"] = round(best_wer if best_wer is not None else 1.0, 6)
        out["asr_agreement_pass"] = available > 0 and pass_count == available
        rows.append(out)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dir / "asr_agreement_scores.jsonl", rows)
    fieldnames = ["id", "cer", "wer", "best_cer", "best_wer", "asr_models_available", "asr_models_passing", "asr_agreement_pass", "reference", "normalized_reference"]
    for name, _ in hyp_sets:
        fieldnames.extend([f"{name}_cer", f"{name}_wer", f"{name}_hypothesis", f"{name}_normalized_hypothesis"])
    write_csv(args.out_dir / "asr_agreement_scores.csv", rows, fieldnames)
    summary = {
        "reference": str(args.reference),
        "hypotheses": [str(path) for path in args.hypothesis],
        "rows": len(rows),
        "by_models_available": dict(Counter(row["asr_models_available"] for row in rows)),
        "rows_all_models_pass": sum(1 for row in rows if row["asr_agreement_pass"]),
        "models": {
            name: {key: round(value, 6) if isinstance(value, float) else value for key, value in aggregate_model_scores(scores).items()}
            for name, scores in per_model_scores.items()
        },
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
