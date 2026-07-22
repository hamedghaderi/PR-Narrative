# Styled HTML visual — CSS, panels, and worked example

This is the artifact that gives a PR the look people love: real HTML/CSS before/after
panels with colored request rows, a red failure, an "extract locally" step, and
little file chips. Build it as a single self-contained `.html` file with inline CSS,
saved to `/tmp/YYYY-MM-DD-pr-<branch>.html`. No mermaid, no ASCII art — use the HTML
below.

All the example content here uses a generic, invented scenario (batching image
downloads through a CDN bundle endpoint) purely to illustrate the shape. Replace it
with the actual change you're documenting.

## Contents

1. Page skeleton + base CSS
2. The before/after panel components (request rows, badges, chips, arrows)
3. Callout components (Note / Tip)
4. Comparison table
5. Full worked example (a complete HTML file)

---

## 1. Page skeleton + base CSS

Keep it one clean page: a title, the Background narrative, the styled before/after
visual, then the Description narrative. This palette leans on GitHub's own colors so
the panels feel native when screenshots land in a PR.

```html
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PR — <short change title></title>
<style>
  :root{
    --ink:#1b1f24; --muted:#57606a; --border:#d0d7de; --panel-bg:#f6f8fa;
    --green-bg:#dafbe1; --green-border:#4ac26b; --green-text:#116329;
    --red-bg:#ffebe9; --red-border:#ff8182; --red-text:#82071e;
    --gray-bg:#eaeef2; --gray-text:#6e7781;
    --amber-bg:#fff8c5; --amber-border:#d4a72c; --accent:#0969da;
  }
  *{box-sizing:border-box}
  body{margin:0;padding:40px 20px 80px;background:#fff;color:var(--ink);
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;line-height:1.55}
  .wrap{max-width:880px;margin:0 auto}
  h1{font-size:26px;margin:0 0 6px}
  h2{font-size:19px;margin:48px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--border)}
  h3{font-size:15px;margin:26px 0 10px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
  p{margin:0 0 14px} .subtitle{color:var(--muted);font-size:14px;margin-bottom:4px}
  code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px}
  @media (max-width:600px){body{padding:24px 14px}}
</style></head><body><div class="wrap">
  <!-- content -->
</div></body></html>
```

---

## 2. Before/after panel components

The heart of the visual. Two panels side by side: the old path (requests failing) and
the new path (one bulk request, extract, chips). Put concrete toy data in every row.

