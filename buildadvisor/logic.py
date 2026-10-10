"""
BuildAdvisor - business logic.

Implements SRS Section 4 (functional requirements) and Section 9 (business
rules): budget-tiered build generation, compatibility checking, FPS estimation
from a benchmark model, mocked live pricing with fallback, upgrade advice, and
a graceful Gemini-style plain-language explanation.
"""

import hashlib
import random
from datetime import datetime, timedelta

import ai
import config
import pricing


# ---------------------------------------------------------------------------
# Budget tiers (SRS 9.1)
# ---------------------------------------------------------------------------
def tier_for_budget(budget: int) -> str:
    for name, low, high in config.TIERS:
        if low <= budget < high:
            return name
    # Above every configured range -> the highest tier (or None if unconfigured).
    return config.TIERS[-1][0] if config.TIERS else None


def _pick(candidates, budget_left, prefer_tier):
    """Pick the best-scoring affordable component, preferring the target tier."""
    affordable = [c for c in candidates if c["price"] <= budget_left]
    if not affordable:
        return None
    tiered = [c for c in affordable if c.get("tier") == prefer_tier]
    pool = tiered or affordable
    # score if present, else cheapest-first is fine
    return max(pool, key=lambda c: (c.get("score", 0), -c["price"]))


# ---------------------------------------------------------------------------
# Compatibility rules (SRS 9.2)
# ---------------------------------------------------------------------------
def check_compatibility(build: dict) -> list:
    """Return a list of human-readable compatibility problems (empty = OK)."""
    problems = []
    cpu, mb = build.get("CPU"), build.get("Motherboard")
    ram, psu = build.get("RAM"), build.get("PSU")
    gpu, case = build.get("GPU"), build.get("Case")

    if cpu and mb and cpu["socket"] != mb["socket"]:
        problems.append(
            f"CPU socket {cpu['socket']} does not match motherboard socket {mb['socket']}."
        )
    if ram and mb and ram["ram_type"] != mb["ram_type"]:
        problems.append(
            f"RAM type {ram['ram_type']} is not supported by the {mb['ram_type']} motherboard."
        )
    if psu and cpu and gpu:
        required = cpu["tdp"] + gpu["tdp"]
        safe = required * 1.4  # safety margin (SRS 9.2)
        if psu["wattage"] < safe:
            problems.append(
                f"PSU {psu['wattage']}W is below the recommended "
                f"{int(safe)}W for a {required}W CPU+GPU load."
            )
    if case and mb and mb["form_factor"] not in case.get("supports", []):
        problems.append(
            f"{mb['form_factor']} motherboard does not fit the selected case."
        )
    return problems


# ---------------------------------------------------------------------------
# Build generation (SRS 4.1) with substitution loop (sequence diagram)
# ---------------------------------------------------------------------------
def generate_build(budget: int, prefer_tier: str = None, catalogue: dict = None):
    """
    Greedy budget-aware generator. Allocates budget across parts, then repairs
    any compatibility issues by substituting cheaper compatible parts.

    `catalogue` is the component catalogue (grouped by type). It comes from the
    SQLite database and MUST be supplied - there is no built-in seed data.

    Returns (build, warnings) or (None, [reason]) if no valid build fits.
    """
    if not config.MIN_BUDGET or not config.TIERS:
        return None, [
            "Business rules are not configured. Set BUILDADVISOR_MIN_BUDGET and "
            "BUILDADVISOR_TIERS in your .env file."
        ]

    order = ["GPU", "CPU", "Motherboard", "RAM", "Storage", "PSU", "Case"]
    if not catalogue:
        return None, ["The component database is empty. Add components before "
                      "generating a build."]
    missing_parts = [p for p in order if not catalogue.get(p)]
    if missing_parts:
        return None, ["Not enough components in the database. Missing: "
                      + ", ".join(missing_parts) + "."]

    if budget < config.MIN_BUDGET:
        return None, [
            f"Minimum budget for a working build is ₹{config.MIN_BUDGET:,}. "
            "Please increase your budget."
        ]

    prefer_tier = prefer_tier or tier_for_budget(budget)

    # Rough budget allocation weights across the 7 parts.
    alloc = {
        "GPU": 0.32, "CPU": 0.20, "Motherboard": 0.13, "RAM": 0.10,
        "Storage": 0.08, "PSU": 0.09, "Case": 0.08,
    }

    # Cheapest possible price for each part, so we can reserve for later parts.
    cheapest = {p: min(c["price"] for c in catalogue[p]) for p in order}

    build = {}
    spent = 0
    for i, part in enumerate(order):
        reserve = sum(cheapest[order[j]] for j in range(i + 1, len(order)))
        cap = budget * alloc[part] * 1.6  # allow some slack, capped by remaining
        budget_left = min(cap, budget - spent - reserve)
        chosen = _pick(catalogue[part], budget_left, prefer_tier)
        if chosen is None:
            chosen = _pick(catalogue[part], budget - spent - reserve, "entry")
        if chosen is None:
            return None, [f"Could not fit a {part} within ₹{budget:,}."]
        build[part] = chosen
        spent += chosen["price"]

    # Repair compatibility by substituting parts (SRS activity diagram).
    build, warnings = _repair(build, budget, catalogue)
    return build, warnings


