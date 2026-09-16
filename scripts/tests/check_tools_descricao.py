# -*- coding: utf-8 -*-
"""Swap Calculator: a Denominacao da curva e o IR pelo cadastro (§479).

Duas coisas que a posicao da B3 NAO diz e a liquidacao precisa:

1. A `Denominacao` da curva VCP — o texto livre que a mesa cadastra e o Live
   Position mostra: `TERM SOFR 3M - Fixings PTAX-Ask T-1 - Initial FX PTAX-V
   15/Jun/26 - (3M SOFR + 0.75%)*1.1765 A/360`. O `*1.1765` so existe ali, e
   sem ele a liquidacao nao bate com a planilha da mesa. O interpretador
   (`precificador/descricao_curva.py`) e de REGRAS: cada achado sai com o
   trecho de onde veio, e o que sobra com numero e operador vai para
   `nao_lido` — nunca uma resposta sem "nao sei".

2. A aliquota de IR vem do CADASTRO, nao de uma tabela fixa: a excecao por
   cliente do `swap-ir-client` vence a direcao (a regra do Trade Level), e as
   faixas sao as do `swap-ir-term`.

O que se prende:
  §1  o interpretador: o exemplo real, divisor, gross-up, contagens, CDI, o
      residual sem leitura, texto vazio;
  §2  o motor: o multiplicador incide na TAXA antes de capitalizar (nao no
      fator), em cada indice; a perna sem taxa ignora; a memoria do resultado
      o descreve; multiplicador nao positivo e erro;
  §3  `aplicar_descricao`: aplicado / confirma / divergente / info, o
      `faltando` perdendo o campo, o % do CDI so na ponta CDI;
  §4  o formulario: `_multiplicador` e `_descricao` chegam a `Ponta`, em
      branco e 1,0;
  §5  `RegraIR` no motor: a excecao vence nas DUAS direcoes, as faixas do
      cadastro, a lacuna acima da ultima faixa caindo na tabela do motor,
      `reter_ir` desligado zerando tudo;
  §6  a leitura do cadastro pela platform, com as linhas STUBADAS: `Starts
      with`, `Exact`, cliente fora, e o `_ops_swap_ir_rate` do Trade Level
      respondendo o mesmo que antes;
  §7  o endpoint `/api/tools/swap-calculator/curve` e o `Calculate` da tela
      com o multiplicador e a excecao de IR.
"""
import datetime as _dt
import os
import sys
from datetime import date

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

falhas = []

from apps import create_app                                             # noqa: E402
from apps.config import DebugConfig                                     # noqa: E402

app = create_app(DebugConfig)


def check(rotulo, obtido, esperado):
    ok = obtido == esperado
    print(('  ok  ' if ok else ' FAIL ') + rotulo + ('' if ok else '\n        obtido=%r\n        esperado=%r' % (obtido, esperado)))
    if not ok:
        falhas.append(rotulo)


def perto(rotulo, obtido, esperado, tol=1e-9):
    ok = obtido is not None and esperado is not None and abs(obtido - esperado) <= tol
    print(('  ok  ' if ok else ' FAIL ') + rotulo + ('' if ok else '\n        obtido=%r\n        esperado=%r' % (obtido, esperado)))
    if not ok:
        falhas.append(rotulo)


from apps.pages import routes as R                                      # noqa: E402
from apps.pages.features.tools import domain, queries                   # noqa: E402
from apps.pages.platform import settlement as ST                        # noqa: E402
from apps.pages.precificador import (calendario, contagem, descricao_curva as dc,  # noqa: E402
                                     liquidacao, renda_fixa)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 1. o interpretador da denominacao ==')
EXEMPLO = ('TERM SOFR 3M - Fixings PTAX-Ask T-1 - Initial FX PTAX-V 15/Jun/26 - '
           '(3M SOFR + 0.75%)*1.1765 A/360')
L = dc.interpretar(EXEMPLO)
check('o multiplicador da taxa sai do `)*1.1765`',
      (L.valor(dc.MULTIPLICADOR), [a.trecho for a in L.achados if a.campo == dc.MULTIPLICADOR]),
      ('1.17650000', [')*1.1765']))
