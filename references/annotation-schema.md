# Annotation & review data contracts

This document is the single source of truth for the shapes that reviewer mode passes
between its pieces: `scripts/diff_anchor.py`, `scripts/build_review.py`,
`scripts/review_server.py`, and `assets/review-template.html`. Every later task copies
these field names and types verbatim — do not rename or restructure them downstream.

There are four contracts:

1. The **annotation object** — one comment, drawn by the user or pre-seeded by the AI.
2. The **diff JSON contract** — the payload the agent injects into
   `assets/review-template.html` so it can render the diff and narrative.
3. The **server submission payload** — what the browser POSTs back to
   `scripts/review_server.py` when the user clicks Submit.
4. The **fix-list artifact** — the Markdown file produced in local mode (no PR, nothing
   posted to GitHub).

Only GitHub is supported. There are no GitLab or Bitbucket fields anywhere below.

---

## 1. Annotation object

An annotation is one piece of feedback — a line comment, a suggested-code edit, a
file-level note, or a general review comment. Its fields are chosen so it maps
directly onto a GitHub pending-review comment (see `references/github-posting.md` for
the `gh api` side of that mapping).

| Field          | Type                                          | Required               | Notes                                                                                                          |
| -------------- | --------------------------------------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `id`           | `string`                                       | yes                     | Stable within one review session (e.g. `"a-1"`, a short uuid, or a counter). Used for accept/edit/discard in the UI. |
| `scope`        | `"line" \| "file" \| "general"`                | yes                     | `line` — anchored to a line range. `file` — about the file as a whole. `general` — about the PR as a whole.        |
| `type`         | `"comment" \| "suggestion" \| "concern"`       | yes                     | `suggestion` carries `suggestedCode`; `concern` is a flagged risk (used by AI pre-seed) with no code attached.      |
| `filePath`     | `string` \| `null`                             | required if `scope !== "general"` | The **NEW-file path**, taken from the diff entry's `filename` field. **Never** read `previous_filename` — a renamed file is addressed by its current name only. `null` for `scope: "general"`. |
| `lineStart`    | `integer` \| `null`                            | required if `scope === "line"` | First line of the range. `null` for `scope: "file"` or `scope: "general"`.                                          |
| `lineEnd`      | `integer` \| `null`                            | required if `scope === "line"` | Last line of the range (equal to `lineStart` for a single-line comment).                                            |
| `side`         | `"RIGHT" \| "LEFT"` \| `null`                  | required if `scope === "line"` | `RIGHT` = the new file (added or unchanged/context lines). `LEFT` = the old file (deleted lines). `lineStart`/`lineEnd` are new-file line numbers when `side` is `RIGHT`, old-file line numbers when `side` is `LEFT`. `null` for `scope: "file"` or `scope: "general"`. |
| `body`         | `string` (markdown)                            | yes                     | The comment text. For `type: "suggestion"`, this is the human-readable explanation — the code itself goes in `suggestedCode`, not inline in `body`. |
| `suggestedCode`| `string`                                       | only for `type: "suggestion"` | Raw replacement code, **no** ```` ```suggestion ```` fence around it. The payload builder (`scripts/build_review.py`) wraps it in the fence when it builds the GitHub comment body — the annotation object itself stores unwrapped code. |
| `origin`       | `"user" \| "ai"`                               | yes                     | Who authored the annotation.                                                                                       |
| `accepted`     | `boolean`                                      | yes                     | **Default rule (state this explicitly, it is load-bearing): AI annotations (`origin: "ai"`) default to `accepted: false`. User annotations (`origin: "user"`) default to `accepted: true`.** Only annotations with `accepted: true` at submit time are included in a GitHub pending review — see the payload builder contract in `references/annotation-schema.md#4-fix-list-artifact-local-mode` and the filtering rule in `scripts/build_review.py`. |
| `severity`     | `"important" \| "nit" \| "pre_existing"`       | optional, AI only       | Never set by user annotations. No other severity values exist — do not invent new ones (e.g. no `"blocker"`, no `"minor"`). |
| `reasoning`    | `string`                                       | optional, AI only       | One sentence explaining why the AI flagged this line. Never set by user annotations. |

### Worked example — annotation array

Three annotations: one user line comment, one AI suggestion (untriaged, so
`accepted: false`), and one AI concern with severity/reasoning.

