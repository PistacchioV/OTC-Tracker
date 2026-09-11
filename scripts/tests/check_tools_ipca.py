# -*- coding: utf-8 -*-
"""check_tools_ipca.py — o fixing M-1/M-2 da perna IPCA do Swap Calculator
(HANDOFF §449) e o 0% do fluxo sem Taxa Amortização no pré-preenchimento.

O que se prende, e por que cada coisa não daria erro sozinha:

  1. o MÊS do fixing: M-1 é o mês anterior à data (liquidação do fluxo),
     M-2 o segundo anterior — inclusive virando o ano (fev → dez/jan);
  2. a leitura da resposta do IBGE (tabela 1737, variável 2266): a chave é
     AAAAMM, o valor vem como texto, e mês não publicado simplesmente NÃO vem
     — o motor diz o mês que falta, nunca inventa um índice;
  3. a perna IPCA com fixing busca o número FINAL (M-n contado do fim do
     fluxo); o inicial é o do CONTRATO quando digitado (a cotação inicial da
     posição) e só cai para o IBGE em branco; a correção fica no PRINCIPAL e
     só o cupom é juros — os números da planilha da mesa (VIBRA) batem;
  4. o memo: o que o IBGE já publicou não é pedido de novo;
  5. o form: o campo `<lado>_ipca_fixing` entra na Ponta e valor estranho é
     erro de formulário, não fixing presumido; a tela devolve os números
     buscados aos campos e a nota dos meses;
  6. o pré-preenchimento: evento do DFLUXO sem Taxa Amortização é 0%, não
     lacuna (a célula em branco é o fluxo que só paga juros).

Nada sai da máquina: a rede é um stub e o resultado é conferido no número.
"""
import os
import sys
from datetime import date

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


from apps.pages.precificador import ipca, liquidacao, rede            # noqa: E402
from apps.pages.features.tools import domain, queries                 # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
print('== 1. o mês do fixing ==')
check('M-1 de 11/09/2026 é agosto', ipca.mes_do_fixing(date(2026, 9, 11), ipca.M1), (2026, 8))
check('M-2 de 11/09/2026 é julho', ipca.mes_do_fixing(date(2026, 9, 11), ipca.M2), (2026, 7))
check('M-1 vira o ano', ipca.mes_do_fixing(date(2026, 1, 5), ipca.M1), (2025, 12))
check('M-2 vira o ano', ipca.mes_do_fixing(date(2026, 2, 5), ipca.M2), (2025, 12))
check('aceita ISO', ipca.mes_do_fixing('2026-03-11', ipca.M1), (2026, 2))
try:
    ipca.mes_do_fixing(date(2026, 1, 1), 'm3')
    check('fixing desconhecido levanta', False, True)
except ipca.ErroDeDado as exc:
    check('fixing desconhecido levanta', 'm3' in str(exc), True)

# ─────────────────────────────────────────────────────────────────────────────
print('== 2. a resposta do IBGE ==')
# a forma REAL da API (agregados/1737, variável 2266, localidade BR): o valor
# vem como texto com 13 casas, e o mês não publicado não está na série.
PUBLICADO = {'202602': '7545.53', '202604': '7596.09', '202605': '7640.15',
             '202606': '7652.3700000000000',
             '202607': '7657.7300000000000', '202608': '7633.2300000000000'}
chamadas = []


def _stub_obter_json(url, cabecalho=None, timeout=40):
    chamadas.append(url)
    de, ate = url.split('/periodos/')[1].split('/')[0].split('-')
    serie = {k: v for k, v in PUBLICADO.items() if de <= k <= ate}
    return [{'id': '2266', 'variavel': 'IPCA - Número-índice (base: dezembro de 1993 = 100)',
             'unidade': 'Número-índice',
             'resultados': [{'classificacoes': [], 'series': [
                 {'localidade': {'id': '1', 'nome': 'Brasil'}, 'serie': serie}]}]}]


_obter_original = rede.obter_json
rede.obter_json = _stub_obter_json
ipca._memo.clear()

s = ipca.serie((2026, 6), (2026, 9))
check('a URL é a da tabela 1737, variável 2266, BR',
      chamadas[-1], 'https://servicodados.ibge.gov.br/api/v3/agregados/1737/periodos/'
                    '202606-202609/variaveis/2266?localidades=BR')
check('a série volta por AAAAMM em float', s, {'202606': 7652.37, '202607': 7657.73, '202608': 7633.23})
check('mês não publicado não vem', '202609' in s, False)
check('invertido, os meses se ordenam', ipca.serie((2026, 8), (2026, 6)) == s, True)

n = ipca.numeros_indice([(2026, 8), (2026, 2)])
check('numeros_indice devolve os pedidos', n, {(2026, 2): 7545.53, (2026, 8): 7633.23})
try:
    ipca.numeros_indice([(2026, 8), (2026, 9)])
    check('mês não publicado é erro com o mês', False, True)
except ipca.ErroIBGE as exc:
    check('mês não publicado é erro com o mês', '09/2026' in str(exc) and 'not published' in str(exc), True)
