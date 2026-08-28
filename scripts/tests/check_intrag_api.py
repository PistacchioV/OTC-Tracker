# -*- coding: utf-8 -*-
"""As telas da Intrag (NDF / Option / Swap) ponta a ponta.

As tres familias sao simetricas (list / edit / approve / send-file / mapping);
o que este script prende e o CICLO DE VIDA com trava de quatro olhos:

  1. **persistir de novo nao rebaixa o status**: so a PRIMEIRA gravacao nasce
     'New' — o re-save preserva status/maker/checker (senao todo pull da API
     devolveria para a fila o que ja foi aprovado);
  2. **edit → Pending com o maker gravado e o checker LIMPO**;
  3. **maker nao aprova a propria edicao** (403) — outro usuario aprova
     (Pending → Approved com o checker);
  4. so Pending aprova (400 no resto); entrada inexistente e 404.
"""
import io, json, os, sys, tempfile
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

# A Intrag mora em features/intrag (nomes preservados no engine).
# O Intrag mora em features/intrag, separado em camadas (§321): os
# arquivos-dia e a gravação são de `infra/persistence`.
from apps.pages.features.intrag.infra import persistence as B   # noqa: E402
B.INTRAG_NDF_CACHE_DIR = os.path.join(TMP, 'ndf')
B.INTRAG_OPT_CACHE_DIR = os.path.join(TMP, 'opt')
B.INTRAG_SWAP_CACHE_DIR = os.path.join(TMP, 'swap')
IN_persist = B._intrag_ndf_persist

NOTIFS = []
R._create_notification = lambda sid, nome, acao, pagina, msg='': NOTIFS.append((acao, pagina))

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def cliente(sid):
    c = app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = sid
        s['user_name'] = sid
        s['user_role'] = 'BO'
        s['user_email'] = sid + '@x'
        s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


maker, checker, anon = cliente('A111111'), cliente('B222222'), app.test_client()
TD = datetime(2026, 8, 20)

print('== 1. sem sessao ==')
for ep in ('/api/intrag/ndf', '/api/intrag/option', '/api/intrag/swap'):
    check('%s -> 401' % ep, anon.get(ep).status_code, 401)

print('\n== 2. persistir de novo nao rebaixa o ciclo ==')
IN_persist({'_deal': 'D-1', '_client': 'ACME', 'campo': 'v1'}, TD)
IN_persist({'_deal': 'D-2', '_client': 'BETA', 'campo': 'x'}, TD)
d = maker.get('/api/intrag/ndf?date=2026-08-20').get_json()
# A PRIMEIRA gravacao entra sem coluna de ciclo nenhuma (a tela desenha como
# New); e o RE-SAVE que materializa 'New' — comportamento registrado como e.
check('as duas entradas, ainda sem ciclo materializado',
      sorted((e['_deal'], e.get('status')) for e in d['entries']),
      [('D-1', None), ('D-2', None)])
IN_persist({'_deal': 'D-2', '_client': 'BETA', 'campo': 'x2'}, TD)
d = maker.get('/api/intrag/ndf?date=2026-08-20').get_json()
check('   e o re-save materializa o New',
      next(e.get('status') for e in d['entries'] if e['_deal'] == 'D-2'), 'New')

print('\n== 3. edit: Pending com maker, checker limpo ==')
r = maker.post('/api/intrag/ndf/edit', json={'deal_id': 'D-1', 'trade_date': '2026-08-20',
                                             'fields': {'campo': 'v2', '_deal': 'HACK'}})
check('vira Pending', (r.status_code, r.get_json()['status']), (200, 'Pending'))
e = next(x for x in maker.get('/api/intrag/ndf?date=2026-08-20').get_json()['entries']
         if x['_deal'] == 'D-1')
check('   campo editado, chave protegida, maker gravado',
      (e['campo'], e['_deal'], e['maker'], e['checker']), ('v2', 'D-1', 'A111111', ''))

# re-save do pull: o estado NAO volta para New
IN_persist({'_deal': 'D-1', '_client': 'ACME', 'campo': 'v3'}, TD)
e = next(x for x in maker.get('/api/intrag/ndf?date=2026-08-20').get_json()['entries']
         if x['_deal'] == 'D-1')
