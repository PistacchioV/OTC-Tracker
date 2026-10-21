# -*- coding: utf-8 -*-
"""Regressão da página New Deals › Swap › Cetes (mesa, 21/10/2026, §650).

O que chega é o e-mail "Cetes & associated trades - ##new trade, tranche N",
com os blocos da tranche; só o `#N cetip usd irs` vai à B3 — o swap USD Fixed
× SOFR entre o Banco e o Lawton, registrado pelas duas pontas.

O que este script prende:

1. a LEITURA do e-mail (.eml com o corpo em tabela, e o corpo solto): só o
   bloco cetip usd irs vira operação; tranche do assunto; o VALOR BASE em
   REAIS (USD notional × fx rate for reference); quem paga a fixa pelo
   `direction`; o D-n do `fx fixing`; planilha recusada;
2. os DOIS registros 0301 (layout v1, header 38 + registro 1899) byte a byte
   com o arquivo que a mesa mandou — Banco e Lawton, o mesmo Meu Número, a
   Parte com a curva que recebe;
3. as lacunas (código + params): perna sem cadastro, fx, quem paga, t-n,
   conta própria, duas pernas fixas;
4. import (dry-run e gravação), re-import preservando esteira e Meu Número;
5. o Send: os dois arquivos com a conta da visão no nome (§646), Sent;
6. o Mapping B3 ID pelo retorno: B3 ID + Success, e a linha da Intrag Swap na
   visão do LAWTON (INTRAGJP552), perna a perna;
7. a página: catálogo em cards (colunas = as do domínio), rota, busca,
   cadastro `swap-cetes-leg`, aba no /mapping, menu, os três mapas de
   notificação e o Intraday Monitor (Swap CEM e a Intrag do Lawton);
8. os cards no Chromium (`deal-cards.js`): um por operação, os quatro botões
   da casa pelo status, seleção, Select all, duplo clique = preview.

Roda em tmp: cache, Conecta e a pasta de retorno em diretórios temporários.
"""
import io
import os
import re
import sys
import tempfile
from datetime import datetime

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, RAIZ)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, cond):
    print(('  ok  ' if cond else '  FAIL ') + nome)
    if not cond:
        FALHAS.append(nome)


# Os registros que a mesa mandou em 21/10/2026 (VERBATIM — 1899 caracteres cada;
# o do Lawton chegou sem os dois espaços finais do campo 117, devolvidos aqui).
EX = {
 'bank': 'SWAP 10301953466035873760009                        00041007                        2026073020270121010000056822064000000101                                                                                                    20261021                                                                                                                                                                                                                                                                                                                                                                                                            10000C00                                                 10000C00        000039430                                                                   000000000000010000000017182SOFR OVERNIGHT - CALENDARIO USD/BRL - COTACAO CAMBIO PTAX - TIPO VENDA - COTACAO CAMBIO D-2 - ACT360 - CUPOM LIMPO 5,1168                                                                                                                                                                                                       0000000000000100000000   21                                                                                                                                                                                                                                                                                                                                0000000511680000200000005116800002                                                                                                                                                                                                                                                                                                                                                                                                     CEM  ',
 'lawton': 'SWAP 10301953466035800041007                        73760009                        2026073020270121010000056822064000000101                                                                                                    20261021                                                                                                                                                                                                                                                                                                                                                                                                            10000C00        000039430                                10000C00                                                                                    0000000000000100000000   21DOLAR DOS EUA - ACT/360 - Dolar inicio: 5,1168 - AMORTIZACAO: na data do vencimento - Juros: 3,9430%  - Cotacao cambio: D-2 - Calendarios a serem considerados BRL e  NY                                                                                                                                                        000000000000010000000017182                                                                                                                                                                                                                                                                                                                                0000000511680000200000005116800002                                                                                                                                                                                                                                                                                                                                                                                                     CEM  ',
}
EX_HEADER = {'bank': 'SWAP 00301JPMORGANBM          20261021', 'lawton': 'SWAP 00301INTRAGLAWTONFDO     20261021'}


def _eml(html, subject='Cetes & associated trades - ##new trade, tranche 111'):
    from email.message import EmailMessage
    m = EmailMessage()
    m['Subject'] = subject
    m['From'] = 'desk@example.com'
    m['To'] = 'brazil.cete.notifications@example.com'
    m.set_content('see html')
    m.add_alternative(html, subtype='html')
    return bytes(m)