check('o spread sai do `SOFR + 0.75%`', L.valor(dc.TAXA), '0.7500')
check('a contagem sai do `A/360`', L.valor(dc.CONVENCAO), contagem.ACT_360)
check('o prazo do fixing sai do `3M SOFR`', L.valor(dc.TENOR), '3 month')
check('o D-n da PTAX sai do `PTAX-Ask T-1`', L.valor(dc.PTAX_OFFSET), '1')
check('a data do fixing inicial e SO informacao (campo None)',
      [(a.valor, a.rotulo) for a in L.achados if a.campo is None and 'date' in a.rotulo],
      [('15/JUN/26', 'initial FX fixing date')])
check('nada sobrou sem leitura no exemplo real', L.nao_lido, [])
check('os achados vem na ORDEM do texto',
      [a.inicio for a in L.achados] == sorted(a.inicio for a in L.achados), True)

check('`(…)/0.85` e o mesmo gross-up, como divisao',
      dc.interpretar('(SOFR - 0.20%)/0.85 ACT/360').valor(dc.MULTIPLICADOR), '1.17647059')
check('   e o spread negativo sai com sinal',
      dc.interpretar('(SOFR - 0.20%)/0.85').valor(dc.TAXA), '-0.2000')
check('`gross-up 15%` vira 1/(1-0,15)',
      dc.interpretar('CDI + 2% gross-up 15%').valor(dc.MULTIPLICADOR), '1.17647059')
check('`1.1765*(...)` na frente tambem',
      dc.interpretar('1.1765*(3M SOFR + 0.75%)').valor(dc.MULTIPLICADOR), '1.17650000')
check('`110% do CDI` e o percentual, nao spread',
      (dc.interpretar('110% do CDI').valor(dc.PERCENTUAL), dc.interpretar('110% do CDI').valor(dc.TAXA)),
      ('110.0000', None))
check('`Exp/252` e DU/252 composto; `Lin/360` e ACT/360 simples',
      (dc.interpretar('CDI + 1.07% Exp/252').valor(dc.CONVENCAO),
       dc.interpretar('CDI + 1.07% Exp/252').valor(dc.REGIME),
       dc.interpretar('SOFR + 1% Lin/360').valor(dc.CONVENCAO),
       dc.interpretar('SOFR + 1% Lin/360').valor(dc.REGIME)),
      (contagem.DU_252, contagem.COMPOSTO, contagem.ACT_360, contagem.SIMPLES))
check('30/360, 30E/360, BUS/252, ACT/ACT',
      [dc.interpretar(t).valor(dc.CONVENCAO) for t in ('x 30/360', 'x 30E/360', 'x BUS/252', 'x ACT/ACT')],
      [contagem.T30_360, contagem.T30E_360, contagem.DU_252, contagem.ACT_ACT])
check('EURIBOR 6M e o prazo; lookback e shift do SOFR composto',
      (dc.interpretar('EURIBOR 6M + 1.5%').valor(dc.TENOR),
       dc.interpretar('SOFR compounded lookback 5 shift 2').valor(dc.LOOKBACK),
       dc.interpretar('SOFR compounded lookback 5 shift 2').valor(dc.SHIFT)),
      ('6 month', '5', '2'))
# O residual: numero com operador que NENHUMA regra consumiu vai para a mesa.
L2 = dc.interpretar('EURIBOR 6M + 1.5% 30/360 - fator 2 aplicado x 0.5 no cupom')
check('o que sobra com numero e operador vai para `nao_lido`',
      L2.nao_lido, ['fator 2 aplicado x 0.5 no cupom'])
check('   e o que foi lido nao volta como sobra',
      (L2.valor(dc.TAXA), L2.valor(dc.CONVENCAO)), ('1.5000', contagem.T30_360))
check('texto sem numero-com-operador nao gera sobra',
      dc.interpretar('Fixings PTAX-Ask T-1 - Term SOFR 3M').nao_lido, [])
check('texto vazio: leitura vazia', (dc.interpretar('').vazia, dc.interpretar(None).vazia), (True, True))
check('um campo sai UMA vez: a primeira regra vence',
      len([a for a in dc.interpretar('(SOFR + 1%)*1.2 x (CDI+1%)*1.3').achados
           if a.campo == dc.MULTIPLICADOR]), 1)
check('acento e caixa nao atrapalham', dc.interpretar('cdi + 1,07% exp/252').valor(dc.TAXA), '1.0700')
# O ` - ` da B3 separa clausulas: em `DI - 110% do CDI + 0.5%` nao ha spread de -110%.
L3 = dc.interpretar('DI - 110% do CDI + 0.5% Exp/252')
check('o ` - ` separador de clausula nao vira spread negativo',
      (L3.valor(dc.PERCENTUAL), L3.valor(dc.TAXA)), ('110.0000', '0.5000'))
