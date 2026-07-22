#!/usr/bin/env python3
"""Live review server for the pr-narrative skill.

Serves an interactive PR review page and captures the reviewer's decisions the moment
they click Submit — no manual download/hand-back step. On submit it writes the
decisions JSON to disk (where the agent reads it) and then shuts itself down.

Standard library only; no pip installs. Usage:

    python3 review_server.py --page /tmp/pr-review-<branch>.html \
                             --out  /tmp/pr-review-decisions.json \
                             [--port 0] [--timeout 1800]

It prints one line to stdout: `PR_REVIEW_URL http://127.0.0.1:<port>/` so the caller
knows where to open the browser. When the reviewer submits (or the timeout elapses),
the process exits. Poll --out for the decisions file; its presence means "done".

The page is served with a `<meta name="pr-review-live" content="1">` marker injected,
which flips the page into live-POST mode (see references/review-ui.md). Without the
server, the same page still works via its Download-decisions fallback.

Security note: this server binds to 127.0.0.1 (loopback) only, on purpose. That is the
trust boundary — the reviewer typing comments is the local operator who launched the
skill, so the decisions JSON is first-party input. Do NOT change the bind address to
0.0.0.0 or expose it beyond localhost: doing so would let a *different* person's
free-text comments flow into the agent's revision instructions (indirect prompt
injection). The agent treats comments as untrusted feedback data regardless (see
SKILL.md), but keeping the socket loopback-only is the primary guard.
"""

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LIVE_MARKER = '<meta name="pr-review-live" content="1">'


def build_handler(page_html: str, out_path: str, done_event: threading.Event):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def _send(self, code, body=b"", ctype="text/plain; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, page_html.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/health":
                self._send(200, b"ok")
            else:
                self._send(404, b"not found")

        def do_POST(self):
            if self.path != "/submit":
                self._send(404, b"not found")
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._send(400, b'{"error":"invalid json"}', "application/json")
                return
            tmp = out_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            os.replace(tmp, out_path)  # atomic rename so the agent never reads a half-written file
            self._send(200, b'{"ok":true}', "application/json")
            done_event.set()

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", required=True, help="path to the review HTML file")
    ap.add_argument("--out", required=True, help="path to write the decisions JSON")
    ap.add_argument("--port", type=int, default=0, help="port (0 = pick a free one)")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="max seconds to wait for a submit before giving up")
    args = ap.parse_args()

    with open(args.page, "r", encoding="utf-8") as fh:
        page_html = fh.read()

    # Inject the live marker so the page enables server mode. Put it right after
    # <head> if present, else prepend — either way the page can detect it.
    if LIVE_MARKER not in page_html:
        if "<head>" in page_html:
            page_html = page_html.replace("<head>", "<head>\n" + LIVE_MARKER, 1)
        else:
            page_html = LIVE_MARKER + page_html

    done = threading.Event()
    handler = build_handler(page_html, args.out, done)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    port = httpd.server_address[1]

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    print(f"PR_REVIEW_URL http://127.0.0.1:{port}/", flush=True)

    submitted = done.wait(timeout=args.timeout)

    time.sleep(0.4)
    httpd.shutdown()

    if submitted:
        print("PR_REVIEW_DONE", flush=True)
        sys.exit(0)
    else:
        print("PR_REVIEW_TIMEOUT", flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
