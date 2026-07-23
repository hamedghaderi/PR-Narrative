# Markdown PR body — conventions and worked example

The Markdown body fills the repo's PR template and is complete on its own: a reviewer
who never opens the HTML still gets the full narrative from GitHub-rendered Markdown.
It links to the HTML file for the rich before/after visual.

Write it as a short story a reviewer can follow without outside context, not a
paraphrase of the ticket. Assume the reader hasn't read the ticket or the commit
message, and might be a junior developer on the team: they need every technical fact
that matters, just not the assumed background you already carry in your head. Every
claim in the Background and Description should trace back to the diff or to code you
actually read. The ticket is there to fact-check names and numbers, never to lift
sentences from.

All example content here uses a generic, invented scenario (batching image downloads
through a CDN bundle endpoint) purely to show the shape. Replace it with the real
change.

## Contents

1. GitHub callout syntax
2. Comparison / benchmark tables
3. Linking to the HTML companion
4. Filling the repo's PR template
5. Title conventions
6. Full worked example (a finished Markdown body)

---

## 1. GitHub callout syntax

GitHub renders these blockquote callouts natively — use them for definitions and edge
cases (they mirror the Note/Tip panels in the HTML):

```markdown
> [!NOTE]
> Unwanted images are filtered out before download, so a bundle only fetches images
> worth having.

> [!TIP]
> Small jobs (≤ 2 images) keep the old per-image path — the single-page case can't
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

## 3. Linking to the HTML companion

Near the top of the Description, point the reviewer at the styled visual. Since the
HTML lives outside the repo (`/tmp/...`), tell the user how it's meant to be shared —
usually they open it locally, or paste screenshots of the panels into the PR comment.
Phrase it plainly:

```markdown
> [!TIP]
> A styled before/after walkthrough of this change is in the visual companion:
> `/tmp/2026-07-22-pr-thumbnails.html` — open it locally, or drop the panels into the
> PR as images.
```

If the user has already told you how images get into their PRs (drag-drop upload,
etc.), adapt the wording. The skill itself never uploads or opens the PR.

---

## 4. Filling the repo's PR template

Detect the repo's PR template (usually `.github/pull_request_template.md`) and keep its
exact section headers and checklists. Many templates use a "why / how" shape — for
example a template with `## Background (Why?)` and `## Description (How?)` maps
directly onto this skill:

- **Background / Why** → tell it as a small scene: what the system does today, what
  concretely goes wrong, and why that actually hurts someone. Pull every detail from
  the diff or from code you've read, not from the ticket; the ticket is only there to
  check you got a name or a number right. Write for a reviewer who hasn't seen the
  ticket and might be junior: keep the technical facts, drop the assumed context. Add
  a `> [!NOTE]` for any term a newcomer would trip on. End with `Closes #xxxx` if
  there's a linked issue. If the story fits in one line, one line is enough; don't pad
  it into paragraphs it doesn't need.
- **Description / How** → open with the one-sentence core idea, in plain words, then
  show what things look like now that it's fixed. Link to the HTML visual, walk the
  before/after in a sentence or two plus a comparison table, and name the trade-off
  honestly. **No method-name dumps, no file-by-file listing.** One idea per
  paragraph; if a paragraph is doing two jobs, split it.
- **Affected areas / models** (if the template has it) → a *short* bulleted list of
  surfaces, not files.
- **Testing / QA** → a couple of concrete things worth checking, not a checklist for
  its own sake.

If the branch bundles unrelated work, add a brief `### Also bundled in this branch`
list under the Description and say so honestly, rather than pretending it's one story.
If the repo has no template, fall back to the structure in `SKILL.md`.

---

## 5. Title conventions

Follow the repo's convention. Conventional-commit style, readable as a release-note
line, is a safe default:

- `feat(thumbnails): batch downloads via CDN bundle endpoint`
- `fix(import): stop bulk rebuild failing with rate-limit errors`

If the repo excludes some changes from release notes (e.g. an `[Internal]` marker),
respect that. Mention any relevant labels to the user; the skill doesn't apply labels
itself.

---

## 6. Full worked example

A finished Markdown body for the generic thumbnail-batching change lives alongside this
reference at `examples/pr-body-thumbnails.md`. It reads like something a teammate told
you at your desk, not like the ticket read back to you: every fact in it traces to the
diff, and it's written for someone who never opened that ticket. Notice what it does
*not* contain: no file list, no method names, just the scene, the idea, a visual link,
a table, and an honest trade-off. Read it as the quality bar, then write the real one
the same way.
