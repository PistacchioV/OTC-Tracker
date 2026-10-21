# -*- coding: utf-8 -*-
"""check_unwind_swap_trs.py — a recompra de SWAP da EDG pelo recap do TRS (§657).

O "Internal Recap - <ticker> TRS onshore Unwind (20-Oct-26)" e UMA tabela
TRANSPOSTA: rotulos na primeira coluna, uma TRANCHE por coluna, com o CETIP ID
(o B3 ID). O que este teste prende:

  1. o LEITOR (`product/domain.linhas_do_recap_swap_trs`), com a tabela do e-mail
     da mesa (tranches #1-#9 do RDOR, 20/10/2026): uma recompra por tranche, o
     TOTAL fora; nocional = acoes x strike original; o fator de cada leg =
     round(valor de liquidacao / VBR + 1, 8) (§660 — o VBR e o Valor Base
     Remanescente do Live Position; sem ele nao ha fator), com quem RECEBE cada
     perna dito pelo rotulo ("RDOR Recebe" / "RDOR Paga"); VBR x (fator nosso −
     fator deles) = o (A + B) do e-mail; a parcial nao mantem premios; a data
     do ASSUNTO; o D+1;
  2. o IMPORT pela API, com o .eml no formato do Outlook (`<p class=MsoNormal>`
     dentro de cada `<td>`) e a posicao: papel pela CONTA MENOR (Ponta 1 =
     menor, manual 4.2.12), os fatores na Ponta certa, Party/Counterparty pela
     conta, a liquidacao no dia util seguinte, Check OK, o total do e-mail que
     o saldo desmente avisado, e o SWAP 0014 campo a campo — a planilha da mesa;
  3. o EDIT: acoes novas refazem o nocional (o fator e do VBR e fica); VBR novo
     refaz os fatores; o papel sozinho troca os
     fatores de ponta SEM trocar o centavo do caixa do e-mail;
  4. a TELA em cards (Chromium, a pagina RENDERIZADA pelo app): um card por
     recompra, com os ids, Party/Counterparty e a pilula da LOB; o Edit do card
     abre o modal; o duplo clique, o preview do arquivo da B3.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_unwind_swap_trs.py
"""
import io
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra) else ''))
    if not cond:
        FALHAS.append(nome)


# A tabela do e-mail da mesa (20/10/2026), verbatim.
TRANCHES = ['#1', '#2', '#3', '#4', '#5', '#6', '#7', '#8', '#9']
TABELA = [
    ['Tranche'] + TRANCHES + ['TOTAL'],
    ['Unwind Parcial/Total'] + ['Total'] * 8 + ['Parcial', ''],
    ['Data de execução original', '23-Dec-25', '26-Dec-25', '29-Dec-25', '29-Dec-25', '30-Dec-25',
     '30-Dec-25', '2-Jan-26', '5-Jan-26', '5-Jan-26', ''],
    ['Deal ID', '70045952', '70055000', '70060296', '70060302', '70067588', '70067589', '70079260',
     '70091144', '70091155', ''],
    ['Instrumento ID', '1314140011', '1314149805', '1314157591', '1314157618', '1314167215',
     '1314167226', '1314180220', '1314194956', '1314194975', ''],
    ['CETIP ID', '25L03771509', '25L03938191', '25L04197405', '25L04197411', '25L04405096',
     '25L04405108', '26A00078816', '26A01720249', '26A01719958', ''],
    ['Número de ações', '159,300', '245,200', '42,200', '159,200', '340,800', '51,900', '417,000',
     '31,100', '164,900', '1,611,600'],
    ['Strike Original'] + ['20.96'] * 10,
    ['Preço de Unwind'] + ['28.3739'] * 10,
    ['(A) Perna Equity (RDOR Recebe) ajustado para 1 dia de DI', '1,180,434.45', '1,816,965.01',
     '312,707.68', '1,179,693.43', '2,525,373.88', '384,585.99', '3,090,026.14', '230,455.19',
     '1,221,931.20', '11,942,172.96'],
    ['(B) Perna Funding (RDOR Paga DI + 0.50%) ajustado para 1 dia de DI', '-47,963.05', '-73,826.37',
     '-12,705.84', '-47,932.94', '-102,610.22', '-15,626.38', '-125,553.00', '-9,363.78', '-49,649.14',
     '-485,230.73'],
    ['(A + B) Valor Total de Liquidação (RDOR Recebe em D+1)', '1,132,471.39', '1,743,138.64',
     '300,001.84', '1,131,760.49', '2,422,763.66', '368,959.61', '2,964,473.14', '221,091.40',
     '1,172,282.06', '11,456,942.24'],
]
ASSUNTO = 'Internal Recap - FLRY3 TRS onshore Unwind (20-Oct-26)'


