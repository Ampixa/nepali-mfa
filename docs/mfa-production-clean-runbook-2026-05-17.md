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
- strongest domains: SLR54, Sushant, YouTube fixed120
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

## Next Production Target

Train the next MFA model from a larger reviewed seed:

- start with `mfa_clean_seed.jsonl` from held-out and source reviews;
- add clean SLR54 and clean Sushant rows;
- exclude/downweight `BG audio`;
- repair reviewed `Number` rows;
- keep source-balanced sampling so Chirp2/YouTube do not dominate.

Acceptance target for the next MFA baseline:

- held-out TextGrid export above 97%;
- no source below 90%;
- reviewed `BG audio` rows remain in noisy ASR tier, not clean MFA seed;
- number/year mismatches are repaired before alignment.
