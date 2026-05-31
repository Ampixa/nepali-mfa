# MFA Export Status (2026-05-16)

## Machine

- Host: `cdjk@100.117.21.47`
- Mounted drive: `/dev/sda2` (`TRANSCEND`, exFAT) at `/mnt/transcend4tb`
- Export root: `/home/cdjk/asr_mfa_outputs_20260516`
- Validation slice root: `/home/cdjk/asr_mfa_validation_slices_20260516/slice_250`

## Completed Export

The full MFA-prep export completed successfully.

| Source | Rows | Source hours |
|---|---:|---:|
| `slr54_gold_v1` | 157871 | 154.446 |
| `podcast_source_reviewed_le30` | 10214 | 37.102 |
| `youtube_caption_wordtimed_fixed120` | 35150 | 69.660 |
| `chirp2_cer1` | 43640 | 214.503 |
| `chirp2_gt1_reviewed` | 6940 | 33.827 |

Total rows: 253815.

Approximate represented source hours: 509.5.

## Generated Files

Each source has:

- `mfa_corpus/<speaker>/<utt_id>.<audio_ext>`
- `mfa_corpus/<speaker>/<utt_id>.lab`
- `nepali.dict`
- `mfa_manifest.jsonl`
- `oov_words.tsv`
- `summary.json`

The reverse G2P index is:

- `/home/cdjk/asr_mfa_outputs_20260516/reverse/reverse_index.json`

## Validation Slice

A reproducible 250-row validation slice was generated with:

```bash
PYTHONPATH=/home/cdjk/asr_mfa_pipeline/g2p \
python3 /home/cdjk/asr_mfa_pipeline/g2p/nepali-mfa CLI build_mfa_validation_slice.py \
  --export-root /home/cdjk/asr_mfa_outputs_20260516 \
  --out-dir /home/cdjk/asr_mfa_validation_slices_20260516/slice_250 \
  --per-source 50 \
  --replace
```

The slice contains 50 rows from each exported source.

## MFA Install

MFA was not installed on `cdjk`, and no conda/mamba install existed. A user-space
micromamba/MFA install was created at:

- `/home/cdjk/asr_mfa_env`
- log: `/home/cdjk/asr_mfa_env/logs/install.log`

Installed MFA version:

- `3.3.9`

The official MFA install path is conda-forge/mamba because the Kaldi dependency
is bundled through conda packages.

## Slice Validation

No-acoustic validation passed for the 250-row slice:

- 250 sound files
- 250 lab files
- 47 speakers
- no sound read errors
- no missing transcripts
- no transcript files missing sound
- no dictionary OOVs after merging source dictionaries

Command:

```bash
/home/cdjk/asr_mfa_env/bin/micromamba run \
  -r /home/cdjk/asr_mfa_env/micromamba \
  -n aligner \
  mfa validate \
  --ignore_acoustics \
  /home/cdjk/asr_mfa_validation_slices_20260516/slice_250/mfa_corpus \
  /home/cdjk/asr_mfa_validation_slices_20260516/slice_250/nepali.dict
```

## Slice Acoustic Training

MFA acoustic-model training was started on the 250-row slice:

- script: `/home/cdjk/asr_mfa_training_20260516/slice_250/run_train_slice.sh`
- log: `/home/cdjk/asr_mfa_training_20260516/slice_250/logs/train.log`
- poll: `/home/cdjk/asr_mfa_training_20260516/slice_250/logs/poll.log`
- model target: `/home/cdjk/asr_mfa_training_20260516/slice_250/nepali_slice_250_acoustic.zip`
- aligned target: `/home/cdjk/asr_mfa_training_20260516/slice_250/aligned`

The first attempt with `--language nepali` failed because the MFA environment
did not include spaCy. The retry uses the default tokenizer because our labels
are already normalized by the ASR pipeline. This passed text normalization,
generated MFCCs/CMVN, compiled graphs, and reached monophone acoustic training.

Do not run full 509h alignment until slice training exports an acoustic model
and a sample alignment can be inspected.

Status update:

