# -*- coding: utf-8 -*-
"""check_swap_strategy.py — Live Position › Swap › Strategy.

  1. a leitura das DUAS consultas do MID de Swap da B3, pelo CONTEUDO: a lista
     (ConsultaEstrategiaContratos) e os dados (ConsultaDadosEstrategia, com o
     titulo acima do cabecalho e a virgula do "B3 S.A. - BRASIL, BOLSA,
     BALCAO" que nao pode virar separador); o `#` do contrato sai; xlsx com
     numero vira texto pt-BR sem lixo binario;
  2. a fusao por contrato: a lista nao apaga os dados, os dados nao apagam o
     nome; Status Complete/Pending;
  3. a API ponta a ponta no armazem real (tmp): import, data (Contraparte e
     LOB do Live Position pelo contrato), edit, delete, erros por codigo;
  4. o Swap Calculator: contrato de estrategia (as duas curvas VCP na posicao)
     tem as pontas pela consulta — Indicador_1/_2 (USD pelo nome da moeda no
     currency-base), taxa Cupom_n, Percentual, Base taxa Cupom; so a lista
     importada e lacuna dita; contrato fora de estrategia nao muda;
  5. o menu tem o item e as tres traducoes existem.

Roda em tmp: DATA_DIR/DATABASE_DIR proprios, posicao stub.
"""
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
RAIZ = tempfile.mkdtemp(prefix='otc-sst-')
os.environ['OTC_DATA_DIR'] = RAIZ
os.environ['OTC_DATABASE_DIR'] = os.path.join(RAIZ, 'db')
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra) else ''))
    if not cond:
        FALHAS.append(nome)


LISTA = ('Código da Estratégia\tNome da Estratégia\tCódigo do Contrato\n'
         'SWP00001153\tAporte SOFR Flex x ME\t23F02430278\n'
         'SWP00001153\tAporte SOFR Flex x ME\t23F02430033\n'
         'SWP00001072\tSwap Aporte Libor x ME\t21C00035804\n').encode('cp1252')
DADOS = ('B3 S.A. - BRASIL, BOLSA, BALCÃO\n'
         'Dados da Estratégia de Derivativos - Data e Hora da Consulta: 30/09/2026 - 09:31:24\n'
         '\n'
         'Critério de Busca:\n'
         '\n'
         'Código do Contrato\tParte (Conta)\tCurva - Parte\tValor Base Remanescente\t'
         'Código da Estratégia\tIndicador_1\tIndicador_2\n'
         '#23F02430278\t73760.00-9\tVCP\t51.670.430,98\tSWP00001153\tUSD\tSOFR Overnight\n'
         '#23F02430033\t73760.00-9\tVCP\t133.233.419,70\tSWP00001153\tUSD\tSOFR Overnight\n').encode('cp1252')


