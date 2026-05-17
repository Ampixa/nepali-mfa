# Learned Reverse G2P (2026-05-16)

## What this adds

The existing reverse path is an exact lexicon index:

- `nepali_frontend/g2p/reverse.py`
- `nepali-mfa-build-reverse-g2p`

That path only returns spellings for phone sequences already present in the
lexicon. The learned path trains a phone-token to Devanagari-character seq2seq
model so unseen phone sequences can receive spelling candidates.

## Files

- `nepali_frontend/g2p/reverse_model.py`
  - lexicon pair loading
  - stable train/dev/test split
  - vocab serialization
  - PyTorch GRU encoder-decoder with attention
- `nepali-mfa-train-reverse-g2p`
  - trains from TSV lexicon data
  - writes `checkpoint.pt` and `metrics.json`
- `nepali-mfa-predict-reverse-g2p`
  - loads checkpoint
  - emits beam-search spelling candidates

## Train

First build the canonical, profile-tagged training corpus:

```bash
nepali-mfa-build-reverse-g2p-corpus \
  --profile spoken_nepali_linguistic \
  --out-jsonl artifacts/reverse_g2p_corpus_v1/rows.jsonl \
  --out-tsv artifacts/reverse_g2p_corpus_v1/rows.tsv \
  --summary-json artifacts/reverse_g2p_corpus_v1/summary.json
```

Then train from the profile you want. For the linguistics/Wikipedia-aligned
model:

```bash
nepali-mfa-train-reverse-g2p \
  --training-corpus-jsonl artifacts/reverse_g2p_corpus_v1/rows.jsonl \
  --profile spoken_nepali_linguistic \
  --target akshara \
  --out-dir artifacts/reverse_g2p_linguistic_v1 \
  --epochs 40 \
  --batch-size 128 \
  --embedding-dim 128 \
  --hidden-dim 256 \
  --device auto
```

Do not train the `real_nepali_tts` affricate-rewrite profile for this reverse
G2P target. It is a TTS acoustic/product profile and intentionally diverges
from the Wikipedia/Khatiwada-style affricate labels.

If a future TTS-only repair pass needs reverse lookup over `ch/chh/j/jh`, build
that as a separate experimental artifact, not as the default reverse-G2P model.

For a quick smoke run:

```bash
nepali-mfa-build-reverse-g2p-corpus \
  --profile spoken_nepali_linguistic \
  --out-jsonl /tmp/reverse_g2p_corpus_smoke.jsonl

nepali-mfa-train-reverse-g2p \
  --training-corpus-jsonl /tmp/reverse_g2p_corpus_smoke.jsonl \
  --profile spoken_nepali_linguistic \
  --target akshara \
  --out-dir /tmp/reverse_g2p_smoke \
  --epochs 1 \
  --batch-size 16 \
  --embedding-dim 16 \
  --hidden-dim 24 \
  --limit 96 \
  --device cpu
```

## Predict

```bash
nepali-mfa-predict-reverse-g2p \
  --checkpoint artifacts/reverse_g2p_linguistic_v1/checkpoint.pt \
  --phones "aa . j" \
  --beam-size 8 \
  --top-k 5
```

TSV output columns:

- phones
- rank
- spelling
- average log probability

Use `--jsonl` for structured output.

## Intended use

Use the exact reverse index first when a phone sequence is covered by the
lexicon. Use the learned model for OOV phone sequences, then rerank or review the
candidates before promotion into MFA/TTS data.
