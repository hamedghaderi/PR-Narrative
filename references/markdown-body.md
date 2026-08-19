# Markdown PR body: conventions and worked example

The Markdown body fills the repo's PR template and is complete on its own: a reviewer
who never opens the HTML still gets the full narrative from GitHub-rendered Markdown.
It never links back to the local review page (see §3).

Write it as a short story a reviewer can follow without outside context, not a
paraphrase of the ticket. The reader model is fixed: assume the reader has never seen
this feature before, does not know the architecture, does not know the business
terminology, and can read basic code but should not need to read code to understand
the PR. The measurable test is: a reader should understand the problem and expected
behavior without opening the diff. If they need the code to understand the story,
PR-Narrative failed.

Assume the reader hasn't read the ticket or the commit message. Every claim in the
body should trace back to the diff or to code you actually read. The ticket is there
to fact-check names and numbers, never to lift sentences from.

All example content here uses a generic, invented scenario (batching image downloads
through a CDN bundle endpoint) purely to show the shape. Replace it with the real
change.

## Contents

1. GitHub callout syntax
2. Comparison / benchmark tables
3. No links to the local review page
4. The default body structure
5. Filling the repo's PR template
6. Title conventions
7. Full worked example (a finished Markdown body)

---

## 1. GitHub callout syntax

GitHub renders these blockquote callouts natively; use them for definitions and edge
cases (they mirror the Note/Tip panels in the HTML):

```markdown
> [!NOTE]
> Unwanted images are filtered out before download, so a bundle only fetches images
> worth having.

> [!TIP]
> Small jobs (≤ 2 images) keep the old per-image path, so the single-page case can't
> regress.

> [!WARNING]
> The archive is held in memory during unpacking; watch this if a folder ever holds
> unusually large files.
```

Available types: `[!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`, `[!CAUTION]`.

---

## 2. Comparison / benchmark tables

When the change is about performance or behaviour, show numbers. A table is enough.

```markdown
| Scenario                     | Requests before | Requests after |
| ---------------------------- | --------------- | -------------- |
| Single product page (1 img)  | 1               | 1 (unchanged)  |
| Category rebuild (45 imgs)   | 45              | 1              |
| Supplier import (3 folders)  | ~135            | 3              |
```

Escape pipes inside cells as `\|`. Leave a blank line before the table.

---

## 3. No links to the local review page

The PR body is pasted into GitHub, and any local file path or loopback URL is dead the
moment it leaves your machine. Never embed the review page's local path or URL in the
Markdown body. If a visual companion exists, mention it in conversation with the user
("the review page is at…"), not inside the body. The body has to stand on its own: a
reviewer on GitHub gets the full story with nothing to open locally.

```markdown
> [!TIP]
> A styled before/after walkthrough of this change was shared separately as a visual
> companion. The narrative below tells the same story on its own.
```

If the user wants the visual embedded some other way (drag-dropped screenshots in the
PR comment, for example), that's a separate action outside the Markdown body itself;
the skill never uploads or opens the PR.

---

## 4. The default body structure

When the repo has no PR template, use these 11 sections in exactly this order. The
structure is two-layered: sections 1-9 are the human explanation, sections 10-11 are
the supporting technical layer. Apply the doctrine "Human explanation → Technical
explanation, never the reverse."

### In one sentence

The hardest sentence. A single plain-language statement of what this PR does. If it
cannot be written without method names, classes, or architecture jargon, the author
has not yet understood the change.

### The problem

What someone was trying to do and what went wrong. Preface or close with `Closes #N`
when a ticket is linked. This is not an abstract category; name the real situation
that started the work.

### What happens today

Life before this PR: the manual workaround, the missing capability, or the broken
behavior a user actually sees. For net-new features, describe what is impossible or
awkward today. Never manufacture a fake bug just to create narrative tension.

### Why that's a problem

The consequence. Who feels pain, what it costs, or why the current state is unsafe or
unacceptable. Keep it concrete.

### What changes

One simple sentence first, then technical elaboration if needed. If the change is
trivial enough that no concrete example exists, omit the Example section and state
why in one line here.

### Before and after

A compressed scene or comparison table that shows the same situation played out under
the old code and the new code. Use arrows, tables, or numbered steps; do not dump file
paths or identifiers.

### Example

One truthful, concrete walkthrough with toy numbers. Mandatory for any non-trivial
change. Show an input, the chain of events, and the output. If no truthful concrete
example exists, omit this section and explain why under What changes.

### What QA should test

