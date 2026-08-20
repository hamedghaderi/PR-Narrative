#!/usr/bin/env python3
"""Existing-review-activity normalizer for the pr-narrative reviewer mode.

Pure normalization: given the JSON returned by the read-only GraphQL query in
`references/github-posting.md` ("Fetch existing review activity"), this module
flattens review threads, their replies, the submitted review summaries, and the
PR's non-inline conversation comments into the `existingActivity` object the
browser template consumes (`references/annotation-schema.md` §2a).

Standard library only; no pip installs, no network calls, no `gh` invocation.
The caller feeds it JSON, exactly like `scripts/diff_anchor.py`. Usage:

    python3 existing_activity.py --activity-json /tmp/pr-<n>-activity.json \
        [--head-ref-oid <sha>] [--allow-host github.example.com]

Three rules drive every decision in here, and all three exist because this data
is READ-ONLY third-party text that must never be mistaken for the reviewer's own
draft:

1. **Nothing here is ever submittable.** This module emits no `annotation`
   objects and no `accepted` field. `existingActivity` is a sibling of
   `aiAnnotations` in the page data, never merged into it, so the submit path
   (`buildPayload()` in the template, then `scripts/build_review.py`) cannot see
   it. See the invariant test in `scripts/tests/test_existing_activity.py`.

2. **`originalLine` is not a current line.** GitHub reports `line: null` on a
   thread whose anchor no longer exists in the current diff, keeping the
   historical position in `originalLine`. Anchoring a card at `originalLine`
   would silently attach old feedback to whatever code now occupies that number.
   Both are carried through; only `line` may be used to anchor.

3. **"Outdated" is not "handled".** `isOutdated` says the code moved;
   `isResolved` says a human closed the thread. An unresolved-but-outdated
   thread is still open feedback. They are kept as two independent booleans and
   never collapsed into one "stale" flag.
"""

import argparse
import datetime
import json
import sys
from urllib.parse import urlsplit

# Caps. Counts alone are not enough: one pathological thread can carry more text
# than fifty ordinary ones, so a byte budget backstops every count below.
DEFAULT_THREAD_CAP = 50
DEFAULT_COMMENT_CAP = 100
DEFAULT_COMMENTS_PER_THREAD = 10
DEFAULT_BODY_CHARS = 4000
DEFAULT_TOTAL_BODY_CHARS = 120000

BODY_TRUNCATION_MARKER = "\n[truncated - open the thread on GitHub to read the rest]"

# Only https URLs on a known host survive into the page. Everything in this
# payload is attacker-influenced text, and the template renders these straight
# into href attributes; an unchecked `javascript:` or off-host URL would turn a
# review comment into a clickable payload.
DEFAULT_ALLOWED_HOSTS = ("github.com", "www.github.com")

# A submitted review with an empty body and state COMMENTED is the invisible
# container GitHub creates to hold inline comments. Its comments are already
# rendered as threads, so surfacing the empty husk as "someone reviewed this"
# would be noise. PENDING is excluded for a different reason: it is the viewer's
# own unsubmitted draft, not previous activity, and the reviewer-mode preflight
# in references/github-posting.md §2 already forces a REPLACE/ABORT decision.
_NOISE_REVIEW_STATE = "COMMENTED"
_PENDING_REVIEW_STATE = "PENDING"

STATUS_COMPLETE = "complete"
STATUS_PARTIAL = "partial"
STATUS_UNAVAILABLE = "unavailable"


def load_documents(text):
    """Parse whatever `gh api graphql` printed into a list of page objects.

    `gh` emits three different shapes depending on the flags used, and the
    playbook should not have to care which: a single JSON object (no
    `--paginate`), a JSON array of pages (`--paginate --slurp`), or several
    concatenated top-level objects (`--paginate` alone). Concatenated objects
    are not valid JSON as a whole, so they are decoded one at a time.
    """
    if isinstance(text, (list, dict)):
        return text if isinstance(text, list) else [text]

    stripped = text.strip()
    if not stripped:
        return []

    try:
        loaded = json.loads(stripped)
    except ValueError:
        pass
    else:
        return loaded if isinstance(loaded, list) else [loaded]

    decoder = json.JSONDecoder()
    documents = []
    index = 0
    length = len(stripped)
    while index < length:
        while index < length and stripped[index] in " \t\r\n":
            index += 1
        if index >= length:
            break
        obj, end = decoder.raw_decode(stripped, index)
        documents.append(obj)
        index = end
    return documents


def _dig(node, *path):
    """Walk a chain of dict keys, returning None the moment one is missing.

    GraphQL nulls out an entire subtree when a field errors, so every level here
    can legitimately be None on a response that still carries useful data.
    """
    current = node
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _nodes(connection):
    value = _dig(connection, "nodes")
    return [n for n in value if isinstance(n, dict)] if isinstance(value, list) else []


