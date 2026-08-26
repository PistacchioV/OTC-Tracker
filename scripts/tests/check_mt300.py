"""MT300: quem entra no e-mail, e como cada numero e derivado.

O que erra em SILENCIO:

1. **Quem entra sai do CADASTRO**, nao de uma lista no codigo. O casamento tenta
   CNPJ, SPN e o nome por tokens, e basta UM casar — o CNPJ vem primeiro porque
   e o unico que nao muda de grafia. No e-mail real, "CHOCOLATES GAROTO LTDA"
   casa com o cadastro "CHOCOLATES GAROTO SA" pelo CNPJ; por nome nao casaria, e
   a operacao sumiria da mensagem sem ninguem ver.

2. **O SINAL vem da DIRECAO**, nao do arquivo: o notional e gravado sempre
   positivo e no MT300 a venda e negativa. Sem isso as duas pontas do mesmo trade
   sairiam identicas na mensagem.

3. **`Other Quantity` e DERIVADO** (quantity x rate). Ele nao existe como campo.
   VALOR sai com duas casas e TAXA com oito: sao coisas diferentes — o
   contravalor e dinheiro e se le em centavos, e a taxa e o que converte um no
   outro, onde duas casas fariam dois strikes distintos aparecerem iguais.

4. **Sem operacao das contrapartes cadastradas o e-mail NAO sai**: ele pede para
   casar o trade no DVP, e sem trade nao ha o que casar.

Nao encosta em rede (SMTP stubado) nem em dado real (arquivo-dia em tempfile).
"""
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps import create_app                                  # noqa: E402
from apps.config import DebugConfig                          # noqa: E402
from apps.pages import routes as R                           # noqa: E402
# O MT300 saiu do routes.py para features/mt300 — os nomes agora moram la.
from apps.pages.features.mt300 import commands as MC, domain as MD, queries as MQ  # noqa: E402
from apps.pages.features.mt300.infra import mail as MM, persistence as MP          # noqa: E402
from flask import render_template                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label
          + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8', errors='ignore').read()


app = create_app(DebugConfig)
REF = datetime(2026, 8, 7)
tmp = tempfile.mkdtemp(prefix='check-mt300-')
_orig = {'dir': R._GENERIC_ND_PRODUCTS['vanilla']['dir'], 'd': R._DAILY_METRIC_DIR,
         'send': MM.send}


def deal(nome, cliente, cnpj, spn, notional, direction='SELL', rate='5.25470000'):
    return {'Deal': nome, 'Client': cliente, 'TaxID': cnpj, 'SPN': spn, 'LE': 'JPM',
            'Instrument': 'Avg Rate Forward', 'TradeDate': '07/08/2026',
            'SettlementDate': '27/01/2027', 'Notional': notional, 'Rate': rate,
            'FirstFixingDate': '02/01/2027', 'LastFixingDate': '20/01/2027',
            'QuantityCurrency': 'USD', 'OtherQuantityCurrency': 'BRL',
            'Direction': direction}


