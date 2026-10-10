"""
BuildAdvisor - HTTP client used by the Streamlit frontend to talk to the Flask
backend (SRS 6.4 - client/server over HTTP). Centralises the base URL and
error handling so the UI code stays clean.
"""

import os

import requests

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
TIMEOUT = 15


class BackendError(Exception):
    """Raised when the backend is unreachable or returns an error."""


def _request(method, path, **kwargs):
    url = f"{BASE_URL}{path}"
    try:
        resp = requests.request(method, url, timeout=TIMEOUT, **kwargs)
    except requests.exceptions.RequestException:
        raise BackendError(
            f"Cannot reach the backend at {BASE_URL}. "
            "Start it with `python backend.py` and try again."
        )
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("error", resp.text)
        except ValueError:
            msg = resp.text
        raise BackendError(msg)
    return resp.json()


# --- Reference data -------------------------------------------------------
def health():
    return _request("GET", "/health")


def get_config():
    return _request("GET", "/config")


def get_games():
    return _request("GET", "/games")


def get_components():
    return _request("GET", "/components")


# --- Core flows -----------------------------------------------------------
def generate_build(budget, game, resolution, live_prices, ai_available):
    return _request("POST", "/generate-build", json={
        "budget": budget, "game": game, "resolution": resolution,
        "live_prices": live_prices, "ai_available": ai_available,
    })


def upgrade(cpu_score, gpu_score, ram_gb, extra_budget):
    return _request("POST", "/upgrade", json={
        "cpu_score": cpu_score, "gpu_score": gpu_score,
        "ram_gb": ram_gb, "extra_budget": extra_budget,
    })


def save_build(result, name):
    return _request("POST", "/builds", json={
        "name": name,
        "share_code": result["share_code"],
        "total": result["live_total"],
        "game": result["game"]["name"],
        "game_id": result["game"]["id"],
        "fps": result["fps"],
        "build": result["build"],
    })


def list_builds():
    return _request("GET", "/builds")


def rate_build(build_id, score):
    return _request("POST", f"/builds/{build_id}/ratings", json={"score": score})


# --- Admin ----------------------------------------------------------------
def admin_login(password):
    return _request("POST", "/admin/login", json={"password": password})


def admin_add_component(token, ctype, name, price, **specs):
    payload = {"type": ctype, "name": name, "price": price, **specs}
    return _request("POST", "/admin/components", json=payload,
                    headers={"X-Admin-Token": token})


def admin_import(token, components=None, games=None):
    return _request("POST", "/admin/import",
                    json={"components": components or [], "games": games or []},
                    headers={"X-Admin-Token": token})


def admin_add_game(token, name, weight, cpu_bound=False):
    return _request("POST", "/admin/games",
                    json={"name": name, "weight": weight, "cpu_bound": cpu_bound},
                    headers={"X-Admin-Token": token})


def admin_remove_ratings(token, build_id):
    return _request("DELETE", f"/admin/builds/{build_id}/ratings",
                    headers={"X-Admin-Token": token})
