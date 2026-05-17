"""Shared path helpers for CLI defaults."""

from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def default_lexicon_paths() -> list[Path]:
    """Return candidate lexicon paths from env or common local layouts.

    Production jobs should pass ``--lexicon`` explicitly. The fallback exists so
    local development can reuse the sibling text-frontend checkout.
    """

    env_value = os.environ.get("NEPALI_MFA_LEXICON", "").strip()
    if env_value:
        return [Path(item).expanduser() for item in env_value.split(os.pathsep) if item]

    candidates = [
        REPO_ROOT / "data" / "frontend" / "candidates_lexicon.tsv",
        REPO_ROOT.parent / "g2p" / "data" / "frontend" / "candidates_lexicon.tsv",
    ]
    return [path for path in candidates if path.exists()]


def require_lexicon_paths(paths: list[Path] | None = None) -> list[Path]:
    resolved = list(paths or default_lexicon_paths())
    if not resolved:
        raise FileNotFoundError(
            "No Nepali lexicon found. Pass --lexicon or set NEPALI_MFA_LEXICON "
            "to one or more TSV files separated by the OS path separator."
        )
    return resolved
