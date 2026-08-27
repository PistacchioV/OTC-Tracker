# -*- coding: utf-8 -*-
"""O link.txt, os dois arquivos do card e a lista de usuários ativos."""
import json
import os
import traceback

from apps.config import Config
from apps.pages.features.appver import domain


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`.

    `_DAILY_METRIC_DIR`, `APP_PORT`, o `get_db_connection` e o
    `_atomic_write_json` são plataforma e moram no `routes`; e os testes trocam
    atributos lá (`R.DB_PATH = tmp`).
    """
    from apps.pages import routes
    return routes


# `link.txt` mora na pasta Application, e o caminho dela pende do
# `SHARED_DRIVE_ROOT` — nunca de um literal `I:\...` ou `\\servidor\...`, que
# ficaria preso na letra mapeada no dia em que a instância passasse a falar com o
# UNC (CLAUDE.md §8, e o `check_config_names` recusa por AST).
LINK_FILE = os.environ.get('OTC_VERSION_FILE', '').strip() or os.path.join(
    Config.SHARED_DRIVE_ROOT, 'Confirmation', 'Derivativos', 'OTC Tracker',
    'Application', 'link.txt')

# Os dois endereços da aplicação, para o passo 3 do e-mail. NÃO saem do
# `_otc_app_url`: aquele monta `http://<hostname>:8050`, e o hostname é o de
# QUEM ENVIA — cada pessoa roda a própria instância na própria máquina, então o
# endereço do remetente não abre nada para quem recebe. O e-mail saía com
# `http://chcd293c37n1:8050`, que é a máquina de uma pessoa só.
#
# São dois porque servem a momentos diferentes: o atalho interno é o que se
# digita de memória, e o localhost é o que funciona quando o atalho não resolve
# (é a instância que a pessoa acabou de subir).
SHORTCUT = os.environ.get('OTC_TRACKER_SHORTCUT', '').strip() or 'go/otctracker'


def local_url():
    return (os.environ.get('OTC_TRACKER_LOCAL_URL', '').strip()
            or 'http://localhost:{}'.format(_routes().APP_PORT))


def metric_dir():
    return _routes()._DAILY_METRIC_DIR


def recipients_file():
    return os.path.join(metric_dir(), 'app_version_recipients.json')


def status_file():
    return os.path.join(metric_dir(), 'app_version_status.json')


def read_link(path=None):
    """(versao, texto_lido, erro) do `link.txt`.

    A leitura tenta utf-8 e cai para latin-1: o arquivo é escrito no Windows e
    um acento em cp1252 estouraria a decodificação — perder o acento é melhor do
    que não ler a versão.
    """
    alvo = path or LINK_FILE
    try:
        with open(alvo, 'rb') as fh:
            bruto = fh.read()
    except Exception as e:                                  # noqa: BLE001
        return ('', '', '{}: {}'.format(type(e).__name__, e))
    try:
        texto = bruto.decode('utf-8')
    except UnicodeDecodeError:
        texto = bruto.decode('latin-1', 'replace')
    texto = texto.strip()
    versao, erro = domain.parse_link(texto)
    return (versao, texto, erro)


def active_users():
    """[(nome, e-mail)] de quem está ATIVO no cadastro de usuários.

    `Active` é o status da tela de Users & Roles, e a comparação é normalizada
    porque o valor é gravado por um `select` mas pode ter vindo de importação
    antiga. `Pending` (quem se cadastrou e ainda não foi aprovado) e `Inactive`
    ficam de fora: o aviso é para quem usa a ferramenta.

    Só leitura — `readonly=True`, senão a consulta entra na fila de escrita
    (CLAUDE.md §4).
    """
    conn = _routes().get_db_connection(readonly=True)
    try:
        linhas = conn.execute(
            "SELECT Name, Email FROM users "
            "WHERE UPPER(TRIM(COALESCE(Status,''))) = 'ACTIVE' "
            "  AND COALESCE(TRIM(Email),'') <> '' "
            "ORDER BY Name"
        ).fetchall()
    finally:
        conn.close()
    saida, vistos = [], set()
    for nome, email in linhas:
        chave = str(email or '').strip().lower()
        if chave and chave not in vistos:
            vistos.add(chave)
            saida.append((str(nome or '').strip(), str(email or '').strip()))
    return saida


def load_recipients():
    try:
        with open(recipients_file(), encoding='utf-8') as fh:
            d = json.load(fh)
        if isinstance(d, dict):
            return {'cc': d.get('cc', '') or ''}
    except Exception:                                       # noqa: BLE001
        pass
    return {'cc': ''}


def save_recipients(d):
    os.makedirs(metric_dir(), exist_ok=True)
    atual = load_recipients()
    if 'cc' in (d or {}):
        atual['cc'] = str((d or {}).get('cc') or '').strip()
    _routes()._atomic_write_json(recipients_file(), atual)


def write_status(result, when):
    R = _routes()
    try:
        os.makedirs(metric_dir(), exist_ok=True)
        R._atomic_write_json(status_file(),
                             {'result': result, 'at': when.strftime('%d/%m/%Y %H:%M:%S')})
    except Exception:                                       # noqa: BLE001
        R.log.warning('[app-version] não consegui gravar o status:\n%s', traceback.format_exc())


def read_status():
    try:
        with open(status_file(), encoding='utf-8') as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:                                       # noqa: BLE001
        return {}
