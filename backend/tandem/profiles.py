"""Rewrite reels and movies into one shared taste vocabulary with Claude.

Both sides land in the same schema (mood, themes, aesthetic, pacing, setting, who loves it),
so the encoder compares like with like instead of creator-speak vs critic-speak.
"""
import asyncio
import base64
import os

from pydantic import BaseModel, Field

from . import config

SCHEMA_HELP = (
    "Describe TASTE, not topic: a cooking reel might be 'warm, tactile, patient craft', "
    "not 'cooking'. Keep each field to a short phrase or a few comma-separated words."
)


class TasteProfile(BaseModel):
    mood: str
    themes: str
    aesthetic: str
    pacing: str
    setting: str
    who_loves_this: str

    def to_text(self) -> str:
        return (
            f"mood: {self.mood}. themes: {self.themes}. aesthetic: {self.aesthetic}. "
            f"pacing: {self.pacing}. setting: {self.setting}. who loves this: {self.who_loves_this}."
        )


class ReelProfile(TasteProfile):
    is_ad_or_noise: bool = Field(description="True for ads, sponsored posts, or screens with no reel on them")
    caption_summary: str = Field(description="One short line saying what the reel shows")


def has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _client():
    import anthropic

    return anthropic.AsyncAnthropic()


async def _parse(client, content, output_format):
    resp = await client.messages.parse(
        model=config.PROFILE_MODEL,
        max_tokens=1024,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": content}],
        output_format=output_format,
    )
    return resp.parsed_output


async def profile_reels(screenshots=(), captions=(), concurrency=8):
    """screenshots: list of (bytes, media_type). captions: list of text (e.g. from an IG data export)."""
    client = _client()
    sem = asyncio.Semaphore(concurrency)
    ask = (
        "This is one Instagram reel from someone's feed. Write a taste profile of it. "
        f"{SCHEMA_HELP} Flag ads and non-reel screens with is_ad_or_noise."
    )

    async def one_image(data, media_type):
        async with sem:
            img = {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                                "data": base64.standard_b64encode(data).decode()}}
            return await _parse(client, [img, {"type": "text", "text": ask}], ReelProfile)

    async def one_caption(text):
        async with sem:
            return await _parse(client, [{"type": "text", "text": f"{ask}\n\nReel caption:\n{text}"}], ReelProfile)

    jobs = [one_image(d, m) for d, m in screenshots] + [one_caption(c) for c in captions]
    return await asyncio.gather(*jobs)


async def profile_movies(movies, concurrency=16, on_done=None):
    """movies: list of dicts with title, year, overview, genres, keywords, tagline."""
    client = _client()
    sem = asyncio.Semaphore(concurrency)

    async def one(m):
        async with sem:
            text = (
                "Write a taste profile of this film, in the words a fan would use to describe how it feels. "
                f"{SCHEMA_HELP}\n\nTitle: {m['title']} ({m.get('year', '')})\nGenres: {m.get('genres', '')}\n"
                f"Keywords: {m.get('keywords', '')}\nTagline: {m.get('tagline', '')}\nOverview: {m.get('overview', '')}"
            )
            try:
                p = await _parse(client, [{"type": "text", "text": text}], TasteProfile)
            except Exception as e:  # one bad row shouldn't kill a 5k build; fall back to raw text
                print(f"profile failed for {m['title']}: {e}")
                p = None
            if on_done:
                on_done(m, p)
            return p

    return await asyncio.gather(*[one(m) for m in movies])


def raw_movie_text(m) -> str:
    """No-LLM fallback: the raw metadata, so the pipeline still runs without an API key."""
    return f"{m['title']}. genres: {m.get('genres', '')}. keywords: {m.get('keywords', '')}. {m.get('tagline', '')} {m.get('overview', '')}"
