#!/usr/bin/env python3
"""Tests for scripts/diff_anchor.py — the diff-anchoring engine.

TDD: these tests are written FIRST and must fail before diff_anchor.py exists
(RED), then pass once the module is implemented (GREEN). Stdlib unittest only.

The module under test parses the JSON array returned by
`gh api repos/{o}/{r}/pulls/{n}/files`, walks each file's unified-diff `patch`
into numbered hunk lines, and exposes anchor-validation + diff-JSON emission.
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

import diff_anchor  # noqa: E402


MULTI_HUNK_PATCH = (
    "@@ -1,3 +1,4 @@\n"
    " context a\n"
    "-old line\n"
    "+new line 1\n"
    "+new line 2\n"
    " context b\n"
    "@@ -20,2 +21,3 @@\n"
    " context c\n"
    "+added tail\n"
    " context d\n"
)

ADJACENT_HUNK_PATCH = (
    "@@ -1,2 +1,2 @@\n"
    " keep 1\n"
    "-drop 2\n"
    "+add 2\n"
    "@@ -3,2 +3,3 @@\n"
    " keep 3\n"
    "+add 3b\n"
    " keep 4\n"
)

DELETE_ONLY_PATCH = (
    "@@ -10,3 +10,1 @@\n"
    " ctx keep\n"
    "-removed one\n"
    "-removed two\n"
)

SHORT_HEADER_PATCH = (
    "@@ -1 +1 @@\n"
    "-only old\n"
    "+only new\n"
)


def _file(filename, patch, status="modified", additions=1, deletions=1,
          previous_filename=None):
    obj = {
        "filename": filename,
        "status": status,
        "additions": additions,
        "deletions": deletions,
        "patch": patch,
    }
    if previous_filename is not None:
        obj["previous_filename"] = previous_filename
    return obj


class ParsePatchTests(unittest.TestCase):
    def test_happy_path_multi_hunk_numbering(self):
        """happy-path multi-hunk patch → correct old/new numbering."""
        hunks = diff_anchor.parse_patch(MULTI_HUNK_PATCH)
        self.assertEqual(len(hunks), 2)

        h1 = hunks[0]
        self.assertEqual(h1["oldStart"], 1)
        self.assertEqual(h1["newStart"], 1)
        kinds = [ln["kind"] for ln in h1["lines"]]
        self.assertEqual(kinds, ["context", "del", "add", "add", "context"])

        by_text = {ln["text"]: ln for ln in h1["lines"]}
        self.assertEqual(by_text["context a"]["oldLine"], 1)
        self.assertEqual(by_text["context a"]["newLine"], 1)
        self.assertEqual(by_text["old line"]["oldLine"], 2)
        self.assertIsNone(by_text["old line"]["newLine"])
        self.assertEqual(by_text["new line 1"]["newLine"], 2)
        self.assertIsNone(by_text["new line 1"]["oldLine"])
        self.assertEqual(by_text["new line 2"]["newLine"], 3)
        self.assertEqual(by_text["context b"]["oldLine"], 3)
        self.assertEqual(by_text["context b"]["newLine"], 4)

        h2 = hunks[1]
        self.assertEqual(h2["oldStart"], 20)
        self.assertEqual(h2["newStart"], 21)
        by_text2 = {ln["text"]: ln for ln in h2["lines"]}
        self.assertEqual(by_text2["context c"]["oldLine"], 20)
        self.assertEqual(by_text2["context c"]["newLine"], 21)
        self.assertEqual(by_text2["added tail"]["newLine"], 22)
        self.assertIsNone(by_text2["added tail"]["oldLine"])
        self.assertEqual(by_text2["context d"]["oldLine"], 21)
        self.assertEqual(by_text2["context d"]["newLine"], 23)

    def test_adjacent_hunks_do_not_double_count(self):
        """adjacent hunks don't double-count line numbers."""
        hunks = diff_anchor.parse_patch(ADJACENT_HUNK_PATCH)
        self.assertEqual(len(hunks), 2)
        new_nums = []
        old_nums = []
        for h in hunks:
            for ln in h["lines"]:
                if ln["newLine"] is not None:
                    new_nums.append(ln["newLine"])
                if ln["oldLine"] is not None:
                    old_nums.append(ln["oldLine"])
        self.assertEqual(len(new_nums), len(set(new_nums)),
                         "newLine numbers double-counted across adjacent hunks")
        self.assertEqual(len(old_nums), len(set(old_nums)),
                         "oldLine numbers double-counted across adjacent hunks")

    def test_short_header_form_parses(self):
        """`@@ -1 +1 @@` short header form parses correctly."""
        hunks = diff_anchor.parse_patch(SHORT_HEADER_PATCH)
        self.assertEqual(len(hunks), 1)
        h = hunks[0]
        self.assertEqual(h["oldStart"], 1)
        self.assertEqual(h["newStart"], 1)
        by_text = {ln["text"]: ln for ln in h["lines"]}
        self.assertEqual(by_text["only old"]["oldLine"], 1)
        self.assertIsNone(by_text["only old"]["newLine"])
        self.assertEqual(by_text["only new"]["newLine"], 1)
        self.assertIsNone(by_text["only new"]["oldLine"])