- 250-row mixed-source training completed.
- Model: `/home/cdjk/asr_mfa_training_20260516/slice_250/nepali_slice_250_acoustic.zip`
- TextGrid output: `/home/cdjk/asr_mfa_training_20260516/slice_250/aligned`
- Exported TextGrids: 235 of 250 rows.
- Median `overall_log_likelihood`: -53.401
- Median `phone_duration_deviation`: 5.007
- Median `snr`: 3.711

This proves the MFA acoustic path works, but the mixed-source 250-row model is
not a production aligner.

## SLR54 5000-Row Acoustic Smoke

To get a cleaner acoustic-model estimate, a 5000-row SLR54-only slice was
created and structurally validated:

- slice: `/home/cdjk/asr_mfa_validation_slices_20260516/slr54_5000`
- rows: 5000
- speakers: 470
- duration: 19123.4 seconds, about 5.31 hours
- no missing audio
- no missing transcripts
- no dictionary OOVs

Training was started:

- PID: `2248663`
- poller PID: `2250872`
- script: `/home/cdjk/asr_mfa_training_20260516/slr54_5000/run_train.sh`
- log: `/home/cdjk/asr_mfa_training_20260516/slr54_5000/logs/train.log`
- model target: `/home/cdjk/asr_mfa_training_20260516/slr54_5000/nepali_slr54_5000_acoustic.zip`
- aligned target: `/home/cdjk/asr_mfa_training_20260516/slr54_5000/aligned`

It reached monophone training after successful MFCC/CMVN generation and initial
alignment.

## SLR54 5000-Row M4 Migration

Timestamp: 2026-05-16 20:38 NPT.

The i5 4TB-box run became impractically slow in final SAT training:

- host: `cdjk@100.117.21.47`
- runtime before stop: about 5h43m
- final observed stage: `sat_3 - Iteration 24 of 35`
- old train PID: `2248663`
- old poller PID: `2250872`
- status: stopped after M4 run was verified healthy

An M4 Pro laptop was prepared as a faster MFA CPU host:

- host: `cdjk@100.109.18.109`
- CPU: Apple M4 Pro, 14 physical cores
- RAM: 24 GB
- MFA install: `/Users/cdjk/asr_mfa_env`
- MFA version: `3.3.9`

The validated 5000-row SLR54 slice was copied to:

- `/Users/cdjk/asr_mfa_validation_slices_20260516/slr54_5000`

The copied slice was structurally validated on the M4:

- 5000 sound files
- 5000 text files
- 470 speakers
- 19123.400 seconds total duration
- no sound read errors
- no missing transcripts
- no dictionary OOVs

Fresh M4 training was started in background:

- train PID: `93613`
- poller PID: `93614`
- log: `/Users/cdjk/asr_mfa_training_20260516/slr54_5000_m4/logs/train.log`
- poll: `/Users/cdjk/asr_mfa_training_20260516/slr54_5000_m4/logs/poll.log`
- temp: `/Users/cdjk/asr_mfa_tmp/slr54_5000_m4_train`
- model target: `/Users/cdjk/asr_mfa_training_20260516/slr54_5000_m4/nepali_slr54_5000_acoustic.zip`
- aligned target: `/Users/cdjk/asr_mfa_training_20260516/slr54_5000_m4/aligned`

The M4 job passed corpus setup, generated MFCC/CMVN features, compiled initial
graphs, and reached `monophone - Iteration 1 of 40` before the i5 job was
stopped.

Completion update: 2026-05-16 21:24 NPT.

The M4 5000-row SLR54 training finished successfully:

- wall time reported by MFA: 2659.130 seconds, about 44.3 minutes
- model: `/Users/cdjk/asr_mfa_training_20260516/slr54_5000_m4/nepali_slr54_5000_acoustic.zip`
- model size: 55 MB
- TextGrids exported: 4996
- alignment analysis: `/Users/cdjk/asr_mfa_training_20260516/slr54_5000_m4/aligned/alignment_analysis.csv`

Alignment-analysis summary:

| Metric | p10 | median | p90 |
|---|---:|---:|---:|
| `overall_log_likelihood` | -79.715 | -67.046 | -56.895 |
| `speech_log_likelihood` | -60.456 | -56.137 | -52.122 |
| `phone_duration_deviation` | 1.072 | 2.002 | 4.925 |
| `snr` | 9.145 | 13.793 | 18.188 |

