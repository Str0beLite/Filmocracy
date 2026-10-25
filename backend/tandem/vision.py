"""The only LLM step: Meta Muse Spark reads each Explore tile into free-form tags with weights.

Talks to the Meta Model API's OpenAI-compatible Chat Completions (see config.MUSE_*).
"""
import asyncio
import base64
import json
import os
import re

from . import config


def has_api_key() -> bool:
    return bool(os.environ.get(config.MUSE_API_KEY_ENV))


def _client():
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=os.environ.get(config.MUSE_API_KEY_ENV), base_url=config.MUSE_BASE_URL)


SCHEMA = {
    "type": "object",
    "properties": {
        "is_ad_or_noise": {"type": "boolean"},
        "tags": {"type": "array", "items": {
            "type": "object",
            "properties": {"tag": {"type": "string"}, "weight": {"type": "number", "minimum": 0, "maximum": 1}},
            "required": ["tag", "weight"]}},
    },
    "required": ["is_ad_or_noise", "tags"],
}

PROMPT = (
    "This is one post or reel from someone's Instagram Explore page, which Instagram picked to match their "
    "taste. Guess what kind of person this user is, with 5 to 15 short lowercase tags (1 to 4 words each), each "
    "with a weight from 0 to 1 for how strongly it applies. At least half the tags must be moods, vibes or "
    "personality (e.g. 'cozy', 'dark humor', 'chaotic energy', 'adrenaline junkie'); the rest can name the "
    "topic (e.g. 'street food', 'deadlift'). Skip plain objects unless they are the whole theme. "
    "Set is_ad_or_noise to true for ads, sponsored posts, or tiles with no real content.\n\n"
    'Reply with JSON only: {"is_ad_or_noise": false, "tags": [{"tag": "...", "weight": 0.8}]}'
)

MAX_TAGS = 20


def parse_reply(text):
    """Tolerant parse: strip code fences, tidy tag strings, clamp weights. Returns (is_noise, {tag: w})."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(text[text.find("{"): text.rfind("}") + 1])
    tags = {}
    for t in data.get("tags", [])[:MAX_TAGS]:
        name = " ".join(str(t.get("tag", "")).lower().split())[:60]
        if name:
            tags[name] = max(tags.get(name, 0.0), min(max(float(t.get("weight", 0)), 0.0), 1.0))
    return bool(data.get("is_ad_or_noise", False)), tags


async def read_screenshots(screenshots, concurrency=6):
    """screenshots: list of (bytes, media_type). Returns [(is_noise, {tag: weight})], one per screenshot."""
    client = _client()
    sem = asyncio.Semaphore(concurrency)

    async def one(data, media_type):
        async with sem:
            uri = f"data:{media_type};base64,{base64.standard_b64encode(data).decode()}"
            resp = await client.chat.completions.create(
                model=config.MUSE_MODEL,
                max_tokens=config.MUSE_MAX_TOKENS,
                **({"reasoning_effort": config.MUSE_REASONING} if config.MUSE_REASONING else {}),
                messages=[{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": uri}},
                    {"type": "text", "text": PROMPT},
                ]}],
                response_format={"type": "json_schema",
                                 "json_schema": {"name": "feed_tags", "schema": SCHEMA}},
            )
            try:
                return parse_reply(resp.choices[0].message.content or "")
            except (ValueError, KeyError, TypeError):
                return True, {}   # unreadable reply: treat that screenshot as noise rather than fail the upload

    return await asyncio.gather(*[one(d, m) for d, m in screenshots])


def merge(readings):
    """Average tag weights over the screenshots that weren't noise."""
    kept = [tags for noise, tags in readings if not noise and tags]
    total = {}
    for tags in kept:
        for t, w in tags.items():
            total[t] = total.get(t, 0.0) + w / len(kept)
    return total, len(readings) - len(kept)
