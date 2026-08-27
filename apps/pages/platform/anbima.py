# -*- coding: utf-8 -*-
"""O calendário de dias úteis do app inteiro (ANBIMA + horário de Brasília).

É a horizontal que a vertical de Feriados deixou para trás de propósito
(CLAUDE.md §10): o SLA da esteira, o aging do CGD, os schedulers e o D-1 das
recons perguntam tudo aqui. Movida VERBATIM do `routes.py`, nomes preservados —
inclusive o `_pcx_is_bizday`, que nasceu no Pending Confirmation Spreadsheet e
virou a resposta de "é dia útil?" de meia dúzia de features.

O ESTADO (o set de feriados, os flags de carga) mora NESTE módulo: teste que
precisa de um calendário de mentira troca `_ANBIMA_HOLIDAYS`/`_anbima_loaded`
aqui, não no `routes` (o alias de lá é da FUNÇÃO; um alias de set ficaria
apontando para o objeto velho quando `_load_anbima` rebinda o global).

Há DUAS cargas do mesmo arquivo (`_load_anbima` e `_anbima_holidays`), como
sempre houve no `routes.py`: uma lê pelo `data_path` (com a queda para a cópia
empacotada) e a outra pelo diretório de dados cru. Unificá-las muda
comportamento de borda e é outra decisão — a fatia move, não refatora.
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from apps.pages.data_paths import data_path

log = logging.getLogger('otc_tracker')

# ──────────────────────────────────────────────────────────────────────────
# Horário de Brasília
# ──────────────────────────────────────────────────────────────────────────
# Os agendamentos da aplicação (aviso de pendências às 19h, manutenção diária
# às 11h30) são horários do BRASIL. `datetime.now()` devolve o horário LOCAL do
# servidor, e a instância do time não roda necessariamente em BRT — foi por isso
# que o aviso das 19h não saiu na hora esperada.
#
# No Windows o `zoneinfo` depende do pacote `tzdata`, que pode não estar
# instalado; sem ele cai no offset fixo de -03:00, que vale o ano todo desde que
# o Brasil acabou com o horário de verão (2019). Não é uma aproximação
# arriscada: é o mesmo offset que o banco de fusos daria hoje.
try:
    from zoneinfo import ZoneInfo
    _BR_TZ = ZoneInfo('America/Sao_Paulo')
except Exception:                                   # noqa: BLE001
    _BR_TZ = timezone(timedelta(hours=-3))


def _br_now():
    """Agora em horário de Brasília, como datetime ingênuo (sem tzinfo) — é
    assim que o resto do código compara, formata e nomeia arquivos por data."""
    return datetime.now(_BR_TZ).replace(tzinfo=None)


# ── ANBIMA calendar ───────────────────────────────────────────────────────────

_ANBIMA_HOLIDAYS: set = set()
_anbima_loaded = False


def _load_anbima():
    global _ANBIMA_HOLIDAYS, _anbima_loaded
    if _anbima_loaded:
        return
    try:
        path = data_path('anbima.json')
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        _ANBIMA_HOLIDAYS = {d['date'] for d in data}
    except Exception as exc:
        log.warning('[ANBIMA] Failed to load anbima.json: %s', exc)
        _ANBIMA_HOLIDAYS = set()
    _anbima_loaded = True


def _prev_anbima_bizday(ref):
    """Return the previous ANBIMA business day (D-1) before `ref` (date/datetime).
    Skips weekends and ANBIMA holidays."""
    _load_anbima()
    cur = ref - timedelta(days=1)
    while cur.weekday() >= 5 or cur.strftime('%Y-%m-%d') in _ANBIMA_HOLIDAYS:
        cur -= timedelta(days=1)
    return cur


def _anbima_bizdays_between(d1, d2):
    """Count ANBIMA business days from d1 (inclusive) up to d2 - 1 (d2 exclusive).

    Counts the first date and stops at the second date minus one day, using the
    ANBIMA holiday calendar (weekdays minus ANBIMA holidays).
    """
    _load_anbima()
    if d1 >= d2:
        return 0
    count, cur = 0, d1
    while cur < d2:
        if cur.weekday() < 5 and cur.strftime('%Y-%m-%d') not in _ANBIMA_HOLIDAYS:
            count += 1
        cur += timedelta(days=1)
    return count


def _weekday_bizdays_between(d1, d2):
    """Count weekday-only days from d1 (inclusive) up to d2 - 1 (d2 exclusive).

    Counts the first date and stops at the second date minus one day, using only
    weekdays (Mon-Fri), with no holiday calendar.
    """
    if d1 >= d2:
        return 0
    count, cur = 0, d1
    while cur < d2:
        if cur.weekday() < 5:
            count += 1
        cur += timedelta(days=1)
    return count


def _last_anbima_bizday_of_month(year, month):
    """Last ANBIMA business day of the given year/month (datetime)."""
    _load_anbima()
    nm = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    cur = nm - timedelta(days=1)
    while cur.weekday() >= 5 or cur.strftime('%Y-%m-%d') in _ANBIMA_HOLIDAYS:
        cur -= timedelta(days=1)
    return cur


def _pcx_is_bizday(d):
    _load_anbima()
    return d.weekday() < 5 and d.strftime('%Y-%m-%d') not in _ANBIMA_HOLIDAYS


_anbima_hols_cache = None


def _anbima_holidays():
    global _anbima_hols_cache
    if _anbima_hols_cache is None:
        # Andaime declarado: o `_B3_DATA_DIR` ainda é do `routes` (é o mesmo
        # `data_dir()` do app), e os testes o trocam LÁ (`R._B3_DATA_DIR = tmp`).
        from apps.pages import routes
        try:
            with open(os.path.join(routes._B3_DATA_DIR, 'anbima.json'), encoding='utf-8') as fh:
                _anbima_hols_cache = {(x.get('date') if isinstance(x, dict) else x)
                                      for x in json.load(fh)}
        except (IOError, json.JSONDecodeError):
            _anbima_hols_cache = set()
    return _anbima_hols_cache


def _anbima_biz_diff(start_dt, end_dt):
    """ANBIMA business days in (start, end] — the 'diferença de dias úteis'."""
    if not start_dt or not end_dt or end_dt <= start_dt:
        return 0
    hols, n, cur = _anbima_holidays(), 0, start_dt
    while cur < end_dt:
        cur += timedelta(days=1)
        if cur.weekday() < 5 and cur.strftime('%Y-%m-%d') not in hols:
            n += 1
    return n


def _anbima_add_biz(start_dt, n):
    """start advanced by n ANBIMA business days."""
    if not start_dt:
        return None
    hols, cur, left = _anbima_holidays(), start_dt, n
    while left > 0:
        cur += timedelta(days=1)
        if cur.weekday() < 5 and cur.strftime('%Y-%m-%d') not in hols:
            left -= 1
    return cur
