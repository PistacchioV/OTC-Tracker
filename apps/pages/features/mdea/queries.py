# -*- coding: utf-8 -*-
"""As leituras do card: as linhas de cada rotina, as listas e o status."""
from apps.pages.features.mdea import domain
from apps.pages.features.mdea.infra import persistence


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`): o cadastro do /mapping, o
    parse de datas e o teste de contraparte interna são plataforma."""
    from apps.pages import routes
    return routes


def le_names():
    """{LE → razão social do Reference Data}, do cadastro `le-spn`.

    O e-mail traz o nome por extenso porque quem recebe casa por ele, não pela
    sigla — e o nome é o do Reference Data, nunca um literal daqui: seria uma
    segunda grafia das mesmas entidades, para divergir na primeira correção."""
    out = {}
    for r in _routes()._mapping_rows('le-spn'):
        le = str(r.get('LE', '') or '').strip().upper()
        nome = str(r.get('NAME', '') or '').strip()
        if le and nome and le not in out:
            out[le] = nome
    return out


def date_key(v):
    """`dd/mm/aaaa` → `aaaa-mm-dd`, para comparar datas sem depender da grafia.

    As duas datas comparadas vêm de arquivos diferentes (o registro do par e o
    dia da rotina) e já apareceram com zero à esquerda de um jeito e de outro —
    comparar o texto cru erraria em silêncio, que aqui significa deixar uma
    operação dentro do e-mail (ou tirá-la) sem ninguém ver."""
    d = _routes()._parse_date_any(v)
    return d.strftime('%Y-%m-%d') if d else ''


def rows(kind, ref):
    """As linhas do e-mail do dia, por rotina."""
    R = _routes()
    nomes = le_names()
    if kind == 'fwdstart':
        # A referência é a Strike Set Date, e o arquivo do dia da fixação é
        # justamente onde o par foi gravado. O Deal que sai é o do VANILLA.
        #
        # FICA DE FORA o FWD Start cuja TRADE DATE é a própria Strike Set Date:
        # bookado e fixado no mesmo dia, ele não é uma operação que ficou
        # esperando o fixing — é um trade normal do dia, e o EA automático o
        # enxerga como qualquer outro. Pedir para excluí-lo tiraria da métrica
        # uma operação que não tem nada de manual.
        #
        # A data comparada é a do FWD START ORIGINAL, nunca a do vanilla: a do
        # vanilla É a Strike Set Date por construção do pareamento
        # (`_ndf_rebook_key`), então compará-la excluiria TODAS as linhas.
        alvo = date_key(ref.strftime('%d/%m/%Y'))
        out = []
        for r in persistence.rebook_rows(ref):
            if not str(r.get('Deal') or '').strip():
                continue
            fwd_trade = date_key(r.get('FwdStartTradeDate'))
            # Sem a data gravada não dá para afirmar que foi no mesmo dia, e o
            # lado seguro é INCLUIR: uma operação a mais no pedido é revisada
            # por quem recebe; uma a menos fica no EA sem ninguém ver.
            if fwd_trade and fwd_trade == alvo:
                R.log.info('[manual-deals-ea] FWD Start %s fora do e-mail: bookado e '
                           'fixado no mesmo dia (%s)',
                           r.get('FwdStartDeal') or r.get('Deal'), r.get('FwdStartTradeDate'))
                continue
            out.append(domain.row(r, nomes))
        return out
    out = []
    for d in persistence.day_deals('other-publishers', ref):
        if not str(d.get('Deal', '') or '').strip():
            continue
        # Só contraparte EXTERNA. A pergunta é a mesma que o Pending Confirmation
        # já responde, então é a mesma função: o teste é o ECONOMIC GROUP do
        # Reference Data, e não o nome começar em "BANCO" — que derrubaria Banco
        # Safra, Bradesco e Santander, que são clientes (CLAUDE.md §7).
        if R._pc_is_internal_counterparty(d.get('Client', ''), d.get('SPN', '')):
            continue
        out.append(domain.row(d, nomes))
    return out


def recipients():
    return persistence.load_recipients()


def status():
    return persistence.read_status()
