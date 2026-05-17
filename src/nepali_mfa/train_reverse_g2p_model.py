#!/usr/bin/env python3
"""Train a learned reverse-G2P model from phone lexicon TSVs."""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nepali_mfa import reverse_model as rm
from nepali_mfa.paths import require_lexicon_paths


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lexicon", type=Path, action="append", default=[])
    ap.add_argument("--training-corpus-jsonl", type=Path, action="append", default=[],
                    help="canonical rows from build_reverse_g2p_training_corpus.py")
    ap.add_argument("--profile", action="append", default=[],
                    help="only use these profile names from canonical corpus rows")
    ap.add_argument("--target", choices=["akshara", "char"], default="akshara",
                    help="target units for canonical corpus rows")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch-size", type=int, default=128)
    ap.add_argument("--embedding-dim", type=int, default=128)
    ap.add_argument("--hidden-dim", type=int, default=256)
    ap.add_argument("--dropout", type=float, default=0.1)
    ap.add_argument("--learning-rate", type=float, default=0.001)
    ap.add_argument("--dev-fraction", type=float, default=0.08)
    ap.add_argument("--test-fraction", type=float, default=0.02)
    ap.add_argument("--max-source-len", type=int, default=48)
    ap.add_argument("--max-target-len", type=int, default=32)
    ap.add_argument("--min-count-source", type=int, default=1)
    ap.add_argument("--min-count-target", type=int, default=1)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    ap.add_argument("--limit", type=int, default=0, help="debug limit after lexicon filtering")
    return ap.parse_args()


def iter_jsonl(path: Path):
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc


def load_canonical_pairs(
    paths: list[Path],
    *,
    profiles: set[str],
    target: str,
    max_source_len: int,
    max_target_len: int,
) -> list[rm.ReverseG2PPair]:
    pairs: list[rm.ReverseG2PPair] = []
    for path in paths:
        for row in iter_jsonl(path):
            profile = str(row.get("profile") or "").strip()
            if profiles and profile not in profiles:
                continue
            phones_value = row.get("canonical_phones") or row.get("phones") or []
            if isinstance(phones_value, str):
                phones = tuple(p for p in phones_value.split() if p)
            else:
                phones = tuple(str(p) for p in phones_value if str(p))
            spelling = str(row.get("text") or row.get("spelling") or "").strip()
            if target == "akshara":
                units_value = row.get("akshara_units") or []
                if isinstance(units_value, str):
                    target_units = tuple(u for u in units_value.split() if u)
                else:
                    target_units = tuple(str(u) for u in units_value if str(u))
            else:
                target_units = tuple(spelling)
            if not phones or not spelling or not target_units:
                continue
            if len(phones) > max_source_len or len(target_units) > max_target_len:
                continue
            pairs.append(
                rm.ReverseG2PPair(
                    phones=phones,
                    spelling=spelling,
                    normalized=str(row.get("normalized") or spelling).strip() or spelling,
                    source=str(row.get("source") or profile or "canonical_corpus"),
                    status=str(row.get("status") or row.get("forward_source") or "generated"),
                    target_units=target_units,
                )
            )
    return pairs


def choose_device(torch, requested: str):
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def pad_sequences(torch, seqs: list[list[int]], *, pad_id: int = 0):
    max_len = max(len(seq) for seq in seqs)
    out = torch.full((len(seqs), max_len), pad_id, dtype=torch.long)
    lengths = torch.tensor([len(seq) for seq in seqs], dtype=torch.long)
    for i, seq in enumerate(seqs):
        out[i, : len(seq)] = torch.tensor(seq, dtype=torch.long)
    return out, lengths


def make_batch(torch, pairs, source_vocab: rm.Vocab, target_vocab: rm.Vocab, device):
    src_ids = [source_vocab.encode(pair.phones, add_eos=True) for pair in pairs]
    target_chars = [list(pair.target_tokens) for pair in pairs]
    decoder_input = [
        [target_vocab.stoi[rm.BOS]] + target_vocab.encode(chars, add_eos=False)
        for chars in target_chars
    ]
    target_output = [target_vocab.encode(chars, add_eos=True) for chars in target_chars]
    src, src_lens = pad_sequences(torch, src_ids)
    dec_in, _ = pad_sequences(torch, decoder_input)
    tgt_out, _ = pad_sequences(torch, target_output)
    return src.to(device), src_lens.to(device), dec_in.to(device), tgt_out.to(device)


