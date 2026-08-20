# Interactive review UI: the approve/reject HTML

This page lets the user review each section, instead of reading one fixed document. It
shows a **section-by-section review**: each part of the PR gets **Approve / Request
change** buttons and a comment box. When the reviewer is done they click **Submit**, and
their decisions go straight back to the agent.

## The round-trip (how decisions come back)

Normally the page uses a **live local server** (`scripts/review_server.py`), so nobody has
to download a file and hand it back. If the page is opened without the server, a
**Download-decisions** button still works.

**Live mode (primary):**

1. The agent writes the review HTML to `/tmp/YYYY-MM-DD-pr-review-<branch>.html`, then
   starts the server pointing at it:
   `python3 scripts/review_server.py --page <html> --out /tmp/pr-review-decisions.json --open`.
   The server prints `PR_REVIEW_URL http://127.0.0.1:<port>/` and injects a
   `<meta name="pr-review-live" content="1">` marker into the page it serves.
   With `--open`, it also attempts to open the URL in the browser and prints either
   `PR_REVIEW_OPEN_OK <url>` (a launcher succeeded) or `PR_REVIEW_OPEN_FAILED <url>`
   (all launchers failed, so the agent must then echo the URL prominently for the user to
   click manually). See SKILL.md §3 for the full bash block with sentinel polling and
   the conditional shell-level fallback.
2. The browser opens the review page (or the user clicks the printed URL). The page sees
   the live marker and switches its Submit button to **POST `/submit`** instead of
   downloading a file.