The M4 run confirms the previous i5 bottleneck was machine/runtime related, not
an MFA data-prep failure.

## Mixed-Source 250 Validation

Timestamp: 2026-05-16 23:55 NPT.

The SLR54 5.3h acoustic model was tested as an aligner on the mixed 250-row
validation slice:

- slice: `/Users/cdjk/asr_mfa_validation_slices_20260516/slice_250`
- acoustic model: `/Users/cdjk/asr_mfa_training_20260516/slr54_5000_m4/nepali_slr54_5000_acoustic.zip`
- output: `/Users/cdjk/asr_mfa_training_20260516/mixed_250_with_slr54_5h/aligned`
- runtime: 225.304 seconds
- TextGrids exported: 184 / 250

Coverage by source:

| Source | Exported | Total | Coverage |
|---|---:|---:|---:|
| `chirp2_cer1` | 32 | 50 | 64.0% |
| `chirp2_gt1_reviewed` | 33 | 50 | 66.0% |
| `slr54_gold_v1` | 50 | 50 | 100.0% |
| `podcast_source_reviewed_le30` | 41 | 50 | 82.0% |
| `youtube_caption_wordtimed_fixed120` | 28 | 50 | 56.0% |

The SLR54 model warned that six dictionary pronunciations contained phones not
present in the acoustic model. A repaired dictionary was created:

- `/Users/cdjk/asr_mfa_validation_slices_20260516/slice_250/nepali.repaired_for_slr54_5h.dict`

Phone repairs applied:

| Missing phone | Replacement |
|---|---|
| `f` | `ph` |
| `z` | `dz` |
| `tsh:` | `tsh` |
| `dxh:` | `dxh` |

Affected words:

- `ऑफ़`
- `पुछ्छ`
- `बढ्ढा`
- `बिछ्छ`
- `मिज़बुर`
- `हैज़`

Re-running alignment with this repaired dictionary removed the missing-phone
warning but did not improve coverage: the result remained 184 / 250 TextGrids.
Therefore, the primary problem is acoustic-domain mismatch, not just dictionary
phone inventory mismatch.

For comparison, a mixed-source acoustic model was trained on the same 250-row
slice using the repaired dictionary:

- output root: `/Users/cdjk/asr_mfa_training_20260516/mixed_250_train_m4`
- model: `/Users/cdjk/asr_mfa_training_20260516/mixed_250_train_m4/nepali_mixed_250_acoustic.zip`
- runtime reported by MFA: 1456.166 seconds, about 24.3 minutes
- TextGrids exported: 250 / 250

Coverage by source:

| Source | Exported | Total | Coverage |
|---|---:|---:|---:|
| `chirp2_cer1` | 50 | 50 | 100.0% |
| `chirp2_gt1_reviewed` | 50 | 50 | 100.0% |
| `slr54_gold_v1` | 50 | 50 | 100.0% |
| `podcast_source_reviewed_le30` | 50 | 50 | 100.0% |
| `youtube_caption_wordtimed_fixed120` | 50 | 50 | 100.0% |

Metric comparison:

| Model | TextGrids | Median overall LL | Median speech LL | Median phone duration deviation | Median SNR |
|---|---:|---:|---:|---:|---:|
| SLR54 5.3h aligner | 184 / 250 | -59.747 | -62.801 | 5.195 | 5.602 |
| Mixed 250 train | 250 / 250 | -52.808 | -56.696 | 5.959 | 4.705 |

Decision:

- The SLR54 5.3h model is a useful gold-read-speech smoke artifact, but it is
  not a sufficient baseline aligner for Chirp2, podcast source, and YouTube data.
- The mixed-source model proves that domain coverage matters and that the mixed
  corpus is alignable with our current dictionary/normalization path.
- The next serious baseline should be a larger mixed-source MFA model, not a
  pure SLR54 model.

Next gate:

1. Build a larger mixed validation/training slice, initially 5000 rows balanced
   across the five sources.
2. Train mixed-source MFA on the M4.
3. Align a held-out mixed validation slice.
4. Promote only if held-out TextGrid export is high and human spot checks pass.
5. Use reverse-G2P/dictionary repair for the residual OOV and phone-inventory
   issues, not as a substitute for mixed-domain acoustic training.