def batches(items, batch_size: int, *, shuffle: bool, seed: int):
    idx = list(range(len(items)))
    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(idx)
    for start in range(0, len(idx), batch_size):
        yield [items[i] for i in idx[start : start + batch_size]]


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(
                min(
                    prev[j] + 1,
                    cur[j - 1] + 1,
                    prev[j - 1] + (0 if ca == cb else 1),
                )
            )
        prev = cur
    return prev[-1]


def greedy_decode(torch, model, source_vocab, target_vocab, phones, device, max_len: int):
    src_ids = [source_vocab.encode(phones, add_eos=True)]
    src, src_lens = pad_sequences(torch, src_ids)
    src = src.to(device)
    src_lens = src_lens.to(device)
    with torch.no_grad():
        enc_out, hidden = model.encode(src, src_lens)
        src_mask = torch.arange(enc_out.size(1), device=device).unsqueeze(0) < src_lens.unsqueeze(1)
        prev = torch.tensor([target_vocab.stoi[rm.BOS]], dtype=torch.long, device=device)
        out: list[int] = []
        for _ in range(max_len):
            emb = model.tgt_embed(prev).unsqueeze(1)
            context = model.attend(enc_out, hidden, src_mask)
            dec_out, hidden = model.decoder(torch.cat([emb, context], dim=2), hidden)
            logits = model.out(torch.cat([dec_out.squeeze(1), context.squeeze(1)], dim=1))
            next_id = int(logits.argmax(dim=1).item())
            if target_vocab.tokens[next_id] == rm.EOS:
                break
            out.append(next_id)
            prev = torch.tensor([next_id], dtype=torch.long, device=device)
    return "".join(target_vocab.decode(out, stop_at_eos=True))


def evaluate(torch, model, pairs, source_vocab, target_vocab, device, batch_size: int, max_len: int):
    if not pairs:
        return {"loss": None, "exact": None, "char_error_rate": None, "rows": 0}
    import torch.nn.functional as F

    model.eval()
    total_loss = 0.0
    total_tokens = 0
    exact = 0
    char_edits = 0
    char_total = 0
    with torch.no_grad():
        for batch in batches(pairs, batch_size, shuffle=False, seed=0):
            src, src_lens, dec_in, tgt_out = make_batch(torch, batch, source_vocab, target_vocab, device)
            logits = model(src, src_lens, dec_in)
            loss = F.cross_entropy(
                logits.reshape(-1, logits.size(-1)),
                tgt_out.reshape(-1),
                ignore_index=0,
                reduction="sum",
            )
            tokens = int((tgt_out != 0).sum().item())
            total_loss += float(loss.item())
            total_tokens += tokens
        for pair in pairs[: min(len(pairs), 1000)]:
            pred = greedy_decode(
                torch, model, source_vocab, target_vocab, pair.phones, device, max_len=max_len
            )
            exact += int(pred == pair.spelling)
            char_edits += edit_distance(pred, pair.spelling)
            char_total += len(pair.spelling)
    sampled = min(len(pairs), 1000)
    return {
        "loss": total_loss / max(total_tokens, 1),
        "exact": exact / max(sampled, 1),
        "char_error_rate": char_edits / max(char_total, 1),
        "rows": len(pairs),
        "decoded_rows": sampled,
    }


