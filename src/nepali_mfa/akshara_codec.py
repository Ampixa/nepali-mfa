"""Akshara-aware Nepali text codec.

NeMo char-CTC tokenizers operate on single Unicode code points. Nepali
aksharas are often multi-codepoint grapheme clusters, so this codec maps each
Devanagari akshara unit to one private-use Unicode character for training.
Predictions can then be decoded back to normal Devanagari text.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from nepali_frontend.g2p import akshara as ak
from nepali_frontend.normalize import normalize_text
from nepali_frontend.tokenize.script import tokenize


PunctuationMode = Literal["drop", "keep"]
PUA_START = 0xE000
PUA_END = 0xF8FF
PUA_SUPPLEMENT_START = 0xF0000
SPACE = " "


def _append_space(units: list[str]) -> None:
    if units and units[-1] != SPACE:
        units.append(SPACE)


def text_to_units(
    text: str,
    *,
    punctuation: PunctuationMode = "drop",
    lowercase_latin: bool = True,
    normalize: bool = True,
) -> list[str]:
    """Convert transcript text to logical ASR units.

    Devanagari runs become akshara units. Latin runs become character units so
    English code-mix remains representable in the same CTC model.
    """
    if punctuation not in {"drop", "keep"}:
        raise ValueError("punctuation must be 'drop' or 'keep'")

    text = unicodedata.normalize("NFC", text or "")
    if normalize:
        text = normalize_text(text)

    units: list[str] = []
    for token in tokenize(text):
        if token.kind == "space":
            _append_space(units)
            continue

        if token.kind == "devanagari":
            for item in ak.parse(token.text):
                if item.type == "punct":
                    if punctuation == "keep":
                        units.append(item.text)
                    continue
                units.append(item.text)
            continue

        if token.kind == "latin":
            value = token.text.lower() if lowercase_latin else token.text
            units.extend(value)
            continue

        if token.kind == "digit":
            units.extend(token.text)
            continue

        if token.kind in {"sentence_end", "question", "exclamation", "punct"}:
            if punctuation == "keep":
                units.append(token.text)
            continue

        if punctuation == "keep":
            units.append(token.text)

    while units and units[-1] == SPACE:
        units.pop()
    return units


def _needs_private_char(unit: str) -> bool:
    if unit == SPACE:
        return False
    return not (len(unit) == 1 and unit.isascii())


def _private_char(index: int) -> str:
    codepoint = PUA_START + index
    if codepoint <= PUA_END:
        return chr(codepoint)
    return chr(PUA_SUPPLEMENT_START + (index - (PUA_END - PUA_START + 1)))


def _unit_sort_key(unit: str) -> tuple[int, str]:
    if unit == SPACE:
        return (0, unit)
    if not _needs_private_char(unit):
        return (1, unit)
    return (2, unit)


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class AksharaCtcCodec:
    """Bidirectional mapping between transcript units and CTC label chars."""

    unit_to_char: dict[str, str]
    punctuation: PunctuationMode = "drop"
    lowercase_latin: bool = True

    @classmethod
    def from_texts(
        cls,
        texts: Iterable[str],
        *,
        punctuation: PunctuationMode = "drop",
        lowercase_latin: bool = True,
        normalize: bool = True,
    ) -> "AksharaCtcCodec":
        units: set[str] = set()
        for text in texts:
            units.update(
                text_to_units(
                    text,
                    punctuation=punctuation,
                    lowercase_latin=lowercase_latin,
                    normalize=normalize,
                )
            )
        return cls.from_units(
            units,
            punctuation=punctuation,
            lowercase_latin=lowercase_latin,
        )

    @classmethod
    def from_units(
        cls,
        units: Iterable[str],
        *,
        punctuation: PunctuationMode = "drop",
        lowercase_latin: bool = True,
    ) -> "AksharaCtcCodec":
        ordered = sorted(set(units), key=_unit_sort_key)
        private_index = 0
        mapping: dict[str, str] = {}
        for unit in ordered:
            if not unit:
                continue
            if _needs_private_char(unit):
                mapping[unit] = _private_char(private_index)
                private_index += 1
            else:
                mapping[unit] = unit
        return cls(mapping, punctuation=punctuation, lowercase_latin=lowercase_latin)

    @property
    def char_to_unit(self) -> dict[str, str]:
        return {char: unit for unit, char in self.unit_to_char.items()}

    @property
    def labels(self) -> list[str]:
        return [self.unit_to_char[unit] for unit in sorted(self.unit_to_char, key=_unit_sort_key)]

    def encode_units(self, units: Iterable[str]) -> str:
        chars: list[str] = []
        for unit in units:
            try:
                chars.append(self.unit_to_char[unit])
            except KeyError as exc:
                raise KeyError(f"unit {unit!r} is not in the codec inventory") from exc
        return "".join(chars)

    def encode_text(self, text: str, *, normalize: bool = True) -> str:
        return self.encode_units(
            text_to_units(
                text,
                punctuation=self.punctuation,
                lowercase_latin=self.lowercase_latin,
                normalize=normalize,
            )
        )

    def decode_text(self, encoded: str) -> str:
        units = [self.char_to_unit.get(char, char) for char in encoded or ""]
        return _collapse_spaces("".join(units))

    def to_json_obj(self) -> dict[str, object]:
        return {
            "version": 1,
            "description": "Nepali akshara CTC codec; Devanagari units map to Unicode private-use characters.",
            "punctuation": self.punctuation,
            "lowercase_latin": self.lowercase_latin,
            "unit_to_char": self.unit_to_char,
            "labels": self.labels,
            "label_codepoints": [f"U+{ord(label):04X}" for label in self.labels],
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_json_obj(), f, ensure_ascii=False, indent=2)
            f.write("\n")

    @classmethod
    def read(cls, path: Path) -> "AksharaCtcCodec":
        with path.open(encoding="utf-8") as f:
            obj = json.load(f)
        return cls(
            unit_to_char={str(k): str(v) for k, v in obj["unit_to_char"].items()},
            punctuation=obj.get("punctuation", "drop"),
            lowercase_latin=bool(obj.get("lowercase_latin", True)),
        )
