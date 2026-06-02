# MFA Heldout Clean-Detection Smoke - 2026-06-02

This smoke test checks whether the current Nepali MFA baseline can separate
clean-likely unseen audio from risky/noisy unseen audio using alignment
diagnostics.

It does not test on the mixed 5000 training corpus. It uses the held-out 1000
slice aligned by the mixed 5000 model, and then re-aligns a fresh 24-file smoke
corpus copied from that held-out slice.

## Model And Data

M4 host:

```text
cdjk@100.109.18.109
```

Model:

```text
/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/nepali_mixed_5000_acoustic.zip
```

Dictionary:

```text
/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/nepali.dict
```

Held-out source manifest:

```text
/Users/cdjk/asr_mfa_validation_slices_20260516/mixed_heldout_1000/mfa_manifest.jsonl
```

Fresh smoke output:

```text
/Users/cdjk/asr_mfa_training_20260517/mfa_heldout_clean_detection_smoke_20260602
```

The smoke corpus contains 24 held-out files:

| Label | Rows | Sources |
|---|---:|---|
| `clean_candidate` | 12 | `slr54_gold_v1`, `sushant_source_reviewed_le30` |
| `risk_candidate` | 12 | `youtube_caption_wordtimed_fixed120`, `chirp2_cer1`, `chirp2_gt1_reviewed` |

The clean candidates were selected from high-SNR held-out rows. The risk
candidates were selected from low-SNR held-out rows. These are not human
ground-truth labels for "no background noise"; they are a real-data smoke set
for checking whether the MFA metrics behave as expected on unseen audio.

## Command

MFA needs the aligner environment bin directory on `PATH` so its subprocess
checks can find OpenFST and audio tools:

```bash
export PATH=/Users/cdjk/asr_mfa_env/micromamba/envs/aligner/bin:$PATH
/Users/cdjk/asr_mfa_env/micromamba/envs/aligner/bin/mfa align \
  --clean \
  --overwrite \
  /Users/cdjk/asr_mfa_training_20260517/mfa_heldout_clean_detection_smoke_20260602/mfa_corpus \
  /Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/nepali.dict \
  /Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/nepali_mixed_5000_acoustic.zip \
  /Users/cdjk/asr_mfa_training_20260517/mfa_heldout_clean_detection_smoke_20260602/aligned
```

Result:

```text
24 / 24 TextGrids exported
37.276 seconds wall time
```

## Gate Used

The smoke gate is intentionally simple:

```text
pred_clean =
  snr >= 10.5
  and speech_log_likelihood >= -70
  and overall_log_likelihood >= -70
```

This gate should be read as "clean-likely and aligned enough for high-confidence
promotion." It should not be read as a definitive background-noise detector.

## Fresh Smoke Result

| Label | Rows | Passed clean gate | Median SNR | Median speech LL | Median overall LL | Median phone deviation |
|---|---:|---:|---:|---:|---:|---:|
| `clean_candidate` | 12 | 12 | 17.38 | -58.93 | -52.71 | 3.03 |
| `risk_candidate` | 12 | 0 | -0.84 | -55.88 | -51.48 | 3.42 |

The fresh held-out smoke test separated these selected groups perfectly:

- all high-SNR clean candidates passed;
- all low-SNR risk candidates failed;
- the separation was driven mainly by SNR, not by phone-duration deviation.

## Full Heldout Context

The existing mixed-heldout-1000 alignment has 1000 rows. Empty MFA metrics are
treated as `not clean`.

Using the same gate:

| Source slice | Rows | Rows with metrics | Passed clean gate | Median SNR |
|---|---:|---:|---:|---:|
| `chirp2_cer1` | 200 | 189 | 1 | 4.46 |
| `chirp2_gt1_reviewed` | 200 | 159 | 0 | 3.85 |
| `slr54_gold_v1` | 200 | 200 | 96 | 10.35 |
| `sushant_source_reviewed_le30` | 200 | 199 | 50 | 8.11 |
| `youtube_caption_wordtimed_fixed120` | 200 | 187 | 2 | 3.55 |

This matches the earlier manual review pattern: source-caption and documentary
style audio often aligns, but it is not necessarily clean/no-background audio.

## Interpretation

The current MFA model can identify high-confidence clean-likely unseen audio
when SNR is high and the alignment likelihoods are normal. It also rejects
obvious low-SNR risky clips.

The current MFA model cannot prove that a clip has no background bed, room tone,
river sound, music, or background speaker. Light background audio can still
align correctly and may pass if speech dominates. For production promotion,
MFA should be one gate in a committee:

- MFA clean gate: TextGrid exists, SNR high, likelihoods sane;
- ASR agreement: transcript matches one or more ASR passes;
- audio-quality/noise gate: DNSMOS or a similar no-reference audio-quality
  model;
- human review for borderline rows or new sources.

Recommended policy after this smoke:

| Tier | Criteria |
|---|---|
| `mfa_clean_candidate` | passes MFA clean gate and ASR agreement |
| `asr_silver_noisy` | transcript is correct but background/noise exists |
| `needs_review` | low SNR, failed metrics, or source/chunking uncertainty |
| `reject_or_repair` | text mismatch, bad chunk, severe background, or bad audio |