def merge_pages(documents):
    """Fold paginated GraphQL pages into one pull-request view.

    Only `reviewThreads` is paginated by the playbook's query, so thread nodes
    accumulate across pages while the scalar fields and the un-paginated
    connections are taken from the first page that actually carries them.

    Returns `(pull_request, errors, truncated_by_pagination)`. `errors` collects
    every GraphQL `errors` member seen: a GraphQL response can be HTTP 200 and
    still be missing half its data, which is the case this exists to catch.
    """
    pull_request = None
    threads = []
    errors = []
    truncated_by_pagination = False

    for document in documents:
        if not isinstance(document, dict):
            continue

        document_errors = document.get("errors")
        if isinstance(document_errors, list):
            errors.extend(e for e in document_errors if e is not None)

        pr = _dig(document, "data", "repository", "pullRequest")
        if not isinstance(pr, dict):
            continue

        if pull_request is None:
            pull_request = dict(pr)

        threads.extend(_nodes(pr.get("reviewThreads")))

        page_info = _dig(pr, "reviewThreads", "pageInfo")
        if isinstance(page_info, dict):
            truncated_by_pagination = bool(page_info.get("hasNextPage"))

        for key in ("reviews", "comments"):
            if not _nodes(pull_request.get(key)) and _nodes(pr.get(key)):
                pull_request[key] = pr.get(key)
        if not pull_request.get("headRefOid") and pr.get("headRefOid"):
            pull_request["headRefOid"] = pr.get("headRefOid")

    if pull_request is not None:
        pull_request["reviewThreads"] = {"nodes": threads}

    return pull_request, errors, truncated_by_pagination


def _safe_url(value, allowed_hosts):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme != "https":
        return None
    host = parsed.hostname
    if host is None or host.lower() not in allowed_hosts:
        return None
    return value


def _login(actor):
    """A GitHub actor is null for a deleted account; the page shows "unknown"."""
    login = _dig(actor, "login")
    return login if isinstance(login, str) and login else None


def _text(value):
    return value if isinstance(value, str) else ""


def _truncate_body(body, limit):
    if len(body) <= limit:
        return body, False
    keep = max(0, limit - len(BODY_TRUNCATION_MARKER))
    return body[:keep] + BODY_TRUNCATION_MARKER, True


