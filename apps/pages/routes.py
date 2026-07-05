from gettext import install
import os
import io
import re
import random
import string
import smtplib
import json
import threading
import traceback
import unicodedata
import uuid
import shutil
import tempfile
import base64
import logging
import time
import duckdb
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import awmpy
from flask import (
    render_template, request, redirect,
    url_for, session, flash, jsonify, make_response
)
from jinja2 import TemplateNotFound

from apps.pages import blueprint

# ==============================================================================
# LOGGING CONFIG
# ==============================================================================

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s [%(funcName)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('otc_tracker')


# ==============================================================================
# SESSION EXPIRY — server-side check (independente do browser restaurar cookies)
# ==============================================================================

@blueprint.before_request
def enforce_session_expiry():
    if not session.get('authenticated'):
        return
    expires_at = session.get('session_expires_at')
    if not expires_at:
        session.clear()
        return
    try:
        expiry = datetime.fromisoformat(expires_at)
        now = datetime.now(tz=timezone.utc)
        # Garante comparação timezone-aware
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if now > expiry:
            session.clear()
            log.info("[enforce_session_expiry] Session expired — cleared")
    except (ValueError, TypeError):
        session.clear()


# Endpoints reachable while the screen is locked. Everything else is bounced to
# the lock screen so the user cannot navigate (or "go back") into the app
# without re-entering their SID and passing IP verification / 2FA.
_LOCK_ALLOWED_ENDPOINTS = {
    'static',
    'pages_blueprint.lock_screen_page',   # the lock screen itself
    'pages_blueprint.unlock',             # SID submit to unlock
    'pages_blueprint.two_factor_page',    # 2FA page (IP-mismatch unlock path)
    'pages_blueprint.verify_2fa',         # 2FA code submit
    'pages_blueprint.resend_code',        # resend 2FA code
    'pages_blueprint.sign_in_page',       # "Not you? Sign in"
    'pages_blueprint.login',              # sign in as a different user
    'pages_blueprint.logout',             # allow logging out while locked
    'pages_blueprint.dev_login',          # DEV BYPASS — reachable while locked (strip before commit)
}


@blueprint.before_request
def enforce_screen_lock():
    """While session['locked'] is set, only the unlock flow is reachable."""
    if not session.get('locked') or not session.get('authenticated'):
        return
    if request.endpoint in _LOCK_ALLOWED_ENDPOINTS:
        return
    return redirect(url_for('pages_blueprint.lock_screen_page'))


@blueprint.after_request
def add_no_store_on_authed_pages(response):
    """Prevent the browser back/forward cache from showing protected HTML after
    the screen is locked or the session ends. Limited to HTML so static assets
    keep caching normally."""
    try:
        if session.get('authenticated') and response.mimetype == 'text/html':
            response.headers['Cache-Control'] = 'no-store, max-age=0'
            response.headers['Pragma'] = 'no-cache'
    except Exception:
        pass
    return response


# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "data", "db", "Users_OTCTracker.db")
CACHE_BASE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "static", "data", "cache", "new deals", "Option", "Commodities"
))
# FXO has its own cache dir so the dashboard labels it "Option FXO" (not Commodities)
OPT_FXO_CACHE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "static", "data", "cache", "new deals", "Option", "FXO"
))
SHARED_MAILBOX = "otc.tracker@jpmorgan.com"
RETURN_PATH     = os.getenv('RETURN_PATH',     r'I:\Confirmation\Derivativos\OTC Tracker\Batch Conecta\Return')
CONECTA_NEW_PATH = os.getenv('CONECTA_NEW_PATH', r'I:\Confirmation\Derivativos\OTC Tracker\Batch Conecta\New')
# Electronic Inventory: one folder per counterparty with Confirmations /
# Transactional / SSI subfolders. Created here on Reference Data checker approval
# and in bulk by scripts/create_counterparty_folders.py (kept in sync).
ELECTRONIC_INVENTORY_ROOT = os.getenv(
    'ELECTRONIC_INVENTORY_ROOT',
    r'I:\Confirmation\Derivativos\OTC Tracker\Electronic Inventory')
EI_SUBFOLDERS = ('Confirmations', 'Transactional', 'SSI')
_EI_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _ei_sanitize(name):
    """Windows-safe counterparty folder name (drop illegal chars incl. '/',
    collapse whitespace, trim trailing dots/spaces). Mirrors
    scripts/create_counterparty_folders.sanitize_folder_name."""
    s = _EI_ILLEGAL.sub('', name or '')
    s = re.sub(r'\s+', ' ', s).strip()
    return s.rstrip('. ')


def _ensure_counterparty_folders(company):
    """Create ELECTRONIC_INVENTORY_ROOT\\<company>\\{Confirmations,Transactional,SSI}
    if missing. Tolerant existence match (case/whitespace/illegal-char insensitive)
    so a folder created earlier under a slightly different name is reused, not
    duplicated. Best-effort: never raises (the share may be offline in dev)."""
    folder = _ei_sanitize(company)
    if not folder:
        return
    try:
        root = ELECTRONIC_INVENTORY_ROOT
        key = folder.upper()
        actual = folder
        if os.path.isdir(root):
            for entry in os.listdir(root):
                if os.path.isdir(os.path.join(root, entry)) and _ei_sanitize(entry).upper() == key:
                    actual = entry
                    break
        parent = os.path.join(root, actual)
        for sub in EI_SUBFOLDERS:
            os.makedirs(os.path.join(parent, sub), exist_ok=True)
    except Exception as exc:
        log.warning('Electronic Inventory folder creation failed for %r: %s', company, exc)
_cache_lock = threading.Lock()


def _atomic_write_json(file_path, data):
    """Write JSON safely: atomic rename on POSIX; direct write fallback on Windows.

    On Windows, os.replace() raises PermissionError if a concurrent reader holds
    the file open without FILE_SHARE_DELETE (e.g. _find_deal_in_cache). In that
    case we fall back to a direct write — safe because _cache_lock already
    serialises all concurrent writes to the same file.
    """
    import tempfile
    dir_name = os.path.dirname(file_path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        try:
            os.replace(tmp_path, file_path)
            return
        except PermissionError:
            pass  # Windows: target held open by a reader — fall through
        # Fallback: copy content then remove temp
        with open(file_path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _unique_filepath(output_dir, filename):
    """Return a path inside output_dir that does not collide with an existing
    file. If 'filename' is free it is used as-is; otherwise a copy suffix is
    inserted before the extension based on how many same-named files exist:
    'TCO_BANCO.txt' -> 'TCO_BANCO (1).txt' -> 'TCO_BANCO (2).txt' ...
    """
    base, ext = os.path.splitext(filename)
    candidate = filename
    n = 0
    while os.path.exists(os.path.join(output_dir, candidate)):
        n += 1
        candidate = base + ' (' + str(n) + ')' + ext
    return os.path.join(output_dir, candidate)


SMTP_HOST = "mailhost.jpmchase.net"
SMTP_PORT = 25
CODE_EXPIRY_MINUTES = 10

ROLE_META = {
    'ADMIN':        {'display': 'Admin',         'icon': 'ti-shield-lock',          'description': 'Full platform administration and user management.',         'responsibilities': ['Manage Users', 'Configure System', 'View All Data', 'Assign Roles']},
    'BO':           {'display': 'Back Office',   'icon': 'ti-briefcase',            'description': 'Back office operations and settlement processing.',         'responsibilities': ['Settlement Processing', 'Position Reconciliation', 'Trade Confirmation', 'Reporting']},
    'MO':           {'display': 'Middle Office', 'icon': 'ti-calculator',           'description': 'Risk management and trade operations oversight.',           'responsibilities': ['Risk Monitoring', 'P&L Attribution', 'Trade Validation', 'Limit Monitoring']},
    'FO':           {'display': 'Front Office',  'icon': 'ti-chart-arrows-vertical','description': 'Trading and client-facing OTC operations.',                'responsibilities': ['OTC Trading', 'Client Management', 'Trade Execution', 'Market Analysis']},
    'INSTITUTIONAL':{'display': 'Institutional', 'icon': 'ti-building-bank',        'description': 'Institutional client operations and portfolio management.', 'responsibilities': ['Portfolio Management', 'Client Reporting', 'Compliance Review', 'Investment Analysis']},
    'HUB':          {'display': 'Hub',           'icon': 'ti-topology-star-3',      'description': 'Hub operations coordinating cross-desk activity.',          'responsibilities': ['Cross-Desk Coordination', 'Deal Routing', 'Workflow Management', 'Escalation Handling']},
}


# ==============================================================================
# FUNÇÕES AUXILIARES — BANCO DE DADOS (DuckDB)
# ==============================================================================
# DuckDB only allows ONE connection per process to an on-disk database.
# We use a singleton connection + a threading lock so concurrent requests
# queue up rather than failing with BinderException.

_duckdb_conn = None
_duckdb_conn_lock = threading.Lock()

# Lazy one-time schema init (see _ensure_db_initialized). Deferred so the
# Werkzeug auto-reloader's supervisor process never opens the single-writer
# DuckDB file — only the worker that actually serves requests does.
_db_init_done = False
_db_init_lock = threading.RLock()     # re-entrant: init_db() re-enters via get_db_connection()
_db_init_tls  = threading.local()     # per-thread "currently initializing" flag


class _DuckDBHandle:
    """Proxy that holds _duckdb_conn_lock for its lifetime; close() releases it."""
    __slots__ = ('_conn', '_closed')

    def __init__(self, conn):
        self._conn = conn
        self._closed = False

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        if not self._closed:
            self._closed = True
            _duckdb_conn_lock.release()


def _duckdb_open():
    global _duckdb_conn
    abs_path = os.path.abspath(DB_PATH)
    _duckdb_conn = duckdb.connect(
        abs_path,
        config={
            "autoinstall_known_extensions": "false",
            "autoload_known_extensions": "false",
        }
    )
    log.debug("DuckDB singleton opened → %s", abs_path)
    return _duckdb_conn


def get_db_connection(max_retries=6, retry_delay=0.05):
    global _duckdb_conn
    _ensure_db_initialized()        # lazy, one-time schema/migrations (no-op after first run)
    last_exc = None
    for attempt in range(max_retries):
        try:
            _duckdb_conn_lock.acquire()
            try:
                if _duckdb_conn is None:
                    _duckdb_open()
                else:
                    try:
                        _duckdb_conn.execute("SELECT 1")
                    except Exception:
                        log.warning("DuckDB singleton unhealthy, reconnecting…")
                        try:
                            _duckdb_conn.close()
                        except Exception:
                            pass
                        _duckdb_open()
            except Exception:
                _duckdb_conn_lock.release()
                raise
            return _DuckDBHandle(_duckdb_conn)
        except duckdb.IOException as e:
            # The inner handler above already released the lock before re-raising,
            # so we must NOT release it again here (that caused
            # "RuntimeError: release unlocked lock" masking the real IOException).
            last_exc = e
            if attempt < max_retries - 1:
                wait = retry_delay * (2 ** attempt)
                log.warning("DuckDB locked (attempt %d/%d), retrying in %.0fms…",
                            attempt + 1, max_retries, wait * 1000)
                time.sleep(wait)
        except Exception:
            log.error("Failed to open DuckDB:\n%s", traceback.format_exc())
            raise
    log.error("DuckDB unavailable after %d retries", max_retries)
    raise last_exc


def init_db():
    log.info("[init_db] Initializing database schema…")
    conn = get_db_connection()
    try:
        log.debug("[init_db] Creating sequence seq_vc_id")
        conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_vc_id START 1")
        log.debug("[init_db] Creating table users")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                SID              VARCHAR PRIMARY KEY,
                Name             VARCHAR NOT NULL,
                Email            VARCHAR NOT NULL,
                Role_Description VARCHAR DEFAULT '',
                Position         VARCHAR DEFAULT '',
                Role             VARCHAR DEFAULT '',
                Status           VARCHAR DEFAULT 'Pending',
                IP_Address       VARCHAR,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        log.debug("[init_db] Creating table verification_codes")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verification_codes (
                id         INTEGER  DEFAULT nextval('seq_vc_id') PRIMARY KEY,
                SID        VARCHAR  NOT NULL,
                code       VARCHAR(6) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                used       BOOLEAN  DEFAULT FALSE
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vc_lookup
            ON verification_codes (SID, used, expires_at)
        """)
        conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_notif_id START 1")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id          INTEGER DEFAULT nextval('seq_notif_id') PRIMARY KEY,
                actor_sid   VARCHAR NOT NULL DEFAULT '',
                actor_name  VARCHAR NOT NULL DEFAULT '',
                action      VARCHAR NOT NULL DEFAULT '',
                page        VARCHAR NOT NULL DEFAULT '',
                detail      VARCHAR DEFAULT '',
                target_role VARCHAR DEFAULT '',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        log.info("[init_db] Schema ready")
    except Exception:
        log.error("[init_db] FAILED:\n%s", traceback.format_exc())
        raise
    finally:
        conn.close()


def _migrate_schema():
    """Migra schemas antigos: sequence nula e colunas Role/Status ausentes."""
    log.info("[migrate] Checking schema migrations…")
    conn = get_db_connection()
    try:
        # Fix verification_codes: id NULL (schema sem sequence)
        try:
            row = conn.execute("SELECT COUNT(*) FROM verification_codes WHERE id IS NULL").fetchone()
            null_count = row[0] if row else 0
            log.debug("[migrate] verification_codes rows with NULL id: %d", null_count)
            if null_count > 0:
                log.warning("[migrate] Dropping verification_codes to fix NULL ids")
                conn.execute("DROP TABLE verification_codes")
                conn.execute("DROP SEQUENCE IF EXISTS seq_vc_id")
                conn.commit()
        except Exception:
            log.debug("[migrate] verification_codes check skipped: %s", traceback.format_exc())

        # Fix users: Role -> Role_Description + add Role + add Status
        try:
            cols = [c[0] for c in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='users'"
            ).fetchall()]
            log.debug("[migrate] users columns: %s", cols)

            if 'Role' in cols and 'Role_Description' not in cols:
                log.warning("[migrate] Renaming Role → Role_Description")
                conn.execute("ALTER TABLE users RENAME COLUMN Role TO Role_Description")
                conn.commit()
                cols = [c[0] for c in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='users'"
                ).fetchall()]
                log.debug("[migrate] users columns after rename: %s", cols)

            if 'Role' not in cols:
                log.warning("[migrate] Adding missing column Role")
                conn.execute("ALTER TABLE users ADD COLUMN Role VARCHAR DEFAULT ''")
                conn.commit()

            if 'Status' not in cols:
                log.warning("[migrate] Adding missing column Status")
                conn.execute("ALTER TABLE users ADD COLUMN Status VARCHAR")
                conn.execute("UPDATE users SET Status = 'Pending' WHERE Status IS NULL")
                conn.commit()

            if 'Position' not in cols:
                log.warning("[migrate] Adding missing column Position")
                conn.execute("ALTER TABLE users ADD COLUMN Position VARCHAR DEFAULT ''")
                conn.commit()

            log.info("[migrate] Schema migration complete")
        except Exception:
            log.error("[migrate] users schema migration FAILED:\n%s", traceback.format_exc())

        # Ensure notifications table exists
        try:
            conn.execute("SELECT 1 FROM notifications LIMIT 1")
        except Exception:
            log.warning("[migrate] notifications table missing — creating")
            try:
                conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_notif_id START 1")
            except Exception:
                pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id          INTEGER DEFAULT nextval('seq_notif_id') PRIMARY KEY,
                    actor_sid   VARCHAR NOT NULL DEFAULT '',
                    actor_name  VARCHAR NOT NULL DEFAULT '',
                    action      VARCHAR NOT NULL DEFAULT '',
                    page        VARCHAR NOT NULL DEFAULT '',
                    detail      VARCHAR DEFAULT '',
                    target_role VARCHAR DEFAULT '',
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            log.info("[migrate] notifications table created")
    finally:
        conn.close()


def _create_notification(actor_sid, actor_name, action, page, detail='', target_role=''):
    try:
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO notifications (actor_sid, actor_name, action, page, detail, target_role) VALUES (?, ?, ?, ?, ?, ?)",
                [actor_sid or '', actor_name or '', action, page, detail or '', target_role or '']
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        log.error("[_create_notification] FAILED:\n%s", traceback.format_exc())


def _nd_token(value):
    """Return a ' [ND:YYYY-MM-DD]' suffix for a notification detail so the bell can
    deep-link to that date (Accrual → ?date=, New Deals → ?tradedate=). Accepts a
    date, YYYYMMDD, YYYY-MM-DD or dd/mm/yyyy string; returns '' when unparseable.
    The topbar strips the token before displaying the detail."""
    if not value:
        return ''
    s = str(value).strip()
    d = None
    if re.match(r'^\d{8}$', s):
        try:
            d = datetime.strptime(s, '%Y%m%d')
        except Exception:
            d = None
    if d is None:
        try:
            d = _parse_date_any(s)
        except Exception:
            d = None
    return ' [ND:{}]'.format(d.strftime('%Y-%m-%d')) if d else ''


def get_user_by_sid(sid):
    log.debug("[get_user_by_sid] Looking up SID=%s", sid)
    conn = get_db_connection()
    try:
        result = conn.execute(
            "SELECT SID, Name, Email, Role_Description, Position, Role, Status, IP_Address FROM users WHERE SID = ?",
            [sid]
        ).fetchone()
        if result:
            user = {
                "SID": result[0],
                "Name": result[1],
                "Email": result[2],
                "Role_Description": result[3],
                "Position": result[4] or "",
                "Role": result[5],
                "Status": result[6] or "Pending",
                "IP_Address": result[7]
            }
            log.debug("[get_user_by_sid] Found: Name=%s Role=%s Status=%s IP=%s",
                      user["Name"], user["Role"], user["Status"], user["IP_Address"])
            return user
        log.debug("[get_user_by_sid] SID=%s not found in DB", sid)
        return None
    except Exception:
        log.error("[get_user_by_sid] Query error:\n%s", traceback.format_exc())
        raise
    finally:
        conn.close()


def get_all_users():
    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT SID, Name, Email, Role_Description, Position, Role, Status, IP_Address, created_at
            FROM users
            ORDER BY created_at DESC
        """).fetchall()
        users = []
        for r in rows:
            users.append({
                "SID": r[0],
                "Name": r[1],
                "Email": r[2],
                "Role_Description": r[3] or "",
                "Position": r[4] or "",
                "Role": r[5] or "",
                "Status": r[6] or "Pending",
                "IP_Address": r[7],
                "created_at": r[8].strftime("%d %b, %Y") if r[8] else ""
            })
        return users
    finally:
        conn.close()


def get_role_groups():
    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT Role, COUNT(*) AS cnt,
                   LIST(SID   ORDER BY created_at DESC) AS sids,
                   LIST(Name  ORDER BY created_at DESC) AS names
            FROM users
            WHERE Role IS NOT NULL AND Role != ''
            GROUP BY Role
        """).fetchall()

        groups = {}
        for role, cnt, sids, names in rows:
            meta = ROLE_META.get(role, {
                'display': role, 'icon': 'ti-user',
                'description': '', 'responsibilities': [],
            })
            preview = [{'SID': s, 'Name': n}
                       for s, n in zip((sids or [])[:4], (names or [])[:4])]
            groups[role] = {
                'role': role,
                'display': meta['display'],
                'icon': meta['icon'],
                'description': meta['description'],
                'responsibilities': meta['responsibilities'],
                'count': cnt,
                'users': preview,
            }

        result = []
        for key in ['ADMIN', 'FO', 'MO', 'BO', 'INSTITUTIONAL', 'HUB']:
            if key in groups:
                result.append(groups[key])
        for key, val in groups.items():
            if key not in ['ADMIN', 'FO', 'MO', 'BO', 'INSTITUTIONAL', 'HUB']:
                result.append(val)
        return result
    finally:
        conn.close()


def insert_new_user(sid, name, email, role_description, ip_address):
    log.info("[insert_new_user] Inserting SID=%s Name=%s Email=%s IP=%s", sid, name, email, ip_address)
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO users (SID, Name, Email, Role_Description, Position, Role, Status, IP_Address)
            VALUES (?, ?, ?, ?, '', '', 'Pending', ?)
        """, [sid, name, email, role_description or "", ip_address])
        conn.commit()
        log.info("[insert_new_user] Inserted SID=%s OK", sid)
    except Exception:
        log.error("[insert_new_user] FAILED for SID=%s:\n%s", sid, traceback.format_exc())
        raise
    finally:
        conn.close()


def update_user_ip(sid, ip_address):
    conn = get_db_connection()
    try:
        conn.execute("UPDATE users SET IP_Address = ? WHERE SID = ?", [ip_address, sid])
        conn.commit()
    finally:
        conn.close()


def update_user_role_status(sid, role, status, position=None):
    conn = get_db_connection()
    try:
        if position is not None:
            conn.execute(
                "UPDATE users SET Role = ?, Status = ?, Position = ? WHERE SID = ?",
                [role, status, position, sid]
            )
        else:
            conn.execute(
                "UPDATE users SET Role = ?, Status = ? WHERE SID = ?",
                [role, status, sid]
            )
        conn.commit()
    finally:
        conn.close()


def save_verification_code(sid, code):
    log.info("[save_verification_code] Saving code for SID=%s (expiry=%d min)", sid, CODE_EXPIRY_MINUTES)
    conn = get_db_connection()
    try:
        invalidated = conn.execute(
            "UPDATE verification_codes SET used = TRUE WHERE SID = ? AND used = FALSE",
            [sid]
        ).rowcount
        log.debug("[save_verification_code] Invalidated %s old codes for SID=%s", invalidated, sid)
        conn.execute(
            f"INSERT INTO verification_codes (SID, code, expires_at) "
            f"VALUES (?, ?, CURRENT_TIMESTAMP + INTERVAL '{CODE_EXPIRY_MINUTES}' MINUTE)",
            [sid, code]
        )
        conn.commit()
        log.info("[save_verification_code] Code saved for SID=%s", sid)
    except Exception:
        log.error("[save_verification_code] FAILED for SID=%s:\n%s", sid, traceback.format_exc())
        raise
    finally:
        conn.close()


def verify_code(sid, code):
    log.info("[verify_code] Verifying code for SID=%s", sid)
    conn = get_db_connection()
    try:
        result = conn.execute("""
            SELECT id FROM verification_codes
            WHERE SID = ? AND code = ? AND used = FALSE
              AND expires_at > CURRENT_TIMESTAMP
            ORDER BY created_at DESC
            LIMIT 1
        """, [sid, code]).fetchone()

        if not result:
            exists = conn.execute(
                "SELECT 1 FROM verification_codes WHERE SID = ? AND code = ? AND used = FALSE",
                [sid, code]
            ).fetchone()
            if exists:
                log.warning("[verify_code] Code for SID=%s is EXPIRED", sid)
                return False, "Verification code has expired. Please request a new one."
            log.warning("[verify_code] Invalid code attempt for SID=%s", sid)
            return False, "Invalid verification code."

        conn.execute("UPDATE verification_codes SET used = TRUE WHERE id = ?", [result[0]])
        conn.commit()
        log.info("[verify_code] Code verified OK for SID=%s (row id=%s)", sid, result[0])
        return True, "Code verified successfully."
    except Exception:
        log.error("[verify_code] Error for SID=%s:\n%s", sid, traceback.format_exc())
        raise
    finally:
        conn.close()


def cleanup_expired_codes():
    conn = get_db_connection()
    try:
        conn.execute("""
            DELETE FROM verification_codes
            WHERE used = TRUE OR expires_at < CURRENT_TIMESTAMP
        """)
        conn.commit()
    finally:
        conn.close()


# ==============================================================================
# FUNÇÕES AUXILIARES — UTILITÁRIOS
# ==============================================================================

def get_client_ip():
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.remote_addr


def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))


def get_user_data_from_phonebook(sid):
    log.info("[phonebook] Fetching data for SID=%s", sid)
    try:
        data = awmpy.get_phonebook_data(sid)
        log.debug("[phonebook] Raw response keys for SID=%s: %s", sid, list(data.keys()) if data else None)
        result = {
            "nameFull": data.get("nameFull", ""),
            "email": data.get("email", ""),
            "positionName": data.get("positionName", "")
        }
        log.info("[phonebook] SID=%s → name=%s email=%s position=%s",
                 sid, result["nameFull"], result["email"], result["positionName"])
        return result
    except Exception:
        log.error("[phonebook] FAILED for SID=%s:\n%s", sid, traceback.format_exc())
        return None


def get_masked_email(email):
    if not email or '@' not in email:
        return "*******"
    local, domain = email.split('@', 1)
    if len(local) <= 2:
        masked_local = local[0] + '*****'
    else:
        masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def get_masked_phone():
    return "******6789"


# ==============================================================================
# FUNÇÕES AUXILIARES — EMAIL
# ==============================================================================

def send_verification_email(to_email, code, recipient_name):
    from email.mime.image import MIMEImage
    from flask import current_app

    html_body = render_email_template(code, recipient_name)

    msg = MIMEMultipart('mixed')
    msg['Subject'] = "OTC Tracker - Verification Code"
    msg['From'] = SHARED_MAILBOX
    msg['To'] = to_email

    msg_related = MIMEMultipart('related')
    msg_alternative = MIMEMultipart('alternative')
    msg_alternative.attach(MIMEText('Please use an HTML email client to view this message.', 'plain'))
    msg_alternative.attach(MIMEText(html_body, 'html'))
    msg_related.attach(msg_alternative)

    logo_path = _get_logo_path()
    if logo_path:
        try:
            with open(logo_path, 'rb') as f:
                logo_data = f.read()
            logo_mime = MIMEImage(logo_data)
            logo_mime.add_header('Content-ID', '<otc_logo>')
            logo_mime.add_header('Content-Disposition', 'inline', filename='logo.png')
            msg_related.attach(logo_mime)
        except Exception as e:
            print(f"Warning: Could not attach logo: {e}")

    msg.attach(msg_related)

    log.info("[send_email] Connecting to SMTP %s:%d", SMTP_HOST, SMTP_PORT)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.sendmail(SHARED_MAILBOX, to_email, msg.as_string())
        log.info("[send_email] Verification email sent to %s", to_email)
        return True
    except Exception:
        log.error("[send_email] FAILED sending to %s:\n%s", to_email, traceback.format_exc())
        return False


def send_account_activated_email(to_email, first_name):
    from email.mime.image import MIMEImage
    from datetime import datetime

    html_body = render_template(
        'pages/email-template-account-activated.html',
        first_name=first_name,
        sign_in_url=url_for('pages_blueprint.sign_in_page', _external=True),
        current_year=datetime.now().year
    )

    msg = MIMEMultipart('mixed')
    msg['Subject'] = "OTC Tracker - Your Account Has Been Activated"
    msg['From'] = SHARED_MAILBOX
    msg['To'] = to_email

    msg_related = MIMEMultipart('related')
    msg_alternative = MIMEMultipart('alternative')
    msg_alternative.attach(MIMEText('Your OTC Tracker account has been activated. Please sign in.', 'plain'))
    msg_alternative.attach(MIMEText(html_body, 'html'))
    msg_related.attach(msg_alternative)

    logo_path = _get_logo_path()
    if logo_path:
        try:
            with open(logo_path, 'rb') as f:
                logo_data = f.read()
            logo_mime = MIMEImage(logo_data)
            logo_mime.add_header('Content-ID', '<otc_logo>')
            logo_mime.add_header('Content-Disposition', 'inline', filename='logo.png')
            msg_related.attach(logo_mime)
        except Exception as e:
            print(f"Warning: Could not attach logo to activation email: {e}")
    else:
        print("Warning: logo not found, activation email will have no logo.")

    msg.attach(msg_related)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.sendmail(SHARED_MAILBOX, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Error sending activation email to {to_email}: {e}")
        return False


def _get_logo_path():
    from flask import current_app
    candidates = [
        os.path.join(current_app.root_path, 'static', 'images', 'logo.png'),
        os.path.join(os.path.dirname(current_app.root_path), 'static', 'images', 'logo.png'),
        os.path.join(current_app.root_path, '..', 'static', 'images', 'logo.png'),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.exists(path):
            return path
    return None


def render_email_template(code, recipient_name):
    return render_template(
        'pages/email-verification.html',
        recipient_name=recipient_name,
        digits=list(code),
        expiry_minutes=CODE_EXPIRY_MINUTES,
        current_year=datetime.now().year
    )


# ==============================================================================
# INICIALIZAÇÃO DO BANCO DE DADOS
# ==============================================================================

def _ensure_duckdb_file():
    """Remove o arquivo se for SQLite (criado pelo SQLAlchemy antigo) para o DuckDB recriar."""
    db_path = os.path.abspath(DB_PATH)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        try:
            with open(db_path, 'rb') as f:
                header = f.read(16)
            if header.startswith(b'SQLite format 3\x00'):
                print(f"[DB] Arquivo SQLite detectado em {db_path} — removendo para recriar como DuckDB.")
                os.remove(db_path)
        except Exception as e:
            print(f"[DB] Erro ao verificar formato do arquivo: {e}")


_ensure_duckdb_file()


def _ensure_db_initialized():
    """Run schema creation + migrations exactly once, lazily, in the process
    that first needs the DB. Deferred (NOT run at import) so the Werkzeug
    auto-reloader's supervisor process — which imports this module but never
    serves requests — does not open the single-writer DuckDB file and lock it
    out from the worker. In production (gunicorn) the first request triggers it.

    Re-entrant safe: init_db()/_migrate_schema() themselves call
    get_db_connection(), which calls back here. The per-thread `running` flag lets
    those nested calls fall straight through to open the connection without
    recursing into init again, while concurrent first-callers from OTHER threads
    block on the lock until init has fully completed (done set only on success)."""
    global _db_init_done
    if _db_init_done:
        return
    # Nested call on the SAME thread (from init_db's own get_db_connection):
    # don't recurse — let it proceed to open the connection.
    if getattr(_db_init_tls, 'running', False):
        return
    with _db_init_lock:
        if _db_init_done:
            return
        _db_init_tls.running = True
        try:
            init_db()
            _migrate_schema()
            cleanup_expired_codes()
            _db_init_done = True        # only mark done AFTER schema/migrations succeed
            log.info("[startup] Database initialized successfully at %s", os.path.abspath(DB_PATH))
        except Exception:
            log.error("[startup] Could not initialize database:\n%s", traceback.format_exc())
            raise
        finally:
            _db_init_tls.running = False


# ==============================================================================
# ROTAS — PÁGINAS DE AUTENTICAÇÃO
# ==============================================================================

@blueprint.route('/')
def index():
    if session.get('authenticated'):
        return redirect(url_for('pages_blueprint.dashboard'))
    return render_template('pages/auth-2-sign-in.html', segment='auth-2-sign-in')


@blueprint.route('/auth-2-sign-in')
def sign_in_page():
    return render_template('pages/auth-2-sign-in.html', segment='auth-2-sign-in')


@blueprint.route('/auth-2-sign-up')
def sign_up_page():
    return render_template('pages/auth-2-sign-up.html', segment='auth-2-sign-up')


@blueprint.route('/auth-2-two-factor')
def two_factor_page():
    return render_template(
        'pages/auth-2-two-factor.html',
        segment='auth-2-two-factor',
        masked_email=session.get('masked_email', '******'),
        masked_phone=session.get('masked_phone', '******6789')
    )


# ==============================================================================
# ROTAS — LÓGICA DE AUTENTICAÇÃO (POST)
# ==============================================================================

def _validate_sid(sid):
    return sid and re.match(r'^[A-Z][0-9]{6}$', sid)


@blueprint.route('/register', methods=['POST'])
def register():
    sid = request.form.get('sid', '').strip().upper()
    log.info("[register] Attempt SID=%s IP=%s", sid, get_client_ip())

    if not _validate_sid(sid):
        log.warning("[register] Invalid SID format: %r", sid)
        flash("Invalid SID format. Must be 1 letter + 6 numbers.", "error")
        return redirect(url_for('pages_blueprint.sign_up_page'))

    client_ip = get_client_ip()
    existing_user = get_user_by_sid(sid)

    if existing_user:
        log.info("[register] SID=%s already exists — delegating to _handle_existing_user", sid)
        return _handle_existing_user(existing_user, sid, client_ip,
                                     redirect_page='pages_blueprint.sign_up_page')
    else:
        log.info("[register] SID=%s is new — delegating to _handle_new_user", sid)
        return _handle_new_user(sid, client_ip,
                                redirect_page='pages_blueprint.sign_up_page')


@blueprint.route('/login', methods=['POST'])
def login():
    sid = request.form.get('sid', '').strip().upper()
    remember_me = request.form.get('remember_me') == 'on'
    client_ip = get_client_ip()
    log.info("[login] Attempt SID=%s IP=%s remember=%s", sid, client_ip, remember_me)

    if not _validate_sid(sid):
        log.warning("[login] Invalid SID format: %r", sid)
        flash("Invalid SID format. Must be 1 letter + 6 numbers.", "error")
        return redirect(url_for('pages_blueprint.sign_in_page'))

    existing_user = get_user_by_sid(sid)

    if existing_user:
        log.info("[login] SID=%s found in DB (Status=%s) — delegating to _handle_existing_user",
                 sid, existing_user.get("Status"))
        return _handle_existing_user(existing_user, sid, client_ip,
                                     redirect_page='pages_blueprint.sign_in_page',
                                     remember_me=remember_me)
    else:
        log.info("[login] SID=%s not in DB — delegating to _handle_new_user", sid)
        return _handle_new_user(sid, client_ip,
                                redirect_page='pages_blueprint.sign_in_page')


def _handle_existing_user(user, sid, client_ip, redirect_page, remember_me=False):
    status = user.get("Status", "Pending")
    stored_ip = user.get("IP_Address")
    log.info("[_handle_existing_user] SID=%s Status=%s StoredIP=%s ClientIP=%s remember=%s",
             sid, status, stored_ip, client_ip, remember_me)

    if status == 'Inactive':
        log.warning("[_handle_existing_user] SID=%s is Inactive — blocking login", sid)
        flash("Your account is inactive. Please contact the OTC Tracker administrator.", "error")
        return redirect(url_for(redirect_page))

    if status == 'Pending':
        log.warning("[_handle_existing_user] SID=%s is Pending — blocking login", sid)
        flash("Your account is pending approval. You will receive an email once it is activated.", "warning")
        return redirect(url_for(redirect_page))

    # Active
    if stored_ip == client_ip:
        log.info("[_handle_existing_user] SID=%s IP match — granting session directly", sid)
        _set_session(user, remember_me=remember_me)
        return redirect(url_for('pages_blueprint.dashboard'))
    else:
        log.info("[_handle_existing_user] SID=%s IP mismatch (stored=%s vs current=%s) — triggering 2FA",
                 sid, stored_ip, client_ip)
        # Do NOT persist the new IP yet: storing it before the code is verified
        # would let anyone holding the SID overwrite the trusted IP and then log
        # in directly (IP-match shortcut) without ever passing 2FA. Stash it in
        # the session and only commit it after verify_2fa succeeds.
        session['pending_remember_me'] = remember_me
        session['pending_ip'] = client_ip
        return _initiate_2fa(sid, user["Email"], user["Name"])


def _handle_new_user(sid, client_ip, redirect_page):
    log.info("[_handle_new_user] SID=%s — querying phonebook", sid)
    user_data = get_user_data_from_phonebook(sid)
    if not user_data:
        log.error("[_handle_new_user] Phonebook returned None for SID=%s", sid)
        flash("Could not retrieve user data. Please verify your SID.", "error")
        return redirect(url_for(redirect_page))

    log.info("[_handle_new_user] Phonebook OK for SID=%s — inserting into DB", sid)
    insert_new_user(sid, user_data["nameFull"], user_data["email"],
                    user_data["positionName"], client_ip)

    first_name = user_data["nameFull"].split()[0] if user_data["nameFull"] else sid
    log.info("[_handle_new_user] SID=%s registered successfully, showing success page", sid)
    _create_notification(sid, user_data.get("nameFull", sid), 'Access Request', 'Users',
                         sid + ' — ' + user_data.get("positionName", ''), target_role='ADMIN')
    return render_template('pages/auth-2-success-mail.html',
                           segment='auth-2-success-mail',
                           first_name=first_name)


def _set_session(user, remember_me=False):
    session.permanent = remember_me
    session['authenticated'] = True
    session['user_sid'] = user["SID"]
    session['user_name'] = user["Name"]
    session['user_email'] = user["Email"]
    session['user_role'] = user["Role"]
    session['remember_me'] = remember_me
    # A freshly established session is never locked.
    session.pop('locked', None)
    # Without "Keep me signed in": hard cap of 5 hours (absolute, even with
    # activity). With it: 30 days + IP re-verification on a new IP.
    lifetime = timedelta(days=30) if remember_me else timedelta(hours=5)
    session['session_expires_at'] = (datetime.now(tz=timezone.utc) + lifetime).isoformat()


@blueprint.route('/verify-2fa', methods=['POST'])
def verify_2fa():
    sid = session.get('pending_sid')
    log.info("[verify_2fa] Request from IP=%s session_sid=%s is_json=%s",
             get_client_ip(), sid, request.is_json)

    if not sid:
        log.warning("[verify_2fa] No pending_sid in session — session keys: %s", list(session.keys()))
        flash("Session expired. Please try again.", "error")
        return redirect(url_for('pages_blueprint.sign_in_page'))

    if request.is_json:
        body = request.get_json()
        log.debug("[verify_2fa] JSON body keys: %s", list(body.keys()) if body else None)
        code = (body or {}).get('code', '').strip()
    else:
        code = request.form.get('code', '').strip()

    log.debug("[verify_2fa] Code length=%d for SID=%s", len(code), sid)

    if not code or len(code) != 6:
        log.warning("[verify_2fa] Invalid code format for SID=%s: %r", sid, code)
        if request.is_json:
            return jsonify({"success": False, "message": "Please enter a valid 6-digit code."}), 400
        flash("Please enter a valid 6-digit code.", "error")
        return redirect(url_for('pages_blueprint.two_factor_page'))

    is_valid, message = verify_code(sid, code)
    log.info("[verify_2fa] verify_code result for SID=%s: valid=%s msg=%s", sid, is_valid, message)

    if is_valid:
        user = get_user_by_sid(sid)
        remember_me = session.pop('pending_remember_me', False)
        # Now that the code is verified, trust this IP for future direct logins.
        pending_ip = session.pop('pending_ip', None)
        if pending_ip:
            update_user_ip(sid, pending_ip)
        session.pop('pending_sid', None)
        session.pop('masked_email', None)
        session.pop('masked_phone', None)
        _set_session(user, remember_me=remember_me)
        log.info("[verify_2fa] 2FA SUCCESS for SID=%s remember=%s — session set", sid, remember_me)

        if request.is_json:
            return jsonify({"success": True, "redirect": url_for('pages_blueprint.dashboard')})
        return redirect(url_for('pages_blueprint.dashboard'))
    else:
        log.warning("[verify_2fa] 2FA FAILED for SID=%s: %s", sid, message)
        if request.is_json:
            return jsonify({"success": False, "message": message}), 400
        flash(message, "error")
        return redirect(url_for('pages_blueprint.two_factor_page'))


@blueprint.route('/resend-code', methods=['POST'])
def resend_code():
    sid = session.get('pending_sid')

    if not sid:
        if request.is_json:
            return jsonify({"success": False, "message": "Session expired."}), 400
        flash("Session expired. Please try again.", "error")
        return redirect(url_for('pages_blueprint.sign_in_page'))

    user = get_user_by_sid(sid)
    if not user:
        if request.is_json:
            return jsonify({"success": False, "message": "User not found."}), 404
        flash("User not found.", "error")
        return redirect(url_for('pages_blueprint.sign_in_page'))

    code = generate_verification_code()
    save_verification_code(sid, code)
    email_sent = send_verification_email(user["Email"], code, user["Name"])

    if request.is_json:
        if email_sent:
            return jsonify({"success": True, "message": "New code sent successfully."})
        return jsonify({"success": False, "message": "Failed to send email."}), 500

    if email_sent:
        flash("A new verification code has been sent to your email.", "success")
    else:
        flash("Failed to send verification email. Please try again.", "error")
    return redirect(url_for('pages_blueprint.two_factor_page'))


# ==============================================================================
# ROTAS — LOCK SCREEN
# ==============================================================================

@blueprint.route('/lock')
def lock():
    """Lock the current session and send the user to the lock screen.
    Used by the topbar 'Lock Screen' item and the 3h idle auto-lock."""
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    session['locked'] = True
    log.info("[lock] Screen locked for SID=%s", session.get('user_sid'))
    return redirect(url_for('pages_blueprint.lock_screen_page'))


@blueprint.route('/auth-2-lock-screen')
def lock_screen_page():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template(
        'pages/auth-2-lock-screen.html',
        segment='auth-2-lock-screen',
        user_name=session.get('user_name', ''),
        user_sid=session.get('user_sid', ''),
    )


@blueprint.route('/unlock', methods=['POST'])
def unlock():
    """Unlock the screen: the SID must match the locked account and pass the
    same IP verification as login (direct on IP match, otherwise 2FA)."""
    locked_sid = session.get('user_sid')
    if not session.get('authenticated') or not locked_sid:
        return redirect(url_for('pages_blueprint.sign_in_page'))

    sid = request.form.get('sid', '').strip().upper()
    log.info("[unlock] Attempt SID=%s lockedSID=%s IP=%s", sid, locked_sid, get_client_ip())

    if not _validate_sid(sid):
        flash("Invalid SID format. Must be 1 letter + 6 numbers.", "error")
        return redirect(url_for('pages_blueprint.lock_screen_page'))

    if sid != locked_sid:
        log.warning("[unlock] SID mismatch (entered=%s locked=%s)", sid, locked_sid)
        flash("This SID does not match the locked account.", "error")
        return redirect(url_for('pages_blueprint.lock_screen_page'))

    user = get_user_by_sid(sid)
    if not user:
        session.clear()
        return redirect(url_for('pages_blueprint.sign_in_page'))

    # Reuse the login IP-verification flow. On IP match _set_session clears the
    # 'locked' flag; on mismatch it routes to 2FA, after which verify_2fa does.
    remember_me = session.get('remember_me', False)
    return _handle_existing_user(user, sid, get_client_ip(),
                                 redirect_page='pages_blueprint.lock_screen_page',
                                 remember_me=remember_me)


# ==============================================================================
# ROTAS — APLICAÇÃO (PÓS-AUTENTICAÇÃO)
# ==============================================================================

@blueprint.route('/dashboard')
def dashboard():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/index.html', segment='index')


@blueprint.route('/api/dashboard-stats')
def api_dashboard_stats():
    if not session.get('authenticated'):
        return jsonify({'error': 'unauthorized'}), 401

    period = request.args.get('period', 'all')  # month | year | all
    now = datetime.now()
    cur_month, cur_year = now.month, now.year

    def _file_in_period(fdate):
        if period == 'month':
            return fdate.month == cur_month and fdate.year == cur_year
        if period == 'year':
            return fdate.year == cur_year
        return True

    def _is_lawton(d):
        return 'lawton' in (d.get('Client') or '').lower()

    def _is_bank(d):
        cl = (d.get('Client') or '').lower()
        return 'banco' in cl or 'j.p morgan' in cl or 'jp morgan' in cl or 'jpmorgan' in cl

    def _product_from_path(file_path):
        """Derive product label from directory path relative to new deals/ root.
        e.g. .../Option/Commodities/2026/06/file.json  → 'Option Commodities'
             .../NDF/FWD Start/2026/06/file.json       → 'NDF FWD Start'
        """
        rel = os.path.relpath(file_path, NEW_DEALS_CACHE_ROOT).replace('\\', '/')
        parts = rel.split('/')
        label_parts = [p for p in parts[:-1] if not p.isdigit()][:2]
        return ' '.join(label_parts) if label_parts else 'Other'

    def _type_from_product(product):
        p = product.lower()
        if p.startswith('option'):
            return 'OPT'
        if p.startswith('swap'):
            return 'SWAP'
        return 'NDF'

    # Generic scan of all new deals cache directories
    all_deals = []
    if os.path.isdir(NEW_DEALS_CACHE_ROOT):
        for root, _dirs, files in os.walk(NEW_DEALS_CACHE_ROOT):
            for fname in sorted(files):
                if not fname.endswith('.json') or fname.endswith('.tmp') or fname.endswith('.bak'):
                    continue
                date_str = fname[:8]
                try:
                    fdate = datetime.strptime(date_str, '%Y%m%d')
                except ValueError:
                    continue
                if not _file_in_period(fdate):
                    continue
                fp = os.path.join(root, fname)
                product = _product_from_path(fp)
                deal_type = _type_from_product(product)
                try:
                    with open(fp, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                    for d in data:
                        if isinstance(d, dict) and (d.get('Deal') or '').strip():
                            d['_fdate']   = fdate.strftime('%Y-%m-%d')
                            d['_product'] = product
                            d['_type']    = deal_type
                            all_deals.append(d)
                except Exception:
                    pass

    def _is_fxo(d):
        return 'fxo' in (d.get('_product') or '').lower()
    # Commodities/NDF dedupe by the Lawton leg; FXO is one row per deal (count all),
    # but the Banco J.P. Morgan counterparty leg is never counted.
    lawton_deals = [d for d in all_deals
                    if (_is_fxo(d) and not _is_bank(d)) or (not _is_fxo(d) and _is_lawton(d))]
    client_deals = [d for d in all_deals if not _is_lawton(d) and not _is_bank(d)]

    def _fam(d):
        # FXO is split out of the OPT bucket so the dashboard can show it apart
        return 'FXO' if _is_fxo(d) else d['_type']
    ndf_lawton     = [d for d in lawton_deals if _fam(d) == 'NDF']
    optcomm_lawton = [d for d in lawton_deals if _fam(d) == 'OPT']
    fxo_lawton     = [d for d in lawton_deals if _fam(d) == 'FXO']
    swap_lawton    = [d for d in lawton_deals if _fam(d) == 'SWAP']
    opt_lawton     = optcomm_lawton + fxo_lawton  # all options (stat card)
    pending_statuses = {'Pending', 'New', 'pending', 'new'}
    pending_total = sum(1 for d in lawton_deals if (d.get('Status') or '').strip() in pending_statuses)

    # Swap deals counted like NDF/Opt: by the Lawton (intragroup) leg, from any
    # product folder under new deals whose path starts with "Swap".
    swap_total = len(swap_lawton)

    client_counts = Counter(
        (d.get('Client') or '').strip()
        for d in client_deals
        if (d.get('Client') or '').strip()
    )
    top5_clients = []
    for c, n in client_counts.most_common(5):
        by_product = Counter(
            d['_product'] for d in client_deals if (d.get('Client') or '').strip() == c
        )
        top5_clients.append({'label': c, 'count': n, 'by_product': dict(by_product)})

    product_counts = Counter(d['_product'] for d in lawton_deals)
    top5_products  = [{'label': p, 'count': n} for p, n in product_counts.most_common(5)]

    # Top 5 Underlying Assets — commodities show the Commodity name; FXO (no
    # Commodity) falls back to UnderlyingAsset (the currency).
    def _underlying_label(d):
        return (d.get('Commodities') or d.get('Commodity') or d.get('UnderlyingAsset') or '').strip()
    underlying_counts = Counter(
        _underlying_label(d) for d in lawton_deals if _underlying_label(d)
    )
    top5_underlying = [{'label': c, 'count': n} for c, n in underlying_counts.most_common(5)]

    # Monthly counts for current year (always full year, ignores period filter)
    monthly_opt = [0] * 12
    monthly_ndf = [0] * 12
    monthly_fxo = [0] * 12
    monthly_swap = [0] * 12
    if os.path.isdir(NEW_DEALS_CACHE_ROOT):
        for root, _dirs, files in os.walk(NEW_DEALS_CACHE_ROOT):
            for fname in files:
                if not fname.endswith('.json') or fname.endswith('.tmp') or fname.endswith('.bak'):
                    continue
                try:
                    fdate = datetime.strptime(fname[:8], '%Y%m%d')
                except ValueError:
                    continue
                if fdate.year != cur_year:
                    continue
                fp = os.path.join(root, fname)
                product = _product_from_path(fp)
                is_fxo_file = 'fxo' in product.lower()
                ptype = _type_from_product(product)
                if is_fxo_file:
                    target = monthly_fxo
                elif ptype == 'OPT':
                    target = monthly_opt
                elif ptype == 'SWAP':
                    target = monthly_swap
                else:
                    target = monthly_ndf
                try:
                    with open(fp, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                    # FXO counts every deal except the Banco J.P. Morgan leg;
                    # Commodities/NDF dedupe by the Lawton leg
                    cnt = sum(
                        1 for d in data
                        if isinstance(d, dict)
                        and (d.get('Deal') or '').strip()
                        and ((is_fxo_file and not _is_bank(d))
                             or (not is_fxo_file and 'lawton' in (d.get('Client') or '').lower()))
                    )
                    target[fdate.month - 1] += cnt
                except Exception:
                    pass

    # Recent deals: last 50 client rows sorted desc — frontend filters by product
    recent_sorted = sorted(client_deals, key=lambda d: d.get('_fdate', ''), reverse=True)[:50]
    recent_deals = [
        {
            'deal':    d.get('Deal', ''),
            'client':  d.get('Client', ''),
            'date':    d.get('TradeDate', '') or d.get('_fdate', ''),
            'status':  d.get('Status', ''),
            'product': d['_product'],
            'type':    d['_type'],
        }
        for d in recent_sorted
    ]

    return jsonify({
        'ndf_total':     len(ndf_lawton),
        'opt_total':     len(opt_lawton),
        'pending_total': pending_total,
        'swap_total':    swap_total,
        'total_deals':   len(lawton_deals),
        'top5_clients':  top5_clients,
        'top5_products': top5_products,
        'top5_underlying': top5_underlying,
        'dist_ndf':      len(ndf_lawton),
        'dist_opt':      len(optcomm_lawton),
        'dist_fxo':      len(fxo_lawton),
        'dist_swap':     len(swap_lawton),
        'monthly_opt':   monthly_opt,
        'monthly_ndf':   monthly_ndf,
        'monthly_fxo':   monthly_fxo,
        'monthly_swap':  monthly_swap,
        'recent_deals':  recent_deals,
    })


# Live Position entity breakdown. The Banco (holder 73760) is a party to EVERY
# intragroup trade, so its bucket AGGREGATES all operations it faces against the
# four intragroup counterparty accounts below (its own 73760.10-2 book + Lawton +
# MGT + Atacama). Lawton/MGT/Atacama remain their own counterparty-specific tallies.
# Order fixed as Banco → Lawton → MGT → Atacama.
_LIVE_ENTITY_MAP = {
    '73760009': 'BANCO',    # holder book 73760.00-9 (mock data)
    '73760102': 'BANCO',    # Banco counterparty book 73760.10-2
    '00041007': 'LAWTON',   # 00041.00-7
    '04880006': 'MGT',      # 04880.00-6
    '85398005': 'ATACAMA',  # 85398.00-5
}
_LIVE_ENTITY_ORDER = ['BANCO', 'LAWTON', 'MGT', 'ATACAMA']
# Counterparties whose trades the BANCO bucket aggregates (all intragroup).
_LIVE_BANCO_COUNTERPARTIES = {'BANCO', 'LAWTON', 'MGT', 'ATACAMA'}

# Every standard product is listed even at 0 (mirrors the Settlement Forecast
# card), so the bar set is stable and never "loses" a product — e.g. Swap CEMHYB —
# just because the current snapshot happens to have none. COE is tracked but not
# yet counted (no logic wired) — shows 0 until the counting rule arrives.
_LIVE_PLACEHOLDER_PRODUCTS = ['NDF Moeda', 'NDF Commodities', 'Option FXO',
                             'Option Commodities', 'Option EDG',
                             'SWAP CEM', 'SWAP EDG', 'SWAP CEMHYB', 'COE']
# Fixed display order for the Live Position product bar (unknown products last).
_LIVE_PRODUCT_ORDER = {p: i for i, p in enumerate(_LIVE_PLACEHOLDER_PRODUCTS)}


def _live_map_entity(raw):
    """Like _fcst_map_entity but keeps BANCO (holder account) in the breakdown."""
    s = (raw or '').strip()
    if not s:
        return None
    digits = ''.join(ch for ch in s if ch.isdigit())
    if digits in _LIVE_ENTITY_MAP:
        return _LIVE_ENTITY_MAP[digits]
    up = s.upper()
    for nm in _LIVE_ENTITY_ORDER:
        if nm in up:
            return nm
    return None


# One entry per B3 position (DPOSICAO*) snapshot file. Each row = one live
# operation still in custody on the reference date. Product/entity resolved by
# name token (reusing the forecast classifiers) so it survives header drift.
_LIVE_POSITION_SOURCES = [
    {'key': 'ndf', 'label': 'NDF', 'category': 'NDF',
     'file': lambda r: '73760_{}_DPOSICAO-TER.json'.format(r),
     'entity': ['titular', 'contraparte', 'parte', 'conta'],
     'product': ('ndfclass', ['classe do ativo', 'ativo subjacente', 'mercadoria', 'classe'])},
    {'key': 'opc', 'label': 'Options', 'category': 'Option',
     'file': lambda r: '73760_{}_DPOSICAO.json'.format(r),
     'entity': ['titular', 'contraparte', 'conta'],
     'product': ('optclass', ['classe do ativo subjacente', 'classe do ativo', 'classe'])},
    {'key': 'swap', 'label': 'Swap', 'category': 'Swap',
     'file': lambda r: '73760_{}_DPOSICAO-SWAP.json'.format(r),
     'entity': ['contraparte', 'titular', 'parte'],
     'product': ('lob', ['código identificador', 'codigo identificador', 'identificador'])},
]


@blueprint.route('/api/dashboard-live-position')
def api_dashboard_live_position():
    """Snapshot of open operations still in custody on a reference date, read from
    the B3 position (DPOSICAO*) JSONs. Independent of the trade-date period filter:
    it's a photo of current inventory. `date` (YYYY-MM-DD) defaults to D-1 ANBIMA."""
    if not session.get('authenticated'):
        return jsonify({'error': 'unauthorized'}), 401

    date_str = request.args.get('date')
    ref = None
    if date_str:
        try:
            ref = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            ref = None
    if ref is None:
        ref = _prev_anbima_bizday(datetime.now())
    dref = ref.strftime('%y%m%d')

    by_product, by_entity = {}, {}
    sources = []
    for src in _LIVE_POSITION_SOURCES:
        path = os.path.join(B3_JSON_ROOT, src['category'], _b3_date_subpath(dref), src['file'](dref))
        st = {'label': src['label'], 'file': os.path.basename(path), 'found': False, 'count': 0}
        if not os.path.isfile(path):
            sources.append(st)
            continue
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                rows = json.load(fh)
        except Exception:
            sources.append(st)
            continue
        st['found'] = True
        if not rows:
            sources.append(st)
            continue
        keys = list(rows[0].keys())
        ent_key = _fcst_resolve_key(keys, src['entity'])
        pmode, pspec = src['product']
        prod_key = _fcst_resolve_key(keys, pspec)
        cnt = 0
        for row in rows:
            if pmode == 'ndfclass':
                product = _fcst_ndf_product(row.get(prod_key, '') if prod_key else '')
            elif pmode == 'optclass':
                product = _fcst_opt_class_product(row.get(prod_key, '') if prod_key else '')
            elif pmode == 'lob':
                product = 'SWAP ' + _fcst_lob(row.get(prod_key, '') if prod_key else '')
            else:
                product = src['label']
            by_product[product] = by_product.get(product, 0) + 1
            ent = _live_map_entity(row.get(ent_key, '')) if ent_key else None
            if ent:
                # Counterparty-specific bucket (LAWTON / MGT / ATACAMA / Banco own book).
                by_entity[ent] = by_entity.get(ent, 0) + 1
                # BANCO aggregates EVERY intragroup trade it is a party to. A row
                # already resolving to BANCO (its own 73760.10-2 book) is counted
                # once above; Lawton/MGT/Atacama rows add to BANCO on top of their
                # own tally.
                if ent in _LIVE_BANCO_COUNTERPARTIES and ent != 'BANCO':
                    by_entity['BANCO'] = by_entity.get('BANCO', 0) + 1
            cnt += 1
        st['count'] = cnt
        sources.append(st)

    # Only surface the product bar when there is real position data. COE (and any
    # other placeholder) is always shown at 0 alongside the real products.
    if by_product:
        for p in _LIVE_PLACEHOLDER_PRODUCTS:
            by_product.setdefault(p, 0)
    product_rows = [{'label': k, 'count': by_product[k]}
                    for k in sorted(by_product, key=lambda k: (_LIVE_PRODUCT_ORDER.get(k, 999), k))]
    entity_rows = [{'label': k, 'count': by_entity[k]}
                   for k in _LIVE_ENTITY_ORDER if k in by_entity]
    return jsonify({
        'ref_date':     ref.strftime('%Y-%m-%d'),
        'ref_date_fmt': ref.strftime('%d/%m/%Y'),
        'total':        sum(by_product.values()),
        'by_product':   product_rows,
        'by_entity':    entity_rows,
        'sources':      sources,
    })


@blueprint.route('/about')
def about():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/about.html', segment='about')


@blueprint.route('/control-panel')
def control_panel():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    cetip_default_date = _prev_anbima_bizday(datetime.now()).strftime('%Y-%m-%d')
    return render_template('pages/control-panel.html', segment='control-panel',
                           cetip_default_date=cetip_default_date)


# ============================================================================
#  CONTROL PANEL — Daily Settlement routines
# ============================================================================
#
#  Routine: "Salvar Arquivos CETIP" — Python translation of the Alteryx flow
#  (Directory → Filter → DynamicInput → Formula → Select → DbFileOutput → Email).
#
#  It reads the raw CETIP files B3 drops in the daily download folder, filters
#  them by type, renames each to the standard `73760_{YYMMDD}_{TYPE}` convention
#  and saves them into a single per-day destination folder the KPI process reads.
#  Two HTML e-mails are then sent from the OTC Tracker mailbox (best-effort):
#  one to Brazil OTC Ops and one to Brazil Sales Support MO (cc Ops).
#
#  Source folder (per run):  CETIP_SOURCE_ROOT\{YYYY}\{mm. Month}\{DD}
#  Destination folder:       CETIP_DEST_ROOT\{YYYY}\{mm. Month}\{DD}
#  (both keyed on the reference date; the file date in the rename still comes
#   from the source filename via Substring)
# ----------------------------------------------------------------------------
CETIP_SOURCE_ROOT = os.getenv('CETIP_SOURCE_ROOT',
                              r'I:\Confirmation\Derivativos\OTC Tracker\Alteryx\Posição B3\ARQUIVOS CETIP')
CETIP_DEST_ROOT   = os.getenv('CETIP_DEST_ROOT',
                              r'I:\Confirmation\Derivativos\OTC Tracker\CETIP Files\Position Files')
# Use the PRIMARY SMTP address (jpmorgan.com) — the jpmchase.com one is a
# secondary alias and the relay was not delivering to it.
CETIP_OTC_OPS_EMAIL       = os.getenv('CETIP_OTC_OPS_EMAIL',       'brazil.otc.ops@jpmorgan.com')
CETIP_SALES_SUPPORT_EMAIL = os.getenv('CETIP_SALES_SUPPORT_EMAIL', 'brazil_sales_support_mo@jpmchase.com')
# CEM Latam BA (Buenos Aires CIB Ops) — receive the Option Position .OPC file, cc OTC Ops.
CETIP_CEM_LATAM_EMAILS    = [e.strip() for e in os.getenv(
    'CETIP_CEM_LATAM_EMAILS',
    'lautaro.larriera@jpmchase.com,sacha.yebrin@jpmchase.com,candela.ferreiro@jpmorgan.com,'
    'martina.rambert@jpmchase.com,mercedes.e.mino@jpmchase.com').split(',') if e.strip()]


def _ensure_cetip_roots():
    """At server start, make sure the CETIP source/destination ROOT folders exist;
    create them if missing. Windows-only (the I:\\ paths are JPM network paths) —
    skipped elsewhere so dev machines don't create junk dirs from backslash paths."""
    if os.name != 'nt':
        return
    for root in (CETIP_SOURCE_ROOT, CETIP_DEST_ROOT):
        try:
            if not os.path.isdir(root):
                os.makedirs(root, exist_ok=True)
                log.info("[cetip] created root folder: %s", root)
        except Exception:
            log.warning("[cetip] could not create root %s:\n%s", root, traceback.format_exc())

_ensure_cetip_roots()

# Network shares for the secondary (flat) copies of two types, mirroring the
# Alteryx second outputs (commented date subfolder → flat folder).
CETIP_OPTIONS_SHARE = os.getenv('CETIP_OPTIONS_SHARE', r'I:\CETIP_OPTIONS')
CETIP_NDF_SHARE     = os.getenv('CETIP_NDF_SHARE',     r'I:\CETIP_NDF')

# Each rule mirrors one Filter→Formula→Output branch of the Alteryx container.
#   match      : predicate on the LOWER-CASED source FileName (case-insensitive,
#                so .TXT / .txt both match — Alteryx Contains was the reference)
#   date_start : 0-based offset of the YYMMDD date inside the FileName (Alteryx
#                Substring) — 6 for OPCAO_*, 4 for *-TER/*SIC, 8 for the CETIP21
#   dest_name  : builds the renamed output FileName from the YYMMDD ref
#   extra_dest : (optional) a flat network-share folder to also copy the file to
# Destination is a single per-day folder (CETIP_DEST_ROOT\YYYY\mm. Month\dd),
# so the per-type subfolders of the original Alteryx flow are not used here.
_CETIP_RULES = [
    {'label': 'NDF Position (DPOSICAO C21)',
     'match': lambda n: 'dposicao_c21.txt' in n,
     'date_start': 8,
     'dest_name': lambda r: '73760_{}_DPOSICAO.CETIP21'.format(r)},
    {'label': 'SWAP Position (DPOSICAO-SWAP)',
     'match': lambda n: 'dposicao-swap.txt' in n,
     'date_start': 8,
     'dest_name': lambda r: '73760_{}_DPOSICAO-SWAP.CETIP21'.format(r),
     'attach_sales_support': True,      # SWAP position also e-mailed to Sales Support
     'json': {'category': 'Swap', 'has_header': False, 'header_key': 'swap_position',
              # de-dup: Conta Parte (coluna D = "Participante")
              'filter': {'column': ['participante'], 'index': 3,
                         'allowed': ['73760009', '04880006']}}},
    {'label': 'Option Position (OPC DPOSICAO)',
     'match': lambda n: 'opc_' in n and '_dposicao.txt' in n,
     'date_start': 4,                  # OPC_YYMMDD_DPOSICAO.TXT → date at index 4
     'dest_name': lambda r: '73760_{}_DPOSICAO.OPC'.format(r),
     'extra_dest': CETIP_OPTIONS_SHARE,
     'attach_cem_latam': True,          # this .OPC file is e-mailed to CEM Latam BA
     'attach_sales_support': True,      # .OPC position also e-mailed to Sales Support
     'json': {'category': 'Option', 'has_header': True,
              # de-dup: keep only our side (Parte/conta = coluna E)
              'filter': {'column': ['parte (conta)', 'parte(conta)', 'parte'], 'index': 4,
                         'allowed': ['73760009']}}},
    {'label': 'Option Movement (OPC DMOVIMENTO)',
     'match': lambda n: ('opc_' in n and '_dmovimento.txt' in n
                         and '_15h00.txt' not in n and '_18h30.txt' not in n),
     'date_start': 4,                  # OPC_YYMMDD_DMOVIMENTO.TXT → date at index 4
     'dest_name': lambda r: '73760_{}_DMOVIMENTO_3.OPC'.format(r)},
    {'label': 'Term Movement (DMOVIMENTO C21)',
     'match': lambda n: '_dmovimento_c21.txt' in n,
     'date_start': 8,
     'dest_name': lambda r: '73760_{}_DMOVIMENTO.CETIP21'.format(r)},
    {'label': 'SWAP Movement (DMOVIMENTO-SWAP)',
     'match': lambda n: '_dmovimento-swap.txt' in n,
     'date_start': 8,
     'dest_name': lambda r: '73760_{}_DMOVIMENTO-SWAP.CETIP21'.format(r)},
    {'label': 'SWAP Flow (DFLUXO_SWAP)',
     'match': lambda n: '_dfluxo_swap.txt' in n,
     'date_start': 8,
     'dest_name': lambda r: '73760_{}_DFLUXO.CETIP21'.format(r),
     'json': {'category': 'Swap', 'has_header': False, 'header_key': 'swap_fluxo',
              # de-dup: Conta Parte (coluna C = "Código Conta Cetip Parte")
              'filter': {'column': ['código conta cetip parte', 'codigo conta cetip parte',
                                    'conta cetip parte'], 'index': 2,
                         'allowed': ['73760009', '04880006']}}},
    {'label': 'SWAP Premium Agenda (DAGENDAPREMIOS)',
     'match': lambda n: '_dagendapremios.txt' in n,
     'date_start': 8,                  # CETIP21_YYMMDD_DAGENDAPREMIOS.TXT → date at index 8
     'dest_name': lambda r: '73760_{}_DAGENDAPREMIOS.CETIP21'.format(r),
     'json': {'category': 'Swap', 'has_header': False, 'header_key': 'swap_premio',
              # de-dup: Conta da Parte (coluna D = "Parte")
              'filter': {'column': ['parte'], 'index': 3,
                         'allowed': ['73760009', '04880006']}}},
    {'label': 'SWAP Indexers (INDEXADORESSWAP_VCP)',
     'match': lambda n: 'indexadoresswap_vcp.txt' in n,
     'date_start': 8,                  # CETIP21_YYMMDD_INDEXADORESSWAP_VCP.TXT → date at index 8
     'dest_name': lambda r: 'CETIP21_{}_INDEXADORESSWAP_VCP.TXT'.format(r),
     # Not a position file: after saving, its rows refresh the VCP indexer
     # reference JSON (see _cetip_update_vcp_json), used by the Swap Characteristics
     # page. A=Qualification ID, B=Description, C=Additional Description,
     # D=Level 1 Classification, E=Status (Habilitado→Active / Bloqueado→Inactive).
     'vcp_update': True},
    {'label': 'Operations (DOPERACOES)',
     'match': lambda n: '_doperacoes.txt' in n,
     'date_start': 8,
     'dest_name': lambda r: '73760_{}_DOPERACOES.CETIP21'.format(r),
     'json': {'category': 'Operations', 'has_header': False, 'header_key': 'operations'}},
    {'label': 'COE (DRESUMOEMISSOR-COE)',
     'match': lambda n: '_dresumoemissor-coe.txt' in n,
     'date_start': 8,
     'dest_name': lambda r: 'CETIP21_{}_SP_DRESUMOEMISSOR-COE.TXT'.format(r)},
    {'label': 'Accelerator Agent (MID DAGENTEACELERADOR)',
     'match': lambda n: '_mid_dagenteacelerador.txt' in n,
     'date_start': 8,
     'dest_name': lambda r: '73760_{}_MID_DAGENTEACELERADOR.CETIP21'.format(r)},
    {'label': 'Term Position (DPOSICAO-TER)',
     'match': lambda n: '_dposicao-ter.txt' in n,
     'date_start': 4,
     'dest_name': lambda r: '73760_{}_DPOSICAO-TER.TER'.format(r),
     'extra_dest': CETIP_NDF_SHARE,
     'attach_sales_support': True,      # .TER position also e-mailed to Sales Support
     'json': {'category': 'NDF', 'has_header': True,
              # de-dup: keep only our side (Código da Parte = coluna B)
              'filter': {'column': ['código da parte', 'codigo da parte'], 'index': 1,
                         'allowed': ['73760009', '04880006']}}},
    {'label': 'SIC Contract Position (DPOSCONTRATOSIC)',
     'match': lambda n: '_dposcontratosic.txt' in n,
     'date_start': 4,
     'dest_name': lambda r: '73760_{}_DPOSCONTRATOSIC.txt'.format(r),
     'attach_sales_support': True},   # this file is e-mailed to Sales Support
    {'label': 'Comitente Registry (DCADCOMITENTES)',
     'match': lambda n: '_dcadcomitentes.txt' in n,
     'date_start': 4,                 # SIC_YYMMDD_DCADCOMITENTES.TXT → date at index 4
     # Keep the original SIC name so the Comitente reconciliation finds it unchanged.
     'dest_name': lambda r: 'SIC_{}_DCADCOMITENTES.txt'.format(r)},
]


# ── B3 JSON export (feeds the Settlement Forecast) ────────────────────────────
# While saving the CETIP files, the relevant position files are ALSO parsed into
# tidy JSON under static/data/B3 Files/<category>/, so downstream routines (the
# Settlement Forecast) read named fields instead of guessing column positions.
#   NDF    → TER files          (DPOSICAO-TER)         — file has its own header
#   Option → OPC files          (DPOSICAO.OPC)         — file has its own header
#   Swap   → SWAP position/flow/premium agenda          — HEADERLESS: column names
#            come from _B3_SWAP_HEADERS (stored standard, keyed per file type)
B3_JSON_ROOT = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'cache', 'b3 files')
ACCRUAL_JSON_ROOT = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'cache', 'accrual')
# Network folder the VCP / CEM / EDG / HYB source files are dropped into, per run.
# Layout: ACCRUAL_SOURCE_ROOT\{YYYY}\{mm. Month}\{DD} (run = last ANBIMA bizday of the
# month). Only reachable on the JPM environment; override with the env var off-site.
ACCRUAL_SOURCE_ROOT = os.getenv('ACCRUAL_SOURCE_ROOT',
                                r'I:\Confirmation\Derivativos\OTC Tracker\Regulatory\Accrual')

# Standard column headers for the HEADERLESS SWAP-family files (';'-delimited),
# in file order. These are the authoritative field names (the SWAP files ship with
# no header row). Stored as raw ';' strings and split on load. NOTE: the SWAP
# position layout repeats several column names (e.g. "Percentual", "Data de
# Cotação"); _b3_export_json de-duplicates repeats by appending _2, _3, …
_B3_SWAP_HEADERS_RAW = {
    # 73760_*_DPOSICAO-SWAP.CETIP21
    'swap_position': (
        "Tipo de Contrato;Data;Contrato;Participante;CPF/CNPJ Cliente Parte;Cesta Garantias Parte;"
        "Comissão Parte;Contraparte;CPF/CNPJ Cliente Contraparte;Cesta Garantias Contraparte;"
        "Comissão Contraparte;Data início;Data vencimento;Tipo de Adesão;Valor base;"
        "Valor Base Remanescente;Valor Antecipado;Saldo;Sinal Saldo;Data do Saldo;Funcionalidade;"
        "Agenda de Prêmio;Reset;Observação;Valor base inicial;Data operação termo;Índice Termo;"
        "Percentual Termo;PU Inicial;Tipo/Classe;Nome Tipo/Classe;Denominação;Juros a cada;"
        "Expresso em;Data inicio pagamento juros;Amortização a cada;Expresso em;"
        "Data inicio pagamento amortização;Tipo de amortização;Percentual;Código índice;TR Escolhida;"
        "Sinal Taxa;Taxa;Lim. Inferior (Floor);Lim. Superior (Cap);Valor Curva Atualizado;"
        "Data Correção;Fator Original de Juros;Percentual;Código índice;TR Escolhida;Sinal Taxa;Taxa;"
        "Lim. Inferior (Floor);Lim. Superior (Cap);Valor Curva Atualizado;Data Correção;"
        "Fator Original de Juros;Parte/Contraparte;Cupom Limpo;Percentual;Curva;Sinal Taxa;"
        "Taxa de Juros;Limitador;Pu inicial;Pu atual;Tipo/Classe;Nome Tipo/Classe;Denominação;"
        "Pu inicial;Pu atual;Tipo/Classe;Nome Tipo/Classe;Denominação;Cupom Limpo;Data de Cotação;"
        "Cupom Limpo;Data de Cotação;Tipo Libor - moeda;Tipo Libor - período;Data de Cotação;"
        "Variação Cambial;Tipo Classe;Nome Tipo/Classe;Outros - Cotação;Alíquota - IR;"
        "Limite inferior (FLOOR) - Perc.;Limite superior (CAP) - Perc.;Tipo Libor - moeda;"
        "Tipo Libor - período;Data de Cotação;Variação Cambial;Tipo Classe;Nome Tipo/Classe;"
        "Outros - Cotação;Alíquota - IR;Limite inferior (FLOOR) - Perc.;Limite superior (CAP) - Perc.;"
        "Taxa Juros;Troca de Fluxo;Variação Cambial;Tipo Classe;Nome Tipo/Classe;Outros - Cotação;"
        "Alíquota - IR;Limite inferior (FLOOR) - Perc.;Limite superior (CAP) - Perc.;Taxa Juros;"
        "Troca de Fluxo;Variação Cambial;Tipo Classe;Nome Tipo/Classe;Outros - Cotação;Alíquota - IR;"
        "Limite inferior (FLOOR) - Perc.;Limite superior (CAP) - Perc.;Parte/Contraparte;"
        "Fator/Valor/Taxa;Verificação;Data Disparo;Parte/Contraparte;Fator/Valor/Taxa;Verificação;"
        "Data Disparo;Titular;Prêmio 1;Rebate;Liquidação do Rebate;Dias Úteis após o Trigger Out;"
        "Prêmio 2;Data Exercício Prêmio 2;Estratégia;Amortiza sem Troca de Diferencial;"
        "Data da Cotação - Variação Cambial;Data da Cotação - Variação Cambial;Cotação Inicial;"
        "Código Commodity;Media Asiática Verificação;Data Cotação para Ajuste;Cotação Inicial;"
        "Código Commodity;Media Asiática Verificação;Data Cotação para Ajuste;Código Identificador;"
        "Data de Cotação Final – Termo;Tipo de Cotação (Parte);Tipo de Cotação (Contraparte);"
        "Data Liquidação;Cotação Inicial Moeda Parte;Metodologia de composição da taxa Parte;"
        "Deslocamento da taxa Parte;Expressão Juros Parte;Alíquota IR (em %) Parte;"
        "Cotação Inicial Moeda Contraparte;Metodologia de composição da taxa Contraparte;"
        "Deslocamento da taxa Contraparte;Expressão Juros Contraparte;Alíquota IR (em %) Contraparte;"
        "Data de Fixing IPCA (Parte);Data de Fixing IPCA (Contraparte);Sinal Spread (Parte);"
        "Spread (Parte);Sinal Spread (Contraparte);Spread (Contraparte);Variação Cambial;"
        "Cotação Inicial Moeda;Variação Cambial;Cotação Inicial Moeda"
    ),
    # 73760_*_DFLUXO.CETIP21
    'swap_fluxo': (
        "Código do contrato;Tipo Sistema;Código Conta Cetip Parte;Nome Simplificado Parte;"
        "Papel Parte;Código Conta Cetip Contraparte;Nome Simplificado Contraparte;Papel Contraparte;"
        "Tipo Amortização;Data Pagamento de Juros;Código Identificador;Data de ocorrência do Evento;"
        "Sinal Juros Parte;Taxa de Juros Parte;Limite Inferior Parte;Limite Superior Parte;"
        "Taxa Amortização;Sinal Juros Contraparte;Taxa de Juros Contraparte;Limite Inferior Contraparte;"
        "Limite Superior Contraparte;Taxa Amortização;Data Início Composição da Taxa Parte;"
        "Data Final Composição da Taxa Parte;Data Fixing Moeda Parte;"
        "Data Início Composição da Taxa Contraparte"
    ),
    # 73760_*_DAGENDAPREMIOS.CETIP21
    'swap_premio': (
        "Codigo do Contrato;Data;ID do Sistema;Parte;Nome Simplificado;Data do Evento;"
        "Operacao;Valor;Titular;Estado"
    ),
    # 73760_*_DOPERACOES.CETIP21
    'operations': (
        "Participante (Nome Simpl.);Conta;Liquidante;Cod.Operacao;Tipo Operacao;C/V;"
        "Tipo Compra/Venda;Titulo;Codigo IF Anterior;Tipo Titulo;Data Emissao;Data Vencimento;"
        "Quantidade;PU;Valor;Tx Colocacao;Sistema;Modalidade Liquidacao;Status;Numero Operacao;"
        "Numero Associacao;Data Liquidacao;Data Origem;Instituicao Confirmadora(Conta);"
        "Instituicao Confirmadora(Papel);Contraparte (Nome Simpl.);Conta Contraparte;"
        "Data Compromisso;PU/Ida Compromisso;Numero Operacao Original;"
        "Data da Operacao Original/Data Operacao Original da Antecipacao;PU Op Original;"
        "Qtd Op Original;ISPB Liq. Contraparte;Nu Op Msg;Num Ctrl Operacao;Programa de Emissao"
    ),
}
_B3_SWAP_HEADERS = {k: [h.strip() for h in v.split(';')]
                    for k, v in _B3_SWAP_HEADERS_RAW.items()}


def _b3_date_subpath(dref):
    """YYMMDD ref → 'YYYY/MM/DD' subfolders so the per-day JSON files are split by
    year/month/day inside each product folder. '' if the ref can't be parsed."""
    try:
        d = datetime.strptime(dref, '%y%m%d')
    except (ValueError, TypeError):
        return ''
    return os.path.join(d.strftime('%Y'), d.strftime('%m'), d.strftime('%d'))


def _b3_export_json(src_path, json_cfg, dest_name, dref):
    """Parse a saved CETIP file into a list-of-dicts JSON under
    B3 Files/<category>/YYYY/MM/DD/<dest_name>.json. Header files use their own
    first line; headerless files use the stored standard header
    (_B3_SWAP_HEADERS) or positional Field_N names. Best-effort — returns the
    JSON path on success or None on failure."""
    try:
        with open(src_path, 'r', encoding='latin-1', newline='') as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        if not lines:
            return None

        if json_cfg.get('has_header'):
            header = [h.strip() for h in lines[0].split(';')]
            data_lines = lines[1:]
        else:
            header = list(_B3_SWAP_HEADERS.get(json_cfg.get('header_key', ''), []) or [])
            data_lines = lines

        # De-duplicate repeated header names (SWAP position repeats many) so no
        # field is silently overwritten: 1st keeps its name, repeats get _2, _3…
        uniq_header = []
        if header:
            seen = {}
            for h in header:
                seen[h] = seen.get(h, 0) + 1
                uniq_header.append(h if seen[h] == 1 else '{}_{}'.format(h, seen[h]))

        rows = []
        for ln in data_lines:
            fields = ln.split(';')
            if uniq_header:
                row = {}
                for i, val in enumerate(fields):
                    key = uniq_header[i] if i < len(uniq_header) else 'Field_{}'.format(i + 1)
                    row[key] = val.strip()
            else:                              # no stored header → positional names
                row = {'Field_{}'.format(i + 1): v.strip() for i, v in enumerate(fields)}
            rows.append(row)

        # Optional de-dup filter: keep only rows whose <column> value is allowed.
        filt = json_cfg.get('filter')
        if filt and rows:
            keys = list(rows[0].keys())
            col_key = None
            for tok in filt.get('column', []):
                for k in keys:
                    if tok in k.lower():
                        col_key = k
                        break
                if col_key:
                    break
            if col_key is None and 'index' in filt:
                ix = filt['index']
                col_key = keys[ix] if ix < len(keys) else None
            def _digits(s):
                return ''.join(ch for ch in str(s) if ch.isdigit())
            allowed = set(_digits(a) for a in filt.get('allowed', []))
            if col_key and allowed:
                before = len(rows)
                rows = [r for r in rows if _digits(r.get(col_key, '')) in allowed]
                log.info("[b3-json] %s filter on %r kept %d/%d rows",
                         os.path.basename(dest_name), col_key, len(rows), before)
            elif not col_key:
                log.warning("[b3-json] %s filter column not found (tokens=%s, index=%s)",
                            os.path.basename(dest_name), filt.get('column'), filt.get('index'))

        out_dir = os.path.join(B3_JSON_ROOT, json_cfg['category'], _b3_date_subpath(dref))
        os.makedirs(out_dir, exist_ok=True)
        json_name = os.path.splitext(dest_name)[0] + '.json'
        json_path = os.path.join(out_dir, json_name)
        with open(json_path, 'w', encoding='utf-8') as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2)
        return json_path
    except Exception:
        log.warning("[b3-json] export failed for %s:\n%s", src_path, traceback.format_exc())
        return None


def _cetip_save_file(src_path, dest_path):
    """Replicate the Alteryx DynamicInput→DbFileOutput pass: read the raw file as
    Latin-1 (CodePage 28591) and rewrite it with CRLF line endings to the new
    location. Latin-1 is a byte-for-byte mapping, so content is preserved; only
    line endings are normalised to CRLF — matching what the KPI process expects."""
    with open(src_path, 'r', encoding='latin-1', newline='') as f:
        lines = f.read().splitlines()
    out = '\r\n'.join(lines)
    if lines:
        out += '\r\n'
    with open(dest_path, 'w', encoding='latin-1', newline='') as f:
        f.write(out)


# Existing VCP qualification table (Descrição/Classificação/STATUS per Qualification
# ID) — the Save CETIP Files routine refreshes it in place from the
# INDEXADORESSWAP_VCP file. Also read by the Swap Characteristics page and index-b3.
VCP_JSON = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'VCP.json')


def _cetip_update_vcp_json(src_path):
    """Refresh the existing VCP.json IN PLACE from the saved INDEXADORESSWAP_VCP
    file (';'-delimited, Latin-1). File columns: A=Qualification ID, B=Description,
    C=Additional Description, D=Level 1 Classification, E=Status (Habilitado →
    ACTIVE / Bloqueado → INACTIVE).

    Upsert by "ID da Qualificação": existing rows have their STATUS/descriptions/
    classification updated (MAKER/CHECKER preserved); new IDs are appended with
    Produto=SWAP. Rows not present in the file (e.g. the OPC entries) are left
    untouched. Best-effort — returns the path or None."""
    try:
        with open(src_path, 'r', encoding='latin-1', newline='') as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        if not lines:
            return None
        # Skip a header row if the file ships with one.
        first = [c.strip().lower() for c in lines[0].split(';')]
        if any('qualif' in c or c == 'status' or 'classif' in c or 'descri' in c for c in first):
            lines = lines[1:]

        # Load the existing table + index by Qualification ID (as string).
        current = []
        if os.path.isfile(VCP_JSON):
            try:
                with open(VCP_JSON, encoding='utf-8') as fh:
                    current = json.load(fh) or []
            except Exception:
                current = []
        by_id = {str(r.get('ID da Qualificação')): r for r in current}

        added = updated = 0
        for ln in lines:
            f = ln.split(';')
            def g(i):
                return f[i].strip() if i < len(f) else ''
            qid_raw = g(0)
            if not qid_raw:
                continue
            try:
                qid = int(''.join(ch for ch in qid_raw if ch.isdigit() or ch == '-'))
            except ValueError:
                qid = qid_raw
            st = _fcst_norm(g(4))
            status = 'ACTIVE' if 'habilitad' in st else ('INACTIVE' if 'bloquead' in st else g(4))
            row = by_id.get(str(qid))
            if row is None:
                current.append({
                    'STATUS':                              status,
                    'ID da Qualificação':                  qid,
                    'Descrição da Qualificação':           g(1),
                    'Descrição Adicional da Qualificação': g(2),
                    'Classificação Nível 1':               g(3),
                    'Produto':                             'SWAP',
                    'MAKER':                               None,
                    'CHECKER':                             None,
                })
                by_id[str(qid)] = current[-1]
                added += 1
            else:
                row['STATUS'] = status
                row['Descrição da Qualificação'] = g(1)
                row['Descrição Adicional da Qualificação'] = g(2)
                row['Classificação Nível 1'] = g(3)
                updated += 1

        with open(VCP_JSON, 'w', encoding='utf-8') as fh:
            json.dump(current, fh, ensure_ascii=False, indent=2)
        log.info("[cetip] VCP.json refreshed: %d updated, %d added (%d total)",
                 updated, added, len(current))
        return VCP_JSON
    except Exception:
        log.warning("[cetip] VCP.json update failed:\n%s", traceback.format_exc())
        return None


def _send_cetip_email(to_list, cc_list, subject, greeting, message_html,
                      ref_date_fmt, saved, dest_folder='', attachments=None, missing=None):
    """Render the CETIP HTML template and send it FROM the OTC Tracker mailbox
    (SHARED_MAILBOX) with the embedded logo (cid:otc_logo) and optional file
    attachments. Best-effort — returns True on success or an error string."""
    from email.mime.image import MIMEImage
    from email.mime.base import MIMEBase
    from email import encoders
    attachments = attachments or []
    missing = missing or []
    try:
        attach_names = [os.path.basename(p) for p in attachments]
        html = render_template(
            'pages/email-template-cetip-saved.html',
            subject=subject, greeting=greeting, message_html=message_html,
            ref_date_fmt=ref_date_fmt, file_count=len(saved), saved_files=saved,
            missing_files=missing, missing_count=len(missing),
            attachment_names=attach_names, dest_folder=dest_folder,
            current_year=datetime.now().year)

        # mixed > [ related > [ alternative > [plain, html], logo ], attachment... ]
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = SHARED_MAILBOX
        msg['To'] = ', '.join(to_list)
        if cc_list:
            msg['Cc'] = ', '.join(cc_list)

        related = MIMEMultipart('related')
        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText('CETIP files saved.', 'plain', 'utf-8'))
        alt.attach(MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)

        logo_path = _get_logo_path()
        if logo_path:
            with open(logo_path, 'rb') as f:
                img = MIMEImage(f.read())
            img.add_header('Content-ID', '<otc_logo>')
            img.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(img)
        msg.attach(related)

        for path in attachments:
            try:
                with open(path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment',
                                filename=os.path.basename(path))
                msg.attach(part)
            except Exception:
                log.warning("[cetip] could not attach %s:\n%s", path, traceback.format_exc())

        recipients = list(to_list) + list(cc_list or [])
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.sendmail(SHARED_MAILBOX, recipients, msg.as_string())
        log.info("[cetip] e-mail '%s' sent to %s", subject, recipients)
        return True
    except Exception as e:
        log.error("[cetip] e-mail '%s' FAILED:\n%s", subject, traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)   # error string surfaced to the UI


def _cetip_distribute_emails(ref, dest_dir, send_mail):
    """Stage 2 of Save CETIP Files ("Send to other areas"): e-mail Sales Support
    (SIC + Term/Option/SWAP positions) and CEM Latam BA (.OPC) with the files that
    stage 1 already saved to dest_dir — no re-save. Attachment paths are rebuilt
    from each rule's deterministic dest name for the reference date."""
    if not os.path.isdir(dest_dir):
        return jsonify({'success': False,
                        'error': 'No saved files found for this date. Run "Save CETIP Files" first.'}), 400
    ref_yymmdd = ref.strftime('%y%m%d')
    ref_fmt    = ref.strftime('%d/%m/%Y')
    attach_paths, attach_saved = [], []   # Sales Support (SIC + positions)
    opc_paths,    opc_saved    = [], []   # CEM Latam (.OPC)
    for rule in _CETIP_RULES:
        if not (rule.get('attach_sales_support') or rule.get('attach_cem_latam')):
            continue
        try:
            dest_name = rule['dest_name'](ref_yymmdd)
        except Exception:
            continue
        dest_path = os.path.join(dest_dir, dest_name)
        if not os.path.isfile(dest_path):
            continue
        entry = {'src': dest_name, 'dest': dest_name, 'type': rule['label']}
        if rule.get('attach_sales_support'):
            attach_paths.append(dest_path); attach_saved.append(entry)
        if rule.get('attach_cem_latam'):
            opc_paths.append(dest_path); opc_saved.append(entry)

    if not attach_paths and not opc_paths:
        return jsonify({'success': False,
                        'error': 'No position files found for {}. Run "Save CETIP Files" first.'
                        .format(ref_fmt)}), 400

    mail_ss = mail_cem = None
    if send_mail:
        ss_msg = ('Please find attached the position files (Contract/SIC — DPOSCONTRATOSIC, '
                  'Term — DPOSICAO-TER.TER, Option — DPOSICAO.OPC, and SWAP — DPOSICAO-SWAP), '
                  'as requested. The complete list is shown below.' if attach_paths else
                  'The requested position files were not found for the reference date.')
        ss_subject = 'CETIP Consolidated - Corporate - {}'.format(ref_yymmdd)
        mail_ss = _send_cetip_email(
            [CETIP_SALES_SUPPORT_EMAIL], [CETIP_OTC_OPS_EMAIL], ss_subject,
            'Hello, Sales Support.', ss_msg,
            ref_fmt, attach_saved, attachments=attach_paths)

        cem_msg = ('Please find attached the option position file (DPOSICAO.OPC), '
                   'as requested.' if opc_paths else
                   'The DPOSICAO.OPC file was not found for the reference date.')
        cem_subject = 'CETIP Option Position - CEM Latam - {}'.format(ref_yymmdd)
        mail_cem = _send_cetip_email(
            CETIP_CEM_LATAM_EMAILS, [CETIP_OTC_OPS_EMAIL], cem_subject,
            'Hello CEM Latam BA,', cem_msg,
            ref_fmt, opc_saved, attachments=opc_paths)

    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'CETIP Files Distributed', 'Control Panel',
                         'Sales Support + CEM Latam ({})'.format(ref.strftime('%Y-%m-%d')))

    msg = 'Distribution e-mails sent for <b>{}</b>.'.format(ref_fmt)
    if send_mail:
        probs = [v for v in (mail_ss, mail_cem) if v is not True and v is not None]
        if not probs:
            msg = '<br>Distribution e-mails sent (Sales Support + CEM Latam).'
        else:
            msg = ('<span class="text-warning">Some distribution e-mails failed: {}</span>'
                   .format(probs[0]))
    return jsonify({'success': True, 'message': msg,
                    'email_sent': {'sales_support': mail_ss, 'cem_latam': mail_cem},
                    'destination': dest_dir})


@blueprint.route('/api/control-panel/cetip-settlement', methods=['POST'])
def api_cp_cetip_settlement():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    payload   = request.get_json(silent=True) or {}
    date_str  = (payload.get('date') or '').strip()
    send_mail = payload.get('send_email', True)
    # Two-stage split: 'save' (default) saves the files/JSONs + e-mails OTC Ops only;
    # 'distribute' only e-mails the other areas (Sales Support + CEM Latam) with the
    # already-saved position files — no re-save.
    stage     = (payload.get('stage') or 'save').strip().lower()

    try:
        ref = (datetime.strptime(date_str, '%Y-%m-%d') if date_str
               else _prev_anbima_bizday(datetime.now()))
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date (expected YYYY-MM-DD).'}), 400

    # Folder pattern: YYYY\mm. Month\dd (e.g. 2026\06. June\24) — same for source
    # and destination, both keyed on the reference date.
    month_folder = ref.strftime('%m') + '. ' + _EN_MONTH_NAMES[ref.month - 1]
    src_dir  = os.path.join(CETIP_SOURCE_ROOT, ref.strftime('%Y'), month_folder, ref.strftime('%d'))
    dest_dir = os.path.join(CETIP_DEST_ROOT,   ref.strftime('%Y'), month_folder, ref.strftime('%d'))

    # Stage 2 ("Send to other areas") — no re-save; e-mail Sales Support + CEM Latam
    # from the already-saved files. Requires stage 1 ("Save CETIP Files") to have run.
    if stage == 'distribute':
        return _cetip_distribute_emails(ref, dest_dir, send_mail)

    # Ensure the dated source folder exists (B3 daily drop). On Windows create it
    # in the standard layout if missing; on dev (POSIX) just error out cleanly.
    if not os.path.isdir(src_dir):
        if os.name == 'nt':
            try:
                os.makedirs(src_dir, exist_ok=True)
                log.info("[cetip] created source folder: %s", src_dir)
            except Exception:
                log.warning("[cetip] could not create source %s:\n%s", src_dir, traceback.format_exc())
        if not os.path.isdir(src_dir):
            return jsonify({'success': False,
                            'error': 'Source folder not found: {}'.format(src_dir)}), 400

    files = [f for f in os.listdir(src_dir) if os.path.isfile(os.path.join(src_dir, f))]
    if not files:
        return jsonify({'success': False,
                        'error': 'No files found in the source folder: {}'.format(src_dir)}), 400

    # Make sure the destination day folder exists before saving anything.
    os.makedirs(dest_dir, exist_ok=True)
    saved, errors = [], []
    # (Sales Support / CEM Latam attachments are gathered in stage 2 from dest_dir,
    # so stage 1 only saves + e-mails OTC Ops — see _cetip_distribute_emails.)

    # One pass per rule (mirrors the independent Alteryx branches). All matched
    # files land in the single per-day destination folder, renamed. Rules with no
    # matching source file are collected in `missing` so the e-mail can flag the
    # expected-but-absent files (expected name derived from the reference date).
    ref_yymmdd = ref.strftime('%y%m%d')
    missing = []
    for rule in _CETIP_RULES:
        rule_matched = False
        for name in files:
            if not rule['match'](name.lower()):
                continue
            rule_matched = True
            dref = name[rule['date_start']:rule['date_start'] + 6]
            if len(dref) < 6 or not dref.isdigit():
                errors.append({'file': name, 'type': rule['label'],
                               'error': 'Could not parse date from filename.'})
                continue
            dest_name = rule['dest_name'](dref)
            dest_path = os.path.join(dest_dir, dest_name)
            src_path  = os.path.join(src_dir, name)
            try:
                _cetip_save_file(src_path, dest_path)
                entry = {'src': name, 'dest': dest_name, 'type': rule['label']}
                saved.append(entry)
                # Also emit a tidy JSON (NDF / Option / Swap / Operations), split
                # into per-day folders (<category>/YYYY/MM/DD/).
                if rule.get('json'):
                    _b3_export_json(dest_path, rule['json'], dest_name, dref)
                # INDEXADORESSWAP_VCP → refresh the VCP indexer reference JSON.
                if rule.get('vcp_update'):
                    _cetip_update_vcp_json(dest_path)
            except Exception as e:
                errors.append({'file': name, 'type': rule['label'], 'error': str(e)})
                continue
            # Optional secondary copy to a flat network share (mirrors Alteryx 2nd output).
            extra = rule.get('extra_dest')
            if extra:
                try:
                    os.makedirs(extra, exist_ok=True)
                    _cetip_save_file(src_path, os.path.join(extra, dest_name))
                except Exception:
                    log.warning("[cetip] secondary copy failed %s → %s:\n%s",
                                name, extra, traceback.format_exc())
        if not rule_matched:
            try:
                exp = rule['dest_name'](ref_yymmdd)
            except Exception:
                exp = ''
            missing.append({'dest': exp, 'type': rule['label']})

    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'CETIP Files Saved', 'Control Panel',
                         '{} file(s) saved ({})'.format(len(saved), ref.strftime('%Y-%m-%d')))

    # Stage 1 e-mail — Brazil OTC Ops only: saved-files notice + the complete list
    # (no attachment). The Sales Support + CEM Latam e-mails go out in stage 2
    # ("Send to other areas" → _cetip_distribute_emails).
    ref_fmt = ref.strftime('%d/%m/%Y')
    mail_ops = None
    if send_mail and saved:
        ops_msg = ('The CETIP files required for the KPI generation have been saved successfully. '
                   'The complete list is shown below.')
        if missing:
            ops_msg += (' <b>{}</b> expected file(s) were <b>not found</b> in the source folder '
                        'and are flagged as <i>Not found</i> in the table.'.format(len(missing)))
        mail_ops = _send_cetip_email(
            [CETIP_OTC_OPS_EMAIL], [], 'CETIP Files Saved',
            'Hello,', ops_msg,
            ref_fmt, saved, dest_folder=dest_dir, missing=missing)

    msg = '<b>{}</b> file(s) saved.'.format(len(saved))
    if errors:
        msg += '<br><span class="text-warning">{} file(s) skipped/failed.</span>'.format(len(errors))
    if send_mail and saved:
        # _send_cetip_email returns True on success or an error string on failure.
        if mail_ops is True:
            msg += '<br>Confirmation e-mail sent to OTC Ops.'
        else:
            msg += ('<br><span class="text-warning">Files saved, but the OTC Ops e-mail failed: {}</span>'
                    .format(mail_ops))

    return jsonify({'success': True, 'message': msg, 'saved': saved, 'errors': errors,
                    'source': src_dir, 'destination': dest_dir,
                    'email_sent': {'otc_ops': mail_ops}})


# ============================================================================
#  SETTLEMENT FORECAST  (Alteryx "Settlement Forecast v2" → Python)
# ----------------------------------------------------------------------------
#  Reads the tidy JSON emitted by the File-Saving routine (B3 Files/<category>/),
#  projects the upcoming settlements per business day broken down by product and
#  by entity, and returns the data to the page. The page renders dashboard-style
#  ApexCharts and (on Run) exports them to PNG, which the e-mail endpoint embeds
#  into the report sent to Brazil OTC Ops.
# ============================================================================

FORECAST_BIZDAYS = 15                 # default business-day look-ahead window (from today, inclusive)
FORECAST_RANGE_CHOICES = (15, 20, 30) # selectable horizons offered on the dashboard

# Entity code → name. Keys are normalised (digits only) at lookup, so dotted
# variants (00041.00-7) match too. Anything unmapped is dropped from the by-entity
# breakdown (mirrors the Alteryx !Contains([Entity],"0") filter).
_FCST_ENTITY_MAP = {
    '00041007': 'LAWTON',
    '04880006': 'MGT',
    '85398005': 'ATACAMA',
}
_FCST_ENTITY_ORDER = ['LAWTON', 'MGT', 'ATACAMA']
_FCST_PRODUCT_ORDER = ['NDF Moeda', 'NDF Commodities', 'Option FXO', 'Option Commodities',
                       'Option EDG', 'SWAP CEM', 'SWAP EDG', 'SWAP CEMHYB']

# One entry per JSON source. Field resolution is by NAME token (case-insensitive
# "contains", first match wins) so it survives small header differences.
#   date    : tokens to find the settlement/maturity/event date column
#   entity  : tokens to find the entity/counterparty column
#   product : ('fixed', label)        → constant product label
#             ('ndfclass', tokens)    → NDF Moeda / NDF Commodities from class field
#             ('sisbacen', tokens)    → option product by Código SISBACEN
#             ('lob', tokens)         → SWAP CEM/EDG/CEMHYB from "Código Identificador"
_FORECAST_SOURCES = [
    {'key': 'ndf', 'label': 'NDF (TER)', 'category': 'NDF',
     'file': lambda r: '73760_{}_DPOSICAO-TER.json'.format(r),
     # Prefer the exact "Data de Vencimento" (maturity) — the real JP TER file has
     # many columns and could carry other "…vencimento…" fields; fall back to a
     # loose 'vencimento' only if the exact name isn't present.
     'date': ['data de vencimento', 'vencimento'],
     'entity': ['titular', 'contraparte', 'parte', 'conta'],
     'product': ('ndfclass', ['classe do ativo', 'ativo subjacente', 'mercadoria', 'classe'])},
    {'key': 'opc', 'label': 'Options (OPC)', 'category': 'Option',
     'file': lambda r: '73760_{}_DPOSICAO.json'.format(r),
     'date': ['vencimento'], 'entity': ['titular', 'contraparte', 'conta'],
     'product': ('optclass', ['classe do ativo', 'ativo subjacente', 'classe']),
     # Options (FXO/Comm/EDG) are counted on TWO dates: the maturity (col M,
     # "Data do Vencimento", via 'date') AND the premium settlement (col BN,
     # "Data de Liquidação do Prêmio", via 'date2'). A single contract therefore
     # contributes a count on each of those business days within the window.
     'date2': ['data de liquidacao do premio', 'data liquidacao do premio',
               'liquidacao do premio'],
     'date2_index': 65},   # fallback: col BN (1-based 66) if the header name shifts
    {'key': 'swap_pos', 'label': 'SWAP Position', 'category': 'Swap',
     'file': lambda r: '73760_{}_DPOSICAO-SWAP.json'.format(r),
     'date': ['data vencimento'], 'entity': ['contraparte'],
     'product': ('lob', ['código identificador', 'codigo identificador', 'identificador']),
     # "Tipo de Contrato" (1st col): 1 = cash-flow swap → counted via the FLUXO
     # file only (counting both would double it); 2 = bullet/final payment →
     # counted here by maturity (col M). So the Position file counts ONLY tipo 2.
     'count_where': (['tipo de contrato', 'tipo do contrato', 'tipo contrato', 'tipo de contr'], {'2'})},
    {'key': 'swap_flx', 'label': 'SWAP Flow', 'category': 'Swap',
     'file': lambda r: '73760_{}_DFLUXO.json'.format(r),
     'date': ['ocorrência do evento', 'ocorrencia do evento', 'evento'],
     'entity': ['nome simplificado contraparte', 'nome simplificado'],
     'product': ('lob', ['código identificador', 'codigo identificador', 'identificador'])},
    {'key': 'swap_prm', 'label': 'SWAP Premium Agenda', 'category': 'Swap',
     'file': lambda r: '73760_{}_DAGENDAPREMIOS.json'.format(r),
     # Premium settlement date = "Data do Evento" (col F). Name first, then col F
     # (index 5) as a fallback when the stored header is positional.
     'date': ['data do evento', 'evento'],
     'date_index': 5,
     'entity': ['nome simplificado', 'parte'],
     'product': ('lob', ['código identificador', 'codigo identificador',
                         'codigo do contrato', 'identificador'])},
]


def _fcst_parse_date(s):
    """Parse a CETIP date string (several known layouts) → date, or None."""
    s = (s or '').strip()
    if not s:
        return None
    s = s.split(' ')[0].split('T')[0]
    for fmt in ('%Y%m%d', '%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y', '%d.%m.%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _fcst_map_entity(raw):
    """Map an entity code/name to LAWTON/MGT/ATACAMA, or None if unmapped."""
    s = (raw or '').strip()
    if not s:
        return None
    digits = ''.join(ch for ch in s if ch.isdigit())
    if digits in _FCST_ENTITY_MAP:
        return _FCST_ENTITY_MAP[digits]
    up = s.upper()
    for nm in _FCST_ENTITY_ORDER:
        if nm in up:
            return nm
    return None


def _fcst_option_product(code):
    """Map an option's Código SISBACEN da Moeda Base → product (Alteryx Replace).
    220 → FX (FXO), COM → Commodities, INI → Equities. Falls back to FXO so an
    option is never dropped just because the classifier column couldn't be read."""
    c = (code or '').upper()
    if 'COM' in c or 'MERCAD' in c:
        return 'Option Commodities'
    if 'INI' in c or 'EQU' in c or 'ACAO' in c or 'AÇÃO' in c:
        return 'Option Equities'
    return 'Option FXO'   # 220 / câmbio / unmapped → FX options (default, never None)


def _fcst_ndf_product(asset_class):
    """NDF Moeda vs NDF Commodities from the asset-class field (Alteryx Replace:
    TAXAS DE CAMBIO → Moeda, COMMODITIES → Commodities)."""
    c = (asset_class or '').upper()
    if 'COMMOD' in c or 'MERCAD' in c:
        return 'NDF Commodities'
    return 'NDF Moeda'


def _fcst_opt_class_product(asset_class):
    """Option product from the OPC "Classe do Ativo Subjacente" (coluna N):
    TAXA DE CAMBIO → FXO, Commodities → Comm, everything else → EDG."""
    c = (asset_class or '').upper()
    if 'CAMB' in c or 'MOEDA' in c:
        return 'Option FXO'
    if 'COMMOD' in c or 'MERCAD' in c:
        return 'Option Commodities'
    return 'Option EDG'


def _fcst_lob(identifier):
    """SWAP line of business from the "Código Identificador" string.
    Order matters: hybrid is tested BEFORE CEM/EDG, because a hybrid's identifier
    also contains 'CEM' (e.g. 'CEMHYB', 'CEM-HIB') — testing 'CEM' first would
    swallow every hybrid into CEM and leave SWAP CEMHYB at zero.
    Accent-insensitive and tolerant of PT/EN hybrid spellings: the mock uses the
    English 'CEMHYB'/'HYB', but real B3 identifiers may use the Portuguese
    'HÍBRIDO'/'HIB'. Mirrors _accrual_lob (same field)."""
    s = _fcst_norm(identifier)   # lower-case + accent-stripped
    if 'cemhyb' in s or 'hib' in s:
        return 'CEMHYB'
    if 'edg' in s:
        return 'EDG'
    if 'cem' in s:
        return 'CEM'
    return 'CEMHYB'


def _forecast_spine(anchor=None, count=None):
    """The forecast column spine: the next `count` (default FORECAST_BIZDAYS)
    ANBIMA business days starting TODAY (inclusive), skipping weekends/holidays."""
    _load_anbima()
    count = count or FORECAST_BIZDAYS
    start = datetime.now().date()
    days, d = [], start
    while len(days) < count:
        if d.weekday() < 5 and d.strftime('%Y-%m-%d') not in _ANBIMA_HOLIDAYS:
            days.append(d)
        d += timedelta(days=1)
    return days


def _fcst_norm(s):
    """Lower-case + strip accents, so an ascii token like 'liquidacao do premio'
    matches a 'Liquidação do Prêmio' column header."""
    s = unicodedata.normalize('NFKD', (s or '').lower())
    return ''.join(c for c in s if not unicodedata.combining(c))


def _fcst_resolve_key(keys, tokens):
    """Resolve a column by name (tokens in priority order, accent- and
    case-insensitive). An EXACT name match wins over a substring match, so
    'data de vencimento' resolves to the column literally named "Data de
    Vencimento" even when a longer "Data de Vencimento Antecipado" is present."""
    low = [(k, _fcst_norm(k)) for k in keys]
    for tok in tokens:                     # 1) exact match, priority order
        tnorm = _fcst_norm(tok)
        for k, kl in low:
            if kl == tnorm:
                return k
    for tok in tokens:                     # 2) substring fallback, priority order
        tnorm = _fcst_norm(tok)
        for k, kl in low:
            if tnorm in kl:
                return k
    return None


def _forecast_collect(dref, spine):
    """Read every JSON source and tally counts into by_product / by_entity
    matrices aligned with the business-day spine. Returns (by_product, by_entity,
    status[])."""
    spine_index = {d: i for i, d in enumerate(spine)}
    n = len(spine)
    by_product, by_entity = {}, {}
    status = []
    for src in _FORECAST_SOURCES:
        path = os.path.join(B3_JSON_ROOT, src['category'], _b3_date_subpath(dref), src['file'](dref))
        st = {'label': src['label'], 'file': os.path.basename(path),
              'found': False, 'records': 0, 'counted': 0}
        if not os.path.isfile(path):
            status.append(st)
            continue
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                rows = json.load(fh)
        except Exception:
            log.warning("[forecast] could not read %s:\n%s", path, traceback.format_exc())
            status.append(st)
            continue
        st['found'] = True
        st['records'] = len(rows)
        if not rows:
            status.append(st)
            continue

        keys = list(rows[0].keys())
        date_key = _fcst_resolve_key(keys, src['date'])
        # Primary date fallback to a fixed column index if the header name could
        # not be resolved (e.g. Agenda Prêmios premium settlement = col F).
        if date_key is None and src.get('date_index') is not None:
            di = src['date_index']
            if 0 <= di < len(keys):
                date_key = keys[di]
        # Optional second date column (e.g. options also count on the premium
        # settlement date). Resolve by name, then fall back to a fixed column
        # index if the header name could not be found.
        date2_key = _fcst_resolve_key(keys, src['date2']) if src.get('date2') else None
        if date2_key is None and src.get('date2_index') is not None:
            i2 = src['date2_index']
            if 0 <= i2 < len(keys):
                date2_key = keys[i2]
        ent_key = _fcst_resolve_key(keys, src['entity'])
        pmode, pspec = src['product']
        prod_key = (_fcst_resolve_key(keys, pspec)
                    if pmode in ('sisbacen', 'lob', 'ndfclass', 'optclass') else None)

        # Optional row gate: only count rows whose value in a given column is in
        # an allowed set (e.g. SWAP Position counts only "Tipo de Contrato" = 2).
        cw = src.get('count_where')
        cw_key = _fcst_resolve_key(keys, cw[0]) if cw else None
        cw_allowed = cw[1] if cw else None
        if cw and cw_key is None:
            log.warning("[forecast] %s: count_where column %r not found; counting all rows",
                        src['label'], cw[0])

        counted = 0
        for row in rows:
            if cw_key is not None:
                cwv = str(row.get(cw_key, '') or '').strip()
                if cwv.endswith('.0'):       # numeric read as 2.0 → '2'
                    cwv = cwv[:-2]
                if cwv not in cw_allowed:
                    continue
            # Business-day slots this row counts on: the primary date plus an
            # optional second date (e.g. options count on both maturity AND
            # premium settlement). Dedup so a single row counts at most once per
            # day even when both dates land on the same business day.
            slots = set()
            d = _fcst_parse_date(row.get(date_key, '')) if date_key else None
            if d in spine_index:
                slots.add(spine_index[d])
            if date2_key is not None:
                d2 = _fcst_parse_date(row.get(date2_key, ''))
                if d2 in spine_index:
                    slots.add(spine_index[d2])
            if not slots:
                continue
            if pmode == 'fixed':
                product = pspec
            elif pmode == 'lob':
                product = 'SWAP ' + _fcst_lob(row.get(prod_key, '') if prod_key else '')
            elif pmode == 'ndfclass':
                product = _fcst_ndf_product(row.get(prod_key, '') if prod_key else '')
            elif pmode == 'optclass':
                product = _fcst_opt_class_product(row.get(prod_key, '') if prod_key else '')
            else:
                product = _fcst_option_product(row.get(prod_key, '') if prod_key else '')
            ent = _fcst_map_entity(row.get(ent_key, '')) if ent_key else None
            for di in slots:
                if product:
                    by_product.setdefault(product, [0] * n)[di] += 1
                if ent:
                    by_entity.setdefault(ent, [0] * n)[di] += 1
            counted += 1
        st['counted'] = counted
        st['date_field'] = date_key
        st['date2_field'] = date2_key
        st['entity_field'] = ent_key
        st['product_field'] = prod_key
        st['columns'] = keys
        st['count_where_field'] = cw_key
        status.append(st)
        log.info("[forecast] %s: %d rows, %d counted | date=%r date2=%r entity=%r product=%r%s",
                 src['label'], len(rows), counted, date_key, date2_key, ent_key, prod_key,
                 (' where=%r in %r' % (cw_key, sorted(cw_allowed))) if cw else '')
    return by_product, by_entity, status


def _forecast_matrix(mapping, order):
    """Ordered list of {label, values[], total} rows (known order first)."""
    ordered = [k for k in order if k in mapping] + [k for k in mapping if k not in order]
    return [{'label': k, 'values': mapping[k], 'total': sum(mapping[k])} for k in ordered]


def _forecast_payload(ref, days=None):
    """Compute the full forecast payload for a reference date."""
    dref = ref.strftime('%y%m%d')
    spine = _forecast_spine(ref, count=days)
    by_product, by_entity, status = _forecast_collect(dref, spine)
    product_rows = _forecast_matrix(by_product, _FCST_PRODUCT_ORDER)
    entity_rows = _forecast_matrix(by_entity, _FCST_ENTITY_ORDER)
    col_tot = [sum(r['values'][i] for r in product_rows) for i in range(len(spine))]
    return {
        'ref_date': ref.strftime('%Y-%m-%d'),
        'ref_date_fmt': ref.strftime('%d/%m/%Y'),
        'days': len(spine),
        'date_labels': [d.strftime('%d/%m') for d in spine],
        'date_full': [d.strftime('%d/%m/%Y') for d in spine],
        'products': product_rows,
        'entities': entity_rows,
        'col_totals': col_tot,
        'grand_total': sum(col_tot),
        'sources': status,
    }


def _forecast_has_files(ref):
    """True if at least one source JSON exists for this reference date."""
    dref = ref.strftime('%y%m%d')
    for src in _FORECAST_SOURCES:
        if os.path.isfile(os.path.join(B3_JSON_ROOT, src['category'], _b3_date_subpath(dref), src['file'](dref))):
            return True
    return False


def _forecast_latest_ref(max_back=10):
    """Walk back from D-1 ANBIMA until a date with saved B3 JSONs is found.
    Returns that date, or None if none exist within `max_back` business days.
    Used by the dashboard chart, which should show the latest available data;
    the Control Panel run instead requires D-1 strictly."""
    ref = _prev_anbima_bizday(datetime.now())
    for _ in range(max_back):
        if _forecast_has_files(ref):
            return ref
        ref = _prev_anbima_bizday(ref)
    return None


def _decode_data_uri(d):
    """Decode a 'data:image/png;base64,...' URI into raw bytes (or None)."""
    if not d:
        return None
    try:
        if ',' in d:
            d = d.split(',', 1)[1]
        return base64.b64decode(d)
    except Exception:
        return None


def _send_forecast_email(payload, images):
    """Render the Settlement Forecast HTML report and e-mail it to OTC Ops with
    the chart PNGs embedded (cid). `images` maps cid → raw PNG bytes. Best-effort
    — returns True on success or an error string."""
    from email.mime.image import MIMEImage
    try:
        html = render_template(
            'pages/email-template-settlement-forecast.html',
            ref_date_fmt=payload['ref_date_fmt'],
            date_labels=payload['date_labels'],
            products=payload['products'],
            entities=payload['entities'],
            col_totals=payload['col_totals'],
            grand_total=payload['grand_total'],
            has_chart_product=bool(images.get('fcst_product')),
            has_chart_entity=bool(images.get('fcst_entity')),
            has_chart_mix=bool(images.get('fcst_mix')),
            current_year=datetime.now().year)

        msg = MIMEMultipart('mixed')
        msg['Subject'] = 'Settlement Forecast'
        msg['From'] = SHARED_MAILBOX
        msg['To'] = CETIP_OTC_OPS_EMAIL

        related = MIMEMultipart('related')
        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText('Settlement Forecast — please view in HTML.', 'plain', 'utf-8'))
        alt.attach(MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)

        logo_path = _get_logo_path()
        if logo_path:
            with open(logo_path, 'rb') as f:
                limg = MIMEImage(f.read())
            limg.add_header('Content-ID', '<otc_logo>')
            limg.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(limg)

        for cid, data in images.items():
            if not data:
                continue
            cimg = MIMEImage(data)
            cimg.add_header('Content-ID', '<{}>'.format(cid))
            cimg.add_header('Content-Disposition', 'inline', filename='{}.png'.format(cid))
            related.attach(cimg)
        msg.attach(related)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.sendmail(SHARED_MAILBOX, [CETIP_OTC_OPS_EMAIL], msg.as_string())
        log.info("[forecast] e-mail sent to %s", CETIP_OTC_OPS_EMAIL)
        return True
    except Exception as e:
        log.error("[forecast] e-mail FAILED:\n%s", traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)


@blueprint.route('/api/control-panel/settlement-forecast/data', methods=['POST'])
def api_cp_forecast_data():
    """Compute the forecast for a reference date and return it as JSON for the
    page to render (ApexCharts + tables)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    mode = (payload.get('mode') or '').strip().lower()
    date_str = (payload.get('date') or '').strip()
    try:
        days = int(payload.get('days') or FORECAST_BIZDAYS)
    except (TypeError, ValueError):
        days = FORECAST_BIZDAYS
    if days not in FORECAST_RANGE_CHOICES:
        days = FORECAST_BIZDAYS
    try:
        if date_str:
            ref = datetime.strptime(date_str, '%Y-%m-%d')
        elif mode == 'latest':
            # Dashboard: use the most recent date that actually has saved JSONs
            # (D-1, else D-2, …). Never blocks just because D-1 isn't saved yet.
            ref = _forecast_latest_ref()
            if ref is None:
                return jsonify({'success': False,
                                'error': 'No B3 JSON files found in the last 10 business days. '
                                         'Run “Save CETIP Files” first.'}), 400
        else:
            ref = _prev_anbima_bizday(datetime.now())   # strict D-1 (Control Panel run)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date (expected YYYY-MM-DD).'}), 400

    data = _forecast_payload(ref, days=days)
    if not any(s['found'] for s in data['sources']):
        # In strict mode this means the mandatory D-1 files are missing.
        return jsonify({'success': False,
                        'error': 'No B3 JSON files found for {}. Run “Save CETIP Files” first.'
                        .format(ref.strftime('%d/%m/%Y')),
                        'sources': data['sources']}), 400
    return jsonify({'success': True, **data})


@blueprint.route('/api/control-panel/settlement-forecast/email', methods=['POST'])
def api_cp_forecast_email():
    """Receive the client-rendered chart PNGs (data URIs), rebuild the report
    tables server-side and e-mail the Settlement Forecast to OTC Ops."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    date_str = (payload.get('date') or '').strip()
    try:
        ref = (datetime.strptime(date_str, '%Y-%m-%d') if date_str
               else _prev_anbima_bizday(datetime.now()))
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date (expected YYYY-MM-DD).'}), 400

    data = _forecast_payload(ref)
    imgs = payload.get('images') or {}
    images = {
        'fcst_product': _decode_data_uri(imgs.get('by_product')),
        'fcst_entity':  _decode_data_uri(imgs.get('by_entity')),
    }
    result = _send_forecast_email(data, images)
    if result is not True:
        return jsonify({'success': False, 'error': 'E-mail failed: {}'.format(result)}), 500

    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Settlement Forecast Sent', 'Control Panel',
                         'Forecast e-mailed to OTC Ops ({})'.format(ref.strftime('%Y-%m-%d')))
    return jsonify({'success': True,
                    'message': 'Settlement Forecast e-mailed to OTC Ops.'})


# ──────────────────────────────────────────────────────────────────────────
# Control Panel — Update Contacts
# Native port of scripts/import_client_contacts.py. Imports the "CONTATO DE
# CLIENTES" spreadsheet into CounterpartyDetails.json: one contact per row,
# data starting at row 5, grouped by SPN (leading zeros ignored). For a matched
# SPN the CONTACTS array is replaced; CGD/BANKING are preserved. SPNs missing
# from the JSON are appended as new records. _cpd_save_list writes a .bak first.
# ──────────────────────────────────────────────────────────────────────────
_CONTACTS_DATA_START_ROW = 5    # 1-based; first data row in the sheet
# 0-based column indices: B,C,D,E,F,G,H
_CC_SPN, _CC_NAME, _CC_ACTIVE, _CC_CONTACT, _CC_PHONE, _CC_EMAIL, _CC_RULE = 1, 2, 3, 4, 5, 6, 7

# Map spreadsheet rule labels → the canonical rules used by the Reference Data
# editor. Unknown values are kept verbatim.
_CONTACT_RULE_MAP = {
    'NEGOTIATION': 'Negotiation', 'NEGOCIACAO': 'Negotiation', 'NEGOCIAÇÃO': 'Negotiation',
    'REPURCHASE': 'Repurchase', 'RECOMPRA': 'Repurchase',
    'SETTLEMENT': 'Settlement', 'LIQUIDACAO': 'Settlement', 'LIQUIDAÇÃO': 'Settlement',
    'CONFIRMATION LETTER': 'Confirmation Letter', 'CARTA DE CONFIRMACAO': 'Confirmation Letter',
    'CARTA DE CONFIRMAÇÃO': 'Confirmation Letter',
    'SETTLEMENT ADVICE': 'Settlement Advice', 'AVISO DE LIQUIDACAO': 'Settlement Advice',
    'AVISO DE LIQUIDAÇÃO': 'Settlement Advice',
    'CONTACT CONFIRMATION': 'Contact Confirmation', 'CONFIRMACAO DE CONTATO': 'Contact Confirmation',
    'IOF': 'IOF',
}


def _cc_cell(row, idx):
    if idx >= len(row):
        return ''
    v = row[idx]
    if v is None:
        return ''
    if isinstance(v, float):
        if v != v:                 # NaN
            return ''
        if v.is_integer():         # 123.0 (numeric SPN) → '123'
            return str(int(v))
    return str(v).strip()


def _cc_parse_rules(raw):
    out, seen = [], set()
    for part in str(raw or '').replace('\n', ';').replace('/', ';').replace(',', ';').split(';'):
        p = part.strip()
        if not p:
            continue
        canon = _CONTACT_RULE_MAP.get(p.upper(), p)
        if canon.upper() not in seen:
            seen.add(canon.upper())
            out.append(canon)
    return out


def _cc_read_rows(filename, raw_bytes):
    """Return a list of rows (each a list of cell values) from an uploaded
    .xlsx/.xlsm, .csv, .tsv or .txt. Raises ValueError on an unsupported type."""
    name = (filename or '').lower()
    if name.endswith(('.csv', '.tsv', '.txt')):
        import csv as _csv
        # Pick the first encoding that decodes WITHOUT replacement chars, so accented
        # headers (Código, Início, …) never turn into mojibake regardless of the
        # export encoding (utf-8 / Windows-1252 / Latin-1). latin-1 never fails and is
        # byte-exact for ISO-8859-1, so it is the guaranteed last resort.
        text = None
        for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
            try:
                cand = raw_bytes.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
            if '�' not in cand:
                text = cand
                break
        if text is None:
            text = raw_bytes.decode('latin-1', errors='replace')
        if name.endswith('.tsv'):
            delimiter = '\t'
        elif name.endswith('.txt'):
            # Auto-detect: financial exports use tab/';' so the comma thousand
            # separators inside numbers ("-1,802,855.64") don't split columns.
            first = next((ln for ln in text.splitlines() if ln.strip()), '')
            delimiter = '\t' if '\t' in first else (';' if ';' in first else ',')
        else:
            delimiter = ','
        return [list(r) for r in _csv.reader(io.StringIO(text), delimiter=delimiter)]
    if name.endswith(('.xlsx', '.xlsm')):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
        ws = wb.active
        return [list(r) for r in ws.iter_rows(values_only=True)]
    raise ValueError('Unsupported file type. Please upload .xlsx, .xlsm, .csv or .tsv.')


def _import_client_contacts(filename, raw_bytes):
    """Parse the spreadsheet bytes and merge contacts into CounterpartyDetails.json.
    Returns a summary dict; raises ValueError on a recoverable input problem."""
    rows = _cc_read_rows(filename, raw_bytes)

    groups = {}                    # nspn -> {'spn', 'name', 'contacts'[]}
    rows_seen = 0
    for i in range(_CONTACTS_DATA_START_ROW - 1, len(rows)):
        row = rows[i]
        spn_raw = _cc_cell(row, _CC_SPN)
        nspn = _norm_spn(spn_raw)
        if not nspn:
            continue
        # Only import contacts flagged Active ("A") in column D — inactive rows
        # are ignored entirely (an SPN with no active rows is left untouched).
        if _cc_cell(row, _CC_ACTIVE).upper() != 'A':
            continue
        cname = _cc_cell(row, _CC_CONTACT)
        phone = _cc_cell(row, _CC_PHONE)
        email = _cc_cell(row, _CC_EMAIL)
        rule  = _cc_cell(row, _CC_RULE)
        if not (cname or phone or email or rule):
            continue               # blank contact line
        rows_seen += 1
        g = groups.setdefault(nspn, {'spn': spn_raw.strip(), 'name': '', 'contacts': []})
        cp_name = _cc_cell(row, _CC_NAME)
        if cp_name and not g['name']:
            g['name'] = cp_name
        g['contacts'].append({
            'name': cname, 'phone': phone, 'email': email,
            'rules': _cc_parse_rules(rule), 'status': 'Active',
        })

    if not groups:
        raise ValueError('No active contact rows found (data is expected to start at row 5, '
                         'with the SPN in column B and the Active flag "A" in column D).')

    data = _cpd_load()
    by_nspn = {}
    for rec in data:
        by_nspn.setdefault(_norm_spn(rec.get('SPN', '')), rec)

    matched = created = 0
    for nspn, g in groups.items():
        rec = by_nspn.get(nspn)
        if rec is None:
            rec = {'SPN': g['spn'], 'COUNTERPARTY': g['name'], 'CGD': [],
                   'BANKING': {'PAY': [], 'RECEIVE': []}, 'CONTACTS': []}
            data.append(rec)
            by_nspn[nspn] = rec
            created += 1
        else:
            matched += 1
            if g['name'] and not str(rec.get('COUNTERPARTY', '') or '').strip():
                rec['COUNTERPARTY'] = g['name']
        rec['CONTACTS'] = g['contacts']     # replace contacts for this SPN

    _cpd_save_list(data)
    return {
        'rows': rows_seen, 'spns': len(groups),
        'contacts': sum(len(g['contacts']) for g in groups.values()),
        'matched': matched, 'created': created, 'total': len(data),
    }


# Network folder scanned for Daily Settlement source files when the dropzone is
# left empty (see api_cp_daily_settlement_save).
SETTLEMENTS_ROOT = os.getenv('SETTLEMENTS_ROOT',
                             r'I:\Confirmation\Derivativos\OTC Tracker\Settlements')

# Text-import specs translated from the VBA "ImportarTexto" (OpenText, TAB
# delimited) — one per source file, EXCLUDING Settlement OTM (done on its own
# page). Each cashflows/blotter file is a tab-delimited export; we read it, keep
# the header row, filter the data rows and write a per-type JSON. The Excel
# XLOOKUP enrichment (Tipo/Contraparte columns) is NOT part of the text import
# and is left out.
#   header  : 1-based row that holds the column names
#   filters : list of (kind, col, allowed) applied to each data row (ALL must pass)
#             kind 'digits' → compare digits-only cell; 'set' → compare UPPER cell
#   json    : output base name (…_YYYYMMDD.json under the daily-settlement folder)
_DS_IMPORTS = [
    {'key': 'operacoes-jpm', 'label': 'Operações JPM', 'json': 'operacoes-jpm', 'header': 5,
     'match': lambda n: n.startswith('operacoes'),
     'filters': [('digits', 2, {'73760009'}),
                 ('set', 10, {'OPC', 'OFVC', 'OFCC', 'SWAP', 'TER', 'COE'})]},
    {'key': 'operacoes-mgt', 'label': 'Operações MGT', 'json': 'operacoes-mgt', 'header': 5,
     'match': lambda n: n.startswith('mgt.'),
     'filters': [('digits', 2, {'04880006'}),
                 ('set', 10, {'OPC', 'OFVC', 'OFCC', 'SWAP', 'TER', 'COE'})]},
    {'key': 'eventos-swap-jpm', 'label': 'Eventos Swap', 'json': 'eventos-swap-jpm', 'header': 7,
     'match': lambda n: n.startswith('swap-instrumentofinanceiro-consultacontrato'),
     'filters': [('set', 2, {'CONFIRMADO'}), ('digits', 23, {'73760009'})]},
    {'key': 'eventos-swap-mgt', 'label': 'Eventos Swap MGT', 'json': 'eventos-swap-mgt', 'header': 7,
     'match': lambda n: n.startswith('swapmgt.'),
     'filters': [('set', 2, {'CONFIRMADO'}), ('digits', 23, {'04880006'})]},
    {'key': 'tss-fx', 'label': 'TSS-FX', 'json': 'tss-fx', 'header': 1,
     'match': lambda n: n.startswith('fxo detail'),
     'filters': [], 'skip_no_data': True},
]


def _ds_read_rows(raw):
    """Rows from a Daily Settlement source file — tab-delimited text (as the VBA
    OpenText Tab:=True treats them) with a real-.xlsx (zip) fallback."""
    if raw[:2] == b'PK':
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    return [ln.split('\t') for ln in raw.decode('latin-1').splitlines()]


def _ds_cell(row, i):
    return '' if (i < 0 or i >= len(row) or row[i] is None) else str(row[i]).strip()


def _ds_match_spec(name):
    n = (name or '').lower()
    for spec in _DS_IMPORTS:
        if spec['match'](n):
            return spec
    return None


def _ds_process(raw, spec):
    """Apply one spec: header row + row filters → list of dicts (kept rows). Returns
    (records, total_data_rows)."""
    rows = _ds_read_rows(raw)
    hidx = spec['header'] - 1
    if len(rows) <= hidx:
        return [], 0
    if spec.get('skip_no_data') and _ds_cell(rows[hidx], 0).lower().startswith('no data available'):
        return [], 0
    raw_header = rows[hidx]
    seen, header = {}, []
    for i in range(len(raw_header)):
        h = _ds_cell(raw_header, i) or 'Field_{}'.format(i + 1)
        seen[h] = seen.get(h, 0) + 1
        header.append(h if seen[h] == 1 else '{}_{}'.format(h, seen[h]))
    out, total = [], 0
    for row in rows[hidx + 1:]:
        if not any(_ds_cell(row, i) for i in range(len(row))):
            continue                                   # skip fully-blank lines
        total += 1
        keep = True
        for kind, col, allowed in spec['filters']:
            v = _ds_cell(row, col - 1)
            if kind == 'digits':
                if ''.join(ch for ch in v if ch.isdigit()) not in allowed:
                    keep = False
                    break
            elif v.upper() not in allowed:
                keep = False
                break
        if not keep:
            continue
        out.append({header[i] if i < len(header) else 'Field_{}'.format(i + 1): _ds_cell(row, i)
                    for i in range(len(row))})
    return out, total


def _ds_handle(name, raw, delete_path, ref, processed, skipped):
    spec = _ds_match_spec(name)
    if not spec:
        skipped.append(name)
        return
    try:
        recs, total = _ds_process(raw, spec)
    except Exception:
        log.warning("[ds] process failed for %s:\n%s", name, traceback.format_exc())
        skipped.append(name)
        return
    jp = os.path.join(OTM_JSON_ROOT, ref.strftime('%Y'), ref.strftime('%m'), ref.strftime('%d'),
                      '{}_{}.json'.format(spec['json'], ref.strftime('%Y%m%d')))
    os.makedirs(os.path.dirname(jp), exist_ok=True)
    with open(jp, 'w', encoding='utf-8') as fh:
        json.dump(recs, fh, ensure_ascii=False, indent=2)
    processed.append({'file': name, 'type': spec['label'], 'kept': len(recs), 'total': total})
    if delete_path:                                    # mirror the VBA Kill (folder source only)
        try:
            os.remove(delete_path)
        except OSError:
            log.warning("[ds] could not delete %s", delete_path)


@blueprint.route('/api/control-panel/daily-settlement-save', methods=['POST'])
def api_cp_daily_settlement_save():
    """Control Panel — "Save Daily Settlement Files". Source files come from the
    card's dropzone (multipart 'files'); if none were attached, fall back to
    scanning SETTLEMENTS_ROOT. Each recognised file is read (tab-delimited),
    filtered per the VBA ImportarTexto rules and written to a per-type JSON under
    the daily-settlement cache (today's date). Folder sources are deleted after
    processing (mirrors the VBA Kill). OTM cashflows are handled on their own
    page and are ignored here. No file anywhere → error (UI warns the user)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    ref = datetime.now()
    uploaded = [f for f in request.files.getlist('files') if f and f.filename]
    processed, skipped = [], []
    source = 'dropzone'

    if uploaded:
        for f in uploaded:
            _ds_handle(f.filename, f.read(), None, ref, processed, skipped)
    else:
        source = 'folder'
        folder_files = []
        if os.path.isdir(SETTLEMENTS_ROOT):
            try:
                folder_files = [f for f in os.listdir(SETTLEMENTS_ROOT)
                                if os.path.isfile(os.path.join(SETTLEMENTS_ROOT, f))]
            except OSError:
                folder_files = []
        if not folder_files:
            return jsonify({'success': False,
                            'error': ('Nenhum arquivo encontrado para processamento — o dropzone está '
                                      'vazio e não há arquivos em {}.'.format(SETTLEMENTS_ROOT))}), 400
        for name in folder_files:
            p = os.path.join(SETTLEMENTS_ROOT, name)
            try:
                with open(p, 'rb') as fh:
                    raw = fh.read()
            except OSError:
                skipped.append(name)
                continue
            _ds_handle(name, raw, p, ref, processed, skipped)

    if processed:
        _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'Daily Settlement Saved', 'Control Panel',
                             '{} file(s) processed ({})'.format(len(processed), ref.strftime('%Y-%m-%d')))

    lines = ['<b>{}</b>: {} de {} linha(s)'.format(p['type'], p['kept'], p['total']) for p in processed]
    msg = ''
    if lines:
        msg += '{} arquivo(s) processado(s) via {}:<br>'.format(len(processed),
               'dropzone' if source == 'dropzone' else 'pasta') + '<br>'.join(lines)
    if skipped:
        msg += ('<br><br>' if msg else '') + \
            '<span class="text-muted">{} ignorado(s) (não reconhecido/OTM): {}</span>'.format(
                len(skipped), ', '.join(skipped[:8]) + ('…' if len(skipped) > 8 else ''))
    return jsonify({'success': True, 'source': source, 'processed': processed,
                    'skipped': skipped, 'message': msg or 'Nada a processar.'})


@blueprint.route('/api/control-panel/import-contacts', methods=['POST'])
def api_cp_import_contacts():
    """Update client contacts from the uploaded 'CONTATO DE CLIENTES' spreadsheet."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'No file uploaded.'}), 400
    try:
        summary = _import_client_contacts(f.filename, f.read())
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        log.error('[contacts] import failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to process the spreadsheet.'}), 500

    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Contacts Updated', 'Control Panel',
                         '{} contacts across {} counterparties'.format(summary['contacts'], summary['spns']))
    msg = ('<b>{contacts}</b> contacts imported across <b>{spns}</b> counterparties.'
           '<br>Matched existing: {matched} &middot; New records appended: {created}'
           '<br>Total counterparties: {total}').format(**summary)
    return jsonify({'success': True, 'message': msg})


# ============================================================================
#  ACCRUAL — SWAP (VCP) classification by line of business
# ----------------------------------------------------------------------------
#  Reads the uploaded "Swap-IntrumentoFincaneiro-ConsultaContratoVCPSemPU"
#  spreadsheet (headers on row 9), cleans column A (# -> ''), keeps only the two
#  house accounts in column K, then joins each contract (col A) against the
#  latest saved SWAP position JSON to read its "Código Identificador" and route
#  the row to its line-of-business table (CEM / EDG / Hybrids / Commodities).
#  Each table keeps columns A, F, K, L, N, Q, R, T.
# ============================================================================

_ACC_HEADER_ROW = 9                                # 1-based: headers on row 9
_ACC_ACCOUNT_COL = 10                              # col K — house-account filter
_ACC_ACCOUNTS   = {'73760009', '04880006'}         # col K house accounts (digits only)

# Fixed table columns (always shown, independent of the imported file).
_ACC_FIXED_HEADERS = [
    'Código IF', 'Data Início', 'Data Vencimento',
    'PARTE / Conta', 'PARTE / Nome Simplificado', 'PARTE / Indexador',
    'CONTRAPARTE / Conta', 'CONTRAPARTE / Nome Simplificado', 'CONTRAPARTE / Indexador',
    'Fator Parte', 'Fator Contraparte', 'Comments',
]
# Source file column (0-based) for each fixed display column; None = placeholder
# (filled later by the grab logic / edited by hand). 0 = Código IF = col A ('#' stripped).
#   A, F, G, K, L, N, Q, R, T, —(Fator Parte), —(Fator Contra), —(Comments)
_ACC_DISPLAY_SRC = [0, 5, 6, 10, 11, 13, 16, 17, 19, None, None, None]


def _acc_digits(s):
    return re.sub(r'\D', '', str(s or ''))


def _accrual_lob(identifier):
    """Map a SWAP 'Código Identificador' to one of the four LOB buckets.
    Order matters: hybrid / COMM are tested before the CEM / EDG substrings.
    Accent-insensitive and tolerant of PT/EN hybrid spellings (HYB / HIB /
    HÍBRIDO), mirroring _fcst_lob."""
    s = _fcst_norm(identifier)   # lower-case + accent-stripped
    if 'hyb' in s or 'hib' in s:  return 'Hybrids'
    if 'comm' in s:               return 'Commodities'
    if 'edg' in s:                return 'EDG'
    if 'cem' in s:                return 'CEM'
    return None


def _swap_pos_latest_records(max_back=15):
    """Latest available SWAP position JSON (list-of-dicts) + its ref date 'YYYY-MM-DD'.
    Walks back from D-1 ANBIMA until the DPOSICAO-SWAP.json file exists."""
    ref = _prev_anbima_bizday(datetime.now())
    for _ in range(max_back):
        dref = ref.strftime('%y%m%d')
        path = os.path.join(B3_JSON_ROOT, 'Swap', _b3_date_subpath(dref),
                            '73760_{}_DPOSICAO-SWAP.json'.format(dref))
        if os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    return json.load(fh), ref.strftime('%Y-%m-%d')
            except Exception:
                log.error('[accrual] failed reading %s:\n%s', path, traceback.format_exc())
                return [], None
        ref = _prev_anbima_bizday(ref)
    return [], None


def _swap_pos_lob_map(records):
    """Build {contract -> identifier} from the SWAP position records, keyed by the
    upper-cased contract AND a digits-only fallback ('#'+digits)."""
    cmap = {}
    if not records:
        return cmap
    keys = list(records[0].keys())
    # 'Contrato' must not collide with 'Tipo de Contrato'; prefer the exact key.
    k_contract = 'Contrato' if 'Contrato' in keys else _fcst_resolve_key(
        [k for k in keys if _fcst_norm(k) != 'tipo de contrato'], ['contrato'])
    k_lob = ('Código Identificador' if 'Código Identificador' in keys
             else _fcst_resolve_key(keys, ['codigo identificador']))
    if not k_contract or not k_lob:
        return cmap
    for rec in records:
        c = str(rec.get(k_contract, '') or '').strip()
        if not c:
            continue
        ident = str(rec.get(k_lob, '') or '').strip()
        cmap.setdefault(c.upper(), ident)
        dg = _acc_digits(c)
        if dg:
            cmap.setdefault('#' + dg, ident)
    return cmap


@blueprint.route('/accrual-swap')
def accrual_swap():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/accrual-swap.html', segment='accrual-swap')


@blueprint.route('/mtm-swap')
def mtm_swap():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/mtm-swap.html', segment='mtm-swap')


# ── Other Products Summary (Settlement Batch) ────────────────────────────────
#  Counts operations SETTLING on the reference date, reusing the Settlement
#  Forecast JSON sources (position files from Save CETIP Files). Each forecast
#  source maps to a product family + sub-event; options also settle on the
#  premium date (date2), swaps split flow/premium/maturity across the 3 files.
_OPS_SRC_MAP = {
    'swap_pos': ('swap', 'maturity'),   # DPOSICAO-SWAP (tipo 2, maturity)
    'swap_flx': ('swap', 'flow'),       # DFLUXO (event date)
    'swap_prm': ('swap', 'premium'),    # DAGENDAPREMIOS (premium settlement = col F)
    'opc':      ('option', 'maturity'), # OPC maturity; date2 → premium
    'ndf':      ('ndf', 'maturity'),    # TER maturity
}


def _ops_src_latest_path(src, max_back=10):
    """Newest existing snapshot (path, dref) for ONE forecast source, walking back
    from D-1 ANBIMA. Each product folder is saved independently and the dates can
    drift a day apart (e.g. the NDF TER file lands after the SWAP files, or the
    Save-CETIP routine ran for one family but not another). Resolving the ref
    PER SOURCE — instead of a single shared `pos_ref` — keeps a family from
    silently counting zero just because its file is missing on the shared date."""
    ref = _prev_anbima_bizday(datetime.now())
    for _ in range(max_back):
        dref = ref.strftime('%y%m%d')
        path = os.path.join(B3_JSON_ROOT, src['category'], _b3_date_subpath(dref), src['file'](dref))
        if os.path.isfile(path):
            return path, dref
        ref = _prev_anbima_bizday(ref)
    return None, None


def _ops_settlement_counts(settle_ref, pos_ref):
    """Count operations settling on `settle_ref` (date) by product family +
    sub-event, reading each family's OWN latest position JSON. Missing files /
    no data → zeros (graceful, and logged so a silent zero is diagnosable)."""
    fams = {'swap':   {'total': 0, 'flow': 0, 'premium': 0, 'maturity': 0},
            'option': {'total': 0, 'maturity': 0, 'premium': 0},
            'ndf':    {'total': 0, 'maturity': 0},
            'coe':    {'total': 0}}
    # A tipo-2 swap is a cash-flow contract: it appears in DFLUXO with several
    # event dates. The event that lands on its OWN maturity date is the final
    # (bullet) payment → it must be counted as MATURITY, not Flow. So we collect
    # the "Código Identificador" of every contract maturing on `settle_ref`
    # (from DPOSICAO-SWAP, tipo 2) and then EXCLUDE those ids from the DFLUXO
    # Flow count — a flow event only counts as Flow when its contract's maturity
    # is NOT the picker date. swap_pos is processed before swap_flx in
    # _FORECAST_SOURCES, so the set is fully populated by the time Flow is read.
    swap_mat_ids = set()
    _ID_TOKENS = ['código identificador', 'codigo identificador', 'identificador']
    for src in _FORECAST_SOURCES:
        mapping = _OPS_SRC_MAP.get(src['key'])
        if not mapping:
            continue
        fam, primary_sub = mapping
        if fam == 'ndf':
            continue   # handled below via _forecast_collect (verbatim index logic)
        path, dref = _ops_src_latest_path(src)   # files are named yymmdd (e.g. 260703)
        if path is None:
            log.warning("[ops] %s (%s): no snapshot found in last 10 biz days; card counts 0",
                        src['key'], fam)
            continue
        try:
            with open(path, encoding='utf-8') as fh:
                rows = json.load(fh)
        except Exception:
            continue
        if not rows:
            continue
        keys = list(rows[0].keys())
        date_key = _fcst_resolve_key(keys, src['date'])
        if date_key is None and src.get('date_index') is not None and 0 <= src['date_index'] < len(keys):
            date_key = keys[src['date_index']]
        date2_key = _fcst_resolve_key(keys, src['date2']) if src.get('date2') else None
        if date2_key is None and src.get('date2_index') is not None and 0 <= src['date2_index'] < len(keys):
            date2_key = keys[src['date2_index']]
        cw = src.get('count_where')
        cw_key = _fcst_resolve_key(keys, cw[0]) if cw else None
        cw_allowed = cw[1] if cw else None
        id_key = _fcst_resolve_key(keys, _ID_TOKENS)   # contract join key (swap)
        for row in rows:
            if cw_key is not None:
                cwv = str(row.get(cw_key, '') or '').strip()
                if cwv.endswith('.0'):
                    cwv = cwv[:-2]
                if cwv not in cw_allowed:
                    continue
            cid = str(row.get(id_key, '') or '').strip() if id_key else ''
            # Flow event whose contract matures on the picker date → it's the
            # maturity payment (already counted via swap_pos), not a Flow.
            if src['key'] == 'swap_flx' and cid and cid in swap_mat_ids:
                continue
            if date_key and _fcst_parse_date(row.get(date_key, '')) == settle_ref:
                fams[fam]['total'] += 1
                fams[fam][primary_sub] += 1
                if src['key'] == 'swap_pos' and cid:
                    swap_mat_ids.add(cid)
            if date2_key and _fcst_parse_date(row.get(date2_key, '')) == settle_ref:
                fams[fam]['total'] += 1
                if fam == 'option':
                    fams[fam]['premium'] += 1

    # NDF Commodities — reuse the Settlement Forecast (index.html) computation
    # VERBATIM so the two cards can never disagree: same TER file, same "Data de
    # Vencimento" field, same "Classe do Ativo Subjacente" → NDF Commodities
    # mapping. Single-day spine at the settlement date; read that day's slot.
    if pos_ref is not None:
        f_by_product, _, _ = _forecast_collect(pos_ref.strftime('%y%m%d'), [settle_ref])
        ndf_c = (f_by_product.get('NDF Commodities') or [0])[0]
        fams['ndf']['total'] = ndf_c
        fams['ndf']['maturity'] = ndf_c
    return fams


@blueprint.route('/other-products-summary')
def other_products_summary():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/other-products-summary.html', segment='other-products-summary',
                           today=datetime.now().strftime('%Y-%m-%d'))


@blueprint.route('/api/other-products-summary/data')
def api_ops_data():
    """Settlement-batch payload: widget counts for the reference date (from the B3
    position JSONs) + the worksheet rows (empty until seeding is wired)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        settle_ref = datetime.strptime(ds[:10], '%Y-%m-%d').date() if ds else datetime.now().date()
    except ValueError:
        settle_ref = datetime.now().date()
    pos_ref = _forecast_latest_ref()          # cards read the LATEST available position JSON
    return jsonify({'success': True, 'date': settle_ref.strftime('%Y-%m-%d'),
                    'pos_date': pos_ref.strftime('%Y-%m-%d') if pos_ref else None,
                    'widgets': _ops_settlement_counts(settle_ref, pos_ref),
                    'summary': [], 'trade': []})


# ── Live Position › Swap › Characteristics ───────────────────────────────────
#  Read-only "photo" of the swap book still in custody on a reference date, from
#  the DPOSICAO-SWAP position JSON (same source as the dashboard Live Position).
#  Widgets break the count down by Tipo de Contrato, LOB, Indexador and
#  Funcionalidade; the table lists every contract with its full characteristic
#  column set. The canonical column list lives HERE (single source of truth) and
#  is shipped to the front-end so the header/data arrays can never drift apart.
#
#  Column names repeat by design (the B3 swap layout has parallel leg/index
#  blocks), so rows are emitted as POSITIONAL arrays aligned to _SWAPCHAR_LABELS
#  — a name-keyed dict would collapse the duplicates.
_SWAPCHAR_LABELS = [
    'Tipo de Contrato', 'Data', 'Contrato', 'Participante', 'CPF/CNPJ Cliente Parte',
    'Cesta Garantias Parte', 'Comissão Parte', 'Contraparte', 'CPF/CNPJ Cliente Contraparte',
    'Cesta Garantias Contraparte', 'Comissão Contraparte', 'Data início', 'Data vencimento',
    'Tipo de Adesão', 'Valor base', 'Valor Base Remanescente', 'Valor Antecipado', 'Saldo',
    'Sinal Saldo', 'Data do Saldo', 'Funcionalidade', 'Agenda de Prêmio', 'Reset', 'Observação',
    'Valor base inicial', 'Data operação termo', 'Índice Termo', 'Percentual Termo', 'PU Inicial',
    'Tipo/Classe', 'Nome Tipo/Classe', 'Denominação', 'Juros a cada', 'Expresso em',
    'Data inicio pagamento juros', 'Amortização a cada', 'Expresso em',
    'Data inicio pagamento amortização', 'Tipo de amortização', 'Percentual', 'Código índice',
    'TR Escolhida', 'Sinal Taxa', 'Taxa', 'Lim. Inferior (Floor)', 'Lim. Superior (Cap)',
    'Valor Curva Atualizado', 'Data Correção', 'Fator Original de Juros', 'Percentual',
    'Código índice', 'TR Escolhida', 'Sinal Taxa', 'Taxa', 'Lim. Inferior (Floor)',
    'Lim. Superior (Cap)', 'Valor Curva Atualizado', 'Data Correção', 'Fator Original de Juros',
    'Parte/Contraparte', 'Cupom Limpo', 'Percentual', 'Curva', 'Sinal Taxa', 'Taxa de Juros',
    'Limitador', 'Pu inicial', 'Pu atual', 'Tipo/Classe', 'Nome Tipo/Classe', 'Denominação',
    'Pu inicial', 'Pu atual', 'Tipo/Classe', 'Nome Tipo/Classe', 'Denominação', 'Cupom Limpo',
    'Data de Cotação', 'Cupom Limpo', 'Data de Cotação', 'Tipo Libor - moeda',
    'Tipo Libor - período', 'Data de Cotação', 'Variação Cambial', 'Tipo Classe',
    'Nome Tipo/Classe', 'Outros - Cotação', 'Alíquota - IR', 'Limite inferior (FLOOR) - Perc.',
    'Limite superior (CAP) - Perc.', 'Tipo Libor - moeda', 'Tipo Libor - período',
    'Data de Cotação', 'Variação Cambial', 'Tipo Classe', 'Nome Tipo/Classe', 'Outros - Cotação',
    'Alíquota - IR', 'Limite inferior (FLOOR) - Perc.', 'Limite superior (CAP) - Perc.',
    'Taxa Juros', 'Troca de Fluxo', 'Variação Cambial', 'Tipo Classe', 'Nome Tipo/Classe',
    'Outros - Cotação', 'Alíquota - IR', 'Limite inferior (FLOOR) - Perc.',
    'Limite superior (CAP) - Perc.', 'Taxa Juros', 'Troca de Fluxo', 'Variação Cambial',
    'Tipo Classe', 'Nome Tipo/Classe', 'Outros - Cotação', 'Alíquota - IR',
    'Limite inferior (FLOOR) - Perc.', 'Limite superior (CAP) - Perc.', 'Parte/Contraparte',
    'Fator/Valor/Taxa', 'Verificação', 'Data Disparo', 'Parte/Contraparte', 'Fator/Valor/Taxa',
    'Verificação', 'Data Disparo', 'Titular', 'Prêmio 1', 'Rebate', 'Liquidação do Rebate',
    'Dias Úteis após o Trigger Out', 'Prêmio 2', 'Data Exercício Prêmio 2', 'Estratégia',
    'Amortiza sem Troca de Diferencial', 'Data da Cotação - Variação Cambial',
    'Data da Cotação - Variação Cambial', 'Cotação Inicial', 'Código Commodity',
    'Media Asiática Verificação', 'Data Cotação para Ajuste', 'Cotação Inicial', 'Código Commodity',
    'Media Asiática Verificação', 'Data Cotação para Ajuste', 'Código Identificador',
]

# Funcionalidade code → clean label (no underscores/parentheses; OPCAO_ARREPEND →
# "OPCAO ARREPENDIMENTO"). Keyed by the integer code as a string ('0'..'9').
_SWAPCHAR_FUNC_MAP = {
    '0': 'SEM FUNCIONALIDADE', '1': 'KNOCK IN', '2': 'KNOCK OUT', '3': 'KNOCK INOUT',
    '4': 'SWAPTION', '5': 'COMPOUND', '6': 'OPCAO ARREPENDIMENTO', '7': 'KNOCK IN COM OPCAO',
    '8': 'KNOCK OUT COM OPCAO', '9': 'SWAP COM PRÊMIO',
}
# Header tokens (normalised) that mark a numeric/value column → format #,##0.00.
_SWAPCHAR_VALUE_TOKENS = ('valor', 'saldo', 'percentual', 'pu inicial', 'pu atual', 'taxa',
                          'lim. inferior', 'lim. superior', 'limite inferior', 'limite superior',
                          'curva atualizado', 'fator original', 'cupom limpo', 'premio', 'rebate',
                          'cotacao inicial', 'aliquota', 'fator/valor', 'outros - cotacao',
                          'variacao cambial', 'prêmio')


def _swapchar_lob(identifier):
    """Swap LOB bucket for the Characteristics widget: CEM / EDG / COMM / HYB.
    Hybrid is tested first (its id also contains 'CEM')."""
    s = _fcst_norm(identifier)
    if 'hyb' in s or 'hib' in s:
        return 'HYB'
    if 'comm' in s or 'commod' in s:
        return 'COMM'
    if 'edg' in s:
        return 'EDG'
    if 'cem' in s:
        return 'CEM'
    return 'CEM'


def _swapchar_coltype(label):
    """Formatting class for a column: date | func | amort | value | text."""
    n = _fcst_norm(label)
    if n.startswith('data'):
        return 'date'
    if n == 'funcionalidade':
        return 'func'
    if n == 'tipo de amortizacao':
        return 'amort'
    if n.startswith('sinal') or n.startswith('tipo') or n.startswith('nome'):
        return 'text'
    if any(tok in n for tok in _SWAPCHAR_VALUE_TOKENS):
        return 'value'
    return 'text'


_SWAPCHAR_TYPES = [_swapchar_coltype(l) for l in _SWAPCHAR_LABELS]


def _swapchar_func_text(v):
    """Map a Funcionalidade cell to its clean label (strip underscores/parentheses)."""
    s = str(v or '').strip()
    if not s:
        return ''
    digits = ''.join(ch for ch in s if ch.isdigit())
    if digits:
        code = str(int(digits))
        if code in _SWAPCHAR_FUNC_MAP:
            return _SWAPCHAR_FUNC_MAP[code]
    t = ' '.join(s.replace('(', ' ').replace(')', ' ').replace('_', ' ').split())
    if 'ARREPEND' in t.upper():
        return 'OPCAO ARREPENDIMENTO'
    return t


# Tipo de amortização code → text (image mapping; parentheses dropped, text kept).
_SWAPCHAR_AMORT_MAP = {
    '0': 'Sobre Valor Base Original',
    '1': 'Sobre Valor Base Remanescente',
    '3': 'Na Data de Vencimento',
    '4': 'Sem Troca de Amortização',
}


def _swapchar_amort_text(v):
    """Map a Tipo de amortização cell to its text label (no parentheses)."""
    s = str(v or '').strip()
    if not s:
        return ''
    m = re.search(r'\(([^)]*)\)', s)          # value already carries "NN (text)"
    if m and m.group(1).strip():
        return m.group(1).strip()
    digits = ''.join(ch for ch in s if ch.isdigit())
    if digits:
        code = str(int(digits))
        if code in _SWAPCHAR_AMORT_MAP:
            return _SWAPCHAR_AMORT_MAP[code]
    return s


def _swapchar_fmt_value(v):
    """Numeric cell → #,##0.00 (1,234.56); non-numeric passes through unchanged."""
    s = str(v or '').strip()
    if not s:
        return ''
    try:
        n = float(s.replace(' ', '').replace(',', '.'))
    except ValueError:
        return s
    return '{:,.2f}'.format(n)


def _swapchar_fmt_cell(value, ctype):
    if value in (None, ''):
        return ''
    if ctype == 'date':
        d = _fcst_parse_date(value)
        return d.strftime('%d/%m/%Y') if d else str(value)
    if ctype == 'func':
        return _swapchar_func_text(value)
    if ctype == 'amort':
        return _swapchar_amort_text(value)
    if ctype == 'value':
        return _swapchar_fmt_value(value)
    return str(value)


# Columns actually shown on the page — a subset of the 146 (in file order), from
# the desk's reference layout. Values are read POSITIONALLY from the position-file
# rows (which carry all 146 fields in order), so the repeated column names still
# resolve unambiguously to the right cell.
_SWAPCHAR_DISPLAY_IDX = [
    0, 2, 3, 7, 8, 11, 12, 14, 15, 16, 17, 18, 20, 21, 22, 23,           # A,C,D,H,I,L,M,O,P,Q,R,S,U,V,W,X
    24, 25, 26, 27, 28, 31, 38, 39, 40, 42, 43,                          # Y,Z,AA,AB,AC,AF,AM,AN,AO,AQ,AR
    44, 45, 46, 48, 49, 50, 52, 53, 54, 55, 56, 58, 60, 61, 62, 63, 64,  # AS..BM (skips AV,AZ,BF,BH)
    65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75,                          # BN..BX
    76, 77, 78, 79, 126, 127, 132, 133, 134, 144, 145,                   # BY,BZ,CA,CB,DW,DX,EC,ED,EE,EO,EP
]
_SWAPCHAR_DISPLAY_LABELS = [_SWAPCHAR_LABELS[i] for i in _SWAPCHAR_DISPLAY_IDX]


def _swapchar_collect(ref):
    """Build widgets + display rows from the DPOSICAO-SWAP file for `ref` (date).
    The saved position JSON carries all 146 fields IN ORDER (headerless file parsed
    with _B3_SWAP_HEADERS), so cells are read positionally by index; only the
    _SWAPCHAR_DISPLAY_IDX subset is emitted. Missing file → empty payload (logged)."""
    widgets = {
        'total': 0,
        'tipo':  {'total': 0, 'cashflow': 0, 'bullet': 0},
        'lob':   {'total': 0, 'CEM': 0, 'EDG': 0, 'COMM': 0, 'HYB': 0},
        # VCP / Calculado breakdown — counting logic pending (user will supply).
        'index': {'total': 0, 'vcp': 0, 'calculado': 0},
        # Forward Start / Notional / Prêmio / Arrependimento / Sem Funcionalidade —
        # counting logic pending (user will supply).
        'func':  {'total': 0, 'forward_start': 0, 'notional': 0, 'premio': 0,
                  'arrependimento': 0, 'sem': 0},
    }
    dref = ref.strftime('%y%m%d')
    path = os.path.join(B3_JSON_ROOT, 'Swap', _b3_date_subpath(dref),
                        '73760_{}_DPOSICAO-SWAP.json'.format(dref))
    rows_out = []
    if not os.path.isfile(path):
        log.warning("[swapchar] no DPOSICAO-SWAP for %s; page shows 0", dref)
        return {'widgets': widgets, 'columns': _SWAPCHAR_DISPLAY_LABELS, 'rows': []}
    try:
        with open(path, encoding='utf-8') as fh:
            src = json.load(fh)
    except Exception:
        return {'widgets': widgets, 'columns': _SWAPCHAR_DISPLAY_LABELS, 'rows': []}
    if not src:
        return {'widgets': widgets, 'columns': _SWAPCHAR_DISPLAY_LABELS, 'rows': []}

    keys = list(src[0].keys())
    tipo_key = _fcst_resolve_key(keys, ['tipo de contrato', 'tipo do contrato', 'tipo contrato'])
    cpty_key = _fcst_resolve_key(keys, ['contraparte'])
    venc_key = _fcst_resolve_key(keys, ['data vencimento', 'data de vencimento'])
    id_key   = _fcst_resolve_key(keys, ['código identificador', 'codigo identificador', 'identificador'])
    func_key = _fcst_resolve_key(keys, ['funcionalidade'])
    for row in src:
        vals = list(row.values())          # all 146 fields, in file order (real file)
        full = len(vals) >= 120             # sparse mock (4 named cols) → name-resolve fallback
        tv = str(row.get(tipo_key, '') or '').strip() if tipo_key else ''
        if tv.endswith('.0'):
            tv = tv[:-2]
        if tv.isdigit():                    # '01' → '1', '02' → '2' (leading zeros)
            tv = str(int(tv))
        cid = str(row.get(id_key, '') or '') if id_key else ''
        # Sparse-mock fallback: the few present fields keyed by their 146-list index.
        sparse = {} if full else {
            0: tv,
            7: (row.get(cpty_key, '') if cpty_key else ''),
            12: (row.get(venc_key, '') if venc_key else ''),
            20: (row.get(func_key, '') if func_key else ''),
            145: cid,
        }
        disp = []
        for i in _SWAPCHAR_DISPLAY_IDX:
            raw = (vals[i] if i < len(vals) else '') if full else sparse.get(i, '')
            if i == 0:                      # Tipo de Contrato: 01 → Bullet, 02 → Cashflow
                rv = str(raw or '').strip()
                if rv.endswith('.0'):
                    rv = rv[:-2]
                if rv.isdigit():
                    rv = str(int(rv))
                disp.append('Bullet' if rv == '1' else ('Cashflow' if rv == '2'
                            else _swapchar_fmt_cell(raw, _SWAPCHAR_TYPES[i])))
            else:
                disp.append(_swapchar_fmt_cell(raw, _SWAPCHAR_TYPES[i]))
        rows_out.append(disp)
        # Widgets
        widgets['total'] += 1
        widgets['tipo']['total'] += 1
        if tv == '1':                       # 01 → Bullet, 02 → Cashflow
            widgets['tipo']['bullet'] += 1
        elif tv == '2':
            widgets['tipo']['cashflow'] += 1
        lob = _swapchar_lob(cid)
        widgets['lob']['total'] += 1
        widgets['lob'][lob] += 1
    return {'widgets': widgets, 'columns': _SWAPCHAR_DISPLAY_LABELS, 'rows': rows_out}


@blueprint.route('/live-position-swap-characteristics')
def live_position_swap_characteristics():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ref_date = _prev_anbima_bizday(datetime.now()).strftime('%Y-%m-%d')
    return render_template('pages/live-position-swap-characteristics.html',
                           segment='live-position-swap-characteristics', ref_date=ref_date)


@blueprint.route('/api/live-position-swap-characteristics/data')
def api_swapchar_data():
    """Swap Characteristics payload for a reference date (default D-1 ANBIMA)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d').date() if ds else \
            _prev_anbima_bizday(datetime.now()).date()
    except ValueError:
        ref = _prev_anbima_bizday(datetime.now()).date()
    payload = _swapchar_collect(ref)
    payload.update({'success': True, 'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)


# ── Other Products › OTM Settlements ─────────────────────────────────────────
#  Replaces the legacy Excel/VBA "Settlement - OTM" import. A cashflows_*.xlsx
#  file (actually a TAB-delimited text export, opened by the VBA via OpenText
#  Tab:=True) is dropped in OTM_SOURCE_ROOT. On import we clean it exactly like
#  the macro's CleanSettlementOTM:
#    A) drop rows whose col 14 == "DELETE" (keep header),
#    B) normalise col 22 to a 4-digit text code (leading zeros),
#    C) keep only col 22 in {"0228","0123"},
#  then keep ONLY the reporting columns below and write them to
#    static/data/cache/daily settlement/YYYY/MM/DD/otm-settlement_YYYYMMDD.json
#  (today's date), deleting the consumed source file. Widgets' counting logic
#  (RATES/EQUITIES/COMMODITIES) is pending (user will supply).
OTM_SOURCE_ROOT = os.getenv('OTM_SOURCE_ROOT',
                            r'I:\Confirmation\Derivativos\OTC Tracker\Settlement\OTM')
OTM_JSON_ROOT = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'cache', 'daily settlement')
_OTM_COLUMNS = [
    'Trade Id', 'Currency', 'Amount', 'Value Date', 'Direction', 'Cpty SPN', 'Cpty Name',
    'Owner SPN', 'Trade Date', 'Asset Class', 'Owner Legal Entity', 'Owner Name',
    'Exception Type', 'Cashflow Stage', 'Trade Ref', 'Underlying', 'Product Class', 'Break Reason',
]
_OTM_DATE_COLS = {'Value Date', 'Trade Date'}
_OTM_KEEP_CODES = {'0228', '0123'}          # col 22 values to keep (CleanSettlementOTM step C)


def _otm_json_path(ref):
    return os.path.join(OTM_JSON_ROOT, ref.strftime('%Y'), ref.strftime('%m'), ref.strftime('%d'),
                        'otm-settlement_{}.json'.format(ref.strftime('%Y%m%d')))


def _otm_read_rows(path):
    """Rows (list of lists) from the cashflows file. The VBA treats it as a TAB
    text file even though it's named .xlsx; handle both a real .xlsx (zip) and a
    tab-delimited text export."""
    with open(path, 'rb') as fh:
        raw = fh.read()
    if raw[:2] == b'PK':                     # real .xlsx (zip container)
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    text = raw.decode('latin-1')
    return [ln.split('\t') for ln in text.splitlines() if ln.strip()]


def _otm_import(ref=None):
    """Find cashflows_*.xlsx in OTM_SOURCE_ROOT, clean + extract the reporting
    columns, write today's JSON and delete the source. Returns a summary dict."""
    ref = ref or datetime.now()
    if not os.path.isdir(OTM_SOURCE_ROOT):
        return {'success': False, 'error': 'Source folder not found: {}'.format(OTM_SOURCE_ROOT)}
    matches = sorted(f for f in os.listdir(OTM_SOURCE_ROOT)
                     if f.lower().startswith('cashflows_') and f.lower().endswith('.xlsx'))
    if not matches:
        return {'success': False, 'error': 'No cashflows_*.xlsx found in {}'.format(OTM_SOURCE_ROOT)}
    src_path = os.path.join(OTM_SOURCE_ROOT, matches[0])
    try:
        rows = _otm_read_rows(src_path)
    except Exception:
        log.warning("[otm] read failed for %s:\n%s", src_path, traceback.format_exc())
        return {'success': False, 'error': 'Could not read {}'.format(matches[0])}
    if not rows or len(rows) < 2:
        return {'success': False, 'error': 'File {} has no data rows'.format(matches[0])}

    header = [str(h or '').strip() for h in rows[0]]
    hnorm = [_fcst_norm(h) for h in header]

    def col_idx(name):
        n = _fcst_norm(name)
        if n in hnorm:
            return hnorm.index(n)
        for i, h in enumerate(hnorm):
            if h and (n in h or h in n):
                return i
        return None
    idx_map = {c: col_idx(c) for c in _OTM_COLUMNS}

    def cell(r, i):
        return str(r[i]).strip() if (i is not None and i < len(r) and r[i] is not None) else ''

    out, kept, deleted, filtered = [], 0, 0, 0
    for r in rows[1:]:
        if cell(r, 13).upper() == 'DELETE':          # col 14 (0-based 13)
            deleted += 1
            continue
        c22 = cell(r, 21)                            # col 22 (0-based 21)
        try:
            c22 = '{:04d}'.format(int(float(c22))) if c22 else ''
        except (ValueError, TypeError):
            pass
        if c22 not in _OTM_KEEP_CODES:
            filtered += 1
            continue
        out.append({c: cell(r, idx_map.get(c)) for c in _OTM_COLUMNS})
        kept += 1

    jp = _otm_json_path(ref)
    os.makedirs(os.path.dirname(jp), exist_ok=True)
    with open(jp, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    try:
        os.remove(src_path)
    except OSError:
        log.warning("[otm] could not delete source %s", src_path)
    log.info("[otm] imported %s: kept %d (deleted %d, filtered %d) → %s",
             matches[0], kept, deleted, filtered, jp)
    return {'success': True, 'file': matches[0], 'rows': kept, 'deleted': deleted,
            'filtered': filtered, 'date': ref.strftime('%Y-%m-%d')}


def _otm_collect(ref):
    """Read the OTM JSON for `ref` (date) → display rows + widgets. Dates are
    formatted dd/mm/yyyy and Amount as #,##0.00. Widget breakdown pending."""
    widgets = {'total': 0, 'rates': 0, 'equities': 0, 'commodities': 0}
    jp = _otm_json_path(ref)
    rows_out = []
    if os.path.isfile(jp):
        try:
            with open(jp, encoding='utf-8') as fh:
                data = json.load(fh) or []
        except Exception:
            data = []
        for rec in data:
            row = []
            for c in _OTM_COLUMNS:
                v = rec.get(c, '')
                if c in _OTM_DATE_COLS:
                    d = _fcst_parse_date(v)
                    v = d.strftime('%d/%m/%Y') if d else (v or '')
                elif c == 'Amount':
                    v = _swapchar_fmt_value(v)
                row.append('' if v is None else v)
            rows_out.append(row)
        widgets['total'] = len(data)
    return {'widgets': widgets, 'columns': _OTM_COLUMNS, 'rows': rows_out}


@blueprint.route('/otm-settlements')
def otm_settlements():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/otm-settlements.html', segment='otm-settlements',
                           today=datetime.now().strftime('%Y-%m-%d'))


@blueprint.route('/api/otm-settlements/data')
def api_otm_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    payload = _otm_collect(ref)
    payload.update({'success': True, 'date': ref.strftime('%Y-%m-%d'),
                    'date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)


@blueprint.route('/api/otm-settlements/import', methods=['POST'])
def api_otm_import():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    res = _otm_import(datetime.now())
    if res.get('success'):
        _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'OTM Imported', 'OTM Settlements',
                             '{} row(s) imported ({})'.format(res.get('rows', 0), res.get('date', '')))
    return jsonify(res)


# ============================================================================
#  MtM — Swap Mark-to-Market by line of business (+ COE)
#  Swap file  "…ConsultaInfoDerivativosSemAtualMID" → CEM / EDG / Hybrids /
#             Commodities. Cols A,C,D,E,F,H,K; house account 73760.00-9 in col D;
#             classified via the latest SWAP position (same join as Accrual).
#             The file lists contracts PENDING MtM update, so 'Valor MTM' has no
#             source column and starts blank (K → 'Data Vencimento').
#  COE  file  "Swap-COE-ConsultaMTMCOE" → COE table. Cols A,B,C,D; col G reference
#             date must equal the last ANBIMA business day of the PENULTIMATE month.
#  Disk : MTM_JSON_ROOT/YYYY/MM/DD/mtm_swap_YYYYMMDD.json
#  Source folder: MTM_SOURCE_ROOT\YYYY\mm. Month\DD
# ============================================================================
MTM_SOURCE_ROOT = os.getenv('MTM_SOURCE_ROOT',
                            r'I:\Confirmation\Derivativos\OTC Tracker\Regulatory\MTM')
MTM_JSON_ROOT = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'cache', 'mtm')

_MTM_ACCOUNT      = '73760009'               # col D house account (73760.00-9), digits only
_MTM_FILTER_COL   = 3                         # col D
_MTM_RECON_DATA_ROW  = 8                      # ConsultaInformacoesAtualizMID: headers row 8, data from row 9 (idx 8)
_MTM_RECON_VALUE_COL = 6                      # col G = registered Valor MTM (signed)
_MTM_SWAP_BOOKS   = ('CEM', 'EDG', 'Hybrids', 'Commodities')
_MTM_FIXED_HEADERS = [
    'Código IF', 'Data Início', 'PARTE / Conta', 'Nome Simplificado Parte',
    'CONTRAPARTE / Conta', 'Nome Simplificado Contraparte',
    'Data Vencimento', 'Valor MTM', 'Comments',
]
# Source column (0-based) per fixed header: A=0, C=2, D=3, E=4, F=5, G=6, K=10.
# 'Nome Simplificado Contraparte' comes from col G (6). 'Valor MTM' (pending →
# blank) and 'Comments' (manual) have no source.
_MTM_DISPLAY_SRC  = [0, 2, 3, 4, 5, 6, 10, None, None]

_MTM_COE_HEADERS  = ['Código do COE', 'Nome Simplificado Emissor', 'Conta Emissor', 'Nome Figura', 'Valor MTM', 'Comments']
_MTM_COE_SRC      = [0, 1, 2, 3, None, None]  # A,B,C,D (A '#' stripped) + Valor MTM (blank) + Comments (manual)
_MTM_COE_REFDATE_COL = 6                       # col G reference date

# Position of 'Valor MTM' / 'Comments' within a swap-book data row / a COE row.
_MTM_VALOR_IDX    = _MTM_FIXED_HEADERS.index('Valor MTM')    # 7
_MTM_COMMENT_IDX  = _MTM_FIXED_HEADERS.index('Comments')     # 8
_MTM_COE_VALOR_IDX   = _MTM_COE_HEADERS.index('Valor MTM')   # 4
_MTM_COE_COMMENT_IDX = _MTM_COE_HEADERS.index('Comments')    # 5

# CEM MtM values file "VCP_CETIP_MTM": A=Trade Name, B=Counterparty Name,
# C=CETIP ID, D=MTM in BRL. Keep rows where B <> our own GEM-Rates side, join
# C (CETIP ID) to the CEM book's Código IF, D → rounded 2dp (signed).
_MTM_ZERO_COMMENT   = 'MtM não pode ser Zero'
_MTM_STATUS_MISSING = 'Missing MtM'                   # rows with no matching MtM value


def _mtm_norm_party(s):
    """Normalize a counterparty label for a lenient match: strip quotes + accents,
    drop ALL whitespace, lowercase. Robust to leading/trailing/inner spacing
    variations and accents (e.g. 'Bco J.P. Morgan … RATES ' with a trailing space)."""
    s = str(s or '').strip().strip("'").strip('"')
    s = ''.join(ch for ch in unicodedata.normalize('NFKD', s) if not unicodedata.combining(ch))
    return re.sub(r'\s+', '', s).lower()


# Our own GEM-Rates side (normalized) — these rows are excluded from the CEM join.
_MTM_CEM_SELF_PARTY = _mtm_norm_party('Bco J.P. Morgan S.A. 2768 - GEM BR - RATES')


def _mtm_is_cem_value_name(n):
    nl = (n or '').lower()
    return 'vcp_cetip_mtm' in nl and not nl.endswith('.msg')


def _mtm_parse_num(s):
    """Parse a US/en amount like "-1,802,855.646864" (comma thousands, dot decimal,
    optional surrounding quotes) → float, or None. This is the format the page stores
    (Valor MTM = '{:,.2f}')."""
    s = str(s or '').strip().strip("'").strip('"').replace(',', '').strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _mtm_parse_num_br(s):
    """Parse a BRL-formatted amount like "-1.802.855,64" (dot thousands, comma
    decimal, optional surrounding quotes) → float, or None. Used for the recon file
    (ConsultaInformacoesAtualizMID), whose values are in BRL format — unlike the
    page's US-format Valor MTM (see _mtm_parse_num)."""
    s = str(s or '').strip().strip("'").strip('"').strip()
    if not s:
        return None
    s = s.replace('.', '').replace(',', '.')      # drop dot thousands, comma → decimal
    try:
        return float(s)
    except ValueError:
        return None


def _mtm_apply_cem_values(cem_rows, file_rows):
    """Fill each CEM row's 'Valor MTM' (rounded 2dp, signed) from VCP_CETIP_MTM,
    matching col C (CETIP ID) to Código IF. Zero → keep 0.00 + zero comment.
    Rows with NO matching value → status 'Missing MtM'. cem_rows are FINALIZED
    (status at index -4). Returns (matched, zeros, missing)."""
    vmap = {}
    for r in file_rows:
        b = _mtm_norm_party(_cc_cell(r, 1))
        if not b or b == _MTM_CEM_SELF_PARTY:
            continue                                     # keep B <> our GEM-Rates side
        cid = str(_cc_cell(r, 2) or '').strip().strip("'").strip('"')
        num = _mtm_parse_num(_cc_cell(r, 3))
        if not cid or num is None:
            continue                                     # header row skipped here too
        vmap.setdefault(cid.upper(), num)
    matched = zeros = missing = 0
    for row in cem_rows:
        cid = str(row[0] or '').strip().upper()
        if cid in vmap:
            v = round(vmap[cid], 2)
            if v == 0:                                     # keep 0.00 in the table (the
                row[_MTM_COMMENT_IDX] = _MTM_ZERO_COMMENT  # preview/file registers 1 cent)
                zeros += 1
            row[_MTM_VALOR_IDX] = '{:,.2f}'.format(v)      # #,##0.00 (comma thousands)
            matched += 1
        else:
            row[-4] = _MTM_STATUS_MISSING                  # no MtM value → Missing MtM
            missing += 1
    return matched, zeros, missing


def _mtm_is_edg_value_name(n):
    """EDG/COE MtM values file — named 'EDG.<ext>' (any extension)."""
    return os.path.splitext(n or '')[0].strip().lower() == 'edg'


def _mtm_apply_edg_values(data, file_rows):
    """EDG file: col A = contract ID, col B = MtM value (IDs 'JP*' are COE, the rest
    EDG). Match by ID onto the EDG and COE tables; set 'Valor MTM' (#,##0.00 signed,
    zero → 0.00 + zero comment). Rows with NO matching value → status 'Missing MtM'.
    Rows are FINALIZED (status at -4). Returns (edg_matched, coe_matched, zeros, missing)."""
    tables = data.get('tables') or {}
    fmap = {}
    for r in file_rows:
        cid = str(_cc_cell(r, 0) or '').strip().strip("'").strip('"')
        num = _mtm_parse_num(_cc_cell(r, 1))
        if cid and num is not None:
            fmap.setdefault(cid.upper(), num)              # header row skipped (value not numeric)
    edg_m = coe_m = zeros = missing = 0
    for row in tables.get('EDG', []) or []:
        cid = str(row[0] or '').strip().upper()
        if cid in fmap:
            v = round(fmap[cid], 2)
            if v == 0:                                     # keep 0.00 in the table (the
                row[_MTM_COMMENT_IDX] = _MTM_ZERO_COMMENT  # preview/file registers 1 cent)
                zeros += 1
            row[_MTM_VALOR_IDX] = '{:,.2f}'.format(v)
            edg_m += 1
        else:
            row[-4] = _MTM_STATUS_MISSING
            missing += 1
    for row in tables.get('COE', []) or []:
        cid = str(row[0] or '').strip().upper()
        if cid in fmap:
            v = round(fmap[cid], 2)
            if v == 0:                                     # keep 0.00 in the table (the
                row[_MTM_COE_COMMENT_IDX] = _MTM_ZERO_COMMENT  # preview/file registers 1 cent)
                zeros += 1
            row[_MTM_COE_VALOR_IDX] = '{:,.2f}'.format(v)
            coe_m += 1
        else:
            row[-4] = _MTM_STATUS_MISSING
            missing += 1
    return edg_m, coe_m, zeros, missing


# Hybrids MtM values file "Stream_level_MTM": col A = Trade Name, col E (idx 4) =
# 'MTM in scaling currency'. SUMIF col E grouped by Trade Name, resolve the
# mapping_swap-hyb.json B3 ID and set the Hybrids row (Código IF = B3 ID).
_MTM_HYB_MAP_PATH  = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'mapping_swap-hyb.json')
_MTM_HYB_VALUE_COL = 4                                # col E: MTM in scaling currency


def _mtm_is_hyb_value_name(n):
    return 'stream_level_mtm' in (n or '').lower()


def _mtm_load_hyb_mapping():
    try:
        with open(_MTM_HYB_MAP_PATH, encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _mtm_apply_hyb_values(hyb_rows, file_rows, mapping):
    """SUMIF col E ('MTM in scaling currency') grouped by Trade Name (col A) in the
    Stream_level_MTM file; resolve the mapping's B3 ID and set each Hybrids row's
    'Valor MTM' (Código IF = B3 ID). Rows with NO matching value → 'Missing MtM'.
    hyb_rows are FINALIZED (status at -4). Returns (matched, zeros, missing)."""
    sums = {}                                            # normalized Trade Name → Σ col E
    for r in file_rows:
        name = _mtm_norm_party(_cc_cell(r, 0))
        num  = _mtm_parse_num(_cc_cell(r, _MTM_HYB_VALUE_COL))
        if not name or num is None:
            continue                                     # header / blank line
        sums[name] = sums.get(name, 0.0) + num
    vmap = {}                                            # B3 ID → summed value
    for m in mapping:
        key = _mtm_norm_party(m.get('trade_name'))
        b3  = str(m.get('b3_id') or '').strip().upper()
        if b3 and key in sums:
            vmap[b3] = vmap.get(b3, 0.0) + sums[key]
    matched = zeros = missing = 0
    for row in hyb_rows:
        cid = str(row[0] or '').strip().upper()
        if cid in vmap:
            v = round(vmap[cid], 2)
            if v == 0:                                     # keep 0.00 in the table (the
                row[_MTM_COMMENT_IDX] = _MTM_ZERO_COMMENT  # preview/file registers 1 cent)
                zeros += 1
            row[_MTM_VALOR_IDX] = '{:,.2f}'.format(v)
            matched += 1
        else:
            row[-4] = _MTM_STATUS_MISSING
            missing += 1
    return matched, zeros, missing


def _mtm_path_for(ymd):
    return os.path.join(MTM_JSON_ROOT, ymd[:4], ymd[4:6], ymd[6:8], 'mtm_swap_{}.json'.format(ymd))


def _mtm_source_dir(ymd):
    ref = datetime.strptime(ymd, '%Y%m%d')
    month_folder = ref.strftime('%m') + '. ' + _EN_MONTH_NAMES[ref.month - 1]
    return os.path.join(MTM_SOURCE_ROOT, ref.strftime('%Y'), month_folder, ref.strftime('%d'))


def _mtm_is_swap_name(n):
    return 'sematualmid' in (n or '').lower()


def _mtm_is_coe_name(n):
    nl = (n or '').lower()
    return 'coe' in nl and ('consultamtmcoe' in nl or 'swap-coe' in nl)


def _last_anbima_bizday_of_month(year, month):
    """Last ANBIMA business day of the given year/month (datetime)."""
    _load_anbima()
    nm = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    cur = nm - timedelta(days=1)
    while cur.weekday() >= 5 or cur.strftime('%Y-%m-%d') in _ANBIMA_HOLIDAYS:
        cur -= timedelta(days=1)
    return cur


def _mtm_coe_refdate():
    """Last ANBIMA business day of the PENULTIMATE month vs. today (e.g. Jul → May)."""
    now = datetime.now()
    y, m = now.year, now.month - 2
    while m <= 0:
        m += 12
        y -= 1
    return _last_anbima_bizday_of_month(y, m).date()


def _mtm_build_swap(rows):
    """Split swap rows into the four LOB books via the latest SWAP position join."""
    records, ref_date = _swap_pos_latest_records()
    lob_map = _swap_pos_lob_map(records)
    buckets = {k: [] for k in _MTM_SWAP_BOOKS}
    kept = matched = 0
    for row in rows:
        a_raw = _cc_cell(row, 0)
        if not a_raw and not any(_cc_cell(row, c) for c in _MTM_DISPLAY_SRC if c is not None):
            continue                                     # blank line
        if _acc_digits(_cc_cell(row, _MTM_FILTER_COL)) != _MTM_ACCOUNT:
            continue                                     # col D: house account only
        kept += 1
        contract = a_raw.replace('#', '').strip()        # col A: drop '#'
        ident = lob_map.get(contract.upper()) or lob_map.get('#' + _acc_digits(contract))
        lob = _accrual_lob(ident)
        if not lob:
            continue                                     # IF not found / unclassified
        matched += 1
        cells = []
        for src in _MTM_DISPLAY_SRC:
            if src is None:  cells.append('')
            elif src == 0:   cells.append(contract)
            else:            cells.append(_cc_cell(row, src))
        buckets[lob].append(cells)
    return buckets, ref_date, kept, matched


def _mtm_build_coe(rows):
    """COE rows whose col G reference date == last ANBIMA bizday of the penultimate month."""
    tgt = _mtm_coe_refdate()
    out = []
    for row in rows:
        a_raw = _cc_cell(row, 0)
        if not a_raw and not any(_cc_cell(row, c) for c in _MTM_COE_SRC if c is not None):
            continue
        g = _parse_date_any(_cc_cell(row, _MTM_COE_REFDATE_COL))
        if g is None or g != tgt:
            continue
        cells = []
        for src in _MTM_COE_SRC:
            if src is None:  cells.append('')
            elif src == 0:   cells.append(a_raw.replace('#', '').strip())
            else:            cells.append(_cc_cell(row, src))
        out.append(cells)
    return out, tgt.strftime('%Y-%m-%d')


def _mtm_finalize(buckets):
    """Append [status, maker, checker, id] to each row; return per-book counts."""
    for lob, rws in buckets.items():
        for i, rw in enumerate(rws):
            rw.extend(['New', '', ''])
            rw.append('{}-{}'.format(lob, i))
    return {k: len(v) for k, v in buckets.items()}


def _mtm_normalize_zeros(data):
    """Belt-and-suspenders: any STORED Valor MTM that is exactly zero is KEPT as
    0.00 in the table (canonical #,##0.00 format) + the zero comment, across every
    book. The value is inserted exactly as it comes from the spreadsheet; only the
    preview and generated files bump a zero to 1 in the last decimal place (B3
    rejects a zero MtM) — see _mtm_gen_min_value. Blank (unfilled / 'Missing MtM')
    cells are left untouched. Returns the count normalized."""
    n = 0
    for lob, table in (data.get('tables') or {}).items():
        vidx = _MTM_COE_VALOR_IDX if lob == 'COE' else _MTM_VALOR_IDX
        cidx = _MTM_COE_COMMENT_IDX if lob == 'COE' else _MTM_COMMENT_IDX
        for r in table or []:
            if not r or len(r) <= vidx:
                continue
            raw = '' if r[vidx] is None else str(r[vidx]).strip()
            if raw == '':
                continue                                   # blank / Missing → leave as-is
            v = _mtm_parse_num(raw)
            if v is not None and round(v, 2) == 0:
                r[vidx] = '{:,.2f}'.format(0.0)            # keep 0.00 in the table
                if len(r) > cidx and not str(r[cidx] or '').strip():
                    r[cidx] = _MTM_ZERO_COMMENT
                n += 1
    return n


def _mtm_build_from_folder(folder):
    files = [fn for fn in os.listdir(folder) if os.path.isfile(os.path.join(folder, fn))]
    swap_fn = next((fn for fn in files if _mtm_is_swap_name(fn)), None)
    coe_fn  = next((fn for fn in files if _mtm_is_coe_name(fn)), None)
    buckets = {k: [] for k in _MTM_SWAP_BOOKS}
    buckets['COE'] = []
    ref_date = coe_ref = None
    kept = matched = 0
    if swap_fn:
        with open(os.path.join(folder, swap_fn), 'rb') as fh:
            rows = _cc_read_rows(swap_fn, fh.read())
        sb, ref_date, kept, matched = _mtm_build_swap(rows)
        buckets.update(sb)
    if coe_fn:
        with open(os.path.join(folder, coe_fn), 'rb') as fh:
            rows = _cc_read_rows(coe_fn, fh.read())
        buckets['COE'], coe_ref = _mtm_build_coe(rows)
    # CEM MtM values (VCP_CETIP_MTM) — applied to the CEM book before finalize.
    # Finalize FIRST (adds status/meta) so the value files can set 'Missing MtM'.
    counts = _mtm_finalize(buckets)
    cem_val_fn = next((fn for fn in files if _mtm_is_cem_value_name(fn)), None)
    cem_matched = cem_zeros = cem_missing = 0
    if cem_val_fn and buckets.get('CEM'):
        with open(os.path.join(folder, cem_val_fn), 'rb') as fh:
            vrows = _cc_read_rows(cem_val_fn, fh.read())
        cem_matched, cem_zeros, cem_missing = _mtm_apply_cem_values(buckets['CEM'], vrows)
    edg_val_fn = next((fn for fn in files if _mtm_is_edg_value_name(fn)), None)
    edg_matched = edg_coe_matched = edg_missing = 0
    if edg_val_fn:
        with open(os.path.join(folder, edg_val_fn), 'rb') as fh:
            erows = _cc_read_rows(edg_val_fn, fh.read())
        edg_matched, edg_coe_matched, _ez, edg_missing = _mtm_apply_edg_values({'tables': buckets}, erows)
    # Hybrids MtM values (Stream_level_MTM) — SUMIF by Trade Name via mapping_swap-hyb.json.
    hyb_val_fn = next((fn for fn in files if _mtm_is_hyb_value_name(fn)), None)
    hyb_matched = hyb_zeros = hyb_missing = 0
    if hyb_val_fn and buckets.get('Hybrids'):
        with open(os.path.join(folder, hyb_val_fn), 'rb') as fh:
            hrows = _cc_read_rows(hyb_val_fn, fh.read())
        hyb_matched, hyb_zeros, hyb_missing = _mtm_apply_hyb_values(
            buckets['Hybrids'], hrows, _mtm_load_hyb_mapping())
    # Final guard: canonicalize any zero MtM to 0.00 + zero comment (the table keeps
    # the exact spreadsheet value; the preview/files bump it to 1 cent when generated).
    _mtm_normalize_zeros({'tables': buckets})
    return {
        'success': True, 'tables': buckets, 'counts': counts,
        'ref_date': ref_date, 'coe_ref_date': coe_ref,
        'diagnostics': {'kept': kept, 'matched': matched,
                        'swap_file': swap_fn, 'coe_file': coe_fn,
                        'cem_value_file': cem_val_fn,
                        'cem_matched': cem_matched, 'cem_zeros': cem_zeros, 'cem_missing': cem_missing,
                        'edg_value_file': edg_val_fn,
                        'edg_matched': edg_matched, 'edg_coe_matched': edg_coe_matched,
                        'edg_missing': edg_missing,
                        'hyb_value_file': hyb_val_fn,
                        'hyb_matched': hyb_matched, 'hyb_zeros': hyb_zeros,
                        'hyb_missing': hyb_missing},
    }, (swap_fn, coe_fn)


def _mtm_save(path, data):
    """Persist the MtM dataset, creating the YYYY/MM/DD dir first (mkstemp needs it)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _atomic_write_json(path, data)


def _mtm_load(date_str):
    ymd = _accrual_parse_date(date_str) or datetime.now().strftime('%Y%m%d')
    path = _mtm_path_for(ymd)
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, encoding='utf-8') as fh:
            return path, json.load(fh)
    except Exception:
        log.error('[mtm] read failed %s:\n%s', path, traceback.format_exc())
        return None, None


def _mtm_latest_ymd():
    latest = None
    if not os.path.isdir(MTM_JSON_ROOT):
        return None
    for _root, _dirs, files in os.walk(MTM_JSON_ROOT):
        for fn in files:
            m = re.match(r'mtm_swap_(\d{8})\.json$', fn)
            if m and (latest is None or m.group(1) > latest):
                latest = m.group(1)
    return '{}-{}-{}'.format(latest[:4], latest[4:6], latest[6:8]) if latest else None


def _mtm_find_row(data, lob, rid):
    for r in (data.get('tables') or {}).get(lob, []) or []:
        if r and str(r[-1]) == str(rid):
            return r
    return None


@blueprint.route('/api/mtm-swap/data')
def api_mtm_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    path, data = _mtm_load(request.args.get('date'))
    if not data:
        return jsonify({'success': True, 'empty': True})
    # Repair legacy datasets: canonicalize any zero MtM to 0.00 + zero comment so the
    # table shows the exact spreadsheet value (the preview/files bump it to 1 cent).
    if path and _mtm_normalize_zeros(data):
        try:
            _atomic_write_json(path, data)
        except Exception:
            log.error('[mtm] zero-normalize save failed:\n%s', traceback.format_exc())
    data['success'] = True
    return jsonify(data)


@blueprint.route('/api/mtm-swap/latest')
def api_mtm_latest():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True, 'date': _mtm_latest_ymd()})


@blueprint.route('/api/mtm-swap/mapping/add', methods=['POST'])
def api_mtm_mapping_add():
    """Append a Hybrids Trade Name mapping (B3 ID / Hybrids ID / Trade Name) to
    mapping_swap-hyb.json (used by the Hybrids MtM SUMIF)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p    = request.get_json(silent=True) or {}
    b3   = str(p.get('b3_id') or '').strip()
    hyb  = str(p.get('hybrids_id') or '').strip()
    name = str(p.get('trade_name') or '').strip()
    if not (b3 and hyb and name):
        return jsonify({'success': False, 'error': 'All three fields are required.'}), 400
    mapping = _mtm_load_hyb_mapping()
    mapping.append({'b3_id': b3, 'hybrids_id': hyb, 'trade_name': name})
    try:
        _atomic_write_json(_MTM_HYB_MAP_PATH, mapping)
    except Exception:
        log.error('[mtm] mapping add failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    return jsonify({'success': True, 'count': len(mapping),
                    'entry': {'b3_id': b3, 'hybrids_id': hyb, 'trade_name': name}})


@blueprint.route('/api/mtm-swap/import-folder', methods=['POST'])
def api_mtm_import_folder():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p   = request.get_json(silent=True) or {}
    ymd = _accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    folder = _mtm_source_dir(ymd)
    if not os.path.isdir(folder):
        return jsonify({'success': False, 'error': 'Folder not found: {}'.format(folder)}), 400
    try:
        result, (swap_fn, coe_fn) = _mtm_build_from_folder(folder)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        log.error('[mtm] import-folder failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the MTM files.'}), 500
    if not swap_fn and not coe_fn:
        return jsonify({'success': False, 'error': 'No MTM files found in {}'.format(folder)}), 400

    result['date'] = datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d')
    try:
        _mtm_save(_mtm_path_for(ymd), result)
    except Exception:
        log.error('[mtm] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to save the imported data.'}), 500

    swap_n = sum(result['counts'].get(k, 0) for k in _MTM_SWAP_BOOKS)
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Imported', 'MtM',
                         '{} swap · {} COE'.format(swap_n, result['counts'].get('COE', 0)) + _nd_token(ymd))
    return jsonify(result)


@blueprint.route('/api/mtm-swap/row/comment', methods=['POST'])
def api_mtm_row_comment():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    path, data = _mtm_load(p.get('date'))
    if not data:
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    r = _mtm_find_row(data, p.get('lob', ''), p.get('id', ''))
    if not r:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    r[len(r) - 5] = str(p.get('comment', ''))            # Comments = last data cell
    try:
        _atomic_write_json(path, data)
    except Exception:
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    return jsonify({'success': True})


@blueprint.route('/api/mtm-swap/row/edit', methods=['POST'])
def api_mtm_row_edit():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    sid = session.get('user_sid', '')
    path, data = _mtm_load(p.get('date'))
    if not data:
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    r = _mtm_find_row(data, p.get('lob', ''), p.get('id', ''))
    if not r:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    cells = p.get('cells', [])
    for i, v in enumerate(cells):
        if i < len(r) - 4:
            r[i] = v
    r[-4], r[-3], r[-2] = 'Pending', sid, ''             # status, maker, checker (reset)
    try:
        _atomic_write_json(path, data)
    except Exception:
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _create_notification(sid, session.get('user_name', ''), 'MTM Updated', 'MtM',
                         '{} · {}'.format(p.get('lob', ''), p.get('id', '')) + _nd_token(p.get('date')))
    return jsonify({'success': True, 'row': r})


@blueprint.route('/api/mtm-swap/row/send', methods=['POST'])
def api_mtm_row_send():
    """Confirm a row (New/Pending → Sent). Maker/checker guard: whoever last changed
    the row cannot confirm it — a different user must."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    sid = session.get('user_sid', '')
    path, data = _mtm_load(p.get('date'))
    if not data:
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    r = _mtm_find_row(data, p.get('lob', ''), p.get('id', ''))
    if not r:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    if str(r[-3] or '') == sid:                          # maker == current user → blocked
        return jsonify({'success': False, 'error': 'same_user'}), 403
    r[-4], r[-2] = 'Sent', sid                           # status, checker
    try:
        _atomic_write_json(path, data)
    except Exception:
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _create_notification(sid, session.get('user_name', ''), 'MTM Sent', 'MtM',
                         '{} · {}'.format(p.get('lob', ''), p.get('id', '')) + _nd_token(p.get('date')))
    return jsonify({'success': True, 'row': r})


@blueprint.route('/api/mtm-swap/row/delete', methods=['POST'])
def api_mtm_row_delete():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob, rid = p.get('lob', ''), str(p.get('id', ''))
    path, data = _mtm_load(p.get('date'))
    if not data:
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    rows = (data.get('tables') or {}).get(lob)
    if rows is None:
        return jsonify({'success': False, 'error': 'Book not found.'}), 404
    data['tables'][lob] = [r for r in rows if not (r and str(r[-1]) == rid)]
    data['counts'][lob] = len(data['tables'][lob])
    try:
        _atomic_write_json(path, data)
    except Exception:
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Deleted', 'MtM', '{} · 1 row'.format(lob) + _nd_token(p.get('date')))
    return jsonify({'success': True, 'counts': data['counts']})


@blueprint.route('/api/mtm-swap/rows/delete', methods=['POST'])
def api_mtm_rows_delete():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob = p.get('lob', '')
    ids = {str(x) for x in (p.get('ids') or [])}
    path, data = _mtm_load(p.get('date'))
    if not data or lob not in (data.get('tables') or {}):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    data['tables'][lob] = [r for r in data['tables'][lob] if not (r and str(r[-1]) in ids)]
    data['counts'][lob] = len(data['tables'][lob])
    try:
        _atomic_write_json(path, data)
    except Exception:
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Deleted', 'MtM', '{} · {} rows'.format(lob, len(ids)) + _nd_token(p.get('date')))
    return jsonify({'success': True, 'counts': data['counts']})


@blueprint.route('/api/mtm-swap/process', methods=['POST'])
def api_mtm_process():
    """Dropzone upload: detect swap vs COE by filename, build that portion and merge
    it into the selected date's saved dataset (the other portion is preserved)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'No file provided.'}), 400
    ymd = _accrual_parse_date(request.form.get('date')) or datetime.now().strftime('%Y%m%d')
    try:
        rows = _cc_read_rows(f.filename, f.read())
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        log.error('[mtm] process read failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the file.'}), 500

    # Load existing dataset for the date (or start a fresh skeleton).
    _, data = _mtm_load(datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d'))
    if not data:
        data = {'success': True, 'tables': {k: [] for k in _MTM_SWAP_BOOKS},
                'counts': {}, 'ref_date': None, 'coe_ref_date': None,
                'date': datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d')}
        data['tables']['COE'] = []

    if _mtm_is_cem_value_name(f.filename):
        cem_rows = (data.get('tables') or {}).get('CEM', [])
        if not cem_rows:
            return jsonify({'success': False,
                            'error': 'No CEM contracts loaded for this date — import the swap file first.'}), 400
        m, z, miss = _mtm_apply_cem_values(cem_rows, rows)   # Valor MTM + Missing MtM on CEM
        data['diagnostics'] = dict(data.get('diagnostics') or {},
                                   cem_value_file=f.filename, cem_matched=m, cem_zeros=z, cem_missing=miss)
    elif _mtm_is_edg_value_name(f.filename):
        if not (data.get('tables') or {}).get('EDG') and not (data.get('tables') or {}).get('COE'):
            return jsonify({'success': False,
                            'error': 'No EDG/COE rows loaded for this date — import the swap/COE files first.'}), 400
        em, cm, z, miss = _mtm_apply_edg_values(data, rows)  # JP* → COE, else EDG; + Missing MtM
        data['diagnostics'] = dict(data.get('diagnostics') or {},
                                   edg_value_file=f.filename, edg_matched=em, edg_coe_matched=cm,
                                   edg_zeros=z, edg_missing=miss)
    elif _mtm_is_coe_name(f.filename):
        coe_rows, coe_ref = _mtm_build_coe(rows)
        for i, rw in enumerate(coe_rows):
            rw.extend(['New', '', ''])
            rw.append('COE-{}'.format(i))
        data['tables']['COE'] = coe_rows
        data['coe_ref_date'] = coe_ref
    elif _mtm_is_swap_name(f.filename):
        buckets, ref_date, _kept, _matched = _mtm_build_swap(rows)
        for lob in _MTM_SWAP_BOOKS:
            rws = buckets.get(lob, [])
            for i, rw in enumerate(rws):
                rw.extend(['New', '', ''])
                rw.append('{}-{}'.format(lob, i))
            data['tables'][lob] = rws
        data['ref_date'] = ref_date
    else:
        return jsonify({'success': False,
                        'error': 'Unrecognized file. Expected the swap (…SemAtualMID), COE (…ConsultaMTMCOE), CEM values (VCP_CETIP_MTM) or EDG/COE values (Stream_level_MTM) file.'}), 400

    data['counts'] = {k: len(v) for k, v in data['tables'].items()}
    try:
        _mtm_save(_mtm_path_for(ymd), data)
    except Exception:
        log.error('[mtm] process save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to save.'}), 500
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Imported', 'MtM', f.filename + _nd_token(ymd))
    return jsonify(data)


# ---------------------------------------------------------------------------
#  MtM — fixed-width Conecta file generation (Send batch / Validation)
#  Header (control) line: tipo-linha '0'; data lines: tipo-linha '1'.
#  Rows use the datepicker date; headers use TODAY (system date).
#  Files saved to CONECTA_NEW_PATH and the day's MTM source folder.
# ---------------------------------------------------------------------------
# Intragroup fund accounts that register a mirror line (opposite sign) against the
# Banco book. Atacama (85398.00-5) and Lawton (00041.00-7) trade ONLY vs Banco.
# MGT (04880.00-6) faces only Banco + external clients — never Lawton/Atacama — so
# it is NOT a mirror counterparty here.
_MTM_GEN_LAWTON_ACCT  = '00041007'                   # Lawton  = 00041.00-7
_MTM_GEN_ATACAMA_ACCT = {'85398005'}                 # Atacama = 85398.00-5
_MTM_GEN_PARTY = {                                   # Nome Simplificado Parte (20 chars)
    'BANCO':   'JPMORGANBM'       + ' ' * 10,
    'LAWTON':  'INTRAGLAWTONFDO'  + ' ' * 5,
    'ATACAMA': 'INTRAGATACAMAFDO' + ' ' * 4,
}
_MTM_GEN_PARTY_ACCT = {                              # Código Conta Parte per view
    'BANCO': '73760009', 'LAWTON': '00041007', 'ATACAMA': '85398005',
}
_MTM_GEN_BOOK_SUFFIX = {'EDG': 'EDG', 'CEM': 'CEM', 'Hybrids': 'HYB'}
# Fixed counterparty file per book: EDG→Atacama, CEM/Hybrids→Lawton
# (MtM_ATACAMA-EDG, MtM_LAWTON-CEM, MtM_LAWTON-HYB).
_MTM_GEN_BOOK_CPTY = {'EDG': 'ATACAMA', 'CEM': 'LAWTON', 'Hybrids': 'LAWTON'}
_MTM_GEN_SWAP_COLS = ['ID do Sistema', 'ID Tipo de Linha', 'Código da Operação', 'Meu Número',
                      'Código do Contrato', 'Nome Simplificado Parte', 'Código Conta Parte',
                      'Sinal Valor MTM', 'Valor MTM', 'Notional Mínimo', 'Notional Máximo',
                      'Data de Referência MTM']
_MTM_GEN_COE_COLS  = ['Tipo IF', 'Tipo de Linha', 'Código operação', 'Código do Instrumento Financeiro',
                      'Conta do Emissor', 'Data Referência', 'Valor MTM', 'Débito/Crédito']


def _mtm_gen_min_value(v):
    """Zero MtM → the smallest registrable amount (1 in the last available decimal
    place, i.e. 0.01), since B3 rejects a zero MtM. Applied ONLY when generating the
    preview / file — the table keeps the spreadsheet's exact 0.00. Non-zero values
    pass through unchanged."""
    v = v or 0.0
    return 0.01 if round(v, 2) == 0 else v


def _mtm_valor_fixed(v, int_digits):
    """Absolute value as (int_digits + 2) zero-padded digits (implicit 2 decimals)."""
    return str(int(round(abs(v or 0.0) * 100))).zfill(int_digits + 2)


def _mtm_rand_meunum():
    return ''.join(random.choice('0123456789') for _ in range(10))


def _mtm_cpty_of(row):
    """Lawton / Atacama / None from the book row's CONTRAPARTE / Conta (idx 4)."""
    acct = _acc_digits(row[4] if len(row) > 4 else '')
    if acct == _MTM_GEN_LAWTON_ACCT:
        return 'LAWTON'
    if acct in _MTM_GEN_ATACAMA_ACCT:
        return 'ATACAMA'
    return None


def _mtm_swap_fields(cid, party_key, sinal, v, ymd):
    return {
        'ID do Sistema': 'MID  ', 'ID Tipo de Linha': '1', 'Código da Operação': '0848',
        'Meu Número': _mtm_rand_meunum(), 'Código do Contrato': str(cid or ''),
        'Nome Simplificado Parte': _MTM_GEN_PARTY[party_key],
        'Código Conta Parte': _MTM_GEN_PARTY_ACCT[party_key],
        'Sinal Valor MTM': sinal, 'Valor MTM': _mtm_valor_fixed(_mtm_gen_min_value(v), 10),
        'Notional Mínimo': ' ' * 6, 'Notional Máximo': ' ' * 6, 'Data de Referência MTM': ymd,
    }


def _mtm_swap_header(party_key, today):
    return 'MID' + '  ' + '0' + '0848' + _MTM_GEN_PARTY[party_key] + today


def _mtm_coe_header(today):
    return 'COE' + '  ' + '0' + '0475' + _MTM_GEN_PARTY['BANCO'] + today


def _mtm_generate_book(book_key, rows, ymd):
    """Files for one swap book: MtM_BANCO-<suffix> always; plus the book's fixed
    counterparty file (EDG→Atacama, CEM/Hybrids→Lawton) with the mirror rows
    (opposite sign) for that book's intragroup contracts."""
    suffix = _MTM_GEN_BOOK_SUFFIX.get(book_key)
    if not suffix:
        return {}
    book_cpty = _MTM_GEN_BOOK_CPTY.get(book_key)     # ATACAMA (EDG) / LAWTON (CEM,HYB)
    today = datetime.now().strftime('%Y%m%d')
    banco = 'MtM_BANCO-' + suffix
    files = {banco: {'view': 'BANCO', 'cols': _MTM_GEN_SWAP_COLS,
                     'header': _mtm_swap_header('BANCO', today), 'rows': []}}
    for row in rows:
        v = _mtm_parse_num(row[7]) or 0.0            # Valor MTM (display) → float
        cid = row[0]
        sinal = '00' if v >= 0 else '01'
        files[banco]['rows'].append(_mtm_swap_fields(cid, 'BANCO', sinal, v, ymd))
        # Mirror only the rows whose counterparty matches the book's fixed side.
        if book_cpty and _mtm_cpty_of(row) == book_cpty:
            fn = 'MtM_' + book_cpty + '-' + suffix
            files.setdefault(fn, {'view': book_cpty, 'cols': _MTM_GEN_SWAP_COLS,
                                  'header': _mtm_swap_header(book_cpty, today), 'rows': []})
            files[fn]['rows'].append(_mtm_swap_fields(cid, book_cpty, '01' if v >= 0 else '00', v, ymd))
    return files


def _mtm_generate_coe(rows, ymd):
    today = datetime.now().strftime('%Y%m%d')
    f = {'view': 'BANCO', 'cols': _MTM_GEN_COE_COLS, 'header': _mtm_coe_header(today), 'rows': []}
    for row in rows:
        v = _mtm_parse_num(row[_MTM_COE_VALOR_IDX]) or 0.0
        f['rows'].append({
            'Tipo IF': 'COE  ', 'Tipo de Linha': '1', 'Código operação': '0475',
            'Código do Instrumento Financeiro': str(row[0] or ''), 'Conta do Emissor': '73760401',
            'Data Referência': ymd, 'Valor MTM': _mtm_valor_fixed(_mtm_gen_min_value(v), 16),
            'Débito/Crédito': '+' if v >= 0 else '-',
        })
    return {'MtM_BANCO-COE': f}


def _mtm_file_lines(fdata):
    return [fdata['header']] + [''.join(r[c] for c in fdata['cols']) for r in fdata['rows']]


def _mtm_write_gen_files(files, ymd):
    """Write each file (.txt, Latin-1, CRLF) to CONECTA_NEW_PATH and the day's MTM
    source folder. Returns list of written paths (best-effort)."""
    dests = [CONECTA_NEW_PATH, _mtm_source_dir(ymd)]
    written = []
    for fname, fdata in files.items():
        content = '\r\n'.join(_mtm_file_lines(fdata)) + '\r\n'
        for d in dests:
            try:
                os.makedirs(d, exist_ok=True)
                path = os.path.join(d, fname + '.txt')
                with open(path, 'w', encoding='latin-1', newline='') as fh:
                    fh.write(content)
                written.append(path)
            except Exception:
                log.error('[mtm] write %s → %s failed:\n%s', fname, d, traceback.format_exc())
    return written


def _mtm_gen_preview(files):
    """Preview payload: per file, the parsed columns/rows for the modal table."""
    return [{'filename': fn + '.txt', 'view': fd['view'], 'cols': fd['cols'],
             'header': fd['header'], 'rows': [[r[c] for c in fd['cols']] for r in fd['rows']]}
            for fn, fd in files.items()]


@blueprint.route('/api/mtm-swap/send-batch', methods=['POST'])
def api_mtm_send_batch():
    """Generate the fixed-width Conecta file(s) for ONE book (Send batch)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob = p.get('lob', '')
    ymd = _accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    _, data = _mtm_load(datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d'))
    if not data:
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    rows = (data.get('tables') or {}).get(lob) or []
    if not rows:
        return jsonify({'success': False, 'error': 'No rows in this book to generate.'}), 400
    try:
        files = _mtm_generate_coe(rows, ymd) if lob == 'COE' else _mtm_generate_book(lob, rows, ymd)
    except Exception:
        log.error('[mtm] send-batch build failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Generation failed.'}), 500
    if not files:
        return jsonify({'success': False, 'error': 'Nothing to generate for this book.'}), 400
    written = _mtm_write_gen_files(files, ymd)
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Sent', 'MtM',
                         '{} · {} file(s)'.format(lob, len(files)) + _nd_token(ymd))
    return jsonify({'success': True, 'files': _mtm_gen_preview(files), 'written': len(written)})


@blueprint.route('/api/mtm-swap/row/preview', methods=['POST'])
def api_mtm_row_preview():
    """Preview the fixed-width Conecta file line(s) that ONE row would generate
    (double-click on a table row). Same generator/format as Send batch, but scoped
    to the single contract — nothing is written to disk."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob = p.get('lob', '')
    rid = str(p.get('id', ''))
    ymd = _accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    _, data = _mtm_load(datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d'))
    if not data:
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    rows = (data.get('tables') or {}).get(lob) or []
    row = next((r for r in rows if str(r[-1]) == rid), None)
    if row is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    if str(row[-4]) == _MTM_STATUS_MISSING:
        return jsonify({'success': False, 'error': 'missing_mtm'}), 400
    try:
        files = _mtm_generate_coe([row], ymd) if lob == 'COE' else _mtm_generate_book(lob, [row], ymd)
    except Exception:
        log.error('[mtm] row preview build failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Generation failed.'}), 500
    if not files:
        return jsonify({'success': False, 'error': 'Nothing to generate for this row.'}), 400
    return jsonify({'success': True, 'files': _mtm_gen_preview(files)})


# ── MtM Validation / End Process (EOM) — e-mail to Brazil OTC Ops ──────────────
#  From otc.tracker@jpmorgan.com → brazil.otc.ops@jpmorgan.com.
#  Validation: generate all book files (CEM/EDG/Hybrids swap + COE), attach the
#  Lawton/Atacama view files. End Process: summary of 'Check' rows (recon) with
#  their comments, or a 'no divergence' notice when there are none.
_MTM_VAL_BOOKS = ('CEM', 'EDG', 'Hybrids')           # swap books (+ COE handled apart)


def _mtm_missing_rows(data, books):
    """Rows still flagged 'Missing MtM' (no MtM value) across the given books."""
    out, tables = [], (data.get('tables') or {})
    for lob in books:
        for r in tables.get(lob, []) or []:
            if r and str(r[-4] or '').strip().lower().startswith('missing'):
                out.append({'lob': lob, 'codigo': str(r[0] or ''), 'id': str(r[-1])})
    return out


def _mtm_check_status_rows(data):
    """(checks, uncommented) — rows whose status is 'Check' (recon divergence).
    MtM row = data cells + [status(-4), maker(-3), checker(-2), id(-1)]; Comments = -5."""
    checks, pending = [], []
    for lob, table in (data.get('tables') or {}).items():
        for r in table or []:
            if not r or len(r) < 5:
                continue
            if str(r[-4] or '').strip().lower() == 'check':
                comment = str(r[-5] or '').strip()
                item = {'id': str(r[-1]), 'lob': lob, 'codigo': str(r[0] or ''), 'comment': comment}
                checks.append(item)
                if not comment:
                    pending.append(item)
    return checks, pending


def _send_mtm_validation_email(subject, html, logo_path, attach_paths):
    """SMTP-only MtM EOM validation e-mail to Brazil OTC Ops, attaching the
    Lawton/Atacama view files. HTML/logo resolved by the caller. Best-effort."""
    from email.mime.image import MIMEImage
    from email.mime.base import MIMEBase
    from email import encoders
    try:
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = SHARED_MAILBOX
        msg['To'] = CETIP_OTC_OPS_EMAIL
        related = MIMEMultipart('related')
        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText('MtM EOM validation files attached.', 'plain', 'utf-8'))
        alt.attach(MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)
        if logo_path:
            with open(logo_path, 'rb') as f:
                img = MIMEImage(f.read())
            img.add_header('Content-ID', '<otc_logo>')
            img.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(img)
        msg.attach(related)
        for path in attach_paths:
            try:
                with open(path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(path))
                msg.attach(part)
            except Exception:
                log.warning('[mtm] could not attach %s:\n%s', path, traceback.format_exc())
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.sendmail(SHARED_MAILBOX, [CETIP_OTC_OPS_EMAIL], msg.as_string())
        log.info('[mtm] validation e-mail sent to %s', CETIP_OTC_OPS_EMAIL)
        return True
    except Exception:
        log.error('[mtm] validation e-mail FAILED:\n%s', traceback.format_exc())
        return False


def _send_mtm_endprocess_email(subject, html, logo_path):
    """SMTP-only MtM EOM final-status e-mail to Brazil OTC Ops. Best-effort."""
    from email.mime.image import MIMEImage
    try:
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = SHARED_MAILBOX
        msg['To'] = CETIP_OTC_OPS_EMAIL
        msg['Cc'] = ', '.join(_ACC_ENDPROC_CC)               # same From/To/Cc as accrual end-process
        related = MIMEMultipart('related')
        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText('MtM Swap EOM final status.', 'plain', 'utf-8'))
        alt.attach(MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)
        if logo_path:
            with open(logo_path, 'rb') as f:
                img = MIMEImage(f.read())
            img.add_header('Content-ID', '<otc_logo>')
            img.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(img)
        msg.attach(related)
        recipients = [CETIP_OTC_OPS_EMAIL] + _ACC_ENDPROC_CC
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.sendmail(SHARED_MAILBOX, recipients, msg.as_string())
        log.info('[mtm] end-process e-mail sent to %s (cc %s)', CETIP_OTC_OPS_EMAIL, _ACC_ENDPROC_CC)
        return True
    except Exception:
        log.error('[mtm] end-process e-mail FAILED:\n%s', traceback.format_exc())
        return False


@blueprint.route('/api/mtm-swap/validation', methods=['POST'])
def api_mtm_validation():
    """EOM Validation: generate the batch files for ALL MtM books (CEM/EDG/Hybrids
    swap + COE), then e-mail the Lawton/Atacama view files to Brazil OTC Ops."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    ymd = _accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    path, data = _mtm_load(datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d'))
    if not data or not data.get('tables'):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404

    missing = _mtm_missing_rows(data, list(_MTM_VAL_BOOKS) + ['COE'])   # block if any row lacks a value
    if missing:
        return jsonify({'success': False, 'error': 'missing_accrual', 'missing': missing}), 400

    tables = data.get('tables') or {}
    files = {}
    try:
        for lob in _MTM_VAL_BOOKS:
            rows = tables.get(lob) or []
            if rows:
                files.update(_mtm_generate_book(lob, rows, ymd))
        coe_rows = tables.get('COE') or []
        if coe_rows:
            files.update(_mtm_generate_coe(coe_rows, ymd))
    except Exception:
        log.error('[mtm] validation generate failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to write the batch files.'}), 500
    if not files:
        return jsonify({'success': False, 'error': 'No records to validate.'}), 400

    _mtm_write_gen_files(files, ymd)

    # All batch files generated → mark EVERY row in ALL tables as 'Sent'
    # (checker = current user) and persist, so the page reflects the finished run.
    sid = session.get('user_sid', '')
    for lob_rows in (data.get('tables') or {}).values():
        for r in lob_rows or []:
            if r and len(r) >= 4:
                r[-4], r[-2] = 'Sent', sid
    try:
        _mtm_save(path, data)
    except Exception:
        log.error('[mtm] validation status save failed:\n%s', traceback.format_exc())

    ref = datetime.strptime(ymd, '%Y%m%d')
    summary = [{'filename': fn + '.txt', 'view': fd['view'], 'count': len(fd['rows'])}
               for fn, fd in files.items()]
    attach = [os.path.join(CONECTA_NEW_PATH, fn + '.txt')
              for fn, fd in files.items() if fd['view'] in ('LAWTON', 'ATACAMA')]
    subject = 'MtM EOM - {} - Validation'.format(ref.strftime('%d/%m/%Y'))
    try:
        html = render_template(
            'pages/email-template-mtm-validation.html',
            ref_date_fmt=ref.strftime('%d/%m/%Y'), generated_files=summary,
            attachment_names=[os.path.basename(a) for a in attach],
            current_year=datetime.now().year)
        logo_path = _get_logo_path()
        threading.Thread(target=_send_mtm_validation_email,
                         args=(subject, html, logo_path, attach), daemon=True).start()
    except Exception:
        log.error('[mtm] validation e-mail prep failed:\n%s', traceback.format_exc())

    total = sum(len(fd['rows']) for fd in files.values())
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Sent', 'MtM',
                         'EOM Validation · {} file(s), {} attached'.format(len(files), len(attach)) + _nd_token(ymd))
    return jsonify({'success': True, 'files': summary,
                    'attached': [os.path.basename(a) for a in attach],
                    'total': total, 'mail': 'queued'})


@blueprint.route('/api/mtm-swap/end-process', methods=['POST'])
def api_mtm_end_process():
    """Finish the EOM MtM Swap process: every 'Check' row must be commented; then
    e-mail the final status to Brazil OTC Ops (summary table or 'no divergence')."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    ymd = _accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    _, data = _mtm_load(datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d'))
    if not data or not data.get('tables'):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404

    checks, pending = _mtm_check_status_rows(data)
    if pending:
        return jsonify({'success': False, 'error': 'uncommented', 'pending': pending}), 400

    ref = datetime.strptime(ymd, '%Y%m%d')
    subject = 'MtM Swap - EOM - Final Status - {}'.format(ref.strftime('%d/%m/%Y'))
    try:
        html = render_template(
            'pages/email-template-mtm-endprocess.html',
            ref_date_fmt=ref.strftime('%d/%m/%Y'), has_check=bool(checks), checks=checks,
            folder=_mtm_source_dir(ymd), current_year=datetime.now().year)
        logo_path = _get_logo_path()
        threading.Thread(target=_send_mtm_endprocess_email,
                         args=(subject, html, logo_path), daemon=True).start()
    except Exception:
        log.error('[mtm] end-process e-mail prep failed:\n%s', traceback.format_exc())

    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Sent', 'MtM',
                         'End Process · {} check row(s)'.format(len(checks)) + _nd_token(ymd))
    return jsonify({'success': True, 'checks': len(checks)})


# ── MtM Recon: match the B3 ConsultaInformacoesAtualizMID file against the page ──
#  File name (source folder): Swap-MID-ConsultaInformacoesAtualizMID.<ext>.
#  Header row = 8, data from row 9. Col A = contract ID ('#' removed so it matches
#  the page's Código IF). Col D = house account (73760.00-9)
#  filter. Col G = registered MtM (signed). A page row whose Valor MTM equals the
#  file value → Success (green pill); a divergence → Check (red pill, tooltip = file
#  value) and its Comments field is unlocked.
def _mtm_is_recon_name(n):
    return 'consultainformacoesatualizmid' in _mtm_norm_party(n)


def _mtm_recon_key(s):
    """Contract-ID match key: drop the '#' (replace with nothing) and normalize to
    match the page's Código IF."""
    return str(s or '').replace('#', '').strip().strip("'").strip('"').upper()


def _mtm_run_recon(data, rows):
    """Build {ID → registered MtM} from the ConsultaInformacoesAtualizMID rows (house
    account only) and flag each page row Success/Check by value equality. Mutates
    data (recon map + status). Returns a summary dict."""
    fmap = {}
    for i in range(_MTM_RECON_DATA_ROW, len(rows)):
        row = rows[i]
        if _acc_digits(_cc_cell(row, _MTM_FILTER_COL)) != _MTM_ACCOUNT:      # col D
            continue
        key = _mtm_recon_key(_cc_cell(row, 0))                              # col A
        val = _mtm_parse_num_br(_cc_cell(row, _MTM_RECON_VALUE_COL))        # col G (BRL format)
        if not key or val is None:
            continue
        fmap.setdefault(key, round(val, 2))

    recon_out, ok_rows, check_rows = {}, 0, 0
    for lob, table in (data.get('tables') or {}).items():
        vidx = _MTM_COE_VALOR_IDX if lob == 'COE' else _MTM_VALOR_IDX
        for r in table or []:
            if not r or len(r) < 5:
                continue
            key = _mtm_recon_key(r[0])
            if key not in fmap:
                continue
            fv = fmap[key]
            pv = _mtm_parse_num(r[vidx])
            # Compare against the value we'd register: a page 0.00 is generated as
            # 0.01 (B3 rejects a zero MtM), so it should reconcile with the file's 0.01.
            ok = (pv is not None and round(_mtm_gen_min_value(pv), 2) == fv)
            recon_out[str(r[-1])] = {'ok': ok, 'file': '{:,.2f}'.format(fv)}
            r[-4] = 'Success' if ok else 'Check'                            # status
            if ok: ok_rows += 1
            else:  check_rows += 1
    data['recon'] = recon_out
    return {'success_rows': ok_rows, 'check_rows': check_rows, 'map_entries': len(fmap)}


def _mtm_find_recon_file(folder):
    if not os.path.isdir(folder):
        return None
    for fn in os.listdir(folder):
        if os.path.isfile(os.path.join(folder, fn)) and _mtm_is_recon_name(fn):
            return os.path.join(folder, fn)
    return None


@blueprint.route('/api/mtm-swap/recon', methods=['POST'])
def api_mtm_recon():
    """Reconcile the saved MtM values against the B3 ConsultaInformacoesAtualizMID
    return file (uploaded via the dropzone, or read from the run folder)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    date_arg = request.form.get('date')
    path, data = _mtm_load(date_arg)
    if not data or not data.get('tables'):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404

    ymd = _accrual_parse_date(date_arg) or datetime.now().strftime('%Y%m%d')
    try:
        if f and f.filename:
            rows = _cc_read_rows(f.filename, f.read())
        else:
            op = _mtm_find_recon_file(_mtm_source_dir(ymd))
            if not op:
                return jsonify({'success': False,
                                'error': 'ConsultaInformacoesAtualizMID file not found in {}'.format(_mtm_source_dir(ymd))}), 400
            with open(op, 'rb') as fh:
                rows = _cc_read_rows(os.path.basename(op), fh.read())
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        log.error('[mtm] recon read failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the recon file.'}), 500

    summary = _mtm_run_recon(data, rows)
    try:
        _mtm_save(path, data)
    except Exception:
        log.error('[mtm] recon save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to save the recon result.'}), 500

    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Mapped', 'MtM',
                         'Recon · {} ok, {} check'.format(summary['success_rows'], summary['check_rows']) + _nd_token(ymd))
    return jsonify({
        'success': True,
        'tables': data.get('tables') or {},
        'counts': data.get('counts') or {},
        'recon': data.get('recon') or {},
        'ref_date': data.get('ref_date'), 'date': data.get('date'),
        'summary': summary,
    })


def _accrual_build_result(rows):
    """Core VCP→tables logic (no I/O). Splits the rows into the four LOB books and
    returns the result dict (without 'date'/'saved_at')."""
    records, ref_date = _swap_pos_latest_records()
    lob_map = _swap_pos_lob_map(records)

    buckets = {'CEM': [], 'EDG': [], 'Hybrids': [], 'Commodities': []}
    total = kept = matched = 0
    for i in range(_ACC_HEADER_ROW, len(rows)):
        row = rows[i]
        a_raw = _cc_cell(row, 0)
        if not a_raw and not any(_cc_cell(row, c) for c in _ACC_DISPLAY_SRC if c is not None):
            continue                                    # fully blank line
        total += 1
        contract = a_raw.replace('#', '').strip()       # col A: drop '#'
        if _acc_digits(_cc_cell(row, _ACC_ACCOUNT_COL)) not in _ACC_ACCOUNTS:
            continue                                    # col K: house accounts only
        kept += 1
        ident = lob_map.get(contract.upper())
        if ident is None:
            ident = lob_map.get('#' + _acc_digits(contract))
        lob = _accrual_lob(ident)
        if not lob:
            continue                                    # IF not found / unclassified
        matched += 1
        # Build the row aligned to _ACC_FIXED_HEADERS (None src → empty placeholder).
        cells = []
        for src in _ACC_DISPLAY_SRC:
            if src is None:      cells.append('')
            elif src == 0:       cells.append(contract)         # Código IF (# stripped)
            else:                cells.append(_cc_cell(row, src))
        buckets[lob].append(cells)

    # Append, per row, the maker/checker meta and a stable id as the LAST cell.
    # Row layout: [ ...fixed data cells..., status, maker, checker, id ]
    for _lob, _rws in buckets.items():
        for _i, _rw in enumerate(_rws):
            _rw.extend(['New', '', ''])                # status, maker, checker
            _rw.append('{}-{}'.format(_lob, _i))       # stable id (last cell)

    return {
        'success': True,
        'headers': list(_ACC_FIXED_HEADERS),
        'tables': buckets,
        'counts': {k: len(v) for k, v in buckets.items()},
        'ref_date': ref_date,
        'diagnostics': {'total': total, 'kept': kept, 'matched': matched,
                        'position_records': len(records)},
    }


def _accrual_persist(result, source_file, ymd=None):
    """Persist a build result under static/data/cache/accrual/YYYY/MM/DD/. Defaults
    to today; pass ymd ('YYYYMMDD') to store under the run/reference date instead.
    Returns (path, saved_dict)."""
    now = datetime.now()
    ymd = ymd or now.strftime('%Y%m%d')
    out_dir = os.path.join(ACCRUAL_JSON_ROOT, ymd[:4], ymd[4:6], ymd[6:8])
    os.makedirs(out_dir, exist_ok=True)
    saved = dict(result)
    saved['date']        = '{}-{}-{}'.format(ymd[:4], ymd[4:6], ymd[6:8])
    saved['saved_at']    = now.strftime('%Y-%m-%d %H:%M:%S')
    saved['source_file'] = source_file
    path = os.path.join(out_dir, 'accrual_swap_{}.json'.format(ymd))
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(saved, fh, ensure_ascii=False, indent=2)
    log.info('[accrual] saved %s', path)
    return path, saved


@blueprint.route('/api/accrual-swap/process', methods=['POST'])
def api_accrual_swap_process():
    """Process the VCP spreadsheet → rows split into CEM/EDG/Hybrids/Commodities."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'No file uploaded.'}), 400
    try:
        rows = _cc_read_rows(f.filename, f.read())
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        log.error('[accrual] read failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the spreadsheet.'}), 500

    if len(rows) < _ACC_HEADER_ROW:
        return jsonify({'success': False,
                        'error': 'File has fewer than {} rows — headers expected on row {}.'
                        .format(_ACC_HEADER_ROW, _ACC_HEADER_ROW)}), 400

    result = _accrual_build_result(rows)
    try:
        _, saved = _accrual_persist(result, f.filename)
        result['date'] = saved['date']
    except Exception:
        log.error('[accrual] save failed:\n%s', traceback.format_exc())
        result['date'] = datetime.now().strftime('%Y-%m-%d')

    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Imported', 'Accrual',
                         'VCP · {} classified'.format(result.get('diagnostics', {}).get('matched', 0)) + _nd_token(result.get('date')))
    return jsonify(result)


# ── Accrual JSON helpers (load/save a specific day's file) ───────────────────
# Row layout: [ ...data cells..., status, maker, checker, id ]  (id is last)
def _accrual_path_for(ymd):
    return os.path.join(ACCRUAL_JSON_ROOT, ymd[:4], ymd[4:6], ymd[6:8],
                        'accrual_swap_{}.json'.format(ymd))


def _accrual_latest_ymd():
    """Newest saved accrual date as 'YYYY-MM-DD' (scans accrual_swap_*.json under
    ACCRUAL_JSON_ROOT), or None if nothing saved yet. Lets the page land on the
    most recent dataset when no explicit date is requested (e.g. from a bell
    notification), instead of an empty 'today'."""
    latest = None
    if not os.path.isdir(ACCRUAL_JSON_ROOT):
        return None
    for _root, _dirs, files in os.walk(ACCRUAL_JSON_ROOT):
        for fn in files:
            m = re.match(r'accrual_swap_(\d{8})\.json$', fn)
            if m and (latest is None or m.group(1) > latest):
                latest = m.group(1)
    return '{}-{}-{}'.format(latest[:4], latest[4:6], latest[6:8]) if latest else None


def _accrual_parse_date(s):
    try:
        return datetime.strptime(str(s)[:10], '%Y-%m-%d').strftime('%Y%m%d')
    except Exception:
        return None


def _accrual_load(date_str):
    ymd = _accrual_parse_date(date_str) or datetime.now().strftime('%Y%m%d')
    path = _accrual_path_for(ymd)
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return path, _accrual_migrate(json.load(fh))
    except Exception:
        log.error('[accrual] read failed %s:\n%s', path, traceback.format_exc())
        return None, None


def _accrual_migrate(data):
    """Bring rows saved under an older column layout up to the current fixed set,
    padding the data block (before the 4 meta cells status/maker/checker/id) so a
    newly-added column like 'Comments' lands in the right place for old files too."""
    nfix = len(_ACC_FIXED_HEADERS)
    for rows in (data.get('tables') or {}).values():
        for r in rows:
            ndata = len(r) - 4                       # cells before status/maker/checker/id
            while 0 <= ndata < nfix:
                r.insert(ndata, '')                  # append to the data block, push meta right
                ndata += 1
    data['headers'] = list(_ACC_FIXED_HEADERS)
    return data


def _accrual_save(path, data):
    data['counts'] = {k: len(v) for k, v in (data.get('tables') or {}).items()}
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _accrual_find(data, lob, rid):
    for r in (data.get('tables') or {}).get(lob, []):
        if r and str(r[-1]) == str(rid):
            return r
    return None


# ── CEM / EDG factor enrichment (translated & hardened from the Alteryx VBA) ──
#  The bank's view is LE 228. For every CETIP ID (= the accrual "Código IF") we
#  decide which factor feeds the PARTE and the CONTRAPARTE side, then fill the two
#  factor columns ONLY when that side's indexer is VCP (otherwise '-'). A contract
#  that sits in the table but has no factor for a VCP side is flagged 'Missing
#  Accrual'. CEM derives the LE from the workbook's 'Kapital CETIP' sheet
#  (Kapital → LE); EDG already ships A=CETIP / B=Fator Parte / C=Fator Contraparte.
_ACC_FACTOR_STATUS_MISSING = 'Missing Accrual'


def _acc_parse_num(s):
    """Parse a number that may be BR (1.234,56) or US (1,234.56) formatted."""
    t = str('' if s is None else s).strip().replace('%', '').replace(' ', '')
    if not t or not re.search(r'\d', t):
        return None
    neg = t.startswith('-')
    t = t.lstrip('+-')
    has_c, has_d = ',' in t, '.' in t
    if has_c and has_d:                                  # decimal = whichever comes last
        dec = ',' if t.rfind(',') > t.rfind('.') else '.'
        t = t.replace('.' if dec == ',' else ',', '').replace(dec, '.')
    elif has_c:
        t = t.replace(',', '.')
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _acc_fmt_factor(s):
    """US format, 8 decimals (rounded), ALWAYS absolute (drop any '-'). '' when the
    cell is not a number."""
    v = _acc_parse_num(s)
    return '' if v is None else '{:.8f}'.format(round(abs(v), 8))


def _acc_le_norm(s):
    """Normalise an LE/view to bare digits without leading zeros (0228 → 228)."""
    return re.sub(r'\D', '', str(s or '')).lstrip('0')


def _acc_read_sheets(filename, raw_bytes):
    """{sheet_name: rows} for .xlsx/.xlsm; one '__main__' sheet for csv/tsv."""
    name = (filename or '').lower()
    if name.endswith(('.xlsx', '.xlsm')):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
        return {sn: [list(r) for r in wb[sn].iter_rows(values_only=True)] for sn in wb.sheetnames}
    return {'__main__': _cc_read_rows(filename, raw_bytes)}


def _acc_factor_keys(code):
    """Lookup keys for a CETIP ID / Código IF: upper-cased and digits-only ('#'+d)."""
    code = str(code or '').strip()
    keys = [code.upper()]
    dg = re.sub(r'\D', '', code)
    if dg:
        keys.append('#' + dg)
    return keys


def _acc_fmap_put(fmap, cetip, parte_factor, contra_factor):
    for k in _acc_factor_keys(cetip):
        fmap.setdefault(k, (parte_factor, contra_factor))


def _acc_fmap_get(fmap, code):
    for k in _acc_factor_keys(code):
        if k in fmap:
            return fmap[k]
    return None


def _acc_parse_cem_factors(filename, raw_bytes):
    """{cetip -> (parte_factor, contra_factor)} from the CEM workbook.
    LE comes from the 'Kapital CETIP' sheet (col B Kapital → col E LE). When a CETIP
    ID carries view 228 it is the bank view → normal (Parte = col I, Contraparte =
    col J). When it only carries view 199 the factors are inverted (Parte = col J,
    Contraparte = col I). Duplicated 228/199 → keep the 228 row."""
    sheets = _acc_read_sheets(filename, raw_bytes)
    kap_rows = main_rows = None
    for sn, rws in sheets.items():
        if 'kapital' in re.sub(r'\s+', '', str(sn).lower()):
            kap_rows = rws
        elif main_rows is None:
            main_rows = rws
    if main_rows is None:
        main_rows = next(iter(sheets.values()), [])
    if kap_rows is None:
        raise ValueError("CEM file is missing the 'Kapital CETIP' sheet (Kapital → LE).")

    # Kapital ID (col B) → LE digits (col E). Both sides drop the leading zeros so
    # the lookup is robust to '00123' vs '123' mismatches between the two sheets.
    def _kap_key(v):
        return str(v or '').strip().upper().lstrip('0')

    kap_le = {}
    for r in kap_rows:
        kid = _kap_key(_cc_cell(r, 1))
        le  = _acc_le_norm(_cc_cell(r, 4))
        if kid and le:
            kap_le.setdefault(kid, le)

    # Group every data row by CETIP ID (col C), tagging its LE via the Kapital map.
    groups = {}
    for r in main_rows:
        cetip = _cc_cell(r, 2).strip()
        if not re.search(r'\d', cetip):                  # skip title/header/blank rows
            continue
        kid = _kap_key(_cc_cell(r, 1))
        groups.setdefault(cetip, []).append(
            {'le': kap_le.get(kid, ''), 'i': _cc_cell(r, 8), 'j': _cc_cell(r, 9)})

    fmap = {}
    for cetip, items in groups.items():
        v228 = next((it for it in items if it['le'] == '228'), None)
        v199 = next((it for it in items if it['le'] == '199'), None)
        if v228:                                         # bank view → normal mapping
            pf, cf = _acc_fmt_factor(v228['i']), _acc_fmt_factor(v228['j'])
        elif v199:                                       # only 199 → inverted mapping
            pf, cf = _acc_fmt_factor(v199['j']), _acc_fmt_factor(v199['i'])
        else:
            continue                                     # other view (e.g. 123) → not the bank view
        _acc_fmap_put(fmap, cetip, pf, cf)
    return fmap


def _acc_parse_direct_factors(filename, raw_bytes, cetip_col=0, parte_col=1, contra_col=2):
    """{cetip -> (parte_factor, contra_factor)} from a direct file (no LE / no
    inversion). Column indices are 0-based:
        EDG → CETIP=A(0), Fator Parte=B(1),  Fator Contraparte=C(2)
        HYB → CETIP=B(1), Fator Parte=L(11), Fator Contraparte=M(12)"""
    sheets = _acc_read_sheets(filename, raw_bytes)
    main_rows = next(iter(sheets.values()), [])
    fmap = {}
    for r in main_rows:
        cetip = _cc_cell(r, cetip_col).strip()
        if not re.search(r'\d', cetip):
            continue
        _acc_fmap_put(fmap, cetip,
                      _acc_fmt_factor(_cc_cell(r, parte_col)), _acc_fmt_factor(_cc_cell(r, contra_col)))
    return fmap


def _acc_apply_factors(data, lob, fmap):
    """Fill Fator Parte/Contraparte for the rows of one LOB table. A side keyed by a
    non-VCP indexer gets '-'; a VCP side with no factor flags the row 'Missing
    Accrual'. Row layout: [ ...11 data..., status, maker, checker, id ]."""
    rows = (data.get('tables') or {}).get(lob, [])
    matched = missing = 0
    for row in rows:
        if not row or len(row) < 15:
            continue
        parte_idx  = str(row[5] or '').strip().upper()
        contra_idx = str(row[8] or '').strip().upper()
        entry = _acc_fmap_get(fmap, row[0])
        if entry:
            matched += 1
        pf, cf = entry if entry else ('', '')
        row_missing = False
        if parte_idx == 'VCP':
            if pf:
                row[9] = pf
            else:
                row[9] = ''
                row_missing = True
        else:
            row[9] = '-'
        if contra_idx == 'VCP':
            if cf:
                row[10] = cf
            else:
                row[10] = ''
                row_missing = True
        else:
            row[10] = '-'
        if row_missing:
            row[-4] = _ACC_FACTOR_STATUS_MISSING
            missing += 1
    return matched, missing


# Factor file kind → (LOB table, parser). HYB ships its factors in cols L/M.
_ACC_FACTOR_KINDS = {
    'cem': {'lob': 'CEM',     'parser': lambda fn, raw: _acc_parse_cem_factors(fn, raw)},
    'edg': {'lob': 'EDG',     'parser': lambda fn, raw: _acc_parse_direct_factors(fn, raw)},
    'hyb': {'lob': 'Hybrids', 'parser': lambda fn, raw: _acc_parse_direct_factors(
                                            fn, raw, cetip_col=1, parte_col=11, contra_col=12)},
}


@blueprint.route('/api/accrual-swap/factors', methods=['POST'])
def api_accrual_swap_factors():
    """Enrich a saved accrual day with a CEM / EDG / HYB factor file (Fator Parte/Contraparte)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'No file uploaded.'}), 400

    kind = (request.form.get('kind') or '').strip().lower()
    if kind not in _ACC_FACTOR_KINDS:
        base = os.path.splitext(os.path.basename(f.filename))[0].lower()
        kind = ('cem' if base.startswith('cem') else 'edg' if base.startswith('edg')
                else 'hyb' if base.startswith('hyb') else '')
    if kind not in _ACC_FACTOR_KINDS:
        return jsonify({'success': False,
                        'error': 'Unrecognised factor file (expected a CEM, EDG or HYB file).'}), 400

    path, data = _accrual_load(request.form.get('date'))
    if not data or not data.get('tables'):
        return jsonify({'success': False,
                        'error': 'No accrual data for this date — process the VCP file first.'}), 400

    spec = _ACC_FACTOR_KINDS[kind]
    lob  = spec['lob']
    try:
        raw  = f.read()
        fmap = spec['parser'](f.filename, raw)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        log.error('[accrual] factor read failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the factor file.'}), 500

    matched, missing = _acc_apply_factors(data, lob, fmap)
    try:
        _accrual_save(path, data)
    except Exception:
        log.error('[accrual] factor save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to save the enriched data.'}), 500

    log.info('[accrual] %s factors: %d mapped, %d matched, %d missing', lob, len(fmap), matched, missing)
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Mapped', 'Accrual',
                         '{} · {} matched, {} missing'.format(lob, matched, missing) + _nd_token(data.get('date')))
    return jsonify({
        'success': True,
        'headers': data.get('headers') or list(_ACC_FIXED_HEADERS),
        'tables':  data.get('tables') or {},
        'counts':  data.get('counts') or {},
        'ref_date': data.get('ref_date'),
        'date': data.get('date'),
        'factors': {'lob': lob, 'matched': matched, 'missing': missing, 'mapped': len(fmap)},
    })


def _accrual_source_dir(ymd):
    """ACCRUAL_SOURCE_ROOT\\YYYY\\mm. Month\\DD for a 'YYYYMMDD' run date."""
    ref = datetime.strptime(ymd, '%Y%m%d')
    month_folder = ref.strftime('%m') + '. ' + _EN_MONTH_NAMES[ref.month - 1]
    return os.path.join(ACCRUAL_SOURCE_ROOT, ref.strftime('%Y'), month_folder, ref.strftime('%d'))


def _accrual_is_vcp_name(n):
    nl = n.lower()
    return ('vcp' in nl) or ('instrumentofin' in nl) or ('intrumentofin' in nl)


@blueprint.route('/api/accrual-swap/import-folder', methods=['POST'])
def api_accrual_import_folder():
    """Run the whole pipeline by reading the run folder directly (no dropzone): pick
    the VCP file → split into the four books, then apply any CEM/EDG/HYB factor file
    found alongside it. Persists under the selected date."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p   = request.get_json(silent=True) or {}
    ymd = _accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    folder = _accrual_source_dir(ymd)
    if not os.path.isdir(folder):
        return jsonify({'success': False, 'error': 'Folder not found: {}'.format(folder)}), 400

    files = [fn for fn in os.listdir(folder) if os.path.isfile(os.path.join(folder, fn))]
    vcp = next((fn for fn in files if _accrual_is_vcp_name(fn)), None)
    if not vcp:
        return jsonify({'success': False,
                        'error': 'No VCP file found in {}'.format(folder)}), 400

    try:
        with open(os.path.join(folder, vcp), 'rb') as fh:
            rows = _cc_read_rows(vcp, fh.read())
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        log.error('[accrual] folder VCP read failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the VCP file.'}), 500
    if len(rows) < _ACC_HEADER_ROW:
        return jsonify({'success': False,
                        'error': 'VCP file has fewer than {} rows.'.format(_ACC_HEADER_ROW)}), 400

    result = _accrual_build_result(rows)
    path, data = _accrual_persist(result, vcp, ymd=ymd)

    # Apply each factor file present in the folder (CEM / EDG / HYB), in turn.
    applied = []
    for kind, spec in _ACC_FACTOR_KINDS.items():
        fn = next((x for x in files
                   if os.path.splitext(x)[0].lower().startswith(kind)), None)
        if not fn:
            continue
        try:
            with open(os.path.join(folder, fn), 'rb') as fh:
                fmap = spec['parser'](fn, fh.read())
            m, miss = _acc_apply_factors(data, spec['lob'], fmap)
            applied.append({'kind': kind, 'lob': spec['lob'], 'file': fn,
                            'matched': m, 'missing': miss, 'mapped': len(fmap)})
        except Exception:
            log.error('[accrual] folder factor (%s) failed:\n%s', kind, traceback.format_exc())
            applied.append({'kind': kind, 'lob': spec['lob'], 'file': fn, 'error': True})

    try:
        _accrual_save(path, data)
    except Exception:
        log.error('[accrual] folder save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to save the imported data.'}), 500

    log.info('[accrual] folder import %s: VCP=%s, factors=%s', folder, vcp,
             ', '.join('{}:{}'.format(a['kind'], a.get('matched', 'err')) for a in applied))
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Imported', 'Accrual',
                         'Folder · {} classified · {} factor file(s)'.format(
                             result.get('diagnostics', {}).get('matched', 0), len(applied)) + _nd_token(ymd))
    return jsonify({
        'success': True,
        'headers': data.get('headers') or list(_ACC_FIXED_HEADERS),
        'tables':  data.get('tables') or {},
        'counts':  data.get('counts') or {},
        'ref_date': data.get('ref_date'),
        'date': data.get('date'),
        'diagnostics': result.get('diagnostics', {}),
        'folder': folder, 'vcp_file': vcp, 'applied': applied,
    })


@blueprint.route('/api/accrual-swap/data')
def api_accrual_data():
    """Return the saved accrual JSON for a given date (?date=YYYY-MM-DD, default today)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    _, data = _accrual_load(request.args.get('date'))
    if not data:
        return jsonify({'success': True, 'empty': True})
    data['success'] = True
    return jsonify(data)


@blueprint.route('/api/accrual-swap/latest')
def api_accrual_latest():
    """Most recent saved accrual date (YYYY-MM-DD) so the page can land on real
    data by default — e.g. when opened from a bell notification."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True, 'date': _accrual_latest_ymd()})


@blueprint.route('/api/accrual-swap/row/delete', methods=['POST'])
def api_accrual_row_delete():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob, rid = p.get('lob'), str(p.get('id', ''))
    path, data = _accrual_load(p.get('date'))
    if not data or lob not in (data.get('tables') or {}):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    data['tables'][lob] = [r for r in data['tables'][lob] if not (r and str(r[-1]) == rid)]
    try:
        _accrual_save(path, data)
    except Exception:
        log.error('[accrual] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Deleted', 'Accrual', '{} · 1 row'.format(lob) + _nd_token(data.get('date')))
    return jsonify({'success': True, 'counts': data['counts']})


@blueprint.route('/api/accrual-swap/rows/delete', methods=['POST'])
def api_accrual_rows_delete():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob = p.get('lob')
    ids = set(str(x) for x in (p.get('ids') or []))
    path, data = _accrual_load(p.get('date'))
    if not data or lob not in (data.get('tables') or {}):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    data['tables'][lob] = [r for r in data['tables'][lob] if not (r and str(r[-1]) in ids)]
    try:
        _accrual_save(path, data)
    except Exception:
        log.error('[accrual] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Deleted', 'Accrual', '{} · {} rows'.format(lob, len(ids)) + _nd_token(data.get('date')))
    return jsonify({'success': True, 'counts': data['counts']})


@blueprint.route('/api/accrual-swap/row/edit', methods=['POST'])
def api_accrual_row_edit():
    """Edit a row's data cells → status Pending, maker = current user (checker reset)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob, rid = p.get('lob'), str(p.get('id', ''))
    cells = p.get('cells') or []
    sid = session.get('user_sid', '')
    path, data = _accrual_load(p.get('date'))
    if not data or lob not in (data.get('tables') or {}):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    target = _accrual_find(data, lob, rid)
    if target is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    ndata = len(target) - 4                         # cells before status/maker/checker/id
    for i in range(min(len(cells), ndata)):
        target[i] = cells[i]
    target[-4], target[-3], target[-2] = 'Pending', sid, ''   # status, maker, checker
    try:
        _accrual_save(path, data)
    except Exception:
        log.error('[accrual] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _create_notification(sid, session.get('user_name', ''),
                         'Accrual Updated', 'Accrual', '{} · {}'.format(lob, rid) + _nd_token(data.get('date')))
    return jsonify({'success': True, 'row': target})


@blueprint.route('/api/accrual-swap/row/send', methods=['POST'])
def api_accrual_row_send():
    """Send/approve a row — maker/checker guard: the user who changed it cannot send it."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob, rid = p.get('lob'), str(p.get('id', ''))
    sid = session.get('user_sid', '')
    path, data = _accrual_load(p.get('date'))
    if not data or lob not in (data.get('tables') or {}):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    target = _accrual_find(data, lob, rid)
    if target is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    maker = str(target[-3] or '')
    if maker and maker == sid:
        return jsonify({'success': False, 'error': 'same_user',
                        'message': 'A different user must send a row you changed.'}), 403
    target[-4], target[-2] = 'Sent', sid            # status, checker
    try:
        _accrual_save(path, data)
    except Exception:
        log.error('[accrual] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _create_notification(sid, session.get('user_name', ''),
                         'Accrual Sent', 'Accrual', '{} · {}'.format(lob, rid) + _nd_token(data.get('date')))
    return jsonify({'success': True, 'row': target})


# ── CETIP SWAP "Atualização de PU/Fator" — batch file generation ─────────────
#  One accrual row → 1/2/4 fixed-width records (per updater × VCP leg). Larger
#  account = role/curve "01", smaller = "00". Updaters = our own group participants
#  (prefixes below); an external bank counterparty is not an updater (bank view only).
#  Records are split by VIEW into ACCRUAL_<VIEW>-<LOB>.txt in the Batch Conecta folder.
_ACC_VIEW_BY_PREFIX = {'73760': 'BANCO', '04880': 'BANCO', '85398': 'ATACAMA', '00041': 'LAWTON'}
_ACC_VIEW_PART_NAME = {'BANCO': 'JPMORGANBM', 'LAWTON': 'INTRAGLAWTONFDO', 'ATACAMA': 'INTRAGATACAMAFDO'}
_ACC_LOB_TAG = {'CEM': 'CEM', 'EDG': 'EDG', 'Hybrids': 'HYB', 'Commodities': 'COMM'}


def _acc_swap_fator(f):
    """Factor → 2 integer + 8 decimal digits, no separator, absolute. 1.0 → '0100000000'."""
    try:
        n = abs(float(str(f or '').replace(',', '.')))
    except (ValueError, TypeError):
        n = 0.0
    ip, fp = '{:.8f}'.format(n).split('.')
    return ip[-2:].rjust(2, '0') + fp


def _acc_swap_header(view, today):
    return 'SWAP 00015' + _ACC_VIEW_PART_NAME.get(view, view).ljust(20) + today


def _acc_swap_records(row, today):
    """Return a list of {view, line} for one accrual row (empty when no VCP leg)."""
    codigo = str(row[0] or '').strip()
    accP, idxP = row[3], str(row[5] or '').strip().upper()
    accC, idxC = row[6], str(row[8] or '').strip().upper()
    fatP, fatC = row[9], row[10]
    digP = re.sub(r'\D', '', str(accP or '')); digC = re.sub(r'\D', '', str(accC or ''))
    numP = int(digP or '0'); numC = int(digC or '0')
    roleP = '01' if numP > numC else '00'
    roleC = '01' if numC > numP else '00'
    legs = []                                       # (curva, fator) per VCP leg
    if idxP == 'VCP': legs.append((roleP, fatP))
    if idxC == 'VCP': legs.append((roleC, fatC))
    if not legs:
        return []
    prefP, prefC = digP[:5], digC[:5]
    updaters = [(roleP, prefP)]                      # PARTE (our house entity) always updates
    if prefC in _ACC_VIEW_BY_PREFIX and prefC != prefP:
        updaters.append((roleC, prefC))             # group counterparty also submits its view
    out = []
    for papel, pref in updaters:
        view = _ACC_VIEW_BY_PREFIX.get(pref)
        if not view:
            continue
        for curva, fat in legs:
            meu = ''.join(random.choice('0123456789') for _ in range(10))
            line = ('SWAP ' + '1' + '0015' + codigo + papel + '00' + curva +
                    today + meu + (' ' * 22) + _acc_swap_fator(fat))
            out.append({'view': view, 'line': line})
    return out


def _acc_write_batch_files(data, lob, today, evidence_dir=None):
    """Generate + write ACCRUAL_<view>-<lob>.txt for one LOB book, split by view.
    Written to the Batch Conecta folder AND (best-effort) to the evidence folder
    (Regulatory\\Accrual\\YYYY\\mm. Month\\DD). Returns [{filename, path, view, count}]."""
    by_view = {}
    for r in ((data.get('tables') or {}).get(lob) or []):
        if not r or len(r) < 15:
            continue
        if str(r[-4] or '') == _ACC_FACTOR_STATUS_MISSING:    # skip rows without a factor
            continue
        for rec in _acc_swap_records(r, today):
            by_view.setdefault(rec['view'], []).append(rec['line'])
    if not by_view:
        return []
    lob_tag = _ACC_LOB_TAG.get(lob, str(lob).upper())
    os.makedirs(CONECTA_NEW_PATH, exist_ok=True)
    if evidence_dir:
        try:
            os.makedirs(evidence_dir, exist_ok=True)
        except Exception:
            log.warning('[accrual] could not create evidence dir %s:\n%s', evidence_dir, traceback.format_exc())
    generated = []
    for view in ('BANCO', 'LAWTON', 'ATACAMA'):
        lines = by_view.get(view)
        if not lines:
            continue
        content = '\n'.join([_acc_swap_header(view, today)] + lines)
        fpath = _unique_filepath(CONECTA_NEW_PATH, 'ACCRUAL_{}-{}.txt'.format(view, lob_tag))
        with open(fpath, 'w', encoding='utf-8') as fh:
            fh.write(content)
        # Evidence copy (same base name), best-effort — never blocks the Conecta write.
        if evidence_dir and os.path.isdir(evidence_dir):
            try:
                with open(os.path.join(evidence_dir, os.path.basename(fpath)), 'w', encoding='utf-8') as fh:
                    fh.write(content)
            except Exception:
                log.warning('[accrual] evidence copy failed for %s:\n%s', fpath, traceback.format_exc())
        generated.append({'filename': os.path.basename(fpath), 'path': fpath, 'view': view, 'count': len(lines)})
    return generated


def _acc_missing_accrual_rows(data, lobs):
    """Rows flagged 'Missing Accrual' (no updated factor) across the given LOB books.
    Their presence blocks file generation. Returns [{id, lob, codigo}]."""
    out = []
    for lob in lobs:
        for r in ((data.get('tables') or {}).get(lob) or []):
            if r and len(r) >= 15 and str(r[-4] or '') == _ACC_FACTOR_STATUS_MISSING:
                out.append({'id': str(r[-1]), 'lob': lob, 'codigo': str(r[0] or '')})
    return out


def _send_accrual_validation_email(subject, html, logo_path, attach_paths):
    """SMTP-only e-mail of the EOM accrual validation to OTC Ops, attaching the
    Lawton/Atacama files. The HTML and logo path are resolved by the caller (so this
    can run in a background thread without a Flask app context). Best-effort."""
    from email.mime.image import MIMEImage
    from email.mime.base import MIMEBase
    from email import encoders
    try:
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = SHARED_MAILBOX
        msg['To'] = CETIP_OTC_OPS_EMAIL

        related = MIMEMultipart('related')
        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText('Accrual EOM validation files attached.', 'plain', 'utf-8'))
        alt.attach(MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)
        if logo_path:
            with open(logo_path, 'rb') as f:
                img = MIMEImage(f.read())
            img.add_header('Content-ID', '<otc_logo>')
            img.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(img)
        msg.attach(related)

        for path in attach_paths:
            try:
                with open(path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(path))
                msg.attach(part)
            except Exception:
                log.warning('[accrual] could not attach %s:\n%s', path, traceback.format_exc())

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.sendmail(SHARED_MAILBOX, [CETIP_OTC_OPS_EMAIL], msg.as_string())
        log.info('[accrual] validation e-mail sent to %s', CETIP_OTC_OPS_EMAIL)
        return True
    except Exception as e:
        log.error('[accrual] validation e-mail FAILED:\n%s', traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)


@blueprint.route('/api/accrual-swap/send-batch', methods=['POST'])
def api_accrual_send_batch():
    """Generate the CETIP PU/Factor batch files for one LOB book, split by view
    (BANCO / LAWTON / ATACAMA) into the Batch Conecta folder."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob = p.get('lob')
    path, data = _accrual_load(p.get('date'))
    if not data or lob not in (data.get('tables') or {}):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    missing = _acc_missing_accrual_rows(data, [lob])          # block when any factor is missing
    if missing:
        return jsonify({'success': False, 'error': 'missing_accrual', 'missing': missing}), 400
    ymd = _accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    try:
        generated = _acc_write_batch_files(data, lob, datetime.now().strftime('%Y%m%d'),
                                           evidence_dir=_accrual_source_dir(ymd))
    except Exception:
        log.error('[accrual] send-batch failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to write the batch files.'}), 500
    if not generated:
        return jsonify({'success': False, 'error': 'No VCP records to send for this book.'}), 400
    total = sum(g['count'] for g in generated)
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Sent', 'Accrual',
                         '{} · {} file(s), {} line(s)'.format(lob, len(generated), total) + _nd_token(ymd))
    files = [{'filename': g['filename'], 'view': g['view'], 'count': g['count']} for g in generated]
    return jsonify({'success': True, 'files': files, 'total': total, 'lob': lob})


@blueprint.route('/api/accrual-swap/validation', methods=['POST'])
def api_accrual_validation():
    """EOM Validation: generate the batch files for ALL LOB books, then e-mail the
    Lawton/Atacama view files to Brazil OTC Ops for validation."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    path, data = _accrual_load(p.get('date'))
    if not data or not (data.get('tables')):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404

    missing = _acc_missing_accrual_rows(data, ['CEM', 'EDG', 'Hybrids', 'Commodities'])   # block across all books
    if missing:
        return jsonify({'success': False, 'error': 'missing_accrual', 'missing': missing}), 400

    ymd = _accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    ref = datetime.strptime(ymd, '%Y%m%d')
    today = datetime.now().strftime('%Y%m%d')
    evidence_dir = _accrual_source_dir(ymd)

    generated = []
    try:
        for lob in ('CEM', 'EDG', 'Hybrids', 'Commodities'):
            if lob in (data.get('tables') or {}):
                generated.extend(_acc_write_batch_files(data, lob, today, evidence_dir=evidence_dir))
    except Exception:
        log.error('[accrual] validation generate failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to write the batch files.'}), 500
    if not generated:
        return jsonify({'success': False, 'error': 'No VCP records to validate.'}), 400

    # Attach ONLY the Lawton / Atacama view files.
    attach = [g['path'] for g in generated if g['view'] in ('LAWTON', 'ATACAMA')]
    subject = 'Accrual EOM - {} - Validation'.format(ref.strftime('%d/%m/%Y'))
    summary = [{'filename': g['filename'], 'view': g['view'], 'count': g['count']} for g in generated]

    # Render the HTML + resolve the logo HERE (needs the Flask app context), then send
    # the e-mail in a background thread so a slow/unreachable SMTP host never blocks
    # (or times out) the HTTP response — the files are already written either way.
    try:
        html = render_template(
            'pages/email-template-accrual-validation.html',
            ref_date_fmt=ref.strftime('%d/%m/%Y'), generated_files=summary,
            attachment_names=[os.path.basename(a) for a in attach],
            current_year=datetime.now().year)
        logo_path = _get_logo_path()
        threading.Thread(
            target=_send_accrual_validation_email,
            args=(subject, html, logo_path, attach), daemon=True).start()
    except Exception:
        log.error('[accrual] validation e-mail prep failed:\n%s', traceback.format_exc())

    total = sum(g['count'] for g in generated)
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Sent', 'Accrual',
                         'EOM Validation · {} file(s), {} attached'.format(len(generated), len(attach)) + _nd_token(ymd))
    return jsonify({
        'success': True,
        'files': summary,
        'attached': [os.path.basename(a) for a in attach],
        'total': total, 'mail': 'queued',
    })


# ── Recon: match the 'operacoes' return file against the saved accrual factors ──
#  operacoes layout: headers on row 5, data from row 6. Filter col B (index 1) to the
#  two house accounts AND col E == 'REGISTRO DE PU/FATOR'. col H (index 7) = título
#  (= Código IF), col P (index 15) = registered factor (BR decimal comma).
#  Simple match: gather all registered factors per Código IF; a VCP leg's factor
#  (Fator Parte / Fator Contraparte) is OK when it appears among them — else Check.
_ACC_RECON_ACCOUNTS = {'04880006', '73760009'}
_ACC_RECON_MARKER = 'REGISTRO DE PU/FATOR'
_ACC_RECON_HEADER_ROW = 5                  # 1-based → data starts at index 5


def _acc_run_recon(data, rows):
    """Gather registered factors per Código IF from the operacoes rows, then flag each
    VCP leg OK/Check by simple factor membership. Mutates data (recon + status)."""
    by_cif = {}                                           # cif_key -> [rounded floats]
    for i in range(_ACC_RECON_HEADER_ROW, len(rows)):     # data from row 6 (index 5)
        row = rows[i]
        if _acc_digits(_cc_cell(row, 1)) not in _ACC_RECON_ACCOUNTS:       # col B house account
            continue
        if _cc_cell(row, 4).strip().upper() != _ACC_RECON_MARKER:          # col E marker
            continue
        cif = _cc_cell(row, 7).strip()                                     # col H título
        fac = _acc_parse_num(_cc_cell(row, 15))                            # col P factor (comma→dot)
        if not cif or fac is None:
            continue
        for k in _acc_factor_keys(cif):
            by_cif.setdefault(k, []).append(round(fac, 8))

    def _regs(cif):
        for k in _acc_factor_keys(cif):
            if k in by_cif:
                return by_cif[k]
        return []

    recon_out, ok_rows, check_rows = {}, 0, 0
    for table in (data.get('tables') or {}).values():
        for r in table:
            if not r or len(r) < 15:
                continue
            idxP = str(r[5] or '').strip().upper()
            idxC = str(r[8] or '').strip().upper()
            legs = []                                       # (tag, accrual_factor); p=Parte, c=Contra
            if idxP == 'VCP': legs.append(('p', r[9]))
            if idxC == 'VCP': legs.append(('c', r[10]))
            if not legs:
                continue
            regs = _regs(str(r[0] or '').strip())
            regset = set(regs)
            regdisp = ', '.join('{:.8f}'.format(x) for x in regs)
            entry, all_ok = {}, True
            for tag, acc_fac in legs:
                accv = _acc_parse_num(acc_fac)
                ok = (accv is not None and round(accv, 8) in regset)
                if not ok:
                    all_ok = False
                entry[tag] = {'ok': ok, 'reg': regdisp}
            recon_out[str(r[-1])] = entry
            r[-4] = 'Success' if all_ok else 'Check'        # status
            if all_ok: ok_rows += 1
            else:      check_rows += 1
    data['recon'] = recon_out
    return {'success_rows': ok_rows, 'check_rows': check_rows, 'map_entries': len(by_cif)}


def _acc_find_operacoes(folder):
    if not os.path.isdir(folder):
        return None
    for fn in os.listdir(folder):
        if not os.path.isfile(os.path.join(folder, fn)):
            continue
        base = os.path.splitext(fn)[0].lower()
        base = (base.replace('ç', 'c').replace('õ', 'o').replace('ã', 'a')
                    .replace('é', 'e').replace('ô', 'o'))
        if base.startswith('operac'):
            return os.path.join(folder, fn)
    return None


@blueprint.route('/api/accrual-swap/recon', methods=['POST'])
def api_accrual_recon():
    """Reconcile the saved accrual factors against the operacoes return file (uploaded
    via the dropzone, or read from the run folder when from_folder=1)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    date_arg = request.form.get('date')
    path, data = _accrual_load(date_arg)
    if not data or not data.get('tables'):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404

    try:
        if f and f.filename:
            rows = _cc_read_rows(f.filename, f.read())
        else:
            ymd = _accrual_parse_date(date_arg) or datetime.now().strftime('%Y%m%d')
            folder = _accrual_source_dir(ymd)
            op = _acc_find_operacoes(folder)
            if not op:
                return jsonify({'success': False,
                                'error': 'operacoes file not found in {}'.format(folder)}), 400
            with open(op, 'rb') as fh:
                rows = _cc_read_rows(os.path.basename(op), fh.read())
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        log.error('[accrual] recon read failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the operacoes file.'}), 500

    summary = _acc_run_recon(data, rows)
    try:
        _accrual_save(path, data)
    except Exception:
        log.error('[accrual] recon save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to save the recon result.'}), 500

    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Mapped', 'Accrual',
                         'Recon · {} ok, {} check'.format(summary['success_rows'], summary['check_rows']) + _nd_token(ymd))
    return jsonify({
        'success': True,
        'headers': data.get('headers') or list(_ACC_FIXED_HEADERS),
        'tables': data.get('tables') or {},
        'counts': data.get('counts') or {},
        'recon': data.get('recon') or {},
        'ref_date': data.get('ref_date'), 'date': data.get('date'),
        'summary': summary,
    })


@blueprint.route('/api/accrual-swap/row/comment', methods=['POST'])
def api_accrual_row_comment():
    """Update only the Comments cell (no status change) — used by the inline comment
    field that the recon enables on Check rows."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob, rid = p.get('lob'), str(p.get('id', ''))
    path, data = _accrual_load(p.get('date'))
    if not data or lob not in (data.get('tables') or {}):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    target = _accrual_find(data, lob, rid)
    if target is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    target[-5] = str(p.get('comment', ''))                # Comments = last data cell
    try:
        _accrual_save(path, data)
    except Exception:
        log.error('[accrual] comment save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    return jsonify({'success': True})


# ── End Process: final EOM status e-mail to OTC Ops (cc Middle Office) ────────
_ACC_ENDPROC_CC = ['renato.montoza@jpmorgan.com', 'danilo.camposfonseca@jpmchase.com']


def _acc_check_status_rows(data):
    """Return (all_check_rows, uncommented) — rows whose status is 'Check'."""
    checks, pending = [], []
    for lob, table in (data.get('tables') or {}).items():
        for r in table:
            if not r or len(r) < 15:
                continue
            if str(r[-4] or '').strip().lower() == 'check':
                comment = str(r[-5] or '').strip()
                item = {'id': str(r[-1]), 'lob': lob, 'codigo': str(r[0] or ''), 'comment': comment}
                checks.append(item)
                if not comment:
                    pending.append(item)
    return checks, pending


def _send_accrual_endprocess_email(subject, html, logo_path):
    """SMTP-only final-status e-mail to OTC Ops, cc the Middle Office. Best-effort."""
    from email.mime.image import MIMEImage
    try:
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = SHARED_MAILBOX
        msg['To'] = CETIP_OTC_OPS_EMAIL
        msg['Cc'] = ', '.join(_ACC_ENDPROC_CC)
        related = MIMEMultipart('related')
        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText('Accrual Swap EOM final status.', 'plain', 'utf-8'))
        alt.attach(MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)
        if logo_path:
            with open(logo_path, 'rb') as f:
                img = MIMEImage(f.read())
            img.add_header('Content-ID', '<otc_logo>')
            img.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(img)
        msg.attach(related)
        recipients = [CETIP_OTC_OPS_EMAIL] + _ACC_ENDPROC_CC
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.sendmail(SHARED_MAILBOX, recipients, msg.as_string())
        log.info('[accrual] end-process e-mail sent to %s (cc %s)', CETIP_OTC_OPS_EMAIL, _ACC_ENDPROC_CC)
        return True
    except Exception:
        log.error('[accrual] end-process e-mail FAILED:\n%s', traceback.format_exc())
        return False


@blueprint.route('/api/accrual-swap/end-process', methods=['POST'])
def api_accrual_end_process():
    """Finish the EOM Accrual Swap process: every 'Check' row must be commented; then
    e-mail the final status to OTC Ops (cc Middle Office)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    path, data = _accrual_load(p.get('date'))
    if not data or not data.get('tables'):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404

    checks, pending = _acc_check_status_rows(data)
    if pending:
        return jsonify({'success': False, 'error': 'uncommented', 'pending': pending}), 400

    ymd = _accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    ref = datetime.strptime(ymd, '%Y%m%d')
    subject = 'Accrual Swap - EOM - Final Status - {}'.format(ref.strftime('%d/%m/%Y'))
    try:
        html = render_template(
            'pages/email-template-accrual-endprocess.html',
            ref_date_fmt=ref.strftime('%d/%m/%Y'), has_check=bool(checks), checks=checks,
            folder=_accrual_source_dir(ymd), current_year=datetime.now().year)
        logo_path = _get_logo_path()
        threading.Thread(target=_send_accrual_endprocess_email,
                         args=(subject, html, logo_path), daemon=True).start()
    except Exception:
        log.error('[accrual] end-process e-mail prep failed:\n%s', traceback.format_exc())

    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Sent', 'Accrual',
                         'End Process · {} check row(s)'.format(len(checks)) + _nd_token(ymd))
    return jsonify({'success': True, 'checks': len(checks)})


@blueprint.route('/holidays-calendar')
def holidays_calendar():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/holidays-calendar.html', segment='holidays-calendar')


@blueprint.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('pages_blueprint.sign_in_page'))


@blueprint.route('/users-roles')
def users_roles():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    users = get_all_users()
    role_groups = get_role_groups()
    role_display = {k: v['display'] for k, v in ROLE_META.items()}
    return render_template('pages/users-roles.html', segment='users-roles',
                           users=users, role_groups=role_groups, role_display=role_display)


@blueprint.route('/api/users/update', methods=['POST'])
def api_update_user():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data = request.get_json()
    sid = data.get('sid', '').strip().upper()
    new_role = data.get('role', '').strip()
    new_status = data.get('status', '').strip()
    new_position = data.get('position', '').strip()

    valid_roles = {'', 'ADMIN', 'BO', 'FO', 'MO', 'INSTITUTIONAL', 'HUB'}
    valid_statuses = {'Active', 'Inactive', 'Pending'}
    valid_positions = {'', 'Consultant', 'Intern', 'Analyst', 'Associate', 'Senior Associate', 'VP', 'ED', 'MD'}

    if not sid:
        return jsonify({"success": False, "message": "SID is required."}), 400
    if new_role not in valid_roles:
        return jsonify({"success": False, "message": "Invalid role."}), 400
    if new_status not in valid_statuses:
        return jsonify({"success": False, "message": "Invalid status."}), 400
    if new_position not in valid_positions:
        return jsonify({"success": False, "message": "Invalid position."}), 400

    user = get_user_by_sid(sid)
    if not user:
        return jsonify({"success": False, "message": "User not found."}), 404

    prev_status = user.get("Status", "Pending")
    update_user_role_status(sid, new_role, new_status, new_position)

    # Send activation email when Pending -> Active
    if prev_status == 'Pending' and new_status == 'Active':
        first_name = user["Name"].split()[0] if user["Name"] else sid
        send_account_activated_email(user["Email"], first_name)

    _create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'User Updated', 'Users',
        sid + ' — Role: ' + new_role + ' | Status: ' + new_status
    )
    return jsonify({"success": True, "message": "User updated successfully."})


@blueprint.route('/api/users/delete', methods=['POST'])
def api_delete_user():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    if session.get('user_role') != 'ADMIN':
        return jsonify({"success": False, "message": "Only Admin users can delete accounts."}), 403

    data = request.get_json()
    sid = data.get('sid', '').strip().upper()

    if not sid:
        return jsonify({"success": False, "message": "SID is required."}), 400

    if sid == session.get('user_sid', '').upper():
        return jsonify({"success": False, "message": "You cannot delete your own account."}), 400

    if not get_user_by_sid(sid):
        return jsonify({"success": False, "message": "User not found."}), 404

    deleted_name = get_user_by_sid(sid).get('Name', sid)
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM verification_codes WHERE SID = ?", [sid])
        conn.execute("DELETE FROM users WHERE SID = ?", [sid])
        conn.commit()
    finally:
        conn.close()

    _create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'User Deleted', 'Users', deleted_name + ' (' + sid + ')'
    )
    return jsonify({"success": True, "message": "User deleted successfully."})


@blueprint.route('/user-info')
def user_info():
    if not session.get('authenticated'):
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({
        "sid": session.get('user_sid'),
        "name": session.get('user_name'),
        "email": session.get('user_email'),
        "role": session.get('user_role'),
        "client_ip": get_client_ip()
    })


# ==============================================================================
# ROTAS — CACHE DE DEALS (New Deals › Options › Commodities)
# ==============================================================================

def _find_deal_in_cache(deal_name, client_name=None):
    """Search all YYYYMMDD_optcomm.json files for a deal by Deal + Client.
    Returns (file_path, list_index) or (None, None)."""
    files_scanned     = 0
    deal_name_matches = []   # Deal matched but Client didn't

    for root, _dirs, files in os.walk(CACHE_BASE_DIR):
        for fname in sorted(files, reverse=True):   # newest files first
            if not fname.endswith('_optcomm.json'):
                continue
            fpath = os.path.join(root, fname)
            files_scanned += 1
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
                for i, deal in enumerate(deals):
                    d_name   = (deal.get('Deal')   or '').strip()
                    d_client = (deal.get('Client') or '').strip()
                    if d_name == deal_name.strip():
                        want = (client_name or '').strip()
                        if not want or d_client == want:
                            log.debug("[_find_opt] FOUND %r client=%r → %s[%d]",
                                      deal_name, client_name, fname, i)
                            return fpath, i
                        else:
                            deal_name_matches.append({
                                'file': fname, 'idx': i,
                                'stored_client': repr(d_client),
                                'wanted_client': repr(want)
                            })
            except Exception:
                log.warning("[_find_opt] Error reading %s: %s", fpath, traceback.format_exc())
                continue

    if deal_name_matches:
        log.warning(
            "[_find_opt] CLIENT MISMATCH for deal=%r  wanted_client=%r\n"
            "  Matches by name (stored vs wanted): %s",
            deal_name, repr(client_name), deal_name_matches
        )
    elif files_scanned == 0:
        log.error("[_find_opt] No _optcomm.json files found in %s", CACHE_BASE_DIR)
    else:
        log.warning("[_find_opt] deal=%r client=%r NOT FOUND in %d file(s)",
                    deal_name, client_name, files_scanned)
    return None, None


@blueprint.route('/api/new-deals/opt-commodities/cache', methods=['POST'])
def api_save_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    # Use the deal's TradeDate (dd/mm/yyyy) for the directory; fall back to today
    trade_date_raw = data.get('TradeDate', '')
    try:
        ref_date = datetime.strptime(trade_date_raw, '%d/%m/%Y')
    except (ValueError, TypeError):
        ref_date = datetime.now()

    dir_path = os.path.join(
        CACHE_BASE_DIR,
        ref_date.strftime('%Y'),
        ref_date.strftime('%m')
    )
    os.makedirs(dir_path, exist_ok=True)

    fname = ref_date.strftime('%Y%m%d') + '_optcomm.json'
    file_path = os.path.join(dir_path, fname)

    with _cache_lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
            except (json.JSONDecodeError, ValueError):
                deals = []
        else:
            deals = []

        deal_name   = data.get('Deal', '').strip()
        client_name = data.get('Client', '').strip()
        data.pop('_client', None)
        existing_idx = next((i for i, d in enumerate(deals)
                             if deal_name
                             and d.get('Deal', '').strip() == deal_name
                             and d.get('Client', '').strip() == client_name), None)
        if existing_idx is not None:
            deals[existing_idx] = data
        else:
            deals.append(data)
        target_idx = existing_idx if existing_idx is not None else len(deals) - 1
        for _k in ('Maker', 'Checker'):
            if _k in deals[target_idx]:
                deals[target_idx][_k] = deals[target_idx].pop(_k)
        _atomic_write_json(file_path, deals)

    return jsonify({"success": True, "deal": data.get('Deal', '')})


def _parse_date_any(val):
    """Parse a date string in any supported format → datetime.date, or None.

    Handles the smart-filter input (dd/mm/yyyy) and the formats stored in the
    JSON cache (yyyy-mm-dd, yyyy-mm-dd HH:MM:SS, yyyymmdd, dd-mm-yyyy).
    """
    val = str(val or '').strip()
    if not val:
        return None
    val = val.split('T')[0].split(' ')[0]  # drop any time component
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%Y%m%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def _deal_matches(deal, filters):
    """Return True when a deal dict satisfies every filter.

    Date filters support a `mode` of 'from' (cell >= value), 'to'
    (cell <= value) or 'exact'/absent (equality, both bounds inclusive when a
    'from'+'to' pair is supplied for the same field).
    """
    for f in filters:
        field = f.get('field', '')
        ftype = f.get('type', 'text')
        value = str(f.get('value', '')).strip()
        if not field or not value:
            continue
        cell_val = str(deal.get(field, '')).strip()
        if ftype == 'text':
            if value.lower() not in cell_val.lower():
                return False
        elif ftype == 'date':
            mode = (f.get('mode') or 'exact').lower()
            fval = _parse_date_any(value)
            cval = _parse_date_any(cell_val)
            if mode in ('from', 'to'):
                # Range bound — both the filter value and the cell must parse
                if fval is None or cval is None:
                    return False
                if mode == 'from' and cval < fval:
                    return False
                if mode == 'to' and cval > fval:
                    return False
            else:
                # Exact: compare as dates when both parse, else fall back to
                # substring so partial inputs (e.g. "06/2026") still work
                if fval is not None and cval is not None:
                    if cval != fval:
                        return False
                elif value not in cell_val:
                    return False
        elif ftype == 'number':
            if value.replace(',', '') not in cell_val.replace(',', ''):
                return False
    return True


@blueprint.route('/api/new-deals/opt-commodities/cache/search', methods=['POST'])
def api_search_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    body = request.get_json(silent=True) or {}
    filters = body.get('filters', [])

    matched = []
    for root, _dirs, files in os.walk(CACHE_BASE_DIR):
        for fname in sorted(files):
            if not fname.endswith('_optcomm.json'):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
                for deal in deals:
                    if _deal_matches(deal, filters):
                        matched.append(deal)
            except Exception:
                continue

    return jsonify({"success": True, "deals": matched})


@blueprint.route('/api/new-deals/opt-commodities/cache/<deal_id>', methods=['PATCH'])
def api_update_deal_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    client  = request.args.get('client')
    updates = request.get_json(silent=True)
    if not updates:
        return jsonify({"success": False, "message": "No data provided"}), 400

    file_path, _ = _find_deal_in_cache(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        updates.pop('_client', None)
        deals[idx].update(updates)
        for _k in ('Maker', 'Checker'):
            if _k in deals[idx]:
                deals[idx][_k] = deals[idx].pop(_k)
        _atomic_write_json(file_path, deals)
        updated_deal = deals[idx].copy()

    # Mirror NDF: push to Intrag Option when Status→Success and the counterparty
    # is Banco J.P. Morgan (intragroup).
    if str(updates.get('Status', '')) == 'Success':
        _maybe_save_intrag_opt(updated_deal)

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            # The 'Sent' transition is already announced by the 'Sent to B3'
            # notification emitted from send-conecta — skip the redundant
            # 'Status Updated' entry so the bell shows a single item per send.
            if str(_fields.get('Status', '')) != 'Sent':
                _create_notification(
                    session.get('user_sid', ''), session.get('user_name', ''),
                    'Status Updated', 'Opt Comm',
                    deal_id + ' → ' + str(_fields.get('Status', '')) + _nd_token(updated_deal.get('TradeDate'))
                )
        else:
            _create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Deal Updated', 'Opt Comm',
                deal_id + ' (' + ', '.join(_fields.keys()) + ')' + _nd_token(updated_deal.get('TradeDate'))
            )
    return jsonify({"success": True})


@blueprint.route('/api/new-deals/opt-commodities/cache/<deal_id>', methods=['DELETE'])
def api_delete_deal_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    client = request.args.get('client')
    file_path, _ = _find_deal_in_cache(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        removed = deals.pop(idx)
        _atomic_write_json(file_path, deals)

    _create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'Deal Deleted', 'Opt Comm', deal_id + _nd_token((removed or {}).get('TradeDate'))
    )
    return jsonify({"success": True})


@blueprint.route('/api/new-deals/opt-commodities/cache/bulk-delete', methods=['POST'])
def api_bulk_delete_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data  = request.get_json(silent=True)
    pairs = data.get('pairs', []) if data else []
    if not pairs:
        return jsonify({"success": False, "message": "No pairs provided"}), 400

    pair_set = {(p.get('deal', ''), p.get('client', '')) for p in pairs}

    # Group pairs by their source file (search outside the lock — read-only scan)
    file_pairs = {}
    for deal_name, client_name in pair_set:
        fp, _ = _find_deal_in_cache(deal_name, client_name)
        if fp:
            file_pairs.setdefault(fp, set()).add((deal_name, client_name))

    deleted = 0
    for fp, pairs_in_file in file_pairs.items():
        with _cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            if not isinstance(deals, list):
                deals = [deals]
            before = len(deals)
            deals  = [d for d in deals if (d.get('Deal', ''), d.get('Client', '')) not in pairs_in_file]
            deleted += before - len(deals)
            _atomic_write_json(fp, deals)

    not_found = len(pair_set) - deleted
    if deleted > 0:
        _create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Bulk Delete', 'Opt Comm',
            str(deleted) + ' deal' + ('s' if deleted != 1 else '') + ' deleted'
        )
    return jsonify({"success": True, "deleted": deleted, "not_found": not_found})


@blueprint.route('/api/new-deals/opt-commodities/cache/bulk-patch', methods=['POST'])
def api_opt_bulk_patch_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data    = request.get_json(silent=True)
    patches = data.get('patches', []) if data else []
    if not patches:
        return jsonify({"success": False, "message": "No patches provided"}), 400

    # Group by source file (outside lock — read-only scan)
    file_patches = {}
    for p in patches:
        deal_id = p.get('deal_id', '')
        client  = p.get('client', '')
        updates = p.get('updates', {})
        if not deal_id or not updates:
            continue
        fp, _ = _find_deal_in_cache(deal_id, client)
        if fp:
            file_patches.setdefault(fp, []).append((deal_id, client, updates))

    updated = 0
    for fp, file_ops in file_patches.items():
        with _cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            for deal_id, client, updates in file_ops:
                want_client = (client or '').strip()
                matching = [i for i, d in enumerate(deals)
                            if (d.get('Deal') or '').strip() == deal_id.strip()
                            and (not want_client or (d.get('Client') or '').strip() == want_client)]
                if matching:
                    for idx in matching:
                        deals[idx].update(updates)
                        updated += 1
                else:
                    log.warning("[OPT BULK-PATCH] idx not found: deal=%r client=%r in %s",
                                deal_id, client, fp)
            _atomic_write_json(fp, deals)

    if updated > 0:
        _create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Bulk Update', 'Opt Comm',
            str(updated) + ' deal' + ('s' if updated != 1 else '') + ' updated'
        )
    return jsonify({"success": True, "updated": updated})


# ==============================================================================
# API — OPT FXO CACHE (mesma lógica que opt-commodities, arquivo _optfxo.json)
# CRUD + bulk only. mapping-b3 / send-conecta / premium / econ-affirmation e o
# import do blotter XLSX (Brazil_FXO_Blotter_Extended_*_YYYYMMDD.xlsx) são
# product-specific e serão implementados quando o mapeamento de colunas chegar.
# ==============================================================================
def _find_fxo(deal_name, client_name=None):
    """Search all YYYYMMDD_optfxo.json files for a deal by Deal + Client.
    Returns (file_path, list_index) or (None, None)."""
    for root, _dirs, files in os.walk(OPT_FXO_CACHE_DIR):
        for fname in sorted(files, reverse=True):
            if not fname.endswith('_optfxo.json'):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
                for i, deal in enumerate(deals):
                    d_name   = (deal.get('Deal')   or '').strip()
                    d_client = (deal.get('Client') or '').strip()
                    if deal_name and d_name == deal_name.strip():
                        want = (client_name or '').strip()
                        if not want or d_client == want:
                            return fpath, i
            except Exception:
                continue
    return None, None


@blueprint.route('/api/new-deals/opt-fxo/cache', methods=['POST'])
def api_save_fxo_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    trade_date_raw = data.get('TradeDate', '')
    try:
        ref_date = datetime.strptime(trade_date_raw, '%d/%m/%Y')
    except (ValueError, TypeError):
        ref_date = datetime.now()

    dir_path = os.path.join(OPT_FXO_CACHE_DIR, ref_date.strftime('%Y'), ref_date.strftime('%m'))
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, ref_date.strftime('%Y%m%d') + '_optfxo.json')

    with _cache_lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
            except (json.JSONDecodeError, ValueError):
                deals = []
        else:
            deals = []

        deal_name   = data.get('Deal', '').strip()
        client_name = data.get('Client', '').strip()
        data.pop('_client', None)
        existing_idx = next((i for i, d in enumerate(deals)
                             if deal_name
                             and d.get('Deal', '').strip() == deal_name
                             and d.get('Client', '').strip() == client_name), None)
        # Persist in table-column order (Maker/Checker last) — not alphabetical.
        if existing_idx is not None:
            deals[existing_idx] = _fxo_order_deal(data)
        else:
            deals.append(_fxo_order_deal(data))
        _atomic_write_json(file_path, deals)

    return jsonify({"success": True, "deal": data.get('Deal', '')})


@blueprint.route('/api/new-deals/opt-fxo/cache/search', methods=['POST'])
def api_search_fxo_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    body = request.get_json(silent=True) or {}
    filters = body.get('filters', [])
    matched = []
    for root, _dirs, files in os.walk(OPT_FXO_CACHE_DIR):
        for fname in sorted(files):
            if not fname.endswith('_optfxo.json'):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
                for deal in deals:
                    if _deal_matches(deal, filters):
                        matched.append(deal)
            except Exception:
                continue
    return jsonify({"success": True, "deals": matched})


@blueprint.route('/api/new-deals/opt-fxo/cache/<deal_id>', methods=['PATCH'])
def api_update_fxo_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    client  = request.args.get('client')
    updates = request.get_json(silent=True)
    if not updates:
        return jsonify({"success": False, "message": "No data provided"}), 400

    file_path, _ = _find_fxo(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        updates.pop('_client', None)
        deals[idx].update(updates)
        # Rewrite in table-column order (Maker/Checker last) — not alphabetical.
        deals[idx] = _fxo_order_deal(deals[idx])
        _atomic_write_json(file_path, deals)
        updated_deal = deals[idx].copy()

    # Mirror opt-comm: push to Intrag Option (FXO overrides) when Status→Success
    # and the counterparty is Banco J.P. Morgan (intragroup).
    if str(updates.get('Status', '')) == 'Success':
        _maybe_save_intrag_fxo(updated_deal)

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            if str(_fields.get('Status', '')) != 'Sent':
                _create_notification(
                    session.get('user_sid', ''), session.get('user_name', ''),
                    'Status Updated', 'Opt FXO',
                    deal_id + ' → ' + str(_fields.get('Status', '')) + _nd_token(updated_deal.get('TradeDate'))
                )
        else:
            _create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Deal Updated', 'Opt FXO',
                deal_id + ' (' + ', '.join(_fields.keys()) + ')' + _nd_token(updated_deal.get('TradeDate'))
            )
    return jsonify({"success": True})


@blueprint.route('/api/new-deals/opt-fxo/cache/<deal_id>', methods=['DELETE'])
def api_delete_fxo_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    client = request.args.get('client')
    file_path, _ = _find_fxo(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        removed = deals.pop(idx)
        _atomic_write_json(file_path, deals)

    _create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'Deal Deleted', 'Opt FXO', deal_id + _nd_token((removed or {}).get('TradeDate'))
    )
    return jsonify({"success": True})


@blueprint.route('/api/new-deals/opt-fxo/cache/bulk-delete', methods=['POST'])
def api_bulk_delete_fxo_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    data  = request.get_json(silent=True)
    pairs = data.get('pairs', []) if data else []
    if not pairs:
        return jsonify({"success": False, "message": "No pairs provided"}), 400

    pair_set = {(p.get('deal', ''), p.get('client', '')) for p in pairs}
    file_pairs = {}
    for deal_name, client_name in pair_set:
        fp, _ = _find_fxo(deal_name, client_name)
        if fp:
            file_pairs.setdefault(fp, set()).add((deal_name, client_name))

    deleted = 0
    for fp, pairs_in_file in file_pairs.items():
        with _cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            if not isinstance(deals, list):
                deals = [deals]
            before = len(deals)
            deals  = [d for d in deals if (d.get('Deal', ''), d.get('Client', '')) not in pairs_in_file]
            deleted += before - len(deals)
            _atomic_write_json(fp, deals)

    not_found = len(pair_set) - deleted
    if deleted > 0:
        _create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Bulk Delete', 'Opt FXO',
            str(deleted) + ' deal' + ('s' if deleted != 1 else '') + ' deleted'
        )
    return jsonify({"success": True, "deleted": deleted, "not_found": not_found})


@blueprint.route('/api/new-deals/opt-fxo/cache/bulk-patch', methods=['POST'])
def api_fxo_bulk_patch_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    data    = request.get_json(silent=True)
    patches = data.get('patches', []) if data else []
    if not patches:
        return jsonify({"success": False, "message": "No patches provided"}), 400

    file_patches = {}
    for p in patches:
        deal_id = p.get('deal_id', '')
        client  = p.get('client', '')
        updates = p.get('updates', {})
        if not deal_id or not updates:
            continue
        fp, _ = _find_fxo(deal_id, client)
        if fp:
            file_patches.setdefault(fp, []).append((deal_id, client, updates))

    updated = 0
    for fp, file_ops in file_patches.items():
        with _cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            for deal_id, client, updates in file_ops:
                want_client = (client or '').strip()
                matching = [i for i, d in enumerate(deals)
                            if (d.get('Deal') or '').strip() == deal_id.strip()
                            and (not want_client or (d.get('Client') or '').strip() == want_client)]
                for idx in matching:
                    deals[idx].update(updates)
                    deals[idx] = _fxo_order_deal(deals[idx])
                    updated += 1
            _atomic_write_json(fp, deals)

    if updated > 0:
        _create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Bulk Update', 'Opt FXO',
            str(updated) + ' deal' + ('s' if updated != 1 else '') + ' updated'
        )
    return jsonify({"success": True, "updated": updated})


# ──────────────────────────────────────────────────────────────────────────
# OPT FXO — XLSX blotter import (Brazil_FXO_Blotter_Extended_*_YYYYMMDD.xlsx)
# ──────────────────────────────────────────────────────────────────────────
# Internal 3-letter currency codes (feed) → ISO. Extend as new codes appear.
_FXO_CCY_MAP = {
    'BRR': 'BRL', 'USB': 'USD', 'EUB': 'EUR', 'GBB': 'GBP',
    'CHB': 'CHF', 'NOB': 'NOK', 'COB': 'COP',
}
_FXO_MONTHS_EN = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                  'August', 'September', 'October', 'November', 'December']


def _fxo_ccy(code):
    c = str(code or '').strip().upper()
    return _FXO_CCY_MAP.get(c, c)


def _fxo_num(v):
    """Parse a blotter number (native float, or BR '1.234,56' / US '1234.56') → float|None."""
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    neg = s.startswith('-')
    s = s.lstrip('+-').replace(' ', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')   # BR: dot=thousands, comma=decimal
    elif ',' in s:
        s = s.replace(',', '.')                     # comma decimal
    try:
        val = float(s)
        return -val if neg else val
    except ValueError:
        return None


def _fxo_date_dmy(v):
    """yyyy-mm-dd / datetime / date → dd/mm/yyyy; blank/other → ''."""
    if v is None or v == '':
        return ''
    if hasattr(v, 'strftime'):
        return v.strftime('%d/%m/%Y')
    s = str(v).strip().split('T')[0].split(' ')[0]
    if not s:
        return ''
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    return s


def _fxo_refdata_by_spn():
    """SPN (leading-zeros stripped) → RefData record, for client/taxid/acronym lookup."""
    out = {}
    try:
        with open(os.path.join(_B3_DATA_DIR, 'RefData.json'), encoding='utf-8') as fh:
            data = json.load(fh)
        for rec in (data if isinstance(data, list) else []):
            key = _norm_spn(rec.get('SPN', ''))
            if key:
                out[key] = rec
    except (IOError, json.JSONDecodeError):
        pass
    return out


# Canonical field order = the New Deals Opt-FXO table column order (same order the
# XLSX import builds each dict). Persisted _optfxo.json must follow this, not the
# alphabetical order some legacy writes produced. Maker/Checker are kept last.
_FXO_FIELD_ORDER = (
    'Status', 'Deal', 'B3_ID', 'TradeDate', 'Month', 'SettlementDate',
    'SPN', 'Acronym', 'Client', 'TaxID', 'TradeType', 'UnderlyingAsset',
    'FXHolidaySchedule', 'TotalNotional', 'Instrument', 'Strike',
    'StrikeCurrency', 'Direction', 'Premium', 'PremiumPerUnit', 'PremiumCCY',
    'SpotDate', 'FixingStartDate', 'FixingEndDate', 'TradingBook', 'OtherBook',
)


def _fxo_order_deal(d):
    """Return a new dict with keys in table-column order so the persisted
    _optfxo.json is column-ordered (not alphabetical). Known columns come first
    in canonical order, then any extra keys (e.g. _fdate) in their existing
    order, and Maker/Checker always last (matching the previous convention)."""
    if not isinstance(d, dict):
        return d
    tail = ('Maker', 'Checker')
    ordered = {}
    for k in _FXO_FIELD_ORDER:
        if k in d:
            ordered[k] = d[k]
    for k, v in d.items():
        if k not in ordered and k not in tail:
            ordered[k] = v
    for k in tail:
        if k in d:
            ordered[k] = d[k]
    return ordered


def _fxo_persist_deals(deals):
    """Upsert FXO deals into per-TradeDate _optfxo.json by Deal+Client. Returns count."""
    by_file = {}
    for d in deals:
        try:
            ref_date = datetime.strptime(d.get('TradeDate', ''), '%d/%m/%Y')
        except (ValueError, TypeError):
            ref_date = datetime.now()
        dir_path = os.path.join(OPT_FXO_CACHE_DIR, ref_date.strftime('%Y'), ref_date.strftime('%m'))
        fpath = os.path.join(dir_path, ref_date.strftime('%Y%m%d') + '_optfxo.json')
        by_file.setdefault(fpath, (dir_path, []))[1].append(d)

    saved = 0
    with _cache_lock:
        for fpath, (dir_path, ds) in by_file.items():
            os.makedirs(dir_path, exist_ok=True)
            try:
                with open(fpath, encoding='utf-8') as fh:
                    existing = json.load(fh)
                if not isinstance(existing, list):
                    existing = [existing]
            except (IOError, json.JSONDecodeError):
                existing = []
            for d in ds:
                idx = next((i for i, e in enumerate(existing)
                            if (e.get('Deal') or '').strip() == (d.get('Deal') or '').strip()
                            and (e.get('Client') or '').strip() == (d.get('Client') or '').strip()), None)
                if idx is not None:
                    existing[idx] = _fxo_order_deal(d)
                else:
                    existing.append(_fxo_order_deal(d))
                saved += 1
            _atomic_write_json(fpath, existing)
    return saved


@blueprint.route('/api/new-deals/opt-fxo/cache/batch', methods=['POST'])
def api_fxo_cache_batch():
    """Persist a finalized list of FXO deals (after the page resolves duplicates)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    data = request.get_json(silent=True) or {}
    deals = data.get('deals', [])
    if not deals:
        return jsonify({'success': True, 'imported': 0})
    saved = _fxo_persist_deals(deals)
    if saved:
        _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'New Deals', 'Opt FXO',
                             '{} deal{} imported from XLSX'.format(saved, '' if saved == 1 else 's'))
    return jsonify({'success': True, 'imported': saved})


@blueprint.route('/api/new-deals/opt-fxo/import-xlsx', methods=['POST'])
def api_fxo_import_xlsx():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    import openpyxl

    files = request.files.getlist('files')
    if not files and 'file' in request.files:
        files = [request.files['file']]
    if not files:
        return jsonify({'success': False, 'message': 'no_file'}), 400

    sid = session.get('user_sid', '') or ''
    refmap = _fxo_refdata_by_spn()
    PUT_CALL = {'PUT': 'Option (Put)', 'CALL': 'Option (Call)'}
    deals, errors = [], []

    for f in files:
        if not f or not (f.filename or '').lower().endswith('.xlsx'):
            continue
        try:
            wb = openpyxl.load_workbook(io.BytesIO(f.read()), read_only=True, data_only=True)
        except Exception as e:                       # noqa: BLE001
            errors.append('{}: {}'.format(f.filename, e))
            continue
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        try:
            header = next(it)
        except StopIteration:
            wb.close()
            continue

        col = {}
        for i, h in enumerate(header):
            n = re.sub(r'[\s_]+', ' ', str(h or '').strip().upper())
            if n and n not in col:
                col[n] = i

        def g(row, name):
            i = col.get(name)
            return row[i] if (i is not None and i < len(row)) else None

        for r in it:
            if r is None:
                continue
            # Drop rows with empty End Counterparty (P) / Description (Q) / SPN (O)
            if str(g(r, 'END COUNTERPARTY') or '').strip() == '':
                continue
            if str(g(r, 'END COUNTERPARTY DESCRIPTION') or '').strip() == '':
                continue
            if str(g(r, 'SPN') or '').strip() == '':
                continue

            # B3 does not accept underscores in the deal id on file registration —
            # replace '_' with '-' at the source (applies to Deal, dedup, Conecta).
            deal_name = str(g(r, 'DEAL NAME') or '').strip().replace('_', '-')
            if not deal_name:
                continue

            spn = str(g(r, 'SPN') or '').strip()
            if spn.endswith('.0'):
                spn = spn[:-2]
            ref = refmap.get(_norm_spn(spn), {})

            strike_v = _fxo_num(g(r, 'STRIKE'))
            premq_v  = _fxo_num(g(r, 'PREMIUM QUANTITY'))
            qty_v    = _fxo_num(g(r, 'QUANTITY'))
            ppu_v    = (premq_v / qty_v) if (premq_v is not None and qty_v not in (None, 0)) else None

            first_fix = g(r, 'FIRST FIXING DATE')
            last_fix  = g(r, 'LAST FIXING DATE')
            if str(first_fix or '').strip() and str(last_fix or '').strip():
                trade_type, fix_start, fix_end = 'ASIAN', _fxo_date_dmy(first_fix), _fxo_date_dmy(last_fix)
            else:
                exp = _fxo_date_dmy(g(r, 'EXPIRATION DATE'))
                trade_type, fix_start, fix_end = 'VANILLA', exp, exp

            trade_date = _fxo_date_dmy(g(r, 'TRADE DATE'))
            try:
                month = _FXO_MONTHS_EN[datetime.strptime(trade_date, '%d/%m/%Y').month - 1] if trade_date else ''
            except ValueError:
                month = ''

            direction = str(g(r, 'TYPE') or '').strip().upper()
            strike_ccy = _fxo_ccy(g(r, 'QUANTITY CURRENCY'))  # FXO: Underlying Asset == Strike Currency

            deals.append({
                'Status':            'New',
                'Deal':              deal_name,
                'B3_ID':             '',
                'TradeDate':         trade_date,
                'Month':             month,
                'SettlementDate':    _fxo_date_dmy(g(r, 'SETTLEMENT DATE')),
                'SPN':               spn,
                'Acronym':           ref.get('FX CASH ACCRONYM', '') or '',
                'Client':            ref.get('COUNTERPARTY', '') or '',
                'TaxID':             ref.get('TAX ID', '') or '',
                'TradeType':         trade_type,
                'UnderlyingAsset':   strike_ccy,
                'FXHolidaySchedule': 'ANBIMA',
                'TotalNotional':     ('{:,.2f}'.format(qty_v) if qty_v is not None else ''),
                'Instrument':        PUT_CALL.get(str(g(r, 'OPTION TYPE') or '').strip().upper(), ''),
                'Strike':            ('{:.6f}'.format(strike_v) if strike_v is not None else ''),
                'StrikeCurrency':    strike_ccy,
                'Direction':         direction,
                'Premium':           ('{:,.2f}'.format(premq_v) if premq_v is not None else ''),
                'PremiumPerUnit':    ('{:,.8f}'.format(ppu_v) if ppu_v is not None else ''),
                'PremiumCCY':        _fxo_ccy(g(r, 'PREMIUM CCY')),
                'SpotDate':          _fxo_date_dmy(g(r, 'PREMIUM DATE')),
                'FixingStartDate':   fix_start,
                'FixingEndDate':     fix_end,
                'TradingBook':       str(g(r, 'TRADING BOOK') or '').strip(),
                'OtherBook':         str(g(r, 'OTHER BOOK') or '').strip(),
                'Maker':             sid,
            })
        wb.close()

    # dry_run=1 → parse only (the page first checks Deal+Client duplicates against
    # the table and asks the user before persisting via /cache/batch).
    dry_run = (request.args.get('dry_run') in ('1', 'true', 'yes')
               or (request.form.get('dry_run') in ('1', 'true', 'yes')))
    saved = 0
    if not dry_run:
        saved = _fxo_persist_deals(deals)
        if saved:
            _create_notification(sid, session.get('user_name', ''),
                                 'New Deals', 'Opt FXO',
                                 '{} deal{} imported from XLSX'.format(saved, '' if saved == 1 else 's'))
    return jsonify({'success': True, 'imported': saved, 'deals': deals, 'errors': errors})


@blueprint.route('/api/new-deals/opt-fxo/send-conecta', methods=['POST'])
def api_fxo_send_conecta():
    """B3 Conecta file for FXO. Same layout as opt-commodities with the FXO tweaks:
    Tipo Indicador (f[2])='4', Tipo de Cotação (f[17])='2',
    'Data de fixing do ativo subjacente' (f[19]) = last fixing date when VANILLA (blank ASIAN),
    'Data de fixing da moeda do ativo subjacente' (f[20]) always blank.
    Asian fixing-date count uses the ANBIMA calendar (FXHolidaySchedule)."""
    from decimal import Decimal
    import datetime as _dt
    import json as _json

    data  = request.get_json(silent=True) or {}
    deals = data.get('deals', [])
    if not deals:
        return jsonify({'ok': False, 'error': 'No deals provided'}), 400

    today = _dt.datetime.today().strftime('%Y%m%d')

    def _sh(v):
        return re.sub(r'<[^>]+>', '', str(v or '')).strip()

    def _date(val):
        val = _sh(val)
        if not val:
            return ''
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                return _dt.datetime.strptime(val, fmt).strftime('%Y%m%d')
            except ValueError:
                continue
        return ''

    def _num(val, div100=False):
        val = _sh(str(val or ''))
        if not val:
            return ''
        clean = val.replace(',', '')
        try:
            d = Decimal(clean)
            if div100:
                d = d / Decimal('100')
            return format(d.normalize(), 'f').replace('.', ',')
        except Exception:
            return clean.replace('.', ',')

    def _qty(val):
        v = _sh(str(val or ''))
        if not v:
            return ''
        try:
            return str(int(round(float(v.replace(',', ''))))) + ',00'
        except Exception:
            return v

    def _cli(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '73760009'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '00041007'
        return '73760009'

    def _cpty(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '00041007'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '73760009'
        return '73760102'

    def _taxid(client, taxid):
        c = client.upper()
        if 'LAWTON' in c or 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return ''
        return re.sub(r'[.\-/]', '', _sh(taxid))

    deal_count = 0
    all_lines  = []

    for deal in deals:
        client     = _sh(deal.get('Client', ''))
        taxid      = _sh(deal.get('TaxID', ''))
        instrument = _sh(deal.get('Instrument', ''))
        direction  = _sh(deal.get('Direction', ''))
        trade_type       = _sh(deal.get('TradeType', ''))
        strike_ccy       = _sh(deal.get('StrikeCurrency', ''))
        fx_holiday_sched = _sh(deal.get('FXHolidaySchedule', '')) or 'anbima'
        vanilla          = trade_type.upper() == 'VANILLA'
        asian            = trade_type.upper() == 'ASIAN'
        brl              = strike_ccy.upper() == 'BRL'

        opt = 'P' if 'PUT' in instrument.upper() else ('C' if 'CALL' in instrument.upper() else '')
        dir_code  = '2' if direction.upper() == 'SELL' else '1'
        fix_start = _date(deal.get('FixingStartDate', ''))
        fix_end   = _date(deal.get('FixingEndDate', ''))

        # ANBIMA calendar (file name is case-insensitive on the FS we run on)
        _deal_holidays = set()
        if not vanilla and fx_holiday_sched:
            _sched_file = fx_holiday_sched.replace('-', '_').lower()
            holiday_path = os.path.join(_B3_DATA_DIR, '{}.json'.format(_sched_file))
            try:
                with open(holiday_path, encoding='utf-8') as _hf:
                    _raw = _json.load(_hf)
                _deal_holidays = set(item['date'] if isinstance(item, dict) else item for item in _raw)
            except Exception:
                pass

        _biz = 0
        if not vanilla and fix_start and fix_end:
            try:
                _s = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e = _dt.datetime.strptime(fix_end, '%Y%m%d').date()
                _cur = _s
                while _cur <= _e:
                    if _cur.weekday() < 5 and _cur.strftime('%Y-%m-%d') not in _deal_holidays:
                        _biz += 1
                    _cur += _dt.timedelta(days=1)
            except Exception:
                pass

        f = [''] * 63
        f[0]  = 'OPC  00002'
        f[1]  = '1'
        f[2]  = '4'                                   # FXO: Tipo Indicador
        f[3]  = _cli(client)
        f[4]  = dir_code
        f[6]  = _cpty(client)
        f[7]  = _taxid(client, taxid)
        f[8]  = opt
        f[9]  = _date(deal.get('TradeDate', ''))
        f[10] = _date(deal.get('SettlementDate', ''))
        f[11] = _sh(deal.get('UnderlyingAsset', ''))
        f[12] = _qty(deal.get('TotalNotional', ''))
        f[13] = _num(deal.get('Strike', ''))
        f[14] = '1'
        f[16] = '2'
        f[17] = '1'                                   # FXO: Tipo de Cotação
        f[18] = 'S' if brl else ''
        f[19] = fix_end if vanilla else ''            # FXO: data fixing ativo subjacente = last fixing (VANILLA)
        f[20] = ''                                    # FXO: data fixing moeda sempre em branco
        f[23] = str(random.randint(1000000000, 9999999999))
        f[24] = _sh(deal.get('Deal', ''))
        f[26] = _num(deal.get('PremiumPerUnit', ''))
        _spot_date = _date(deal.get('SpotDate', ''))
        _is_bank_or_lawton = ('LAWTON' in client.upper() or 'BANCO J.P MORGAN' in client.upper()
                              or 'JP MORGAN' in client.upper())
        if _is_bank_or_lawton:
            f[28] = '2' if f[9] == _spot_date else '3'
        else:
            f[28] = '1'
        f[32] = _spot_date

        if vanilla:
            f[47] = ''
            f[48] = '0'
        else:
            f[47] = '1'
            f[48] = str(_biz) if _biz else ''

        deal_count += 1
        all_lines.append(';'.join(f))

        # Asian — one fixing line (line type 2) per business day in the window
        if asian and fix_start and fix_end:
            try:
                _s2 = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e2 = _dt.datetime.strptime(fix_end, '%Y%m%d').date()
                _cur2 = _s2
                while _cur2 <= _e2:
                    if _cur2.weekday() < 5 and _cur2.strftime('%Y-%m-%d') not in _deal_holidays:
                        _d = _cur2.strftime('%Y%m%d')
                        all_lines.append('OPC  00002;2;{};;;'.format(_d))
                    _cur2 += _dt.timedelta(days=1)
            except Exception:
                pass

    header  = 'OPC  00002;0;JPMORGANBM;{};00002;'.format(today)
    content = '\n'.join([header] + all_lines)

    try:
        os.makedirs(CONECTA_NEW_PATH, exist_ok=True)
        filepath = _unique_filepath(CONECTA_NEW_PATH, 'FXO_Banco.txt')
        with open(filepath, 'w', encoding='utf-8') as fh:
            fh.write(content)
        if deal_count > 0:
            _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                 'Sent to B3', 'Opt FXO',
                                 str(deal_count) + ' deal' + ('' if deal_count == 1 else 's') + ' sent')
        return jsonify({'ok': True, 'filename': os.path.basename(filepath), 'count': deal_count})
    except Exception as exc:                          # noqa: BLE001
        return jsonify({'ok': False, 'error': str(exc)}), 500


@blueprint.route('/api/new-deals/opt-fxo/mapping-b3', methods=['POST'])
def api_fxo_mapping_b3():
    """Same B3-ID mapping as opt-commodities (Conecta return files carry 'OPC'
    option lines), but resolves deals in the _optfxo.json cache."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    data = request.get_json(silent=True) or {}
    sent_deals = data.get('deals', [])
    if not sent_deals:
        return jsonify({'ok': True, 'results': []})

    mapping = {}
    files_to_delete = []
    try:
        if not os.path.isdir(RETURN_PATH):
            return jsonify({'ok': False, 'error': 'Return folder not found: {}'.format(RETURN_PATH)}), 400
        for fname in os.listdir(RETURN_PATH):
            fpath = os.path.join(RETURN_PATH, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                with open(fpath, encoding='utf-8', errors='replace') as fh:
                    lines = fh.readlines()
                file_has_opc = False
                for line in lines[1:]:
                    line = line.strip()
                    if not line or line[56:59] != 'OPC':
                        continue
                    file_has_opc = True
                    parts = line.split(';')
                    if len(parts) < 5:
                        continue
                    b3_id       = parts[1].strip()
                    status_text = parts[3].strip()
                    pipe_parts  = parts[4].strip().split('|')
                    if len(pipe_parts) < 25 or pipe_parts[1].strip() != '1':
                        continue
                    deal_text = pipe_parts[24].strip()
                    if not deal_text:
                        continue
                    is_ok = (status_text == 'EXECUCAO OK')
                    if deal_text not in mapping or (is_ok and not mapping[deal_text]['ok']):
                        mapping[deal_text] = {'b3_id': b3_id, 'ok': is_ok}
                if file_has_opc:
                    files_to_delete.append(fpath)
            except Exception:
                continue
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    results = []
    for sent in sent_deals:
        deal_text   = sent.get('Deal', '')
        client_name = sent.get('Client', '')
        if not deal_text or deal_text not in mapping:
            continue
        info       = mapping[deal_text]
        new_status = 'Success' if info['ok'] else 'Error'
        updates    = {'Status': new_status}
        if info['ok']:
            updates['B3_ID'] = info['b3_id']

        file_path, idx = _find_fxo(deal_text, client_name)
        if file_path is not None:
            intrag_candidate = None
            with _cache_lock:
                try:
                    with open(file_path, 'r', encoding='utf-8') as fh:
                        deals_list = json.load(fh)
                    deals_list[idx].update(updates)
                    _atomic_write_json(file_path, deals_list)
                    if new_status == 'Success':
                        intrag_candidate = deals_list[idx].copy()
                except Exception:
                    pass
            if intrag_candidate is not None:
                _maybe_save_intrag_fxo(intrag_candidate)

        results.append({
            'id':     deal_text,
            'deal':   deal_text,
            'b3_id':  info['b3_id'] if info['ok'] else '',
            'status': new_status,
        })

    for fpath in files_to_delete:
        try:
            os.remove(fpath)
        except Exception:
            pass

    if results:
        _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'B3 Mapped', 'Opt FXO',
                             str(len(results)) + ' deal' + ('' if len(results) == 1 else 's') + ' mapped')
    return jsonify({'ok': True, 'results': results})


# ==============================================================================
# API — NDF COMMODITIES CACHE (mesma lógica que opt-commodities, arquivo _ndfcomm.json)
# ==============================================================================

NDF_COMM_CACHE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "static", "data", "cache", "new deals", "NDF", "Commodities"
))

NEW_DEALS_CACHE_ROOT = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "static", "data", "cache", "new deals"
))

INTRAG_NDF_CACHE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "static", "data", "cache", "new deals", "Intrag", "NDF"
))
INTRAG_OPT_CACHE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "static", "data", "cache", "new deals", "Intrag", "Option"
))

# Network share where generated Intrag NDF .txt files are written. Hardcoded
# Windows path for the JPM machine (mirrors DB_PATH) — change per environment.
INTRAG_NDF_SEND_DIR = r"I:\Confirmation\Derivativos\OTC Tracker\Intrag"

# English month names for the "mm. Mmmm" folder (e.g. "06. June") — fixed list
# so the folder name never depends on the server locale.
_EN_MONTH_NAMES = (
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
)

# ── ANBIMA calendar ───────────────────────────────────────────────────────────

_ANBIMA_HOLIDAYS: set = set()
_anbima_loaded = False

def _load_anbima():
    global _ANBIMA_HOLIDAYS, _anbima_loaded
    if _anbima_loaded:
        return
    try:
        path = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'anbima.json')
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        _ANBIMA_HOLIDAYS = {d['date'] for d in data}
    except Exception as exc:
        log.warning('[ANBIMA] Failed to load anbima.json: %s', exc)
        _ANBIMA_HOLIDAYS = set()
    _anbima_loaded = True

def _prev_anbima_bizday(ref):
    """Return the previous ANBIMA business day (D-1) before `ref` (date/datetime).
    Skips weekends and ANBIMA holidays."""
    _load_anbima()
    cur = ref - timedelta(days=1)
    while cur.weekday() >= 5 or cur.strftime('%Y-%m-%d') in _ANBIMA_HOLIDAYS:
        cur -= timedelta(days=1)
    return cur

def _anbima_bizdays_between(d1, d2):
    """Count ANBIMA business days from d1 (inclusive) up to d2 - 1 (d2 exclusive).

    Counts the first date and stops at the second date minus one day, using the
    ANBIMA holiday calendar (weekdays minus ANBIMA holidays).
    """
    _load_anbima()
    if d1 >= d2:
        return 0
    count, cur = 0, d1
    while cur < d2:
        if cur.weekday() < 5 and cur.strftime('%Y-%m-%d') not in _ANBIMA_HOLIDAYS:
            count += 1
        cur += timedelta(days=1)
    return count

def _weekday_bizdays_between(d1, d2):
    """Count weekday-only days from d1 (inclusive) up to d2 - 1 (d2 exclusive).

    Counts the first date and stops at the second date minus one day, using only
    weekdays (Mon-Fri), with no holiday calendar.
    """
    if d1 >= d2:
        return 0
    count, cur = 0, d1
    while cur < d2:
        if cur.weekday() < 5:
            count += 1
        cur += timedelta(days=1)
    return count

# ── Subjacente.json lookup (keyed by Codigo do Ativo Subjacente, first match) ──

def _load_subjacente_lookup():
    try:
        fp = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'Subjacente.json')
        with open(fp, 'r', encoding='utf-8') as fh:
            rows = json.load(fh)
        result = {}
        for row in rows:
            code = (row.get('Codigo do Ativo Subjacente') or '').strip().upper()
            if code and code not in result:
                result[code] = row
        return result
    except Exception as exc:
        log.warning('[SUBJACENTE] Failed to load: %s', exc)
        return {}

_SUBJACENTE_BY_CODE = _load_subjacente_lookup()

_MONTH_ABBR = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12',
}

def _parse_deal_date(s):
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y%m%d'):
        try:
            return datetime.strptime(s.strip(), fmt)
        except (ValueError, AttributeError):
            pass
    return None

def _save_intrag_ndf_entry(deal):
    """Compute all Intrag NDF fields and append/update in the daily JSON file."""
    td = _parse_deal_date(deal.get('TradeDate', '') or '')
    sd = _parse_deal_date(deal.get('SettlementDate', '') or '')
    fx = _parse_deal_date(deal.get('FXConvDate', '') or '')
    fe = _parse_deal_date(deal.get('FixingEndDate', '') or '')

    fmt_d = lambda d: d.strftime('%Y-%m-%d') if d else ''

    direction = (deal.get('Direction', '') or '').upper()
    position = 'VENDEDOR' if direction == 'SELL' else ('COMPRADOR' if direction == 'BUY' else '')

    try:
        total_notional = float(str(deal.get('TotalNotional', 0) or 0).replace(',', ''))
    except (ValueError, TypeError):
        total_notional = 0.0
    try:
        strike_val = float(str(deal.get('Strike', 0) or 0).replace(',', ''))
    except (ValueError, TypeError):
        strike_val = 0.0

    qic = (deal.get('QuotedInCents', 'NO') or 'NO').upper() == 'YES'
    strike_effective = strike_val / 100.0 if qic else strike_val
    notional_value_str = f'{total_notional * strike_effective:.2f}' if (total_notional and strike_val) else ''
    qty_str = str(int(round(total_notional))) if total_notional else ''
    strike_str = f'{strike_effective:.4f}' if strike_val else ''

    underlying_asset = (deal.get('UnderlyingAsset', '') or '').strip()
    subj = _SUBJACENTE_BY_CODE.get(underlying_asset.upper(), {})
    reference_exchange = (subj.get('Bolsa de Negociacao') or '').strip()
    commodity = (deal.get('Commodities', '') or '').strip()
    unit = (subj.get('Unidade de Negociacao') or '').strip()
    strike_ccy = (deal.get('StrikeCurrency', '') or '').strip()

    # Expiry month/year from Month field (e.g. "DEC26" → "12-2026")
    expiry_str = ''
    month_raw = (deal.get('Month', '') or '').strip().upper()
    m = re.match(r'^([A-Z]{3})(\d{2,4})$', month_raw)
    if m:
        mon_num = _MONTH_ABBR.get(m.group(1), '')
        yr = m.group(2) if len(m.group(2)) == 4 else '20' + m.group(2)
        if mon_num:
            expiry_str = f'{mon_num}-{yr}'
    elif re.match(r'^\d{4}-\d{2}$', month_raw):
        parts = month_raw.split('-')
        expiry_str = f'{parts[1]}-{parts[0]}'
    elif sd:
        expiry_str = sd.strftime('%m-%Y')

    # ANBIMA biz days between FXConvDate and SettlementDate
    anbima_days = ''
    if fx and sd:
        lo, hi = (fx, sd) if fx < sd else (sd, fx)
        anbima_days = f'D-{_anbima_bizdays_between(lo, hi)}'

    # Weekday biz days between SettlementDate and FixingEndDate
    weekday_days = ''
    if sd and fe:
        lo, hi = (sd, fe) if sd < fe else (fe, sd)
        weekday_days = f'D-{_weekday_bizdays_between(lo, hi)}'

    trade_type = (deal.get('TradeType', '') or '').upper()
    trade_type_label = 'ASIATICO' if 'ASIAN' in trade_type else ('FINAL' if 'VANILLA' in trade_type else '')

    strike_ccy_label = 'Strike em BRL' if strike_ccy.upper() == 'BRL' else ''

    entry = {
        'contract_type':          'NDF - TERMO MERCADORIA',
        'b3_id':                  deal.get('B3_ID', '') or '',
        'portfolio_code':         'INTRAGJP552',
        'participant_position':   position,
        'party_tax_id':           '',
        'counterparty':           'JPM',
        'cpty_tax_id':            '',
        'cpty_collateral_basket': 'NÃO',
        'party_collateral_basket':'NÃO',
        'notional_value':         notional_value_str,
        'trade_date':             fmt_d(td),
        'registration_date':      fmt_d(td),
        'maturity_date':          fmt_d(sd),
        'currency':               'N/A',
        'reference_exchange':     reference_exchange,
        'commodity':              commodity,
        'underlying_asset':       underlying_asset,
        'quantity':               qty_str,
        'unit_of_negotiation':    unit,
        'strike':                 strike_str,
        'strike_currency':        strike_ccy,
        'expiry_month_year':      expiry_str,
        'anbima_bizdays':         anbima_days,
        'fixed_0':                '0',
        'na_1':                   'N/A',
        'na_2':                   'N/A',
        'weekday_bizdays':        weekday_days,
        'trade_type_label':       trade_type_label,
        'strike_ccy_label':       strike_ccy_label,
        'na_3':                   'N/A',
        '_deal':                  deal.get('Deal', '') or '',
        '_client':                deal.get('Client', '') or '',
        'status':                 'New',
        'maker':                  '',
        'checker':                '',
    }

    ref = td or datetime.now()
    dir_path = os.path.join(INTRAG_NDF_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'))
    os.makedirs(dir_path, exist_ok=True)
    fname = ref.strftime('%Y%m%d') + '_intrag_ndf.json'
    file_path = os.path.join(dir_path, fname)

    with _cache_lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    entries = json.load(fh)
                if not isinstance(entries, list):
                    entries = []
            except (json.JSONDecodeError, ValueError):
                entries = []
        else:
            entries = []
        deal_id = entry['_deal']
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            # Preserve the existing lifecycle state on re-save — only the very
            # first time an entry lands in the JSON does it start as 'New'.
            entry['status']  = entries[idx].get('status') or 'New'
            entry['maker']   = entries[idx].get('maker', '')
            entry['checker'] = entries[idx].get('checker', '')
            entries[idx] = entry
        else:
            entries.append(entry)
        _atomic_write_json(file_path, entries)
    log.info('[INTRAG NDF] Saved entry deal=%r → %s', deal_id, file_path)


# Intra-group accounts: 73760.00-9 = Banco J.P. Morgan, 00041.00-7 = Lawton.
_INTRAG_OPT_JPM_ACC    = '73760.00-9'
_INTRAG_OPT_LAWTON_ACC = '00041.00-7'
_INTRAG_OPT_JPM_NAME    = 'BANCO J.P MORGAN S.A'
_INTRAG_OPT_LAWTON_NAME = 'LAWTON MULTIMERCADO-FI'


def _intrag_opt_name_for(acc):
    if acc == _INTRAG_OPT_JPM_ACC:
        return _INTRAG_OPT_JPM_NAME
    if acc == _INTRAG_OPT_LAWTON_ACC:
        return _INTRAG_OPT_LAWTON_NAME
    return ''


def _save_intrag_opt_entry(deal, is_fxo=False):
    """Compute the Intrag Option fields from a New Deals Opt-Comm (or Opt-FXO)
    deal and append/update the daily JSON. Only the columns specified so far are
    filled; the rest are placeholders to be wired later. Random my_number /
    cetip_number are generated once and preserved on re-save (like the lifecycle
    state).

    FXO deals share the same intrag_opt.json file and the same filling logic,
    but override seven fields (information source, exchange, ticker, currency
    symbol, bulletin, bulletin time and SISBACEN currency code)."""
    td = _parse_deal_date(deal.get('TradeDate', '') or '')
    sd = _parse_deal_date(deal.get('SettlementDate', '') or '')
    fmt_br = lambda d: d.strftime('%d/%m/%Y') if d else ''

    direction = (deal.get('Direction', '') or '').upper()
    if direction == 'BUY':
        buyer_account = _INTRAG_OPT_LAWTON_ACC
    elif direction == 'SELL':
        buyer_account = _INTRAG_OPT_JPM_ACC
    else:
        buyer_account = ''
    buyer_name = _intrag_opt_name_for(buyer_account)
    # Seller is the inverse account/name of the buyer.
    if buyer_account == _INTRAG_OPT_JPM_ACC:
        seller_account = _INTRAG_OPT_LAWTON_ACC
    elif buyer_account == _INTRAG_OPT_LAWTON_ACC:
        seller_account = _INTRAG_OPT_JPM_ACC
    else:
        seller_account = ''
    seller_name = _intrag_opt_name_for(seller_account)

    instrument = (deal.get('Instrument', '') or '').upper()
    if 'PUT' in instrument:
        contract = 'OFVC'
    elif 'CALL' in instrument:
        contract = 'OFCC'
    else:
        contract = ''

    currency_symbol = (deal.get('Commodities', '') or '').strip()[:3].upper()

    # ── numeric columns ──────────────────────────────────────────────────
    def _f(v):
        try:
            return float(str(v if v is not None else '').replace(',', '').strip() or 0)
        except (ValueError, TypeError):
            return 0.0

    def _has(key):
        return str(deal.get(key, '') or '').strip() != ''

    qic        = (deal.get('QuotedInCents', 'NO') or 'NO').upper() == 'YES'
    strike_ccy = (deal.get('StrikeCurrency', '') or '').strip().upper()
    is_brl     = strike_ccy == 'BRL'
    # Non-BRL quoted-in-cents prices are normalized /100; BRL never divides.
    _cents = lambda v: (v / 100.0) if (qic and not is_brl) else v

    is_call = 'CALL' in instrument
    is_put  = 'PUT' in instrument

    premium_val  = _f(deal.get('Premium'))
    notional_val = _f(deal.get('TotalNotional'))
    strike_adj   = _cents(_f(deal.get('Strike')))
    ppu_adj      = _cents(_f(deal.get('PremiumPerUnit')))

    premium_str    = '{:.2f}'.format(premium_val)  if _has('Premium')       else ''
    fxbase_str     = '{:.2f}'.format(notional_val) if _has('TotalNotional') else ''
    quantity_str   = '{:.2f}'.format(notional_val) if _has('TotalNotional') else ''
    call_strike    = '{:.8f}'.format(strike_adj)   if (is_call and _has('Strike')) else ''
    put_strike     = '{:.8f}'.format(strike_adj)   if (is_put  and _has('Strike')) else ''
    call_premium   = '{:.8f}'.format(ppu_adj)      if (is_call and _has('PremiumPerUnit')) else ''
    put_premium    = '{:.8f}'.format(ppu_adj)      if (is_put  and _has('PremiumPerUnit')) else ''

    # Fixing = weekday biz-days (no calendar) between FixingEndDate and SettlementDate.
    fe = _parse_deal_date(deal.get('FixingEndDate', '') or '')
    fixing_days = ''
    if fe and sd:
        lo, hi = (fe, sd) if fe < sd else (sd, fe)
        fixing_days = str(_weekday_bizdays_between(lo, hi))
    fixing_desc = ('D-' + fixing_days) if fixing_days != '' else ''

    underlying_asset = (deal.get('UnderlyingAsset', '') or '').strip()
    subj = _SUBJACENTE_BY_CODE.get(underlying_asset.upper(), {})
    exchange = (subj.get('Bolsa de Negociacao') or '').strip()

    spot = _parse_deal_date(deal.get('SpotDate', '') or '')
    trade_type = (deal.get('TradeType', '') or '').upper()
    if 'ASIAN' in trade_type:
        asian_label = 'APLICÁVEL'
    elif 'VANILLA' in trade_type:
        asian_label = 'NÃO APLICÁVEL'
    else:
        asian_label = ''

    # FXO overrides these seven columns; everything else uses the shared logic.
    if is_fxo:
        info_source   = 'SISBACEN'
        exchange_val  = 'BACEN'
        ticker_val    = 'USD'
        currency_sym  = 'USD'
        bulletin_val  = '3'
        bulletin_time = '18:00'
        sisbacen_ccy  = '220'
    else:
        info_source   = 'COMMODITIES'
        exchange_val  = exchange
        ticker_val    = underlying_asset
        currency_sym  = currency_symbol
        bulletin_val  = '9'
        bulletin_time = ''
        sisbacen_ccy  = 'COM'

    entry = {
        'portfolio':              'INTRAGJP552',
        'system_id':              'OPCAO',
        'line_type_id':           '1',
        'registration_date':      fmt_br(td),
        'buyer_account':          buyer_account,
        'buyer_name':             buyer_name,
        'contract':               contract,
        'b3_id':                  deal.get('B3_ID', '') or '',
        'my_number':              ''.join(random.choice(string.digits) for _ in range(10)),
        'trade_type':             '002',
        'seller_account':         seller_account,
        'seller_name':            seller_name,
        'start_date':             fmt_br(td),
        'maturity_date':          fmt_br(sd),
        'cetip_number':           ''.join(random.choice(string.digits) for _ in range(16)),
        'sisbacen_currency_code': sisbacen_ccy,
        'currency_symbol':        currency_sym,
        'investment_amount':      premium_str,        # Premium
        'fx_base_value':          fxbase_str,         # Total Notional
        'prepaid_value':          '',                 # Unwind Amount
        'prepayment_unit_price':  '',                 # Unwind Unit Price
        'redemption_value':       '0.00',
        'call_strike_price':      call_strike,
        'put_strike_price':       put_strike,
        'call_unit_premium':      call_premium,
        'put_unit_premium':       put_premium,
        'barrier_rate':           '',
        'exercise_type':          'EUROPEIA',
        'information_source':     info_source,
        'bulletin':               bulletin_val,
        'bulletin_time':          bulletin_time,
        'maturity_rate':          fixing_days,        # Fixing (biz-day count)
        'maturity_rate_desc':     fixing_desc,        # Fixing Description (D-n)
        'query_source':           exchange_val,       # Exchange (Bolsa de Negociacao)
        'ticker':                 ticker_val,
        'quantity':               quantity_str,
        'premium_payment_date':   spot.strftime('%d/%m/%Y') if spot else '',
        'asian_option_average':   asian_label,
        '_deal':   deal.get('Deal', '') or '',
        '_client': deal.get('Client', '') or '',
        'status':  'New',
        'maker':   '',
        'checker': '',
    }

    ref = td or datetime.now()
    dir_path = os.path.join(INTRAG_OPT_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'))
    os.makedirs(dir_path, exist_ok=True)
    fname = ref.strftime('%Y%m%d') + '_intrag_opt.json'
    file_path = os.path.join(dir_path, fname)

    with _cache_lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    entries = json.load(fh)
                if not isinstance(entries, list):
                    entries = []
            except (json.JSONDecodeError, ValueError):
                entries = []
        else:
            entries = []
        deal_id = entry['_deal']
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            # Preserve lifecycle + the once-generated random numbers on re-save.
            for k in ('status', 'maker', 'checker', 'my_number', 'cetip_number'):
                if entries[idx].get(k):
                    entry[k] = entries[idx][k]
            entries[idx] = entry
        else:
            entries.append(entry)
        _atomic_write_json(file_path, entries)
    log.info('[INTRAG %s] Saved entry deal=%r → %s', 'FXO' if is_fxo else 'OPT', deal_id, file_path)


def _maybe_save_intrag_opt(deal):
    """Save to Intrag Option when the counterparty is Banco J.P. Morgan (intragroup)."""
    cl = (deal.get('Client', '') or '').lower()
    if 'banco' in cl and 'morgan' in cl:
        try:
            _save_intrag_opt_entry(deal)
        except Exception as exc:
            log.error('[INTRAG OPT] save failed for deal=%r: %s', deal.get('Deal', ''), exc)


def _maybe_save_intrag_fxo(deal):
    """Save an Opt-FXO deal to Intrag Option (shared file) when the counterparty
    is Banco J.P. Morgan (intragroup). Same logic as opt-comm with FXO overrides."""
    cl = (deal.get('Client', '') or '').lower()
    if 'banco' in cl and 'morgan' in cl:
        try:
            _save_intrag_opt_entry(deal, is_fxo=True)
        except Exception as exc:
            log.error('[INTRAG FXO] save failed for deal=%r: %s', deal.get('Deal', ''), exc)


def _find_intrag_ndf_entry(deal_id, trade_date):
    """Locate an Intrag NDF entry by deal id (+ optional trade date to narrow the
    daily file). Returns (file_path, entries_list, idx) or (None, None, None)."""
    if not deal_id:
        return None, None, None
    ref = _parse_date_any(trade_date) if trade_date else None
    candidate_files = []
    if ref is not None:
        fp = os.path.join(
            INTRAG_NDF_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
            ref.strftime('%Y%m%d') + '_intrag_ndf.json'
        )
        if os.path.isfile(fp):
            candidate_files.append(fp)
    if not candidate_files and os.path.isdir(INTRAG_NDF_CACHE_DIR):
        for root, _, files in os.walk(INTRAG_NDF_CACHE_DIR):
            for fname in files:
                if fname.endswith('_intrag_ndf.json'):
                    candidate_files.append(os.path.join(root, fname))
    for fp in candidate_files:
        try:
            with open(fp, 'r', encoding='utf-8') as fh:
                entries = json.load(fh)
            if not isinstance(entries, list):
                continue
        except (json.JSONDecodeError, ValueError, OSError):
            continue
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            return fp, entries, idx
    return None, None, None


@blueprint.route('/api/intrag/ndf')
def api_intrag_ndf():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    date_str  = request.args.get('date', '').strip()       # YYYY-MM-DD (single day)
    date_from = request.args.get('date_from', '').strip()  # YYYY-MM-DD (range start)
    date_to   = request.args.get('date_to', '').strip()    # YYYY-MM-DD (range end)
    entries = []
    if date_from or date_to:
        # Trade Date range — load every day-file within [from, to] inclusive
        d_from = _parse_date_any(date_from)
        d_to   = _parse_date_any(date_to)
        if os.path.isdir(INTRAG_NDF_CACHE_DIR):
            for root, _, files in os.walk(INTRAG_NDF_CACHE_DIR):
                for fname in sorted(files):
                    if not fname.endswith('_intrag_ndf.json'):
                        continue
                    fdate = _parse_date_any(fname[:8])
                    if fdate is None:
                        continue
                    if d_from and fdate < d_from:
                        continue
                    if d_to and fdate > d_to:
                        continue
                    try:
                        with open(os.path.join(root, fname), 'r', encoding='utf-8') as fh:
                            data = json.load(fh)
                        if isinstance(data, list):
                            entries.extend(data)
                    except Exception as exc:
                        log.warning('[INTRAG NDF] Skip %s: %s', fname, exc)
    elif date_str:
        try:
            ref = datetime.strptime(date_str, '%Y-%m-%d')
            fname = ref.strftime('%Y%m%d') + '_intrag_ndf.json'
            fp = os.path.join(INTRAG_NDF_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'), fname)
            if os.path.isfile(fp):
                with open(fp, 'r', encoding='utf-8') as fh:
                    entries = json.load(fh)
                if not isinstance(entries, list):
                    entries = []
        except Exception as exc:
            log.warning('[INTRAG NDF] date load error date=%r: %s', date_str, exc)
    else:
        if os.path.isdir(INTRAG_NDF_CACHE_DIR):
            for root, _, files in os.walk(INTRAG_NDF_CACHE_DIR):
                for fname in sorted(files):
                    if not fname.endswith('_intrag_ndf.json'):
                        continue
                    fp = os.path.join(root, fname)
                    try:
                        with open(fp, 'r', encoding='utf-8') as fh:
                            data = json.load(fh)
                        if isinstance(data, list):
                            entries.extend(data)
                    except Exception as exc:
                        log.warning('[INTRAG NDF] Skip %s: %s', fp, exc)
    return jsonify({'success': True, 'entries': entries})


@blueprint.route('/api/intrag/option')
def api_intrag_option():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    date_str  = request.args.get('date', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to   = request.args.get('date_to', '').strip()
    suffix = '_intrag_opt.json'
    entries = []
    if date_from or date_to:
        d_from = _parse_date_any(date_from)
        d_to   = _parse_date_any(date_to)
        if os.path.isdir(INTRAG_OPT_CACHE_DIR):
            for root, _, files in os.walk(INTRAG_OPT_CACHE_DIR):
                for fname in sorted(files):
                    if not fname.endswith(suffix):
                        continue
                    fdate = _parse_date_any(fname[:8])
                    if fdate is None:
                        continue
                    if d_from and fdate < d_from:
                        continue
                    if d_to and fdate > d_to:
                        continue
                    try:
                        with open(os.path.join(root, fname), 'r', encoding='utf-8') as fh:
                            data = json.load(fh)
                        if isinstance(data, list):
                            entries.extend(data)
                    except Exception as exc:
                        log.warning('[INTRAG OPT] Skip %s: %s', fname, exc)
    elif date_str:
        try:
            ref = datetime.strptime(date_str, '%Y-%m-%d')
            fp = os.path.join(INTRAG_OPT_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
                              ref.strftime('%Y%m%d') + suffix)
            if os.path.isfile(fp):
                with open(fp, 'r', encoding='utf-8') as fh:
                    entries = json.load(fh)
                if not isinstance(entries, list):
                    entries = []
        except Exception as exc:
            log.warning('[INTRAG OPT] date load error date=%r: %s', date_str, exc)
    else:
        if os.path.isdir(INTRAG_OPT_CACHE_DIR):
            for root, _, files in os.walk(INTRAG_OPT_CACHE_DIR):
                for fname in sorted(files):
                    if not fname.endswith(suffix):
                        continue
                    try:
                        with open(os.path.join(root, fname), 'r', encoding='utf-8') as fh:
                            data = json.load(fh)
                        if isinstance(data, list):
                            entries.extend(data)
                    except Exception as exc:
                        log.warning('[INTRAG OPT] Skip %s: %s', fname, exc)
    return jsonify({'success': True, 'entries': entries})


def _find_intrag_opt_entry(deal_id, trade_date):
    """Locate an Intrag Option entry by deal id (+ optional trade date)."""
    if not deal_id:
        return None, None, None
    ref = _parse_date_any(trade_date) if trade_date else None
    candidate_files = []
    if ref is not None:
        fp = os.path.join(INTRAG_OPT_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
                          ref.strftime('%Y%m%d') + '_intrag_opt.json')
        if os.path.isfile(fp):
            candidate_files.append(fp)
    if not candidate_files and os.path.isdir(INTRAG_OPT_CACHE_DIR):
        for root, _, files in os.walk(INTRAG_OPT_CACHE_DIR):
            for fname in files:
                if fname.endswith('_intrag_opt.json'):
                    candidate_files.append(os.path.join(root, fname))
    for fp in candidate_files:
        try:
            with open(fp, 'r', encoding='utf-8') as fh:
                entries = json.load(fh)
            if not isinstance(entries, list):
                continue
        except (json.JSONDecodeError, ValueError, OSError):
            continue
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            return fp, entries, idx
    return None, None, None


@blueprint.route('/api/intrag/option/send-file', methods=['POST'])
def api_intrag_option_send_file():
    """Generate the Intrag Option .txt file(s) from the selected rows and flip
    New/Approved → Sent. Same standard folder as NDF; file Intrag-Option-YYYYMMDD.txt.

    Body: { "items": [ { "deal_id": str, "cells": [...38...] } ] }. Rows are
    grouped by Registration Date (data col index 3) — one file per date."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    payload = request.get_json(silent=True) or {}
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        rows = payload.get('rows')
        if not isinstance(rows, list) or not rows:
            return jsonify({'success': False, 'message': 'No rows provided'}), 400
        items = [{'deal_id': '', 'cells': r} for r in rows if isinstance(r, list)]

    REG_DATE_IDX = 3   # Registration Date within the 38 data columns
    SENDABLE = {'New', 'Approved'}

    groups = {}
    sent_ids = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cells = ['' if c is None else str(c) for c in (it.get('cells') or [])]
        if not cells:
            continue
        td_raw = cells[REG_DATE_IDX] if len(cells) > REG_DATE_IDX else ''
        ref = _parse_date_any(td_raw) or datetime.now()
        groups.setdefault(ref.strftime('%Y%m%d'), {'ref': ref, 'rows': []})['rows'].append(cells)
        if it.get('deal_id'):
            sent_ids.append((it['deal_id'], td_raw))

    if not groups:
        return jsonify({'success': False, 'message': 'No valid rows provided'}), 400

    written = []
    try:
        with _cache_lock:
            for key, grp in groups.items():
                ref = grp['ref']
                month_folder = ref.strftime('%m') + '. ' + _EN_MONTH_NAMES[ref.month - 1]
                dir_path = os.path.join(INTRAG_NDF_SEND_DIR, ref.strftime('%Y'), month_folder, ref.strftime('%d'))
                os.makedirs(dir_path, exist_ok=True)
                base = 'Intrag-Option-' + key
                candidate = base + '.txt'
                n = 0
                while os.path.exists(os.path.join(dir_path, candidate)):
                    n += 1
                    candidate = base + ' (' + str(n) + ').txt'
                file_path = os.path.join(dir_path, candidate)
                with open(file_path, 'w', encoding='utf-8') as fh:
                    fh.write('\n'.join(';'.join(r) for r in grp['rows']))
                written.append(file_path)
                log.info('[INTRAG OPT] Wrote send file %s (%d row(s))', file_path, len(grp['rows']))

            for deal_id, td_raw in sent_ids:
                fp, entries, idx = _find_intrag_opt_entry(deal_id, td_raw)
                if idx is None:
                    continue
                if (entries[idx].get('status') or 'New') in SENDABLE:
                    entries[idx]['status'] = 'Sent'
                    _atomic_write_json(fp, entries)
    except Exception as exc:
        log.error('[INTRAG OPT] send-file failed: %s', exc)
        return jsonify({'success': False, 'message': 'File generation failed: ' + str(exc)}), 500

    return jsonify({'success': True, 'files': written, 'count': len(items)})


@blueprint.route('/api/intrag/option/edit', methods=['POST'])
def api_intrag_option_edit():
    """Row-level edit on an Intrag Option entry → status 'Pending', records maker."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    fields     = payload.get('fields') or {}
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400
    with _cache_lock:
        fp, entries, idx = _find_intrag_opt_entry(deal_id, trade_date)
        if idx is None:
            return jsonify({'success': False, 'message': 'Entry not found'}), 404
        if isinstance(fields, dict):
            for k, v in fields.items():
                if k in entries[idx] and k not in ('_deal', '_client', 'status', 'maker', 'checker'):
                    entries[idx][k] = v
        entries[idx]['status']  = 'Pending'
        entries[idx]['maker']   = session.get('user_sid', '')
        entries[idx]['checker'] = ''
        _atomic_write_json(fp, entries)
    return jsonify({'success': True, 'status': 'Pending'})


@blueprint.route('/api/intrag/option/approve', methods=['POST'])
def api_intrag_option_approve():
    """Move an Intrag Option entry Pending → Approved (maker ≠ checker)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400
    user_sid = session.get('user_sid', '')
    with _cache_lock:
        fp, entries, idx = _find_intrag_opt_entry(deal_id, trade_date)
        if idx is None:
            return jsonify({'success': False, 'message': 'Entry not found'}), 404
        if (entries[idx].get('status') or '') != 'Pending':
            return jsonify({'success': False, 'message': 'Only Pending entries can be approved.'}), 400
        if entries[idx].get('maker') and entries[idx]['maker'] == user_sid:
            return jsonify({'success': False,
                            'message': 'Maker cannot approve their own change — a different user must check it.'}), 403
        entries[idx]['status']  = 'Approved'
        entries[idx]['checker'] = user_sid
        _atomic_write_json(fp, entries)
    return jsonify({'success': True, 'status': 'Approved'})


@blueprint.route('/api/intrag/ndf/send-file', methods=['POST'])
def api_intrag_ndf_send_file():
    """Generate the Intrag NDF .txt file(s) from the selected table rows.

    Body: { "rows": [ [col0, col1, ... col29], ... ] } — the 30 data columns,
    in NDF_COLS order. Rows are grouped by their Trade Date (data col index 10)
    so each file lands in its own date folder:

        I:\\Confirmation\\Derivativos\\OTC Tracker\\Intrag\\YYYY\\mm. Mmmm\\dd
        (e.g. 2026\\06. June\\22)

    Each file is named Intrag-NDF-YYYYMMDD.txt; if a file already exists it is
    NOT overwritten — a copy with " (1)", " (2)", ... is created instead. Each
    selected row becomes one line; columns are separated by ';'. A single-row
    (row-level) send therefore produces a file with one line.
    """
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    payload = request.get_json(silent=True) or {}
    # New format: items = [{ "deal_id": str, "cells": [...30...] }, ...]
    # Legacy format: rows = [[...30...], ...] (no status tracking).
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        rows = payload.get('rows')
        if not isinstance(rows, list) or not rows:
            return jsonify({'success': False, 'message': 'No rows provided'}), 400
        items = [{'deal_id': '', 'cells': r} for r in rows if isinstance(r, list)]

    TRADE_DATE_IDX = 10  # index of Trade Date within the 30 data columns
    SENDABLE = {'New', 'Approved'}

    # Group rows by Trade Date → one file per distinct trade date. For the common
    # case (all rows share a trade date) this yields a single file.
    groups = {}
    sent_ids = []   # (deal_id, trade_date) pairs eligible to flip to 'Sent'
    for it in items:
        if not isinstance(it, dict):
            continue
        cells = ['' if c is None else str(c) for c in (it.get('cells') or [])]
        if not cells:
            continue
        td_raw = cells[TRADE_DATE_IDX] if len(cells) > TRADE_DATE_IDX else ''
        ref = _parse_date_any(td_raw) or datetime.now()
        key = ref.strftime('%Y%m%d')
        groups.setdefault(key, {'ref': ref, 'rows': []})['rows'].append(cells)
        if it.get('deal_id'):
            sent_ids.append((it['deal_id'], td_raw))

    if not groups:
        return jsonify({'success': False, 'message': 'No valid rows provided'}), 400

    written = []
    try:
        with _cache_lock:
            for key, grp in groups.items():
                ref = grp['ref']
                month_folder = ref.strftime('%m') + '. ' + _EN_MONTH_NAMES[ref.month - 1]
                dir_path = os.path.join(
                    INTRAG_NDF_SEND_DIR, ref.strftime('%Y'), month_folder, ref.strftime('%d')
                )
                os.makedirs(dir_path, exist_ok=True)

                base = 'Intrag-NDF-' + key
                candidate = base + '.txt'
                n = 0
                while os.path.exists(os.path.join(dir_path, candidate)):
                    n += 1
                    candidate = base + ' (' + str(n) + ').txt'
                file_path = os.path.join(dir_path, candidate)

                content = '\n'.join(';'.join(r) for r in grp['rows'])
                with open(file_path, 'w', encoding='utf-8') as fh:
                    fh.write(content)
                written.append(file_path)
                log.info('[INTRAG NDF] Wrote send file %s (%d row(s))', file_path, len(grp['rows']))

            # Flip status New/Approved → Sent for every persisted entry sent.
            for deal_id, td_raw in sent_ids:
                fp, entries, idx = _find_intrag_ndf_entry(deal_id, td_raw)
                if idx is None:
                    continue
                if (entries[idx].get('status') or 'New') in SENDABLE:
                    entries[idx]['status'] = 'Sent'
                    _atomic_write_json(fp, entries)
    except Exception as exc:
        log.error('[INTRAG NDF] send-file failed: %s', exc)
        return jsonify({'success': False, 'message': 'File generation failed: ' + str(exc)}), 500

    return jsonify({'success': True, 'files': written, 'count': len(items)})


@blueprint.route('/api/intrag/ndf/edit', methods=['POST'])
def api_intrag_ndf_edit():
    """Persist a row-level edit on an Intrag NDF entry → status becomes 'Pending'
    and the editing user is recorded as the maker (4-eyes control)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    fields     = payload.get('fields') or {}
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400

    with _cache_lock:
        fp, entries, idx = _find_intrag_ndf_entry(deal_id, trade_date)
        if idx is None:
            return jsonify({'success': False, 'message': 'Entry not found'}), 404
        if isinstance(fields, dict):
            for k, v in fields.items():
                if k in entries[idx] and k not in ('_deal', '_client', 'status', 'maker', 'checker'):
                    entries[idx][k] = v
        entries[idx]['status']  = 'Pending'
        entries[idx]['maker']   = session.get('user_sid', '')
        entries[idx]['checker'] = ''
        _atomic_write_json(fp, entries)

    return jsonify({'success': True, 'status': 'Pending'})


@blueprint.route('/api/intrag/ndf/approve', methods=['POST'])
def api_intrag_ndf_approve():
    """Move an Intrag NDF entry Pending → Approved. Enforces maker ≠ checker:
    the user who made the edit cannot approve their own change."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400

    user_sid = session.get('user_sid', '')
    with _cache_lock:
        fp, entries, idx = _find_intrag_ndf_entry(deal_id, trade_date)
        if idx is None:
            return jsonify({'success': False, 'message': 'Entry not found'}), 404
        if (entries[idx].get('status') or '') != 'Pending':
            return jsonify({'success': False, 'message': 'Only Pending entries can be approved.'}), 400
        if entries[idx].get('maker') and entries[idx]['maker'] == user_sid:
            return jsonify({'success': False,
                            'message': 'Maker cannot approve their own change — a different user must check it.'}), 403
        entries[idx]['status']  = 'Approved'
        entries[idx]['checker'] = user_sid
        _atomic_write_json(fp, entries)

    return jsonify({'success': True, 'status': 'Approved'})


# ── Intrag ID mapping (Return-folder export CSV → fill each entry's intrag_id) ──
# The Return folder holds a single Boletas CSV (Boletas.csv / Boletas(1).csv / …) with
# ALL operations and NO header — match by row content, not column names:
#   • Option: col C (idx 2) == 'OPCAO'                → col I (idx 8) = B3 ID, col A (idx 0) = Intrag ID
#   • NDF:    col B (idx 1) == 'NDF - TERMO MERCADORIA'→ col C (idx 2) = B3 ID, col A (idx 0) = Intrag ID
def _intrag_b3_key(v):
    """B3 ID match key — stripped, leading zeros dropped (both sides)."""
    s = str(v or '').strip()
    return s.lstrip('0') or s


def _intrag_find_export_csv():
    """Most recent Boletas*.csv in the Return folder, or None."""
    try:
        cands = [os.path.join(RETURN_PATH, fn) for fn in os.listdir(RETURN_PATH)
                 if fn.lower().startswith('boletas') and fn.lower().endswith('.csv')]
    except OSError:
        return None
    cands = [p for p in cands if os.path.isfile(p)]
    return max(cands, key=lambda p: os.path.getmtime(p)) if cands else None


def _intrag_build_b3_map(csv_path, match_col, match_val, b3_col):
    """Parse the Boletas CSV (no header) → {b3_key → Intrag ID (col A)} for rows whose
    `match_col` equals `match_val`."""
    import csv as _csv
    out = {}
    with open(csv_path, 'r', encoding='latin-1', newline='') as fh:
        sample = fh.read(4096); fh.seek(0)
        delim = ';' if sample.count(';') > sample.count(',') else ','
        for row in _csv.reader(fh, delimiter=delim):
            if len(row) <= max(match_col, b3_col):
                continue
            if str(row[match_col]).strip().upper() != match_val:
                continue
            b3, intrag_id = _intrag_b3_key(row[b3_col]), str(row[0]).strip()
            if b3 and intrag_id:
                out.setdefault(b3, intrag_id)
    return out


def _intrag_run_mapping(deals, match_col, match_val, b3_col, finder):
    """Map each requested deal's B3 ID → Intrag ID via the export CSV, persist the
    intrag_id onto the matching JSON entry (loaded rows only). Returns (results, err)."""
    csv_path = _intrag_find_export_csv()
    if not csv_path:
        return None, 'No Boletas CSV found in the Return folder.'
    try:
        b3map = _intrag_build_b3_map(csv_path, match_col, match_val, b3_col)
    except Exception:
        log.error('[intrag-map] CSV parse failed:\n%s', traceback.format_exc())
        return None, 'Failed to read the Boletas CSV.'
    results = []
    with _cache_lock:
        for d in (deals or []):
            did = str(d.get('id') or '').strip()
            b3  = _intrag_b3_key(d.get('b3_id'))
            if not did or not b3 or b3 not in b3map:
                continue
            intrag_id = b3map[b3]
            fp, entries, idx = finder(did, None)
            if idx is None:
                results.append({'id': did, 'intrag_id': intrag_id, 'status': 'Error'})
                continue
            entries[idx]['intrag_id'] = intrag_id
            entries[idx]['status']    = 'Success'          # mapped → Success
            try:
                _atomic_write_json(fp, entries)
            except Exception:
                log.error('[intrag-map] save failed %s:\n%s', fp, traceback.format_exc())
                results.append({'id': did, 'intrag_id': intrag_id, 'status': 'Error'})
                continue
            results.append({'id': did, 'intrag_id': intrag_id, 'status': 'Success'})
    return results, None


@blueprint.route('/api/intrag/ndf/mapping-intrag-id', methods=['POST'])
def api_intrag_ndf_mapping_intrag_id():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    results, err = _intrag_run_mapping(deals, 1, 'NDF - TERMO MERCADORIA', 2, _find_intrag_ndf_entry)
    if results is None:
        return jsonify({'ok': False, 'error': err}), 400
    return jsonify({'ok': True, 'results': results})


@blueprint.route('/api/intrag/option/mapping-intrag-id', methods=['POST'])
def api_intrag_option_mapping_intrag_id():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    results, err = _intrag_run_mapping(deals, 2, 'OPCAO', 8, _find_intrag_opt_entry)
    if results is None:
        return jsonify({'ok': False, 'error': err}), 400
    return jsonify({'ok': True, 'results': results})


@blueprint.route('/api/new-deals/ndf-commodities/cache', methods=['POST'])
def api_ndf_save_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    trade_date_raw = data.get('TradeDate', '')
    try:
        ref_date = datetime.strptime(trade_date_raw, '%d/%m/%Y')
    except (ValueError, TypeError):
        ref_date = datetime.now()

    dir_path = os.path.join(NDF_COMM_CACHE_DIR, ref_date.strftime('%Y'), ref_date.strftime('%m'))
    os.makedirs(dir_path, exist_ok=True)

    fname = ref_date.strftime('%Y%m%d') + '_ndfcomm.json'
    file_path = os.path.join(dir_path, fname)

    with _cache_lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
            except (json.JSONDecodeError, ValueError):
                deals = []
        else:
            deals = []

        deal_name   = data.get('Deal', '').strip()
        client_name = data.get('Client', '').strip()
        existing_idx = next((i for i, d in enumerate(deals)
                             if deal_name
                             and d.get('Deal', '').strip() == deal_name
                             and d.get('Client', '').strip() == client_name), None)
        if existing_idx is not None:
            deals[existing_idx] = data
        else:
            deals.append(data)

        _atomic_write_json(file_path, deals)

    # When used as the manual-edit fallback (PATCH 404 → upsert), ?notify=1 makes
    # the row-level edit produce the same bell notification a PATCH would.
    if request.args.get('notify') and deal_name:
        _create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Deal Updated', 'NDF Comm',
            deal_name + (' / ' + client_name if client_name else '') + _nd_token(data.get('TradeDate')))

    return jsonify({"success": True, "deal": data.get('Deal', '')})


@blueprint.route('/api/new-deals/ndf-commodities/cache/search', methods=['POST'])
def api_ndf_search_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    body = request.get_json(silent=True) or {}
    filters = body.get('filters', [])

    matched = []
    for root, _dirs, files in os.walk(NDF_COMM_CACHE_DIR):
        for fname in sorted(files):
            if not fname.endswith('_ndfcomm.json'):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
                for deal in deals:
                    if _deal_matches(deal, filters):
                        matched.append(deal)
            except Exception:
                continue

    return jsonify({"success": True, "deals": matched})


def _find_ndf_deal_in_cache(deal_name, client_name=None):
    """Search all YYYYMMDD_ndfcomm.json files for a deal by Deal + Client.
    Returns (file_path, list_index) or (None, None)."""
    files_scanned     = 0
    deals_scanned     = 0
    deal_name_matches = []   # where Deal matched but Client didn't
    all_names_seen    = []   # sample of (fname, deal_name, client) for every deal scanned

    if not os.path.isdir(NDF_COMM_CACHE_DIR):
        log.error("[_find_ndf] CACHE DIR MISSING: %s", NDF_COMM_CACHE_DIR)
        return None, None

    for root, _dirs, files in os.walk(NDF_COMM_CACHE_DIR):
        for fname in sorted(files):
            if not fname.endswith('_ndfcomm.json'):
                continue
            fpath = os.path.join(root, fname)
            files_scanned += 1
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
                for i, deal in enumerate(deals):
                    deals_scanned += 1
                    d_name   = deal.get('Deal', '')
                    d_client = deal.get('Client', '')
                    all_names_seen.append((fname, d_name, d_client))
                    # Trim-tolerant match: a stray leading/trailing space in the
                    # cache or in the request must not cause a phantom 404.
                    if (d_name or '').strip() == (deal_name or '').strip():
                        if client_name is None or (d_client or '').strip() == (client_name or '').strip():
                            log.debug("[_find_ndf] FOUND %r client=%r → %s[%d]",
                                      deal_name, client_name, fname, i)
                            return fpath, i
                        else:
                            deal_name_matches.append({
                                'file': fname, 'idx': i,
                                'stored_client': repr(d_client),
                                'wanted_client': repr(client_name)
                            })
            except Exception:
                log.warning("[_find_ndf] Error reading %s: %s", fpath, traceback.format_exc())
                continue

    # ── Not found — emit targeted diagnosis ──────────────────────────────
    if deal_name_matches:
        # Deal name exists in cache but client field doesn't match
        log.warning(
            "[_find_ndf] CLIENT MISMATCH for deal=%r  wanted_client=%r\n"
            "  Matches by name (stored_client vs wanted_client): %s",
            deal_name, repr(client_name), deal_name_matches
        )
    elif files_scanned == 0:
        # Directory exists but contains no _ndfcomm.json files
        try:
            tree = []
            for root2, _dirs2, files2 in os.walk(NDF_COMM_CACHE_DIR):
                level = root2.replace(NDF_COMM_CACHE_DIR, '').count(os.sep)
                indent = '  ' * level
                tree.append(f"{indent}{os.path.basename(root2)}/")
                for f2 in files2[:5]:
                    tree.append(f"{'  ' * (level+1)}{f2}")
            log.warning(
                "[_find_ndf] NO _ndfcomm.json FILES FOUND in %s\n  Directory tree:\n%s",
                NDF_COMM_CACHE_DIR, '\n'.join(tree) or '  (empty)'
            )
        except Exception:
            log.warning("[_find_ndf] NO _ndfcomm.json FILES FOUND in %s", NDF_COMM_CACHE_DIR)
    else:
        # Deal name itself was never found in any file
        # Show every (file, stored_Deal, stored_Client) so the mismatch is obvious
        log.warning(
            "[_find_ndf] DEAL NAME NOT MATCHED: wanted=%r (repr=%r)\n"
            "  Scanned %d file(s), %d deal(s). All stored (Deal, Client) pairs:\n%s",
            deal_name, repr(deal_name),
            files_scanned, deals_scanned,
            '\n'.join(
                f"    [{fn}] Deal={repr(dn)}  Client={repr(dc)}"
                for fn, dn, dc in all_names_seen
            ) or '    (none)'
        )

    return None, None


@blueprint.route('/api/new-deals/ndf-commodities/cache/<deal_id>', methods=['PATCH'])
def api_ndf_update_deal_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    client  = request.args.get('client')
    updates = request.get_json(silent=True)
    log.info("[NDF PATCH] deal_id=%r client=%r updates=%s", deal_id, client, updates)

    if not updates:
        log.warning("[NDF PATCH] No JSON body received")
        return jsonify({"success": False, "message": "No data provided"}), 400

    file_path, idx_found = _find_ndf_deal_in_cache(deal_id, client)
    log.info("[NDF PATCH] _find_ndf_deal_in_cache → file=%s idx=%s", file_path, idx_found)

    if file_path is None:
        # _find_ndf_deal_in_cache already emitted the detailed diagnosis (repr diffs, client mismatch list)
        log.warning("[NDF PATCH] 404 — deal_id=%r (repr=%r) client=%r (repr=%r)",
                    deal_id, repr(deal_id), client, repr(client))
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            log.error("[NDF PATCH] JSON parse error in file=%s", file_path)
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        log.debug("[NDF PATCH] idx in loaded file=%s", idx)
        if idx is None:
            log.warning("[NDF PATCH] 404 — deal found in file scan but not after reload. deal_id=%r client=%r file=%s", deal_id, client, file_path)
            return jsonify({"success": False, "message": "Deal not found"}), 404
        prev_status = deals[idx].get('Status', '?')
        deals[idx].update(updates)
        log.info("[NDF PATCH] Updated deal[%d] %r: Status %r→%r updates=%s",
                 idx, deal_id, prev_status, deals[idx].get('Status', '?'), updates)
        _atomic_write_json(file_path, deals)
        updated_deal = deals[idx].copy()

    # Save to Intrag when Status→Success and client is BANCO JP MORGAN
    new_status = updated_deal.get('Status', '')
    cl_lower = (updated_deal.get('Client', '') or '').lower()
    if new_status == 'Success' and 'banco' in cl_lower and 'morgan' in cl_lower:
        try:
            _save_intrag_ndf_entry(updated_deal)
        except Exception as exc:
            log.error('[NDF PATCH] Failed to save Intrag entry for deal=%r: %s', deal_id, exc)

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            # The 'Sent' transition is already announced by the 'Sent to B3'
            # notification emitted from send-conecta — skip the redundant
            # 'Status Updated' entry so the bell shows a single item per send.
            if str(_fields.get('Status', '')) != 'Sent':
                _create_notification(
                    session.get('user_sid', ''), session.get('user_name', ''),
                    'Status Updated', 'NDF Comm',
                    deal_id + ' → ' + str(_fields.get('Status', '')) + _nd_token(updated_deal.get('TradeDate'))
                )
        else:
            _create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Deal Updated', 'NDF Comm',
                deal_id + ' (' + ', '.join(_fields.keys()) + ')' + _nd_token(updated_deal.get('TradeDate'))
            )
    return jsonify({"success": True})


@blueprint.route('/api/new-deals/ndf-commodities/cache/<deal_id>', methods=['DELETE'])
def api_ndf_delete_deal_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    client = request.args.get('client')
    file_path, _ = _find_ndf_deal_in_cache(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        removed = deals.pop(idx)
        _atomic_write_json(file_path, deals)

    _create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'Deal Deleted', 'NDF Comm', deal_id + _nd_token((removed or {}).get('TradeDate'))
    )
    return jsonify({"success": True})


@blueprint.route('/api/new-deals/ndf-commodities/cache/bulk-delete', methods=['POST'])
def api_ndf_bulk_delete_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data  = request.get_json(silent=True)
    pairs = data.get('pairs', []) if data else []
    log.info("[NDF BULK-DELETE] Received %d pair(s): %s", len(pairs), pairs)

    if not pairs:
        return jsonify({"success": False, "message": "No pairs provided"}), 400

    pair_set = {(p.get('deal', ''), p.get('client', '')) for p in pairs}
    log.info("[NDF BULK-DELETE] Unique pairs after dedup: %s", list(pair_set))

    # Check for suspicious empty keys
    empty_keys = [(d, c) for d, c in pair_set if not d or not c]
    if empty_keys:
        log.warning("[NDF BULK-DELETE] WARNING — pairs with empty deal or client: %s", empty_keys)

    # Group pairs by their source file (search outside the lock — read-only scan)
    file_pairs = {}
    for deal_name, client_name in pair_set:
        fp, idx_found = _find_ndf_deal_in_cache(deal_name, client_name)
        log.debug("[NDF BULK-DELETE] _find deal=%r client=%r → file=%s idx=%s",
                  deal_name, client_name, fp, idx_found)
        if fp:
            file_pairs.setdefault(fp, set()).add((deal_name, client_name))
        else:
            log.warning("[NDF BULK-DELETE] NOT FOUND: deal=%r (repr=%r) client=%r (repr=%r)",
                        deal_name, repr(deal_name), client_name, repr(client_name))

    log.info("[NDF BULK-DELETE] Files to mutate: %s", list(file_pairs.keys()))

    deleted = 0
    for fp, pairs_in_file in file_pairs.items():
        with _cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                log.error("[NDF BULK-DELETE] JSON parse error in %s", fp)
                deals = []
            if not isinstance(deals, list):
                deals = [deals]
            before = len(deals)
            log.info("[NDF BULK-DELETE] File %s has %d deals BEFORE delete. Removing pairs: %s",
                     os.path.basename(fp), before, list(pairs_in_file))
            deals  = [d for d in deals if (d.get('Deal', ''), d.get('Client', '')) not in pairs_in_file]
            after  = len(deals)
            deleted += before - after
            log.info("[NDF BULK-DELETE] File %s: %d → %d deals (removed %d)",
                     os.path.basename(fp), before, after, before - after)
            _atomic_write_json(fp, deals)

    not_found = len(pair_set) - deleted
    log.info("[NDF BULK-DELETE] Done. deleted=%d not_found=%d", deleted, not_found)
    if deleted > 0:
        _create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Bulk Delete', 'NDF Comm',
            str(deleted) + ' deal' + ('s' if deleted != 1 else '') + ' deleted'
        )
    return jsonify({"success": True, "deleted": deleted, "not_found": not_found})


@blueprint.route('/api/new-deals/ndf-commodities/cache/bulk-patch', methods=['POST'])
def api_ndf_bulk_patch_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data    = request.get_json(silent=True)
    patches = data.get('patches', []) if data else []
    log.info("[NDF BULK-PATCH] Received %d patch(es)", len(patches))

    if not patches:
        return jsonify({"success": False, "message": "No patches provided"}), 400

    # Group by source file (outside lock — read-only scan)
    file_patches = {}
    for p in patches:
        deal_id = p.get('deal_id', '')
        client  = p.get('client', '')
        updates = p.get('updates', {})
        if not deal_id or not updates:
            continue
        fp, _ = _find_ndf_deal_in_cache(deal_id, client)
        if fp:
            file_patches.setdefault(fp, []).append((deal_id, client, updates))
        else:
            log.warning("[NDF BULK-PATCH] NOT FOUND: deal=%r client=%r", deal_id, client)

    updated = 0
    for fp, file_ops in file_patches.items():
        with _cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            for deal_id, client, updates in file_ops:
                idx = next((i for i, d in enumerate(deals)
                            if d.get('Deal') == deal_id and (not client or d.get('Client', '') == client)), None)
                if idx is not None:
                    deals[idx].update(updates)
                    updated += 1
                    log.debug("[NDF BULK-PATCH] Updated deal=%r client=%r", deal_id, client)
            _atomic_write_json(fp, deals)

    log.info("[NDF BULK-PATCH] Done. updated=%d", updated)
    if updated > 0:
        _create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Bulk Update', 'NDF Comm',
            str(updated) + ' deal' + ('s' if updated != 1 else '') + ' updated'
        )
    return jsonify({"success": True, "updated": updated})


@blueprint.route('/api/new-deals/ndf-commodities/send-conecta', methods=['POST'])
def api_ndf_send_conecta():
    from decimal import Decimal
    import datetime as _dt

    data  = request.get_json(silent=True) or {}
    deals = data.get('deals', [])
    if not deals:
        return jsonify({'ok': False, 'error': 'No deals provided'}), 400

    today = _dt.datetime.today().strftime('%Y%m%d')

    def _sh(v):
        return re.sub(r'<[^>]+>', '', str(v or '')).strip()

    def _date(val):
        val = _sh(val)
        if not val:
            return ''
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                return _dt.datetime.strptime(val, fmt).strftime('%Y%m%d')
            except ValueError:
                continue
        return ''

    def _num(val, div100=False):
        val = _sh(str(val or ''))
        if not val:
            return ''
        clean = val.replace(',', '')
        try:
            d = Decimal(clean)
            if div100:
                d = d / Decimal('100')
            s = format(d.normalize(), 'f')
            return s.replace('.', ',')
        except Exception:
            return clean.replace('.', ',')

    def _cpty(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '00041007'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '73760009'
        return '73760102'

    def _taxid(client, taxid):
        c = client.upper()
        if 'LAWTON' in c or 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return ''
        return re.sub(r'[.\-/]', '', _sh(taxid))

    def _pos(s, width, align='left', fill=' '):
        s = str(s or '')
        if len(s) > width:
            s = s[:width]
        return s.rjust(width, fill) if align == 'right' else s.ljust(width, fill)

    def _pos_num(val, int_digits, dec_digits, div100=False):
        """Fixed-width positional numeric: int_digits integer + dec_digits decimal, no separator."""
        v = _sh(str(val or ''))
        if not v:
            return '0' * (int_digits + dec_digits)
        try:
            d = Decimal(v.replace(',', ''))
            if div100:
                d = d / Decimal('100')
            d = abs(d)
            int_part = int(d)
            frac_int = int(((d - int_part) * Decimal(10 ** dec_digits)).to_integral_value())
            return str(int_part).zfill(int_digits) + str(frac_int).zfill(dec_digits)
        except Exception:
            return '0' * (int_digits + dec_digits)

    FIXED_UNDERLYINGS = {'NACX0005', 'PTS005', 'PTS002', 'PTS006', 'PTS003', 'PMTCLAUS'}

    import json as _json
    lawton_lines = []
    banco_lines  = []
    lawton_count = 0
    banco_count  = 0

    for deal in deals:
        client           = _sh(deal.get('Client', ''))
        taxid            = _sh(deal.get('TaxID', ''))
        direction        = _sh(deal.get('Direction', ''))
        trade_type       = _sh(deal.get('TradeType', '')).upper()
        strike_ccy       = _sh(deal.get('StrikeCurrency', '')).upper()
        underlying       = _sh(deal.get('UnderlyingAsset', '')).upper()
        instrument       = _sh(deal.get('Instrument', '')).upper()
        _cu              = client.upper()
        is_jpmorgan      = bool(re.search(r'J\.?P\.?\s*MORGAN', _cu))
        part_account     = '00041007' if is_jpmorgan else '73760009'
        fx_holiday_sched = _sh(deal.get('FXHolidaySchedule', ''))
        qic              = _sh(deal.get('QuotedInCents', 'NO')).upper() == 'YES'
        asian            = trade_type == 'ASIAN'
        vanilla          = trade_type == 'VANILLA'
        brl              = strike_ccy == 'BRL'
        is_tas           = instrument.startswith('TAS')
        is_fixed         = underlying in FIXED_UNDERLYINGS

        dir_code   = '0' if direction.upper() == 'BUY' else '1'
        fix_start  = _date(deal.get('FixingStartDate', ''))
        fix_end    = _date(deal.get('FixingEndDate', ''))
        fxconv     = _date(deal.get('FXConvDate', ''))
        trade_date = _date(deal.get('TradeDate', ''))
        settl_date = _date(deal.get('SettlementDate', ''))
        deal_id    = _sh(deal.get('Deal', ''))
        notional   = _sh(deal.get('TotalNotional', ''))
        strike_str = _pos_num(deal.get('Strike', ''), 12, 8, div100=(qic and not brl))

        # Notional: integer right-justified to 14 chars + '00' = 16 chars total
        try:
            qty_int = int(round(float(notional.replace(',', ''))))
            qty_str = str(qty_int).rjust(14, '0') + '00'
        except Exception:
            qty_str = '0' * 16

        tipo_cotacao = 'F' if is_fixed else 'A'
        fonte_info   = '340' if is_fixed else '358'

        fix_single = fix_start if (fix_start and fix_start == fix_end) else ''
        tipo_media = 'N' if fix_single else 'A'

        _deal_holidays = set()
        if not vanilla and fx_holiday_sched:
            _sched_file = fx_holiday_sched.replace('-', '_')
            holiday_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                '..', 'static', 'data', f'{_sched_file}.json'
            )
            try:
                with open(holiday_path, encoding='utf-8') as _hf:
                    _raw = _json.load(_hf)
                _deal_holidays = set(
                    item['date'] if isinstance(item, dict) else item
                    for item in _raw
                )
            except Exception:
                pass

        biz_count = 0
        if not vanilla and fix_start and fix_end:
            try:
                _s = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e = _dt.datetime.strptime(fix_end,   '%Y%m%d').date()
                _cur = _s
                while _cur <= _e:
                    if _cur.weekday() < 5 and _cur.strftime('%Y-%m-%d') not in _deal_holidays:
                        biz_count += 1
                    _cur += _dt.timedelta(days=1)
            except Exception:
                pass

        if vanilla:
            biz_str = '000'
        else:
            biz_str = str(biz_count).zfill(3)
        my_number = str(random.randint(1000000000, 9999999999))

        # Positional (fixed-width, no delimiter) — TER format
        line = (
            _pos('TER  ', 5)                        +  # ID do Sistema
            _pos('1', 1)                             +  # ID Tipo de Linha
            _pos('0001', 4)                          +  # Código Operação
            _pos(my_number, 10)                      +  # Meu Número
            _pos(part_account, 8)                    +  # Lançamento do Participante
            _pos(dir_code, 1)                        +  # Papel
            _pos('', 14)                             +  # CPF/CNPJ Cliente Parte
            _pos(_cpty(client), 8)                   +  # Contraparte
            _pos(_taxid(client, taxid), 14)          +  # CPF/CNPJ Contraparte
            _pos('S', 1)                             +  # Contrato Global
            _pos('4', 20, 'right')                   +  # Classe do Ativo Subjacente
            _pos(' ' + fonte_info, 4)                +  # Fonte de Informação
            _pos('', 3)                              +  # Moeda de Referência
            _pos('', 3)                              +  # Moeda Cotada
            _pos('', 1)                              +  # Cotação para o Vencimento
            _pos(qty_str, 16)                        +  # Valor Base / Quantidade
            _pos(underlying, 10, 'right')            +  # Código do Ativo Subjacente
            _pos(strike_str, 20)                     +  # Taxa a Termo (R$/Moeda)
            _pos(fix_single, 8)                      +  # Data de Fixing do Ativo Subjacente
            _pos(trade_date, 8)                      +  # Data de Operação
            _pos(settl_date, 8)                      +  # Data de Vencimento
            _pos('', 1)                              +  # Boletim
            _pos(tipo_cotacao, 1)                    +  # Tipo de Cotação
            _pos('' if brl else fxconv, 8)           +  # Data de Fixing da Moeda
            _pos('', 1)                              +  # Cross Rate na Avaliação?
            _pos('', 1)                              +  # Fonte de Consulta
            _pos('', 8)                              +  # Tela ou Função de Consulta
            _pos('', 8)                              +  # Praça de Negociação
            _pos('', 8)                              +  # Horário de Consulta
            _pos('', 1)                              +  # Cotação Taxa de Câmbio R$/USD
            _pos('', 1)                              +  # Cotação Paridade
            _pos('', 8)                              +  # Data de Avaliação
            _pos('', 10)                             +  # Código da Paridade Cross
            _pos('', 8)                              +  # Data de Fixing da Paridade Cross
            _pos('S' if is_tas else 'N', 1)          +  # Termo a Termo
            _pos(trade_date if is_tas else '', 8)    +  # Data de Fixação
            _pos('V' if is_tas else '', 1)           +  # Forma de Atualização
            _pos('', 12)                             +  # Valor / Percentual Negociado
            _pos('', 1)                              +  # Cotação para Fixing
            _pos('N', 1)                             +  # Atualizar Valor Base?
            _pos('', 12)                             +  # Cotação Inicial
            _pos('N', 1)                             +  # Ajustar Taxa
            _pos('', 1)                              +  # Responsável pelo Ajuste da Taxa
            _pos('', 8)                              +  # Data Inicial para Ajuste da Taxa
            _pos('', 8)                              +  # Data Final para Ajuste da Taxa
            _pos('', 1)                              +  # Limites
            _pos('', 14)                             +  # Superior (Paridade)
            _pos('', 14)                             +  # Inferior (Paridade)
            _pos('', 8)                              +  # Data de Liquidação do Prêmio
            _pos('', 1)                              +  # Prêmio a ser Pago Pelo
            _pos('', 16)                             +  # Valor do Prêmio
            _pos('', 1)                              +  # Modalidade de Liquidação
            _pos('', 1)                              +  # Prêmio em Moeda Estrangeira
            _pos('', 8)                              +  # Data de Fixing da Moeda do Prêmio
            _pos('S' if brl else '', 1)              +  # Taxa a Termo em Reais
            _pos('', 280)                            +  # Observação
            _pos(deal_id, 14, 'right')               +  # Código Identificador
            _pos(tipo_media, 1)                      +  # Tipo Média Asiático
            _pos(biz_str, 3)                            # Quantidade de Datas de Verificação
        )
        dest = lawton_lines if is_jpmorgan else banco_lines
        dest.append(line)
        if is_jpmorgan:
            lawton_count += 1
        else:
            banco_count += 1

        # Asian fixing date rows (line type 2)
        if asian and fix_start and fix_end:
            try:
                _s2 = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e2 = _dt.datetime.strptime(fix_end,   '%Y%m%d').date()
                _cur2 = _s2
                while _cur2 <= _e2:
                    if _cur2.weekday() < 5 and _cur2.strftime('%Y-%m-%d') not in _deal_holidays:
                        _d  = _cur2.strftime('%Y%m%d')
                        _fx = _d if brl else ''
                        fix_line = (
                            _pos('TER  ', 5)   +  # ID do Sistema
                            _pos('2', 1)        +  # ID Tipo de Linha
                            _pos('0001', 4)     +  # Código Operação
                            _pos(_d, 8)         +  # Data de Fixing do Ativo Subjacente
                            _pos('0' * 16, 16)  +  # Quantidade de Referência
                            _pos(_fx, 8)        +  # Data de Fixing da Moeda
                            _pos('', 10)           # Padding
                        )
                        dest.append(fix_line)
                    _cur2 += _dt.timedelta(days=1)
            except Exception:
                pass

    # Headers differ by counterparty type; trailer code is 00003
    lawton_header = (_pos('TER  ', 5) + _pos('0', 1) + _pos('0001', 4) +
                     'INTRAGLAWTONFDO' + '     ' + today + '00003')
    banco_header  = (_pos('TER  ', 5) + _pos('0', 1) + _pos('0001', 4) +
                     'JPMORGANBM' + '          ' + today + '00003')

    output_dir = CONECTA_NEW_PATH
    generated  = []
    try:
        os.makedirs(output_dir, exist_ok=True)
        if lawton_lines:
            lawton_path = _unique_filepath(output_dir, 'TCO_LAWTON.txt')
            with open(lawton_path, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([lawton_header] + lawton_lines))
            generated.append({'filename': os.path.basename(lawton_path), 'count': lawton_count})
        if banco_lines:
            banco_path = _unique_filepath(output_dir, 'TCO_BANCO.txt')
            with open(banco_path, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([banco_header] + banco_lines))
            generated.append({'filename': os.path.basename(banco_path), 'count': banco_count})
        total = lawton_count + banco_count
        primary = generated[0]['filename'] if generated else ''
        if total > 0:
            _create_notification(session.get('user_sid', ''), session.get('user_name', ''), 'Sent to B3', 'NDF Comm', str(total) + ' deal' + ('' if total == 1 else 's') + ' sent')
        return jsonify({'ok': True, 'filename': primary, 'count': total, 'files': generated})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@blueprint.route('/api/new-deals/ndf-commodities/mapping-b3', methods=['POST'])
def api_ndf_mapping_b3():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    data = request.get_json(silent=True) or {}
    sent_deals = data.get('deals', [])
    if not sent_deals:
        return jsonify({'ok': True, 'results': []})

    mapping         = {}
    files_to_delete = []
    try:
        if not os.path.isdir(RETURN_PATH):
            return jsonify({'ok': False, 'error': f'Return folder not found: {RETURN_PATH}'}), 400

        for fname in os.listdir(RETURN_PATH):
            fpath = os.path.join(RETURN_PATH, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                with open(fpath, 'r', encoding='latin-1') as fh:
                    lines = fh.readlines()
                file_has_ter = False
                for line in lines[1:]:  # skip header row
                    line = line.strip()
                    if not line:
                        continue
                    # Sigla at chars 57-59 (1-based): NDF maps only 'TER' (termo) lines
                    if line[56:59] != 'TER':
                        continue
                    file_has_ter = True
                    if 'EXECUCAO OK' not in line:
                        continue
                    parts = line.split(';')
                    if len(parts) < 2:
                        continue
                    b3_id = parts[1].strip()
                    for sd in sent_deals:
                        deal_text = sd.get('Deal', '')
                        if deal_text and deal_text not in mapping and deal_text in line:
                            mapping[deal_text] = b3_id
                # Only delete return files that actually carried TER (NDF) lines
                if file_has_ter:
                    files_to_delete.append(fpath)
            except Exception:
                continue
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    results = []
    for sd in sent_deals:
        deal_text   = sd.get('Deal', '')
        client_name = sd.get('Client', '')

        if deal_text and deal_text in mapping:
            b3_id      = mapping[deal_text]
            new_status = 'Success'
            updates    = {'Status': new_status, 'B3_ID': b3_id}
        else:
            b3_id      = ''
            new_status = 'Error'
            updates    = {'Status': new_status}

        intrag_candidate = None
        if deal_text:
            file_path, idx = _find_ndf_deal_in_cache(deal_text, client_name)
            if file_path is not None:
                with _cache_lock:
                    try:
                        with open(file_path, 'r', encoding='utf-8') as fh:
                            deals_list = json.load(fh)
                        deals_list[idx].update(updates)
                        with open(file_path, 'w', encoding='utf-8') as fh:
                            json.dump(deals_list, fh, ensure_ascii=False, indent=2)
                        if new_status == 'Success':
                            intrag_candidate = deals_list[idx].copy()
                    except Exception:
                        pass

        if intrag_candidate is not None:
            cl_low = (intrag_candidate.get('Client', '') or '').lower()
            if 'banco' in cl_low and 'morgan' in cl_low:
                try:
                    _save_intrag_ndf_entry(intrag_candidate)
                except Exception as exc:
                    log.error('[MAPPING-B3] Intrag save failed for deal=%r: %s', deal_text, exc)

        results.append({
            'id':     deal_text,
            'deal':   deal_text,
            'b3_id':  b3_id,
            'status': new_status,
        })

    for fpath in files_to_delete:
        try:
            os.remove(fpath)
        except Exception:
            pass

    if results:
        _create_notification(session.get('user_sid', ''), session.get('user_name', ''), 'B3 Mapped', 'NDF Comm', str(len(results)) + ' deal' + ('' if len(results) == 1 else 's') + ' mapped')
    return jsonify({'ok': True, 'results': results})


# ==============================================================================
# API — B3 JSON CRUD (Subjacente / VCP / Domínio / RefData)
# ==============================================================================

_B3_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'static', 'data'))
_B3_FILE_MAP = {
    'subj':    'Subjacente.json',
    'vcp':     'VCP.json',
    'dominio': 'Dominio.json',
    'refdata': 'RefData.json',
}


def _b3_load(table):
    path = os.path.join(_B3_DATA_DIR, _B3_FILE_MAP[table])
    with open(path, encoding='utf-8') as fh:
        return json.load(fh), path


def _b3_save(path, records):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)


@blueprint.route('/api/fx-holiday-schedules', methods=['GET'])
def api_fx_holiday_schedules():
    _SYSTEM_FILES = {
        'Subjacente.json', 'VCP.json', 'Dominio.json', 'RefData.json',
        'datatables-rendering.json', 'datatables.json',
        'treeview-data.json', 'typeahead-data-2.json', 'typeahead.json',
    }
    try:
        schedules = []
        for fname in os.listdir(_B3_DATA_DIR):
            if fname.endswith('.json') and fname not in _SYSTEM_FILES:
                schedules.append(fname[:-5])
        schedules.sort()
        return jsonify({'ok': True, 'schedules': schedules})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


_HOLIDAY_FILE_MAP = {
    'ANBIMA':       'anbima.json',
    'BURSA':        'bursa.json',
    'CBY_AGS':      'cby_ags.json',
    'EURIBOR':      'euribor.json',
    'ICEAGS':       'iceags.json',
    'IPE':          'ipe.json',
    'LME':          'lme.json',
    'NYMEX':        'nymex.json',
    'PLATTS-ASIA':  'platts_asia.json',
    'PLATTS-EUROPE':'platts_europe.json',
    'SOFR':         'sofr.json',
}


@blueprint.route('/api/holidays/save', methods=['POST'])
def api_holidays_save():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401

    payload = request.get_json(silent=True) or {}
    calendar_name = payload.get('calendar', '').strip()
    date          = payload.get('date', '').strip()   # YYYY-MM-DD
    title         = payload.get('title', '').strip()

    if not all([calendar_name, date, title]):
        return jsonify({'ok': False, 'error': 'Missing fields'})

    filename = _HOLIDAY_FILE_MAP.get(calendar_name)
    if not filename:
        return jsonify({'ok': False, 'error': f'Unknown calendar: {calendar_name}'})

    file_path = os.path.join(_B3_DATA_DIR, filename)

    try:
        if os.path.exists(file_path):
            with open(file_path, encoding='utf-8') as f:
                holidays = json.load(f)
        else:
            holidays = []
    except (json.JSONDecodeError, IOError):
        holidays = []

    new_entry = {'date': date, 'title': title, 'calendar': calendar_name}
    if new_entry not in holidays:
        holidays.append(new_entry)
        holidays.sort(key=lambda x: x.get('date', ''))

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(holidays, f, ensure_ascii=False, indent=4)
    except IOError as e:
        return jsonify({'ok': False, 'error': str(e)})

    return jsonify({'ok': True, 'total': len(holidays)})


@blueprint.route('/api/b3/update', methods=['POST'])
def api_b3_update():
    payload = request.get_json(silent=True) or {}
    table   = payload.get('table', '')
    idx     = payload.get('idx')
    fields  = payload.get('fields', {})
    action  = payload.get('action', 'edit')   # 'edit' | 'approve'
    user    = session.get('user_sid', 'UNKNOWN')

    if table not in _B3_FILE_MAP or idx is None:
        return jsonify({'ok': False, 'error': 'bad_request'}), 400

    records, path = _b3_load(table)
    if not (0 <= int(idx) < len(records)):
        return jsonify({'ok': False, 'error': 'bad_index'}), 400

    rec = records[int(idx)]

    if action == 'approve':
        if rec.get('MAKER') == user:
            return jsonify({'ok': False, 'error': 'same_user'}), 403
        rec['CHECKER'] = user
        new_status = 'INACTIVE' if rec.get('STATUS') == 'PENDING INACTIVE' else 'ACTIVE'
        rec['STATUS']  = new_status
    elif action == 'deactivate':
        rec['STATUS']  = 'PENDING INACTIVE'
        rec['MAKER']   = user
        rec['CHECKER'] = None
        new_status     = 'PENDING INACTIVE'
    else:
        for k, v in fields.items():
            rec[k] = v
        rec['STATUS']  = 'PENDING'
        rec['MAKER']   = user
        rec['CHECKER'] = None
        new_status     = 'PENDING'

    _b3_save(path, records)
    # On checker approval of a Reference Data counterparty (→ ACTIVE), make sure
    # its Electronic Inventory folder tree exists. Best-effort, never blocks.
    if table == 'refdata' and action == 'approve' and new_status == 'ACTIVE':
        _ensure_counterparty_folders(rec.get('COUNTERPARTY', ''))
    # Reference Data shares this endpoint but is its own page — name it correctly
    # and carry SPN + counterparty so the bell deep-links to /reference-data?spn=.
    if table == 'refdata':
        page = 'Reference Data'
        spn  = str(rec.get('SPN', '') or '').strip()
        name = str(rec.get('COUNTERPARTY', '') or '').strip()
        detail = ('SPN ' + spn) if spn else 'SPN —'
        if name:
            detail += ' · ' + name
        detail += ' — ' + action + ' → ' + new_status
    else:
        page = 'Index B3'
        detail = table + ' — ' + action + ' → ' + new_status
    _create_notification(user, session.get('user_name', ''), 'Item Updated', page, detail)
    return jsonify({'ok': True, 'new_status': new_status})


@blueprint.route('/api/b3/delete', methods=['POST'])
def api_b3_delete():
    payload = request.get_json(silent=True) or {}
    table   = payload.get('table', '')
    idx     = payload.get('idx')

    if table not in _B3_FILE_MAP or idx is None:
        return jsonify({'ok': False, 'error': 'bad_request'}), 400

    records, path = _b3_load(table)
    if not (0 <= int(idx) < len(records)):
        return jsonify({'ok': False, 'error': 'bad_index'}), 400

    removed = records.pop(int(idx))
    _b3_save(path, records)
    if table == 'refdata':
        page = 'Reference Data'
        spn  = str((removed or {}).get('SPN', '') or '').strip()
        name = str((removed or {}).get('COUNTERPARTY', '') or '').strip()
        detail = ('SPN ' + spn) if spn else 'SPN —'
        if name:
            detail += ' · ' + name
    else:
        page = 'Index B3'
        detail = table
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Item Deleted', page, detail)
    return jsonify({'ok': True})


@blueprint.route('/api/b3/add', methods=['POST'])
def api_b3_add():
    payload = request.get_json(silent=True) or {}
    table   = payload.get('table', '')
    fields  = payload.get('fields', {})
    user    = session.get('user_sid', 'UNKNOWN')

    if table not in _B3_FILE_MAP:
        return jsonify({'ok': False, 'error': 'bad_request'}), 400

    records, path = _b3_load(table)
    fields['STATUS']  = 'PENDING'
    fields['MAKER']   = user
    fields['CHECKER'] = None
    records.append(fields)
    _b3_save(path, records)

    # Reference Data shares this endpoint but is its own page — name it correctly
    # and carry SPN + counterparty so the bell deep-links to /reference-data?spn=.
    if table == 'refdata':
        page = 'Reference Data'
        spn  = str(fields.get('SPN', '') or '').strip()
        name = str(fields.get('COUNTERPARTY', '') or '').strip()
        detail = ('SPN ' + spn) if spn else 'SPN —'
        if name:
            detail += ' · ' + name
        detail += ' (Pending approval)'
    else:
        page = 'Index B3'
        detail = table + ': ' + str(fields.get('TICKER', fields.get('CODE', fields.get('NAME', ''))))
    _create_notification(user, session.get('user_name', ''), 'New Item', page, detail)
    return jsonify({'ok': True, 'idx': len(records) - 1})


# ==============================================================================
# PARSE MSG EMAIL — extrai HTML de arquivo .msg do Outlook
# ==============================================================================

@blueprint.route('/api/parse-msg-html', methods=['POST'])
def api_parse_msg_html():
    f = request.files.get('file')
    if not f:
        return jsonify({'ok': False, 'error': 'no file'}), 400
    try:
        import extract_msg
        import io
        data = f.read()
        msg = extract_msg.openMsg(io.BytesIO(data))
        html_body = getattr(msg, 'htmlBody', None)
        if html_body:
            if isinstance(html_body, bytes):
                html_body = html_body.decode('utf-8', errors='replace')
            return jsonify({'ok': True, 'html': html_body})
        # Fallback to plain text body wrapped in <pre>
        body = getattr(msg, 'body', None) or ''
        if isinstance(body, bytes):
            body = body.decode('utf-8', errors='replace')
        return jsonify({'ok': True, 'html': '<pre>' + body + '</pre>'})
    except Exception as e:
        log.error('parse_msg_html error: %s', e)
        return jsonify({'ok': False, 'error': str(e)}), 500


# ==============================================================================
# SEND TO CONECTA — gera arquivo TXT para B3 Batch Conecta
# ==============================================================================

@blueprint.route('/api/new-deals/opt-commodities/send-conecta', methods=['POST'])
def api_send_conecta():
    from decimal import Decimal
    import datetime as _dt

    data  = request.get_json(silent=True) or {}
    deals = data.get('deals', [])
    if not deals:
        return jsonify({'ok': False, 'error': 'No deals provided'}), 400

    today = _dt.datetime.today().strftime('%Y%m%d')

    def _sh(v):
        return re.sub(r'<[^>]+>', '', str(v or '')).strip()

    def _date(val):
        val = _sh(val)
        if not val:
            return ''
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                return _dt.datetime.strptime(val, fmt).strftime('%Y%m%d')
            except ValueError:
                continue
        return ''

    def _num(val, div100=False):
        val = _sh(str(val or ''))
        if not val:
            return ''
        clean = val.replace(',', '')
        try:
            d = Decimal(clean)
            if div100:
                d = d / Decimal('100')
            s = format(d.normalize(), 'f')
            return s.replace('.', ',')
        except Exception:
            return clean.replace('.', ',')

    def _qty(val):
        """Integer quantity formatted as {int},00 for B3 field 13."""
        v = _sh(str(val or ''))
        if not v:
            return ''
        clean = v.replace(',', '')
        try:
            return str(int(round(float(clean)))) + ',00'
        except Exception:
            return v

    def _cli(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '73760009'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '00041007'
        return '73760009'

    def _cpty(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '00041007'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '73760009'
        return '73760102'

    def _taxid(client, taxid):
        c = client.upper()
        if 'LAWTON' in c or 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return ''
        return re.sub(r'[.\-/]', '', _sh(taxid))

    import json as _json
    deal_count = 0
    all_lines  = []

    for deal in deals:
        client     = _sh(deal.get('Client', ''))
        taxid      = _sh(deal.get('TaxID', ''))
        instrument = _sh(deal.get('Instrument', ''))
        direction  = _sh(deal.get('Direction', ''))
        trade_type        = _sh(deal.get('TradeType', ''))
        strike_ccy        = _sh(deal.get('StrikeCurrency', ''))
        fx_holiday_sched  = _sh(deal.get('FXHolidaySchedule', ''))
        qic               = _sh(deal.get('QuotedInCents', 'NO')).upper() == 'YES'
        vanilla           = trade_type.upper() == 'VANILLA'
        asian             = trade_type.upper() == 'ASIAN'
        brl               = strike_ccy.upper() == 'BRL'

        opt = 'P' if 'PUT'  in instrument.upper() else ('C' if 'CALL' in instrument.upper() else '')
        dir_code   = '2' if direction.upper() == 'SELL' else '1'
        fix_start  = _date(deal.get('FixingStartDate', ''))
        fix_end    = _date(deal.get('FixingEndDate', ''))
        fxconv     = _date(deal.get('FXConvDate', ''))

        _deal_holidays = set()
        if not vanilla and fx_holiday_sched:
            _sched_file2 = fx_holiday_sched.replace('-', '_')
            holiday_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                '..', 'static', 'data', f'{_sched_file2}.json'
            )
            try:
                with open(holiday_path, encoding='utf-8') as _hf:
                    _raw = _json.load(_hf)
                _deal_holidays = set(
                    item['date'] if isinstance(item, dict) else item
                    for item in _raw
                )
            except Exception:
                pass

        _biz = 0
        if not vanilla and fix_start and fix_end:
            try:
                _s = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e = _dt.datetime.strptime(fix_end,   '%Y%m%d').date()
                _cur = _s
                while _cur <= _e:
                    _date_str = _cur.strftime('%Y-%m-%d')
                    if _cur.weekday() < 5 and _date_str not in _deal_holidays:
                        _biz += 1
                    _cur += _dt.timedelta(days=1)
            except Exception:
                pass

        f = [''] * 63
        f[0]  = 'OPC  00002'
        f[1]  = '1'
        f[2]  = '3'
        f[3]  = _cli(client)
        f[4]  = dir_code
        f[6]  = _cpty(client)
        f[7]  = _taxid(client, taxid)
        f[8]  = opt
        f[9]  = _date(deal.get('TradeDate', ''))
        f[10] = _date(deal.get('SettlementDate', ''))
        f[11] = _sh(deal.get('UnderlyingAsset', ''))
        f[12] = _qty(deal.get('TotalNotional', ''))
        f[13] = _num(deal.get('Strike', ''), div100=qic)
        f[14] = '1'
        f[16] = '2'
        f[17] = '5'
        f[18] = 'S' if brl else ''
        f[19] = fix_start if vanilla else ''
        f[20] = fxconv if (not brl or vanilla) else ''
        f[23] = str(random.randint(1000000000, 9999999999))
        f[24] = _sh(deal.get('Deal', ''))
        f[26] = _num(deal.get('PremiumPerUnit', ''), div100=qic)
        _spot_date = _date(deal.get('SpotDate', ''))
        _is_bank_or_lawton = 'LAWTON' in client.upper() or 'BANCO J.P MORGAN' in client.upper() or 'JP MORGAN' in client.upper()
        if _is_bank_or_lawton:
            f[28] = '2' if f[9] == _spot_date else '3'
        else:
            f[28] = '1'
        f[32] = _spot_date

        if vanilla:
            f[47] = ''
            f[48] = '0'
        else:
            f[47] = '1'
            f[48] = str(_biz) if _biz else ''

        deal_count += 1
        all_lines.append(';'.join(f))

        if asian and fix_start and fix_end:
            try:
                _s2 = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e2 = _dt.datetime.strptime(fix_end,   '%Y%m%d').date()
                _cur2 = _s2
                while _cur2 <= _e2:
                    if _cur2.weekday() < 5 and _cur2.strftime('%Y-%m-%d') not in _deal_holidays:
                        _d = _cur2.strftime('%Y%m%d')
                        _fx = _d if brl else ''
                        all_lines.append(f'OPC  00002;2;{_d};{_fx};;')
                    _cur2 += _dt.timedelta(days=1)
            except Exception:
                pass

    header  = f'OPC  00002;0;JPMORGANBM;{today};00002;'
    content = '\n'.join([header] + all_lines)

    output_dir = CONECTA_NEW_PATH
    try:
        os.makedirs(output_dir, exist_ok=True)
        filepath = _unique_filepath(output_dir, 'OPC_Banco.txt')
        with open(filepath, 'w', encoding='utf-8') as fh:
            fh.write(content)
        if deal_count > 0:
            _create_notification(session.get('user_sid', ''), session.get('user_name', ''), 'Sent to B3', 'Opt Comm', str(deal_count) + ' deal' + ('' if deal_count == 1 else 's') + ' sent')
        return jsonify({'ok': True, 'filename': os.path.basename(filepath), 'count': deal_count})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ==============================================================================
# MAPPING B3 ID — lê arquivos de retorno do Batch Conecta e atualiza B3_ID
# ==============================================================================

@blueprint.route('/api/new-deals/opt-commodities/mapping-b3', methods=['POST'])
def api_mapping_b3():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    data = request.get_json(silent=True) or {}
    sent_deals = data.get('deals', [])   # [{id, Deal}]
    if not sent_deals:
        return jsonify({'ok': True, 'results': []})

    # ── scan return folder ────────────────────────────────────────────
    mapping       = {}   # deal_text -> {'b3_id': str, 'ok': bool}
    files_to_delete = []
    try:
        if not os.path.isdir(RETURN_PATH):
            return jsonify({'ok': False, 'error': f'Return folder not found: {RETURN_PATH}'}), 400

        for fname in os.listdir(RETURN_PATH):
            fpath = os.path.join(RETURN_PATH, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                with open(fpath, encoding='utf-8', errors='replace') as fh:
                    lines = fh.readlines()
                file_has_opc = False
                for line in lines[1:]:   # skip header
                    line = line.strip()
                    if not line:
                        continue
                    # Sigla at chars 57-59 (1-based): Options map only 'OPC' (opção) lines
                    if line[56:59] != 'OPC':
                        continue
                    file_has_opc = True
                    parts = line.split(';')
                    if len(parts) < 5:
                        continue
                    b3_id       = parts[1].strip()
                    status_text = parts[3].strip()
                    opc_part    = parts[4].strip()
                    pipe_parts  = opc_part.split('|')
                    if len(pipe_parts) < 25:
                        continue
                    if pipe_parts[1].strip() != '1':   # only type-1 (characteristics) lines
                        continue
                    deal_text = pipe_parts[24].strip()
                    if not deal_text:
                        continue
                    is_ok = (status_text == 'EXECUCAO OK')
                    if deal_text not in mapping or (is_ok and not mapping[deal_text]['ok']):
                        mapping[deal_text] = {'b3_id': b3_id, 'ok': is_ok}
                # Only delete return files that actually carried OPC (Option) lines
                if file_has_opc:
                    files_to_delete.append(fpath)
            except Exception:
                continue
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    # ── match sent deals and update cache ────────────────────────────
    results = []
    for sent in sent_deals:
        deal_text   = sent.get('Deal', '')
        client_name = sent.get('Client', '')
        if not deal_text or deal_text not in mapping:
            continue

        info       = mapping[deal_text]
        new_status = 'Success' if info['ok'] else 'Error'
        updates    = {'Status': new_status}
        if info['ok']:
            updates['B3_ID'] = info['b3_id']

        if deal_text:
            file_path, idx = _find_deal_in_cache(deal_text, client_name)
            if file_path is not None:
                intrag_candidate = None
                with _cache_lock:
                    try:
                        with open(file_path, 'r', encoding='utf-8') as fh:
                            deals_list = json.load(fh)
                        deals_list[idx].update(updates)
                        with open(file_path, 'w', encoding='utf-8') as fh:
                            json.dump(deals_list, fh, ensure_ascii=False, indent=2)
                        if new_status == 'Success':
                            intrag_candidate = deals_list[idx].copy()
                    except Exception:
                        pass
                if intrag_candidate is not None:
                    _maybe_save_intrag_opt(intrag_candidate)

        results.append({
            'id':     deal_text,
            'deal':   deal_text,
            'b3_id':  info['b3_id'] if info['ok'] else '',
            'status': new_status
        })

    # ── delete processed return files ────────────────────────────────
    for fpath in files_to_delete:
        try:
            os.remove(fpath)
        except Exception:
            pass

    if results:
        _create_notification(session.get('user_sid', ''), session.get('user_name', ''), 'B3 Mapped', 'Opt Comm', str(len(results)) + ' deal' + ('' if len(results) == 1 else 's') + ' mapped')
    return jsonify({'ok': True, 'results': results})


# ==============================================================================
# API — SETTLEMENT / CONFIRMATION E-MAILS (Premium D0 + Economic Affirmation)
# Builds the HTML drafts in apps/pages/otc_emails.py and opens them in Outlook
# for manual review (win32com — Windows/JPM only; degrades gracefully elsewhere).
# ==============================================================================
def _email_drafts_response(drafts):
    """Return the drafts as a downloadable .eml / .zip so the file opens in the
    ACTING user's Outlook (server-side Outlook automation would only ever open on
    the server). From = the logged-in user's e-mail (resolved from their SID)."""
    from apps.pages import otc_emails
    fname, mime, data = otc_emails.build_drafts_download(drafts, session.get('user_email'))
    resp = make_response(data)
    resp.headers['Content-Type'] = mime
    resp.headers['Content-Disposition'] = 'attachment; filename="{}"'.format(fname)
    resp.headers['X-Draft-Count'] = str(len(drafts))
    return resp


@blueprint.route('/api/new-deals/opt-commodities/premium-email', methods=['POST'])
def api_opt_premium_email():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_premium_emails(deals)
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _email_drafts_response(drafts)


@blueprint.route('/api/new-deals/opt-fxo/premium-email', methods=['POST'])
def api_fxo_premium_email():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_premium_emails(deals, asset_label='Taxas de Câmbio',
                                             ref_key='FX CASH ACCRONYM')
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _email_drafts_response(drafts)


@blueprint.route('/api/new-deals/opt-commodities/economic-affirmation', methods=['POST'])
def api_opt_economic_affirmation_email():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_economic_affirmation_emails(deals, asset_label='Opção Mercadoria')
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _email_drafts_response(drafts)


@blueprint.route('/api/new-deals/ndf-commodities/economic-affirmation', methods=['POST'])
def api_ndf_economic_affirmation_email():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_economic_affirmation_emails(deals, asset_label='Termo de Mercadoria')
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _email_drafts_response(drafts)


# ==============================================================================
# API — COUNTERPARTY DETAILS (Reference Data double-click editor)
# Persists CGD / Banking (PAY+RECEIVE) / Contacts to CounterpartyDetails.json,
# keyed by SPN. Replaces (or appends) the record for the edited counterparty.
# ==============================================================================

@blueprint.route('/api/counterparty-details/save', methods=['POST'])
def api_counterparty_details_save():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    payload = request.get_json(silent=True) or {}
    spn = str(payload.get('SPN', '') or '').strip()
    if not spn:
        return jsonify({'ok': False, 'error': 'missing_spn'}), 400

    created = _cpd_find(_cpd_load(), spn) is None
    data, rec = _cpd_get_record(spn)

    # COUNTERPARTY name can still be set here; CGD / CONTACTS / BANKING are each
    # managed by their dedicated maker/checker endpoints below and are left untouched.
    if payload.get('COUNTERPARTY'):
        rec['COUNTERPARTY'] = payload.get('COUNTERPARTY')

    try:
        _cpd_save_list(data)
    except IOError as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    return jsonify({'ok': True, 'created': created})


# ──────────────────────────────────────────────────────────────────────────
# Banking accounts — maker/checker (Pending → Active) + Default PAY/RECEIVE
# Model in CounterpartyDetails.json:
#   BANKING: { ACCOUNTS:[{id,bank,agency,account,status,maker,checker}],
#              DEFAULT_PAY:{current,pending,maker,checker},
#              DEFAULT_RECEIVE:{...} }
# ⚠️ SPN matching ignores leading zeros on both sides.
# ──────────────────────────────────────────────────────────────────────────
def _cpd_path():
    return os.path.join(_B3_DATA_DIR, 'CounterpartyDetails.json')


def _cpd_load():
    try:
        with open(_cpd_path(), encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError, FileNotFoundError):
        return []


def _cpd_save_list(data):
    path = _cpd_path()
    try:
        shutil.copy2(path, path + '.bak')
    except (IOError, OSError):
        pass
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _norm_spn(value):
    s = str(value or '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    s = s.lstrip('0')
    return s or ('0' if value not in (None, '') else '')


def _cpd_find(data, spn):
    target = _norm_spn(spn)
    for rec in data:
        if _norm_spn(rec.get('SPN', '')) == target:
            return rec
    return None


def _default_slot(existing=None):
    existing = existing or {}
    return {
        'current': existing.get('current') or None,
        'pending': existing.get('pending') or None,
        'maker':   existing.get('maker', '') or '',
        'checker': existing.get('checker', '') or '',
    }


def _bank_norm(bank):
    """Coerce any stored BANKING shape into the ACCOUNTS + defaults model."""
    if not isinstance(bank, dict):
        bank = {}
    accounts = bank.get('ACCOUNTS')
    if not isinstance(accounts, list):
        accounts = []
        legacy = []
        for key in ('PAY', 'RECEIVE'):
            for b in (bank.get(key) or []):
                legacy.append({'bank': b.get('bank', ''), 'agency': b.get('agency', ''),
                               'account': b.get('account', '')})
        seen = set()
        for a in legacy:
            k = (a['bank'], a['agency'], a['account'])
            if any(a.values()) and k not in seen:
                seen.add(k)
                accounts.append({'id': uuid.uuid4().hex[:8], 'bank': a['bank'],
                                 'agency': a['agency'], 'account': a['account'],
                                 'status': 'Active', 'maker': 'IMPORT', 'checker': 'IMPORT'})
    out = []
    for a in accounts:
        a = a or {}
        out.append({
            'id':      a.get('id') or uuid.uuid4().hex[:8],
            'bank':    a.get('bank', ''), 'agency': a.get('agency', ''),
            'account': a.get('account', ''),
            'status':  a.get('status', 'Active') or 'Active',
            'maker':   a.get('maker', '') or '', 'checker': a.get('checker', '') or '',
        })
    return {'ACCOUNTS': out,
            'DEFAULT_PAY': _default_slot(bank.get('DEFAULT_PAY')),
            'DEFAULT_RECEIVE': _default_slot(bank.get('DEFAULT_RECEIVE'))}


def _bank_get_record(spn):
    """Return (data, rec, banking) for an SPN, creating the record if needed."""
    data = _cpd_load()
    rec = _cpd_find(data, spn)
    if rec is None:
        rec = {'SPN': str(spn or '').strip(), 'COUNTERPARTY': '', 'CGD': [],
               'BANKING': _bank_norm({}), 'CONTACTS': []}
        data.append(rec)
    rec['BANKING'] = _bank_norm(rec.get('BANKING'))
    return data, rec, rec['BANKING']


def _cgd_norm(cgd):
    """Coerce stored CGD into a list of maker/checker items.
    Legacy shapes (string / list-of-strings) become Active items imported."""
    items = []
    raw = cgd if isinstance(cgd, list) else ([cgd] if cgd not in (None, '') else [])
    for x in raw:
        if isinstance(x, dict):
            val = str(x.get('value', '') or '').strip()
            if not val:
                continue
            items.append({
                'id':      x.get('id') or uuid.uuid4().hex[:8],
                'value':   val,
                'status':  x.get('status', 'Active') or 'Active',
                'maker':   x.get('maker', '') or '',
                'checker': x.get('checker', '') or '',
            })
        else:
            val = str(x).strip()
            if val:
                items.append({'id': uuid.uuid4().hex[:8], 'value': val,
                              'status': 'Active', 'maker': 'IMPORT', 'checker': 'IMPORT'})
    return items


def _contacts_norm(contacts):
    """Coerce stored CONTACTS into maker/checker items. `status` keeps the business
    Active/Inactive value; approval state lives in `appr` (Pending/Active) + maker/checker.
    Legacy contacts (no appr/maker keys) are imported as already approved."""
    out = []
    for c in (contacts or []):
        c = c or {}
        legacy = ('appr' not in c) and ('maker' not in c)
        rules = c.get('rules')
        if not isinstance(rules, list):
            rules = c.get('RULES') if isinstance(c.get('RULES'), list) else []
        out.append({
            'id':      c.get('id') or uuid.uuid4().hex[:8],
            'name':    c.get('name')  or c.get('NAME')  or '',
            'phone':   c.get('phone') or c.get('PHONE') or '',
            'email':   c.get('email') or c.get('EMAIL') or '',
            'rules':   rules,
            'status':  c.get('status') or c.get('STATUS') or 'Active',
            'appr':    c.get('appr') or ('Active' if legacy else 'Pending'),
            'maker':   c.get('maker', '') or ('IMPORT' if legacy else ''),
            'checker': c.get('checker', '') or ('IMPORT' if legacy else ''),
        })
    return out


# Settlement Net Type — single value per counterparty with maker/checker.
# Item: {value ∈ _CP_NET_TYPES, status ∈ Active|Pending, maker, checker}
_CP_NET_TYPES = ['Total Net', 'Pay/Rec', 'No Net']


def _net_norm(net):
    """Coerce a stored Settlement Net Type into {value,status,maker,checker}.
    Missing/legacy records default to Total Net, already Active (imported)."""
    if not isinstance(net, dict):
        net = {}
    val = str(net.get('value', '') or '').strip()
    return {
        'value':   val if val in _CP_NET_TYPES else 'Total Net',
        'status':  net.get('status', 'Active') or 'Active',
        'maker':   net.get('maker', '') or '',
        'checker': net.get('checker', '') or '',
    }


def _cpd_get_record(spn):
    """Return (data, rec) for an SPN with CGD/CONTACTS/BANKING/NET normalized; create if missing."""
    data = _cpd_load()
    rec = _cpd_find(data, spn)
    if rec is None:
        rec = {'SPN': str(spn or '').strip(), 'COUNTERPARTY': '', 'CGD': [],
               'BANKING': _bank_norm({}), 'CONTACTS': [], 'NET': _net_norm({})}
        data.append(rec)
    rec['CGD'] = _cgd_norm(rec.get('CGD'))
    rec['CONTACTS'] = _contacts_norm(rec.get('CONTACTS'))
    rec['BANKING'] = _bank_norm(rec.get('BANKING'))
    rec['NET'] = _net_norm(rec.get('NET'))
    return data, rec


def _contact_disp(c):
    if not c:
        return ''
    return (c.get('name') or c.get('email') or c.get('id') or '').strip()


def _acc_disp(acc):
    if not acc:
        return ''
    return (acc.get('bank') or acc.get('account') or acc.get('id') or '').strip()


def _bank_detail(spn, rec, extra=''):
    """Notification detail: 'SPN <spn> · <counterparty> · <extra>'. The leading
    'SPN <spn>' lets the bell deep-link to Reference Data filtered by that SPN."""
    name = str((rec or {}).get('COUNTERPARTY', '') or '').strip()
    head = 'SPN {} · {}'.format(spn, name) if name else 'SPN {}'.format(spn)
    return head + ' · ' + extra if extra else head


def _notify_bank(action, detail):
    """Emit a notification-bell entry for a banking maker/checker action."""
    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         action, 'Reference Data', detail)


@blueprint.route('/api/counterparty-details/banking/account/add', methods=['POST'])
def api_cp_banking_account_add():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    if not spn:
        return jsonify({'ok': False, 'error': 'missing_spn'}), 400
    bank = str(p.get('bank', '') or '').strip()
    agency = str(p.get('agency', '') or '').strip()
    account = str(p.get('account', '') or '').strip()
    if not (bank or agency or account):
        return jsonify({'ok': False, 'error': 'empty_account'}), 400

    sid = session.get('user_sid', '') or ''
    data, rec, banking = _bank_get_record(spn)
    acc = {'id': uuid.uuid4().hex[:8], 'bank': bank, 'agency': agency,
           'account': account, 'status': 'Pending', 'maker': sid, 'checker': ''}
    banking['ACCOUNTS'].append(acc)
    _cpd_save_list(data)
    _notify_bank('Bank Account Added', _bank_detail(spn, rec, _acc_disp(acc) + ' (Pending approval)'))
    return jsonify({'ok': True, 'account': acc})


@blueprint.route('/api/counterparty-details/banking/account/edit', methods=['POST'])
def api_cp_banking_account_edit():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    acc_id = str(p.get('id', '') or '').strip()
    if not spn:
        return jsonify({'ok': False, 'error': 'missing_spn'}), 400
    bank = str(p.get('bank', '') or '').strip()
    agency = str(p.get('agency', '') or '').strip()
    account = str(p.get('account', '') or '').strip()
    if not (bank or agency or account):
        return jsonify({'ok': False, 'error': 'empty_account'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec, banking = _bank_get_record(spn)
    acc = next((a for a in banking['ACCOUNTS'] if a['id'] == acc_id), None)
    if acc is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    # Editing bank details requires re-approval → back to Pending (maker/checker).
    acc['bank'] = bank
    acc['agency'] = agency
    acc['account'] = account
    acc['status'] = 'Pending'
    acc['maker'] = sid
    acc['checker'] = ''
    _cpd_save_list(data)
    _notify_bank('Bank Account Edited', _bank_detail(spn, rec, _acc_disp(acc) + ' (Pending approval)'))
    return jsonify({'ok': True, 'account': acc})


@blueprint.route('/api/counterparty-details/banking/account/approve', methods=['POST'])
def api_cp_banking_account_approve():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    acc_id = str(p.get('id', '') or '').strip()
    sid = session.get('user_sid', '') or ''
    data, rec, banking = _bank_get_record(spn)
    acc = next((a for a in banking['ACCOUNTS'] if a['id'] == acc_id), None)
    if acc is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    if acc.get('maker') and acc['maker'] == sid:
        return jsonify({'ok': False, 'error': 'same_user'}), 403
    acc['status'] = 'Active'
    acc['checker'] = sid
    _cpd_save_list(data)
    _notify_bank('Bank Account Approved', _bank_detail(spn, rec, _acc_disp(acc)))
    return jsonify({'ok': True, 'account': acc})


@blueprint.route('/api/counterparty-details/banking/account/delete', methods=['POST'])
def api_cp_banking_account_delete():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    acc_id = str(p.get('id', '') or '').strip()
    data, rec, banking = _bank_get_record(spn)
    removed = next((a for a in banking['ACCOUNTS'] if a['id'] == acc_id), None)
    banking['ACCOUNTS'] = [a for a in banking['ACCOUNTS'] if a['id'] != acc_id]
    for slot in ('DEFAULT_PAY', 'DEFAULT_RECEIVE'):
        d = banking[slot]
        if d.get('current') == acc_id:
            d['current'] = None
        if d.get('pending') == acc_id:
            d['pending'] = None
    _cpd_save_list(data)
    _notify_bank('Bank Account Deleted', _bank_detail(spn, rec, _acc_disp(removed)))
    return jsonify({'ok': True})


@blueprint.route('/api/counterparty-details/banking/default/set', methods=['POST'])
def api_cp_banking_default_set():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    kind = str(p.get('kind', '') or '').upper()
    acc_id = str(p.get('id', '') or '').strip()
    if kind not in ('PAY', 'RECEIVE'):
        return jsonify({'ok': False, 'error': 'bad_kind'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec, banking = _bank_get_record(spn)
    acc = next((a for a in banking['ACCOUNTS'] if a['id'] == acc_id), None)
    if acc is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    if str(acc.get('status', '')).lower() != 'active':
        return jsonify({'ok': False, 'error': 'not_active'}), 400
    slot = banking['DEFAULT_' + kind]
    slot['pending'] = acc_id
    slot['maker'] = sid
    slot['checker'] = ''
    _cpd_save_list(data)
    _notify_bank('Bank Default Set', _bank_detail(spn, rec, '{} → {} (Pending approval)'.format(kind, _acc_disp(acc))))
    return jsonify({'ok': True, 'slot': slot})


@blueprint.route('/api/counterparty-details/banking/default/approve', methods=['POST'])
def api_cp_banking_default_approve():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    kind = str(p.get('kind', '') or '').upper()
    if kind not in ('PAY', 'RECEIVE'):
        return jsonify({'ok': False, 'error': 'bad_kind'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec, banking = _bank_get_record(spn)
    slot = banking['DEFAULT_' + kind]
    if not slot.get('pending'):
        return jsonify({'ok': False, 'error': 'no_pending'}), 400
    if slot.get('maker') and slot['maker'] == sid:
        return jsonify({'ok': False, 'error': 'same_user'}), 403
    slot['current'] = slot['pending']
    slot['pending'] = None
    slot['checker'] = sid
    _cpd_save_list(data)
    _acc = next((a for a in banking['ACCOUNTS'] if a['id'] == slot['current']), None)
    _notify_bank('Bank Default Approved', _bank_detail(spn, rec, '{} → {}'.format(kind, _acc_disp(_acc))))
    return jsonify({'ok': True, 'slot': slot})


# ──────────────────────────────────────────────────────────────────────────
# CGD — maker/checker (Pending → Active). Item: {id,value,status,maker,checker}
# ──────────────────────────────────────────────────────────────────────────
@blueprint.route('/api/counterparty-details/cgd/add', methods=['POST'])
def api_cp_cgd_add():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    if not spn:
        return jsonify({'ok': False, 'error': 'missing_spn'}), 400
    value = str(p.get('value', '') or '').strip()
    if not value:
        return jsonify({'ok': False, 'error': 'empty_value'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec = _cpd_get_record(spn)
    item = {'id': uuid.uuid4().hex[:8], 'value': value,
            'status': 'Pending', 'maker': sid, 'checker': ''}
    rec['CGD'].append(item)
    _cpd_save_list(data)
    _notify_bank('CGD Added', _bank_detail(spn, rec, value + ' (Pending approval)'))
    return jsonify({'ok': True, 'item': item})


@blueprint.route('/api/counterparty-details/cgd/edit', methods=['POST'])
def api_cp_cgd_edit():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    value = str(p.get('value', '') or '').strip()
    if not value:
        return jsonify({'ok': False, 'error': 'empty_value'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec = _cpd_get_record(spn)
    item = next((x for x in rec['CGD'] if x['id'] == iid), None)
    if item is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    item['value'] = value
    item['status'] = 'Pending'
    item['maker'] = sid
    item['checker'] = ''
    _cpd_save_list(data)
    _notify_bank('CGD Edited', _bank_detail(spn, rec, value + ' (Pending approval)'))
    return jsonify({'ok': True, 'item': item})


@blueprint.route('/api/counterparty-details/cgd/approve', methods=['POST'])
def api_cp_cgd_approve():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    sid = session.get('user_sid', '') or ''
    data, rec = _cpd_get_record(spn)
    item = next((x for x in rec['CGD'] if x['id'] == iid), None)
    if item is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    if item.get('maker') and item['maker'] == sid:
        return jsonify({'ok': False, 'error': 'same_user'}), 403
    item['status'] = 'Active'
    item['checker'] = sid
    _cpd_save_list(data)
    _notify_bank('CGD Approved', _bank_detail(spn, rec, item['value']))
    return jsonify({'ok': True, 'item': item})


@blueprint.route('/api/counterparty-details/cgd/delete', methods=['POST'])
def api_cp_cgd_delete():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    data, rec = _cpd_get_record(spn)
    removed = next((x for x in rec['CGD'] if x['id'] == iid), None)
    rec['CGD'] = [x for x in rec['CGD'] if x['id'] != iid]
    _cpd_save_list(data)
    _notify_bank('CGD Deleted', _bank_detail(spn, rec, (removed or {}).get('value', '')))
    return jsonify({'ok': True})


# ──────────────────────────────────────────────────────────────────────────
# SETTLEMENT NET TYPE — single value per counterparty, maker/checker.
# Editing proposes a change (→ Pending); a different SID approves (→ Active).
# ──────────────────────────────────────────────────────────────────────────
@blueprint.route('/api/counterparty-details/net/edit', methods=['POST'])
def api_cp_net_edit():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    if not spn:
        return jsonify({'ok': False, 'error': 'missing_spn'}), 400
    value = str(p.get('value', '') or '').strip()
    if value not in _CP_NET_TYPES:
        return jsonify({'ok': False, 'error': 'invalid_value'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec = _cpd_get_record(spn)
    rec['NET'] = {'value': value, 'status': 'Pending', 'maker': sid, 'checker': ''}
    _cpd_save_list(data)
    _notify_bank('Net Type Edited', _bank_detail(spn, rec, value + ' (Pending approval)'))
    return jsonify({'ok': True, 'item': rec['NET']})


@blueprint.route('/api/counterparty-details/net/approve', methods=['POST'])
def api_cp_net_approve():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    sid = session.get('user_sid', '') or ''
    data, rec = _cpd_get_record(spn)
    net = rec['NET']
    if net.get('maker') and net['maker'] == sid:
        return jsonify({'ok': False, 'error': 'same_user'}), 403
    net['status'] = 'Active'
    net['checker'] = sid
    _cpd_save_list(data)
    _notify_bank('Net Type Approved', _bank_detail(spn, rec, net['value']))
    return jsonify({'ok': True, 'item': net})


# ──────────────────────────────────────────────────────────────────────────
# CONTACTS — maker/checker (Pending → Active). Approval lives in `appr`;
# `status` stays the business Active/Inactive value.
# Item: {id,name,phone,email,rules,status,appr,maker,checker}
# ──────────────────────────────────────────────────────────────────────────
def _contact_payload(p):
    rules = p.get('rules')
    if not isinstance(rules, list):
        rules = []
    return {
        'name':   str(p.get('name', '') or '').strip(),
        'phone':  str(p.get('phone', '') or '').strip(),
        'email':  str(p.get('email', '') or '').strip(),
        'rules':  [str(r).strip() for r in rules if str(r).strip()],
        'status': str(p.get('status', 'Active') or 'Active').strip() or 'Active',
    }


@blueprint.route('/api/counterparty-details/contact/add', methods=['POST'])
def api_cp_contact_add():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    if not spn:
        return jsonify({'ok': False, 'error': 'missing_spn'}), 400
    fields = _contact_payload(p)
    if not (fields['name'] or fields['phone'] or fields['email'] or fields['rules']):
        return jsonify({'ok': False, 'error': 'empty_contact'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec = _cpd_get_record(spn)
    item = dict(fields, id=uuid.uuid4().hex[:8], appr='Pending', maker=sid, checker='')
    rec['CONTACTS'].append(item)
    _cpd_save_list(data)
    _notify_bank('Contact Added', _bank_detail(spn, rec, _contact_disp(item) + ' (Pending approval)'))
    return jsonify({'ok': True, 'item': item})


@blueprint.route('/api/counterparty-details/contact/edit', methods=['POST'])
def api_cp_contact_edit():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    fields = _contact_payload(p)
    if not (fields['name'] or fields['phone'] or fields['email'] or fields['rules']):
        return jsonify({'ok': False, 'error': 'empty_contact'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec = _cpd_get_record(spn)
    item = next((x for x in rec['CONTACTS'] if x['id'] == iid), None)
    if item is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    item.update(fields)
    item['appr'] = 'Pending'
    item['maker'] = sid
    item['checker'] = ''
    _cpd_save_list(data)
    _notify_bank('Contact Edited', _bank_detail(spn, rec, _contact_disp(item) + ' (Pending approval)'))
    return jsonify({'ok': True, 'item': item})


@blueprint.route('/api/counterparty-details/contact/approve', methods=['POST'])
def api_cp_contact_approve():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    sid = session.get('user_sid', '') or ''
    data, rec = _cpd_get_record(spn)
    item = next((x for x in rec['CONTACTS'] if x['id'] == iid), None)
    if item is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    if item.get('maker') and item['maker'] == sid:
        return jsonify({'ok': False, 'error': 'same_user'}), 403
    item['appr'] = 'Active'
    item['checker'] = sid
    _cpd_save_list(data)
    _notify_bank('Contact Approved', _bank_detail(spn, rec, _contact_disp(item)))
    return jsonify({'ok': True, 'item': item})


@blueprint.route('/api/counterparty-details/contact/delete', methods=['POST'])
def api_cp_contact_delete():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    data, rec = _cpd_get_record(spn)
    removed = next((x for x in rec['CONTACTS'] if x['id'] == iid), None)
    rec['CONTACTS'] = [x for x in rec['CONTACTS'] if x['id'] != iid]
    _cpd_save_list(data)
    _notify_bank('Contact Deleted', _bank_detail(spn, rec, _contact_disp(removed)))
    return jsonify({'ok': True})


# ==============================================================================
# API — GENERIC NEW-DEALS CACHE (NDF FWD Start / NDF Other Publisher)
# Page + CRUD only. Same Deal+Client keyed JSON cache model as ndf-commodities.
# Import-parse / mapping-B3 / send-Conecta are product-specific and intentionally
# not wired here (handled per-product later).
# ==============================================================================

_GENERIC_ND_PRODUCTS = {
    'fwd-start': {
        'dir':    os.path.join(NEW_DEALS_CACHE_ROOT, 'NDF', 'FwdStart'),
        'suffix': '_ndffwdstart.json',
        'label':  'NDF FWD Start',
    },
    'other-publishers': {
        'dir':    os.path.join(NEW_DEALS_CACHE_ROOT, 'NDF', 'OtherPublisher'),
        'suffix': '_ndfotherpub.json',
        'label':  'NDF Other Publisher',
    },
}


def _generic_nd_cfg(product):
    return _GENERIC_ND_PRODUCTS.get(product)


def _find_generic_nd_deal(cfg, deal_name, client_name=None):
    """Locate a deal by Deal (+optional Client) across the product's cache files.
    Returns (file_path, list_index) or (None, None)."""
    base = cfg['dir']
    if not os.path.isdir(base):
        return None, None
    for root, _dirs, files in os.walk(base):
        for fname in sorted(files):
            if not fname.endswith(cfg['suffix']):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
                for i, deal in enumerate(deals):
                    if deal.get('Deal', '') == deal_name and (client_name is None or deal.get('Client', '') == client_name):
                        return fpath, i
            except Exception:
                continue
    return None, None


@blueprint.route('/api/new-deals/<product>/cache', methods=['POST'])
def api_generic_nd_save_cache(product):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    try:
        ref_date = datetime.strptime(data.get('TradeDate', ''), '%d/%m/%Y')
    except (ValueError, TypeError):
        ref_date = datetime.now()

    dir_path = os.path.join(cfg['dir'], ref_date.strftime('%Y'), ref_date.strftime('%m'))
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, ref_date.strftime('%Y%m%d') + cfg['suffix'])

    with _cache_lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
            except (json.JSONDecodeError, ValueError):
                deals = []
        else:
            deals = []

        deal_name   = data.get('Deal', '').strip()
        client_name = data.get('Client', '').strip()
        existing_idx = next((i for i, d in enumerate(deals)
                             if deal_name
                             and d.get('Deal', '').strip() == deal_name
                             and d.get('Client', '').strip() == client_name), None)
        if existing_idx is not None:
            deals[existing_idx] = data
        else:
            deals.append(data)
        _atomic_write_json(file_path, deals)

    return jsonify({"success": True, "deal": data.get('Deal', '')})


@blueprint.route('/api/new-deals/<product>/cache/search', methods=['POST'])
def api_generic_nd_search_cache(product):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    filters = (request.get_json(silent=True) or {}).get('filters', [])
    matched = []
    if os.path.isdir(cfg['dir']):
        for root, _dirs, files in os.walk(cfg['dir']):
            for fname in sorted(files):
                if not fname.endswith(cfg['suffix']):
                    continue
                try:
                    with open(os.path.join(root, fname), 'r', encoding='utf-8') as fh:
                        deals = json.load(fh)
                    if not isinstance(deals, list):
                        deals = [deals]
                    for deal in deals:
                        if _deal_matches(deal, filters):
                            matched.append(deal)
                except Exception:
                    continue
    return jsonify({"success": True, "deals": matched})


@blueprint.route('/api/new-deals/<product>/cache/<deal_id>', methods=['PATCH'])
def api_generic_nd_update_cache(product, deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    client  = request.args.get('client')
    updates = request.get_json(silent=True)
    if not updates:
        return jsonify({"success": False, "message": "No data provided"}), 400

    file_path, _ = _find_generic_nd_deal(cfg, deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if d.get('Deal') == deal_id and (client is None or d.get('Client', '') == client)), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        deals[idx].update(updates)
        _atomic_write_json(file_path, deals)
        updated_deal = deals[idx].copy()

    # Save to Intrag NDF when Status→Success and client is BANCO JP MORGAN
    # (fwd-start / other-publishers share this generic endpoint).
    cl_lower = (updated_deal.get('Client', '') or '').lower()
    if str(updates.get('Status', '')) == 'Success' and 'banco' in cl_lower and 'morgan' in cl_lower:
        try:
            _save_intrag_ndf_entry(updated_deal)
        except Exception as exc:
            log.error('[NDF GENERIC PATCH] Failed to save Intrag entry for deal=%r: %s', deal_id, exc)

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            # The 'Sent' transition is already announced by the 'Sent to B3'
            # notification emitted from send-conecta — skip the redundant
            # 'Status Updated' entry so the bell shows a single item per send.
            if str(_fields.get('Status', '')) != 'Sent':
                _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                     'Status Updated', cfg['label'], deal_id + ' → ' + str(_fields.get('Status', '')) + _nd_token(updated_deal.get('TradeDate')))
        else:
            _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                 'Deal Updated', cfg['label'], deal_id + ' (' + ', '.join(_fields.keys()) + ')' + _nd_token(updated_deal.get('TradeDate')))
    return jsonify({"success": True})


@blueprint.route('/api/new-deals/<product>/cache/<deal_id>', methods=['DELETE'])
def api_generic_nd_delete_cache(product, deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    client = request.args.get('client')
    file_path, _ = _find_generic_nd_deal(cfg, deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if d.get('Deal') == deal_id and (client is None or d.get('Client', '') == client)), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        removed = deals.pop(idx)
        _atomic_write_json(file_path, deals)

    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Deal Deleted', cfg['label'], deal_id + _nd_token((removed or {}).get('TradeDate')))
    return jsonify({"success": True})


@blueprint.route('/api/new-deals/<product>/cache/bulk-delete', methods=['POST'])
def api_generic_nd_bulk_delete_cache(product):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    data  = request.get_json(silent=True)
    pairs = data.get('pairs', []) if data else []
    if not pairs:
        return jsonify({"success": False, "message": "No pairs provided"}), 400

    pair_set = {(p.get('deal', ''), p.get('client', '')) for p in pairs}
    file_pairs = {}
    for deal_name, client_name in pair_set:
        fp, _ = _find_generic_nd_deal(cfg, deal_name, client_name)
        if fp:
            file_pairs.setdefault(fp, set()).add((deal_name, client_name))

    deleted = 0
    for fp, pairs_in_file in file_pairs.items():
        with _cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            if not isinstance(deals, list):
                deals = [deals]
            before = len(deals)
            deals  = [d for d in deals if (d.get('Deal', ''), d.get('Client', '')) not in pairs_in_file]
            deleted += before - len(deals)
            _atomic_write_json(fp, deals)

    not_found = len(pair_set) - deleted
    if deleted > 0:
        _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'Bulk Delete', cfg['label'],
                             str(deleted) + ' deal' + ('s' if deleted != 1 else '') + ' deleted')
    return jsonify({"success": True, "deleted": deleted, "not_found": not_found})


@blueprint.route('/api/new-deals/<product>/cache/bulk-patch', methods=['POST'])
def api_generic_nd_bulk_patch_cache(product):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    data    = request.get_json(silent=True)
    patches = data.get('patches', []) if data else []
    if not patches:
        return jsonify({"success": False, "message": "No patches provided"}), 400

    file_patches = {}
    for p in patches:
        deal_id = p.get('deal_id', '')
        client  = p.get('client', '')
        updates = p.get('updates', {})
        if not deal_id or not updates:
            continue
        fp, _ = _find_generic_nd_deal(cfg, deal_id, client)
        if fp:
            file_patches.setdefault(fp, []).append((deal_id, client, updates))

    updated = 0
    for fp, file_ops in file_patches.items():
        with _cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            for deal_id, client, updates in file_ops:
                idx = next((i for i, d in enumerate(deals)
                            if d.get('Deal') == deal_id and (not client or d.get('Client', '') == client)), None)
                if idx is not None:
                    deals[idx].update(updates)
                    updated += 1
            _atomic_write_json(fp, deals)

    if updated > 0:
        _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'Bulk Update', cfg['label'],
                             str(updated) + ' deal' + ('s' if updated != 1 else '') + ' updated')
    return jsonify({"success": True, "updated": updated})


# ==============================================================================
# NOTIFICATIONS
# ==============================================================================

@blueprint.route('/api/notifications', methods=['GET'])
def api_get_notifications():
    if not session.get('authenticated'):
        return jsonify({"success": False}), 401
    user_role = session.get('user_role', '')
    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT id, actor_sid, actor_name, action, page, detail, target_role, created_at
            FROM notifications
            WHERE DATE(created_at) = CURRENT_DATE
              AND (target_role = '' OR target_role = ?)
            ORDER BY created_at DESC
            LIMIT 50
        """, [user_role]).fetchall()
        notifs = []
        for r in rows:
            notifs.append({
                "id": r[0],
                "actor_sid": r[1] or '',
                "actor_name": r[2] or '',
                "action": r[3] or '',
                "page": r[4] or '',
                "detail": r[5] or '',
                "created_at": r[7].isoformat() if r[7] else ''
            })
        return jsonify({"success": True, "notifications": notifs, "total_today": len(notifs)})
    finally:
        conn.close()


@blueprint.route('/api/notifications', methods=['POST'])
def api_create_notification():
    if not session.get('authenticated'):
        return jsonify({"success": False}), 401
    data        = request.get_json(silent=True) or {}
    action      = data.get('action', '').strip()
    page        = data.get('page', '').strip()
    detail      = data.get('detail', '').strip()
    target_role = data.get('target_role', '').strip()
    if not action or not page:
        return jsonify({"success": False, "message": "action and page required"}), 400
    _create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        action, page, detail, target_role
    )
    return jsonify({"success": True})


# ==============================================================================
# RECONCILIAÇÃO DE COMITENTES
# ==============================================================================

@blueprint.route('/reconciliation-comitente')
def reconciliation_comitente():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/reconciliation-comitente.html', segment='reconciliation-comitente')


@blueprint.route('/reconciliation-comitente/data')
def reconciliation_comitente_data():
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        from apps.pages.recon_comitente import load_from_db
        return jsonify(load_from_db())
    except Exception as e:
        log.error('[recon_comitente_data] %s', e)
        return jsonify({'error': str(e)}), 500


@blueprint.route('/reconciliation-comitente/run', methods=['POST'])
def reconciliation_comitente_run():
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    mode        = request.form.get('mode', 'auto')
    recon_date  = request.form.get('recon_date', '')

    try:
        if mode == 'auto':
            from apps.pages.recon_comitente import run_auto
            result = run_auto(recon_date)
        else:
            f_b3_cgd = request.files.get('file_b3_cgd')
            f_dcad   = request.files.get('file_dcad')
            f_party  = request.files.get('file_party')
            if not f_b3_cgd or not f_dcad or not f_party:
                return jsonify({'error': 'Os 3 arquivos são obrigatórios no modo manual.'}), 400
            from apps.pages.recon_comitente import run_reconciliation
            result = run_reconciliation(f_b3_cgd, f_dcad, f_party, recon_date)

        # Envia email com sumário + Excel em background (não bloqueia resposta)
        file_path = result.pop('file_path', None)
        filename  = result.pop('filename', None)
        counts = result.get('counts', {})
        if counts.get('total', 0) > 0:
            try:
                from apps.pages.recon_comitente import send_recon_comitente_email
                send_recon_comitente_email(recon_date, counts, file_path, filename)
            except Exception as mail_err:
                log.warning('[reconciliation_comitente_run] email não enviado: %s', mail_err)

            _create_notification(
                session.get('user_sid', ''),
                session.get('user_name', ''),
                'Recon Generated',
                'Recon Comitente',
                f"{counts.get('total', 0)} records — OK:{counts.get('ok', 0)} Check:{counts.get('check', 0)} Amend:{counts.get('amend', 0)} ({recon_date})"
            )

        return jsonify(result)
    except FileNotFoundError as e:
        log.warning('[reconciliation_comitente_run] arquivo não encontrado: %s', e)
        return jsonify({'not_found': True, 'missing': getattr(e, 'missing', None), 'detail': str(e)})
    except Exception as e:
        log.error('[reconciliation_comitente_run] %s', e)
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# ROTA GENÉRICA — TEMPLATES (deve ser a ÚLTIMA rota definida)
# ==============================================================================

@blueprint.route('/<template>')
def route_template(template):
    try:
        if not template.endswith('.html'):
            template += '.html'
        segment = get_segment(request)
        log.debug("[route_template] Rendering pages/%s (segment=%s)", template, segment)
        return render_template("pages/" + template, segment=segment)
    except TemplateNotFound:
        log.warning("[route_template] Template not found: pages/%s", template)
        return render_template('pages/error-404.html'), 404
    except Exception:
        log.error("[route_template] Error rendering pages/%s:\n%s", template, traceback.format_exc())
        return render_template('pages/error-500.html'), 500


# ==============================================================================
# FUNÇÕES AUXILIARES — INTERNAS
# ==============================================================================

def _initiate_2fa(sid, email, name):
    log.info("[_initiate_2fa] Generating 2FA code for SID=%s email=%s", sid, email)
    code = generate_verification_code()
    save_verification_code(sid, code)

    email_sent = send_verification_email(email, code, name)
    log.info("[_initiate_2fa] Email sent=%s for SID=%s", email_sent, sid)
    if not email_sent:
        flash("Failed to send verification email. Please try again.", "error")
        return redirect(url_for('pages_blueprint.sign_in_page'))

    session['pending_sid'] = sid
    session['masked_email'] = get_masked_email(email)
    session['masked_phone'] = get_masked_phone()
    log.info("[_initiate_2fa] Session set for SID=%s → redirecting to 2FA page", sid)
    return redirect(url_for('pages_blueprint.two_factor_page'))


def get_segment(request):
    try:
        segment = request.path.split('/')[-1]
        return segment if segment else 'index'
    except Exception:
        return None
