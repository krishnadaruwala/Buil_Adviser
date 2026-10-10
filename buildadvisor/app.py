"""
BuildAdvisor - AI-Powered PC Build Recommender for Gamers
Streamlit frontend (SRS Section 6.1).

This is a thin client: all business logic, data, and persistence live in the
Flask backend (backend.py) + SQLite (db.py). The frontend calls the backend
over HTTP via api.py, matching the client/server architecture in SRS §7.

Run the backend first:   python backend.py
Then run this frontend:  streamlit run app.py
"""

import streamlit as st

# `python app.py` runs Streamlit in bare mode, where st.stop() and session
# state don't work. Relaunch through `streamlit run` instead.
if __name__ == "__main__":
    from streamlit import runtime
    if not runtime.exists():
        import subprocess
        import sys
        sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", __file__, *sys.argv[1:]]))

import api
import ui

st.set_page_config(
    page_title="BuildAdvisor",
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="expanded",
)

ui.inject_css()

ss = st.session_state
ss.setdefault("admin_token", None)
ss.setdefault("last_result", None)


def _rupees(v):
    return f"₹{int(v):,}"


def _handle(fn, *a, **k):
    """Call an api.* function, surfacing BackendError as a Streamlit error."""
    try:
        return fn(*a, **k)
    except api.BackendError as e:
        st.error(str(e))
        st.stop()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🖥️ BuildAdvisor")
    st.caption("AI-Powered PC Build Recommender for Gamers")

    # Backend connectivity + live-capability indicators.
    try:
        h = api.health()
        ui.chips(
            ("Backend online", "ok"),
            ("Gemini live" if h.get("gemini_live") else "Gemini simulated",
             "accent" if h.get("gemini_live") else "neutral"),
            ("Pricing live" if h.get("scraping_live") else "Pricing simulated",
             "accent" if h.get("scraping_live") else "neutral"),
        )
        if not h.get("rules_configured", True):
            st.warning(
                "Business rules not fully configured. Missing: "
                + ", ".join(h.get("rules_missing", []))
                + ". Set these in your `.env` file.",
                icon="⚠️",
            )
        if h.get("catalogue_empty"):
            st.info("Component database is empty. Add components in the "
                    "**Admin** screen to start generating builds.", icon="📭")
    except api.BackendError:
        ui.chips(("Backend offline", "bad"))
        st.caption("Run `python backend.py` to connect.")

    page = st.radio(
        "Navigate",
        ["Build Advisor", "Upgrade Advisor", "Community", "Admin"],
        label_visibility="collapsed",
    )
    st.divider()
    st.markdown("**Simulate service state**")
    live_prices = st.toggle("Live pricing available", value=True,
                            help="Off = simulate a retailer outage (SRS 9.4 fallback).")
    ai_available = st.toggle("Gemini API available", value=True,
                             help="Off = simulate an AI outage (SRS 10 graceful fallback).")


