# MFA Current Run Record - 2026-05-31

This document is the current operational record for the Nepali MFA run. It ties
together the older chronological notes, the committed tooling, the active
dashboards, and the current decisions about clean/noisy/rejected data.

GitHub repo:

```text
git@github.com:Ampixa/nepali-mfa.git
```

Current important commits:

| Commit | Purpose |
|---|---|
| `0c86183` | Add source-review label applier |
| `cec1c17` | Add source-review dashboard for MFA candidates |
| `441f9f4` | Record background-audio MFA review decision |
| `c51d2b0` | Add MFA baseline audit workflow |
| `97f9a5d` | Initial Nepali MFA toolkit |

## Scope

This repo owns the forced-alignment and data-quality gate for the Nepali ASR
pipeline. It does not train the ASR model. Its outputs are manifests and review
tiers that downstream ASR training can consume.

The current goal is to build a clean-enough MFA seed and a reliable review loop
so larger Nepali ASR datasets can be split into:

- clean speech/text rows for MFA acoustic-model training;
- correct but noisy rows for ASR robustness training;
- repair-needed rows;
- rejected rows.

## Machines And Paths

Primary MFA CPU host:

```text
cdjk@100.109.18.109
```

Earlier 4TB SSD/export host:

```text
cdjk@100.117.21.47
```

Important M4 paths:

| Artifact | Path |
|---|---|
| MFA environment | `/Users/cdjk/asr_mfa_env` |
| Mixed 5000 validation slice | `/Users/cdjk/asr_mfa_validation_slices_20260516/mixed_5000` |
| Held-out 1000 validation slice | `/Users/cdjk/asr_mfa_validation_slices_20260516/mixed_heldout_1000` |
| Mixed 5000 trained MFA model | `/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/nepali_mixed_5000_acoustic.zip` |
| Held-out alignment output | `/Users/cdjk/asr_mfa_training_20260517/mixed_heldout_1000_align_mixed5k/aligned` |
| Held-out failure dashboard | `/Users/cdjk/asr_mfa_training_20260517/mixed_heldout_1000_align_mixed5k/failure_dashboard` |
| source dashboard | source-specific runtime dashboard path on the M4, not tracked in Git |

Important 4TB/export paths:

| Artifact | Path |
|---|---|
| Full MFA export root | `/home/cdjk/asr_mfa_outputs_20260516` |
| Mixed 5000 source slice | `/home/cdjk/asr_mfa_validation_slices_20260516/mixed_5000` |
| Held-out 1000 source slice | `/home/cdjk/asr_mfa_validation_slices_20260516/mixed_heldout_1000` |

GitHub does not store audio, TextGrids, trained acoustic models, copied
dashboards with audio, or large manifests. Those are runtime artifacts.

## Source Inventory

The full MFA-prep export completed on 2026-05-16:

| Source | Rows | Source hours |
|---|---:|---:|
| `slr54_gold_v1` | 157871 | 154.446 |
| `podcast_source_reviewed_le30` | 10214 | 37.102 |
| `youtube_caption_wordtimed_fixed120` | 35150 | 69.660 |
| `chirp2_cer1` | 43640 | 214.503 |
| `chirp2_gt1_reviewed` | 6940 | 33.827 |

Total represented source hours: about `509.5h`.

Current source policy:

| Source | Current role |
|---|---|
| `slr54_gold_v1` | Clean read-speech anchor; useful for MFA seed, but domain-limited. |
| `podcast_source_reviewed_le30` | Candidate clean podcast speech; needs source review export before promotion. |
| `youtube_caption_wordtimed_fixed120` | Potential ASR source; chunking/caption alignment needs strict validation. |
| `chirp2_cer1` | Strong ASR transcript source; likely usable, but not automatically clean MFA seed. |
| `chirp2_gt1_reviewed` | Weakest held-out MFA coverage; review/repair before trusting. |

## Acoustic-Model Lineage

### SLR54 5000 Model

Trained on M4:

```text
/Users/cdjk/asr_mfa_training_20260516/slr54_5000_m4/nepali_slr54_5000_acoustic.zip
```

Result:

- training rows: `5000`
- training duration: about `5.31h`
- wall time: about `44.3m`
- TextGrids exported: `4996 / 5000`

