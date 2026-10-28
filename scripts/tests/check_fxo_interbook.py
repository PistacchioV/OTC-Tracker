"""O filtro interbook no import da API de FXO (New Deals › Opt FXO, §720).

O pull de NDF descarta a perna interna pelo cadastro `interbook-ndf` (pares
campo × valor); o de FXO não tinha filtro nenhum, e a perna da equipe contra a
equipe entrava na tela como operação de cliente. Agora há um cadastro PRÓPRIO,
`interbook-fxo`, com a mesma forma.

  1. o cadastro existe: `_MAPPING_DEFS` (colunas do NDF, campos da API de FXO,
     seed VAZIO — nenhum de-para no código), a aba no `/mapping` e o rótulo
     nas três línguas;
  2. o filtro: par cadastrado sai (contado); `BOTH WAYS` casa trocado; valor
     comparado achatado (caixa, espaço, hífen); par pela metade não descarta;
     cadastro vazio não descarta nada; as regras do NDF NÃO valem no FXO;
  3. o pull devolve `skipped_interbook` (o que a tela já lê no resumo).

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_fxo_interbook.py
"""
import json
import os
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402

app = create_app(DebugConfig)
from apps.pages import routes as R                               # noqa: E402
from apps.pages import athena_api                                # noqa: E402
from apps.pages.platform import new_deals as ND                  # noqa: E402

fails = []


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def rec(deal, acr='CLIENTE', spn='1', **extra):
    r = {'Deal Name': deal, 'End Counterparty': acr, 'End Counterparty Description': acr + ' DESC',
         'SPN': spn, 'Trade Date': '28/10/2026', 'Settlement Date': '30/11/2026',
         'Expiration Date': '26/11/2026', 'Type': 'BUY', 'Option Type': 'CALL', 'Strike': 5.4,
         'Quantity': 1000000, 'Premium Quantity': 10000, 'Quantity Currency': 'USD',
         'Trading Book': 'TB CLIENTE', 'Other Book': ''}
    r.update(extra)
    return r


print('== 1. o cadastro ==')
d = R._MAPPING_DEFS.get('interbook-fxo') or {}
check(bool(d), '`interbook-fxo` existe no _MAPPING_DEFS')
check([c['key'] for c in d.get('columns', [])] ==
      [c['key'] for c in R._MAPPING_DEFS['interbook-ndf']['columns']], 'mesmas colunas do NDF')
campos = (d.get('columns') or [{}])[0].get('options') or []
check({'OTHER BOOK', 'TRADING BOOK', 'END COUNTERPARTY', 'OPTION TYPE'} <= set(campos),
      'os campos são os da API de FXO (%d)' % len(campos))
check(d.get('seed') == [], 'nasce vazio: o que é perna interna a equipe cadastra')
html = open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'mapping.html'), encoding='utf-8').read()
check("key: 'interbook-fxo'" in html, 'a aba no /mapping (TYPES)')
for lang in ('en', 'br', 'es'):
    tr = json.load(open(os.path.join(ROOT, 'apps', 'static', 'data', 'translations', lang + '.json'),
                        encoding='utf-8'))
    check(bool(tr.get('map-tab-interbook-fxo')), 'rótulo da aba em %s' % lang)

print('\n== 2. o filtro ==')
CAD = {'interbook-fxo': [], 'interbook-ndf': []}
_rows, _ref = R._mapping_rows, R._fxo_refdata_by_spn
R._mapping_rows = lambda key, strict=False: [dict(r) for r in CAD[key]] if key in CAD else _rows(key)
R._fxo_refdata_by_spn = lambda: {'1': {'SPN': '1', 'COUNTERPARTY': 'CLIENTE SA', 'TAX ID': '1',
                                       'FX CASH ACCRONYM': 'CLIENTE'}}


def puxa(registros):
    cont = {}
    deals, _c = ND._fxo_deals_from_api_records(registros, 'API', cont)
    return sorted(x['Deal'] for x in deals), cont.get('interbook')


try:
    REG = [rec('FX1'), rec('FX2', **{'Other Book': 'GN FXO BJPM', 'Trading Book': 'LM-FXOBRR FXC'}),
           rec('FX3', **{'Other Book': 'LM-FXOBRR FXC', 'Trading Book': 'GN FXO BJPM'}),
           rec('FX4', **{'Other Book': 'GN FXO BJPM', 'Trading Book': 'OUTRO'})]
    check(puxa(REG) == (['FX1', 'FX2', 'FX3', 'FX4'], 0), 'cadastro vazio: nada sai')
    CAD['interbook-ndf'] = [{'FIELD A': 'OTHER BOOK', 'VALUE A': 'GN FXO BJPM',
                             'FIELD B': 'TRADING BOOK', 'VALUE B': 'LM-FXOBRR FXC', 'BOTH WAYS': 'YES'}]
    check(puxa(REG)[1] == 0, 'a regra do NDF NÃO vale no FXO')
    CAD['interbook-ndf'] = []
    CAD['interbook-fxo'] = [{'FIELD A': 'OTHER BOOK', 'VALUE A': 'gn fxo bjpm',
                             'FIELD B': 'TRADING BOOK', 'VALUE B': 'LM FXOBRR FXC', 'BOTH WAYS': ''}]
    check(puxa(REG) == (['FX1', 'FX3', 'FX4'], 1),
          'o par cadastrado sai e é contado (caixa/espaço/hífen não importam)')
    CAD['interbook-fxo'][0]['BOTH WAYS'] = 'YES'
    check(puxa(REG) == (['FX1', 'FX4'], 2), 'BOTH WAYS casa também com os valores trocados')
    CAD['interbook-fxo'] = [{'FIELD A': 'OTHER BOOK', 'VALUE A': 'GN FXO BJPM',
                             'FIELD B': 'TRADING BOOK', 'VALUE B': '', 'BOTH WAYS': ''}]
    check(puxa(REG)[1] == 0, 'par pela metade não descarta nada')
    check(ND._fxo_deals_from_api_records(REG, 'API')[0] is not None,
          'quem chama sem `contagem` segue funcionando (duas respostas)')

    print('\n== 3. o pull ==')
    CAD['interbook-fxo'] = [{'FIELD A': 'END COUNTERPARTY', 'VALUE A': 'BOOK INTERNO',
                             'FIELD B': 'TRADING BOOK', 'VALUE B': 'TB X', 'BOTH WAYS': ''}]
    orig = (athena_api.is_available, athena_api.fetch_fxo_trades, athena_api.extract_records,
            ND._fxo_persist_new_deals, R._create_notification)
    athena_api.is_available = lambda: True
    athena_api.fetch_fxo_trades = lambda date: {}
    athena_api.extract_records = lambda payload: [rec('FX9', acr='BOOK INTERNO', **{'Trading Book': 'TB X'}),
                                                 rec('FX8')]
    gravados = []
    ND._fxo_persist_new_deals = lambda deals, variant=None: (gravados.extend(deals) or list(deals), [])
    R._create_notification = lambda *a, **k: None
    try:
        res = ND._fxo_api_pull(ref_date='2026-10-28')
    finally:
        (athena_api.is_available, athena_api.fetch_fxo_trades, athena_api.extract_records,
         ND._fxo_persist_new_deals, R._create_notification) = orig
    check(res.get('skipped_interbook') == 1, 'o pull devolve skipped_interbook (%r)' % res.get('skipped_interbook'))
    check([g['Deal'] for g in gravados] == ['FX8'], 'só a operação de cliente é gravada')
finally:
    R._mapping_rows, R._fxo_refdata_by_spn = _rows, _ref

print(('\nFALHAS (%d): %s' % (len(fails), fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
