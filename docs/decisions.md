# Decisions

One line each: date, decision, why.

- 2026-10-25: Backend is one FastAPI process (serving + background trainer thread). W is ~6k params, so retraining takes seconds on CPU and needs no separate worker or GPU.
- 2026-10-25: Host on Railway (Dockerfile, volume at `/data` for SQLite + W checkpoints). HF Spaces is the free fallback, but its disk is wiped on restart.
- 2026-10-25: Open-vocabulary tags: every tag string is embedded with frozen `bge-small-en-v1.5` (not an LLM); a feed or film = weighted mean of its tag embeddings. W = I + ABᵀ (384×384, rank 8), so no fixed tag lists or hand-made prior. Replaces the fixed 132-tag × movie-tag W.
- 2026-10-25: Only LLM step is screenshot → free-form tags, using Meta Llama vision (Llama API, OpenAI-compatible). No LLM on the movie side.
- 2026-10-25: Loss = taste term (cos(Wx, mean loved-film tags)) + InfoNCE ranking with thumbs-downs as hard negatives + λ‖ABᵀ‖².
- 2026-10-25: Live loop retrains on the whole buffer every 20 events and swaps W only if held-out recall@50 doesn't drop.
