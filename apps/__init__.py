from flask import Flask
from importlib import import_module


apps = ('pages',)


def register_blueprints(app):
    for module_name in apps:
        module = import_module('apps.{}.routes'.format(module_name))
        app.register_blueprint(module.blueprint)


def create_app(config):
    app = Flask(__name__)
    app.config.from_object(config)

    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True
    app.jinja_env.cache = {}

    register_blueprints(app)
    return app
