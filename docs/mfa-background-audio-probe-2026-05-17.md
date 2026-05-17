# MFA Background-Audio Probe - 2026-05-17

Purpose: test whether MFA metrics distinguish clean speech from background
music/noise, using controlled Piper TTS audio with known transcripts.

## Setup

Generated 20 Nepali Piper TTS utterances with:

- clean speech
- music bed mixed throughout at volume `0.14`
- music bed mixed throughout at volume `0.35`
- music bed mixed throughout at volume `0.60`
- clean speech plus 2 seconds of music appended after speech

Voice:

- `data/external/piper_voices/ne_NP/chitwan-medium.onnx`

Background music source:

- `/Users/cdjk/github/latent-sync_(Instrumental)_model_bs_roformer_ep_317_sdr_12.flac`

MFA model:

- `/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/nepali_mixed_5000_acoustic.zip`

Remote probe paths on the M4:

- `/Users/cdjk/asr_mfa_training_20260517/asr_mfa_tts_probe_levels_20260517`
- aligned output: `/Users/cdjk/asr_mfa_training_20260517/asr_mfa_tts_probe_levels_20260517/aligned_mixed5k`
- analysis CSV: `/Users/cdjk/asr_mfa_training_20260517/asr_mfa_tts_probe_levels_20260517/aligned_mixed5k/alignment_analysis.csv`

All 100 utterances exported TextGrids.

## Results

Median metrics by controlled condition:

| Variant | Rows | Overall LL median | Speech LL median | Phone dev median | SNR median |
|---|---:|---:|---:|---:|---:|
| clean | 20 | -63.130 | -62.845 | 3.097 | 11.931 |
| music014 | 20 | -62.861 | -60.319 | 2.509 | 10.015 |
| music035 | 20 | -62.307 | -59.866 | 2.482 | 7.607 |
| music060 | 20 | -62.068 | -59.307 | 2.454 | 6.149 |
| tailmusic | 20 | -66.593 | -74.771 | 3.097 | 11.590 |

Median per-text deltas vs clean:

| Variant | Overall LL delta | Speech LL delta | SNR delta | Phone dev delta |
|---|---:|---:|---:|---:|
| music014 | +1.074 | +2.688 | -1.988 | -0.315 |
| music035 | +1.499 | +3.000 | -4.102 | -0.474 |
| music060 | +1.395 | +3.141 | -5.985 | -0.586 |
| tailmusic | -3.479 | -11.880 | +0.919 | 0.000 |

## Interpretation

MFA is not directly classifying music. The metrics behave differently for
different background-audio shapes:

- Music bed throughout speech lowered SNR monotonically as music got louder.
- Overall likelihood and speech likelihood did not degrade for the music-bed
  cases in this synthetic control. In fact, they got slightly better, likely
  because the utterance was still fully explained by speech phones and the
  mixed audio changed feature statistics rather than creating an unmatched
  post-speech region.
- Music appended after speech strongly degraded speech likelihood and overall
  likelihood. This is the easiest case for MFA to flag because there is audio
  that cannot be explained by the transcript.

So the right claim is:

- MFA metrics can surface background-audio risk, especially music/noise tails
  and low-SNR bed audio.
- MFA does not provide a standalone "music present" classifier.
- SNR is the most direct metric for music bed in this probe.
- Low speech likelihood / low overall likelihood are stronger signals for
  untranscribed tails, bad cuts, or transcript/audio mismatch.

## Practical Rule

For dashboard triage:

- Use `BG audio` when speech and text are correct but music/noise is present.
- Use `Audio bad` only when the speech becomes hard to understand.
- Treat `BG audio` as acceptable for ASR robustness training if transcript is
  correct.
- Exclude or downweight `BG audio` rows for clean MFA seed training.

For automatic filtering:

- Do not use one metric alone.
- Candidate rule for background/noisy tier:
  - SNR below a calibrated threshold, or
  - low speech likelihood with a clean transcript, or
  - high phone-duration deviation with audible background/tail noise.
- Thresholds must be calibrated against dashboard labels, not set only from this
  small Piper probe.