Use:

- good read-speech smoke model;
- not enough domain coverage for podcasts, Chirp2, and YouTube.

### Mixed 250 Model

Trained on a small balanced mixed-source slice:

```text
/Users/cdjk/asr_mfa_training_20260516/mixed_250_train_m4/nepali_mixed_250_acoustic.zip
```

Result:

- training rows: `250`
- TextGrids exported: `250 / 250`
- confirmed mixed-source acoustic coverage matters.

Use:

- proof-of-path only;
- not a production model.

### Mixed 5000 Model

Current best MFA baseline:

```text
/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/nepali_mixed_5000_acoustic.zip
```

Training slice:

```text
/Users/cdjk/asr_mfa_validation_slices_20260516/mixed_5000
```

Composition:

| Source | Rows |
|---|---:|
| `chirp2_cer1` | 1000 |
| `chirp2_gt1_reviewed` | 1000 |
| `slr54_gold_v1` | 1000 |
| `podcast_source_reviewed_le30` | 1000 |
| `youtube_caption_wordtimed_fixed120` | 1000 |

Training result:

- total duration: about `15.93h`
- wall time: about `3.20h`
- model size: `59 MB`
- TextGrids exported on training slice: `4922 / 5000`

Training-slice coverage:

| Source | Exported | Total | Coverage |
|---|---:|---:|---:|
| `chirp2_cer1` | 984 | 1000 | 98.4% |
| `chirp2_gt1_reviewed` | 947 | 1000 | 94.7% |
| `slr54_gold_v1` | 1000 | 1000 | 100.0% |
| `podcast_source_reviewed_le30` | 1000 | 1000 | 100.0% |
| `youtube_caption_wordtimed_fixed120` | 991 | 1000 | 99.1% |

Use:

- current operational aligner and review signal generator;
- not final, because it was trained on a mixed slice that includes noisy domains.

## Held-Out Validation

Held-out slice:

```text
/Users/cdjk/asr_mfa_validation_slices_20260516/mixed_heldout_1000
```

Held-out alignment output:

```text
/Users/cdjk/asr_mfa_training_20260517/mixed_heldout_1000_align_mixed5k/aligned
```

Aligned with:

```text
/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/nepali_mixed_5000_acoustic.zip
```

Held-out result:

- rows: `1000`
- duration: about `3.26h`
- TextGrids exported: `934 / 1000`
- runtime: about `129s`

Coverage by source:

| Source | Exported | Total | Coverage |
|---|---:|---:|---:|
| `chirp2_cer1` | 189 | 200 | 94.5% |
| `chirp2_gt1_reviewed` | 159 | 200 | 79.5% |
| `slr54_gold_v1` | 200 | 200 | 100.0% |
| `podcast_source_reviewed_le30` | 199 | 200 | 99.5% |
| `youtube_caption_wordtimed_fixed120` | 187 | 200 | 93.5% |

Interpretation:

- `slr54` and `podcast_source` generalize well.
- `youtube_caption_wordtimed_fixed120` is promising but still needs chunk/text
  review.
- `chirp2_gt1_reviewed` is the main weak spot for this model.

## Held-Out Failure Audit

Committed CLI:

```text
nepali-mfa-audit-alignment-baseline
```

Local audit output:

```text
outputs/baseline_20260522/audit
```

This path is intentionally untracked because it is a generated local artifact.

Summary:

- total rows: `1000`
- total hours: `3.260117`
- machine-pass candidates: `752` rows, `2.407513h`
- machine-review rows: `248` rows, `0.852603h`

Failure buckets:

| Bucket | Rows |
|---|---:|
| `missing_textgrid` | 66 |
| `high_phone_deviation` | 60 |
| `low_overall_ll` | 57 |
| `low_snr` | 47 |
| `low_speech_ll` | 18 |

By source:

| Source | Rows | Machine pass | Machine review |
|---|---:|---:|---:|
| `chirp2_cer1` | 200 | 163 | 37 |
| `chirp2_gt1_reviewed` | 200 | 128 | 72 |
| `slr54_gold_v1` | 200 | 190 | 10 |
| `podcast_source_reviewed_le30` | 200 | 178 | 22 |
| `youtube_caption_wordtimed_fixed120` | 200 | 93 | 107 |