try:
    d = os.path.join(tmp, '2026', '08')
    os.makedirs(d, exist_ok=True)
    io.open(os.path.join(d, '20260807_ndfvanilla.json'), 'w', encoding='utf-8').write(json.dumps([
        deal('D5VL-2HTCA4', 'NESTLE BRASIL LTDA.', '60.409.075/0001-52', '806544', '1,572,509.21'),
        # O nome do arquivo (LTDA) diverge do cadastro (SA): casa pelo CNPJ.
        deal('D5VL-2HTCIL', 'CHOCOLATES GAROTO LTDA', '28.053.619/0001-83', '8837805', '5,605,296.67'),
        # Sem CNPJ e sem SPN: so o nome resolve.
        deal('D5VL-SONOME', 'ABB AUTOMACAO LTDA', '', '', '1,000.00'),
        # Fora do cadastro.
        deal('D5VL-OUTRO', 'SUZANO SA', '16.404.287/0001-55', '999', '100.00', 'BUY'),
    ]))
    R._GENERIC_ND_PRODUCTS['vanilla']['dir'] = tmp
    R._DAILY_METRIC_DIR = tmp

    print('== 1. So as contrapartes do cadastro entram ==')
    rows = MQ.rows(REF)
    check('as tres cadastradas, e so elas', [r['deal'] for r in rows],
          ['D5VL-2HTCA4', 'D5VL-2HTCIL', 'D5VL-SONOME'])
    check('   e quem esta fora do cadastro nao entra',
          [r for r in rows if 'SUZANO' in r['cpty']], [])
    # O CNPJ e o unico identificador que nao muda de grafia.
    check('nome divergente casa pelo CNPJ (GAROTO LTDA x cadastro SA)',
          [r['cpty'] for r in rows if r['deal'] == 'D5VL-2HTCIL'], ['CHOCOLATES GAROTO LTDA'])
    check('sem CNPJ e sem SPN, casa pelo nome por tokens',
          [r['cpty'] for r in rows if r['deal'] == 'D5VL-SONOME'], ['ABB AUTOMACAO LTDA'])

    print('\n== 2. Os numeros da mensagem ==')
    # Conferidos contra o e-mail real de 2026-08-07.
    r0 = rows[0]
    check('quantity NEGATIVO na venda', r0['qty'], '-1,572,509.21')
    check('other quantity = quantity x rate, em DUAS casas (e dinheiro)',
          r0['other_qty'], '-8,263,064.15')
    check('   e a segunda linha tambem', rows[1]['other_qty'], '-29,454,152.41')
    # A TAXA vai em oito casas: duas fariam dois strikes distintos aparecerem
    # iguais na mensagem.
    check('a taxa em OITO casas', r0['rate'], '5.25470000')
    check('as moedas saem de campos distintos (quantity x other)',
          (r0['qty_ccy'], r0['other_units']), ('USD', 'BRL'))
    # As datas saem no formato do resto do app — a mesa le o e-mail ao lado das
    # telas, e uma segunda grafia so no MT300 obrigaria a traduzir de cabeca.
    check('datas em dd/mm/aaaa', (r0['booking'], r0['settlement']),
          ('07/08/2026', '27/01/2027'))
    # Fixing Date = a coluna LAST Fixing Date do New Deals: numa media o que
    # interessa e a ULTIMA fixacao, quando a taxa fecha.
    check('fixing date vem do LastFixingDate', r0['fixing'], '20/01/2027')
    # Position: a operacao por extenso, do lado da NOSSA entidade. Os dois verbos
    # sao SEMPRE opostos — comprar uma moeda do par e vender a outra, e escreve-los
    # de forma independente deixaria a linha dizer que a mesa comprou as duas.
    check('position: venda', r0['position'], 'JPM sells USD / buys BRL')
    # A compra sai POSITIVA — o sinal e da direcao, nao do arquivo.
    io.open(os.path.join(d, '20260807_ndfvanilla.json'), 'w', encoding='utf-8').write(json.dumps([
        deal('D5VL-COMPRA', 'NESTLE BRASIL LTDA', '60.409.075/0001-52', '806544', '10.00', 'BUY')]))
    r_compra = MQ.rows(REF)[0]
    check('a compra sai POSITIVA', r_compra['qty'], '10.00')
    check('   e a position se inverte junto', r_compra['position'], 'JPM buys USD / sells BRL')
    # A entidade sai da LE do deal, nao de um literal: a mesma operacao e bookada
    # em entidades diferentes, e a mensagem e confirmada por quem a bookou.
    check('a entidade vem da LE do deal',
          MD.position({'LE': 'MGT', 'QuantityCurrency': 'USD',
                             'OtherQuantityCurrency': 'BRL', 'Direction': 'SELL'}),
          'MGT sells USD / buys BRL')
    # Sem uma das moedas nao da para dizer a operacao: melhor a celula vazia do
    # que uma frase pela metade.
    check('sem moeda, a celula fica vazia',
          MD.position({'LE': 'JPM', 'QuantityCurrency': 'USD',
                             'OtherQuantityCurrency': '', 'Direction': 'BUY'}), '')

    print('\n== 3. Sem operacao do grupo, o e-mail NAO sai ==')
    io.open(os.path.join(d, '20260807_ndfvanilla.json'), 'w', encoding='utf-8').write(json.dumps([
        deal('D5VL-OUTRO', 'SUZANO SA', '16.404.287/0001-55', '999', '100.00')]))
    enviados = []
    MM.send = lambda rows, to, cc, ref: (
        enviados.append({'rows': len(rows), 'to': list(to), 'cc': list(cc)}) or True)
    with app.test_request_context():
        MP.save_recipients({'to': 'bacc@x.com'})
        out = MC.run(REF)
        check('dia sem operacao do grupo', (out['sent'], out['reason']), (False, 'empty'))
        check('   e nem monta o e-mail', enviados, [])
        # Com operacao, mas sem TO: o pedido nao saiu de casa. Desfecho DISTINTO.
        io.open(os.path.join(d, '20260807_ndfvanilla.json'), 'w', encoding='utf-8').write(
            json.dumps([deal('D5VL-2HTCA4', 'NESTLE BRASIL LTDA', '60.409.075/0001-52',
                             '806544', '1,572,509.21')]))
        MP.save_recipients({'to': ''})
        out = MC.run(REF)
        check('com operacao e sem TO', (out['sent'], out['reason']), (False, 'no_recipient'))
        MP.save_recipients({'to': 'bacc@x.com'})
        out = MC.run(REF)
        check('com os dois, envia', (out['sent'], out['rows']), (True, 1))
        check('   e o Cc padrao e a caixa do OTC Ops', enviados[-1]['cc'],
              ['brazil.otc.ops@jpmorgan.com'])

    print('\n== 4. Cadastro, card e template ==')
    seed = {r['COUNTERPARTY'] for r in R._MAPPING_DEFS['mt300']['seed']}
    check('as seis empresas do grupo estao no seed', len(seed), 6)
    check('   com CNPJ e SPN em todas',
          all(r['CNPJ'] and r['SPN'] for r in R._MAPPING_DEFS['mt300']['seed']), True)
    check('o horario e 19:30', MD.TIME, (19, 30))
    check('o card esta no registro de acesso',
          any(c['id'] == 'mt300' for c in R._CONTROL_PANEL_CARDS), True)
    check('   e os dois endpoints apontam para ele',
          [R._CP_ENDPOINT_CARD.get('/api/control-panel/mt300/recipients'),
           R._CP_ENDPOINT_CARD.get('/api/control-panel/mt300/run')], ['mt300', 'mt300'])
    TPL = read('apps/templates/pages/control-panel.html')
    check('o card existe, com TO — BACC',
          ['data-cp-card="mt300"' in TPL, 'id="cp-mt300-to"' in TPL], [True, True])
    MAIL = read('apps/templates/pages/email-template-mt300.html')
    check('o template tem as DOZE colunas da mensagem',
          all(h in MAIL for h in ('Instrument Type', 'Deal Name', 'End Counterparty Desc',
                                  'Booking Date', 'Fixing Date', 'Settlement Date',
                                  'Position', 'Other Quantity', 'Other Quantity Units',
                                  'Quantity Currency', 'Quantity', 'Rate')), True)
    check('   e o pedido por extenso', 'match the trade in DVP' in MAIL, True)
    # Cabecalho e cor solida + gradiente CSS, nunca imagem/VML (CLAUDE.md §2).
    check('usa o header de gradiente da casa, sem VML',
          ["{% include 'partials/email-gradient-header.html' %}" in MAIL, '<v:rect' in MAIL],
          [True, False])
    with app.test_request_context():
        html = render_template('pages/email-template-mt300.html', ref_date_fmt='07/08/2026',
                               rows=rows, current_year=2026)
    check('o template renderiza com as linhas', 'D5VL-2HTCA4' in html, True)
    for lang in ('en', 'br', 'es'):
        tr = json.load(io.open(os.path.join(ROOT, 'apps', 'static', 'data', 'translations',
                                            lang + '.json'), encoding='utf-8'))
        faltando = [k for k in ('map-tab-mt300', 'cp-r-mt300-title', 'cp-mt300-to',
                                'cp-mt300-empty', 'cp-mt300-norec') if k not in tr]
        check('%s.json tem as chaves' % lang, faltando, [])
finally:
    R._GENERIC_ND_PRODUCTS['vanilla']['dir'] = _orig['dir']
    R._DAILY_METRIC_DIR = _orig['d']
    MM.send = _orig['send']
    shutil.rmtree(tmp, ignore_errors=True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
