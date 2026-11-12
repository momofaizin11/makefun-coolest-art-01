#!/usr/bin/env python3
"""coolest-art-01 entry: copy the finished image to the output directory.

The art is `entry.png`, sitting beside this file. This program writes those
exact bytes to `$MAKEFUN_OUTPUT_DIR/entry.png`, falling back to `/output`, so
the same file can be produced inside the grader and on a laptop.

    MAKEFUN_OUTPUT_DIR=out python3 main.py

Standard library only, deterministic, no network.
"""
import os
import sys

IMAGE = "entry.png"


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    src = os.path.join(here, IMAGE)
    dst = os.path.join(out_dir, IMAGE)

    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        print("cannot create output directory %s: %s" % (out_dir, exc), file=sys.stderr)
        return 1

    with open(src, "rb") as fh:
        data = fh.read()
    if not data:
        print("source image %s is empty" % src, file=sys.stderr)
        return 1

    if os.path.abspath(src) != os.path.abspath(dst):
        with open(dst, "wb") as fh:
            fh.write(data)
    print("wrote %s (%d bytes)" % (dst, len(data)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
