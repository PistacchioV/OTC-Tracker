"""Os JSON que a tela le: o caminho, o diagnostico, e o mapa do Subjacente.

Duas falhas da mesma familia — a tela abre, a API responde 200 e nao ha dado:

  1. `_conf_subjacente_map` montava o caminho do `__file__` e apontava para
     `apps/Subjacente.json`, um arquivo que NAO EXISTE (o real esta em
     `apps/static/data/`). O `getmtime` estourava, a funcao devolvia `{}` e TODA
     operacao saia com "Ativo X sem cadastro no Subjacente (bolsa/fator
     ausentes)" — inclusive as cadastradas. O mapa nunca teve uma linha;
  2. o Index B3 lia quatro JSON num `Promise.all` cru: um 404, um corpo vazio e
     um JSON que nao e lista davam a MESMA tela (os selects so com o
     placeholder), e bastava um falhar para os outros tres se perderem junto.

O que este script prova:

  - o mapa do Subjacente sai do `data_path` e tem registros de verdade;
  - nenhum modulo de `apps/` volta a montar caminho de DADO pelo `__file__`;
  - o `/api/data-files/status` diz de onde cada arquivo veio, e separa "existe"
    de "serve" (um `[]` de 2 bytes existe, tem data e nao enche select nenhum);
  - o Index B3 nomeia o arquivo e o motivo em vez de ficar em branco.
"""
import ast
import io
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))

from apps.pages import routes as R                         # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('== 1. o mapa do Subjacente ==')
_mapa = R._conf_subjacente_map()
# Zero e o sintoma: o mapa vazio faz TODA operacao avisar "sem cadastro".
check('tem registros', len(_mapa) > 1000, True)
check('e resolve um ativo de commodity', bool(_mapa.get('CTZ6')), True)
check('   com bolsa e fator', sorted((_mapa.get('CTZ6') or {}).keys()),
      ['bolsa', 'fator', 'mercadoria'])

print('\n== 2. nenhum caminho de DADO sai do __file__ ==')
# O `data_paths` existe para isto: caminho montado do `__file__` amarra o dado
# ao diretorio do CODIGO, e na instancia do JPM as duas pastas nao sao a mesma.
# Codigo e asset (sidenav.html, sw-push.js, o logo do e-mail) continuam
# valendo — o que nao pode e JSON de dado.
_DADOS = ('Subjacente.json', 'VCP.json', 'Dominio.json', 'SwapIndex.json',
          'RefData.json', 'CounterpartyDetails.json', 'anbima.json',
          'holiday-calendars.json')
_maus = []


def _subarvore(no):
    """Todo Name e todo Constant de string dentro de uma expressao."""
    nomes, textos = set(), set()
    for x in ast.walk(no):
        if isinstance(x, ast.Name):
            nomes.add(x.id)
        elif isinstance(x, ast.Constant) and isinstance(x.value, str):
            textos.add(x.value)
    return nomes, textos


# Por AST, e nao por texto: a busca textual acusa o COMENTARIO que explica o
# bug (e o `check` passaria a exigir que ninguem escreva sobre ele). O que
# importa e a EXPRESSAO — uma chamada que junta `__file__` com o nome de um
# arquivo de dado.
for _raiz, _dirs, _arqs in os.walk(os.path.join(ROOT, 'apps')):
    _dirs[:] = [d for d in _dirs if d not in ('__pycache__', 'static', 'templates')]
    for _a in _arqs:
        if not _a.endswith('.py') or _a.endswith(' 2.py'):
            continue
        _p = os.path.join(_raiz, _a)
        try:
            _arv = ast.parse(io.open(_p, encoding='utf-8').read())
        except SyntaxError:
            continue
        for _no in ast.walk(_arv):
            if not isinstance(_no, (ast.Call, ast.BinOp, ast.JoinedStr)):
                continue
            _nomes, _textos = _subarvore(_no)
            if '__file__' not in _nomes:
                continue
            _casou = sorted(_textos & set(_DADOS))
            if _casou:
                _maus.append('%s:%d (%s)' % (os.path.relpath(_p, ROOT),
                                             getattr(_no, 'lineno', 0), _casou[0]))
check('nenhum JSON de dado montado pelo __file__', sorted(set(_maus)), [])

print('\n== 3. o endpoint de diagnostico ==')
from apps import create_app                                # noqa: E402
from apps.config import DebugConfig                        # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True
cl = app.test_client()
check('sem sessao devolve 401', cl.get('/api/data-files/status').status_code, 401)
with cl.session_transaction() as s:
    s.update(authenticated=True, user_sid='X1', user_name='X', user_role='BO',
             user_email='x@x', session_expires_at=(datetime.now() + timedelta(days=1)).isoformat())
_d = cl.get('/api/data-files/status').get_json()
check('responde', bool(_d and _d.get('success')), True)
# As tres raizes: sem elas, a mesma resposta vinda da dev e da instancia se
# parece, e o diagnostico nao diz de qual ambiente saiu.
for _k in ('data_dir', 'packaged_dir', 'same_folder', 'database_dir', 'shared_drive_root'):
    check('traz ' + _k, _k in _d, True)
_arqs = {f['file']: f for f in _d['files']}
check('cobre o Subjacente', 'Subjacente.json' in _arqs, True)
check('   e diz de onde veio', _arqs['Subjacente.json']['from'] in ('DATA_DIR', 'packaged'), True)
# "existe" e "serve" sao coisas diferentes: um `[]` de 2 bytes existe.
check('   e quantos registros tem', _arqs['Subjacente.json']['records'] > 1000, True)
check('traz o tamanho do mapa do gerador',
      _d.get('subjacente_map_size') == len(_mapa), True)

print('\n== 4. o Index B3 nomeia a falha ==')
_tpl = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'index-b3.html'),
               encoding='utf-8').read()
check('nao ha mais Promise.all cru sobre os fetch',
      "fetch('{{ config.ASSETS_ROOT }}/data/Subjacente.json').then(r => r.json())," in _tpl, False)
for _motivo in ('HTTP ', 'arquivo vazio', 'não é uma lista', 'não é JSON'):
    check('reporta: ' + _motivo.strip(), _motivo in _tpl, True)
check('e o aviso fica na TELA, nao num alert',
      'mostraFalha' in _tpl and "alert('Failed to load reference data" not in _tpl, True)
check('e aponta o diagnostico', '/api/data-files/status' in _tpl, True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
