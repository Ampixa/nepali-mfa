#!/usr/bin/env python3
"""Build a static dashboard for MFA held-out failure and risk review."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MFA Failure Review</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <div class="shell">
    <aside class="queue">
      <header class="queue-head">
        <div>
          <h1>MFA Review</h1>
          <p id="summary"></p>
        </div>
        <button id="exportTsv" class="button">Export TSV</button>
      </header>
      <div class="filters">
        <button class="status active" data-status="all">All</button>
        <button class="status" data-status="open">Open</button>
        <button class="status" data-status="done">Done</button>
        <button class="status" data-status="bad">Bad</button>
      </div>
      <div class="filters" id="bucketFilters"></div>
      <div class="filters" id="sourceFilters"></div>
      <div id="list" class="sample-list"></div>
    </aside>
    <main class="review">
      <section class="topbar">
        <div>
          <p id="eyebrow" class="eyebrow"></p>
          <h2 id="title"></h2>
        </div>
        <div class="nav">
          <button id="prev" class="button">Prev</button>
          <button id="next" class="button">Next</button>
        </div>
      </section>
      <section class="audio-row">
        <audio id="audio" controls preload="metadata"></audio>
        <label class="speed">Speed
          <select id="speed">
            <option value="0.8">0.8x</option>
            <option value="1" selected>1.0x</option>
            <option value="1.15">1.15x</option>
            <option value="1.3">1.3x</option>
          </select>
        </label>
      </section>
      <section id="metrics" class="metrics"></section>
      <section class="text-panel">
        <article class="transcript">
          <header>Transcript</header>
          <p id="transcript"></p>
        </article>
        <details id="rawBlock">
          <summary>Raw text</summary>
          <p id="rawText"></p>
        </details>
        <article>
          <header>Seed lexicon fallback</header>
          <p id="fallbackWords"></p>
        </article>
      </section>
      <section class="label-panel">
        <div id="labels" class="labels"></div>
        <textarea id="notes" placeholder="Notes"></textarea>
      </section>
    </main>
  </div>
  <script src="data.js"></script>
  <script src="app.js"></script>
</body>
</html>
"""