# ===========================================================================
# 1. BUILD ADVISOR
# ===========================================================================
def render_build_advisor():
    ui.hero("Build Advisor",
            "Enter your budget and target game — get a complete, compatible, "
            "priced build with a plain-language explanation.")

    cfg = _handle(api.get_config)
    games = _handle(api.get_games)
    game_names = [g["name"] for g in (games or [])]

    if not game_names:
        st.info("No games in the database yet. Add games in the **Admin** screen "
                "before generating a build.")
        return

    resolutions = cfg.get("resolutions") or ["1080p"]
    min_budget = cfg.get("min_budget") or 30000
    default_budget = max(min_budget, min(90000, min_budget * 2))

    with st.form("build_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            budget = st.slider("Budget (₹)", min_value=int(min_budget),
                               max_value=max(int(min_budget) + 50000, 250000),
                               value=int(default_budget), step=5000)
        with c2:
            game_name = st.selectbox("Target game", game_names)
        with c3:
            resolution = st.selectbox("Resolution / FPS target", resolutions)
        submitted = st.form_submit_button("⚙️  Generate Build", use_container_width=True)

    if submitted:
        result = _handle(api.generate_build, budget, game_name, resolution,
                         live_prices, ai_available)
        if not result.get("buildable"):
            st.error(result.get("error", "No build could be generated."))
            ss.last_result = None
            return
        ss.last_result = result

    if ss.last_result is None:
        return

    r = ss.last_result
    for w in r.get("warnings", []):
        st.warning(w)

    # --- Headline metrics ---
    m1, m2, m3 = st.columns(3)
    m1.metric("List total", _rupees(r["list_total"]))
    m2.metric("Best live total", _rupees(r["live_total"]),
              delta=_rupees(r["live_total"] - r["list_total"]), delta_color="inverse")
    m3.metric(f"Est. FPS · {r['game']['name']} @ {r['resolution']}",
              f"~{r['fps']}" + (" *" if r["fps_approximate"] else ""))
    if r["fps_approximate"]:
        st.caption("\\* FPS is an approximate estimate from the nearest benchmark "
                   "combination (SRS 9.3).")

    st.divider()
    left, right = st.columns([3, 2])

    with left:
        st.subheader("Recommended build")
        if not r["live_prices"]:
            st.info("Live pricing unavailable — showing last-known prices with a note.")
        table = [{
            "Part": row["part"], "Component": row["name"],
            "Best price": _rupees(row["lowest"]), "Retailer": row["retailer"],
            "Fresh": "✅" if row["fresh"] else "🕒",
        } for row in r["price_rows"]]
        st.dataframe(table, use_container_width=True, hide_index=True)

        with st.expander("Per-retailer price breakdown"):
            for row in r["price_rows"]:
                if row["quotes"]:
                    quotes = "  ·  ".join(f"{k}: {_rupees(v)}" for k, v in row["quotes"].items())
                    st.write(f"**{row['name']}** — {quotes}")
                else:
                    st.write(f"**{row['name']}** — last-known {_rupees(row['lowest'])}")

    with right:
        st.subheader("Why this build")
        if r.get("explanation"):
            st.markdown(r["explanation"])
        else:
            st.warning("AI explanation is temporarily unavailable. "
                       "Your build is still complete and usable.")
            if st.button("🔄 Retry explanation"):
                st.rerun()

    st.divider()
    st.subheader("Save & share")
    sc1, sc2 = st.columns([3, 1])
    with sc1:
        name = st.text_input("Name this build", value="My gaming build", max_chars=60)
    with sc2:
        st.write("")
        st.write("")
        if st.button("💾 Save & get share link", use_container_width=True):
            res = _handle(api.save_build, r, name)
            st.success(f"Saved! Share link: `buildadvisor.app/b/{res['share_code']}`")


