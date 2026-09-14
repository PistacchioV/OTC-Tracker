# -*- coding: utf-8 -*-
"""check_equity_leg_prefix.py — o elo de equity: como o Título da B3 chega à
linha do OTM, e quem decide se ela é a perna interna ou a do cliente.

A rota tem três paradas:

    Operations B3 --Título--> Latam Desk Position --Deal_Ref--> OTM Settlements
                              CLEARING_TRD_ID_CLNT  = CETIP ID do cliente
                              CLEARING_TRD_ID_INT   = CETIP ID interno

e duas perguntas diferentes que é fácil confundir numa só:

  1. **qual `Deal_Ref`?** — o Trade Id do OTM menos o PREFIXO (`270WI`,
     `270WC`, `270RI`…). O prefixo só atrapalha o casamento; o cadastro
     `equity-leg-prefix` existe para saber o que descartar. Prefixo
     desconhecido não vira chave: a linha é ignorada, e o aviso sai com o nome
     curto da B3 e os valores em branco;
  2. **qual PERNA?** — o `Cpty SPN` da própria linha do OTM
     (`_ops_is_internal_cpty`: cadastro `le-spn` e o Reference Data com
     `ECONOMIC GROUP = INTERNAL`). **Não é o prefixo.** Ler `WI`/`WC` como
     mnemônico de internal/client é coincidência dos dois primeiros — `270RI`
     é de CLIENTE —, e perna trocada é pior que perna nenhuma: a linha exibe a
     contraparte da OUTRA ponta, com valor, sem nada indicando a troca, num
     documento que vai ao cliente.

O encontro das duas é o elo: a COLUNA em que o Título estava diz o lado que se
quer, o SPN diz o lado de cada grupo do OTM.
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

falhas = []


def check(rotulo, obtido, esperado):
    ok = obtido == esperado
    print(('  ok  ' if ok else ' FAIL ') + rotulo +
          ('' if ok else '\n        got=%r\n        exp=%r' % (obtido, esperado)))
    if not ok:
        falhas.append(rotulo)


from apps.pages import routes as R                                    # noqa: E402
from apps.pages.platform import settlement as S                       # noqa: E402

print('== 1. o cadastro é a lista do que se DESCARTA ==')
check('o seed traz os três prefixos',
      sorted(r['PREFIX'] for r in R._MAP_EQ_LEG_SEED), ['270RI', '270WC', '270WI'])
check('o arquivo versionado concorda',
      sorted(r['PREFIX'] for r in R._mapping_rows('equity-leg-prefix')),
      ['270RI', '270WC', '270WI'])
# A coluna LEG saiu: ela decidia a perna, e decidia errado.
check('o cadastro não tem mais coluna de perna',
      [c['key'] for c in R._MAPPING_DEFS['equity-leg-prefix']['columns']],
      ['PREFIX', 'NOTES'])

print('\n== 2. o Trade Id vira Deal_Ref (o prefixo é jogado fora) ==')
_rows_real = R._mapping_rows
try:
    R._mapping_rows = lambda k: ([{'PREFIX': p} for p in ('270WI', '270WC', '270RI')]
                                 if k == 'equity-leg-prefix' else [])
    check('270WI0012345 → 12345', S._ops_eq_trade_key('270WI0012345'), '12345')
    check('270RI0258485 → 258485', S._ops_eq_trade_key('270RI0258485'), '258485')
    check('e o Deal_Ref do Latam normaliza igual', S._ops_eq_ref_key('0258485'), '258485')
    check('zeros à esquerda somem dos DOIS lados',
          S._ops_eq_trade_key('270WC0000077'), S._ops_eq_ref_key('77'))
    check('prefixo desconhecido não vira chave', S._ops_eq_trade_key('270XX0258485'), '')
    check('vazio não vira chave', S._ops_eq_trade_key(''), '')

    # Prefixo que é começo de outro: o mais longo tem de sair primeiro, senão
    # sobra um pedaço dele no Deal_Ref e a chave não casa nada.
    R._mapping_rows = lambda k: ([{'PREFIX': '270'}, {'PREFIX': '270RI'}]
                                 if k == 'equity-leg-prefix' else [])
    check('o prefixo mais longo é descartado primeiro',
          S._ops_eq_trade_key('270RI0258485'), '258485')

    R._mapping_rows = lambda k: []
    check('cadastro vazio cai na semente',
          sorted(S._ops_eq_prefixos()), ['270RI', '270WC', '270WI'])
finally:
    R._mapping_rows = _rows_real

print('\n== 3. a PERNA sai do Cpty SPN, não do prefixo ==')
# Deal_Ref 258485, duas pernas: a do cliente (SPN 910711, REDE D OR) e a
# interna (SPN 1808267, uma entidade do `le-spn`). Os prefixos são os MESMOS
# nos dois de propósito — se o prefixo decidisse, este caso não teria resposta.
LATAM = [{'Deal_Ref': '0258485',
          'CLEARING_TRD_ID_CLNT': '26901956578',
          'CLEARING_TRD_ID_INT': '26901900000',
          'Underlying_Name': 'FLRY3', 'Trade_Date': '2026-02-04'}]
OTM = [
    {'Trade Id': '270RI0258485', 'Amount': '15000.00', 'Cpty SPN': '0910711',
     'Cpty Name': 'REDE D OR SAO LUIZ S.A.', 'Owner Legal Entity': 'BANCO J.P. MORGAN S.A.'},
    {'Trade Id': '270RI0258485', 'Amount': '-5000.00', 'Cpty SPN': '0910711',
     'Cpty Name': 'REDE D OR SAO LUIZ S.A.', 'Owner Legal Entity': 'BANCO J.P. MORGAN S.A.'},
    {'Trade Id': '270WI0258485', 'Amount': '9000.00', 'Cpty SPN': '1808267',
     'Cpty Name': 'ATACAMA', 'Owner Legal Entity': 'BANCO J.P. MORGAN S.A.'},
]
_lat_ref, _lat_load, _otm_load, _rows = (R._latam_latest_ref, R._latam_load,
                                         R._otm_load, R._mapping_rows)
try:
    R._latam_latest_ref = lambda: 'qualquer'
    R._latam_load = lambda ref: ('x', LATAM)
    R._otm_load = lambda ref: ('x', OTM)
    # `le-spn` conhece só o 1808267 → é ele, e só ele, a perna interna.
    R._mapping_rows = lambda k: ([{'SPN': '1808267', 'LE': 'ATA',
                                   'NAME': 'ATACAMA FUNDO DE INVESTIMENTO'}] if k == 'le-spn' else
                                 [{'PREFIX': p} for p in ('270WI', '270WC', '270RI')]
                                 if k == 'equity-leg-prefix' else [])
    R._refdata_records = lambda: []
    elo = S._ops_equity_link.__wrapped__(None) if hasattr(S._ops_equity_link, '__wrapped__') \
        else S._ops_equity_link(None)

    cli = elo.get('26901956578') or {}
    check('o Título do CLNT traz a contraparte EXTERNA',
          cli.get('counterparty'), 'REDE D OR SAO LUIZ S.A.')
    check('e o Trade Id dela — mesmo o prefixo sendo 270RI',
          cli.get('internal_id'), '270RI0258485')
    check('as curvas são os positivos e os negativos',
          (cli.get('curva_banco'), cli.get('curva_cliente')), (15000.0, -5000.0))
    check('e o settlement é a soma', cli.get('settlement'), 10000.0)

    itn = elo.get('26901900000') or {}
    # A razão social do `le-spn`, não o Nome Simplificado da B3.
    check('o Título do INT traz a perna interna',
          itn.get('counterparty'), 'ATACAMA FUNDO DE INVESTIMENTO')
    check('e o OUTRO Trade Id, com o mesmo Deal_Ref',
          itn.get('internal_id'), '270WI0258485')

    # A prova de que o prefixo não manda: trocando o le-spn, o MESMO arquivo
    # inverte as duas pernas sem que um prefixo mude.
    R._mapping_rows = lambda k: ([{'SPN': '0910711', 'LE': 'X',
                                   'NAME': 'REDE D OR SAO LUIZ S.A.'}] if k == 'le-spn' else
                                 [{'PREFIX': p} for p in ('270WI', '270WC', '270RI')]
                                 if k == 'equity-leg-prefix' else [])
    elo2 = S._ops_equity_link.__wrapped__(None) if hasattr(S._ops_equity_link, '__wrapped__') \
        else S._ops_equity_link(None)
    check('mudando só o le-spn, as pernas trocam (é o SPN que manda)',
          (elo2.get('26901900000') or {}).get('counterparty'), 'REDE D OR SAO LUIZ S.A.')
finally:
    (R._latam_latest_ref, R._latam_load, R._otm_load,
     R._mapping_rows) = _lat_ref, _lat_load, _otm_load, _rows

print('\n== 4. a aba existe na tela ==')
html = open(os.path.join(ROOT, 'apps/templates/pages/mapping.html'), encoding='utf-8').read()
check("a aba 'equity-leg-prefix' está no TYPES", "key: 'equity-leg-prefix'" in html, True)

print('\nFALHAS: %d' % len(falhas))
if falhas:
    for f in falhas:
        print('  - %s' % f)
sys.exit(1 if falhas else 0)
