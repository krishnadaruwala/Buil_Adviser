"""
BuildAdvisor UI polish helpers.

Ye module sirf *presentation* ke liye hai — koi business logic yaha nahi.
app.py ke top par ek baar `ui.inject_css()` call karo, aur jaha chahiye
wahi status chips / hero use kar lo.

Design intent:
  * dark "gamer" canvas + violet/cyan accent (theme .streamlit/config.toml se aata hai)
  * cards ko softer border + hover lift
  * st.metric ko card jaisa look
  * colored HTML status chips (live/simulated/offline)
"""

import streamlit as st

# Accent palette — config.toml ke saath consistent rakho.
ACCENT = "#7c5cff"
ACCENT_2 = "#22d3ee"
OK = "#22c55e"
WARN = "#f59e0b"
BAD = "#ef4444"
MUTED = "#8b93a7"


def inject_css() -> None:
    """Custom CSS ek baar inject karo (app ke top par)."""
    st.markdown(
        f"""
        <style>
          /* ---- typography + width ---- */
          .block-container {{ padding-top: 2.2rem; max-width: 1200px; }}
          h1, h2, h3 {{ letter-spacing: -0.01em; font-weight: 700; }}

          /* ---- metric ko card look ---- */
          div[data-testid="stMetric"] {{
            background: linear-gradient(180deg, #191f2b 0%, #141924 100%);
            border: 1px solid #262c3a;
            border-radius: 14px;
            padding: 16px 18px;
            box-shadow: 0 1px 0 rgba(255,255,255,0.03) inset;
          }}
          div[data-testid="stMetricLabel"] p {{
            color: {MUTED}; font-size: 0.8rem; text-transform: uppercase;
            letter-spacing: 0.06em;
          }}
          div[data-testid="stMetricValue"] {{ font-weight: 700; }}

          /* ---- bordered containers (cards) ---- */
          div[data-testid="stVerticalBlockBorderWrapper"] {{
            border-radius: 16px !important;
            border-color: #262c3a !important;
            transition: border-color .18s ease, transform .18s ease;
          }}
          div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
            border-color: {ACCENT} !important;
            transform: translateY(-2px);
          }}

          /* ---- buttons ---- */
          div.stButton > button, div.stFormSubmitButton > button {{
            border-radius: 10px;
            font-weight: 600;
            border: 1px solid #2b3242;
            transition: transform .12s ease, box-shadow .12s ease;
          }}
          div.stButton > button:hover, div.stFormSubmitButton > button:hover {{
            transform: translateY(-1px);
            box-shadow: 0 6px 18px rgba(124,92,255,0.25);
          }}

          /* ---- inputs / tabs ---- */
          div[data-baseweb="tab-list"] {{ gap: 4px; }}
          button[data-baseweb="tab"] {{ border-radius: 10px 10px 0 0; }}
          div[data-testid="stForm"] {{
            border: 1px solid #262c3a; border-radius: 16px; padding: 8px 4px;
          }}

          /* ---- dataframe polish ---- */
          div[data-testid="stDataFrame"] {{ border-radius: 12px; overflow: hidden; }}

          /* ---- status chips ---- */
          .chip {{
            display: inline-flex; align-items: center; gap: 6px;
            padding: 3px 10px; border-radius: 999px;
            font-size: 0.78rem; font-weight: 600; line-height: 1.6;
            border: 1px solid transparent;
          }}
          .chip .dot {{ width: 7px; height: 7px; border-radius: 50%; }}

          /* ---- hero ---- */
          .ba-hero {{
            background: radial-gradient(120% 140% at 0% 0%, rgba(124,92,255,0.18), transparent 55%),
                        radial-gradient(120% 140% at 100% 0%, rgba(34,211,238,0.14), transparent 55%),
                        #141924;
            border: 1px solid #262c3a; border-radius: 18px;
            padding: 26px 28px; margin-bottom: 18px;
          }}
          .ba-hero h1 {{ margin: 0 0 6px 0; font-size: 1.9rem; }}
          .ba-hero p  {{ margin: 0; color: {MUTED}; font-size: 0.98rem; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def chip(label: str, status: str = "neutral") -> str:
    """Return an HTML status chip. status: ok | warn | bad | accent | neutral."""
    palette = {
        "ok": (OK, "rgba(34,197,94,0.12)"),
        "warn": (WARN, "rgba(245,158,11,0.12)"),
        "bad": (BAD, "rgba(239,68,68,0.12)"),
        "accent": (ACCENT_2, "rgba(34,211,238,0.12)"),
        "neutral": (MUTED, "rgba(139,147,167,0.12)"),
    }
    color, bg = palette.get(status, palette["neutral"])
    return (
        f'<span class="chip" style="color:{color};background:{bg};'
        f'border-color:{color}33;">'
        f'<span class="dot" style="background:{color}"></span>{label}</span>'
    )


def chips(*items) -> None:
    """Render multiple chips inline. Each item: (label, status)."""
    html = " ".join(chip(lbl, st_) for lbl, st_ in items)
    st.markdown(html, unsafe_allow_html=True)


def hero(title: str, subtitle: str) -> None:
    """Gradient hero header — headers se zyada polished lagta hai."""
    st.markdown(
        f'<div class="ba-hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )
