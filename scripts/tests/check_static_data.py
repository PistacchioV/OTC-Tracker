"""O `/static/data/...` do navegador tem de sair do `DATA_DIR`, como o servidor.

Setenta e um `fetch` espalhados por quinze telas leem JSON por URL estatica
(`RefData.json`, `Subjacente.json`, `anbima.json`, os cadastros do /mapping).
Como URL estatica, o Flask os servia da pasta do CODIGO — enquanto o servidor
le e grava no `DATA_DIR`. Na dev as duas pastas sao a mesma e nada aparece; na
instancia do JPM nao sao, e a mesa editava o Reference Data pela tela, o app
gravava no share, e a tela recarregava mostrando a copia versionada. Nenhum
erro, dois arquivos.

Cobre tambem o motivo de a rota entregar RAIZ e caminho RELATIVO separados ao
`send_from_directory`: e o `safe_join` dele que recusa o `..`, e passar o
caminho ja resolvido anula a checagem.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

SHARE = tempfile.mkdtemp(prefix='static-data-share-')
os.environ['OTC_DATA_DIR'] = SHARE
os.environ.setdefault('SECRET_KEY', 'x')
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))

from apps.config import DebugConfig                       # noqa: E402
from apps.pages.data_paths import PACKAGED_DIR            # noqa: E402
from apps import create_app                               # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True
cl = app.test_client()

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('== 0. o cenario da instancia: DATA_DIR fora do checkout ==')
check('as duas pastas sao diferentes', DebugConfig.DATA_DIR == PACKAGED_DIR, False)

print('\n== 1. o que o app GRAVA e o que a tela LE ==')
with open(os.path.join(SHARE, 'RefData.json'), 'w', encoding='utf-8') as fh:
    json.dump([{'COUNTERPARTY': 'CLIENTE EDITADO NA TELA'}], fh)
r = cl.get('/static/data/RefData.json')
check('a tela recebe 200', r.status_code, 200)
check('e le o arquivo do DATA_DIR',
      [d.get('COUNTERPARTY') for d in r.get_json(force=True)], ['CLIENTE EDITADO NA TELA'])

print('\n== 2. o que so existe no repositorio continua servido ==')
r = cl.get('/static/data/anbima.json')          # versionado, nunca copiado ao share
check('cai para a copia empacotada', r.status_code, 200)
check('e vem com conteudo', len(r.data) > 1000, True)
check('subpasta tambem', cl.get('/static/data/mappings/mt300.json').status_code, 200)
check('inexistente e 404', cl.get('/static/data/naoexiste.json').status_code, 404)

print('\n== 3. o resto do /static nao muda ==')
check('js continua servido', cl.get('/static/js/table-std.js').status_code, 200)

print('\n== 4. o `..` da URL e recusado ==')
# O cliente de teste normaliza o caminho, entao o traversal precisa vir
# percent-encoded — que e exatamente como ele chegaria de fora.
for url in ('/static/data/%2e%2e/%2e%2e/config.py',
            '/static/data/..%2f..%2fconfig.py',
            '/static/data/..%2f..%2f..%2fapps%2fconfig.py'):
    r = cl.get(url)
    vazou = b'SECRET_KEY' in r.data or b'class Config' in r.data
    check('nao serve %s' % url[13:40], (r.status_code, vazou), (404, False))

shutil.rmtree(SHARE, ignore_errors=True)
print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
