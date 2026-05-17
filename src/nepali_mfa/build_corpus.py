#!/usr/bin/env python3
"""Build an MFA-ready corpus bundle from an ASR committee JSONL manifest.

Inputs are intentionally plain and close to your existing ingestion manifests:

- each row has `audio_path`, text and optional `id`, `speaker_id`, `duration_sec`.
- output is MFA-style per-speaker directories with WAV/LAB pairs plus a dictionary.

No external MFA runtime is imported. The script only prepares data and emits
commands for the next step so it can be run in AWS transfer/sleep cycles.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import wave
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from nepali_frontend.g2p import phonemizer as base_phonemizer

from nepali_mfa.paths import require_lexicon_paths


DEVANAGARI_RE = re.compile(r"[ऀ-ॣॲ-ॿ]+")
TOKEN_RE = re.compile(r"[ऀ-ॣॲ-ॿ]+|[A-Za-z']+|\d+")
BRACKET_NOISE_RE = re.compile(r"[\[(（][^\]\)）]{1,80}[\]\)）]")
MARKER_RE = re.compile(r"(?:^|\s)(?:>{2,}|≫+|»+)\s*")
WHITESPACE_RE = re.compile(r"\s+")
REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--audio-root", type=Path, default=None)
    ap.add_argument("--manifest-format", choices=["auto", "jsonl", "tsv"], default="auto")
    ap.add_argument("--audio-field", default="audio_path")
    ap.add_argument("--text-field", default="text")
    ap.add_argument("--id-field", default="id")
    ap.add_argument("--speaker-field", default="speaker_id")
    ap.add_argument("--duration-field", default="duration_sec")
    ap.add_argument("--lexicon", type=Path, action="append", default=[],
                    help="candidate pronunciation lexicon TSV; repeatable")
    ap.add_argument("--oov-policy", choices=["skip_row", "skip_word", "g2p_fallback"], default="skip_row")
    ap.add_argument("--allow-english", action="store_true", help="keep ASCII words in transcripts")
    ap.add_argument("--max-oov-per-row", type=int, default=0)
    ap.add_argument("--copy-audio", action="store_true", help="copy audio instead of symlink")
    ap.add_argument("--transcode-wav", action="store_true", help="ffmpeg to 16k mono WAV")
    ap.add_argument("--summary-json", type=Path, default=None)
    ap.add_argument("--print-mfa-cmd", action="store_true")
    ap.add_argument("--dict-name", default="nepali.dict")
    return ap.parse_args()


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def iter_tsv(path: Path) -> Iterable[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            yield r


def clean_text(text: str) -> str:
    text = BRACKET_NOISE_RE.sub(" ", text)
    text = MARKER_RE.sub(" ", text)
    text = text.replace("\u200b", " ")
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def tokenize_text(text: str, *, allow_english: bool) -> tuple[list[str], dict[str, int]]:
    cleaned = clean_text(text)
    tokens = TOKEN_RE.findall(cleaned)
    out: list[str] = []
    stats: Counter[str] = Counter()
    for t in tokens:
        if DEVANAGARI_RE.search(t):
            out.append(t)
            continue
        if allow_english and t.isascii():
            out.append(t.lower())
            stats["ascii"] += 1
            continue
        stats["filtered"] += 1
    return out, dict(stats)


def sanitize_id(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]", "_", value).strip("._-")
    return value or "row"


def load_lexicon(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    lex: dict[str, str] = {}
    norm: dict[str, str] = {}
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            word = str(row.get("text") or "").strip()
            phones = str(row.get("phones") or "").strip()
            if not word or not phones:
                continue
            if word not in lex:
                lex[word] = phones
            if word not in norm:
                norm[word] = str(row.get("normalized") or word).strip() or word
    return lex, norm


def load_lexicons(paths: Iterable[Path]) -> tuple[dict[str, str], dict[str, str]]:
    merged_lex: dict[str, str] = {}
    merged_norm: dict[str, str] = {}
    for path in paths:
        lex, norm = load_lexicon(path)
        for word, phones in lex.items():
            merged_lex.setdefault(word, phones)
        for word, normalized in norm.items():
            merged_norm.setdefault(word, normalized)
    return merged_lex, merged_norm


def transcode_audio(src: Path, dst: Path) -> bool:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        str(dst),
    ]
    r = subprocess.run(cmd)
    return r.returncode == 0


def ensure_audio(
    source: Path,
    target: Path,
    *,
    transcode_wav: bool,
    copy_audio: bool,
) -> tuple[bool, float]:
    target.parent.mkdir(parents=True, exist_ok=True)
    if transcode_wav and source.suffix.lower() != ".wav":
        ok = transcode_audio(source, target)
    else:
        if copy_audio:
            shutil.copy2(source, target)
        else:
            if target.exists():
                target.unlink()
            target.symlink_to(source)
        ok = target.exists()
    duration = 0.0
    if ok and target.suffix.lower() == ".wav" and target.exists():
        with wave.open(str(target), "rb") as wf:
            duration = wf.getnframes() / wf.getframerate()
    return ok, duration


def emit_commands(out_dir: Path, corpus_dir: Path, dict_path: Path) -> list[str]:
    return [
        f"cd {out_dir}",
        "# optional: validate alignment readiness first",
        f"# mfa validate {corpus_dir} {dict_path.name} nepali",
        "# then align",
        f"# mfa align {corpus_dir} {dict_path.name} <acoustic_model> <aligned_out_dir>",
    ]


def row_duration(row: dict[str, Any], field: str) -> float:
    """Read duration from the requested field, then common manifest fallbacks."""
    for key in (field, "duration_sec", "duration"):
        value = row.get(key)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    try:
        start = float(row.get("start") or 0.0)
        end = float(row.get("end") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, end - start)


def write_audit_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest
    rows = iter_jsonl(manifest_path) if args.manifest_format == "jsonl" or (
        args.manifest_format == "auto" and manifest_path.suffix.lower() == ".jsonl"
    ) else iter_tsv(manifest_path)

    corpus_root = args.out_dir / "mfa_corpus"
    dict_root = corpus_root.parent
    dict_path = dict_root / args.dict_name

    lexicon, _ = load_lexicons(require_lexicon_paths(args.lexicon))

    oov = Counter()
    row_stats = Counter()
    total_rows = 0
    kept_rows = 0
    kept_audio_sec = 0.0
    manifest_rows = []

    for i, row in enumerate(rows, 1):
        total_rows += 1
        rid = str(row.get(args.id_field) or row.get("utt_id") or f"row_{i}")
        rid = sanitize_id(rid)
        audio_field = str(row.get(args.audio_field) or "").strip()
        if not audio_field:
            row_stats["missing_audio_path"] += 1
            continue
        audio_src = Path(audio_field)
        if not audio_src.is_absolute() and args.audio_root is not None:
            audio_src = args.audio_root / audio_src
        if not audio_src.exists():
            row_stats["audio_missing"] += 1
            continue
        text = str(row.get(args.text_field) or "").strip()
        if not text:
            row_stats["empty_text"] += 1
            continue

        raw_tokens, tok_stats = tokenize_text(text, allow_english=args.allow_english)
        row_stats.update({f"tok_{k}": v for k, v in tok_stats.items()})
        if not raw_tokens:
            row_stats["empty_tokens"] += 1
            continue

        filtered_tokens: list[str] = []
        seed_lexicon_oov: list[str] = []
        g2p_fallback_words: list[str] = []
        unresolved_oov: list[str] = []
        for tok in raw_tokens:
            if tok in lexicon:
                filtered_tokens.append(tok)
                continue
            seed_lexicon_oov.append(tok)
            if args.oov_policy == "skip_word":
                unresolved_oov.append(tok)
                continue
            if args.oov_policy == "g2p_fallback":
                if not DEVANAGARI_RE.search(tok):
                    unresolved_oov.append(tok)
                    continue
                phone_results = base_phonemizer.phonemize_text(tok)
                if not phone_results:
                    unresolved_oov.append(tok)
                    continue
                phones = " ".join(phone_results[0].phones)
                if phones:
                    if tok not in lexicon:
                        lexicon[tok] = phones
                    g2p_fallback_words.append(tok)
                    filtered_tokens.append(tok)
                else:
                    unresolved_oov.append(tok)
                continue
            unresolved_oov.append(tok)

        if args.oov_policy == "skip_row" and seed_lexicon_oov:
            row_stats["row_skipped_for_oov"] += 1
            row_stats["seed_lexicon_oov_words"] += len(seed_lexicon_oov)
            continue
        if args.max_oov_per_row and len(unresolved_oov) > args.max_oov_per_row:
            row_stats["row_skipped_for_oov"] += 1
            row_stats["row_oov_excess"] += 1
            row_stats["unresolved_oov_words"] += len(unresolved_oov)
            continue

        speaker = sanitize_id(str(row.get(args.speaker_field) or "unknown"))
        speaker_dir = corpus_root / speaker
        ext = audio_src.suffix.lower() or ".wav"
        if args.transcode_wav and ext != ".wav":
            ext = ".wav"
        audio_dst = speaker_dir / f"{rid}{ext}"
        lab_path = speaker_dir / f"{rid}.lab"
        ok, duration = ensure_audio(
            source=audio_src,
            target=audio_dst,
            transcode_wav=args.transcode_wav,
            copy_audio=args.copy_audio,
        )
        if not ok:
            row_stats["audio_copy_fail"] += 1
            continue
        transcript = " ".join(filtered_tokens)
        if not transcript:
            row_stats["empty_after_oov_policy"] += 1
            continue

        row_stats["kept"] += 1
        kept_rows += 1
        fallback_duration = row_duration(row, args.duration_field)
        kept_audio_sec += duration or fallback_duration

        lab_path.write_text(transcript, encoding="utf-8")
        row_stats[f"seed_lexicon_oov_{len(seed_lexicon_oov)}"] += 1
        row_stats[f"unresolved_oov_{len(unresolved_oov)}"] += 1
        for w in seed_lexicon_oov:
            oov[w] += 1

        manifest_rows.append({
            "id": rid,
            "audio_src": str(audio_src),
            "audio_mfa": str(audio_dst),
            "lab": str(lab_path),
            "text_raw": text,
            "transcript": transcript,
            "speaker_id": speaker,
            # Backwards-compatible fields: these are seed lexicon misses, not
            # necessarily final MFA dictionary OOVs when g2p_fallback is used.
            "oov_count": len(seed_lexicon_oov),
            "oov_words": seed_lexicon_oov,
            "seed_lexicon_oov_count": len(seed_lexicon_oov),
            "seed_lexicon_oov_words": seed_lexicon_oov,
            "g2p_fallback_count": len(g2p_fallback_words),
            "g2p_fallback_words": g2p_fallback_words,
            "unresolved_oov_count": len(unresolved_oov),
            "unresolved_oov_words": unresolved_oov,
            "source": str(row.get("source") or "unknown"),
            "duration_sec": float(duration) if duration else fallback_duration,
        })

    # write dictionary (ordered by spelling for repeatability)
    with dict_path.open("w", encoding="utf-8") as f:
        for word in sorted(lexicon):
            phones = lexicon[word].strip()
            if not phones:
                continue
            f.write(f"{word} {phones}\n")

    mfa_manifest = args.out_dir / "mfa_manifest.jsonl"
    with mfa_manifest.open("w", encoding="utf-8") as f:
        for r in manifest_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    oov_path = args.out_dir / "oov_words.tsv"
    with oov_path.open("w", encoding="utf-8") as f:
        f.write("word\tcount\n")
        for w, c in oov.most_common():
            f.write(f"{w}\t{c}\n")

    if args.summary_json:
        summary = {
            "input": str(manifest_path),
            "manifest_rows": total_rows,
            "kept_rows": kept_rows,
            "kept_hours": round(kept_audio_sec / 3600.0, 6),
            "rows_with_seed_lexicon_oov": sum(1 for r in manifest_rows if r["seed_lexicon_oov_count"] > 0),
            "rows_with_g2p_fallback": sum(1 for r in manifest_rows if r["g2p_fallback_count"] > 0),
            "rows_with_unresolved_oov": sum(1 for r in manifest_rows if r["unresolved_oov_count"] > 0),
            "max_oov_per_row": args.max_oov_per_row,
            "oov_policy": args.oov_policy,
            "stats": dict(sorted(row_stats.items())),
            "top_oov": oov.most_common(100),
            "mfa_corpus": str(corpus_root),
            "dictionary": str(dict_path),
            "manifest": str(mfa_manifest),
            "oov_file": str(oov_path),
            "commands": emit_commands(args.out_dir, corpus_root, dict_path),
        }
        write_audit_json(args.summary_json, summary)

    readme = args.out_dir / "README_mfa_prep.md"
    emit_cmds = "\n".join(f"# {line}" for line in emit_commands(args.out_dir, corpus_root, dict_path))
    readme.write_text(
        "# MFA export\n\n"
        "This directory contains a prepared corpus bundle for MFA.\n\n"
        "- `mfa_corpus/<speaker>/<utt_id>.<ext>`: per-speaker audio files (WAV if requested)\n"
        "- `mfa_corpus/<speaker>/<utt_id>.lab`: one sentence per line transcript\n"
        "- `nepali.dict`: lexicon used/bootstrapped from candidates lexicon\n"
        "- `mfa_manifest.jsonl`: traceable manifest for review\n"
        "- `oov_words.tsv`: per-word seed-lexicon miss counts; with `g2p_fallback`, these can still be present in `nepali.dict`\n\n"
        "You can align with your installed MFA version:\n\n"
        "```bash\n"
        f"{emit_cmds}\n"
        "```\n\n"
        "Use your preferred acoustic model/tokenizer for your MFA version.\n"
    )

    if args.print_mfa_cmd:
        for line in emit_commands(args.out_dir, corpus_root, dict_path):
            print(line)

    print(f"kept_rows\t{kept_rows}")
    print(f"kept_hours\t{round(kept_audio_sec / 3600.0, 3)}")
    print(f"oov_types\t{len(oov)}")
    print(f"dict_entries\t{sum(1 for _ in lexicon)}")
    return 0 if kept_rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
