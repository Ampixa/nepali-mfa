import importlib.util

import pytest

from nepali_mfa import build_reverse_g2p_training_corpus as mod


def test_build_rows_spoken_profile():
    words = [
        mod.SourceWord(
            text="छ",
            normalized="छ",
            raw_phones="tsh ax",
            source="test",
            status="gold",
        )
    ]

    rows = mod.build_rows(
        words,
        profiles=["spoken_nepali_linguistic"],
    )

    by_profile = {row.profile: row for row in rows}
    assert by_profile["spoken_nepali_linguistic"].canonical_phones == ["tsh", "ax"]


@pytest.mark.skipif(importlib.util.find_spec("real_nepali") is None, reason="optional profile package not installed")
def test_build_rows_keeps_optional_real_nepali_profile_separate():
    words = [mod.SourceWord(text="छ", normalized="छ", raw_phones="tsh ax", source="test", status="gold")]

    rows = mod.build_rows(words, profiles=["spoken_nepali_linguistic", "real_nepali_tts"])

    by_profile = {row.profile: row for row in rows}
    assert by_profile["real_nepali_tts"].canonical_phones == ["chh", "ax"]
    assert by_profile["real_nepali_tts"].base_phones == ["tsh", "ax"]
    assert "clear_standard_affricates" in by_profile["real_nepali_tts"].trace_rules


def test_iter_lexicon_words_filters_latin(tmp_path):
    path = tmp_path / "lexicon.tsv"
    path.write_text(
        "\n".join(
            [
                "text\tnormalized\tphones\tsource\tstatus",
                "आज\tआज\taa . dz ax\ttest\tcandidate",
                "decoder\tdecoder\tdx i\ttest\tcandidate",
                "",
            ]
        ),
        encoding="utf-8",
    )

    words = list(mod.iter_lexicon_words([path]))

    assert [word.text for word in words] == ["आज"]
    assert words[0].raw_phones == "aa . dz ax"


def test_writers_emit_jsonl_and_tsv(tmp_path):
    rows = mod.build_rows(
        [mod.SourceWord(text="आज", normalized="आज", raw_phones="aa . dz ax")],
        profiles=["spoken_nepali_linguistic"],
    )
    out_jsonl = tmp_path / "rows.jsonl"
    out_tsv = tmp_path / "rows.tsv"

    assert mod.write_jsonl(out_jsonl, rows) == 1
    assert mod.write_tsv(out_tsv, rows) == 1

    assert '"profile": "spoken_nepali_linguistic"' in out_jsonl.read_text(encoding="utf-8")
    assert "canonical_phones" in out_tsv.read_text(encoding="utf-8").splitlines()[0]