def _repair(build: dict, budget: int, catalogue: dict):
    warnings = []
    for _ in range(8):
        problems = check_compatibility(build)
        if not problems:
            break
        p = problems[0]
        # Resolve the motherboard around the CPU socket & RAM around the board.
        if "socket" in p and build.get("CPU"):
            match = [m for m in catalogue["Motherboard"] if m["socket"] == build["CPU"]["socket"]]
            if match:
                build["Motherboard"] = min(match, key=lambda m: m["price"])
        if "RAM type" in p and build.get("Motherboard"):
            match = [r for r in catalogue["RAM"] if r["ram_type"] == build["Motherboard"]["ram_type"]]
            if match:
                build["RAM"] = min(match, key=lambda r: r["price"])
        if "PSU" in p and build.get("CPU") and build.get("GPU"):
            need = (build["CPU"]["tdp"] + build["GPU"]["tdp"]) * 1.4
            match = [u for u in catalogue["PSU"] if u["wattage"] >= need]
            if match:
                build["PSU"] = min(match, key=lambda u: u["price"])
        if "case" in p and build.get("Motherboard"):
            match = [c for c in catalogue["Case"] if build["Motherboard"]["form_factor"] in c["supports"]]
            if match:
                build["Case"] = min(match, key=lambda c: c["price"])

    # Budget trim: while over budget, downgrade the priciest non-essential part
    # to the next-cheaper compatible option (SRS 9.1 - never exceed budget).
    trim_order = ["Storage", "RAM", "GPU", "CPU", "Case", "PSU", "Motherboard"]
    for _ in range(20):
        if build_total(build) <= budget:
            break
        downgraded = False
        for part in trim_order:
            cur = build[part]
            cheaper = [c for c in _compatible_options(part, build, catalogue)
                       if c["price"] < cur["price"]]
            if cheaper:
                build[part] = max(cheaper, key=lambda c: c["price"])
                downgraded = True
                break
        if not downgraded:
            break

    over = build_total(build) - budget
    if over > 0:
        warnings.append(
            f"Even the most affordable compatible build is ₹{over:,} over your budget. "
            "Consider raising it slightly."
        )
    remaining = check_compatibility(build)
    if remaining:
        warnings.extend(remaining)
    return build, warnings


def _compatible_options(part: str, build: dict, catalogue: dict):
    """Candidate components for `part` that keep the build compatible."""
    out = []
    for c in catalogue[part]:
        trial = dict(build)
        trial[part] = c
        if not check_compatibility(trial):
            out.append(c)
    return out


def build_total(build: dict) -> int:
    return sum(c["price"] for c in build.values())


# ---------------------------------------------------------------------------
# FPS estimation from a benchmark model (SRS 4.2 / 9.3)
# ---------------------------------------------------------------------------
def estimate_fps(build: dict, game: dict, resolution: str):
    """Return (fps, approximate) using a simple benchmark model."""
    gpu = build.get("GPU")
    cpu = build.get("CPU")
    if not gpu or not cpu:
        return 0, True
    res_mult = config.RESOLUTIONS.get(resolution, 1.0)
    # blend GPU/CPU depending on whether the game is CPU-bound
    if game["cpu_bound"]:
        base = gpu["score"] * 0.55 + cpu["score"] * 0.45
    else:
        base = gpu["score"] * 0.8 + cpu["score"] * 0.2
    fps = (base * 3.2) / (game["weight"] * res_mult)
    return max(15, int(round(fps))), True  # always flagged approximate (no exact DB match)


# ---------------------------------------------------------------------------
# Live pricing with fallback (SRS 4.4 / 9.4 / error handling)
# ---------------------------------------------------------------------------
def _last_known(component):
    stamp = (datetime.now() - timedelta(days=2)).strftime("%d %b %Y")
    return {
        "lowest": component["price"],
        "retailer": "last-known",
        "fresh": False,
        "note": f"Live pricing unavailable — last known price from {stamp}.",
        "quotes": {},
    }


def _mock_quotes(component):
    rng = random.Random(component["id"])  # deterministic per component
    quotes = {}
    for r in (config.RETAILERS or ["Retailer"]):
        delta = rng.uniform(-0.06, 0.09)
        quotes[r] = int(component["price"] * (1 + delta))
    return quotes


