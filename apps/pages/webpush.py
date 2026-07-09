"""Minimal, dependency-light Web Push (VAPID) sender.

We send *payloadless* pushes (a "tickle"): the server only wakes the Service
Worker, which then fetches /api/notifications itself and shows the notification.
This means NO user data ever transits the browser vendor's push service, and we
avoid the fragile http-ece/pywebpush build (only `cryptography` is required).

Keys (VAPID, P-256) are read from the environment; if unset, push is disabled
and the app runs normally without it.

  VAPID_PUBLIC_KEY   base64url of the 65-byte uncompressed EC public point
  VAPID_PRIVATE_KEY  base64url of the 32-byte raw private scalar
  VAPID_SUBJECT      contact URI, e.g. 'mailto:otc-tracker@example.com'

Generate a keypair with: python scripts/generate_vapid.py
"""
import os
import json
import time
import base64
import logging
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

log = logging.getLogger(__name__)


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def _b64u_decode(s: str) -> bytes:
    s = s + '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode('ascii'))


def generate_keypair():
    """Return (public_b64url, private_b64url) for a fresh VAPID P-256 key."""
    priv = ec.generate_private_key(ec.SECP256R1())
    priv_raw = priv.private_numbers().private_value.to_bytes(32, 'big')
    from cryptography.hazmat.primitives import serialization
    pub_raw = priv.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return _b64u(pub_raw), _b64u(priv_raw)


def get_public_key() -> str:
    return os.getenv('VAPID_PUBLIC_KEY', '') or ''


def is_enabled() -> bool:
    return bool(os.getenv('VAPID_PUBLIC_KEY') and os.getenv('VAPID_PRIVATE_KEY'))


def _load_private_key():
    raw = _b64u_decode(os.environ['VAPID_PRIVATE_KEY'])
    return ec.derive_private_key(int.from_bytes(raw, 'big'), ec.SECP256R1())


def _vapid_auth_header(endpoint: str) -> str:
    """Build the 'Authorization: vapid t=<jwt>,k=<pub>' header for an endpoint."""
    parsed = urlparse(endpoint)
    aud = '{}://{}'.format(parsed.scheme, parsed.netloc)
    header = _b64u(json.dumps({'typ': 'JWT', 'alg': 'ES256'},
                              separators=(',', ':')).encode())
    body = _b64u(json.dumps({
        'aud': aud,
        'exp': int(time.time()) + 12 * 3600,
        'sub': os.getenv('VAPID_SUBJECT', 'mailto:otc-tracker@example.com'),
    }, separators=(',', ':')).encode())
    signing_input = (header + '.' + body).encode('ascii')
    der = _load_private_key().sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    raw_sig = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
    jwt = header + '.' + body + '.' + _b64u(raw_sig)
    return 'vapid t={},k={}'.format(jwt, get_public_key())


def send_push(endpoint: str, ttl: int = 86400) -> int:
    """Send one payloadless push. Returns the HTTP status code.

    A 404/410 means the subscription is gone and the caller should delete it.
    Raises nothing for network errors — returns 0 so the caller can decide.
    """
    if not is_enabled():
        return 0
    try:
        req = Request(endpoint, data=b'', method='POST')
        req.add_header('Authorization', _vapid_auth_header(endpoint))
        req.add_header('TTL', str(ttl))
        req.add_header('Content-Length', '0')
        req.add_header('Urgency', 'normal')
        with urlopen(req, timeout=10) as resp:
            return resp.getcode()
    except HTTPError as e:
        return e.code
    except (URLError, Exception) as e:  # noqa: BLE001
        log.warning('[webpush] send failed for %s…: %s', endpoint[:60], e)
        return 0
