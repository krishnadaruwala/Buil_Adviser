"""
BuildAdvisor - Gemini API integration (SRS 4.6 / 7.5).

Generates a plain-language explanation of a recommended build by calling
Google's Gemini API over its REST endpoint. Uses only `requests` (no extra SDK)
so the dependency footprint stays small.

Configuration (environment variables):
    GEMINI_API_KEY   - your Google AI Studio API key (required for live calls)
    GEMINI_MODEL     - model id, default "gemini-1.5-flash"

If no key is configured, or the call fails/times out, the caller falls back to a
locally generated explanation (SRS 10 - graceful degradation).
"""

import os

try:
    import requests
except ImportError:  # keep the app importable even if requests is absent
    requests = None

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT = 20


def is_configured() -> bool:
    return bool(API_KEY) and requests is not None


def _build_prompt(build, budget, game, resolution, fps):
    parts = "\n".join(f"- {part}: {comp['name']} (₹{comp['price']:,})"
                      for part, comp in build.items())
    return (
        "You are a friendly PC-building advisor talking to a gamer who has no "
        "hardware background. In 3-4 short sentences, explain in plain language "
        "why this build is a good, balanced choice for their goal. Mention the "
        "GPU/CPU pairing and value; do NOT use headings or bullet points.\n\n"
        f"Budget: ₹{budget:,}\n"
        f"Target: {game['name']} at {resolution}\n"
        f"Estimated performance: ~{fps} FPS\n"
        f"Components:\n{parts}\n"
    )


def explain(build, budget, game, resolution, fps):
    """
    Call the Gemini API and return the explanation text.
    Returns None on any failure so the caller can fall back gracefully.
    """
    if not is_configured():
        return None

    url = ENDPOINT.format(model=MODEL)
    gen_config = {
        "temperature": 0.7,
        # Room for the full answer. Gemini 2.5 "thinking" models spend part of
        # this budget on internal reasoning, so keep it generous.
        "maxOutputTokens": 1024,
    }
    # Disable "thinking" on 2.5 models so the whole budget goes to the visible
    # answer (fixes truncated/empty responses). 1.5 models reject this field.
    if "2.5" in MODEL:
        gen_config["thinkingConfig"] = {"thinkingBudget": 0}

    payload = {
        "contents": [{"parts": [{"text": _build_prompt(build, budget, game, resolution, fps)}]}],
        "generationConfig": gen_config,
    }
    try:
        resp = requests.post(url, params={"key": API_KEY}, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        candidate = data["candidates"][0]
        # Join every text part (a response can be split across parts).
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        return text or None
    except (requests.exceptions.RequestException, KeyError, IndexError, ValueError):
        # Network error, rate limit, timeout, or unexpected response shape.
        return None