class ParseFilesTests(unittest.TestCase):
    def test_binary_or_missing_patch_yields_empty_hunks(self):
        """binary/missing patch → empty hunks, no exception."""
        files_json = json.dumps([
            {"filename": "logo.png", "status": "added",
             "additions": 0, "deletions": 0},
            {"filename": "huge.bin", "status": "modified",
             "additions": 0, "deletions": 0, "patch": None},
        ])
        files = diff_anchor.parse_files(files_json)
        self.assertEqual(len(files), 2)
        for f in files:
            self.assertEqual(f["hunks"], [])

    def test_renamed_file_keyed_by_filename_not_previous(self):
        """renamed file with previous_filename present → anchors keyed by filename."""
        files_json = json.dumps([
            _file("src/new_name.py", SHORT_HEADER_PATCH, status="renamed",
                  previous_filename="src/old_name.py"),
        ])
        files = diff_anchor.parse_files(files_json)
        self.assertEqual(files[0]["filename"], "src/new_name.py")
        anchors = diff_anchor.valid_anchors(files)
        paths = {path for (path, line, side) in anchors}
        self.assertIn("src/new_name.py", paths)
        self.assertNotIn("src/old_name.py", paths)

    def test_parse_files_accepts_already_parsed_list(self):
        """parse_files also accepts an already-decoded list (convenience)."""
        parsed = [_file("a.py", SHORT_HEADER_PATCH)]
        files = diff_anchor.parse_files(parsed)
        self.assertEqual(files[0]["filename"], "a.py")
        self.assertEqual(len(files[0]["hunks"]), 1)


class ValidAnchorTests(unittest.TestCase):
    def test_delete_only_file_left_anchors_only(self):
        """deleted-only file → LEFT anchors only, no RIGHT for deleted lines."""
        files = diff_anchor.parse_files([_file("d.py", DELETE_ONLY_PATCH)])
        anchors = diff_anchor.valid_anchors(files)
        sides = {side for (_p, _l, side) in anchors}
        # oldStart=10: "ctx keep"=10, "removed one"=11, "removed two"=12.
        self.assertIn(("d.py", 11, "LEFT"), anchors)
        self.assertIn(("d.py", 12, "LEFT"), anchors)
        self.assertNotIn(("d.py", 11, "RIGHT"), anchors)
        self.assertNotIn(("d.py", 12, "RIGHT"), anchors)
        self.assertIn("LEFT", sides)

    def test_context_line_valid_right_anchor_outside_invalid(self):
        """context line inside hunk → valid RIGHT anchor; line outside → invalid."""
        files = diff_anchor.parse_files([_file("m.py", MULTI_HUNK_PATCH)])
        anchors = diff_anchor.valid_anchors(files)
        # "context a"=new line 1, "context b"=new line 4 (both context anchors).
        self.assertIn(("m.py", 1, "RIGHT"), anchors)
        self.assertIn(("m.py", 4, "RIGHT"), anchors)
        self.assertNotIn(("m.py", 100, "RIGHT"), anchors)

    def test_added_line_is_right_anchor(self):
        files = diff_anchor.parse_files([_file("m.py", MULTI_HUNK_PATCH)])
        anchors = diff_anchor.valid_anchors(files)
        # "+new line 1"=new line 2, "+new line 2"=new line 3.
        self.assertIn(("m.py", 2, "RIGHT"), anchors)
        self.assertIn(("m.py", 3, "RIGHT"), anchors)


