#!/usr/bin/env python3
"""Offline studio for the coolest-art-01 entry (not the shipped entrypoint).

Renders the entry image in linear light with numpy, tone maps it, and writes a
1024x1024 PNG. Pillow + numpy are authoring tools only; the shipped main.py
copies the finished bytes with the standard library alone.

    python3 tools/render.py koi    /root/makefun/art/work/koi.png
    python3 tools/render.py eclipse /root/makefun/art/work/eclipse.png
"""
import sys

import numpy as np
from PIL import Image

N = 1024  # render size


# ---------------------------------------------------------------- small maths
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _box(a, k, axis):
    if k < 2:
        return a
    k = int(k) | 1
    r = k // 2
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r, r)
    ap = np.pad(a, pad, mode="edge")
    c = np.cumsum(ap, axis=axis, dtype=np.float32)
    shp = list(ap.shape)
    shp[axis] = 1
    c = np.concatenate([np.zeros(shp, np.float32), c], axis=axis)
    n = ap.shape[axis]
    m = n - k + 1
    lo = np.take(c, np.arange(0, m), axis=axis)
    hi = np.take(c, np.arange(k, n + 1), axis=axis)
    return (hi - lo) / float(k)


def blur(a, sigma):
    """Approximate gaussian with three box passes."""
    if sigma <= 0.6:
        return a
    k = int(round(sigma * 2.0)) | 1
    b = a
    for _ in range(3):
        b = _box(b, k, 0)
        b = _box(b, k, 1)
    return b


def catmull_rom(pts, m):
    """Smooth curve through pts (M,2) -> dense polyline (m,2)."""
    p = np.asarray(pts, np.float32)
    p = np.vstack([p[0] + (p[0] - p[1]), p, p[-1] + (p[-1] - p[-2])])
    segs = len(p) - 3
    t = np.linspace(0.0, segs - 1e-6, m, dtype=np.float32)
    i = np.clip(t.astype(np.int32), 0, segs - 1)
    f = (t - i)[:, None]
    p0, p1, p2, p3 = p[i], p[i + 1], p[i + 2], p[i + 3]
    return 0.5 * (
        2 * p1
        + (-p0 + p2) * f
        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f ** 2
        + (-p0 + 3 * p1 - 3 * p2 + p3) * f ** 3
    )


def resample_even(poly, n):
    d = np.r_[0.0, np.cumsum(np.hypot(*np.diff(poly, axis=0).T))]
    s = np.linspace(0.0, d[-1], n)
    return np.stack([np.interp(s, d, poly[:, 0]), np.interp(s, d, poly[:, 1])], 1), s