def _celula(txt, negrito=False):
    corpo = ('<b>%s</b>' % txt) if (negrito and txt) else txt
    return ("<td nowrap valign=bottom style='padding:0cm 5.4pt 0cm 5.4pt'><p class=MsoNormal>"
            "<span style='color:black'>%s<o:p></o:p></span></p></td>" % (corpo or '<o:p>&nbsp;</o:p>'))


def _eml():
    from email.message import EmailMessage
    linhas = ''.join('<tr>' + ''.join(_celula(c, i == 0) for c in r) + '</tr>'
                     for i, r in enumerate(TABELA))
    html = ("<html><body><div class=WordSection1><p class=MsoNormal>Boa tarde pessoal,</p>"
            "<p class=MsoNormal>Seguem os detalhes do unwind para Rede D'or:</p>"
            "<p class=MsoNormal><b>Rede D'or recebe BRL 11,456,942.24 em (D+1)</b></p>"
            "<table class=MsoNormalTable border=0 cellspacing=0 cellpadding=0>" + linhas +
            "</table><p class=MsoNormal>Att,</p></div></body></html>")
    m = EmailMessage()
    m['Subject'] = ASSUNTO
    m['From'] = 'bruna@example.com'
    m['To'] = 'edg@example.com'
    m.set_content('see html')
    m.add_alternative(html, subtype='html')
    return bytes(m)


def _digitos(v):
    return ''.join(ch for ch in str(v or '') if ch.isdigit())


def _posicao(contrato, cpty, base, doc='06047087000139'):
    return {'Contrato': contrato, 'Participante': '73760009', 'Contraparte': cpty,
            'CPF/CNPJ Cliente Contraparte': doc, 'Data início': '23/12/2025',
            'Data vencimento': '23/12/2027', 'Valor base': '%.2f' % base, 'Valor Antecipado': '0',
            'Valor Base Remanescente': '%.2f' % base,
            'Código Identificador': 'EDG', 'Curva Parte': 'DI', 'Curva Contraparte': 'ACAO RDOR3'}


