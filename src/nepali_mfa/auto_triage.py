#!/usr/bin/env python3
"""Automatically tier Nepali ASR/MFA candidate rows before human review."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from nepali_mfa.apply_review_labels import iter_jsonl, load_review_tsv, write_jsonl
from nepali_mfa.apply_source_review_labels import normalize_label, source_review_tier
from nepali_mfa.audit_alignment_baseline import as_float


TEXT_FIELDS = ("transcript", "text", "reference_text", "normalized_text")
ID_FIELDS = ("id", "utt_id", "file", "audio_id")
NON_SPEECH_BRACKET_RE = re.compile(r"[\[\(（][^\]\)）]{1,32}[\]\)）]")
CAPTION_ARTIFACT_RE = re.compile(r"(>>|♪|♫|subscribe|like share|caption)", re.IGNORECASE)
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
ARABIC_DIGIT_RE = re.compile(r"\d")
DEVANAGARI_DIGIT_RE = re.compile(r"[०-९]")
YEAR_HINT_RE = re.compile(r"(हजार|सय|उन्नाइस|बीस|एक्काइस|साल|ईस्वी|सन)")


def row_id(row: dict[str, Any]) -> str:
    for field in ID_FIELDS:
        value = str(row.get(field) or "").strip()
        if value:
            return value
    return ""


def row_text(row: dict[str, Any]) -> str:
    for field in TEXT_FIELDS:
        value = str(row.get(field) or "").strip()
        if value:
            return value
    return ""


def row_duration(row: dict[str, Any], analysis: dict[str, str] | None = None) -> float:
    for field in ("duration_sec", "duration", "audio_duration_sec"):
        value = as_float(row.get(field))
        if value is not None and value > 0:
            return value
    if analysis:
        begin = as_float(analysis.get("begin"))
        end = as_float(analysis.get("end"))
        if begin is not None and end is not None and end > begin:
            return end - begin
    return 0.0


def parse_word_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in text.replace(",", " ").split() if item.strip()]


def oov_words(row: dict[str, Any]) -> list[str]:
    merged: list[str] = []
    for field in ("unresolved_oov_words", "seed_lexicon_oov_words", "g2p_fallback_words", "oov_words"):
        merged.extend(parse_word_list(row.get(field)))
    return list(dict.fromkeys(merged))


def token_count(text: str) -> int:
    return len([item for item in text.split() if item.strip()])


def load_indexed_csv(path: Path | None) -> dict[str, dict[str, str]]:
    if not path:
        return {}
    rows = read_delimited(path)
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        rid = ""
        for field in ID_FIELDS:
            rid = str(row.get(field) or "").strip()
            if rid:
                break
        if rid:
            out[rid] = row
    return out


def load_failure_csv(path: Path | None) -> dict[str, dict[str, str]]:
    if not path:
        return {}
    rows = read_delimited(path)
    return {str(row.get("id") or row.get("file") or "").strip(): row for row in rows if row.get("id") or row.get("file")}


def read_delimited(path: Path) -> list[dict[str, str]]:
    sample = path.read_text(encoding="utf-8")[:4096]
    delimiter = "\t" if "\t" in sample.splitlines()[0] else ","
    with path.open(encoding="utf-8", newline="") as f:
        return [
            {str(k): (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(f, delimiter=delimiter)
        ]


def metric(row: dict[str, str], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = as_float(row.get(name))
        if value is not None:
            return value
    return None


def asr_has_signal(asr: dict[str, str] | None) -> bool:
    if not asr:
        return False
    available = as_float(asr.get("asr_models_available"))
    if available is not None and available <= 0:
        return False
    return asr_cer(asr) is not None or asr_wer(asr) is not None


def asr_cer(asr: dict[str, str]) -> float | None:
    return metric(
        asr,
        (
            "cer",
            "source_cer",
            "agreement_cer",
            "committee_cer",
            "whisper_cer",
            "chirp_cer",
            "chirp2_cer",
        ),
    )


def asr_wer(asr: dict[str, str]) -> float | None:
    return metric(asr, ("wer", "source_wer", "agreement_wer", "committee_wer", "whisper_wer"))


def manual_label_decision(label: str) -> tuple[str, bool, bool, str] | None:
    label = normalize_label(label)
    if not label:
        return None
    return source_review_tier(label)


def score_row(
    row: dict[str, Any],
    *,
    review: dict[str, str] | None,
    failure: dict[str, str] | None,
    analysis: dict[str, str] | None,
    asr: dict[str, str] | None,
    args: argparse.Namespace,
) -> dict[str, Any]:
    rid = row_id(row)
    text = row_text(row)
    duration = row_duration(row, analysis)
    words = max(token_count(text), 1)
    oovs = oov_words(row)
    oov_ratio = len(oovs) / words
    reasons: list[str] = []
    risk = 0

    manual = manual_label_decision((review or {}).get("label", ""))
    if manual:
        quality_tier, use_asr, use_clean, decision = manual
        reasons.append(f"human_label:{normalize_label((review or {}).get('label', ''))}")
        confidence = 1.0 if use_clean else 0.85 if use_asr else 0.0
    else:
        quality_tier = "auto_review_uncertain"
        use_asr = False
        use_clean = False
        decision = "review"
        confidence = 0.0

        if not text:
            reasons.append("missing_text")
            risk += 100
        elif not DEVANAGARI_RE.search(text):
            reasons.append("no_devanagari_text")
            risk += 25

        if duration < args.min_duration:
            reasons.append("duration_too_short")
            risk += 80
        elif duration > args.max_duration:
            reasons.append("duration_too_long")
            risk += 45

        if CAPTION_ARTIFACT_RE.search(text):
            reasons.append("caption_artifact")
            risk += 80
        if NON_SPEECH_BRACKET_RE.search(text):
            reasons.append("bracketed_non_speech")
            risk += 90
        if (ARABIC_DIGIT_RE.search(text) or DEVANAGARI_DIGIT_RE.search(text)) and YEAR_HINT_RE.search(text):
            reasons.append("number_or_year_needs_normalization_check")
            risk += 25

        if len(oovs) > args.max_oov_words:
            reasons.append("many_oov_words")
            risk += 20
        if oov_ratio > args.max_oov_ratio:
            reasons.append("high_oov_ratio")
            risk += 25

        if failure:
            bucket = str(failure.get("issue_bucket") or "mfa_failure").strip() or "mfa_failure"
            reasons.append(f"mfa_failure:{bucket}")
            risk += 45

        if analysis:
            snr = metric(analysis, ("snr",))
            if snr is not None and snr < args.min_snr:
                reasons.append("low_snr")
                risk += 35
            phone_dev = metric(analysis, ("phone_duration_deviation",))
            if phone_dev is not None and phone_dev > args.max_phone_duration_deviation:
                reasons.append("high_phone_duration_deviation")
                risk += 35
            overall_ll = metric(analysis, ("overall_log_likelihood",))
            if overall_ll is not None and overall_ll < args.min_overall_log_likelihood:
                reasons.append("low_overall_log_likelihood")
                risk += 25
            speech_ll = metric(analysis, ("speech_log_likelihood",))
            if speech_ll is not None and speech_ll < args.min_speech_log_likelihood:
                reasons.append("low_speech_log_likelihood")
                risk += 25

        if asr_has_signal(asr):
            cer = asr_cer(asr)
            wer = asr_wer(asr)
            if cer is not None and cer > args.max_cer:
                reasons.append("high_asr_cer")
                risk += 70
            if wer is not None and wer > args.max_wer:
                reasons.append("high_asr_wer")
                risk += 70

        if risk >= args.reject_risk:
            quality_tier = "auto_reject"
            decision = "reject"
        elif risk >= args.review_risk:
            quality_tier = "auto_needs_review"
            decision = "review"
        elif failure:
            quality_tier = "auto_bronze_mfa_risky"
            decision = "accept_asr_bronze"
            use_asr = True
            confidence = 0.55
        elif analysis and any(reason in reasons for reason in ("low_snr", "low_speech_log_likelihood")):
            quality_tier = "auto_bronze_noisy"
            decision = "accept_asr_bronze"
            use_asr = True
            confidence = 0.6
        elif asr_has_signal(asr):
            quality_tier = "auto_silver_asr_mfa"
            decision = "accept_silver"
            use_asr = True
            use_clean = True
            confidence = 0.9
        elif args.allow_rules_only_silver:
            quality_tier = "auto_silver_rules"
            decision = "accept_silver"
            use_asr = True
            use_clean = True
            confidence = 0.75
        else:
            quality_tier = "auto_needs_review_no_external_signal"
            decision = "review"
            confidence = 0.0

        if not reasons:
            reasons.append("all_available_checks_passed")

    out = dict(row)
    out["id"] = rid
    out["duration_sec"] = duration or row.get("duration_sec") or row.get("duration")
    out["auto_triage"] = {
        "decision": decision,
        "quality_tier": quality_tier,
        "confidence": round(confidence, 4),
        "risk_score": risk,
        "reasons": reasons,
        "duration_sec": duration,
        "oov_count": len(oovs),
        "oov_ratio": round(oov_ratio, 4),
        "human_override": bool(manual),
    }
    out["quality_tier"] = quality_tier
    out["review_decision"] = decision
    out["use_for_asr_training"] = use_asr
    out["use_for_clean_mfa_seed_candidate"] = use_clean
    return out


def split_name(row: dict[str, Any]) -> str:
    decision = str(row.get("review_decision") or "")
    tier = str(row.get("quality_tier") or "")
    if row.get("use_for_clean_mfa_seed_candidate") and decision.startswith("accept"):
        return "auto_silver_clean"
    if row.get("use_for_asr_training") and ("bronze" in tier or "noisy" in tier or "background" in tier):
        return "auto_bronze_asr"
    if decision == "reject":
        return "auto_rejected"
    return "needs_review"


def write_summary(out_dir: Path, rows: list[dict[str, Any]], splits: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    def dur(items: Iterable[dict[str, Any]]) -> float:
        return round(sum(as_float(row.get("duration_sec")) or 0.0 for row in items) / 3600.0, 6)

    summary = {
        "rows": len(rows),
        "hours": dur(rows),
        "by_split": {name: len(value) for name, value in splits.items()},
        "hours_by_split": {name: dur(value) for name, value in splits.items()},
        "by_quality_tier": dict(Counter(str(row.get("quality_tier") or "") for row in rows)),
        "by_decision": dict(Counter(str(row.get("review_decision") or "") for row in rows)),
        "top_reasons": dict(
            Counter(reason for row in rows for reason in row.get("auto_triage", {}).get("reasons", [])).most_common(40)
        ),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--review-tsv", type=Path)
    parser.add_argument("--failure-audit-csv", type=Path)
    parser.add_argument("--analysis-csv", type=Path)
    parser.add_argument("--asr-scores-csv", type=Path)
    parser.add_argument("--min-duration", type=float, default=0.4)
    parser.add_argument("--max-duration", type=float, default=30.0)
    parser.add_argument("--max-oov-words", type=int, default=8)
    parser.add_argument("--max-oov-ratio", type=float, default=0.35)
    parser.add_argument("--max-cer", type=float, default=0.15)
    parser.add_argument("--max-wer", type=float, default=0.30)
    parser.add_argument("--min-snr", type=float, default=10.0)
    parser.add_argument("--max-phone-duration-deviation", type=float, default=3.0)
    parser.add_argument("--min-overall-log-likelihood", type=float, default=-250.0)
    parser.add_argument("--min-speech-log-likelihood", type=float, default=-250.0)
    parser.add_argument("--review-risk", type=int, default=40)
    parser.add_argument("--reject-risk", type=int, default=90)
    parser.add_argument(
        "--allow-rules-only-silver",
        action="store_true",
        help="Allow clean text/duration rules alone to promote rows to silver when no ASR/MFA/review signal exists.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest_rows = list(iter_jsonl(args.manifest))
    reviews = load_review_tsv(args.review_tsv) if args.review_tsv else {}
    failures = load_failure_csv(args.failure_audit_csv)
    analysis = load_indexed_csv(args.analysis_csv)
    asr_scores = load_indexed_csv(args.asr_scores_csv)

    rows: list[dict[str, Any]] = []
    splits: dict[str, list[dict[str, Any]]] = {
        "auto_silver_clean": [],
        "auto_bronze_asr": [],
        "auto_rejected": [],
        "needs_review": [],
    }
    for row in manifest_rows:
        rid = row_id(row)
        scored = score_row(
            row,
            review=reviews.get(rid),
            failure=failures.get(rid),
            analysis=analysis.get(rid),
            asr=asr_scores.get(rid),
            args=args,
        )
        rows.append(scored)
        splits[split_name(scored)].append(scored)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dir / "auto_triaged_all.jsonl", rows)
    for name, split_rows in splits.items():
        write_jsonl(args.out_dir / f"{name}.jsonl", split_rows)
    summary = write_summary(args.out_dir, rows, splits)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
