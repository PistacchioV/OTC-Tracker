# -*- coding: utf-8 -*-
"""A leitura do `Subjacente.json` — ao vivo, cacheada por mtime."""
import json
import os
import traceback

_cache = {'mtime': None, 'data': {}}


def active_by_class():
    """{Classe: {CÓDIGO_MAIÚSCULO: código como cadastrado}}, só os `ACTIVE`.

    Vem do Subjacente **ao vivo** (cacheado por mtime, como o resto que lê esse
    arquivo): ativo novo cadastrado no Index B3 aparece nas Cotações no mesmo
    dia, sem release e sem um segundo cadastro.

    Só os ACTIVE: um subjacente inativo não é escolha de tela — e ele continua
    no arquivo justamente para o histórico não perder o código.

    Ver a nota em `features/support/infra/persistence.py`: o `_B3_DATA_DIR` e o
    `log` ainda são do `routes`, e a busca é ATRASADA.
    """
    from apps.pages import routes
    fp = os.path.join(routes._B3_DATA_DIR, 'Subjacente.json')
    try:
        mt = os.path.getmtime(fp)
    except OSError:
        return {}
    if _cache['mtime'] != mt:
        try:
            with open(fp, encoding='utf-8') as fh:
                data = json.load(fh) or []
        except Exception:                                   # noqa: BLE001
            routes.log.warning('[quotes] Subjacente.json ilegível:\n%s',
                               traceback.format_exc())
            data = []
        por_classe = {}
        for rec in (data if isinstance(data, list) else []):
            if str(rec.get('STATUS', '') or '').strip().upper() != 'ACTIVE':
                continue
            classe = str(rec.get('Classe', '') or '').strip()
            code = str(rec.get('Codigo do Ativo Subjacente', '') or '').strip()
            if classe and code:
                por_classe.setdefault(classe, {}).setdefault(code.upper(), code)
        _cache['mtime'] = mt
        _cache['data'] = por_classe
    return _cache['data']