antes = len(chamadas)
ipca.numeros_indice([(2026, 7), (2026, 8)])
check('o memo poupa a ida ao IBGE', len(chamadas), antes)


def _falha(url, cabecalho=None, timeout=40):
    raise rede.ErroRede('could not reach {url} (offline)', url=url)


rede.obter_json = _falha
try:
    ipca.numeros_indice([(2026, 9)])
    check('rede fora é ErroIBGE, não traceback', False, True)
except ipca.ErroIBGE as exc:
    check('rede fora é ErroIBGE, não traceback', 'offline' in str(exc), True)
rede.obter_json = _stub_obter_json

# ─────────────────────────────────────────────────────────────────────────────
print('== 3. a perna IPCA com fixing ==')
cal = liquidacao.calendario_anbima()
d0, d1 = date(2026, 3, 11), date(2026, 9, 11)
# O fixing diz o mês do número FINAL; o inicial é o do CONTRATO quando está
# digitado (a cotação inicial da posição) e só cai para o IBGE em branco.
p_m1 = liquidacao.Ponta(indexador=liquidacao.IPCA, taxa=0.05, ipca_fixing=ipca.M1,
                        ni_inicial=7600.0, ni_final=2.0)          # final digitado: ignorado
r1 = liquidacao.liquidar_ponta(p_m1, 1000000.0, d0, d1, cal)
check('M-1: o final é agosto (do fim) e o inicial é o digitado',
      (r1.ni_inicial, r1.ni_final, r1.mes_ni_inicial, r1.mes_ni_final),
      (7600.0, 7633.23, None, '08/2026'))
cupom = liquidacao.contagem.fator(0.05, p_m1.convencao, p_m1.regime, d0, d1, cal)
check('a correção fica FORA do índice: fator_do_indice é só o cupom',
      (round(r1.fator_do_indice, 12), round(r1.fator_correcao, 12)),
      (round(cupom, 12), round(7633.23 / 7600.0, 12)))
check('o fator total é correção × cupom', round(r1.fator, 12), round(cupom * 7633.23 / 7600.0, 12))
check('os juros são só o cupom sobre o principal corrigido',
      round(r1.juros, 2), round(1000000.0 * (7633.23 / 7600.0) * (cupom - 1), 2))
check('e a correção do principal fecha a identidade',
      round(r1.juros + r1.efeito_correcao + r1.efeito_cambial, 2), round(r1.valor - 1000000.0, 2))
check('a descrição diz o mês e a fonte', 'contract → 08/2026, IBGE' in r1.descricao_texto, True)
check('o fixing vai no resultado', r1.ipca_fixing, ipca.M1)

p_m2 = liquidacao.Ponta(indexador=liquidacao.IPCA, taxa=0.0, ipca_fixing=ipca.M2)
r2 = liquidacao.liquidar_ponta(p_m2, 1000000.0, date(2026, 8, 5), d1, cal)
check('inicial em branco: M-2 do início (junho) e do fim (julho)',
      (r2.mes_ni_inicial, r2.mes_ni_final), ('06/2026', '07/2026'))
check('sem cupom o fator é só a correção', round(r2.fator, 10), round(7657.73 / 7652.37, 10))
check('e sem cupom não há juros', round(r2.juros, 2), 0.0)

p_dig = liquidacao.Ponta(indexador=liquidacao.IPCA, taxa=0.0, ni_inicial=100.0, ni_final=110.0)
r3 = liquidacao.liquidar_ponta(p_dig, 1000000.0, d0, d1, cal)
check('sem fixing os digitados valem', (r3.fator, r3.mes_ni_final, r3.ni_final), (1.1, None, 110.0))
check('e a descrição não cita o IBGE', 'IBGE' in r3.descricao_texto, False)

try:
    liquidacao.liquidar_ponta(liquidacao.Ponta(indexador=liquidacao.IPCA, ipca_fixing=ipca.M1),
                              1000000.0, d0, date(2026, 10, 5), cal)
    check('fim cujo M-1 não saiu recusa', False, True)
except ipca.ErroIBGE as exc:
    check('fim cujo M-1 não saiu recusa', '09/2026' in str(exc), True)

# A planilha da mesa (VIBRA, 26F03049396): VBR 1.044.042.991,00, fluxo
# 15/06 → 11/09/2026 (63 DU), IPCA + 5,3995%, fixing -2, Ativo Início
# 7.640,15 (da posição) e Ativo Fim 7.657,73 (julho) → Juros 13.848.372,29.
p_mesa = liquidacao.Ponta(indexador=liquidacao.IPCA, taxa=0.053995, ipca_fixing=ipca.M2,
                          ni_inicial=7640.15)
r4 = liquidacao.liquidar_ponta(p_mesa, 1044042991.0, date(2026, 6, 15), date(2026, 9, 11), cal)
check('planilha da mesa: 63 DU, julho no fim, maio (posição) no início',
      (r4.dias_uteis, r4.ni_inicial, r4.ni_final, r4.mes_ni_final), (63, 7640.15, 7657.73, '07/2026'))