check('   e um spread negativo de verdade continua negativo',
      dc.interpretar('CDI - 0.5%').valor(dc.TAXA), '-0.5000')
check('   e a clausula sem leitura entre dois separadores sai limpa',
      dc.interpretar('DI - 110% do CDI + 0.5% Exp/252 - tranche 2 x 0.5').nao_lido, ['tranche 2 x 0.5'])

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 2. o motor: o multiplicador incide na TAXA, antes de capitalizar ==')
cal = calendario.calendario_anbima()
op, ini, fim = date(2025, 9, 1), date(2025, 9, 1), date(2026, 3, 2)


def ponta_liq(p):
    return liquidacao.liquidar_ponta(p, 1_000_000.0, ini, fim, cal)


pre = ponta_liq(liquidacao.Ponta(indexador=liquidacao.PRE, taxa=0.14, multiplicador=1.1765))
tau = contagem.fracao(contagem.DU_252, ini, fim, cal)
perto('PRE: (1 + 0,14 x 1,1765)^tau — a taxa multiplicada, nao o fator',
      pre.fator_do_indice, (1 + 0.14 * 1.1765) ** tau, 1e-12)
check('   e NAO ((1+0,14)^tau) x 1,1765',
      abs(pre.fator_do_indice - ((1.14 ** tau) * 1.1765)) > 1e-6, True)
check('   o resultado guarda o multiplicador', pre.multiplicador, 1.1765)
check('   e a descricao o diz', 'rate × 1.176500' in pre.descricao_texto, True)
sem = ponta_liq(liquidacao.Ponta(indexador=liquidacao.PRE, taxa=0.14))
check('sem multiplicador nada muda (1,0 e o padrao)',
      (sem.multiplicador, 'rate ×' in sem.descricao_texto), (1.0, False))
perto('   e 1,0 explicito e o mesmo que nenhum',
      ponta_liq(liquidacao.Ponta(indexador=liquidacao.PRE, taxa=0.14, multiplicador=1.0)).fator,
      sem.fator, 1e-15)

# Term SOFR com a taxa do fixing DADA (sem base importada): (fix + spread) x k
ts = ponta_liq(liquidacao.Ponta(indexador=liquidacao.TERM_SOFR, taxa=0.0075, taxa_indice=0.0430,
                                convencao=contagem.ACT_360, regime=contagem.SIMPLES,
                                moeda=liquidacao.SEM_CONVERSAO, multiplicador=1.1765))
tau360 = contagem.fracao(contagem.ACT_360, ini, fim, cal)
perto('Term SOFR: 1 + (4,30% + 0,75%) x 1,1765 x tau — o exemplo da mesa',
      ts.fator_do_indice, 1 + (0.0430 + 0.0075) * 1.1765 * tau360, 1e-12)
check('   a perna sem multiplicador NAO bate: e o que faltava para a planilha',
      abs(ponta_liq(liquidacao.Ponta(indexador=liquidacao.TERM_SOFR, taxa=0.0075, taxa_indice=0.0430,
                                     convencao=contagem.ACT_360, regime=contagem.SIMPLES,
                                     moeda=liquidacao.SEM_CONVERSAO)).fator_do_indice
          - ts.fator_do_indice) > 1e-6, True)
moeda = ponta_liq(liquidacao.Ponta(indexador=liquidacao.MOEDA, moeda='USD', ptax_inicial=5.0,
                                   ptax_final=5.5, multiplicador=1.1765))
check('perna SEM taxa (moeda) ignora o multiplicador — nao ha taxa a multiplicar',
      (moeda.fator_do_indice, 'rate ×' in moeda.descricao_texto), (1.0, False))
fat = ponta_liq(liquidacao.Ponta(indexador=liquidacao.FATOR, fator_manual=1.05, multiplicador=2.0))
check('   e o fator informado tambem', fat.fator, 1.05)
try:
    ponta_liq(liquidacao.Ponta(indexador=liquidacao.PRE, taxa=0.14, multiplicador=0.0))
    check('multiplicador zero e erro', 'passou', 'ErroLiquidacao')
except liquidacao.ErroLiquidacao as exc:
    check('multiplicador zero e erro', 'positive' in str(exc), True)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 3. aplicar_descricao: o que ela diz sobre os campos da ponta ==')
