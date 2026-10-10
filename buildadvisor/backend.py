"""
BuildAdvisor - Flask backend (SRS Section 7.3).

Handles request routing and business logic, reads/writes the SQLite component
database, and orchestrates pricing + AI-explanation. The Streamlit frontend
talks to these endpoints over HTTP, matching the sequence diagram in SRS 3.11.

Run:  python backend.py         (serves on http://localhost:8000)
"""

from functools import wraps

# Load environment variables from a local .env file BEFORE importing modules
# (ai.py / pricing.py read their config at import time). Safe no-op if the
# python-dotenv package or the .env file is missing.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import Flask, jsonify, request

import ai
import config
import db
import logic
import pricing

app = Flask(__name__)

# Demo admin credential (SRS 12 - admin functions require authentication).
ADMIN_PASSWORD = "admin123"
ADMIN_TOKEN = "admin-session-token"

# Ensure the database file and empty tables exist on startup (no seeding).
db.init_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.headers.get("X-Admin-Token") != ADMIN_TOKEN:
            return jsonify({"error": "Admin authentication required."}), 401
        return fn(*args, **kwargs)
    return wrapper


def _serialize_build(build: dict):
    """Turn the {part: component} build into a JSON-safe list."""
    return [{"part": part, **comp} for part, comp in build.items()]


# ---------------------------------------------------------------------------
# Health & reference data
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "BuildAdvisor backend",
        "gemini_live": ai.is_configured(),      # real Gemini key present
        "scraping_live": pricing.is_enabled(),   # live retailer scraping on
        "rules_configured": config.is_configured(),  # business rules in .env
        "rules_missing": config.missing(),
        "catalogue_empty": db.is_empty(),        # no components added yet
    })


@app.get("/config")
def get_config():
    """Expose the env-driven business rules the frontend needs (resolutions, tiers)."""
    return jsonify({
        "min_budget": config.MIN_BUDGET,
        "tiers": [{"name": n, "low": lo, "high": hi} for n, lo, hi in config.TIERS],
        "resolutions": list(config.RESOLUTIONS.keys()),
        "retailers": config.RETAILERS,
        "configured": config.is_configured(),
        "missing": config.missing(),
    })


@app.get("/games")
def games():
    return jsonify(db.get_games())


@app.get("/components")
def components():
    return jsonify(db.list_components())


