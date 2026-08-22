#!/usr/bin/env python3
"""Tests for scripts/review_server.py: the live review server.

TDD: these tests are written FIRST and must fail against the pre-extension
server (RED), then pass once the reviewer-mode routing, 400 (invalid JSON) and
413 (oversized body) guards are added (GREEN). Stdlib unittest + http.client
only, no `requests`, no pip installs.

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


class QAServerTestCase(unittest.TestCase):
    NONCE = "a1b2c3"

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.out_path = os.path.join(self._tmpdir, "submit.json")
        self.session_dir = os.path.join(self._tmpdir, "session")
        os.makedirs(os.path.join(self.session_dir, "questions"))
        os.makedirs(os.path.join(self.session_dir, "answers"))
        self.done = threading.Event()
        handler = review_server.build_handler(
            PAGE_HTML,
            self.out_path,
            self.done,
            session_dir=self.session_dir,
            nonce=self.NONCE,
        )
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

    def _post(self, path, payload, headers=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        conn = self._conn()
        try:
            conn.request("POST", path, body=body, headers=h)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def _get_json(self, path):
        conn = self._conn()
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            conn.close()

    def _question(self, counter=1, **overrides):
        qid = f"{self.NONCE}-q{counter}"
        payload = {
            "qid": qid,
            "nonce": self.NONCE,
            "kind": "question",
            "target": {"type": "annotation", "annotationId": "ai-1"},
            "threadId": qid,
            "parentQid": None,
            "body": "Why does this matter?",
            "askedAt": "2026-08-20T12:34:56Z",
        }
        payload.update(overrides)
        return payload

    def _question_path(self, qid):
        return os.path.join(self.session_dir, "questions", qid + ".json")

    def test_post_ask_writes_question_without_setting_done(self):
        question = self._question()
        status, body = self._post("/ask", question)
        self.assertEqual((status, json.loads(body)), (200, {"ok": True}))
        with open(self._question_path(question["qid"]), "r", encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), question)
        self.assertFalse(self.done.is_set())

    def test_two_asks_create_distinct_files_and_both_are_pending(self):
        first = self._question(1)
        second = self._question(2)
        self.assertEqual(self._post("/ask", first)[0], 200)
        self.assertEqual(self._post("/ask", second)[0], 200)
        self.assertTrue(os.path.exists(self._question_path(first["qid"])))
        self.assertTrue(os.path.exists(self._question_path(second["qid"])))
        status, payload = self._get_json("/answers")
        self.assertEqual(status, 200)
        self.assertEqual(payload["answers"], [])
        self.assertEqual(payload["pending"], [first["qid"], second["qid"]])

    def test_get_answers_is_empty_before_any_questions(self):
        status, payload = self._get_json("/answers")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"answers": [], "pending": []})

    def test_get_answers_returns_disk_answer_and_remaining_pending_qids(self):
        first = self._question(1)
        second = self._question(2)
        self._post("/ask", first)
        self._post("/ask", second)
        answer = {
            "qid": first["qid"],
            "body": "Because this caller does not catch the exception.",
            "answeredAt": "2026-08-20T12:36:00Z",
        }
        answer_path = os.path.join(self.session_dir, "answers", first["qid"] + ".json")
        with open(answer_path, "w", encoding="utf-8") as fh:
            json.dump(answer, fh)
        status, payload = self._get_json("/answers")
        self.assertEqual(status, 200)
        self.assertEqual(payload["answers"], [answer])
        self.assertEqual(payload["pending"], [second["qid"]])

    def test_post_ask_wrong_or_missing_nonce_returns_409_without_writing(self):
        for counter, nonce in ((1, "wrong"), (2, None)):
            question = self._question(counter)
            if nonce is None:
                question.pop("nonce")
            else:
                question["nonce"] = nonce
            status, _ = self._post("/ask", question)
            self.assertEqual(status, 409)
            self.assertFalse(os.path.exists(self._question_path(question["qid"])))

    def test_post_ask_oversized_body_returns_413_without_writing(self):
        question = self._question(body="x" * (review_server.MAX_BODY_BYTES + 1))
        status, _ = self._post("/ask", question)
        self.assertEqual(status, 413)
        self.assertFalse(os.path.exists(self._question_path(question["qid"])))

    def test_post_ask_question_body_over_4000_chars_returns_413_without_writing(self):
        """The schema's 4000-char question cap triggers 413 independently of raw body size."""
        question = self._question(body="x" * (review_server.MAX_QUESTION_CHARS + 1))
        self.assertLess(len(json.dumps(question)), review_server.MAX_BODY_BYTES)
        status, _ = self._post("/ask", question)
        self.assertEqual(status, 413)
        self.assertFalse(os.path.exists(self._question_path(question["qid"])))

    def test_post_submit_still_writes_atomically_and_sets_done(self):
        payload = dict(REVIEW_ANNOTATIONS_PAYLOAD, nonce=self.NONCE)
        status, body = self._post("/submit", payload)
        self.assertEqual((status, json.loads(body)), (200, {"ok": True}))
        with open(self.out_path, "r", encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), payload)
        self.assertFalse(os.path.exists(self.out_path + ".tmp"))
        self.assertTrue(self.done.is_set())

    def test_post_submit_with_large_transcript_roundtrips_intact(self):
        """A large-but-valid transcript under MAX_BODY_BYTES is written verbatim."""
        transcript = [
            {
                "qid": f"{self.NONCE}-q{i}",
                "threadId": f"{self.NONCE}-q{i}",
                "target": {"type": "annotation", "annotationId": f"a-{i}"},
                "body": f"Question body number {i}: " + "x" * 2048,
                "answer": f"Answer body number {i}: " + "y" * 2048,
                "answered": True,
            }
            for i in range(100)
        ]
        payload = dict(REVIEW_ANNOTATIONS_PAYLOAD, nonce=self.NONCE,
                       transcript=transcript)
        body = json.dumps(payload).encode("utf-8")
        self.assertLess(len(body), review_server.MAX_BODY_BYTES)
        status, resp = self._post("/submit", body)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(resp), {"ok": True})
        with open(self.out_path, "r", encoding="utf-8") as fh:
            written = json.load(fh)
        self.assertEqual(written["transcript"], transcript)
        self.assertEqual(written["kind"], "review-annotations")
        self.assertTrue(self.done.is_set())

    def test_post_submit_with_transcript_over_max_body_bytes_returns_413(self):
        """An oversized transcript-shaped body respects the raw MAX_BODY_BYTES guard."""
        transcript = [
            {
                "qid": f"{self.NONCE}-q{i}",
                "threadId": f"{self.NONCE}-q{i}",
                "target": {"type": "annotation", "annotationId": "big"},
                "body": "z" * 1024,
                "answer": "w" * 1024,
                "answered": True,
            }
            for i in range(3000)
        ]
        payload = dict(REVIEW_ANNOTATIONS_PAYLOAD, nonce=self.NONCE,
                       transcript=transcript)
        body = json.dumps(payload).encode("utf-8")
        self.assertGreater(len(body), review_server.MAX_BODY_BYTES)
        status, resp = self._post("/submit", body,
                                  headers={"Content-Type": "application/json"})
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(resp), {"error": "payload too large"})
        self.assertFalse(os.path.exists(self.out_path))
        self.assertFalse(self.done.is_set())

    def test_post_ask_malformed_json_returns_400_and_server_keeps_serving(self):
        status, _ = self._post("/ask", b"not json")
        self.assertEqual(status, 400)
        self.assertEqual(os.listdir(os.path.join(self.session_dir, "questions")), [])
        self.assertFalse(self.done.is_set())
        answers_status, payload = self._get_json("/answers")
        self.assertEqual((answers_status, payload), (200, {"answers": [], "pending": []}))

    def test_post_ask_rejects_invalid_qid_without_writing(self):
        question = self._question(qid="../escape")
        status, _ = self._post("/ask", question)
        self.assertEqual(status, 400)
        self.assertEqual(os.listdir(os.path.join(self.session_dir, "questions")), [])


