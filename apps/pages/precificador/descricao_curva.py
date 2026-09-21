# -*- coding: utf-8 -*-
"""A `Denominação` da curva VCP, lida como CONTRATO (§479).

Quando a curva de uma ponta é VCP, a posição da B3 traz, além do `Nome
Tipo/Classe`, uma `Denominação` em texto livre — a descrição da curva que a
mesa cadastrou —, e é nela que mora o que as colunas normais não têm. O
exemplo que motivou isto:

    TERM SOFR 3M - Fixings PTAX-Ask T-1 - Initial FX PTAX-V 15/Jun/26
    - (3M SOFR + 0.75%)*1.1765 A/360

A posição diz "Term SOFR 3M com spread de 0,75%"; o `*1.1765` (o gross-up de
15% de IR sobre a taxa) só existe aqui, e sem ele a liquidação não bate com a
planilha da mesa nem com o sistema do banco.

Este módulo é um INTERPRETADOR DE REGRAS, de propósito: cada coisa que ele
reconhece sai como um `Achado` com o TRECHO exato de onde veio, e o que sobra
do texto com número e operador — o que ele NÃO entendeu — volta em
`nao_lido`, para a mesa conferir à mão. Um modelo estatístico aqui daria uma
resposta sem trecho e sem "não sei": num número que multiplica o notional, a
resposta errada com confiança é pior que a lacuna sinalizada. E a instância
roda sem internet, sem GPU e sem biblioteca de ML — a tabela `_REGRAS` abaixo
é o que cresce quando aparecer uma denominação nova.

Puro: sem Flask, sem rede, sem arquivo. Os valores saem no FORMATO DO
FORMULÁRIO do Swap Calculator (texto, ponto decimal), prontos para os campos.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

from apps.pages.precificador import contagem

# os campos da ponta que uma denominação pode preencher
MULTIPLICADOR = 'multiplicador'
TAXA = 'taxa'                 # o spread contratado (% a.a.)
PERCENTUAL = 'percentual'     # % do CDI
CONVENCAO = 'convencao'
REGIME = 'regime'
TENOR = 'tenor'
PTAX_OFFSET = 'ptax_offset'
LOOKBACK = 'lookback'
SHIFT = 'shift'
# Equity: o PREÇO INICIAL é um percentual sobre um fechamento — `Preco in ativo
# - 100.00% Close 20-Sep-24`. O percentual é o Cupom Limpo; a data é a do pregão
# cujo fechamento ele multiplica.
CUPOM_LIMPO = 'cupom_limpo'   # % (100.0000 = 100%)
CUPOM_DATA = 'cupom_data'     # ISO — o pregão do fechamento


@dataclass(frozen=True)
class Achado:
    """Uma coisa que a denominação diz.

    `campo` é o campo do formulário que ela preenche — `None` quando é só
    informação (a data do fixing inicial, o lado da PTAX), que a tela mostra e
    não aplica. `trecho` é o pedaço do texto de onde saiu: é o que deixa a
    mesa conferir a leitura sem ter de acreditar nela."""
    campo: Optional[str]
    valor: str
    trecho: str
    rotulo: str
    inicio: int = 0
    fim: int = 0


@dataclass
class Leitura:
    texto: str
    achados: List[Achado] = field(default_factory=list)
    nao_lido: List[str] = field(default_factory=list)

    def valor(self, campo):
        for a in self.achados:
            if a.campo == campo:
                return a.valor
        return None

    @property
    def vazia(self):
        return not self.achados and not self.nao_lido


def _num(texto):
    """'1,1765' / '1.1765' / '0.75' → float. Vírgula é decimal aqui — a
    denominação não escreve milhar."""
    return float(str(texto).strip().replace(',', '.'))


def _fmt(valor, casas):
    return '{:.{c}f}'.format(valor, c=casas)


def _sem_acento(s):
    s = unicodedata.normalize('NFKD', str(s or ''))
    return ''.join(c for c in s if not unicodedata.combining(c))


_INDICES = r'(?:TERM\s+SOFR|SOFR|EURIBOR|LIBOR|CDI|\bDI\b|SELIC|IPCA|IGP-?M|PRE)'
_NUM = r'\d+(?:[.,]\d+)?'
_TENOR_NOME = {1: '1 month', 3: '3 month', 6: '6 month', 12: '12 month'}


def _tenor(n):
    return _TENOR_NOME.get(int(n))


# ── as regras ────────────────────────────────────────────────────────────────
# (campo, regex, valor(m), rótulo). O regex roda em MAIÚSCULAS sem acento; o
# `valor` recebe o match e devolve o texto do formulário — ou None para
# descartar o match. A ORDEM importa só para o `nao_lido`: cada trecho casado
# sai do texto residual.

def _mult_de_divisor(m):
    d = _num(m.group(1))
    return _fmt(1.0 / d, 8) if d else None


def _mult_de_grossup(m):
    p = _num(m.group(1)) / 100.0
    return _fmt(1.0 / (1.0 - p), 8) if 0 < p < 1 else None


def _spread(m):
    sinal = -1.0 if m.group(1) in ('-', '−', '–') else 1.0
    return _fmt(sinal * _num(m.group(2)), 4)


def _dc(codigo):
    return lambda m: codigo


# Os meses como a denominação os escreve: em inglês (o Bloomberg) e em
# português (a mesa). Só as três letras — `September` e `Setembro` caem no mesmo.
_MESES = {'JAN': 1, 'FEB': 2, 'FEV': 2, 'MAR': 3, 'APR': 4, 'ABR': 4, 'MAY': 5, 'MAI': 5,
          'JUN': 6, 'JUL': 7, 'AUG': 8, 'AGO': 8, 'SEP': 9, 'SET': 9, 'OCT': 10, 'OUT': 10,
          'NOV': 11, 'DEC': 12, 'DEZ': 12}


def _data_do_close(m):
    """`20-Sep-24` / `20/SET/2024` → ISO; data que não existe descarta o match."""
    mes = _MESES.get(m.group(2)[:3])
    if not mes:
        return None
    ano = int(m.group(3))
    ano += 2000 if ano < 100 else 0
    try:
        from datetime import date
        return date(ano, mes, int(m.group(1))).isoformat()
    except ValueError:
        return None


def _cupom_pct(m):
    return _fmt(_num(m.group(1)), 4)


def _cupom_fator(m):
    # `1.5 Close 14-Aug-26`: sem o `%`, o número é o FATOR (1.5 = 150%)
    return _fmt(_num(m.group(1)) * 100.0, 4)


_REGRAS = [
    # o multiplicador da taxa: `(… + 0.75%)*1.1765`, `(…) x 1,1765`, `1.1765*(…)`
    (MULTIPLICADOR, r'\)\s*[*X×]\s*(' + _NUM + r')', lambda m: _fmt(_num(m.group(1)), 8),
     'rate multiplier'),
    (MULTIPLICADOR, r'(' + _NUM + r')\s*[*X×]\s*\(', lambda m: _fmt(_num(m.group(1)), 8),
     'rate multiplier'),
    (MULTIPLICADOR, r'%\s*[*X×]\s*(' + _NUM + r')(?![\d.,]*\s*%)',
     lambda m: _fmt(_num(m.group(1)), 8), 'rate multiplier'),
    # `(…)/0.85` é o mesmo gross-up escrito como divisão
    (MULTIPLICADOR, r'\)\s*/\s*(0[.,]\d+)', _mult_de_divisor, 'rate multiplier (from the divisor)'),
    (MULTIPLICADOR, r'GROSS[\s-]*UP\s*(?:OF|DE)?\s*(' + _NUM + r')\s*%', _mult_de_grossup,
     'rate multiplier (from the gross-up)'),
    # o percentual do CDI: `110% CDI`, `100% do DI` — ANTES do spread, porque
    # em `DI - 110% do CDI` o ` - ` é o separador de cláusula da B3, não um
    # spread negativo: o trecho consumido aqui não casa de novo lá embaixo
    (PERCENTUAL, r'(' + _NUM + r')\s*%\s*(?:DO|DE|OF)?\s*(?:CDI|\bDI\b)',
     lambda m: _fmt(_num(m.group(1)), 4), '% of CDI'),
    # o spread: `SOFR + 0.75%`, `3M SOFR - 0.5%`, `CDI + 1.07%`
    (TAXA, _INDICES + r'\s*(?:\d+\s*M\b)?\s*([+\-−–])\s*(' + _NUM + r')\s*%', _spread, 'spread'),
    # a contagem de dias
    (CONVENCAO, r'\b(?:A|ACT|ACTUAL)\s*/\s*360\b', _dc(contagem.ACT_360), 'day count'),
    (CONVENCAO, r'\b(?:A|ACT|ACTUAL)\s*/\s*365\b', _dc(contagem.ACT_365), 'day count'),
    (CONVENCAO, r'\b30E\s*/\s*360\b', _dc(contagem.T30E_360), 'day count'),
    (CONVENCAO, r'\b30\s*/\s*360\b', _dc(contagem.T30_360), 'day count'),
    (CONVENCAO, r'\b(?:DU|BUS|BD|B)\s*/\s*252\b', _dc(contagem.DU_252), 'day count'),
    (CONVENCAO, r'\bACT\s*/\s*ACT\b', _dc(contagem.ACT_ACT), 'day count'),
    # `Exp/252` e `Lin/360` (a grafia da planilha da mesa): a base diz a contagem
    (CONVENCAO, r'\b(?:EXP|LIN)\s*/\s*252\b', _dc(contagem.DU_252), 'day count'),
    (CONVENCAO, r'\b(?:EXP|LIN)\s*/\s*360\b', _dc(contagem.ACT_360), 'day count'),
    (CONVENCAO, r'\b(?:EXP|LIN)\s*/\s*365\b', _dc(contagem.ACT_365), 'day count'),
    # o regime, quando a denominação o escreve (`Lin/360`, `Exp/252`)
    (REGIME, r'\b(?:LIN|LINEAR|SIMPLES|SIMPLE)\b', lambda m: contagem.SIMPLES, 'compounding'),
    (REGIME, r'\b(?:EXP|EXPONENCIAL|COMPOUND(?:ED)?|COMPOSTO)\b', lambda m: contagem.COMPOSTO,
     'compounding'),
    # o prazo do fixing: `TERM SOFR 3M`, `3M SOFR`, `EURIBOR 6M`
    (TENOR, r'(\d+)\s*M\b\s*(?:TERM\s+)?(?:SOFR|EURIBOR)', lambda m: _tenor(m.group(1)),
     'fixing tenor'),
    (TENOR, r'(?:TERM\s+SOFR|SOFR|EURIBOR)\s*(\d+)\s*M\b', lambda m: _tenor(m.group(1)),
     'fixing tenor'),
    (TENOR, r'(?:TERM\s+SOFR|SOFR|EURIBOR)\s*1\s*W\b', lambda m: '1 week', 'fixing tenor'),
    # o deslocamento da PTAX do fixing: `PTAX-Ask T-1`, `PTAX D-2`
    (PTAX_OFFSET, r'PTAX[\s-]*(?:ASK|BID|VENDA|COMPRA|V|C)?\s*[TD]\s*-\s*(\d)',
     lambda m: str(int(m.group(1))), 'fixing offset (business days)'),
    # SOFR composto: lookback e observation shift
    (LOOKBACK, r'LOOK[\s-]*BACK\s*(?:OF|DE)?\s*(\d+)', lambda m: str(int(m.group(1))), 'lookback'),
    (SHIFT, r'(?:OBS(?:ERVATION)?\s*)?SHIFT\s*(?:OF|DE)?\s*(\d+)', lambda m: str(int(m.group(1))),
     'observation shift'),
    # Equity — o preço inicial como % de um fechamento. A cláusula do CLOSE
    # vem ANTES de `Preco Inicial: 100.00%`: as duas dizem o mesmo percentual,
    # e a primeira regra que acha o campo vence — a que está ao lado da data é a
    # que o contrato amarra ao pregão.
    (CUPOM_LIMPO, r'(' + _NUM + r')\s*%\s*(?:DO\s+|OF\s+)?(?:CLOSE|FECHAMENTO)\b', _cupom_pct,
     'clean coupon (% of the close)'),
    (CUPOM_LIMPO, r'(?<![\d.,])(' + _NUM + r')\s+(?:CLOSE|FECHAMENTO)\b', _cupom_fator,
     'clean coupon (factor of the close)'),
    (CUPOM_LIMPO, r'(' + _NUM + r')\s*%\s*(?:DO\s+|OF\s+)?SPOT\b', _cupom_pct,
     'clean coupon (% of the spot)'),
    (CUPOM_LIMPO, r'PRECO\s+INICIAL\s*:?\s*(' + _NUM + r')\s*%', _cupom_pct,
     'clean coupon (initial price %)'),
    # o grupo do VALOR é o último (a regra do `valor_usado`): dia, mês e ano
    # entram num grupo só, e o `_data_do_close` os separa
    (CUPOM_DATA, r'(?:CLOSE|FECHAMENTO)\s*[:\-]?\s*((\d{1,2})[-/ ]([A-Z]{3,9})[-/ ](\d{2,4}))',
     lambda m: _data_do_close(_Grupos(m)), 'close date of the initial price'),
    # só informação: a data e o lado do fixing inicial da moeda
    (None, r'INITIAL\s+FX\s+PTAX[\s-]*(?:ASK|BID|VENDA|COMPRA|V|C)?\s*(\d{1,2}/[A-Z]{3}/\d{2,4})',
     lambda m: m.group(1), 'initial FX fixing date'),
    (None, r'PTAX[\s-]*(ASK|BID|VENDA|COMPRA)\b', lambda m: m.group(1).lower(), 'PTAX side'),
]

class _Grupos(object):
    """O match da data com os grupos DESLOCADOS: o grupo 1 é a data inteira (o
    valor, para o `valor_usado`), e dia/mês/ano são os 2, 3 e 4."""
    def __init__(self, m):
        self._m = m

    def group(self, n):
        return self._m.group(n + 1)


# o que, sobrando no texto, merece conferência: um número com operador ou %
_SUSPEITO = re.compile(r'(?:\d\s*[%*X×/^]|[*X×/^]\s*\d)')


def interpretar(texto):
    """A `Leitura` de uma denominação: os achados e o que ficou sem leitura.

    Um campo sai UMA vez — a primeira regra que o encontra vence, e as
    seguintes só consomem o trecho (para não cair no `nao_lido`). E um NÚMERO
    vira valor uma vez: o que uma regra tomou como valor não casa na seguinte."""
    original = ' '.join(str(texto or '').split())
    leitura = Leitura(texto=original)
    if not original:
        return leitura
    alvo = _sem_acento(original).upper()
    consumido = [False] * len(alvo)         # o que alguma regra leu (para o residual)
    valor_usado = [False] * len(alvo)       # o NÚMERO que já virou valor de um campo
    vistos = set()
    for campo, regex, valor, rotulo in _REGRAS:
        for m in re.finditer(regex, alvo):
            # Um número vira valor UMA vez: em `DI - 110% do CDI + 0.5%` o `110`
            # é o percentual, e o ` - 110%` não pode virar spread de -110%. O
            # TOKEN pode servir a duas leituras (`CDI` no percentual e no
            # spread, `Exp` na contagem e no regime): só o grupo do valor é
            # que não se repete.
            g = m.lastindex
            if g and any(valor_usado[m.start(g):m.end(g)]):
                continue
            v = valor(m)
            if v is None:
                continue
            for i in range(m.start(), m.end()):
                consumido[i] = True
            if g:
                for i in range(m.start(g), m.end(g)):
                    valor_usado[i] = True
            chave = campo or rotulo
            if chave in vistos:
                continue
            vistos.add(chave)
            leitura.achados.append(Achado(campo=campo, valor=v,
                                          trecho=original[m.start():m.end()],
                                          rotulo=rotulo, inicio=m.start(), fim=m.end()))
    leitura.achados.sort(key=lambda a: a.inicio)
    # o residual: os pedaços entre os trechos lidos, por cláusula (` - `)
    residual = ' '.join(''.join(c if not consumido[i] else ' '
                                for i, c in enumerate(original)).split())
    # `\s*-\s+`, não `\s+-\s+`: dois separadores seguidos (o que havia entre
    # eles foi lido) ficam `- -`, e o primeiro engoliria o espaço do segundo
    for pedaco in re.split(r'\s*-\s+|;|\|', residual):
        p = ' '.join(pedaco.replace('(', ' ').replace(')', ' ').split())
        if p and _SUSPEITO.search(_sem_acento(p).upper()):
            leitura.nao_lido.append(p)
    return leitura