APP_JS = r"""const LABELS = [
  ["keep", "Keep"],
  ["minor", "Minor"],
  ["text_bad", "Text bad"],
  ["number_mismatch", "Number"],
  ["background_audio", "BG audio"],
  ["audio_bad", "Audio bad"],
  ["alignment_bad", "Align bad"],
  ["unsure", "Unsure"],
];

const STORE_PREFIX = `mfa_failure_review:${window.REVIEW_META.dataset}:`;
let rows = window.REVIEW_ROWS || [];
let filtered = [];
let current = 0;
let statusFilter = "all";
let activeBuckets = new Set();
let activeSources = new Set();

const $ = (id) => document.getElementById(id);

function key(row) {
  return `${STORE_PREFIX}${row.id}`;
}

function review(row) {
  try {
    return JSON.parse(localStorage.getItem(key(row)) || "{}");
  } catch {
    return {};
  }
}

function save(row, patch) {
  localStorage.setItem(key(row), JSON.stringify({
    ...review(row),
    ...patch,
    updated_at: new Date().toISOString(),
  }));
}

function badLabel(label) {
  return ["text_bad", "number_mismatch", "background_audio", "audio_bad", "alignment_bad"].includes(label);
}

function escapeHtml(text) {
  return String(text || "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[ch]));
}

function fmt(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "";
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  return n.toFixed(digits);
}

function initFilters() {
  const buckets = [...new Set(rows.map((row) => row.issue_bucket))].sort();
  const sources = [...new Set(rows.map((row) => row.slice_source || row.source))].sort();
  activeBuckets = new Set(buckets);
  activeSources = new Set(sources);
  $("bucketFilters").innerHTML = buckets.map((bucket) =>
    `<button class="chip active" data-kind="bucket" data-value="${escapeHtml(bucket)}">${escapeHtml(bucket)}</button>`
  ).join("");
  $("sourceFilters").innerHTML = sources.map((source) =>
    `<button class="chip active" data-kind="source" data-value="${escapeHtml(source)}">${escapeHtml(source)}</button>`
  ).join("");
  document.querySelectorAll(".chip").forEach((button) => {
    button.addEventListener("click", () => {
      const set = button.dataset.kind === "bucket" ? activeBuckets : activeSources;
      const value = button.dataset.value;
      if (set.has(value)) {
        set.delete(value);
        button.classList.remove("active");
      } else {
        set.add(value);
        button.classList.add("active");
      }
      current = 0;
      applyFilters();
    });
  });
}

function applyFilters() {
  filtered = rows.filter((row) => {
    if (!activeBuckets.has(row.issue_bucket)) return false;
    if (!activeSources.has(row.slice_source || row.source)) return false;
    const label = review(row).label || "";
    if (statusFilter === "open") return !label;
    if (statusFilter === "done") return Boolean(label);
    if (statusFilter === "bad") return badLabel(label);
    return true;
  });
  current = Math.min(current, Math.max(filtered.length - 1, 0));
  renderList();
  renderCurrent();
}

function renderSummary() {
  const labels = rows.map((row) => review(row).label || "");
  const done = labels.filter(Boolean).length;
  const bad = labels.filter(badLabel).length;
  $("summary").textContent = `${done}/${rows.length} reviewed, ${bad} bad, ${filtered.length} visible`;
}

function renderList() {
  renderSummary();
  $("list").innerHTML = filtered.map((row, idx) => {
    const r = review(row);
    const label = r.label || "open";
    const active = idx === current ? " active" : "";
    const bad = badLabel(r.label || "") ? " bad" : "";
    const failed = row.has_textgrid ? "" : " failed";
    return `<button class="sample${active}${failed}" data-index="${idx}">
      <span class="sample-title">${escapeHtml(row.id)}</span>
      <span class="sample-text">${escapeHtml(row.transcript)}</span>
      <span class="sample-meta">
        <span>${escapeHtml(row.issue_bucket)}</span>
        <span>${escapeHtml(row.slice_source || row.source)}</span>
        <span>${fmt(row.duration_sec, 1)}s</span>
        <span class="pill${r.label ? " done" : ""}${bad}">${escapeHtml(label)}</span>
      </span>
    </button>`;
  }).join("");
  document.querySelectorAll(".sample").forEach((button) => {
    button.addEventListener("click", () => {
      current = Number(button.dataset.index);
      renderList();
      renderCurrent();
    });
  });
}

function metric(label, value, digits = 2) {
  return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value === "" ? "" : fmt(value, digits))}</strong></div>`;
}

function textMetric(label, value) {
  return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value || "")}</strong></div>`;
}

function renderCurrent() {
  if (!filtered.length) {
    $("title").textContent = "No samples";
    $("eyebrow").textContent = "";
    $("audio").removeAttribute("src");
    $("metrics").innerHTML = "";
    $("transcript").textContent = "";
    $("rawText").textContent = "";
    $("fallbackWords").textContent = "";
    $("labels").innerHTML = "";
    $("notes").value = "";
    return;
  }
  const row = filtered[current];
  const r = review(row);
  $("title").textContent = row.id;
  $("eyebrow").textContent = `${row.issue_bucket} | ${row.has_textgrid ? "TextGrid exported" : "missing TextGrid"}`;
  $("audio").src = row.audio;
  $("audio").playbackRate = Number($("speed").value);
  $("metrics").innerHTML = [
    textMetric("Source", row.slice_source || row.source),
    textMetric("TextGrid", row.has_textgrid ? "yes" : "no"),
    metric("Duration", row.duration_sec, 2),
    metric("Overall LL", row.overall_log_likelihood, 2),
    metric("Speech LL", row.speech_log_likelihood, 2),
    metric("Phone dev", row.phone_duration_deviation, 2),
    metric("SNR", row.snr, 2),
    textMetric("Seed fallback", row.oov_count),
  ].join("");
  $("transcript").textContent = row.transcript || "";
  $("rawText").textContent = row.text_raw || "";
  $("fallbackWords").textContent = (row.oov_words || []).join(", ") || "none";
  $("labels").innerHTML = LABELS.map(([value, label], index) =>
    `<button class="label${r.label === value ? " active" : ""}" data-label="${value}">${index + 1}. ${label}</button>`
  ).join("");
  $("notes").value = r.notes || "";
  document.querySelectorAll(".label").forEach((button) => {
    button.addEventListener("click", () => {
      save(row, {label: button.dataset.label, notes: $("notes").value || ""});
      next();
    });
  });
}

function next() {
  if (!filtered.length) return;
  current = Math.min(current + 1, filtered.length - 1);
  renderList();
  renderCurrent();
}

function prev() {
  if (!filtered.length) return;
  current = Math.max(current - 1, 0);
  renderList();
  renderCurrent();
}

function exportTsv() {
  const header = ["id", "slice_source", "issue_bucket", "has_textgrid", "duration_sec", "overall_log_likelihood", "speech_log_likelihood", "phone_duration_deviation", "snr", "label", "notes", "transcript"];
  const lines = [header.join("\t")];
  rows.forEach((row) => {
    const r = review(row);
    lines.push([
      row.id,
      row.slice_source || row.source || "",
      row.issue_bucket || "",
      row.has_textgrid ? "1" : "0",
      row.duration_sec || "",
      row.overall_log_likelihood || "",
      row.speech_log_likelihood || "",
      row.phone_duration_deviation || "",
      row.snr || "",
      r.label || "",
      (r.notes || "").replaceAll("\t", " ").replaceAll("\n", " "),
      (row.transcript || "").replaceAll("\t", " ").replaceAll("\n", " "),
    ].join("\t"));
  });
  const blob = new Blob([lines.join("\n") + "\n"], {type: "text/tab-separated-values;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${window.REVIEW_META.dataset}_mfa_review.tsv`;
  a.click();
  URL.revokeObjectURL(url);
}

function init() {
  initFilters();
  document.querySelectorAll(".status").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".status").forEach((b) => b.classList.remove("active"));
      button.classList.add("active");
      statusFilter = button.dataset.status;
      current = 0;
      applyFilters();
    });
  });
  $("next").addEventListener("click", next);
  $("prev").addEventListener("click", prev);
  $("exportTsv").addEventListener("click", exportTsv);
  $("speed").addEventListener("change", () => {
    $("audio").playbackRate = Number($("speed").value);
  });
  $("notes").addEventListener("input", () => {
    if (filtered.length) save(filtered[current], {notes: $("notes").value});
  });
  document.addEventListener("keydown", (event) => {
    if (event.target.tagName === "TEXTAREA" || event.target.tagName === "INPUT") return;
    if (event.key === "ArrowRight") next();
    if (event.key === "ArrowLeft") prev();
    if (event.key === " ") {
      event.preventDefault();
      const player = $("audio");
      player.paused ? player.play() : player.pause();
    }
    const idx = Number(event.key) - 1;
    if (idx >= 0 && idx < LABELS.length && filtered.length) {
      save(filtered[current], {label: LABELS[idx][0], notes: $("notes").value || ""});
      next();
    }
  });
  applyFilters();
}

init();
"""


