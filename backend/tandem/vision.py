"""The only LLM step: a Meta Llama vision model reads feed screenshots into free-form tags with weights.

Talks to any OpenAI-compatible endpoint (Meta's Llama API by default; see config.LLAMA_*).
"""
import asyncio
import base64
import json
import os
import re

from . import config


def has_api_key() -> bool:
    return bool(os.environ.get(config.LLAMA_API_KEY_ENV))


def _client():
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=os.environ.get(config.LLAMA_API_KEY_ENV), base_url=config.LLAMA_BASE_URL)


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
    "This is a screenshot of someone's Instagram feed or a reel they watched. Describe it with 5 to 15 short "
    "lowercase tags (1 to 4 words each), each with a weight from 0 to 1 for how strongly it applies. Cover what "
    "it shows (e.g. 'street food', 'deadlift') AND how it feels (e.g. 'chaotic energy', 'cozy', 'dark humor'). "
    "Set is_ad_or_noise to true for ads, sponsored posts, or screens with no real content.\n\n"
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
                model=config.LLAMA_MODEL,
                max_tokens=512,
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
