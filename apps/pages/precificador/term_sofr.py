# -*- coding: utf-8 -*-
"""Term SOFR — a curva a termo da CME, importada do relatório da B3.

O Term SOFR *forward-looking* de 1, 3, 6 e 12 meses é administrado pela CME e
**licenciado**: não há fonte pública que permita redistribuí-lo. Quem tem a
licença tem o arquivo — a B3 exporta as cotações num relatório com uma coluna
de ticker e uma de valor, e este módulo lê esse arquivo e guarda o que veio.

    coluna L   ticker            TSFR1M, TSFR3M, TSFR6M, TSFR12M
    coluna O   data da cotação   serial do Excel ou dd/mm/aaaa
    coluna P   valor da cotação  3,74231

**O valor não é taxa.** A planilha traz ``3,74231`` — o percentual como número
—, e o motor inteiro trabalha em decimal. A divisão por 100 acontece na
importação, uma vez. As colunas são procuradas pelo CABEÇALHO e só caem na
posição fixa se ele não aparecer.

Os tickers são a nomenclatura da própria CME/B3 (o layout do arquivo), não
um de-para de negócio — por isso vivem aqui e não no /mapping.
"""
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Dict, List

from apps.pages.precificador import bases, planilha
from apps.pages.precificador.calendario import para_data
from apps.pages.precificador.erros import ErroFerramenta

ARQUIVO = 'term_sofr_b3.json'

TICKERS = {
    'TSFR1M': ('m1', 'Term SOFR 1 month', 1),
    'TSFR3M': ('m3', 'Term SOFR 3 months', 3),
    'TSFR6M': ('m6', 'Term SOFR 6 months', 6),
    'TSFR12M': ('m12', 'Term SOFR 12 months', 12),
}
CAMPOS = [(campo, rotulo, meses) for campo, rotulo, meses in TICKERS.values()]
CAMPO_POR_MESES = {meses: campo for campo, _, meses in CAMPOS}

COLUNA_TICKER, COLUNA_DATA, COLUNA_VALOR = 11, 14, 15      # L, O, P

_CABECALHOS = {
    'ticker': ('ticker',),
    'data': ('data da cotacao', 'data da cotação', 'data', 'date'),
    'valor': ('valor da cotacao', 'valor da cotação', 'valor', 'taxa', 'value', 'rate'),
}


class ErroTermSOFR(ErroFerramenta, ValueError):
    """Arquivo que não dá para importar, com o motivo por extenso."""


@dataclass
class Importacao:
    linhas_lidas: int
    aproveitadas: int
    novas: int
    atualizadas: int
    datas: List[date]
    tickers: Dict[str, int]
    ignorados: Dict[str, int]

    @property
    def inicio(self):
        return min(self.datas) if self.datas else None

    @property
    def fim(self):
        return max(self.datas) if self.datas else None


def _sem_acento(texto):
    normal = unicodedata.normalize('NFKD', texto or '')
    return ''.join(c for c in normal if not unicodedata.combining(c)).strip().lower()


def _achar_colunas(linhas):
    for numero, linha in enumerate(linhas):
        achado = {}
        for indice, celula in enumerate(linha):
            rotulo = _sem_acento(celula)
            for chave, aceitos in _CABECALHOS.items():
                if chave not in achado and rotulo in aceitos:
                    achado[chave] = indice
        if len(achado) == 3:
            return numero, achado['ticker'], achado['data'], achado['valor']
    return -1, COLUNA_TICKER, COLUNA_DATA, COLUNA_VALOR


def carregar_base():
    """``{data: {campo: taxa}}`` a partir dos registros da base (DB-first) —
    a base vive também em `db/tools/term_sofr_b3.db`, pelo espelho."""
    return bases.para_dict(bases.carregar(ARQUIVO))


def salvar_base(taxas):
    bases.salvar(ARQUIVO, bases.para_lista(taxas, [c for c, _, _ in CAMPOS]))


