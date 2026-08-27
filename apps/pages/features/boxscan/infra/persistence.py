# -*- coding: utf-8 -*-
"""Onde cada produto grava o arquivo-dia, e a gravação com a regra do navegador."""
import json
import os
from datetime import datetime

from apps.pages.features.boxscan import domain


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`."""
    from apps.pages import routes
    return routes


# O diretório sai por FUNÇÃO porque as constantes de cache do routes são
# reapontadas pelos testes — congelar o valor aqui leria o cache real.
PRODUCTS = {
    'ndf': {'label': 'NDF Comm', 'layout': 'ndf',
            'dir': lambda: _routes().NDF_COMM_CACHE_DIR, 'suffix': '_ndfcomm.json'},
    'opt': {'label': 'Opt Comm', 'layout': 'opt',
            'dir': lambda: _routes().CACHE_BASE_DIR, 'suffix': '_optcomm.json'},
}


def persist_deals(product, deals):
    """Grava os deals de um e-mail no arquivo do dia, com a MESMA regra do
    caminho do navegador: a chave é **Deal + Acronym**; já existente vira
    'Amend' preservando o B3 ID (uma operação já registrada não perde o número),
    novo entra como 'New'. Retorna (novos, amendados)."""
    cfg = PRODUCTS[product]
    R = _routes()
    new_n = amend_n = 0
    by_file = {}
    for d in deals:
        try:
            ref = datetime.strptime(d.get('TradeDate', ''), '%d/%m/%Y')
        except (ValueError, TypeError):
            ref = datetime.now()
        fpath = os.path.join(cfg['dir'](), ref.strftime('%Y'), ref.strftime('%m'),
                             ref.strftime('%Y%m%d') + cfg['suffix'])
        by_file.setdefault(fpath, []).append(d)

    for fpath, items in by_file.items():
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        # ler → alterar → gravar inteiro sob o lock: o _atomic_write_json sozinho
        # evita arquivo pela metade, não perda de atualização de outro usuário.
        with R._cache_lock:
            try:
                with open(fpath, encoding='utf-8') as fh:
                    existing = json.load(fh)
                if not isinstance(existing, list):
                    existing = [existing]
            except (IOError, json.JSONDecodeError):
                existing = []
            idx = {}
            for i, e in enumerate(existing):
                if isinstance(e, dict):
                    idx[((e.get('Deal') or '').strip(),
                         (e.get('Acronym') or '').strip())] = i
            for d in items:
                key = ((d.get('Deal') or '').strip(), (d.get('Acronym') or '').strip())
                pos = idx.get(key)
                if pos is None:
                    existing.append(d)
                    idx[key] = len(existing) - 1
                    new_n += 1
                    continue
                old = existing[pos]
                keep_b3 = str(old.get('B3_ID') or '').strip()
                changed = [k for k, v in d.items()
                           if k not in ('Status', 'B3_ID', 'Maker', 'Checker')
                           and str(old.get(k, '') or '').strip() != str(v or '').strip()]
                if not changed:
                    continue                       # e-mail repetido: nada a fazer
                merged = dict(old)
                merged.update(d)
                merged['B3_ID'] = keep_b3
                merged['Status'] = 'Amend'
                merged['Maker'] = old.get('Maker') or domain.MAKER_SID
                merged['Checker'] = ''             # amend exige nova aprovação
                merged['AmendChanged'] = sorted(set(old.get('AmendChanged') or []) | set(changed))
                existing[pos] = merged
                amend_n += 1
            R._atomic_write_json(fpath, existing)
    return new_n, amend_n

