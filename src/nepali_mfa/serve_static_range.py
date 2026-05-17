#!/usr/bin/env python3
"""Small static file server with byte-range and no-cache headers."""

from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class RangeStaticHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def send_head(self):  # noqa: ANN001
        path = Path(self.translate_path(self.path))
        if path.is_dir():
            for index in ("index.html", "index.htm"):
                candidate = path / index
                if candidate.exists():
                    path = candidate
                    break
            else:
                return self.list_directory(str(path))

        ctype = self.guess_type(str(path))
        try:
            f = path.open("rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        size = os.fstat(f.fileno()).st_size
        range_header = self.headers.get("Range")
        self._range = None

        if range_header and range_header.startswith("bytes="):
            spec = range_header.split("=", 1)[1].split(",", 1)[0].strip()
            start_s, _, end_s = spec.partition("-")
            try:
                if start_s:
                    start = int(start_s)
                    end = int(end_s) if end_s else size - 1
                else:
                    suffix = int(end_s)
                    start = max(size - suffix, 0)
                    end = size - 1
                if start < 0 or end < start or start >= size:
                    raise ValueError
                end = min(end, size - 1)
            except ValueError:
                f.close()
                self.send_error(416, "Requested Range Not Satisfiable")
                return None

            self._range = (start, end)
            f.seek(start)
            self.send_response(206)
            self.send_header("Content-type", ctype)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Last-Modified", self.date_time_string(path.stat().st_mtime))
            self.end_headers()
            return f

        self.send_response(200)
        self.send_header("Content-type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Last-Modified", self.date_time_string(path.stat().st_mtime))
        self.end_headers()
        return f

    def copyfile(self, source, outputfile) -> None:  # noqa: ANN001
        byte_range = getattr(self, "_range", None)
        if not byte_range:
            return super().copyfile(source, outputfile)
        start, end = byte_range
        remaining = end - start + 1
        while remaining > 0:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--bind", default="0.0.0.0")
    args = parser.parse_args()

    handler = partial(RangeStaticHandler, directory=args.directory)
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    print(f"serving {args.directory} on http://{args.bind}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
