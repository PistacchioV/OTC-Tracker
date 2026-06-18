from gettext import install
import os
import re
import random
import string
import smtplib
import json
import threading
import traceback
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
    url_for, session, flash, jsonify
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


# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "data", "db", "Users_OTCTracker.db")
CACHE_BASE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "static", "data", "cache", "new deals", "Option", "Commodities"
))
SHARED_MAILBOX = "otc.tracker@jpmorgan.com"
RETURN_PATH     = os.getenv('RETURN_PATH',     r'I:\Confirmation\Derivativos\OTC Tracker\Batch Conecta\Return')
CONECTA_NEW_PATH = os.getenv('CONECTA_NEW_PATH', r'I:\Confirmation\Derivativos\OTC Tracker\Batch Conecta\New')
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
            last_exc = e
            if attempt < max_retries - 1:
                wait = retry_delay * (2 ** attempt)
                log.warning("DuckDB locked (attempt %d/%d), retrying in %.0fms…",
                            attempt + 1, max_retries, wait * 1000)
                time.sleep(wait)
            else:
                _duckdb_conn_lock.release()
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
try:
    init_db()
    _migrate_schema()
    cleanup_expired_codes()
    log.info("[startup] Database initialized successfully at %s", os.path.abspath(DB_PATH))
except Exception:
    log.error("[startup] Could not initialize database:\n%s", traceback.format_exc())


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
        update_user_ip(sid, client_ip)
        session['pending_remember_me'] = remember_me
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
    lifetime = timedelta(days=30) if remember_me else timedelta(hours=8)
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
        return 'OPT' if product.lower().startswith('option') else 'NDF'

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

    lawton_deals = [d for d in all_deals if _is_lawton(d)]
    client_deals = [d for d in all_deals if not _is_lawton(d) and not _is_bank(d)]

    ndf_lawton = [d for d in lawton_deals if d['_type'] == 'NDF']
    opt_lawton  = [d for d in lawton_deals if d['_type'] == 'OPT']
    pending_statuses = {'Pending', 'New', 'pending', 'new'}
    pending_total = sum(1 for d in lawton_deals if (d.get('Status') or '').strip() in pending_statuses)

    # Swap deals not yet implemented in the project — placeholder until the
    # Swap product cache directory exists. Will count Swap-type deals later.
    swap_total = 0

    client_counts = Counter(
        (d.get('Client') or '').strip()
        for d in client_deals
        if (d.get('Client') or '').strip()
    )
    top5_clients = [{'label': c, 'count': n} for c, n in client_counts.most_common(5)]

    product_counts = Counter(d['_product'] for d in lawton_deals)
    top5_products  = [{'label': p, 'count': n} for p, n in product_counts.most_common(5)]

    commodity_counts = Counter(
        (d.get('Commodities') or d.get('Commodity') or '').strip()
        for d in lawton_deals
        if (d.get('Commodities') or d.get('Commodity') or '').strip()
    )
    top5_commodities = [{'label': c, 'count': n} for c, n in commodity_counts.most_common(5)]

    # Monthly counts for current year (always full year, ignores period filter)
    monthly_opt = [0] * 12
    monthly_ndf = [0] * 12
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
                deal_type = _type_from_product(product)
                target = monthly_opt if deal_type == 'OPT' else monthly_ndf
                try:
                    with open(fp, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                    cnt = sum(
                        1 for d in data
                        if isinstance(d, dict)
                        and (d.get('Deal') or '').strip()
                        and 'lawton' in (d.get('Client') or '').lower()
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
        'top5_commodities': top5_commodities,
        'monthly_opt':   monthly_opt,
        'monthly_ndf':   monthly_ndf,
        'recent_deals':  recent_deals,
    })


