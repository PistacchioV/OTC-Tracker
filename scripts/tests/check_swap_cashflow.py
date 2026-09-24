# -*- coding: utf-8 -*-
"""Regressão da página New Deals › Swap › Cashflow (o swap da CEM, 21/09/2026).

O que este script prende:

1. o CONTRATO com o catálogo: as colunas do `domain` são as do
   `new_deals/catalog.py` (feature não importa feature — cópia com guarda),
   o cronograma é o `_SCHEDULE`, e as rotas que o `new_deals-product.html`
   chama existem (e o stub 501 não sobrou para o cashflow);
2. o Deal Ticket é o MESMO do Bullet (lido pela horizontal
   `platform/swap_deal_ticket`): a aba do DT com a tabela Cash Flow dá o MESMO
   deal que o Bullet daria, mais o cronograma, o tipo de amortização, a LOB e
   a paridade do DT da CEM; o PDF chega ao mesmo cronograma; o arquivo é lido
   pelo CONTEÚDO (xlsx renomeado, e-mail com o DT anexo);
3. o registro 0301 de Fluxo Não Constante (4.2.7 v00003) tem 2021 caracteres
   e leva, CAMPO A CAMPO, os mesmos valores do 0301 de Pagamento Final do
   Bullet nas posições deste layout (as regras das pernas são uma só);
4. o 0034 (o cronograma): header 38, registro 62, uma linha de 194 por fluxo,
   com o Meu Número do contrato, a ponta pela conta menor e o código do
   cadastro `swap-amortizacao`;
5. as lacunas são ESTRUTURADAS (código + params) e todo código tem texto nas
   três línguas do `_TRANS` da página;
6. import (dry-run → batch com `_replace` → Amend), edit (cronograma, 4-olhos,
   B3 ID = mapeamento → Pending Confirmation / Intrag), confirm, delete, send
   (cp1252, lote com lacuna recusa tudo) e o sino com o rótulo do catálogo;
7. os vizinhos: o Monitor soma a linha no card da LOB, a segregação das
   confirmações lê o cashflow, o backfill tem família para a pasta, e o
   e-mail do Economic Affirmation leva a tabela Cash Flow.

Roda em tmp: o cache, a pasta Conecta e a Intrag apontam para temporários, e
o sino, o Pending Confirmation e a esteira são espiões.
"""
import io
import os
import re
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
from apps.config import Config as _Cfg                      # noqa: E402
_Cfg.FOUR_EYES = True   # prova a trava da PROD; na dev o maker/checker e desligado (§553)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else '  FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra != '') else ''))
    if not cond:
        FALHAS.append(nome)


FLOWS = [('2026-09-15', '2026-12-15', 0.25, 63, 91), ('2026-12-15', '2027-03-15', 0.25, 58, 90),
         ('2027-03-15', '2027-06-07', 0.5, 58, 84)]