STYLES_CSS = """* {
  box-sizing: border-box;
}

html,
body {
  height: 100%;
}

body {
  margin: 0;
  background: #f5f6f8;
  color: #111827;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  letter-spacing: 0;
  overflow: hidden;
}

button,
select,
textarea {
  font: inherit;
}

button {
  border: 1px solid #c8ced8;
  background: #fff;
  color: #111827;
  cursor: pointer;
}

button:hover {
  border-color: #6b7280;
}

.shell {
  display: grid;
  grid-template-columns: minmax(350px, 430px) minmax(0, 1fr);
  height: 100vh;
  min-height: 0;
}

.queue {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100vh;
  background: #fff;
  border-right: 1px solid #d8dde6;
  overflow: hidden;
}

.queue-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid #e5e7eb;
}

h1,
h2,
p {
  margin: 0;
}

h1 {
  font-size: 20px;
  line-height: 1.2;
}

h2 {
  font-size: 20px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.queue-head p,
.eyebrow,
.sample-meta,
.metric span {
  color: #5f6877;
  font-size: 13px;
}

.button,
.status,
.chip,
.label {
  min-height: 36px;
  border-radius: 6px;
  padding: 0 11px;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 16px 0;
}

.filters:last-of-type {
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.status.active,
.chip.active,
.label.active {
  background: #0f766e;
  border-color: #0f766e;
  color: #fff;
}

.sample-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 8px;
  scrollbar-width: thin;
  scrollbar-color: #9ca3af #eef0f4;
}

.sample-list::-webkit-scrollbar,
.text-panel::-webkit-scrollbar {
  width: 10px;
}

.sample-list::-webkit-scrollbar-track,
.text-panel::-webkit-scrollbar-track {
  background: #eef0f4;
}

.sample-list::-webkit-scrollbar-thumb,
.text-panel::-webkit-scrollbar-thumb {
  background: #9ca3af;
  border: 2px solid #eef0f4;
  border-radius: 999px;
}

.sample {
  width: 100%;
  display: grid;
  gap: 6px;
  text-align: left;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 10px;
}

.sample.active {
  background: #eaf7f5;
  border-color: #8fc8bf;
}

.sample.failed {
  border-left: 4px solid #b91c1c;
}

.sample-title {
  font-weight: 700;
  overflow-wrap: anywhere;
}

.sample-text {
  color: #374151;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sample-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.pill {
  display: inline-flex;
  min-height: 22px;
  align-items: center;
  padding: 0 8px;
  border-radius: 999px;
  background: #e5e7eb;
  color: #374151;
}

.pill.done {
  background: #d1fae5;
  color: #065f46;
}

.pill.bad {
  background: #fee2e2;
  color: #991b1b;
}

.review {
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr) auto;
  gap: 16px;
  height: 100vh;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  padding: 22px;
}

.topbar,
.audio-row,
.label-panel {
  display: flex;
  gap: 14px;
  align-items: center;
  justify-content: space-between;
}

.nav,
.labels {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

audio {
  width: min(780px, 100%);
}

.speed {
  display: flex;
  gap: 8px;
  align-items: center;
  color: #4b5563;
}

select {
  height: 36px;
  border: 1px solid #c8ced8;
  border-radius: 6px;
  background: #fff;
  padding: 0 8px;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 8px;
}

.metric {
  min-width: 0;
  display: grid;
  gap: 4px;
  background: #fff;
  border: 1px solid #d8dde6;
  border-radius: 6px;
  padding: 10px;
}

.metric strong {
  font-size: 14px;
  overflow-wrap: anywhere;
}

.text-panel {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  display: grid;
  align-content: start;
  gap: 12px;
  scrollbar-width: thin;
  scrollbar-color: #9ca3af #eef0f4;
}

.text-panel article,
.text-panel details {
  background: #fff;
  border: 1px solid #d8dde6;
  border-left: 4px solid #0f766e;
  border-radius: 6px;
  padding: 14px;
}

.text-panel details {
  border-left-color: #9ca3af;
}

.text-panel header,
.text-panel summary {
  font-weight: 700;
  color: #374151;
  margin-bottom: 8px;
}

.text-panel p {
  font-size: 21px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.label-panel {
  align-items: stretch;
}

.labels {
  flex: 1;
}

textarea {
  width: min(420px, 38vw);
  min-height: 58px;
  resize: vertical;
  border: 1px solid #c8ced8;
  border-radius: 6px;
  padding: 10px;
}

@media (max-width: 900px) {
  body {
    overflow: auto;
  }

  .shell {
    grid-template-columns: 1fr;
    height: auto;
  }

  .queue {
    height: 42vh;
    min-height: 42vh;
    border-right: 0;
    border-bottom: 1px solid #d8dde6;
  }

  .review {
    height: auto;
    min-height: 58vh;
    overflow: visible;
  }

  .topbar,
  .audio-row,
  .label-panel {
    display: block;
  }

  .nav,
  .speed,
  .labels {
    margin-top: 12px;
  }

  .metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  textarea {
    width: 100%;
    margin-top: 12px;
  }
}
"""


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            if isinstance(row, dict):
                yield row