@blueprint.route('/about')
def about():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/about.html', segment='about')


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
        idx = next((i for i, d in enumerate(deals) if d.get('Deal') == deal_id and (client is None or d.get('Client', '') == client)), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        updates.pop('_client', None)
        deals[idx].update(updates)
        for _k in ('Maker', 'Checker'):
            if _k in deals[idx]:
                deals[idx][_k] = deals[idx].pop(_k)
        _atomic_write_json(file_path, deals)

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            _create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Status Updated', 'Opt Comm',
                deal_id + ' → ' + str(_fields.get('Status', ''))
            )
        else:
            _create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Deal Updated', 'Opt Comm',
                deal_id + ' (' + ', '.join(_fields.keys()) + ')'
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
        idx = next((i for i, d in enumerate(deals) if d.get('Deal') == deal_id and (client is None or d.get('Client', '') == client)), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        deals.pop(idx)
        _atomic_write_json(file_path, deals)

    _create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'Deal Deleted', 'Opt Comm', deal_id
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
            entries[idx] = entry
        else:
            entries.append(entry)
        _atomic_write_json(file_path, entries)
    log.info('[INTRAG NDF] Saved entry deal=%r → %s', deal_id, file_path)


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
                    if d_name == deal_name:
                        if client_name is None or d_client == client_name:
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
        idx = next((i for i, d in enumerate(deals) if d.get('Deal') == deal_id and (client is None or d.get('Client', '') == client)), None)
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
            _create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Status Updated', 'NDF Comm',
                deal_id + ' → ' + str(_fields.get('Status', ''))
            )
        else:
            _create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Deal Updated', 'NDF Comm',
                deal_id + ' (' + ', '.join(_fields.keys()) + ')'
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
        idx = next((i for i, d in enumerate(deals) if d.get('Deal') == deal_id and (client is None or d.get('Client', '') == client)), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        deals.pop(idx)
        _atomic_write_json(file_path, deals)

    _create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'Deal Deleted', 'NDF Comm', deal_id
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
            lawton_path = os.path.join(output_dir, 'TCO_LAWTON.txt')
            with open(lawton_path, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([lawton_header] + lawton_lines))
            generated.append({'filename': 'TCO_LAWTON.txt', 'count': lawton_count})
        if banco_lines:
            banco_path = os.path.join(output_dir, 'TCO_BANCO.txt')
            with open(banco_path, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([banco_header] + banco_lines))
            generated.append({'filename': 'TCO_BANCO.txt', 'count': banco_count})
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
    _create_notification(
        user, session.get('user_name', ''),
        'Item Updated', 'Index B3',
        table + ' — ' + action + ' → ' + new_status
    )
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

    records.pop(int(idx))
    _b3_save(path, records)
    _create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'Item Deleted', 'Index B3', table
    )
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
    _create_notification(
        user, session.get('user_name', ''),
        'New Item', 'Index B3',
        table + ': ' + str(fields.get('TICKER', fields.get('CODE', fields.get('NAME', ''))))
    )
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
    filepath   = os.path.join(output_dir, 'OPC_Banco.txt')
    try:
        os.makedirs(output_dir, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as fh:
            fh.write(content)
        if deal_count > 0:
            _create_notification(session.get('user_sid', ''), session.get('user_name', ''), 'Sent to B3', 'Opt Comm', str(deal_count) + ' deal' + ('' if deal_count == 1 else 's') + ' sent')
        return jsonify({'ok': True, 'filename': 'OPC_Banco.txt', 'count': deal_count})
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
                with _cache_lock:
                    try:
                        with open(file_path, 'r', encoding='utf-8') as fh:
                            deals_list = json.load(fh)
                        deals_list[idx].update(updates)
                        with open(file_path, 'w', encoding='utf-8') as fh:
                            json.dump(deals_list, fh, ensure_ascii=False, indent=2)
                    except Exception:
                        pass

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

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                 'Status Updated', cfg['label'], deal_id + ' → ' + str(_fields.get('Status', '')))
        else:
            _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                 'Deal Updated', cfg['label'], deal_id + ' (' + ', '.join(_fields.keys()) + ')')
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
        deals.pop(idx)
        _atomic_write_json(file_path, deals)

    _create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Deal Deleted', cfg['label'], deal_id)
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
        return jsonify({'not_found': True, 'detail': str(e)})
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
