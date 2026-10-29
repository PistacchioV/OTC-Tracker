# -*- coding: utf-8 -*-
"""Quem está RED agora (§730) — horizontal: o card do Control Panel, as telas
de liquidação e os avisos de liquidação perguntam aqui.

A lista sai do Reference Data — a marca `RED` no registro que o card do
Control Panel (RED Clients — Rapid Exposure) põe e tira —, e não do arquivo da
última rodada: é o cadastro que a tela de Reference Data mostra. Marcado e
ainda PENDING (esperando aprovação) TAMBÉM conta: o crédito tem de ser
consultado do mesmo jeito.

Platform não importa feature nem nome do `routes` (busca atrasada).
"""
import base64
import json
import unicodedata

FLAG = 'RED'
_SUFIXOS = (' SA', ' S A', ' LTDA', ' LTD', ' INC', ' LLC', ' PLC', ' AG', ' NV', ' BV')


def _R():
    from apps.pages import routes
    return routes


def _digits(v):
    return ''.join(c for c in str(v or '') if c.isdigit()).lstrip('0')


def name_key(nome):
    """O nome para comparar: sem acento, pontuação e sufixo societário — a
    tela de liquidação escreve o nome que veio do arquivo do dia, e "BANCO X
    S.A." e "BANCO X SA" são o mesmo cliente."""
    s = unicodedata.normalize('NFKD', str(nome or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c)).upper()
    s = ''.join(c if c.isalnum() else ' ' for c in s)
    s = ' '.join(s.split())
    mudou = True
    while mudou and s:
        mudou = False
        for suf in _SUFIXOS:
            if s.endswith(suf) and len(s) > len(suf):
                s = s[:-len(suf)].strip()
                mudou = True
    return s


def flagged():
    """[{name, spn, taxid, eci, status}] das contrapartes marcadas."""
    registros, _ = _R()._b3_load('refdata')
    out = []
    for rec in registros or []:
        if isinstance(rec, dict) and rec.get(FLAG):
            eci = _digits(rec.get('ECI'))
            out.append({'name': str(rec.get('COUNTERPARTY', '') or '').strip(),
                        'spn': _digits(rec.get('SPN')),
                        'taxid': _digits(rec.get('TAX ID')),
                        'eci': eci,
                        'status': str(rec.get('STATUS', '') or '').strip().upper()})
    return out


def red_names(nomes):
    """Dos nomes dados, os que são de contraparte RED (na ordem, sem repetir)."""
    chaves = {name_key(c['name']) for c in flagged() if c.get('name')}
    chaves.discard('')
    out, vistos = [], set()
    for n in nomes or []:
        k = name_key(n)
        if k and k in chaves and k not in vistos:
            vistos.add(k)
            out.append(str(n).strip())
    return out


def anota_avisos(drafts):
    """Avisos de liquidação gerados com cliente RED: o cabeçalho
    `X-Red-Clients` (base64 de uma lista JSON de nomes) sai na resposta —
    qualquer que seja ela, o JSON dos ≤2 avisos ou o zip — e o
    `red-clients.js` da tela mostra o aviso antes do resultado. Melhor
    esforço: a consulta que falha não impede o aviso de sair."""
    try:
        nomes = red_names([d.get('counterparty', '') for d in drafts or []
                           if isinstance(d, dict)])
    except Exception:                                   # noqa: BLE001
        _R().log.warning('[red-clients] consulta dos avisos falhou', exc_info=True)
        return []
    if nomes:
        from flask import after_this_request
        valor = base64.b64encode(json.dumps(nomes, ensure_ascii=False).encode('utf-8')).decode('ascii')

        @after_this_request
        def _marca(resp):
            resp.headers['X-Red-Clients'] = valor
            resp.headers['Access-Control-Expose-Headers'] = 'X-Red-Clients'
            return resp
    return nomes