3. The user reviews each section (Approve / Request change + comments; choices are
   mirrored to `localStorage` so a refresh won't lose them) and clicks **Submit**.
4. The POST body is the decisions JSON; the server writes it atomically to `--out` and
   shuts down (printing `PR_REVIEW_DONE`). The agent reads that file and revises.

**Fallback mode (no server):** if the page is opened directly as a `file://` (no live
marker), Submit becomes **Download decisions** → saves `pr-review-decisions.json` to
Downloads, which the user hands back. Same JSON either way.

> Keep the decisions JSON small and predictable so the agent can act on it
> deterministically. The schema is defined below.

## Decisions JSON schema

Each reviewable section has a stable `id`. The exported file looks like:

```json
{
  "branch": "feature/xyz",
  "generated_at": "2026-07-22T14:00:00Z",
  "overall": "approved",            // "approved" | "changes_requested" | "pending"
  "sections": [
    { "id": "one-sentence", "decision": "approved",          "comment": "" },
    { "id": "problem",      "decision": "approved",          "comment": "" },
    { "id": "what-changes", "decision": "changes_requested", "comment": "lead with the empty page, not the API" },
    { "id": "qa",           "decision": "pending",           "comment": "" }
  ]
}
```

The agent should revise every section marked `changes_requested`, apply the comments, and
leave the `approved` sections unchanged.

The page's **Copy PR description** button (see below) is outside this contract: it
copies the embedded Markdown body to the clipboard and contributes nothing to the
`sections` array, the `overall` value, or the progress count.

## Building the HTML

Reuse the base CSS palette from `html-visual.md` (GitHub-native colors) so the review
page looks consistent with the visual companion. Render the real PR content the skill
generated (the actual generated narrative sections (per the pinned structure in
`references/markdown-body.md`), the styled before/after panels, tables), each wrapped in
a `<section data-review-id="...">` with a review control bar underneath.

### Section wrapper + control bar

Give every reviewable block a stable `data-review-id` and drop in the control bar.
Every section present in the generated body gets its own control: a Core-4 body renders
four review controls, a full body renders 11. The slugs come from the pinned structure
in `references/markdown-body.md`, so each `<section>` matches one generated section.

```html
<section class="review-section" data-review-id="problem" data-review-label="The problem">
  <h2>The problem</h2>
  <!-- the actual generated The problem prose / callouts go here -->
  <p>The Requests page could only filter by status and a rough date range, so users
     had to export the results to a spreadsheet to answer even simple questions.</p>

  <!-- control bar (identical markup for every section; JS wires it up) -->
  <div class="review-bar">
    <button class="rv-approve">✓ Approve</button>
    <button class="rv-changes">✎ Request change</button>
    <span class="rv-status" data-status="pending">Pending</span>
    <textarea class="rv-comment" placeholder="Optional comment (required if requesting a change)…"></textarea>
  </div>
</section>
```

### CSS for the control bar

```html
<style>
  .review-section{border:1px solid var(--border);border-radius:10px;padding:18px 20px;margin:18px 0;background:#fff}
  .review-section.is-approved{border-color:var(--green-border);box-shadow:0 0 0 1px var(--green-border) inset}
  .review-section.is-changes{border-color:var(--amber-border);box-shadow:0 0 0 1px var(--amber-border) inset}
  .review-bar{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-top:14px;
              padding-top:12px;border-top:1px dashed var(--border)}
  .review-bar button{font:inherit;font-size:13px;font-weight:600;cursor:pointer;
                     border:1px solid var(--border);border-radius:7px;padding:6px 12px;background:#f6f8fa}
  .rv-approve.on{background:var(--green-bg);border-color:var(--green-border);color:var(--green-text)}
  .rv-changes.on{background:var(--amber-bg);border-color:var(--amber-border);color:#7a5c00}
  .rv-status{font-size:12px;font-weight:600;padding:2px 10px;border-radius:999px;background:var(--gray-bg);color:var(--gray-text)}
  .rv-status[data-status="approved"]{background:var(--green-bg);color:var(--green-text)}
  .rv-status[data-status="changes_requested"]{background:var(--amber-bg);color:#7a5c00}
  .rv-comment{flex-basis:100%;margin-top:8px;min-height:44px;resize:vertical;
              font:inherit;font-size:13px;padding:8px 10px;border:1px solid var(--border);border-radius:7px}
  /* sticky summary/export bar */
  .review-actionbar{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:14px;
                    background:#fff;border-bottom:1px solid var(--border);padding:12px 0;margin-bottom:8px}
  .review-actionbar .progress{font-size:13px;color:var(--muted)}
  .review-actionbar button{margin-left:auto;font:inherit;font-size:13px;font-weight:700;cursor:pointer;
                    border:1px solid var(--green-border);background:var(--green-bg);color:var(--green-text);
                    border-radius:8px;padding:8px 16px}
  .review-actionbar button.secondary{margin-left:0;border-color:var(--border);background:#f6f8fa;color:var(--ink)}
</style>
```

### Sticky action bar (progress + submit + copy)

Put this near the top of `<body>`, before the sections. The Submit button's label is
set by the JS depending on whether the live server is present. **Copy PR description**
sits between Reset and Submit and reuses the existing `.secondary` style; every
generated page must include it:

```html
<div class="review-actionbar">
  <strong>PR review</strong>
  <span class="progress" id="rv-progress">0 / N reviewed</span>
  <button class="secondary" id="rv-reset" type="button">Reset</button>
  <button class="secondary" id="rv-copy-md" type="button">📋 Copy PR description</button>
  <button id="rv-submit" type="button">Submit</button>
</div>
```

The three existing ids (`rv-progress`, `rv-reset`, `rv-submit`) keep their meaning
exactly; `rv-copy-md` is additive and stateless. It never reads or writes
`localStorage`, never touches `buildPayload()`, and has no bearing on the decisions
JSON. It exists so the reviewer can lift the Markdown body straight out of the page
they just read, instead of the agent pasting a wall of Markdown into the terminal.

### Embedded PR body payload

The copy button needs the Markdown to copy, so the agent embeds the full PR body in
the page as an inert JSON payload. Put it anywhere in `<body>` (next to the action bar
is fine) and it renders nothing:

```html
<script type="application/json" id="pr-body-md">JSON_ENCODED_BODY</script>
```

`JSON_ENCODED_BODY` is produced with:

```python
json.dumps(md_body).replace("</", "<\\/")
```

**Both halves are mandatory.**

- `json.dumps` gives you one valid JSON string literal (quotes, newlines, backslashes,
  and tabs all escaped) so the whole multi-line Markdown body survives as a single
  token that `JSON.parse` hands back verbatim.
- `.replace("</", "<\\/")` is the part that's easy to skip and expensive to debug. A PR
  body routinely contains fenced code blocks, and any `</script>` inside one ends the
  `script` element at **HTML-parse time**, before any JavaScript runs. The browser
  doesn't care that the sequence is inside a JSON string; the tokenizer stops there and
  the rest of the page, including every review section and the submit JS, is silently
  truncated. (Git precedent: commit `6651321`. The same convention is spelled out for
  reviewer mode's diff payload at `assets/review-template.html:175-187`: *"Escape `</`
  as `<\/` in the dumped JSON (`json.dumps(...).replace("</", "<\\/")`): a diff
  containing `</script>` would otherwise close that script element at HTML-parse time
  and truncate the data."*)
- The escape is free on the read side: `<\/` is a legal JSON escape for `/`, so
  `JSON.parse` gives back `</` transparently. No un-escaping step, no post-processing.

Two rules about the *content*:

- **Body only, never the title.** GitHub takes the PR title in its own input field, so
  a title line pasted into the body box just becomes a stray heading the author has to
  delete. What's embedded is exactly what belongs in the description box.
- **It's the current draft.** Each generated page carries the body as it stands for that
  round of review. If the user requests changes, the agent regenerates the body *and*
  the page, so the next page's payload is the revised draft.

> [!IMPORTANT]
> Do **not** wrap this payload in a reviewable `<section class="review-section" …>`.
> The decisions JS collects every `.review-section` and reads its review-id, so a
> wrapper would add a phantom entry to the `sections` array that can never be approved:
> `#rv-progress` would report a denominator one too high and `overall` would be stuck at
> `pending` forever. `#pr-body-md` is hidden, inert data; it stays outside the
> reviewable sections entirely.

### Copy PR description JS

A small self-contained block, separate from the decisions IIFE so neither can break the
other. Include it as-is:

```html
<script>
(function () {
  var bodyEl = document.getElementById("pr-body-md");
  var md = bodyEl ? JSON.parse(bodyEl.textContent) : null;
  var copyBtn = document.getElementById("rv-copy-md");
  if (!copyBtn || !md) return;
  copyBtn.addEventListener("click", function () {
    var original = copyBtn.textContent;
    // MUST call writeText synchronously inside the click handler:
    // Safari drops transient user activation if anything awaits before the clipboard call.
    var p = navigator.clipboard
      ? navigator.clipboard.writeText(md)
      : Promise.reject(new Error("no clipboard API"));
    p.then(function () {
      copyBtn.textContent = "✓ Copied. Paste into GitHub";
      setTimeout(function () { copyBtn.textContent = original; }, 2000);
    }).catch(function () {
      // Off-screen textarea fallback (NOT display:none; hidden elements can't be selected).
      var ta = document.createElement("textarea");
      ta.value = md;
      ta.style.cssText = "position:fixed;left:-9999px;top:0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); copyBtn.textContent = "✓ Copied. Paste into GitHub"; }
      catch (e) { copyBtn.textContent = "Copy failed"; }
      setTimeout(function () { copyBtn.textContent = original; document.body.removeChild(ta); }, 2000);
    });
  });
})();
</script>
```

Three details that are required for this to work:

- **`writeText` is called synchronously inside the handler.** The promise it returns may
  resolve later, but the call itself has to happen while the click's transient user
  activation is still alive; Safari discards that activation the moment anything is
  awaited first, and the copy silently fails.
- **The fallback textarea is positioned off-screen, not hidden.** `position:fixed;
  left:-9999px` keeps it selectable; `display:none` or `visibility:hidden` would make
  `ta.select()` a no-op and `document.execCommand("copy")` copy nothing.
- **The `catch` is the expected path often enough to matter.** It covers a rejected
  `writeText` *and* `navigator.clipboard` being undefined entirely, which is how some
  browsers treat a non-HTTPS page.

This works in both modes. In live mode the page is served from
`http://127.0.0.1:<port>/`, which is a secure context, so the async Clipboard API is
normally available. In `file://` mode the button matters more, not less: `SKILL.md`
tells the agent to skip the server and `open` the HTML directly when Python 3 isn't
  available, and in that situation the copy button is a **primary output path**: the
reviewer can lift the finished PR body out of the page even with no server, no POST
endpoint, and no terminal round-trip.

### The JavaScript (self-contained, no dependencies)

This wires every section's buttons, tracks state, persists to `localStorage`, updates
progress, and submits the decisions. It reads the branch from a
`<body data-branch="…">` attribute, and detects live mode from the
`<meta name="pr-review-live">` marker the server injects, and POSTs to `/submit` when
live, or downloading `pr-review-decisions.json` as the fallback.

```html
<script>
(function () {
  const branch = document.body.dataset.branch || "unknown-branch";
  const sections = Array.from(document.querySelectorAll(".review-section"));
  const storeKey = "pr-review:" + branch;
  const isLive = !!document.querySelector('meta[name="pr-review-live"]');

  const state = JSON.parse(localStorage.getItem(storeKey) || "{}");

  function save() { localStorage.setItem(storeKey, JSON.stringify(state)); }

  function apply(sec) {
    const id = sec.dataset.reviewId;
    const s = state[id] || { decision: "pending", comment: "" };
    const approve = sec.querySelector(".rv-approve");
    const changes = sec.querySelector(".rv-changes");
    const status  = sec.querySelector(".rv-status");
    const comment = sec.querySelector(".rv-comment");
    approve.classList.toggle("on", s.decision === "approved");
    changes.classList.toggle("on", s.decision === "changes_requested");
    sec.classList.toggle("is-approved", s.decision === "approved");
    sec.classList.toggle("is-changes", s.decision === "changes_requested");
    status.dataset.status = s.decision;
    status.textContent = s.decision === "approved" ? "Approved"
                       : s.decision === "changes_requested" ? "Changes requested"
                       : "Pending";
    if (document.activeElement !== comment) comment.value = s.comment || "";
  }

  function updateProgress() {
    const reviewed = sections.filter(sec => {
      const s = state[sec.dataset.reviewId];
      return s && s.decision !== "pending";
    }).length;
    document.getElementById("rv-progress").textContent = reviewed + " / " + sections.length + " reviewed";
  }

  sections.forEach(sec => {
    const id = sec.dataset.reviewId;
    if (!state[id]) state[id] = { decision: "pending", comment: "" };
    sec.querySelector(".rv-approve").addEventListener("click", () => {
      state[id].decision = state[id].decision === "approved" ? "pending" : "approved";
      save(); apply(sec); updateProgress();
    });
    sec.querySelector(".rv-changes").addEventListener("click", () => {
      state[id].decision = state[id].decision === "changes_requested" ? "pending" : "changes_requested";
      save(); apply(sec); updateProgress();
    });
    sec.querySelector(".rv-comment").addEventListener("input", (e) => {
      state[id].comment = e.target.value; save();
    });
    apply(sec);
  });
  updateProgress();

  document.getElementById("rv-reset").addEventListener("click", () => {
    if (!confirm("Clear all review decisions?")) return;
    Object.keys(state).forEach(k => delete state[k]);
    sections.forEach(sec => { state[sec.dataset.reviewId] = { decision: "pending", comment: "" }; apply(sec); });
    save(); updateProgress();
  });

  function buildPayload() {
    const decisions = sections.map(sec => ({
      id: sec.dataset.reviewId,
      label: sec.dataset.reviewLabel || sec.dataset.reviewId,
      decision: (state[sec.dataset.reviewId] || {}).decision || "pending",
      comment: (state[sec.dataset.reviewId] || {}).comment || ""
    }));
    const anyChanges = decisions.some(d => d.decision === "changes_requested");
    const allApproved = decisions.every(d => d.decision === "approved");
    return {
      branch: branch,
      generated_at: new Date().toISOString(),
      overall: anyChanges ? "changes_requested" : allApproved ? "approved" : "pending",
      sections: decisions
    };
  }

  const submitBtn = document.getElementById("rv-submit");
  submitBtn.textContent = isLive ? "Submit review" : "⬇ Download decisions";

  submitBtn.addEventListener("click", async () => {
    const payload = buildPayload();
    if (isLive) {
      submitBtn.disabled = true;
      submitBtn.textContent = "Sending…";
      try {
        const res = await fetch("/submit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error("HTTP " + res.status);
        submitBtn.textContent = "✓ Sent. You can close this tab";
      } catch (e) {
        // Server gone? Fall back to a download so the review isn't lost.
        submitBtn.disabled = false;
        submitBtn.textContent = "⬇ Download decisions (server unreachable)";
        download(payload);
      }
      return;
    }
    download(payload);
  });

  function download(payload) {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "pr-review-decisions.json";
    document.body.appendChild(a); a.click(); a.remove();
  }
})();
</script>
```

## What the agent does after the user submits

**Live mode:** the server writes the decisions to `--out` (e.g.
`/tmp/pr-review-decisions.json`) and exits with `PR_REVIEW_DONE`. The agent, having
launched the server in the background, waits for that file to appear (poll it, or wait
for the process to exit) and reads it. **Fallback mode:** read
`~/Downloads/pr-review-decisions.json` (check for `pr-review-decisions (1).json` if
exported more than once).

Then, regardless of mode:

1. If `overall` is `approved`, deliver the Markdown body exactly as approved. Do not edit
   it afterwards: do not reword a sentence and do not change a heading. The reviewer
   approved one specific text, and the copy button on that page put that same text on
   their clipboard. If you change it now, the clipboard and the "final" body will differ,
   and nobody will be told. The Copy PR description button on the last page served always
   gives the final text.
2. If it is not approved, revise each section marked `decision: "changes_requested"`, using
   its `comment`. Leave the approved sections unchanged. Regenerate the Markdown body, and
   the review page if the visual changed. Restart the server and open the page again.
   Repeat until `overall` is `approved`.

This is the loop: **generate → serve + open → review → submit → revise → re-serve → …**
until the user approves everything.
