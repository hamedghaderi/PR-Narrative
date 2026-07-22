#!/usr/bin/env python3
"""Tests for scripts/build_review.py — the GitHub pending-review payload builder.

TDD: these tests are written FIRST and must fail before build_review.py exists
(RED), then pass once the module is implemented (GREEN). Stdlib unittest only.

The module under test turns the reviewer-mode server submission payload (the
`annotations` array, contract §1/§3 in references/annotation-schema.md) into a
GitHub pending-review payload `{ commit_id, body, comments: [...] }`, validating
every anchor against the parsed diff via `scripts/diff_anchor.py`. It NEVER emits
an `event` key (a review with no event is PENDING) and NEVER emits the deprecated
`position` field.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

# Make `scripts/` importable regardless of the discover cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import build_review  # noqa: E402
import diff_anchor  # noqa: E402


# A patch that gives us RIGHT anchors on new lines 10..17 and a LEFT anchor on
# old line 12, matching the annotation-schema worked example (formatDate.js).
FORMAT_DATE_PATCH = (
    "@@ -10,6 +10,8 @@\n"
    " function formatDate(d) {\n"
    "   if (!d) return '';\n"
    "-  const date = new Date(d);\n"
    "+  const date = new Date(d);\n"
    "+  if (Number.isNaN(date.getTime())) {\n"
    "+    throw new Error(`Invalid date: ${d}`);\n"
    "+  }\n"
    "   return date.toISOString().split('T')[0];\n"
    " }\n"
)

# A second, separate hunk in the same file so we can build a cross-hunk range.
TWO_HUNK_PATCH = (
    "@@ -10,3 +10,4 @@\n"
    " a\n"
    "+b\n"
    " c\n"
    " d\n"
    "@@ -40,2 +41,3 @@\n"
    " e\n"
    "+f\n"
    " g\n"
)


def _file(filename, patch, status="modified", additions=1, deletions=1):
    return {
        "filename": filename,
        "status": status,
        "additions": additions,
        "deletions": deletions,
        "patch": patch,
    }


def _ann(**kw):
    """Build an annotation dict with sane defaults, overridable via kwargs."""
    base = {
        "id": "x-1",
        "scope": "line",
        "type": "comment",
        "filePath": "src/utils/formatDate.js",
        "lineStart": 10,
        "lineEnd": 10,
        "side": "RIGHT",
        "body": "hi",
        "origin": "user",
        "accepted": True,
    }
    base.update(kw)
    return base


def _files():
    return diff_anchor.parse_files([_file("src/utils/formatDate.js",
                                          FORMAT_DATE_PATCH)])


class AcceptedFilteringTests(unittest.TestCase):
    def test_accepted_only_filtering(self):
        """AI accepted:false excluded; user annotation (accepted:true) included."""
        anns = [
            _ann(id="a-1", origin="user", accepted=True, lineStart=10,
                 lineEnd=10),
            _ann(id="a-2", origin="ai", accepted=False, lineStart=13,
                 lineEnd=13, severity="important", reasoning="risky"),
        ]
        result = build_review.build_payload(anns, _files(),
                                            "deadbeef", body="")
        comments = result["payload"]["comments"]
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["path"], "src/utils/formatDate.js")

    def test_accepted_ai_annotation_is_included(self):
        """AI annotation with accepted:true IS included (user triaged it in)."""
        anns = [_ann(id="a-2", origin="ai", accepted=True, lineStart=13,
                     lineEnd=13, severity="important", reasoning="risky")]
        result = build_review.build_payload(anns, _files(),
                                            "deadbeef", body="")
        self.assertEqual(len(result["payload"]["comments"]), 1)


class MappingTests(unittest.TestCase):
    def test_single_line_field_set(self):
        """single-line mapping produces line + side, no start_line/start_side."""
        anns = [_ann(lineStart=13, lineEnd=13, side="RIGHT")]
        c = build_review.build_payload(anns, _files(), "sha")["payload"]["comments"][0]
        self.assertEqual(c["path"], "src/utils/formatDate.js")
        self.assertEqual(c["line"], 13)
        self.assertEqual(c["side"], "RIGHT")
        self.assertNotIn("start_line", c)
        self.assertNotIn("start_side", c)
        self.assertNotIn("position", c)

    def test_multi_line_field_set(self):
        """multi-line mapping produces start_line+start_side+line+side."""
        anns = [_ann(lineStart=13, lineEnd=15, side="RIGHT")]
        c = build_review.build_payload(anns, _files(), "sha")["payload"]["comments"][0]
        self.assertEqual(c["start_line"], 13)
        self.assertEqual(c["start_side"], "RIGHT")
        self.assertEqual(c["line"], 15)
        self.assertEqual(c["side"], "RIGHT")
        self.assertNotIn("position", c)


class GeneralScopeTests(unittest.TestCase):
    def test_general_scope_merges_into_body_not_comments(self):
        """general-scope → review body, never a comments[] entry."""
        anns = [
            _ann(id="g", scope="general", type="comment", filePath=None,
                 lineStart=None, lineEnd=None, side=None,
                 body="overall this is fine", origin="user", accepted=True),
        ]
        result = build_review.build_payload(anns, _files(), "sha",
                                            body="lead body")
        self.assertEqual(result["payload"]["comments"], [])
        self.assertIn("overall this is fine", result["payload"]["body"])
        self.assertIn("lead body", result["payload"]["body"])


class FileScopeTests(unittest.TestCase):
    def test_file_scope_first_valid_anchor_prefixed_body(self):
        """file-scope → first valid anchor line, body prefixed File-level comment."""
        anns = [
            _ann(id="f", scope="file", type="comment",
                 filePath="src/utils/formatDate.js",
                 lineStart=None, lineEnd=None, side=None,
                 body="whole-file note", origin="user", accepted=True),
        ]
        c = build_review.build_payload(anns, _files(), "sha")["payload"]["comments"][0]
        # First RIGHT anchor in the patch is new line 10 (context "function...").
        self.assertEqual(c["line"], 10)
        self.assertEqual(c["side"], "RIGHT")
        self.assertIn("**File-level comment:**", c["body"])
        self.assertIn("whole-file note", c["body"])


class SuggestionTests(unittest.TestCase):
    def test_suggestion_on_right_produces_fence(self):
        """suggestion on RIGHT → ```suggestion fenced block appended to body."""
        anns = [
            _ann(id="s", type="suggestion", lineStart=13, lineEnd=15,
                 side="RIGHT", body="prefer returning ''",
                 suggestedCode="  return '';"),
        ]
        c = build_review.build_payload(anns, _files(), "sha")["payload"]["comments"][0]
        self.assertIn("```suggestion", c["body"])
        self.assertIn("  return '';", c["body"])
        self.assertIn("```", c["body"])
        self.assertIn("prefer returning ''", c["body"])

    def test_suggestion_on_left_downgraded_to_comment(self):
        """suggestion on LEFT → downgraded to plain comment with a note, no fence."""
        anns = [
            _ann(id="s", type="suggestion", lineStart=12, lineEnd=12,
                 side="LEFT", body="cannot suggest here",
                 suggestedCode="  return '';"),
        ]
        result = build_review.build_payload(anns, _files(), "sha")
        c = result["payload"]["comments"][0]
        self.assertNotIn("```suggestion", c["body"])
        self.assertIn("cannot suggest here", c["body"])
        # A note explaining the downgrade should be present.
        self.assertTrue(
            "suggestion" in c["body"].lower() or
            any("suggest" in w.lower() for w in result["warnings"]),
            "expected a downgrade note in body or a warning")