```html
<style>
  .badge{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;
         font-weight:600;font-family:ui-monospace,monospace;border:1px solid}
  .badge-200{background:var(--green-bg);border-color:var(--green-border);color:var(--green-text)}
  .badge-429{background:var(--red-bg);border-color:var(--red-border);color:var(--red-text)}
  .badge-skip{background:var(--gray-bg);border-color:var(--border);color:var(--gray-text)}
  .visual-grid{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin:20px 0 8px}
  @media (max-width:720px){.visual-grid{grid-template-columns:1fr}}
  .panel{border:1px solid var(--border);border-radius:10px;overflow:hidden;background:#fff}
  .panel-head{padding:10px 14px;font-weight:600;font-size:13.5px;border-bottom:1px solid var(--border)}
  .panel-head.before{background:#fff1f0;color:var(--red-text)}
  .panel-head.after{background:var(--green-bg);color:var(--green-text)}
  .panel-body{padding:12px 14px}
  .req-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:5px 0;font-size:12.5px}
  .req-row .path{font-family:ui-monospace,monospace}
  .req-row.dim{opacity:.45}
  .note-inline{font-size:12px;color:var(--red-text);margin:6px 0;font-style:italic}
  .step-box{margin:12px 0;padding:10px 12px;background:var(--panel-bg);border:1px dashed var(--border);
            border-radius:8px;font-size:12.5px;text-align:center}
  .step-box .arrow-in{font-size:16px;color:var(--muted);margin-bottom:2px}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}
  .chip{border:1px solid var(--green-border);background:var(--green-bg);color:var(--green-text);
        border-radius:6px;padding:3px 8px;font-family:ui-monospace,monospace;font-size:11.5px}
  .chip.more{border-color:var(--border);background:var(--gray-bg);color:var(--gray-text)}
  .chip.miss{border-color:var(--red-border);background:var(--red-bg);color:var(--red-text)}
  .fallback-box{margin-top:10px;padding:9px 12px;background:var(--amber-bg);border:1px solid var(--amber-border);
                border-radius:8px;font-size:12.5px}
</style>

<div class="visual-grid">
  <div class="panel">
    <div class="panel-head before">Before — one GET per image</div>
    <div class="panel-body">
      <div class="req-row"><span class="path">GET <b>shoes/img-001</b>.jpg</span><span class="badge badge-200">200</span></div>
      <div class="req-row"><span class="path">GET <b>shoes/img-002</b>.jpg</span><span class="badge badge-200">200</span></div>
      <div class="req-row"><span class="path">GET <b>shoes/img-003</b>.jpg</span><span class="badge badge-429">429</span></div>
      <div class="note-inline">Rate limited — rebuild throws, remaining images never requested</div>
      <div class="req-row dim"><span class="path">GET <b>shoes/img-004</b>.jpg</span><span class="badge badge-skip">skipped</span></div>
      <div class="req-row dim"><span class="path">… more never attempted</span></div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-head after">After — one GET per category folder</div>
    <div class="panel-body">
      <div class="req-row"><span class="path">GET <b>/shoes</b>?bundle</span><span class="badge badge-200">200 → shoes.zip</span></div>
      <div class="step-box"><div class="arrow-in">↓</div>Unpack locally — no further network calls</div>
      <div class="chips">
        <span class="chip">img-001.jpg</span><span class="chip">img-002.jpg</span>
        <span class="chip more">+40 more matched</span>
        <span class="chip miss">img-019.jpg — missing</span>
      </div>
      <div class="fallback-box"><b>Fallback (1 image):</b> not in the archive → individual download, same as before.</div>
    </div>
  </div>
</div>
```

---

## 3. Callout components (Note / Tip)

Mirror GitHub's callouts so the HTML and the Markdown feel consistent.

```html
<style>
  .callout{border-left:4px solid var(--accent);background:#ddf4ff;padding:12px 16px;
           border-radius:6px;margin:18px 0;font-size:14.5px}
  .callout.tip{border-left-color:var(--green-border);background:var(--green-bg)}
  .callout b{display:block;margin-bottom:4px;font-size:12px;text-transform:uppercase;letter-spacing:.05em}
</style>

<div class="callout"><b>Note</b>
  Bundle mode only kicks in once a job asks for more than a couple of images, so the
  single-page path is untouched.
</div>
<div class="callout tip"><b>Tip</b>
  A missing image or a failed bundle falls back to an individual download — worst case,
  no worse than before.
</div>
```

---

## 4. Comparison table (HTML)

```html
<style>
  table{border-collapse:collapse;width:100%;margin:14px 0;font-size:13.5px}
  th,td{border:1px solid var(--border);padding:8px 10px;text-align:left}
  th{background:var(--panel-bg)}
</style>
<table>
  <tr><th>Scenario</th><th>Requests before</th><th>Requests after</th></tr>
  <tr><td>Single product page (1 image)</td><td>1</td><td>1 (unchanged)</td></tr>
  <tr><td>Category rebuild (45 images)</td><td>45</td><td>1</td></tr>
  <tr><td>Supplier import (3 folders)</td><td>~135</td><td>3</td></tr>
</table>
```

---

## 5. Full worked example

A complete, self-contained HTML file for the generic thumbnail-batching change lives
alongside this reference at `examples/pr-thumbnails.html` — open it in a browser to see
the target quality bar (narrative + styled before/after, no mermaid, no method dumps).
Copy its structure and swap in the real change you're documenting.
