# -*- coding: utf-8 -*-
"""check_tools_ipca.py — o fixing M-1/M-2 da perna IPCA do Swap Calculator
(HANDOFF §449) e o 0% do fluxo sem Taxa Amortização no pré-preenchimento.

O que se prende, e por que cada coisa não daria erro sozinha:

  1. o MÊS do fixing: M-1 é o mês anterior à data (liquidação do fluxo),
     M-2 o segundo anterior — inclusive virando o ano (fev → dez/jan);
  2. a leitura da resposta do IBGE (tabela 1737, variável 2266): a chave é
     AAAAMM, o valor vem como texto, e mês não publicado simplesmente NÃO vem
     — o motor diz o mês que falta, nunca inventa um índice;
  3. a perna IPCA com fixing busca os DOIS números (inicial contado do início
     do fluxo, final contado do fim) e IGNORA os digitados; sem fixing, os
     digitados continuam valendo, e o resultado carrega de que meses são;
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
PUBLICADO = {'202602': '7545.53', '202606': '7652.3700000000000',
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
p_m1 = liquidacao.Ponta(indexador=liquidacao.IPCA, taxa=0.05, ipca_fixing=ipca.M1,
                        ni_inicial=1.0, ni_final=2.0)         # digitados: têm de ser ignorados
r1 = liquidacao.liquidar_ponta(p_m1, 1000000.0, d0, d1, cal)
check('M-1: inicial de fev (do início) e final de ago (do fim)',
      (r1.ni_inicial, r1.ni_final, r1.mes_ni_inicial, r1.mes_ni_final),
      (7545.53, 7633.23, '02/2026', '08/2026'))
check('os digitados foram ignorados', r1.fator_do_indice > 1.01, True)
esperado = (7633.23 / 7545.53) * liquidacao.contagem.fator(0.05, p_m1.convencao, p_m1.regime, d0, d1, cal)
check('o fator é NI_final/NI_inicial vezes o cupom', round(r1.fator_do_indice, 12), round(esperado, 12))
check('a descrição diz os meses e a fonte', '02/2026 → 08/2026, IBGE' in r1.descricao_texto, True)
check('o fixing vai no resultado', r1.ipca_fixing, ipca.M1)

p_m2 = liquidacao.Ponta(indexador=liquidacao.IPCA, taxa=0.0, ipca_fixing=ipca.M2)
r2 = liquidacao.liquidar_ponta(p_m2, 1000000.0, date(2026, 8, 5), d1, cal)
check('M-2: junho (do início) e julho (do fim)', (r2.mes_ni_inicial, r2.mes_ni_final), ('06/2026', '07/2026'))
check('sem cupom o fator é só a correção', round(r2.fator_do_indice, 10), round(7657.73 / 7652.37, 10))

p_dig = liquidacao.Ponta(indexador=liquidacao.IPCA, taxa=0.0, ni_inicial=100.0, ni_final=110.0)
r3 = liquidacao.liquidar_ponta(p_dig, 1000000.0, d0, d1, cal)
check('sem fixing os digitados valem', (r3.fator_do_indice, r3.mes_ni_inicial, r3.ni_final), (1.1, None, 110.0))
check('e a descrição não cita o IBGE', 'IBGE' in r3.descricao_texto, False)

try:
    liquidacao.liquidar_ponta(liquidacao.Ponta(indexador=liquidacao.IPCA, ipca_fixing=ipca.M1),
                              1000000.0, d0, date(2026, 10, 5), cal)
    check('fim cujo M-1 não saiu recusa', False, True)
except ipca.ErroIBGE as exc:
    check('fim cujo M-1 não saiu recusa', '09/2026' in str(exc), True)

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
    check('os números buscados voltam para os campos',
          'value="7545.530000"' in html and 'value="7633.230000"' in html, True)
    check('a nota diz os meses', '02/2026 → 08/2026' in html, True)
    check('o resumo mostra o número-índice',
          'Index number' in html and '(02/2026)' in html and '(08/2026)' in html, True)
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