def main():
    from apps.pages.features.swap_strategy import commands, domain, queries

    print('== 1. leitura pelo conteudo ==')
    lst = commands.parse_file(LISTA, 'Swap-MID-ConsultaEstrategiaContratos.tsv')
    check('lista: 3 contratos, kind list', lst['kind'] == 'list' and len(lst['records']) == 3, lst)
    dad = commands.parse_file(DADOS, 'Swap-MID-ConsultaDadosEstrategia (1).tsv')
    r0 = dad['records'][0]
    check('dados: kind data, # removido', dad['kind'] == 'data' and r0['Contract'] == '23F02430278', r0)
    check('dados: hora da consulta', dad['consulta'] == '30/09/2026 - 09:31:24', dad['consulta'])
    check('dados: colunas proprias na ordem, sem as de identidade',
          [p[0] for p in r0['Details']] == ['Parte (Conta)', 'Curva - Parte', 'Valor Base Remanescente',
                                            'Indicador_1', 'Indicador_2'], r0['Details'])
    check('dados: estrategia pela coluna', r0['StrategyCode'] == 'SWP00001153')
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['B3 S.A. - BRASIL, BOLSA, BALCÃO'])
    ws.append(['Código do Contrato', 'Valor Base Remanescente', 'Data de Vencimento', 'Código da Estratégia'])
    ws.append(['#23F02430033', 133233419.7, datetime(2028, 3, 31), 'SWP00001153'])
    buf = io.BytesIO()
    wb.save(buf)
    x = commands.parse_file(buf.getvalue(), 'dados.xlsx')['records'][0]['Details']
    check('xlsx: numero pt-BR e data dd/mm/aaaa',
          x == [['Valor Base Remanescente', '133.233.419,7'], ['Data de Vencimento', '31/03/2028']], x)
    try:
        commands.parse_file(b'a\tb\n1\t2\n', 'x.tsv')
        check('arquivo sem Codigo do Contrato recusa', False)
    except commands.CommandError as exc:
        check('arquivo sem Codigo do Contrato recusa por codigo', exc.code == 'strategy_header_unknown', exc.code)

    print('== 2. fusao ==')
    m, n, u = domain.merge([], lst, 'l.tsv', 'A', 't1')
    m, n2, u2 = domain.merge(m, dad, 'd.tsv', 'A', 't2')
    by = {e['Contract']: e for e in m}
    check('lista + dados: nome preservado, dados gravados',
          by['23F02430278']['StrategyName'] == 'Aporte SOFR Flex x ME' and by['23F02430278']['Details'], by['23F02430278'])
    m, _, _ = domain.merge(m, lst, 'l2.tsv', 'A', 't3')
    by = {e['Contract']: e for e in m}
    check('a lista de novo nao apaga os dados', bool(by['23F02430278']['Details']))
    check('status', domain.status_of(by['23F02430278']) == 'Complete'
          and domain.status_of(by['21C00035804']) == 'Pending')

    print('== 3. API ponta a ponta ==')
    from apps import create_app
    from apps.config import DebugConfig
    app = create_app(DebugConfig)
    from apps.pages import routes as R
    queries.position_map = lambda ref=None: ({'23F02430278': {'counterparty': 'CLIENTE X SA', 'lob': 'CEM'}},
                                             '2026-09-29')
    cl = app.test_client()
    with cl.session_transaction() as ss:
        ss['authenticated'] = True
        ss['user_sid'] = 'A000001'
        ss['user_name'] = 'Teste'
        ss['session_ip'] = '127.0.0.1'
        ss['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    api = '/api/live-position-swap-strategy'
    check('pagina 200', cl.get('/live-position-swap-strategy').status_code == 200)
    for nome, dados in (('Swap-MID-ConsultaEstrategiaContratos.tsv', LISTA),
                        ('Swap-MID-ConsultaDadosEstrategia.tsv', DADOS)):
        r = cl.post(api + '/import-file', data={'file': (io.BytesIO(dados), nome)},
                    content_type='multipart/form-data')
        check('import ' + nome, r.status_code == 200 and r.get_json()['success'], r.get_json())
    d = cl.get(api + '/data').get_json()
    by = {e['Contract']: e for e in d['entries']}
    check('3 contratos no cadastro', len(by) == 3, list(by))
    e = by['23F02430278']
    check('contraparte e LOB do Live Position', e['Counterparty'] == 'CLIENTE X SA' and e['LOB'] == 'CEM', e)
    check('status Complete com dados', e['Status'] == 'Complete' and e['Details'][0][0] == 'Parte (Conta)', e)
    check('fora da posicao: vazio', by['21C00035804']['Counterparty'] == '' and not by['21C00035804']['InPosition'])
    check('source_date', d['source_date'] == '2026-09-29')
    r = cl.post(api + '/edit', data=json.dumps({'id': '#23f02430278', 'fields': {'StrategyName': 'Novo', 'Contract': 'X'}}),
                content_type='application/json')
    e = {x['Contract']: x for x in cl.get(api + '/data').get_json()['entries']}['23F02430278']
    check('edit so dos campos editaveis', r.status_code == 200 and e['StrategyName'] == 'Novo', e)
    r = cl.post(api + '/edit', data=json.dumps({'id': 'NAOEXISTE', 'fields': {}}), content_type='application/json')
    check('edit de contrato ausente: 404 com codigo', r.status_code == 404 and r.get_json()['code'] == 'strategy_not_found')
    r = cl.post(api + '/import-file', data={'file': (io.BytesIO(b'x\ty\n'), 'a.tsv')}, content_type='multipart/form-data')
    check('import invalido: 400 com codigo', r.status_code == 400 and r.get_json()['code'] == 'strategy_header_unknown')
    r = cl.post(api + '/delete', data=json.dumps({'ids': ['21C00035804']}), content_type='application/json')
    check('delete', r.get_json().get('deleted') == 1 and len(cl.get(api + '/data').get_json()['entries']) == 2)

    print('== 4. Swap Calculator: o contrato de estrategia puxa as pontas daqui ==')
    from datetime import date
    from apps.pages.features.tools import queries as TQ
    from apps.pages.platform import swap_flows as SF
    P = SF.POS
    vals = [''] * 170
    vals[P['contrato']] = '23F02430278'
    vals[P['tipo_contrato']] = '01'
    vals[P['inicio']] = '26/06/2023'
    vals[P['vencimento']] = '31/03/2028'
    vals[P['remanescente']] = '51670430,98'
    for k in (0, 1):
        vals[P['indice'][k]] = 'C07'          # VCP na posicao: as duas curvas
        vals[P['nome_classe'][k]] = 'VCP'
        vals[P['taxa'][k]] = '9,99'            # a taxa da posicao NAO e a da estrategia
    TQ._posicao_swap = lambda b3: ((vals, {}), '2026-09-29')
    TQ._fluxos_do_contrato = lambda *a, **k: []
    TQ._ptax_do_fixing = lambda moeda, fim, n: (5.0, date(2026, 9, 28), '')
    TQ.taxa_do_fixing = lambda *a, **k: (0.043, date(2026, 9, 28), '')
    R._swapindex_name = lambda c: 'VCP'
    regras = [{'MATCH': 'DI', 'MODE': 'Exact', 'INDEX': 'cdi'},
              {'MATCH': 'SOFR', 'MODE': 'Contains', 'INDEX': 'sofr', 'CURRENCY': 'USD'},
              {'MATCH': 'TERM SOFR', 'MODE': 'Contains', 'INDEX': 'term_sofr', 'CURRENCY': 'USD'},
              {'MATCH': 'DOLAR', 'MODE': 'Contains', 'INDEX': 'cambio', 'CURRENCY': 'USD'}]
    cadastros = {'tools-swap-index': regras,
                 'currency-base': [{'SIMBOLO': 'USD', 'DESCRICAO DO CAMPO': 'DOLAR DOS EUA'}]}
    R._mapping_rows = lambda key, *a, **k: cadastros.get(key, [])
    check('USD pelo nome da moeda no currency-base', (TQ.regra_da_estrategia(regras, 'USD') or {}).get('INDEX') == 'cambio')
    check('Term SOFR vence SOFR', (TQ.regra_da_estrategia(regras, 'Term SOFR') or {}).get('INDEX') == 'term_sofr')
    import apps.pages.platform.swap_strategies as SS
    SS.find = lambda c: {'Contract': '23F02430278', 'StrategyCode': 'SWP00001229',
                         'StrategyName': 'Swap SOFR Flex x BRL Aj. de Tx',
                         'Details': [['Indicador_1', 'DI'], ['Indicador_2', 'Term SOFR'],
                                     ['Percentual Indicador_2', '100'], ['taxa Cupom_1', '0,6'],
                                     ['taxa Cupom_2', '1,4'], ['Base taxa Cupom_2', '360']]}
    with app.test_request_context():
        d = TQ.swap_prefill('23F02430278')
    a_, p_ = d['ativa'], d['passiva']
    check('estrategia na resposta', d.get('estrategia', {}).get('codigo') == 'SWP00001229' and d['estrategia']['dados'], d.get('estrategia'))
    # A Parte (banco) e o `_2`: na 'SOFR Flex x BRL' ela RECEBE o SOFR (mesa, 30/09/2026).
    check('ativa (Parte) = Indicador_2 (Term SOFR) com taxa Cupom_2', a_['indexador'] == 'term_sofr' and float(a_['taxa']) == 1.4, a_)
    check('passiva (Contraparte) = Indicador_1 (DI) com taxa Cupom_1', p_['indexador'] == 'cdi' and float(p_['taxa']) == 0.6, p_)
    check('Base taxa Cupom 360 -> act_360', a_['convencao'] == 'act_360', a_['convencao'])
    check('fonte marca a estrategia', a_.get('fonte', {}).get('estrategia', {}).get('indicador') == 'Term SOFR')
    # A imagem da mesa (23F02369705): USD x SOFR Overnight — a cotacao inicial
    # e o D-2 da moeda vem da estrategia, nao da Denominacao (que diz T-1).
    vals[P['denominacao'][0]] = 'TERM SOFR 3M - Fixings PTAX-Ask T-1 - (3M SOFR + 0.75%)*1.1765 A/360'
    SS.find = lambda c: {'Contract': '23F02430278', 'StrategyCode': 'SWP00001153',
                         'Details': [['Indicador_1', 'USD'], ['Indicador_2', 'SOFR Overnight'],
                                     ['taxa Cupom_1', '3,8500'], ['Cotação Inicial Moeda', '4,77500000'],
                                     ['Data Cotação Moeda Final', 'D-2'], ['Valor Inicial 1', '4,77500000'],
                                     ['Fixing 1', 'D-2'], ['Contagem de Dias_1', 'ACT/360'],
                                     ['Contagem de Dias_2', 'ACT/360'], ['Fixing 2', 'D-1'],
                                     ['Valor Inicial 2', '1,00000000'], ['Lookback da Taxa_1', 'D-5']]}
    with app.test_request_context():
        d = TQ.swap_prefill('23F02430278')
    # 23F02369705 (Aporte SOFR Flex x ME): o banco RECEBE o SOFR — ativa = `_2`.
    p_, a_ = d['ativa'], d['passiva']
    check('USD: cambio com a cotacao inicial da estrategia', a_['indexador'] == 'cambio'
          and float(a_['ptax_inicial']) == 4.775, a_)
    check('USD: D-2 da estrategia vence o T-1 da Denominacao', a_['ptax_offset'] == '2', a_.get('ptax_offset'))
    check('USD: cotacao inicial fora das lacunas', 'passiva.ptax_inicial' not in d['missing'], d['missing'])
    check('23F02369705: SOFR na ponta ATIVA (o banco recebe), USD na passiva',
          d['ativa']['indexador'] == 'sofr' and d['passiva']['indexador'] == 'cambio', (d['ativa']['indexador'], d['passiva']['indexador']))
    check('SOFR: a cotacao sem numero vale na ponta em moeda', p_['indexador'] == 'sofr'
          and float(p_['ptax_inicial']) == 4.775 and p_['ptax_offset'] == '2', p_)
    check('SOFR: o Fixing 2/Valor Inicial 2 do indice nao viram a moeda', p_['ptax_offset'] == '2'
          and float(p_['ptax_inicial']) == 4.775, p_)
    check('SOFR: Lookback da Taxa_1 (o unico) vai para a ponta de SOFR', p_.get('lookback') == '5'
          and not a_.get('lookback'), (p_.get('lookback'), a_.get('lookback')))
    check('Contagem de Dias ACT/360', a_['convencao'] == 'act_360' and p_['convencao'] == 'act_360')
    SS.find = lambda c: {'Contract': '23F02430278', 'StrategyCode': 'SWP00001229', 'Details': None}
    with app.test_request_context():
        d = TQ.swap_prefill('23F02430278')
    check('so a lista: pontas pela posicao e a lacuna dita', 'estrategia' in d['missing'] and not d['estrategia']['dados'])
    SS.find = lambda c: None
    with app.test_request_context():
        d = TQ.swap_prefill('23F02430278')
    check('contrato fora de estrategia: nada muda', 'estrategia' not in d and 'estrategia' not in d['missing'])

    print('== 5. menu e traducoes ==')
    nav = open(os.path.join(ROOT, 'apps', 'templates', 'partials', 'sidenav.html'), encoding='utf-8').read()
    check('item no menu', 'href="/live-position-swap-strategy"' in nav and 'data-lang="nav-strategy"' in nav)
    for l in ('en', 'br', 'es'):
        tr = json.load(open(os.path.join(ROOT, 'apps', 'static', 'data', 'translations', l + '.json'), encoding='utf-8'))
        check('traducao ' + l, all(k in tr for k in ('nav-strategy', 'sst-title', 'sst-col-counterparty', 'sst-col-lob')))


if __name__ == '__main__':
    main()
    print('\n%d falha(s)' % len(FALHAS))
    sys.exit(1 if FALHAS else 0)