def _dt_sheet(ws, client, spn, vcp_holder, van_holder, payer, categoria, cashflow=True):
    """O DT do Swap Bullet (o mesmo do `check_swap_bullet`) + o que o de
    cashflow da CEM traz a mais (SUPOSIÇÃO de layout, a do `domain`)."""
    ws['A1'] = 'DEAL TICKET SWAP VCP'
    ws['A4'] = 'Swap Com Opção de Arrependimento - Call'
    ws['A7'] = 'Cliente'; ws['B7'] = client
    ws['A8'] = 'SPN'; ws['B8'] = spn
    ws['A9'] = 'Inicio'; ws['B9'] = datetime(2026, 9, 15); ws['D9'] = 'Funcionalidades'; ws['E9'] = 'Opção de Arrependimento'; ws['G9'] = 'Agenda de premios'; ws['H9'] = 'Sim'
    ws['A10'] = 'Vencimento'; ws['B10'] = datetime(2027, 6, 7); ws['D10'] = 'Ativo VCP'; ws['E10'] = vcp_holder; ws['G10'] = 'Data de Pagamento do Premio'; ws['H10'] = datetime(2026, 9, 16)
    ws['A11'] = 'Valor Base'; ws['B11'] = 'BRL 346.000,00'; ws['D11'] = 'Ativo Curva Vanilla'; ws['E11'] = van_holder; ws['G11'] = 'Pagador do Premio'; ws['H11'] = payer
    ws['G12'] = 'Premio'; ws['H12'] = 23355
    ws['A15'] = 'Curva VCP'; ws['D15'] = 'Curva Vanilla'; ws['G15'] = 'Informações Curvas VCP'
    ws['A16'] = 'Percentual'; ws['B16'] = 1.0; ws['B16'].number_format = '0.00%'; ws['D16'] = 'Percentual'; ws['E16'] = 1.0; ws['E16'].number_format = '0.00%'
    ws['G16'] = 'Preço Inicial(Cupom Limpo)'; ws['H16'] = '100.00% Spot'
    ws['A17'] = 'Categoria'; ws['B17'] = 'VCP'; ws['D17'] = 'Categoria'; ws['E17'] = 'JUROS'; ws['G17'] = 'Fonte de Informação'; ws['H17'] = 'Bloomberg'
    ws['A18'] = 'Curva'; ws['B18'] = 'MSFT US'; ws['D18'] = 'Curva'; ws['E18'] = 'PRÉ FIXADO BRL'; ws['G18'] = 'Data de Cotação'; ws['H18'] = datetime(2027, 6, 4)
    ws['A20'] = 'Sinal +/-'; ws['B20'] = '+'; ws['D20'] = 'Sinal +/-'; ws['E20'] = '+'; ws['G20'] = 'Denominação'; ws['H20'] = 'Quanto (ausencia variação cambial)'
    ws['A21'] = 'Juros'; ws['B21'] = 0; ws['B21'].number_format = '0.00%'; ws['D21'] = 'Juros'; ws['E21'] = 0; ws['E21'].number_format = '0.00%'; ws['H21'] = 'Cupom Limpo inicial em percentual'
    ws['A22'] = 'Lim Superior'; ws['B22'] = '117% Spot'; ws['H22'] = 'Preco in ativo Close 15-Sep-26'
    ws['A23'] = 'Lim Inferior'
    ws['A25'] = 'OBS: Caso aplicável, colocar também no campo denominação as informações dos limitadores'
    ws['A27'] = 'Informações do Indicador'
    ws['A29'] = 'Categoria da Curva VCP'; ws['B29'] = categoria
    ws['A30'] = 'Código'; ws['B30'] = 10615
    ws['A31'] = 'Curva VCP'; ws['B31'] = 'MSFT US'
    ws['A32'] = 'Descrição da Curva VCP'; ws['B32'] = 'Microsoft Corporation'
    ws['A34'] = 'Informações necessárias para registro'; ws['B34'] = 'Consultar o Manual de Operações de Swap'
    ws['A35'] = 'Link para o Manual de Operações'; ws['B35'] = 'www.b3.com.br'
    if not cashflow:
        return
    ws['A13'] = 'Tipo de Amortização'; ws['B13'] = 'Sobre Valor Base Original'
    ws['D13'] = 'LOB'; ws['E13'] = 'CEM'
    ws['A36'] = 'Paridade Inicial'; ws['B36'] = '5,4321'
    ws['A38'] = 'Cash Flow'
    for col, h in zip('ABCDEF', ('Data Início', 'Data Pagamento', 'Amortização (%)', 'Dias Úteis (BD/252)',
                                 'Dias Corridos (Act/360)', 'Data Fixing')):
        ws[col + '39'] = h
    for i, (ini, pg, am, du, dc) in enumerate(FLOWS):
        r = str(40 + i)
        ws['A' + r] = datetime.strptime(ini, '%Y-%m-%d'); ws['B' + r] = datetime.strptime(pg, '%Y-%m-%d')
        ws['C' + r] = am; ws['C' + r].number_format = '0.00%'; ws['D' + r] = du; ws['E' + r] = dc


def build_xlsx(cashflow=True):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active; ws.title = 'Deal Ticket Cliente (CETIP)'
    _dt_sheet(ws, 'Safra', 281808, 'Cliente', 'Banco JP Morgan', 'Cliente', 'ACOES INTERNACIONAIS', cashflow)
    ws2 = wb.create_sheet('B2B - Atacama')
    _dt_sheet(ws2, 'Atacama', 9632845, 'Banco JP Morgan', 'Atacama', 'Banco JP Morgan', 'INDICES INTERNACIONAIS', cashflow)
    ws3 = wb.create_sheet('Recap'); ws3['A1'] = 'Recap'; ws3['A2'] = 'nada aqui'
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


PDF_DT = (
    "DEAL TICKET SWAP VCP\n"
    "Swap Com Opção de Arrependimento - Call\n"
    "Cliente Safra\n"
    "SPN 281808\n"
    "Inicio 15-Sep-26 Funcionalidades Opção de Arrependimento Agenda de premios Sim\n"
    "Vencimento 7-Jun-27 Ativo VCP Cliente Data de Pagamento do Premio 16-Sep-26\n"
    "Valor Base BRL 346.000,00 Ativo Curva Vanilla Banco JP Morgan Pagador do Premio Cliente\n"
    "Premio 23.355,00\n"
    "Curva VCP Curva Vanilla Informações Curvas VCP\n"
    "Percentual 100,00% Percentual 100,00% Preço Inicial(Cupom Limpo) 100.00% Spot\n"
    "Categoria VCP Categoria JUROS Fonte de Informação Bloomberg\n"
    "Curva MSFT US Curva PRÉ FIXADO BRL Data de Cotação 04/jun/27\n"
    "Sinal +/- + Sinal +/- + Denominação Quanto (ausencia variação cambial)\n"
    "Juros 0,00% Juros 0,00% Cupom Limpo inicial em percentual\n"
    "Lim Superior 117% Spot Preco in ativo Close 15-Sep-26\n"
    "Lim Inferior\n"
    "OBS: Caso aplicável, colocar também no campo denominação as informações dos limitadores\n"
    "Informações do Indicador\n"
    "Categoria da Curva VCP ACOES INTERNACIONAIS\n"
    "Código 10615\n"
    "Curva VCP MSFT US\n"
    "Descrição da Curva VCP Microsoft Corporation\n"
    "Informações necessárias para registro Consultar o Manual\n"
)
PDF_CF = (
    "Cash Flow\n"
    "Data Início Data Pagamento Amortização (%) Dias Úteis Dias Corridos\n"
    "15/09/2026 15/12/2026 25,00% 63 91\n"
    "15/12/2026 15/03/2027 25,00% 58 90\n"
    "15/03/2027 07/06/2027 50,00% 58 84\n"
)


