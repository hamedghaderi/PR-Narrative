#!/usr/bin/env python3
"""Tests for scripts/existing_activity.py: the existing-review-activity normalizer.

Stdlib unittest only, matching test_anchoring.py and test_payload.py.

The invariant class at the bottom is the important one: it proves that existing
GitHub activity cannot reach a GitHub write path, which is the safety property
the whole read-only feature depends on.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import build_review  # noqa: E402
import diff_anchor  # noqa: E402
import existing_activity  # noqa: E402


def _comment(body, login="octocat", url="https://github.com/o/r/pull/1#discussion_r1",
             created="2026-08-20T12:00:00Z", node_id="C_1", association="MEMBER"):
    return {
        "id": node_id,
        "databaseId": 1,
        "body": body,
        "author": {"login": login} if login is not None else None,
        "authorAssociation": association,
        "createdAt": created,
        "url": url,
    }


def _thread(comments=None, resolved=False, outdated=False, path="src/a.py",
            line=10, original_line=8, side="RIGHT", node_id="T_1",
            subject_type="LINE", resolved_by=None, start_line=None):
    return {
        "id": node_id,
        "isResolved": resolved,
        "isOutdated": outdated,
        "isCollapsed": resolved,
        "resolvedBy": {"login": resolved_by} if resolved_by else None,
        "path": path,
        "line": line,
        "originalLine": original_line,
        "startLine": start_line,
        "originalStartLine": None,
        "diffSide": side,
        "startDiffSide": None,
        "subjectType": subject_type,
        "comments": {"nodes": comments if comments is not None else [_comment("root")]},
    }


def _response(threads=None, reviews=None, issue_comments=None,
              head="abc123", has_next=False, errors=None):
    document = {
        "data": {
            "repository": {
                "pullRequest": {
                    "headRefOid": head,
                    "reviewThreads": {
                        "pageInfo": {"hasNextPage": has_next, "endCursor": "cur"},
                        "nodes": threads if threads is not None else [],
                    },
                    "reviews": {
                        "totalCount": len(reviews or []),
                        "nodes": reviews or [],
                    },
                    "comments": {
                        "totalCount": len(issue_comments or []),
                        "nodes": issue_comments or [],
                    },
                }
            }
        }
    }
    if errors is not None:
        document["errors"] = errors
    return document


FIXED_TIME = "2026-08-21T09:00:00Z"


def _normalize(raw, **kwargs):
    kwargs.setdefault("fetched_at", FIXED_TIME)
    return existing_activity.to_existing_activity(raw, **kwargs)


class LoadDocumentsTests(unittest.TestCase):
    def test_single_object(self):
        self.assertEqual(len(existing_activity.load_documents('{"a":1}')), 1)

    def test_slurped_array(self):
        self.assertEqual(len(existing_activity.load_documents('[{"a":1},{"a":2}]')), 2)

    def test_concatenated_objects_from_plain_paginate(self):
        docs = existing_activity.load_documents('{"a":1}\n{"a":2}\n{"a":3}')
        self.assertEqual([d["a"] for d in docs], [1, 2, 3])

    def test_empty_input(self):
        self.assertEqual(existing_activity.load_documents("   "), [])


class ThreadNormalizationTests(unittest.TestCase):
    def test_basic_thread_anchor_fields(self):
        activity = _normalize(_response(threads=[_thread()]))
        self.assertEqual(activity["status"], "complete")
        thread = activity["threads"][0]
        self.assertEqual(thread["filePath"], "src/a.py")
        self.assertEqual(thread["line"], 10)
        self.assertEqual(thread["side"], "RIGHT")
        self.assertEqual(thread["subjectType"], "LINE")
        self.assertFalse(thread["isResolved"])
        self.assertFalse(thread["isOutdated"])

    def test_outdated_thread_keeps_original_line_separate_from_line(self):
        raw = _response(threads=[_thread(outdated=True, line=None, original_line=8)])
        thread = _normalize(raw)["threads"][0]
        self.assertIsNone(thread["line"])
        self.assertEqual(thread["originalLine"], 8)
        self.assertTrue(thread["isOutdated"])

    def test_resolved_and_outdated_stay_independent(self):
        raw = _response(threads=[
            _thread(node_id="T_open", resolved=False, outdated=True),
            _thread(node_id="T_done", resolved=True, outdated=False, resolved_by="alice"),
        ])
        threads = {t["id"]: t for t in _normalize(raw)["threads"]}
        self.assertTrue(threads["T_open"]["isOutdated"])
        self.assertFalse(threads["T_open"]["isResolved"])
        self.assertTrue(threads["T_done"]["isResolved"])
        self.assertEqual(threads["T_done"]["resolvedBy"], "alice")

    def test_replies_are_kept_in_order(self):
        comments = [_comment("root", node_id="C_1"),
                    _comment("reply one", node_id="C_2"),
                    _comment("reply two", node_id="C_3")]
        thread = _normalize(_response(threads=[_thread(comments=comments)]))["threads"][0]
        self.assertEqual([c["body"] for c in thread["comments"]],
                         ["root", "reply one", "reply two"])

    def test_file_level_thread_has_no_line(self):
        raw = _response(threads=[_thread(subject_type="FILE", line=None,
                                         original_line=None)])
        thread = _normalize(raw)["threads"][0]
        self.assertEqual(thread["subjectType"], "FILE")
        self.assertIsNone(thread["line"])

    def test_null_author_becomes_none_not_crash(self):
        raw = _response(threads=[_thread(comments=[_comment("hi", login=None)])])
        thread = _normalize(raw)["threads"][0]
        self.assertIsNone(thread["comments"][0]["author"])

    def test_missing_author_object_entirely(self):
        node = _comment("hi")
        del node["author"]
        thread = _normalize(_response(threads=[_thread(comments=[node])]))["threads"][0]
        self.assertIsNone(thread["comments"][0]["author"])


class UrlSafetyTests(unittest.TestCase):
    def test_javascript_url_is_dropped(self):
        raw = _response(threads=[_thread(
            comments=[_comment("x", url="javascript:alert(1)")])])
        thread = _normalize(raw)["threads"][0]
        self.assertIsNone(thread["comments"][0]["url"])

    def test_offhost_url_is_dropped(self):
        raw = _response(threads=[_thread(
            comments=[_comment("x", url="https://evil.example.com/pull/1")])])
        thread = _normalize(raw)["threads"][0]
        self.assertIsNone(thread["comments"][0]["url"])

    def test_plain_http_is_dropped(self):
        raw = _response(threads=[_thread(
            comments=[_comment("x", url="http://github.com/o/r/pull/1")])])
        thread = _normalize(raw)["threads"][0]
        self.assertIsNone(thread["comments"][0]["url"])

    def test_enterprise_host_allowed_when_opted_in(self):
        raw = _response(threads=[_thread(
            comments=[_comment("x", url="https://git.acme.com/o/r/pull/1")])])
        thread = _normalize(
            raw, allowed_hosts=("github.com", "git.acme.com"))["threads"][0]
        self.assertEqual(thread["comments"][0]["url"], "https://git.acme.com/o/r/pull/1")


class StatusTests(unittest.TestCase):
    def test_errors_bearing_200_is_partial_not_complete(self):
        raw = _response(threads=[_thread()],
                        errors=[{"message": "Something collapsed"}])
        activity = _normalize(raw)
        self.assertEqual(activity["status"], "partial")
        self.assertIn("Something collapsed", activity["reason"])

    def test_missing_pull_request_is_unavailable(self):
        activity = _normalize({"data": {"repository": None}})
        self.assertEqual(activity["status"], "unavailable")
        self.assertEqual(activity["threads"], [])

    def test_unavailable_is_distinguishable_from_genuinely_empty(self):
        empty = _normalize(_response(threads=[]))
        broken = _normalize({"errors": [{"message": "bad credentials"}]})
        self.assertEqual(empty["status"], "complete")
        self.assertEqual(broken["status"], "unavailable")
        self.assertEqual(empty["threads"], broken["threads"])

    def test_has_next_page_marks_partial(self):
        activity = _normalize(_response(threads=[_thread()], has_next=True))
        self.assertEqual(activity["status"], "partial")

    def test_head_mismatch_marks_partial(self):
        activity = _normalize(_response(threads=[_thread()], head="aaa"),
                              head_ref_oid="bbb")
        self.assertEqual(activity["status"], "partial")
        self.assertIn("branch moved", activity["reason"])

    def test_head_match_stays_complete(self):
        activity = _normalize(_response(threads=[_thread()], head="aaa"),
                              head_ref_oid="aaa")
        self.assertEqual(activity["status"], "complete")

    def test_pagination_merges_thread_nodes_across_pages(self):
        page1 = _response(threads=[_thread(node_id="T_1")], has_next=True)
        page2 = _response(threads=[_thread(node_id="T_2")], has_next=False)
        activity = _normalize([page1, page2])
        self.assertEqual([t["id"] for t in activity["threads"]], ["T_1", "T_2"])
        self.assertEqual(activity["status"], "complete")


class BudgetTests(unittest.TestCase):
    def test_thread_cap_prefers_unresolved(self):
        threads = [_thread(node_id="T_resolved", resolved=True),
                   _thread(node_id="T_open", resolved=False)]
        activity = _normalize(_response(threads=threads), thread_cap=1)
        self.assertEqual([t["id"] for t in activity["threads"]], ["T_open"])
        self.assertEqual(activity["truncation"]["threadsOmitted"], 1)

    def test_unresolved_outdated_outranks_resolved(self):
        threads = [_thread(node_id="T_resolved", resolved=True),
                   _thread(node_id="T_stale", resolved=False, outdated=True)]
        activity = _normalize(_response(threads=threads), thread_cap=1)
        self.assertEqual([t["id"] for t in activity["threads"]], ["T_stale"])

    def test_surviving_threads_keep_original_order(self):
        threads = [_thread(node_id="T_a", resolved=False),
                   _thread(node_id="T_b", resolved=True),
                   _thread(node_id="T_c", resolved=False)]
        activity = _normalize(_response(threads=threads), thread_cap=2)
        self.assertEqual([t["id"] for t in activity["threads"]], ["T_a", "T_c"])

    def test_per_thread_comment_cap_keeps_root_and_newest(self):
        comments = [_comment("root", node_id="C_0")] + [
            _comment("reply %d" % i, node_id="C_%d" % i) for i in range(1, 10)]
        activity = _normalize(_response(threads=[_thread(comments=comments)]),
                             comments_per_thread=3)
        thread = activity["threads"][0]
        bodies = [c["body"] for c in thread["comments"]]
        self.assertEqual(bodies, ["root", "reply 8", "reply 9"])
        self.assertEqual(thread["commentsOmitted"], 7)
        self.assertEqual(activity["truncation"]["commentsOmitted"], 7)

    def test_body_char_cap_truncates_and_flags(self):
        activity = _normalize(_response(threads=[_thread(
            comments=[_comment("x" * 500)])]), body_chars=100)
        comment = activity["threads"][0]["comments"][0]
        self.assertTrue(comment["bodyTruncated"])
        self.assertLessEqual(len(comment["body"]), 100)

    def test_total_byte_budget_stops_adding_threads(self):
        threads = [_thread(node_id="T_%d" % i,
                           comments=[_comment("y" * 400, node_id="C_%d" % i)])
                   for i in range(10)]
        activity = _normalize(_response(threads=threads), total_body_chars=1000)
        self.assertLess(len(activity["threads"]), 10)
        self.assertGreater(activity["truncation"]["threadsOmitted"], 0)

    def test_one_oversized_thread_still_renders(self):
        threads = [_thread(comments=[_comment("z" * 5000)])]
        activity = _normalize(_response(threads=threads), total_body_chars=10)
        self.assertEqual(len(activity["threads"]), 1)


class ReviewSummaryTests(unittest.TestCase):
    def _review(self, state="APPROVED", body="looks good", login="alice",
                node_id="R_1"):
        return {
            "id": node_id,
            "author": {"login": login},
            "state": state,
            "body": body,
            "submittedAt": "2026-08-20T10:00:00Z",
            "url": "https://github.com/o/r/pull/1#pullrequestreview-1",
        }

    def test_review_states_pass_through(self):
        raw = _response(reviews=[self._review(state="CHANGES_REQUESTED")])
        self.assertEqual(_normalize(raw)["reviews"][0]["state"], "CHANGES_REQUESTED")

    def test_unknown_future_state_is_not_dropped(self):
        raw = _response(reviews=[self._review(state="SOMETHING_NEW")])
        self.assertEqual(_normalize(raw)["reviews"][0]["state"], "SOMETHING_NEW")

    def test_dismissed_state_survives(self):
        raw = _response(reviews=[self._review(state="DISMISSED")])
        self.assertEqual(_normalize(raw)["reviews"][0]["state"], "DISMISSED")

    def test_pending_review_is_excluded(self):
        raw = _response(reviews=[self._review(state="PENDING", body="my draft")])
        self.assertEqual(_normalize(raw)["reviews"], [])

    def test_empty_bodied_commented_review_is_dropped_as_noise(self):
        raw = _response(reviews=[self._review(state="COMMENTED", body="")])
        self.assertEqual(_normalize(raw)["reviews"], [])

    def test_empty_bodied_approval_is_kept(self):
        raw = _response(reviews=[self._review(state="APPROVED", body="")])
        self.assertEqual(len(_normalize(raw)["reviews"]), 1)

    def test_issue_comments_are_separate_from_threads(self):
        raw = _response(issue_comments=[_comment("general chatter")])
        activity = _normalize(raw)
        self.assertEqual(len(activity["issueComments"]), 1)
        self.assertEqual(activity["threads"], [])


class CliTests(unittest.TestCase):
    def _run(self, payload, extra=None):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(payload, fh)
            path = fh.name
        try:
            proc = subprocess.run(
                [sys.executable,
                 os.path.join(_SCRIPTS, "existing_activity.py"),
                 "--activity-json", path,
                 "--fetched-at", FIXED_TIME] + (extra or []),
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return json.loads(proc.stdout)
        finally:
            os.unlink(path)

    def test_cli_emits_contract_keys(self):
        out = self._run(_response(threads=[_thread()]))
        for key in ("status", "sourceHeadOid", "fetchedAt", "truncation",
                    "threads", "reviews", "issueComments"):
            self.assertIn(key, out)

    def test_cli_head_mismatch_flag(self):
        out = self._run(_response(threads=[_thread()], head="aaa"),
                        extra=["--head-ref-oid", "bbb"])
        self.assertEqual(out["status"], "partial")


class NeverSubmittedInvariantTests(unittest.TestCase):
    """Existing activity must never reach a GitHub write path.

    The sentinel string below is what a malicious or merely unlucky existing
    comment looks like. If any future refactor lets `existingActivity` leak into
    the annotation list, one of these assertions fails.
    """

    SENTINEL = "SENTINEL-EXISTING-COMMENT-MUST-NOT-BE-POSTED"

    def test_normalizer_emits_no_annotation_fields(self):
        raw = _response(threads=[_thread(comments=[_comment(self.SENTINEL)])])
        activity = _normalize(raw)
        blob = json.dumps(activity)
        self.assertIn(self.SENTINEL, blob)
        for forbidden in ('"accepted"', '"origin"', '"scope"', '"suggestedCode"'):
            self.assertNotIn(forbidden, blob)

    def test_build_review_ignores_existing_activity_shaped_input(self):
        files = diff_anchor.parse_files([{
            "filename": "src/a.py", "status": "modified",
            "additions": 1, "deletions": 0,
            "patch": "@@ -1,2 +1,3 @@\n ctx\n+added\n ctx2\n",
        }])
        submission = {
            "kind": "review-annotations",
            "annotations": [{
                "id": "u-1", "scope": "line", "type": "comment",
                "filePath": "src/a.py", "lineStart": 2, "lineEnd": 2,
                "side": "RIGHT", "body": "my own comment",
                "origin": "user", "accepted": True,
            }],
            "existingActivity": _normalize(
                _response(threads=[_thread(
                    comments=[_comment(self.SENTINEL)])])),
        }
        annotations, general = build_review._extract_annotations(submission)
        result = build_review.build_payload(annotations, files, "sha123", body=general)
        blob = json.dumps(result)
        self.assertIn("my own comment", blob)
        self.assertNotIn(self.SENTINEL, blob)

    def test_build_review_rejects_unknown_origin(self):
        files = diff_anchor.parse_files([{
            "filename": "src/a.py", "status": "modified",
            "additions": 1, "deletions": 0,
            "patch": "@@ -1,2 +1,3 @@\n ctx\n+added\n ctx2\n",
        }])
        leaked = [{
            "id": "gh-1", "scope": "line", "type": "comment",
            "filePath": "src/a.py", "lineStart": 2, "lineEnd": 2,
            "side": "RIGHT", "body": self.SENTINEL,
            "origin": "github", "accepted": True,
        }]
        result = build_review.build_payload(leaked, files, "sha123")
        blob = json.dumps(result["payload"])
        self.assertNotIn(self.SENTINEL, blob)
        self.assertEqual(result["payload"]["comments"], [])
        self.assertTrue(any("origin" in w for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
