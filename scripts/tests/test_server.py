#!/usr/bin/env python3
"""Tests for scripts/review_server.py — the live review server.

TDD: these tests are written FIRST and must fail against the pre-extension
server (RED), then pass once the reviewer-mode routing, 400 (invalid JSON) and
413 (oversized body) guards are added (GREEN). Stdlib unittest + http.client
only — no `requests`, no pip installs.

Scope is LOCKED to five behaviors (per the plan's Metis S4 directive):
  1. POST valid author-mode payload  -> 200, file written, round-trips
  2. POST valid review-annotations    -> 200, file written, `kind` preserved
  3. POST invalid JSON                 -> 400, no output file written
  4. POST body > 5 MB                  -> 413, no output file written
  5. GET the served page               -> 200 with text/html content type

Threading internals, concurrent requests, and the /health endpoint are
deliberately out of scope and not tested here.
"""

import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

# Make `scripts/` importable regardless of the discover cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)
import sys
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import review_server  # noqa: E402


AUTHOR_PAYLOAD = {
    "branch": "feature/xyz",
    "generated_at": "2026-07-22T14:00:00Z",
    "overall": "approved",
    "sections": [
        {"id": "background", "decision": "approved", "comment": ""},
        {"id": "core-idea", "decision": "changes_requested", "comment": "lead with the 429"},
    ],
}

REVIEW_ANNOTATIONS_PAYLOAD = {
    "kind": "review-annotations",
    "mode": "pr",
    "repo": "acme/catalog-service",
    "prNumber": 482,
    "branch": "fix/date-parsing-guard",
    "generalComment": "Nice fix overall.",
    "annotations": [
        {
            "id": "a-1",
            "scope": "line",
            "type": "comment",
            "filePath": "src/utils/formatDate.js",
            "lineStart": 12,
            "lineEnd": 12,
            "side": "RIGHT",
            "body": "Do we always get a string here?",
            "origin": "user",
            "accepted": True,
        }
    ],
}

PAGE_HTML = "<html><head><title>Review</title></head><body>hello review</body></html>"


class ServerTestCase(unittest.TestCase):
    """Spin up the real handler on 127.0.0.1:0 in a background thread and hit
    it over HTTP, exactly like `main()` does, without invoking the CLI."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.out_path = os.path.join(self._tmpdir, "decisions.json")
        self.done = threading.Event()
        handler = review_server.build_handler(PAGE_HTML, self.out_path, self.done)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def _conn(self):
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)

    def _post(self, path, body_bytes, headers=None):
        conn = self._conn()
        try:
            conn.request("POST", path, body=body_bytes, headers=headers or {})
            resp = conn.getresponse()
            data = resp.read()
            return resp.status, data
        finally:
            conn.close()

    def _get(self, path):
        conn = self._conn()
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            data = resp.read()
            ctype = resp.getheader("Content-Type")
            return resp.status, ctype, data
        finally:
            conn.close()

    def test_author_mode_payload_written_and_roundtrips(self):
        body = json.dumps(AUTHOR_PAYLOAD).encode("utf-8")
        status, _ = self._post("/submit", body)
        self.assertEqual(status, 200)
        self.assertTrue(os.path.exists(self.out_path))
        with open(self.out_path, "r", encoding="utf-8") as fh:
            written = json.load(fh)
        self.assertEqual(written, AUTHOR_PAYLOAD)
        self.assertNotIn("kind", written)

    def test_review_annotations_payload_written_and_kind_preserved(self):
        body = json.dumps(REVIEW_ANNOTATIONS_PAYLOAD).encode("utf-8")
        status, _ = self._post("/submit", body)
        self.assertEqual(status, 200)
        self.assertTrue(os.path.exists(self.out_path))
        with open(self.out_path, "r", encoding="utf-8") as fh:
            written = json.load(fh)
        self.assertEqual(written, REVIEW_ANNOTATIONS_PAYLOAD)
        self.assertEqual(written.get("kind"), "review-annotations")

    def test_invalid_json_returns_400_and_writes_nothing(self):
        status, _ = self._post("/submit", b"not json at all")
        self.assertEqual(status, 400)
        self.assertFalse(os.path.exists(self.out_path))

    def test_oversized_body_returns_413_and_writes_nothing(self):
        limit = review_server.MAX_BODY_BYTES
        oversized = b'{"pad":"' + (b"x" * (limit + 1)) + b'"}'
        self.assertGreater(len(oversized), limit)
        status, _ = self._post(
            "/submit",
            oversized,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 413)
        self.assertFalse(os.path.exists(self.out_path))

    def test_get_serves_page_as_html(self):
        status, ctype, data = self._get("/")
        self.assertEqual(status, 200)
        self.assertIsNotNone(ctype)
        self.assertIn("text/html", ctype)
        self.assertIn(b"hello review", data)


if __name__ == "__main__":
    unittest.main()