# o cadastro manda DU/252 de proposito: a denominacao diz A/360, e a
# divergencia e o que se quer ver (o padrao do Term SOFR ja e A/360)
regra = {'INDEX': liquidacao.TERM_SOFR, 'CURRENCY': 'USD', 'DAY COUNT': contagem.DU_252,
         'REGIME': '', 'TENOR': ''}
campos, faltando = domain.montar_ponta(regra, None, 0.75, 1.0, 'TERM SOFR 3M', 5.043,
                                       deslocamento=None)
check('antes: a posicao trouxe o spread e nao trouxe o D-n da PTAX',
      (campos['taxa'], 'ptax_offset' in faltando, campos['multiplicador']), ('0.7500', True, ''))
domain.aplicar_descricao(campos, EXEMPLO, faltando)
estados = {it['campo']: it['estado'] for it in campos['leitura'] if it['campo']}
check('o multiplicador entra como APLICADO (a coluna nao o tem)',
      (campos['multiplicador'], estados[dc.MULTIPLICADOR]), ('1.17650000', 'aplicado'))
check('o spread CONFIRMA a coluna (0,75 = 0,7500)', estados[dc.TAXA], 'confirma')
check('o D-n da PTAX e aplicado e sai de `faltando`',
      (campos['ptax_offset'], estados[dc.PTAX_OFFSET], 'ptax_offset' in faltando), ('1', 'aplicado', False))
check('a contagem A/360 DIVERGE do cadastro (DU/252) e a denominacao VENCE',
      (campos['convencao'], estados[dc.CONVENCAO]), (contagem.ACT_360, 'divergente'))
check('   guardando o que a coluna trazia',
      [it.get('anterior') for it in campos['leitura'] if it['campo'] == dc.CONVENCAO],
      [contagem.DU_252])
check('   e com o padrao do indice (A/360) ela CONFIRMA',
      {it['campo']: it['estado'] for it in domain.aplicar_descricao(
          domain.montar_ponta(dict(regra, **{'DAY COUNT': ''}), None, 0.75, 1.0, 'TERM SOFR 3M', 5.043)[0],
          EXEMPLO)['leitura']}[dc.CONVENCAO], 'confirma')
check('a data do fixing inicial e info: mostrada, nao aplicada',
      [it['estado'] for it in campos['leitura'] if it['campo'] is None], ['info', 'info'])
check('o texto normalizado fica no campo `descricao`', campos['descricao'], EXEMPLO)
check('nada ficou sem leitura', campos['nao_lido'], [])
# spread ZERADO na coluna conta como vazio: a denominacao preenche, nao diverge
c2, _ = domain.montar_ponta({'INDEX': liquidacao.PRE}, None, None, 1.0, '', None)
domain.aplicar_descricao(c2, 'PRE + 12.5% DU/252')
check('taxa `0.0000` da coluna e vazio: o spread da denominacao e APLICADO',
      (c2['taxa'], [it['estado'] for it in c2['leitura'] if it['campo'] == dc.TAXA]),
      ('12.5000', ['aplicado']))
# % do CDI numa ponta que nao e CDI: so informacao
c3, _ = domain.montar_ponta({'INDEX': liquidacao.PRE}, None, 0.10, 1.0, '', None)
domain.aplicar_descricao(c3, '110% do CDI')
check('% do CDI numa ponta PRE e info, nao aplicado',
      ([it['estado'] for it in c3['leitura']], c3.get('percentual')), (['info'], ''))
c4, _ = domain.montar_ponta({'INDEX': liquidacao.CDI}, 100.0, 0.0, 1.0, '', None)
domain.aplicar_descricao(c4, '110% do CDI + 1.07%')
check('   na ponta CDI o percentual DIVERGE (100 → 110) e o spread e aplicado',
      (c4['percentual'], c4['taxa'], {it['campo']: it['estado'] for it in c4['leitura']}),
      ('110.0000', '1.0700', {dc.PERCENTUAL: 'divergente', dc.TAXA: 'aplicado'}))
c4b, _ = domain.montar_ponta({'INDEX': liquidacao.CDI}, 1.10, 0.0, 1.0, '', None)
domain.aplicar_descricao(c4b, '110% do CDI')
check('   `1,10` da posicao e `110%` da denominacao sao o MESMO percentual: confirma',
      [it['estado'] for it in c4b['leitura']], ['confirma'])
