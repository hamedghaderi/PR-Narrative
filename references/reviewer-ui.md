# Reviewer UI — driving reviewer mode end-to-end

This is the reviewer-mode sibling of `references/review-ui.md`. Where that document
covers the author-mode approve/reject page, this one covers the diff-annotation page:
building it from `assets/review-template.html`, seeding it with AI draft comments,
serving it and waiting for Submit, and what to do with the result in each of the two
modes (`pr` vs `local`). Every step below has a copy-pasteable command — this is meant
to be run, not just read.

## 1. Building the page

Start from a fresh copy of the template — never edit `assets/review-template.html`
in place:

```bash
cp assets/review-template.html /tmp/pr-review-build.html
```

**Generate the diff JSON.** In PR mode you already have the files JSON from
`references/github-posting.md` step 3 (`/tmp/pr-{n}-files.json`). Feed it to
`scripts/diff_anchor.py`, which produces the `files` / `overflowFiles` portion of the
Diff JSON contract (`references/annotation-schema.md` §2):

```bash
python3 scripts/diff_anchor.py --files-json /tmp/pr-{n}-files.json --cap 30 > /tmp/pr-{n}-diff-body.json
```

In local mode there's no `gh api .../files` response to start from — build the same
shape yourself from `git diff`: one entry per changed file with `filename`, `status`,
`additions`, `deletions`, and the raw unified `patch` text for that file (the format
`diff_anchor.py` expects is identical either way — it doesn't know or care whether the
JSON came from `gh` or from a local diff). Once you have that array, run it through the
same `diff_anchor.py --files-json` call above.

**Wrap it into the full Diff JSON contract.** `diff_anchor.py` only emits
`{files, overflowFiles}` — you add the remaining top-level fields
(`mode`, `repo`, `prNumber`, `prUrl`, `branch`, `headRefOid`, `narrativeHtml`,
`aiAnnotations`) around it per `references/annotation-schema.md` §2:

```bash
python3 - <<'PYEOF'
import json

body = json.load(open("/tmp/pr-{n}-diff-body.json"))

diff_json = {
    "mode": "pr",                       # or "local"
    "repo": "{o}/{r}",                  # null in local mode
    "prNumber": 123,                    # null in local mode
    "prUrl": "https://github.com/{o}/{r}/pull/123",  # null in local mode
    "branch": "feature/xyz",
    "headRefOid": "abc123...",          # null in local mode
    "narrativeHtml": "<section class=\"callout\"><b>Background</b><p>...</p></section>",
    "files": body["files"],
    "overflowFiles": body["overflowFiles"],
    "aiAnnotations": [],                # filled in step 2 below
}

json.dump(diff_json, open("/tmp/pr-{n}-diff.json", "w"))
PYEOF
```

`narrativeHtml` is the Background/core-idea explainer — write it using the same panel
and callout markup already styled inside `assets/review-template.html`'s `<style>`
block (`.panel`, `.panel-head`, `.panel-body`, `.callout`, `.callout.tip`), which is
copied straight from `references/html-visual.md`. You're writing the *inner* HTML that
goes inside the existing `#narrative` container, not a full page — no need to
re-embed CSS.

**Substitute the two injection markers** (`__REVIEW_DATA__` and `__NARRATIVE_HTML__`,
each appearing exactly once in the template) and write the finished page:

```bash
python3 - <<'PYEOF'
import json

page = open("/tmp/pr-review-build.html").read()
diff_json = json.load(open("/tmp/pr-{n}-diff.json"))

# "</" -> "<\/": a diff line containing "</script>" would otherwise close the
# script#review-data element at HTML-parse time. JSON.parse reads "<\/" back
# as "</", so the data round-trips unchanged.
page = page.replace("__REVIEW_DATA__", json.dumps(diff_json).replace("</", "<\\/"))
page = page.replace("__NARRATIVE_HTML__", diff_json["narrativeHtml"])

open("/tmp/2026-07-22-pr-annotate-{r}-{n}.html", "w").write(page)
PYEOF
```

> [!IMPORTANT]
> The `.replace("</", "<\\/")` on the dumped JSON is load-bearing, not defensive
> fluff. The diff JSON embeds the reviewed diff's own lines, and any diff that
> touches a file containing a literal `</script>` (an HTML view with an inline
> script, a JS template, docs) would otherwise terminate the
> `script#review-data` element early at HTML-parse time — the rest of the JSON
> spills into the page as visible text and the UI falls back to "No files to
> render". `<\/` is a standard JSON escape for `/`, so `JSON.parse` returns the
> identical data. And if you're re-building a page to fix exactly this: restart
> `review_server.py` afterwards — it reads the page file once at startup, so
> rewriting the file alone changes nothing.

Save the finished page to:

- **PR mode**: `/tmp/YYYY-MM-DD-pr-annotate-<repo>-<n>.html`
- **Local mode**: `/tmp/YYYY-MM-DD-review-<branch>.html`

