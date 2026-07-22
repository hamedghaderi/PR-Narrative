
# GitHub posting playbook — the exact `gh` commands for reviewer mode

This is the command-by-command playbook the agent follows to talk to GitHub in
reviewer mode: check before you touch anything, fetch what you need, post a
**PENDING** review, and stop. Every command below is copy-runnable — swap in the
real `{o}` (owner), `{r}` (repo), and `{n}` (PR number) parsed from the PR URL.

No GraphQL. No `gh pr create`. No `gh pr review` (that porcelain command submits a
verdict event — this skill never does that). The user always finalizes the review
on github.com.

## 1. Preflight (MUST run before rendering any UI)

Do these checks *before* building the annotation page. If any of them fail, stop
and tell the user — don't render a UI that's going to break at Submit time.

**`gh` binary present:**

```bash
command -v gh
```

Missing → stop. Tell the user: "The `gh` CLI is required for reviewer mode on
GitHub PRs. Install it from https://cli.github.com/ (macOS: `brew install gh`),
then run `gh auth login`."

**Authenticated:**

```bash
gh auth status
```

Non-zero exit → stop. Tell the user to run `gh auth login` and re-invoke.

**Parse owner/repo/number from the PR URL** (e.g.
`https://github.com/{o}/{r}/pull/{n}`) — `{o}`, `{r}`, `{n}` feed every command
below. If the user gave a bare `#{n}` instead of a URL, resolve `{o}/{r}` from the
current repo's `origin` remote.

**Confirm the PR exists and check its state:**

```bash
gh pr view {n} --repo {o}/{r} --json state,isDraft,title,headRefOid
```

- Non-zero exit / `state` missing → the PR number or repo is wrong — stop, tell
  the user to double-check the URL.
- `"isDraft": true` → warn the user first: "This PR is still a draft — a review
  may be unsolicited by the author. Continue anyway?" Only proceed on explicit
  confirmation.

## 2. Pending-review collision check

GitHub allows exactly **one PENDING review per user per PR**. A second `POST` to
the reviews endpoint while one is already pending returns a `422`. Check for an
existing pending review *before* doing any other work, so the user picks a path
before they've spent time annotating:

```bash
gh api repos/{o}/{r}/pulls/{n}/reviews --jq '[.[] | select(.state=="PENDING")]'
```

If the result is a non-empty array, present the user with **exactly two options**
— never silently pick one, and never attempt a second create:

- **REPLACE** — delete the stale pending review, then proceed with a fresh one:

  ```bash
  gh api --method DELETE repos/{o}/{r}/pulls/{n}/reviews/{review_id}
  ```

  (`{review_id}` comes from the `.id` field of the pending review found above.)

- **ABORT** — leave the existing pending review untouched and stop reviewer mode
  entirely. The user can go finish that review on github.com themselves.

There is no third option. Do not attempt `POST .../reviews` while a pending
review already exists — that's the exact call that 422s.

## 3. Fetch

Pull everything the narrative and the diff-anchoring engine need in one pass:

```bash
gh pr view {n} --repo {o}/{r} --json title,body,files,commits,headRefOid
```

```bash
gh api repos/{o}/{r}/pulls/{n}/files --paginate > /tmp/pr-{n}-files.json
```

The second call is the one that matters for annotation: it returns each file's
`filename`, `status`, `additions`, `deletions`, and unified-diff `patch` fragment.
Save it to `/tmp/pr-{n}-files.json` — that's the input `scripts/diff_anchor.py`
expects via `--files-json`. `--paginate` matters for PRs with more files than fit
on one page; without it you silently get a truncated file list.

## 4. Post (pending review)

Two things must happen right before the `POST`, in this order:

**Re-fetch `headRefOid` immediately before building the payload** — this is the
force-push guard. If the branch moved between the fetch step and now (the user
took a while annotating), the stale SHA gets rejected:

```bash
gh pr view {n} --repo {o}/{r} --json headRefOid --jq .headRefOid
```

**Build the payload** with `scripts/build_review.py`, feeding it the annotations
from the annotation UI, the files JSON from step 3, and the freshly re-fetched
`commit_id`:

```bash
python3 scripts/build_review.py \
  --annotations /tmp/pr-annotations.json \
  --files-json /tmp/pr-{n}-files.json \
  --commit-id <fresh-headRefOid> \
  > /tmp/pr-{n}-review-payload.json
```

**Post it** via heredoc `--input -`. Never use `-f` bracket notation for arrays —
it doesn't compose the nested `comments[]` structure correctly and will silently
mangle or drop entries. The payload must have **no `event` key** — that's what
keeps the review in `PENDING` state instead of submitting a verdict:

```bash
gh api repos/{o}/{r}/pulls/{n}/reviews --method POST --input - <<< "$(cat /tmp/pr-{n}-review-payload.json)"
```

The response must contain `"state": "PENDING"`. If it doesn't — or the call
errors — see the error table below before retrying.

## 5. After post

Once the `POST` succeeds:

- Print the count of comments actually posted (from the response's
  `comments` array length).
- Print any dropped-anchor warnings that `build_review.py` returned alongside
  the payload (lines that didn't map onto a valid diff anchor, cross-hunk
  ranges, etc.) — the user should know what didn't make it in and why.
- Print the PR URL.
- Remind the user: **the review is PENDING.** They finalize it themselves —
  Approve, Request changes, or Comment — on github.com. The skill never calls
  the finalize endpoint:

```bash
# NEVER run this from the skill — the user finalizes on github.com, not the CLI
gh api repos/{o}/{r}/pulls/{n}/reviews/{review_id}/events --method POST -f event=APPROVE
```

That command is shown here only as a "never do this" reference, not part of the
playbook.

## 6. Error table

| Error | Cause | Fix |
| --- | --- | --- |
| `422` — line not in diff | The anchor (`path` + `line` + `side`) doesn't correspond to a real diff line, usually because the files JSON is stale or the anchor was computed against a different commit | Re-fetch `repos/{o}/{r}/pulls/{n}/files`, re-run `diff_anchor.py`, re-anchor the comment against the fresh hunks |
| `422` — stale `commit_id` | The branch was force-pushed or moved after the files JSON was fetched | Re-fetch `headRefOid` (step 4), rebuild the payload with the new SHA, retry the `POST` |
| `422` — pending review already exists | A pending review from this user is already open on the PR | Go back to the collision check (step 2) — REPLACE or ABORT, never retry the create directly |
| `404` | Wrong `{o}/{r}/{n}` combination, or the PR is on a repo the token can't see | Double-check the parsed owner/repo/number against the original PR URL |
| `403` | Token missing the `repo` scope, or rate-limited | Check `gh auth status` for scopes; check `gh api rate_limit` for remaining calls |
| Fork PRs | The PR's head branch lives in a fork | Still post to the **base** repo (`{o}/{r}` from the PR URL, not the fork) — `path` values in comments are always **base-repo paths**, matching what `pulls/{n}/files` returns |
