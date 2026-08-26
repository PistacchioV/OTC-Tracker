import os, secrets
from datetime import timedelta


def _absolute_path_from_environment(variable_name, default_path):
    """Resolve an optional environment path and require an absolute value."""
    configured_path = os.getenv(variable_name, default_path)
    if not os.path.isabs(configured_path):
        raise ValueError('{} must be an absolute path'.format(variable_name))
    return os.path.normpath(configured_path)


class Config(object):

    basedir = os.path.abspath(os.path.dirname(__file__))

    # Assets Management
    ASSETS_ROOT = os.getenv('ASSETS_ROOT', '/static')  
    
    # Set up the App SECRET_KEY. Fall back to a cryptographically secure random
    # key (only suitable for dev — production must set SECRET_KEY; enforced in
    # create_app). random.choice()/ascii_lowercase was neither strong nor
    # stable across restarts.
    SECRET_KEY  = os.getenv('SECRET_KEY', None)
    if not SECRET_KEY:
        SECRET_KEY = secrets.token_hex(32)

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Reject oversized request bodies before they are read into memory. Uploads
    # (.msg / .xlsx) are read fully into RAM and handed to extract_msg / openpyxl
    # / pandas, so without a cap a small zip-bomb xlsx can OOM the worker.
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB

    # SameSite blocks the session cookie from riding cross-site POST/fetch
    # requests — the main defense against CSRF while token-based protection is
    # not wired app-wide. Applied in every environment (works over HTTP too).
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SAMESITE = 'Lax'

    DB_ENGINE   = os.getenv('DB_ENGINE'   , None)
    DB_USERNAME = os.getenv('DB_USERNAME' , None)
    DB_PASS     = os.getenv('DB_PASS'     , None)
    DB_HOST     = os.getenv('DB_HOST'     , None)
    DB_PORT     = os.getenv('DB_PORT'     , None)
    DB_NAME     = os.getenv('DB_NAME'     , None)

    # ══ AMBIENTE — o único bloco que difere entre as branches ═════════════════
    #
    # `visual-refresh` (desenvolvimento) aponta para dentro da aplicação;
    # `visual-refresh-prod` (instância do JPM) aponta para o share. É a ÚNICA
    # diferença entre as duas, e ela mora aqui de propósito: o resto do código
    # pergunta ao Config e não sabe onde os bancos estão.
    #
    # Os dois continuam podendo ser trocados por variável de ambiente
    # (`OTC_DATABASE_DIR`, `OTC_SHARED_DRIVE_ROOT`) sem tocar no arquivo.
    #
    # ── ENV:DEV ──────────────────────────────────────────────────────────────
    _DATA_DIR_DEFAULT = os.path.join(basedir, 'static', 'data')
    _DATABASE_DIR_DEFAULT = os.path.join(basedir, 'static', 'data', 'db')
    _SHARED_DRIVE_DEFAULT = 'I:\\'
    _SQLITE_DIR_DEFAULT = basedir
    # ── /ENV ─────────────────────────────────────────────────────────────────

    # A PASTA dos bancos, e é dela que sai todo caminho de banco do app — o
    # `Users_OTCTracker.db` das rotas, os três do Pending Confirmation, os dois
    # da esteira e o de comitentes. Cada módulo montava o caminho por conta
    # própria a partir do diretório do pacote, e mover o banco exigia achar os
    # quatro lugares; agora é este.
    DATABASE_DIR = _absolute_path_from_environment('OTC_DATABASE_DIR', _DATABASE_DIR_DEFAULT)

    # Primary DuckDB file used by the route layer. Set DATABASE_PATH to move
    # only this one; DATABASE_DIR move todos de uma vez.
    DATABASE_PATH = _absolute_path_from_environment(
        'DATABASE_PATH',
        os.path.join(DATABASE_DIR, 'Users_OTCTracker.db'),
    )

    # Root of the JPM shared drive used by file-processing routes. Individual
    # route settings can still override their specific directory.
    SHARED_DRIVE_ROOT = _absolute_path_from_environment('OTC_SHARED_DRIVE_ROOT',
                                                        _SHARED_DRIVE_DEFAULT)

    # A pasta dos DADOS em JSON — os arquivos-dia do cache, os cadastros do
    # /mapping, os tickets, o RefData, o calendário. É o terceiro caminho que
    # muda de lugar entre a dev e a instância do JPM, ao lado do `DATABASE_DIR`
    # e do `SHARED_DRIVE_ROOT`.
    #
    # Ela existe porque o cache é GITIGNORADO: um checkout novo não traz nenhum
    # arquivo-dia, e os módulos montavam esse caminho a partir do próprio
    # `__file__` — então a instância do JPM lia a pasta do CÓDIGO, que numa
    # máquina recém-atualizada está vazia. O sintoma é o pior possível: a tela
    # abre, as APIs respondem 200 e os gráficos vêm sem nada, como se não
    # houvesse operação no dia.
    #
    # A LEITURA cai para a cópia empacotada quando o arquivo não existe aqui
    # (ver `apps/pages/data_paths.py`): é o que mantém funcionando o que vem
    # versionado no repositório — `anbima.json`, `Subjacente.json`, as seeds dos
    # cadastros — sem exigir que alguém as copie para o share antes de subir.
    DATA_DIR = _absolute_path_from_environment('OTC_DATA_DIR', _DATA_DIR_DEFAULT)

    USE_SQLITE  = True

    DATABASE_LOCAL_SEMAPHORE_TIMEOUT_SECONDS = float(
        os.getenv('DATABASE_LOCAL_SEMAPHORE_TIMEOUT_SECONDS', '15')
    )
    DATABASE_READ_LOCK_TIMEOUT_SECONDS = float(os.getenv('DATABASE_READ_LOCK_TIMEOUT_SECONDS', '15'))
    DATABASE_WRITE_LOCK_TIMEOUT_SECONDS = float(os.getenv('DATABASE_WRITE_LOCK_TIMEOUT_SECONDS', '30'))
    DATABASE_SQLITE_BUSY_TIMEOUT_SECONDS = int(os.getenv('DATABASE_SQLITE_BUSY_TIMEOUT_SECONDS', '10000'))
    DATABASE_SLOW_LOCK_WARNING_SECONDS = float(os.getenv('DATABASE_SLOW_LOCK_WARNING_SECONDS', '5'))
    DATABASE_LOCK_RETRY_LIMIT = int(os.getenv('DATABASE_LOCK_RETRY_LIMIT', '4'))
    DATABASE_READ_CONCURRENCY = int(os.getenv('DATABASE_READ_CONCURRENCY', '4'))
    # Todo banco que o app abre. É esta lista que o `validate_database_paths`
    # confere na subida (pasta gravável + arquivo de lock), então um banco que
    # não estiver aqui só acusa problema no primeiro request que o abrir.
    # O banco das NOTIFICAÇÕES é separado do de usuários de propósito. O lock
    # desta camada é por ARQUIVO: enquanto os quatro conviviam num só, cada
    # gravação de notificação — e elas acontecem a cada ação de qualquer pessoa —
    # segurava o arquivo inteiro, e com ele o login, a allowlist e a gestão de
    # usuários. O sino ainda consulta por aba aberta. Separados, o tráfego de
    # notificação não encosta em quem está entrando no app.
    NOTIFICATIONS_DATABASE_PATH = _absolute_path_from_environment(
        'OTC_NOTIFICATIONS_DATABASE_PATH',
        os.path.join(DATABASE_DIR, 'Notifications_OTCTracker.db'),
    )

    DATABASE_ACCESS_PATHS = (
        DATABASE_PATH,
        NOTIFICATIONS_DATABASE_PATH,
        os.path.join(DATABASE_DIR, 'pending-confirmation-backlog.db'),
        os.path.join(DATABASE_DIR, 'pending-confirmation-pending.db'),
        os.path.join(DATABASE_DIR, 'pending-confirmation-ok.db'),
        os.path.join(DATABASE_DIR, 'manual_confirmations_pending.db'),
        os.path.join(DATABASE_DIR, 'manual_confirmations_ok.db'),
        os.path.join(DATABASE_DIR, 'matching_comitentes.db'),
        os.path.join(DATABASE_DIR, 'cgd_sharepoint.db'),
        os.path.join(_SQLITE_DIR_DEFAULT, 'db.sqlite3'),
    )

    # try to set up a Relational DBMS
    if DB_ENGINE and DB_NAME and DB_USERNAME:

        try:
            
            # Relational DBMS: PSQL, MySql
            SQLALCHEMY_DATABASE_URI = '{}://{}:{}@{}:{}/{}'.format(
                DB_ENGINE,
                DB_USERNAME,
                DB_PASS,
                DB_HOST,
                DB_PORT,
                DB_NAME
            ) 

            USE_SQLITE  = False

        except Exception as e:

            print('> Error: DBMS Exception: ' + str(e) )
            print('> Fallback to SQLite ')    

    if USE_SQLITE:

        # O MESMO caminho que entra no DATABASE_ACCESS_PATHS: com os dois
        # escritos à mão, o gerenciador de lock guardava um arquivo e o ORM
        # abria outro — e nada acusaria isso.
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(_SQLITE_DIR_DEFAULT, 'db.sqlite3')


class ProductionConfig(Config):
    DEBUG = False

    # Security
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    # Only send the auth cookies over HTTPS (prod runs behind the TLS proxy).
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_DURATION = 3600
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)

class DebugConfig(Config):
    DEBUG = True
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)

# Load all possible configurations
config_dict = {
    'Production': ProductionConfig,
    'Debug'     : DebugConfig
}