def _pos(line, a, b):
    return line[a - 1:b]


def main():
    from run import app
    from apps.pages import routes as R
    from apps.pages.features.new_deals import catalog
    from apps.pages.features.swap_bullet import domain as bullet
    from apps.pages.features.swap_bullet import queries as bullet_q
    from apps.pages.features.swap_cashflow import commands, domain, entrypoint, queries
    from apps.pages.features.swap_cashflow.infra import persistence
    from apps.pages.platform import swap_deal_ticket as dtk
    from apps.pages.platform import swap_new_deals as sw

    tmp = tempfile.mkdtemp(prefix='otc-swc-')
    persistence.cache_dir = lambda: os.path.join(tmp, 'cache')
    R.CONECTA_NEW_PATH = os.path.join(tmp, 'conecta')
    SINO = []
    _notif_orig = R._create_notification
    R._create_notification = lambda *a, **k: SINO.append(a)
    REF = [{'SPN': '281808', 'COUNTERPARTY': 'BANCO SAFRA S.A.', 'TAX ID': '58.160.789/0001-28',
            'B3 ACCOUNT': '74220.00-5'}]
    _ref_orig = R._refdata_records
    R._refdata_records = lambda: REF
    _rows_orig = R._mapping_rows

    def _rows(key):
        if key == 'le-spn':
            return [{'LE': 'ATACAMA', 'NAME': 'ATACAMA MULTIMERCADO FI', 'SPN': '9632845', 'NOTES': ''}]
        return _rows_orig(key)
    R._mapping_rows = _rows
    try:
        _main(R, app, catalog, bullet, bullet_q, commands, domain, entrypoint, queries, persistence, dtk, sw,
              tmp, SINO)
    finally:
        R._create_notification = _notif_orig
        R._refdata_records = _ref_orig
        R._mapping_rows = _rows_orig
    print('\n%s' % ('TUDO OK' if not FALHAS else '%d FALHA(S): %s' % (len(FALHAS), FALHAS)))
    return 1 if FALHAS else 0


