import os
import logging

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from importlib import import_module
from werkzeug.middleware.proxy_fix import ProxyFix


db = SQLAlchemy()

def register_extensions(app):
    db.init_app(app)

apps = ('pages',)

def register_blueprints(app):
    for module_name in apps:
        module = import_module('apps.{}.routes'.format(module_name))
        app.register_blueprint(module.blueprint)


def configure_database(app):
    """Configure database initialization and teardown."""
    
    # Initialize database tables on app startup (not per request)
    with app.app_context():
        try:
            db.create_all()
            app.logger.info('Database tables created successfully')
        except Exception as e:
            app.logger.error(f'Database initialization error: {str(e)}')
            
            # Only fallback to SQLite in development mode
            if app.config.get('DEBUG', False):
                basedir = os.path.abspath(os.path.dirname(__file__))
                fallback_uri = 'sqlite:///' + os.path.join(basedir, 'db.sqlite3')
                app.config['SQLALCHEMY_DATABASE_URI'] = fallback_uri
                
                app.logger.warning('Fallback to SQLite in development mode')
                db.create_all()
            else:
                # In production, don't fallback - raise the error
                raise

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        """Clean up database session."""
        db.session.remove()


def create_app(config):
    app = Flask(__name__)
    app.config.from_object(config)

    # Refuse to boot a production instance without an explicit SECRET_KEY: the
    # config falls back to an ephemeral random key otherwise, which silently
    # invalidates every session cookie on each restart and hides a misconfig.
    if not app.config.get('DEBUG', False) and not os.getenv('SECRET_KEY'):
        raise RuntimeError('SECRET_KEY environment variable is required in production')

    # Single reverse proxy in front of the app (127.0.0.1:9443). Trust exactly
    # one X-Forwarded-For hop so get_client_ip() reads the real client IP from
    # the rightmost trusted value instead of a client-spoofable header. Without
    # this, an attacker could forge X-Forwarded-For to match a stored IP and
    # bypass 2FA.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    # Configure templates for environment
    if not app.config.get('DEBUG', False):
        # Production settings
        app.config['TEMPLATES_AUTO_RELOAD'] = False
    else:
        # Development settings - force templates to reload
        app.config['TEMPLATES_AUTO_RELOAD'] = True
        app.jinja_env.auto_reload = True
        app.jinja_env.cache = {}
    
    # Camada de lock/transação dos bancos de ARQUIVO (os DuckDB/SQLite avulsos:
    # usuários, Pending Confirmation, esteira manual, comitentes). Ela é
    # configurada AQUI, e antes dos blueprints, por duas razões:
    #
    #   · `configure_database_access` grava um global do módulo. Sem esta
    #     chamada os `DATABASE_*` do `config.py` não valem nada — o módulo cai
    #     nos defaults dele e o ajuste de timeout feito na configuração não tem
    #     efeito nenhum, sem erro em lugar nenhum;
    #   · `validate_database_paths` cria o diretório e o `.lock` ao lado de cada
    #     banco. Falhar AQUI é o desejado: um lock que não pode ser escrito só
    #     apareceria no primeiro request que tentasse gravar, no meio de uma
    #     rotina, e como falha de banco.
    from apps.pages.database_access import (
        configure_database_access, validate_database_paths,
    )
    configure_database_access(app.config)
    validate_database_paths(tuple(app.config.get('DATABASE_ACCESS_PATHS') or ()))

    register_extensions(app)
    register_blueprints(app)
    configure_database(app)
    return app
