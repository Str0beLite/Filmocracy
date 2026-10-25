"""Split an Instagram Explore screenshot into one crop per tile, from pixel colour alone.

Explore tiles are separated by thin gutters in the app's background colour (white or black). We find
those gutters as rows/columns of near-uniform background pixels and cut recursively (XY-cut), which
also handles the tall reel tiles that span two rows. Status bar, search bar and nav bar fall out as
boxes that are mostly background or the wrong shape, and get dropped.
"""
import io

import numpy as np
from PIL import Image, UnidentifiedImageError

FLAT = 8           # max channel range for a line to count as flat
BG_TOL = 10        # how close a flat line must be to the background colour (search bar grey is ~16 off)
MIN_TILE = 0.18    # min tile side, as a fraction of image width
ASPECT = (0.35, 1.6)   # tile width / height: square posts ~1, tall reels ~0.5


def _background(a):
    """The gutter colour: the median colour of fully flat columns, else of fully flat rows."""
    for axis in (0, 1):
        flat = np.ptp(a, axis=axis).max(-1) <= FLAT
        if flat.any():
            lines = a[:, flat] if axis == 0 else a[flat]
            return np.median(lines.reshape(-1, 3), axis=0)
    return None


def _gutters(a, bg, axis):
    """Bool per column (axis=0) or row (axis=1): is this whole line flat background?"""
    flat = np.ptp(a, axis=axis).max(-1) <= FLAT
    near = np.abs(a.mean(axis=axis) - bg).max(-1) <= BG_TOL
    return flat & near


def _segments(mask):
    """Runs of False in mask -> [(start, end)]."""
    out, start = [], None
    for i, g in enumerate(list(mask) + [True]):
        if not g and start is None:
            start = i
        elif g and start is not None:
            out.append((start, i))
            start = None
    return out


def _cut(a, bg, x0, y0, x1, y1, depth=0):
    if depth > 8:
        return [(x0, y0, x1, y1)]
    sub = a[y0:y1, x0:x1]
    for axis in (0, 1):   # try column gutters first, then row gutters
        segs = _segments(_gutters(sub, bg, axis))
        if len(segs) > 1 or (segs and segs[0] != (0, sub.shape[1 - axis])):
            boxes = []
            for s, e in segs:
                box = (x0 + s, y0, x0 + e, y1) if axis == 0 else (x0, y0 + s, x1, y0 + e)
                boxes += _cut(a, bg, *box, depth + 1)
            return boxes
    return [(x0, y0, x1, y1)]


def _regrow(a, bg, boxes):
    """A tile with a white sky (or black night) at its edge gets cut short, because that edge looks like
    gutter. Grow such tiles back into the flat rows above/below to a full square (S) or tall reel (2S + g)."""
    w_img = a.shape[1]
    cols = [b for b in boxes if MIN_TILE * w_img <= b[2] - b[0] < 0.5 * w_img]   # tile-width boxes (not nav icons)
    squares = [b[3] - b[1] for b in cols if abs((b[3] - b[1]) - (b[2] - b[0])) <= 0.02 * (b[2] - b[0])]
    if not squares:
        return boxes
    s = int(np.median(squares))
    gaps = [r[0] - left[2] for left in cols for r in cols if left[1] == r[1] and 0 < r[0] - left[2] < 0.02 * w_img]
    g = int(np.median(gaps)) if gaps else 0
    out = []
    for x0, y0, x1, y1 in boxes:
        h = y1 - y0
        if (x0, y0, x1, y1) in cols and min(abs(h - s), abs(h - (2 * s + g))) > 0.02 * s:
            need = min((t for t in (s, 2 * s + g) if t > h), default=h) - h
            above = a[max(y0 - need, 0):y0, x0:x1]
            below = a[y1:y1 + need, x0:x1]
            if need and len(above) == need and _gutters(above, bg, 1).all():
                y0 -= need
            elif need and len(below) == need and _gutters(below, bg, 1).all():
                y1 += need
        out.append((x0, y0, x1, y1))
    return out


def find_tiles(img: Image.Image):
    """Image -> [(x0, y0, x1, y1)] tile boxes in reading order (top to bottom, left to right)."""
    a = np.asarray(img.convert("RGB"), dtype=np.int16)
    bg = _background(a)
    if bg is None:
        return []
    h, w = a.shape[:2]
    keep = []
    for x0, y0, x1, y1 in _regrow(a, bg, _cut(a, bg, 0, 0, w, h)):
        bw, bh = x1 - x0, y1 - y0
        if min(bw, bh) < MIN_TILE * w or not ASPECT[0] <= bw / bh <= ASPECT[1]:
            continue
        bg_share = (np.abs(a[y0:y1, x0:x1] - bg).max(-1) <= BG_TOL).mean()
        if bg_share < 0.5:   # mostly background = UI chrome, not a post
            keep.append((x0, y0, x1, y1))
    return sorted(keep, key=lambda b: (b[1], b[0])) if len(keep) >= 2 else []   # one box is a photo, not a grid


def split_explore(data: bytes):
    """Screenshot bytes -> [(png bytes, "image/png")], one per tile. Empty if no grid was found."""
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except (UnidentifiedImageError, OSError):
        return []
    out = []
    for box in find_tiles(img):
        buf = io.BytesIO()
        img.crop(box).save(buf, "PNG")
        out.append((buf.getvalue(), "image/png"))
    return out
