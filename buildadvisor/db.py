"""
BuildAdvisor - SQLite data layer (SRS Section 7.4 & 8).

Implements the schema from the ER diagram (§8.1): User, Component, Build,
BuildComponent, Game, Benchmark, Rating. Component-specific spec fields
(socket, tdp, ram_type, wattage, form_factor, supports, score) are stored as a
JSON blob in Component.specs, matching the `specs TEXT` column in the data
dictionary while keeping the schema portable to MySQL (SRS 7.4).

On first run the database file and its tables are created empty. There is no
seed dataset - components and games are added at runtime (e.g. via the Admin
screen or the /admin/components API), so the database is the single source of
truth for catalogue data.
"""

import json
import os
import sqlite3

DB_PATH = os.environ.get("BUILDADVISOR_DB", os.path.join(os.path.dirname(__file__), "buildadvisor.db"))

# Columns that live in the flat component dict but are stored inside specs JSON.
_SPEC_FIELDS = ("socket", "tdp", "ram_type", "form_factor", "wattage", "supports", "score")


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# Schema (SRS 8.3 - database tables)
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS User (
    user_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    email    TEXT,
    role     TEXT NOT NULL DEFAULT 'Gamer'
);

CREATE TABLE IF NOT EXISTS Component (
    component_id TEXT PRIMARY KEY,
    type         TEXT NOT NULL,
    name         TEXT NOT NULL,
    price        INTEGER NOT NULL,
    tier         TEXT,
    specs        TEXT              -- JSON: socket, tdp, ram_type, ...
);
CREATE INDEX IF NOT EXISTS idx_component_type ON Component(type);

CREATE TABLE IF NOT EXISTS Game (
    game_id    TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    weight     REAL NOT NULL,
    cpu_bound  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS Build (
    build_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    share_code  TEXT UNIQUE NOT NULL,
    user_id     INTEGER,
    name        TEXT,
    game        TEXT,
    total_price INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES User(user_id)
);

CREATE TABLE IF NOT EXISTS BuildComponent (
    build_id     INTEGER NOT NULL,
    component_id TEXT NOT NULL,
    PRIMARY KEY (build_id, component_id),
    FOREIGN KEY (build_id) REFERENCES Build(build_id) ON DELETE CASCADE,
    FOREIGN KEY (component_id) REFERENCES Component(component_id)
);

CREATE TABLE IF NOT EXISTS Benchmark (
    build_id      INTEGER NOT NULL,
    game_id       TEXT NOT NULL,
    estimated_fps INTEGER NOT NULL,
    PRIMARY KEY (build_id, game_id),
    FOREIGN KEY (build_id) REFERENCES Build(build_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Rating (
    rating_id INTEGER PRIMARY KEY AUTOINCREMENT,
    build_id  INTEGER NOT NULL,
    user_id   INTEGER,
    score     INTEGER NOT NULL,
    comment   TEXT,
    FOREIGN KEY (build_id) REFERENCES Build(build_id) ON DELETE CASCADE
);
"""


def init_db():
    """Create the database file and empty tables if they do not exist."""
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def is_empty() -> bool:
    """True when no components have been added yet (fresh database)."""
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM Component").fetchone()[0]
    conn.close()
    return n == 0


def add_game(game: dict):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO Game (game_id, name, weight, cpu_bound) VALUES (?,?,?,?)",
        (game["id"], game["name"], game["weight"], int(game.get("cpu_bound", 0))),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Component <-> row helpers
# ---------------------------------------------------------------------------
def _insert_component(conn, c):
    specs = {k: c[k] for k in _SPEC_FIELDS if k in c}
    conn.execute(
        "INSERT OR REPLACE INTO Component (component_id, type, name, price, tier, specs) "
        "VALUES (?,?,?,?,?,?)",
        (c["id"], c["type"], c["name"], int(c["price"]), c.get("tier"), json.dumps(specs)),
    )


def _row_to_component(row):
    comp = {
        "id": row["component_id"], "type": row["type"], "name": row["name"],
        "price": row["price"], "tier": row["tier"],
    }
    if row["specs"]:
        comp.update(json.loads(row["specs"]))
    return comp


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------
def get_catalogue():
    """Return the live catalogue grouped by type (same shape as data.CATALOGUE)."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM Component ORDER BY type, price").fetchall()
    conn.close()
    cat = {}
    for r in rows:
        cat.setdefault(r["type"], []).append(_row_to_component(r))
    return cat


def list_components():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM Component ORDER BY type, price").fetchall()
    conn.close()
    return [_row_to_component(r) for r in rows]


def get_games():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM Game ORDER BY name").fetchall()
    conn.close()
    return [{"id": r["game_id"], "name": r["name"], "weight": r["weight"],
             "cpu_bound": bool(r["cpu_bound"])} for r in rows]


# ---------------------------------------------------------------------------
# Write APIs
# ---------------------------------------------------------------------------
def add_component(comp: dict):
    conn = get_conn()
    _insert_component(conn, comp)
    conn.commit()
    conn.close()


def save_build(share_code, name, build, total, game_name, fps=None, game_id=None, user_id=None):
    """Persist a Build + its BuildComponent rows (+ Benchmark if fps given)."""
    conn = get_conn()
    existing = conn.execute(
        "SELECT build_id FROM Build WHERE share_code = ?", (share_code,)
    ).fetchone()
    if existing:
        conn.close()
        return existing["build_id"], False

    from datetime import datetime
    cur = conn.execute(
        "INSERT INTO Build (share_code, user_id, name, game, total_price, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (share_code, user_id, name, game_name, int(total),
         datetime.utcnow().isoformat(timespec="seconds")),
    )
    build_id = cur.lastrowid
    conn.executemany(
        "INSERT OR IGNORE INTO BuildComponent (build_id, component_id) VALUES (?,?)",
        [(build_id, c["id"]) for c in build.values()],
    )
    if fps is not None and game_id is not None:
        conn.execute(
            "INSERT OR REPLACE INTO Benchmark (build_id, game_id, estimated_fps) VALUES (?,?,?)",
            (build_id, game_id, int(fps)),
        )
    conn.commit()
    conn.close()
    return build_id, True


def get_builds():
    """Return saved builds with their components and ratings."""
    conn = get_conn()
    builds = conn.execute("SELECT * FROM Build ORDER BY created_at DESC").fetchall()
    result = []
    for b in builds:
        comp_rows = conn.execute(
            "SELECT c.* FROM Component c "
            "JOIN BuildComponent bc ON bc.component_id = c.component_id "
            "WHERE bc.build_id = ?", (b["build_id"],)
        ).fetchall()
        ratings = conn.execute(
            "SELECT score FROM Rating WHERE build_id = ?", (b["build_id"],)
        ).fetchall()
        result.append({
            "build_id": b["build_id"],
            "share_code": b["share_code"],
            "name": b["name"],
            "game": b["game"],
            "total": b["total_price"],
            "created_at": b["created_at"],
            "components": [_row_to_component(r) for r in comp_rows],
            "ratings": [r["score"] for r in ratings],
        })
    conn.close()
    return result


def add_rating(build_id, score, user_id=None, comment=None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO Rating (build_id, user_id, score, comment) VALUES (?,?,?,?)",
        (build_id, user_id, int(score), comment),
    )
    conn.commit()
    conn.close()


def remove_ratings(build_id):
    conn = get_conn()
    conn.execute("DELETE FROM Rating WHERE build_id = ?", (build_id,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Initialised {DB_PATH}")
    print(f"Components: {len(list_components())}, Games: {len(get_games())}")