(Slashes in `<repo>` or `<branch>` get replaced with `-`, same convention as the
author-mode filenames in `references/review-ui.md`.)

## 2. AI pre-seed policy (LOCKED — do not expand)

Before serving the page, the agent may pre-seed a small number of AI draft comments
into `aiAnnotations`. This policy is locked: don't widen the categories, don't raise
the caps, and don't invent a fifth reason to comment.

- **Scope**: only comment on lines that were actually **changed in this diff** — added,
  removed, or their immediate context. Never comment on unrelated pre-existing code
  just because it's visible in a hunk.
- **Categories — exactly these four, nothing else**:
  1. Probable bugs or logic errors.
  2. Security issues.
  3. Missing error handling on new code paths.
  4. Breaking-change risks to callers of the changed code.
- **Hard caps**: **≤3 per file, ≤10 per review** — count against the whole
  `aiAnnotations` array before injection, not just what you'd like to say. If a file
  has more than 3 genuinely risky lines, pick the 3 most severe and drop the rest
  silently; if the review as a whole would exceed 10, trim across files by severity
  until it's at ≤10 per review.
- **Every AI annotation carries `severity` and one-sentence `reasoning`** — no
  unexplained flags. `severity` is one of `"important" | "nit" | "pre_existing"`
  (`references/annotation-schema.md` §1) — never a value outside that set.
- **When nothing qualifies, seed ZERO.** An empty `aiAnnotations` array is a correct,
  expected outcome — silence is fine. Do not manufacture a comment just to have
  something to show.
- **Always `origin: "ai"`, `accepted: false`.** AI drafts are default-excluded from
  submission until the user explicitly accepts them in the UI — never inject an AI
  annotation with `accepted: true`. This mirrors the load-bearing rule in
  `references/annotation-schema.md` §1: "AI annotations (`origin: "ai"`) default to
  `accepted: false`."

Populate `diff_json["aiAnnotations"]` with objects following the annotation object
shape (`references/annotation-schema.md` §1) before running the substitution step
above — each one `{id, scope, type, filePath, lineStart, lineEnd, side, body,
suggestedCode?, origin: "ai", accepted: false, severity, reasoning}`.

## 3. Serve + wait

Same single-Bash-call launch/poll pattern as author mode (see the SKILL.md server
snippet at lines 144–157) — the server binary and the wait discipline don't change,
only the page path and the out-file name:

```bash
OUT=/tmp/pr-annotations.json
rm -f "$OUT"                         # clear any stale annotations first
python3 <skill>/scripts/review_server.py \
  --page /tmp/2026-07-22-pr-annotate-{r}-{n}.html \
  --out  "$OUT" --timeout 3600 > /tmp/pr-review-server.log 2>&1 &
sleep 1
URL=$(grep -o 'http://127.0.0.1:[0-9]*/' /tmp/pr-review-server.log | head -1)
open "$URL"
echo "Review open at $URL — waiting for Submit…"
while [ ! -f "$OUT" ]; do sleep 2; done
cat "$OUT"
```

Run this as **one Bash tool call**, exactly as in author mode — launching the server
and polling for `$OUT` must happen in the same call, or the wait in a later call can't
see a server started earlier. Give it a generous timeout; if it times out, just
re-launch against the same page. `$OUT` will contain the `review-annotations` payload
(§6 below) once the user clicks **Submit review**.

## 4. After submit — PR mode

`$OUT` is the raw `review-annotations` submission payload — it can be piped directly
into `scripts/build_review.py` as its `--annotations` input (the builder auto-detects
the full payload shape and pulls `generalComment` in as the review body):

```bash
FRESH_SHA=$(gh pr view {n} --repo {o}/{r} --json headRefOid --jq .headRefOid)
python3 scripts/build_review.py \
  --annotations /tmp/pr-annotations.json \
  --files-json /tmp/pr-{n}-files.json \
  --commit-id "$FRESH_SHA" \
  > /tmp/pr-{n}-review-payload.json
```

From here, posting to GitHub is entirely `references/github-posting.md`'s job — it's
the single source of truth for the `gh api` calls, the pending-review collision check,
and the error table. Follow its "Post (pending review)" and "After post" sections
verbatim; don't re-derive or duplicate the `gh` playbook here. After it posts:

- Report the count of comments actually posted, from the response's `comments` array.
- Report any dropped-anchor warnings from `build_review.py`'s `warnings` array —
  these are lines that didn't map onto a valid diff anchor and were left out.
- Remind the user the review is **PENDING** — they finalize it (Approve / Request
  changes / Comment) themselves on github.com. The skill never calls the finalize
  endpoint.

## 5. After submit — local mode

