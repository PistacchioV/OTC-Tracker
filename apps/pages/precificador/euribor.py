# -*- coding: utf-8 -*-
"""EURIBOR — taxas diárias do Banco da Finlândia, com base histórica local.

O Suomen Pankki publica o EURIBOR de 1 semana, 1, 3, 6 e 12 meses num
relatório SSRS que exporta CSV. O relatório mostra seis meses por vez, a
partir de uma data escolhida num seletor — um postback ASP.NET, que não passa
pela URL. Para alcançar o resto:

1. GET na página do visualizador, guardando ``__VIEWSTATE`` e cookies;
2. POST com o índice da janela e o botão "View Report";
3. a resposta traz ``ReportSession`` e ``ControlID``;
4. GET em ``Reserved.ReportViewerWebControl.axd`` com os dois e ``Format=CSV``.

A base local (`DATA_DIR/tools/euribor_historico.json`, espelhada em
`db/tools/euribor_historico.db`) só acrescenta: uma
data gravada nunca é sobrescrita, e o que a fonte deixar de publicar continua
aqui. O seed versionado traz 2006 em diante.
"""
import csv
import io
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List

from apps.pages.precificador import bases, rede
from apps.pages.precificador.calendario import para_data
from apps.pages.precificador.erros import ErroDeFonte

RELATORIO = '/tilastot/markkina-_ja_hallinnolliset_korot/euriborkorot_pv_chrt_en'
RAIZ = 'https://reports.suomenpankki.fi'
VISUALIZADOR = '{}/WebForms/ReportViewerPage.aspx?report={}&output='.format(RAIZ, RELATORIO)
EXPORTACAO_DIRETA = '{}/WebForms/ReportViewerPage.aspx?report={}&output=CSV'.format(RAIZ, RELATORIO)
HANDLER = '{}/Reserved.ReportViewerWebControl.axd'.format(RAIZ)
PAGINA = ('https://www.suomenpankki.fi/en/statistics/data-and-charts/interest-rates/'
          'charts/korot_kuviot_en/euriborkorot_pv_chrt_en/')

ARQUIVO = 'euribor_historico.json'
INTERVALO_SYNC = 30 * 60

CAMPO_SELETOR = 'ReportViewer1$ctl04$ctl03$ddValue'
CAMPO_BOTAO = 'ReportViewer1$ctl04$ctl00'

TENORES = ['1 week', '1 month', '3 month', '6 month', '12 month']
TENOR_MESES = {'1 week': 0.25, '1 month': 1, '3 month': 3, '6 month': 6, '12 month': 12}


class ErroEuribor(ErroDeFonte):
    """Falha ao obter ou interpretar o relatório do Banco da Finlândia."""


@dataclass(frozen=True)
class FixingEuribor:
    data: date
    tenor: str
    taxa: float          # decimal ao ano (0.02154 = 2,154%)


class Sessao:
    """Uma sessão do visualizador SSRS, com cookies e viewstate."""

    def __init__(self, timeout=90):
        self._rede = rede.SessaoNavegada(timeout=timeout)
        self._campos = {}
        self._html = ''

    def abrir(self):
        self._html = self._get(VISUALIZADOR).decode('utf-8', 'replace')
        self._campos = self._ler_campos(self._html)
        return self

    def _get(self, url, referer=None):
        try:
            return self._rede.get(url, referer=referer)
        except rede.ErroRede as exc:
            raise ErroEuribor('Bank of Finland: {motivo}', motivo=str(exc)) from exc

    def _post(self, url, dados):
        try:
            return self._rede.post(url, dados, referer=VISUALIZADOR).decode('utf-8', 'replace')
        except rede.ErroRede as exc:
            raise ErroEuribor('Bank of Finland: {motivo}', motivo=str(exc)) from exc

    @staticmethod
    def _ler_campos(html):
        return dict(re.findall(r'<input type="hidden" name="([^"]+)"[^>]*value="([^"]*)"', html))

    def janelas(self):
        """As janelas do seletor: (índice, data inicial)."""
        if not self._html:
            self.abrir()
        saida = []
        for indice, rotulo in re.findall(r'<option[^>]*value="(\d+)">([^<]+)</option>', self._html):
            limpo = rotulo.replace('&nbsp;', ' ').strip()
            try:
                saida.append((indice, datetime.strptime(limpo, '%d %b %Y').date()))
            except ValueError:
                continue
        return saida

    def csv_da_janela(self, indice):
        if not self._campos:
            self.abrir()
        dados = dict(self._campos)
        dados.update({'__EVENTTARGET': '', '__EVENTARGUMENT': '',
                      CAMPO_SELETOR: indice, CAMPO_BOTAO: 'View Report',
                      'ReportViewer1$ctl05$ctl00$CurrentPage': '1'})
        resposta = self._post(VISUALIZADOR, dados)
        sessao = re.search(r'ReportSession=([a-z0-9]+)', resposta)
        controle = re.search(r'ControlID=([a-f0-9]+)', resposta)
        if not (sessao and controle):
            raise ErroEuribor('the report viewer returned no report session — the page '
                              'may have changed')
        novos = self._ler_campos(resposta)
        if novos:
            self._campos = novos
        url = ('{}?ReportSession={}&Culture=1033&CultureOverrides=True&UICulture=1033'
               '&UICultureOverrides=True&ReportStack=1&ControlID={}&OpType=Export'
               '&FileName=euribor&ContentDisposition=OnlyHtmlInline&Format=CSV'
               .format(HANDLER, sessao.group(1), controle.group(1)))
        return self._get(url, referer=VISUALIZADOR).decode('utf-8-sig', 'replace')

    def fechar(self):
        self._rede.close()


