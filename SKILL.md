---
name: pr-narrative
description: >
  Write pull-request descriptions that read like a clear explainer instead of a
  code dump. Use this whenever the user asks to write, draft, generate, or improve
  a PR description / PR body / PR write-up — or says things like "make a PR for
  this branch", "write the PR", "describe these changes for review", or wants a PR
  that explains the *why* and the *intuition* behind a change with a rich styled
  before/after visual, callouts, and comparison tables. Produces TWO artifacts: a
  self-contained styled HTML file (report-quality before/after panels, file chips,
  callouts — like the explain-diff skill's visuals) saved outside the repo, AND a
  GitHub-flavored Markdown PR body that fills the repo's PR template, leads with a
  narrative Background + Description, uses GitHub [!NOTE]/[!TIP] callouts and
  comparison tables, and links to the HTML for the rich visual. Deliberately avoids
  mermaid diagrams, file-by-file changelogs, and method-name dumps. Do NOT use for
  code review, confidence scores, commit messages, or release notes.
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

## What you produce — two artifacts

1. **A styled HTML file** (`/tmp/YYYY-MM-DD-pr-<branch>.html`) — self-contained,
   inline CSS, no dependencies. This holds the *rich visual*: the report-quality
   before/after panels (colored request rows, a red failure, an "extract locally"
   step, little file chips), plus the Background and Description narrative. This is
   the artifact that looks like the thing the user loves. Build it the same way
   `explain-diff` builds its HTML: one clean page, styled panels, **no mermaid, no
   ASCII diagrams** — use real HTML/CSS for the visuals.

2. **A Markdown PR body** (`/tmp/pr-body-<branch>.md`) — GitHub-flavored, fills the
   repo's PR template, and is *complete on its own*: a reviewer who never opens the
   HTML still gets the full narrative from the Markdown, using GitHub callouts and
   comparison tables. It **links to the HTML file** for the rich before/after visual.

Print the Markdown body inline at the end so the user can read/copy it immediately.
Do **not** run `gh pr create` or open a PR unless the user explicitly asks — this
skill produces the description; the user decides when to open the PR.

For the exact HTML styling (CSS for the panels, request rows, badges, file chips,
callouts) and a full worked example of both artifacts, read
`references/html-visual.md`. Consult it whenever you build the HTML or want the
quality bar. For the Markdown conventions (GitHub callout syntax, tables, template
filling), read `references/markdown-body.md`.

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

### 3. Build the styled HTML visual

Create the self-contained HTML file with the report-quality before/after panels and
the Background + Description narrative. Follow `references/html-visual.md` for the CSS
and structure. Save to `/tmp/YYYY-MM-DD-pr-<branch>.html` (outside the repo, dated
prefix so files stay time-sorted).

### 4. Write the Markdown body, filling the repo's template

Detect and respect the repo's PR template (e.g. `.github/pull_request_template.md`).
Keep its section headers and required checklists. Many templates use a "why / how"
shape — e.g. `## Background (Why?)` and `## Description (How?)` — which maps directly
onto this skill.

Fill them with narrative, using GitHub `> [!NOTE]` / `> [!TIP]` callouts for
definitions and edge cases, and Markdown comparison/benchmark tables for the
before/after numbers. Near the top of the Description, link to the HTML file for the
rich visual (e.g. *"See the visual before/after walkthrough: `<path>`"*). See
`references/markdown-body.md` for conventions and a worked example.

Save to `/tmp/pr-body-<branch>.md` and print it inline.

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

## Quality bar — before you hand it over

Re-read both artifacts as if you were the reviewer:

- Could a reviewer who's never seen this code understand *why* it exists from the
  Background alone?
- Is the core idea stated in one clear sentence at the top of the Description?
- Does the HTML have a genuinely helpful styled before/after visual (not decoration)?
- Is the Markdown body complete on its own, and does it link to the HTML?
- Did you avoid a file-by-file listing and method-name dumps? (If you see "then I
  changed…" or "`someMethod()` does…", cut or rephrase to the idea level.)
- Is the main trade-off named honestly?
- Does it fit the repo's template and title conventions (conventional-commit title,
  `[Internal]` when it shouldn't hit release notes)?

If any answer is "no", fix it before delivering.
