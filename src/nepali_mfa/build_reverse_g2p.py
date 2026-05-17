#!/usr/bin/env python3
"""CLI wrapper around the Nepali MFA reverse-G2P index."""

from __future__ import annotations

import argparse
from pathlib import Path

from nepali_mfa import reverse as reverse_g2p


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phones", help="space-separated phone sequence")
    ap.add_argument("--top-k", type=int, default=10, help="max candidates to emit")
    ap.add_argument("--lexicon", type=Path, action="append", default=[], help="phone lexicon TSV")
    ap.add_argument("--strict", action="store_true", default=True,
                    help="validate phones against project phone inventory")
    ap.add_argument("--no-strict", dest="strict", action="store_false",
                    help="skip phone-inventory validation")
    ap.add_argument("--export", type=Path,
                    help="optional reverse-index JSON export path")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    index = reverse_g2p.load_reverse_index(
        lexicon=args.lexicon or None,
        strict=args.strict,
    )
    if args.export:
        total = reverse_g2p.export_reverse_index(index, args.export)
        print(f"index_entries\t{total}")
    if not args.phones:
        return 0
    cands = reverse_g2p.reverse_lookup(args.phones, index=index, top_k=args.top_k)
    if not cands:
        print("[]")
        return 1
    for c in cands:
        print(f"\t".join([
            c.spelling,
            c.normalized,
            " ".join(c.phones),
            c.source,
            c.status,
            f"{c.rank_score:.2f}",
        ]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