check('planilha da mesa: juros R$ 13.848.372,29 (±1)', abs(r4.juros - 13848372.29) < 1.0, True)
check('planilha da mesa: o cupom é 1,013233727', round(r4.fator_do_indice, 9), 1.013233727)

# ─────────────────────────────────────────────────────────────────────────────
print('== 4. o form e a tela ==')
form = {'ativa_indexador': 'ipca', 'ativa_taxa': '5', 'ativa_ipca_fixing': 'm1',
        'ativa_ni_inicial': '', 'ativa_ni_final': ''}
pa = domain.ponta_do_form(form, 'ativa')
check('o fixing entra na Ponta', pa.ipca_fixing, 'm1')
check('em branco é digitado', domain.ponta_do_form({'passiva_indexador': 'ipca'}, 'passiva').ipca_fixing, '')
try:
    domain.ponta_do_form(dict(form, ativa_ipca_fixing='m5'), 'ativa')
    check('fixing estranho é erro de formulário', False, True)
except domain.ErroFormulario as exc:
    check('fixing estranho é erro de formulário', 'm5' in str(exc), True)

from apps import create_app                                            # noqa: E402
from apps.config import DebugConfig                                    # noqa: E402
app = create_app(DebugConfig)
app.config['TESTING'] = True
with app.test_client() as c:
    with c.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = 'E930179'
        s['user_name'] = 'Teste'
        s['user_role'] = 'ADMIN'
        s['session_expires_at'] = '2999-01-01T00:00:00'
    from apps.pages.features.tools import entrypoint as E             # noqa: E402
    base = E._form_padrao_swap(date(2026, 9, 11))
    check('o form padrão traz o fixing em branco nas duas pernas',
          (base['ativa_ipca_fixing'], base['passiva_ipca_fixing']), ('', ''))
    dados = dict(base, data_operacao='2026-03-11', inicio='2026-03-11', fim='2026-09-11',
                 ativa_indexador='ipca', ativa_taxa='5', ativa_ipca_fixing='m1',
                 ativa_ni_inicial='1', ativa_ni_final='1',
                 passiva_indexador='pre', passiva_taxa='14')
    resp = c.post('/tools/swap-calculator', data=dados)
    html = resp.get_data(as_text=True)
    check('a tela calcula', resp.status_code, 200)
    check('o select do fixing existe e M-1 fica escolhido',
          'id="ativa_ipca_fixing"' in html and 'value="m1" selected' in html, True)
    check('o final buscado volta para o campo; o inicial digitado fica',
          'value="7633.230000"' in html and 'value="7545.530000"' not in html, True)
    check('a nota diz o mês do final e que o inicial é do contrato',
          '08/2026' in html and 'initial from the contract' in html, True)
    check('o resumo mostra o número-índice e a correção no principal',
          'Index number' in html and '(contract)' in html and '(08/2026)' in html
          and 'Inflation adjustment on the principal' in html, True)
    resp_b = c.post('/tools/swap-calculator', data=dict(dados, ativa_ni_inicial=''))
    html_b = resp_b.get_data(as_text=True)
    check('inicial em branco: os dois vêm do IBGE e voltam para os campos',
          'value="7545.530000"' in html_b and 'value="7633.230000"' in html_b
          and '02/2026 → 08/2026' in html_b, True)
    check('as opções vêm do motor', 'data-lang="tl-ipca-m2"' in html, True)
    resp2 = c.post('/tools/swap-calculator', data=dict(dados, fim='2026-10-05'))
    html2 = resp2.get_data(as_text=True)
    check('mês não publicado vira o erro da tela',
          resp2.status_code == 200 and 'not published yet' in html2 and '09/2026' in html2, True)
    resp3 = c.get('/tools/swap-calculator')
    check('o GET abre com o fixing em branco', 'value="" selected' in resp3.get_data(as_text=True), True)

# ─────────────────────────────────────────────────────────────────────────────
print('== 5. o fluxo sem Taxa Amortização é 0% ==')
x = {'tipo_amort': 'Sobre Valor Base Original', 'taxa_amort': None}
queries._amortizacao_do_evento(x, '')
check('evento sem taxa: 0%, com a base do tipo', (x['p_amort'], x['p_base_amort']),
      ('0', liquidacao.SOBRE_ORIGINAL))
x = {'tipo_amort': '', 'taxa_amort': None}
queries._amortizacao_do_evento(x, 'Sobre Valor Base Remanescente')
check('sem tipo no evento vale o da posição, e a taxa vazia segue 0%',
      (x['p_amort'], x['p_base_amort']), ('0', liquidacao.SOBRE_REMANESCENTE))
x = {'tipo_amort': 'Sobre Valor Base Original', 'taxa_amort': 33.33}
queries._amortizacao_do_evento(x, '')
check('com taxa, a taxa', x['p_amort'], '33.3300')
x = {'tipo_amort': 'Na Data de Vencimento', 'taxa_amort': 33.33}
queries._amortizacao_do_evento(x, '')
check('no vencimento o fluxo não amortiza mesmo com taxa', x['p_amort'], '0')

rede.obter_json = _obter_original
print()
print('FALHAS: %d' % len(falhas) if falhas else 'tudo ok')
sys.exit(1 if falhas else 0)
