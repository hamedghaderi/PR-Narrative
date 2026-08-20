#!/usr/bin/env python3
"""Live review server for the pr-narrative skill.

By default this is the existing single-shot server: it serves an interactive PR review
page, writes the reviewer's JSON decisions to disk on ``POST /submit``, and exits after
submit or ``--timeout`` seconds.

Reviewer mode can optionally enable file-backed live Q&A with ``--session-dir`` and
``--nonce``. ``POST /ask`` validates the run nonce and atomically writes one question to
``questions/<qid>.json`` without ending the session. ``GET /answers`` returns parsed
``answers/*.json`` files plus unanswered question ids. In this mode ``POST /submit``
also validates the nonce, and the timeout is inactivity-based: ask, answers, and submit
requests reset it, while ``--max-lifetime`` supplies an absolute ceiling. Q&A state is
never kept in memory; the session files are authoritative.

Two Submit payload shapes are accepted, discriminated by the presence of a `kind`
field (see references/annotation-schema.md §3):
  - author mode: `{ branch, generated_at, overall, sections }` (no `kind` field).
  - reviewer mode: `{ kind: "review-annotations", ... }`.
Both are written verbatim to --out and resolve the single-shot wait identically; the
server only routes on `kind`, it does not interpret the annotation contents.

Standard library only; no pip installs. Usage:

    python3 review_server.py --page /tmp/pr-review-<branch>.html \
                             --out  /tmp/pr-review-decisions.json \
                             [--port 0] [--timeout 1800] [--open] \
                             [--session-dir /tmp/pr-review-session-...] \
                             [--nonce <hex>] [--max-lifetime 14400]

It prints one line to stdout: `PR_REVIEW_URL http://127.0.0.1:<port>/` so the caller
knows where to open the browser. When the reviewer submits (or the timeout elapses),
the process exits. Poll --out for the decisions file; its presence means "done".

With --open, the server tries to open the review URL in a browser once it is listening,
walking a platform-aware chain of launchers (`BROWSER` env var, `/usr/bin/open`,
`xdg-open`/`wslview`, `os.startfile`, then Python's `webbrowser`). It stops at the first
launcher that reports success. Three stdout sentinels describe what happened:

  - `PR_REVIEW_OPEN_DIAG strategy=<name> rc=<returncode|ok|timeout|error:<ExcType>>`:
    one line per launcher actually attempted, for diagnosing a silent failure.
  - `PR_REVIEW_OPEN_OK <url>`: a launcher reported success. Note this means the launch
    command succeeded, not that a window is definitely on screen.
  - `PR_REVIEW_OPEN_FAILED <url>`: every launcher failed; the caller should open the
    URL manually (e.g. in a headless environment).

Exactly one of `PR_REVIEW_OPEN_OK` / `PR_REVIEW_OPEN_FAILED` is printed per run, and
only when --open is passed. Either way the server keeps serving.

The page is served with a `<meta name="pr-review-live" content="1">` marker injected,
which flips the page into live-POST mode (see references/review-ui.md). Without the
server, the same page still works via its Download-decisions fallback.

Security note: this server binds to 127.0.0.1 (loopback) only, on purpose. That is the
trust boundary: the reviewer typing comments is the local operator who launched the
skill, so the decisions JSON is first-party input. Do NOT change the bind address to
0.0.0.0 or expose it beyond localhost: doing so would let a *different* person's
free-text comments flow into the agent's revision instructions (indirect prompt
injection). The agent treats comments as untrusted feedback data regardless (see
SKILL.md), but keeping the socket loopback-only rather than binding all interfaces is
the primary guard.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LIVE_MARKER = '<meta name="pr-review-live" content="1">'

MAX_BODY_BYTES = 5 * 1024 * 1024
MAX_QUESTION_CHARS = 4000

# Seconds to wait on a launcher subprocess before giving up on it. Launchers are
# fire-and-forget by design, so anything this slow is hung, not working.
OPEN_TIMEOUT_SECONDS = 10


def _open_browser(url: str) -> bool:
    """Try hard to open `url` in a browser, and say out loud what was tried.

    `webbrowser.open()` alone is not enough: it returns True as soon as it finds a
    *handler*, which on macOS means an osascript hop that quietly does nothing from a
    non-interactive shell. So instead we walk platform-native launchers first and print a
    `PR_REVIEW_OPEN_DIAG` line for every strategy attempted, then exactly one
    `PR_REVIEW_OPEN_OK` / `PR_REVIEW_OPEN_FAILED` verdict.

    Returns True if some launcher reported success. Never raises: opening a browser is a
    convenience, and the server must keep serving even if it fails.
    """

    def diag(strategy, rc):
        print(f"PR_REVIEW_OPEN_DIAG strategy={strategy} rc={rc}", flush=True)

    def succeeded():
        print(f"PR_REVIEW_OPEN_OK {url}", flush=True)
        return True

    def try_webbrowser(strategy):
        try:
            opened = webbrowser.open(url)
        except Exception as exc:
            diag(strategy, f"error:{type(exc).__name__}")
            return False
        # False means "no handler found at all", the one case webbrowser is honest about.
        diag(strategy, "ok" if opened else "error:NoHandler")
        return bool(opened)

    def try_launcher(strategy, argv, timeout_is_success):
        try:
            proc = subprocess.run(
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=OPEN_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            # A launcher that blocks usually handed off to a browser and then sat there.
            diag(strategy, "timeout")
            return timeout_is_success
        except Exception as exc:
            diag(strategy, f"error:{type(exc).__name__}")
            return False
        diag(strategy, proc.returncode)
        return proc.returncode == 0

    try:
        # An explicit BROWSER is the operator's stated preference, so honor it first,
        # but log it distinctly, since a broken BROWSER is a silent false positive.
        if os.environ.get("BROWSER", "").strip():
            if try_webbrowser("BROWSER-env"):
                return succeeded()

        if sys.platform == "darwin":
            if try_launcher("darwin-open", ["/usr/bin/open", url], timeout_is_success=False):
                return succeeded()
        elif sys.platform.startswith("linux"):
            for strategy in ("xdg-open", "wslview"):
                exe = shutil.which(strategy)
                if exe is None:
                    continue
                if try_launcher(strategy, [exe, url], timeout_is_success=True):
                    return succeeded()
        elif sys.platform.startswith("win"):
            if hasattr(os, "startfile"):
                try:
                    os.startfile(url)
                except Exception as exc:
                    diag("os-startfile", f"error:{type(exc).__name__}")
                else:
                    diag("os-startfile", "ok")
                    return succeeded()

        if try_webbrowser("webbrowser"):
            return succeeded()
    except Exception as exc:  # the chain itself broke; still never take the server down
        diag("chain", f"error:{type(exc).__name__}")

    print(f"PR_REVIEW_OPEN_FAILED {url}", flush=True)
    return False


def build_handler(
    page_html: str,
    out_path: str,
    done_event: threading.Event,
    *,
    session_dir=None,
    nonce=None,
):
    last_activity = [time.monotonic()]

    class Handler(BaseHTTPRequestHandler):
        @classmethod
        def get_last_activity(cls):
            return last_activity[0]

        def log_message(self, *args):
            return

        def _record_activity(self):
            last_activity[0] = time.monotonic()

        def _send(self, code, body=b"", ctype="text/plain; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _reject_oversized(self):
            # Drain the client's still-streaming body in bounded chunks first, so
            # the 413 response reaches the client instead of racing a socket reset,
            # then ask the client to close the (now-poisoned) connection.
            remaining = int(self.headers.get("Content-Length", 0))
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    break
                remaining -= len(chunk)
            self.close_connection = True
            self._send(413, b'{"error":"payload too large"}', "application/json")

        def _read_json(self):
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY_BYTES:
                self._reject_oversized()
                return None
            raw = self.rfile.read(length) if length else b"{}"
            try:
                return json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._send(400, b'{"error":"invalid json"}', "application/json")
                return None

        def _write_json_atomically(self, path, payload):
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            os.replace(tmp, path)

        def _send_answers(self):
            answers_dir = os.path.join(session_dir, "answers")
            questions_dir = os.path.join(session_dir, "questions")
            answers = []
            answered_qids = set()
            for name in sorted(os.listdir(answers_dir)):
                if not name.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(answers_dir, name), "r", encoding="utf-8") as fh:
                        answers.append(json.load(fh))
                except (OSError, ValueError, UnicodeDecodeError):
                    continue
                answered_qids.add(name[:-5])
            pending = [
                name[:-5]
                for name in sorted(os.listdir(questions_dir))
                if name.endswith(".json") and name[:-5] not in answered_qids
            ]
            body = json.dumps({"answers": answers, "pending": pending}).encode("utf-8")
            self._send(200, body, "application/json")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, page_html.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/health":
                self._send(200, b"ok")
            elif self.path == "/answers" and session_dir is not None:
                self._record_activity()
                self._send_answers()
            else:
                self._send(404, b"not found")

        def do_POST(self):
            if self.path == "/ask" and session_dir is not None:
                self._record_activity()
                payload = self._read_json()
                if payload is None:
                    return
                if not isinstance(payload, dict) or payload.get("nonce") != nonce:
                    self._send(409, b'{"ok":false}', "application/json")
                    return
                qid = payload.get("qid")
                expected_qid = rf"{re.escape(nonce)}-q[0-9]+"
                if not isinstance(qid, str) or re.fullmatch(expected_qid, qid) is None:
                    self._send(400, b'{"ok":false}', "application/json")
                    return
                body = payload.get("body", "")
                if not isinstance(body, str) or len(body) > MAX_QUESTION_CHARS:
                    self._send(413, b'{"ok":false}', "application/json")
                    return
                question_path = os.path.join(session_dir, "questions", qid + ".json")
                self._write_json_atomically(question_path, payload)
                self._send(200, b'{"ok":true}', "application/json")
                return
            if self.path != "/submit":
                self._send(404, b"not found")
                return
            if session_dir is not None:
                self._record_activity()
            payload = self._read_json()
            if payload is None:
                return
            if session_dir is not None and (
                not isinstance(payload, dict) or payload.get("nonce") != nonce
            ):
                self._send(409, b'{"ok":false}', "application/json")
                return
            self._write_json_atomically(out_path, payload)
            self._send(200, b'{"ok":true}', "application/json")
            done_event.set()

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", required=True, help="path to the review HTML file")
    ap.add_argument("--out", required=True, help="path to write the decisions JSON")
    ap.add_argument("--port", type=int, default=0, help="port (0 = pick a free one)")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="seconds before timeout (Q&A mode: inactivity window)")
    ap.add_argument("--max-lifetime", type=int, default=14400,
                    help="Q&A mode absolute lifetime ceiling in seconds")
    ap.add_argument("--session-dir", help="directory for questions/ and answers/")
    ap.add_argument("--nonce", help="per-run nonce required by Q&A requests")
    ap.add_argument("--open", action="store_true",
                    help="open the review URL in the default browser once the server is listening")
    args = ap.parse_args()

    if (args.session_dir is None) != (args.nonce is None):
        ap.error("--session-dir and --nonce must be provided together")
    if args.session_dir is not None:
        os.makedirs(os.path.join(args.session_dir, "questions"), exist_ok=True)
        os.makedirs(os.path.join(args.session_dir, "answers"), exist_ok=True)

    with open(args.page, "r", encoding="utf-8") as fh:
        page_html = fh.read()

    # Inject the live marker so the page enables server mode. Put it right after
    # <head> if present, else prepend; either way the page can detect it.
    if LIVE_MARKER not in page_html:
        if "<head>" in page_html:
            page_html = page_html.replace("<head>", "<head>\n" + LIVE_MARKER, 1)
        else:
            page_html = LIVE_MARKER + page_html

    done = threading.Event()
    handler = build_handler(
        page_html,
        args.out,
        done,
        session_dir=args.session_dir,
        nonce=args.nonce,
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    port = httpd.server_address[1]

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    print(f"PR_REVIEW_URL http://127.0.0.1:{port}/", flush=True)

    if args.open:
        _open_browser(f"http://127.0.0.1:{port}/")

    if args.session_dir is None:
        submitted = done.wait(timeout=args.timeout)
    else:
        started_at = time.monotonic()
        submitted = False
        while True:
            now = time.monotonic()
            inactivity_remaining = args.timeout - (now - handler.get_last_activity())
            lifetime_remaining = args.max_lifetime - (now - started_at)
            if inactivity_remaining <= 0 or lifetime_remaining <= 0:
                break
            if done.wait(timeout=min(2.0, inactivity_remaining, lifetime_remaining)):
                submitted = True
                break

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
