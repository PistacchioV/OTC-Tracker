import os

# Load .env BEFORE importing apps.config — config reads os.getenv() at import
# time (e.g. SECRET_KEY). Under Gunicorn the .env is not auto-loaded like it is
# with `flask run`, so without this the SECRET_KEY falls back to a random value
# on every startup, invalidating all session cookies (breaks "Keep me signed
# in" across restarts).
from dotenv import load_dotenv
load_dotenv()

from   flask_migrate import Migrate
from   flask_minify  import Minify
from   sys import exit

from apps.config import config_dict
from apps import create_app, db

# WARNING: Don't run with debug turned on in production!
DEBUG = True

# The configuration
get_config_mode = 'Debug' if DEBUG else 'Production'

try:
    # Load the configuration using the default values
    app_config = config_dict[get_config_mode.capitalize()]
    
except KeyError:
    exit('Error: Invalid <config_mode>. Expected values [Debug, Production] ')

app = create_app(app_config)
Migrate(app, db)

# Disable all caching in development
if DEBUG:
    # Disable template caching
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.cache = {}

    app.logger.info('DEBUG            = ' + str(DEBUG))
    app.logger.info('Page Compression = FALSE')
    app.logger.info('DBMS             = ' + app_config.SQLALCHEMY_DATABASE_URI)
    app.logger.info('ASSETS_ROOT      = ' + app_config.ASSETS_ROOT )
    app.logger.info('Template Cache   = DISABLED')

if __name__ == "__main__":
    app.run()
