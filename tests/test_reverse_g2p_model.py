from __future__ import annotations

import importlib.util

import pytest

from nepali_mfa import reverse_model as rm


def test_iter_lexicon_pairs_and_vocabs(tmp_path):
    lexicon = tmp_path / "lexicon.tsv"
    lexicon.write_text(
        "\n".join(
            [
                "text\tnormalized\tphones\tsource\tstatus",
                "अ\tअ\tax\ttest\tgold",
                "आज\tआज\taa . j\ttest\tgold",
                "decoder\tdecoder\tdx i\ttest\tcandidate",
                "",
            ]
        ),
        encoding="utf-8",
    )

    pairs = rm.iter_lexicon_pairs([lexicon])

    assert [p.spelling for p in pairs] == ["अ", "आज"]
    assert pairs[1].phones == ("aa", ".", "j")

    source_vocab, target_vocab = rm.build_vocabs(pairs)
    assert "aa" in source_vocab.stoi
    assert "ज" in target_vocab.stoi
    assert target_vocab.decode(target_vocab.encode("आज", add_eos=True)) == ["आ", "ज"]


def test_split_pairs_is_stable():
    pairs = [
        rm.ReverseG2PPair((f"p{i}",), f"क{i}", f"क{i}", "test", "candidate")
        for i in range(50)
    ]

    first = rm.split_pairs(pairs, dev_fraction=0.1, test_fraction=0.1, seed=7)
    second = rm.split_pairs(pairs, dev_fraction=0.1, test_fraction=0.1, seed=7)

    assert [[p.spelling for p in part] for part in first] == [
        [p.spelling for p in part] for part in second
    ]
    assert sum(len(part) for part in first) == 50


@pytest.mark.skipif(importlib.util.find_spec("torch") is None, reason="PyTorch not installed")
def test_seq2seq_forward_shape():
    import torch

    pairs = [
        rm.ReverseG2PPair(("ax",), "अ", "अ", "test", "gold"),
        rm.ReverseG2PPair(("aa", ".", "j"), "आज", "आज", "test", "gold"),
    ]
    source_vocab, target_vocab = rm.build_vocabs(pairs)
    config = rm.ReverseG2PModelConfig(
        source_vocab_size=len(source_vocab),
        target_vocab_size=len(target_vocab),
        embedding_dim=8,
        hidden_dim=12,
        dropout=0.0,
    )
    model = rm.make_model(config)
    src = torch.tensor(
        [
            source_vocab.encode(("ax",), add_eos=True) + [0, 0],
            source_vocab.encode(("aa", ".", "j"), add_eos=True),
        ],
        dtype=torch.long,
    )
    src_lens = torch.tensor([2, 4], dtype=torch.long)
    dec_in = torch.tensor(
        [
            [target_vocab.stoi[rm.BOS], target_vocab.stoi["अ"], 0],
            [target_vocab.stoi[rm.BOS], target_vocab.stoi["आ"], target_vocab.stoi["ज"]],
        ],
        dtype=torch.long,
    )

    logits = model(src, src_lens, dec_in)

    assert logits.shape == (2, 3, len(target_vocab))
