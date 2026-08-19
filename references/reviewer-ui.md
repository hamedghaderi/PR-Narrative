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
    "narrativeHtml": "<section class=\"callout\"><b>In one sentence</b><p>...</p></section>",
    "files": body["files"],
    "overflowFiles": body["overflowFiles"],
    "aiAnnotations": [],                # filled in step 2 below
}

json.dump(diff_json, open("/tmp/pr-{n}-diff.json", "w"))
PYEOF
```

`narrativeHtml` is the human-first explainer (the one-sentence summary and the problem story). Write it using the same panel
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
- **Every `severity: "important"` annotation also carries `disproof`**: the smallest
  concrete check that would prove the concern **false**. Write the check that would
  make you withdraw the comment, not one more argument for why you're right. Prefer a
  test the author can actually run ("assert `formatDate(null)` still returns `''`");
  fall back to a command to run or an output to look at only when the concern isn't
  testable. If you can't name a check that would settle it, you don't understand the
  risk well enough to call it important: drop it to `"nit"` or drop it entirely.
  **Never invent a plausible-looking test for a concern that can't be tested**: a
  fabricated check is worse than the sentence it replaced, because it reads as
  evidence. `nit` and `pre_existing` annotations omit `disproof`.
- **When nothing qualifies, seed ZERO.** An empty `aiAnnotations` array is a correct,
  expected outcome; silence is fine. Do not manufacture a comment just to have
  something to show.
- **Always `origin: "ai"`, `accepted: false`.** AI drafts are default-excluded from
  submission until the user explicitly accepts them in the UI; never inject an AI
  annotation with `accepted: true`. This mirrors the default stated in
  `references/annotation-schema.md` §1: "AI annotations (`origin: "ai"`) default to
  `accepted: false`."
- **Every `body` follows §2c.** Deciding a line qualifies is only half the work. How the
  comment is worded is governed by §2c below: lead with the problem in plain English,
  then the consequence, then an example if it helps, then a suggestion or question. A
  correct finding a reviewer cannot follow has not landed.

Populate `diff_json["aiAnnotations"]` with objects following the annotation object
shape (`references/annotation-schema.md` §1) before running the substitution step
above, each one `{id, scope, type, filePath, lineStart, lineEnd, side, body,
suggestedCode?, origin: "ai", accepted: false, severity, reasoning, disproof?}`
(`disproof` present exactly when `severity` is `"important"`).

A security-only variant of this policy, used by the review-security subcommand, is
defined in §2b below. The body-writing rules in §2c apply to both.

## 2b. Security-only pre-seed variant (review-security)

This variant applies **only** when the skill was invoked through the `review-security`
subcommand. In every other invocation, §2 above is the policy and this section does not
apply.

Everything in §2 carries over **unchanged** except the category list:

- **Same scope rule**: only lines that were actually **changed in this diff** (added,
  removed, or their immediate context). Never comment on unrelated pre-existing code
  just because it's visible in a hunk.
- **Same hard caps**: **≤3 per file, ≤10 per review**, counted against the whole
  `aiAnnotations` array before injection. Trim by severity, silently, to stay under both.
- **Same required fields**: every annotation carries `severity` and a one-sentence
  `reasoning`, and every `severity: "important"` one also carries `disproof`.
  `severity` stays one of `"important" | "nit" | "pre_existing"`; a security focus
  does not earn a new severity tier.
- **Same injection contract**: always `origin: "ai"`, `accepted: false`, so drafts are
  excluded from submission until the user explicitly accepts them in the UI.
- **Same zero-findings rule**: when nothing qualifies, seed ZERO. An empty
  `aiAnnotations` array is a correct outcome, not a failure, and not a reason to
  manufacture a comment.
- **Same body-writing rules**: §2c governs the wording of every draft here too. A
  security finding is not exempt from being explained plainly; if anything the reader is
  less likely to already know the attack it describes, so name the concrete risk before
  naming the mechanism.

**Categories: exactly these five, nothing else**:

1. Injection risks (SQL/command/template/path traversal) on changed input-handling
   lines.
2. Authentication/authorization flaws (missing checks, privilege escalation, insecure
   session handling).
3. Secrets exposure (hardcoded credentials, tokens, keys, or any secret written to
   logs).
4. Unsafe deserialization or unvalidated input reaching a sensitive sink.
5. Dependency/supply-chain risk introduced by changed dependency or lockfile lines.

Category 5 is the one that most often has no honest `disproof`: "this new dependency
might be malicious" is not something a test can refute. When that happens, do not
manufacture a check to satisfy the field. Either name a real verifiable step (the
advisory ID to look up, the `npm audit`/`pip-audit` invocation, the published
checksum to compare) or set `severity` to `"nit"` and leave `disproof` off. The rule
in §2 holds here: an unfalsifiable concern is not an `"important"` finding.

This variant is **locked**, same as §2: do not widen the categories, do not raise the
caps, and do not apply it outside the `review-security` subcommand. Ordinary bugs,
missing error handling, and breaking-change risks belong to §2's list, not this one.

## 2c. Writing the finding body (applies to §2 and §2b)

§2 and §2b decide **whether** a line deserves a comment. This section decides **how the
comment reads**, and it applies to every AI draft either policy produces.

**Which field this governs.** This is about `body`, the text a reviewer actually reads
on the page and the only prose that reaches GitHub (`scripts/build_review.py` carries
`body` and `disproof` into the posted comment and nothing else). `reasoning` stays one
sentence: it renders as the in-page "Why flagged" line and never leaves the browser.

**Who you are writing for.** Assume a junior developer, a QA engineer, or someone who
has never opened this part of the codebase. The test is blunt: they should understand
the concern after reading it **once**, without opening another file first. Finding a
real problem is only half the job; a correct comment nobody can act on has not landed.

### Order: problem, then consequence, then example, then suggestion

1. **Open with the problem in plain English.** The first sentence must stand on its own
   without the reader opening another file. No identifier is allowed to carry the
   meaning of that sentence.
2. **Say why it matters.** What actually goes wrong, in terms of behavior a person
   could observe.
3. **Give one concrete example or scenario**, when it makes the concern easier to
   believe. Skip it when the problem is already obvious.
4. **Close with a suggested change or a clear question.** Leave the reader something to
   do or something to answer.

Class names, method names, queries and line references are **supporting evidence**.
They belong after the plain sentence, never in front of it.

Never use the reverse order: implementation detail, then code history, then edge cases,
then the conclusion. If the point of the comment only becomes clear in the last
sentence, rewrite it.

### Length scales with severity and complexity

Keep every comment as short as it can be without losing the reasoning needed to
understand the concern. Padding a simple point into four beats is a defect; so is
compressing a subtle one until the reason disappears.

| Finding | Shape |
|---|---|
| `important`, and the reasoning is not obvious | All four beats, in short paragraphs. |
| `important`, but the problem is self-evident once stated | Problem, consequence, suggestion. Drop the example. |
| `nit` or `pre_existing` | One or two plain sentences. Never four beats. |

### Describe behavior, not mechanics

Explain what can actually happen at runtime, not what the code technically says.

When two code paths disagree, state it outright rather than leaving the reader to infer
it: **"These two paths can return different results for the same input."** Then explain
why in one sentence.

Specific cases that are routinely written too densely:

- **Performance.** Name the unnecessary work that happens and roughly why it costs
  something. "This runs one query per row, so a 500-row page issues 500 queries" beats
  "N+1 risk".
- **A magic number or a hidden dependency.** Say what other behavior the value depends
  on, and what would break if that behavior changed later.
- **A fallback that hides a mistake.** Say what the caller was expected to do, what
  happens if they forget, and why that is dangerous.
- **A cross-file relationship.** Spell out how the two pieces relate. Do not assume the
  reader already knows that one method calls the other, or that two classes share a
  base.

### Name the kind of concern in words, not in `severity`

Be explicit about what sort of problem this is, and do not let a comment sound more
serious than it is:

- a correctness bug
- a possible inconsistency
- a performance issue
- a maintainability concern
- a cosmetic improvement

Say it in the prose. **Do not encode it in `severity`**, which stays exactly
`"important" | "nit" | "pre_existing"` per `references/annotation-schema.md` §1 and
gains no new values for this. The five kinds above and the three severity levels are
different axes: a performance issue can be `important`, and a correctness bug in dead
code can be a `nit`.

### Unpack compressed phrases

The problem is not technical vocabulary, it is **unexplained** vocabulary. A precise
term is welcome once the reader has been given the plain version; a term used *instead
of* the plain version is not.

Phrases like these must not carry the weight of a sentence on their own: "load-bearing",
"data drift", "escape hatch", "silent contract", "invariant", "forward path", "narrows
the batch", "hydrates rows". Each one compresses a real idea into a phrase the reader
has to decompress before they can even start evaluating the concern.

Two ways to fix one:

- Replace it with what it actually means here. "load-bearing" becomes "this value is
  depended on by X, and if X changes this breaks".
- Or keep the term and define it inline, in half a sentence, right where it appears.

This rule governs **generated review comments**. The skill's own internal notes about
build steps and escaping stay as precise as they need to be.

### Evidence discipline

- Include only the evidence needed to understand and trust the finding. You will
  usually have found more than that; leave the rest out.
- No implementation history. How the code got this way is almost never the reader's
  problem.
- No long chains of reasoning inside one paragraph. Short paragraphs, simple sentences.
- Avoid speculative edge cases unless they are realistically reachable from the code as
  it stands now.
- No em dashes, matching the Writing style rules in `SKILL.md`.

### Check every body before you inject it

- Can someone understand this after reading it once?
- Is the actual problem stated before the technical proof?
- Does it explain behavior that can really happen, rather than restating the code?
- Are cross-file and cross-class relationships explained rather than assumed?
- Is the implementation history gone?
- Would simpler words carry the same information without losing it?
- Does the stated seriousness match the real seriousness?

If a finding cannot be explained simply, your own understanding of it is the thing that
needs simplifying, not the wording. If it still will not come out clearly, it is not
ready: demote it to `nit` or drop it. This sits alongside the `disproof` rule in §2,
which already says an unfalsifiable concern is not an `important` finding.

### A rewrite, before and after

Too dense:

> The batch narrows forward product counts to the source's own delivery type while the
> single-source evaluator counts all types, so the two can return different
> actualCounts for the same source.

Clear:

> Here we only count rows matching the price source's current `delivery_type_id`, but
> `EvaluateForwardCheck` does not apply that filter. This means the batch check and the
> single-source check can return different counts for the same price source. For
> example, this can happen if the delivery type changes while older rows still exist.
> Could we make both paths use the same filtering rule?

Too dense:

> `subDays(3)` is load-bearing but unexplained.

Clear:

> `subDays(3)` depends on how far `lastCompletedDeliveryDay()` can look back. Three days
> is enough with the current logic, but if that lookback changes later this query may
> stop loading enough data. Could we add a comment explaining that dependency, or derive
> the value from the same source?

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
      "body": "This line now throws when the date can't be parsed. Before this change the same input quietly returned an empty string, so this is a correctness risk for code that already calls formatDate.\n\nAny caller that passes bad input and expects '' back will now get an exception instead, and most of them won't be wrapped in a try/catch, because until now there was nothing to catch.\n\nFor example, a page rendering a record with a missing date used to show a blank cell. Now it fails while rendering that cell.\n\nCould we return '' here instead, matching the existing !d branch a few lines above?",
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
      "body": "The new invalid-date branch in formatDate.js isn't covered by any test here, so a future change could break that path and every test would still pass. Worth adding one case for it.",
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