Important caveat:

`machine_pass_candidates.jsonl` does not mean human-reviewed clean. It only
means the current model did not select those rows for the failure dashboard.

## Held-Out Failure Dashboard

Dashboard:

```text
http://100.109.18.109:8770/
```

Dashboard path:

```text
/Users/cdjk/asr_mfa_training_20260517/mixed_heldout_1000_align_mixed5k/failure_dashboard
```

Committed CLI:

```text
nepali-mfa-build-failure-dashboard
```

Purpose:

- inspect risky held-out rows;
- categorize failure modes;
- produce a TSV that can be merged into tiered manifests.

Labels:

| UI label | Stored label | Meaning | ASR use | Clean MFA seed use |
|---|---|---|---|---|
| `Keep` | `keep` | speech/text good | yes | yes |
| `Minor` | `minor` | small issue | yes | conservative no for held-out failure flow |
| `Number` | `number_mismatch` | year/number verbalization mismatch | repair then yes | repair then yes |
| `BG audio` | `background_audio` | target speech plus background music/noise/other voices/ambience | noisy tier | no |
| `Audio bad` | `audio_bad` | target speech unreliable | no | no |
| `Text bad` | `text_bad` | transcript mismatch | no | no |
| `Align bad` | `alignment_bad` | audio/text ok but MFA failed | ASR candidate | no |
| `Unsure` | `unsure` | inconclusive | review | no |

2026-05-27 decision:

- Sampled held-out failure-dashboard rows had background audio.
- All 248 dashboard rows were conservatively bulk-labeled
  `background_audio`.
- Resulting tier:
  - `asr_noisy_background`: `248` rows, `0.852603h`
  - `mfa_clean_seed`: `0` rows
  - `needs_review`: `752` rows

Generated local files:

```text
outputs/baseline_20260522/audit/manual_review_all_background_audio.tsv
outputs/baseline_20260522/reviewed_tiers_all_bg/asr_noisy_background.jsonl
outputs/baseline_20260522/reviewed_tiers_all_bg/summary.json
```

M4 copy of the bulk TSV:

```text
/Users/cdjk/asr_mfa_training_20260517/mixed_heldout_1000_align_mixed5k/failure_dashboard/mixed_heldout_1000_all_background_audio_review.tsv
```

## Source Candidate-Clean Dashboard

Dashboard:

```text
http://100.109.18.109:8771/
```

Dashboard path:

```text
/Users/cdjk/asr_mfa_training_YYYYMMDD/source_candidate_clean_dashboard
```

Committed CLI:

```text
nepali-mfa-build-source-review-dashboard
```

Input manifest:

```text
/Users/cdjk/asr_mfa_validation_slices_20260516/mixed_5000/mfa_manifest.jsonl
```

Dashboard summary:

- `rows_matching_source`: `1000`
- `rows_missing_audio`: `0`
- `rows_review`: `1000`
- `review_hours`: `3.6438`
- `source`: `podcast_source`
- `slice_source`: `podcast_source_reviewed_le30`

The dashboard serves audio through symlinks and byte-range HTTP. It does not
duplicate the wav files.

Current server status as of 2026-05-31:

- server URL: `http://100.109.18.109:8771/`
- process is started with `nepali_mfa.serve_static_range`
- page verified with `HTTP 200`
- first audio verified with `HTTP 206 Partial Content`

Important browser-state caveat:

- review labels live in the reviewer's browser `localStorage`;
- the server cannot see review progress until the reviewer clicks `Export TSV`;
- after export, the TSV must be copied back to the M4 or local repo before the
  label applier can count reviewed/clean/noisy rows.

Public review deployment update, 2026-05-31 12:06 NPT:

- public URL: `https://tts.ampixa.com/mfa/review/`;
- dataset: `mfa_source_review_public_20260531`;
- rows: `1000`;
- review hours: `3.6438h`;
- audio package: MP3, mono `16 kHz`, `32 kbps`;
- compressed public audio size: about `53 MB`, down from about `402 MB` raw;
- public row IDs are anonymized as `mfa_0001` through `mfa_1000`;
- private ID mapping is stored outside the public web root on the deployment
  host;
