---
name: pr-narrative
description: >
  Write pull-request descriptions that read like a clear explainer instead of a
  code dump, then review them interactively in the browser. Use this whenever the
  user asks to write, draft, generate, review, or improve a PR description / PR body
  / PR write-up — or says things like "make a PR for this branch", "write the PR",
  "describe these changes for review", or wants a PR that explains the *why* and the
  *intuition* behind a change with a rich styled before/after visual, callouts, and
  comparison tables. Produces an interactive, self-contained HTML review page that
  auto-opens in the browser (report-quality before/after panels + callouts like the
  explain-diff skill's visuals, PLUS per-section Approve / Request-change controls
  and a Download-decisions button), and a GitHub-flavored Markdown PR body that fills
  the repo's PR template, leads with a narrative Background + Description, uses GitHub
  [!NOTE]/[!TIP] callouts and comparison tables. The user reviews section by section
  in the browser, exports their decisions, and the skill revises until every section
  is approved. Deliberately avoids mermaid diagrams, file-by-file changelogs, and
  method-name dumps. Do NOT use for code review scoring, commit messages, or release
  notes.
---

# PR Narrative

Most PR descriptions are written for the author, not the reviewer. They list which
files changed and restate the diff in prose — information the reviewer can already
see. The result is a wall of text that adds no understanding.

A *good* PR description does the opposite: it gives the reviewer the context and the
mental model they need **before** they read a single line of the diff. It answers
"why does this change exist?" and "what's the core idea?" — and it uses a clear
before/after picture, small examples, and comparisons to do it, because those
compress understanding far better than paragraphs or a mermaid box-and-arrow blob.

This skill produces that. It mirrors the look and feel of the `explain-diff` skill's
**Background** and **Intuition** — the styled panels, the callouts, the concrete toy
data — but shaped for a PR.

## What you produce — an interactive review page + a Markdown body

1. **An interactive HTML review page** (`/tmp/YYYY-MM-DD-pr-review-<branch>.html`) —
   self-contained, inline CSS/JS, no server. This is the centerpiece and it **opens
   automatically in the browser**. It holds the *rich visual* (report-quality
   before/after panels — colored request rows, a red failure, an "extract" step,
   little file chips — plus the Background and Description narrative, exactly the
   look people love from `explain-diff`), and on top of that, each section carries an
   **Approve / Request-change** control and a comment box, with a **Download
   decisions** button. The user reviews section by section right in the page. Build
   the visuals the same way `explain-diff` does: one clean page, styled panels, **no
   mermaid, no ASCII diagrams**.

2. **A Markdown PR body** (`/tmp/pr-body-<branch>.md`) — GitHub-flavored, fills the
   repo's PR template, and is *complete on its own*: a reviewer who never opens the
   HTML still gets the full narrative from the Markdown, using GitHub callouts and
   comparison tables. It **links to the review page** for the rich visual.

Do **not** run `gh pr create` or open a PR — this skill produces (and helps the user
review) the description; the user decides when to open the PR.

### The review loop (this is the point of the skill)

The skill is not "generate and done" — it's a loop:

**generate → auto-open review page → user approves/requests changes per section →
user clicks Download decisions → agent reads the decisions file → revises the
requested sections → re-open → repeat until everything is approved.**

When every section is approved, finalize the Markdown body and hand it over (print it
inline so the user can copy it). See `references/review-ui.md` for the exact
interactive HTML (the per-section control bar, the JS that tracks decisions and
exports `pr-review-decisions.json`, the decisions schema, and what to do after the
user exports).

For the visual styling itself (CSS for the panels, request rows, badges, file chips,
callouts) read `references/html-visual.md`. For the Markdown conventions (GitHub
callout syntax, tables, template filling) read `references/markdown-body.md`.

## What this skill is (and isn't)

- **Is:** a narrative, visual PR description — the *why* and the *essence* — with a
  styled HTML before/after visual and a clean Markdown body.
- **Isn't:** a code review, a quality/confidence score, a per-file changelog, a
  commit message, or release notes. If the user wants a full standalone teaching
  document with a code walkthrough and a quiz, that's `explain-diff`.

The most common failure mode is drifting into a file-by-file "I changed X in Y, then
refactored Z" listing, or dumping method names ("`downloadSourceFilesInBulk()`
groups the files…"). Reviewers don't need that — the diff shows the *what* and the
*where*. Your job is the *why* and the *idea*. Explain at the level of concepts, not
identifiers.

## The workflow

### 1. Understand the change before writing a word

You cannot explain a change you don't understand. Gather context first:

- Get the diff and history against the base branch (usually `master`/`main`):
  `git diff --stat <base>...HEAD`, `git log --oneline <base>..HEAD`,
  `git diff <base>...HEAD -- <key files>`.
- Read the **actual changed code**, not just the diff summary. Understand the system
  *before* the change well enough to explain it to a newcomer.
- Find the linked issue/ticket (branch name, "Closes #…"). The ticket usually states
  the real problem — the "why".
- If the branch bundles several unrelated changes, say so honestly, build the visual
  and narrative around the *primary* change, and summarize the rest in a short list.

