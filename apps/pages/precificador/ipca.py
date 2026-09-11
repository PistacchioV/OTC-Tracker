# -*- coding: utf-8 -*-
"""IPCA — o número-índice mensal do IBGE, para a perna IPCA do Swap Calculator.

A perna IPCA corrige o notional por ``NI_final / NI_inicial``. Até aqui os
dois números eram digitados; a mesa os copiava do SIDRA. O contrato diz de
QUAL mês é cada número pela defasagem do fixing:

    M-1   o mês anterior à data de liquidação do fluxo
    M-2   o segundo mês anterior

A mesma defasagem vale nas duas pontas do fluxo: o número inicial é o do mês
M-n contado do INÍCIO do fluxo, o final é o do mês M-n contado do FIM (a
data do ajuste). Um fluxo de 11/03/2026 a 11/09/2026 com M-1 corrige de
fevereiro/2026 a agosto/2026 — agosto é o último IPCA publicado antes de
setembro; com M-2, de janeiro a julho.

A fonte é a API de agregados do IBGE (SIDRA): tabela 1737, variável 2266
(*IPCA — Número-índice, base dezembro de 1993 = 100*), localidade Brasil.
É a mesma URL da macro VBA da mesa (``agregados/1737/periodos/AAAAMM-AAAAMM``),
com a variável fixada em vez de "a primeira que vier": sem ela a resposta
traz seis variáveis e a primeira é a variação mensal, não o índice.

Mês ainda não publicado NÃO vem na série (a chave simplesmente falta) —
nunca vem como zero. Aqui isso é erro dito com o mês, nunca um índice
inventado: o IPCA sai por volta do dia 10 do mês seguinte, e um fluxo que
liquida no dia 5 com M-1 pede um número que ainda não existe.

O que já foi publicado não muda: o memo de processo guarda cada mês que a
API devolveu, e só o mês que faltou volta a ser pedido.
"""
import logging
import threading

from apps.pages.precificador import rede
from apps.pages.precificador.calendario import para_data
from apps.pages.precificador.erros import ErroDeDado, ErroDeFonte

log = logging.getLogger('otc_tracker')

API = ('https://servicodados.ibge.gov.br/api/v3/agregados/1737/periodos/{de}-{ate}'
       '/variaveis/2266?localidades=BR')

M1 = 'm1'
M2 = 'm2'
DEFASAGEM = {M1: 1, M2: 2}
FIXINGS = [
    (M1, 'M-1 — the month before the flow settlement'),
    (M2, 'M-2 — two months before the flow settlement'),
]
TIMEOUT = 40

_memo = {}                    # 'AAAAMM' -> float
_memo_lock = threading.Lock()


class ErroIBGE(ErroDeFonte):
    """Falha ao obter o número-índice do IBGE — ou mês não publicado."""


def mes_do_fixing(referencia, fixing):
    """O ``(ano, mês)`` do IPCA que um fixing M-1/M-2 pede para uma data."""
    if fixing not in DEFASAGEM:
        raise ErroDeDado('unknown IPCA fixing: {fixing}', fixing=fixing)
    d = para_data(referencia)
    n = d.year * 12 + (d.month - 1) - DEFASAGEM[fixing]
    return n // 12, n % 12 + 1


def chave(ano, mes):
    return '{:04d}{:02d}'.format(ano, mes)


def rotulo(ano, mes):
    """``08/2026`` — como a tela escreve mês."""
    return '{:02d}/{:04d}'.format(mes, ano)


def serie(de, ate, timeout=TIMEOUT):
    """Os números-índice publicados entre dois meses (``(ano, mês)``),
    como ``{'AAAAMM': float}``. Mês sem publicação simplesmente não vem."""
    if (ate[0], ate[1]) < (de[0], de[1]):
        de, ate = ate, de
    url = API.format(de=chave(*de), ate=chave(*ate))
    try:
        bruto = rede.obter_json(url, timeout=timeout)
    except rede.ErroRede as exc:
        raise ErroIBGE('could not fetch the IPCA index number from IBGE: {motivo}',
                       motivo=str(exc)) from exc
    valores = {}
    try:
        for variavel in bruto or []:
            for resultado in variavel.get('resultados') or []:
                for s in resultado.get('series') or []:
                    for k, v in (s.get('serie') or {}).items():
                        try:
                            valores[str(k)] = float(v)
                        except (TypeError, ValueError):
                            continue      # '...' e '-' são "sem dado"
    except AttributeError as exc:
        raise ErroIBGE('unexpected answer from IBGE: {motivo}', motivo=str(exc)) from exc
    with _memo_lock:
        _memo.update(valores)
    return valores


def numeros_indice(meses, timeout=TIMEOUT):
    """O número-índice de cada ``(ano, mês)`` pedido, numa ida só à API para
    o que o memo não tem. Levanta ``ErroIBGE`` nomeando o mês que o IBGE
    ainda não publicou."""
    pedidos = sorted(set((int(a), int(m)) for a, m in meses))
    with _memo_lock:
        faltam = [am for am in pedidos if chave(*am) not in _memo]
    if faltam:
        serie(faltam[0], faltam[-1], timeout=timeout)
    saida = {}
    with _memo_lock:
        for am in pedidos:
            v = _memo.get(chave(*am))
            if v is None:
                raise ErroIBGE('the IPCA index number of {mes} is not published yet '
                               '(IBGE table 1737)', mes=rotulo(*am))
            saida[am] = v
    return saida
