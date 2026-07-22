## Background (Why?)

The catalog service builds product thumbnails by downloading each product image from
our CDN, one at a time. That's fine for a single product page, but it falls apart for
bulk jobs: rebuilding thumbnails for a whole category, or importing a new supplier's
catalog, means issuing one HTTP request per image, back to back.

The CDN rate-limits that pattern. Past a certain number of requests in a short window
it starts answering with `429`, and the rebuild throws partway through the category,
leaving thumbnails half-generated with no easy way to tell where it stopped.

> [!NOTE]
> This only affects **bulk jobs** (category rebuilds, supplier imports). The per-page
> thumbnail fetch was never at risk — the problem only shows up once a job asks for
> more than a handful of images at once.

## Description (How?)

The core idea: the CDN stores images in per-category folders and can hand back a whole
folder as a single `.zip` via a `?bundle` endpoint. So instead of asking for each
image one request at a time, we ask for the category once, unpack it locally, and only
fall back to individual per-image requests for whatever the archive didn't contain.

> [!TIP]
> A styled before/after walkthrough (colored request rows, the 429, the extract step,
> file chips) is in the visual companion: `examples/pr-thumbnails.html` — open it in a
> browser, or drop the panels into the PR as images.

Concretely, for a category with 45 images:

| | Before | After |
|---|---|---|
| Requests to the CDN | 45 (one per image) | 1 bundle + up to a few fallbacks |
| Where it fails | Aborts on the ~6th request (`429`) | Completes; only genuinely missing images fall back |
| Images actually built | 5 of 45 | 45 of 45 |

Requested images are grouped by the category folder they live in, each folder is
fetched once as a `.zip`, and the archive is unpacked locally so the rest of the
pipeline never notices the difference — it still receives the same `id → local path`
map it always did.

> [!NOTE]
> Bulk mode only kicks in once a job asks for **more than 2 images**. A 1–2 image
> request — the per-page case — isn't worth building and unpacking a `.zip` for, so it
> keeps using plain per-image requests exactly as before.

Two failure modes are handled differently on purpose:

- **An image is missing from the archive**, or **the whole bundle request fails**
  (timeout, a `429` on that one request, folder not published yet) — logged as a
  warning, and that specific image falls back to the original per-image download. One
  bad folder doesn't take down the rest of the job.
- **Access is denied** (`401`/`403`) — the token simply can't see this category, so
  retrying per-image would just waste time hiding a real access problem. This is raised
  immediately instead of falling back.

> [!WARNING]
> **Trade-off:** unpacking a folder's `.zip` reads every image in that category into
> memory before picking out the ones actually requested. Our category folders are small
> enough that this isn't a concern in practice, but it's worth knowing if a folder ever
> grows unusually large.

Closes #123

### Affected areas & models

- Thumbnail build pipeline — bulk downloads from the CDN
- No change to the per-page single-image path

### Should be tested by QA

Yes.

- Run a category rebuild for more than 2 images and confirm all expected thumbnails
  build successfully (previously this could abort with a rate-limit error partway
  through).
- Run a single-product page and confirm the thumbnail still loads as before.
- Optional: point at a category where one image is known to be missing and confirm it
  falls back gracefully instead of failing the whole job.
