# PR Narrative

[![Install with npx skills](https://img.shields.io/badge/npx%20skills%20add-hamedghaderi%2Fpr--narrative-black?logo=npm)](https://github.com/vercel-labs/skills)

Review pull requests as a story, not a wall of code.

PR Narrative adds a human review layer between coding agents and GitHub, on both sides
of a pull request:

- **Reviewer mode:** review a real diff in an interactive browser UI, accept or reject AI findings, and create one pending GitHub review
- **Author mode:** turn your branch diff into a reviewer-friendly PR description

```bash
npx skills add hamedghaderi/pr-narrative
```

### 22-second demo: a cold diff becomes an annotated review

https://github.com/user-attachments/assets/2f2cb4b7-e87d-43bc-830b-5129ebfa8110

## Why not just ask an agent to review the PR?

You can, and it will find real things. The gap isn't analysis quality, it's what
happens to the findings afterwards. Ask an agent to review a PR and you get prose in a
terminal: not attached to any line, invisible to your teammates, and changing nothing on
the PR itself.

| | Plain agent prompt | Reviewer mode |
|---|---|---|
| Where findings land | Terminal scrollback | A pending review on the PR, anchored to real diff lines |
| How many you get | Unbounded | Hard cap: 3 per file, 10 per review |
| What it comments on | Depends on the prompt and model | Four categories only: probable bugs, security, missing error handling, breaking-change risk |
| How findings are triaged | Manually interpreted and copied from chat or terminal output | Each finding is visibly accepted or rejected before submission |
| Who signs the review | Ambiguous | You do. The skill never sets Approve, Request changes, or Comment |

The cap is the constraint that matters most. An unconstrained agent has no reason to
stop at three findings in a file, so it writes eleven, and the two that mattered get
buried under nine that didn't. Seeding zero findings is an explicitly valid outcome:
when nothing in the diff clears the bar, the page opens with no AI comments at all.

## How it works

### Reviewer mode

PR URL or local branch → narrative context → interactive diff → accept or reject AI
findings → **pending GitHub review**, or a local fix-list

The page puts the narrative up top and the real diff below it. Click a line to comment,
drag across a few lines for a range, or leave a suggestion. AI-drafted callouts arrive
unaccepted, so nothing reaches GitHub that you didn't keep. On Submit, your accepted
comments post as a single pending review that you finalize yourself on github.com.
Reviewing a local branch posts nothing anywhere.

### Author mode

Branch diff → narrative PR body → section-by-section approval → revision loop →
**final Markdown**

It writes the description from the code rather than the ticket. You Approve or
Request-change each section, your decisions go back through a small bundled local
server, and it revises until everything is approved. The body fills your repo's PR
template and stands on its own.

Both modes avoid mermaid diagrams, file-by-file changelogs and method-name dumps, and
Author mode never opens the PR for you.

## Example output

Both artifacts below come from one invented scenario: a service that fetched product
thumbnails one at a time and hit a CDN rate limit, and now pulls a whole category as a
single bundle.

![Author-mode review page for the thumbnail-batching example](examples/screenshots/hero-review-page.png)

*The before panel shows one-request-per-image calls hitting a red `429` and stalling the
rest of the batch; the after panel shows the single `?bundle` request unpacking into
file chips instead.*

![Section-level Approve / Request-change controls](examples/screenshots/section-controls.png)

*Two adjacent sections, two independent verdicts: "Description" is green "Approved",
"Before → After" is amber "Changes requested". Each section carries its own state until
every one is approved.*

The Markdown body that ships alongside the page makes the same change concrete:

| | Before | After |
|---|---|---|
| Requests to the CDN | 45 (one per image) | 1 bundle plus rare fallbacks |
| Where it fails | Aborts on the ~6th request (`429`) | Completes; only genuinely missing images fall back |
| Images actually built | 5 of 45 | 45 of 45 |

The full generated pair, the [Markdown body](./examples/pr-body-thumbnails.md) and its
[HTML visual](./examples/pr-thumbnails.html), lives in [`examples/`](./examples).

## Works with

PR Narrative uses the open `SKILL.md` format and installs through the
[`skills` CLI](https://github.com/vercel-labs/skills) for **Claude Code**, **OpenCode**,
**Cursor**, **Codex** and
[other supported agents](https://github.com/vercel-labs/skills#supported-agents).

Running it needs an agent that can execute shell commands and open a browser. The live
review server is optional, but using it also means the agent has to hold a background
process open.

## Installation

```bash
npx skills add hamedghaderi/pr-narrative
```

The CLI clones the repo, finds the `pr-narrative` skill, detects your agent, and
installs it to the right directory. For flags like `--list`, `-g` and `--copy`, see the
[`skills` CLI docs](https://github.com/vercel-labs/skills).

<details>
<summary><strong>Requirements by mode</strong></summary>

| Requirement | Reviewer mode | Author mode |
|---|---|---|
| An agent with shell access | Required. Backgrounding a process is needed only for the optional live server | Required, same |
| `git` and a browser | Required | Required |
| `gh`, authenticated | Only to review a real PR; reviewing a local branch needs none | Never used. Reads your local git history only |
| `python3` | Optional. Runs the live review server; without it the page falls back to a download button | Optional, identical fallback |

</details>

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
a PR".

**To write a description:** "write the PR for this branch", "make a PR description for
these changes", "describe this change for review".

> ⭐ If this improves your review workflow, star the repository so other developers can
> find it.

## License

[MIT](./LICENSE)
