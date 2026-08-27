"""Quoted in Cents: a divisao por 100 NAO olha a moeda do strike.

A regra e do ATIVO — Fator Conversao 0,01 no Subjacente — e nao do par de
moedas do deal. Ate 03/08/2026 dois dos quatro caminhos excetuavam o BRL e dois
nao, cruzados: NDF Comm dividia sem exceção no Intrag e com exceção no Conecta,
e o Opt Comm fazia o contrario. O mesmo deal saia com strike 100x diferente
dependendo do arquivo. Ficou um criterio so: cotado em cents divide, ponto.

O que este script protege:

  1. `_is_cents_factor`: so 0,01 e cents, em qualquer grafia (0.01, '0,01').
  2. O parser do booking recap marca YES/NO/MISSING pelo cadastro do Subjacente.
  3. NENHUM ponto que aplica a divisao menciona moeda. Esta e a asserção que
     pega a reintrodução da exceção — os quatro caminhos (Conecta e Intrag, de
     NDF Comm e Opt Comm) e as duas copias no navegador estão cobertos por
     varredura de codigo-fonte, porque executa-los exigiria escrever arquivo do
     dia e disparar rota.
  4. `_conf_strike_adj` (confirmações) segue pelo Fator Conversão, sem moeda.

Nao encosta em dado real.
"""
import io
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import otc_boxparse as B                     # noqa: E402
from apps.pages import routes as R                           # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('\n== 1. o que conta como cents ==')
for f, exp in ((0.01, True), ('0.01', True), ('0,01', True), (' 0.01 ', True),
               (0.010000000001, True),          # tolerancia do float
               (1, False), (0.1, False), (0.001, False), (100, False),
               ('', False), (None, False), ('abc', False), (0, False)):
    check('_is_cents_factor(%r)' % (f,), B._is_cents_factor(f), exp)

print('\n== 2. o parser marca YES/NO/MISSING pelo Subjacente ==')
DEAL = {'DealName': 'D-1', 'TradeDate': '01/08/2026', 'Contract': 'Dec26',
        'Market': 'HO_NYMEX', 'Acronym': 'ACME', 'Type': 'BUY',
        'FixingStartDate': '01/12/2026', 'FixingEndDate': '01/12/2026',
        'SettlementDate': '05/12/2026', 'TotalNotional': '100', 'Strike': '250,00'}
MAPS = {'fixed': {}, 'dynamic': {'HO_NYMEX': 'HO"MY"'}, 'holiday': {'HO_NYMEX': 'NYMEX'}}


def quoted(subj_idx):
    return B.build_deal(dict(DEAL), {}, subj_idx, 'E930179', 'ndf', MAPS)['QuotedInCents']


check('fator 0,01 -> YES',        quoted({'HOZ6': {'commodity': 'X', 'fatorConversao': 0.01}}), 'YES')
check('fator 1 -> NO',            quoted({'HOZ6': {'commodity': 'X', 'fatorConversao': 1}}), 'NO')
check('fator ausente -> NO',      quoted({'HOZ6': {'commodity': 'X'}}), 'NO')
check('sem cadastro -> MISSING',  quoted({}), 'MISSING')

print('\n== 3. nenhum ponto da divisao olha a moeda ==')
# Toda linha que APLICA a regra (nao a que define o helper) e varrida atras de
# qualquer termo de moeda. Uma exceção de BRL reintroduzida cai aqui.
ALVOS = [
    ('apps/pages/routes.py',
     r'^\s*(?!def ).*(div100\s*=|_cents\s*=\s*lambda|strike_effective\s*=)'),
    ('apps/pages/features/new_deals/entrypoint.py',
     r'^\s*(?!def ).*(div100\s*=|_cents\s*=\s*lambda|strike_effective\s*=)'),
    ('apps/templates/pages/new_deals-ndf-commodities.html',
     r'_num\(deal\.(Strike|PremiumPerUnit)'),
    ('apps/templates/pages/new_deals-opt-commodities.html',
     r'_num\(deal\.(Strike|PremiumPerUnit)'),
]
MOEDA = re.compile(r'brl|strike_ccy|strikeCcy|StrikeCurrency', re.I)
aplicacoes = 0
for path, pat in ALVOS:
    rx = re.compile(pat)
    for n, line in enumerate(io.open(path, encoding='utf-8'), start=1):
        if not rx.search(line) or 'div100=False' in line:
            continue
        aplicacoes += 1
        check('%s:%d sem moeda na regra' % (os.path.basename(path), n),
              bool(MOEDA.search(line)), False)
# Se a varredura parar de achar as aplicacoes (refactor mudou o nome), o teste
# viraria vacuo — entao o numero minimo tambem e asserção.
check('a varredura achou as aplicacoes', aplicacoes >= 6, True)

print('\n== 4. os quatro caminhos dividem igual ==')
# Comparacao literal das expressoes, uma por caminho, para o teste dizer QUAL
# caminho divergiu em vez de so "achei moeda numa linha".
# Os gravadores da Intrag moram em features/intrag desde a extracao — os dois
# arquivos entram na mesma varredura.
src = (io.open('apps/pages/routes.py', encoding='utf-8').read()
       + io.open('apps/pages/features/intrag/engine.py', encoding='utf-8').read()
       + io.open('apps/pages/features/new_deals/entrypoint.py', encoding='utf-8').read())
check('NDF Comm -> Intrag',
      'strike_effective = strike_val / 100.0 if qic else strike_val' in src, True)
check('Opt Comm -> Intrag',
      '_cents = lambda v: (v / 100.0) if qic else v' in src, True)
check('NDF Comm -> Conecta',
      "strike_str = _pos_num(deal.get('Strike', ''), 12, 8, div100=qic)" in src, True)
# Desde o File Interface v3 a montagem e por seq do template (values dict),
# nao mais por indice de lista — a regra continua a mesma.
check('Opt Comm -> Conecta (strike)',
      "'14': _num(deal.get('Strike', ''), div100=qic)" in src, True)
check('Opt Comm -> Conecta (premio/unidade)',
      "'27': _num(deal.get('PremiumPerUnit', ''), div100=qic)" in src, True)
js_ndf = io.open('apps/templates/pages/new_deals-ndf-commodities.html', encoding='utf-8').read()
js_opt = io.open('apps/templates/pages/new_deals-opt-commodities.html', encoding='utf-8').read()
check('NDF Comm -> Conecta (navegador)', "f[17] = _num(deal.Strike || '', qic);" in js_ndf, True)
check('Opt Comm -> Conecta (navegador)', "f[13] = _num(deal.Strike || '', qic);" in js_opt, True)

print('\n== 5. confirmações: o ajuste vem do Fator, sem moeda ==')
# Fator cadastrado manda; sem fator, cai no YES do deal; senao, strike cru.
for subj, deal, exp in (
        ({'fator': 0.01}, {'Strike': '250'},                        2.5),
        ({'fator': 0.01}, {'Strike': '250', 'StrikeCurrency': 'BRL'}, 2.5),
        ({'fator': 1},    {'Strike': '250', 'StrikeCurrency': 'BRL'}, 250.0),
        (None,            {'Strike': '250', 'QuotedInCents': 'YES'},  2.5),
        (None,            {'Strike': '250', 'QuotedInCents': 'YES',
                           'StrikeCurrency': 'BRL'},                  2.5),
        (None,            {'Strike': '250', 'QuotedInCents': 'NO'},   250.0),
        (None,            {'Strike': ''},                             None)):
    check('_conf_strike_adj(subj=%r, %r)' % (subj, deal.get('StrikeCurrency', '-')),
          R._conf_strike_adj(deal, subj), exp)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