Concrete behavioral verifications, not a checklist for its own sake. Write what a
human tester would actually do and expect to observe.

### What this does not change

The blast-radius limiter. Explicitly fence off adjacent behavior so QA and reviewers
do not imagine a larger change than the one in the diff.

### Technical details

The only place identifiers (method names, classes, file paths) are permitted, and
only where a concept-level sentence cannot carry the meaning. Still banned here:
file-by-file changelogs, diff restatement, "then I refactored X" narration. Sections
1-9 are ideas-only.

### Risks / trade-offs

Honest limits: performance cost, behavior someone might dislike, edge cases still not
handled, follow-up work needed.

### Two-layer doctrine

Sections 1-9 explain the change to a human. Sections 10-11 support that explanation
with technical facts. Never start from the code and try to tack on motivation
afterward.

### Trivial vs non-trivial

A change is trivial only when it produces no behavior a user or QA could observe or
regress (typo fix, comment, rename, formatting, dead-code removal). File count is not
the test.

For trivial PRs, use only the Core-4 sections:

1. In one sentence
2. The problem
3. What changes
4. What this does not change

`Example` and `What QA should test` become mandatory the moment the change is
non-trivial.

### 8-question checklist

Every non-trivial PR must answer these eight questions, in this order. They are a
derivation and validation tool, not a literal 1:1 section list.

1. What was someone trying to do?
2. What went wrong?
3. Why did it happen?
4. What does this PR change?
5. What happens differently now?
6. Give me one concrete example.
7. What should QA verify?
8. What does this PR deliberately NOT solve?

The mapping to the 11 sections:

| Question | Default section |
| --- | --- |
| 1 | The problem |
| 2 | The problem + What happens today |
| 3 | What happens today + Why that's a problem |
| 4 | In one sentence + What changes |
| 5 | Before and after |
| 6 | Example |
| 7 | What QA should test |
| 8 | What this does not change |

### Closes #N placement

Put `Closes #N` at the end of `## The problem` in the default structure, or at the end
of the mapped background-like section when filling a repo template.

### Worked micro-example

A pagination fix gives us 65,000 rows, a page size of 1,000, and page 40 temporarily
empty. The body might render the Example section like this:

```markdown
## Example

1. A job asks for page 40 of a 65,000-row dataset with page size 1,000.
2. The upstream source returns an empty page because that slice is temporarily blank.
3. Old path: importer sees `{}` → stops → finishes the import early.
   New path: importer sees `{}` → keeps a cursor → tries page 41 → finishes only
   after the real end of the data.
4. Result: all 65 pages are imported; the temporary empty page does not abort the
   job.
```

---

## 5. Filling the repo's PR template

Detect the repo's PR template (usually `.github/pull_request_template.md`) and keep its
exact section headers and checklists verbatim. Do not invent new `##` sections inside
the template. Instead, map the narrative order into the template's existing shape.

- Open the body with the In-one-sentence content as a bold lead-in line above the
  first template header: `**In one sentence:** ...`. No new `##` header is inserted;
  the repo template's own headers stay untouched.
- Pour each remaining section into the closest matching template section. Background /
  Why / Motivation sections take The problem, What happens today, and Why that's a
  problem. Description / How / Changes sections take What changes and Before and
  after.
- QA, Example, Risks, or What this does not change content with no natural home is
  appended as extra sections after the template's own sections, keeping the canonical
  headings.
- Put `Closes #N` at the end of the mapped background-like section, not at the top of
  the body.
- If the branch bundles unrelated work, add a brief `### Also bundled in this branch`
list under the most relevant template section and say so honestly, rather than
pretending it's one story.
- If the repo has no template, fall back to the default 11-section structure in §4.

---

## 6. Title conventions

Follow the repo's convention. Conventional-commit style, readable as a release-note
line, is a safe default:

- `feat(thumbnails): batch downloads via CDN bundle endpoint`
- `fix(import): stop bulk rebuild failing with rate-limit errors`

If the repo excludes some changes from release notes (e.g. an `[Internal]` marker),
respect that. Mention any relevant labels to the user; the skill doesn't apply labels
itself.

---

## 7. Full worked example

A finished Markdown body for the generic thumbnail-batching change lives alongside this
reference at `examples/pr-body-thumbnails.md`. It reads like something a teammate told
you at your desk, not like the ticket read back to you: every fact in it traces to the
diff, and it's written for someone who never opened that ticket. Notice what it does
*not* contain: no file list, no method names, just the scene, the idea, a visual link,
a table, and an honest trade-off. Read it as the quality bar, then write the real one
the same way.
