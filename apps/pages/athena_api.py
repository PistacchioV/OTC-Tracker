"""
athena_api.py
=============

Client for the Brazil Athena Trade Data REST API ``getTrades`` endpoint.
One product per call — NDF, Commodities, FXO and Swaps respondem no PROD.

Endpoint (PROD)::

    https://athena-app.jpmchase.net/FXCASH/brazil-trade-data-api/api/v1/getTrades?product=NDF&date=20260728

Authentication is ADFS / IDAnywhere (Kerberos single sign-on); the current
Windows identity is used, so no credentials are prompted. The SSO handshake
(browser User-Agent + ADFS form_post replay) mirrors di_and_sofr_live_curves.py.

Off a Windows/JPMC host neither ``requests_negotiate_sspi`` nor the network
route exist — ``is_available()`` lets callers (the in-app scheduler) skip
politely instead of crashing at import time.

Requirements::

    pip install requests requests-negotiate-sspi   # the latter is Windows-only
"""

from __future__ import annotations

import os
from html.parser import HTMLParser
from typing import Optional

try:
    import requests
except ImportError:  # pragma: no cover - local dev venv without requests
    requests = None

try:
    from requests_negotiate_sspi import HttpNegotiateAuth
except ImportError:  # pragma: no cover - only fails outside a Windows/JPMC host
    HttpNegotiateAuth = None


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

BASE_URL = "https://athena-app.jpmchase.net/FXCASH/brazil-trade-data-api"
TRADES_ENDPOINT = "/api/v1/getTrades"

# Canonical key → value of the ``product`` query-string parameter.
PRODUCTS = {
    "NDF": "NDF",
    "FXO": "FXO",
    "COMMODITIES": "Commodities",
    "SWAPS": "Swaps",
}
# All four products answer on the PROD endpoint.
FUNCTIONAL_PRODUCTS = ("NDF", "FXO", "COMMODITIES", "SWAPS")

# ADFS only issues the Kerberos 'Negotiate' challenge for User-Agents on its
# WIASupportedUserAgents allow-list. The default python-requests UA is not on it,
# so ADFS would serve an HTML login page (causing a JSON decode error). A Windows
# browser UA (Trident token) makes ADFS negotiate Kerberos silently.
WIA_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Trident/7.0; rv:11.0) like Gecko"
)

REQUEST_TIMEOUT = 30


def is_available():
    """True when the HTTP stack needed to call the API is importable."""
    return requests is not None


# --------------------------------------------------------------------------- #
# API client
# --------------------------------------------------------------------------- #

class _AutoPostFormParser(HTMLParser):
    """Extract the action URL and hidden fields of an ADFS auto-submit form."""

    def __init__(self):
        super().__init__()
        self.action = None
        self.method = "post"
        self.fields = {}
        self._in_form = False

    def handle_starttag(self, tag, attrs):
        attr = {k: (v or "") for k, v in attrs}
        if tag == "form":
            self._in_form = True
            self.action = attr.get("action")
            self.method = (attr.get("method") or "post").lower()
        elif tag == "input" and self._in_form:
            name = attr.get("name")
            if name:
                self.fields[name] = attr.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self._in_form = False


def build_session():
    """Create a requests session that uses Kerberos SSO (ADFS / IDAnywhere)."""
    if requests is None:
        raise RuntimeError(
            "The 'requests' package is not installed; the Athena API client is "
            "unavailable. Install it with 'pip install requests'."
        )
    session = requests.Session()
    # athena-app-uat.jpmchase.net is an INTERNAL host: the corporate proxy set in
    # the environment refuses it (WinError 10061 "Unable to connect to proxy")
    # while the browser goes direct. Ignore proxy/env settings entirely.
    session.trust_env = False
    # If TLS verification fails against the internal JPM CA, point this env var
    # at the corporate CA bundle (.pem) — certifi does not ship internal roots.
    ca_bundle = os.getenv("ATHENA_CA_BUNDLE")
    if ca_bundle:
        session.verify = ca_bundle
    if HttpNegotiateAuth is not None:
        session.auth = HttpNegotiateAuth()
    # A Windows browser UA is required so ADFS negotiates Kerberos instead of
    # returning an HTML Forms-login page.
    session.headers.update({"User-Agent": WIA_USER_AGENT})
    return session


def get_json(session, path: str, params: Optional[dict] = None):
    """GET an Athena endpoint via Kerberos SSO, replaying ADFS form_post hops."""
    resp = session.get(BASE_URL + path, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    # After SSO, ADFS returns auto-submitting form_post pages. Replay them
    # until the real JSON payload is returned (a browser does this in JS).
    for _ in range(6):
        if "html" not in resp.headers.get("Content-Type", "").lower():
            break
        parser = _AutoPostFormParser()
        parser.feed(resp.text)
        if not parser.action or parser.method != "post":
            break
        resp = session.post(parser.action, data=parser.fields, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

    return resp.json()


def fetch_trades(session, product: str, date: str):
    """Call getTrades for a product/date and return the parsed JSON payload."""
    return get_json(session, TRADES_ENDPOINT, {"product": product, "date": date})


def fetch_product_trades(product_key: str, date: str, session=None):
    """getTrades for a canonical product key ('NDF', 'FXO', 'COMMODITIES',
    'SWAPS') on a YYYYMMDD date. Creates a SSO session when none is given."""
    key = str(product_key or "").strip().upper()
    if key not in PRODUCTS:
        raise ValueError("Unknown Athena product: {!r}".format(product_key))
    if key not in FUNCTIONAL_PRODUCTS:
        raise NotImplementedError(
            "The Athena getTrades API is not functional for {} yet.".format(PRODUCTS[key])
        )
    return fetch_trades(session or build_session(), PRODUCTS[key], date)


def fetch_ndf_trades(date: str, session=None):
    """NDF trades for a YYYYMMDD date (mapping logic to be defined later)."""
    return fetch_product_trades("NDF", date, session=session)


def fetch_fxo_trades(date: str, session=None):
    """FXO trades for a YYYYMMDD date — feeds the New Deals Opt-FXO page."""
    return fetch_product_trades("FXO", date, session=session)


def fetch_commodities_trades(date: str, session=None):  # pragma: no cover
    """Placeholder — the Commodities product is not functional on the API yet."""
    return fetch_product_trades("COMMODITIES", date, session=session)


def fetch_swaps_trades(date: str, session=None):  # pragma: no cover
    """Placeholder — the Swaps product is not functional on the API yet."""
    return fetch_product_trades("SWAPS", date, session=session)


def extract_records(payload):
    """The trade list out of a getTrades payload. Accepts a bare list or a
    wrapper object ({'trades': [...]}, {'data': [...]}, …)."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("trades", "data", "results", "items", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        # Single-trade object → treat as a one-item list.
        if payload:
            return [payload]
    return []
