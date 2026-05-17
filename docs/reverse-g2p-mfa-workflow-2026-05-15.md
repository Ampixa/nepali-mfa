# Reverse G2P + MFA Workflow (2026-05-15)

## Goal

Enable a controllable Nepali reverse-G2P path and a reproducible MFA export
pipeline for alignment-based filtering, without introducing transcript or phone
poisoning into the training set.

## New Components

- `nepali_frontend/g2p/reverse.py`
  - builds phone->word reverse index from lexicon data
  - supports ranked `reverse_lookup`
  - optional JSON reverse-index export
- `nepali-mfa-build-reverse-g2p`
  - CLI wrapper for quick lookup
- `nepali-mfa-build-corpus`
  - builds speaker-grouped MFA corpus from a manifest
  - emits dictionary + manifest + OOV audit + optional helper commands

## Why this exists

The previous flow had strong forward G2P and weak-to-strong ASR promotion, but
alignment tooling needed explicit lexical reverse coverage and a deterministic
MFA corpus layout. This closes that gap and makes forced alignment reviewable
and resumable.

## 1) Reverse G2P sanity check

```bash
nepali-mfa-build-reverse-g2p \
  --phones "bh aa . j u t" \
  --top-k 8 \
  --export /tmp/reverse_index.json
```

Output columns (TSV style):

- spelling
- normalized
- phones
- source
- status
- rank score

If no rows are returned, the exact phone sequence is not present in current
candidate lexicons.

## 2) Prepare manifest bundle for MFA

### Input contract

Supported manifest formats:

- JSONL: one object per row
- TSV: standard header names

Required/expected fields:

- `audio_path`
- `text` (or choose another via `--text-field`)

Optional fields:

- `speaker_id`, `id`, `duration_sec`, `source`

### Run

```bash
nepali-mfa-build-corpus \
  --manifest /mnt/data/asr/committee_rows.jsonl \
  --audio-root /mnt/data/asr/audio \
  --out-dir /mnt/data/asr/mfa_nepali_batch1 \
  --oov-policy skip_row \
  --summary-json /mnt/data/asr/mfa_nepali_batch1/summary.json \
  --print-mfa-cmd
```

Useful variants:

- `--oov-policy skip_word` (drops only missing words)
- `--oov-policy g2p_fallback` (adds G2P-generated entries when lexicon is missing)
- `--allow-english` (keep ASCII tokens instead of filtering)
- `--copy-audio` (copy files instead of symlink)
- `--transcode-wav` (ffmpeg to 16k mono WAV)

Outputs in `--out-dir`:

- `mfa_corpus/<speaker>/<utt_id>.wav`
- `mfa_corpus/<speaker>/<utt_id>.lab`
- `nepali.dict`
- `mfa_manifest.jsonl`
- `oov_words.tsv`
- `summary.json`
- `README_mfa_prep.md`

## 3) MFA handoff (next step)

Use the generated `README_mfa_prep.md` or run your locally available MFA CLI.

```bash
mfa validate <mfa_corpus> <nepali.dict> nepali
mfa align <mfa_corpus> <nepali.dict> <acoustic_model> <aligned_out>
```

Model names and exact command flags depend on your installed MFA version.

## 4) Audit before promotion

1. review `summary.json` for OOV rate and rows kept
2. inspect `mfa_manifest.jsonl` with audio ids linked to `oov_count`
3. only promote rows with accepted alignment + low speaker overlap + clean transcript

## 5) Timestamped trace

- 2026-05-15: reverse G2P module + MFA export script added.
- Use this document as the handoff note for any future retraining run.
