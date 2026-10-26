# -*- coding: utf-8 -*-
"""check_unwind_api.py — a recompra de NDF de moeda pela API (20/10/2026).

Desde 20/10/2026 a recompra entra pelo `getTradesBySettle` do Athena — a MESMA
API de liquidacao do NDF Cockpit —, no bloco `termination` do trade, com o
`Cetip ID` do contrato. Antes ela vinha do e-mail `BRL NDF Unwind
Notification` varrido no Outlook, e a ponte ate o contrato era o `Codigo
Identificador` truncado do Live Position. O que este teste prende:

  1. o de-para da API e o do e-mail: a amostra STP-XE-10PSG8U-0-0 da o mesmo
     resultado, direcao e DU (12, contado no ANBIMA) que o aviso daquela
     recompra; so entra a recompra que LIQUIDA na data pedida;
  2. a posicao se acha pelo B3 ID, na visao do Banco antes da do fundo, e o
     contrato fora da posicao e dito como tal (nao como "sem contrato");
  3. o pull pede a data E o dia util seguinte (a recompra liquida em D0 ou
     D+1) e grava pelo mesmo caminho do e-mail: arquivo-dia da recompra,
     esteira, Pending Confirmation e o NDF Cockpit da liquidacao;
  4. so a recompra NOVA entra: o segundo pull nao reescreve a linha que a mesa
     editou; a leitura do dia e estrita (banco ocupado sobe);
  5. uma data que a API nao responde nao derruba a outra; todas falhando e
     erro com o motivo;
  6. a rota do Import, o laco de 30 minutos e o cadastro `api-links`.

Roda em tmp: cache, esteira, Pending Confirmation e Cockpit apontam para
diretorios temporarios, a API e a posicao sao stubs.
"""
import copy
import io
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra) else ''))
    if not cond:
        FALHAS.append(nome)


AQUI = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(AQUI, '..', '..'))
AMOSTRA = json.load(io.open(os.path.join(AQUI, 'fixtures', 'unwind-ndf-api-settle.json'),
                            encoding='utf-8'))

# A posicao da amostra, na visao do BANCO (vendido: e o lado que fecha a conta
# do aviso, +7.265,60 a receber). O `Codigo Identificador` NAO casa com o
# Athena ID de proposito: a ponte agora e o B3 ID, e o identificador nao pode
# ser o que acha a linha.
POS = {
    'Codigo Identificador': 'NADA-A-VER-0-0',
    'Contrato': '26D04217190',
    'Simbolo da Moeda': 'USD',
    'Descricao da posicao do Participante': 'VENDEDOR',
    'Valor Base no registro': '20,000.00',
    'Valor Antecipado': '',
    'Codigo da Parte': '73760.00-9',
    'Codigo da Contraparte': '99999.00-1',
    'Nome da Contraparte': 'MAXMIX COMERCIAL LTDA',
    'CPF/CNPJ da Contraparte': '03.002.339/0001-15',
}


def _trade(deal, cetip, eventos, **extra):
    t = copy.deepcopy(AMOSTRA[0])
    t['Deal Name'], t['Cetip ID'], t['termination'] = deal, cetip, eventos
    t.update(extra)
    return t


def _evento(nome, trade_date, liq, qtd=20000.0, fee=7265.6, parcial=False):
    e = copy.deepcopy(AMOSTRA[0]['termination'][0])
    e.update({'Event Name': nome, 'Trade Date': trade_date, 'Settlement Date': liq,
              'Quantity': qtd, 'Settlement Quantity': fee, 'Partial': parcial})
    return e


