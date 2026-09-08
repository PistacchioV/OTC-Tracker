# -*- coding: utf-8 -*-
"""Calendário de dias úteis.

Reproduz as funções de planilha das macros originais:

    NETWORKDAYS(inicio; fim; feriados) - 1   ->  Calendario.dias_uteis
    WORKDAY(data; n; feriados)               ->  Calendario.workday
    EDATE(data; meses)                       ->  soma_meses

**Os feriados são os do Holidays Calendar do app**, não arquivos próprios: o
registro `holiday-calendars.json` diz o arquivo de cada calendário (`anbima.json`,
`sofr.json`, `euribor.json`), lido pelo `data_paths` — o mesmo caminho que a
tela de feriados grava. Um feriado acrescentado pela tela vale aqui no request
seguinte (cache por mtime). Fora do alcance do arquivo da EURIBOR vale a regra
do TARGET2 (seis feriados por ano, dois móveis), e o `US+BR` é a união do SOFR
com o ANBIMA — as pernas em dólar de um swap local param nos dois países.
"""
import json
import os
from datetime import date, datetime, timedelta

from apps.pages.data_paths import data_path
from apps.pages.precificador.erros import ErroDeDado

REGISTRO = 'holiday-calendars.json'
# O arquivo de cada calendário quando o registro não responde — é a mesma
# resposta do seed do Holidays (`domain.CAL_SEED`), escrita aqui só como
# último recurso.
_ARQUIVO_PADRAO = {'ANBIMA': 'anbima.json', 'SOFR': 'sofr.json', 'EURIBOR': 'euribor.json'}


