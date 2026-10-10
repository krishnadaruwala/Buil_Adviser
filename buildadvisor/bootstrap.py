"""
BuildAdvisor - bulk-load components & games into the SQLite database.

Since there is no seed dataset, this CLI is the quickest way to populate a fresh
database directly (no running backend required). It reads the same JSON shape as
the Admin "Bulk import" screen:

    {
      "components": [
        {"type": "CPU", "name": "Ryzen 5 7600", "price": 20500,
         "tier": "mid", "score": 72, "socket": "AM5", "tdp": 65},
        ...
      ],
      "games": [
        {"name": "Cyberpunk 2077", "weight": 1.4, "cpu_bound": false}
      ]
    }

Usage:
    python bootstrap.py catalogue.json
    BUILDADVISOR_DB=/path/to/buildadvisor.db python bootstrap.py catalogue.json
"""

import json
import sys

import db

_SPEC_FIELDS = ("socket", "tdp", "ram_type", "form_factor", "wattage", "supports")


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def import_payload(payload: dict):
    db.init_db()
    existing = len(db.list_components())
    added_c, added_g, errors = 0, 0, []

    for i, c in enumerate(payload.get("components", []) or []):
        ctype, name = c.get("type"), str(c.get("name", "")).strip()
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
        for f in _SPEC_FIELDS:
            if f in c:
                comp[f] = c[f]
        db.add_component(comp)
        added_c += 1

    for i, g in enumerate(payload.get("games", []) or []):
        name = str(g.get("name", "")).strip()
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

    return added_c, added_g, errors


def main():
    if len(sys.argv) != 2:
        print("Usage: python bootstrap.py <catalogue.json>")
        raise SystemExit(2)

    try:
        payload = _load(sys.argv[1])
    except FileNotFoundError:
        print(f"File not found: {sys.argv[1]}")
        raise SystemExit(1)
    except ValueError as e:
        print(f"Invalid JSON: {e}")
        raise SystemExit(1)

    added_c, added_g, errors = import_payload(payload)
    print(f"Imported {added_c} component(s) and {added_g} game(s) into {db.DB_PATH}")
    for err in errors:
        print(f"  ! {err}")
    print(f"Totals now — components: {len(db.list_components())}, games: {len(db.get_games())}")


if __name__ == "__main__":
    main()
