"""
BuildAdvisor - Gemini connectivity checker.

Run this BEFORE the presentation to confirm your .env key + model work and that
the explanation comes back complete (not truncated).

Usage:
    python test_gemini.py
"""

import os

# Load .env exactly like backend.py does, before importing ai.
try:
    from dotenv import load_dotenv
    load_dotenv()
    _DOTENV = True
except ImportError:
    _DOTENV = False

import ai


def _mask(key: str) -> str:
    if not key:
        return "(empty)"
    return f"{key[:6]}...{key[-4:]} ({len(key)} chars)"


def main():
    print("=" * 60)
    print("BuildAdvisor - Gemini connectivity check")
    print("=" * 60)

    # 1. Environment / config
    print(f"python-dotenv installed : {_DOTENV}")
    print(f"requests installed      : {ai.requests is not None}")
    print(f"GEMINI_API_KEY          : {_mask(ai.API_KEY)}")
    print(f"GEMINI_MODEL            : {ai.MODEL}")
    print(f"ai.is_configured()      : {ai.is_configured()}")
    print("-" * 60)

    if not ai.API_KEY:
        print("❌ No API key found. Create a .env file with:")
        print("     GEMINI_API_KEY=your-key")
        return
    if not ai.API_KEY.startswith("AIza"):
        print("⚠️  Warning: a standard Gemini API key usually starts with 'AIza'.")
        print("   If the call fails below, generate an API key (not an OAuth token)")
        print("   at https://aistudio.google.com/apikey")
    if not ai.is_configured():
        print("❌ ai.is_configured() is False - cannot make a live call.")
        return

    # 2. A real call with a tiny sample build
    sample_build = {
        "CPU": {"name": "AMD Ryzen 5 7600", "price": 20500},
        "GPU": {"name": "NVIDIA RTX 4060", "price": 29000},
        "RAM": {"name": "16GB DDR5 5600MHz", "price": 4800},
        "PSU": {"name": "550W 80+ Bronze", "price": 4200},
    }
    game = {"name": "Cyberpunk 2077"}

    print("Calling Gemini... (this makes a real network request)")
    text = ai.explain(sample_build, 90000, game, "1080p", 75)

    print("-" * 60)
    if not text:
        print("❌ No explanation returned.")
        print("   Possible causes: invalid/expired key, wrong model id, no")
        print("   internet, or rate limit. The app will fall back to a local")
        print("   explanation, so it still works - but live Gemini is off.")
        return

    print("✅ Gemini responded. Explanation:\n")
    print(text)
    print("-" * 60)
    # Heuristic: a complete answer ends with sentence punctuation.
    if text.rstrip().endswith((".", "!", "?", "\"")):
        print("✅ Response looks COMPLETE (ends with sentence punctuation).")
    else:
        print("⚠️  Response may be TRUNCATED (does not end cleanly).")
        print("   Increase maxOutputTokens in ai.py if this persists.")


if __name__ == "__main__":
    main()