class InvalidAnchorTests(unittest.TestCase):
    def test_invalid_anchor_dropped_with_warning(self):
        """invalid anchor (line outside hunks) → dropped + warning; payload valid."""
        anns = [_ann(id="bad", lineStart=999, lineEnd=999, side="RIGHT")]
        result = build_review.build_payload(anns, _files(), "sha")
        self.assertEqual(result["payload"]["comments"], [])
        self.assertEqual(len(result["warnings"]), 1)
        # Payload still structurally valid.
        self.assertIn("commit_id", result["payload"])
        self.assertIn("comments", result["payload"])

    def test_cross_hunk_range_dropped_with_warning(self):
        """cross-hunk range → dropped + warning, payload still valid."""
        files = diff_anchor.parse_files([_file("m.py", TWO_HUNK_PATCH)])
        # Hunk 1 covers new lines 10..13; hunk 2 covers 41..43. 11->42 is cross-hunk.
        anns = [_ann(id="cross", filePath="m.py", lineStart=11, lineEnd=42,
                     side="RIGHT")]
        result = build_review.build_payload(anns, files, "sha")
        self.assertEqual(result["payload"]["comments"], [])
        self.assertEqual(len(result["warnings"]), 1)


class TruncationTests(unittest.TestCase):
    def test_body_boundary_truncation(self):
        """body at exactly 65,536 chars → truncated to 65,535 with [truncated]."""
        big = "x" * 65536
        anns = [_ann(id="big", lineStart=13, lineEnd=13, side="RIGHT",
                     body=big)]
        c = build_review.build_payload(anns, _files(), "sha")["payload"]["comments"][0]
        self.assertEqual(len(c["body"]), 65535)
        self.assertTrue(c["body"].endswith("\n[truncated]"))

    def test_body_under_limit_untouched(self):
        anns = [_ann(id="ok", lineStart=13, lineEnd=13, side="RIGHT",
                     body="short")]
        c = build_review.build_payload(anns, _files(), "sha")["payload"]["comments"][0]
        self.assertEqual(c["body"], "short")

    def test_review_body_truncated_too(self):
        """review-level body also truncated at the 65,535 boundary."""
        result = build_review.build_payload([], _files(), "sha",
                                            body="y" * 100000)
        self.assertEqual(len(result["payload"]["body"]), 65535)
        self.assertTrue(result["payload"]["body"].endswith("\n[truncated]"))


