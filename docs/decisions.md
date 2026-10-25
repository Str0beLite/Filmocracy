# Decisions

One line each: date, decision, why.

- 2026-10-25: Backend is one FastAPI process (serving + background trainer thread). W is ~6k params, so retraining takes seconds on CPU and needs no separate worker or GPU.
- 2026-10-25: Host on Railway (Dockerfile, volume at `/data` for SQLite + W checkpoints). HF Spaces is the free fallback, but its disk is wiped on restart.
- 2026-10-25: Tag-to-tag model: IG tag vector x (fixed 132-tag vocab) → W → movie tag vector, scored by cosine against each film's row in the movie tag database. W = W0 + ABᵀ (rank 8), W0 built from tag names + hand-picked links, A=0 at start.
- 2026-10-25: Only LLM step is screenshot → IG tags, using Meta Llama vision (Llama API, OpenAI-compatible). No LLM on the movie side.
- 2026-10-25: Loss = taste term (cos(Wx, mean loved-film tags)) + InfoNCE ranking with thumbs-downs as hard negatives + λ‖ABᵀ‖².
- 2026-10-25: Live loop retrains on the whole buffer every 20 events and swaps W only if held-out recall@50 doesn't drop.