class ValidateRangeTests(unittest.TestCase):
    def test_same_hunk_multiline_true_cross_hunk_false(self):
        """cross-hunk range → False; same-hunk multi-line → True."""
        files = diff_anchor.parse_files([_file("m.py", MULTI_HUNK_PATCH)])
        # Hunk 1 covers new lines 1..4; hunk 2 covers 21..23.
        self.assertTrue(
            diff_anchor.validate_range(files, "m.py", 1, 4, "RIGHT"))
        self.assertFalse(
            diff_anchor.validate_range(files, "m.py", 1, 22, "RIGHT"))

    def test_single_valid_line_true(self):
        files = diff_anchor.parse_files([_file("m.py", MULTI_HUNK_PATCH)])
        self.assertTrue(
            diff_anchor.validate_range(files, "m.py", 2, 2, "RIGHT"))

    def test_range_with_invalid_line_false(self):
        files = diff_anchor.parse_files([_file("m.py", MULTI_HUNK_PATCH)])
        # new line 5 is outside hunk 1's range (1..4).
        self.assertFalse(
            diff_anchor.validate_range(files, "m.py", 4, 5, "RIGHT"))

    def test_reversed_range_normalized(self):
        files = diff_anchor.parse_files([_file("m.py", MULTI_HUNK_PATCH)])
        self.assertTrue(
            diff_anchor.validate_range(files, "m.py", 4, 1, "RIGHT"))


class ToDiffJsonTests(unittest.TestCase):
    def test_file_cap_overflow(self):
        """file cap: 31 files in → 30 rendered + 1 in overflowFiles."""
        many = [_file("f%02d.py" % i, SHORT_HEADER_PATCH) for i in range(31)]
        diff = diff_anchor.to_diff_json(many, cap=30)
        self.assertEqual(len(diff["files"]), 30)
        self.assertEqual(len(diff["overflowFiles"]), 1)
        self.assertEqual(diff["overflowFiles"][0]["filename"], "f30.py")
        of = diff["overflowFiles"][0]
        self.assertIn("additions", of)
        self.assertIn("deletions", of)
        self.assertIn("url", of)

    def test_truncated_marked_for_no_patch(self):
        files = [
            {"filename": "logo.png", "status": "added",
             "additions": 0, "deletions": 0},
            _file("a.py", SHORT_HEADER_PATCH),
        ]
        diff = diff_anchor.to_diff_json(files, cap=30)
        by_name = {f["filename"]: f for f in diff["files"]}
        self.assertTrue(by_name["logo.png"]["truncated"])
        self.assertFalse(by_name["a.py"]["truncated"])

    def test_per_file_contract_shape(self):
        diff = diff_anchor.to_diff_json([_file("a.py", MULTI_HUNK_PATCH)],
                                        cap=30)
        f = diff["files"][0]
        for key in ("filename", "status", "additions", "deletions",
                    "hunks", "truncated"):
            self.assertIn(key, f)
        h = f["hunks"][0]
        for key in ("header", "oldStart", "newStart", "lines"):
            self.assertIn(key, h)
        ln = h["lines"][0]
        for key in ("kind", "oldLine", "newLine", "text"):
            self.assertIn(key, ln)

    def test_top_level_diff_json_roundtrips(self):
        diff = diff_anchor.to_diff_json([_file("a.py", MULTI_HUNK_PATCH)])
        self.assertEqual(json.loads(json.dumps(diff)), diff)


class CliTests(unittest.TestCase):
    def test_cli_emits_files_and_overflow(self):
        many = [_file("f%02d.py" % i, SHORT_HEADER_PATCH) for i in range(31)]
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False) as fh:
            json.dump(many, fh)
            fixture = fh.name
        try:
            script = os.path.join(_SCRIPTS, "diff_anchor.py")
            out = subprocess.check_output(
                [sys.executable, script, "--files-json", fixture, "--cap", "30"])
            data = json.loads(out.decode("utf-8"))
            self.assertIn("files", data)
            self.assertIn("overflowFiles", data)
            self.assertEqual(len(data["files"]), 30)
            self.assertEqual(len(data["overflowFiles"]), 1)
        finally:
            os.unlink(fixture)


if __name__ == "__main__":
    unittest.main()