- review decisions save server-side through `/mfa/api/decisions`;
- reviewers get server-side sample claims through `/mfa/api/claims/next`;
- claims skip chunks already decided by any reviewer and skip chunks claimed by
  another reviewer in the last two hours;
- stats endpoint verified:
  `/mfa/api/stats?dataset=mfa_source_review_public_20260531`;
- a smoke write to dataset `mfa_review_smoke` succeeded.

The public dashboard removes the old localStorage-only progress problem for new
reviewers. Local dashboards still need manual TSV export.

Public review import update, 2026-05-31 14:48 NPT:

- recovered a local browser-exported TSV from mail;
- TSV rows: `1000`;
- labeled rows imported into public API: `200`;
- imported labels: `164 keep`, `30 text_bad`, `4 minor`,
  `2 background_audio`;
- public review stats now report `200 / 1000` completed for
  `mfa_source_review_public_20260531`;
- UI now loads server-reviewed IDs on start and marks those rows read-only, so
  Start/Next begins at the next unreviewed chunk instead of repeating reviewed
  work.

Current review/export status as of 2026-05-31:

- the public review API has imported `200` source-review labels;
- no source-review TSV has been applied to the MFA tier output manifests yet;
- no applied output exists yet at:

```text
/Users/cdjk/asr_mfa_training_YYYYMMDD/source_candidate_clean_reviewed
```

## Source Label Promotion

Committed CLI:

```text
nepali-mfa-apply-source-review-labels
```

Apply a browser-exported TSV:

```bash
nepali-mfa-apply-source-review-labels \
  --manifest /Users/cdjk/asr_mfa_training_YYYYMMDD/source_candidate_clean_dashboard/source_review_manifest.jsonl \
  --review-tsv /path/to/source_candidate_clean_YYYYMMDD_source_review.tsv \
  --out-dir /Users/cdjk/asr_mfa_training_YYYYMMDD/source_candidate_clean_reviewed
```

Outputs:

```text
mfa_clean_seed_candidate.jsonl
asr_noisy_background.jsonl
rejected.jsonl
needs_review.jsonl
reviewed_all.jsonl
summary.json
```

Source-review policy:

| Label | Split | Notes |
|---|---|---|
| `keep` | `mfa_clean_seed_candidate` | Clean source candidate. |
| `minor` | `mfa_clean_seed_candidate` | Accepted for source review because podcast source is likely clean; inspect notes before final MFA v2 seed. |
| `background_audio` | `asr_noisy_background` | Correct text can still train ASR robustness, but not clean MFA seed. |
| `text_bad` | `rejected` | Do not train unless repaired. |
| `audio_bad` | `rejected` | Do not train. |
| `unsure` | `needs_review` | Needs another pass. |
| unlabeled | `needs_review` | Exported TSV had no decision for the row. |

Smoke result:

- a four-label smoke TSV matched four source rows;
- split result: `2` clean candidates, `1` noisy background, `1` rejected,
  `996` unlabeled needs-review rows;
- this verified the applier against the live dashboard manifest.

## Background Audio Policy

`background_audio` means any non-target audio under or around the target speech:

- music;
- river/water/wind/traffic/room ambience;
- other people speaking faintly;
- TV/radio/field sound;
- non-transcribed tails at the start or end.

MFA is not a music classifier. It can still surface risk through:

- missing TextGrid;
- low SNR;
- low speech or overall likelihood;
- high phone-duration deviation;
- failed/unstable alignment.

Rows with clear speech and correct text but background audio are useful ASR
robustness data. They are excluded from the clean MFA seed unless we explicitly
decide to train a noisy-domain MFA model later.

## Number And Year Repair Policy

Observed failure:

- transcript: plain cardinal form like `एक हजार नौ सय ...`
- audio: year-style speech like `उन्नाइस सय ...`

Repair is review-driven. Do not globally rewrite all four-digit numbers,
because the same number can be a quantity, year, count, amount, or identifier.

Held-out review applier:

```bash
nepali-mfa-apply-review-labels \
  --manifest /path/to/mfa_manifest.jsonl \
  --review-tsv /path/to/exported_mfa_review.tsv \
  --analysis-csv /path/to/alignment_analysis.csv \
  --out-dir /path/to/reviewed_tiers \
  --repair-year-style
```