## Mixed-Source 5000 Training

Timestamp: 2026-05-16 23:58 NPT.

A balanced 5000-row mixed-source slice was built on the 4TB box:

- source root: `/home/cdjk/asr_mfa_outputs_20260516`
- slice: `/home/cdjk/asr_mfa_validation_slices_20260516/mixed_5000`
- per source: 1000 rows
- rows: 5000
- dictionary entries: 201763

Source composition:

| Source | Rows |
|---|---:|
| `chirp2_cer1` | 1000 |
| `chirp2_gt1_reviewed` | 1000 |
| `slr54_gold_v1` | 1000 |
| `podcast_source_reviewed_le30` | 1000 |
| `youtube_caption_wordtimed_fixed120` | 1000 |

The slice was copied to the M4 with audio symlinks dereferenced:

- M4 slice: `/Users/cdjk/asr_mfa_validation_slices_20260516/mixed_5000`
- copied size: 1.4 GB
- audio files: 5000
- lab files: 5000
- dictionary: `/Users/cdjk/asr_mfa_validation_slices_20260516/mixed_5000/nepali.dict`

MFA structural validation on the M4 passed:

- 5000 sound files
- 5000 text files
- 402 speakers
- 57355.304 seconds total duration, about 15.93 hours
- no sound read errors
- no missing transcripts
- no dictionary OOVs

M4 training was started in the background:

- train PID: `52117`
- poller PID: `52118`
- log: `/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/logs/train.log`
- poll: `/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/logs/poll.log`
- temp: `/Users/cdjk/asr_mfa_tmp/mixed_5000_train_m4`
- model target: `/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/nepali_mixed_5000_acoustic.zip`
- aligned target: `/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/aligned`

The existing M4 tmux session now has watch windows:

```bash
/opt/homebrew/bin/tmux attach -t mfa_slr54_m4
```

Relevant windows:

- `mixed5k`: live training log
- `mixed5kstat`: process/load/temp/TextGrid/model status

Completion update: 2026-05-17 09:42 NPT.

The mixed-source 5000-row MFA training finished successfully:

- wall time reported by MFA: 11536.748 seconds, about 3.20 hours
- model: `/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/nepali_mixed_5000_acoustic.zip`
- model size: 59 MB
- TextGrids exported: 4922 / 5000
- alignment analysis: `/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/aligned/alignment_analysis.csv`

Coverage by source:

| Source | Exported | Total | Coverage |
|---|---:|---:|---:|
| `chirp2_cer1` | 984 | 1000 | 98.4% |
| `chirp2_gt1_reviewed` | 947 | 1000 | 94.7% |
| `slr54_gold_v1` | 1000 | 1000 | 100.0% |
| `podcast_source_reviewed_le30` | 1000 | 1000 | 100.0% |
| `youtube_caption_wordtimed_fixed120` | 991 | 1000 | 99.1% |

Alignment-analysis summary:

| Metric | p10 | median | p90 |
|---|---:|---:|---:|
| `overall_log_likelihood` | -57.562 | -50.371 | -44.826 |
| `speech_log_likelihood` | -56.230 | -51.362 | -46.258 |
| `phone_duration_deviation` | 1.662 | 4.360 | 11.123 |
| `snr` | 2.694 | 6.904 | 12.667 |

Decision:

- This is the first useful mixed-domain MFA baseline.
- It is substantially stronger than the SLR54-only aligner for Chirp2,
  podcast source, and YouTube data.
- It is not yet a final release model because it was evaluated on the same
  slice it trained on. Next step is held-out mixed validation.

## Mixed-Source 1000 Held-Out Validation

Timestamp: 2026-05-17 09:54 NPT.

A held-out validation builder was added:

- `nepali-mfa-build-heldout-slice`

It excludes rows from one or more prior manifests before selecting validation
rows. This avoids evaluating the MFA model only on its own training slice.

A 1000-row held-out slice was built on the 4TB box:

- source root: `/home/cdjk/asr_mfa_outputs_20260516`
- slice: `/home/cdjk/asr_mfa_validation_slices_20260516/mixed_heldout_1000`
- exclude manifest: `/home/cdjk/asr_mfa_validation_slices_20260516/mixed_5000/mfa_manifest.jsonl`
- per source: 200 rows
- rows: 1000
- dictionary entries: 201763

