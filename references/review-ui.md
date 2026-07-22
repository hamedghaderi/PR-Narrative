# Interactive review UI — the approve/reject HTML

This is what makes the skill *interactive* rather than a static write-up. The page
shows a **section-by-section review**: each part of the PR gets **Approve / Request
change** buttons and a comment box. When the reviewer is done they click **Submit**,
and their decisions come straight back to the agent.

## The round-trip (how decisions come back)

The primary path is a **live local server** (`scripts/review_server.py`) so there's no
manual download/hand-back step. The page also keeps a **Download-decisions fallback**
so it still works if opened without the server.

**Live mode (primary):**

1. The agent writes the review HTML to `/tmp/YYYY-MM-DD-pr-review-<branch>.html`, then
   starts the server pointing at it:
   `python3 scripts/review_server.py --page <html> --out /tmp/pr-review-decisions.json`.
   The server prints `PR_REVIEW_URL http://127.0.0.1:<port>/` and injects a
   `<meta name="pr-review-live" content="1">` marker into the page it serves.
2. The agent opens that URL in the browser. The page sees the live marker and switches
   its Submit button to **POST `/submit`** instead of downloading a file.
3. The user reviews each section (Approve / Request change + comments — choices are
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
    { "id": "background",   "decision": "approved",          "comment": "" },
    { "id": "core-idea",    "decision": "changes_requested", "comment": "lead with the 429, not the bug" },
    { "id": "visual",       "decision": "approved",          "comment": "" },
    { "id": "tradeoff",     "decision": "pending",           "comment": "" }
  ]
}
```

The agent should treat `changes_requested` sections as the work list, apply the
comments, and leave `approved` ones untouched.

## Building the HTML

Reuse the base CSS palette from `html-visual.md` (GitHub-native colors) so the review
page looks consistent with the visual companion. Render the real PR content the skill
generated — the actual Background prose, the styled before/after panels, tables — each
wrapped in a `<section data-review-id="...">` with a review control bar underneath.

### Section wrapper + control bar

Give every reviewable block a stable `data-review-id` and drop in the control bar:

```html
<section class="review-section" data-review-id="background" data-review-label="Background (Why?)">
  <h2>Background (Why?)</h2>
  <!-- the actual generated Background prose / callouts go here -->
  <p>The Incoming Requests page could only filter by status, method, and a coarse
     period …</p>

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

### Sticky action bar (progress + submit)

Put this near the top of `<body>`, before the sections. The Submit button's label is
set by the JS depending on whether the live server is present.

```html
<div class="review-actionbar">
  <strong>PR review</strong>
  <span class="progress" id="rv-progress">0 / N reviewed</span>
  <button class="secondary" id="rv-reset" type="button">Reset</button>
  <button id="rv-submit" type="button">Submit</button>
</div>
```

### The JavaScript (self-contained, no dependencies)

This wires every section's buttons, tracks state, persists to `localStorage`, updates
progress, and submits the decisions. It reads the branch from a
`<body data-branch="…">` attribute, and detects live mode from the
`<meta name="pr-review-live">` marker the server injects — POSTing to `/submit` when
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
        submitBtn.textContent = "✓ Sent — you can close this tab";
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

1. If `overall` is `approved`, finalize the Markdown body as-is and hand it over.
2. Otherwise, for each section with `decision: "changes_requested"`, revise that
   section per its `comment`, leave approved sections untouched, regenerate the
   Markdown body and (if the visual changed) the review page, restart the server, and
   re-open it for another pass. Repeat until `overall` is `approved`.

This is the loop: **generate → serve + open → review → submit → revise → re-serve → …**
until the user approves everything.