class BuildMarkerTestCase(unittest.TestCase):
    """An unsubstituted __FONT_CSS__ loads no @font-face at all, yet
    getComputedStyle still reports the embedded families and
    document.fonts.status still reads "loaded". The page renders in fallback
    fonts and looks merely off, so the launch has to catch it instead.
    """

    def test_unsubstituted_font_css_is_refused_and_explains_the_effect(self):
        err = review_server.marker_error("<style>__FONT_CSS__</style>")
        self.assertIsNotNone(err)
        self.assertIn("__FONT_CSS__", err)
        self.assertIn("fallback fonts", err)

    def test_every_marker_is_reported_not_just_the_first(self):
        page = "<style>__FONT_CSS__</style>__REVIEW_DATA__ __NARRATIVE_HTML__"
        err = review_server.marker_error(page)
        for marker in review_server.BUILD_MARKERS:
            self.assertIn(marker, err)

    def test_fully_substituted_page_is_accepted(self):
        self.assertIsNone(review_server.marker_error("<style>@font-face{}</style>"))

    def test_markers_are_listed_for_inspection(self):
        page = "__FONT_CSS__ and __NARRATIVE_HTML__"
        self.assertEqual(review_server.unsubstituted_markers(page),
                         ["__FONT_CSS__", "__NARRATIVE_HTML__"])


