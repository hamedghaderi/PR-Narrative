#!/usr/bin/env python3
"""GitHub pending-review payload builder for pr-narrative reviewer mode.

Turns the reviewer-mode submission annotations (contract §1/§3 of
`references/annotation-schema.md`) into the payload for
`POST /repos/{o}/{r}/pulls/{n}/reviews`, validating every line anchor against the
parsed diff via `scripts/diff_anchor.py`. The result is:

    { "payload": { "commit_id", "body", "comments": [...] }, "warnings": [...] }

The payload NEVER carries an `event` key: a review created with no event is a
PENDING review, which is the whole point. The user finalizes the verdict on
github.com. The deprecated `position` field is likewise never emitted.

Standard library only; no network calls, no `gh` invocation. The caller pipes the
printed JSON into `gh api ... --input -`. Usage:

    python3 build_review.py --annotations <path> --files-json <path> --commit-id <sha>
"""

import argparse
import json
import sys

import diff_anchor

MAX_BODY = 65535
TRUNCATE_SUFFIX = "\n[truncated]"
SUGGESTION_FENCE = "```suggestion"
# Must stay byte-identical to DISPROOF_LABEL in assets/review-template.html.
DISPROOF_LABEL = "**Smallest check that would prove this wrong:**"


def _truncate(body):
    if len(body) <= MAX_BODY:
        return body
    keep = MAX_BODY - len(TRUNCATE_SUFFIX)
    return body[:keep] + TRUNCATE_SUFFIX


def _first_valid_anchor(files, path):
    for f in files:
        if f["filename"] != path:
            continue
        for hunk in f["hunks"]:
            for ln in hunk["lines"]:
                if ln["kind"] in ("add", "context"):
                    return ln["newLine"], "RIGHT"
                if ln["kind"] == "del":
                    return ln["oldLine"], "LEFT"
    return None


def _details_block(text, summary):
    return "\n\n<details><summary>%s</summary>\n%s\n</details>" % (summary, text)


def _disproof_note(ann):
    if ann.get("origin") != "ai":
        return ""
    text = (ann.get("disproof") or "").strip()
    return DISPROOF_LABEL + " " + text if text else ""


def _background_block(ann):
    if ann.get("origin") != "ai":
        return ""
    text = (ann.get("background") or "").strip()
    return _details_block(text, "Background") if text else ""


def _assemble_comment_body(parts):
    block = parts[-1] if parts else ""
    base_parts = [part for part in parts[:-1] if part]
    base = "\n\n".join(base_parts).strip()
    if not block:
        return _truncate(base)
    if len(base) + len(block) <= MAX_BODY:
        return _truncate(base + block)
    return _truncate(base)


def _build_comment_body(ann, downgraded=False):
    body = ann.get("body") or ""
    note = _disproof_note(ann)
    if note:
        body = (body + "\n\n" + note).strip()
    if ann.get("type") == "suggestion" and ann.get("suggestedCode") is not None:
        code = ann["suggestedCode"]
        if downgraded:
            note = ("_Suggestion could not be applied to a deleted (LEFT-side) "
                    "line; showing the proposed code as a plain comment._")
            block = SUGGESTION_FENCE.replace("```suggestion", "```") + \
                "\n" + code + "\n```"
            body = (body + "\n\n" + note + "\n\n" + block).strip()
        else:
            body = (body + "\n\n" + SUGGESTION_FENCE + "\n" + code +
                    "\n```").strip()
    return body


def _build_comment_body_with_background(ann, downgraded=False, file_body=None):
    if file_body is not None:
        base_body = file_body
    else:
        base_body = _build_comment_body(ann, downgraded)
    return _assemble_comment_body([base_body, _background_block(ann)])


def _map_line_comment(ann, files, warnings):
    path = ann["filePath"]
    side = ann["side"]
    start = ann["lineStart"]
    end = ann["lineEnd"]

    if not diff_anchor.validate_range(files, path, start, end, side):
        warnings.append(
            "dropped annotation %s: anchor %s:%s-%s (%s) is not a valid range "
            "in the diff (outside hunks or cross-hunk)"
            % (ann.get("id"), path, start, end, side))
        return None

    downgraded = ann.get("type") == "suggestion" and side == "LEFT"
    comment = {"path": path, "body": _build_comment_body_with_background(ann, downgraded)}

    lo, hi = sorted((start, end))
    if lo == hi:
        comment["line"] = hi
        comment["side"] = side
    else:
        comment["start_line"] = lo
        comment["start_side"] = side
        comment["line"] = hi
        comment["side"] = side
    return comment


def _map_file_comment(ann, files, warnings):
    path = ann["filePath"]
    anchor = _first_valid_anchor(files, path)
    if anchor is None:
        warnings.append(
            "dropped file-level annotation %s: no valid anchor line found in "
            "%s" % (ann.get("id"), path))
        return None
    line, side = anchor
    body = "**File-level comment:**\n\n" + (ann.get("body") or "")
    note = _disproof_note(ann)
    if note:
        body = (body + "\n\n" + note).strip()
    return {"path": path, "line": line, "side": side,
            "body": _build_comment_body_with_background(ann, file_body=body)}


def build_payload(annotations, files, commit_id, body=""):
    """Assemble the pending-review payload from accepted annotations.

    `annotations`: list of annotation objects (contract §1). Only those with
    `accepted: true` are considered. `files`: output of `diff_anchor.parse_files`
    (or a raw gh files list, which is re-normalized). `commit_id`: the headRefOid
    the diff was generated against. `body`: the review-level lead text (usually the
    submission's `generalComment`).
    """
    files = diff_anchor.parse_files(files)

    warnings = []
    comments = []
    general_bodies = []

    for ann in annotations:
        if not ann.get("accepted"):
            continue

        scope = ann.get("scope")
        if scope == "general":
            general_bodies.append(ann.get("body") or "")
            continue
        if scope == "file":
            mapped = _map_file_comment(ann, files, warnings)
        else:
            mapped = _map_line_comment(ann, files, warnings)

        if mapped is not None:
            comments.append(mapped)

    review_body_parts = [p for p in ([body] + general_bodies) if p]
    review_body = _truncate("\n\n".join(review_body_parts))

    payload = {"commit_id": commit_id, "body": review_body, "comments": comments}
    return {"payload": payload, "warnings": warnings}


def _extract_annotations(loaded):
    if isinstance(loaded, dict) and "annotations" in loaded:
        return loaded["annotations"], loaded.get("generalComment", "")
    return loaded, ""


def main():
    ap = argparse.ArgumentParser(
        description="Build a GitHub pending-review payload from annotations.")
    ap.add_argument("--annotations", required=True,
                    help="path to a JSON annotations array or a full "
                         "review-annotations submission payload")
    ap.add_argument("--files-json", required=True,
                    help="path to the gh api .../pulls/{n}/files JSON")
    ap.add_argument("--commit-id", required=True,
                    help="headRefOid the diff was generated against")
    ap.add_argument("--body", default="",
                    help="optional review-level lead body; overridden by a "
                         "submission payload's generalComment when present")
    args = ap.parse_args()

    with open(args.annotations, "r", encoding="utf-8") as fh:
        loaded = json.load(fh)
    with open(args.files_json, "r", encoding="utf-8") as fh:
        files = diff_anchor.parse_files(fh.read())

    annotations, general = _extract_annotations(loaded)
    body = general if general else args.body

    result = build_payload(annotations, files, args.commit_id, body=body)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
