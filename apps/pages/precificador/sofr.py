# -*- coding: utf-8 -*-
"""SOFR realizado — taxas do Federal Reserve de Nova York e juros compostos.

O Term SOFR é *forward-looking*, cotado de antemão; o SOFR puro é
*backward-looking* e só fecha no fim do período, capitalizando o overnight dia
a dia. Este módulo cuida do segundo: busca a série do NY Fed e compõe o
período conforme a convenção do contrato.

    https://markets.newyorkfed.org/api/rates/secured/sofr/search.json
    https://markets.newyorkfed.org/api/rates/secured/sofrai/search.json  (índice)

As duas defasagens de contrato são independentes: **lookback** (no dia ``d``
usa-se a taxa de ``k`` dias úteis antes, com o peso do próprio dia) e
**observation shift** (a janela inteira desloca ``k`` dias úteis — taxas E
pesos; é a convenção ISDA e a que fecha com o SOFR Index).

A **base histórica** (overnight, médias de 30/90/180 dias e o SOFR Index) fica
em `DATA_DIR/tools/sofr_historico.json` (e no banco `db/tools/sofr_historico.db`, pelo espelho), sincronizada a cada abertura da tela
com um teto de frequência — o NY Fed não precisa ser consultado a cada refresh.
"""
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional

from apps.pages.precificador import bases, rede
from apps.pages.precificador.calendario import calendario_sofr, para_data
from apps.pages.precificador.erros import ErroDeDado, ErroDeFonte

API = 'https://markets.newyorkfed.org/api/rates/secured'
ARQUIVO = 'sofr_historico.json'
INICIO_DA_SERIE = date(2018, 4, 2)          # primeiro fixing publicado do SOFR
# a sincronização incremental roda no máximo uma vez a cada tanto por processo
INTERVALO_SYNC = 30 * 60

CAMPOS = [
    ('overnight', 'SOFR overnight'),
    ('media30', '30-day compounded average'),
    ('media90', '90-day compounded average'),
    ('media180', '180-day compounded average'),
]


def convencao(lookback, shift):
    """Como o mercado chamaria a combinação, em (molde, valores) — inglês."""
    if not lookback and not shift:
        return ('No lag', {})
    if lookback and not shift:
        return ('{lookback} business-day lookback', {'lookback': lookback})
    if shift and not lookback:
        return ('{shift} business-day observation shift', {'shift': shift})
    return ('{lookback} bd lookback with {shift} bd observation shift',
            {'lookback': lookback, 'shift': shift})


class ErroFed(ErroDeFonte):
    """Falha ao obter a série do NY Fed."""


@dataclass(frozen=True)
class FixingSOFR:
    data: date
    taxa: float
    volume: Optional[float] = None


def _buscar(url, timeout=30):
    try:
        return rede.obter_json(url, timeout=timeout)
    except rede.ErroRede as exc:
        raise ErroFed('could not fetch the NY Fed series: {motivo}', motivo=str(exc)) from exc


def serie_sofr(inicio, fim):
    d0, d1 = para_data(inicio), para_data(fim)
    dados = _buscar('{}/sofr/search.json?startDate={:%Y-%m-%d}&endDate={:%Y-%m-%d}'
                    .format(API, d0, d1))
    linhas = dados.get('refRates', []) if isinstance(dados, dict) else dados
    fixings = [FixingSOFR(para_data(l['effectiveDate']), float(l['percentRate']) / 100.0,
                          l.get('volumeInBillions'))
               for l in linhas if l.get('type') == 'SOFR' and l.get('percentRate') is not None]
    return sorted(fixings, key=lambda f: f.data)


def serie_indice(inicio, fim):
    d0, d1 = para_data(inicio), para_data(fim)
    dados = _buscar('{}/sofrai/search.json?startDate={:%Y-%m-%d}&endDate={:%Y-%m-%d}'
                    .format(API, d0, d1))
    linhas = dados.get('refRates', []) if isinstance(dados, dict) else dados
    return {para_data(l['effectiveDate']): float(l['index'])
            for l in linhas if l.get('index') is not None}


