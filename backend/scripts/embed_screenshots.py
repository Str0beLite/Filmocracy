"""Try piece A on its own: feed screenshots -> Llama vision tags -> feed vector x. No server, no catalog.

    set -a; source .env; set +a
    python scripts/embed_screenshots.py ~/Desktop/shot1.png ~/Desktop/shot2.png

Prints each screenshot's tags, the merged tags, and the 384-dim x. Needs LLAMA_API_KEY (see config.LLAMA_*).
"""
import asyncio
import mimetypes
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tandem import vision  # noqa: E402
from tandem.encoder import bag  # noqa: E402


def main(paths):
    if not paths:
        sys.exit(__doc__)
    if not vision.has_api_key():
        sys.exit("set LLAMA_API_KEY first (source .env)")
    shots = [(Path(p).read_bytes(), mimetypes.guess_type(p)[0] or "image/png") for p in paths]
    readings = asyncio.run(vision.read_screenshots(shots))
    for p, (noise, tags) in zip(paths, readings):
        print(f"{Path(p).name}: {'NOISE ' if noise else ''}{tags}")
    tags, dropped = vision.merge(readings)
    x = bag(tags)
    print("\nmerged:", dict(sorted(tags.items(), key=lambda kv: -kv[1])), f"(dropped {dropped} as noise)")
    print(f"x: shape {x.shape}, norm {np.linalg.norm(x):.3f}, first 5 {np.round(x[:5], 3)}")


if __name__ == "__main__":
    main(sys.argv[1:])
