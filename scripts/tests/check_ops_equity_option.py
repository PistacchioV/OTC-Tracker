# -*- coding: utf-8 -*-
"""OPÇÃO DE EQUITY — o valor interno sai do OTM Settlements, como no swap.

A B3 registra a opção de ação com um Título, e o Trade Level monta a linha a
partir dele. O valor (Settlement, a coluna do valor INTERNO) vinha do OTM pelo
SUFIXO da `Combinação de operações` da Live Position de Opção — campo que a
opção de ação não preenche. Sem sufixo não havia valor: a linha aparecia no
Trade Level com a célula vazia e SUMIA do Settlement Summary, que descarta quem
não tem o que liquidar.

O plano B é o MESMO elo que o swap de equity usa — Operations B3 (Título) →
Latam Desk Position (CLEARING_TRD_ID_*) → OTM Settlements (270WI/270WC +
Deal_Ref). Este script prova as quatro coisas que ele tem de fazer:

  1. o valor sai do OTM quando o sufixo não resolve;
  2. o SPN — e portanto o NOME da contraparte — vem junto;
  3. o sufixo, quando EXISTE, continua vencendo (é um join direto);
  4. a linha, com valor, chega ao Settlement Summary.

As fontes são fixtures: nada aqui toca dado real.
"""
import os
import sys
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)

falhas = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        falhas.append(msg)


from apps.pages import routes as R                     # noqa: E402

REF = datetime(2026, 8, 18)
TITULO = 'OPEQ0001'                                    # Título/Código IF da B3
DEAL_REF = '0000778899'                                # o Deal_Ref do Latam (com zeros)

# ── Operations B3: uma opção liquidando na data ──────────────────────────────
OPB3 = [{'Título': TITULO, 'Tipo Título': 'Opção de Ações',
         'Conta Contraparte': '12345.67-8', 'Contraparte (Nome Simpl.)': 'SAFRABM',
         'Valor Líquido': ''}]

# ── Live Position de Opção: a `Combinação de operações` vem VAZIA, que é o caso
#    da opção de ação — é isso que apagava o valor.
LPOPT_COLS = ['Código IF', 'Combinação de operações', 'Classe do ativo subjacente',
              'Data de fixing do ativo subjacente', 'Data de fixing da moeda do ativo subjacente',
              'Média Asiática (data) 1', 'Tipo de Mercadoria', 'Ativo subjacente / Moeda base',
              'CPF/CNPJ Cliente Contraparte', 'Contraparte (Nome simplificado)']


def _lpopt(conf):
    return {'columns': LPOPT_COLS,
            'rows': [[TITULO, conf, 'Ações', '18/08/2026', '', '', '', 'PETR4', '', 'SAFRABM']]}


# ── Latam Desk Position: o Título casa a coluna do CLIENTE (270WC) ────────────
LATAM = [{'Deal_Ref': DEAL_REF, 'CLEARING_TRD_ID_INT': '', 'CLEARING_TRD_ID_CLNT': TITULO,
          'Underlying_Name': 'PETROBRAS PN', 'Trade_Date': '10/08/2026'}]

# ── OTM Settlements: dois fluxos do mesmo trade ──────────────────────────────
OTM = [{'Trade Id': '270WC778899', 'Amount': '15000.00', 'Cpty SPN': '9911',
        'Cpty Name': 'CLIENTE X', 'Owner Legal Entity': 'BANCO', 'Underlying': 'PETR4'},
       {'Trade Id': '270WC778899', 'Amount': '-5000.00', 'Cpty SPN': '9911',
        'Cpty Name': 'CLIENTE X', 'Owner Legal Entity': 'BANCO', 'Underlying': 'PETR4'}]
ESPERADO = 10000.0                                     # 15000 + (-5000)

orig = {n: getattr(R, n) for n in ('_opb3_settle_rows', '_lpopt_collect', '_ndfadv_otm_by_suffix',
                                   '_latam_equity_b3_index', '_otm_load', '_optadv_cognos_prm',
                                   '_optadv_edits_load', '_opssum_meta_load')}


def _stub(conf='', otm_suffix=None):
    R._opb3_settle_rows = lambda ref: list(OPB3)
    R._lpopt_collect = lambda ref: _lpopt(conf)
    R._ndfadv_otm_by_suffix = lambda ref: (otm_suffix or {}, {})
    R._otm_load = lambda ref: ('', list(OTM))
    R._optadv_cognos_prm = lambda ref: ({}, {})
    R._optadv_edits_load = lambda ref: ('', {})
    R._opssum_meta_load = lambda ref: ('', {})
    # o índice do Latam roda de verdade sobre a fixture: é ele que decide a
    # forma da chave (Título em maiúscula), e um teste que o pulasse não veria
    # um de-para que casa com a grafia errada.
    R._latam_equity_b3_index = lambda: {
        str(r['CLEARING_TRD_ID_CLNT']).upper(): (R._ops_eq_ref_key(r['Deal_Ref']), '270WC', r)
        for r in LATAM}


try:
    # 1 e 2 — sem sufixo, o elo de equity responde pelo valor e pelo SPN
    _stub(conf='')
    linhas = R._optadv_collect(REF)
    ok(len(linhas) == 1, 'a opção de equity produz uma linha')
    r = linhas[0] if linhas else {}
    ok(r.get('apurado') == ESPERADO,
       'sem sufixo, o valor vem do OTM pelo elo do Título ({} → {})'.format(
           r.get('apurado'), ESPERADO))
    ok(str(r.get('spn', '')) == '9911', 'o SPN do OTM chega à linha (contraparte pelo cadastro)')

    # 3 — o sufixo, quando existe, vence: é um join direto e mais confiável
    _stub(conf='ATH-123-ZZ9', otm_suffix={'ZZ9': 4242.0})
    r2 = (R._optadv_collect(REF) or [{}])[0]
    ok(r2.get('apurado') == 4242.0,
       'com sufixo, o valor do sufixo vence o elo de equity ({})'.format(r2.get('apurado')))

    # 4 — com valor, a linha chega ao Trade Level E ao Settlement Summary
    _stub(conf='')
    tl = R._ops_opt_trade_rows(REF)
    ok(len(tl) == 1 and tl[0].get('_settle_n') == ESPERADO,
       'Trade Level: a coluna Settlement (valor interno) sai preenchida')
    ok(tl and tl[0].get('settlement') == '10,000.00',
       'Trade Level: o valor sai formatado #,##0.00')
    ok(tl and tl[0].get('product') == 'OPTION', 'Trade Level: o produto é OPTION')
    somadas = R._opssum_rows(tl, REF)
    ok(len(somadas) == 1,
       'Settlement Summary: a linha deixa de ser descartada por falta de valor')
finally:
    for n, fn in orig.items():
        setattr(R, n, fn)

print('')
print('FALHAS: {}'.format(len(falhas)))
sys.exit(1 if falhas else 0)
