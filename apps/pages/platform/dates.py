# -*- coding: utf-8 -*-
"""O parse de datas compartilhado — as grafias que convivem nos caches e nas
telas (dd/mm/aaaa do filtro, ISO do JSON, yyyymmdd dos arquivos-dia).

Movido VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). O CALENDÁRIO
(dias úteis, feriados) é outro módulo — `platform/anbima.py`: aqui é só ler e
escrever data, lá é decidir se ela conta.
"""
from datetime import datetime

_EN_MONTH_NAMES = (
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
)


def _parse_date_any(val):
    """Parse a date string in any supported format → datetime.date, or None.

    Handles the smart-filter input (dd/mm/yyyy) and the formats stored in the
    JSON cache (yyyy-mm-dd, yyyy-mm-dd HH:MM:SS, yyyymmdd, dd-mm-yyyy).
    """
    val = str(val or '').strip()
    if not val:
        return None
    val = val.split('T')[0].split(' ')[0]  # drop any time component
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%Y%m%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def _parse_deal_date(s):
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y%m%d'):
        try:
            return datetime.strptime(s.strip(), fmt)
        except (ValueError, AttributeError):
            pass
    return None