def main():
    from run import app
    from apps.pages import routes as R
    from apps.pages.features.unwinds import catalog
    from apps.pages.features.unwinds.infra import persistence, product_store
    from apps.pages.features.unwinds.product import commands as PC
    from apps.pages.features.unwinds.product import domain as PD
    from apps.pages.platform import swap_flows as SF

    print('== 1. o leitor do recap do TRS ==')
    linhas, avisos = PD.linhas_do_recap_swap_trs([TABELA], ASSUNTO)
    check('uma recompra por tranche, o TOTAL fora, sem aviso',
          [l['Contract'] for l in linhas] == TABELA[5][1:10] and avisos == [], avisos)
    l1, l9 = linhas[0], linhas[8]
    check('ids, datas e numeros da tranche #1',
          (l1['DealID'], l1['InstrumentID'], l1['TradeDate'], l1['UnwindDate'], l1['Shares'], l1['Strike'],
           l1['UnwindPrice'], l1['EquityLeg'], l1['FundingLeg'])
          == ('70045952', '1314140011', '2025-12-23', '2026-10-20', 159300.0, 20.96, 28.3739,
              1180434.45, -47963.05), l1)
    check('nocional = acoes x strike original (159.300 x 20,96)', l1['UnwoundNotional'] == 3338928.0)
    check('o caixa e o (A + B) do e-mail com o sinal do BANCO (o RDOR recebe = o banco paga)',
          l1['Result'] == -1132471.39 and l9['Result'] == -1172282.06)
    check('sem o VBR (a posicao ainda nao foi lida) nao ha fator', 'FactorOurs' not in l1 and 'FactorLeg1' not in l1)
    f1 = PD.recalcular_swap(dict(l1, VBR=3338928.0))
    check('com o VBR, fator de cada leg = valor de liquidacao / VBR + 1 na 8a casa: o NOSSO (funding, '
          'o RDOR paga) e o DELE (equity, o RDOR recebe)',
          (f1['FactorOurs'], f1['FactorTheirs']) == (round(47963.05 / 3338928 + 1, 8), round(1180434.45 / 3338928 + 1, 8))
          == (1.01436481, 1.35353696), (f1.get('FactorOurs'), f1.get('FactorTheirs')))
    f9 = PD.recalcular_swap(dict(l9, VBR=2 * 3456304.0))
    check('na parcial a base e o VBR do contrato, nao o recomprado (#9 com VBR = 2x)',
          (f9['FactorOurs'], f9['FactorTheirs']) == (round(49649.14 / 6912608 + 1, 8), round(1221931.20 / 6912608 + 1, 8)),
          (f9.get('FactorOurs'), f9.get('FactorTheirs')))
    # A conta inversa: VBR x (nosso - deles) = o caixa. Cada fator vai na 8a
    # casa: meio 1e-8 x VBR em cada um (no #4, 3 centavos) — a tolerancia do Check.
    for l in linhas:
        l = PD.recalcular_swap(dict(l, VBR=l['UnwoundNotional']))
        caixa = l['VBR'] * (l['FactorOurs'] - l['FactorTheirs'])
        if abs(caixa - l['Result']) > PD.TOLERANCIA + l['VBR'] * 2e-8:
            check('o caixa pelos fatores bate com o e-mail (%s)' % l['Contract'], False,
                  (round(caixa, 2), l['Result']))
            break
    else:
        check('as nove tranches: VBR x (fator nosso - fator deles) = o (A + B) do e-mail '
              '(no arredondamento dos fatores)', True)
    check('a parcial (#9) nao mantem premios; a total nao diz nada',
          (l9['UnwindType'], l9.get('KeepPremium'), l1['UnwindType'], l1.get('KeepPremium'))
          == ('Partial', 'Não', 'Total', None))
    check('quem recebe cada perna saiu do rotulo; a liquidacao e D+1',
          l1['LegSides'] == {'visao': 'cliente', 'EquityLeg': 'cliente', 'FundingLeg': 'banco'}
          and l1['_d_mais'] == 1, l1.get('LegSides'))
    check('tabela sem CETIP ID nao e o recap (None, o leitor generico segue)',
          PD.linhas_do_recap_swap_trs([[r for r in TABELA if r[0] != 'CETIP ID']], ASSUNTO) is None)
    # O MESMO #1 escrito na visao do BANCO: a perna equity e o que o banco
    # PAGA (negativa para ele), a funding o que ele RECEBE, e o total o que ele
    # PAGA — sinal e fatores tem de sair iguais.
    jpm = [['Tranche', '#1'], ['CETIP ID', '25L03771509'], ['Número de ações', '159,300'],
           ['Strike Original', '20.96'], ['(A) Perna Equity (JPM Paga)', '-1,180,434.45'],
           ['(B) Perna Funding (JPM Recebe DI + 0.50%)', '47,963.05'],
           ['(A + B) Valor Total de Liquidação (JPM Paga em D+1)', '1,132,471.39']]
    lj = PD.recalcular_swap(dict(PD.linhas_do_recap_swap_trs([jpm], ASSUNTO)[0][0], VBR=3338928.0))
    check('o mesmo recap na visao do BANCO ("JPM Paga") da o mesmo sinal e os mesmos fatores',
          (lj.get('Result'), lj.get('FactorOurs'), lj.get('FactorTheirs')) == (-1132471.39, 1.01436481, 1.35353696),
          (lj.get('Result'), lj.get('FactorOurs'), lj.get('FactorTheirs')))

    print('\n== 2. o import pela API ==')
    tmp = tempfile.mkdtemp(prefix='otc-unwtrs-')
    raiz = os.path.join(tmp, 'unwinds')
    product_store.cache_root = lambda: raiz
    persistence.cache_root = lambda: raiz
    R.CONECTA_NEW_PATH = os.path.join(tmp, 'conecta')
    R._b3_account_le = lambda a: {'73760009': 'JPM'}.get(_digitos(a).zfill(8), '')
    # Party e Counterparty pela cascata do Live Position (§660): o CPF/CNPJ pelo
    # Reference Data e, sem ele, a conta pelo B3 ACCOUNT; o nome do cadastro
    # b3-accounts e so o plano B da Party. Os nomes diferem de proposito, para
    # o teste dizer de onde cada um saiu.
    R._b3_account_refdata_name = lambda a: {'73760009': 'NOME DO B3-ACCOUNTS'}.get(_digitos(a).zfill(8), '')
    R._b3_is_omnibus = lambda a: False
    R._b3_participant_name = lambda le: {'JPM': 'JPMORGANBM'}.get(le, '')
    R._lp_cpty_by_account = lambda a: {'74220005': 'REDE DOR (PELA CONTA)', '00012345': 'REDE DOR (PELA CONTA)',
                                       '73760009': 'BANCO J.P. MORGAN S/A'}.get(_digitos(a).zfill(8), '')
    R._lp_cpty_name_by_taxid = lambda d: 'REDE DOR SAO LUIZ SA' if _digitos(d) == '06047087000139' else ''
    R._create_notification = lambda *a, **k: None
    PC._hoje = lambda: date(2026, 10, 21)
    # A posicao: o RDOR na conta 74220005 (maior que a nossa: somos a Ponta 1),
    # menos no #2, numa conta MENOR (somos a Ponta 2). O #3 tem saldo maior que
    # o recomprado (o e-mail diz Total), e o #9 e a parcial de verdade.
    vr = {l['Contract']: l['UnwoundNotional'] for l in linhas}
    pos = []
    for c in TABELA[5][1:10]:
        base = vr[c] * (2 if c in ('25L04197405', '26A01719958') else 1)
        # o #2 vem SEM documento: a contraparte sai da conta
        pos.append(_posicao(c, '00012345' if c == '25L03938191' else '74220005', base,
                            doc='' if c == '25L03938191' else '06047087000139'))
    SF.swap_day_file = lambda tpl, ref=None: ('/nao/existe.json', '261020')
    R._db_day_records = lambda p: [dict(x) for x in pos]

    pg = catalog.PAGES['/unwinds/swap/edg']
    check('a pagina de Swap EDG le o recap e e em cards', pg['recap'] == 'swap-trs' and pg['cards']
          and pg['cards']['lob']['fallback'] == 'EDG' and 'fatores' in pg['checks'])
    cl = app.test_client()
    with cl.session_transaction() as ss:
        ss.update({'authenticated': True, 'user_sid': 'A000001', 'user_name': 'Teste',
                   'session_expires_at': (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()})
    r = cl.post(pg['api'] + '/import-file', data={'file': (io.BytesIO(_eml()), 'recap.msg'), 'date': '2026-10-21'},
                content_type='multipart/form-data')
    j = r.get_json(silent=True) or {}
    rows = {x['Contract']: x for x in j.get('rows') or []}
    check('import 200, as nove tranches', r.status_code == 200 and len(rows) == 9, (r.status_code, j.get('code')))
    a, b, c3, n9 = rows.get('25L03771509', {}), rows.get('25L03938191', {}), rows.get('25L04197405', {}), \
        rows.get('26A01719958', {})
    check('papel pela CONTA MENOR: #1 Ponta 1 (73760009 < 74220005), #2 Ponta 2 (> 00012345)',
          (a.get('Role'), b.get('Role')) == ('Ponta 1', 'Ponta 2'), (a.get('Role'), b.get('Role')))
    check('Ponta 1: Factor Leg 1 = o NOSSO; Ponta 2: Factor Leg 1 = o DELES',
          (a.get('FactorLeg1'), a.get('FactorLeg2')) == (1.01436481, 1.35353696)
          and (b.get('FactorLeg1'), b.get('FactorLeg2')) == (b.get('FactorTheirs'), b.get('FactorOurs')),
          (a.get('FactorLeg1'), a.get('FactorLeg2'), b.get('FactorLeg1'), b.get('FactorLeg2')))
    check('Party e Counterparty pela cascata do Live Position: o documento vence a conta; '
          'a Party pela conta do Live Position, antes do b3-accounts; LOB da posicao',
          (a.get('Party'), a.get('Counterparty'), a.get('LOB')) == ('BANCO J.P. MORGAN S/A', 'REDE DOR SAO LUIZ SA', 'EDG'),
          (a.get('Party'), a.get('Counterparty'), a.get('LOB')))
    check('sem documento na posicao (#2), a contraparte sai da CONTA',
          b.get('Counterparty') == 'REDE DOR (PELA CONTA)', b.get('Counterparty'))
    check('recompra em 20/10 (o assunto), liquidacao no dia util seguinte (21/10), direcao PAY',
          (a.get('UnwindDate'), a.get('SettlementDate'), a.get('Direction')) == ('2026-10-20', '2026-10-21', 'PAY'))
    check('Check OK (saldo e fatores) nas que fecham',
          all(rows[k].get('Check') == 'OK' for k in rows if k != '25L04197405'),
          {k: (x.get('Check'), x.get('Warnings')) for k, x in rows.items() if x.get('Check') != 'OK'})
    check('o e-mail diz Total e o saldo da posicao diz parcial: avisado',
          'unwind_type_differs' in (c3.get('Warnings') or []), c3.get('Warnings'))

    rr = cl.get(pg['api'] + '/preview?id=%s&date=2026-10-21' % a.get('_id'))
    rec = (((rr.get_json() or {}).get('files') or [{}])[0].get('records') or [''])[0]
    check('SWAP 0014 do #1 — a planilha da mesa: papel 00, fator nosso na Ponta 1, Data Antecipacao '
          '= hoje, Liquidante em branco, nocional no 11, total sem Mantem Premios, liquidacao em branco',
          rr.status_code == 200 and len(rec) == 111 and rec[:10] == 'SWAP 10014' and rec[10:21] == '25L03771509'
          and rec[21:23] == '00' and rec[33:51] == '000000000101436481' and rec[51:69] == '000000000135353696'
          and rec[69:77] == '20261021' and rec[77:85] == ' ' * 8 and rec[85:101] == '0000000333892800'
          and rec[101:103] == '  ' and rec[103:] == ' ' * 8, (rr.status_code, rec))
    rr = cl.get(pg['api'] + '/preview?id=%s&date=2026-10-21' % n9.get('_id'))
    rec9 = (((rr.get_json() or {}).get('files') or [{}])[0].get('records') or [''])[0]
    check('a parcial (#9): Mantem Premios 01 (nao), o nocional recomprado no 11, os fatores sobre o VBR '
          'do Live Position (6.912.608,00)',
          rec9[101:103] == '01' and rec9[85:101] == '0000000345630400' and n9.get('VBR') == 6912608.0
          and rec9[33:51] == '%018d' % round(round(49649.14 / 6912608 + 1, 8) * 1e8)
          and rec9[51:69] == '%018d' % round(round(1221931.20 / 6912608 + 1, 8) * 1e8), (rec9, n9.get('VBR')))
    rr = cl.get(pg['api'] + '/preview?id=%s&date=2026-10-21' % b.get('_id'))
    rec2 = (((rr.get_json() or {}).get('files') or [{}])[0].get('records') or [''])[0]
    check('o #2 (Ponta 2): papel 01 e o fator DELES (equity) na Ponta 1',
          rec2[21:23] == '01' and rec2[33:51] == '%018d' % round(b.get('FactorTheirs') * 1e8), rec2)

    print('\n== 3. o Edit ==')
    st = cl.post(pg['api'] + '/edit', data=json.dumps({'id': a['_id'], 'date': '2026-10-21',
                                                       'fields': {'Shares': '159,000'}}),
                 content_type='application/json')
    e = (st.get_json() or {}).get('row') or {}
    check('acoes novas refazem o nocional; os fatores sao do VBR e ficam; o caixa do e-mail fica',
          e.get('UnwoundNotional') == 3332640.0 and e.get('FactorLeg1') == 1.01436481
          and e.get('Result') == -1132471.39 and e.get('Check') == 'OK', e)
    st = cl.post(pg['api'] + '/edit', data=json.dumps({'id': a['_id'], 'date': '2026-10-21',
                                                       'fields': {'VBR': '3,400,000.00'}}),
                 content_type='application/json')
    ev = (st.get_json() or {}).get('row') or {}
    check('VBR novo refaz os fatores (valor / VBR + 1, 8 casas)',
          ev.get('FactorLeg1') == round(47963.05 / 3400000 + 1, 8)
          and ev.get('FactorLeg2') == round(1180434.45 / 3400000 + 1, 8) and ev.get('Check') == 'OK', ev)
    st = cl.post(pg['api'] + '/edit', data=json.dumps({'id': a['_id'], 'date': '2026-10-21',
                                                       'fields': {'VBR': '3,338,928.00'}}),
                 content_type='application/json')
    e = (st.get_json() or {}).get('row') or {}
    st = cl.post(pg['api'] + '/edit', data=json.dumps({'id': a['_id'], 'date': '2026-10-21',
                                                       'fields': {'Role': 'Ponta 2'}}),
                 content_type='application/json')
    e2 = (st.get_json() or {}).get('row') or {}
    check('o papel sozinho troca os fatores de ponta e NAO troca o centavo do caixa',
          (e2.get('FactorLeg1'), e2.get('FactorLeg2')) == (e.get('FactorLeg2'), e.get('FactorLeg1'))
          and e2.get('Result') == -1132471.39 and e2.get('Check') == 'OK', e2)

    print('\n== 4. a tela em cards ==')
    html = cl.get('/unwinds/swap/edg').get_data(as_text=True)
    check('a pagina carrega o deal-cards.js e desenha #unwCards',
          'deal-cards.js' in html and 'id="unwCards"' in html and 'unw-cards-mode' in html)
    check('a de Opcoes segue em tabela', 'id="unwCards"' not in cl.get('/unwinds/options/fxo').get_data(as_text=True))
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:                                          # pragma: no cover
        print('  (sem playwright: secao pulada)')
        return

    def servir(route):
        req = route.request
        u = urlparse(req.url)
        resp = cl.open(u.path + ('?' + u.query if u.query else ''), method=req.method,
                       data=req.post_data_buffer, headers={'Content-Type': req.headers.get('content-type', '')})
        route.fulfill(status=resp.status_code, body=resp.get_data(),
                      headers={'Content-Type': resp.headers.get('Content-Type', 'text/html')})

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page(viewport={'width': 1500, 'height': 1000})
        erros = []
        p.on('pageerror', lambda ex: erros.append(str(ex)))
        p.add_init_script("""(() => { const F = new Date('2026-10-21T12:00:00').getTime(); const D = Date;
            window.Date = class extends D { constructor(...a){ super(...(a.length ? a : [F])); } static now(){ return F; } }; })();""")
        p.route('http://otc.test/**', servir)
        p.goto('http://otc.test/unwinds/swap/edg')
        p.wait_for_selector('.otc-deal-card', timeout=20000)
        p.wait_for_timeout(500)
        n = p.locator('.otc-deal-card').count()
        txt = p.inner_text('.otc-deal-card[data-key="%s"]' % a['_id']) if n else ''
        check('um card por recompra (9), a tabela escondida', n == 9 and not p.is_visible('#unw-table'), n)
        check('o card diz os ids, Party e Counterparty, o nocional e o caixa com a direcao',
              all(x in txt for x in ('25L03771509', '70045952', '1314140011', 'BANCO J.P. MORGAN S/A',
                                     'REDE DOR SAO LUIZ SA', '3,332,640.00', '-1,132,471.39 · PAY')), txt)
        lob = p.evaluate("""k => { const x = document.querySelector('.otc-deal-card[data-key="' + k + '"] .otc-deal-card__lob');
                                   return x ? [x.textContent, x.dataset.lob] : null; }""", a['_id'])
        check('a pilula da LOB: EDG', lob == ['EDG', 'edg'], lob)
        p.click('.otc-deal-card[data-key="%s"] .btn-row-edit' % a['_id'])
        p.wait_for_selector('#unwEditModal.show', timeout=5000)
        check('o Edit do card abre o modal com a linha', 'Edit' in p.inner_text('#unwEditTitle')
              and '25L03771509' in p.inner_text('#unwEditTitle'))
        p.keyboard.press('Escape')
        p.wait_for_timeout(500)
        p.dblclick('.otc-deal-card[data-key="%s"] .otc-deal-card__facts' % a['_id'])
        p.wait_for_timeout(1200)
        check('o duplo clique abre o preview do arquivo da B3', 'SWAP 0014' in p.inner_text('body'))
        check('sem erro de JS', not erros, erros)
        b.close()


if __name__ == '__main__':
    main()
    print('\n%s' % ('TUDO OK' if not FALHAS else '%d FALHA(S): %s' % (len(FALHAS), FALHAS)))
    sys.exit(1 if FALHAS else 0)
