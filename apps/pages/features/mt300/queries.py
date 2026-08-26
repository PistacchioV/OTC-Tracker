# -*- coding: utf-8 -*-
"""As leituras do card: as linhas da mensagem, as listas e o último desfecho."""
import re

from apps.pages.features.mt300 import domain
from apps.pages.features.mt300.infra import persistence


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`): o cadastro do /mapping e os
    normalizadores de SPN/nome são plataforma."""
    from apps.pages import routes
    return routes


def targets():
    """[(cnpj_digitos, spn, [tokens do nome])] do cadastro `mt300`."""
    R = _routes()
    alvos = []
    for r in R._mapping_rows('mt300'):
        cnpj = re.sub(r'\D', '', str(r.get('CNPJ', '') or ''))
        spn = R._norm_spn(r.get('SPN', ''))
        tokens = [t for t in (R._pc_norm(w) for w in str(r.get('COUNTERPARTY', '') or '').split()) if t]
        if cnpj or spn or tokens:
            alvos.append((cnpj, spn, tokens))
    return alvos


def _data(v):
    """A data como a tabela do MT300 mostra: `dd/mm/aaaa`.

    Passa pelo `_parse_date_any` em vez de repassar o texto: as fontes gravam a
    data em mais de uma grafia, e é o mesmo formato do resto do app — a mesa lê
    o e-mail ao lado das telas."""
    d = _routes()._parse_date_any(v)
    return d.strftime('%d/%m/%Y') if d else str(v or '')


def rows(ref):
    """As linhas do e-mail: NDF Vanilla do dia, só das contrapartes cadastradas."""
    R = _routes()
    alvos = targets()
    if not alvos:
        return []
    out = []
    for d in persistence.load_day(ref):
        if not isinstance(d, dict):
            continue
        cnpj = re.sub(r'\D', '', str(d.get('TaxID', '') or ''))
        spn = R._norm_spn(d.get('SPN', ''))
        nome = R._pc_norm(d.get('Client', '') or d.get('Acronym', '') or '')
        if not domain.matches(cnpj, spn, nome, alvos):
            continue
        qty = domain.signed_qty(R._conf_to_float(d.get('Notional')), d.get('Direction'))
        rate = R._conf_to_float(d.get('Rate'))
        # Other Quantity é o notional CONVERTIDO pela taxa — o contravalor em
        # BRL. Ele não existe como campo: é derivado, e por isso segue o sinal
        # do Quantity.
        other = (qty * rate) if (qty is not None and rate is not None) else None
        out.append({
            'instrument': str(d.get('Instrument', '') or ''),
            'deal': str(d.get('Deal', '') or ''),
            'cpty': str(d.get('Client', '') or d.get('Acronym', '') or ''),
            'booking': _data(d.get('TradeDate')),
            # Fixing Date = a coluna **Last Fixing Date** do New Deals. Numa
            # média (Avg Rate Forward) o que interessa é a ÚLTIMA fixação, que é
            # quando a taxa fecha; a primeira só abre a janela.
            'fixing': _data(d.get('LastFixingDate')),
            'settlement': _data(d.get('SettlementDate')),
            # Position: a operação dita por extenso, do lado da NOSSA entidade —
            # a entidade sai da LE do deal (JPM/MGT/LAWTON), não de um literal:
            # a mesma operação é bookada em entidades diferentes, e a mensagem é
            # confirmada por quem a bookou.
            'position': domain.position(d),
            # VALOR em duas casas e TAXA em oito: são coisas diferentes. O
            # contravalor é dinheiro e se lê em centavos; a taxa é o que converte
            # um no outro, e duas casas fariam dois strikes distintos aparecerem
            # iguais na mensagem (é a mesma regra do padrão de tabela, §3).
            'other_qty': ('{:,.2f}'.format(other) if other is not None else ''),
            'other_units': str(d.get('OtherQuantityCurrency', '') or ''),
            'qty_ccy': str(d.get('QuantityCurrency', '') or ''),
            'qty': ('{:,.2f}'.format(qty) if qty is not None else ''),
            # Formatado a partir do NÚMERO, não repassado como texto: o campo já
            # chega com oito casas, mas repassá-lo deixaria o formato preso à
            # gravação de quem produziu o deal.
            'rate': ('{:,.8f}'.format(rate) if rate is not None else ''),
        })
    return out


def recipients():
    return persistence.load_recipients()


def status():
    return persistence.read_status()
