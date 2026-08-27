# -*- coding: utf-8 -*-
"""As leituras que alimentam o parser: RefData, Subjacente e os mapas B3.

São os espelhos em Python dos loaders do `otc-fileupload.js` — mesma regra dos
dois lados, com o `check_boxparse.py` provando que concordam.
"""
import json
import os
import traceback

from apps.pages import otc_boxparse
from apps.pages.data_paths import data_path


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`."""
    from apps.pages import routes
    return routes


def refdata_by_accronym():
    """{accronym → {spn, counterparty, taxId}} — o `loadRefData` do JS: indexa
    por COMMODITIES ACCRONYM e, quando a chave ainda está livre, por FX CASH
    ACCRONYM (o primeiro a chegar vence, como no `if (fxAcr && !map[fxAcr])`)."""
    out = {}
    try:
        with open(os.path.join(_routes()._B3_DATA_DIR, 'RefData.json'), encoding='utf-8') as fh:
            rows = json.load(fh) or []
    except Exception:
        _routes().log.warning('[boxscan] RefData.json ilegível:\n%s', traceback.format_exc())
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry = {'spn': row.get('SPN') or '',
                 'counterparty': row.get('COUNTERPARTY') or '',
                 'taxId': row.get('TAX ID') or ''}
        comm = str(row.get('COMMODITIES ACCRONYM') or '').upper().strip()
        fx = str(row.get('FX CASH ACCRONYM') or '').upper().strip()
        if comm:
            out[comm] = entry
        if fx and fx not in out:
            out[fx] = entry
    return out


def subjacente_index():
    """{código ou ticker → {commodity, fatorConversao}} — o `loadSubjacenteData`
    do JS, incluindo o merge que prefere o fator de centavos quando o mesmo
    código aparece com fatores conflitantes (§77.1)."""
    idx = {}
    try:
        fp = data_path('Subjacente.json')
        with open(fp, encoding='utf-8') as fh:
            rows = json.load(fh) or []
    except Exception:
        _routes().log.warning('[boxscan] Subjacente.json ilegível:\n%s', traceback.format_exc())
        return idx
    for row in rows:
        if not isinstance(row, dict):
            continue
        commodity = row.get('Commodity') or ''
        fator = otc_boxparse._parse_fator(row.get('Fator Conversao'))
        for key in (str(row.get('Codigo do Ativo Subjacente') or '').strip(),
                    str(row.get('Ticker') or '').strip()):
            if not key:
                continue
            prev = idx.get(key)
            if not prev:
                idx[key] = {'commodity': commodity, 'fatorConversao': fator}
                continue
            if otc_boxparse._is_cents_factor(fator) or (
                    prev.get('fatorConversao') is None and fator is not None):
                prev['fatorConversao'] = fator
            if not prev.get('commodity') and commodity:
                prev['commodity'] = commodity
    return idx


def commodity_maps():
    """Mapas Commodities × B3 vindos do CADASTRO (/mapping), não de literais —
    é a mesma fonte que o JS consome via /api/mappings/commodities-b3 (§131).

    Cada entrada é POR TRADE TYPE ({mkt: {'V': …, 'A': …}}): a coluna TRADE
    TYPE restringe a linha à vanilla ou à asiática (BOTH/vazio = as duas), e é
    isso que permite ao BRT_IPE ter a linha SPECIAL só da asiática e uma PREFIX
    só da vanilla (§251). `calculate_b3_id` aceita também o formato antigo
    (valor plano = vale para os dois), então mapa de teste/fixture não quebra."""
    fixed, dynamic, holiday, special = {}, {}, {}, {}

    def _flags(row):
        tt = str(row.get('TRADE TYPE') or '').strip().upper()
        if tt == 'VANILLA':
            return ('V',)
        if tt == 'ASIAN':
            return ('A',)
        return ('V', 'A')                          # BOTH ou em branco

    for row in _routes()._mapping_rows('commodities-b3'):
        typ = str(row.get('TYPE') or '').upper()
        mkt = str(row.get('MARKET') or '').strip().upper()
        code = str(row.get('B3 CODE') or '')      # sem trim: 'C ' tem espaço no código
        cal = str(row.get('HOLIDAY CALENDAR') or '').strip()
        if mkt and cal:
            holiday[mkt] = cal
        if typ == 'SPECIAL' and mkt:
            # SPECIAL leva os DOIS códigos: o do mês (B3 CODE) e o distante
            # (B3 CODE FAR). Qual dos dois sai é lógica — a distância até a
            # liquidação —, mas os códigos em si saem do cadastro.
            for f in _flags(row):
                special.setdefault(mkt, {})[f] = {
                    'near': code, 'far': str(row.get('B3 CODE FAR') or '').strip()}
            continue
        if not mkt or not code:
            continue
        alvo = dynamic if 'PREFIX' in typ else fixed
        for f in _flags(row):
            alvo.setdefault(mkt, {})[f] = code
    return {'fixed': fixed, 'dynamic': dynamic, 'holiday': holiday, 'special': special}