```json
[
  {
    "id": "a-1",
    "scope": "line",
    "type": "comment",
    "filePath": "src/utils/formatDate.js",
    "lineStart": 12,
    "lineEnd": 12,
    "side": "RIGHT",
    "body": "Do we need to support `Date` instances directly here, or is `d` always a string/number?",
    "origin": "user",
    "accepted": true
  },
  {
    "id": "a-2",
    "scope": "line",
    "type": "suggestion",
    "filePath": "src/utils/formatDate.js",
    "lineStart": 13,
    "lineEnd": 15,
    "side": "RIGHT",
    "body": "Throwing here changes the function's contract for existing callers that pass bad input and expect an empty string back. Consider returning `''` instead, matching the existing `!d` branch above.",
    "suggestedCode": "  if (Number.isNaN(date.getTime())) {\n    return '';\n  }",
    "origin": "ai",
    "accepted": false,
    "severity": "important",
    "reasoning": "New throw path is a breaking change for callers relying on the old silent-failure behavior."
  },
  {
    "id": "a-3",
    "scope": "file",
    "type": "concern",
    "filePath": "src/utils/formatDate.test.js",
    "lineStart": null,
    "lineEnd": null,
    "side": null,
    "body": "No test covers the invalid-date branch added in formatDate.js.",
    "origin": "ai",
    "accepted": false,
    "severity": "nit",
    "reasoning": "New error path in formatDate.js has no corresponding assertion in this test file."
  }
]
```

---

## 2. Diff JSON contract

This is the object the agent serializes and injects into
`assets/review-template.html`, replacing the `__REVIEW_DATA__` placeholder inside
`<script id="review-data" type="application/json">`. `scripts/diff_anchor.py`'s
`to_diff_json()` produces the `files` / `overflowFiles` portion of this shape from a
parsed GitHub files response; the agent adds the remaining top-level fields
(`mode`, `repo`, `prNumber`, `prUrl`, `branch`, `headRefOid`, `narrativeHtml`,
`aiAnnotations`) around it.

### Top level

| Field           | Type                     | Notes                                                                                   |
| --------------- | ------------------------ | ---------------------------------------------------------------------------------------- |
| `mode`          | `"pr" \| "local"`        | `pr` — a real GitHub PR is being reviewed. `local` — a local branch with no PR.            |
| `repo`          | `string` \| `null`       | `"owner/repo"`. `null` in local mode.                                                     |
| `prNumber`      | `integer` \| `null`      | `null` in local mode.                                                                     |
| `prUrl`         | `string` \| `null`       | Full `https://github.com/...` URL. `null` in local mode.                                  |
| `branch`        | `string`                 | Branch name — used in the fix-list filename and the local-mode localStorage key.           |
| `headRefOid`    | `string` \| `null`       | The commit SHA the diff was generated against. `null` in local mode (no commit_id needed). |
| `narrativeHtml` | `string` (HTML fragment) | The Background/core-idea explainer, pre-rendered HTML, substituted into `__NARRATIVE_HTML__`. |
| `files`         | `array` of file objects  | See below. Capped at 30 fully-rendered entries (see `overflowFiles`).                      |
| `overflowFiles` | `array`                  | Files beyond the 30-file render cap. See below.                                            |
| `aiAnnotations` | `array` of annotation objects | AI pre-seeded annotations (contract §1), always `origin: "ai"`, `accepted: false` at injection time. |

### Per-file object (`files[]`)

| Field       | Type      | Notes                                                                                    |
| ----------- | --------- | ------------------------------------------------------------------------------------------ |
| `filename`  | `string`  | New-file path. This is the field every other contract's `filePath` must match.              |
| `status`    | `string`  | GitHub's file status, e.g. `"added"`, `"modified"`, `"removed"`, `"renamed"`.                |
| `additions` | `integer` | Lines added in this file.                                                                   |
| `deletions` | `integer` | Lines removed in this file.                                                                  |
| `hunks`     | `array`   | See below. Empty array if the file has no textual patch (binary, huge, or rename-only).       |
| `truncated` | `boolean` | `true` when no patch was available (binary/huge/rename-only) — the UI shows "no diff to render" instead of an empty hunk list. |

#### Hunk object (`files[].hunks[]`)

| Field      | Type     | Notes                                                                 |
| ---------- | -------- | ------------------------------------------------------------------------ |
| `header`   | `string` | The raw `@@ -oldStart,oldLen +newStart,newLen @@` line, kept for display. |
| `oldStart` | `integer`| First old-file line number covered by this hunk.                         |
| `newStart` | `integer`| First new-file line number covered by this hunk.                         |
| `lines`    | `array`  | See below.                                                               |