def main() -> int:
    args = parse_args()
    torch, _, _, _ = rm._require_torch()
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    device = choose_device(torch, args.device)

    if args.training_corpus_jsonl:
        lexicons: list[Path] = []
        pairs = load_canonical_pairs(
            args.training_corpus_jsonl,
            profiles=set(args.profile),
            target=args.target,
            max_source_len=args.max_source_len,
            max_target_len=args.max_target_len,
        )
    else:
        lexicons = require_lexicon_paths(args.lexicon)
        pairs = rm.iter_lexicon_pairs(
            lexicons,
            max_source_len=args.max_source_len,
            max_target_len=args.max_target_len,
        )
    if args.limit:
        pairs = pairs[: args.limit]
    if not pairs:
        raise SystemExit("no training pairs found")

    train, dev, test = rm.split_pairs(
        pairs,
        dev_fraction=args.dev_fraction,
        test_fraction=args.test_fraction,
        seed=args.seed,
    )
    source_vocab, target_vocab = rm.build_vocabs(
        train,
        min_count_source=args.min_count_source,
        min_count_target=args.min_count_target,
    )
    model_config = rm.ReverseG2PModelConfig(
        source_vocab_size=len(source_vocab),
        target_vocab_size=len(target_vocab),
        embedding_dim=args.embedding_dim,
        hidden_dim=args.hidden_dim,
        dropout=args.dropout,
    )
    training_config = rm.ReverseG2PTrainingConfig(
        seed=args.seed,
        dev_fraction=args.dev_fraction,
        test_fraction=args.test_fraction,
        batch_size=args.batch_size,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        max_source_len=args.max_source_len,
        max_target_len=args.max_target_len,
        min_count_source=args.min_count_source,
        min_count_target=args.min_count_target,
    )
    model = rm.make_model(model_config).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    criterion = torch.nn.CrossEntropyLoss(ignore_index=0)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "lexicons": [str(p) for p in lexicons] if not args.training_corpus_jsonl else [],
        "training_corpus_jsonl": [str(p) for p in args.training_corpus_jsonl],
        "profiles": args.profile,
        "target": args.target if args.training_corpus_jsonl else "char",
        "device": str(device),
        "pairs": len(pairs),
        "train_rows": len(train),
        "dev_rows": len(dev),
        "test_rows": len(test),
        "source_vocab_size": len(source_vocab),
        "target_vocab_size": len(target_vocab),
    }
    print(json.dumps(metadata, ensure_ascii=False), flush=True)

    history = []
    best_dev = float("inf")
    best_path = args.out_dir / "checkpoint.pt"
    for epoch in range(1, args.epochs + 1):
        started = time.time()
        model.train()
        total_loss = 0.0
        total_tokens = 0
        for batch in batches(train, args.batch_size, shuffle=True, seed=args.seed + epoch):
            src, src_lens, dec_in, tgt_out = make_batch(torch, batch, source_vocab, target_vocab, device)
            optimizer.zero_grad()
            logits = model(src, src_lens, dec_in)
            loss = criterion(logits.reshape(-1, logits.size(-1)), tgt_out.reshape(-1))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            tokens = int((tgt_out != 0).sum().item())
            total_loss += float(loss.item()) * tokens
            total_tokens += tokens

        train_loss = total_loss / max(total_tokens, 1)
        dev_metrics = evaluate(
            torch, model, dev, source_vocab, target_vocab, device, args.batch_size, args.max_target_len
        )
        epoch_metrics = {
            "epoch": epoch,
            "train_loss": train_loss,
            "dev": dev_metrics,
            "seconds": round(time.time() - started, 3),
        }
        history.append(epoch_metrics)
        print(json.dumps(epoch_metrics, ensure_ascii=False), flush=True)
        dev_loss = dev_metrics["loss"] if dev_metrics["loss"] is not None else train_loss
        if dev_loss < best_dev:
            best_dev = float(dev_loss)
            metrics = {"metadata": metadata, "history": history, "best_epoch": epoch}
            torch.save(
                rm.checkpoint_payload(
                    model=model,
                    model_config=model_config,
                    training_config=training_config,
                    source_vocab=source_vocab,
                    target_vocab=target_vocab,
                    metrics=metrics,
                ),
                best_path,
            )

    checkpoint = torch.load(best_path, map_location=device)
    model.load_state_dict(checkpoint["state_dict"])
    final_metrics = dict(checkpoint["metrics"])
    final_metrics["test"] = evaluate(
        torch, model, test, source_vocab, target_vocab, device, args.batch_size, args.max_target_len
    )
    final_metrics["checkpoint"] = str(best_path)
    rm.save_metrics_json(args.out_dir / "metrics.json", final_metrics)
    print(json.dumps({"saved": str(best_path), "metrics": str(args.out_dir / "metrics.json")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