Only rows labeled `number_mismatch` are eligible for the year-style repair.

## OOV Clarification

The dashboard's older `OOV words` display was not true final MFA dictionary OOV.
It meant words missed by the seed Google/candidate lexicon before G2P fallback
and merged dictionary coverage.

Many displayed words were valid Nepali and already existed in the final MFA
dictionary. Therefore, seed-lexicon fallback words are review context, not an
automatic rejection reason.

Future manifests separate:

- `seed_lexicon_oov_count` / `seed_lexicon_oov_words`;
- `g2p_fallback_count` / `g2p_fallback_words`;
- `unresolved_oov_count` / `unresolved_oov_words`.

Only unresolved OOVs should block MFA readiness.

## Committed Tooling

Current CLIs:

| CLI | Purpose |
|---|---|
| `nepali-mfa-build-corpus` | Build MFA corpus, `.lab` files, dictionary, manifest. |
| `nepali-mfa-build-validation-slice` | Build balanced source validation slices. |
| `nepali-mfa-build-heldout-slice` | Build held-out slices while excluding training rows. |
| `nepali-mfa-build-failure-dashboard` | Build held-out failure/risk dashboard. |
| `nepali-mfa-build-source-review-dashboard` | Build source-level clean-candidate review dashboard. |
| `nepali-mfa-audit-alignment-baseline` | Summarize held-out alignment and produce review/pass candidates. |
| `nepali-mfa-apply-review-labels` | Apply held-out failure-dashboard labels. |
| `nepali-mfa-apply-source-review-labels` | Apply source-dashboard labels. |
| `nepali-mfa-build-reverse-g2p` | Build reverse-G2P index. |
| `nepali-mfa-build-reverse-g2p-corpus` | Build learned reverse-G2P training rows. |
| `nepali-mfa-train-reverse-g2p` | Train learned reverse-G2P model. |
| `nepali-mfa-predict-reverse-g2p` | Decode phones with learned reverse-G2P model. |
| `nepali-mfa-serve-static-range` | Serve static dashboards with byte-range audio support. |

Current tests:

```bash
pytest -q
```

Latest local result before this document:

```text
13 passed, 1 skipped
```

## What Is Not Done Yet

1. The source review has not been exported to TSV, so reviewed count and clean
   hours are not yet known server-side.
2. source clean candidates have not been promoted into
   `source_candidate_clean_reviewed`.
3. A clean MFA v2 model has not been trained from reviewed SLR54 + reviewed
   podcast source.
4. The full 509h export has not been re-tiered with the improved label policy.
5. YouTube caption rows still need stricter chunk/text validation before they
   can be treated as high-confidence clean data.
6. Chirp2 rows are promising for ASR, but the `chirp2_gt1_reviewed` held-out
   weakness must be explained before using it as clean MFA seed.
7. Background-audio automatic filtering thresholds are not final; use dashboard
   labels as ground truth for calibration.
8. Reverse-G2P repair exists, but it has not been promoted into a final
   production lexicon-update loop for this MFA run.

## Next Exact Steps

1. Finish source review in the browser.
2. Click `Export TSV`.
3. Copy the exported TSV to the M4 or local repo.
4. Run `nepali-mfa-apply-source-review-labels`.
5. Inspect `summary.json` for clean/noisy/rejected hours.
6. Build a clean seed from:
   - reviewed podcast source `keep` / `minor`;
   - SLR54 clean rows;
   - reviewed number repairs where applicable.
7. Train MFA v2 on the clean seed.
8. Re-align the mixed held-out 1000 rows.
9. Compare against current held-out baseline:
   - target TextGrid export above `97%`;
   - no source below `90%`;
   - background-audio rows kept out of the clean MFA seed;
   - number/year mismatches repaired before alignment/training.

## What Not To Claim Yet

- Do not claim the current MFA model is production final.
- Do not claim `machine_pass_candidates` are human-clean.
- Do not claim podcast source has been reviewed until a TSV export is applied.
- Do not claim background-audio detection is automatic or solved.
- Do not train clean MFA v2 from YouTube/Chirp2/Herne-Katha-style noisy data
  without review or source-specific filtering.
