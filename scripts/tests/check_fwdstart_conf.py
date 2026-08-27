"""Confirmacao de NDF FWD START (Termo de Moeda com inicio a termo).

O documento e um contrato assinado: uma celula errada no Anexo I nao levanta
erro nenhum, sai bonita e vai para a contraparte. O que este teste prende:

  1. as TRES colunas que so existem neste documento.
     Pontos de Termo = Strike Set Offset e Data de Verificacao da Taxa Forward =
     Strike Set Date. Trocar as duas e o defeito silencioso obvio: as duas saem
     preenchidas, e a Taxa Forward que a clausula 4.2.l.2 manda calcular
     (cambio da Data de Verificacao + Pontos) fica errada. Data Efetiva = Trade
     Date.

  2. o No = B3 ID, nao o Deal. O numero da B3 so existe DEPOIS do registro; sem
     ele a coluna sai VAZIA e a tela avisa, em vez de imprimir o codigo interno
     que a contraparte nao reconhece.

  3. a Taxa Forward "Nao Aplicavel". No forward start ela nao existe na
     contratacao (o import zera o Rate) — e e esse "Nao Aplicavel" que liga a
     clausula 4.2.l.2. Imprimir 0,00 desligaria a clausula.

  4. a janela de verificacao. First Fixing vazio ou igual ao Last = janela de UM
     dia, Data Inicial "Nao Aplicavel" (clausula 4.2.j). First != Last imprime
     as duas. Repetir a mesma data nas duas colunas diria que ha uma media a
     apurar onde ha uma cotacao so.

  5. a Moeda Base sendo a moeda ESTRANGEIRA. A Moeda Cotada e fixa em BRL
     (clausula 3.d); ler sempre a Quantity Currency faria um deal cotado em BRL
     sair com BRL nas duas pontas.

  6. o EIXO da segregacao sendo o mesmo na tela e na geracao. A tela lista
     contraparte x moeda base; se a geracao usasse outro eixo, o link abriria
     404 num grupo que a tela mostrou.

  7. o documento e o PDF saindo do MESMO HTML (o padrao do FXO, §139) — uma
     segunda transcricao do texto do Word e como os dois arquivos divergem.

Nao encosta em dado real: o day-file vai para um tempfile, o CGD/Inventory/
FepWeb sao stubs e as raizes do modulo voltam no finally.
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R
# O motor `_conf_*` mora em platform/confirmations.py (§316): o gerador da
# página chama `_conf_cgd_lookup` por DENTRO do módulo, então o espião entra
# nos dois lugares — o alias do routes cobre o chamador da feature.
from apps.pages.platform import confirmations as PC                        # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


DEAL = {
    'Status': 'Success', 'Deal': 'D1', 'B3_ID': '26G04736337', 'LE': 'JPM',
    'TradeDate': '29/06/2026', 'SettlementDate': '28/08/2026', 'SPN': '1',
    'Acronym': 'SUZANO', 'Client': 'SUZANO SA', 'TaxID': '16404287000155',
    'FirstFixingDate': '27/08/2026', 'LastFixingDate': '27/08/2026',
    'StrikeSetDate': '30/07/2026', 'StrikeSetOffset': '0,0337',
    'Direction': 'SELL', 'QuantityCurrency': 'USD', 'OtherQuantityCurrency': 'BRL',
    'Notional': '198,723,470.91', 'Rate': '',
}


def run(deals, path='/api/new-deals/ndf-fwdstart/confirmations?date=2026-08-05'):
    """Monta o dia e devolve (grupos, html_do_documento_do_1o_grupo)."""
    from apps import create_app
    from apps.config import DebugConfig
    cfg = R._GENERIC_ND_PRODUCTS['fwd-start']
    real = (cfg['dir'], PC._conf_cgd_lookup)
    tmp = tempfile.mkdtemp(prefix='fwdconf-')
    try:
        cfg['dir'] = tmp
        d = os.path.join(tmp, '2026', '08')
        os.makedirs(d)
        with io.open(os.path.join(d, '20260805_ndffwdstart.json'), 'w', encoding='utf-8') as fh:
            json.dump(deals, fh, ensure_ascii=False)
        R._conf_cgd_lookup = PC._conf_cgd_lookup = lambda first: '28 de Maio de 2008'
        app = create_app(DebugConfig)
        cl = app.test_client()
        with cl.session_transaction() as s:
            s['authenticated'] = True
            s['user_sid'] = 'T000000'
            s['user_name'] = 'T'
            s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
        groups = (cl.get(path).get_json() or {}).get('groups') or []
        html = ''
        if groups and groups[0].get('url'):
            html = cl.get(groups[0]['url']).data.decode('utf-8')
        return groups, html
    finally:
        cfg['dir'], PC._conf_cgd_lookup = real
        R._conf_cgd_lookup = PC._conf_cgd_lookup
        shutil.rmtree(tmp, ignore_errors=True)


def cells(html):
    """{chave -> texto} das celulas do Anexo I do documento renderizado."""
    return dict(re.findall(r'data-k="(\w+)">([^<]*)<', html))


# ─────────────────────────────────────────────────────────────────────────────
print('== 1. as tres colunas proprias do forward start ==')
groups, html = run([dict(DEAL)])
c = cells(html)
check('Pontos de Termo = Strike Set Offset', c.get('pontosTermo'), '0,0337')
check('Data de Verif. da Taxa Forward = Strike Set Date', c.get('dtVerifFwd'), '30/07/2026')
check('Data Efetiva = Trade Date', c.get('dtEfetiva'), '29/06/2026')
# As duas primeiras nao podem ser a mesma coisa: uma e um PRECO, a outra e uma DATA.
check('e as duas nao sao o mesmo campo', c.get('pontosTermo') == c.get('dtVerifFwd'), False)

print('\n== 2. o No e o B3 ID ==')
check('No = B3 ID', c.get('num'), '26G04736337')
check('e nao o Deal interno', c.get('num') == DEAL['Deal'], False)
_g, h2 = run([dict(DEAL, B3_ID='')])
check('sem registro, a coluna sai VAZIA', cells(h2).get('num'), '')
check('e o painel avisa', 'sem B3 ID' in h2, True)

print('\n== 3. a Taxa Forward do forward start ==')
check('sem Rate, "Nao Aplicavel"', c.get('taxaFwd'), 'Não Aplicável')
_g, h3 = run([dict(DEAL, Rate='5.4321')])
check('com Rate, e o Rate', cells(h3).get('taxaFwd'), '5,43210000')

print('\n== 4. a janela de verificacao ==')
check('First == Last -> Inicial "Nao Aplicavel"', c.get('dtIni'), 'Não Aplicável')
check('e a Final e o Last Fixing', c.get('dtFim'), '27/08/2026')
_g, h4 = run([dict(DEAL, FirstFixingDate='')])
check('First vazio -> tambem "Nao Aplicavel"', cells(h4).get('dtIni'), 'Não Aplicável')
_g, h5 = run([dict(DEAL, FirstFixingDate='20/08/2026')])
check('First != Last -> imprime as DUAS', cells(h5).get('dtIni'), '20/08/2026')
check('   com a Final intacta', cells(h5).get('dtFim'), '27/08/2026')

print('\n== 5. a Moeda Base e a moeda ESTRANGEIRA ==')
check('USD/BRL -> USD', c.get('moedaBase'), 'USD')
check('BRL/EUR -> EUR (a cotada e sempre BRL)',
      R._conf_fwdstart_moeda({'QuantityCurrency': 'BRL', 'OtherQuantityCurrency': 'EUR'}), 'EUR')
check('sem a outra ponta, sobra a que ha',
      R._conf_fwdstart_moeda({'QuantityCurrency': 'BRL', 'OtherQuantityCurrency': ''}), 'BRL')
# Taxa de Conversao vem do cadastro `fxo-conv-rate`, o mesmo do FXO — nao ha
# uma segunda tabela de moedas para manter.
check('Taxa de Conversao do cadastro', c.get('taxaConv'), 'USD PTAX')
check('e o Tipo junto', c.get('tipoTaxaConv'), 'Venda')

print('\n== 6. o eixo da segregacao ==')
check('um grupo por contraparte x moeda base',
      [(g['acronym'], g['mercadoria'], g['family']) for g in groups],
      [('SUZANO', 'USD', 'strike-me')])
# Duas moedas da MESMA contraparte = dois documentos (o Anexo II define a moeda).
g2, _h = run([dict(DEAL), dict(DEAL, Deal='D2', B3_ID='B2', QuantityCurrency='EUR')])
check('moedas diferentes = grupos diferentes',
      sorted(g['mercadoria'] for g in g2), ['EUR', 'USD'])
# O link que a tela publica tem de abrir: mesmo eixo dos dois lados.
check('o link do grupo abre o documento (nao 404)', bool(html) and 'ANEXO' in html, True)

print('\n== 7. o PDF sai do MESMO HTML do .doc ==')
# As rotas de confirmação moram em features/confirmation desde a extração; o
# routes segue com os geradores — os dois entram no mesmo texto.
src = (io.open(os.path.join(ROOT, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()
       + io.open(os.path.join(ROOT, 'apps', 'pages', 'platform',
                              'confirmations.py'), encoding='utf-8').read()
       + io.open(os.path.join(ROOT, 'apps', 'pages', 'features', 'confirmation',
                              'entrypoint.py'), encoding='utf-8').read())
blk = src.split('def api_conf_fwdstart_save')[1].split('def api_conf_fwdstart_pdf')[0]
check('o save renderiza o doc com doc_only', 'doc_only=True' in blk, True)
check('e passa ESSE html para o PDF', 'word_html_pdf(doc_html)' in blk, True)
pdfs = io.open(os.path.join(ROOT, 'apps', 'pages', 'confirmation_pdfs.py'), encoding='utf-8').read()
check('word_html_pdf existe uma vez', pdfs.count('def word_html_pdf'), 1)
check('e o opcao_fx_pdf delega (nao ha duas implementacoes)',
      'return word_html_pdf(doc_html)' in pdfs, True)

print('\n== 8. o documento tem as lacunas preenchidas ==')
outs = dict(re.findall(r'id="out_(\w+)">([^<]*)<', html))
check('Parte B', outs.get('parteb_nome'), 'SUZANO SA')
check('CNPJ formatado', outs.get('parteb_cnpj'), '16.404.287/0001-55')
check('Data de Negociacao', outs.get('data_neg'), '29/06/2026')
check('Data por extenso (assinatura)', outs.get('data_extenso'), '29 de Junho de 2026')
check('CGD do Reference Data', outs.get('cgd_date'), '28 de Maio de 2008')
# No do cabecalho: com UMA operacao e o B3 ID dela; com varias nao ha numero que
# represente o documento, e o da primeira seria o de uma das operacoes contidas.
check('No do cabecalho com 1 operacao', outs.get('num_conf'), '26G04736337')
_g6, h6 = run([dict(DEAL), dict(DEAL, Deal='D2', B3_ID='B2')])
check('com 2 operacoes, cabecalho vazio',
      dict(re.findall(r'id="out_(\w+)">([^<]*)<', h6)).get('num_conf'), '')

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 9. a coluna Strike e o XML ==')
# Inserir coluna nas paginas de NDF e o defeito que ja corrompeu dado duas vezes
# (§132): os indices ficam desencontrados entre as listas POSICIONAIS e a tela
# passa a gravar o valor de uma coluna no campo de outra, sem erro nenhum.
PAGE = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages',
                            'new_deals-ndf-fwdstart.html'), encoding='utf-8').read()
head = PAGE.split('<thead', 1)[1].split('</thead>', 1)[0]
rows_th = re.split(r'<tr[^>]*>', head)[1:]
check('cabecalho e linha de filtros com o MESMO numero de colunas',
      [r.count('<th') for r in rows_th], [32, 32])
arr = PAGE.split('return _escRow([', 1)[1].split('], {0:1', 1)[0]
arr = [l.strip() for l in arr.split('\n') if l.strip()]
check('e o array do dealJsonToRow tambem', len(arr), 32)
check('Strike na posicao 17 do array', arr[17].startswith('deal.Strike'), True)
labels = re.findall(r'data-lang="(nd-col-[\w-]+)"', rows_th[0])
# O checkbox (col 0) nao tem data-lang, entao labels[i] e a coluna i+1.
check('Strike na posicao 17 do cabecalho', labels[16], 'nd-col-strike')
check("COL_TO_JSON_FIELD[17] = 'Strike'", "17: 'Strike'" in PAGE, True)
check('AMEND_FIELD_COLS acompanha', 'Strike: 17, Instrument: 18' in PAGE, True)
check('o Maker foi de 30 para 31', 'var rowMaker  = d[31]' in PAGE, True)
check('e o COL_TO_JSON_FIELD concorda', "31: 'Maker'" in PAGE, True)
# O smart filter le a coluna pelo dtCol; ficar em 16 leria o Strike Set Offset.
check('smart filter aponta para 17', "{ label: 'Strike',            type: 'number', dtCol: 17 }" in PAGE, True)

# ── o XML: o strike converte o notional ────────────────────────────────────
# O termo de MERCADORIA é quantidade × preço; o de MOEDA não. Aplicar a fórmula
# da mercadoria aqui multiplicaria dólares pela taxa e chamaria reais de "valor
# estrangeiro" — o arquivo sai, e sai errado.
legs = R._conf_fx_legs({'Notional': '198,723,470.91', 'Strike': '5.43210000',
                        'QuantityCurrency': 'USD'}, None)
check('notional na moeda base: estrangeiro = o proprio notional', round(legs[0], 2), 198723470.91)
check('   e o valor em BRL sai do strike', round(legs[1], 2), 1079485766.33)
legs = R._conf_fx_legs({'Notional': '1,000,000.00', 'Strike': '5.00000000',
                        'QuantityCurrency': 'BRL'}, None)
check('notional em BRL: o strike DIVIDE para chegar a moeda base', round(legs[0], 2), 200000.00)
check('   e o valor em BRL e o proprio notional', round(legs[1], 2), 1000000.00)
check('sem strike nao ha conversao (fwd start nao fixado)',
      R._conf_fx_legs({'Notional': '100', 'Strike': ''}, None), None)
# E a fórmula da mercadoria continua intacta para quem sempre a usou.
src_xml = src.split('def _conf_ndf_xml')[1].split('\ndef ', 1)[0]
check('a fórmula da mercadoria sobrevive sem legs_fn',
      'strike_adj = _conf_strike_adj(deal, subj)' in src_xml, True)
check('e a confirmacao do FWD Start passa a de moeda',
      'legs_fn=_conf_fx_legs' in src or 'legs_fn=_R()._conf_fx_legs' in src, True)
# A moeda do XML é a Moeda Base do grupo, não a Quantity Currency (que pode ser BRL).
check('e manda a Moeda Base explicita', 'ccy=merc)' in src, True)

# ── 8. O tipoOperacao do XML ────────────────────────────────────────────────
# O FWD Start e um NDF: o que ele tem de proprio e a data de inicio la na frente,
# nao o tipo de operacao. Ele saia com `Termo`, que nao pertence ao dominio que o
# FepWeb espera nesse campo. E uma palavra so, num arquivo que ninguem abre — o
# documento e gerado, gravado e enviado sem nada acusar.
import ast                                                        # noqa: E402
_arv = ast.parse(src)
_tipos = {}
for _no in ast.walk(_arv):
    if not isinstance(_no, ast.Call):
        continue
    _nome_fn = getattr(_no.func, 'id', '') or getattr(_no.func, 'attr', '')
    if _nome_fn != '_conf_ndf_xml':
        continue
    _kw = {k.arg: getattr(k.value, 'value', None) for k in _no.keywords}
    # A chamada sem `prefixo` e a do NDF Commodities, que usa o default.
    _tipos[_kw.get('prefixo') or 'NDF_Comm'] = _kw.get('tipo') or 'NDF'
check('o XML do FWD Start sai com tipoOperacao NDF', _tipos.get('NDF_FwdStart'), 'NDF')
# As duas familias de OPCAO saem em MAIUSCULO, como o NDF: e o que o FepWeb le,
# e o `Option` com inicial maiuscula era a unica saida do app fora desse padrao.
check('   e as outras tres seguem o produto delas',
      (_tipos.get('NDF_Comm'), _tipos.get('Opt_Comm'), _tipos.get('Opt_FXO')),
      ('NDF', 'OPTION', 'OPTION'))
check('   e o tipo vai sempre em CAIXA ALTA',
      [t for t in _tipos.values() if t != t.upper()], [])

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