def _bloco(num, titulo, kv):
    rows = '<tr><td><b>#%s</b></td><td><b>%s</b></td></tr>' % (num, titulo)
    rows += ''.join('<tr><td>%s:</td><td>%s</td></tr>' % x for x in kv)
    return '<table>' + rows + '</table><p>&nbsp;</p>'


IRS = [('booking', 'F Talioli'), ('venue', 'Cetip'), ('fx rate for reference', '5.00890'),
       ('usd notional', '78,860,000.00'), ('effective', '22-Oct-26'), ('maturity', '15-Apr-27'),
       ('fix rate', '4.22800%'), ('we pay', 'USD Fixed rate, Bullet A/360 Mod Following Adj'),
       ('we rec', 'USD-SOFR-COMPOUND(1d) Bullet A/360 Mod Following Adj'), ('accruals', 'USD'),
       ('payments', 'USD, BRL'), ('fx fixing', 't-2'), ('fx settlement', 'ptax bacen (venda)'),
       ('direction', 'banco (cetesbra) pays fix vs lawton (cetesbra)')]
NDF = [('booking', 'F Talioli'), ('value date', '15-Apr-27'), ('mxn amount', '1,500,000,000.00'),
       ('direction', 'chase ny sells usdmxn to jpm oc')]
HTML = '<html><body><p>Hi all</p>' + _bloco(8, 'offshore intercompany ndf', NDF) + _bloco(9, 'cetip usd irs', IRS) + '</body></html>'


def _celula(txt, negrito=False):
    """A célula como o Outlook a escreve: um <p class=MsoNormal> DENTRO do
    <td> — o html_to_lines quebra em cada parágrafo, e cada célula vira uma
    linha (o e-mail real da mesa, tranche 111)."""
    corpo = ('<b>%s</b>' % txt) if (negrito and txt) else txt
    return ("<td nowrap valign=bottom style='padding:0cm 5.4pt 0cm 5.4pt'><p class=MsoNormal>"
            "<span style='color:black'>%s<o:p></o:p></span></p></td>" % (corpo or '<o:p>&nbsp;</o:p>'))


def _bloco_outlook(num, titulo, kv):
    rows = '<tr>' + _celula('#%s' % num, True) + _celula(titulo, True) + '</tr>'
    rows += ''.join('<tr>' + _celula(a + ':') + _celula(b) + '</tr>' for a, b in kv)
    return "<table class=MsoNormalTable border=0 cellspacing=0 cellpadding=0>" + rows + '</table><p class=MsoNormal>&nbsp;</p>'


# o NDF com uma célula VAZIA (facing:) e um valor com DOIS-PONTOS (fixing:)
NDF_OUTLOOK = [('facing', ''), ('booking', 'F Talioli'), ('fixing', 'wmr ldn: 4pm'), ('direction', 'chase ny sells usdmxn to jpm oc')]
HTML_OUTLOOK = ("<html><body><div class=WordSection1><p class=MsoNormal>Hi all</p>"
                + _bloco_outlook(8, 'offshore intercompany ndf', NDF_OUTLOOK)
                + _bloco_outlook(9, 'cetip usd irs', IRS) + '</div></body></html>')

# o deal do EXEMPLO da mesa (os campos que o arquivo dela carrega)
EX_DEAL = {'Status': 'New', 'LE': 'JPM', 'LOB': 'CEM', 'TradeDate': '2026-10-21', 'StartDate': '2026-07-30',
           'MaturityDate': '2027-01-21', 'NotionalUSD': '111050000.00', 'FxRate': '5.1168', 'FixedRate': '3.943',
           'FixedPayer': 'BANCO', 'WePay': 'USD Fixed rate, Bullet A/360 Mod Following Adj',
           'WeRec': 'USD-SOFR-COMPOUND(1d) Bullet A/360 Mod Following Adj', 'FxFixing': 't-2',
           'Adhesion': 'CGD', 'Functionality': 'SEM FUNCIONALIDADE', 'PremiumSchedule': 'Não', 'Reset': 'Não',
           'MyNumber': '9534660358'}

SEED_LEGS = None   # preenchido em main(): a semente do _MAPPING_DEFS


