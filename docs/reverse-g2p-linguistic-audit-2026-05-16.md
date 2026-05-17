# Reverse G2P Linguistic Audit (2026-05-16)

## Bottom Line

A learned reverse-G2P model should not be trained as a generic
`phones -> Devanagari` seq2seq task over raw Google lexicon phones.

It must be trained against the forward-G2P profile that matches the target
analysis:

1. `spoken_nepali_linguistic`
   - matches the project phonology notes, Khatiwada/Regmi-style analysis, and
     Wikipedia/Wiktionary-style IPA conventions as closely as the current data
     allows.
   - affricates are `ts/tsh/dz/dzh`.

The `real_nepali_tts` affricate rewrite profile should not be used for the
default reverse-G2P target because it intentionally diverges from
Wikipedia/Khatiwada-style affricate labels.

## Source Consensus

| Issue | Linguistics / Papers | Wikipedia / Wiktionary Direction | Project Requirement |
|---|---|---|---|
| Affricates | Khatiwada 2009 and Clements/Khatiwada-style work support alveolar affricates. Regmi 2025 uses the same broad direction. | Wikipedia Nepali phonology lists alveolar affricates and gives schwa examples with `t͡s/d͡z` style IPA. | Default reverse G2P emits and consumes `ts/tsh/dz/dzh`. Do not use `ch/chh/j/jh` for this target. |
| Sibilants | Khatiwada and Regmi collapse `श/ष/स` to one phoneme /s/ in ordinary Nepali. | Wikipedia Help/Nepali-style conventions generally support a single /s/ with Sanskritized exceptions. | Default reverse model must know that one phone `s` maps to multiple spellings. Candidate ranking must use lexicon/frequency, not assume one spelling. |
| Nasals | Khatiwada: three core nasals; Regmi explicitly says `ञ/ण` are pronounced as `n/n` in Nepali, with contextual nasalization/assimilation. | Wikipedia lists debated Sanskrit/loan consonants separately; core system does not require a five-nasal default. | Default reverse model must treat `n` as many-to-one orthographically: `न/ण/ञ` may all be candidates depending on word/source. |
| Vowel length | Khatiwada: written long/short `i/u` are not contrastive in spoken Nepali, aside from allophonic length from `/h/` deletion. | Wikipedia Nepali phonology follows no broad spoken length contrast; Help:IPA may preserve some orthographic length in transcription conventions. | Default reverse model must emit ranked spelling candidates for `i` and `u`, not assume `ि` vs `ी` or `ु` vs `ू` from phones alone. |
| Diphthongs | Pokharel/Khatiwada discuss a 10-diphthong analysis; Google has a practical 7 oral + 6 nasalized label set. | Wikipedia Nepali phonology lists Pokharel-style diphthongs. | Keep the project's current 13-label engineering inventory for model inputs, but test against Wikipedia/Pokharel examples. |
| Schwa | Regmi confirms inherent `अ` is often not pronounced final/medial in compounds. Wikipedia gives concrete Nepali schwa-retention rules. | Wikipedia Nepali phonology and schwa-deletion page are directly useful for final schwa and postposition behavior. | Training corpus must be generated from our rule path plus lexicon overrides, not copied from raw orthography or Hindi rules. |
| Aspiration | Clements/Khatiwada and Schwarz/Sonderegger/Goad-style findings support preserving aspirated/breathy contrasts. | Wikipedia preserves aspirated stop/affricate contrasts. | Reverse model must not collapse `kh/gh/tsh/dzh/...`; these remain distinct source tokens. |

## What This Means For Reverse G2P

Reverse G2P is inherently one-to-many because the forward G2P intentionally
collapses orthographic contrasts:

- `श/ष/स -> s`
- `ञ/ण/न -> n`
- written `ि/ी -> i`
- written `ु/ू -> u`
- several spellings can share the same schwa-deleted surface form

Therefore the learned model must be a candidate generator, not an oracle.

Required production stack:

```text
input phone sequence
  -> exact reverse index under spoken_nepali_linguistic
  -> learned profile-conditioned decoder if no strong exact hit
  -> forward-G2P roundtrip check under spoken_nepali_linguistic
  -> frequency/source/rule-trace rerank
  -> review queue before lexicon promotion
```

## Model Architecture Requirement

The current Python/PyTorch seq2seq scaffold is a useful harness, but not the
final design.

For the serious model:

- source tokens: profile-specific phone tokens;
- target units: akshara/orthographic units, not raw Unicode characters;
- decoder: constrained beam search over valid Devanagari/akshara units;
- reranker: forward-G2P distance + source priority + word frequency;
- output: top-k candidates with scores and roundtrip diagnostics.

Recommended outputs:

```json
{
  "phones": "aa . dz ax",
  "profile": "spoken_nepali_linguistic",
  "candidates": [
    {
      "spelling": "आज",
      "model_score": -1.2,
      "roundtrip_phones": "aa . dz ax",
      "roundtrip_distance": 0,
      "source": "lexicon_or_model",
      "needs_review": false
    }
  ]
}
```

## Training Corpus Recipe

Do not train directly from raw lexicon `phones` only.

Generate profile-tagged canonical rows:

```text
word
profile
canonical_phones
akshara_units
forward_source
trace_rules
source_priority
frequency
```

Sources, in priority order:

1. reviewed/gold lexicon;
2. candidate lexicon after canonical forward G2P regeneration;
3. high-frequency Devanagari word list with rule-generated phones;
4. Wikipedia/Wiktionary comparison/stress cases;
5. ASR/MFA repaired OOVs after human review.

Any non-linguistic/acoustic profile must be generated as a separate experimental
corpus and kept out of the default reverse-G2P metrics.

## Evaluation Recipe

Report more than exact seq2seq accuracy:

- exact reverse-index coverage;
- learned top-1/top-3/top-5 accuracy;
- hybrid top-k accuracy;
- valid-akshara output rate;
- forward roundtrip phone edit distance;
- source-priority agreement;
- stress-set accuracy for:
  - affricates;
  - sibilant collapse;
  - three-nasal policy;
  - written vowel-length collapse;
  - schwa retention/deletion;
  - diphthong examples from Wikipedia/Pokharel;
  - aspiration and voiced aspirates.

## Decision

Train and evaluate the canonical `spoken_nepali_linguistic` reverse model as the
default. Do not use the current `real_nepali_tts` affricate-rewrite profile for
this Wikipedia-aligned reverse-G2P work.
