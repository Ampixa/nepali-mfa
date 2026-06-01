# MFA Production-Clean Runbook - 2026-05-17

This runbook turns the current MFA baseline into a production-clean data gate.
The goal is not to let MFA reject data by itself. The goal is to combine MFA
metrics, manual review labels, transcript repair, and tiered manifests so every
training row has a traceable decision.

## Current Baseline

Model:

- `/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/nepali_mixed_5000_acoustic.zip`

Held-out result:

- held-out rows: 1000
- TextGrids exported: 934
- strongest domains: SLR54, podcast source, YouTube fixed120
- weakest reviewed source: `chirp2_gt1_reviewed`

This is good enough for triage and training-data gating. It is not a final
automatic rejection authority.

## Review Labels

Use these labels in the dashboard:

| Label | Meaning | ASR use | Clean MFA seed use |
|---|---|---|---|
| `Keep` | speech/text good | yes | yes |
| `Minor` | small issue, still useful | yes | no by default |
| `Number` | text uses wrong number/year verbalization | repair then yes | repair then yes |
| `BG audio` | transcript correct but music/noise is present | yes, noisy tier | no by default |
| `Audio bad` | speech not reliable/intelligible | no | no |
| `Text bad` | transcript does not match speech | no | no |
| `Align bad` | audio/text good but MFA failed | ASR candidate | no |
| `Unsure` | not enough confidence | review | no |

## Export Labels

In the dashboard, use `Export TSV`. Then merge labels back into the held-out or
full-source manifest:

```bash
nepali-mfa-apply-review-labels \
  --manifest /path/to/mfa_manifest.jsonl \
  --review-tsv /path/to/exported_review.tsv \
  --analysis-csv /path/to/alignment_analysis.csv \
  --out-dir /path/to/reviewed_tiers \
  --repair-year-style
```

Outputs:

- `reviewed_all.jsonl`
- `mfa_clean_seed.jsonl`
- `asr_noisy_background.jsonl`
- `asr_reviewed_candidate.jsonl`
- `rejected.jsonl`
- `needs_review.jsonl`
- `summary.json`

## Number Repairs

Year-style repairs are explicit and review-driven.

Example:

- before: `एक हजार नौ सय पन्चानब्बे`
- after: `उन्नाइस सय पन्चानब्बे`

The default normalizer still keeps plain cardinals because `1995` can also be a
quantity. Use `--repair-year-style` only when dashboard review confirms the
speaker used year-style speech.

## Seed Lexicon Fallback

Dashboard "Seed lexicon fallback" words are not automatic data errors. They are
words missed by the seed Google/candidate lexicon before G2P fallback and merged
dictionary coverage.

Future manifests separate:

- `seed_lexicon_oov_words`
- `g2p_fallback_words`
- `unresolved_oov_words`

Only unresolved OOVs should block MFA readiness.

## Background Audio

The controlled Piper probe showed:

- SNR drops as music-bed volume rises.
- Music tails after speech strongly hurt speech likelihood.
- Likelihood alone does not classify music beds.

So automatic filtering should use a combination:

- SNR
- speech log likelihood
- overall log likelihood
- phone-duration deviation
- dashboard labels

`BG audio` rows can remain in ASR robustness training if the transcript is
correct. They should be excluded or downweighted for the clean MFA seed set.

## Production-Clean Loop

1. Build source-specific MFA corpus with `g2p_fallback`.
2. Align with current best mixed-domain MFA model.
3. Build dashboard with `build_mfa_failure_dashboard.py`.
4. Review the riskiest rows and export TSV.
5. Merge labels with `apply_mfa_review_labels.py`.
6. Train the next MFA model only on `mfa_clean_seed.jsonl`.
7. Keep `asr_noisy_background.jsonl` as a separate ASR robustness tier.
8. Re-run held-out validation and compare coverage by source.

## Automated Nepali Triage

Use `nepali-mfa-auto-triage` before large manual review batches. It combines:

- human review labels, if available;
- source transcript text checks for `[सङ्गीत]`, `>>`, and other caption artifacts;
- duration bounds;
- OOV count and OOV ratio;
- MFA failure buckets and `alignment_analysis.csv` metrics;
- optional ASR agreement scores such as CER/WER from Chirp2, Whisper, or a
  committee pass.

Build ASR agreement scores first when multiple transcript passes exist:

```bash
nepali-mfa-asr-agreement \
  --reference /path/to/mfa_manifest.jsonl \
  --hypothesis /path/to/whisper_large_v3.jsonl \
  --hypothesis /path/to/chirp2.jsonl \
  --out-dir /path/to/asr_agreement
```

Example:

```bash
nepali-mfa-auto-triage \
  --manifest /path/to/mfa_manifest.jsonl \
  --analysis-csv /path/to/alignment_analysis.csv \
  --failure-audit-csv /path/to/failure_audit.csv \
  --asr-scores-csv /path/to/asr_agreement/asr_agreement_scores.csv \
  --review-tsv /path/to/exported_review.tsv \
  --out-dir /path/to/auto_triage
```

Output policy:

- `auto_silver_clean.jsonl`: clean candidate rows for ASR and clean MFA seed.
- `auto_bronze_asr.jsonl`: usable for ASR robustness, not clean MFA seed.
- `auto_rejected.jsonl`: obvious text/audio/artifact failures.
- `needs_review.jsonl`: uncertain rows for human review.

This is a gate, not a final judge. For Nepali, keep human review on:

- rows with numbers/year wording;
- high OOV ratio;
- background audio or other speakers;
- failed MFA alignment but apparently correct transcript;
- new channels or domains before trusting their captions.

By default, rows without an external signal stay in `needs_review` even if basic
text and duration checks pass. Use `--allow-rules-only-silver` only for trusted,
already-characterized sources.

After triage, select a bounded manual-review batch:

```bash
nepali-mfa-select-review-batch \
  --manifest /path/to/auto_triage/auto_triaged_all.jsonl \
  --limit-rows 1000 \
  --max-hours 5 \
  --stratify source_reason \
  --out-dir /path/to/review_batch_001
```

This avoids reviewing only one channel, one failure mode, or one easy source.

## Next Production Target

Train the next MFA model from a larger reviewed seed:

- start with `mfa_clean_seed.jsonl` from held-out and source reviews;
- add clean SLR54 and clean source rows;
- exclude/downweight `BG audio`;
- repair reviewed `Number` rows;
- keep source-balanced sampling so Chirp2/YouTube do not dominate.

Acceptance target for the next MFA baseline:

- held-out TextGrid export above 97%;
- no source below 90%;
- reviewed `BG audio` rows remain in noisy ASR tier, not clean MFA seed;
- number/year mismatches are repaired before alignment.