def importar(nome, dados):
    """Lê o relatório da B3 e junta o que veio à base. O que já existe é
    SUBSTITUÍDO — o arquivo mais novo é a correção do anterior."""
    try:
        linhas = planilha.ler(nome, dados)
    except planilha.ErroPlanilha as exc:
        raise ErroTermSOFR.de(exc) from exc
    if not linhas:
        raise ErroTermSOFR('the file is empty')
    cabecalho, c_ticker, c_data, c_valor = _achar_colunas(linhas)
    encontrados, tickers, ignorados, aproveitadas = {}, {}, {}, 0
    for numero, linha in enumerate(linhas):
        if numero <= cabecalho:
            continue
        ticker = planilha.celula(linha, c_ticker).upper().replace(' ', '')
        if not ticker:
            continue
        if ticker not in TICKERS:
            ignorados[ticker] = ignorados.get(ticker, 0) + 1
            continue
        dia = planilha.como_data(planilha.celula(linha, c_data))
        valor = planilha.como_numero(planilha.celula(linha, c_valor))
        if dia is None or valor is None:
            ignorados['no date or value'] = ignorados.get('no date or value', 0) + 1
            continue
        encontrados.setdefault(dia.isoformat(), {})[TICKERS[ticker][0]] = valor / 100.0
        tickers[ticker] = tickers.get(ticker, 0) + 1
        aproveitadas += 1
    if not encontrados:
        raise ErroTermSOFR(
            'no Term SOFR quote in the file. Looked for the ticker in column {ticker}, '
            'the date in {data} and the value in {valor}, expecting one of: {esperados}.',
            ticker=planilha.letra_da_coluna(c_ticker), data=planilha.letra_da_coluna(c_data),
            valor=planilha.letra_da_coluna(c_valor), esperados=', '.join(sorted(TICKERS)))
    with bases.trava():
        base = carregar_base()
        novas = atualizadas = 0
        for dia, taxas in encontrados.items():
            if dia in base:
                atualizadas += 1
                base[dia].update(taxas)
            else:
                novas += 1
                base[dia] = taxas
        salvar_base(base)
    return Importacao(linhas_lidas=len(linhas), aproveitadas=aproveitadas, novas=novas,
                      atualizadas=atualizadas, datas=[para_data(d) for d in encontrados],
                      tickers=tickers, ignorados=ignorados)


@dataclass
class Historico:
    taxas: Dict[str, dict]

    @classmethod
    def da_base(cls):
        return cls(carregar_base())

    @property
    def datas(self):
        return [para_data(d) for d in sorted(self.taxas)]

    @property
    def campos(self):
        presentes = {c for linha in self.taxas.values() for c in linha}
        return [campo for campo, _, _ in CAMPOS if campo in presentes]

    @property
    def inicio(self):
        datas = self.datas
        return datas[0] if datas else None

    @property
    def fim(self):
        datas = self.datas
        return datas[-1] if datas else None

    @property
    def vazio(self):
        return not self.taxas

    def por_data(self):
        return {para_data(d): dict(linha) for d, linha in self.taxas.items()}

    def em(self, referencia):
        """As taxas vigentes na data, ou a última publicação anterior."""
        alvo = para_data(referencia).isoformat()
        candidatas = [d for d in sorted(self.taxas) if d <= alvo]
        if not candidatas:
            return None, {}
        escolhida = candidatas[-1]
        return para_data(escolhida), dict(self.taxas[escolhida])

    def taxa(self, meses, referencia):
        campo = CAMPO_POR_MESES.get(meses)
        if not campo:
            return None
        _, linha = self.em(referencia)
        return linha.get(campo)

    def janela(self, inicio, fim):
        i, f = para_data(inicio).isoformat(), para_data(fim).isoformat()
        return Historico({d: v for d, v in self.taxas.items() if i <= d <= f})


def carregar():
    return Historico.da_base()
