from gettext import install
import os
import random
import string
import getpass
import smtplib
import duckdb
import sqlite3
from datetime import datetime, timedelta
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
# CONFIGURAÇÕES
# ==============================================================================

DB_PATH = r"C:\Users\e930179\ds\OTCTracker\apps\db\Users_OTCTracker.db"
SHARED_MAILBOX = "otc.tracker@jpmorgan.com"
SMTP_HOST = "mailhost.jpmchase.net"
SMTP_PORT = 25
CODE_EXPIRY_MINUTES = 10


# ==============================================================================
# FUNÇÕES AUXILIARES — BANCO DE DADOS (DuckDB)
# ==============================================================================

def get_db_connection():
    """Cria e retorna uma conexão DuckDB."""
    #conn = duckdb.execute('INSTALL sqlite');
    conn = duckdb.connect(
        DB_PATH,
        config={
            "autoinstall_known_extensions": "false",
            "autoload_known_extensions": "false"
        }
    )
    return conn


def init_db():
    """Inicializa as tabelas necessárias no banco de dados."""
    conn = get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                SID VARCHAR PRIMARY KEY,
                Name VARCHAR,
                Email VARCHAR,
                Role VARCHAR,
                IP_Address VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verification_codes (
                id INTEGER PRIMARY KEY,
                SID VARCHAR,
                code VARCHAR(6),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                used BOOLEAN DEFAULT FALSE
            )
        """)
        conn.commit()
    finally:
        conn.close()


def get_user_by_sid(sid):
    """Busca um usuário pelo SID no banco de dados."""
    conn = get_db_connection()
    try:
        result = conn.execute(
            "SELECT SID, Name, Email, Role, IP_Address FROM users WHERE SID = ?",
            [sid]
        ).fetchone()
        if result:
            return {
                "SID": result[0],
                "Name": result[1],
                "Email": result[2],
                "Role": result[3],
                "IP_Address": result[4]
            }
        return None
    finally:
        conn.close()


def upsert_user(sid, name, email, role, ip_address):
    """Insere ou atualiza um usuário no banco de dados."""
    conn = get_db_connection()
    try:
        existing = conn.execute(
            "SELECT SID FROM users WHERE SID = ?", [sid]
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE users
                SET Name = ?, Email = ?, Role = ?, IP_Address = ?
                WHERE SID = ?
            """, [name, email, role, ip_address, sid])
        else:
            conn.execute("""
                INSERT INTO users (SID, Name, Email, Role, IP_Address)
                VALUES (?, ?, ?, ?, ?)
            """, [sid, name, email, role, ip_address])
        conn.commit()
    finally:
        conn.close()


def save_verification_code(sid, code, expires_at):
    """Salva um código de verificação no banco de dados."""
    conn = get_db_connection()
    try:
        # Invalida códigos anteriores do mesmo SID
        conn.execute("""
            UPDATE verification_codes SET used = TRUE WHERE SID = ? AND used = FALSE
        """, [sid])
        conn.execute("""
            INSERT INTO verification_codes (SID, code, expires_at)
            VALUES (?, ?, ?)
        """, [sid, code, expires_at.strftime('%Y-%m-%d %H:%M:%S')])
        conn.commit()
    finally:
        conn.close()


