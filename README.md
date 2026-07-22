# pr-narrative

An agent skill that writes **pull-request descriptions that read like a clear
explainer instead of a code dump.**

Most PR descriptions are written for the author, not the reviewer — they list which
files changed and restate the diff in prose the reviewer can already see. This skill
does the opposite: it gives the reviewer the *context* and the *mental model* they
need before they read a single line of the diff. It answers **"why does this change
exist?"** and **"what's the core idea?"**, using a styled before/after visual, small
concrete examples, and comparison tables.

It's modelled on the "Background" and "Intuition" of a change explainer, shaped for a
PR.

## What it produces

Two artifacts, plus an interactive review loop:

1. **An interactive HTML review page** — it **opens automatically in your browser**
   and shows the rich visual (report-quality before/after panels — colored request
   rows, a red failure, an "extract locally" step, file chips — and the
   Background/Description narrative), with **Approve / Request-change** controls and a
   comment box under each section. You review section by section and click **Submit**;
   your decisions go straight back to the agent via a small bundled local server
   (`scripts/review_server.py`, Python stdlib, no installs), which revises until every
   section is approved. If the server isn't running, the page falls back to a
   **Download decisions** button. No mermaid, no ASCII art — real HTML/CSS.
2. **A GitHub-flavored Markdown PR body** — fills your repo's PR template, is complete
   on its own (a reviewer who never opens the HTML still gets the full story), uses
   GitHub `> [!NOTE]` / `> [!TIP]` callouts and comparison tables, and links to the
   review page for the rich visual.

The loop is: **generate → auto-open review page → approve / request changes per
section → download decisions → agent revises → re-open → repeat until approved.**

It deliberately avoids **mermaid diagrams**, **file-by-file changelogs**, and
**method-name dumps**. It never opens a PR for you — you get the files and decide when
to create the PR.

> See [`examples/`](./examples) for a generated pair built from a generic, invented
> scenario: the [Markdown body](./examples/pr-body-thumbnails.md) and the
> [HTML visual](./examples/pr-thumbnails.html) (open it in a browser).

## Example output

The examples use a made-up scenario — a service that downloaded product thumbnails one
at a time (hitting a CDN rate limit) and now fetches a whole category as a single
bundle. The Markdown body leads with the problem and the core idea, then shows a
comparison table:

```markdown
## Background (Why?)

The catalog service downloads product thumbnails from the CDN one at a time. That's
fine for a single page, but bulk jobs — rebuilding a whole category — issue one HTTP
request per image, and the CDN rate-limits that pattern with `429`.

## Description (How?)

The core idea: the CDN can hand back a whole category folder as one `.zip` via a
`?bundle` endpoint. So instead of asking for each image one at a time, ask for the
category once and unpack it locally.

| Scenario                    | Requests before | Requests after |
| --------------------------- | --------------- | -------------- |
| Single product page (1 img) | 1               | 1 (unchanged)  |
| Category rebuild (45 imgs)  | 45              | 1              |
```

The HTML companion renders the same before/after as styled panels with `200`/`429`
badges and file chips.

## Installation

This is an agent skill (a `SKILL.md` plus reference files). Install it by copying the
skill folder into your agent's skills directory.

**Clone and copy:**

```bash
git clone git@github.com:hamedghaderi/PR-Review.git
# then copy the skill files into your skills directory as a folder named "pr-narrative"
```

Pick the location your agent uses:

```bash
# OpenCode / .agents-style skills:
mkdir -p ~/.agents/skills/pr-narrative
cp -R PR-Review/SKILL.md PR-Review/references ~/.agents/skills/pr-narrative/

# Claude Code / .claude-style skills:
mkdir -p ~/.claude/skills/pr-narrative
cp -R PR-Review/SKILL.md PR-Review/references ~/.claude/skills/pr-narrative/
```

Only `SKILL.md` and `references/` are needed for the skill to work; `examples/` is
just for reference.

## Usage

Once installed, the skill triggers when you ask your agent to write a PR description.
Natural phrasings that trigger it:

- "write the PR for this branch"
- "make a PR description for these changes"
- "describe this change for review"

The agent will read the diff against your base branch, understand the change, generate
the review page and open it in your browser. Review each section (Approve / Request
change), click **Download decisions**, and hand the file back; the agent revises until
you've approved everything, then gives you the final Markdown. Create the PR yourself
(the skill won't open it for you).

## Repository layout

```
.
├── SKILL.md                  # the skill definition + workflow
├── references/
│   ├── html-visual.md        # HTML/CSS for the before/after panels + worked example
│   ├── markdown-body.md      # GitHub callout/table conventions + worked example
│   └── review-ui.md          # interactive review page: controls, submit JS, decisions schema
├── scripts/
│   └── review_server.py      # live review server (stdlib): serves page, captures Submit, writes decisions
├── examples/
│   ├── pr-body-thumbnails.md   # a generated Markdown PR body (generic scenario)
│   └── pr-thumbnails.html      # the matching HTML visual (open in a browser)
├── README.md
└── LICENSE
```

## License

[MIT](./LICENSE)
