# -*- coding: utf-8 -*-
"""O aviso do sino de um cadastro no Index B3 diz QUAL registro (§545).

O `/api/b3/*` serve o Reference Data e as quatro tabelas do Index B3
(Subjacente, VCP, Domínio, Swap Index). No Reference Data o aviso já dizia o
SPN e o nome; no Index B3 dizia só o nome INTERNO da tabela (`subj`), e o New
Item procurava TICKER/CODE/NAME, campos que nenhuma das quatro tem. Saía
`subj: ` vazio, e a mesa não sabia que ativo tinha sido cadastrado.

Prende:
  1. New Item, Item Updated e Item Deleted identificam o registro pelo código
     e pelo que diz o que ele é (`Underlying Asset KWZ6 · TRIGO · COMMODITIES`),
     nas quatro tabelas;
  2. o Reference Data não mudou (SPN + nome, o deep-link do sino depende disso).

Tudo num tmp; o sino é um espião.
"""
import os, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

TMP = tempfile.mkdtemp()

from apps.pages import routes as R                          # noqa: E402
from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True
R._B3_DATA_DIR = TMP

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def cliente(sid):
    c = app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = sid
        s['user_name'] = 'Fulano ' + sid
        s['user_role'] = 'BO'
        s['user_email'] = 'x@jpmorgan.com'
        s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


AVISOS = []
R._create_notification = lambda sid, nome, acao, pagina, detalhe='', *a, **k: AVISOS.append(
    (acao, pagina, detalhe))
R._user_can_access_page = lambda *a, **k: True
maker, checker = cliente('A111111'), cliente('B222222')

CASOS = [
    ('subj', {'Codigo do Ativo Subjacente': 'KWZ6', 'Commodity': 'TRIGO', 'Classe': 'COMMODITIES'},
     'Underlying Asset KWZ6 · TRIGO · COMMODITIES'),
    ('vcp', {'ID da Qualificação': '123', 'Descrição da Qualificação': 'IPCA'},
     'VCP 123 · IPCA'),
    ('dominio', {'Identificador Qualificacao': '104', 'Codigo TipoIF': 'CCB',
                 'Descricao Qualificacao': 'IGP-M'},
     'Domain 104 · CCB · IGP-M'),
    ('swapindex', {'Codigo Referencia Externa': 'C99', 'Nome Curva': 'PREFIXADO 252D'},
     'Swap Index C99 · PREFIXADO 252D'),
]

for tabela, campos, esperado in CASOS:
    print('\n== %s ==' % tabela)
    R._atomic_write_json(os.path.join(TMP, R._B3_FILE_MAP[tabela]), [])
    del AVISOS[:]
    r = maker.post('/api/b3/add', json={'table': tabela, 'fields': dict(campos)})
    check('add 200', r.status_code, 200)
    check('New Item diz o registro', AVISOS[-1],
          ('New Item', 'Index B3', esperado + ' (Pending approval)'))
    r = checker.post('/api/b3/update', json={'table': tabela, 'idx': 0, 'action': 'approve'})
    check('Item Updated diz o registro', AVISOS[-1],
          ('Item Updated', 'Index B3', esperado + ' — approve → ACTIVE'))
    r = maker.post('/api/b3/delete', json={'table': tabela, 'idx': 0})
    check('Item Deleted diz o registro', AVISOS[-1], ('Item Deleted', 'Index B3', esperado))

print('\n== registro sem o codigo ==')
R._atomic_write_json(os.path.join(TMP, R._B3_FILE_MAP['subj']), [])
maker.post('/api/b3/add', json={'table': 'subj', 'fields': {}})
check('vazio vira travessao, nunca some', AVISOS[-1][2], 'Underlying Asset — (Pending approval)')

print('\n== Reference Data nao mudou ==')
R._atomic_write_json(os.path.join(TMP, R._B3_FILE_MAP['refdata']), [])
maker.post('/api/b3/add', json={'table': 'refdata',
                                'fields': {'SPN': '111', 'COUNTERPARTY': 'ALPHA SA'}})
check('SPN + nome', AVISOS[-1], ('New Item', 'Reference Data', 'SPN 111 · ALPHA SA (Pending approval)'))

print('\n%s' % ('FAIL: %d' % len(fails) if fails else 'all ok'))
sys.exit(1 if fails else 0)