# ---------------------------------------------------------------------------
# Generate build (SRS 4.1 / sequence diagram POST /generate-build)
# ---------------------------------------------------------------------------
@app.post("/generate-build")
def generate_build():
    body = request.get_json(force=True, silent=True) or {}
    try:
        budget = int(body.get("budget", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Budget must be a number."}), 400

    game_name = body.get("game")
    resolution = body.get("resolution", "1080p")
    live_prices = bool(body.get("live_prices", True))
    ai_available = bool(body.get("ai_available", True))

    if budget <= 0:
        return jsonify({"error": "Please enter a valid budget."}), 400

    catalogue = db.get_catalogue()
    games_list = db.get_games()
    if not games_list:
        return jsonify({
            "error": "No games in the database yet. Add games before generating a build.",
            "buildable": False,
        }), 200
    game = next((g for g in games_list if g["name"] == game_name), games_list[0])

    build, warnings = logic.generate_build(budget, catalogue=catalogue)
    if build is None:
        return jsonify({"error": warnings[0], "buildable": False}), 200

    fps, approx = logic.estimate_fps(build, game, resolution)
    rows, live_total = logic.price_build(build, live=live_prices)
    explanation = logic.explain_build(build, budget, game, resolution, fps,
                                      ai_available=ai_available)

    return jsonify({
        "buildable": True,
        "budget": budget,
        "game": game,
        "resolution": resolution,
        "build": _serialize_build(build),
        "list_total": logic.build_total(build),
        "live_total": live_total,
        "price_rows": rows,
        "fps": fps,
        "fps_approximate": approx,
        "explanation": explanation,
        "warnings": warnings,
        "live_prices": live_prices,
        "share_code": logic.share_id(build),
    })


# ---------------------------------------------------------------------------
# Upgrade advisor (SRS 4.5)
# ---------------------------------------------------------------------------
@app.post("/upgrade")
def upgrade():
    body = request.get_json(force=True, silent=True) or {}
    current = {
        "CPU": float(body.get("cpu_score", 0)),
        "GPU": float(body.get("gpu_score", 0)),
        "RAM_gb": int(body.get("ram_gb", 16)),
    }
    extra = int(body.get("extra_budget", 0))
    catalogue = db.get_catalogue()
    bottleneck, best, recos = logic.upgrade_advice(current, extra, catalogue=catalogue)
    return jsonify({
        "bottleneck": bottleneck,
        "best": best,
        "options": recos,
    })


# ---------------------------------------------------------------------------
# Save / share / rate builds (SRS 4.7)
# ---------------------------------------------------------------------------
@app.post("/builds")
def save_build():
    body = request.get_json(force=True, silent=True) or {}
    name = logic.sanitize(body.get("name", "Untitled build"))
    share_code = body.get("share_code")
    total = int(body.get("total", 0))
    game_name = body.get("game")
    fps = body.get("fps")
    game_id = body.get("game_id")

    # Reconstruct {part: component} from the posted component list.
    build = {}
    for c in body.get("build", []):
        build[c["part"]] = c
    if not build or not share_code:
        return jsonify({"error": "Invalid build payload."}), 400

    build_id, created = db.save_build(
        share_code, name or "Untitled build", build, total, game_name,
        fps=fps, game_id=game_id,
    )
    return jsonify({"build_id": build_id, "share_code": share_code, "created": created})


@app.get("/builds")
def list_builds():
    return jsonify(db.get_builds())


@app.post("/builds/<int:build_id>/ratings")
def rate_build(build_id):
    body = request.get_json(force=True, silent=True) or {}
    try:
        score = int(body.get("score"))
    except (TypeError, ValueError):
        return jsonify({"error": "Score must be an integer 1-5."}), 400
    if not 1 <= score <= 5:
        return jsonify({"error": "Score must be between 1 and 5."}), 400
    db.add_rating(build_id, score, comment=logic.sanitize(body.get("comment", ""), 200))
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Admin (SRS 4.8 / 12) - authentication + component & rating management
# ---------------------------------------------------------------------------
@app.post("/admin/login")
def admin_login():
    body = request.get_json(force=True, silent=True) or {}
    if body.get("password") == ADMIN_PASSWORD:
        return jsonify({"token": ADMIN_TOKEN})
    return jsonify({"error": "Incorrect password."}), 401


@app.post("/admin/components")
@require_admin
def admin_add_component():
    body = request.get_json(force=True, silent=True) or {}
    ctype = body.get("type")
    name = logic.sanitize(body.get("name", ""), 40)
    if not ctype or not name:
        return jsonify({"error": "Type and name are required."}), 400
    try:
        price = int(body.get("price", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Price must be a number."}), 400
    if price <= 0:
        return jsonify({"error": "Price must be positive."}), 400

    existing = len(db.list_components())
    comp = {
        "id": f"custom-{existing}-{name[:6].replace(' ', '')}",
        "type": ctype, "name": name, "price": price,
        "tier": body.get("tier", "mid"), "score": int(body.get("score", 50)),
    }
    # Carry through any relevant spec fields the admin supplies.
    for f in ("socket", "tdp", "ram_type", "form_factor", "wattage", "supports"):
        if f in body:
            comp[f] = body[f]
    db.add_component(comp)
    return jsonify({"ok": True, "component": comp})


@app.post("/admin/import")
@require_admin
def admin_import():
    """Bulk-load components and/or games from a JSON payload (SRS 4.8).

    Body: {"components": [ {...}, ... ], "games": [ {...}, ... ]}
    Each component needs at least type/name/price; games need name/weight.
    """
    body = request.get_json(force=True, silent=True) or {}
    comps = body.get("components", []) or []
    games_in = body.get("games", []) or []
    added_c, added_g, errors = 0, 0, []

    existing = len(db.list_components())
    for i, c in enumerate(comps):
        ctype, name = c.get("type"), logic.sanitize(str(c.get("name", "")), 40)
        try:
            price = int(c.get("price", 0))
        except (TypeError, ValueError):
            price = 0
        if not ctype or not name or price <= 0:
            errors.append(f"component #{i + 1}: type, name and positive price required")
            continue
        comp = {
            "id": c.get("id") or f"import-{existing + added_c}-{name[:6].replace(' ', '')}",
            "type": ctype, "name": name, "price": price,
            "tier": c.get("tier", "mid"), "score": int(c.get("score", 50)),
        }
        for f in ("socket", "tdp", "ram_type", "form_factor", "wattage", "supports"):
            if f in c:
                comp[f] = c[f]
        db.add_component(comp)
        added_c += 1

    for i, g in enumerate(games_in):
        name = logic.sanitize(str(g.get("name", "")), 40)
        if not name:
            errors.append(f"game #{i + 1}: name required")
            continue
        try:
            weight = float(g.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        db.add_game({
            "id": g.get("id") or f"game-{name[:8].replace(' ', '').lower()}",
            "name": name, "weight": weight, "cpu_bound": bool(g.get("cpu_bound", False)),
        })
        added_g += 1

    return jsonify({"ok": True, "components_added": added_c,
                    "games_added": added_g, "errors": errors})


@app.post("/admin/games")
@require_admin
def admin_add_game():
    body = request.get_json(force=True, silent=True) or {}
    name = logic.sanitize(body.get("name", ""), 40)
    if not name:
        return jsonify({"error": "Game name is required."}), 400
    try:
        weight = float(body.get("weight", 1.0))
    except (TypeError, ValueError):
        return jsonify({"error": "Weight must be a number."}), 400
    game = {
        "id": body.get("id") or f"game-{name[:8].replace(' ', '').lower()}",
        "name": name,
        "weight": weight,
        "cpu_bound": bool(body.get("cpu_bound", False)),
    }
    db.add_game(game)
    return jsonify({"ok": True, "game": game})


@app.delete("/admin/builds/<int:build_id>/ratings")
@require_admin
def admin_remove_ratings(build_id):
    db.remove_ratings(build_id)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