def quad_bezier(p0, p1, p2, m):
    t = np.linspace(0.0, 1.0, m, dtype=np.float32)[:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


def rot(x, y, a):
    c, s = np.cos(a), np.sin(a)
    return c * x - s * y, s * x + c * y


# ---------------------------------------------------------------- light canvas
class Canvas:
    """Additive linear-light RGB canvas."""

    def __init__(self, n=N):
        self.n = n
        self.rgb = np.zeros((n, n, 3), np.float32)
        self.yy, self.xx = np.mgrid[0:n, 0:n].astype(np.float32)

    def add(self, mask, color):
        self.rgb += mask[..., None] * np.asarray(color, np.float32)[None, None, :]

    def add_rgb(self, arr):
        self.rgb += arr

    def disc(self, cx, cy, r, color, intensity=1.0, feather=2.0, ring=0.0):
        d = np.hypot(self.xx - cx, self.yy - cy)
        m = smoothstep(r + feather, max(r - feather, r * 0.2), d)
        if ring:
            m = m * (1.0 - ring) + ring * np.exp(-((d - r * 0.86) / (r * 0.09 + 1e-3)) ** 2)
        self.add(m * intensity, color)

    def stroke(self, pts, radii, colors, intens, feather=1.5):
        """Tapered additive stroke along a polyline."""
        pts = np.asarray(pts, np.float32)
        radii = np.asarray(radii, np.float32)
        colors = np.asarray(colors, np.float32)
        if colors.ndim == 1:
            colors = np.repeat(colors[None, :], len(pts), 0)
        intens = np.asarray(intens, np.float32)
        if intens.ndim == 0:
            intens = np.full(len(pts), float(intens), np.float32)
        n = self.n
        for i in range(len(pts)):
            r = float(radii[i]) + feather
            if r <= 0.3 or intens[i] <= 0.0:
                continue
            cx, cy = float(pts[i, 0]), float(pts[i, 1])
            x0, x1 = int(max(0, cx - r - 1)), int(min(n, cx + r + 2))
            y0, y1 = int(max(0, cy - r - 1)), int(min(n, cy + r + 2))
            if x1 <= x0 or y1 <= y0:
                continue
            dx = np.arange(x0, x1, dtype=np.float32)[None, :] - cx
            dy = np.arange(y0, y1, dtype=np.float32)[:, None] - cy
            d = np.sqrt(dx * dx + dy * dy)
            inner = max(radii[i] - feather * 1.6, radii[i] * 0.45)
            w = smoothstep(r, inner, d)
            self.rgb[y0:y1, x0:x1, :] += (
                (w * intens[i])[..., None] * colors[i][None, None, :]
            )

    def save(self, path, exposure=1.0, vignette=0.0, grain=0.0, seed=7):
        x = np.maximum(self.rgb, 0.0) * exposure
        # soft exponential shoulder: keeps mid-tones apart instead of clipping them
        y = 1.0 - np.exp(-x)
        y = np.clip(y, 0.0, 1.0)
        srgb = np.where(y <= 0.0031308, y * 12.92, 1.055 * y ** (1 / 2.4) - 0.055)
        if vignette:
            r = np.hypot(self.xx - self.n / 2, self.yy - self.n / 2) / (self.n * 0.72)
            srgb *= (1.0 - vignette * np.clip(r, 0, 1.6) ** 2)[..., None]
        if grain:
            rng = np.random.default_rng(seed)
            srgb += rng.normal(0.0, grain, srgb.shape[:2]).astype(np.float32)[..., None]
        u8 = np.clip(srgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
        img = Image.fromarray(u8)
        img.save(path, optimize=True)
        g = u8.mean(2)
        print("   stats: mean %.1f  p50 %.0f p90 %.0f p99 %.0f  blown(>250) %.2f%%  lit(>40) %.1f%%"
              % (g.mean(), np.percentile(g, 50), np.percentile(g, 90), np.percentile(g, 99),
                 100.0 * (g > 250).mean(), 100.0 * (g > 40).mean()), flush=True)
        return path


# ---------------------------------------------------------------- body fields
def body_fields(pts, radii, feather=1.6):
    """Nearest-sample fields for a variable-radius ribbon: mask, u, vn, r."""
    n = N
    mask = np.zeros((n, n), np.float32)
    uu = np.zeros((n, n), np.float32)
    vv = np.zeros((n, n), np.float32)
    rr = np.zeros((n, n), np.float32)
    best = np.full((n, n), 1e18, np.float32)
    seg = np.diff(pts, axis=0)
    nrm = np.stack([-seg[:, 1], seg[:, 0]], 1)
    nrm /= np.maximum(np.hypot(nrm[:, 0], nrm[:, 1]), 1e-6)[:, None]
    nrm = np.vstack([nrm, nrm[-1:]])
    for i in range(len(pts)):
        r = float(radii[i])
        R = r + feather + 2.0
        cx, cy = float(pts[i, 0]), float(pts[i, 1])
        x0, x1 = int(max(0, cx - R)), int(min(n, cx + R + 2))
        y0, y1 = int(max(0, cy - R)), int(min(n, cy + R + 2))
        if x1 <= x0 or y1 <= y0:
            continue
        dx = np.arange(x0, x1, dtype=np.float32)[None, :] - cx
        dy = np.arange(y0, y1, dtype=np.float32)[:, None] - cy
        d2 = dx * dx + dy * dy
        loc = best[y0:y1, x0:x1]
        upd = d2 < loc
        loc[upd] = d2[upd]
        uu[y0:y1, x0:x1][upd] = i / (len(pts) - 1.0)
        vv[y0:y1, x0:x1][upd] = (dx * nrm[i, 0] + dy * nrm[i, 1])[upd]
        rr[y0:y1, x0:x1][upd] = r
    d = np.sqrt(best)
    m = smoothstep(rr + feather, np.maximum(rr - feather * 0.35, 0.0), d)
    m *= (rr > 0.0)
    vn = np.clip(vv / np.maximum(rr, 1e-6), -1.5, 1.5)
    return m, uu, vn, rr


def blob(u, vn, u0, u1, v0, v1, p0=0.0, p1=0.0, wob=0.30):
    a = (u - u0) / (u1 - u0)
    b = (vn - v0) / (v1 - v0)
    q = np.hypot((a - 0.5) * 2.0, (b - 0.5) * 2.0)
    q = q * (1.0 + wob * (np.sin(2 * np.pi * 2.7 * a + p0) + 0.7 * np.sin(2 * np.pi * 1.9 * b + p1)))
    return smoothstep(1.02, 0.62, q)


def fin(canvas, origin, ang_c, ang_half, length, col_in, col_out, bright,
        lobes=5, scallop=0.13, feather=4.0, phase=0.0, rim=0.75, base_dim=0.45,
        ray_w=0.030, ray_bright=0.085, ray_over=1.06, taper_low=0.0, back=0.0):
    """One fin: a scalloped translucent web plus ribs that end on its long points.

    Web and ribs are generated from the same angular function, so the fin reads as
    a single object instead of two overlaid ones.
    """
    ox, oy = float(origin[0]), float(origin[1])
    col_in = np.asarray(col_in, np.float32)
    col_out = np.asarray(col_out, np.float32)
    d = np.hypot(canvas.xx - ox, canvas.yy - oy)
    rel = np.arctan2(canvas.yy - oy, canvas.xx - ox) - ang_c
    rel = (rel + np.pi) % (2 * np.pi) - np.pi
    ar = np.abs(rel)
    inside = smoothstep(ang_half + 0.02, ang_half - 0.06, ar)
    lobe = 0.5 - 0.5 * np.cos(np.pi * lobes * ar / ang_half + phase)
    L = length * (1.0 - scallop * lobe)
    L *= (1.0 - taper_low) + taper_low * (0.55 + 0.45 * np.cos(np.pi * ar / ang_half))
    f = np.clip(d / np.maximum(L, 1e-3), 0.0, 1.0)
    mem = inside * smoothstep(1.0, 1.0 - feather / np.maximum(L, 1e-3), f)
    c = col_in[None, None, :] * (1 - f)[..., None] + col_out[None, None, :] * f[..., None]
    val = mem * bright * (base_dim + (1.0 - base_dim) * (1.0 - f) ** 1.2)
    val += inside * np.exp(-((d - L) / (feather * 0.9)) ** 2) * bright * rim
    canvas.add_rgb(val[..., None] * c)

    # ribs, one per long point of the web
    n = lobes + 1
    for k in range(n):
        relk = -ang_half + 2.0 * ang_half * k / lobes
        a = ang_c + relk
        ell = length * (1.0 - scallop * (0.5 - 0.5 * np.cos(np.pi * lobes * abs(relk) / ang_half + phase)))
        ell *= (1.0 - taper_low) + taper_low * (0.55 + 0.45 * np.cos(np.pi * abs(relk) / ang_half))
        m = 30
        p0 = np.array([ox, oy], np.float32) + np.array([np.cos(a), np.sin(a)], np.float32) * back
        p2 = np.array([ox, oy], np.float32) + np.array([np.cos(a), np.sin(a)], np.float32) * ell * ray_over
        p1 = (p0 + p2) / 2 + np.array([-np.sin(a), np.cos(a)], np.float32) * 0.06 * ell * (1 if k % 2 else -1)
        seg = quad_bezier(p0, p1, p2, m)
        s = np.linspace(0, 1, m)
        rad = np.maximum(0.8, ray_w * ell * np.sin(np.linspace(0, np.pi, m)) ** 0.35)
        if k in (0, n - 1):
            rad *= 0.55
        cols = col_in[None, :] * (1 - s[:, None]) + col_out[None, :] * s[:, None]
        canvas.stroke(seg, rad, cols, ray_bright * (1.0 - 0.5 * s ** 1.4), feather=1.3)


def spark_spray(canvas, origin, direction, spread, length, count, col, seed=11,
                streaks=12):
    """The tail fin coming apart: distinct soft sparks plus a few motion streaks."""
    rng = np.random.default_rng(seed)
    d = np.asarray(direction, np.float32)
    d = d / np.hypot(*d)
    p = np.array([-d[1], d[0]])
    col = np.asarray(col, np.float32)
    for _ in range(count):
        t = rng.random() ** 0.60
        dist = length * (0.02 + 0.98 * t)
        lat = rng.normal(0, 1) * spread * (0.12 + 1.8 * t)
        pos = origin + d * dist + p * lat
        r = 1.8 + 5.6 * rng.random() ** 2.0
        inten = (0.35 + 1.10 * rng.random() ** 1.3) * (1.0 - 0.32 * t)
        canvas.disc(float(pos[0]), float(pos[1]), float(r),
                    col * (0.72 + 0.5 * rng.random()), float(inten), feather=1.6)
    for _ in range(streaks):
        t = rng.random() ** 0.7
        dist = length * (0.04 + 0.85 * t)
        lat = rng.normal(0, 1) * spread * (0.15 + 1.4 * t)
        base = origin + d * dist + p * lat
        a = np.arctan2(d[1], d[0]) + rng.normal(0, 0.30)
        ll = 12.0 + 34.0 * rng.random()
        tip = base + np.array([np.cos(a), np.sin(a)], np.float32) * ll
        m = 8
        seg = quad_bezier(base, (base + tip) / 2 + p * 3.0 * rng.normal(), tip, m)
        s = np.linspace(0, 1, m)
        canvas.stroke(seg, np.maximum(0.8, 2.4 * (1 - s) ** 1.2), col * 0.9,
                      (0.45 + 0.55 * rng.random()) * (1 - s) ** 1.1, feather=1.5)


# ---------------------------------------------------------------- concept A
KOI = dict(
    exposure=1.65,
    fish=1.0,
    bloom_n=0.26, bloom_ns=4.0,       # tight glow, keeps detail
    bloom_m=0.14, bloom_ms=22.0,
    bloom_w=0.050, bloom_ws=85.0,
    turq=0.10,
    vignette=0.26,
    grain=0.0018,
)


def render_koi(path, **over):
    p = dict(KOI)
    p.update(over)
    cv = Canvas()
    rng = np.random.default_rng(4)
    X, Y = cv.xx, cv.yy
    x, y = X / N, Y / N

    # --- spine: tail base (lower left) to snout (upper right), gentle S
    ctrl = np.array([[0.205, 0.726], [0.332, 0.778], [0.460, 0.664],
                     [0.586, 0.484], [0.686, 0.300]], np.float32) * N
    dense = catmull_rom(ctrl, 700)
    pts, _ = resample_even(dense, 460)
    u_of = np.linspace(0.0, 1.0, 460)
    uprof = np.array([0.00, 0.06, 0.18, 0.32, 0.46, 0.60, 0.72, 0.82, 0.90, 0.96, 1.00])
    rprof = np.array([0.021, 0.043, 0.082, 0.112, 0.128, 0.136, 0.127, 0.106, 0.080, 0.048, 0.012])
    radii = np.maximum(np.interp(u_of, uprof, rprof) * N, 1.2)

    tng = np.gradient(pts, axis=0)
    tng /= (np.hypot(tng[:, 0], tng[:, 1])[:, None] + 1e-6)
    nrm = np.stack([-tng[:, 1], tng[:, 0]], 1)     # fish's own left flank

    mask, uu, vn, rr = body_fields(pts, radii, feather=1.7)
    u = uu

    # --- body: a smooth luminous volume, lit from above and behind
    shade = np.sqrt(np.clip(1.0 - vn ** 2, 0.0, 1.0))
    top = smoothstep(-1.0, 0.25, -vn)
    stream = 0.5 + 0.5 * np.sin(2 * np.pi * (1.5 * vn + 0.55 * u + 0.22 * np.sin(2 * np.pi * 0.9 * u + 0.4)))
    stream2 = 0.5 + 0.5 * np.sin(2 * np.pi * (0.8 * vn - 0.30 * u + 0.6))

    p1 = blob(u, vn, 0.30, 0.60, -1.10, 0.10, 0.4, 1.1)
    p2 = blob(u, vn, 0.78, 1.00, -1.15, 0.02, 2.2, 0.2)
    p3 = blob(u, vn, 0.02, 0.16, -0.85, 0.30, 1.3, 2.7)
    pat = np.clip(p1 + 0.95 * p2 + 0.80 * p3, 0.0, 1.0) * mask

    wave = 0.58 + 0.42 * (0.5 + 0.5 * np.sin(2 * np.pi * (1.15 * u + 0.18 * np.sin(2 * np.pi * 0.7 * u))))
    lum = 0.045 + 0.155 * shade ** 1.1 + 0.105 * top
    lum += (0.070 * stream + 0.038 * stream2) * shade ** 0.7 * (1.0 - 0.72 * pat)
    lum -= 0.045 * smoothstep(-0.3, 1.0, vn)
    lum += (0.070 + 0.110 * wave) * np.exp(-((np.abs(vn) - 0.965) / 0.070) ** 2)
    lum += 0.055 * wave * np.exp(-((vn + 0.72) / 0.11) ** 2)
    hard = np.exp(-((-vn - 0.962) / 0.024) ** 2) * (0.65 + 0.35 * wave)
    hard *= 1.0 - 0.40 * smoothstep(0.85, 0.99, u)      # let the head keep its contour
    lum += 0.42 * hard * mask
    ugain = 1.0 + 0.20 * np.exp(-((u - 0.955) / 0.06) ** 2)
    ugain *= 0.72 + 0.28 * smoothstep(0.0, 0.20, u)
    lum *= mask * p["fish"] * ugain
    lum *= (1.0 - 0.42 * np.exp(-((u - 0.050) / 0.034) ** 2))     # peduncle narrows

    cream = np.array([1.00, 0.845, 0.630], np.float32)
    coral = np.array([1.00, 0.255, 0.095], np.float32)
    tcol = np.clip(pat, 0, 1)[..., None]
    col = cream[None, None, :] * (1 - tcol) + coral[None, None, :] * tcol
    lum *= (1.0 + 0.40 * pat)

    front = Canvas()
    back = Canvas()
    near = Canvas()
    front.add_rgb(lum[..., None] * col)

    # --- pectoral fins: near one sweeps down and out like a wing, far one up and back
    si = int(0.84 * (len(pts) - 1))
    sh = pts[int(0.795 * (len(pts) - 1))]
    sang = float(np.arctan2(tng[si, 1], tng[si, 0]))
    pno = sh + 0.060 * N * np.array([np.cos(sang + 1.5), np.sin(sang + 1.5)], np.float32)
    fin(near, pno, sang + 2.36, 0.54, 0.195 * N, [1.0, 0.87, 0.68], [1.0, 0.46, 0.24],
        0.150, lobes=4, scallop=0.16, feather=3.4, rim=0.0, base_dim=0.55,
        ray_w=0.032, ray_bright=0.060, ray_over=0.96, back=0.025 * N)
    pfo = sh + 0.060 * N * np.array([np.cos(sang - 1.5), np.sin(sang - 1.5)], np.float32)
    fin(back, pfo, sang - 2.48, 0.42, 0.140 * N, [0.90, 0.76, 0.58], [0.90, 0.38, 0.18],
        0.045, lobes=4, scallop=0.16, feather=3.0, rim=0.0, base_dim=0.55,
        ray_w=0.024, ray_bright=0.026, ray_over=0.96, back=0.025 * N)

    # --- dorsal fin: a low translucent ridge with fine ribs
    db, dt = int(0.38 * (len(pts) - 1)), int(0.68 * (len(pts) - 1))
    dpts, drad, dcol, dint = [], [], [], []
    for i in range(db, dt):
        fq = (i - db) / max(1.0, dt - db)
        h = 0.032 * N * np.sin(np.pi * fq) ** 0.8
        base_p = pts[i] - nrm[i] * (radii[i] * 0.80)
        dpts.append(base_p - nrm[i] * h * 0.5)
        drad.append(h * 0.55)
        dcol.append(np.array([0.92, 0.72, 0.50]) * (1 - fq) + np.array([1.0, 0.5, 0.25]) * fq)
        dint.append(0.050 * np.sin(np.pi * fq) ** 0.6 + 0.02)
    front.stroke(np.array(dpts, np.float32), np.maximum(np.array(drad, np.float32), 1.0),
                 np.array(dcol, np.float32), np.array(dint, np.float32), feather=3.0)

    # --- strands of light lifting off the back, drifting back toward the tail
    for k, (uu0, ll, br) in enumerate([(0.36, 0.150, 0.055), (0.50, 0.185, 0.065),
                                       (0.63, 0.150, 0.050), (0.74, 0.105, 0.040)]):
        i = int(uu0 * (len(pts) - 1))
        base = pts[i] - nrm[i] * (radii[i] * 0.92)
        up = -nrm[i]
        tip = base + (up * 0.75 - tng[i] * 0.55) * ll * N
        ctrl = (base + tip) / 2 + up * 0.10 * ll * N
        seg = quad_bezier(base, ctrl, tip, 26)
        sN = np.linspace(0, 1, 26)
        rad = np.maximum(0.9, 5.0 * (1 - sN) ** 0.8)
        canvas_fin = front
        canvas_fin.stroke(seg, rad, [1.0, 0.84, 0.60],
                          br * (1 - sN) ** 1.6, feather=2.4)

    # --- tail fin: a coherent fan at the peduncle that comes apart into sparks
    tb = pts[0]
    td = tb - pts[int(0.10 * (len(pts) - 1))]
    tang = float(np.arctan2(td[1], td[0]))
    fin(front, tb, tang, 0.80, 0.230 * N, [1.0, 0.90, 0.72], [1.0, 0.42, 0.18],
        0.130, lobes=8, scallop=0.20, feather=4.0, rim=0.30, base_dim=0.46,
        ray_w=0.023, ray_bright=0.070, ray_over=1.04, taper_low=0.22, back=0.075 * N)
    front.add(np.exp(-((u - 0.108) / 0.022) ** 2) * mask * 0.09, [1.0, 0.72, 0.45])
    start = tb + np.array([np.cos(tang), np.sin(tang)], np.float32) * 0.175 * N
    spark_spray(front, start, [np.cos(tang), np.sin(tang)], 0.095 * N, 0.33 * N, 190,
                [1.0, 0.66, 0.30], seed=33, streaks=14)
    gp = np.array([np.cos(tang), np.sin(tang)], np.float32)
    pp = np.array([-gp[1], gp[0]], np.float32)
    a_ = (X - float(tb[0])) * gp[0] + (Y - float(tb[1])) * gp[1]
    b_ = (X - float(tb[0])) * pp[0] + (Y - float(tb[1])) * pp[1]
    cloud = np.exp(-((a_ - 0.27 * N) / (0.155 * N)) ** 2) * \
        np.exp(-(b_ / (0.055 * N + 0.26 * np.maximum(a_, 0.0))) ** 2)
    cloud *= smoothstep(0.0, 0.13 * N, a_)
    front.add(blur(cloud, 30) * 0.075, [1.0, 0.40, 0.28])

    # --- composite: the far fin is occluded by the body
    nearc = np.clip(near.rgb.mean(2) * 9.0, 0.0, 1.0)
    fish = front.rgb + back.rgb * (1.0 - np.clip(mask + nearc, 0.0, 1.0))[..., None] + near.rgb
    cover = np.clip(fish.mean(2) * 6.0, 0.0, 1.0)

    # --- water: near-black indigo, faint mottling, a soft dark pocket behind the fish
    bg = (1 - y)[..., None] * np.array([0.0022, 0.0030, 0.0080], np.float32) + \
        y[..., None] * np.array([0.0055, 0.0063, 0.0150], np.float32)
    mott = blur(rng.random((N, N)).astype(np.float32), 60)
    mott = (mott - mott.mean()) / (mott.std() + 1e-6)
    bg = bg * (1.0 + 0.30 * mott)[..., None]
    bg *= (1.0 - 0.60 * np.clip(blur(cover, 30), 0.0, 1.0))[..., None]
    cv.add_rgb(bg)

    F = fish
    cv.add_rgb(F)
    cv.add_rgb(blur(F, p["bloom_ns"]) * p["bloom_n"])
    cv.add_rgb(blur(F, p["bloom_ms"]) * p["bloom_m"] * np.array([1.0, 0.94, 0.88], np.float32))
    cv.add_rgb(blur(F, p["bloom_ws"]) * p["bloom_w"])
    turq = np.array([0.28, 0.95, 1.00], np.float32)
    cv.add_rgb(blur(F * turq[None, None, :], 140) * p["turq"])

    # --- ripples: barely visible concentric rings centred on the fish, turquoise
    centre = pts[int(0.45 * (len(pts) - 1))]
    angr = -0.62
    dxr, dyr = rot(X - float(centre[0]), Y - float(centre[1]), angr)
    for (ar, br, it) in [(0.30, 0.215, 1.0), (0.42, 0.290, 0.72),
                         (0.56, 0.390, 0.50), (0.72, 0.500, 0.32)]:
        rho = np.hypot(dxr / (ar * N), dyr / (br * N))
        ring = np.exp(-((rho - 1.0) / 0.018) ** 2)
        ring *= 1.0 - smoothstep(0.45, 1.20, rho)
        cv.add(blur(ring, 2.6) * it * 0.075, turq)

    # --- out of focus motes near the lens, kept clear of the fish
    for (mx, my, mr, mi) in [(0.105, 0.150, 0.032, 0.070), (0.880, 0.115, 0.026, 0.055),
                             (0.945, 0.560, 0.038, 0.058), (0.070, 0.392, 0.022, 0.045),
                             (0.520, 0.930, 0.030, 0.042), (0.780, 0.965, 0.022, 0.036)]:
        d = np.hypot(X - mx * N, Y - my * N)
        r = mr * N
        disc = smoothstep(r + 3.0, r - 10.0, d)
        rim = np.exp(-((d - r * 0.90) / (r * 0.13)) ** 2)
        cv.add(blur((disc * 0.5 + rim * 0.8) * mi, 6.0), [1.0, 0.70, 0.42])

    # --- head: gill cover, mouth, fin base, eye — light removed at the very end
    crease = np.exp(-((u - (0.858 - 0.055 * vn)) / 0.020) ** 2)
    cv.rgb *= (1.0 - 0.78 * crease * mask)[..., None]
    cv.add(np.exp(-((u - (0.888 - 0.055 * vn)) / 0.012) ** 2) * mask * 0.13, [1.0, 0.88, 0.66])
    mm = np.exp(-((u - 0.980) / 0.020) ** 2) * np.exp(-((vn + 0.02) / 0.42) ** 2)
    cv.rgb *= (1.0 - 0.80 * mm * mask)[..., None]
    cv.add(np.exp(-((u - 1.0) / 0.007) ** 2) * mask * 0.13, [1.0, 0.90, 0.70])
    fin_base = np.exp(-((u - 0.812) / 0.017) ** 2) * smoothstep(-0.35, 0.75, vn)
    cv.rgb *= (1.0 - 0.48 * fin_base * mask)[..., None]

    ie = int(0.925 * (len(pts) - 1))
    eye_c = pts[ie] + nrm[ie] * (0.44 * radii[ie])
    ang = float(np.arctan2(tng[ie, 1], tng[ie, 0]))
    er = 0.0190 * N
    xn, yn = rot(X - float(eye_c[0]), Y - float(eye_c[1]), -ang)
    ee = np.hypot(xn / (er * 0.66), yn / er)
    iris = np.exp(-((ee - 1.22) / 0.30) ** 2)
    cv.add(iris * 0.16 * mask, [1.0, 0.68, 0.36])
    socket = smoothstep(1.15, 0.60, ee)
    cv.rgb *= (1.0 - 0.30 * socket)[..., None]
    eye = smoothstep(1.02, 0.72, np.hypot(xn / (er * 0.60), yn / er))
    cv.rgb *= (1.0 - 0.996 * eye)[..., None]
    cv.add(eye * 0.02, [0.16, 0.20, 0.34])
    cv.disc(float(eye_c[0]) - 3.6 * np.cos(ang) + 4.8 * np.sin(ang),
            float(eye_c[1]) - 3.6 * np.sin(ang) - 4.8 * np.cos(ang),
            er * 0.28, [1.0, 0.97, 0.90], 0.95, feather=1.3)

    cv.save(path, exposure=p["exposure"], vignette=p["vignette"], grain=p["grain"], seed=5)
    return path


# ---------------------------------------------------------------- concept B
def render_eclipse(path):
    cv = Canvas()
    rng = np.random.default_rng(9)
    yy, xx = cv.yy, cv.xx
    cx, cy = 0.30 * N, 1.62 * N          # planet centre, far below the frame
    pr = 1.28 * N                        # planet radius
    d = np.hypot(xx - cx, yy - cy)
    limb = d - pr

    # night side of the planet
    night = smoothstep(6.0, -40.0, limb)
    cv.add(night * 0.030, [0.10, 0.13, 0.26])
    # atmosphere: thin bright band on the limb
    band = np.exp(-((limb) / (7.0)) ** 2) * (limb > -30.0)
    halo = np.exp(-np.maximum(limb, 0.0) / 34.0) * (limb > -6.0)
    cv.add(band * 1.5 + halo * 0.30, [0.62, 0.80, 1.00])
    cv.add(halo * 0.16, [0.35, 0.55, 1.00])
    # stable star field
    for _ in range(220):
        sx, sy = rng.random() * N, rng.random() * N
        if np.hypot(sx - cx, sy - cy) < pr + 20:
            continue
        cv.disc(sx, sy, 0.6 + 1.6 * rng.random() ** 3, [0.85, 0.90, 1.0],
                0.20 + 0.8 * rng.random() ** 2.2, feather=1.0)
    # city lights on the night side, amber threads
    for _ in range(90):
        a = rng.random() * 2 * np.pi
        rr0 = pr - 8.0 - 190.0 * rng.random() ** 1.6
        bx, by = cx + rr0 * np.cos(a), cy + rr0 * np.sin(a)
        if not (0 <= bx < N and 0 <= by < N):
            continue
        n_seg = int(3 + 14 * rng.random())
        ang = rng.random() * np.pi
        for k in range(n_seg):
            ll = 2.0 + 7.0 * rng.random()
            ox = bx + (k - n_seg / 2) * (ll + 2.0) * np.cos(ang) + rng.normal(0, 3)
            oy = by + (k - n_seg / 2) * (ll + 2.0) * np.sin(ang) + rng.normal(0, 3)
            cv.disc(ox, oy, 0.5 + 1.1 * rng.random(), [1.0, 0.62, 0.22],
                    0.10 + 0.5 * rng.random() ** 2, feather=1.0)
    # the eclipse disc and its corona
    ex, ey, er = 0.615 * N, 0.395 * N, 0.150 * N
    dd = np.hypot(xx - ex, yy - ey)
    ring = np.exp(-((dd - er) / (er * 0.030)) ** 2)
    cv.add(ring * 3.0, [1.0, 0.98, 0.92])
    glow = np.exp(-np.maximum(dd - er, 0) / (er * 0.10)) * (dd > er - 1)
    cv.add(glow * 1.1, [0.90, 0.94, 1.00])
    n_fil = 260
    for k in range(n_fil):
        a = 2 * np.pi * k / n_fil
        wob = (np.sin(3.0 * a + 0.7) + 0.6 * np.sin(7.0 * a) + 0.4 * np.sin(13.0 * a + 2.1))
        ell = er * (0.16 + 0.55 * max(0.0, wob) ** 0.8 + 0.30 * rng.random() ** 3)
        p0 = np.array([ex + er * np.cos(a), ey + er * np.sin(a)], np.float32)
        p2 = np.array([ex + (er + ell) * np.cos(a), ey + (er + ell) * np.sin(a)], np.float32)
        p1 = (p0 + p2) / 2 + np.array([-np.sin(a), np.cos(a)], np.float32) * ell * 0.10 * rng.normal()
        m = 12
        pp = quad_bezier(p0, p1, p2, m)
        prof = np.sin(np.linspace(0, np.pi, m)) ** 0.7
        rad = np.maximum(0.6, 2.2 * prof * (0.6 + 0.8 * abs(wob)))
        inten = 0.25 + 0.85 * max(0.0, wob) + 0.35 * rng.random()
        cv.stroke(pp, rad, [1.0, 0.99, 0.97], inten * prof, feather=1.1)
    # moon disc painted over (occluder)
    occ = smoothstep(er + 1.2, er - 1.2, dd)
    cv.rgb *= (1.0 - occ)[..., None]
    cv.add(occ * 0.004, [0.05, 0.06, 0.12])
    # one small satellite crossing the frame
    sx, sy = 0.845 * N, 0.215 * N
    sdir = np.array([-0.72, 0.69], np.float32)
    for t in range(-9, 10):
        f = t / 9.0
        p = np.array([sx, sy], np.float32) + sdir * f * 26.0
        cv.disc(float(p[0]), float(p[1]), 6.0 - 4.5 * abs(f) ** 1.3,
                [0.80, 0.86, 1.0], 1.5 if abs(f) < 0.35 else 0.45, feather=1.0)
    for sgn in (-1, 1):
        p = np.array([sx, sy], np.float32) + sdir * sgn * 30.0
        q = np.array([-sdir[1], sdir[0]], np.float32)
        dp = np.array([p, p + q * 13, p - q * 13], np.float32)
        cv.stroke(dp, np.array([4.0, 4.0, 1.0]), [0.45, 0.52, 0.80], 0.5, feather=1.0)
    # tiny blue planet shine + bloom
    F = cv.rgb.copy()
    cv.add_rgb(blur(F, 10) * 0.55 + blur(F, 55) * 0.40 + blur(F, 170) * 0.20)
    cv.save(path, exposure=0.95, vignette=0.12, grain=0.0010, seed=6)
    return path


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "koi"
    out = sys.argv[2] if len(sys.argv) > 2 else "/root/makefun/art/work/%s.png" % what
    fn = {"koi": render_koi, "eclipse": render_eclipse}[what]
    print("wrote", fn(out), flush=True)
