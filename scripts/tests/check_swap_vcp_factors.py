# -*- coding: utf-8 -*-
"""check_swap_vcp_factors.py — Swap VCP: os fatores de juros da perna VCP e o
envio do arquivo de PU/Fator (HANDOFF §452).

O que se prende, e por que cada coisa nao daria erro sozinha:

  1. a CONTA: notional amortizado = VBR (ou original) x % do fluxo do dia (a
     regra do Swap Calculator: % e tipo do DFLUXO, base pelo tipo); juros da
     perna = |curva do OTM| - amortizado; diff B3 = Valor Juros da B3 (Swap
     Eventos) - juros JP na perna CALCULADA; fator VCP = (juros + diff da
     outra perna) / VBR + 1 na 8a casa. Um sinal trocado na diff faz a B3
     liquidar o dobro do desvio em vez de zero;
  2. as FONTES: Athena ID pelo CETIP ID do Swap Athena; curvas do OTM pelo
     Athena ID (+ = Parte, - = Contraparte) e, sem OTM, as colunas do Athena;
     VBR da posicao; sem evento no DFLUXO a amortizacao e 0 e `fluxo` vai em
     `missing` — nunca um numero inventado;
  3. a EDICAO: o campo editado vence o calculado e os derivados sao refeitos
     (juros editado muda o fator); vazio devolve o calculado; quem edita e
     maker;
  4. o ENVIO: so a perna VCP gera registro, no arquivo do Accrual
     (ACCRUAL_<VIEW>-<LOB>.txt, fator com 2+8 digitos); o maker nao envia;
     linha sem fator recusa o LOTE; enviado vira Sent nas duas tabelas.

Nada sai da maquina: os arquivos-dia sao sinteticos num tmp, o RefData e o
Operations B3 sao stubs, e o Batch Conecta e uma pasta temporaria.
"""
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


from apps.pages import routes as R                                    # noqa: E402
from apps.pages.platform import pu_fator as PF                        # noqa: E402
from apps.pages.features.other_products import domain, queries, commands   # noqa: E402
from apps.pages.json_to_duckdb import nomes_unicos                    # noqa: E402

REF = datetime(2026, 9, 8)
TMP = tempfile.mkdtemp(prefix='vcp-fat-')

# ── 1. a conta pura ─────────────────────────────────────────────────────────
print('== 1. a conta ==')
check('num BR', domain.num('1.234.567,89'), 1234567.89)
check('num US', domain.num('1,234,567.89'), 1234567.89)
check('num vazio e None', domain.num(''), None)
check('amortizado sobre o ORIGINAL', domain.notional_amortizado(800000.0, 1000000.0, 33.33, 'original'), 333300.0)
check('amortizado sobre o REMANESCENTE', domain.notional_amortizado(800000.0, 1000000.0, 25.0, 'remanescente'), 200000.0)
check('sem % nao amortiza', domain.notional_amortizado(800000.0, 1000000.0, 0.0, 'original'), 0.0)
check('juros = |curva| - amortizado', domain.juros(-345000.0, 333300.0), 11700.0)
check('diff B3 = B3 - JP', domain.diff_b3(16900.0, 16700.0), 200.0)
check('fator na 8a casa, com a diff da outra perna', domain.fator(11700.0, 200.0, 1000000.0), 1.0119)
check('fator sem VBR e None', domain.fator(11700.0, 0.0, None), None)
base = {'vbr': 1000000.0, 'original': 1000000.0, 'pct': '33.3300', 'tipo': 'Sobre Valor Base Original',
        'curva_p': 350000.0, 'curva_c': -345000.0, 'b3_juros_p': '16900,00', 'b3_juros_c': '',
        'b3_fator_p': '1,0169', 'b3_fator_c': '', 'idx_p': 'DI', 'idx_c': 'VCP'}
c = domain.calcular(base)
check('calcular: a perna VCP e a Contraparte', (c['vcp_p'], c['vcp_c']), (False, True))
check('calcular: amortizado, juros das duas pernas', (c['amortizado'], c['juros_p'], c['juros_c']), (333300.0, 16700.0, 11700.0))
check('calcular: diff so na perna calculada', (c['diff_p'], c['diff_c']), (200.0, None))
check('calcular: fator VCP com a diff da outra; a calculada mostra o da B3', (c['fator_c'], c['fator_p']), (1.0119, 1.0169))
c2 = domain.calcular(base, {'juros_c': '12000', 'tipo': ''})
check('editado vence e refaz o fator', (c2['juros_c'], c2['fator_c'], c2['manual']), (12000.0, 1.0122, ['juros_c']))
c3 = domain.calcular(dict(base, tipo='Na Data de Vencimento'))
check('no vencimento o fluxo nao amortiza', (c3['amortizado'], c3['juros_c']), (0.0, 345000.0))
check('linha para o arquivo no formato do Accrual',
      domain.linha_para_arquivo('21C', '73760.00-9', 'DI', '73760.10-2', 'VCP', None, 1.0119)[9:], ['', '1.01190000'])