def _main(R, app, catalog, bullet, bullet_q, commands, domain, entrypoint, queries, persistence, dtk, sw,
          tmp, SINO):
    print('== 1. o contrato com o catálogo e com a tela ==')
    pagina = catalog.PAGES['/new_deals-swap-cashflow']
    check('as colunas do domain são as do catálogo (campo e rótulo, na ordem)',
          [tuple(c[:2]) for c in pagina['columns']] == list(domain.SWC_COLUMNS),
          [c for c in pagina['columns'] if tuple(c[:2]) not in domain.SWC_COLUMNS])
    check('o cronograma é o _SCHEDULE do catálogo', [c[0] for c in pagina['schedule']] == list(domain.SCHEDULE_FIELDS)
          and pagina['schedule_field'] == domain.SCHEDULE_FIELD)
    check('o rótulo do sino é o `label` do catálogo', entrypoint.PAGE == pagina['label'])
    check('o rótulo tem destino nos três mapas', R._notif_page_url(entrypoint.PAGE) == '/new_deals-swap-cashflow')
    regras = {str(r): r for r in app.url_map.iter_rules()}
    tpl = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'new_deals-product.html'), encoding='utf-8').read()
    acoes = sorted(set(re.findall(r"PAGE\.api \+ '/([a-z\-/]+)", tpl)))
    check('toda ação que a tela chama tem rota ESTÁTICA', all(('/api/new-deals/swap-cashflow/' + a) in regras for a in acoes),
          [a for a in acoes if ('/api/new-deals/swap-cashflow/' + a) not in regras])
    check('as ações são as esperadas', set(acoes) >= {'import-file', 'cache/batch', 'cache/search', 'economic-affirmation',
                                                      'preview', 'delete', 'confirm', 'send-conecta', 'edit', 'add'}, acoes)
    check('o stub 501 não atende mais o cashflow',
          regras['/api/new-deals/swap-cashflow/<path:resto>'].endpoint.endswith('api_swap_cashflow_unknown'))

    print('== 2. o Deal Ticket (o do Bullet + a tabela Cash Flow) ==')
    xlsx = build_xlsx()
    sheets = sw.sheets_from_xlsx(xlsx)
    grade, flows = domain.split_cashflow_grid(sheets[0][1])
    check('três fluxos lidos da tabela', len(flows) == 3, flows)
    check('fluxo 1: datas ISO, 25% (formato de porcentagem do Excel), DU/DC inteiros',
          flows[0] == {'StartDate': '2026-09-15', 'PaymentDate': '2026-12-15', 'AmortizationPct': '25',
                       'BusinessDays': '63', 'CalendarDays': '91', 'FixingDate': ''}, flows[0])
    check('a tabela sai da grade (o parser do DT não a lê como rótulo)',
          not any('Data Pagamento' in str(c) or 'Cash Flow' == str(c) for r in grade for c in r))
    raw = dtk.parse_dt_grid(grade)
    base = dtk.deal_from_raw(dtk.parse_dt_grid(sw.sheets_from_xlsx(build_xlsx(cashflow=False))[0][1]), '2026-09-16')
    cf = domain.deal_from_raw(raw, flows, '2026-09-16', domain.cem_extras_grid(grade))
    comuns = [k for k in bullet.SWB_FIELDS if k not in ('Maker', 'Checker', 'Type', 'LOB', 'FXStart')]
    check('os campos do Bullet saem IGUAIS aos do DT sem a tabela (um parser só)',
          [k for k in comuns if cf.get(k) != base.get(k)] == [], [k for k in comuns if cf.get(k) != base.get(k)])
    check('tipo Fluxo de Caixa, chave SWC-, Deal e B3 ID em branco',
          cf['Type'] == 'Fluxo de Caixa' and cf['_id'].startswith('SWC-') and cf['Deal'] == '' and cf['B3ID'] == '')
    check('cronograma no deal e a contagem', len(cf['CashFlows']) == 3 and cf['Flows'] == '3')
    check('o que o DT da CEM traz a mais: LOB, tipo de amortização, paridade inicial',
          cf['LOB'] == 'CEM' and cf['AmortizationType'] == 'Sobre Valor Base Original' and cf['FXStart'] == '5.4321',
          (cf['LOB'], cf['AmortizationType'], cf['FXStart']))
    sem_lob = domain.deal_from_raw(dtk.parse_dt_grid(sw.sheets_from_xlsx(build_xlsx(cashflow=False))[0][1]), [], '2026-09-16')
    check('DT sem LOB: a LOB fica em BRANCO (não se chuta EDG)', sem_lob['LOB'] == '')
    check('linha do topo com datas NÃO é tabela (Inicio | data | Vencimento | data)',
          domain.split_cashflow_grid([['Inicio', '2026-09-15', 'Vencimento', '2027-06-07'],
                                      ['Data Pagamento', '2026-12-15']])[1] == [])
    # PDF: o mesmo cronograma, e o resto do texto chega ao MESMO deal do Bullet.
    texto, fl_pdf = domain.split_cashflow_text(PDF_DT + PDF_CF)
    check('PDF: os três fluxos pela ordem do cabeçalho', [(f['StartDate'], f['PaymentDate'], f['AmortizationPct'], f['BusinessDays'])
                                                          for f in fl_pdf] == [(a, b, str(int(c * 100)), str(d)) for a, b, c, d, _e in FLOWS], fl_pdf)
    check('PDF: sem a tabela o texto dá o MESMO raw do DT', dtk.parse_dt_text(texto) == dtk.parse_dt_text(PDF_DT))
    # Pelo CONTEÚDO: xlsx com nome de .txt, e o DT anexo num .eml.
    itens = sw.read_upload('dt.txt', xlsx)
    check('xlsx renomeado para .txt é lido pelo conteúdo', [t for _k, t, _p in itens][:2] == ['Deal Ticket Cliente (CETIP)', 'B2B - Atacama'])
    from email.message import EmailMessage
    em = EmailMessage(); em['Subject'] = 'DT swap'; em['From'] = 'a@b.com'; em['To'] = 'c@d.com'
    em.set_content('segue'); em.add_attachment(xlsx, maintype='application',
                                               subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                               filename='DT CEM.xlsx')
    itens_eml = sw.read_upload('mail.eml', em.as_bytes())
    check('.eml: o DT anexo vira as abas', len(itens_eml) == 3 and itens_eml[0][1].startswith('DT CEM.xlsx › '))
    try:
        sw.read_upload('x.bin', b'\x00\x01 nada')
        check('arquivo que não é DT recusa', False)
    except ValueError:
        check('arquivo que não é DT recusa', True)

    print('== 3. o 0301 de Fluxo Não Constante = as regras do Bullet nas posições do 4.2.7 ==')
    accounts = queries.own_accounts()
    check('contas próprias do b3-accounts', accounts.get('JPM') == '73760009' and accounts.get('ATACAMA') == '85398005', accounts)
    commands.enrich(cf)
    check('enrich: a contraparte do Reference Data pela SPN (conta própria, sem CNPJ)',
          cf['Client'] == 'BANCO SAFRA S.A.' and cf['ClientAccount'] == '74220005' and cf['ClientRefData'] == 'ok')
    codes = queries.codes_for(cf)
    check('código da amortização pelo cadastro swap-amortizacao', codes['amortization'] == '00', codes.get('amortization'))
    faltas = domain.missing_for_send(cf, codes, accounts, codes['amortization'])
    check('sem lacunas', faltas == [], domain.lacuna_texts(faltas))
    MY = '8985710698'
    for view, deal in (('client', cf),):
        vals = domain.contract_record_values(deal, view, accounts, codes, MY)
        linha = commands._record(commands.CONTRACT_FI_KEY, vals, view, deal)
        check('%s: 2021 caracteres' % view, len(linha) == domain.CONTRACT_RECORD_LENGTH, len(linha))
        bv = bullet.swap_record_values(dict(deal), view, accounts, bullet_q.codes_for(deal), MY)
        pares = [(str(s), str(s)) for s in range(1, 19)] + [(str(s), str(s)) for s in range(26, 40)] + \
            [('47', '41'), ('48', '42'), ('49', '43'), ('50', '44'), ('51', '45'), ('52', '46'),
             ('53', '47'), ('54', '48'), ('55', '49'), ('56', '50'), ('116', '98')]
        dif = [(b, c) for b, c in pares if b not in ('15', '17') and bv[b] != vals[c]]
        check('%s: os campos que os dois layouts têm saem IGUAIS aos do Bullet' % view, dif == [], dif)
        check('%s: posições do manual (tipo, Meu Número, contas, datas, valor base, curva, LOB)' % view,
              _pos(linha, 1, 10) == 'SWAP 10301' and _pos(linha, 11, 20) == MY and _pos(linha, 21, 28) == '73760009'
              and _pos(linha, 53, 60) == '74220005' and _pos(linha, 85, 92) == '20260915' and _pos(linha, 93, 100) == '20270607'
              and _pos(linha, 103, 118) == '0000000034600000' and _pos(linha, 121, 122) == '00'
              and _pos(linha, 634, 636) == 'C99' and _pos(linha, 691, 693) == 'C00'
              and _pos(linha, 1125, 1146) == '0000000000000100000000' and _pos(linha, 1884, 1897).strip() == 'CEM')
    hdr = R._fi_build_line(commands.CONTRACT_FI_KEY, 'header', domain.contract_header_values('JPMORGANBM', '20260916'))
    check('header do 0301 v00003', hdr == 'SWAP 00301JPMORGANBM          2026091600003', hdr)

    print('== 4. o 0034 (o cronograma) ==')
    h, reg, linhas = domain.flow_values(cf, 'client', accounts, MY, '1234567890', codes['amortization'], 'JPMORGANBM', '20260916')
    lh = R._fi_build_line(commands.FLOW_FI_KEY, 'header', h)
    lr = R._fi_build_line(commands.FLOW_FI_KEY, 'registro', reg)
    lf = [R._fi_build_line(commands.FLOW_FI_KEY, 'fluxo', x) for x in linhas]
    check('header 38 = SWAP 0 0034 participante data', lh == 'SWAP 00034JPMORGANBM          20260916', lh)
    check('registro 62: 3 eventos, MN do contrato, MN próprio, contas, papel (conta menor = JPM → 00), amortização 00',
          lr == 'SWAP 10034' + '0003' + MY + '1234567890' + '73760009' + '74220005' + '00' + '00' + ' ' * 8, lr)
    check('uma linha de 194 por fluxo', len(lf) == 3 and all(len(x) == domain.FLOW_LINE_LENGTH for x in lf))
    check('fluxo: data de pagamento nas duas pontas e a taxa 9(03)v9(05)',
          _pos(lf[0], 1, 8) == '20261215' and _pos(lf[0], 50, 57) == '02500000' and _pos(lf[0], 58, 65) == '20261215'
          and _pos(lf[0], 107, 114) == '02500000' and _pos(lf[2], 50, 57) == '05000000', lf[0][:120])
    ha, rega, _l = domain.flow_values(cf, 'atacama', accounts, MY, '1', '00', 'INTRAGATACAMAFDO', '20260916')
    check('na visão da Atacama a ponta da parte é 01 (85398005 > 73760009)', rega['9'] == '01')

    print('== 5. lacunas estruturadas e o _TRANS ==')
    ruim = dict(cf, CashFlows=[{'PaymentDate': '2026-12-15'}, {'PaymentDate': '2026-11-01'}], AmortizationType='',
                LOB='', CurveBCategory='JUROS INTERNACIONAIS')
    lac = domain.missing_for_send(ruim, codes, accounts, '')
    cods = [x['code'] for x in lac]
    check('ordem, vencimento, amortização, LOB e curva internacional viram lacuna com código',
          {'swc_flow_order', 'swc_last_flow_maturity', 'swc_no_amortization', 'swc_no_lob', 'swc_intl_curve'} <= set(cods), cods)
    check('lacuna é {code, params, text}', all(set(x) == {'code', 'params', 'text'} for x in lac))
    srcs = ''.join(io.open(os.path.join(ROOT, 'apps', 'pages', 'features', 'swap_cashflow', f), encoding='utf-8').read()
                   for f in ('domain.py', 'commands.py', 'entrypoint.py'))
    usados = set(re.findall(r"'((?:swc|nd)_[a-z_]+)'", srcs)) - {'swc_'}
    for lang in ('en', 'br', 'es'):
        bloco = re.search(r'\n    ' + lang + r': \{(.*?)\n    \}', tpl, re.S)
        chaves = set(re.findall(r'\b([ew]_[a-z_]+)\s*:', bloco.group(1))) if bloco else set()
        faltam = sorted(c for c in usados if ('e_' + c) not in chaves and ('w_' + c) not in chaves)
        check('_TRANS.%s tem texto para todo código do servidor' % lang, not faltam, faltam)

    print('== 6. import → batch → edit → confirm → send → delete ==')
    res = commands.import_upload('dt.xlsx', xlsx, datetime(2026, 9, 16), sid='A111111', dry_run=True)
    check('dry-run: dois deals, Recap ignorada, nada gravado', len(res['deals']) == 2 and res['ignored'] == ['Recap']
          and res['imported'] == 0 and not os.path.isdir(os.path.join(tmp, 'cache')))
    cli, b2b = res['deals']
    check('B2B: par JPM x ATACAMA pela SPN do le-spn', b2b['Pair'] == 'JPM x ATACAMA' and b2b['ClientAccount'] == '85398005')
    n = commands.persist_deals([dict(cli), dict(b2b)], sid='A111111')
    fp, lst, idx = queries.find(cli['_id'], '2026-09-16')
    check('batch grava no arquivo-dia da Trade Date, na pasta Swap/Cashflow', n == 2 and idx is not None
          and fp.endswith(os.path.join('2026', '09', '20260916_swapcashflow.json')))
    e = lst[idx]
    check('nasce New com os seis Meu Número', e['Status'] == 'New' and all(len(e[k]) == 10 for k in commands._MY_NUMBERS))
    nums = dict((k, e[k]) for k in commands._MY_NUMBERS)
    d, cod = commands.set_status(cli['_id'], '2026-09-16', 'Approved', sid='A111111')
    check('Confirm: New → Approved', d is not None and d['Status'] == 'Approved')
    commands.persist_deals([dict(cli, _replace=True)], sid='B222222')
    _f, l2, i2 = queries.find(cli['_id'], '2026-09-16')
    check('batch com _replace: Approved vira Amend, Meu Número preservado', l2[i2]['Status'] == 'Amend'
          and all(l2[i2][k] == nums[k] for k in commands._MY_NUMBERS))
    d, cod = commands.set_status(cli['_id'], '2026-09-16', 'Approved', sid='C333333')
    # Amend → Approved direto, como o New (mesa, 23/09/2026): Pending é só do Edit.
    check('Amend → Approved (maker = quem confirmou)',
          d['Status'] == 'Approved' and d['Maker'] == 'C333333' and d['Checker'] == '')
    commands.set_status(cli['_id'], '2026-09-16', 'Pending', sid='C333333')
    d2, cod2 = commands.set_status(cli['_id'], '2026-09-16', 'Approved', sid='C333333')
    check('Pending: o maker não aprova o próprio', d2 is None and cod2 == 'swc_maker_checker')
    novo = [dict(f) for f in cli['CashFlows']] + [{'StartDate': '2027-06-07', 'PaymentDate': '2027-06-07'}]
    d3, mapped = commands.edit(cli['_id'], '2026-09-16', {'CashFlows': novo[:3] + [{'PaymentDate': '', 'StartDate': ''}]},
                               sid='D444444')
    check('edit do cronograma: linha em branco cai, contagem refeita, Pending com maker', d3['Flows'] == '3'
          and d3['Status'] == 'Pending' and d3['Maker'] == 'D444444' and not mapped)
    d4, _c = commands.set_status(cli['_id'], '2026-09-16', 'Approved', sid='E555555')
    check('Pending → Approved por outro usuário', d4['Status'] == 'Approved' and d4['Checker'] == 'E555555')
    files = commands.preview(queries.find(b2b['_id'], '2026-09-16')[1][queries.find(b2b['_id'], '2026-09-16')[2]])
    check('preview do B2B: contrato + cronograma + prêmio × Banco e Atacama',
          [(f['kind'], f['view']) for f in files] == [('swap', 'bank'), ('flow', 'bank'), ('premium', 'bank'),
                                                      ('swap', 'atacama'), ('flow', 'atacama'), ('premium', 'atacama')])
    check('preview campo a campo com o rótulo do template', any(x['field'] == 'Quantidade de eventos de Fluxo'
                                                                 and x['value'] == '0003' for x in files[1]['fields']))
    # Lote com lacuna recusa tudo, dizendo qual (estruturado).
    _f, lb, ib = queries.find(b2b['_id'], '2026-09-16'); lb[ib]['AmortizationType'] = ''
    persistence.write_day(_f, lb)
    try:
        commands.send([{'deal_id': cli['_id'], 'trade_date': '2026-09-16'}, {'deal_id': b2b['_id'], 'trade_date': '2026-09-16'}])
        check('lote com lacuna recusa tudo', False)
    except commands.EnvioRecusado as exc:
        check('lote com lacuna recusa tudo, dizendo o deal e o código',
              any(x['deal_id'] == b2b['_id'] and x['code'] == 'swc_no_amortization' for x in exc.itens))
    check('nada foi escrito', not os.path.isdir(R.CONECTA_NEW_PATH) or not os.listdir(R.CONECTA_NEW_PATH))
    lb[ib]['AmortizationType'] = 'Sobre Valor Base Original'; persistence.write_day(_f, lb)
    out = commands.send([{'deal_id': cli['_id'], 'trade_date': '2026-09-16'}, {'deal_id': b2b['_id'], 'trade_date': '2026-09-16'}],
                        sid='F666666')
    nomes = sorted(x['filename'] for x in out['files'])
    check('nove arquivos: contrato, cronograma e prêmio × Cliente/Banco/Atacama, com CF e a LOB no nome',
          nomes == sorted(['SWAP_CF_CEM_CLIENTE.txt', 'SWAP_CF_CEM_BANCO.txt', 'SWAP_CF_CEM_ATACAMA.txt',
                           'FLUXO_SWAP_CF_CEM_CLIENTE.txt', 'FLUXO_SWAP_CF_CEM_BANCO.txt', 'FLUXO_SWAP_CF_CEM_ATACAMA.txt',
                           'PREMIO_SWAP_CF_CEM_CLIENTE.txt', 'PREMIO_SWAP_CF_CEM_BANCO.txt',
                           'PREMIO_SWAP_CF_CEM_ATACAMA.txt']), nomes)
    brut = io.open(os.path.join(R.CONECTA_NEW_PATH, 'SWAP_CF_CEM_BANCO.txt'), 'rb').read().split(b'\n')
    check('contrato do Banco: 2021 BYTES em cp1252 (o travessão da denominação VCP em um byte)',
          len(brut) == 2 and len(brut[1]) == 2021 and b'\x96' in brut[1] and b'\xe2\x80\x93' not in brut[1])
    fl_txt = io.open(os.path.join(R.CONECTA_NEW_PATH, 'FLUXO_SWAP_CF_CEM_ATACAMA.txt'), encoding='cp1252').read().split('\n')
    check('cronograma da Atacama: header INTRAGATACAMAFDO + registro + 3 fluxos', len(fl_txt) == 5
          and 'INTRAGATACAMAFDO' in fl_txt[0] and len(fl_txt[1]) == 62)
    _f, l5, i5 = queries.find(cli['_id'], '2026-09-16')
    check('vira Sent com os arquivos anotados', l5[i5]['Status'] == 'Sent' and 'SWAP_CF_CEM_CLIENTE.txt' in l5[i5]['SentFiles'])

    print('== 6b. B3 ID = mapeamento → Pending Confirmation (cliente) / Intrag Swap (B2B) ==')
    calls, intrag = [], []
    _pc, _ie = R._pc_save_from_deal, R._intrag_engine

    class _Intrag(object):
        @staticmethod
        def _save_intrag_swap_entry(entry, start):
            intrag.append((entry, start))
    R._pc_save_from_deal = lambda deal, pt, pending_status=None, trade_number=None, source=None: \
        calls.append((deal, pt, pending_status, trade_number, source))
    R._intrag_engine = lambda: _Intrag
    try:
        d6, m6 = commands.edit(cli['_id'], '2026-09-16', {'B3ID': '26F04329911'}, sid='G777777')
        d7, m7 = commands.edit(b2b['_id'], '2026-09-16', {'B3ID': '26F04329912'}, sid='G777777')
    finally:
        R._pc_save_from_deal, R._intrag_engine = _pc, _ie
    check('cliente: Success, e a porta do Pending Confirmation com SWAP (Opção de Arrependimento), Pending OTC, chave B3 ID, LOB CEM',
          m6 and d6['Status'] == 'Success' and len(calls) == 1 and calls[0][1:] == ('SWAP', 'Pending OTC', '26F04329911', 'SWAP')
          and calls[0][0]['LOB'] == 'CEM' and calls[0][0]['TaxID'] == '58160789000128')
    check('B2B: a linha da Intrag Swap (visão da Atacama), da Data Início', m7 and len(intrag) == 1
          and intrag[0][0]['b3_id'] == '26F04329912' and intrag[0][1] == datetime(2026, 9, 15))
    confs = R._swap_cashflow_engine().confirmation_deals(datetime(2026, 9, 16))
    check('a segregação das confirmações recebe o cashflow contra cliente (o B2B fica fora)',
          [c['B3_ID'] for c in confs] == ['26F04329911'])
    from apps.pages.platform import confirmations as PCF
    check('e o `_conf_load_swap` da platform lê as DUAS páginas',
          '26F04329911' in [c.get('B3_ID') for c in PCF._conf_load_swap(datetime(2026, 9, 16))])

    print('== 7. os vizinhos: Monitor, backfill, e-mail ==')
    from apps.pages.features.deals_monitor import domain as ndm
    card = [c for c in ndm._NDM_CARDS if c['key'] == 'swap-cem'][0]
    check('Monitor: a linha CEM da pasta Swap/Cashflow cai no card Swap CEM, que perdeu o selo soon',
          ndm._ndm_bucket('Swap/Cashflow', {'LOB': 'CEM'}) in ndm.card_buckets(card) and not card.get('soon'))
    check('persistência na pasta que o Monitor varre', 'Swap/Cashflow' in ndm._NDM_SWAP_DIRS
          and persistence.SUFFIX == '_swapcashflow.json')
    bf = io.open(os.path.join(ROOT, 'scripts', 'backfill_manual_confirmations.py'), encoding='utf-8').read()
    check('backfill: famílias SWAP e SWAP CORPORATE para a pasta Swap/Cashflow',
          bf.count("'dir': ('Swap', 'Cashflow')") == 2)
    from apps.pages import otc_emails
    fi = dict(l5[i5], TradeDate=datetime.now().strftime('%Y-%m-%d'))
    drafts = otc_emails.build_swap_bullet_affirmation_emails([fi])
    check('Economic Affirmation (IF): o Deal Ticket do e-mail leva a tabela Cash Flow',
          len(drafts) == 1 and 'Cash Flow' in drafts[0]['html'] and 'Sobre Valor Base Original' in drafts[0]['html']
          and '25%' in drafts[0]['html'])
    apagados, nao = commands.delete([{'deal_id': cli['_id'], 'trade_date': '2026-09-16'}])
    check('delete apaga do arquivo', apagados == 1 and not nao and queries.find(cli['_id'], '2026-09-16')[2] is None)

    print('== 8. as APIs (test client) ==')
    cl = app.test_client()
    with cl.session_transaction() as ss:
        ss['authenticated'] = True
        ss['user_sid'] = 'T000000'
        ss['user_name'] = 'Teste'
        ss['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    api = pagina['api']
    del SINO[:]
    r = cl.post(api + '/import-file?dry_run=1', data={'file': (io.BytesIO(xlsx), 'dt.xlsx'), 'trade_date': '17/09/2026'},
                content_type='multipart/form-data')
    j = r.get_json()
    check('import dry-run: 200, dois deals, lacunas por id, sem sino', r.status_code == 200 and len(j['deals']) == 2
          and isinstance(j['missing'], dict) and not SINO, (r.status_code, j and j.get('code')))
    r = cl.post(api + '/cache/batch', json={'deals': j['deals']})
    check('batch: 200 e o sino com o rótulo do catálogo', r.status_code == 200 and r.get_json()['imported'] == 2
          and SINO and SINO[-1][3] == 'Swap Cashflow')
    busca = cl.post(api + '/cache/search', json={'filters': [{'field': 'TradeDate', 'type': 'date', 'value': '17/09/2026',
                                                              'mode': 'exact'}]}).get_json()
    check('cache/search: os deals do dia, com o contrato', busca['success'] and len(busca['deals']) == 2
          and busca['fields'] == list(domain.SWC_FIELDS))
    alvo = busca['deals'][0]
    r = cl.get(api + '/preview?deal_id=%s&trade_date=%s' % (alvo['_id'], alvo['TradeDate']))
    check('preview: 200 com os arquivos', r.status_code == 200 and r.get_json()['files'])
    r = cl.post(api + '/edit', json={'deal_id': alvo['_id'], 'trade_date': alvo['TradeDate'], 'changes': {'AmortizationType': ''}})
    check('edit: 200, Pending', r.status_code == 200 and r.get_json()['entry']['Status'] == 'Pending')
    r = cl.get(api + '/preview?deal_id=%s&trade_date=%s' % (alvo['_id'], alvo['TradeDate']))
    jj = r.get_json()
    check('preview com lacuna: 422 com código e as lacunas estruturadas', r.status_code == 422 and jj['code'] == 'swc_lacunas'
          and any(x['code'] == 'swc_no_amortization' for x in jj['lacunas']))
    r = cl.post(api + '/confirm', json={'deal_id': alvo['_id'], 'trade_date': alvo['TradeDate']})
    check('confirm do próprio maker: 403 com código', r.status_code == 403 and r.get_json()['code'] == 'swc_maker_checker')
    r = cl.post(api + '/send-conecta', json={'items': [{'deal_id': alvo['_id'], 'trade_date': alvo['TradeDate']}]})
    check('send de Pending: 400 recusado com a lacuna de status', r.status_code == 400
          and r.get_json()['code'] == 'swc_send_refused' and r.get_json()['lacunas'][0]['code'] == 'swc_status')
    r = cl.post(api + '/add', json={'trade_date': '2026-09-17', 'fields': {'SPN': '281808', 'LOB': 'EDG', 'StartDate': '2026-09-17',
                                                                           'MaturityDate': '2027-09-17', 'Notional': '1000000',
                                                                           'CashFlows': [{'PaymentDate': '2027-09-17', 'AmortizationPct': '100'}]}})
    ja = r.get_json()
    check('add: 200, New, EDG, um fluxo, contraparte pela SPN', r.status_code == 200 and ja['entry']['Status'] == 'New'
          and ja['entry']['LOB'] == 'EDG' and ja['entry']['Flows'] == '1' and ja['entry']['Client'] == 'BANCO SAFRA S.A.')
    r = cl.post(api + '/delete', json={'items': [{'deal_id': ja['entry']['_id'], 'trade_date': '2026-09-17'}]})
    check('delete: 200 e 1 apagado', r.status_code == 200 and r.get_json()['deleted'] == 1)
    r = cl.post(api + '/nada')
    check('ação desconhecida: 404 JSON com código', r.status_code == 404 and r.get_json()['code'] == 'nd_unknown_action')
    r = cl.post(api + '/import-file', data={'file': (io.BytesIO(b'\x00lixo'), 'x.xlsx')}, content_type='multipart/form-data')
    check('arquivo ilegível: 400 com código e o motivo', r.status_code == 400 and r.get_json()['code'] == 'swc_unreadable'
          and r.get_json()['params'].get('reason'))
    check('sem sessão: 401', app.test_client().post(api + '/cache/search').status_code == 401)
    outra = cl.post('/api/new-deals/opt-edg/cache/search', json={'filters': []}).get_json()
    check('o opt-edg segue no stub (vazio com o contrato)', outra.get('success') and outra.get('backend') is False)


if __name__ == '__main__':
    sys.exit(main())
