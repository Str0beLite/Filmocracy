# Decisions

One line each: date, decision, why.

- 2026-10-25: Backend is one FastAPI process (serving + background trainer thread). W is ~6k params, so retraining takes seconds on CPU and needs no separate worker or GPU.
- 2026-10-25: Host on Railway (Dockerfile, volume at `/data` for SQLite + W checkpoints). HF Spaces is the free fallback, but its disk is wiped on restart.
- 2026-10-25: Frozen `bge-small-en-v1.5` encoder; learned low-rank translator W = I + ABᵀ (rank 8, A=0 at start so day 0 is zero-shot). Design doc: https://claude.ai/artifact/CEuwV3qHic4wosqiwbJdV5
- 2026-10-25: Taste profiles for reels and movies written by `claude-haiku-5-5` (cheap, vision). Movie profiles built once offline and committed.
- 2026-10-25: Live loop retrains on the whole buffer every 20 events and swaps W only if held-out recall@50 doesn't drop.