def read_analysis(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row.get("file") or ""
            if key:
                rows[key] = row
    return rows


def read_textgrid_stems(aligned_dir: Path) -> set[str]:
    return {p.stem for p in aligned_dir.rglob("*.TextGrid")}


def fnum(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_audio(row: dict[str, Any], manifest_dir: Path) -> Path | None:
    candidates = [
        row.get("audio_mfa"),
        row.get("audio_src"),
        row.get("audio_filepath"),
        row.get("audio_path"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate))
        if path.exists():
            return path

    row_id = str(row.get("id") or "")
    if not row_id:
        return None
    corpus = manifest_dir / "mfa_corpus"
    for ext in (".wav", ".flac", ".mp3", ".m4a", ".ogg"):
        hits = list(corpus.rglob(f"{row_id}{ext}"))
        if hits:
            return hits[0]
    return None


def safe_name(row_id: str, audio: Path) -> str:
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in row_id)[:100]
    return f"{stem}{audio.suffix.lower() or '.wav'}"


def link_or_copy_audio(audio: Path, audio_dir: Path, copy_audio: bool) -> str:
    audio_dir.mkdir(parents=True, exist_ok=True)
    dest = audio_dir / safe_name(audio.stem, audio)
    if dest.exists() or dest.is_symlink():
        return f"audio/{dest.name}"
    if copy_audio:
        shutil.copy2(audio, dest)
    else:
        rel = os.path.relpath(audio, start=audio_dir)
        dest.symlink_to(rel)
    return f"audio/{dest.name}"


def metric_value(analysis: dict[str, Any], key: str) -> float | None:
    return fnum(analysis.get(key))


def duration(row: dict[str, Any], analysis: dict[str, Any]) -> float:
    manifest_duration = fnum(row.get("duration_sec"), 0.0) or 0.0
    if manifest_duration > 0:
        return manifest_duration
    begin = fnum(analysis.get("begin"), 0.0) or 0.0
    end = fnum(analysis.get("end"), 0.0) or 0.0
    return max(0.0, end - begin)


def select_review_rows(
    records: list[dict[str, Any]],
    worst_per_metric: int,
    include_all_failures: bool,
) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}

    if include_all_failures:
        for row in records:
            if not row["has_textgrid"]:
                row = dict(row)
                row["issue_bucket"] = "missing_textgrid"
                selected[row["id"]] = row

    metric_specs = [
        ("phone_duration_deviation", True, "high_phone_deviation"),
        ("overall_log_likelihood", False, "low_overall_ll"),
        ("speech_log_likelihood", False, "low_speech_ll"),
        ("snr", False, "low_snr"),
    ]
    for metric, descending, bucket in metric_specs:
        candidates = [row for row in records if row.get(metric) is not None]
        candidates.sort(key=lambda row: row[metric], reverse=descending)
        for base in candidates[:worst_per_metric]:
            row = dict(base)
            row["issue_bucket"] = bucket
            selected.setdefault(row["id"], row)

    return sorted(
        selected.values(),
        key=lambda row: (
            row["issue_bucket"] != "missing_textgrid",
            row["issue_bucket"],
            row.get("slice_source") or row.get("source") or "",
            row["id"],
        ),
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "id",
        "slice_source",
        "source",
        "issue_bucket",
        "has_textgrid",
        "duration_sec",
        "overall_log_likelihood",
        "speech_log_likelihood",
        "phone_duration_deviation",
        "snr",
        "oov_count",
        "oov_words",
        "transcript",
        "audio_source",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["oov_words"] = " ".join(row.get("oov_words") or [])
            writer.writerow(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--analysis-csv", type=Path, required=True)
    parser.add_argument("--aligned-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--dataset", default="mfa_heldout_review")
    parser.add_argument("--worst-per-metric", type=int, default=60)
    parser.add_argument("--copy-audio", action="store_true")
    parser.add_argument("--no-all-failures", action="store_true")
    args = parser.parse_args()

    manifest_dir = args.manifest.parent
    analysis_rows = read_analysis(args.analysis_csv)
    textgrid_stems = read_textgrid_stems(args.aligned_dir)
    records: list[dict[str, Any]] = []

    for row in iter_jsonl(args.manifest):
        row_id = str(row.get("id") or "")
        if not row_id:
            continue
        analysis = analysis_rows.get(row_id, {})
        audio = resolve_audio(row, manifest_dir)
        if audio is None:
            continue
        record = {
            "id": row_id,
            "source": row.get("source") or "",
            "slice_source": row.get("slice_source") or row.get("source") or "",
            "audio_source": str(audio),
            "transcript": row.get("transcript") or row.get("text") or "",
            "text_raw": row.get("text_raw") or row.get("transcript") or "",
            "speaker_id": row.get("speaker_id") or "",
            "oov_count": int(row.get("oov_count") or 0),
            "oov_words": row.get("oov_words") or [],
            "duration_sec": round(duration(row, analysis), 4),
            "has_textgrid": row_id in textgrid_stems,
            "overall_log_likelihood": metric_value(analysis, "overall_log_likelihood"),
            "speech_log_likelihood": metric_value(analysis, "speech_log_likelihood"),
            "phone_duration_deviation": metric_value(analysis, "phone_duration_deviation"),
            "snr": metric_value(analysis, "snr"),
        }
        records.append(record)

    review_rows = select_review_rows(
        records,
        worst_per_metric=max(0, args.worst_per_metric),
        include_all_failures=not args.no_all_failures,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = args.out_dir / "audio"
    for row in review_rows:
        row["audio"] = link_or_copy_audio(Path(row["audio_source"]), audio_dir, args.copy_audio)

    counts = {
        "rows_total": len(records),
        "rows_review": len(review_rows),
        "textgrids_exported": sum(1 for row in records if row["has_textgrid"]),
        "textgrids_missing": sum(1 for row in records if not row["has_textgrid"]),
        "review_by_bucket": dict(Counter(row["issue_bucket"] for row in review_rows)),
        "review_by_source": dict(Counter(row.get("slice_source") or row.get("source") for row in review_rows)),
    }
    meta = {
        "dataset": args.dataset,
        "manifest": str(args.manifest),
        "analysis_csv": str(args.analysis_csv),
        "aligned_dir": str(args.aligned_dir),
        **counts,
    }

    (args.out_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (args.out_dir / "app.js").write_text(APP_JS, encoding="utf-8")
    (args.out_dir / "styles.css").write_text(STYLES_CSS, encoding="utf-8")
    (args.out_dir / "data.js").write_text(
        "window.REVIEW_META = "
        + json.dumps(meta, ensure_ascii=False, indent=2)
        + ";\nwindow.REVIEW_ROWS = "
        + json.dumps(review_rows, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    (args.out_dir / "failure_audit.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in review_rows),
        encoding="utf-8",
    )
    write_csv(args.out_dir / "failure_audit.csv", review_rows)
    (args.out_dir / "summary.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
