## Background (Why?)

The catalog service builds product thumbnails by asking the CDN for one image at a
time: a single request per thumbnail. That works fine on a product page, where only
one image is ever needed, but a category rebuild asks for every image in that
category back to back, with nothing pacing the requests out.

Fire off 45 of those requests in a row and the CDN pushes back. Around the sixth
request it starts returning `429`, and the rebuild just stops where it is. The other
39 images are never even requested, and there's no retry, no resume, just a category
stuck at 5 thumbnails out of 45 with no record of where it gave up.

## Description (How?)

The CDN can also hand back an entire category as a single `.zip`, through a
`?bundle` endpoint. So instead of requesting each image on its own, the rebuild now
asks for the category once, unpacks the archive locally, and only reaches for the old
per-image request when something didn't make it into the bundle.

That bundling only kicks in past a couple of images. A single product page still
fetches its one thumbnail the old way, since building and unpacking a `.zip` for one
image isn't worth it.

A styled before/after walkthrough of this, the `429`, the unpack step, the file
chips, is in `examples/pr-thumbnails.html`.

For a category with 45 images:

| | Before | After |
|---|---|---|
| Requests to the CDN | 45 (one per image) | 1 bundle plus rare fallbacks |
| Where it fails | Aborts on the ~6th request (`429`) | Completes; only genuinely missing images fall back |
| Images actually built | 5 of 45 | 45 of 45 |

If an image is missing from the archive, or the bundle request itself times out, that
one image quietly falls back to the old per-image download, logged as a warning,
while the rest of the category keeps going. An access-denied response gets treated
differently: if the token can't see the category at all, retrying image by image
would just hide a permissions problem, so that gets raised immediately instead.

> [!WARNING]
> Unpacking a category's `.zip` loads every image in that folder into memory before
> picking out the ones actually requested. Fine at today's folder sizes, worth
> revisiting if a category ever grows much larger.

Closes #123

### Affected areas & models

- Thumbnail build pipeline — category and bulk-import downloads from the CDN
- No change to the single-image, per-page path

### Should be tested by QA

Yes.

- Rebuild a category with more than a couple dozen images and confirm every thumbnail
  builds (previously this stalled partway through with a rate-limit error).
- Load a single product page and confirm its thumbnail still comes through as before.
- Point at a category with one image known to be missing and confirm it falls back
  instead of failing the whole rebuild.
