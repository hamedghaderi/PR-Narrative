# Reviewer UI: driving reviewer mode end-to-end

This is the reviewer-mode sibling of `references/review-ui.md`. Where that document
covers the author-mode approve/reject page, this one covers the diff-annotation page:
building it from `assets/review-template.html`, seeding it with AI draft comments,
serving it and waiting for Submit, and what to do with the result in each of the two
modes (`pr` vs `local`). Every step below has a copy-pasteable command; this is meant
to be run, not just read.

## 1. Building the page

Start from a fresh copy of the template. Never edit `assets/review-template.html`
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

In local mode there's no `gh api .../files` response to start from; build the same
shape yourself from `git diff`: one entry per changed file with `filename`, `status`,
`additions`, `deletions`, and the raw unified `patch` text for that file (the format
`diff_anchor.py` expects is identical either way; it doesn't know or care whether the
JSON came from `gh` or from a local diff). Once you have that array, run it through the
same `diff_anchor.py --files-json` call above.

**Wrap it into the full Diff JSON contract.** `diff_anchor.py` only emits
`{files, overflowFiles}`; you add the remaining top-level fields
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

`narrativeHtml` is the Background/core-idea explainer. Write it using the same panel
and callout markup already styled inside `assets/review-template.html`'s `<style>`
block (`.panel`, `.panel-head`, `.panel-body`, `.callout`, `.callout.tip`), which is
copied straight from `references/html-visual.md`. You're writing the *inner* HTML that
goes inside the existing `#narrative` container, not a full page, so no need to
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
> `script#review-data` element early at HTML-parse time, so the rest of the JSON
> spills into the page as visible text and the UI falls back to "No files to
> render". `<\/` is a standard JSON escape for `/`, so `JSON.parse` returns the
> identical data. And if you're re-building a page to fix exactly this: restart
> `review_server.py` afterwards, because it reads the page file once at startup, so
> rewriting the file alone changes nothing.

Save the finished page to:

- **PR mode**: `/tmp/YYYY-MM-DD-pr-annotate-<repo>-<n>.html`
- **Local mode**: `/tmp/YYYY-MM-DD-review-<branch>.html`

(Slashes in `<repo>` or `<branch>` get replaced with `-`, same convention as the
author-mode filenames in `references/review-ui.md`.)

## 2. AI pre-seed policy (LOCKED: do not expand)

Before serving the page, the agent may pre-seed a small number of AI draft comments
into `aiAnnotations`. This policy is locked: don't widen the categories, don't raise
the caps, and don't invent a fifth reason to comment.

- **Scope**: only comment on lines that were actually **changed in this diff**: added,
  removed, or their immediate context. Never comment on unrelated pre-existing code
  just because it's visible in a hunk.
- **Categories: exactly these four, nothing else**:
  1. Probable bugs or logic errors.
  2. Security issues.
  3. Missing error handling on new code paths.
  4. Breaking-change risks to callers of the changed code.
- **Hard caps**: **≤3 per file, ≤10 per review**: count against the whole
  `aiAnnotations` array before injection, not just what you'd like to say. If a file
  has more than 3 genuinely risky lines, pick the 3 most severe and drop the rest
  silently; if the review as a whole would exceed 10, trim across files by severity
  until it's at ≤10 per review.
- **Every AI annotation carries `severity` and one-sentence `reasoning`**: no
  unexplained flags. `severity` is one of `"important" | "nit" | "pre_existing"`
  (`references/annotation-schema.md` §1); never a value outside that set.
- **When nothing qualifies, seed ZERO.** An empty `aiAnnotations` array is a correct,
  expected outcome; silence is fine. Do not manufacture a comment just to have
  something to show.
- **Always `origin: "ai"`, `accepted: false`.** AI drafts are default-excluded from
  submission until the user explicitly accepts them in the UI; never inject an AI
  annotation with `accepted: true`. This mirrors the load-bearing rule in
  `references/annotation-schema.md` §1: "AI annotations (`origin: "ai"`) default to
  `accepted: false`."

Populate `diff_json["aiAnnotations"]` with objects following the annotation object
shape (`references/annotation-schema.md` §1) before running the substitution step
above, each one `{id, scope, type, filePath, lineStart, lineEnd, side, body,
suggestedCode?, origin: "ai", accepted: false, severity, reasoning}`.

## 3. Serve + wait

