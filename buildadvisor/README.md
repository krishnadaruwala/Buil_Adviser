# BuildAdvisor — AI-Powered PC Build Recommender for Gamers

Full-stack prototype implementing the BuildAdvisor SRS (v2.0):
**Streamlit frontend → Flask backend → SQLite database** (SRS §7).

## Architecture

```
 Streamlit UI (app.py)
        │  HTTP (api.py)
        ▼
 Flask backend (backend.py)  ──►  business logic (logic.py)
        │
        ▼
 SQLite database (db.py, buildadvisor.db)
```

This mirrors the SRS client/server model and sequence diagram (§3.11): the
frontend POSTs to `/generate-build`, the backend queries the component database,
checks compatibility, prices the build, generates an explanation, and returns
the result.

## Run

Install dependencies:

```bash
pip install -r requirements.txt
```

**Option A — one command (macOS/Linux):**

```bash
./run.sh
```

**Option B — two terminals:**

```bash
# Terminal 1 — backend (creates an EMPTY buildadvisor.db on first run)
python backend.py            # http://localhost:8000

# Terminal 2 — frontend
streamlit run app.py         # http://localhost:8501
```

The sidebar shows a 🟢/🔴 indicator for backend connectivity, plus notices when
business rules aren't configured or the component database is still empty.

## Configuration (`.env`)

There is **no seed dataset**. The database starts empty and the business rules
live in environment variables (not in source), so nothing is hardcoded. Copy the
template and fill it in:

```bash
cp .env.example .env         # then edit values
```

Key variables (see `.env.example` for the full list and formats):

| Variable | Purpose |
|----------|---------|
| `BUILDADVISOR_MIN_BUDGET` | minimum budget (₹) for a working build |
| `BUILDADVISOR_TIERS` | budget tiers, e.g. `entry:0-55000,mid:55000-110000,high:110000-10000000` |
| `BUILDADVISOR_RESOLUTIONS` | resolution difficulty multipliers, e.g. `1080p:1.0,1440p:1.5,4K:2.6` |
| `BUILDADVISOR_RETAILERS` | retailer names for simulated price quotes |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | optional live AI explanation |
| `ENABLE_SCRAPING` / `PRICE_CACHE_TTL` | optional live price scraping |

`.env` is git-ignored — never commit it or your API key. Only `.env.example` is
committed.

## Database (SRS §8)

`db.py` creates the schema from the ER diagram — **User, Component, Build,
BuildComponent, Game, Benchmark, Rating** — as **empty tables** on first run.
There is no seeding: components and games are added at runtime through the
**Admin** screen (or the `/admin/components` and `/admin/games` endpoints), so
the database is the single source of truth for catalogue data. Component spec
fields (socket, TDP, RAM type, wattage, form factor) are stored as JSON in
`Component.specs`, matching the data dictionary and keeping the schema portable
to MySQL (SRS §7.4).

Start over by deleting `buildadvisor.db` and restarting the backend (you'll get
a fresh empty database).

### Populating the database

Three ways to add your catalogue to an empty database:

1. **Admin screen** — sign in (`admin123`) and use **Add component** / **Add
   game** for one-at-a-time entry.
2. **Bulk import in Admin** — the **Bulk import (JSON)** tab accepts a pasted or
   uploaded JSON object with `components` and/or `games` arrays.
3. **`bootstrap.py` CLI** — load a JSON file directly into SQLite, no running
   backend needed:

   ```bash
   python bootstrap.py catalogue.json
   ```

   JSON shape (components need `type`/`name`/`price`; games need `name`/`weight`;
   add spec fields like `socket`, `ram_type`, `wattage`, `form_factor`,
   `supports` so the generator can pair parts):

   ```json
   {
     "components": [
       {"type": "CPU", "name": "Ryzen 5 7600", "price": 20500,
        "tier": "mid", "score": 72, "socket": "AM5", "tdp": 65},
       {"type": "Case", "name": "NR200", "price": 6000, "supports": ["ATX", "mATX"]}
     ],
     "games": [
       {"name": "Cyberpunk 2077", "weight": 1.4, "cpu_bound": false}
     ]
   }
   ```

## REST API

| Method | Endpoint | SRS |
|--------|----------|-----|
| GET  | `/health`, `/config`, `/games`, `/components` | reference data |
| POST | `/generate-build` | 4.1–4.4, 4.6 |
| POST | `/upgrade` | 4.5 |
| POST | `/builds`, GET `/builds` | 4.7 (save/share) |
| POST | `/builds/<id>/ratings` | 4.7 (rate) |
| POST | `/admin/login` | 12 (auth) |
| POST | `/admin/components`, `/admin/games` | 4.8 (add component/game) |
| POST | `/admin/import` | 4.8 (bulk import JSON) |
| DELETE | `/admin/builds/<id>/ratings` | 4.8 (moderate) |

Admin endpoints require the `X-Admin-Token` header issued by `/admin/login`
(demo password `admin123`).

## Screens

- **Build Advisor** — budget + game/resolution → compatible, priced build, FPS estimate, AI explanation, save & share link.
- **Upgrade Advisor** — current parts + extra budget → bottleneck + best upgrade.
- **Community** — saved builds and ratings (persisted in SQLite).
- **Admin** — auth-gated component add, game add, and ratings moderation. Use
  this first on a fresh install to populate the empty database.

Sidebar toggles simulate **pricing** and **Gemini** outages to demonstrate the
graceful fallbacks required by SRS §9.4 and §10.

## Files

| File | Role |
|------|------|
| `app.py` | Streamlit frontend (thin HTTP client) |
| `api.py` | HTTP client for the backend |
| `backend.py` | Flask REST API |
| `db.py` | SQLite schema + queries (empty tables, no seeding) |
| `logic.py` | build generation, compatibility, FPS, pricing, upgrade, explanation |
| `config.py` | business rules (min budget, tiers, resolutions, retailers) loaded from `.env` |
| `bootstrap.py` | CLI to bulk-load components & games from a JSON file |

## Live integrations (Gemini + price scraping)

Both live integrations are optional and off by default, so the app runs with no
keys or network. Each degrades gracefully to a simulated result (SRS §10 / §9.4).

### Gemini API (SRS 4.6 / 7.5) — `ai.py`

Set an API key from [Google AI Studio](https://aistudio.google.com/apikey):

```bash
export GEMINI_API_KEY="your-key-here"
export GEMINI_MODEL="gemini-2.5-flash"   # optional, this is the default
python backend.py
```

When configured, `/generate-build` calls the real Gemini API for the build
explanation. If the key is missing or the call fails/times out, it falls back to
a locally generated explanation.

### Live retailer price scraping (SRS 4.4 / 7.5) — `pricing.py`

```bash
export ENABLE_SCRAPING=1
export PRICE_CACHE_TTL=3600   # optional cache TTL in seconds (SRS 5.1)
python backend.py
```

When enabled, each component price is scraped from retailer search pages
(`requests` + BeautifulSoup) and cached. If scraping is disabled or every
retailer fails, prices fall back to a deterministic estimate; a simulated outage
(sidebar toggle) shows the last-known price with a timestamp.

> Note (SRS §13): retailer page structures change, so the CSS selectors in
> `pricing.py` are best-effort and may need occasional updates.

The sidebar shows whether **Gemini** and **Pricing** are running live or
simulated, based on the backend's `/health` response.