The 4TB SSD had to be remounted before validation because the non-SLR audio
symlinks resolve through `/mnt/transcend4tb`:

```bash
sudo mount -t exfat -o uid=$(id -u),gid=$(id -g),umask=022 /dev/sda2 /mnt/transcend4tb
```

After remounting, all held-out audio resolved correctly:

- audio files: 1000
- lab files: 1000

The slice was copied to the M4:

- `/Users/cdjk/asr_mfa_validation_slices_20260516/mixed_heldout_1000`
- copied size: 306 MB

MFA structural validation on the M4 passed:

- 1000 sound files
- 1000 text files
- 155 speakers
- 11736.420 seconds total duration, about 3.26 hours
- no sound read errors
- no missing transcripts
- no dictionary OOVs

Held-out alignment was run with the mixed 5000 model:

- model: `/Users/cdjk/asr_mfa_training_20260516/mixed_5000_train_m4/nepali_mixed_5000_acoustic.zip`
- output: `/Users/cdjk/asr_mfa_training_20260517/mixed_heldout_1000_align_mixed5k/aligned`
- runtime: 128.902 seconds
- TextGrids exported: 934 / 1000
- alignment analysis: `/Users/cdjk/asr_mfa_training_20260517/mixed_heldout_1000_align_mixed5k/aligned/alignment_analysis.csv`

Coverage by source:

| Source | Exported | Total | Coverage |
|---|---:|---:|---:|
| `chirp2_cer1` | 189 | 200 | 94.5% |
| `chirp2_gt1_reviewed` | 159 | 200 | 79.5% |
| `slr54_gold_v1` | 200 | 200 | 100.0% |
| `podcast_source_reviewed_le30` | 199 | 200 | 99.5% |
| `youtube_caption_wordtimed_fixed120` | 187 | 200 | 93.5% |

Alignment-analysis summary:

| Metric | p10 | median | p90 |
|---|---:|---:|---:|
| `overall_log_likelihood` | -57.467 | -50.228 | -45.212 |
| `speech_log_likelihood` | -59.522 | -53.041 | -47.637 |
| `phone_duration_deviation` | 1.984 | 4.474 | 9.127 |
| `snr` | 2.054 | 5.617 | 11.764 |

Decision:

- The mixed 5000 model generalizes well to held-out `slr54`, `podcast_source`, and
  `youtube_caption_wordtimed_fixed120`.
- `chirp2_cer1` is acceptable but still has failures worth reviewing.
- `chirp2_gt1_reviewed` is not strong enough yet at 79.5% held-out TextGrid
  export and needs failure analysis before a release claim.
- Next work should focus on held-out failure audit, especially Chirp2 reviewed
  rows, before scaling to the full 509h corpus.

## 2026-05-17 12:22 NPT - Held-Out Failure Review Dashboard

A static dashboard builder was added:

- `nepali-mfa-build-failure-dashboard`

It combines the held-out manifest, MFA `alignment_analysis.csv`, and exported
TextGrid paths. It resolves copied M4 audio under the local `mfa_corpus` instead
of trusting stale 4TB absolute paths in the manifest.

The dashboard was built on the M4:

- dashboard: `/Users/cdjk/asr_mfa_training_20260517/mixed_heldout_1000_align_mixed5k/failure_dashboard`
- URL: `http://100.109.18.109:8770/`
- server PID file: `/Users/cdjk/asr_mfa_training_20260517/mixed_heldout_1000_align_mixed5k/failure_dashboard/server.pid`
- server URL file: `/Users/cdjk/asr_mfa_training_20260517/mixed_heldout_1000_align_mixed5k/failure_dashboard/server.url`

Review-pack contents:

| Bucket | Rows |
|---|---:|
| `missing_textgrid` | 66 |
| `high_phone_deviation` | 60 |
| `low_overall_ll` | 57 |
| `low_snr` | 47 |
| `low_speech_ll` | 18 |
| total unique review rows | 248 |

Review rows by source:

| Source | Rows |
|---|---:|
| `youtube_caption_wordtimed_fixed120` | 107 |
| `chirp2_gt1_reviewed` | 72 |
| `chirp2_cer1` | 37 |
| `podcast_source_reviewed_le30` | 22 |
| `slr54_gold_v1` | 10 |

Generated audit files:

- `failure_audit.jsonl`
- `failure_audit.csv`
- `summary.json`

Browser smoke check:

- page loads at `http://100.109.18.109:8770/`
- first FLAC audio metadata loads with duration `12.151973`
- left queue uses independent `overflow-y: auto` scrolling
- missing TextGrid rows show blank MFA metrics rather than misleading zeroes

Review objective:

1. Listen first to `missing_textgrid`, especially `chirp2_gt1_reviewed`.
2. Mark whether failures are bad text, bad audio, true alignment failure, or
   acceptable audio/text where the acoustic model is still weak.
3. Use the labels to decide whether to repair transcripts/dictionary, exclude a
   source subset, or train the next larger mixed-domain MFA model.

Quick non-listening audit:

- Missing TextGrid rows have median duration `17.50s`, p90 `19.29s`, max
  `19.96s`. This suggests length and dense speech may be part of the failure
  mode.
- Missing TextGrid rows by source: `chirp2_gt1_reviewed` 41,
  `youtube_caption_wordtimed_fixed120` 13, `chirp2_cer1` 11,
  `podcast_source_reviewed_le30` 1.
- Top duration-deviation outliers include YouTube ad/news fragments and one
  source 26.18s segment. These are good candidates for stricter duration,
  ad/music, or phrase-boundary filtering.
- Missing-row OOV words are mostly one-off lexical coverage issues rather than
  one repeated bad dictionary entry, so the immediate fix is review and better
  source/duration handling before broad dictionary surgery.

## 2026-05-17 12:34 NPT - Manual Review Signals And Repair Direction

Manual dashboard review found two concrete failure modes:

1. Some clips have background audio/music behind the speech. These may have
   correct text but lower MFA confidence or bad acoustic likelihood because the
   speech is not clean foreground speech.
2. At least one number/year mismatch was real: text had the plain cardinal
   phrase `एक हजार नौ सय ...`, while the speaker said the year-style phrase
   `उन्नाइस सय ...`.

Implementation updates:

- `nepali-mfa-build-failure-dashboard`
  - added `Number` label (`number_mismatch`)
  - added `BG audio` label (`background_audio`)
- `nepali_frontend/normalize/numbers.py`
  - added non-default `year_hundred_style(1995)` ->
    `उन्नाइस सय पन्चानब्बे`
  - added `normalize_numbers_in_text(..., year_style=True)` for explicit
    year-style digit expansion
  - added `rewrite_1900s_cardinal_phrase_to_year_style(...)` for reviewed
    ASR/MFA repair of already-spelled-out transcripts

Important constraint:

- The default text normalizer still keeps `1995` as plain cardinal
  `एक हजार नौ सय पन्चानब्बे`, because the same number can be a quantity,
  price, or count. Year-style rewrite must be context-aware or review-driven,
  not blindly applied to all text.

Focused tests passed:

```bash
python3 -m pytest tests/test_normalize.py -q
```

Result: `34 passed`.

Dashboard was regenerated on the M4 and the same server remains live:

- `http://100.109.18.109:8770/`

The current failure dashboard contains six rows with the exact phrase
`एक हजार नौ सय`, all from `slr54_gold_v1`, and all look like date/year contexts:

- `1e7b92d32d`: `एक हजार नौ सय पचहत्तर मा जुलाई`
- `54a29595ab`: `एक हजार नौ सय सतहत्तर मा`
- `ba5a720d6d`: `एक हजार नौ सय पन्चानब्बे मा भएको थियो`
- `ea5d4473ec`: `एक हजार नौ सय त्रियान्नब्बे साल मङ्सिरमा`
- `70e55adb35`: `एक हजार नौ सय अठहत्तर साल वैशाख`
- `ed0e44890f`: `एक हजार नौ सय पन्चानब्बे मा लेट`

These should be marked `Number` during review if audio confirms year-style
speech. After export, they are safe candidates for the reviewed year-style
rewrite rather than rejecting the audio.

## 2026-05-17 12:45 NPT - Seed Lexicon OOV Clarification

