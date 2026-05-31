# Nepali MFA

Nepali forced-alignment, pronunciation, and review tooling for building cleaner
ASR training data.

This repo is the data-quality layer between raw Nepali audio/transcripts and ASR
training recipes. It prepares MFA-compatible corpora, trains/evaluates MFA
alignment baselines, serves review dashboards, and turns human review labels
into clean/noisy/rejected manifests.

It does not train ASR models. FastConformer, Zipformer, Whisper-style
benchmarking, and downstream ASR recipes consume the manifests produced here.

## Current Status

As of the current run record:

- about `509.5h` of MFA-prepared source data has been exported across SLR54,
  Sushant podcast, YouTube captions, Chirp2 CER<=1, and Chirp2 reviewed data;
- the current best MFA baseline is a mixed-source 5000-row acoustic model;
- held-out mixed validation exported `934 / 1000` TextGrids;
- Sushant podcast rows are being reviewed as candidate-clean MFA seed data;
- background-audio rows are treated as ASR noisy/robustness data, not clean MFA
  seed data;
- browser review progress is not server-visible until `Export TSV` is clicked.

Start here for the full operational record:

- [MFA current run record](docs/mfa-current-run-record-2026-05-31.md)

## What This Repo Owns

- Build MFA-ready corpora:
  `mfa_corpus/<speaker>/<utt>.wav|flac` plus matching `.lab` files.
- Generate and extend Nepali pronunciation dictionaries using the text frontend
  G2P path and reverse-G2P helpers.
- Build balanced validation and held-out slices.
- Train and evaluate MFA acoustic-model baselines.
- Build static browser dashboards for listening and label review.
- Merge review TSVs into tiered manifests for ASR/MFA use.
- Track number/year repairs and background-audio decisions explicitly.

## What This Repo Does Not Store

GitHub stores source code, docs, tests, and lightweight config only.

Do not commit:

- audio;
- copied dashboards with audio;
- TextGrids;
- trained MFA acoustic models;
- ASR checkpoints;
- large manifests or generated review outputs.

Those belong on the working machines, object storage, or Hugging Face
datasets/models.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Optional reverse-G2P model work:

```bash
pip install -e ".[dev,reverse-g2p]"
```

Run tests:

```bash
pytest -q
```

Recent result:

```text
13 passed, 1 skipped
```

## MFA Runtime

The Python package builds corpora and dashboards. Actual MFA training/alignment
uses Montreal Forced Aligner installed separately, usually through conda/mamba
because MFA bundles Kaldi dependencies that way.

Current M4 MFA environment:

```text
/Users/cdjk/asr_mfa_env
```

MFA version used in the current run:

```text
3.3.9
```

## Typical Pipeline

Build an MFA corpus:

```bash
nepali-mfa-build-corpus \
  --manifest clean_candidates.jsonl \
  --out-dir outputs/mfa_export \
  --lexicon /path/to/candidates_lexicon.tsv \
  --oov-policy g2p_fallback \
  --transcode-wav \
  --summary-json outputs/mfa_export/summary.json
```

Validate and align with MFA:

```bash
mfa validate \
  outputs/mfa_export/mfa_corpus \
  outputs/mfa_export/nepali.dict

mfa align \
  outputs/mfa_export/mfa_corpus \
  outputs/mfa_export/nepali.dict \
  acoustic.zip \
  outputs/aligned
```

Build a held-out failure dashboard:

```bash
nepali-mfa-build-failure-dashboard \
  --manifest outputs/mfa_export/mfa_manifest.jsonl \
  --analysis-csv outputs/aligned/alignment_analysis.csv \
  --aligned-dir outputs/aligned \
  --out-dir review_dashboards/heldout
```

Serve a dashboard with audio byte-range support:

```bash
nepali-mfa-serve-static-range \
  --directory review_dashboards/heldout \
  --port 8770 \
  --bind 0.0.0.0
```

Apply exported review labels:

```bash
nepali-mfa-apply-review-labels \
  --manifest outputs/mfa_export/mfa_manifest.jsonl \
  --review-tsv review_dashboards/heldout/exported_review.tsv \
  --analysis-csv outputs/aligned/alignment_analysis.csv \
  --out-dir outputs/reviewed_tiers \
  --repair-year-style
```

## Source Review Workflow

For a source that is likely clean, such as Sushant podcast audio, use the
source-review dashboard instead of the failure-dashboard flow:

```bash
nepali-mfa-build-source-review-dashboard \
  --manifest /path/to/mixed_5000/mfa_manifest.jsonl \
  --out-dir /path/to/sushant_candidate_clean_dashboard \
  --source sushant \
  --dataset sushant_candidate_clean_20260527 \
  --limit 0
```

After the reviewer clicks `Export TSV`, apply labels:

