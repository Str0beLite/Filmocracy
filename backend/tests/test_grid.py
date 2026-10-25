"""grid.find_tiles on a synthetic Explore screenshot: status bar, search bar, 3-column grid with a tall reel,
a half-cut bottom row and a nav bar, in light and dark mode."""
import numpy as np
import pytest
from PIL import Image, ImageDraw
from tandem.grid import find_tiles

W, G, T, NAV = 1080, 3, 358, 2190


def _explore(bg, fg, search):
    rng = np.random.default_rng(0)
    img = Image.new("RGB", (W, 2340), bg)
    d = ImageDraw.Draw(img)
    d.rectangle((900, 40, 1040, 70), fill=fg)
    d.rounded_rectangle((30, 140, 1050, 240), 30, fill=search)
    tiles = []

    def put(x, y, w, h, white_top=False):
        px = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
        if white_top:
            px[: h // 3] = 255   # a white sky touching the gutter must not shrink the tile
        img.paste(Image.fromarray(px), (x, y))
        if y + h <= NAV and h > 200:
            tiles.append((x, y, x + w, y + h))

    xs, last = [0, T + G, 2 * (T + G)], W - 2 * (T + G)
    top, y2 = 280, 280 + T + G
    for c in range(3):
        put(xs[c], top, T if c < 2 else last, T)
    put(0, y2, T, 2 * T + G)   # tall reel spanning two rows
    put(xs[1], y2, T, T, white_top=True)
    put(xs[2], y2, last, T)
    put(xs[1], y2 + T + G, T, T, white_top=True)
    put(xs[2], y2 + T + G, last, T)
    for c in range(3):
        put(xs[c], y2 + 2 * (T + G), T if c < 2 else last, 150)   # cut off by the nav bar
    d.rectangle((0, NAV, W, 2340), fill=bg)
    for k in range(5):
        d.rectangle((90 + k * 210, 2240, 150 + k * 210, 2300), outline=fg, width=6)
    return img, tiles


@pytest.mark.parametrize("bg,fg,search", [((255, 255, 255), (0, 0, 0), (239, 239, 239)),
                                          ((0, 0, 0), (255, 255, 255), (38, 38, 38))])
def test_finds_every_tile_and_skips_ui(bg, fg, search):
    img, tiles = _explore(bg, fg, search)
    assert find_tiles(img) == sorted(tiles, key=lambda b: (b[1], b[0]))


def test_plain_photo_is_not_a_grid():
    px = np.random.default_rng(1).integers(0, 256, (800, 600, 3), dtype=np.uint8)
    assert find_tiles(Image.fromarray(px)) == []
