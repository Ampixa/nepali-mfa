"""Small review API for tts.ampixa.com/mfa/review."""

from __future__ import annotations

import csv
import io
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request


DB_PATH = Path(os.environ.get("DATABASE_PATH", "/app/data/mfa_review.db"))
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
ALLOWED_LABELS = {
    "keep",
    "minor",
    "background_audio",
    "text_bad",
    "audio_bad",
    "unsure",
}

app = Flask(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset TEXT NOT NULL,
  entry_id TEXT NOT NULL,
  label TEXT NOT NULL,
  notes TEXT,
  transcript TEXT,
  duration_sec REAL,
  reviewer_name TEXT NOT NULL,
  reviewer_email TEXT,
  client_ip TEXT,
  client_ua TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_decisions_dataset ON decisions (dataset);
CREATE INDEX IF NOT EXISTS idx_decisions_entry ON decisions (dataset, entry_id);
CREATE INDEX IF NOT EXISTS idx_decisions_reviewer ON decisions (reviewer_name);
CREATE INDEX IF NOT EXISTS idx_decisions_created ON decisions (created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_unique_reviewer_entry
  ON decisions (dataset, entry_id, reviewer_name);
"""


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def require_admin() -> None:
    token = request.args.get("token") or request.headers.get("X-Admin-Token", "")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        abort(403)


def client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    return forwarded or request.remote_addr or ""


def clean_text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "now": datetime.now(timezone.utc).isoformat()})


@app.get("/api/stats")
def stats():
    dataset = request.args.get("dataset", "").strip()
    where = "WHERE dataset = ?" if dataset else ""
    params = (dataset,) if dataset else ()
    with db_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM decisions {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT label, COUNT(*) AS n FROM decisions {where} GROUP BY label",
            params,
        ).fetchall()
        reviewers = conn.execute(
            f"SELECT COUNT(DISTINCT reviewer_name) FROM decisions {where}",
            params,
        ).fetchone()[0]
    return jsonify({
        "dataset": dataset or None,
        "total_decisions": total,
        "by_label": {row["label"]: row["n"] for row in rows},
        "unique_reviewers": reviewers,
    })


@app.post("/api/decisions")
def post_decision():
    payload = request.get_json(silent=True) or {}
    for field in ("dataset", "entry_id", "label", "reviewer_name"):
        if not clean_text(payload.get(field), 256):
            return jsonify({"error": f"missing field: {field}"}), 400

    label = clean_text(payload.get("label"), 64)
    if label not in ALLOWED_LABELS:
        return jsonify({"error": "invalid label"}), 400

    try:
        duration_sec = float(payload.get("duration_sec")) if payload.get("duration_sec") not in (None, "") else None
    except (TypeError, ValueError):
        duration_sec = None

    values = {
        "dataset": clean_text(payload.get("dataset"), 128),
        "entry_id": clean_text(payload.get("entry_id"), 256),
        "label": label,
        "notes": clean_text(payload.get("notes"), 2048),
        "transcript": clean_text(payload.get("transcript"), 8000),
        "duration_sec": duration_sec,
        "reviewer_name": clean_text(payload.get("reviewer_name"), 256),
        "reviewer_email": clean_text(payload.get("reviewer_email"), 256),
        "client_ip": client_ip(),
        "client_ua": clean_text(request.headers.get("User-Agent"), 512),
    }

    with db_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO decisions
              (dataset, entry_id, label, notes, transcript, duration_sec,
               reviewer_name, reviewer_email, client_ip, client_ua)
            VALUES
              (:dataset, :entry_id, :label, :notes, :transcript, :duration_sec,
               :reviewer_name, :reviewer_email, :client_ip, :client_ua)
            ON CONFLICT(dataset, entry_id, reviewer_name) DO UPDATE SET
              label = excluded.label,
              notes = excluded.notes,
              transcript = excluded.transcript,
              duration_sec = excluded.duration_sec,
              reviewer_email = excluded.reviewer_email,
              client_ip = excluded.client_ip,
              client_ua = excluded.client_ua,
              created_at = datetime('now')
            """,
            values,
        )
        conn.commit()
    return jsonify({"ok": True, "id": cur.lastrowid}), 201


@app.get("/api/decisions/export.tsv")
def export_tsv():
    require_admin()
    dataset = request.args.get("dataset", "").strip()
    where = "WHERE dataset = ?" if dataset else ""
    params = (dataset,) if dataset else ()
    with db_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM decisions {where} ORDER BY created_at ASC",
            params,
        ).fetchall()

    fields = [
        "id",
        "dataset",
        "entry_id",
        "label",
        "notes",
        "transcript",
        "duration_sec",
        "reviewer_name",
        "reviewer_email",
        "created_at",
    ]
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t", lineterminator="\n")
    writer.writerow(fields)
    for row in rows:
        writer.writerow([(row[field] if row[field] is not None else "") for field in fields])
    return Response(
        buf.getvalue(),
        mimetype="text/tab-separated-values",
        headers={"Content-Disposition": 'attachment; filename="mfa-review-decisions.tsv"'},
    )


init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8003")))
