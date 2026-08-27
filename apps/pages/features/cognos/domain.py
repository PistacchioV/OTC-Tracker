# -*- coding: utf-8 -*-
"""A regra pura do Cognos — a data de referência que o payload pede (hoje
quando não vem nada). Puro: sem `routes`, sem Flask, sem disco.
"""
from datetime import datetime


def _cog_ref_from(payload):
    ds = str((payload or {}).get('date', '') or '').strip()
    try:
        return datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        return datetime.now()