def _int_or_none(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _normalize_comment(node, allowed_hosts, body_chars):
    body, truncated = _truncate_body(_text(node.get("body")), body_chars)
    return {
        "id": node.get("id") if isinstance(node.get("id"), str) else None,
        "author": _login(node.get("author")),
        "authorAssociation": node.get("authorAssociation")
        if isinstance(node.get("authorAssociation"), str) else None,
        "body": body,
        "bodyTruncated": truncated,
        "createdAt": node.get("createdAt") if isinstance(node.get("createdAt"), str) else None,
        "url": _safe_url(node.get("url"), allowed_hosts),
    }


def _side(value):
    return value if value in ("LEFT", "RIGHT") else None


def _normalize_thread(node, allowed_hosts, body_chars, comments_per_thread):
    """Flatten one `PullRequestReviewThread` node.

    `line` and `startLine` are the CURRENT anchor and may be null; `originalLine`
    and `originalStartLine` are historical and are carried for display only.
    `subjectType` distinguishes a line thread from a file-level one, which has no
    line at all and must not be treated as an unanchorable line thread.
    """
    comment_nodes = _nodes(node.get("comments"))
    kept = comment_nodes
    omitted = 0
    if len(comment_nodes) > comments_per_thread:
        # Root first, then the newest replies: the root states the concern and
        # the tail carries the resolution. Dropping from the middle keeps both
        # halves of the conversation the reviewer actually needs.
        tail_size = comments_per_thread - 1
        kept = [comment_nodes[0]] + comment_nodes[len(comment_nodes) - tail_size:]
        omitted = len(comment_nodes) - len(kept)

    subject_type = node.get("subjectType")
    thread = {
        "id": node.get("id") if isinstance(node.get("id"), str) else None,
        "isResolved": bool(node.get("isResolved")),
        "isOutdated": bool(node.get("isOutdated")),
        "isCollapsed": bool(node.get("isCollapsed")),
        "resolvedBy": _login(node.get("resolvedBy")),
        "subjectType": subject_type if isinstance(subject_type, str) else None,
        "filePath": node.get("path") if isinstance(node.get("path"), str) else None,
        "side": _side(node.get("diffSide")),
        "startSide": _side(node.get("startDiffSide")),
        "line": _int_or_none(node.get("line")),
        "startLine": _int_or_none(node.get("startLine")),
        "originalLine": _int_or_none(node.get("originalLine")),
        "originalStartLine": _int_or_none(node.get("originalStartLine")),
        "commentsOmitted": omitted,
        "comments": [_normalize_comment(c, allowed_hosts, body_chars) for c in kept],
    }
    first_url = thread["comments"][0]["url"] if thread["comments"] else None
    thread["url"] = first_url
    return thread


def _thread_rank(thread):
    """Selection priority when more threads exist than the cap allows.

    Open feedback outranks closed feedback, and an unresolved-but-outdated
    thread is still open, so it outranks anything resolved.
    """
    if not thread["isResolved"] and not thread["isOutdated"]:
        return 0
    if not thread["isResolved"]:
        return 1
    return 2


def _apply_budgets(threads, thread_cap, comment_cap, total_body_chars):
    """Trim to the caps, keeping the most important threads.

    Returns `(kept_threads, truncation)`. Selection happens by rank, but the
    surviving threads are emitted in their original order so the page's layout
    does not reshuffle between runs.
    """
    ordered = sorted(
        range(len(threads)), key=lambda i: (_thread_rank(threads[i]), i))

    selected = []
    comments_used = 0
    chars_used = 0
    comments_omitted = sum(t["commentsOmitted"] for t in threads)
    threads_omitted = 0

    for index in ordered:
        thread = threads[index]
        if len(selected) >= thread_cap:
            threads_omitted += 1
            comments_omitted += len(thread["comments"])
            continue

        cost = sum(len(c["body"]) for c in thread["comments"])
        room = comment_cap - comments_used
        if room <= 0 or (chars_used + cost > total_body_chars and selected):
            threads_omitted += 1
            comments_omitted += len(thread["comments"])
            continue

        if len(thread["comments"]) > room:
            dropped = len(thread["comments"]) - room
            thread = dict(thread)
            thread["comments"] = thread["comments"][:room]
            thread["commentsOmitted"] += dropped
            comments_omitted += dropped
            cost = sum(len(c["body"]) for c in thread["comments"])

        selected.append((index, thread))
        comments_used += len(thread["comments"])
        chars_used += cost

    selected.sort(key=lambda pair: pair[0])
    return (
        [thread for _, thread in selected],
        {"threadsOmitted": threads_omitted, "commentsOmitted": comments_omitted},
    )


def _normalize_reviews(pull_request, allowed_hosts, body_chars):
    """Submitted review summaries, minus the ones that carry no information.

    Returns `(reviews, omitted)`. `state` is passed through verbatim rather than
    validated against an enum: GitHub already ships DISMISSED alongside the
    obvious three, and a state this code has never heard of should still reach
    the page instead of being silently dropped.
    """
    reviews = []
    omitted = 0
    connection = pull_request.get("reviews")
    total = _dig(connection, "totalCount")

    for node in _nodes(connection):
        state = node.get("state") if isinstance(node.get("state"), str) else None
        body = _text(node.get("body")).strip()
        if state == _PENDING_REVIEW_STATE:
            continue
        if not body and state == _NOISE_REVIEW_STATE:
            continue
        truncated_body, truncated = _truncate_body(body, body_chars)
        reviews.append({
            "id": node.get("id") if isinstance(node.get("id"), str) else None,
            "author": _login(node.get("author")),
            "state": state,
            "body": truncated_body,
            "bodyTruncated": truncated,
            "submittedAt": node.get("submittedAt")
            if isinstance(node.get("submittedAt"), str) else None,
            "url": _safe_url(node.get("url"), allowed_hosts),
        })

    if isinstance(total, int) and total > len(_nodes(connection)):
        omitted = total - len(_nodes(connection))
    return reviews, omitted


def _normalize_issue_comments(pull_request, allowed_hosts, body_chars):
    comments = []
    connection = pull_request.get("comments")
    total = _dig(connection, "totalCount")
    nodes = _nodes(connection)

    for node in nodes:
        comments.append(_normalize_comment(node, allowed_hosts, body_chars))

    omitted = total - len(nodes) if isinstance(total, int) and total > len(nodes) else 0
    return comments, omitted


def unavailable(reason, fetched_at=None):
    """The shape to inject when the activity fetch failed outright.

    Deliberately not an empty `threads: []`: "we could not read the PR's
    history" and "this PR has no history" look identical in an empty array, and
    the reviewer must be able to tell them apart before trusting the page.
    """
    return {
        "status": STATUS_UNAVAILABLE,
        "reason": reason,
        "sourceHeadOid": None,
        "fetchedAt": fetched_at or _now(),
        "truncation": {"threadsOmitted": 0, "commentsOmitted": 0,
                       "reviewsOmitted": 0, "issueCommentsOmitted": 0},
        "threads": [],
        "reviews": [],
        "issueComments": [],
    }


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(
        microsecond=0).isoformat().replace("+00:00", "Z")


def to_existing_activity(raw, thread_cap=DEFAULT_THREAD_CAP,
                         comment_cap=DEFAULT_COMMENT_CAP,
                         comments_per_thread=DEFAULT_COMMENTS_PER_THREAD,
                         body_chars=DEFAULT_BODY_CHARS,
                         total_body_chars=DEFAULT_TOTAL_BODY_CHARS,
                         allowed_hosts=DEFAULT_ALLOWED_HOSTS,
                         head_ref_oid=None, fetched_at=None):
    """Build the `existingActivity` object from a raw GraphQL response.

    `raw` may be a JSON string, a decoded object, or a list of paginated pages.
    `head_ref_oid`, when given, is the SHA the rendered diff was built from; a
    mismatch against the SHA in the response downgrades `status` to `partial`,
    because the branch moved mid-fetch and some anchors may describe a diff the
    page is not showing.
    """
    allowed_hosts = tuple(h.lower() for h in allowed_hosts)
    fetched_at = fetched_at or _now()

    documents = load_documents(raw) if isinstance(raw, str) else load_documents(raw)
    pull_request, errors, paginated_out = merge_pages(documents)

    if pull_request is None:
        reason = ("GraphQL response carried no pullRequest data"
                  + (": %s" % _first_error(errors) if errors else ""))
        return unavailable(reason, fetched_at=fetched_at)

    threads = [_normalize_thread(n, allowed_hosts, body_chars, comments_per_thread)
               for n in _nodes(pull_request.get("reviewThreads"))]
    threads, truncation = _apply_budgets(
        threads, thread_cap, comment_cap, total_body_chars)

    reviews, reviews_omitted = _normalize_reviews(
        pull_request, allowed_hosts, body_chars)
    issue_comments, issue_omitted = _normalize_issue_comments(
        pull_request, allowed_hosts, body_chars)

    truncation["reviewsOmitted"] = reviews_omitted
    truncation["issueCommentsOmitted"] = issue_omitted

    source_head = pull_request.get("headRefOid")
    source_head = source_head if isinstance(source_head, str) else None

    status = STATUS_COMPLETE
    reason = None
    if errors:
        status = STATUS_PARTIAL
        reason = "GraphQL returned errors: %s" % _first_error(errors)
    elif paginated_out:
        status = STATUS_PARTIAL
        reason = "more review threads exist than were fetched"
    elif head_ref_oid and source_head and head_ref_oid != source_head:
        status = STATUS_PARTIAL
        reason = ("activity was read at %s but the diff was built from %s; the "
                  "branch moved" % (source_head, head_ref_oid))

    activity = {
        "status": status,
        "sourceHeadOid": source_head,
        "fetchedAt": fetched_at,
        "truncation": truncation,
        "threads": threads,
        "reviews": reviews,
        "issueComments": issue_comments,
    }
    if reason:
        activity["reason"] = reason
    return activity


def _first_error(errors):
    for error in errors:
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
        if isinstance(error, str):
            return error
    return "unknown error"


def main():
    ap = argparse.ArgumentParser(
        description="Normalize existing PR review activity into the "
                    "existingActivity page contract.")
    ap.add_argument("--activity-json", required=True,
                    help="path to the read-only GraphQL response, or - for stdin")
    ap.add_argument("--head-ref-oid", default=None,
                    help="SHA the rendered diff was built from; a mismatch "
                         "downgrades status to partial")
    ap.add_argument("--thread-cap", type=int, default=DEFAULT_THREAD_CAP)
    ap.add_argument("--comment-cap", type=int, default=DEFAULT_COMMENT_CAP)
    ap.add_argument("--comments-per-thread", type=int,
                    default=DEFAULT_COMMENTS_PER_THREAD)
    ap.add_argument("--body-chars", type=int, default=DEFAULT_BODY_CHARS)
    ap.add_argument("--total-body-chars", type=int, default=DEFAULT_TOTAL_BODY_CHARS)
    ap.add_argument("--allow-host", action="append", default=None,
                    help="extra host allowed in comment URLs (GitHub Enterprise); "
                         "repeatable")
    ap.add_argument("--fetched-at", default=None,
                    help="override the fetch timestamp (for reproducible output)")
    args = ap.parse_args()

    if args.activity_json == "-":
        raw = sys.stdin.read()
    else:
        with open(args.activity_json, "r", encoding="utf-8") as fh:
            raw = fh.read()

    hosts = list(DEFAULT_ALLOWED_HOSTS) + list(args.allow_host or [])

    activity = to_existing_activity(
        raw,
        thread_cap=args.thread_cap,
        comment_cap=args.comment_cap,
        comments_per_thread=args.comments_per_thread,
        body_chars=args.body_chars,
        total_body_chars=args.total_body_chars,
        allowed_hosts=hosts,
        head_ref_oid=args.head_ref_oid,
        fetched_at=args.fetched_at,
    )
    json.dump(activity, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
