from flask import Flask
from importlib import import_module
from werkzeug.middleware.proxy_fix import ProxyFix


apps = ('pages',)


def register_blueprints(app):
    for module_name in apps:
        module = import_module('apps.{}.routes'.format(module_name))
        app.register_blueprint(module.blueprint)


def create_app(config):
    app = Flask(__name__)
    app.config.from_object(config)

    # Single reverse proxy in front of the app (127.0.0.1:9443). Trust exactly
    # one X-Forwarded-For hop so get_client_ip() reads the real client IP from
    # the rightmost trusted value instead of a client-spoofable header. Without
    # this, an attacker could forge X-Forwarded-For to match a stored IP and
    # bypass 2FA.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True
    app.jinja_env.cache = {}

    register_blueprints(app)
    return app
