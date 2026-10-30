# -*- coding: utf-8 -*-
"""O liga/desliga do ENVIO AUTOMÁTICO dos cards do Control Panel (§722).

Os seis cards que mandam e-mail sozinhos têm um interruptor no Control Panel.
LIGADO é o padrão (card que ninguém mexeu, arquivo ausente). Desligado, o
disparo AUTOMÁTICO do card não sai até ser ligado de novo — o Run manual do
card continua valendo (quem clica decidiu).

Quem pergunta é o laço de cada card, ANTES de reservar o horário
(`ligado(card)`), e a leitura é ESTRITA: banco ocupado/ilegível LEVANTA e o
laço tenta de novo na volta seguinte. Lido como "ligado", o e-mail de um card
desligado sairia; lido como "desligado", o de um card ligado se perderia.

O horário que cai com o card desligado é CONSUMIDO (desfecho `disabled` no
status do card): religar à tarde não manda o e-mail da manhã que ficou para
trás — o envio volta no próximo horário.
"""
import os

from apps.pages import data_store as _store

# Os cards com envio automático de e-mail — os ids do `_CONTROL_PANEL_CARDS`.
# Card novo com laço que manda e-mail entra aqui E chama `ligado()` no
# disparo (o `check_cp_auto_send.py` varre os laços).
CARDS = ('intradaytasks', 'confescalation', 'initiativealerts',
         'manualdealsea', 'baccea', 'mt300',
         # não manda e-mail: GRAVA a planilha do Pending no share às 10:45 —
         # entrou pelo mesmo interruptor a pedido da equipe (29/10/2026)
         'pendingspreadsheet')

# O desfecho gravado no status do card quando o horário caiu desligado.
DESLIGADO = 'disabled'


def _routes():
    from apps.pages import routes
    return routes


def arquivo():
    return os.path.join(_routes()._DAILY_METRIC_DIR, 'auto_send.json')


def _ler():
    """O documento cru, ESTRITO: só o arquivo ausente é {} (tudo ligado)."""
    try:
        d = _store.read(arquivo())
    except FileNotFoundError:
        return {}
    return d if isinstance(d, dict) else {}


def _ligado_em(doc, card):
    e = doc.get(card)
    return not (isinstance(e, dict) and e.get('enabled') is False)


def estado():
    """{card: {'enabled', 'by', 'at'}} dos seis. Levanta se não deu para ler."""
    doc = _ler()
    out = {}
    for c in CARDS:
        e = doc.get(c) if isinstance(doc.get(c), dict) else {}
        out[c] = {'enabled': _ligado_em(doc, c), 'by': e.get('by', ''), 'at': e.get('at', '')}
    return out


def ligado(card):
    """O envio automático do card está ligado? Levanta se não deu para ler."""
    return _ligado_em(_ler(), card)


def definir(card, enabled, sid='', nome=''):
    """Liga/desliga um card. Ler → alterar → gravar sob o `_cache_lock`."""
    if card not in CARDS:
        raise ValueError(card)
    R = _routes()
    with R._cache_lock:
        doc = _ler()
        doc[card] = {'enabled': bool(enabled), 'by': nome or sid,
                     'sid': sid, 'at': R._br_now().strftime('%d/%m/%Y %H:%M')}
        os.makedirs(R._DAILY_METRIC_DIR, exist_ok=True)
        R._atomic_write_json(arquivo(), doc)
    R.log.warning('[auto-send] %s %s por %s', card, 'LIGADO' if enabled else 'DESLIGADO', sid)
    return doc[card]