check('problemas: sem perna VCP', domain.problemas_para_envio({'vcp_p': False, 'vcp_c': False, 'conta_p': 'x'}), ['no VCP leg'])
check('problemas: fator VCP faltando', domain.problemas_para_envio({'vcp_p': False, 'vcp_c': True, 'fator_c': None, 'conta_p': 'x'}),
      ['Contraparte factor missing'])

# ── 2. as fontes num tmp ────────────────────────────────────────────────────
print('== 2. as fontes ==')
_H = R._B3_SWAP_HEADERS['swap_position']


def _pos(contrato, conta_cp, ix1, ix2, rem, base_v, ini, tipo_am='0', ident='CEM-2026-0001'):
    vals = [''] * len(_H)
    vals[2], vals[7], vals[40], vals[50] = contrato, conta_cp, ix1, ix2
    vals[14], vals[15], vals[24], vals[38], vals[145] = base_v, rem, ini, tipo_am, ident
    return dict(zip(nomes_unicos(list(_H), chave=lambda s: s), vals))


def _flx(contrato, evento, taxa, tipo='0', ident='CEM-2026-0001'):
    fl = [''] * 30
    fl[0], fl[10], fl[8], fl[11], fl[16] = contrato, ident, tipo, evento, taxa
    fl[22], fl[23] = '08/06/2026', evento
    return {('c%03d' % i): v for i, v in enumerate(fl)}


def _ev(contrato, jp, jc, fp, fc, ixp, ixc):
    return {'Código do Contrato': contrato, 'PARTE / Indexador': ixp, 'CONTRAPARTE / Indexador': ixc,
            'CONTRAPARTE / Contraparte': '73760.10-2', 'CONTRAPARTE / CPF/CNPJ': '16.404.287/0001-55',
            'PARTE / Valor Juros': jp, 'CONTRAPARTE / Valor Juros': jc,
            'PARTE / Fator de Juros': fp, 'CONTRAPARTE / Fator de Juros': fc, 'Valor Base Remanescente': '1000000,00'}


def _escrever():
    ds = os.path.join(TMP, 'ds', '2026', '09', '08')
    b3 = os.path.join(TMP, 'b3', 'Swap', '2026', '09', '08')
    os.makedirs(ds); os.makedirs(b3)

    def w(path, data):
        with io.open(path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False)
    w(os.path.join(ds, 'eventos-swap-jpm_20260908.json'), [
        _ev('21C00035804', '16900,00', '', '1,0169', '', 'DI', 'VCP'),
        _ev('24H02170822', '', '5000,00', '', '1,005', 'VCP', 'DI'),
    ])
    w(os.path.join(ds, 'br-onshore-settlements_20260908.json'), [
        {'CETIP ID': '21C00035804', 'Kapital ID': 'K-001', 'Owner Legal Entity': 'Bco J.P. Morgan S.A.',
         'CounterParty': 'SUZANO', 'SPN': '1', 'Owner curve': '350000.00', 'Counterparty curve': '345000.00',
         'BRL Net Amount': '5000.00', 'Direction': 'Counterparty receives'},
        {'CETIP ID': '24H02170822', 'Kapital ID': 'K-002', 'Owner Legal Entity': 'Bco J.P. Morgan S.A.',
         'CounterParty': 'OUTRA', 'SPN': '2', 'Owner curve': '9000.00', 'Counterparty curve': '4000.00',
         'BRL Net Amount': '5000.00', 'Direction': 'Counterparty receives'},
    ])
    w(os.path.join(ds, 'otm-settlement_20260908.json'), [
        {'Trade Id': 'K-001', 'Amount': '350000.00', 'Currency': 'BRL'},
        {'Trade Id': 'K-001', 'Amount': '-345000.00', 'Currency': 'BRL'},
    ])                                                     # K-002 sem OTM: cai nas colunas do Athena
    w(os.path.join(b3, '73760_260908_DPOSICAO-SWAP.json'), [
        _pos('21C00035804', '73760.10-2', 'C03', 'C99', '1000000,00', '1000000,00', '1000000,00'),
        _pos('24H02170822', '73760.10-2', 'C99', 'C03', '500000,00', '500000,00', '500000,00', ident='EDG-2026-1'),
    ])
    w(os.path.join(b3, '73760_260908_DFLUXO.json'), [
        _flx('21C00035804', '08/09/2026', '33,3300'),
        _flx('21C00035804', '08/12/2026', '33,3300'),      # o evento seguinte nao e deste dia
    ])                                                     # 24H sem fluxo no dia: amortizacao 0, `fluxo` em missing