```bash
nepali-mfa-apply-source-review-labels \
  --manifest /path/to/sushant_candidate_clean_dashboard/source_review_manifest.jsonl \
  --review-tsv /path/to/sushant_candidate_clean_20260527_source_review.tsv \
  --out-dir /path/to/sushant_candidate_clean_reviewed
```

Source-review outputs:

- `mfa_clean_seed_candidate.jsonl`
- `asr_noisy_background.jsonl`
- `rejected.jsonl`
- `needs_review.jsonl`
- `reviewed_all.jsonl`
- `summary.json`

Important: review labels live in the browser's localStorage until the reviewer
exports the TSV. The server cannot count reviewed rows before that export.

## Output Tiers

Held-out failure review:

| Output | Meaning |
|---|---|
| `mfa_clean_seed.jsonl` | Clean enough for next MFA acoustic-model seed. |
| `asr_noisy_background.jsonl` | Text/audio usable for ASR robustness, not clean MFA. |
| `asr_reviewed_candidate.jsonl` | Audio/text accepted, but MFA alignment failed or is risky. |
| `rejected.jsonl` | Do not train without repair. |
| `needs_review.jsonl` | Missing or inconclusive label. |

Source review:

| Output | Meaning |
|---|---|
| `mfa_clean_seed_candidate.jsonl` | Source-reviewed clean candidate rows. |
| `asr_noisy_background.jsonl` | Correct but background/noisy rows. |
| `rejected.jsonl` | Bad text/audio rows. |
| `needs_review.jsonl` | Unlabeled or unsure rows. |

## Label Policy

| Label | Meaning | ASR use | Clean MFA seed use |
|---|---|---|---|
| `keep` | speech and transcript match cleanly | yes | yes |
| `minor` | small issue, still useful | yes | source review: candidate; failure review: conservative no |
| `background_audio` | target speech plus music/noise/other voices/ambience | noisy tier | no |
| `number_mismatch` | number/year wording mismatch | repair first | repair first |
| `alignment_bad` | audio/text ok but MFA failed | candidate | no |
| `text_bad` | transcript does not match speech | no | no |
| `audio_bad` | speech not reliable | no | no |
| `unsure` | inconclusive | review | no |

Background audio includes music, river/water/wind/traffic, room ambience, faint
other speakers, TV/radio, and non-transcribed start/end tails.

## Current Active Dashboard

Sushant candidate-clean dashboard:

```text
http://100.109.18.109:8771/
```

Current dashboard path:

```text
/Users/cdjk/asr_mfa_training_20260527/sushant_candidate_clean_dashboard
```

Rows:

- `1000` Sushant chunks
- `3.6438h`
- `0` missing audio

Use this dashboard to decide which Sushant chunks become clean MFA seed
candidates.

## CLI Reference

| CLI | Purpose |
|---|---|
| `nepali-mfa-build-corpus` | Build MFA corpus, `.lab` files, dictionary, manifest. |
| `nepali-mfa-build-validation-slice` | Build balanced validation slices. |
| `nepali-mfa-build-heldout-slice` | Build held-out slices excluding prior rows. |
| `nepali-mfa-build-failure-dashboard` | Build held-out failure/risk dashboard. |
| `nepali-mfa-build-source-review-dashboard` | Build source-level clean-candidate dashboard. |
| `nepali-mfa-audit-alignment-baseline` | Summarize held-out baseline and generate review/pass candidates. |
| `nepali-mfa-apply-review-labels` | Apply held-out failure-dashboard TSV labels. |
| `nepali-mfa-apply-source-review-labels` | Apply source-dashboard TSV labels. |
| `nepali-mfa-build-reverse-g2p` | Build reverse-G2P index. |
| `nepali-mfa-build-reverse-g2p-corpus` | Build learned reverse-G2P training rows. |
| `nepali-mfa-train-reverse-g2p` | Train learned reverse-G2P model. |
| `nepali-mfa-predict-reverse-g2p` | Decode phones with learned reverse-G2P model. |
| `nepali-mfa-serve-static-range` | Serve dashboards with byte-range audio support. |

## Docs

Read in this order:

- [Current MFA run record](docs/mfa-current-run-record-2026-05-31.md)
- [Production-clean runbook](docs/mfa-production-clean-runbook-2026-05-17.md)
- [MFA export status](docs/mfa-export-status-2026-05-16.md)
- [Background-audio probe](docs/mfa-background-audio-probe-2026-05-17.md)
- [Reverse-G2P MFA workflow](docs/reverse-g2p-mfa-workflow-2026-05-15.md)

## Next Work

1. Finish Sushant source review and export TSV.
2. Apply `nepali-mfa-apply-source-review-labels`.
3. Inspect clean/noisy/rejected hours.
4. Build a clean MFA seed from reviewed Sushant plus clean SLR54.
5. Train MFA v2 on clean seed.
6. Re-align held-out mixed 1000 and compare against the current `934 / 1000`
   TextGrid baseline.