# ── composição ──────────────────────────────────────────────────────────────

@dataclass
class DiaComposicao:
    data_juros: date
    data_observacao: date
    taxa: float
    dias: int
    fator_dia: float
    fator_acumulado: float


@dataclass
class ResultadoSOFR:
    inicio: date
    fim: date
    lookback: int
    shift: int
    obs_inicio: date
    obs_fim: date
    dias_corridos: int
    fator: float
    taxa_composta: float
    taxa_media_simples: float
    dias: List[DiaComposicao]


def compor(fixings, inicio, fim, lookback=0, shift=0, calendario=None, base=360.0):
    """fator = Π [1 + r_i · n_i / 360]; taxa = (fator − 1) · 360 / D. ``n_i``
    são os dias corridos até o próximo dia útil — o fixing de sexta remunera
    três dias."""
    cal = calendario or calendario_sofr()
    d0, d1 = para_data(inicio), para_data(fim)
    if d1 <= d0:
        raise ErroDeDado('the period end must be later than its start')
    if lookback < 0 or shift < 0:
        raise ErroDeDado('lookback and shift cannot be negative')
    por_data = {f.data: f.taxa for f in fixings}
    obs_inicio = cal.workday(d0, -shift) if shift else d0
    obs_fim = cal.workday(d1, -shift) if shift else d1
    dias_da_janela = _dias_uteis_entre(cal, obs_inicio, obs_fim)
    sequencia = dias_da_janela + [obs_fim]
    linhas, fator, soma = [], 1.0, 0.0
    for i, dia in enumerate(dias_da_janela):
        n = (sequencia[i + 1] - dia).days
        observacao = cal.workday(dia, -lookback) if lookback else dia
        taxa = _taxa_do_dia(por_data, observacao)
        fator *= 1.0 + taxa * n / base
        soma += taxa * n
        linhas.append(DiaComposicao(dia, observacao, taxa, n, 1.0 + taxa * n / base, fator))
    dias_corridos = (obs_fim - obs_inicio).days
    if dias_corridos <= 0:
        raise ErroDeDado('the period has no calendar days')
    return ResultadoSOFR(
        inicio=d0, fim=d1, lookback=lookback, shift=shift, obs_inicio=obs_inicio,
        obs_fim=obs_fim, dias_corridos=dias_corridos, fator=fator,
        taxa_composta=(fator - 1.0) * base / dias_corridos,
        taxa_media_simples=soma / dias_corridos, dias=linhas)


def _dias_uteis_entre(cal, inicio, fim):
    dias, d = [], inicio
    while d < fim:
        if cal.eh_dia_util(d):
            dias.append(d)
        d += timedelta(days=1)
    return dias


def _taxa_do_dia(por_data, dia):
    """Fixing do dia; faltando, o último publicado antes — o que a convenção
    manda e o que o próprio NY Fed faz no índice."""
    if dia in por_data:
        return por_data[dia]
    anteriores = [d for d in por_data if d < dia]
    if not anteriores:
        raise ErroFed('there is no SOFR fixing published for {data} or before it — '
                      'widen the period', data='{:%d/%m/%Y}'.format(dia))
    return por_data[max(anteriores)]


def compor_por_indice(indice, inicio, fim, base=360.0):
    """taxa = (Index_fim / Index_início − 1) · 360 / D — o atalho do NY Fed."""
    d0, d1 = para_data(inicio), para_data(fim)
    if d0 not in indice or d1 not in indice:
        faltando = d0 if d0 not in indice else d1
        raise ErroFed('the SOFR Index has no publication for {data}',
                      data='{:%d/%m/%Y}'.format(faltando))
    dias = (d1 - d0).days
    if dias <= 0:
        raise ErroDeDado('the period has no calendar days')
    return (indice[d1] / indice[d0] - 1.0) * base / dias


# ── base histórica ──────────────────────────────────────────────────────────

_ultima_sync = {'quando': 0.0}


def carregar_base():
    """``{data: {campo: valor}}`` a partir dos registros da base (DB-first)."""
    return bases.para_dict(bases.carregar(ARQUIVO))


