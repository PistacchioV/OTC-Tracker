# -*- coding: utf-8 -*-
"""check_tools.py — Apps > Tools (o porte do *Precificacao Swap*) e os dois
pedidos que vieram junto: a classe do ativo no assunto da mensageria do
Operations B3 e o Edit do CETIP ID no Swap Athena (HANDOFF §424).

O que se prende, e por que cada coisa nao daria erro sozinha:

  1. o MOTOR (`apps/pages/precificador/`): os calendarios saem do Holidays
     Calendar do app — nao de arquivos proprios —, o acumulo do CDI e na janela
     [inicio, fim), a composicao do SOFR fecha com o indice oficial, e a
     liquidacao so retem IR quando o BANCO paga (retendo dos dois lados o numero
     inflava em toda liquidacao a favor do banco, com a aliquota certa);
  2. as BASES locais gravam LISTA DE REGISTROS pelo funil — e a lista e o que o
     espelho converte em TABELA (`db/tools/*.db`). Um dicionario por data (a
     forma do projeto de origem) vira uma tabela de uma linha e mil colunas;
  3. o PRE-PREENCHIMENTO do Swap Calculator pelo B3 ID: a posicao de 170 campos
     lida POSICIONALMENTE, a curva classificada pelo cadastro
     `tools-swap-index` (VCP -> Nome Tipo/Classe), e o que nao vem fica EM
     BRANCO e sinalizado — um valor chutado numa ponta de swap e uma
     liquidacao errada que parece certa;
  4. a casca: as rotas registradas, o sidenav com o Tools e as seis filhas, e o
     padrao de tela (nada de `.card`, nada de `type="date"` visivel);
  5. a mensageria: `(Moeda)`/`(Mercadoria)` no assunto pelo cadastro, e o
     assunto de SEMPRE quando o token nao tem linha;
  6. o Swap Athena: a coluna Actions so com Edit, e a troca do CETIP ID achando
     a linha pelo Kapital ID (o CETIP ID e o que esta sendo corrigido, entao
     nao pode ser a chave).

Nada sai da maquina: a rede nao e tocada e os arquivos vao para um tmp.
"""
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

TMP = tempfile.mkdtemp(prefix='otc-tools-')
falhas = []


def check(rotulo, obtido, esperado):
    ok = obtido == esperado
    print(('  ok  ' if ok else ' FAIL ') + rotulo +
          ('' if ok else '\n        got=%r\n        exp=%r' % (obtido, esperado)))
    if not ok:
        falhas.append(rotulo)