# ===========================================================================
# 2. UPGRADE ADVISOR
# ===========================================================================
def render_upgrade_advisor():
    ui.hero("Upgrade Advisor",
            "Already have a PC? Tell us your current parts and an extra budget — "
            "we'll find your biggest bottleneck and the smartest upgrade.")

    components = _handle(api.get_components)
    cpus = [c for c in components if c["type"] == "CPU"]
    gpus = [c for c in components if c["type"] == "GPU"]

    if not cpus or not gpus:
        st.info("Add at least one CPU and one GPU in the **Admin** screen before "
                "using the Upgrade Advisor.")
        return

    with st.form("upgrade_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            cur_cpu = st.selectbox("Current CPU", cpus, format_func=lambda c: c["name"])
        with c2:
            cur_gpu = st.selectbox("Current GPU", gpus, format_func=lambda c: c["name"])
        with c3:
            cur_ram = st.select_slider("Current RAM (GB)", [8, 16, 32, 64], value=16)
        extra = st.slider("Extra upgrade budget (₹)", 5000, 100000, 30000, step=2500)
        go = st.form_submit_button("🔍  Find best upgrade", use_container_width=True)

    if not go:
        return

    res = _handle(api.upgrade, cur_cpu.get("score", 0), cur_gpu.get("score", 0),
                  cur_ram, extra)
    st.info(f"**Biggest bottleneck: {res['bottleneck']}** — this is what's most "
            f"holding your system back for gaming.")

    best = res.get("best")
    if not best:
        st.warning("No worthwhile upgrade fits within that extra budget. "
                   "Consider raising it, or your current parts may already be strong.")
        return

    st.success(f"**Recommended upgrade:** {best['name']} — {_rupees(best['price'])}")
    st.caption("Most cost-effective option that improves your bottleneck within budget "
               "(SRS 4.5).")

    if len(res["options"]) > 1:
        with st.expander("Other options in your budget"):
            st.dataframe(
                [{"Upgrade": c["name"], "Price": _rupees(c["price"])} for c in res["options"]],
                use_container_width=True, hide_index=True,
            )


# ===========================================================================
# 3. COMMUNITY
# ===========================================================================
def render_community():
    ui.hero("Community Builds",
            "Saved and shared builds. Rate a build to help other gamers.")

    builds = _handle(api.list_builds)
    if not builds:
        st.info("No builds saved yet. Generate one in **Build Advisor** and save it.")
        return

    for b in builds:
        with st.container(border=True):
            top = st.columns([4, 2, 2])
            top[0].markdown(f"### {b['name']}")
            top[0].caption(f"Target: {b['game']}  ·  share id `{b['share_code']}`")
            top[1].metric("Build cost", _rupees(b["total"]))
            avg = sum(b["ratings"]) / len(b["ratings"]) if b["ratings"] else 0
            top[2].metric("Rating", f"{avg:.1f} ★" if b["ratings"] else "—",
                          help=f"{len(b['ratings'])} rating(s)")

            with st.expander("View components"):
                st.dataframe(
                    [{"Part": c["type"], "Component": c["name"], "Price": _rupees(c["price"])}
                     for c in b["components"]],
                    use_container_width=True, hide_index=True,
                )

            rc1, rc2 = st.columns([3, 1])
            score = rc1.slider("Your rating", 1, 5, 4, key=f"rate-{b['build_id']}")
            rc2.write("")
            rc2.write("")
            if rc2.button("Submit rating", key=f"btn-{b['build_id']}",
                          use_container_width=True):
                _handle(api.rate_build, b["build_id"], score)
                st.rerun()


# ===========================================================================
# 4. ADMIN
# ===========================================================================
def render_admin():
    ui.hero("Admin Dashboard",
            "Manage the component catalogue, games and community ratings.")

    if not ss.admin_token:
        lc, cc, rc = st.columns([1, 2, 1])
        with cc:
            with st.container(border=True):
                st.markdown("#### 🔒 Admin sign in")
                st.caption("Admin functions are protected by authentication (SRS 12).")
                with st.form("admin_login"):
                    pw = st.text_input("Admin password", type="password")
                    if st.form_submit_button("Sign in", use_container_width=True):
                        try:
                            res = api.admin_login(pw)
                            ss.admin_token = res["token"]
                            st.rerun()
                        except api.BackendError as e:
                            st.error(str(e))
                st.caption("Demo password: `admin123`")
        return

    top = st.columns([4, 1])
    with top[0]:
        ui.chips(("Signed in as Admin", "ok"))
    with top[1]:
        if st.button("Sign out", use_container_width=True):
            ss.admin_token = None
            st.rerun()
    st.divider()

    tab1, tab2, tab4, tab5, tab3 = st.tabs(
        ["Component database", "Add component", "Add game",
         "Bulk import (JSON)", "Ratings moderation"])

    with tab1:
        st.subheader("Current components")
        comps = _handle(api.get_components)
        if not comps:
            st.info("No components yet. Use **Add component** to populate the database.")
        else:
            games = _handle(api.get_games)
            mc = st.columns(4)
            mc[0].metric("Components", len(comps))
            mc[1].metric("CPUs", sum(1 for c in comps if c["type"] == "CPU"))
            mc[2].metric("GPUs", sum(1 for c in comps if c["type"] == "GPU"))
            mc[3].metric("Games", len(games))
            st.write("")
            st.dataframe(
                [{"Type": c["type"], "Name": c["name"], "Price": _rupees(c["price"]),
                  "Tier": c.get("tier", "-")} for c in comps],
                use_container_width=True, hide_index=True,
            )

    with tab2:
        st.subheader("Add a component (SRS 4.8 / TC08)")
        st.caption("Add compatibility specs so the generator can pair parts correctly "
                   "(e.g. CPU/Motherboard need a matching socket).")
        with st.form("add_comp"):
            r1c1, r1c2 = st.columns([1, 2])
            ctype = r1c1.selectbox("Type", ["CPU", "GPU", "Motherboard", "RAM",
                                            "Storage", "PSU", "Case"])
            name = r1c2.text_input("Name")
            r2c1, r2c2, r2c3 = st.columns(3)
            price = r2c1.number_input("Price (₹)", min_value=100, value=10000, step=100)
            tier = r2c2.selectbox("Tier", ["entry", "mid", "high"], index=1)
            score = r2c3.number_input("Performance score", min_value=0, value=50, step=5)
            specs_raw = st.text_input(
                "Specs (key=value, comma-separated)",
                help="e.g. socket=AM5, tdp=65   |   ram_type=DDR5   |   wattage=650   |   "
                     "form_factor=ATX   |   supports=ATX;mATX",
            )
            if st.form_submit_button("Add component", use_container_width=True):
                specs = {}
                for pair in specs_raw.split(","):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k == "supports":
                            specs[k] = [x.strip() for x in v.split(";") if x.strip()]
                        elif k in ("tdp", "wattage"):
                            try:
                                specs[k] = int(v)
                            except ValueError:
                                specs[k] = v
                        else:
                            specs[k] = v
                try:
                    res = api.admin_add_component(
                        ss.admin_token, ctype, name, int(price),
                        tier=tier, score=int(score), **specs)
                    st.success(f"Added {res['component']['name']}. "
                               "It will appear in future recommendations.")
                except api.BackendError as e:
                    st.error(str(e))

    with tab4:
        st.subheader("Add a game")
        st.caption("Games power FPS estimates. Higher weight = more demanding; "
                   "mark CPU-bound titles (e.g. strategy/simulation).")
        with st.form("add_game"):
            gc1, gc2 = st.columns([2, 1])
            gname = gc1.text_input("Game name")
            gweight = gc2.number_input("Demand weight", min_value=0.1, value=1.0, step=0.1,
                                       help="Relative GPU/CPU load; 1.0 is a typical AAA title.")
            gcpu = st.checkbox("CPU-bound title")
            if st.form_submit_button("Add game", use_container_width=True):
                try:
                    res = api.admin_add_game(ss.admin_token, gname, float(gweight), gcpu)
                    st.success(f"Added {res['game']['name']}.")
                except api.BackendError as e:
                    st.error(str(e))

    with tab5:
        st.subheader("Bulk import components & games")
        st.caption("Paste a JSON object with `components` and/or `games` arrays, or "
                   "upload a `.json` file. Fastest way to populate an empty database.")
        st.code(
            '{\n'
            '  "components": [\n'
            '    {"type": "CPU", "name": "Ryzen 5 7600", "price": 20500,\n'
            '     "tier": "mid", "score": 72, "socket": "AM5", "tdp": 65},\n'
            '    {"type": "Motherboard", "name": "B650M", "price": 12000,\n'
            '     "socket": "AM5", "ram_type": "DDR5", "form_factor": "mATX"},\n'
            '    {"type": "Case", "name": "NR200", "price": 6000,\n'
            '     "supports": ["ATX", "mATX"]}\n'
            '  ],\n'
            '  "games": [\n'
            '    {"name": "Cyberpunk 2077", "weight": 1.4, "cpu_bound": false}\n'
            '  ]\n'
            '}',
            language="json",
        )
        uploaded = st.file_uploader("Upload JSON file", type=["json"], key="import_file")
        pasted = st.text_area("...or paste JSON here", height=180, key="import_text")
        if st.button("Import"):
            import json as _json
            raw = None
            if uploaded is not None:
                raw = uploaded.getvalue().decode("utf-8")
            elif pasted.strip():
                raw = pasted
            if not raw:
                st.warning("Upload a file or paste JSON first.")
            else:
                try:
                    payload = _json.loads(raw)
                except ValueError as e:
                    st.error(f"Invalid JSON: {e}")
                    payload = None
                if payload is not None:
                    try:
                        res = api.admin_import(
                            ss.admin_token,
                            components=payload.get("components", []),
                            games=payload.get("games", []),
                        )
                        st.success(f"Imported {res['components_added']} component(s) "
                                   f"and {res['games_added']} game(s).")
                        for err in res.get("errors", []):
                            st.warning(err)
                    except api.BackendError as e:
                        st.error(str(e))

    with tab3:
        st.subheader("Moderate community ratings")
        builds = _handle(api.list_builds)
        rated = [b for b in builds if b["ratings"]]
        if not rated:
            st.info("No ratings submitted yet.")
        for b in rated:
            cols = st.columns([4, 2])
            cols[0].write(f"**{b['name']}** — {len(b['ratings'])} rating(s), "
                          f"avg {sum(b['ratings'])/len(b['ratings']):.1f} ★")
            if cols[1].button("Remove all ratings", key=f"mod-{b['build_id']}"):
                _handle(api.admin_remove_ratings, ss.admin_token, b["build_id"])
                st.rerun()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
if page == "Build Advisor":
    render_build_advisor()
elif page == "Upgrade Advisor":
    render_upgrade_advisor()
elif page == "Community":
    render_community()
elif page == "Admin":
    render_admin()

st.sidebar.divider()
st.sidebar.caption("BuildAdvisor v2.0 · Streamlit + Flask + SQLite")
