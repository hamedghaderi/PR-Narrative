#!/usr/bin/env python3
"""Diff-anchoring engine for the pr-narrative reviewer mode.

Pure parsing: given the JSON array returned by
`gh api repos/{o}/{r}/pulls/{n}/files`, this module walks each file's unified
`patch` into numbered hunk lines, computes the set of valid GitHub comment
anchors `(path, line, side)`, validates multi-line ranges, and emits the
"Diff JSON contract" the browser template consumes.

Standard library only; no pip installs, no network calls, no `gh` invocation —
the caller feeds it JSON. Usage:

    python3 diff_anchor.py --files-json /tmp/pr-<n>-files.json [--cap 30]

Line-anchoring rule (GitHub REST): `line` is the NEW-file line number for RIGHT
anchors (added + context lines) counted from the hunk header's newStart, and the
OLD-file line number for LEFT anchors (deleted lines) counted from oldStart.
The deprecated `position` field is never used anywhere.
"""

import argparse
import json
import re
import sys

HUNK_HEADER_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

DEFAULT_FILE_CAP = 30


def parse_patch(patch_text):
    """Parse a unified-diff patch fragment into a list of numbered hunks.

    Each hunk is `{header, oldStart, newStart, lines: [...]}` where every line
    is `{kind, oldLine, newLine, text}` with kind in {add, del, context}. Added
    lines carry newLine only, deleted lines oldLine only, context lines both.
    Line numbers restart from each hunk's own header, so adjacent hunks never
    share or double-count a number.
    """
    hunks = []
    if not patch_text:
        return hunks

    current = None
    old_no = new_no = 0
    for raw in patch_text.split("\n"):
        header = HUNK_HEADER_RE.match(raw)
        if header:
            old_start = int(header.group(1))
            new_start = int(header.group(3))
            current = {
                "header": raw,
                "oldStart": old_start,
                "newStart": new_start,
                "lines": [],
            }
            hunks.append(current)
            old_no = old_start
            new_no = new_start
            continue

        if current is None:
            continue

        if raw == "" or raw.startswith("\\"):
            continue

        marker, text = raw[0], raw[1:]
        if marker == "+":
            current["lines"].append(
                {"kind": "add", "oldLine": None, "newLine": new_no, "text": text})
            new_no += 1
        elif marker == "-":
            current["lines"].append(
                {"kind": "del", "oldLine": old_no, "newLine": None, "text": text})
            old_no += 1
        else:
            current["lines"].append(
                {"kind": "context", "oldLine": old_no, "newLine": new_no,
                 "text": text})
            old_no += 1
            new_no += 1

    return hunks


def parse_files(files_json):
    """Normalize the gh files payload into `{filename, ..., hunks}` records.

    Accepts either a JSON string or an already-decoded list. Each file keeps its
    NEW `filename`; `previous_filename` (present on renamed files) is
    deliberately ignored so anchors always key on the current path. A missing or
    null `patch` (binary, huge, or rename-only files) yields zero hunks rather
    than raising.
    """
    data = json.loads(files_json) if isinstance(files_json, str) else files_json

    files = []
    for entry in data:
        _ = entry.get("previous_filename")  # ignored on purpose: anchor on filename
        files.append({
            "filename": entry["filename"],
            "status": entry.get("status", "modified"),
            "additions": entry.get("additions", 0),
            "deletions": entry.get("deletions", 0),
            "patch": entry.get("patch"),
            "hunks": parse_patch(entry.get("patch")),
        })
    return files


def valid_anchors(files):
    """Return the set of valid `(path, line, side)` comment targets.

    RIGHT anchors are the new-file line numbers of added AND context lines;
    LEFT anchors are the old-file line numbers of deleted lines.
    """
    anchors = set()
    for f in files:
        path = f["filename"]
        for hunk in f["hunks"]:
            for ln in hunk["lines"]:
                if ln["kind"] in ("add", "context"):
                    anchors.add((path, ln["newLine"], "RIGHT"))
                if ln["kind"] == "del":
                    anchors.add((path, ln["oldLine"], "LEFT"))
    return anchors


def _hunk_line_set(hunk, side):
    if side == "RIGHT":
        return {ln["newLine"] for ln in hunk["lines"]
                if ln["kind"] in ("add", "context")}
    return {ln["oldLine"] for ln in hunk["lines"] if ln["kind"] == "del"}


def validate_range(files, path, start_line, end_line, side):
    """True iff every line in the range is a valid anchor on `side` AND the whole
    range lies within a single contiguous hunk. Cross-hunk ranges are rejected.
    """
    lo, hi = sorted((start_line, end_line))
    wanted = set(range(lo, hi + 1))
    for f in files:
        if f["filename"] != path:
            continue
        for hunk in f["hunks"]:
            if wanted <= _hunk_line_set(hunk, side):
                return True
    return False


def to_diff_json(files, cap=DEFAULT_FILE_CAP):
    """Emit the Diff JSON contract: first `cap` files fully rendered, the rest
    summarized in `overflowFiles`. Files without a patch are marked truncated.

    Accepts either the output of `parse_files` or the raw gh file list; it
    re-normalizes so callers need not parse first.
    """
    files = parse_files(files)
    rendered = []
    for f in files[:cap]:
        rendered.append({
            "filename": f["filename"],
            "status": f["status"],
            "additions": f["additions"],
            "deletions": f["deletions"],
            "hunks": f["hunks"],
            "truncated": not f.get("patch"),
        })

    overflow = []
    for f in files[cap:]:
        overflow.append({
            "filename": f["filename"],
            "additions": f["additions"],
            "deletions": f["deletions"],
            "url": "",
        })

    return {"files": rendered, "overflowFiles": overflow}


def main():
    ap = argparse.ArgumentParser(description="Parse a gh files JSON into diff JSON.")
    ap.add_argument("--files-json", required=True,
                    help="path to the JSON array from gh api .../pulls/{n}/files")
    ap.add_argument("--cap", type=int, default=DEFAULT_FILE_CAP,
                    help="max files rendered; the rest go to overflowFiles")
    args = ap.parse_args()

    with open(args.files_json, "r", encoding="utf-8") as fh:
        files = parse_files(fh.read())

    json.dump(to_diff_json(files, cap=args.cap), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
