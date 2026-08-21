# Third-party font notices

The reviewer annotation page embeds three typefaces as base64 WOFF2 inside
`assets/review-fonts.css`, so that a generated review page makes **zero network
requests** and every user renders the page identically regardless of what is
installed locally.

All three are licensed under the **SIL Open Font License, Version 1.1**. The full
licence text accompanies each family in this directory.

## Copyright notices

> Copyright 2022 The Instrument Serif Project Authors
> (https://github.com/Instrument/instrument-serif)

> Copyright 2022 The Instrument Sans Project Authors
> (https://github.com/Instrument/instrument-sans)

> Copyright 2020 The JetBrains Mono Project Authors
> (https://github.com/JetBrains/JetBrainsMono)

None of the three declares a Reserved Font Name.

## Licence text

| Family | Role | Licence file |
|---|---|---|
| Instrument Serif | Display | [`OFL-InstrumentSerif.txt`](./OFL-InstrumentSerif.txt) |
| Instrument Sans | Body / UI | [`OFL-InstrumentSans.txt`](./OFL-InstrumentSans.txt) |
| JetBrains Mono | Code / mono | [`OFL-JetBrainsMono.txt`](./OFL-JetBrainsMono.txt) |

## What was done to these fonts

Each font is the **unmodified upstream file**, converted to WOFF2 with Google's
`woff2_compress` (v1.0.2) and nothing else.

- No subsetting
- No instancing or axis pinning
- No glyph removal
- No name-table edits
- No renaming

This matters legally. The OFL FAQ treats subsetting or glyph removal as creating a
**Modified Version**, which would restrict reuse of the original family name. A
pure format conversion is *not* a Modified Version, provided the font data is
unchanged except for compression, so the original names are retained
legitimately.

Verified: after a WOFF2 → TTF round trip the `cmap` and `fvar` tables are
byte-identical to the originals, and the glyph counts match exactly
(377 / 501 / 1743). The `glyf` table differs by design — WOFF2 re-encodes it —
which is why glyph count and `cmap` are the meaningful checks that nothing was
dropped.

## Provenance

`InstrumentSerif` and `InstrumentSans` were fetched from the `google/fonts`
repository at commit `ec626514f79f831f1ab848a82114a0ce7e2d6372`.

| Family | Upstream | Version | Source path |
|---|---|---|---|
| Instrument Serif | `google/fonts` | 1.000 | `ofl/instrumentserif/InstrumentSerif-Regular.ttf` |
| Instrument Sans | `google/fonts` | 1.000 | `ofl/instrumentsans/InstrumentSans[wdth,wght].ttf` |
| JetBrains Mono | `JetBrains/JetBrainsMono` release `v2.304` | 2.304 | `fonts/variable/JetBrainsMono[wght].ttf` |

JetBrains Mono came from the official release archive
`JetBrainsMono-2.304.zip`, SHA-256
`6f6376c6ed2960ea8a963cd7387ec9d76e3f629125bc33d1fdcd7eb7012f7bbf`.

Roman only — no italic files. The design uses no italic text.

## How these families were identified

The family names were read from the design PDF's **own embedded font table**
(`/BaseFont` entries), which lists `InstrumentSerif-Regular`,
`InstrumentSans-Regular`, `InstrumentSans-Regular_Medium`,
`JetBrainsMono-Regular` and `JetBrainsMonoRoman-Medium`.

Each was then independently confirmed by rendering the design's own strings and
measuring ink-mask overlap (IoU) against a crop of the design:

| Face | IoU vs design | Nearest rejected alternative |
|---|---|---|
| Instrument Serif | **0.894** | Playfair Display, 0.307 |
| Instrument Sans | **0.873** | Plus Jakarta Sans 0.345, DM Sans 0.321, Figtree 0.320 |
| JetBrains Mono | glyph-level match | Menlo, visibly different |

Evidence and the tools that produced it are in
`.sisyphus/evidence/reviewer-page-redesign/`.

## Artifact checksums

| Family | Axes | Glyphs | Source TTF |
|---|---|---|---|
| Instrument Serif | none (static) | 377 | 70,012 B |
| Instrument Sans | `wdth` 75–100, `wght` 400–700 | 501 | 194,336 B |
| JetBrains Mono | `wght` 100–800 | 1743 | 303,144 B |

SHA-256, source TTF:

```
498efd461f6ddfcb7a111bf9a565709d2085d48201d501ead960d93e84ffbb88  InstrumentSerif-Regular.ttf
b24f1812584816958afcf22e22d08e44318c5e51651e25d2438efdde389b33b1  InstrumentSans[wdth,wght].ttf
662a196d58f1183bf2d77428b6d5283fe3f45161ab021bea4036bc98e5cac016  JetBrainsMono[wght].ttf
```

SHA-256, embedded WOFF2:

```
adfe0db5f90e4cc5f5c2016fd117ca402da0735a0e6f31a05a71a732880b0dd3  InstrumentSerif-Regular.woff2   27,408 B
8802dbbb44129ebe8652c5c0a322faa3841076812424942ba9d3b7dd54d78803  InstrumentSans[wdth,wght].woff2  88,776 B
e190ee6595a3b9bd25278613a6f5d3766ee1a708f300ed44fa63dbe84051498f  JetBrainsMono[wght].woff2      113,700 B
```

Total embedded WOFF2: **229,884 B**. Resulting `assets/review-fonts.css`:
**309,106 B**.

Axis ranges above were read from each font's `fvar` table directly, not taken
from documentation.

## Constraints the stylesheet must respect

1. **Instrument Serif is static, Regular only.** No bold, no variable axis. Never
   request a weight above 400 on the display face — the browser would synthesise
   a faux-bold, which on a high-contrast serif looks visibly wrong. Use
   `font-synthesis: none` on serif elements. The design's headings are Regular;
   their presence comes from size and contrast, not weight.
2. **Instrument Sans spans wght 400–700 only.** There is no 200 or 300; asking
   for them clamps to 400 and silently differs from intent.
3. **Instrument Sans carries a `wdth` axis (75–100).** `font-stretch: 75% 100%`
   is declared so the axis is addressable; 100% is the default.

## Regenerating

```bash
brew install woff2          # build-time only; not a runtime dependency

# fetch the pinned upstream files (see Provenance), then:
woff2_compress 'InstrumentSerif-Regular.ttf'
woff2_compress 'InstrumentSans[wdth,wght].ttf'
woff2_compress 'JetBrainsMono[wght].ttf'
```

Then rebuild `assets/review-fonts.css` per Phase 0 of
`.sisyphus/plans/reviewer-page-redesign.md`, verify the checksums above, and
confirm the `font-weight` / `font-stretch` ranges still match each font's `fvar`
table.

`woff2` is required only to regenerate this file. Nothing in `SKILL.md`,
`scripts/` or the generated page depends on it at runtime.
