#!/usr/bin/env python3
"""Decode phone sequences with a learned reverse-G2P checkpoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nepali_mfa import reverse_model as rm


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--phones", action="append", default=[], help="space-separated phone sequence")
    ap.add_argument("--phones-file", type=Path, help="one space-separated phone sequence per line")
    ap.add_argument("--beam-size", type=int, default=5)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--max-len", type=int, default=32)
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    ap.add_argument("--jsonl", action="store_true")
    return ap.parse_args()


def choose_device(torch, requested: str):
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def load_checkpoint(torch, path: Path, device):
    try:
        return torch.load(path, map_location=device, weights_only=False)
    except TypeError:
        return torch.load(path, map_location=device)


def decode_beam(torch, model, source_vocab, target_vocab, phones, device, *, beam_size: int, max_len: int):
    src_ids = [source_vocab.encode(phones, add_eos=True)]
    src = torch.tensor(src_ids, dtype=torch.long, device=device)
    src_lens = torch.tensor([len(src_ids[0])], dtype=torch.long, device=device)
    model.eval()
    with torch.no_grad():
        enc_out, hidden = model.encode(src, src_lens)
        src_mask = torch.arange(enc_out.size(1), device=device).unsqueeze(0) < src_lens.unsqueeze(1)
        beams = [([], hidden, 0.0)]
        completed: list[tuple[list[int], float]] = []
        for _ in range(max_len):
            next_beams = []
            for ids, hyp_hidden, score in beams:
                prev_id = target_vocab.stoi[rm.BOS] if not ids else ids[-1]
                prev = torch.tensor([prev_id], dtype=torch.long, device=device)
                emb = model.tgt_embed(prev).unsqueeze(1)
                context = model.attend(enc_out, hyp_hidden, src_mask)
                dec_out, next_hidden = model.decoder(torch.cat([emb, context], dim=2), hyp_hidden)
                logits = model.out(torch.cat([dec_out.squeeze(1), context.squeeze(1)], dim=1))
                log_probs = torch.log_softmax(logits, dim=1).squeeze(0)
                values, indices = torch.topk(log_probs, k=min(beam_size, log_probs.numel()))
                for value, idx in zip(values.tolist(), indices.tolist(), strict=False):
                    token = target_vocab.tokens[idx]
                    next_score = score + float(value)
                    if token == rm.EOS:
                        completed.append((ids, next_score))
                    elif token not in (rm.PAD, rm.BOS):
                        next_beams.append((ids + [idx], next_hidden.clone(), next_score))
            if not next_beams:
                break
            next_beams.sort(key=lambda item: item[2] / max(len(item[0]), 1), reverse=True)
            beams = next_beams[:beam_size]
        completed.extend((ids, score) for ids, _, score in beams)

    ranked = []
    seen: set[str] = set()
    for ids, score in sorted(completed, key=lambda item: item[1] / max(len(item[0]), 1), reverse=True):
        spelling = "".join(target_vocab.decode(ids, stop_at_eos=True))
        if not spelling or spelling in seen:
            continue
        seen.add(spelling)
        ranked.append(
            {
                "spelling": spelling,
                "score": score,
                "avg_logprob": score / max(len(ids), 1),
            }
        )
    return ranked


def iter_inputs(args: argparse.Namespace) -> list[str]:
    rows = list(args.phones)
    if args.phones_file:
        rows.extend(
            line.strip()
            for line in args.phones_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return rows


def main() -> int:
    args = parse_args()
    torch, _, _, _ = rm._require_torch()
    device = choose_device(torch, args.device)
    checkpoint = load_checkpoint(torch, args.checkpoint, device)
    source_vocab = rm.Vocab.from_json(checkpoint["source_vocab"])
    target_vocab = rm.Vocab.from_json(checkpoint["target_vocab"])
    model_config = rm.ReverseG2PModelConfig(**checkpoint["model_config"])
    model = rm.make_model(model_config).to(device)
    model.load_state_dict(checkpoint["state_dict"])

    inputs = iter_inputs(args)
    if not inputs:
        raise SystemExit("provide --phones or --phones-file")
    for phone_text in inputs:
        phones = tuple(p for p in phone_text.split() if p)
        candidates = decode_beam(
            torch,
            model,
            source_vocab,
            target_vocab,
            phones,
            device,
            beam_size=args.beam_size,
            max_len=args.max_len,
        )[: args.top_k]
        if args.jsonl:
            print(json.dumps({"phones": phone_text, "candidates": candidates}, ensure_ascii=False))
        else:
            for rank, cand in enumerate(candidates, start=1):
                print(
                    "\t".join(
                        [
                            phone_text,
                            str(rank),
                            cand["spelling"],
                            f"{cand['avg_logprob']:.4f}",
                        ]
                    )
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

