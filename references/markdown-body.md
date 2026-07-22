# Markdown PR body — conventions and worked example

The Markdown body fills the repo's PR template and is complete on its own: a reviewer
who never opens the HTML still gets the full narrative from GitHub-rendered Markdown.
It links to the HTML file for the rich before/after visual.

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

- **Background / Why** → the problem + the system before. Lead with the pain in
  concrete terms. Add a `> [!NOTE]` for any key definition. End with `Closes #xxxx`
  if there's a linked issue.
- **Description / How** → the one-sentence core idea, the link to the HTML visual, the
  before/after in prose + a comparison table, and the honest trade-off. **No
  method-name dumps, no file-by-file listing.**
- **Affected areas / models** (if the template has it) → a *short* bulleted list of
  surfaces, not files.
- **Testing / QA** → plus, when useful, a couple of concrete things to check.

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
reference at `examples/pr-body-thumbnails.md`. Notice what it does *not* contain: no
file list, no method names — just the idea, a visual link, a table, and an honest
trade-off. Read it as the quality bar, then write the real one the same way.