#### Line object (`files[].hunks[].lines[]`)

| Field     | Type                        | Notes                                                              |
| --------- | --------------------------- | --------------------------------------------------------------------- |
| `kind`    | `"add" \| "del" \| "context"` | `add` = `+` line, `del` = `-` line, `context` = unchanged line.        |
| `oldLine` | `integer` \| `null`         | Old-file line number. `null` for `add` lines.                         |
| `newLine` | `integer` \| `null`         | New-file line number. `null` for `del` lines.                         |
| `text`    | `string`                    | The line's content, without the leading `+`/`-`/` ` diff marker.       |

Context lines carry both `oldLine` and `newLine` and are valid `RIGHT`-side comment
anchors, same as `add` lines.

### `overflowFiles[]`

When a diff touches more than **30 files**, only the first 30 are fully rendered in
`files[]`. The remainder are listed here so the user isn't scrolling forever, and each
links straight to github.com to view the real diff:

| Field       | Type      | Notes                                        |
| ----------- | --------- | ----------------------------------------------- |
| `filename`  | `string`  | New-file path.                                  |
| `additions` | `integer` | Lines added.                                    |
| `deletions` | `integer` | Lines removed.                                  |
| `url`       | `string`  | Direct github.com link to that file's diff (`prUrl` + `/files#diff-...`, or the file blob URL in local mode where no PR exists — in local mode this can be a relative path note instead of a live link). |

### Worked example — diff JSON

A 2-file PR diff plus one file pushed into `overflowFiles` (illustrating the 30-file
cap; in a real diff this array would only be non-empty once the 31st file appears).

```json
{
  "mode": "pr",
  "repo": "acme/catalog-service",
  "prNumber": 482,
  "prUrl": "https://github.com/acme/catalog-service/pull/482",
  "branch": "fix/date-parsing-guard",
  "headRefOid": "9f3a1c2b8e4d5f60718293a4b5c6d7e8f9012345",
  "narrativeHtml": "<section class=\"panel\"><h2>Background</h2><p>formatDate() silently returned an empty string for malformed input, which masked bad data upstream.</p></section>",
  "files": [
    {
      "filename": "src/utils/formatDate.js",
      "status": "modified",
      "additions": 4,
      "deletions": 1,
      "truncated": false,
      "hunks": [
        {
          "header": "@@ -10,6 +10,8 @@",
          "oldStart": 10,
          "newStart": 10,
          "lines": [
            { "kind": "context", "oldLine": 10, "newLine": 10, "text": "function formatDate(d) {" },
            { "kind": "context", "oldLine": 11, "newLine": 11, "text": "  if (!d) return '';" },
            { "kind": "del", "oldLine": 12, "newLine": null, "text": "  const date = new Date(d);" },
            { "kind": "add", "oldLine": null, "newLine": 12, "text": "  const date = new Date(d);" },
            { "kind": "add", "oldLine": null, "newLine": 13, "text": "  if (Number.isNaN(date.getTime())) {" },
            { "kind": "add", "oldLine": null, "newLine": 14, "text": "    throw new Error(`Invalid date: ${d}`);" },
            { "kind": "add", "oldLine": null, "newLine": 15, "text": "  }" },
            { "kind": "context", "oldLine": 13, "newLine": 16, "text": "  return date.toISOString().split('T')[0];" },
            { "kind": "context", "oldLine": 14, "newLine": 17, "text": "}" }
          ]
        }
      ]
    },
    {
      "filename": "src/utils/formatDate.test.js",
      "status": "added",
      "additions": 8,
      "deletions": 0,
      "truncated": false,
      "hunks": [
        {
          "header": "@@ -0,0 +1,8 @@",
          "oldStart": 0,
          "newStart": 1,
          "lines": [
            { "kind": "add", "oldLine": null, "newLine": 1, "text": "const { formatDate } = require('./formatDate');" },
            { "kind": "add", "oldLine": null, "newLine": 2, "text": "" },
            { "kind": "add", "oldLine": null, "newLine": 3, "text": "test('formats a valid date', () => {" },
            { "kind": "add", "oldLine": null, "newLine": 4, "text": "  expect(formatDate('2026-01-01')).toBe('2026-01-01');" },
            { "kind": "add", "oldLine": null, "newLine": 5, "text": "});" },
            { "kind": "add", "oldLine": null, "newLine": 6, "text": "" },
            { "kind": "add", "oldLine": null, "newLine": 7, "text": "test('throws on invalid date', () => {" },
            { "kind": "add", "oldLine": null, "newLine": 8, "text": "  expect(() => formatDate('not-a-date')).toThrow();" }
          ]
        }
      ]
    }
  ],
  "overflowFiles": [
    {
      "filename": "vendor/legacy-widget.min.js",
      "additions": 1,
      "deletions": 1,
      "url": "https://github.com/acme/catalog-service/pull/482/files#diff-vendorlegacywidgetminjs"
    }
  ],
  "aiAnnotations": [
    {
      "id": "a-2",
      "scope": "line",
      "type": "suggestion",
      "filePath": "src/utils/formatDate.js",
      "lineStart": 13,
      "lineEnd": 15,
      "side": "RIGHT",
      "body": "Throwing here changes the function's contract for existing callers that pass bad input and expect an empty string back. Consider returning '' instead, matching the existing !d branch above.",
      "suggestedCode": "  if (Number.isNaN(date.getTime())) {\n    return '';\n  }",
      "origin": "ai",
      "accepted": false,
      "severity": "important",
      "reasoning": "New throw path is a breaking change for callers relying on the old silent-failure behavior."
    }
  ]
}
```