check('re-save preserva Pending/maker (so o dado muda)',
      (e['status'], e['maker'], e['campo']), ('Pending', 'A111111', 'v3'))

print('\n== 4. quatro olhos ==')
r = maker.post('/api/intrag/ndf/approve', json={'deal_id': 'D-1', 'trade_date': '2026-08-20'})
check('o maker nao aprova a propria edicao (403)', r.status_code, 403)
r = checker.post('/api/intrag/ndf/approve', json={'deal_id': 'D-1', 'trade_date': '2026-08-20'})
check('outro usuario aprova', (r.status_code, r.get_json()['status']), (200, 'Approved'))
e = next(x for x in maker.get('/api/intrag/ndf?date=2026-08-20').get_json()['entries']
         if x['_deal'] == 'D-1')
check('   com o checker carimbado', e['checker'], 'B222222')
r = checker.post('/api/intrag/ndf/approve', json={'deal_id': 'D-1', 'trade_date': '2026-08-20'})
check('so Pending aprova (400 no resto)', r.status_code, 400)
r = checker.post('/api/intrag/ndf/approve', json={'deal_id': 'NAO-EXISTE', 'trade_date': '2026-08-20'})
check('entrada inexistente e 404', r.status_code, 404)

print('\n== 5. o intervalo de datas na listagem ==')
IN_persist({'_deal': 'D-3', '_client': 'GAMA', 'campo': 'y'}, datetime(2026, 8, 21))
d = maker.get('/api/intrag/ndf?date_from=2026-08-21&date_to=2026-08-21').get_json()
check('so o dia pedido', [e['_deal'] for e in d['entries']], ['D-3'])
d = maker.get('/api/intrag/ndf?date_from=2026-08-19&date_to=2026-08-22').get_json()
check('o intervalo traz os dois dias', len(d['entries']), 3)

print('\n== 6. Intrag ID digitado na edicao = Success (o desfecho do Mapping) ==')
from apps.pages.features.intrag import domain as D           # noqa: E402
r = maker.post('/api/intrag/ndf/edit', json={'deal_id': 'D-2', 'trade_date': '2026-08-20',
                                             'fields': {'campo': 'z'}, 'intrag_id': ' 12345 '})
check('edit com intrag_id novo devolve Success', (r.status_code, r.get_json()['status']),
      (200, 'Success'))
e = next(x for x in maker.get('/api/intrag/ndf?date=2026-08-20').get_json()['entries']
         if x['_deal'] == 'D-2')
check('   persistido TRIMADO, com status e maker',
      (e['intrag_id'], e['status'], e['maker']), ('12345', 'Success', 'A111111'))
# Intrag ID INALTERADO: a edicao e de DADO e segue o 4-eyes (Pending) — sem
# isso, qualquer edicao numa linha ja casada escaparia da aprovacao.
r = maker.post('/api/intrag/ndf/edit', json={'deal_id': 'D-2', 'trade_date': '2026-08-20',
                                             'fields': {'campo': 'w'}, 'intrag_id': '12345'})
check('inalterado, edicao de dado segue o 4-eyes', r.get_json()['status'], 'Pending')
# Intrag ID LIMPO: a linha descasou — Pending, e o campo esvazia de verdade.
r = maker.post('/api/intrag/ndf/edit', json={'deal_id': 'D-2', 'trade_date': '2026-08-20',
                                             'fields': {}, 'intrag_id': ''})
e = next(x for x in maker.get('/api/intrag/ndf?date=2026-08-20').get_json()['entries']
         if x['_deal'] == 'D-2')
check('limpo: Pending e campo vazio', (r.get_json()['status'], e['intrag_id']), ('Pending', ''))
# Payload SEM a chave (tela antiga aberta): comportamento de antes, intocado.
r = maker.post('/api/intrag/ndf/edit', json={'deal_id': 'D-3', 'trade_date': '2026-08-21',
                                             'fields': {'campo': 'y2'}})
e = next(x for x in maker.get('/api/intrag/ndf?date=2026-08-21').get_json()['entries']
         if x['_deal'] == 'D-3')
check('payload sem a chave nao toca no campo', (r.get_json()['status'], 'intrag_id' in e),
      ('Pending', False))
