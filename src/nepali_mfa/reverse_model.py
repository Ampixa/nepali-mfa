"""Learned reverse-G2P model utilities.

This module implements a small phone-token to Devanagari-character seq2seq
model. It is intentionally separate from ``reverse.py``: the existing reverse
index is exact lexicon lookup, while this module can generalize to phone
sequences not present in the lexicon.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

PAD = "<pad>"
BOS = "<bos>"
EOS = "<eos>"
UNK = "<unk>"
SPECIALS = [PAD, BOS, EOS, UNK]


@dataclass(frozen=True)
class ReverseG2PPair:
    """A supervised phone-sequence to spelling training row."""

    phones: tuple[str, ...]
    spelling: str
    normalized: str
    source: str
    status: str
    target_units: tuple[str, ...] = field(default_factory=tuple)

    @property
    def target_tokens(self) -> tuple[str, ...]:
        if self.target_units:
            return self.target_units
        return tuple(self.spelling)


@dataclass
class ReverseG2PModelConfig:
    source_vocab_size: int
    target_vocab_size: int
    embedding_dim: int = 128
    hidden_dim: int = 256
    dropout: float = 0.1


@dataclass
class ReverseG2PTrainingConfig:
    seed: int = 13
    dev_fraction: float = 0.08
    test_fraction: float = 0.02
    batch_size: int = 128
    epochs: int = 20
    learning_rate: float = 0.001
    max_source_len: int = 48
    max_target_len: int = 32
    min_count_source: int = 1
    min_count_target: int = 1


class Vocab:
    """Token vocabulary with JSON-serializable storage."""

    def __init__(self, tokens: list[str]):
        if tokens[: len(SPECIALS)] != SPECIALS:
            raise ValueError("vocab must start with special tokens")
        self.tokens = tokens
        self.stoi = {token: i for i, token in enumerate(tokens)}

    @classmethod
    def build(cls, sequences: Iterable[Iterable[str]], *, min_count: int = 1) -> "Vocab":
        counts: dict[str, int] = {}
        for seq in sequences:
            for token in seq:
                counts[token] = counts.get(token, 0) + 1
        regular = sorted(token for token, count in counts.items() if count >= min_count)
        return cls(SPECIALS + [token for token in regular if token not in SPECIALS])

    def encode(self, tokens: Iterable[str], *, add_eos: bool = False) -> list[int]:
        ids = [self.stoi.get(token, self.stoi[UNK]) for token in tokens]
        if add_eos:
            ids.append(self.stoi[EOS])
        return ids

    def decode(self, ids: Iterable[int], *, stop_at_eos: bool = True) -> list[str]:
        out: list[str] = []
        for idx in ids:
            if idx < 0 or idx >= len(self.tokens):
                token = UNK
            else:
                token = self.tokens[idx]
            if stop_at_eos and token == EOS:
                break
            if token not in SPECIALS:
                out.append(token)
        return out

    def to_json(self) -> list[str]:
        return list(self.tokens)

    @classmethod
    def from_json(cls, payload: list[str]) -> "Vocab":
        return cls(list(payload))

    def __len__(self) -> int:
        return len(self.tokens)


def _has_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" or "\ua8e0" <= ch <= "\ua8ff" for ch in text)


def iter_lexicon_pairs(
    lexicon_paths: Iterable[Path],
    *,
    devanagari_only: bool = True,
    max_source_len: int = 48,
    max_target_len: int = 32,
    dedupe: bool = True,
) -> list[ReverseG2PPair]:
    """Read TSV lexicons into supervised reverse-G2P examples."""

    seen: set[tuple[tuple[str, ...], str]] = set()
    pairs: list[ReverseG2PPair] = []
    for path in lexicon_paths:
        with path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                spelling = str(row.get("text") or "").strip()
                phones = tuple(p for p in str(row.get("phones") or "").split() if p)
                if not spelling or not phones:
                    continue
                if devanagari_only and not _has_devanagari(spelling):
                    continue
                if len(phones) > max_source_len or len(spelling) > max_target_len:
                    continue
                key = (phones, spelling)
                if dedupe and key in seen:
                    continue
                seen.add(key)
                pairs.append(
                    ReverseG2PPair(
                        phones=phones,
                        spelling=spelling,
                        normalized=str(row.get("normalized") or spelling).strip() or spelling,
                        source=str(row.get("source") or "").strip(),
                        status=str(row.get("status") or "").strip() or "candidate",
                    )
                )
    return pairs


def split_pairs(
    pairs: Iterable[ReverseG2PPair],
    *,
    dev_fraction: float,
    test_fraction: float,
    seed: int,
) -> tuple[list[ReverseG2PPair], list[ReverseG2PPair], list[ReverseG2PPair]]:
    """Stable hash split by spelling plus phones."""

    train: list[ReverseG2PPair] = []
    dev: list[ReverseG2PPair] = []
    test: list[ReverseG2PPair] = []
    dev_cut = int(dev_fraction * 10000)
    test_cut = dev_cut + int(test_fraction * 10000)
    for pair in pairs:
        key = f"{seed}\t{' '.join(pair.phones)}\t{pair.spelling}".encode("utf-8")
        bucket = int(hashlib.sha1(key).hexdigest()[:8], 16) % 10000
        if bucket < dev_cut:
            dev.append(pair)
        elif bucket < test_cut:
            test.append(pair)
        else:
            train.append(pair)
    return train, dev, test


def build_vocabs(
    pairs: Iterable[ReverseG2PPair],
    *,
    min_count_source: int = 1,
    min_count_target: int = 1,
) -> tuple[Vocab, Vocab]:
    pair_list = list(pairs)
    source_vocab = Vocab.build((pair.phones for pair in pair_list), min_count=min_count_source)
    target_vocab = Vocab.build((pair.target_tokens for pair in pair_list), min_count=min_count_target)
    return source_vocab, target_vocab


def _require_torch():
    try:
        import torch
        from torch import nn
        from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence
    except ImportError as exc:
        raise RuntimeError("learned reverse G2P requires PyTorch") from exc
    return torch, nn, pack_padded_sequence, pad_packed_sequence


def make_model(config: ReverseG2PModelConfig):
    """Create the PyTorch seq2seq model."""

    torch, nn, pack_padded_sequence, pad_packed_sequence = _require_torch()

    class ReverseG2PSeq2Seq(nn.Module):
        def __init__(self, cfg: ReverseG2PModelConfig):
            super().__init__()
            self.cfg = cfg
            self.src_embed = nn.Embedding(cfg.source_vocab_size, cfg.embedding_dim, padding_idx=0)
            self.tgt_embed = nn.Embedding(cfg.target_vocab_size, cfg.embedding_dim, padding_idx=0)
            self.encoder = nn.GRU(
                cfg.embedding_dim,
                cfg.hidden_dim,
                batch_first=True,
                bidirectional=True,
            )
            enc_dim = cfg.hidden_dim * 2
            self.bridge = nn.Linear(enc_dim, cfg.hidden_dim)
            self.attn_query = nn.Linear(cfg.hidden_dim, enc_dim, bias=False)
            self.decoder = nn.GRU(cfg.embedding_dim + enc_dim, cfg.hidden_dim, batch_first=True)
            self.dropout = nn.Dropout(cfg.dropout)
            self.out = nn.Linear(cfg.hidden_dim + enc_dim, cfg.target_vocab_size)

        def encode(self, src, src_lens):
            emb = self.dropout(self.src_embed(src))
            packed = pack_padded_sequence(
                emb, src_lens.cpu(), batch_first=True, enforce_sorted=False
            )
            packed_out, hidden = self.encoder(packed)
            enc_out, _ = pad_packed_sequence(packed_out, batch_first=True)
            final = torch.cat([hidden[-2], hidden[-1]], dim=1)
            dec_hidden = torch.tanh(self.bridge(final)).unsqueeze(0)
            return enc_out, dec_hidden

        def attend(self, enc_out, hidden, src_mask):
            query = self.attn_query(hidden[-1]).unsqueeze(2)
            scores = torch.bmm(enc_out, query).squeeze(2)
            scores = scores.masked_fill(~src_mask, -1e9)
            weights = torch.softmax(scores, dim=1)
            context = torch.bmm(weights.unsqueeze(1), enc_out)
            return context

        def forward(self, src, src_lens, decoder_input):
            enc_out, hidden = self.encode(src, src_lens)
            src_mask = torch.arange(enc_out.size(1), device=src.device).unsqueeze(0) < src_lens.unsqueeze(1)
            logits = []
            for step in range(decoder_input.size(1)):
                prev = decoder_input[:, step]
                emb = self.dropout(self.tgt_embed(prev)).unsqueeze(1)
                context = self.attend(enc_out, hidden, src_mask)
                dec_in = torch.cat([emb, context], dim=2)
                dec_out, hidden = self.decoder(dec_in, hidden)
                step_logits = self.out(torch.cat([dec_out.squeeze(1), context.squeeze(1)], dim=1))
                logits.append(step_logits)
            return torch.stack(logits, dim=1)

    return ReverseG2PSeq2Seq(config)


def checkpoint_payload(
    *,
    model,
    model_config: ReverseG2PModelConfig,
    training_config: ReverseG2PTrainingConfig,
    source_vocab: Vocab,
    target_vocab: Vocab,
    metrics: dict,
) -> dict:
    return {
        "format": "nepali_reverse_g2p_seq2seq_v1",
        "model_config": asdict(model_config),
        "training_config": asdict(training_config),
        "source_vocab": source_vocab.to_json(),
        "target_vocab": target_vocab.to_json(),
        "metrics": metrics,
        "state_dict": model.state_dict(),
    }


def save_metrics_json(path: Path, metrics: dict) -> None:
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