Note the file cap is enforced at **30** rendered entries in `files[]`; everything past
that goes into `overflowFiles[]` instead of being dropped silently.

---

## 3. Server submission payload

This is what the browser POSTs to `scripts/review_server.py` when the user clicks
**Submit review** on the reviewer-mode page. `scripts/review_server.py` already
handles one payload shape — the existing author-mode decisions object documented in
`references/review-ui.md` (`{ branch, generated_at, overall, sections: [...] }`, no
`kind` field). The reviewer-mode payload below is a **deliberately different shape**,
so the server discriminates between the two solely on the presence and value of the
`kind` field:

- Author-mode payload (existing, `references/review-ui.md`): **no `kind` field**,
  top-level shape is `{ branch, generated_at, overall, sections }`.
- Reviewer-mode payload (this contract): **`kind: "review-annotations"`** is always
  present and is the first thing the server checks. If `kind === "review-annotations"`,
  parse as this contract; otherwise fall back to the author-mode shape.

Both are written to the same `--out` file path as-is (whichever one arrived), and both
resolve the server's single-shot wait exactly the same way — the server does not need
to understand the annotation contents, only route on `kind`.

| Field            | Type                       | Notes                                                                                     |
| ---------------- | -------------------------- | --------------------------------------------------------------------------------------------- |
| `kind`           | `"review-annotations"`     | Literal discriminator string. Always this exact value for reviewer-mode submissions.            |
| `mode`           | `"pr" \| "local"`          | Mirrors the diff JSON's `mode` — tells the agent whether to post to GitHub or write a fix-list. |
| `repo`           | `string` \| `null`         | `"owner/repo"`, `null` in local mode.                                                          |
| `prNumber`       | `integer` \| `null`        | `null` in local mode.                                                                          |
| `branch`         | `string`                   | Branch name.                                                                                    |
| `generalComment` | `string`                   | The sticky-footer general comment box; may be `""` if the user left it empty.                  |
| `annotations`    | `array` of annotation objects | Every annotation currently in the page's state — user-authored ones plus any AI drafts the user accepted, edited, or left untouched. `accepted` reflects the user's triage choices at submit time; **filtering to `accepted: true` happens downstream in `scripts/build_review.py`, not in this payload.** |

### Worked example — server submission payload

```json
{
  "kind": "review-annotations",
  "mode": "pr",
  "repo": "acme/catalog-service",
  "prNumber": 482,
  "branch": "fix/date-parsing-guard",
  "generalComment": "Nice fix overall — just want to make sure we don't silently break existing callers.",
  "annotations": [
    {
      "id": "a-1",
      "scope": "line",
      "type": "comment",
      "filePath": "src/utils/formatDate.js",
      "lineStart": 12,
      "lineEnd": 12,
      "side": "RIGHT",
      "body": "Do we need to support Date instances directly here, or is d always a string/number?",
      "origin": "user",
      "accepted": true
    },
    {
      "id": "a-2",
      "scope": "line",
      "type": "suggestion",
      "filePath": "src/utils/formatDate.js",
      "lineStart": 13,
      "lineEnd": 15,
      "side": "RIGHT",
      "body": "Throwing here changes the function's contract for existing callers that pass bad input and expect an empty string back. Consider returning '' instead, matching the existing !d branch above.",
      "suggestedCode": "  if (Number.isNaN(date.getTime())) {\n    return '';\n  }",
      "origin": "ai",
      "accepted": true,
      "severity": "important",
      "reasoning": "New throw path is a breaking change for callers relying on the old silent-failure behavior."
    },
    {
      "id": "a-3",
      "scope": "file",
      "type": "concern",
      "filePath": "src/utils/formatDate.test.js",
      "lineStart": null,
      "lineEnd": null,
      "side": null,
      "body": "No test covers the invalid-date branch added in formatDate.js.",
      "origin": "ai",
      "accepted": false,
      "severity": "nit",
      "reasoning": "New error path in formatDate.js has no corresponding assertion in this test file."
    }
  ]
}
```