c5, _ = domain.montar_ponta({'INDEX': liquidacao.PRE}, None, 0.10, 1.0, '', None)
domain.aplicar_descricao(c5, '')
check('denominacao vazia: leitura vazia e nada muda',
      (c5['leitura'], c5['nao_lido'], c5['taxa']), ([], [], '0.1000'))
c6 = queries.ler_descricao('(SOFR + 1%)*1.2 - tranche 3 x 0.5', {'indexador': 'sofr', 'taxa': '1.0000'})
check('`ler_descricao` (o endpoint) e a mesma funcao: confirma o spread e aplica o resto',
      ({it['campo']: it['estado'] for it in c6['leitura']}, c6['nao_lido']),
      ({dc.TAXA: 'confirma', dc.MULTIPLICADOR: 'aplicado'}, ['tranche 3 x 0.5']))

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 4. o formulario ==')
p = domain.ponta_do_form({'ativa_indexador': 'pre', 'ativa_taxa': '14', 'ativa_multiplicador': '1.1765',
                          'ativa_descricao': '  (PRE)*1.1765  '}, 'ativa')
check('`_multiplicador` e `_descricao` chegam a Ponta', (p.multiplicador, p.descricao_curva),
      (1.1765, '(PRE)*1.1765'))
check('em branco, o multiplicador e 1,0',
      domain.ponta_do_form({'ativa_indexador': 'pre', 'ativa_taxa': '14', 'ativa_multiplicador': ''},
                           'ativa').multiplicador, 1.0)
check('   e ausente tambem',
      domain.ponta_do_form({'ativa_indexador': 'pre', 'ativa_taxa': '14'}, 'ativa').multiplicador, 1.0)
check('virgula decimal e aceita', domain.ponta_do_form(
    {'ativa_indexador': 'pre', 'ativa_taxa': '14', 'ativa_multiplicador': '1,1765'}, 'ativa').multiplicador,
    1.1765)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 5. RegraIR no motor ==')


def liquidar(fa, fp, **kw):
    return liquidacao.liquidar(
        data_operacao=op, inicio=ini, fim=fim, nocional=10_000_000.0,
        ponta_ativa=liquidacao.Ponta(indexador=liquidacao.FATOR, fator_manual=fa),
        ponta_passiva=liquidacao.Ponta(indexador=liquidacao.FATOR, fator_manual=fp),
        calendario=cal, **kw)


exc10 = liquidacao.RegraIR(excecao=0.10, cliente='J.P. MORGAN OVERSEAS CAPITAL LLC')
r = liquidar(1.05, 1.10, regra_ir=exc10)                 # banco paga
check('excecao por cliente: 10% quando o banco paga',
      (r.aliquota_ir, r.origem_ir, r.cliente_ir), (0.10, 'cliente', 'J.P. MORGAN OVERSEAS CAPITAL LLC'))
r2 = liquidar(1.10, 1.05, regra_ir=exc10)                # banco recebe
check('   e TAMBEM quando o banco recebe — a excecao vence a direcao (regra do Trade Level)',
      (r2.aliquota_ir, r2.origem_ir, round(r2.ir, 2)), (0.10, 'cliente', round(abs(r2.ajuste_bruto) * 0.10, 2)))
isento = liquidacao.RegraIR(excecao=0.0, cliente='BANCO')
check('excecao a 0% e isencao, nas duas direcoes',
      (liquidar(1.05, 1.10, regra_ir=isento).ir, liquidar(1.10, 1.05, regra_ir=isento).ir), (0.0, 0.0))
faixas = liquidacao.RegraIR(faixas=((90, 0.30), (365, 0.25), (None, 0.12)))
r3 = liquidar(1.05, 1.10, regra_ir=faixas)               # 182 dias
check('sem excecao, as faixas do CADASTRO valem (182d → 25%), so quando o banco paga',
      (r3.aliquota_ir, r3.origem_ir, liquidar(1.10, 1.05, regra_ir=faixas).aliquota_ir),
      (0.25, 'prazo', 0.0))
check('acima da ultima faixa vale a linha sem limite',
      liquidacao.RegraIR(faixas=((90, 0.30), (None, 0.12))).aliquota_por_prazo(400), 0.12)
check('sem linha "acima de todas", a lacuna cai na tabela do MOTOR — nunca 0%',
      liquidacao.RegraIR(faixas=((90, 0.30),)).aliquota_por_prazo(400), renda_fixa.aliquota_ir(400))