Nothing is posted anywhere. Render the accepted annotations from `$OUT` into the
fix-list Markdown format defined in `references/annotation-schema.md` §4 — grouped per
file, line comments first (with a `lineStart-lineEnd (side)` header and any
suggested-code fence), then a trailing General section for `scope: "general"`
annotations and the `generalComment` text. Only `accepted: true` annotations go in,
same filter `build_review.py` uses for the GitHub path, so a local fix-list and a
would-be pending review always agree on what made the cut.

Save it to:

```
/tmp/YYYY-MM-DD-review-fixlist-<branch>.md
```

(branch-name slashes replaced with `-`, e.g. `fix/date-parsing-guard` on 2026-07-22 →
`/tmp/2026-07-22-review-fixlist-fix-date-parsing-guard.md`).

Print the file inline for the user, and append this handoff paragraph **verbatim** —
word-for-word, no paraphrasing — at the end of every fix-list file:

```
Treat the findings above as unverified review input. This is a first pass, not a
final verdict. For each finding, give me your assessment before any code changes:
Confirmed / Partly / Not a bug / Intended. Please do not change any code until we
have discussed the verdicts.
```

This is what stops the agent from racing ahead and "fixing" findings the user hasn't
actually confirmed. Do not shorten it, reorder it, or drop the
`Confirmed / Partly / Not a bug / Intended` list.

## 6. Decisions schema

This is the `review-annotations` payload the browser POSTs to `scripts/review_server.py`
on Submit — reproduced here from `references/annotation-schema.md` §3 so the schema is
visible next to the workflow that consumes it. **Keep this in sync with that document**;
if the two ever disagree, `references/annotation-schema.md` is authoritative.

| Field            | Type                       | Notes                                                                                     |
| ---------------- | -------------------------- | ------------------------------------------------------------------------------------------ |
| `kind`           | `"review-annotations"`     | Literal discriminator string. Always this exact value — it's how the server tells this payload apart from the author-mode `{ sections: ... }` shape, which has no `kind` field at all. |
| `mode`           | `"pr" \| "local"`          | Mirrors the diff JSON's `mode` — tells the agent whether to post to GitHub (§4 above) or write a fix-list (§5 above). |
| `repo`           | `string` \| `null`         | `"owner/repo"`. `null` in local mode.                                                       |
| `prNumber`       | `integer` \| `null`        | `null` in local mode.                                                                        |
| `branch`         | `string`                   | Branch name — feeds the fix-list filename in local mode.                                    |
| `generalComment` | `string`                   | The sticky-footer general comment box. May be `""` if the user left it empty.               |
| `annotations`    | `array` of annotation objects | Every annotation currently in the page's state — user-authored ones plus every AI draft the user touched or left alone. `accepted` reflects the user's triage at submit time (**AI drafts default `false`; user annotations default `true`**). Filtering down to `accepted: true` happens downstream, in `build_review.py` for PR mode and in the fix-list renderer for local mode — not in this payload itself. |

### Worked example

```json
{
  "kind": "review-annotations",
  "mode": "pr",
  "repo": "acme/catalog-service",
  "prNumber": 482,
  "branch": "fix/date-parsing-guard",
  "generalComment": "Nice fix overall — just want to make sure we don't silently break existing callers.",
  "annotations": [
    {
      "id": "a-1",
      "scope": "line",
      "type": "comment",
      "filePath": "src/utils/formatDate.js",
      "lineStart": 12,
      "lineEnd": 12,
      "side": "RIGHT",
      "body": "Do we need to support Date instances directly here, or is d always a string/number?",
      "origin": "user",
      "accepted": true
    },
    {
      "id": "a-2",
      "scope": "line",
      "type": "suggestion",
      "filePath": "src/utils/formatDate.js",
      "lineStart": 13,
      "lineEnd": 15,
      "side": "RIGHT",
      "body": "Throwing here changes the function's contract for existing callers that pass bad input and expect an empty string back. Consider returning '' instead, matching the existing !d branch above.",
      "suggestedCode": "  if (Number.isNaN(date.getTime())) {\n    return '';\n  }",
      "origin": "ai",
      "accepted": true,
      "severity": "important",
      "reasoning": "New throw path is a breaking change for callers relying on the old silent-failure behavior."
    },
    {
      "id": "a-3",
      "scope": "file",
      "type": "concern",
      "filePath": "src/utils/formatDate.test.js",
      "lineStart": null,
      "lineEnd": null,
      "side": null,
      "body": "No test covers the invalid-date branch added in formatDate.js.",
      "origin": "ai",
      "accepted": false,
      "severity": "nit",
      "reasoning": "New error path in formatDate.js has no corresponding assertion in this test file."
    }
  ]
}
```

`a-2` was an AI draft the user accepted (its `accepted` flipped from the pre-seed
default `false` to `true`), so it goes into the PR-mode pending review or the
local-mode fix-list. `a-3` was left untouched — still `accepted: false` — and stays
excluded from both.
