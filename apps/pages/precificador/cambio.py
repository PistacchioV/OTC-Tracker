# -*- coding: utf-8 -*-
"""Câmbio — o boletim de fechamento (PTAX) de qualquer moeda do BCB.

O mesmo endpoint do Olinda serve dólar, euro, iene, libra e as demais — o que
muda é o código. Vem sempre o par contra o real (``cotacao``) e a paridade
contra o dólar (``paridade``), e é a janela para trás que resolve fim de
semana, feriado e o dia corrente antes das 13h.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional

from apps.pages.precificador import rede
from apps.pages.precificador.calendario import para_data
from apps.pages.precificador.erros import ErroDeFonte

API_MOEDA = ('https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/'
             'CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,'
             'dataFinalCotacao=@dataFinalCotacao)?@moeda=\'{moeda}\''
             '&@dataInicial=\'{inicio}\'&@dataFinalCotacao=\'{fim}\'&$format=json')


class ErroCambio(ErroDeFonte):
    """Falha ao obter cotação de câmbio."""


@dataclass(frozen=True)
class Ptax:
    data: date
    compra: Optional[float]
    venda: float
    moeda: str = 'USD'
    paridade_compra: Optional[float] = None
    paridade_venda: Optional[float] = None


def ptax_moeda(codigo, referencia=None, tolerancia=10):
    """Boletim de fechamento da moeda na data (ou o último anterior, até
    ``tolerancia`` dias para trás)."""
    codigo = (codigo or 'USD').upper()
    fim = para_data(referencia) if referencia else date.today()
    inicio = date.fromordinal(fim.toordinal() - tolerancia)
    url = API_MOEDA.format(moeda=codigo, inicio='{:%m-%d-%Y}'.format(inicio),
                           fim='{:%m-%d-%Y}'.format(fim))
    try:
        dados = rede.obter_json(url, timeout=25)
    except rede.ErroRede as exc:
        raise ErroCambio('could not fetch the {moeda} fixing: {motivo}',
                         moeda=codigo, motivo=str(exc)) from exc
    linhas = [x for x in (dados.get('value') or [])
              if x.get('tipoBoletim') == 'Fechamento' and x.get('cotacaoVenda')]
    if not linhas:
        raise ErroCambio(
            'the Central Bank published no {moeda} closing bulletin between {inicio} '
            'and {fim}. The closing comes out around 13:00 on business days.',
            moeda=codigo, inicio='{:%d/%m/%Y}'.format(inicio), fim='{:%d/%m/%Y}'.format(fim))
    linha = linhas[-1]
    return Ptax(
        data=para_data(linha['dataHoraCotacao'][:10]),
        compra=float(linha['cotacaoCompra']), venda=float(linha['cotacaoVenda']),
        moeda=codigo,
        paridade_compra=float(linha['paridadeCompra']) if linha.get('paridadeCompra') else None,
        paridade_venda=float(linha['paridadeVenda']) if linha.get('paridadeVenda') else None)