check('RegraIR vazia = a tabela do motor',
      liquidar(1.05, 1.10, regra_ir=liquidacao.RegraIR()).aliquota_ir, renda_fixa.aliquota_ir((fim - op).days))
check('`regra_ir=None` e o comportamento de sempre',
      liquidar(1.05, 1.10).aliquota_ir, renda_fixa.aliquota_ir((fim - op).days))
check('reter_ir desligado zera ate a excecao',
      (liquidar(1.05, 1.10, regra_ir=exc10, reter_ir=False).ir,
       liquidar(1.05, 1.10, regra_ir=exc10, reter_ir=False).origem_ir), (0.0, ''))

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 6. a leitura do cadastro pela platform (linhas stubadas) ==')
CLIENTES = [{'CLIENT': 'JPMORGAN CHASE BANK, N.A', 'MATCH': 'Exact', 'RATE': '0'},
            {'CLIENT': 'BANCO', 'MATCH': 'Starts with', 'RATE': '0'},
            {'CLIENT': 'J.P. MORGAN OVERSEAS CAPITAL LLC', 'MATCH': 'Exact', 'RATE': '10'},
            {'CLIENT': 'FUNDO SEM TAXA', 'MATCH': 'Exact', 'RATE': 'x'}]
FAIXAS = [{'UP TO DAYS': '180', 'RATE': '22.5'}, {'UP TO DAYS': '360', 'RATE': '20'},
          {'UP TO DAYS': '720', 'RATE': '17.5'}, {'UP TO DAYS': '', 'RATE': '15'}]
_map_rows = R._mapping_rows
R._mapping_rows = lambda key: (CLIENTES if key == 'swap-ir-client'
                               else FAIXAS if key == 'swap-ir-term' else _map_rows(key))
