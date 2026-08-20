# Markdown PR body: conventions and worked example

The Markdown body fills the repo's PR template and works on its own. A reviewer who never
opens the HTML page must still get the whole explanation from the GitHub-rendered
Markdown. It never links back to the local review page (see §3).

Write it as a story a reviewer can follow with no other context. Do not repeat the ticket
in different words. The reader is always the same: they have never seen this feature, they
do not know the architecture, and they do not know the business words your team uses. They
can read basic code, but they should not need to read code to understand the PR. The test
you can check: a reader should understand the problem and the expected behavior without
opening the diff. If they need the code to follow the story, PR-Narrative failed.

Use simple English. Short sentences and common words. Keep real technical names such as
class names, method names and database terms, but explain everything around them in easy
words. Writing simply does not mean writing less technically.

Assume the reader has not read the ticket or the commit message. Every claim in the body
must come from the diff or from code you actually read. Use the ticket only to check names
and numbers, never to copy sentences from.

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
> Images that are not needed are removed before download, so a bundle only fetches the
> images we actually want.

> [!TIP]
> Small jobs of two images or fewer still use the old one-request-per-image method, so
> single-page behavior does not change.

> [!WARNING]
> The archive is kept in memory while it is unpacked. Watch memory use if a folder can
> hold unusually large files.
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
| Multi-folder job (3 folders)  | ~135            | 3              |
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
> A styled before-and-after page for this change was shared separately. The text below
> explains the whole change on its own, without that page.
```

If the user wants the visual embedded some other way (drag-dropped screenshots in the
PR comment, for example), that's a separate action outside the Markdown body itself;
the skill never uploads or opens the PR.

---

## 4. The default body structure

When the repo has no PR template, use these 11 sections in exactly this order. There are
two parts: sections 1-9 explain the change in plain language, and sections 10-11 give the
technical details. Always explain the change first, then give the details. Never the other
way around.

### In one sentence

The hardest sentence. One plain statement of what this PR does. If you cannot write it
without method names, class names, or architecture terms, you do not understand the change
well enough yet.

### The problem

What someone was trying to do, and what went wrong. Put `Closes #N` at the start or the
end when a ticket is linked. Do not describe a general problem. Name the real situation
that started the work.

### What happens today

How things work before this PR: the manual workaround, the missing feature, or the broken
behavior a user can see. For a brand new feature, describe what people cannot do today, or
what is difficult. Never invent a bug just to make the story more dramatic.

### Why that's a problem

The result. Who it hurts, what it costs, or why the current state is unsafe. Keep it
concrete.

### What changes

One simple sentence first, then more technical detail if needed. If the change is so small
that no real example exists, drop the Example section and say why in one line here.

### Before and after

A short example or a comparison table that shows the same situation with the old code and
with the new code. Use arrows, tables, or numbered steps. Do not list file paths or
identifiers.

### Example

One true, concrete walk-through with small made-up numbers. Required for any change that
is not trivial. Show an input, the steps that follow, and the output. If no true concrete
example exists, drop this section and explain why under What changes.

### What QA should test

Real behavior a tester can check, not a checklist written for its own sake. Write what a
human tester would do, and what they should see.

### What this does not change

This section limits the scope. Say clearly which nearby behavior stays the same, so QA and
reviewers do not imagine a bigger change than the diff contains.

### Technical details

The only section where identifiers (method names, class names, file paths) are allowed,
and only where a plain sentence cannot carry the meaning. Still not allowed here:
file-by-file changelogs, repeating the diff, or "then I refactored X" narration. Sections
1-9 hold ideas only.

### Risks / trade-offs

State the limits honestly: performance cost, behavior someone may dislike, cases the code
still does not handle, and work that still needs doing.

### The two layers

Sections 1-9 explain the change to a person. Sections 10-11 support that explanation with
technical facts. Never start from the code and add the reason afterwards.

### Trivial vs non-trivial

A change is trivial only when no user and no tester can see any difference in behavior, and
nothing can break because of it: a typo fix, a comment, a rename, formatting, or removing
dead code. The number of files is not the test.

For trivial PRs, use only the Core-4 sections:

1. In one sentence
2. The problem
3. What changes
4. What this does not change

`Example` and `What QA should test` become mandatory the moment the change is
non-trivial.

### 8-question checklist

Every non-trivial PR must answer these eight questions, in this order. Use them to write
the description and to check it afterwards. They are not a list of one question per
section.

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
2. The API returns an empty page, because that slice happens to be empty right now.
3. Old path: the reader sees `{}` → stops → finishes early.
   New path: the reader sees `{}` → keeps the cursor → tries page 41 → stops only
   at the real end of the data.
4. Result: all 65 pages are read. One empty page in the middle no longer ends the
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
- Put each remaining section into the closest matching template section. Background / Why /
  Motivation sections take The problem, What happens today, and Why that's a problem.
  Description / How / Changes sections take What changes and Before and after.
- If QA, Example, Risks, or What this does not change content does not fit any template
  section, add it after the template's own sections and keep the standard headings.
- Put `Closes #N` at the end of the background-like section, not at the top of the body.
- If the branch also contains unrelated work, add a short `### Also bundled in this branch`
  list under the closest template section and say so honestly. Do not present unrelated
  work as one change.
- If the repo has no template, fall back to the default 11-section structure in §4.

---

## 6. Title conventions

Follow the repo's convention. Conventional-commit style, readable as a release-note
line, is a safe default:

- `feat(thumbnails): batch downloads via CDN bundle endpoint`
- `fix(uploads): stop large batches failing with rate-limit errors`

If the repo excludes some changes from release notes (e.g. an `[Internal]` marker),
respect that. Mention any relevant labels to the user; the skill doesn't apply labels
itself.

---

## 7. Full worked example

A finished Markdown body for the generic thumbnail-batching change sits next to this
reference at `examples/pr-body-thumbnails.md`. It sounds like a colleague explaining the
change, not like the ticket repeated back to you. Every fact in it comes from the diff, and
it is written for someone who never opened the ticket. Notice what it does *not* contain:
no file list and no method names. It has the situation, the idea, a link to the visual, a
table, and an honest trade-off. Read it as the standard, then write the real one the same
way.
