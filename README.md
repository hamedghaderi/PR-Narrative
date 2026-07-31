# PR Narrative

[![Install with npx skills](https://img.shields.io/badge/npx%20skills%20add-hamedghaderi%2Fpr--narrative-black?logo=npm)](https://github.com/vercel-labs/skills)

Review pull requests as a story, not a wall of code.

PR Narrative gives coding agents two workflows:

- **Author Mode:** turns your branch diff into a reviewer-friendly PR description
- **Reviewer Mode:** opens the real diff in an interactive browser UI where you can comment, triage AI findings, and submit one pending GitHub review

```bash
npx skills add hamedghaderi/pr-narrative
```

https://github.com/user-attachments/assets/2f2cb4b7-e87d-43bc-830b-5129ebfa8110

[`ai-agent`](https://github.com/topics/ai-agent) ·
[`code-review`](https://github.com/topics/code-review) ·
[`pull-request`](https://github.com/topics/pull-request) ·
[`developer-tools`](https://github.com/topics/developer-tools) ·
[`claude-code`](https://github.com/topics/claude-code) ·
[`opencode`](https://github.com/topics/opencode) ·
[`codex`](https://github.com/topics/codex) ·
[`cursor`](https://github.com/topics/cursor) ·
[`agent-skills`](https://github.com/topics/agent-skills)

## Works with

Any coding agent that loads `SKILL.md` files. The
[`skills` CLI](https://github.com/vercel-labs/skills) detects yours and installs to the
right directory: **Claude Code**, **OpenCode**, **Cursor**, **Codex**, and
[70+ more](https://github.com/vercel-labs/skills#supported-agents).

| Requirement | Author mode | Reviewer mode |
|---|---|---|
| `git` and a browser | Required | Required |
| `gh`, authenticated | Never used. Reads your local git history only | Only to review a real PR; reviewing a local branch needs none |
| `python3` | Optional. Runs the live review server; without it the page falls back to a download button | Optional, same |

## How it works

Reviewing a PR usually means opening a diff cold, with no context for why the change
exists and no way to gather your comments into an actual review. Writing one has the
mirror problem: the author understands the change, but the description rarely conveys
it, so the reviewer starts cold anyway.

### Reviewer mode

Point it at a PR, or at a local branch that doesn't have one yet. It builds a page with
the narrative context up top and the real diff below it: click a line to comment, drag
across a few lines for a range, or leave a suggestion. It can also pre-seed a small,
capped set of AI-drafted risk callouts, each shown visually distinct from your own
comments and unaccepted by default. You decide which ones to keep.

On Submit, your accepted comments post to the PR as a single **pending** review.
Nothing is finalized: you open the PR on github.com and click Approve, Request changes,
or Comment yourself. If a pending review from you already exists, the skill asks whether
to replace it rather than creating a second one.

Reviewing a local branch builds the same page but posts nothing anywhere. Submit hands
you a Markdown fix-list instead, alongside a **📋 Copy fix-list** button.

### Author mode

It writes the description from the code, not from the ticket: one a reviewer who has
never read the ticket, including a junior developer on the team, can follow in a single
read. You get two artifacts.

**An interactive review page** opens in your browser showing the before/after visual and
the Background/Description narrative, with **Approve / Request-change** controls and a
comment box under each section. Your decisions go back to the agent through a small
bundled local server (`scripts/review_server.py`, Python stdlib, no installs), which
revises until every section is approved. Without Python, the page falls back to a
**Download decisions** button.

**A GitHub-flavored Markdown PR body** that fills your repo's PR template, stands on its
own for a reviewer who never opens the HTML, and uses GitHub `> [!NOTE]` / `> [!TIP]`
callouts and comparison tables. A **📋 Copy PR description** button copies it once
approved.

Both modes avoid mermaid diagrams, file-by-file changelogs and method-name dumps, and
both stop short of the final action: reviewer mode never submits a verdict, author mode
never opens the PR. You always take that last step yourself.

## Example output

A made-up scenario: a service that downloaded product thumbnails one at a time, hit a
CDN rate limit, and now fetches a whole category as a single bundle.

```markdown
## Background (Why?)

The catalog service builds product thumbnails by asking the CDN for one image at a
time: a single request per thumbnail. That works fine on a product page, where only
one image is ever needed, but a category rebuild asks for every image in that
category back to back, with nothing pacing the requests out.

## Description (How?)

Category rebuilds now ask the CDN for the whole category as one `.zip`, through a
`?bundle` endpoint, instead of requesting each image on its own. The archive gets
unpacked locally, and only images the bundle doesn't have fall back to the old
per-image download.

For a category with 45 images:

| | Before | After |
|---|---|---|
| Requests to the CDN | 45 (one per image) | 1 bundle plus rare fallbacks |
| Where it fails | Aborts on the ~6th request (`429`) | Completes; only genuinely missing images fall back |
| Images actually built | 5 of 45 | 45 of 45 |
```

The HTML companion renders the same before/after as styled panels with `200`/`429`
badges and file chips. Both files live in [`examples/`](./examples).

## See it in action

![Author-mode review page for the thumbnail-batching example](examples/screenshots/hero-review-page.png)
The full page in the browser: the before panel shows the one-request-per-image calls
hitting a red `429` and stalling the rest of the batch, while the after panel shows the
single `?bundle` request unpacking into file chips instead.

![Section-level Approve / Request-change controls](examples/screenshots/section-controls.png)
Two adjacent sections, two independent verdicts: "Description" is already green
"Approved", while "Before → After" is amber "Changes requested" with a reviewer
comment already filled in. Each section carries its own state until every one is
approved.

> **Useful? Star it so other developers can find it.**

## Why not just ask an agent to review the PR?

You can, and it will find real things. The gap isn't analysis quality, it's what
happens to the findings afterwards.

Ask an agent to review a PR and you get prose in a terminal. It isn't attached to any
line, your teammates can't see it, and nothing on the PR itself changes. You're left
re-typing the useful parts into GitHub by hand, which is where most of them quietly
get dropped.

| | Plain agent prompt | Reviewer mode |
|---|---|---|
| Where findings land | Terminal scrollback | A pending review on the PR, anchored to real diff lines |
| How many you get | However many it feels like writing | Hard cap: 3 per file, 10 per review |
| What it comments on | Anything, including style opinions | Four categories only: probable bugs, security, missing error handling, breaking-change risk |
| Who decides what counts | Already written; you skim it | Every AI finding arrives unaccepted. Nothing reaches GitHub until you click Accept |
| Who signs the review | Ambiguous | You do. It posts as pending and never sets Approve, Request changes, or Comment |

The cap is the constraint that matters most. An unconstrained agent has no reason to
stop at three findings in a file, so it writes eleven, and the two that mattered get
buried under nine that didn't. Forcing a ceiling forces a ranking decision before the
page ever reaches you.

Seeding zero findings is an explicitly valid outcome. When nothing in the diff clears
the bar, the page opens with no AI comments at all rather than manufacturing something
so the feature looks busy.

## Installation

```bash
npx skills add hamedghaderi/pr-narrative
```

The CLI clones the repo, finds the `pr-narrative` skill, detects your agent, and
installs it to the right directory. No SSH keys, no manual copying. For flags like
`--list`, `-g` and `--copy`, see the
[`skills` CLI docs](https://github.com/vercel-labs/skills).

<details>
<summary><strong>Manual install (clone and copy)</strong></summary>

```bash
git clone https://github.com/hamedghaderi/pr-narrative.git

# OpenCode / .agents-style skills:
mkdir -p ~/.agents/skills/pr-narrative
cp -R pr-narrative/SKILL.md pr-narrative/references ~/.agents/skills/pr-narrative/

# Claude Code / .claude-style skills:
mkdir -p ~/.claude/skills/pr-narrative
cp -R pr-narrative/SKILL.md pr-narrative/references ~/.claude/skills/pr-narrative/
```

Only `SKILL.md` and `references/` are needed; `examples/` is just for reference.

</details>

## Usage

The skill triggers on either intent, and confirms which one with a single question
before it starts rather than guessing.

**To review:** "review this PR <url>", "review PR #42", "review my branch before I open
a PR". It fetches the PR, or diffs your branch locally when there's no PR yet, builds
the annotation page and opens it in your browser.

**To write a description:** "write the PR for this branch", "make a PR description for
these changes", "describe this change for review". It reads the diff against your base
branch, generates the review page, and revises until you've approved every section.

## License

[MIT](./LICENSE)