For non-trivial or multi-module changes, fire `explore` agents in parallel to map the
before/after and the call sites. Understanding is the expensive part; the writing is
cheap once you get it.

### 2. Find the intuition

Before writing, answer these in one or two sentences each:

- **The problem.** What was broken, missing, or painful? What breaks if we do nothing?
  Use concrete toy data ("a 30-day backfill fired 30 sequential requests").
- **The core idea.** If you explained the fix to a colleague in the hallway in 20
  seconds, what would you say? That sentence opens the Description.
- **The before/after.** What did the old path look like, and the new one? This becomes
  your styled visual.
- **The trade-off.** What did this approach cost or rule out? Reviewers trust an honest
  PR more.

If you can't answer these, you don't understand the change yet — go back to step 1.

### 3. Build the interactive review page, serve it, and open it

Create the self-contained HTML review page: the report-quality before/after panels +
Background/Description narrative (styling from `references/html-visual.md`), with each
reviewable block wrapped in a `<section data-review-id="…">` carrying the Approve /
Request-change control bar, plus the sticky action bar and the submit JavaScript
(all from `references/review-ui.md`). Set `<body data-branch="…">` so decisions are
tagged. Save to `/tmp/YYYY-MM-DD-pr-review-<branch>.html`.

Then start the **live review server** in the background and open the URL it prints:

```bash
python3 <skill>/scripts/review_server.py \
  --page /tmp/YYYY-MM-DD-pr-review-<branch>.html \
  --out  /tmp/pr-review-decisions.json &
# it prints:  PR_REVIEW_URL http://127.0.0.1:<port>/
open "http://127.0.0.1:<port>/"
```

Tell the user to review each section and click **Submit review** when done. This is
the moment the skill becomes interactive — don't just write the file and stop. (If
Python 3 isn't available, skip the server and just `open` the HTML file directly; the
page falls back to a Download-decisions button.)

### 4. Write the Markdown body, filling the repo's template

Detect and respect the repo's PR template (e.g. `.github/pull_request_template.md`).
Keep its section headers and required checklists. Many templates use a "why / how"
shape — e.g. `## Background (Why?)` and `## Description (How?)` — which maps directly
onto this skill.

Fill them with narrative, using GitHub `> [!NOTE]` / `> [!TIP]` callouts for
definitions and edge cases, and Markdown comparison/benchmark tables for the
before/after numbers. Near the top of the Description, link to the review page. See
`references/markdown-body.md` for conventions and a worked example. Save to
`/tmp/pr-body-<branch>.md`.

### 5. Run the review loop

Wait for the decisions to come back. In **live mode** the server writes
`/tmp/pr-review-decisions.json` and exits (`PR_REVIEW_DONE`) the moment the user hits
Submit — wait for that file to appear (poll it, or wait on the background process),
then read it. In **fallback mode** read `~/Downloads/pr-review-decisions.json` (check
for `pr-review-decisions (1).json` if exported more than once).

If `overall` is `approved`, finalize and print the Markdown body inline. Otherwise,
revise each `changes_requested` section per its comment, leave approved sections
untouched, regenerate the review page, restart the server, re-open it, and repeat
until everything is approved. See `references/review-ui.md` for the decisions schema
and the exact behavior.

## Writing style

Write with the clarity and flow of a good technical essayist — engaging, plain, with
smooth transitions. The reviewer is a smart colleague missing *your* context, not a
beginner. Respect their time: every sentence should give understanding they lacked.

- **Lead with the point.** The first two sentences of Background make the problem
  obvious. The first sentence of the Description is the core idea.
- **Concrete toy data over abstractions.** "30 sequential requests → HTTP 429" beats
  "many requests were made".
- **Show, don't tell.** The styled before/after visual and a comparison table beat
  three descriptive paragraphs.
- **Ideas, not identifiers.** Explain what happens conceptually. Don't narrate method
  names or file paths — the diff has those.
- **Be honest about limits.** A noted trade-off or edge case builds trust and saves
  review round-trips.
- **Cut anything the diff already says.** If a sentence just restates the diff, delete
  it unless the *reason* is interesting.

## Quality bar — before you open the review page

Re-read both artifacts as if you were the reviewer:

- Could a reviewer who's never seen this code understand *why* it exists from the
  Background alone?
- Is the core idea stated in one clear sentence at the top of the Description?
- Does the review page have a genuinely helpful styled before/after visual (not
  decoration), and does every reviewable section have its Approve / Request-change
  control bar wired up?
- Does the review page actually open in the browser, and does Download decisions
  export valid `pr-review-decisions.json`?
- Is the Markdown body complete on its own, and does it link to the review page?
- Did you avoid a file-by-file listing and method-name dumps? (If you see "then I
  changed…" or "`someMethod()` does…", cut or rephrase to the idea level.)
- Is the main trade-off named honestly?
- Does it fit the repo's template and title conventions (conventional-commit title,
  `[Internal]` when it shouldn't hit release notes)?

If any answer is "no", fix it before delivering.