class QANonceConsistencyTestCase(unittest.TestCase):
    """The page hides its entire Ask UI when it cannot authenticate, and says
    nothing about it. These lock the launch-time guard that makes that loud.
    """

    NONCE = "cafebabe4242"

    def _page(self, nonce=None):
        data = '{"mode": "pr", "repo": "a/b"'
        if nonce:
            data += ', "sessionNonce": "%s"' % nonce
        return '<html><script id="review-data">%s}</script></html>' % data

    def test_nonce_requested_but_page_has_none_is_refused(self):
        err = review_server.qa_nonce_error(self._page(None), self.NONCE)
        self.assertIsNotNone(err)
        self.assertIn("silently absent", err)
        self.assertIn("(absent)", err)

    def test_nonce_mismatch_is_refused_and_names_both_values(self):
        err = review_server.qa_nonce_error(self._page("adifferentone"), self.NONCE)
        self.assertIsNotNone(err)
        self.assertIn(self.NONCE, err)
        self.assertIn("adifferentone", err)

    def test_page_nonce_without_server_nonce_is_refused(self):
        err = review_server.qa_nonce_error(self._page(self.NONCE), None)
        self.assertIsNotNone(err)
        self.assertIn("404", err)

    def test_matching_nonce_is_accepted(self):
        self.assertIsNone(review_server.qa_nonce_error(self._page(self.NONCE), self.NONCE))

    def test_no_nonce_on_either_side_is_accepted(self):
        """A live server with Q&A deliberately off is a valid configuration."""
        self.assertIsNone(review_server.qa_nonce_error(self._page(None), None))

    def test_nonce_is_read_from_the_page_not_guessed(self):
        self.assertEqual(review_server.page_session_nonce(self._page("abc123")), "abc123")
        self.assertIsNone(review_server.page_session_nonce(self._page(None)))


class QADisabledServerTestCase(unittest.TestCase):
    def test_ask_and_answers_return_404_when_session_dir_is_not_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            done = threading.Event()
            handler = review_server.build_handler(PAGE_HTML, os.path.join(tmpdir, "out.json"), done)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request("POST", "/ask", body=b"{}")
                self.assertEqual(conn.getresponse().status, 404)
                conn.close()
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request("GET", "/answers")
                self.assertEqual(conn.getresponse().status, 404)
                conn.close()
                self.assertFalse(done.is_set())
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