def para_data(valor):
    """Aceita ``date``, ``datetime`` ou string ISO / dd/mm/aaaa."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        texto = valor.strip()
        for formato in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                return datetime.strptime(texto, formato).date()
            except ValueError:
                continue
    raise ErroDeDado('invalid date: {valor}', valor=repr(valor))


class Calendario:
    """Conjunto de feriados + regra de fim de semana (sábado e domingo)."""

    def __init__(self, feriados, nome=''):
        self.nome = nome
        self._feriados = frozenset(feriados)

    @property
    def feriados(self):
        return self._feriados

    def eh_dia_util(self, d):
        d = para_data(d)
        return d.weekday() < 5 and d not in self._feriados

    def ajusta(self, d):
        """Following: o próximo dia útil quando a data não é um."""
        d = para_data(d)
        while not self.eh_dia_util(d):
            d += timedelta(days=1)
        return d

    def workday(self, d, dias):
        """``WORKDAY(d; dias; feriados)`` — n dias úteis à frente/atrás."""
        d = para_data(d)
        if dias == 0:
            return d
        passo = timedelta(days=1 if dias > 0 else -1)
        restantes = abs(int(dias))
        while restantes:
            d += passo
            if self.eh_dia_util(d):
                restantes -= 1
        return d

    def networkdays(self, inicio, fim):
        """``NETWORKDAYS`` do Excel — inclui as duas pontas."""
        inicio, fim = para_data(inicio), para_data(fim)
        if fim < inicio:
            return -self.networkdays(fim, inicio)
        total, d = 0, inicio
        while d <= fim:
            if self.eh_dia_util(d):
                total += 1
            d += timedelta(days=1)
        return total

    def dias_uteis(self, inicio, fim):
        """``NETWORKDAYS − 1`` — a convenção das planilhas. Quando o início é
        dia útil equivale ao intervalo aberto à esquerda, e
        ``dias_uteis(d, d) == 0``."""
        return self.networkdays(inicio, fim) - 1

    @staticmethod
    def dias_corridos(inicio, fim):
        return (para_data(fim) - para_data(inicio)).days


# ── os arquivos do Holidays Calendar ────────────────────────────────────────

def _arquivo_do_calendario(nome):
    """O arquivo de um calendário pelo REGISTRO; sem registro, o padrão."""
    alvo = nome.strip().upper()
    try:
        fp = data_path(REGISTRO)
        if os.path.isfile(fp):
            with open(fp, encoding='utf-8') as fh:
                for row in json.load(fh) or []:
                    if isinstance(row, dict) and str(row.get('name', '')).strip().upper() == alvo:
                        arq = str(row.get('file', '') or '').strip()
                        if arq:
                            return arq
    except (OSError, ValueError):
        pass
    return _ARQUIVO_PADRAO.get(alvo)


_cache = {}


def _feriados_do_arquivo(nome):
    """As datas do arquivo de um calendário, cacheadas por mtime. Arquivo
    ausente → vazio (o chamador decide se completa por regra)."""
    arq = _arquivo_do_calendario(nome)
    if not arq:
        return frozenset()
    fp = data_path(arq)
    try:
        mt = os.path.getmtime(fp)
    except OSError:
        return frozenset()
    chave = (nome.upper(), fp)
    guardado = _cache.get(chave)
    if guardado and guardado[0] == mt:
        return guardado[1]
    datas = set()
    try:
        with open(fp, encoding='utf-8') as fh:
            for item in json.load(fh) or []:
                texto = item.get('date') if isinstance(item, dict) else item
                if texto:
                    try:
                        datas.add(para_data(str(texto)[:10]))
                    except ErroDeDado:
                        continue
    except (OSError, ValueError):
        return frozenset()
    saida = frozenset(datas)
    _cache[chave] = (mt, saida)
    return saida


def calendario_anbima():
    """Feriados bancários brasileiros — o `anbima.json` do app."""
    return Calendario(_feriados_do_arquivo('ANBIMA'), nome='ANBIMA')


def calendario_sofr():
    """Dias bons do SOFR — feriados do Fed mais a Sexta-feira Santa (SIFMA)."""
    return Calendario(_feriados_do_arquivo('SOFR'), nome='SOFR')


def calendario_target2(inicio=1999, fim=2099):
    """TARGET2 pela regra: 1/jan, Sexta-feira Santa, Segunda de Páscoa, 1/mai,
    25 e 26/dez. O TARGET não transfere feriado de fim de semana."""
    feriados = []
    for ano in range(inicio, fim + 1):
        domingo = pascoa(ano)
        feriados.extend([date(ano, 1, 1), domingo - timedelta(days=2),
                         domingo + timedelta(days=1), date(ano, 5, 1),
                         date(ano, 12, 25), date(ano, 12, 26)])
    return Calendario(feriados, nome='TARGET2')


def calendario_bce():
    """EURIBOR/TARGET2: o arquivo do Holidays (que traz também os fechamentos
    de 24 e 31/12) e, nos anos que ele não cobre, a regra do BCE."""
    do_arquivo = _feriados_do_arquivo('EURIBOR')
    anos = {d.year for d in do_arquivo}
    regra = {d for d in calendario_target2().feriados if d.year not in anos}
    return Calendario(do_arquivo | regra, nome='EURIBOR')


def calendario_us_br():
    """União de EUA e Brasil — a perna em dólar de um swap local."""
    return Calendario(_feriados_do_arquivo('SOFR') | _feriados_do_arquivo('ANBIMA'),
                      nome='US+BR')


def pascoa(ano):
    """Domingo de Páscoa (Meeus/Gauss, gregoriano)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7                    # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


# nome exibido → (função, descrição em inglês). A tela lê daqui.
CALENDARIOS_DISPONIVEIS = [
    ('ANBIMA', calendario_anbima, 'Brazilian banking holidays'),
    ('SOFR', calendario_sofr, 'Federal Reserve holidays + Good Friday'),
    ('EURIBOR', calendario_bce, 'TARGET2 with the 24 and 31 Dec closures'),
    ('TARGET2', calendario_target2, 'ECB rule: six holidays a year'),
    ('US+BR', calendario_us_br, 'United States and Brazil combined'),
]
CALENDARIOS = {nome: funcao for nome, funcao, _ in CALENDARIOS_DISPONIVEIS}
CALENDARIOS['BCE'] = calendario_bce


def obter_calendario(nome='ANBIMA'):
    try:
        return CALENDARIOS[str(nome or 'ANBIMA').upper()]()
    except KeyError as exc:
        raise ErroDeDado('unknown calendar: {nome}', nome=nome) from exc


def soma_meses(d, meses):
    """``EDATE`` — soma meses preservando o dia (ou o último dia do mês)."""
    d = para_data(d)
    total = d.month - 1 + meses
    ano = d.year + total // 12
    mes = total % 12 + 1
    dia = min(d.day, _ultimo_dia(ano, mes))
    return date(ano, mes, dia)


def _ultimo_dia(ano, mes):
    if mes == 12:
        return 31
    return (date(ano, mes + 1, 1) - timedelta(days=1)).day