Manual review found that many displayed "OOV words" are valid Nepali words, for
example:

`बालुवाका`, `डाँडाहरु`, `गुम्बाहरु`, `बनाइएका`, `माटाका`,
`बताससँगै`, `बहेली`, `खेलिरहेका`, `पहेलपुर`, `उवाका`, `बारीहरु`

Verification against the held-out MFA dictionary showed every one of those
words is already present in:

- `/Users/cdjk/asr_mfa_validation_slices_20260516/mixed_heldout_1000/nepali.dict`

Conclusion:

- The dashboard field was not true final MFA dictionary OOV.
- It represented words missed by the seed Google/candidate lexicon before
  G2P fallback and merged dictionary coverage.
- These words should not be rejected just because they appeared in that list.

Implementation updates:

- The live dashboard now labels this section `Seed lexicon fallback`.
- `nepali-mfa-build-corpus` now separates future manifest provenance:
  - `seed_lexicon_oov_count` / `seed_lexicon_oov_words`
  - `g2p_fallback_count` / `g2p_fallback_words`
  - `unresolved_oov_count` / `unresolved_oov_words`
- Backward-compatible `oov_count` / `oov_words` remain, but they should be read
  as seed-lexicon misses for existing exports, not as automatic data errors.

## 2026-05-17 12:52 NPT - Background Audio Review Signal

Manual review of dashboard examples confirmed that several MFA-weak rows do
have background music or background audio. This means the held-out MFA failure
dashboard is surfacing a real acoustic complication, not random false alarms.

Interpretation:

- MFA is not a music classifier, but weak TextGrid export, low likelihood, high
  phone-duration deviation, or low SNR can indirectly flag speech that is harder
  to align.
- `BG audio` should not automatically reject a row for ASR training if the
  transcript is correct and speech is intelligible.
- `BG audio` is a risk marker for MFA/acoustic alignment training and for clean
  data tiers.

Decision rule for next data pass:

| Review label | ASR training | MFA/acoustic model training |
|---|---|---|
| `Keep` | keep | keep |
| `BG audio` with clear speech | keep as robust/noisy ASR tier | exclude or downweight for clean MFA tier |
| `BG audio` with hard-to-hear speech | reject or quarantine | reject |
| `Audio bad` | reject/quarantine | reject |
| `Number` | repair transcript, then keep | repair before align/train |
| `Align bad` with correct audio/text | keep for ASR candidate; retrain/retune MFA | do not use as clean MFA seed until alignment improves |

Next pipeline implication:

- Add explicit `review_label` and `quality_tier` fields when exported dashboard
  TSVs are merged back.
- Treat `BG audio` as a separate tier, not as generic bad data.
- For the clean MFA seed model, prefer `Keep` rows and reviewed number repairs.
- For ASR robustness training, allow `BG audio` rows if transcript is verified.

## 2026-05-17 14:22 NPT - Piper TTS Background-Audio Control

A controlled Piper TTS probe was run to test whether MFA metrics distinguish
clean speech from background music/noise:

- detailed report: `docs/mfa-background-audio-probe-2026-05-17.md`
- remote output: `/Users/cdjk/asr_mfa_training_20260517/asr_mfa_tts_probe_levels_20260517`
- rows: 100
- TextGrids exported: 100 / 100

Conditions:

- clean Piper TTS
- music bed throughout at `0.14`, `0.35`, and `0.60`
- music appended after speech

Main finding:

- SNR dropped monotonically as music-bed volume increased.
- Overall/speech likelihood did not degrade for music-bed cases in this
  synthetic control.
- Music appended after speech strongly degraded speech likelihood and overall
  likelihood.

Interpretation:

- MFA is not a standalone music classifier.
- MFA metrics can still surface background-audio risk.
- SNR is the clearest controlled signal for music bed.
- Low speech likelihood / low overall likelihood are better signals for
  untranscribed tails, hard cuts, or audio that cannot be explained by the
  transcript.

Pipeline decision:

- Keep manual `BG audio` as a separate label.
- For automatic filtering, use a metric combination rather than one threshold:
  SNR + speech likelihood + overall likelihood + phone-duration deviation,
  calibrated against dashboard labels.