_escrever()
OPS = [{'Tipo Operação': 'AVISO DE INEXISTENCIA DE PU', 'Título': c, 'Conta': '73760.00-9'}
       for c in ('21C00035804', '24H02170822')]
real = (R.OTM_JSON_ROOT, R.B3_JSON_ROOT, R._opb3_load, R._vcp_refdata_maps, R.CONECTA_NEW_PATH,
        PF.ACCRUAL_SOURCE_ROOT, R.smtplib.SMTP if hasattr(R, 'smtplib') else None)
R.OTM_JSON_ROOT = os.path.join(TMP, 'ds')
R.B3_JSON_ROOT = os.path.join(TMP, 'b3')
R._opb3_load = lambda ref: ('', [dict(o) for o in OPS])
R._vcp_refdata_maps = lambda: ({}, {'16404287000155': 'SUZANO SA'})
R.CONECTA_NEW_PATH = os.path.join(TMP, 'conecta')
PF.ACCRUAL_SOURCE_ROOT = os.path.join(TMP, 'evidence')
_notifs = []
_cn_real = R._create_notification
R._create_notification = lambda *a, **k: _notifs.append(a)

try:
    pay = queries.vcp_payload(REF)
    cols = pay['columns']
    check('Athena ID entre Contraparte e Codigo do Contrato', cols[:3], ['Contraparte', 'Athena ID', 'Código do Contrato'])
    linhas = {r[2]: r for r in pay['rows']}
    check('o Athena ID vem do Swap Athena pelo CETIP ID', linhas['21C00035804'][1], 'K-001')
    fat = {f['contrato']: f for f in pay['factors']}
    f1 = fat['21C00035804']
    check('VBR da posicao, LOB do identificador', (f1['vbr'], f1['lob']), (1000000.0, 'CEM'))
    check('% e tipo do DFLUXO do dia (a regra do Swap Calculator)', (f1['pct'], f1['tipo']), (33.33, 'Sobre Valor Base Original'))
    check('curvas do OTM pelo Athena ID', (f1['curva_p'], f1['curva_c']), (350000.0, 345000.0))
    check('a conta fecha: amortizado, juros, diff, fator VCP',
          (f1['amortizado'], f1['juros_p'], f1['juros_c'], f1['diff_p'], f1['diff_c'], f1['fator_c'], f1['fator_p']),
          (333300.0, 16700.0, 11700.0, 200.0, None, 1.0119, 1.0169))
    check('a primeira tabela recebe o fator SO da perna VCP',
          (linhas['21C00035804'][cols.index('PARTE / Fator')], linhas['21C00035804'][cols.index('CONTRAPARTE/ Fator')]),
          ('', '1.01190000'))
    check('status New nas duas tabelas', (pay['statuses'], f1['status']), (['New', 'New'], 'New'))
    f2 = fat['24H02170822']
    check('sem OTM as curvas caem nas colunas do Athena', (f2['curva_p'], f2['curva_c']), (9000.0, 4000.0))
    check('sem evento no DFLUXO: amortizacao 0 e `fluxo` em missing',
          (f2['pct'], f2['amortizado'], 'fluxo' in f2['missing']), (0.0, 0.0, True))
    check('perna VCP e a Parte: fator com a diff da Contraparte (B3 5000 - JP 4000)',
          (f2['vcp_p'], f2['diff_c'], f2['fator_p']), (True, 1000.0, round((9000.0 + 1000.0) / 500000.0 + 1, 8)))

    # ── 3. a edicao ─────────────────────────────────────────────────────────
    print('== 3. a edicao ==')
    body, st = commands.vcp_factors_edit(REF, '21C00035804', {'juros_c': '12.000,00', 'vbr': ''}, sid='E1')
    check('edit grava e devolve a linha refeita', (st, body['row']['juros_c'], body['row']['fator_c'], body['row']['manual']),
          (200, 12000.0, 1.0122, ['juros_c']))
    check('quem editou e o maker', (body['row']['maker'], body['row']['status']), ('E1', 'New'))
    body, st = commands.vcp_factors_edit(REF, '21C00035804', {'juros_c': 'abc'}, sid='E1')
    check('texto que nao e numero recusa', st, 400)
    body, st = commands.vcp_factors_edit(REF, '21C00035804', {'juros_c': ''}, sid='E1')
    check('vazio devolve o calculado', (body['row']['juros_c'], body['row']['fator_c']), (11700.0, 1.0119))

    # ── 4. o envio ──────────────────────────────────────────────────────────
    print('== 4. o envio ==')
    body, st = commands.vcp_send(REF, ['21C00035804'], sid='E1')
    check('o maker nao envia', (st, body['error'], 'different user' in body['problems'][0]), (400, 'blocked', True))
    R._fi_tpl_cache.clear() if hasattr(R, '_fi_tpl_cache') else None
    body, st = commands.vcp_send(REF, ['21C00035804', '24H02170822'], sid='E2')
    check('o lote sai', (st, body.get('success')), (200, True))
    nomes = sorted(f['filename'] for f in body['files'])
    check('um arquivo por LOB, visao BANCO', nomes, ['ACCRUAL_BANCO-CEM.txt', 'ACCRUAL_BANCO-EDG.txt'])
    txt = io.open(os.path.join(TMP, 'conecta', 'ACCRUAL_BANCO-CEM.txt'), encoding='utf-8').read().split('\n')
    check('header + 1 registro (so a perna VCP)', len(txt), 2)
    check('o fator vai com 2+8 digitos', txt[1][-10:], '0101190000')
    check('a evidencia foi copiada', os.path.isfile(os.path.join(PF.accrual_source_dir(datetime.now().strftime('%Y%m%d')), 'ACCRUAL_BANCO-CEM.txt')), True)
    pay2 = queries.vcp_payload(REF)
    check('enviado vira Sent nas duas tabelas', (pay2['statuses'], [f['status'] for f in pay2['factors']]),
          (['Sent', 'Sent'], ['Sent', 'Sent']))
    check('aviso no sino com a pagina Swap VCP', (_notifs[-1][2], _notifs[-1][3]), ('Accrual Sent', 'Swap VCP'))
    body, st = commands.vcp_send(REF, ['99Z'], sid='E2')
    check('contrato fora da pagina recusa', (st, body['problems']), (400, ['99Z: not on the page']))

    # ── 5. os endpoints ─────────────────────────────────────────────────────
    print('== 5. os endpoints ==')
    from apps import create_app
    from apps.config import DebugConfig
    app = create_app(DebugConfig); app.config['TESTING'] = True
    cl = app.test_client()
    with cl.session_transaction() as s:
        s['authenticated'] = True; s['user_sid'] = 'E3'; s['user_name'] = 'T'
        s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    d = cl.get('/api/other-products-swap-vcp/data?date=2026-09-08').get_json()
    check('GET data traz factors e statuses', (len(d['factors']), d['statuses']), (2, ['Sent', 'Sent']))
    r = cl.post('/api/other-products-swap-vcp/factors/edit', json={'date': '2026-09-08', 'contrato': '21C00035804', 'fields': {'fator_c': '1.02'}})
    check('POST edit', (r.status_code, r.get_json()['row']['fator_c'], r.get_json()['row']['status']), (200, 1.02, 'New'))
    r = cl.post('/api/other-products-swap-vcp/send', json={'date': '2026-09-08', 'contrato': '21C00035804'})
    check('POST send pelo maker e bloqueado', (r.status_code, r.get_json()['error']), (400, 'blocked'))
    html = cl.get('/other-products-swap-vcp').get_data(as_text=True)
    check('a pagina tem a segunda tabela, o modal e o Send em lote',
          all(x in html for x in ('id="vcp-factors"', 'id="vcpModal"', 'id="vcpBulkSend"', 'data-actions="send"')), True)
finally:
    (R.OTM_JSON_ROOT, R.B3_JSON_ROOT, R._opb3_load, R._vcp_refdata_maps, R.CONECTA_NEW_PATH,
     PF.ACCRUAL_SOURCE_ROOT, _s) = real
    R._create_notification = _cn_real
    shutil.rmtree(TMP, ignore_errors=True)

print()
print('FALHAS: %d' % len(fails) if fails else 'tudo ok')
sys.exit(1 if fails else 0)
