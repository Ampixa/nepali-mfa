# MFA v1 Baseline Plan (2026-05-22)

## Current Baseline

Source machine:

- `cdjk@100.109.18.109`

Held-out bundle:

- `/Users/cdjk/asr_mfa_validation_slices_20260516/mixed_heldout_1000/mfa_manifest.jsonl`

Alignment output:

- `/Users/cdjk/asr_mfa_training_20260517/mixed_heldout_1000_align_mixed5k/aligned/alignment_analysis.csv`

Failure dashboard:

- `http://100.109.18.109:8770/`
- remote path: `/Users/cdjk/asr_mfa_training_20260517/mixed_heldout_1000_align_mixed5k/failure_dashboard`

Baseline model:

- `/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/nepali_mixed_5000_acoustic.zip`

## Audit Result

Generated locally with:

```bash
PYTHONPATH=src python3 -m nepali_mfa.audit_alignment_baseline \
  --manifest outputs/baseline_20260522/remote_snapshot/mfa_manifest.jsonl \
  --failure-audit-csv outputs/baseline_20260522/remote_snapshot/failure_audit.csv \
  --analysis-csv outputs/baseline_20260522/remote_snapshot/alignment_analysis.csv \
  --out-dir outputs/baseline_20260522/audit
```

Summary:

- rows: `1000`
- hours: `3.260117`
- machine-pass candidates: `752` rows, `2.407513h`
- machine-review rows: `248` rows, `0.852603h`
- failure buckets:
  - `missing_textgrid`: `66`
  - `high_phone_deviation`: `60`
  - `low_overall_ll`: `57`
  - `low_snr`: `47`
  - `low_speech_ll`: `18`

By source:

| Source | Rows | Machine pass | Machine review |
|---|---:|---:|---:|
| `chirp2_cer1` | 200 | 163 | 37 |
| `chirp2_gt1_reviewed` | 200 | 128 | 72 |
| `slr54_gold_v1` | 200 | 190 | 10 |
| `sushant_source_reviewed_le30` | 200 | 178 | 22 |
| `youtube_caption_wordtimed_fixed120` | 200 | 93 | 107 |

## Local Artifacts

These are intentionally untracked under `outputs/`:

- `outputs/baseline_20260522/audit/baseline_summary.json`
- `outputs/baseline_20260522/audit/machine_pass_candidates.jsonl`
- `outputs/baseline_20260522/audit/machine_review_candidates.jsonl`
- `outputs/baseline_20260522/audit/manual_review_template.tsv`
- `outputs/baseline_20260522/audit/oov_report.tsv`

## Interpretation

`machine_pass_candidates.jsonl` is not a human-reviewed clean seed. It means the
current MFA model did not select those rows for the failure dashboard.

`manual_review_template.tsv` is the missing bridge. Once labels are filled, use
`nepali-mfa-apply-review-labels` to produce:

- `mfa_clean_seed.jsonl`
- `asr_noisy_background.jsonl`
- `asr_reviewed_candidate.jsonl`
- `rejected.jsonl`
- `needs_review.jsonl`

## Next Step

Review the 248 failure-dashboard rows at:

```text
http://100.109.18.109:8770/
```

Labels to use:

- `keep`
- `minor`
- `background_audio`
- `number_mismatch`
- `alignment_bad`
- `text_bad`
- `audio_bad`
- `unsure`

Then merge the exported TSV:

```bash
nepali-mfa-apply-review-labels \
  --manifest outputs/baseline_20260522/remote_snapshot/mfa_manifest.jsonl \
  --review-tsv /path/to/exported_mfa_review.tsv \
  --analysis-csv outputs/baseline_20260522/remote_snapshot/alignment_analysis.csv \
  --out-dir outputs/baseline_20260522/reviewed_tiers \
  --repair-year-style
```

## MFA v1 Training Policy

Train MFA v1 from:

1. reviewed `keep` rows;
2. reviewed `number_mismatch` rows only after explicit year/number repair;
3. high-confidence machine-pass rows only after a small spot-check confirms the
   pass precision is high.

Exclude from clean MFA seed:

- `background_audio`
- `alignment_bad`
- `text_bad`
- `audio_bad`
- `unsure`
- unresolved number/date mismatch rows

Rows with correct text/audio but background music can stay in an ASR noisy tier,
but they should not train the clean MFA acoustic model.

## 2026-05-27 Bulk Review Decision

After sampling the failure-dashboard rows, the reviewer found background audio
across the sampled set. We applied a conservative bulk label to all 248 rows in
the Web UI queue:

- label: `background_audio`
- ASR use: yes, noisy/background tier
- clean MFA seed use: no

Generated local files:

- `outputs/baseline_20260522/audit/manual_review_all_background_audio.tsv`
- `outputs/baseline_20260522/reviewed_tiers_all_bg/asr_noisy_background.jsonl`
- `outputs/baseline_20260522/reviewed_tiers_all_bg/summary.json`

Result:

- `asr_noisy_background`: 248 rows, 0.852603h
- `mfa_clean_seed`: 0 rows
- `needs_review`: 752 rows

The served dashboard was also patched to default open rows to `BG audio`; the
exported TSV is stored on the M4 at:

```text
/Users/cdjk/asr_mfa_training_20260517/mixed_heldout_1000_align_mixed5k/failure_dashboard/mixed_heldout_1000_all_background_audio_review.tsv
```
