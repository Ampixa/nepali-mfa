#!/usr/bin/env python3
"""Build a small MFA validation slice from exported MFA bundles."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export-root", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--per-source", type=int, default=50)
    ap.add_argument("--source", action="append", default=[])
    ap.add_argument("--dict-source", default="slr54_gold_v1")
    ap.add_argument("--replace", action="store_true")
    return ap.parse_args()


def link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if src.is_symlink():
        dst.symlink_to(src.resolve())
    else:
        dst.symlink_to(src)


def load_rows(path: Path, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if len(rows) >= limit:
                break
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def merge_dictionaries(paths: list[Path], out_path: Path) -> int:
    entries: dict[str, str] = {}
    for path in paths:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    continue
                word, phones = parts
                entries.setdefault(word, phones)
    with out_path.open("w", encoding="utf-8") as f:
        for word in sorted(entries):
            f.write(f"{word} {entries[word]}\n")
    return len(entries)


def main() -> int:
    args = parse_args()
    if args.out_dir.exists():
        if not args.replace:
            raise SystemExit(f"output exists; use --replace: {args.out_dir}")
        shutil.rmtree(args.out_dir)
    args.out_dir.mkdir(parents=True)

    mfa_root = args.export_root / "mfa"
    sources = args.source or [
        p.name for p in sorted(mfa_root.iterdir())
        if (p / "mfa_manifest.jsonl").exists()
    ]

    combined: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for source in sources:
        source_dir = mfa_root / source
        rows = load_rows(source_dir / "mfa_manifest.jsonl", args.per_source)
        counts[source] = len(rows)
        for row in rows:
            audio_src = Path(row["audio_mfa"])
            lab_src = Path(row["lab"])
            speaker = audio_src.parent.name
            utt_id = audio_src.stem
            dst_dir = args.out_dir / "mfa_corpus" / source / speaker
            audio_dst = dst_dir / f"{utt_id}{audio_src.suffix}"
            lab_dst = dst_dir / f"{utt_id}.lab"
            link_or_copy(audio_src, audio_dst)
            link_or_copy(lab_src, lab_dst)
            combined.append({
                **row,
                "slice_source": source,
                "audio_mfa": str(audio_dst),
                "lab": str(lab_dst),
            })

    dict_paths = [mfa_root / source / "nepali.dict" for source in sources]
    dict_entries = merge_dictionaries(dict_paths, args.out_dir / "nepali.dict")

    with (args.out_dir / "mfa_manifest.jsonl").open("w", encoding="utf-8") as f:
        for row in combined:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "export_root": str(args.export_root),
        "out_dir": str(args.out_dir),
        "per_source": args.per_source,
        "sources": counts,
        "rows": len(combined),
        "dict_entries": dict_entries,
        "dictionary": str(args.out_dir / "nepali.dict"),
        "mfa_corpus": str(args.out_dir / "mfa_corpus"),
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.out_dir / "README.md").write_text(
        "# MFA validation slice\n\n"
        "Run after installing Montreal Forced Aligner:\n\n"
        "```bash\n"
        "mfa validate mfa_corpus nepali.dict <acoustic_model>\n"
        "mfa align mfa_corpus nepali.dict <acoustic_model> aligned\n"
        "```\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
