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
    
    register_extensions(app)
    register_blueprints(app)
    configure_database(app)
    return app