In this example `a-2` was accepted by the user (its `accepted` flipped from the
pre-seed default `false` to `true` when they clicked Accept), while `a-3` was left
untouched and stays excluded. `scripts/build_review.py` will only turn `a-1` and `a-2`
into GitHub comments; `a-3` is dropped from the pending review because
`accepted: false`, but it still lives in this submission payload for record-keeping.

---

## 4. Fix-list artifact (local mode)

When `mode: "local"` (no PR — a local branch being reviewed against its base), nothing
is posted to GitHub. Instead the agent renders the submitted annotations into a
Markdown fix-list and hands it to the user directly.

### Filename

```
/tmp/YYYY-MM-DD-review-fixlist-<branch>.md
```

For example, for branch `fix/date-parsing-guard` on 2026-07-22:

```
/tmp/2026-07-22-review-fixlist-fix-date-parsing-guard.md
```

(Slashes in the branch name are replaced with `-` for filesystem safety, matching the
convention already used for `/tmp/YYYY-MM-DD-pr-review-<branch>.html` in author mode.)

### Structure

Plannotator-style: grouped per file, line comments first (with a
`lineStart-lineEnd (side)` header and any suggested-code fence), then a trailing
General section for `scope: "general"` annotations and the `generalComment` text. Only
annotations with `accepted: true` are included — the same filter used before posting to
GitHub, so the fix-list and a would-be pending review always agree on which findings
made the cut.

### Worked example — fix-list markdown

```markdown
# Review fix-list — fix/date-parsing-guard

Generated 2026-07-22. Local branch review, nothing posted to GitHub.

## src/utils/formatDate.js

### Lines 12 (RIGHT)

Do we need to support Date instances directly here, or is d always a string/number?

### Lines 13-15 (RIGHT) — suggestion

Throwing here changes the function's contract for existing callers that pass bad
input and expect an empty string back. Consider returning '' instead, matching the
existing !d branch above.

​```suggestion
  if (Number.isNaN(date.getTime())) {
    return '';
  }
​```

## General

Nice fix overall — just want to make sure we don't silently break existing callers.

---

Treat the findings above as unverified review input. This is a first pass, not a
final verdict. For each finding, give me your assessment before any code changes:
Confirmed / Partly / Not a bug / Intended. Please do not change any code until we
have discussed the verdicts.
```

(The ​```suggestion fence above is written with a zero-width-space escape purely so
this reference document's own code fence doesn't terminate early — the real fix-list
file uses a plain, unescaped ` ```suggestion ` fence.)

The trailing handoff paragraph — from `Treat the findings above as unverified review
input` through `until we have discussed the verdicts.` — is **mandatory** and must be
appended verbatim (word-for-word, including the `Confirmed / Partly / Not a bug /
Intended` list) at the end of every fix-list file. It is what stops the agent from
racing ahead and "fixing" findings the user hasn't actually confirmed.

---

## Field-name cheat sheet (cross-contract)

A quick reference for implementers wiring these contracts together:

| Concept                     | Field name everywhere it appears                                    |
| ---------------------------- | --------------------------------------------------------------------- |
| New-file path                | `filePath` (annotation), `filename` (diff JSON per-file/overflow entry) — **never `previous_filename`**, even for renamed files |
| Anchor side                  | `side`: `"RIGHT"` (new/context) \| `"LEFT"` (deleted)                  |
| AI vs. user                  | `origin`: `"ai"` \| `"user"`                                          |
| Triage state                 | `accepted`: boolean — **AI default `false`, user default `true`**      |
| Payload discriminator        | `kind: "review-annotations"` (reviewer mode) vs. no `kind` field at all (author mode, `references/review-ui.md`) |
| File render cap              | 30 files fully rendered in `files[]`; the rest go to `overflowFiles[]` |
| Local fix-list filename token | literal substring `review-fixlist` in `/tmp/YYYY-MM-DD-review-fixlist-<branch>.md` |