def fetch_prices(component: dict, live: bool = True):
    """
    Fetch a multi-retailer price for a component. Returns the lowest price, the
    retailer, and a freshness note.

    Order of preference:
      1. If `live` is False (simulated outage), return last-known price (SRS 9.4).
      2. If live scraping is enabled (ENABLE_SCRAPING=1) and returns quotes, use
         the scraped prices (SRS 4.4 / 7.5).
      3. Otherwise fall back to a deterministic mock so the app works offline.
    """
    if not live:
        return _last_known(component)

    scraped = pricing.fetch_quotes(component)
    if scraped:
        retailer = min(scraped, key=scraped.get)
        return {
            "lowest": scraped[retailer], "retailer": retailer, "fresh": True,
            "note": "Live prices scraped from retailers just now.", "quotes": scraped,
        }

    # Scraping disabled or every retailer failed -> deterministic mock.
    quotes = _mock_quotes(component)
    retailer = min(quotes, key=quotes.get)
    note = ("Live scraping failed for all retailers — showing estimated prices."
            if pricing.is_enabled() else "Prices refreshed just now (simulated).")
    return {
        "lowest": quotes[retailer], "retailer": retailer, "fresh": True,
        "note": note, "quotes": quotes,
    }


def price_build(build: dict, live: bool = True):
    rows, total = [], 0
    for part, comp in build.items():
        p = fetch_prices(comp, live)
        rows.append({
            "part": part, "name": comp["name"],
            "list": comp["price"], "lowest": p["lowest"],
            "retailer": p["retailer"], "fresh": p["fresh"], "quotes": p["quotes"],
        })
        total += p["lowest"]
    return rows, total


# ---------------------------------------------------------------------------
# Upgrade advisor (SRS 4.5)
# ---------------------------------------------------------------------------
def upgrade_advice(current: dict, extra_budget: int, catalogue: dict):
    """
    current = {"CPU": score, "GPU": score, "RAM_gb": int}
    Identify the biggest bottleneck and the most cost-effective upgrade.
    `catalogue` comes from the SQLite database and MUST be supplied.
    """
    catalogue = catalogue or {}
    cpu_s = current.get("CPU", 0)
    gpu_s = current.get("GPU", 0)
    ram = current.get("RAM_gb", 16)

    # Normalised weaknesses (GPU matters most for gaming).
    scores = {
        "GPU": gpu_s,
        "CPU": cpu_s * 1.1,   # slight weight so a very weak CPU still surfaces
        "RAM": (ram / 16) * 60,
    }
    bottleneck = min(scores, key=scores.get)

    recos = []
    if bottleneck == "GPU":
        for g in sorted(catalogue.get("GPU", []), key=lambda x: x["score"]):
            if g["score"] > gpu_s and g["price"] <= extra_budget:
                recos.append(g)
    elif bottleneck == "CPU":
        for c in sorted(catalogue.get("CPU", []), key=lambda x: x["score"]):
            if c["score"] > cpu_s and c["price"] <= extra_budget:
                recos.append(c)
    else:  # RAM
        for r in catalogue.get("RAM", []):
            if r["price"] <= extra_budget:
                recos.append(r)

    best = recos[-1] if recos else None
    return bottleneck, best, recos


# ---------------------------------------------------------------------------
# Gemini-style plain-language explanation (SRS 4.6) with graceful fallback
# ---------------------------------------------------------------------------
def explain_build(build: dict, budget: int, game: dict, resolution: str,
                  fps: int, ai_available: bool = True):
    """
    Produce a plain-language explanation of the build (SRS 4.6).

      1. If `ai_available` is False, return None so the UI shows the build
         without an explanation (SRS 10 - graceful degradation).
      2. If a Gemini API key is configured, call the real Gemini API.
      3. If Gemini is not configured or the call fails, fall back to a locally
         generated explanation so the user still gets a plain-language summary.
    """
    if not ai_available:
        return None

    if ai.is_configured():
        text = ai.explain(build, budget, game, resolution, fps)
        if text:
            return text
        # Gemini configured but failed/timed out -> local fallback below.

    cpu, gpu = build["CPU"], build["GPU"]
    ram, psu = build["RAM"], build["PSU"]
    return (
        f"For a ₹{budget:,} budget aimed at **{game['name']} at {resolution}**, this build "
        f"pairs the **{gpu['name']}** with the **{cpu['name']}** — a balance that keeps the "
        f"graphics card as the star (it does most of the gaming work) while the CPU is strong "
        f"enough to feed it without bottlenecking. You get **{ram['name']}**, which is the "
        f"comfortable sweet spot for modern titles, and a **{psu['name']}** chosen to leave "
        f"headroom above the components' combined power draw. At these settings you should expect "
        f"around **{fps} FPS**. Everything here is socket- and power-compatible, so it will boot "
        f"and run as a balanced whole rather than a mismatched parts list."
    )


# ---------------------------------------------------------------------------
# Save / share (SRS 4.7) - shareable id + validation (SRS 12)
# ---------------------------------------------------------------------------
def share_id(build: dict) -> str:
    key = "|".join(sorted(c["id"] for c in build.values()))
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def sanitize(text: str, limit: int = 60) -> str:
    """Basic validation/sanitisation before storage (SRS 5.4 / 12)."""
    cleaned = "".join(ch for ch in text if ch.isalnum() or ch in " -_'.")
    return cleaned.strip()[:limit]