def salvar_base(taxas):
    bases.salvar(ARQUIVO, bases.para_lista(taxas, [c for c, _ in CAMPOS] + ['indice']))


def _mesclar(base, linhas):
    """Acrescenta o que falta; nunca sobrescreve valor já gravado."""
    novos = 0
    for chave, valores in linhas.items():
        linha = base.setdefault(chave, {})
        for campo, valor in valores.items():
            if valor is not None and campo not in linha:
                linha[campo] = valor
                novos += 1
    return novos


def _janela(inicio, fim):
    coletado = {}
    for f in serie_sofr(inicio, fim):
        coletado.setdefault(f.data.isoformat(), {})['overnight'] = f.taxa
    dados = _buscar('{}/sofrai/search.json?startDate={:%Y-%m-%d}&endDate={:%Y-%m-%d}'
                    .format(API, inicio, fim))
    linhas = dados.get('refRates', []) if isinstance(dados, dict) else dados
    for linha in linhas:
        if linha.get('type') != 'SOFRAI':
            continue
        alvo = coletado.setdefault(para_data(linha['effectiveDate']).isoformat(), {})
        for campo, origem in (('media30', 'average30day'), ('media90', 'average90day'),
                              ('media180', 'average180day')):
            if linha.get(origem) is not None:
                alvo[campo] = float(linha[origem]) / 100.0
        if linha.get('index') is not None:
            alvo['indice'] = float(linha['index'])
    return coletado


def sincronizar(profundo=False, dias_recentes=45):
    """Atualiza a base com o que o NY Fed publicou. ``profundo=True`` varre
    desde 02/04/2018, ano a ano."""
    with bases.trava():
        base = carregar_base()
        antes = len(base)
        relatorio = {'novos': 0, 'janelas': 0, 'erros': []}
        hoje = date.today()
        if profundo:
            intervalos, inicio = [], INICIO_DA_SERIE
            while inicio < hoje:
                fim = min(date(inicio.year + 1, inicio.month, inicio.day), hoje)
                intervalos.append((inicio, fim))
                inicio = fim
        else:
            intervalos = [(hoje - timedelta(days=dias_recentes), hoje)]
        for inicio, fim in intervalos:
            try:
                novos = _mesclar(base, _janela(inicio, fim))
                relatorio['novos'] += novos
                relatorio['janelas'] += 1
                if novos:
                    salvar_base(base)
            except ErroFed as exc:
                relatorio['erros'].append('{:%Y}: {}'.format(inicio, exc))
        if relatorio['novos'] or antes == 0:
            salvar_base(base)
        relatorio.update({'dias_antes': antes, 'dias_depois': len(base)})
        return relatorio


@dataclass
class HistoricoSOFR:
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
        return [c for c, _ in CAMPOS if c in presentes]

    @property
    def inicio(self):
        datas = self.datas
        return datas[0] if datas else None

    @property
    def fim(self):
        datas = self.datas
        return datas[-1] if datas else None

    def por_data(self):
        return {para_data(d): linha for d, linha in self.taxas.items()}

    def em(self, referencia):
        alvo = para_data(referencia).isoformat()
        candidatas = [d for d in sorted(self.taxas) if d <= alvo]
        if not candidatas:
            return None, {}
        escolhida = candidatas[-1]
        return para_data(escolhida), dict(self.taxas[escolhida])

    def janela(self, inicio, fim):
        i, f = para_data(inicio).isoformat(), para_data(fim).isoformat()
        return HistoricoSOFR({d: v for d, v in self.taxas.items() if i <= d <= f})


def carregar_historico(sincroniza=True):
    """A base local, atualizada no máximo a cada `INTERVALO_SYNC`. Falha de
    rede não derruba a tela — fica o que está gravado."""
    if sincroniza and time.time() - _ultima_sync['quando'] > INTERVALO_SYNC:
        _ultima_sync['quando'] = time.time()
        try:
            sincronizar(profundo=False)
        except (ErroDeFonte, OSError):
            pass
    return HistoricoSOFR.da_base()