r = maker.post('/api/intrag/option/edit', json={'deal_id': 'NAO-EXISTE', 'intrag_id': '1'})
check('option: mesma rota, entrada inexistente e 404', r.status_code, 404)

print('\n== 7. Mapping Intrag ID: o CSV de retorno cobre MERCADORIA e MOEDAS ==')
# O filtro da familia e por PREFIXO ('NDF - TERMO'): o retorno ecoa o texto do
# instrumento enviado, e a mesma tela manda dois contract types. Com igualdade
# exata a linha de moedas era descartada ANTES do casamento — o Mapping dizia
# "N mapped" (as de mercadoria) e o termo de moedas ficava sem Intrag ID.
from apps.pages.features.intrag import queries as Q          # noqa: E402
IN_persist({'_deal': 'MAP-MERC', '_client': 'ACME', 'b3_id': '26C0001'},
           datetime(2026, 8, 23))
IN_persist({'_deal': 'MAP-MOEDA', '_client': 'BETA', 'b3_id': '26C0002',
            'contract_type': 'NDF - TERMO DE MOEDAS'}, datetime(2026, 8, 23))
csv_path = os.path.join(TMP, 'boletas.csv')
with open(csv_path, 'w', encoding='latin-1') as fh:
    fh.write('INT-111;NDF - TERMO MERCADORIA;26C0001;x\n'
             'INT-222;NDF - TERMO DE MOEDAS;26C0002;x\n'
             'INT-333;OPCAO;26C0003;x\n')
_finder_orig = Q._intrag_find_export_csv
Q._intrag_find_export_csv = lambda: csv_path
try:
    r = maker.post('/api/intrag/ndf/mapping-intrag-id',
                   json={'deals': [{'id': 'MAP-MERC', 'b3_id': '26C0001'},
                                   {'id': 'MAP-MOEDA', 'b3_id': '26C0002'}]})
finally:
    Q._intrag_find_export_csv = _finder_orig
res = {x['id']: x for x in r.get_json()['results']}
check('mercadoria mapeada', (res['MAP-MERC']['status'], res['MAP-MERC']['intrag_id']),
      ('Success', 'INT-111'))
check('MOEDAS mapeada tambem (era descartada pelo filtro exato)',
      (res['MAP-MOEDA']['status'], res['MAP-MOEDA']['intrag_id']),
      ('Success', 'INT-222'))
d = maker.get('/api/intrag/ndf?date=2026-08-23').get_json()['entries']
check('e PERSISTIDA no arquivo-dia com status Success',
      sorted((e['_deal'], e.get('intrag_id'), e['status']) for e in d),
      [('MAP-MERC', 'INT-111', 'Success'), ('MAP-MOEDA', 'INT-222', 'Success')])

print('\n== 8. Information Source legivel (separador -> espaco) ==')
check('a regra pura', D._intrag_info_source('PTAX|BRR[PTAX'), 'PTAX BRR PTAX')
check('   chave/parentese tambem', D._intrag_info_source('{PTAX}(BRR);<X>'), 'PTAX BRR X')
check('   texto limpo passa intocado', D._intrag_info_source('PTAX USB WMR 4'), 'PTAX USB WMR 4')
check('   nao-texto volta como veio', D._intrag_info_source(None), None)
# Linha GRAVADA antes da limpeza: a leitura ja devolve legivel, sem reescrever
# o arquivo-dia — e sem vazar a limpeza para o cache compartilhado.
IN_persist({'_deal': 'D-4', '_client': 'DELTA', 'na_2': 'PTAX|BRR[PTAX'}, datetime(2026, 8, 22))
e = next(x for x in maker.get('/api/intrag/ndf?date=2026-08-22').get_json()['entries']
         if x['_deal'] == 'D-4')
check('linha antiga sai limpa na listagem', e['na_2'], 'PTAX BRR PTAX')
with open(os.path.join(B.INTRAG_NDF_CACHE_DIR, '2026', '08', '20260822_intrag_ndf.json'),
          encoding='utf-8') as fh:
    cru = next(x for x in json.load(fh) if x['_deal'] == 'D-4')
check('   e o arquivo-dia fica como esta (limpeza e de leitura)',
      cru['na_2'], 'PTAX|BRR[PTAX')

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