def main():
    from run import app  # noqa: F401
    from apps.pages import routes as R
    from apps.pages.features.swap_cetes import commands, domain, queries
    from apps.pages.features.swap_cetes.infra import email_reader, persistence
    from apps.pages.features.new_deals import catalog

    tmp = tempfile.mkdtemp(prefix='otc-swt-')
    persistence.cache_dir = lambda: os.path.join(tmp, 'cache')
    R.CONECTA_NEW_PATH = os.path.join(tmp, 'conecta')
    seed = R._MAPPING_DEFS['swap-cetes-leg']['seed']
    queries.leg_rows = lambda: [dict(r) for r in seed]
    contas = {'JPM': '73760009', 'LAWTON': '00041007', 'MGT': '04880006', 'ATACAMA': '85398005'}
    queries.own_accounts = lambda: dict(contas)
    commands.queries.own_accounts = queries.own_accounts
    nomes = {'JPM': 'JPMORGANBM', 'LAWTON': 'INTRAGLAWTONFDO'}
    queries.participant = lambda le: nomes[le]

    print('== 1. o e-mail: só o bloco "cetip usd irs" vira operação ==')
    assunto, linhas = email_reader.read('cetes.eml', _eml(HTML))
    blocos = domain.blocks(linhas)
    check('dois blocos lidos (#8 e #9), só o #9 é o cetip usd irs',
          [(b['num'], domain.is_cetip_irs(b['title'])) for b in blocos] == [('8', False), ('9', True)])
    deals, ign = commands.parse_upload('cetes.eml', _eml(HTML), '2026-10-20')
    check('um deal; o NDF offshore volta como ignorado', len(deals) == 1 and ign == ['#8 offshore intercompany ndf'])
    d = deals[0]
    check('tranche do assunto, bloco, datas ISO, números de máquina',
          (d['Tranche'], d['Block'], d['StartDate'], d['MaturityDate'], d['NotionalUSD'], d['FxRate'], d['FixedRate'])
          == ('111', '#9', '2026-10-22', '2027-04-15', '78860000.00', '5.0089', '4.228'))
    check('o VALOR BASE em REAIS: USD notional × fx rate for reference (78,86 mi × 5,0089)',
          d['Notional'] == '395001854.00')
    check('quem paga a fixa sai do "direction"; o t-2 vira o D-n 02', d['FixedPayer'] == 'BANCO' and d['QuoteDateCode'] == '02')
    check('o mesmo e-mail dá a mesma chave (re-import cai na mesma linha)',
          commands.parse_upload('cetes.eml', _eml(HTML), '2026-10-20')[0][0]['_id'] == d['_id'])
    txt = 'Subject: x\n\n#9 cetip usd irs\n' + '\n'.join('%s: %s' % kv for kv in IRS)
    dt = commands.parse_upload('corpo.txt', txt.encode('utf-8'), '2026-10-20')[0]
    check('o corpo solto (texto) também é lido', len(dt) == 1 and dt[0]['Notional'] == '395001854.00')
    _a, linhas_ol = email_reader.read('tranche 111.eml', _eml(HTML_OUTLOOK))
    check('a tabela do OUTLOOK chega uma célula por linha (o <p> dentro do <td>)',
          linhas_ol[1:5] == ['#8', 'offshore intercompany ndf', 'facing:', 'booking:'])
    bl = domain.blocks(linhas_ol)
    check('…e o bloco é lido mesmo assim: #9 cetip usd irs, com os mesmos campos',
          [(b['num'], b['title']) for b in bl] == [('8', 'offshore intercompany ndf'), ('9', 'cetip usd irs')]
          and bl[1]['fields'] == dict(IRS))
    check('célula vazia não engole o rótulo seguinte; valor com dois-pontos não vira rótulo',
          bl[0]['fields'] == {'booking': 'F Talioli', 'fixing': 'wmr ldn: 4pm',
                              'direction': 'chase ny sells usdmxn to jpm oc'})
    do = commands.parse_upload('tranche 111.eml', _eml(HTML_OUTLOOK), '2026-10-20')[0]
    check('o deal do e-mail do Outlook é o MESMO do e-mail de uma linha por rótulo',
          len(do) == 1 and {k: do[0][k] for k in ('_id', 'Notional', 'FixedPayer', 'StartDate', 'FixedRate')}
          == {k: d[k] for k in ('_id', 'Notional', 'FixedPayer', 'StartDate', 'FixedRate')})
    plano = ('From: Kimura <mailto:kimura@example.com>\r\nSee <https://example.com/x>\r\n\r\n#9\tcetip usd irs\r\n'
             + '\r\n'.join('%s:\t%s' % kv for kv in IRS))
    dp = commands.parse_upload('corpo.txt', plano.encode('utf-8'), '2026-10-20')[0]
    check('corpo em TEXTO com <mailto:> e TAB entre as células: lido linha a linha, não como HTML',
          len(dp) == 1 and dp[0]['Notional'] == '395001854.00')
    celulas = 'x\n\n#9\n\ncetip usd irs\n\n' + '\n\n'.join('%s:\n\n%s' % kv for kv in IRS)
    dc = commands.parse_upload('corpo.txt', celulas.encode('utf-8'), '2026-10-20')[0]
    check('texto com uma célula por linha também', len(dc) == 1 and dc[0]['FixedRate'] == '4.228')
    check('"lawton pays fix" inverte; sem direction, o "we pay" fixo é o Banco',
          domain.fixed_payer('lawton (cetesbra) pays fix vs banco (cetesbra)') == 'LAWTON'
          and domain.fixed_payer('', 'USD Fixed rate') == 'BANCO' and domain.fixed_payer('', '') == '')
    try:
        commands.parse_upload('dt.xlsx', b'PK\x03\x04' + b'0' * 50, '2026-10-20')
        check('planilha é recusada com o motivo', False)
    except ValueError as exc:
        check('planilha é recusada com o motivo', 'e-mail' in str(exc))

    print('== 2. o 0301 (layout v1) byte a byte com o arquivo da mesa ==')
    ex = dict(EX_DEAL)
    domain.refresh(ex)
    check('o exemplo: 111,05 mi USD × 5,1168 = R$ 568.220.640,00', ex['Notional'] == '568220640.00')
    with app.test_request_context():
        for view in ('bank', 'lawton'):
            f = commands.deal_files(ex, view, '20261021')
            check('[%s] header de 38 igual ao da mesa' % view, f['header'] == EX_HEADER[view])
            rec = f['records'][0]
            dif = next((i + 1 for i, (a, b) in enumerate(zip(rec, EX[view])) if a != b), None)
            check('[%s] registro de 1899 igual ao da mesa%s' % (view, '' if dif is None else ' (1ª diferença na posição %d)' % dif),
                  rec == EX[view])
            check('[%s] arquivo e par de pernas' % view,
                  (f['file_name'], f['le_pair']) == ({'bank': 'SWAP_CETES_BANCO.txt', 'lawton': 'SWAP_CETES_LAWTON.txt'}[view],
                                                     {'bank': 'JPM x LAWTON', 'lawton': 'LAWTON x JPM'}[view]))
    check('o mesmo Meu Número nas duas visões', EX['bank'][10:20] == EX['lawton'][10:20] == '9534660358')
    check('a Parte recebe a curva dela: Banco = SOFR (17182), Lawton = Dólar (21) com o juros fixo',
          EX['bank'][799:804].strip() == '17182' and EX['lawton'][799:804].strip() == '21'
          and EX['lawton'][646:653] == '0039430' and EX['bank'][646:653].strip() == '')
    lo = dict(ex, FixedPayer='LAWTON')
    with app.test_request_context():
        rl = commands.deal_files(lo, 'bank', '20261021')['records'][0]
    check('com o LAWTON pagando a fixa, o Banco recebe o Dólar com o juros', rl[799:804].strip() == '21' and rl[646:653] == '0039430')

    print('== 3. as lacunas recusam o arquivo (código + params) ==')
    def codigos(deal, contas_=None, rows=None):
        return [x['code'] for x in domain.missing_for_send(deal, rows if rows is not None else seed,
                                                           contas_ if contas_ is not None else contas,
                                                           {'adhesion': '01', 'functionality': '00',
                                                            'premium_schedule': '01', 'reset': '01'})]
    check('o deal completo não tem lacuna', codigos(ex) == [])
    check('sem fx rate: falta o FX (e o valor base não sai)', 'swt_missing' in codigos(dict(ex, FxRate='')))
    check('perna sem linha no cadastro', 'swt_leg_unmapped' in codigos(dict(ex, WeRec='EURIBOR 3M')))
    check('sem quem paga a fixa', 'swt_no_direction' in codigos(dict(ex, FixedPayer='')))
    check('sem o t-n do fx fixing', 'swt_no_fx_fixing' in codigos(dict(ex, QuoteDateCode='')))
    check('sem a conta própria do Lawton', 'swt_no_account' in codigos(ex, {'JPM': '73760009'}))
    check('duas pernas fixas não fecham', 'swt_fixed_leg' in codigos(ex, rows=[dict(r, RATE='Yes') for r in seed]))

    print('== 4. import, re-import e o arquivo-dia ==')
    with app.test_request_context():
        res = commands.import_upload('cetes.eml', _eml(HTML), datetime(2026, 10, 20), sid='A111111', dry_run=True)
        check('dry-run não grava', res['imported'] == 0 and not os.path.exists(persistence.day_path(datetime(2026, 10, 20))))
        res = commands.import_upload('cetes.eml', _eml(HTML), datetime(2026, 10, 20), sid='A111111')
        check('o import grava um deal, sem lacuna', res['imported'] == 1 and res['missing'] == {})
        _fp, lst, i = queries.find(d['_id'], '2026-10-20')
        g = lst[i]
        check('Meu Número de 10 dígitos e a conta do Lawton para o plano B do retorno',
              len(g['MyNumber']) == 10 and g['ClientAccount'] == '00041007')
        num = g['MyNumber']
        commands.set_status(d['_id'], '2026-10-20', 'Approved', sid='A111111')
        commands.import_upload('cetes.eml', _eml(HTML), datetime(2026, 10, 20), sid='B222222')
        _fp, lst, i = queries.find(d['_id'], '2026-10-20')
        check('o re-import preserva a esteira e o Meu Número', lst[i]['Status'] == 'Approved' and lst[i]['MyNumber'] == num)

        print('== 5. o Send: dois arquivos, a conta da visão no nome (§646) ==')
        out = commands.send([{'deal_id': d['_id'], 'trade_date': '2026-10-20'}], sid='C333333')
        check('os dois arquivos na New', sorted(x['filename'] for x in out['files'])
              == ['00041007.SWAP_CETES_LAWTON.txt', '73760009.SWAP_CETES_BANCO.txt'])
        b = io.open(os.path.join(R.CONECTA_NEW_PATH, '73760009.SWAP_CETES_BANCO.txt'), encoding='cp1252').read().split('\n')
        check('header JPMORGANBM (38) e registro de 1899', b[0].startswith('SWAP 00301JPMORGANBM') and len(b[0]) == 38
              and len(b[1]) == 1899)
        _fp, lst, i = queries.find(d['_id'], '2026-10-20')
        check('a linha vira Sent', lst[i]['Status'] == 'Sent' and lst[i]['SentBy'] == 'C333333')
        try:
            commands.send([{'deal_id': d['_id'], 'trade_date': '2026-10-20'}])
            check('Sent não reenvia', False)
        except commands.EnvioRecusado as exc:
            check('Sent não reenvia', any(x['code'] == 'swc_status' for x in exc.itens))

        print('== 6. o Mapping B3 ID pelo retorno e a Intrag Swap (visão do Lawton) ==')
        ret_dir = os.path.join(tmp, 'return'); os.makedirs(ret_dir, exist_ok=True)
        R.RETURN_PATH = ret_dir
        lw = io.open(os.path.join(R.CONECTA_NEW_PATH, '00041007.SWAP_CETES_LAWTON.txt'), encoding='cp1252').read().split('\n')
        io.open(os.path.join(ret_dir, 'RET_SWAP.txt'), 'w', encoding='cp1252').write('\n'.join([
            'HEADER', '01;26J09990001;1;EXECUCAO OK;' + b[1], '02;26J09990001;2;EXECUCAO OK;' + lw[1]]))
        gravadas = []
        engine = R._intrag_engine
        R._intrag_engine = lambda: type('E', (), {'_save_intrag_swap_entry': staticmethod(
            lambda entry, start_dt: gravadas.append((entry, start_dt)))})
        try:
            res_map = commands.map_b3('2026-10-20', sid='D444444')
        finally:
            R._intrag_engine = engine
        _fp, lst, i = queries.find(d['_id'], '2026-10-20')
        check('B3 ID e Success pelo Meu Número', lst[i]['B3ID'] == '26J09990001' and lst[i]['Status'] == 'Success'
              and res_map and res_map[0]['saved'])
        check('o retorno todo consumido é apagado', not os.path.exists(os.path.join(ret_dir, 'RET_SWAP.txt')))
        check('uma linha da Intrag Swap, no dia da Data de Início', len(gravadas) == 1
              and gravadas[0][1] == datetime(2026, 10, 22))
        e = gravadas[0][0] if gravadas else {}
        check('na carteira do LAWTON, Parte Lawton × Banco, valor base em reais',
              (e.get('carteira'), e.get('parte'), e.get('contraparte'), e.get('base_value'), e.get('b3_id'))
              == ('INTRAGJP552', 'Lawton', 'Banco JP Morgan', '395001854', '26J09990001'))
        check('perna 1 = a do Lawton (Dólar 21 com o juros fixo), perna 2 = a do Banco (SOFR 17182)',
              (e.get('codigo_1'), e.get('juros_1'), e.get('codigo_2'), e.get('juros_2')) == ('21', '4.228', '17182', '0'))
        check('Data de Cotação = o Effective recuado o D-2 (dias úteis ANBIMA)', e.get('quote_date_1') == '2026-10-20')
        check('a Descrição de cada perna sai do cadastro, com o fx e a taxa',
              'CUPOM LIMPO 5,0089' in e.get('desc_vcp_2', '') and 'Juros: 4,2280%' in e.get('desc_vcp_1', ''))
        check('as 36 colunas da Intrag Swap', all(k in e for k in __import__(
            'apps.pages.platform.swap_deal_ticket', fromlist=['x']).INTRAG_SWAP_FIELDS))

        # A gravação DE VERDADE (sem o espião) e a tela da Intrag Swap (§655): a
        # linha mora no dia da Data Início (22/10, o Effective), e a página abria
        # SÓ no dia de hoje — mapeada em 20/10, a Cetes "não fluía" para a Intrag.
        from apps.pages.features.intrag.infra import persistence as ipers
        dir_antes = ipers.INTRAG_SWAP_CACHE_DIR
        ipers.INTRAG_SWAP_CACHE_DIR = os.path.join(tmp, 'intrag-swap')
        try:
            commands.b3_mapped(lst[i])
            with app.test_client() as c:
                with c.session_transaction() as s:
                    s.update({'authenticated': True, 'user_sid': 'A111111', 'user_role': 'ADMIN',
                              'session_ip': '127.0.0.1'})
                so_hoje = c.get('/api/intrag/swap?date=2026-10-20').get_json()['entries']
                de_hoje = c.get('/api/intrag/swap?date_from=2026-10-20').get_json()['entries']
        finally:
            ipers.INTRAG_SWAP_CACHE_DIR = dir_antes
        check('a linha da Intrag Swap é gravada no arquivo-dia da Data Início (22/10)',
              os.path.isfile(os.path.join(tmp, 'intrag-swap', '2026', '10', '20261022_intrag_swap.json')))
        check('procurada SÓ no dia do mapping (20/10) não aparece; de 20/10 em diante, aparece',
              so_hoje == [] and [x.get('_deal') for x in de_hoje] == [d['_id']])
        itpl = io.open(os.path.join(RAIZ, 'apps', 'templates', 'pages', 'intrag-swap.html'), encoding='utf-8').read()
        check('a Intrag Swap abre de HOJE em diante (o link do Monitor segue no dia exato)',
              "sfAddFilter(SF_COLS[0], _todayDmy(), 'from')" in itpl and 'if (_linkDmy) sfAddFilter(SF_COLS[0], _linkDmy)' in itpl)

    print('== 7. a página: catálogo, cadastro, menu, notificação, Monitor ==')
    p = catalog.page('/new_deals-swap-cetes')
    check('a página está no catálogo, em CARDS, com o Mapping e sem o Econ. Affirmation',
          p is not None and p['cards'] and p['mapping'] is True and p['econ_aff'] is False)
    check('as colunas do catálogo são as do domínio (cópia — feature não importa feature)',
          [tuple(c) for c in p['columns']] == [tuple(c) for c in domain.COLUMNS])
    check('o Swap Bullet e o Cashflow também em cards',
          catalog.page('/new_deals-swap-cashflow')['cards'] is not None)
    tpl = io.open(os.path.join(RAIZ, 'apps', 'templates', 'pages', 'new_deals-swap-bullet.html'), encoding='utf-8').read()
    check('o Bullet carrega o deal-cards.js e desenha #swbCards', 'deal-cards.js' in tpl and 'id="swbCards"' in tpl)
    # §655: Deal e B3 ID à vista mesmo em branco, as pontas da Cetes, a pílula da LOB
    cc, cf = p['cards'], catalog.page('/new_deals-swap-cashflow')['cards']
    check('o card da Cetes começa por Deal, B3 ID, Party (Banco) e Counterparty (o Client, Lawton)',
          [f[0] for f in cc['facts'][:4]] == ['Deal', 'B3ID', 'Banco', 'Client']
          and cc['facts'][2][2] == 'fixed' and d['Client'] == 'Lawton')
    check('Deal e B3 ID primeiro também no Cashflow e no Bullet (fora do pé, onde sumiam vazios)',
          [f[0] for f in cf['facts'][:2]] == ['Deal', 'B3ID']
          and not [m for m in cc['meta'] + cf['meta'] if m[0] in ('Deal', 'B3ID')]
          and tpl.index("t('nd-col-deal', 'Deal')") < tpl.index("t('nd-swb-col-startdate'"))
    check('a pílula da LOB: a Cetes SEMPRE CEM; Bullet e Cashflow pela LOB da linha',
          cc['lob'] == {'fixed': 'CEM'} and cf['lob'] == {'field': 'LOB'}
          and 'lob: function(e){ return String(e.LOB' in tpl)
    check('a LOB da Cetes não se edita, e o refresh devolve CEM à linha gravada com outra',
          'LOB' not in commands.EDITABLE and p['selects']['LOB'] == ['CEM']
          and domain.refresh(dict(d, LOB='EDG'))['LOB'] == 'CEM')
    with app.test_client() as c:
        with c.session_transaction() as s:
            s.update({'authenticated': True, 'user_sid': 'A111111', 'user_name': 'Teste', 'user_role': 'ADMIN',
                      'session_ip': '127.0.0.1'})
        r = c.get('/new_deals-swap-cetes')
        check('GET /new_deals-swap-cetes 200 com a grade de cards', r.status_code == 200 and b'id="swbCards"' in r.data)
        r = c.post('/api/new-deals/swap-cetes/cache/search', json={'filters': []})
        check('a busca da página responde pelo prefixo estático', r.status_code == 200 and r.get_json().get('success'))
    regras = {str(r) for r in app.url_map.iter_rules()}
    tplp = io.open(os.path.join(RAIZ, 'apps', 'templates', 'pages', 'new_deals-product.html'), encoding='utf-8').read()
    acoes = sorted(set(re.findall(r"PAGE\.api \+ '/([a-z0-9\-/]+)", tplp)) - {'economic-affirmation'})
    check('toda ação que a página chama tem rota ESTÁTICA na Cetes (o Econ. Affirmation ela não mostra)',
          [x for x in acoes if '/api/new-deals/swap-cetes/' + x not in regras] == [])
    check('o cadastro swap-cetes-leg (semente: SOFR 17182 e FIXED 21 com a taxa)',
          [(r['LEG'], r['VCP CODE'], r['RATE']) for r in seed] == [('SOFR', '17182', 'No'), ('FIXED', '21', 'Yes')])
    mp = io.open(os.path.join(RAIZ, 'apps', 'templates', 'pages', 'mapping.html'), encoding='utf-8').read()
    check('a aba do cadastro na tela /mapping', "key: 'swap-cetes-leg'" in mp)
    nav = io.open(os.path.join(RAIZ, 'apps', 'templates', 'partials', 'sidenav.html'), encoding='utf-8').read()
    check('o menu New Deals › Swap › Cetes', 'href="/new_deals-swap-cetes"' in nav)
    check('o rótulo "Swap Cetes" nos três mapas de notificação',
          R._NOTIF_PAGE_URL.get('Swap Cetes') == '/new_deals-swap-cetes'
          and "'Swap Cetes'" in io.open(os.path.join(RAIZ, 'apps', 'templates', 'partials', 'topbar.html'), encoding='utf-8').read()
          and "'Swap Cetes'" in io.open(os.path.join(RAIZ, 'apps', 'static', 'js', 'sw-push.js'), encoding='utf-8').read())
    from apps.pages.features.deals_monitor import domain as ndm
    check('o Monitor varre Swap/Cetes (card Swap CEM pela LOB)', 'Swap/Cetes' in ndm._NDM_SWAP_DIRS)
    check('e conta a Intrag desde o import, na entidade do LAWTON',
          ndm.intrag_destino('Swap/Cetes', {'Status': 'New'}) == 'Intrag/Swap'
          and ndm.intrag_destino_le('Intrag/Swap', 'Swap/Cetes') == 'LAW'
          and ndm.intrag_destino('Swap/Cetes', {'Status': 'Success'}) is None)

    print('== 8. os cards no Chromium (deal-cards.js) ==')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sync_playwright = None
        print('  (sem playwright: seção pulada)')
    if sync_playwright:
        st = os.path.join(RAIZ, 'apps', 'static')
        arq = os.path.join(tmp, 'cards.html')
        io.open(arq, 'w', encoding='utf-8').write(
            '<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="file://%s/css/vendors.min.css">'
            '<link rel="stylesheet" href="file://%s/css/otc.css"></head><body><div id="g"></div>'
            '<script src="file://%s/js/deal-cards.js"></script><script>'
            'window.sel = new Set(); window.ev = [];'
            'window.cards = otcDealCards({ el: "#g", selected: sel, key: function(e){ return e.id; },'
            ' title: function(e){ return e.t; }, subtitle: function(){ return "Banco × Lawton"; },'
            ' status: function(e){ return \'<span class="badge otc-status">\' + e.s + "</span>"; },'
            ' lob: function(e){ return e.l; },'
            ' facts: [{label: "USD Notional", value: function(e){ return e.n; }}],'
            ' canConfirm: function(e){ return e.s === "New"; }, canSend: function(e){ return e.s === "New" || e.s === "Approved"; },'
            ' onPreview: function(k){ ev.push("preview:" + k); }, onDelete: function(k){ ev.push("delete:" + k); },'
            ' onSelect: function(){ ev.push("sel:" + sel.size); } });'
            'cards.render([{id: "a", t: "Tranche 111 · #9", s: "New", n: "78,860,000.00", l: "CEM"}, {id: "b", t: "Tranche 112 · #9", s: "Sent", n: "", l: ""}]);'
            '</script></body></html>' % (st, st, st))
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            pg = br.new_page()
            pg.goto('file://' + arq)
            pg.wait_for_timeout(300)
            check('um card por operação, com o título e o fato', pg.locator('.otc-deal-card').count() == 2
                  and 'Tranche 111 · #9' in pg.inner_text('.otc-deal-card[data-key="a"]'))
            vis = pg.evaluate("""() => ['a','b'].map(k => ['confirm','edit','delete','send'].map(x =>
                !document.querySelector('.otc-deal-card[data-key="' + k + '"] .btn-row-' + x).classList.contains('d-none')))""")
            check('os quatro botões da casa; Confirm e Send só no status que os aceita',
                  vis == [[True, True, True, True], [False, True, True, False]])
            pg.click('.otc-deal-card[data-key="a"] .otc-deal-card__check')
            check('a caixa seleciona o card (o conjunto da página e o contorno)',
                  pg.evaluate("[...sel].join(',')") == 'a'
                  and 'is-selected' in pg.get_attribute('.otc-deal-card[data-key="a"]', 'class'))
            pg.evaluate("cards.selectAll(true)")
            check('Select all marca todos', pg.evaluate("sel.size") == 2
                  and pg.locator('.otc-deal-card__check:checked').count() == 2)
            pg.dblclick('.otc-deal-card[data-key="b"] .otc-deal-card__facts')
            pg.click('.otc-deal-card[data-key="b"] .btn-row-delete')
            check('duplo clique = preview; o botão chama a ação da página',
                  'preview:b' in pg.evaluate('ev') and 'delete:b' in pg.evaluate('ev'))
            check('o vazio fica para o card que não tem o valor', '—' in pg.inner_text('.otc-deal-card[data-key="b"]'))
            lob = pg.evaluate("""() => ['a','b'].map(k => { const x = document.querySelector('.otc-deal-card[data-key="' + k + '"] .otc-deal-card__lob');
                return x ? [x.textContent, x.dataset.lob, x.classList.contains('otc-status'), getComputedStyle(x).borderRadius] : null; })""")
            check('a pílula da LOB no cabeçalho (CEM, sem a marca de status); LOB vazia não desenha nada %s' % lob,
                  lob[0] is not None and lob[0][:3] == ['CEM', 'cem', False] and lob[1] is None)
            br.close()


if __name__ == '__main__':
    main()
    print()
    if FALHAS:
        print('FALHOU (%d):' % len(FALHAS))
        for f in FALHAS:
            print('  -', f)
        sys.exit(1)
    print('TUDO OK')