class NoEventKeyTests(unittest.TestCase):
    def test_event_key_never_present(self):
        """`event` key never present in output payload (pending review)."""
        anns = [_ann(id="a-1", lineStart=13, lineEnd=13, side="RIGHT")]
        result = build_review.build_payload(anns, _files(), "sha", body="x")
        self.assertNotIn("event", result["payload"])
        # Exact key set of the payload.
        self.assertEqual(set(result["payload"].keys()),
                         {"commit_id", "body", "comments"})

    def test_commit_id_passed_through(self):
        result = build_review.build_payload([], _files(), "abc123")
        self.assertEqual(result["payload"]["commit_id"], "abc123")


class RoundTripTests(unittest.TestCase):
    def test_output_json_roundtrips(self):
        """output JSON is valid against a json.loads round-trip."""
        anns = [
            _ann(id="a-1", lineStart=13, lineEnd=13, side="RIGHT"),
            _ann(id="g", scope="general", filePath=None, lineStart=None,
                 lineEnd=None, side=None, body="general note"),
        ]
        result = build_review.build_payload(anns, _files(), "sha",
                                            body="lead")
        dumped = json.dumps(result)
        self.assertEqual(json.loads(dumped), result)


class CliTests(unittest.TestCase):
    def test_cli_smoke(self):
        """CLI: --annotations + --files-json + --commit-id → result JSON on stdout."""
        anns = [
            _ann(id="a-1", lineStart=13, lineEnd=13, side="RIGHT",
                 body="user comment"),
            _ann(id="a-2", origin="ai", accepted=False, lineStart=14,
                 lineEnd=14, side="RIGHT", body="ai draft"),
        ]
        files_list = [_file("src/utils/formatDate.js", FORMAT_DATE_PATCH)]
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as afh:
            json.dump(anns, afh)
            anns_path = afh.name
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as ffh:
            json.dump(files_list, ffh)
            files_path = ffh.name
        try:
            script = os.path.join(_SCRIPTS, "build_review.py")
            out = subprocess.check_output([
                sys.executable, script,
                "--annotations", anns_path,
                "--files-json", files_path,
                "--commit-id", "cafebabe",
            ])
            data = json.loads(out.decode("utf-8"))
            self.assertIn("payload", data)
            self.assertIn("warnings", data)
            self.assertNotIn("event", data["payload"])
            self.assertEqual(data["payload"]["commit_id"], "cafebabe")
            # Only the accepted user comment survives filtering.
            self.assertEqual(len(data["payload"]["comments"]), 1)
        finally:
            os.unlink(anns_path)
            os.unlink(files_path)

    def test_cli_accepts_full_submission_payload(self):
        """CLI --annotations may point at a full {kind, annotations, ...} payload."""
        submission = {
            "kind": "review-annotations",
            "mode": "pr",
            "repo": "acme/x",
            "prNumber": 1,
            "branch": "b",
            "generalComment": "overall LGTM",
            "annotations": [
                _ann(id="a-1", lineStart=13, lineEnd=13, side="RIGHT",
                     body="c"),
            ],
        }
        files_list = [_file("src/utils/formatDate.js", FORMAT_DATE_PATCH)]
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as afh:
            json.dump(submission, afh)
            anns_path = afh.name
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as ffh:
            json.dump(files_list, ffh)
            files_path = ffh.name
        try:
            script = os.path.join(_SCRIPTS, "build_review.py")
            out = subprocess.check_output([
                sys.executable, script,
                "--annotations", anns_path,
                "--files-json", files_path,
                "--commit-id", "sha",
            ])
            data = json.loads(out.decode("utf-8"))
            # generalComment folded into review body.
            self.assertIn("overall LGTM", data["payload"]["body"])
            self.assertEqual(len(data["payload"]["comments"]), 1)
        finally:
            os.unlink(anns_path)
            os.unlink(files_path)


if __name__ == "__main__":
    unittest.main()