def parse_csv(conteudo):
    """Lê o CSV do gráfico; o bloco da tabela no rodapé é descartado."""
    leitor = csv.reader(io.StringIO(conteudo))
    try:
        next(leitor)
    except StopIteration:
        return []
    fixings = []
    for linha in leitor:
        if len(linha) < 4:
            continue
        tenor, bruto_data, bruto_taxa = linha[0], linha[2], linha[3]
        if tenor not in TENOR_MESES:
            continue
        try:
            d = datetime.strptime(bruto_data.strip()[:10], '%m/%d/%Y').date()
            taxa = float(bruto_taxa.strip()) / 100.0
        except (ValueError, IndexError):
            continue
        fixings.append(FixingEuribor(d, tenor, taxa))
    return sorted(fixings, key=lambda f: (f.data, TENORES.index(f.tenor)))


def janela_atual(timeout=60):
    """A janela padrão (últimos ~6 meses), sem sessão."""
    try:
        bruto = rede.obter(EXPORTACAO_DIRETA, timeout=timeout).decode('utf-8-sig', 'replace')
    except rede.ErroRede as exc:
        raise ErroEuribor('could not fetch the report: {motivo}', motivo=str(exc)) from exc
    return parse_csv(bruto)


# ── base ────────────────────────────────────────────────────────────────────

_ultima_sync = {'quando': 0.0}


def carregar_base():
    """``{data: {tenor: taxa}}`` a partir dos registros da base (DB-first)."""
    return bases.para_dict(bases.carregar(ARQUIVO))


def salvar_base(taxas):
    limpo = {d: {t: taxas[d][t] for t in TENORES if t in taxas[d]} for d in taxas}
    bases.salvar(ARQUIVO, bases.para_lista(limpo, TENORES))


def mesclar(base, fixings):
    """Só acrescenta: o primeiro valor visto é o que estava publicado no dia."""
    novos = 0
    for f in fixings:
        linha = base.setdefault(f.data.isoformat(), {})
        if f.tenor not in linha:
            linha[f.tenor] = f.taxa
            novos += 1
    return novos


def sincronizar(profundo=False, passo=5, limite=None):
    """``profundo=False`` busca só a janela corrente; ``True`` percorre o
    seletor inteiro (uma janela a cada ``passo``) para semear a base."""
    with bases.trava():
        base = carregar_base()
        antes = len(base)
        relatorio = {'novos': 0, 'janelas': 0, 'erros': []}
        if not profundo:
            try:
                relatorio['novos'] = mesclar(base, janela_atual())
                relatorio['janelas'] = 1
            except ErroEuribor as exc:
                relatorio['erros'].append(str(exc))
        else:
            sessao = Sessao().abrir()
            try:
                janelas = sessao.janelas()
                escolhidas = janelas[::passo]
                if janelas and janelas[-1] not in escolhidas:
                    escolhidas.append(janelas[-1])
                if limite:
                    escolhidas = escolhidas[:limite]
                for indice, inicio in escolhidas:
                    try:
                        novos = mesclar(base, parse_csv(sessao.csv_da_janela(indice)))
                        relatorio['novos'] += novos
                        relatorio['janelas'] += 1
                        if novos:
                            salvar_base(base)
                    except ErroEuribor as exc:
                        relatorio['erros'].append('{:%b/%Y}: {}'.format(inicio, exc))
            finally:
                sessao.fechar()
        if relatorio['novos'] or antes == 0:
            salvar_base(base)
        relatorio.update({'dias_antes': antes, 'dias_depois': len(base)})
        return relatorio


@dataclass
class CurvaEuribor:
    taxas: Dict[str, Dict[str, float]]

    @classmethod
    def da_base(cls):
        return cls(carregar_base())

    @property
    def datas(self):
        return [para_data(d) for d in sorted(self.taxas)]

    @property
    def tenores(self):
        presentes = {t for linha in self.taxas.values() for t in linha}
        return [t for t in TENORES if t in presentes]

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

    def curva_do_dia(self, referencia=None):
        _, linha = self.em(referencia or date.today())
        return [{'tenor': t, 'meses': TENOR_MESES[t], 'taxa': linha[t]}
                for t in TENORES if t in linha]

    def janela(self, inicio, fim):
        i, f = para_data(inicio).isoformat(), para_data(fim).isoformat()
        return CurvaEuribor({d: linha for d, linha in self.taxas.items() if i <= d <= f})


def carregar(sincroniza=True):
    """A base local, atualizada no máximo a cada `INTERVALO_SYNC`."""
    if sincroniza and time.time() - _ultima_sync['quando'] > INTERVALO_SYNC:
        _ultima_sync['quando'] = time.time()
        try:
            sincronizar(profundo=False)
        except (ErroDeFonte, OSError):
            pass
    return CurvaEuribor.da_base()
