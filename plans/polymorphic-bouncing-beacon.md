# Final presentation scripts (role-wise, Hinglish)

## Context
The final project presentation is tomorrow. The team has 3 members:
- Krishna: Backend (Flask)
- Huzaifa: Frontend (Streamlit)
- Haasil: Database (SQLite)

The user wants a separate speaking script for each person, covering what that person should explain.

`buildadvisor/BuildAdvisor_Presentation_Scripts_Hinglish.html` already exists, but it was written for the 40% progress review. The new scripts are for the final project and are based on the actual code.

## Deliverable
New file: `src/imports/BuildAdvisor_Final_Presentation_Scripts.pdf`. It is built from HTML with headless chromium, uses Times New Roman, and is A4. The same scripts also go in the chat.

Each script has three parts:
- What the person speaks (Hinglish)
- Which file or screen to show
- 4–5 likely viva questions with short answers

### Structure
1. **Shared intro** (Huzaifa, about 45 sec): the problem, what the project does, the tech stack, and the three-tier architecture.
2. **Huzaifa – Frontend**
   - Explain `app.py` and its 4 screens: `render_build_advisor`, `render_upgrade_advisor`, `render_community`, `render_admin`.
   - Explain `ui.py`: the dark violet theme, `hero`, `chip` and status chips.
   - Explain `api.py`: it is a thin client, `_request` is the single HTTP point, and errors are handled with `_handle` and `BackendError`, shown as a red chip.
   - Live demo: generate a build, then save it.
3. **Krishna – Backend**
   - Explain the Flask routes in `backend.py`: `/generate-build`, `/upgrade`, `/builds`, ratings, `/admin/*`, and `require_admin` with the X-Admin-Token header.
   - Explain the core logic in `logic.py`:
     - Budget tier and allocation: GPU 32%, CPU 20%, MB 13%, RAM 10%, PSU 9%, Storage 8%, Case 8%.
     - `check_compatibility`: socket, RAM type, PSU wattage, form factor.
     - `_repair`: up to 8 tries.
     - `estimate_fps`, `price_build`, `upgrade_advice`.
   - Explain `ai.py`, the Gemini explanation with a fallback.
   - Explain `pricing.py`, the optional scraping that falls back to last-known prices.
   - Explain `config.py`, which reads business rules from environment variables.
   - Walk through the flow diagram.
4. **Haasil – Database**
   - Explain `db.py` and its 7 tables, and the E-R diagram with its relationships: 1:M, and M:N through BuildComponent and Benchmark.
   - Explain foreign keys with `PRAGMA foreign_keys=ON` and cascade delete.
   - Explain the main functions: `get_catalogue`, `save_build`, `get_builds` with average rating, `add_rating`.
   - Explain `bootstrap.py` and `catalogue.json` seeding, and bulk JSON import.
   - Show the DFD data stores D1–D7 and DB Browser.
5. **Shared conclusion** (Krishna): limitations, future scope, thank you.
6. **Tips**: the demo order and a backup plan if the internet fails (AI fallback and the simulate switches). Don't show the `.env` key on screen.

## Verification
- Render the PDF pages with pdftoppm and check the layout.
- Confirm that function and route names match the code.
