## In one sentence

Category rebuilds now pull every thumbnail in a category as a single archive instead of hammering the CDN with one image at a time.

## The problem

The catalog service builds product thumbnails by asking the CDN for one image at a time. That works fine on a product page, where only one or two images are ever needed, but a category rebuild asks for every image in that category back to back.

Fire off 45 of those requests in a row and the CDN pushes back. Around the sixth request it starts returning `429`, and the rebuild just stops where it is. The other 39 images are never even requested, and there is no retry, no resume, just a category stuck at 5 thumbnails out of 45 with no record of where it gave up.

Closes #123

## What happens today

Imagine a category with 45 images. We fetch image 1, image 2, image 3, image 4, image 5, and around the 6th the CDN starts answering `429`. The job aborts right there. Images 6 through 45 are never requested, never built, and never shown. The category stays stuck at 5 of 45 images, and the next rebuild starts from the beginning and hits the same wall.

## Why that's a problem

The rebuild does not fail gracefully. It does not skip the rate-limited image and keep going. It does not mark which images succeeded so a later run can resume. It simply dies, leaving the category mostly empty and forcing the same failing pattern every time the job runs.

## What changes

Category rebuilds now fetch the whole category as one archive instead of asking for each image separately. A single download replaces the storm of per-image requests, and only the rare image that is genuinely missing from the bundle falls back to the old one-at-a-time path.

The bundling only kicks in past a couple of images. A single product page still fetches its one thumbnail the old way, since building and unpacking an archive for one image is not worth it.

## Before and after

| | Before | After |
|---|---|---|
| Requests to the CDN | 45 (one per image) | 1 bundle plus rare fallbacks |
| Where it fails | Aborts on the ~6th request (`429`) | Completes; only genuinely missing images fall back |
| Images actually built | 5 of 45 | 45 of 45 |

## Example

Before: 45 requests → 429 at ~6 → 5 of 45 built.

After: 1 bundle request → 45 of 45 built, only genuinely missing images fall back.

## What QA should test

- Load a single product page and confirm its thumbnail still renders exactly as before.
- Rebuild a category with more than a couple dozen images and confirm every thumbnail builds with no `429` abort.
- Point at a category with one image known to be missing from the bundle and confirm that one image falls back instead of failing the whole rebuild.
- Run a small job that touches 2 images or fewer and confirm it still uses the old per-image path.

## What this does not change

How thumbnails are stored, named, and served stays the same. Only how the CDN receives the download requests changes.

## Technical details

Category downloads hit the `?bundle` endpoint to collect every image in the category as one `.zip`. The archive is unpacked locally, and only images the bundle does not contain fall back to per-image downloads. If the bundle itself times out, the same fallback applies to the missing images. An access-denied response is treated differently: when the token cannot see the category at all, retrying image by image would only hide a permissions problem, so that failure is raised immediately.

The bundling threshold is 2 images. Jobs with 2 or fewer images keep the old per-image path entirely.

## Risks / trade-offs

> [!WARNING]
> Unpacking a category's `.zip` loads every image in that folder into memory before picking out the requested ones. That is fine at today's folder sizes, but worth revisiting if a category ever grows much larger.