def verify_code(sid, code):
    """Verifica se o código é válido e não expirou."""
    conn = get_db_connection()
    try:
        result = conn.execute("""
            SELECT id, code, expires_at FROM verification_codes
            WHERE SID = ? AND code = ? AND used = FALSE
            ORDER BY created_at DESC
            LIMIT 1
        """, [sid, code]).fetchone()

        if not result:
            return False, "Invalid verification code."

        expires_at_raw = result[2]
        now = datetime.now()

        # Converte para datetime se vier como string do DuckDB
        if isinstance(expires_at_raw, str):
            try:
                expires_at = datetime.strptime(expires_at_raw, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                expires_at = datetime.strptime(expires_at_raw, '%Y-%m-%d %H:%M:%S')
        else:
            expires_at = expires_at_raw

        if now > expires_at:
            return False, "Verification code has expired. Please request a new one."

        conn.execute(
            "UPDATE verification_codes SET used = TRUE WHERE id = ?",
            [result[0]]
        )
        conn.commit()
        return True, "Code verified successfully."
    finally:
        conn.close()


# ==============================================================================
# FUNÇÕES AUXILIARES — UTILITÁRIOS
# ==============================================================================

def get_client_ip():
    """Obtém o IP real do cliente, considerando proxies."""
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.remote_addr


def generate_verification_code():
    """Gera um código numérico de 6 dígitos."""
    return ''.join(random.choices(string.digits, k=6))


def get_user_data_from_phonebook(sid):
    """Busca dados do usuário via awmpy phonebook."""
    try:
        data = awmpy.get_phonebook_data(sid)
        return {
            "nameFull": data.get("nameFull", ""),
            "email": data.get("email", ""),
            "positionName": data.get("positionName", "")
        }
    except Exception as e:
        print(f"Error fetching phonebook data for SID {sid}: {e}")
        return None


def get_masked_email(email):
    """Mascara o email para exibição (ex: g*****@jpmorgan.com)."""
    if not email or '@' not in email:
        return "*******"
    local, domain = email.split('@', 1)
    if len(local) <= 2:
        masked_local = local[0] + '*****'
    else:
        masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def get_masked_phone():
    """Retorna últimos 4 dígitos mascarados (placeholder)."""
    return "******6789"


# ==============================================================================
# FUNÇÕES AUXILIARES — EMAIL
# ==============================================================================

def send_verification_email(to_email, code, recipient_name):
    """Envia email de verificação com o código 2FA via CID attachment."""
    import base64
    from email.mime.image import MIMEImage
    from flask import current_app

    subject = "OTC Tracker - Verification Code"

    # Renderiza o HTML com cid:logo no src
    html_body = render_email_template(code, recipient_name)

    # Estrutura MIME: mixed > alternative + related
    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = SHARED_MAILBOX
    msg['To'] = to_email

    # Parte related: HTML + imagem inline
    msg_related = MIMEMultipart('related')

    # Parte alternative: texto plano + HTML
    msg_alternative = MIMEMultipart('alternative')
    msg_alternative.attach(MIMEText('Please use an HTML email client to view this message.', 'plain'))
    msg_alternative.attach(MIMEText(html_body, 'html'))

    msg_related.attach(msg_alternative)

    # Anexa o logo como CID
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

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.sendmail(SHARED_MAILBOX, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")
        return False


def _get_logo_path():
    """Retorna o path do logo, tentando múltiplos locais."""
    from flask import current_app
    candidates = [
        os.path.join(current_app.root_path, 'static', 'images', 'logo.png'),
        os.path.join(os.path.dirname(current_app.root_path), 'static', 'images', 'logo.png'),
        os.path.join(current_app.root_path, '..', 'static', 'images', 'logo.png'),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.exists(path):
            print(f"[INFO] Logo found at: {path}")
            return path
    print("[WARNING] Logo not found in any candidate path.")
    return None


def render_email_template(code, recipient_name):
    digits = list(code)
    current_year = datetime.now().year

    html = render_template(
        'pages/email-verification.html',
        recipient_name=recipient_name,
        digits=digits,
        expiry_minutes=CODE_EXPIRY_MINUTES,
        current_year=current_year
    )
    return html


# ==============================================================================
# INICIALIZAÇÃO DO BANCO DE DADOS
# ==============================================================================

# Garante que as tabelas existam ao importar o módulo
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
try:
    init_db()
except Exception as e:
    print(f"Warning: Could not initialize database: {e}")


# ==============================================================================
# ROTAS — PÁGINAS DE AUTENTICAÇÃO
# ==============================================================================

@blueprint.route('/')
def index():
    """Página inicial — redireciona para sign-in."""
    return render_template('pages/auth-2-sign-in.html', segment='auth-2-sign-in')


@blueprint.route('/auth-2-sign-in')
def sign_in_page():
    """Exibe a página de sign-in."""
    return render_template('pages/auth-2-sign-in.html', segment='auth-2-sign-in')


@blueprint.route('/auth-2-sign-up')
def sign_up_page():
    """Exibe a página de sign-up (create account)."""
    return render_template('pages/auth-2-sign-up.html', segment='auth-2-sign-up')


@blueprint.route('/auth-2-two-factor')
def two_factor_page():
    """Exibe a página de verificação 2FA."""
    sid = session.get('pending_sid', '')
    masked_email = session.get('masked_email', '******')
    masked_phone = session.get('masked_phone', '******6789')

    return render_template(
        'pages/auth-2-two-factor.html',
        segment='auth-2-two-factor',
        masked_email=masked_email,
        masked_phone=masked_phone
    )


# ==============================================================================
# ROTAS — LÓGICA DE AUTENTICAÇÃO (POST)
# ==============================================================================

@blueprint.route('/register', methods=['POST'])
def register():
    """
    Processa o formulário de Create Account.

    Fluxo:
    1. Valida o SID
    2. Busca dados no phonebook (awmpy)
    3. Verifica se SID já existe no DB
    4. Se existe e IP é igual → entra direto
    5. Se não existe ou IP diferente → gera código 2FA → envia email
    """
    sid = request.form.get('sid', '').strip().upper()

    # Validação do formato do SID
    if not sid or len(sid) != 7:
        flash("Invalid SID format. Must be 1 letter + 6 numbers.", "error")
        return redirect(url_for('pages_blueprint.sign_up_page'))

    import re
    if not re.match(r'^[A-Z][0-9]{6}$', sid):
        flash("Invalid SID format. Must be 1 letter + 6 numbers.", "error")
        return redirect(url_for('pages_blueprint.sign_up_page'))

    # Busca dados do usuário no phonebook
    user_data = get_user_data_from_phonebook(sid)
    if not user_data:
        flash("Could not retrieve user data. Please verify your SID.", "error")
        return redirect(url_for('pages_blueprint.sign_up_page'))

    client_ip = get_client_ip()
    name_full = user_data["nameFull"]
    email = user_data["email"]
    position_name = user_data["positionName"]

    # Verifica se o SID já existe no banco
    existing_user = get_user_by_sid(sid)

    if existing_user:
        # SID existe — verifica se o IP é o mesmo
        if existing_user["IP_Address"] == client_ip:
            # IP igual → entra direto na aplicação
            session['authenticated'] = True
            session['user_sid'] = sid
            session['user_name'] = existing_user["Name"]
            session['user_email'] = existing_user["Email"]
            session['user_role'] = existing_user["Role"]
            return redirect(url_for('pages_blueprint.dashboard'))
        else:
            # IP diferente → precisa de verificação 2FA
            # Atualiza dados do usuário no DB
            upsert_user(sid, name_full, email, position_name, client_ip)
            return _initiate_2fa(sid, email, name_full)
    else:
        # SID não existe → novo usuário, precisa de verificação 2FA
        # Insere dados no DB
        upsert_user(sid, name_full, email, position_name, client_ip)
        return _initiate_2fa(sid, email, name_full)


@blueprint.route('/login', methods=['POST'])
def login():
    """
    Processa o formulário de Sign In.

    Fluxo idêntico ao register:
    1. Valida o SID
    2. Verifica se existe no DB
    3. Se existe e IP é igual → entra direto
    4. Se não existe ou IP diferente → gera código 2FA
    """
    sid = request.form.get('sid', '').strip().upper()

    # Validação do formato do SID
    import re
    if not sid or not re.match(r'^[A-Z][0-9]{6}$', sid):
        flash("Invalid SID format. Must be 1 letter + 6 numbers.", "error")
        return redirect(url_for('pages_blueprint.sign_in_page'))

    # Busca dados do usuário no phonebook
    user_data = get_user_data_from_phonebook(sid)
    if not user_data:
        flash("Could not retrieve user data. Please verify your SID.", "error")
        return redirect(url_for('pages_blueprint.sign_in_page'))

    client_ip = get_client_ip()
    name_full = user_data["nameFull"]
    email = user_data["email"]
    position_name = user_data["positionName"]

    # Verifica se o SID já existe no banco
    existing_user = get_user_by_sid(sid)

    if existing_user:
        # SID existe — verifica se o IP é o mesmo
        if existing_user["IP_Address"] == client_ip:
            # IP igual → entra direto na aplicação
            session['authenticated'] = True
            session['user_sid'] = sid
            session['user_name'] = existing_user["Name"]
            session['user_email'] = existing_user["Email"]
            session['user_role'] = existing_user["Role"]
            return redirect(url_for('pages_blueprint.dashboard'))
        else:
            # IP diferente → atualiza IP e pede 2FA
            upsert_user(sid, name_full, email, position_name, client_ip)
            return _initiate_2fa(sid, email, name_full)
    else:
        # SID não existe no DB → insere e pede 2FA
        upsert_user(sid, name_full, email, position_name, client_ip)
        return _initiate_2fa(sid, email, name_full)


@blueprint.route('/verify-2fa', methods=['POST'])
def verify_2fa():
    """
    Verifica o código 2FA inserido pelo usuário.

    Recebe o código via form ou JSON e valida contra o banco.
    """
    sid = session.get('pending_sid')

    if not sid:
        flash("Session expired. Please try again.", "error")
        return redirect(url_for('pages_blueprint.sign_in_page'))

    # Aceita tanto form data quanto JSON
    if request.is_json:
        data = request.get_json()
        code = data.get('code', '').strip()
    else:
        code = request.form.get('code', '').strip()

    if not code or len(code) != 6:
        if request.is_json:
            return jsonify({"success": False, "message": "Please enter a valid 6-digit code."}), 400
        flash("Please enter a valid 6-digit code.", "error")
        return redirect(url_for('pages_blueprint.two_factor_page'))

    # Verifica o código no banco
    is_valid, message = verify_code(sid, code)

    if is_valid:
        # Código válido → autentica o usuário
        user = get_user_by_sid(sid)
        session.pop('pending_sid', None)
        session.pop('masked_email', None)
        session.pop('masked_phone', None)
        session['authenticated'] = True
        session['user_sid'] = sid
        session['user_name'] = user["Name"] if user else ""
        session['user_email'] = user["Email"] if user else ""
        session['user_role'] = user["Role"] if user else ""

        if request.is_json:
            return jsonify({"success": True, "redirect": url_for('pages_blueprint.dashboard')})
        return redirect(url_for('pages_blueprint.dashboard'))
    else:
        # Código inválido
        if request.is_json:
            return jsonify({"success": False, "message": message}), 400
        flash(message, "error")
        return redirect(url_for('pages_blueprint.two_factor_page'))


@blueprint.route('/resend-code', methods=['POST'])
def resend_code():
    """Reenvia o código de verificação 2FA."""
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

    email = user["Email"]
    name = user["Name"]

    # Gera novo código
    code = generate_verification_code()
    expires_at = datetime.now() + timedelta(minutes=CODE_EXPIRY_MINUTES)
    save_verification_code(sid, code, expires_at)

    # Envia email
    email_sent = send_verification_email(email, code, name)

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
    """Página principal da aplicação após autenticação."""
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/index.html', segment='index')


@blueprint.route('/logout')
def logout():
    """Encerra a sessão do usuário."""
    session.clear()
    return redirect(url_for('pages_blueprint.sign_in_page'))


@blueprint.route('/user-info')
def user_info():
    """Retorna informações do usuário autenticado (API JSON)."""
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
# ROTA GENÉRICA — TEMPLATES (deve ser a ÚLTIMA rota definida)
# ==============================================================================

@blueprint.route('/<template>')
def route_template(template):
    """Serve qualquer template HTML da pasta pages/."""
    try:
        if not template.endswith('.html'):
            template += '.html'

        segment = get_segment(request)
        return render_template("pages/" + template, segment=segment)

    except TemplateNotFound:
        return render_template('pages/error-404.html'), 404

    except Exception:
        return render_template('pages/error-500.html'), 500


# ==============================================================================
# FUNÇÕES AUXILIARES — INTERNAS
# ==============================================================================

def _initiate_2fa(sid, email, name):
    """Inicia o fluxo de 2FA: gera código, envia email, redireciona."""
    code = generate_verification_code()
    expires_at = datetime.now() + timedelta(minutes=CODE_EXPIRY_MINUTES)

    # Salva código no banco
    save_verification_code(sid, code, expires_at)

    # Envia email de verificação
    email_sent = send_verification_email(email, code, name)

    if not email_sent:
        flash("Failed to send verification email. Please try again.", "error")
        return redirect(url_for('pages_blueprint.sign_up_page'))

    # Salva dados na sessão para a página 2FA
    session['pending_sid'] = sid
    session['masked_email'] = get_masked_email(email)
    session['masked_phone'] = get_masked_phone()

    return redirect(url_for('pages_blueprint.two_factor_page'))


def get_segment(request):
    """Extrai o nome da página atual da URL."""
    try:
        segment = request.path.split('/')[-1]
        if segment == '':
            segment = 'index'
        return segment
    except Exception:
        return None