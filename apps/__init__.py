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


# O que o código exige do `config.py` para subir. A lista é curta de propósito:
# são as chaves que módulos de fora leem direto do `Config` (e não do
# `app.config`), então uma que falte só se manifesta no import daquele módulo.
# Nome novo aqui é nome novo no config — acrescente ao acrescentar.
_REQUIRED_CONFIG_NAMES = (
    'DATABASE_DIR',            # a pasta de TODOS os bancos (manual_conf, routes, recon_comitente)
    'DATABASE_PATH',           # o DuckDB de usuários
    'NOTIFICATIONS_DATABASE_PATH',   # o DuckDB das notificações (separado — §4)
    'DATABASE_ACCESS_PATHS',   # a lista que o validate_database_paths confere
    'SHARED_DRIVE_ROOT',       # a raiz do share
    'DATA_DIR',                # a pasta dos JSON (cache, cadastros, tickets)
)


def _require_config_names(cfg):
    """Recusa subir com um `config.py` anterior ao código, dizendo o que falta."""
    faltando = [nome for nome in _REQUIRED_CONFIG_NAMES if nome not in cfg]
    if not faltando:
        return
    raise RuntimeError(
        'apps/config.py esta desatualizado: faltam ' + ', '.join(faltando) + '. '
        'O arquivo costuma ficar modificado localmente na instancia, e nesse caso '
        'o `git pull` nao o sobrescreve. Confira com `git status apps/config.py` e '
        'traga a versao do repositorio (`git checkout -- apps/config.py`, ou guarde '
        'o seu ajuste com `git stash` antes). Reinicie o Flask depois: o reloader '
        'esta desligado na instancia do time.'
    )


def _seed_data_dir(app):
    """Copia para o `DATA_DIR` o que vem versionado no repositório e ainda não
    está lá.

    Na dev as duas pastas são a MESMA e isto não faz nada. Na instância do JPM o
    `DATA_DIR` aponta para o share, que numa subida nova está vazio: sem este
    passo os cadastros do /mapping voltariam à seed, o `anbima.json` sumiria e o
    File Interpreter abriria sem template nenhum — tudo sem erro, porque cada um
    desses arquivos tem um caminho "arquivo ausente" que devolve vazio.

    NUNCA sobrescreve: o arquivo que já está no share é o que a mesa editou pela
    tela, e ele vence a cópia do repositório. É por isso que a operação é
    idempotente e pode rodar em toda subida.
    """
    import shutil
    from apps.pages.data_paths import PACKAGED_DIR

    destino = app.config.get('DATA_DIR')
    if not destino or os.path.normpath(destino) == PACKAGED_DIR:
        return
    copiados = 0
    for raiz, _dirs, arquivos in os.walk(PACKAGED_DIR):
        rel = os.path.relpath(raiz, PACKAGED_DIR)
        # O `db/` é do `DATABASE_DIR`, que tem a sua própria configuração — e
        # copiar banco por cima de banco é o tipo de ajuda que corrompe dado.
        if rel.split(os.sep)[0] == 'db':
            continue
        alvo_dir = os.path.join(destino, rel) if rel != '.' else destino
        for nome in arquivos:
            # `.bak` e `.lock` são sujeira local de quem desenvolve, não dado.
            if nome.endswith(('.bak', '.lock')):
                continue
            alvo = os.path.join(alvo_dir, nome)
            if os.path.exists(alvo):
                continue
            try:
                os.makedirs(alvo_dir, exist_ok=True)
                shutil.copy2(os.path.join(raiz, nome), alvo)
                copiados += 1
            except OSError:
                app.logger.warning('[data-dir] não consegui copiar %s', alvo)
    if copiados:
        app.logger.info('[data-dir] %d arquivo(s) versionado(s) copiado(s) para %s',
                        copiados, destino)


def create_app(config):
    app = Flask(__name__)
    app.config.from_object(config)

    # Recusa subir uma instância de PRODUÇÃO sem `SECRET_KEY` explícita: sem ela
    # a config cai numa chave aleatória, e aí todo cookie de sessão é invalidado
    # a cada restart — a pessoa é deslogada sem motivo aparente, e o defeito não
    # se parece com configuração faltando.
    #
    # "É produção?" tem DUAS respostas no app, e elas podiam discordar: o
    # `app.config['DEBUG']`, que depende de qual objeto de config o chamador
    # passou, e a variável de ambiente `DEBUG`, que é o jeito DOCUMENTADO de
    # escolher o modo (`set DEBUG=False`, ver o topo do `run.py`). Um chamador
    # que passe o `Config` base — sem `DEBUG` nenhum — cai aqui mesmo tendo
    # `DEBUG=True` no ambiente, e o start de debug morre pedindo uma chave que
    # o modo debug não precisa. A pergunta passa a ser uma só: se QUALQUER uma
    # das duas diz debug, não é produção.
    _debug_env = os.getenv('DEBUG', '').strip().lower() in ('1', 'true', 'yes', 'on')
    if not app.config.get('DEBUG', False) and not _debug_env and not os.getenv('SECRET_KEY'):
        raise RuntimeError(
            'SECRET_KEY environment variable is required in production. '
            'Para rodar em DEBUG, defina DEBUG=True no ambiente (ou passe o '
            'DebugConfig para o create_app); para produção, defina SECRET_KEY '
            'no .env.')

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

    # O `config.py` é o arquivo que mais fica para trás numa instância — é o que
    # se ajusta à mão, então um `git pull` não o sobrescreve e ele continua o de
    # antes enquanto o resto do código já é o novo. Sem esta conferência a falha
    # aparece como um `AttributeError` no meio de um import de módulo, a vinte
    # frames de distância, sem dizer que arquivo está velho nem o que fazer.
    _require_config_names(app.config)

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

    # Antes dos blueprints: o `routes` resolve os caminhos de dados no IMPORT, e
    # vários módulos leem cadastro logo na subida. Semear depois seria semear
    # tarde.
    _seed_data_dir(app)

    register_extensions(app)
    register_blueprints(app)
    configure_database(app)
    return app