def ler(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8').read()


from apps.pages import routes as R                                      # noqa: E402
from apps.pages import athena_api as A                                  # noqa: E402,F401
from apps.pages.precificador import (bases, calendario, cdi, contagem,  # noqa: E402
                                     liquidacao, renda_fixa, sofr)
from apps.pages.features.tools import domain, queries                   # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
print('== 1. o motor: calendario e contagem de dias ==')
cal = calendario.calendario_anbima()
check('o ANBIMA vem do Holidays do app, com feriados', len(cal.feriados) > 500, True)
check('Paixao de Cristo nao e dia util', cal.eh_dia_util(date(2026, 4, 3)), False)
check('sabado nao e dia util', cal.eh_dia_util(date(2026, 4, 4)), False)
# NETWORKDAYS-1: com o inicio em dia util e o intervalo aberto a esquerda.
check('dias_uteis(d, d) e zero', cal.dias_uteis(date(2026, 4, 6), date(2026, 4, 6)), 0)
check('WORKDAY pula o feriado', cal.workday(date(2026, 4, 1), 2), date(2026, 4, 6))
sofr_cal = calendario.calendario_sofr()
check('o SOFR tem o Thanksgiving', sofr_cal.eh_dia_util(date(2026, 11, 26)), False)
bce = calendario.calendario_bce()
check('o BCE tem a Sexta-feira Santa', bce.eh_dia_util(date(2026, 4, 3)), False)
check('e o feriado frances NAO e do TARGET', bce.eh_dia_util(date(2026, 7, 14)), True)
check('a Pascoa de 2026', calendario.pascoa(2026), date(2026, 4, 5))

# A contagem e o regime sao escolhas INDEPENDENTES: o mesmo periodo vale coisas
# diferentes em cada convencao, e e essa diferenca que a tela mostra lado a lado.
d0, d1 = date(2026, 1, 2), date(2026, 7, 2)
taus = {c: round(contagem.fracao(c, d0, d1, cal), 6) for c, _n, _t in contagem.CONVENCOES}
check('DU/252 e ACT/360 dao fracoes de ano DIFERENTES',
      taus[contagem.DU_252] != taus[contagem.ACT_360], True)
check('ACT/360 sao os dias corridos sobre 360',
      round((d1 - d0).days / 360.0, 6), taus[contagem.ACT_360])
check('composto e simples so coincidem em tau=0',
      round(contagem.fator(0.14, contagem.ACT_360, contagem.COMPOSTO, d0, d1, cal), 8) !=
      round(contagem.fator(0.14, contagem.ACT_360, contagem.SIMPLES, d0, d1, cal), 8), True)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 2. o motor: CDI, SOFR e renda fixa ==')
# A janela e [inicio, fim): a taxa de um dia rende NAQUELE dia, entao o DI da
# data final nao entra. E o que faz o numero bater com a calculadora da B3.
fix = [cdi.FixingCDI(date(2026, 1, 2), 0.14), cdi.FixingCDI(date(2026, 1, 5), 0.14),
       cdi.FixingCDI(date(2026, 1, 6), 0.14)]
acc = cdi.acumular(fix, date(2026, 1, 2), date(2026, 1, 6), valor=1.0)
check('o CDI acumula [inicio, fim) — o fixing do fim fica de fora', acc.dias_uteis, 2)
esperado = ((1.14 ** (1 / 252.0)) ** 2)
check('e o fator e o produto dos fatores diarios', round(acc.fator, 12), round(esperado, 12))
# % do CDI incide na taxa DIARIA: 110% do CDI nao e a taxa anual vezes 1,10.
meio = cdi.acumular(fix, date(2026, 1, 2), date(2026, 1, 6), percentual=1.10, valor=1.0)
ingenuo = ((1.14 * 1.10) ** (2 / 252.0))
check('110% do CDI nao e a taxa anual vezes 1,10', abs(meio.fator - ingenuo) > 1e-6, True)

# SOFR: n_i sao os dias corridos ate o proximo dia util — o fixing de sexta
# remunera tres dias. A semana escolhida e limpa de proposito: 07/09/2026 e o
# Labor Day americano, e uma sexta antes dele remuneraria QUATRO.
fx = [sofr.FixingSOFR(date(2026, 9, 10), 0.036), sofr.FixingSOFR(date(2026, 9, 11), 0.036),
      sofr.FixingSOFR(date(2026, 9, 14), 0.036)]
comp = sofr.compor(fx, date(2026, 9, 10), date(2026, 9, 15), calendario=sofr_cal)
check('a sexta-feira remunera tres dias', [d.dias for d in comp.dias], [1, 3, 1])
check('e o composto sai acima do simples',
      comp.taxa_composta > 0 and comp.fator > 1.0, True)
# E o feriado entra pelo mesmo caminho: a sexta antes do Labor Day remunera 4.
fx2 = [sofr.FixingSOFR(date(2026, 9, 3), 0.036), sofr.FixingSOFR(date(2026, 9, 4), 0.036)]
comp2 = sofr.compor(fx2, date(2026, 9, 3), date(2026, 9, 8), calendario=sofr_cal)
check('a sexta antes do feriado remunera quatro', [d.dias for d in comp2.dias], [1, 4])
erro = ''
try:
    sofr.compor(fx, date(2026, 9, 10), date(2026, 9, 15), lookback=-1, calendario=sofr_cal)
except Exception as exc:
    erro = type(exc).__name__
check('lookback negativo e recusado', erro != '', True)

rf = renda_fixa.calcular(1000.0, date(2026, 1, 2), date(2026, 7, 2),
                         renda_fixa.PREFIXADO, 0.14, calendario=cal)
check('o IR de 181 a 360 dias e 20%', rf.aliquota_ir, 0.20)
check('o IOF zera depois de 30 dias', rf.aliquota_iof, 0.0)
check('e o liquido e o bruto menos o IR',
      round(rf.valor_liquido, 6), round(rf.valor_bruto - rf.ir, 6))
isento = renda_fixa.calcular(1000.0, date(2026, 1, 2), date(2026, 7, 2),
                             renda_fixa.PREFIXADO, 0.14, produto='lci', calendario=cal)
check('LCI e isenta de IR', (isento.isento, isento.ir), (True, 0.0))

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 3. o motor: a liquidacao ==')
# Fator digitado nas duas pontas: nenhuma ida a rede, e a conta fica visivel.
op, ini, fim = date(2025, 9, 1), date(2025, 9, 1), date(2026, 3, 2)


def liquidar(fa, fp, **kw):
    return liquidacao.liquidar(
        data_operacao=op, inicio=ini, fim=fim, nocional=10_000_000.0,
        ponta_ativa=liquidacao.Ponta(indexador=liquidacao.FATOR, fator_manual=fa),
        ponta_passiva=liquidacao.Ponta(indexador=liquidacao.FATOR, fator_manual=fp),
        calendario=cal, **kw)


r = liquidar(1.10, 1.05)
check('a ativa ganhando, quem recebe e a ativa', r.quem_recebe, liquidacao.ATIVA)
check('o ajuste bruto e a diferenca dos valores futuros',
      round(r.ajuste_bruto, 2), round(10_000_000.0 * (1.10 - 1.05), 2))
# A retencao e da FONTE PAGADORA: o banco so retem quando e ELE quem paga.
check('a ativa GANHANDO nao tem retencao', (r.aliquota_ir, r.ir), (0.0, 0.0))
r2 = liquidar(1.05, 1.10)
check('a ativa PERDENDO retem', r2.ir > 0, True)
check('   e o IR ENCOLHE o que sai do caixa', abs(r2.ajuste_liquido) < abs(r2.ajuste_bruto), True)
check('   com a aliquota do prazo desde a OPERACAO',
      r2.aliquota_ir, renda_fixa.aliquota_ir((fim - op).days))
check('reter_ir desligado nao retem', liquidar(1.05, 1.10, reter_ir=False).ir, 0.0)

# Fluxo que termina ANTES do vencimento e intermediario: so o diferencial de
# juros muda de maos — netar valor futuro ali cobraria um principal que ninguem
# pagou.
inter = liquidar(1.05, 1.10, vencimento=date(2027, 3, 2))
check('fluxo antes do vencimento liquida so juros', inter.so_juros, True)
final = liquidar(1.05, 1.10, vencimento=fim)
check('no vencimento liquida o valor futuro', final.so_juros, False)
check('e sem vencimento o padrao e a liquidacao final', liquidar(1.05, 1.10).so_juros, False)

# Amortizacao: os mesmos 10% valem numeros diferentes conforme a base.
sobre_orig = liquidacao.amortizar(100.0, 60.0, 0.10, liquidacao.SOBRE_ORIGINAL)
sobre_rem = liquidacao.amortizar(100.0, 60.0, 0.10, liquidacao.SOBRE_REMANESCENTE)
check('10% sobre o original x sobre o remanescente', (sobre_orig, sobre_rem), (10.0, 6.0))

# Equity e QUANTO: liquida em reais sem conversao, mesmo cotada em moeda.
eq = liquidacao.liquidar(
    data_operacao=op, inicio=ini, fim=fim, nocional=1_000_000.0,
    ponta_ativa=liquidacao.Ponta(indexador=liquidacao.EQUITY, moeda='USD', ativo='S&P 500',
                                 preco_inicial=100.0, preco_final=110.0),
    ponta_passiva=liquidacao.Ponta(indexador=liquidacao.FATOR, fator_manual=1.0),
    calendario=cal, reter_ir=False)
check('a ponta de equity nao converte cambio', eq.ativa.fator_cambial, 1.0)
check('   e rende a variacao de preco', round(eq.ativa.fator_do_indice, 6), 1.1)
check('   marcada como quanto na tela', eq.ativa.quanto, True)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 4. as bases locais: LISTA de registros, pelo funil ==')
taxas = {'2026-09-07': {'1 week': 0.0215, '3 month': 0.0266},
         '2026-09-04': {'1 week': 0.0214}}
lista = bases.para_lista(taxas, ['1 week', '1 month', '3 month'])
check('a base e uma LISTA de registros (o espelho converte em tabela)',
      isinstance(lista, list) and all(isinstance(x, dict) for x in lista), True)
check('ordenada por data, com a data no registro',
      [x['date'] for x in lista], ['2026-09-04', '2026-09-07'])
check('as colunas saem na ORDEM declarada (o banco nao a promete)',
      list(lista[1].keys()), ['date', '1 week', '3 month'])
check('e a volta e exata', bases.para_dict(lista), taxas)
check('o nome do arquivo nao tem o `_` que tira do espelho',
      [n.startswith('_') for n in ('euribor_historico.json', 'sofr_historico.json',
                                   'term_sofr_b3.json')], [False, False, False])
# O seed versionado e o que faz a instancia nova nascer com o historico.
for nome in ('euribor_historico.json', 'sofr_historico.json'):
    seed = bases.caminho_do_seed(nome)
    check('o seed de %s esta versionado' % nome, os.path.isfile(seed), True)
    if os.path.isfile(seed):
        with io.open(seed, encoding='utf-8') as fh:
            regs = json.load(fh)
        check('   e ja e a lista de registros',
              isinstance(regs, list) and 'date' in regs[0], True)
# A gravacao passa pelo funil (atomica e avisando o espelho), nunca json.dump.
src = ler('apps/pages/precificador/bases.py')
check('a base grava pelo funil _atomic_write_json', '_atomic_write_json' in src, True)
check('e nao ha json.dump solto no motor',
      [n for n in os.listdir(os.path.join(ROOT, 'apps/pages/precificador'))
       if n.endswith('.py') and 'json.dump(' in ler('apps/pages/precificador/' + n)], [])

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 5. o pre-preenchimento: a curva da posicao -> o indice da tela ==')
REGRAS = [
    {'MATCH': 'DI', 'MODE': 'Exact', 'INDEX': 'cdi'},
    {'MATCH': 'PREFIXADO 252D', 'MODE': 'Exact', 'INDEX': 'pre',
     'DAY COUNT': 'du_252', 'REGIME': 'composto'},
    {'MATCH': 'DOLAR', 'MODE': 'Contains', 'INDEX': 'cambio', 'CURRENCY': 'USD'},
    {'MATCH': 'DOLAR DOS EUA 30/360', 'MODE': 'Exact', 'INDEX': 'cambio',
     'CURRENCY': 'USD', 'DAY COUNT': '30_360'},
    {'MATCH': 'TSFR3M', 'MODE': 'Contains', 'INDEX': 'term_sofr',
     'CURRENCY': 'USD', 'TENOR': '3 month'},
    {'MATCH': 'IPCA', 'MODE': 'Contains', 'INDEX': 'ipca'},
]
cl = domain.classificar_indice
check('DI casa exato', cl(REGRAS, 'DI')['INDEX'], 'cdi')
check('PREFIXADO 252D casa exato', cl(REGRAS, 'PREFIXADO 252D')['INDEX'], 'pre')
# Exact vence Contains, e entre os Contains vence o token mais longo — senao
# `DOLAR DOS EUA 30/360` herdaria a contagem do `DOLAR` generico.
check('Exact vence Contains', cl(REGRAS, 'DOLAR DOS EUA 30/360')['DAY COUNT'], '30_360')
check('o Contains mais longo vence', cl(REGRAS, 'DOLAR DOS EUA')['CURRENCY'], 'USD')
# VCP nao e curva: a curva de verdade esta no Nome Tipo/Classe da posicao.
check('VCP cai no Nome Tipo/Classe', cl(REGRAS, 'VCP', 'TSFR3M')['INDEX'], 'term_sofr')
check('e o nome vazio tambem', cl(REGRAS, '', 'IPCA')['INDEX'], 'ipca')
# Curva sem regra devolve None — a tela deixa o indice EM BRANCO e sinalizado.
check('curva sem cadastro nao vira chute', cl(REGRAS, 'CURVA NOVA DA B3'), None)
# O Nome Tipo/Classe e a SEGUNDA pergunta, e nao so no VCP: um `Codigo indice`
# que o `swap-index` nao conhece chega aqui como o proprio codigo, que nao casa
# com nada — e desistir ali deixaria a ponta em branco tendo a curva escrita na
# coluna ao lado.
check('curva que nao casa cai no Nome Tipo/Classe', cl(REGRAS, 'C03', 'DI')['INDEX'], 'cdi')
# `INDEX` que o MOTOR nao conhece e o mesmo que indice nenhum, e sai pela MESMA
# porta: em branco e SINALIZADO. Devolvido, ele punha no `<select>` da tela um
# valor sem opcao correspondente — campo vazio, sem a nota de "nao identificou"
# (o servidor tinha respondido um indice) e sem nada explicando o branco. Foi o
# `cdi_percentual` (codigo da Renda Fixa) do primeiro seed do cadastro.
_LEGADO = [{'MATCH': 'DI', 'MODE': 'Exact', 'INDEX': 'cdi_percentual'}]
check('INDEX que o motor nao conhece sai em branco e sinalizado',
      domain.montar_ponta(cl(_LEGADO, 'DI'), 1.0, 0.008, 1.0, '', None),
      domain.montar_ponta(None, 1.0, 0.008, 1.0, '', None))
# E o `upgrade` do cadastro traduz o codigo antigo na LEITURA: seed so roda
# quando o arquivo NAO existe, entao a instancia que ja o tinha em disco nunca
# receberia a correcao do seed.
check('o upgrade traduz cdi_percentual/cdi_spread para cdi',
      [r['INDEX'] for r in R._tools_swap_index_upgrade(
          [{'INDEX': 'cdi_percentual'}, {'INDEX': 'cdi_spread'}, {'INDEX': 'pre'}])],
      ['cdi', 'cdi', 'pre'])
check('e nao inventa nada para um codigo que ele nao conhece',
      R._tools_swap_index_upgrade([{'INDEX': 'xpto'}])[0]['INDEX'], 'xpto')
check('o cadastro declara o upgrade',
      R._MAPPING_DEFS['tools-swap-index'].get('upgrade') is R._tools_swap_index_upgrade, True)
# O seed nao pode voltar a citar um indice que o motor nao tem — foi assim que
# o `cdi_percentual` chegou ao disco da instancia.
check('todo INDEX do seed e um indexador do motor',
      sorted({r['INDEX'] for r in R._MAPPING_DEFS['tools-swap-index']['seed']
              if r['INDEX'] not in liquidacao.INDEXADOR_POR_CODIGO}), [])
check('e as opcoes do select tambem',
      sorted({o for c in R._MAPPING_DEFS['tools-swap-index']['columns']
              if c['key'] == 'INDEX' for o in c['options']
              if o not in liquidacao.INDEXADOR_POR_CODIGO}), [])
check('e sem nada nas duas continua sem chute', cl(REGRAS, 'C03', 'XPTO'), None)

campos, faltando = domain.montar_ponta(None, None, None, 1.0, '', None)
check('sem regra, o indice fica vazio e sinalizado',
      (campos['indexador'], faltando), ('', ['indexador']))
# O CDI leva as DUAS colunas da posicao: o `Percentual` no percentual e a
# `Taxa` no spread. 100% do CDI + 1,07% e um contrato comum, e com dois indices
# excludentes ele entrava pela metade sem nada dizer isso.
campos, faltando = domain.montar_ponta(cl(REGRAS, 'DI'), 1.10, None, 1.0, '', None)
check('o CDI leva o PERCENTUAL no campo dele', campos['percentual'], '1.1000')
check('e sem spread o campo fica VAZIO, nao zero', campos['taxa'], '')
campos, _f = domain.montar_ponta(cl(REGRAS, 'DI'), 1.00, 0.0107, 1.0, '', None)
check('com spread, os dois convivem',
      (campos['percentual'], campos['taxa']), ('1.0000', '0.0107'))
check('e o sinal da posicao inverte o spread',
      domain.montar_ponta(cl(REGRAS, 'DI'), 1.00, 0.0107, -1.0, '', None)[0]['taxa'], '-0.0107')
campos, faltando = domain.montar_ponta(cl(REGRAS, 'PREFIXADO 252D'), None, 0.14, 1.0, '', None)
check('o pre leva a taxa e a contagem do cadastro',
      (campos['taxa'], campos['convencao'], campos['regime']),
      ('0.1400', 'du_252', 'composto'))
check('o sinal da posicao inverte a taxa',
      domain.montar_ponta(cl(REGRAS, 'PREFIXADO 252D'), None, 0.02, -1.0, '', None)[0]['taxa'],
      '-0.0200')
# A "Cupom Limpo" e a cotacao inicial do ativo, e o campo que a recebe muda com
# o indice: fixing na moeda, numero-indice no IPCA, preco no equity.
campos, _f = domain.montar_ponta(cl(REGRAS, 'DOLAR DOS EUA'), None, 0.03, 1.0, '', 5.4321)
check('na moeda, a cotacao inicial e o FIXING (as casas que tem, ate 8 — §439)', campos['ptax_inicial'], '5.4321')
campos, _f = domain.montar_ponta(cl(REGRAS, 'IPCA'), None, 0.06, 1.0, '', 7545.53)
check('no IPCA, e o NUMERO-INDICE', campos['ni_inicial'], '7545.530000')
campos, faltando = domain.montar_ponta(cl(REGRAS, 'DOLAR DOS EUA'), None, 0.03, 1.0, '', None)
check('sem cotacao na posicao, o campo fica em branco e sinalizado',
      (campos['ptax_inicial'], 'ptax_inicial' in faltando), ('', True))
check('o Term SOFR leva o prazo do cadastro',
      domain.montar_ponta(cl(REGRAS, 'TSFR3M'), None, 0.01, 1.0, '', None)[0]['tenor'], '3 month')
check('a base da amortizacao sai do texto do tipo',
      (domain.base_da_amortizacao('PERCENTUAL SOBRE O VALOR BASE'),
       domain.base_da_amortizacao('SOBRE O SALDO REMANESCENTE'),
       domain.base_da_amortizacao('QUALQUER OUTRA COISA')),
      (liquidacao.SOBRE_ORIGINAL, liquidacao.SOBRE_REMANESCENTE, None))
# `Na Data de Vencimento` tem base PROPRIA: as outras duas descrevem uma
# PARCELA, e dizer "sobre o valor original" num contrato que so amortiza no fim
# afirma um cronograma que ele nao tem. `Sem Troca` continua no original — la o
# percentual e zero e a base nao muda numero nenhum.
check('Na Data de Vencimento vira At Maturity, Sem Troca nao',
      (domain.base_da_amortizacao('NA DATA DE VENCIMENTO'),
       domain.base_da_amortizacao('SEM TROCA DE AMORTIZACAO')),
      (liquidacao.AT_MATURITY, liquidacao.SOBRE_ORIGINAL))
# A 100% as tres bases dao o mesmo numero — e por isso a escolha e sobre o que
# a tela AFIRMA, nao sobre a conta.
check('At Maturity amortiza o SALDO, nao uma fracao do original',
      (liquidacao.amortizar(10000000.0, 8000000.0, 1.0, liquidacao.AT_MATURITY),
       liquidacao.amortizar(10000000.0, 8000000.0, 0.5, liquidacao.AT_MATURITY)),
      (8000000.0, 4000000.0))
# A celula da posicao escreve a virgula como DECIMAL, sem separador de milhar.
check('a celula da posicao le a virgula como decimal',
      domain.numero_da_posicao('280000000,00'), 280000000.0)

# A tela de Term SOFR mostra a curva IMPORTADA (1, 3, 6 e 12 meses), no desenho
# da EURIBOR — e nao o overnight do NY Fed, que e a taxa REALIZADA e vive na
# tela de SOFR Index, ao lado da composicao que a acumula. Duas fontes na mesma
# pagina davam dois quadros de "valores publicados" com perguntas diferentes.
print('\n== 5b. Term SOFR: a curva importada, no desenho da EURIBOR ==')
from apps.pages.precificador import term_sofr as _ts                    # noqa: E402
term_html = ler('apps/templates/pages/tools-term-sofr.html')
idx_html = ler('apps/templates/pages/tools-sofr-index.html')
# Os ROTULOS sao montados no Python (o `campos` do contexto), entao nao estao
# no template — o que se confere aqui e a ESTRUTURA; os rotulos saem na pagina
# renderizada, na secao 9.
check('o Term SOFR itera os campos do term_sofr (tupla de tres)',
      'for campo, rotulo, _m in campos' in term_html, True)
check('e o SOFR Index os do sofr (tupla de dois)',
      'for campo, rotulo in pb.campos' in idx_html, True)
check('cada tela tem UM quadro de valores publicados',
      (term_html.count('tl-published-values'), idx_html.count('tl-published-values')), (1, 0))
check('a dropzone continua na tela do Term SOFR', 'tl-drop' in term_html, True)
# Base vazia nao e erro: e quem ainda nao importou, e a tela diz isso.
check('base vazia aponta para a importacao', 'tl-term-empty' in term_html, True)
# A ORDEM dos prazos e a do CAMPOS, nao a do dicionario: 12 meses depois de 6.
check('os prazos saem em ordem de vencimento',
      [m for _c, _r, m in _ts.CAMPOS], [1, 3, 6, 12])

# A taxa a termo vem da BASE, e a pergunta e UMA para os dois indices: que taxa
# o contrato fixou naquele prazo, naquele dia. Dois endpoints seriam duas
# respostas para divergir no primeiro caso de borda.
print('\n== 5c. o fixing de Term SOFR e EURIBOR sai da base ==')
from datetime import date as _d                                         # noqa: E402
_quando = _d(2026, 9, 4)
_tx, _vig, _mot = queries.taxa_do_fixing(liquidacao.EURIBOR, '3 month', _quando)
check('a EURIBOR responde da base local', (_tx is not None, _mot), (True, ''))
check('e o prazo de 1 semana tambem — que nao cabe num numero de meses',
      queries.taxa_do_fixing(liquidacao.EURIBOR, '1 week', _quando)[0] is not None, True)
check('prazo que a base nao tem volta com o MOTIVO, nao com zero',
      queries.taxa_do_fixing(liquidacao.EURIBOR, '99 month', _quando)[0], None)
# O Term SOFR e licenciado: sem importacao a base esta vazia, e a resposta tem
# de dizer o que fazer — nao um numero inventado nem um 500.
_tx, _v, _mot = queries.taxa_do_fixing(liquidacao.TERM_SOFR, '3 month', _quando)
if _tx is None:
    check('Term SOFR sem importacao diz o remedio', 'Term SOFR' in _mot, True)
# O atalho antigo delega — duas implementacoes da mesma consulta divergiriam.
_src = ler('apps/pages/features/tools/queries.py')
check('o term_sofr_taxa delega ao taxa_do_fixing',
      'taxa, vigente, _motivo = taxa_do_fixing(' in _src, True)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 6. o prefill pelo B3 ID, sobre uma posicao sintetica ==')
_b3_root, _otm_root = R.B3_JSON_ROOT, R.OTM_JSON_ROOT
_map_rows = R._mapping_rows
try:
    R.B3_JSON_ROOT = os.path.join(TMP, 'b3')
    R._mapping_rows = lambda key: REGRAS if key == 'tools-swap-index' else _map_rows(key)
    ref = R._prev_anbima_bizday(datetime.now()).date()
    dref = ref.strftime('%y%m%d')
    pasta = os.path.join(R.B3_JSON_ROOT, 'Swap', R._b3_date_subpath(dref))
    os.makedirs(pasta, exist_ok=True)
    # 170 campos NA ORDEM do layout da B3 — a leitura e POSICIONAL, e e por isso
    # que a primeira e a segunda coluna de mesmo nome sao as duas pontas.
    vals = [''] * 170
    vals[2] = '26G53382860'                     # Contrato
    vals[7] = '73760205'                        # Contraparte (conta)
    vals[8] = '12345678000199'                  # CPF/CNPJ Contraparte
    vals[11] = '01/09/2025'                     # Data inicio
    vals[12] = '02/03/2027'                     # Data vencimento
    vals[14] = '10000000,00'                    # Valor base
    vals[15] = '8000000,00'                     # Valor Base Remanescente
    vals[24] = '10000000,00'                    # Valor base inicial
    vals[38] = '01 (PERCENTUAL SOBRE O VALOR BASE)'
    vals[39], vals[40], vals[42], vals[43] = '', 'C99', '0', '0,14'   # ponta 1: PRE 252
    vals[49], vals[50], vals[52], vals[53] = '1,10', 'C03', '0', ''   # ponta 2: DI
    vals[145] = 'CEM-2026-0001'                 # Codigo Identificador

    def _grava_pos():
        with io.open(os.path.join(pasta, '73760_%s_DPOSICAO-SWAP.json' % dref),
                     'w', encoding='utf-8') as fh:
            fh.write(json.dumps([{('c%03d' % i): v for i, v in enumerate(vals)}],
                                ensure_ascii=False))

    _grava_pos()

    d = queries.swap_prefill('26G53382860')
    check('acha pelo Contrato', d['found'], True)
    check('e tambem pelo Codigo Identificador',
          queries.swap_prefill('CEM-2026-0001')['found'], True)
    check('B3 ID desconhecido nao inventa nada',
          queries.swap_prefill('NAO-EXISTE')['found'], False)
    f = d['fields']
    check('o vencimento vem da posicao', f['vencimento'], '2027-03-02')
    check('o notional e o REMANESCENTE (o que de fato rende)', f['nocional'], '8000000.00')
    check('e o original fica ao lado', f['nocional_original'], '10000000.00')
    check('a base da amortizacao sai do tipo', f['base_amortizacao'], liquidacao.SOBRE_ORIGINAL)
    # A data da operacao e a `Data operacao termo` da posicao. Em branco — o
    # swap que nao e a termo — a de inicio responde por ela, e vai marcada como
    # aproximacao: assumir calado seria errar o prazo do IR.
    check('sem Data operacao termo, a data da operacao vem do inicio, ASSUMIDA',
          (f['data_operacao'], 'data_operacao' in d['assumed']), ('2025-09-01', True))
    check('a ponta ativa e o PRE da primeira coluna',
          (d['ativa']['indexador'], d['ativa']['taxa']), ('pre', '0.1400'))
    check('a passiva e o DI da segunda, com o percentual',
          (d['passiva']['indexador'], d['passiva']['percentual']), ('cdi', '1.1000'))
    # Sem Reference Data no tmp a contraparte nao resolve — e isso e SINALIZADO,
    # nunca preenchido com a conta crua.
    check('contraparte que nao resolve fica em branco e sinalizada',
          (f['counterparty'], 'counterparty' in d['missing']), ('', True))
    # Sem DFLUXO o fim cai em HOJE e vai marcado como ASSUMIDO — um campo de
    # data vazio nao deixa a tela nem abrir a conta, e assumir calado seria
    # pior. O inicio cai na data de inicio do swap, que a posicao tem.
    check('sem DFLUXO, o fim e hoje e vai assumido',
          (d['fields']['fim'], 'fim' in d['assumed'], 'fim' in d['missing']),
          (date.today().isoformat(), True, False))
    check('e o inicio cai no comeco do swap', d['fields']['inicio'], '2025-09-01')
    # O `Tipo de Contrato` decide o que liquida: bullet so tem o pagamento
    # final; cashflow deixa as DATAS decidirem (o `auto` do motor).
    check('sem Tipo de Contrato, o que liquida fica no automatico',
          d['fields']['base_ajuste'], liquidacao.BASE_AUTOMATICA)
    check('nenhum campo do prefill volta com valor inventado',
          [c for c in queries.CAMPOS_PREFILL
           if c in d['missing'] and str(f.get(c) or '') != ''], [])

    # Bullet: so o pagamento final, e nada a amortizar no meio do caminho.
    vals[0] = '02'
    with io.open(os.path.join(pasta, '73760_%s_DPOSICAO-SWAP.json' % dref),
                 'w', encoding='utf-8') as fh:
        fh.write(json.dumps([{('c%03d' % i): v for i, v in enumerate(vals)}], ensure_ascii=False))
    b = queries.swap_prefill('26G53382860')
    check('bullet liquida pelo VALOR FUTURO',
          (b['tipo_contrato'], b['fields']['base_ajuste']),
          ('Bullet', liquidacao.BASE_VALOR_FUTURO))
    # O bullet nao tem fluxo intermediario: o unico fluxo dele termina no
    # VENCIMENTO, que esta na posicao. Terminando em HOJE, a conta saia de um
    # contrato no meio do caminho — e ainda marcada como assumida, com a data
    # na coluna ao lado.
    check('o fluxo do bullet termina no VENCIMENTO, e nao e aproximacao',
          (b['fields']['fim'], 'fim' in b['assumed'], 'fim' in b['missing']),
          ('2027-03-02', False, False))
    # E o que termina no vencimento amortiza 100%: o principal inteiro volta.
    # A coluna `Tipo de amortizacao` esta VAZIA aqui, e vazia e At Maturity —
    # nao e lacuna. A base nao muda nada a 100% (`amortizar` devolve o saldo
    # pelos dois caminhos), entao ela cai no original em vez de pedir cadastro.
    check('bullet amortiza 100% no vencimento',
          (b['fields']['amortizacao'], 'amortizacao' in b['missing']), ('100', False))
    check('com a coluna preenchida, a base e a que ela diz',
          (b['fields']['base_amortizacao'], 'base_amortizacao' in b['missing']),
          (liquidacao.SOBRE_ORIGINAL, False))
    # Coluna VAZIA e At Maturity — nao lacuna, e nao o original: o dropdown da
    # tela tem a opcao propria justamente para o bullet nao sair afirmando um
    # cronograma de parcelas.
    _guardado = vals[38]
    vals[38] = ''
    with io.open(os.path.join(pasta, '73760_%s_DPOSICAO-SWAP.json' % dref),
                 'w', encoding='utf-8') as fh:
        fh.write(json.dumps([{('c%03d' % i): v for i, v in enumerate(vals)}], ensure_ascii=False))
    _vaz = queries.swap_prefill('26G53382860')['fields']
    check('coluna de amortizacao vazia e At Maturity, nao lacuna',
          (_vaz['base_amortizacao'], _vaz['amortizacao']),
          (liquidacao.AT_MATURITY, '100'))
    vals[38] = _guardado
    with io.open(os.path.join(pasta, '73760_%s_DPOSICAO-SWAP.json' % dref),
                 'w', encoding='utf-8') as fh:
        fh.write(json.dumps([{('c%03d' % i): v for i, v in enumerate(vals)}], ensure_ascii=False))
    check('a 100% as duas bases dao o mesmo — por isso a base nao e cobrada',
          (liquidacao.amortizar(10000000.0, 8000000.0, 1.0, liquidacao.SOBRE_ORIGINAL),
           liquidacao.amortizar(10000000.0, 8000000.0, 1.0, liquidacao.SOBRE_REMANESCENTE)),
          (8000000.0, 8000000.0))
    vals[0] = '01'
    with io.open(os.path.join(pasta, '73760_%s_DPOSICAO-SWAP.json' % dref),
                 'w', encoding='utf-8') as fh:
        fh.write(json.dumps([{('c%03d' % i): v for i, v in enumerate(vals)}], ensure_ascii=False))
    c2 = queries.swap_prefill('26G53382860')
    check('cashflow deixa as datas decidirem',
          (c2['tipo_contrato'], c2['fields']['base_ajuste']),
          ('Cashflow', liquidacao.BASE_AUTOMATICA))
    # Cashflow sem DFLUXO e lacuna de verdade: o fluxo que liquidou nao esta em
    # lugar nenhum, e a regra do bullet nao pode cobrir isso — ali o vencimento
    # E o fim do fluxo, aqui nao se sabe qual fluxo era.
    check('cashflow sem DFLUXO continua lacuna, nao 100% no vencimento',
          (c2['fields']['fim'], 'fim' in c2['assumed'],
           c2['fields']['amortizacao'], 'amortizacao' in c2['missing']),
          (date.today().isoformat(), True, '', True))

    # `Data operacao termo` preenchida VENCE a data de inicio: e a data de
    # contratacao de verdade, e ai nao ha aproximacao nenhuma a sinalizar.
    vals[25] = '26/10/2017'                     # Data operacao termo
    _grava_pos()
    dt_ = queries.swap_prefill('26G53382860')
    check('com Data operacao termo, e ELA a data da operacao',
          (dt_['fields']['data_operacao'], 'data_operacao' in dt_['assumed'],
           'data_operacao' in dt_['missing']), ('2017-10-26', False, False))
    vals[25] = ''
    _grava_pos()

    # O DFLUXO. O PRIMEIRO fluxo abre na `Data inicio` do swap: nao ha evento
    # anterior de onde partir, e o `inicio` do proprio evento no DFLUXO nem
    # sempre e essa data (aqui, de proposito, e 15/09). Do segundo em diante, o
    # fluxo abre onde o anterior fechou.
    def _grava_fluxo(*linhas):
        with io.open(os.path.join(pasta, '73760_%s_DFLUXO.json' % dref), 'w', encoding='utf-8') as fh:
            fh.write(json.dumps([{('c%03d' % i): v for i, v in enumerate(x)} for x in linhas],
                                ensure_ascii=False))

    ontem = (date.today() - timedelta(days=1)).strftime('%d/%m/%Y')
    amanha = (date.today() + timedelta(days=400)).strftime('%d/%m/%Y')
    fl = [''] * 30
    fl[0], fl[10], fl[8] = '26G53382860', 'CEM-2026-0001', '01'
    fl[22], fl[23], fl[11], fl[16] = '15/09/2025', ontem, ontem, '10,0000'
    fl2 = list(fl)
    fl2[22], fl2[23], fl2[11], fl2[16] = ontem, amanha, amanha, '20,0000'

    _grava_fluxo(fl, fl2)                     # so o primeiro evento ja ocorreu
    pr = queries.swap_prefill('26G53382860')
    check('o primeiro fluxo abre na Data inicio do swap, nao no inicio do evento',
          (pr['fields']['inicio'], pr['fields']['fim']),
          ('2025-09-01', (date.today() - timedelta(days=1)).isoformat()))
    fl[11] = (date.today() - timedelta(days=40)).strftime('%d/%m/%Y')
    fl2[11] = ontem                           # o segundo tambem ja ocorreu
    _grava_fluxo(fl, fl2)
    check('e o seguinte abre onde o anterior fechou',
          (queries.swap_prefill('CEM-2026-0001')['fields']['inicio'],
           queries.swap_prefill('CEM-2026-0001')['fields']['fim']),
          ((date.today() - timedelta(days=40)).isoformat(),
           (date.today() - timedelta(days=1)).isoformat()))
    # Um periodo que ABRE no dia em que FECHA nao e um periodo: ele liquida com
    # juros zero e nao acusa erro nenhum. Quando o DFLUXO repete a data do
    # evento (mais de um lancamento no dia) ou carimba a composicao da taxa com
    # a propria data do evento, o candidato e DESCARTADO e a busca continua.
    fl3 = list(fl2)
    fl3[22], fl3[16] = ontem, '30,0000'       # composicao "comecando" no fim
    _grava_fluxo(fl, fl2, fl3)
    _deg = queries.swap_prefill('CEM-2026-0001')['fields']
    check('flow start nunca sai igual ao flow end',
          (_deg['inicio'] != _deg['fim'], _deg['inicio']),
          (True, (date.today() - timedelta(days=40)).isoformat()))
    # A regra do periodo e UMA: o servidor manda o periodo de CADA evento
    # (`p_inicio`/`p_fim`), e o seletor da tela so le. Montada tambem no
    # navegador, trocar de evento dava outra resposta que abrir nele.
    _fl = queries.swap_prefill('CEM-2026-0001')['flows']
    check('cada evento leva o proprio periodo calculado',
          all(('p_inicio' in x and 'p_fim' in x and 'p_amort' in x
               and 'p_base_amort' in x) for x in _fl), True)
    check('e nenhum deles abre onde fecha',
          [x for x in _fl if x['p_inicio'] and x['p_inicio'] >= x['p_fim']], [])
    # O `Codigo Identificador` PARECE chave e nao e: na instancia ele guarda a
    # LOB (`CEM`) em toda operacao da mesa. Aceito ao lado do contrato, ele
    # trazia para o fluxo de UM swap os eventos de todos os outros — e o
    # sintoma nao era tela vazia: o "ultimo evento ate hoje" virava o de outro
    # contrato e o "anterior" tinha a MESMA data, com o Flow start saindo igual
    # ao Flow end.
    alheio = [''] * 30
    alheio[0], alheio[10], alheio[8] = '99Z99999999', 'CEM-2026-0001', '01'
    alheio[22], alheio[23], alheio[11], alheio[16] = ontem, ontem, ontem, '90,0000'
    _grava_fluxo(fl, fl2, alheio)
    _lob = queries.swap_prefill('26G53382860')
    check('fluxo de OUTRO contrato com o mesmo identificador fica de fora',
          ([x['evento'] for x in _lob['flows']],
           _lob['fields']['inicio'], _lob['fields']['fim']),
          ([(date.today() - timedelta(days=40)).isoformat(),
            (date.today() - timedelta(days=1)).isoformat()],
           (date.today() - timedelta(days=40)).isoformat(),
           (date.today() - timedelta(days=1)).isoformat()))
    # O identificador so responde onde nao ha contrato — nos DOIS lados. Com a
    # posicao trazendo contrato, uma linha de DFLUXO sem contrato nao entra:
    # o `CEM` dela nao diz de que swap ela e.
    sem_contrato = list(fl2)
    sem_contrato[0] = ''
    _grava_fluxo(fl, sem_contrato)
    check('linha de DFLUXO sem contrato nao entra pelo identificador da LOB',
          [x['evento'] for x in queries.swap_prefill('26G53382860')['flows']],
          [(date.today() - timedelta(days=40)).isoformat()])
    os.remove(os.path.join(pasta, '73760_%s_DFLUXO.json' % dref))

    # A janela de dez dias uteis do `_swap_day_path` e um TETO, e o que esta
    # atras dele nao e "sem posicao": e a ultima posicao que a mesa tem. Com a
    # rotina de save parada por semanas, o B3 ID respondia *not found*, que se
    # le como "esse swap nao existe". Aqui a posicao do D-1 sai de cena e a
    # unica que resta e de 40 dias atras — bem alem do teto.
    velho = ref - timedelta(days=40)
    dref_velho = velho.strftime('%y%m%d')
    pasta_velha = os.path.join(R.B3_JSON_ROOT, 'Swap', R._b3_date_subpath(dref_velho))
    os.makedirs(pasta_velha, exist_ok=True)
    with io.open(os.path.join(pasta_velha, '73760_%s_DPOSICAO-SWAP.json' % dref_velho),
                 'w', encoding='utf-8') as fh:
        fh.write(json.dumps([{('c%03d' % i): v for i, v in enumerate(vals)}],
                            ensure_ascii=False))
    os.rename(os.path.join(pasta, '73760_%s_DPOSICAO-SWAP.json' % dref),
              os.path.join(pasta, 'guardado.json'))
    _alem = queries.swap_prefill('26G53382860')
    check('passado o teto de dez dias uteis, acha a ultima posicao que existe',
          (_alem['found'], _alem.get('source_date')), (True, velho.isoformat()))
    # E nada ADIANTE do D-1 entra pela segunda porta: o arquivo de hoje ficaria
    # de fora da janela e dentro da varredura, e a mesma consulta responderia
    # duas coisas conforme a porta.
    hoje_dref = date.today().strftime('%y%m%d')
    pasta_hoje = os.path.join(R.B3_JSON_ROOT, 'Swap', R._b3_date_subpath(hoje_dref))
    os.makedirs(pasta_hoje, exist_ok=True)
    with io.open(os.path.join(pasta_hoje, '73760_%s_DPOSICAO-SWAP.json' % hoje_dref),
                 'w', encoding='utf-8') as fh:
        fh.write(json.dumps([{('c%03d' % i): v for i, v in enumerate(vals)}],
                            ensure_ascii=False))
    check('a varredura nao anda para a frente do D-1',
          queries.swap_prefill('26G53382860').get('source_date'), velho.isoformat())
    shutil.rmtree(pasta_hoje)
    shutil.rmtree(pasta_velha)
    os.rename(os.path.join(pasta, 'guardado.json'),
              os.path.join(pasta, '73760_%s_DPOSICAO-SWAP.json' % dref))

    # O DFLUXO e procurado a partir do dia da POSICAO, nao do D-1: cada um
    # andando para tras por conta propria para em dias diferentes, e o fluxo de
    # ontem contra a posicao da semana passada nao da erro nenhum — da um
    # periodo que nao e o daquele saldo.
    _fx_src = ler('apps/pages/features/tools/queries.py')
    check('o DFLUXO e ancorado no dia da posicao',
          ("_fluxos_do_contrato(contrato, ident, _data_iso(source_date))" in _fx_src and
           "_swap_day_file('73760_{}_DFLUXO.json', ref=dia_posicao)" in _fx_src), True)

    # O navegador nao remonta o periodo: ele LE o `p_*` que veio do servidor.
    _js = ler('apps/static/js/pages/tools.js')
    check('o applyFlow do tools.js so le o periodo do servidor',
          ("setVal('inicio', flow.p_inicio" in _js,
           'prev ? prev.evento' in _js), (True, False))
    # Clicar num campo seleciona o valor inteiro — e o `focus` sozinho nao
    # resolve o clique de mouse, porque o cursor e posicionado no `mouseup`.
    check('a selecao do valor inteiro e refeita no mouseup',
          ("page.addEventListener('mouseup'" in _js and
           'el.selectionStart !== el.selectionEnd' in _js), True)

    # ── 7. Swap Athena: o Edit do CETIP ID ──────────────────────────────────
    print('\n== 7. Swap Athena: Edit do CETIP ID ==')
    R.OTM_JSON_ROOT = os.path.join(TMP, 'ds')
    dia = datetime(2026, 9, 8)
    jp = R._ds_display_json_path(dia, 'br-onshore-settlements')
    os.makedirs(os.path.dirname(jp), exist_ok=True)
    base_rows = [{'CETIP ID': '26E04610365', 'Kapital ID': '0507050023684', 'SPN': '5685845'},
                 {'CETIP ID': '21B00653221', 'Kapital ID': '0500070009249', 'SPN': '0249556'}]
    with io.open(jp, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(base_rows, ensure_ascii=False))

    payload, status = R._athena_edit_cetip_id(dia, '0500070009249', '21B00653221', '21B00999999')
    check('a troca responde 200', (payload['success'], status), (True, 200))
    with io.open(jp, encoding='utf-8') as fh:
        depois = json.load(fh)
    check('a linha do Kapital ID pedido mudou', depois[1]['CETIP ID'], '21B00999999')
    check('e a OUTRA linha ficou intacta', depois[0]['CETIP ID'], '26E04610365')
    # O CETIP ID e o que esta sendo corrigido: chavear por ele deixaria a linha
    # sem chave assim que a primeira edicao entrasse.
    check('a chave e o Kapital ID, nao o CETIP ID',
          R._athena_edit_cetip_id(dia, '0500070009249', 'QUALQUER', 'X1')[1], 200)
    check('Kapital ID inexistente e 404',
          R._athena_edit_cetip_id(dia, 'NAO-EXISTE', '', 'X')[1], 404)
    check('valor vazio e 400', R._athena_edit_cetip_id(dia, '0500070009249', '', '  ')[1], 400)
    check('dia sem arquivo e 404',
          R._athena_edit_cetip_id(datetime(2026, 1, 2), '0500070009249', '', 'X')[1], 404)
finally:
    R.B3_JSON_ROOT, R.OTM_JSON_ROOT = _b3_root, _otm_root
    R._mapping_rows = _map_rows

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 8. a mensageria: a classe do ativo no assunto ==')
from apps.pages import otc_emails                                       # noqa: E402

ASSET = [{'MATCH': 'TAXA DE CAMBIO', 'LABEL': 'Moeda'},
         {'MATCH': 'COMMODITIES', 'LABEL': 'Mercadoria'},
         {'MATCH': 'COMM', 'LABEL': 'Mercadoria'},
         {'MATCH': 'ACOES', 'LABEL': 'Equities'}]
_map_rows = R._mapping_rows
try:
    R._mapping_rows = lambda key: ASSET if key == 'opb3-msg-asset' else _map_rows(key)
    rot = R._opb3_msg_asset_label
    check('a classe do TER de moeda', rot('TAXA DE CAMBIO'), 'Moeda')
    check('a de commodities', rot('COMMODITIES'), 'Mercadoria')
    check('e a de acoes', rot('ACOES'), 'Equities')
    check('cego a caixa e acento', rot('Taxa de Câmbio'), 'Moeda')
    # O token mais LONGO vence: `COMMODITIES` contem `COMM`, e o de tres letras
    # roubaria a linha da mercadoria se a ordem do arquivo decidisse.
    check('entre dois que casam vence o mais longo', rot('COMMODITIES'), 'Mercadoria')
    check('o LOB do swap tambem casa', rot('CEMCOMM-2026-9243'), 'Mercadoria')
    # Sem linha, sem rotulo: o assunto fica como sempre foi.
    check('token sem cadastro nao poe rotulo', rot('LOB QUE NINGUEM CADASTROU'), '')
    check('e o tipo vazio tambem', rot(''), '')


    def assunto(asset=''):
        return otc_emails.build_opb3_mensageria_email({
            'tipo': 'CEM', 'tipo_titulo': 'TER', 'tipo_operacao': 'RESGATE',
            'cpty': 'SUZANO SA', 'ref_date': '08/09/2026', 'rows': [], 'total': 100.0,
            'internal': None, 'to': 'a@b', 'cc': '', 'asset_label': asset})['subject']

    check('o assunto ganha a classe entre parenteses', assunto('Moeda'),
          'Vencimento de Termo (Moeda) - Liquidação Banco x SUZANO SA - 08/09/2026')
    check('a de mercadoria idem', assunto('Mercadoria'),
          'Vencimento de Termo (Mercadoria) - Liquidação Banco x SUZANO SA - 08/09/2026')
    # Sem rotulo o assunto e o de SEMPRE — a mudanca e aditiva.
    check('sem rotulo, o assunto historico intacto', assunto(),
          'Vencimento de Termo - Liquidação Banco x SUZANO SA - 08/09/2026')
finally:
    R._mapping_rows = _map_rows

# O agrupamento chama a funcao do platform, e nao um segundo teste sobre o Type.
ent = ler('apps/pages/features/operations_b3/entrypoint.py')
check('a mensageria pede o rotulo ao platform', '_opb3_msg_asset_label' in ent, True)
check('e a funcao existe uma vez so',
      ler('apps/pages/platform/operations_b3.py').count('def _opb3_msg_asset_label'), 1)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 9. a casca: rotas, menu e padrao de tela ==')
from apps import create_app                                            # noqa: E402
from apps.config import DebugConfig                                    # noqa: E402

app = create_app(DebugConfig)
regras = {str(r) for r in app.url_map.iter_rules()}
for rota in ('/tools/fixed-income', '/tools/swap-calculator', '/tools/sofr-index',
             '/tools/term-sofr', '/tools/euribor', '/tools/term-sofr/csv',
             '/tools/euribor/csv', '/api/tools/swap-calculator/prefill',
             '/api/tools/term-sofr/import', '/api/tools/term-sofr/rate',
             '/api/tools/fixing-rate', '/tools/sofr-index/csv',
             '/api/tools/term-sofr/sync', '/api/tools/euribor', '/api/tools/euribor/sync',
             '/api/other-products-swap-athena/edit'):
    check('%s registrada' % rota, rota in regras, True)

nav = ler('apps/templates/partials/sidenav.html')
import re                                                              # noqa: E402
filhas = re.findall(r'href="(/quotes|/tools/[a-z-]+)"', nav)
check('o Tools tem o Quotes e as cinco ferramentas, nesta ordem', filhas,
      ['/quotes', '/tools/fixed-income', '/tools/swap-calculator', '/tools/sofr-index',
       '/tools/term-sofr', '/tools/euribor'])
check('o item pai traduz por data-lang', 'data-lang="tools"' in nav, True)
# O Page_Access enxerga o que tem href + class="side-nav-link": as filhas
# precisam ser concediveis uma a uma.
from apps.pages.platform import authz                                  # noqa: E402
check('as cinco entram na allowlist do Page_Access',
      sorted(u for u in authz._load_nav_urls() if u.startswith('/tools/')),
      ['/tools/euribor', '/tools/fixed-income', '/tools/sofr-index',
       '/tools/swap-calculator', '/tools/term-sofr'])

TELAS = ['tools-fixed-income', 'tools-swap-calculator', 'tools-sofr-index',
         'tools-term-sofr', 'tools-euribor']
for t in TELAS:
    html = ler('apps/templates/pages/%s.html' % t)
    # `.card` do tema vence a regra da pagina sem !important (§7) — widget proprio.
    check('%s: widget proprio, nao .card' % t, 'class="card' in html, False)
    # O campo nativo desenha no locale do SISTEMA: no Windows do JP, mm/dd/yyyy.
    check('%s: nenhum type="date" visivel' % t, 'type="date"' in html, False)
    check('%s: carrega o SweetAlert LOCAL' % t,
          'plugins/sweetalert2/sweetalert2.min.js' in html or
          'tools-assets-js.html' in html, True)

# Os rotulos, na pagina RENDERIZADA — o template so itera o contexto.
import datetime as _dt                                                 # noqa: E402
_c = app.test_client()
with _c.session_transaction() as _s:
    _s.update(authenticated=True, user_sid='X1', user_name='t', user_role='ADMIN',
              # UTC, nao o relogio local: com o horario de Brasilia o app le a
              # sessao como VENCIDA e devolve a tela de login — o que se
              # confere aqui sumiria sem nada dizer que foi o fuso.
              session_expires_at=(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
                                  + _dt.timedelta(hours=1)).isoformat())
from apps.pages.precificador import euribor as _eu, sofr as _sf         # noqa: E402
_sf._ultima_sync['quando'] = 1e12                                       # zero rede no teste
_eu._ultima_sync['quando'] = 1e12
_term = _c.get('/tools/term-sofr').data.decode()
_idx = _c.get('/tools/sofr-index').data.decode()
check('a tela de Term SOFR nao traz o overnight do Fed', 'SOFR overnight' in _term, False)
check('e a de SOFR Index traz', 'SOFR overnight' in _idx, True)
# Com a base vazia (a dev nao importa nada) a tela pede a importacao em vez de
# mostrar um quadro vazio — e ainda assim oferece a dropzone.
if 'tl-term-empty' in _term:
    check('base vazia: a tela pede o arquivo e mantem a dropzone',
          ('tl-drop' in _term, 'tl-published-values' in _term), (True, False))
else:
    check('com base, os quatro prazos aparecem',
          [r for _cc, r, _m in _ts.CAMPOS if r not in _term], [])

js = ler('apps/templates/partials/tools-assets-js.html')
# Sem esta linha todo plugin dali para baixo morre com `jQuery is not defined`,
# e a pagina abre sem tabela nenhuma.
check('o jQuery vem ANTES do DataTables',
      js.index('plugins/jquery/jquery.min.js') < js.index('dataTables.min.js'), True)
check('o SweetAlert e o LOCAL (a instancia roda sem internet)',
      'plugins/sweetalert2/sweetalert2.min.js' in js, True)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 10. i18n: todo texto visivel nos tres idiomas ==')
trad = {n: json.loads(ler('apps/static/data/translations/%s.json' % n))
        for n in ('en', 'br', 'es')}
chaves = set()
for t in TELAS:
    chaves.update(re.findall(r'data-lang="(tl-[^"{]+)"', ler('apps/templates/pages/%s.html' % t)))
chaves.update(re.findall(r'data-lang="(tl-[^"{]+|tools)"', nav))
# As chaves DINAMICAS (o codigo do indice, da contagem, do regime) — a tela
# monta `tl-idx-<codigo>`, e um codigo novo sem entrada apareceria cru.
chaves.update('tl-idx-' + c for c, _n in liquidacao.INDEXADORES)
chaves.update('tl-dc-' + c for c, _n, _t in contagem.CONVENCOES)
chaves.update('tl-reg-' + c for c, _n in contagem.REGIMES)
chaves.update('tl-ba-' + c for c, _n in liquidacao.BASES_DE_AJUSTE)
chaves.update('tl-am-' + c for c, _n in liquidacao.BASES_AMORTIZACAO)
chaves.update('tl-rf-i-' + c for c, _n in renda_fixa.INDEXADORES)
for idioma, d in trad.items():
    check('nenhuma chave das Tools falta no %s' % idioma,
          sorted(k for k in chaves if k not in d), [])
# A igualdade das chaves e cobrada SO no conjunto das Tools: os tres arquivos
# divergem em ~8 chaves do tema comprado desde antes disto, e transformar essa
# divergencia herdada numa falha aqui faria este guarda reprovar por um motivo
# que ele nao mede.
for idioma in ('br', 'es'):
    check('as chaves das Tools sao as MESMAS em en e %s' % idioma,
          sorted(k for k in trad['en'] if (k.startswith('tl-') or k == 'tools')
                 and k not in trad[idioma]), [])
check('e nenhuma sobra so no %s' % 'br/es',
      sorted(k for d in (trad['br'], trad['es']) for k in d
             if (k.startswith('tl-') or k == 'tools') and k not in trad['en']), [])

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 11. o fixing de moeda considera ate 8 casas (§439) ==')
# O blur da tela reescrevia o campo com 4 casas (`data-format="price"`) e o
# prefill vinha com 6: o calculo recebia a cotacao arredondada sem aviso.
from apps.pages.features.tools import domain as _dom, entrypoint as _ep
check('fx8: 8 casas ficam inteiras', _dom.fx8(5.12345678), '5.12345678')
check('fx8: a PTAX de 4 casas nao ganha zero', _dom.fx8(5.1253), '5.1253')
check('fx8: curta sobe ao piso de 4', _dom.fx8(5.1), '5.1000')
check('fx8: 6 casas ficam 6', _dom.fx8(5.123456), '5.123456')
check('o filtro tl_fx e o mesmo formatador', (_ep.tl_fx(5.12345678), _ep.tl_fx(None)), ('5.12345678', '—'))
_ponta = _dom.ponta_do_form({'ativa_indexador': 'cambio', 'ativa_taxa': '5', 'ativa_moeda': 'USD',
                             'ativa_ptax_inicial': '5.12345678', 'ativa_ptax_final': '5,87654321'}, 'ativa')
check('o form entrega as 8 casas ao calculo, com ponto ou virgula',
      (_ponta.ptax_inicial, _ponta.ptax_final), (5.12345678, 5.87654321))
_html = ler('apps/templates/pages/tools-swap-calculator.html')
check('os dois fixings de moeda usam o formato fx',
      _html.count('_ptax_inicial" name="{{ lado }}_ptax_inicial" value="{{ f[lado ~ \'_ptax_inicial\'] }}" inputmode="decimal" data-format="fx"')
      + _html.count('_ptax_final" name="{{ lado }}_ptax_final" value="{{ f[lado ~ \'_ptax_final\'] }}" inputmode="decimal" data-format="fx"'), 2)
check('e o resultado mostra as casas que o fixing tem', 'p.ptax_inicial | tl_fx' in _html, True)
_js = ler('apps/static/js/pages/tools.js')
check('o JS formata fx com 4 a 8 casas, sem arredondar a 4', 'fx: { min: 4, max: 8 }' in _js, True)
check('nenhum prefill de fixing sobra com 6 casas fixas',
      "'{:.6f}'.format(cotacao_inicial)\n" in ler('apps/pages/features/tools/domain.py').split("campos['ptax_inicial']")[1][:60], False)

print()
print('FALHAS: %d' % len(falhas) if falhas else 'TUDO OK')
sys.exit(1 if falhas else 0)