try:
    check('`Starts with`: BANCO XYZ S.A. → 0%', ST._swap_ir_excecao('Banco XYZ S.A.'), (0.0, 'BANCO'))
    check('`Exact`: a Overseas → 10%',
          ST._swap_ir_excecao('j.p. morgan overseas capital llc'), (0.10, 'J.P. MORGAN OVERSEAS CAPITAL LLC'))
    check('cliente fora do cadastro → (None, "")', ST._swap_ir_excecao('YAZAKI DO BRASIL LTDA'), (None, ''))
    check('   e sem nome tambem', ST._swap_ir_excecao(''), (None, ''))
    check('linha que casa com RATE ilegivel: casou, mas sem aliquota',
          ST._swap_ir_excecao('FUNDO SEM TAXA'), (None, 'FUNDO SEM TAXA'))
    check('as faixas, na ordem, a sem limite por ultimo',
          ST._swap_ir_faixas(), [(180.0, 0.225), (360.0, 0.20), (720.0, 0.175), (None, 0.15)])
    # O Trade Level continua respondendo o mesmo que antes da refatoracao.
    check('_ops_swap_ir_rate: excecao vence (Overseas, contraparte pagando)',
          ST._ops_swap_ir_rate('J.P. MORGAN OVERSEAS CAPITAL LLC', 100, False), 0.10)
    check('   fora da excecao, contraparte NAO recebe → 0', ST._ops_swap_ir_rate('YAZAKI', 100, False), 0.0)
    check('   direcao desconhecida → None', ST._ops_swap_ir_rate('YAZAKI', 100, None), None)
    check('   prazo desconhecido → None', ST._ops_swap_ir_rate('YAZAKI', None, True), None)
    check('   as faixas: 100d 22,5% · 721d 15% (o vao da planilha fechado)',
          (ST._ops_swap_ir_rate('YAZAKI', 100, True), ST._ops_swap_ir_rate('YAZAKI', 721, True)), (0.225, 0.15))
    check('   linha que casa com RATE ilegivel → None (nao afirma)',
          ST._ops_swap_ir_rate('FUNDO SEM TAXA', 100, True), None)
    check('   sem nome → None', ST._ops_swap_ir_rate('', 100, True), None)
    rg = queries.regra_ir_do_cliente('Banco do Brasil S.A.')
    check('a RegraIR do Swap Calculator sai das mesmas duas perguntas',
          (rg.excecao, rg.cliente, rg.faixas), (0.0, 'BANCO', ((180.0, 0.225), (360.0, 0.20), (720.0, 0.175), (None, 0.15))))
    check('   contraparte vazia: sem excecao, faixas do cadastro',
          (queries.regra_ir_do_cliente('').excecao, len(queries.regra_ir_do_cliente(None).faixas)), (None, 4))

    # ─────────────────────────────────────────────────────────────────────────
    print('\n== 7. a tela: o endpoint da denominacao e o Calculate ==')
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(authenticated=True, user_sid='X1', user_name='t', user_role='ADMIN',
                 session_expires_at=(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
                                     + _dt.timedelta(hours=1)).isoformat())
    resp = c.get('/api/tools/swap-calculator/curve',
                 query_string={'text': EXEMPLO, 'indexador': 'term_sofr', 'taxa': '0.7500 %',
                               'convencao': contagem.ACT_360, 'multiplicador': '', 'tenor': '3 month'})
    d = resp.get_json()
    check('o endpoint responde a leitura sobre os campos atuais',
          (resp.status_code, d['success'], d['multiplicador'],
           {it['campo']: it['estado'] for it in d['leitura'] if it['campo']}),
          (200, True, '1.17650000',
           {dc.PTAX_OFFSET: 'aplicado', dc.TENOR: 'confirma', dc.TAXA: 'confirma',
            dc.MULTIPLICADOR: 'aplicado', dc.CONVENCAO: 'confirma'}))
    check('   sem sessao e 401', app.test_client().get('/api/tools/swap-calculator/curve?text=x').status_code, 401)

    FORM = {'counterparty': 'J.P. MORGAN OVERSEAS CAPITAL LLC',
            'data_operacao': '2025-09-01', 'inicio': '2025-09-01', 'fim': '2026-03-02',
            'vencimento': '2027-09-01', 'base_ajuste': liquidacao.BASE_VALOR_FUTURO,
            'nocional': '10,000,000.00', 'nocional_original': '10,000,000.00',
            'amortizacao': '0', 'base_amortizacao': liquidacao.SOBRE_ORIGINAL,
            'calendario': 'ANBIMA', 'reter_ir': '1',
            'ativa_indexador': 'fator', 'ativa_fator': '1.10',
            'passiva_indexador': 'pre', 'passiva_taxa': '14', 'passiva_convencao': contagem.DU_252,
            'passiva_regime': contagem.COMPOSTO, 'passiva_multiplicador': '1.1765',
            'passiva_descricao': '(PRE 14%)*1.1765 DU/252'}
    calc = queries.liquidar(FORM)
    rr = calc['r']
    perto('Calculate: a perna PRE sai com a taxa x 1,1765',
          rr.passiva.fator_do_indice, (1 + 0.14 * 1.1765) ** tau, 1e-12)
    check('   e o IR e a excecao da Overseas, com o banco RECEBENDO',
          (rr.quem_recebe, rr.aliquota_ir, rr.origem_ir), (liquidacao.ATIVA, 0.10, 'cliente'))
    check('   a RegraIR volta no calculo (a memoria a usa)', calc['regra_ir'].cliente, 'J.P. MORGAN OVERSEAS CAPITAL LLC')
    html = c.post('/tools/swap-calculator', data=FORM).data.decode()
    check('a tela mostra o multiplicador da ponta e a origem da aliquota',
          ('× 1.176500' in html, 'client exception (swap-ir-client)' in html,
           '(PRE 14%)*1.1765 DU/252' in html), (True, True, True))
    check('   e os campos novos existem nas duas pontas',
          all(x in html for x in ('id="ativa_descricao"', 'id="passiva_descricao"',
                                  'id="ativa_multiplicador"', 'id="passiva_multiplicador"')), True)
    FORM2 = dict(FORM, counterparty='YAZAKI DO BRASIL LTDA')
    r4 = queries.liquidar(FORM2)['r']
    check('contraparte fora das excecoes, banco recebendo: sem IR',
          (r4.aliquota_ir, r4.origem_ir), (0.0, ''))
    r5 = queries.liquidar(dict(FORM2, ativa_fator='1.00'))['r']
    check('   e banco pagando: a faixa do cadastro pelo prazo (182d → 20%)',
          (r5.quem_recebe, r5.aliquota_ir, r5.origem_ir), (liquidacao.PASSIVA, 0.20, 'prazo'))
finally:
    R._mapping_rows = _map_rows

print('\n' + ('TUDO OK' if not falhas else 'FALHAS: %d' % len(falhas)))
for f in falhas:
    print('  - ' + f)
sys.exit(1 if falhas else 0)
