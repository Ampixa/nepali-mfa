# Nepali MFA

Production tooling for Nepali forced alignment and alignment review.

This project owns the forced-alignment side of the ASR data pipeline:

- build MFA-ready `mfa_corpus/<speaker>/<utt>.wav|flac` and `.lab` bundles;
- generate/extend a Nepali pronunciation dictionary from the text frontend G2P;
- build validation and held-out slices;
- build a static failure-review dashboard from MFA TextGrid output;
- merge human review labels into clean/noisy/rejected manifest tiers;
- train and run learned reverse-G2P repair models for lexicon gaps.

It intentionally does not own ASR model training. ASR recipes consume manifests
and tiers produced here.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Production jobs should pass the lexicon explicitly:

```bash
export NEPALI_MFA_LEXICON=/path/to/candidates_lexicon.tsv
```

or use `--lexicon /path/to/candidates_lexicon.tsv` where supported.

## Typical Flow

```bash
nepali-mfa-build-corpus \
  --manifest clean_candidates.jsonl \
  --out-dir outputs/mfa_export \
  --lexicon "$NEPALI_MFA_LEXICON" \
  --oov-policy g2p_fallback \
  --transcode-wav \
  --summary-json outputs/mfa_export/summary.json

mfa validate outputs/mfa_export/mfa_corpus outputs/mfa_export/nepali.dict nepali
mfa align outputs/mfa_export/mfa_corpus outputs/mfa_export/nepali.dict acoustic.zip outputs/aligned

nepali-mfa-build-failure-dashboard \
  --manifest outputs/mfa_export/mfa_manifest.jsonl \
  --aligned-dir outputs/aligned \
  --out-dir review_dashboards/heldout

nepali-mfa-apply-review-labels \
  --manifest outputs/mfa_export/mfa_manifest.jsonl \
  --review-tsv review_dashboards/heldout/mfa_review.tsv \
  --analysis-csv outputs/aligned/alignment_analysis.csv \
  --out-dir outputs/reviewed_tiers \
  --repair-year-style
```

Output tiers:

- `mfa_clean_seed.jsonl`: clean enough for the next MFA acoustic-model seed.
- `asr_noisy_background.jsonl`: text/audio usable for ASR but not clean MFA.
- `asr_reviewed_candidate.jsonl`: text/audio accepted but MFA alignment failed.
- `rejected.jsonl`: do not train.
- `needs_review.jsonl`: missing or inconclusive labels.

## Docs

Start with:

- `docs/mfa-production-clean-runbook-2026-05-17.md`
- `docs/mfa-export-status-2026-05-16.md`
- `docs/mfa-background-audio-probe-2026-05-17.md`

## Repository Policy

GitHub stores source, docs, tests, and lightweight config only. Audio, TextGrids,
trained acoustic models, checkpoints, dashboards with copied audio, and manifest
exports belong in object storage or Hugging Face datasets/models.
