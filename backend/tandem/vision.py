"""Muse Spark reads Explore tiles into tags, then summarizes the whole feed in one text-only call.

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
        "tags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"tag": {"type": "string"}, "weight": {"type": "number", "minimum": 0, "maximum": 1}},
                "required": ["tag", "weight"],
            },
        },
    },
    "required": ["is_ad_or_noise", "tags"],
}

# Neither prompt mentions film. Asking for moods, tones and themes (plus a few broad worlds) instead of personality
# traits lands near the catalog's tag vocabulary anyway: on 3 sample feeds, tags near a film tag rose 35% -> 47%.
PROMPT = (
    "This is one post or reel from someone's Instagram Explore page, which Instagram picked to match their "
    "taste. Describe the feeling and world it pulls them into, the way a critic sums up a work's tone and "
    "themes. Give 5 to 12 short lowercase tags (1 to 3 words each), each with a weight from 0 to 1 for how strongly "
    "it applies. Most tags should be the mood, tone or atmosphere ('dark humor', 'whimsical', 'melancholy', "
    "'suspense', 'feel-good', 'gritty', 'dreamlike') and the deeper themes ('rivalry', 'friendship', 'survival', "
    "'coming of age', 'obsession', 'underdog'). A few may name the broad world, setting or style "
    "('technology', 'robots', 'fashion', 'small town', 'tokyo', '1980s', 'surreal', 'colorful'), kept general: "
    "'technology' not 'ui design'. Never tag formats ('tutorial', 'tips', 'memes', 'app'), personality adjectives "
    "('curious', 'ambitious', 'creative'), plain objects, brands, hashtags or text on screen. "
    "Set is_ad_or_noise to true for ads, sponsored posts, or tiles with no real content.\n\n"
    'Reply with JSON only: {"is_ad_or_noise": false, "tags": [{"tag": "...", "weight": 0.8}]}'
)

MAX_TAGS = 20


def parse_reply(text):
    """Tolerant parse: strip code fences, tidy tag strings, clamp weights. Returns (is_noise, {tag: w})."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(text[text.find("{") : text.rfind("}") + 1])
    tags = {}
    for t in data.get("tags", [])[:MAX_TAGS]:
        name = " ".join(str(t.get("tag", "")).lower().split())[:60]
        if name:
            tags[name] = max(tags.get(name, 0.0), min(max(float(t.get("weight", 0)), 0.0), 1.0))
    return bool(data.get("is_ad_or_noise", False)), tags


async def _ask(client, content):
    """One Muse call with the feed_tags JSON schema. Returns (is_noise, {tag: w}); raises on an unreadable reply."""
    resp = await client.chat.completions.create(
        model=config.MUSE_MODEL,
        max_tokens=config.MUSE_MAX_TOKENS,
        **({"reasoning_effort": config.MUSE_REASONING} if config.MUSE_REASONING else {}),
        messages=[{"role": "user", "content": content}],
        response_format={"type": "json_schema", "json_schema": {"name": "feed_tags", "schema": SCHEMA}},
    )
    return parse_reply(resp.choices[0].message.content or "")


async def read_screenshots(screenshots, concurrency=6):
    """screenshots: list of (bytes, media_type). Returns [(is_noise, {tag: weight})], one per screenshot."""
    client = _client()
    sem = asyncio.Semaphore(concurrency)

    async def one(data, media_type):
        async with sem:
            uri = f"data:{media_type};base64,{base64.standard_b64encode(data).decode()}"
            try:
                return await _ask(
                    client, [{"type": "image_url", "image_url": {"url": uri}}, {"type": "text", "text": PROMPT}]
                )
            except (ValueError, KeyError, TypeError, IndexError, AttributeError):
                return True, {}  # unreadable reply: treat that screenshot as noise rather than fail the upload

    tasks = [asyncio.create_task(one(d, m)) for d, m in screenshots]
    try:
        return await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await client.close()


SYNTH_PROMPT = (
    "Below are tags a model wrote for each post on one person's Instagram Explore page, one line per post "
    "(ads already removed). Looking at the whole feed together, sum up the feelings and worlds that draw this "
    "person in, the way a critic sums up a work's tone and themes: give 10 to 15 short lowercase tags (1 to 3 "
    "words) with weights 0 to 1. Merge near-duplicates into one tag, weight tags by how much of the feed supports "
    "them, and drop one-off tags that don't fit the bigger picture. Mostly moods, tones and themes; at most 4 "
    "broad worlds, settings or styles, kept general. No formats, personality adjectives or brands.\n\n{lines}\n\n"
    'Reply with JSON only: {{"is_ad_or_noise": false, "tags": [{{"tag": "...", "weight": 0.8}}]}}'
)


async def summarize(readings):
    """Final pass: one text-only Muse call sees every post's tags and boils them down to the person.

    Returns ({tag: w}, n_dropped). Falls back to merge()'s plain average if there's under 2 posts or the call fails.
    """
    avg, dropped = merge(readings)
    kept = [tags for noise, tags in readings if not noise and tags]
    if len(kept) < 2:
        return avg, dropped
    lines = "\n".join(
        f"post {i + 1}: " + ", ".join(f"{t} {w:.2f}" for t, w in tags.items()) for i, tags in enumerate(kept)
    )
    client = None
    try:
        client = _client()
        _, tags = await _ask(client, [{"type": "text", "text": SYNTH_PROMPT.format(lines=lines)}])
    except Exception:  # noqa: BLE001 - the average is a fine answer, never fail the upload over this
        return avg, dropped
    finally:
        if client is not None:
            await client.close()
    return tags or avg, dropped


def merge(readings):
    """Average tag weights over the screenshots that weren't noise."""
    kept = [tags for noise, tags in readings if not noise and tags]
    total = {}
    for tags in kept:
        for t, w in tags.items():
            total[t] = total.get(t, 0.0) + w / len(kept)
    return total, len(readings) - len(kept)
