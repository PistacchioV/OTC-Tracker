"""
athena_api.py
=============

Client for the Brazil Athena Trade Data REST API ``getTrades`` endpoint.
One product per call — NDF, Commodities, FXO and Swaps respondem no PROD.

Endpoint (PROD)::

    https://athena-app.jpmchase.net/FXCASH/brazil-trade-data-api/api/v1/getTrades?product=NDF&date=20260728

O endereço não é mais constante: ele é **cadastro**, na tela /mapping › API
Links, uma linha por uso (New Deals e Unwinds), com ``YYYYMMDD`` marcando onde
entra a data de referência (ver `registered_url`). O ``BASE_URL``/
``TRADES_ENDPOINT`` abaixo continuam sendo o fallback do New Deals — e o seed do
cadastro é exatamente eles, então nada muda até alguém editar a linha.

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

import json
import os
import re
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
# Link da API — cadastro (/mapping › API Links), não constante
# --------------------------------------------------------------------------- #
# Uma linha por USO. Hoje há dois: 'New Deals' (o getTrades que alimenta as
# páginas de New Deals) e 'Unwinds' (ainda sem consumidor no código — a linha
# nasce VAZIA porque inventar um endereço aqui faria a rotina chamar um endpoint
# que ninguém conferiu).
#
# Na URL, `YYYYMMDD` marca onde entra a data de referência. Não é o único jeito
# de a data chegar: `product` e `date` do query string são SEMPRE reescritos com
# o que o código pediu, porque quem sabe qual produto está sendo puxado é a
# rotina, não o cadastro — um `product=NDF` esquecido na linha traria trades de
# NDF para a página de FXO, em silêncio. O placeholder existe para o caso de a
# data estar no CAMINHO (…/trades/20260728) em vez do query string.
#
# Este módulo lê o JSON direto (mesmo padrão de `_ndf_pdf_set` em otc_emails.py):
# importar `routes` daqui seria circular. Arquivo ausente/ilegível → fallback nas
# constantes acima, que são também o seed da linha do New Deals.

_MAPPINGS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "data", "mappings")
)
API_LINKS_FILE = os.path.join(_MAPPINGS_DIR, "api-links.json")

USE_NEW_DEALS = "New Deals"
USE_UNWINDS = "Unwinds"

# URL do New Deals que estava no código — seed do cadastro e fallback.
DEFAULT_NEW_DEALS_URL = BASE_URL + TRADES_ENDPOINT + "?product=NDF&date=YYYYMMDD"

_DATE_PLACEHOLDER_RE = re.compile(r"yyyy[-/. ]?mm[-/. ]?dd", re.I)


def _use_key(value):
    """'new deals' ≡ 'New Deals' ≡ 'NEW_DEALS' — só letras, em minúsculas."""
    return re.sub(r"[^a-z]", "", str(value or "").lower())


def _api_link_rows():
    try:
        with open(API_LINKS_FILE, encoding="utf-8") as fh:
            rows = json.load(fh)
    except Exception:
        return []
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def registered_link(usage):
    """URL crua cadastrada para o uso (com os placeholders), ou None."""
    want = _use_key(usage)
    for row in _api_link_rows():
        if _use_key(row.get("USE")) == want:
            url = str(row.get("URL") or "").strip()
            return url or None
    return None


def build_url(template, product=None, date=None):
    """Resolve os placeholders do link cadastrado.

    A data substitui `YYYYMMDD` onde ele aparecer (inclusive no caminho), e
    `product`/`date` do query string são forçados para o valor pedido pelo
    código — acrescentados quando a URL cadastrada não os tem.
    """
    url = str(template or "").strip()
    if not url:
        return None
    if date:
        url = _DATE_PLACEHOLDER_RE.sub(str(date), url)

    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    for name, value in (("product", product), ("date", date)):
        if value in (None, ""):
            continue
        value = str(value)
        found = False
        for i, (k, _v) in enumerate(query):
            if k.lower() == name:
                query[i] = (k, value)
                found = True
        if not found:
            query.append((name, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(query), parts.fragment))


def registered_url(usage, product=None, date=None):
    """URL pronta para chamar, do cadastro. None quando não há linha (ou a linha
    está sem URL) — aí o chamador decide entre o fallback e o erro."""
    return build_url(registered_link(usage), product=product, date=date)


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
    """GET an Athena endpoint (path relative to BASE_URL) via Kerberos SSO."""
    return get_json_url(session, BASE_URL + path, params=params)


def get_json_url(session, url: str, params: Optional[dict] = None):
    """GET an absolute URL via Kerberos SSO, replaying ADFS form_post hops."""
    resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
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


def fetch_trades(session, product: str, date: str, usage: str = USE_NEW_DEALS):
    """Call the registered endpoint for a product/date and return the parsed
    JSON payload. Sem linha cadastrada, o New Deals cai no endereço histórico —
    os demais usos (Unwinds) não têm fallback e falham dizendo o que falta."""
    url = registered_url(usage, product=product, date=date)
    if url:
        return get_json_url(session, url)
    if _use_key(usage) != _use_key(USE_NEW_DEALS):
        raise RuntimeError(
            "Nenhuma URL cadastrada para {!r} em /mapping › API Links.".format(usage)
        )
    return get_json(session, TRADES_ENDPOINT, {"product": product, "date": date})


def fetch_product_trades(product_key: str, date: str, session=None,
                         usage: str = USE_NEW_DEALS):
    """getTrades for a canonical product key ('NDF', 'FXO', 'COMMODITIES',
    'SWAPS') on a YYYYMMDD date. Creates a SSO session when none is given."""
    key = str(product_key or "").strip().upper()
    if key not in PRODUCTS:
        raise ValueError("Unknown Athena product: {!r}".format(product_key))
    if key not in FUNCTIONAL_PRODUCTS:
        raise NotImplementedError(
            "The Athena getTrades API is not functional for {} yet.".format(PRODUCTS[key])
        )
    return fetch_trades(session or build_session(), PRODUCTS[key], date, usage=usage)


def fetch_unwinds(product_key: str, date: str, session=None):
    """Unwinds de um produto numa data YYYYMMDD, pela URL cadastrada em
    /mapping › API Links (linha Unwinds). Ainda sem consumidor: existe para a
    rotina de unwinds nascer lendo o cadastro, e não um endereço no código."""
    return fetch_product_trades(product_key, date, session=session, usage=USE_UNWINDS)


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
