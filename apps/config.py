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

    # Primary DuckDB file used by the route layer. Set DATABASE_PATH to move
    # the database outside the application directory.
    DATABASE_PATH = _absolute_path_from_environment(
        'DATABASE_PATH',
        os.path.join(basedir, 'static', 'data', 'db', 'Users_OTCTracker.db'),
    )

    # Root of the JPM shared drive used by file-processing routes. Individual
    # route settings can still override their specific directory.
    SHARED_DRIVE_ROOT = _absolute_path_from_environment('OTC_SHARED_DRIVE_ROOT', 'I:\\')

    USE_SQLITE  = True 

    DATABASE_LOCAL_SEMAPHORE_TIMEOUT_SECONDS = float(
        os.getenv('DATABASE_LOCAL_SEMAPHORE_TIMEOUT_SECONDS', '15')
    )
    DATABASE_READ_LOCK_TIMEOUT_SECONDS = float(os.getenv('DATABASE_READ_LOCK_TIMEOUT_SECONDS', '15'))
    DATABASE_WRITE_LOCK_TIMEOUT_SECONDS = float(os.getenv('DATABASE_WRITE_LOCK_TIMEOUT_SECONDS', '30'))
    DATABASE_SQLITE_BUSY_TIMEOUT_SECONDS = int(os.getenv('DATABASE_SQLITE_BUSY_TIMEOUT_SECONDS', '10000'))
    DATABASE_SLOW_LOCK_WARNING_SECONDS = float(os.getenv('DATABASE_SLOW_LOCK_WARNING_SECONDS', '5'))
    DATABASE_LOCK_RETRY_LIMIT = int(os.getenv('DATABASE_LOCK_RETRY_LIMIT', '2'))
    DATABASE_READ_CONCURRENCY = int(os.getenv('DATABASE_READ_CONCURRENCY', '4'))
    DATABASE_ACCESS_PATHS = (
        DATABASE_PATH,
        os.path.join(basedir, 'static', 'data', 'db', 'pending-confirmation-backlog.db'),
        os.path.join(basedir, 'static', 'data', 'db', 'pending-confirmation-pending.db'),
        os.path.join(basedir, 'static', 'data', 'db', 'pending-confirmation-ok.db'),
        os.path.join(basedir, 'static', 'data', 'db', 'manual_confirmations_pending.db'),
        os.path.join(basedir, 'static', 'data', 'db', 'manual_confirmations_ok.db'),
        os.path.join(basedir, 'static', 'data', 'db', 'matching_comitentes.db'),
        os.path.join(basedir, 'db.sqlite3'),
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

        # This will create a file in <app> FOLDER
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'db.sqlite3')
    
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