Same single-Bash-call launch/poll pattern as author mode (see SKILL.md §4 "Build the
page, serve it, and wait"): the server binary and the wait discipline don't change,
only the page path and the out-file name:

```bash
OUT=/tmp/pr-annotations.json
rm -f "$OUT"                         # clear any stale annotations first
python3 <skill>/scripts/review_server.py \
  --page /tmp/2026-07-22-pr-annotate-{r}-{n}.html \
  --out  "$OUT" --open --timeout 3600 > /tmp/pr-review-server.log 2>&1 &
PID=$!
# Poll for the URL, with dead-process detection (bounded ~15s).
URL=""
for i in $(seq 1 30); do
  URL=$(grep -o 'http://127.0.0.1:[0-9]*/' /tmp/pr-review-server.log | head -1)
  [ -n "$URL" ] && break
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "ERROR: review server exited before printing a URL. Log:"
    tail -20 /tmp/pr-review-server.log
    exit 1
  fi
  sleep 0.5
done
if [ -z "$URL" ]; then
  echo "ERROR: timed out waiting for the review server URL. Log:"
  tail -20 /tmp/pr-review-server.log
  exit 1
fi
# Wait for open sentinel (PR_REVIEW_OPEN_OK or PR_REVIEW_OPEN_FAILED), bounded ~10s.
# The URL prints before the open attempt, so the URL grep can return before the sentinel.
for i in $(seq 1 20); do
  grep -q 'PR_REVIEW_OPEN_OK\|PR_REVIEW_OPEN_FAILED' /tmp/pr-review-server.log && break
  sleep 0.5
done
if grep -q 'PR_REVIEW_OPEN_FAILED' /tmp/pr-review-server.log; then
  # Shell-level fallback: fires ONLY on explicit failure (unconditional = two tabs = second Submit to dead server)
  case "$(uname)" in Darwin) open "$URL" ;; *) command -v xdg-open >/dev/null && xdg-open "$URL" ;; esac
fi
echo "Review page: $URL"
# Always include this URL in your message to the user, open success or not.
# Poll for the annotations file (robust: works even if the server already exited).
while [ ! -f "$OUT" ]; do
  kill -0 "$PID" 2>/dev/null || { echo "Server exited before Submit. Check /tmp/pr-review-server.log (it may have hit --timeout; re-run this block)."; break; }
  sleep 2
done
[ -f "$OUT" ] && cat "$OUT"
```

Run this as **one Bash tool call**, exactly as in author mode: launching the server
and polling for `$OUT` must happen in the same call, or the wait in a later call can't
see a server started earlier. Give it a generous timeout; if it times out, just
re-launch against the same page. `$OUT` will contain the `review-annotations` payload
(§6 below) once the user clicks **Submit review**.

## 4. After submit: PR mode

`$OUT` is the raw `review-annotations` submission payload; it can be piped directly
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

From here, posting to GitHub is entirely `references/github-posting.md`'s job: it's
the single source of truth for the `gh api` calls, the pending-review collision check,
and the error table. Follow its "Post (pending review)" and "After post" sections
verbatim; don't re-derive or duplicate the `gh` playbook here. After it posts:

- Report the count of comments actually posted, from the response's `comments` array.
- Report any dropped-anchor warnings from `build_review.py`'s `warnings` array:
  these are lines that didn't map onto a valid diff anchor and were left out.
- Remind the user the review is **PENDING**: they finalize it (Approve / Request
  changes / Comment) themselves on github.com. The skill never calls the finalize
  endpoint.

## 5. After submit: local mode

Nothing is posted anywhere. Render the accepted annotations from `$OUT` into the
fix-list Markdown format defined in `references/annotation-schema.md` §4: grouped per
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

Print the file inline for the user, and append this handoff paragraph **verbatim** (word-for-word, no paraphrasing) at the end of every fix-list file:

```
Treat the findings above as unverified review input. This is a first pass, not a
final verdict. For each finding, give me your assessment before any code changes:
Confirmed / Partly / Not a bug / Intended. Please do not change any code until we
have discussed the verdicts.
```

This is what stops the agent from racing ahead and "fixing" findings the user hasn't
actually confirmed. Do not shorten it, reorder it, or drop the
`Confirmed / Partly / Not a bug / Intended` list.

### 5.1 The in-page "Copy fix-list" button

The page can also produce that same Markdown without waiting for the agent. The
sticky footer carries a third, secondary button (`#copy-fixlist-btn`,
"📋 Copy fix-list"), styled like `#download-btn` because copying is not the primary
action, that serializes the current annotation state to the clipboard on click. It's
for the case where the user wants the findings *somewhere else* right now (a chat
message, an issue, a scratch file) rather than waiting for a submit round-trip.

The button is stateless: it reads the in-memory annotation state, writes nothing to
`localStorage`, POSTs nothing, and does not touch `buildPayload()` or the Submit path.

- **Local mode only.** The template hides it whenever `DATA.mode !== "local"`, next to
  the existing `isLive` check that hides `#submit-btn`. In PR mode there is no
  fix-list (accepted comments become a pending GitHub review, §4), so a copy button
  there would offer an artifact that mode never produces. There is exactly one copy
  button on the page; do not add a PR-mode counterpart.
- **Acceptance filtering happens in the button, not downstream.** `buildPayload()`
  deliberately ships every live annotation with its `accepted` flag intact and lets
  `build_review.py` filter, so the clipboard serializer cannot reuse it as-is. It
  applies the §5 filter itself: user annotations are included unless `accepted` was
  explicitly set to `false`, AI drafts only when `accepted === true` **and** not
  `_discarded`. Same cut as the GitHub path, so the copied list and a would-be pending
  review always agree.
- **Format is `references/annotation-schema.md` §4, verbatim.** Per-file `##` headings
  in first-seen order, `### Lines N (SIDE)` for a single line and
  `### Lines N-M (SIDE): suggestion` for a range carrying suggested code, an
  unescaped ` ```suggestion ` fence around `suggestedCode`, `### File-level` for
  `scope: "file"`, and a trailing `## General` section holding `scope: "general"`
  bodies followed by the footer's `generalComment`. The `# Review fix-list: <branch>`
  title and `Generated YYYY-MM-DD. Local branch review, nothing posted to GitHub.`
  line come first.
- **The mandatory handoff paragraph is omitted from the clipboard, deliberately.**
  §4 requires that paragraph (`Treat the findings above as unverified review input…`)
  in every fix-list *file*, and §5 above still appends it verbatim when the agent
  writes and prints one. It is an instruction aimed at the agent, telling it not to
  race ahead and "fix" unconfirmed findings. The clipboard content is aimed at a human
  destination the user picks, so carrying those instructions along would only read as
  noise there. Omitting it from the clipboard does **not** relax the §5 requirement for
  the file the agent produces.
- **Clipboard strategy.** `navigator.clipboard.writeText(md)` is called
  **synchronously** inside the click handler (Safari ties clipboard access to
  transient activation, which any intervening `await` discards), and its promise is
  handled with `.then()` / `.catch()`. On rejection (or a missing
  `navigator.clipboard`, e.g. a page opened over plain `http://` in a browser that
  gates the API on a secure context) it falls back to a throwaway `<textarea>`
  positioned off-screen with `position:fixed; left:-9999px` and
  `document.execCommand("copy")`. The fallback element must not use `display:none`:
  hidden elements can't be selected, so the copy silently produces nothing.
- **Feedback.** The label switches to `✓ Copied` (or `Copy failed` if even the
  fallback throws) and reverts to its original text after 2 seconds.

## 6. Decisions schema

This is the `review-annotations` payload the browser POSTs to `scripts/review_server.py`
on Submit, reproduced here from `references/annotation-schema.md` §3 so the schema is
visible next to the workflow that consumes it. **Keep this in sync with that document**;
if the two ever disagree, `references/annotation-schema.md` is authoritative.

| Field            | Type                       | Notes                                                                                     |
| ---------------- | -------------------------- | ------------------------------------------------------------------------------------------ |
| `kind`           | `"review-annotations"`     | Literal discriminator string. Always this exact value: it's how the server tells this payload apart from the author-mode `{ sections: ... }` shape, which has no `kind` field at all. |
| `mode`           | `"pr" \| "local"`          | Mirrors the diff JSON's `mode`: tells the agent whether to post to GitHub (§4 above) or write a fix-list (§5 above). |
| `repo`           | `string` \| `null`         | `"owner/repo"`. `null` in local mode.                                                       |
| `prNumber`       | `integer` \| `null`        | `null` in local mode.                                                                        |
| `branch`         | `string`                   | Branch name: feeds the fix-list filename in local mode.                                    |
| `generalComment` | `string`                   | The sticky-footer general comment box. May be `""` if the user left it empty.               |
| `annotations`    | `array` of annotation objects | Every annotation currently in the page's state: user-authored ones plus every AI draft the user touched or left alone. `accepted` reflects the user's triage at submit time (**AI drafts default `false`; user annotations default `true`**). Filtering down to `accepted: true` happens downstream, in `build_review.py` for PR mode and in the fix-list renderer for local mode, not in this payload itself. |

### Worked example

```json
{
  "kind": "review-annotations",
  "mode": "pr",
  "repo": "acme/catalog-service",
  "prNumber": 482,
  "branch": "fix/date-parsing-guard",
  "generalComment": "Nice fix overall, just want to make sure we don't silently break existing callers.",
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
local-mode fix-list. `a-3` was left untouched (still `accepted: false`) and stays
excluded from both.