def main():
    from run import app  # noqa: F401
    from apps.pages import athena_api, data_store as _ds
    from apps.pages import routes as R
    from apps.pages.features.unwinds import commands, domain, queries
    from apps.pages.features.unwinds import entrypoint as unw_ep
    from apps.pages.features.unwinds.infra import persistence
    from apps.pages.precificador import derivativos

    print('\n== 1. o de-para da API e o do e-mail ==')
    recs = domain.recompras_da_api(AMOSTRA, '2026-10-14', derivativos.dias_uteis_ate)
    check('uma recompra pela entrada do bloco termination', len(recs) == 1, recs)
    r = recs[0] if recs else {}
    antes, depois = r.get('secoes', {}).get('before', {}), r.get('secoes', {}).get('after', {})
    check('Before Unwind: Athena ID, Trade Date, Maturity, Notional, CCY e Strike do trade',
          (antes.get('Athena ID'), antes.get('Trade Date'), antes.get('Maturity Date'),
           antes.get('Notional'), antes.get('Notional CCY'), antes.get('Strike'))
          == ('STP-XE-10PSG8U-0-0', '2026-04-07', '2026-10-30', '20000', 'USB', '5.4055'), antes)
    check('After Unwind: tipo, recomprado, taxas, fee e cliente do termination',
          (depois.get('Unwind Type'), depois.get('Unwound Amount'), depois.get('Termination Rate'),
           depois.get('Pre FWD Rate'), depois.get('Input Termination Fee'), depois.get('Client'))
          == ('TOTAL', '20000', '5.04', '13.65', '7265.6', 'MAXMIXBR-BR'), depois)
    check('o DU e o do aviso (12 dias uteis ANBIMA de 14/10 a 30/10/2026)', depois.get('DU') == '12',
          depois.get('DU'))
    check('o B3 ID vem direto do Cetip ID, e o evento e o segundo id do assunto do e-mail',
          (r.get('contrato'), r.get('notification_id')) == ('26D04217190', 'E5VL-3KTQZ7W'), r)
    check('liquidacao e dia da recompra vem do termination',
          (r.get('liquidacao'), r.get('data_recompra')) == ('2026-10-14', '2026-10-14'), r)
    linha, av = domain.linha_da_recompra(r, POS, date(2026, 10, 14), r.get('contrato'))
    check('a linha fecha como o e-mail: +7.265,60, RECEIVE, Check OK',
          (linha['Result'], linha['Direction'], linha['Check'], linha['CalcResult'])
          == (7265.6, 'RECEIVE', 'OK', None), linha)
    check('a data de liquidacao da linha e a da API (nao o dia do import)',
          linha['SettlementDate'] == '2026-10-14', linha['SettlementDate'])
    check('sem aviso nenhum', av == [], av)
    check('so entra a recompra que LIQUIDA na data pedida',
          domain.recompras_da_api(AMOSTRA, '2026-10-15') == [])
    parcial = _trade('STP_XE_1_0_0', '26D00000001',
                     [_evento('EV-OLD', '2026-08-03', '2026-08-03', parcial=True),
                      _evento('EV-NEW', '2026-10-14', '2026-10-14', qtd=5000.0, parcial=True)])
    rp = domain.recompras_da_api([parcial], '2026-10-14')
    check('a parcial ANTIGA do mesmo trade fica de fora; a de hoje entra como PARTIAL',
          [(x['notification_id'], x['secoes']['after']['Unwind Type']) for x in rp]
          == [('EV-NEW', 'PARTIAL')], rp)
    check('o `_` do Deal Name vira `-` (a grafia do Cockpit e do e-mail)',
          rp and rp[0]['athena_id'] == 'STP-XE-1-0-0', rp and rp[0]['athena_id'])
    check('sem DU contado, a conferencia diz que nao da para conferir',
          domain.linha_da_recompra(domain.recompras_da_api(AMOSTRA, '2026-10-14')[0], POS,
                                   date(2026, 10, 14), '26D04217190')[0]['Check'] == '-')

    print('\n== 2. a posicao pelo B3 ID ==')
    banco = dict(POS)
    fundo = dict(POS, **{'Codigo da Parte': '00041.00-7', 'Codigo da Contraparte': '73760.00-9',
                         'Descricao da posicao do Participante': 'COMPRADOR'})
    rank = lambda l: 0 if l is banco else 1                                  # noqa: E731
    check('o mesmo contrato em duas visoes: vale a do Banco (menor rank)',
          domain.posicao_pelo_contrato([fundo, banco], '26d04217190', rank) is banco)
    check('contrato fora da posicao e None', domain.posicao_pelo_contrato([banco], 'X') is None)
    _l, av = domain.linha_da_recompra(r, None, date(2026, 10, 14), '26D04217190')
    codigos = [a['code'] for a in av]
    check('contrato da API sem linha na posicao e dito como tal, nao como "sem contrato"',
          'unwind_contract_not_in_position' in codigos and 'unwind_no_contract' not in codigos,
          codigos)
    check('e a linha guarda o B3 ID que a API mandou', _l['Contract'] == '26D04217190')
    rank_real = [commands._visao_rank({'Codigo da Parte': c})
                 for c in ('73760.00-9', '00041.00-7', '99999.00-1')]
    check('o rank sai do b3-accounts: Banco 0, fundo 1, conta de fora 2', rank_real == [0, 1, 2],
          rank_real)

    print('\n== 3. o pull: as duas datas e o caminho do import ==')
    check('pede a data e o dia util seguinte (D0 ou D+1)',
          commands.datas_de_liquidacao(date(2026, 10, 14)) == [date(2026, 10, 14), date(2026, 10, 15)])
    check('na sexta, o seguinte e a segunda',
          commands.datas_de_liquidacao(date(2026, 10, 16)) == [date(2026, 10, 16), date(2026, 10, 19)])

    tmp = tempfile.mkdtemp(prefix='otc-unw-api-')
    persistence.cache_root = lambda: os.path.join(tmp, 'cache')
    persistence.cache_dir = lambda: os.path.join(tmp, 'cache', 'NDF', 'FX')
    R._ndfc_json_path = lambda ref: os.path.join(
        tmp, 'cockpit', ref.strftime('%Y%m%d') + '_ndf-cockpit.json')
    R._ndfsum_ir_ledger_path = lambda ref: os.path.join(
        tmp, 'ledger', 'ndf-ir-ledger_' + ref.strftime('%Y%m') + '.json')
    from apps.pages import manual_conf as _mc
    _mc._DB_DIR = os.path.join(tmp, 'mc-db')
    os.makedirs(_mc._DB_DIR, exist_ok=True)
    R._PC_DB_DIR = os.path.join(tmp, 'pc-db')
    os.makedirs(R._PC_DB_DIR, exist_ok=True)
    colunas = list(POS.keys())
    pos_d1 = dict(POS, Contrato='26D04217191')
    coletas = []
    R._lpndf_collect = lambda ref: coletas.append(ref) or {
        'columns': colunas, 'source_date': '2026-10-13',
        'rows': [[p.get(c, '') for c in colunas] for p in (POS, pos_d1)]}
    sino = []
    R._create_notification = lambda *a, **k: sino.append(a)

    # A API: D0 traz a amostra, um cancelado e um trade so com `settlement`;
    # D+1 traz a recompra de HOJE que liquida amanha.
    d1 = _trade('STP-XE-D1-0-0', '26D04217191', [_evento('EV-D1', '2026-10-14', '2026-10-15')])
    cancelado = _trade('STP-XE-CANC-0-0', '26D09999999',
                       [_evento('EV-C', '2026-10-14', '2026-10-14')], isCancelled=True)
    so_liq = _trade('STP-XE-LIQ-0-0', '26D08888888', [])
    respostas = {'20261014': [AMOSTRA[0], cancelado, so_liq], '20261015': [d1]}
    pedidos = []

    def _get(sessao, url, params=None, timeout=None):
        ymd = url.split('date=')[1][:8]
        pedidos.append((ymd, timeout))
        if isinstance(respostas.get(ymd), Exception):
            raise respostas[ymd]
        return respostas.get(ymd, [])

    orig = (athena_api.get_json_url, athena_api.build_session)
    athena_api.get_json_url = _get
    athena_api.build_session = lambda: object()
    try:
        out = commands.importar_da_api(date(2026, 10, 14))
        check('pede as duas datas, com o timeout de RELATORIO',
              pedidos == [('20261014', athena_api.REPORT_TIMEOUT),
                          ('20261015', athena_api.REPORT_TIMEOUT)], pedidos)
        check('entram a amostra e a recompra de hoje que liquida amanha',
              sorted(x['AthenaID'] for x in out['rows']) == ['STP-XE-10PSG8U-0-0', 'STP-XE-D1-0-0'],
              [x['AthenaID'] for x in out['rows']])
        check('o cancelado fica de fora, contado', out['skipped'].get('cancelled') == 1, out['skipped'])
        check('a posicao e lida UMA vez para o lote', len(coletas) == 1, coletas)
        dia = sorted(e['AthenaID'] for e in queries.entries('2026-10-14'))
        check('as duas no arquivo-dia da RECOMPRA (14/10)',
              dia == ['STP-XE-10PSG8U-0-0', 'STP-XE-D1-0-0'], dia)
        d1_linha = [x for x in out['rows'] if x['AthenaID'] == 'STP-XE-D1-0-0'][0]
        check('a de D+1 liquida no dia que a API disse', d1_linha['SettlementDate'] == '2026-10-15',
              d1_linha['SettlementDate'])
        k = domain.chave_esteira([x for x in queries.entries('2026-10-14')
                                  if x['AthenaID'] == 'STP-XE-10PSG8U-0-0'][0])
        pc = R._pc_find_rows([k])
        check('a recompra esta no Pending Confirmation (UNW-…, §696)',
              k == 'UNW-STP-XE-10PSG8U-0-0-20261014' and k in pc, (k, sorted(pc)))
        check('e na esteira', _mc.find_row(k) is not None)
        ck = _ds.read(R._ndfc_json_path(date(2026, 10, 14))) or []
        ids = sorted(x.get('_nc_id') for x in ck if x.get('_nc_unwind'))
        check('no NDF Cockpit do dia da liquidacao', ids == ['UNW-STP-XE-10PSG8U-0-0'], ids)
        ck15 = _ds.read(R._ndfc_json_path(date(2026, 10, 15))) or []
        check('e a de D+1 no Cockpit de 15/10',
              [x.get('_nc_id') for x in ck15 if x.get('_nc_unwind')] == ['UNW-STP-XE-D1-0-0'])

        print('\n== 4. so a recompra NOVA entra ==')
        commands.editar('STP-XE-10PSG8U-0-0', '2026-10-14', {'PreFWDRate': 13.7}, sid='T000001')
        out2 = commands.importar_da_api(date(2026, 10, 14))
        check('o segundo pull nao traz linha nova', out2['rows'] == [], out2['rows'])
        check('e conta as que ja estavam', out2['existing'] == 2, out2['existing'])
        fp, lst, i = queries.find('STP-XE-10PSG8U-0-0', '2026-10-14')
        check('a edicao da mesa ficou como estava', lst[i]['PreFWDRate'] == 13.7
              and lst[i]['Status'] == 'Pending', (lst[i]['PreFWDRate'], lst[i]['Status']))
        orig_isfile = _ds.isfile

        def _ocupado(p):
            if p.endswith(persistence.SUFFIX):
                raise _ds.BancoOcupado(p)
            return orig_isfile(p)
        _ds.isfile = _ocupado
        try:
            subiu = None
            try:
                commands.importar_da_api(date(2026, 10, 14))
            except _ds.BancoOcupado:
                subiu = True
            check('banco ocupado na leitura do dia SOBE (nunca vira "nao ha nada")', subiu is True)
        finally:
            _ds.isfile = orig_isfile

        print('\n== 5. a API que nao responde ==')
        respostas['20261015'] = RuntimeError('502 Bad Gateway')
        out3 = commands.importar_da_api(date(2026, 10, 14))
        check('a data que falhou volta em failed com o motivo',
              [f['date'] for f in out3['failed']] == ['2026-10-15']
              and '502' in out3['failed'][0]['reason'], out3['failed'])
        respostas['20261014'] = RuntimeError('401 Unauthorized')
        msg = None
        try:
            commands.importar_da_api(date(2026, 10, 14))
        except RuntimeError as exc:
            msg = str(exc)
        check('as duas falhando e erro, com os motivos', msg and '401' in msg and '502' in msg, msg)

        print('\n== 6. a rota, o laco e o cadastro ==')
        respostas.update({'20261021': [_trade('STP-XE-ROTA-0-0', '26D04217190',
                                              [_evento('EV-R', '2026-10-21', '2026-10-21')])],
                          '20261022': []})
        cl = app.test_client()
        with cl.session_transaction() as ss:
            ss['authenticated'] = True
            ss['user_sid'] = 'T000000'
            ss['user_name'] = 'Teste'
            ss['session_ip'] = '127.0.0.1'
            ss['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
        sino[:] = []
        rr = cl.post('/api/unwinds/ndf/fx/import-api', json={'date': '2026-10-21'})
        js = rr.get_json() or {}
        check('POST /import-api importa a Reference Date',
              rr.status_code == 200 and [x['AthenaID'] for x in js.get('rows') or []]
              == ['STP-XE-ROTA-0-0'], (rr.status_code, js))
        check('e toca o sino da pagina', len(sino) == 1 and sino[0][3] == commands.PAGE, sino)
        respostas['20261028'] = RuntimeError('timeout')
        respostas['20261029'] = RuntimeError('timeout')
        rf = cl.post('/api/unwinds/ndf/fx/import-api', json={'date': '2026-10-28'})
        jf = rf.get_json() or {}
        check('API fora do ar e 502 com codigo e motivo, nunca "nenhuma recompra"',
              rf.status_code == 502 and jf.get('code') == 'unwind_api_failed'
              and 'timeout' in (jf.get('params') or {}).get('reason', ''), (rf.status_code, jf))
    finally:
        athena_api.get_json_url, athena_api.build_session = orig

    regras = {str(x) for x in app.url_map.iter_rules()}
    check('a rota da varredura do box saiu', '/api/unwinds/ndf/fx/scan' not in regras)
    check('o laco esta no wiring do routes como unwind-api',
          any(l == 'unwind-api' for l, _ in R._SCHEDULERS), [l for l, _ in R._SCHEDULERS])
    check('e o entrypoint expoe o mesmo start_scheduler',
          unw_ep.start_scheduler is commands.start_scheduler)
    check('a cada 30 minutos por padrao (OTC_UNWIND_API_POLL_MIN)',
          commands.POLL_MIN == int(os.getenv('OTC_UNWIND_API_POLL_MIN', '30') or 30), commands.POLL_MIN)
    sino[:] = []
    commands._avisar_pull({'rows': [], 'failed': []})
    check('pull sem recompra nova nao toca o sino', sino == [], sino)
    commands._avisar_pull({'rows': [{'AthenaID': 'X'}], 'failed': [], 'dates': ['2026-10-14']})
    check('recompra nova toca o sino, como Athena API, na pagina da recompra',
          len(sino) == 1 and sino[0][0] == commands.API_MAKER_SID and sino[0][3] == commands.PAGE,
          sino)

    seed = {(x['USE'], x['PRODUCT']): x for x in R._MAPPING_DEFS['api-links']['seed']}
    check('o seed do api-links tem Unwinds x NDF = o getTradesBySettle',
          seed.get(('Unwinds', 'NDF'), {}).get('URL') == R._NDFC_API_URL_FALLBACK)
    orig_reg = athena_api.registered_url
    try:
        athena_api.registered_url = lambda *a, **k: None
        check('sem a linha no cadastro, vale o endereco do Daily Settlement (o do Cockpit)',
              commands._api_url(date(2026, 10, 14)) == R._ndfc_api_url(date(2026, 10, 14)))
        athena_api.registered_url = lambda uso, produto=None, date=None: (
            'https://outro.host/getTradesBySettle?product=NDF&date=' + str(date)
            if (uso, produto) == ('Unwinds', 'NDF') else None)
        check('com a linha Unwinds x NDF, vale a linha',
              commands._api_url(date(2026, 10, 14))
              == 'https://outro.host/getTradesBySettle?product=NDF&date=20261014')
    finally:
        athena_api.registered_url = orig_reg

    tpl = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'unwinds-ndf-fx.html'),
                  encoding='utf-8').read()
    check('a tela: Import com o dropzone vazio puxa da API',
          'if (!files.length) { return runApi(); }' in tpl and "'/api/unwinds/ndf/fx/import-api'" in tpl)
    check('e nao varre mais o box', '/api/unwinds/ndf/fx/scan' not in tpl and 'runScan' not in tpl)
    for lang in ('en', 'br', 'es'):
        d = json.load(io.open(os.path.join(ROOT, 'apps', 'static', 'data', 'translations',
                                           lang + '.json'), encoding='utf-8'))
        check('a frase do dropzone traduzida em %s' % lang, 'API' in d.get('unw-dropzone-hint', ''))

    print('')
    if FALHAS:
        print('FALHAS (%d): %s' % (len(FALHAS), ', '.join(FALHAS)))
        return 1
    print('tudo ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
