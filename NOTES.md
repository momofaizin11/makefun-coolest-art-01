# Notes — coolest-art-01 entry

## Goal
One image, `entry.png` (PNG, <= 1024x1024, <= 1 MiB), written by `main.py` at the repository
root. `main.py` copies the finished image next to it to `$MAKEFUN_OUTPUT_DIR` (fallback
`/output`), standard library only, deterministic. The art itself is authored offline by
`tools/render.py` (a studio script, not shipped as the entrypoint; it uses Pillow + numpy and
is never imported by `main.py`).

## The two concepts, side by side
- **A — "Koi of light"**: a koi carp drawn entirely as flowing light (warm gold, coral, white)
  in absolutely dark still water. Single hero shape on a diagonal, head up-right with one calm
  eye, pectoral fins spread like wings, tail dissolving into a drifting nebula of sparks.
  Palette: indigo-black water, gold-white-coral fish, one restrained turquoise accent on the
  ripples. Mood: nocturnal, luminous, quiet power.
- **B — "Eclipse from orbit"**: black eclipse disc with a coronastream of fine white filaments,
  seen from orbit above a curved horizon; thin bright atmosphere band, amber city-light threads
  on the night side, one small lonely satellite. Palette: black, cold white, deep blue, amber.
  Mood: awe, silence, scale.

Both are rendered at least once and compared on criterion 1 (stops you) and criterion 2 (the
idea) before any further work; the winner is carried to the end.

## How each criterion is answered
1. **Stops you** — the fish is the only bright mass in a near-black frame, roughly 10^3 of
   dynamic range against the water, with a large soft bloom. Nothing competes with it.
2. **The idea** — a koi whose *body* is not a body but a bundle of light ribbons, still carrying
   the kohaku patches as zones of coral light, whose tail fin stops being a fin and becomes a
   drifting nebula of sparks. Not a koi on a pond; a koi as light in the dark.
3. **Style** — one mood only: night, silence, warm light on cold black; one accent colour
   (turquoise) reserved for where the light touches the water.
4. **Craft** — the body is a real solid of revolution (arc-length spine + a smooth depth
   profile, shaded cylindrically, silhouette rimmed) so the taper is anatomically plausible and
   the fins attach at believable places; everything is rendered analytically with feathered
   edges and tone-mapped light, so no smears, no banding, no garbled marks.
5. **Reads small** — at 300 px the piece is one bold gold diagonal with a bright fan of sparks
   against black; the fish silhouette, the eye and the tail are still distinct.

No text, no signature, no numbers anywhere in the image.

## How it is rendered (concept A)
Linear-light additive rendering at 1024x1024 with numpy, then a filmic tone map, sRGB transfer,
subtle vignette and a whisper of grain to kill banding:

1. Water: near-black indigo gradient plus faint large-scale mottling, so the background is
   almost pure black but not flat.
2. Body: a Catmull-Rom spine from tail base to snout; a depth profile over arc length; for every
   spine sample the nearest-sample distance field gives the body mask, the along-body coordinate
   `u`, the cross-body coordinate `vn` and the local radius. All shading, ribbons, the kohaku
   colour patches, the gill crease and the rim light are functions of `(u, vn)`.
3. Light ribbon texture that flows along the body, modulated by `u` so the strands drift.
4. Fins as fans of tapered bezier strands with translucent membranes: near pectoral swept down
   and out, far pectoral up and back, faint dorsal ridge, and a tail fan whose strands lengthen,
   thin out and break into loose sparks.
5. The eye as an absence of light: a small dark almond on the bright head with one specular
   point.
6. Water: three or four concentric ripple rings in turquoise, a handful of large out-of-focus
   motes near the lens, and the fish light bloomed back into the water at three radii, tinted
   turquoise only where the light is already falling.

## Concept choice
Both were rendered and judged. **B (eclipse from orbit)** came out as a competent but generic
space illustration — a "stock-illustration / screensaver" coronastream that a judge has seen
many times, so it fails criterion 2. **A (koi of light)** carries its own idea: not a koi in a
pond but a koi whose body *is* the light, whose kohaku patches are zones of coral light, and
whose tail fin dissolves into a spray of sparks. A was chosen and carried to the end.

## Iteration log
Each round was rendered, then looked at full size and at 300 px, and judged on the five criteria.

1. **v1** — first koi and first eclipse. The eclipse read as an eclipse but as generic space art.
   The koi failed: the tone curve saturated almost immediately (linear 0.5 was already 206/255),
   so the whole body clipped into a featureless white blob, fins read as fibre-optic hairs, and
   the eye was invisible. The eclipse was dropped on criteria 1-2.
2. **v2** — added kohaku colour zones, a gill crease, fins as fans with membranes. Still blown
   out; the head stayed white-hot and the volume flat.
3. **v3** — replaced the filmic curve with a soft exponential shoulder (1 - exp(-x)) and dropped
   the light budget of the body ~4x, so mid-tones stopped colliding. The fish read as a fish at
   300 px for the first time (7/10). Fins still beaded, eye a pinprick, patches smudged.
4. **v4** — found and fixed the real eye bug: `xx, yy` had been overwritten with *normalised*
   coordinates, so the eye, the ripples and the motes were all being drawn hundreds of pixels off
   target. Eye, ripples and motes now land where they belong. Fins rebuilt as a scalloped
   translucent web plus ribs. 8/10: eye clear, no smears, anatomy plausible.
5. **v5** — head detail (mouth, gill edge, fin base crease) and a brighter spark spray, but the
   web and the ribs were generated independently and no longer lined up: the judge called the
   fins "doubled, ghosted, motion-blurred". Regressed to 6/10.
6. **v6** — one `fin()` function now builds web *and* ribs from the same angular function, so the
   ribs end exactly on the web's long points. Mouth and gill line both read.
7. **v7** — a hard bright rim light along the back and head so the silhouette snaps off the
   water, stronger internal ribbons, and a three-plane composite (body, far fin, near fin) so
   the near pectoral fin hides the far one instead of layering with it.
8. **v8** — the two pectorals separated for good: the near one became a compact wing with no
   second margin line, the far one a quieter sweep further back. 300 px judge: 8/10, "stops you
   at a glance".
9. **v9** — the hard rim light was flattening the head contour, so it now eases off over the
   head. Full-size 7.5/10.
10. **v10** — the tail is anchored: a deeper peduncle articulation, the tail web starting inside
    the body, and a brighter fin base where it takes hold. Judge: tail "grows out of the body
    convincingly", no regressions.
11. **v11 (shipped)** — four faint strands of light lifting off the back and drifting toward the
    tail, to make the "made of light" idea explicit. Judge: they "improve the sense of flowing
    light", no artefacts, keep. This is `entry.png`.
