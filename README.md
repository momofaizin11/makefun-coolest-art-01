# Koi of light — coolest-art-01 entry

**The piece.** A koi carp drawn entirely as flowing light: ribbons of warm gold, coral and
white in absolutely black still water. The fish is the only bright mass in the frame — a single
glowing shape on a diagonal, head up and to the right, one calm dark eye, the koi's *kohaku*
pattern carried as zones of coral light, pectoral fins spread like wings, and a tail fin that
stops being a fin and comes apart into a drifting nebula of sparks. Deep indigo-black water,
a few barely visible turquoise ripples, large soft out-of-focus motes near the lens. One mood:
nocturnal, luminous, quiet power.

**How to run it.** The finished image is `entry.png`, beside the program.

```
python3 main.py                                  # writes /output/entry.png
MAKEFUN_OUTPUT_DIR=out python3 main.py           # writes out/entry.png
```

`main.py` is Python 3.13-compatible, standard library only, deterministic, and writes the exact
bytes of `entry.png` to `$MAKEFUN_OUTPUT_DIR` (falling back to `/output`).

**How it was made.** `tools/render.py` is the studio that produced the image — it is not part of
the entry program and nothing in `main.py` imports it. It renders in linear light with numpy
(spine and depth profile for the body, distance-field shading and kohaku colour zones, fins as
scalloped webs with ribs, sparks, bloom, ripples, motes), then tone maps, adds a whisper of
grain and writes the PNG. It needs Pillow and numpy (authoring tools only):

```
python3 tools/render.py koi /tmp/koi.png          # the entry piece
python3 tools/render.py eclipse /tmp/eclipse.png  # the concept it was chosen over
```

`NOTES.md` records the concept, how it answers the judge's five criteria, and the iteration log.
