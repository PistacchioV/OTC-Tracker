# -*- coding: utf-8 -*-
"""O calendário do Outlook de quem clicou Sync, pelo COM (win32com/MAPI) — o
mesmo caminho do box scan (`otc_boxscan._win32`). Só Windows: fora dele (a dev
no macOS) levanta `OutlookUnavailable`, e a tela diz que o Sync precisa do
Outlook da máquina.

Cada pessoa roda a PRÓPRIA instância (CLAUDE.md §9), mas o link do e-mail
aponta para a máquina de quem o mandou — e aí quem clica Sync não é o dono do
Outlook. O calendário vem pela caixa do e-mail cadastrado
(`GetSharedDefaultFolder`, que só abre a agenda de outra pessoa com
permissão de delegado) e, se ela não resolver, pelo calendário padrão do
perfil SÓ quando o perfil é de quem clicou: sem essa conferência as reuniões
do dono da máquina (título, participantes, link do Zoom com a senha) iam para
a Home de outra pessoa, e a presença dela passava a dizer "em reunião" pela
agenda alheia. Fora disso, `CalendarNotAccessible`.

O filtro de data do `Restrict` é texto no formato do Windows de quem roda —
`mm/dd` num, `dd/mm` noutro. Tenta-se os dois e o que volta é conferido de
novo em Python pela data REAL de cada item: um formato lido ao contrário traz
o mês errado, nunca um evento a mais na tela.
"""
import logging
import re
from datetime import datetime

log = logging.getLogger('otc_tracker')

OL_FOLDER_CALENDAR = 9
_CANCELED = (5, 7)                 # olMeetingCanceled, olMeetingReceivedAndCanceled
_MAX_ITEMS = 400                   # recorrência sem fim não vira laço sem fim
# a reunião do JPM é por ZOOM (mesa, 20/10/2026): o link vem no Local ou no
# corpo do convite (`https://<conta>.zoom.us/j/<id>?pwd=…`)
_JOIN_RE = re.compile(r'https://[\w.-]*zoom\.us/(?:j|w|my|s)/[^\s"<>]+', re.I)
_FORMATOS = ('%m/%d/%Y %I:%M %p', '%d/%m/%Y %H:%M')


class OutlookUnavailable(EnvironmentError):
    """Sem win32com ou sem Outlook nesta máquina."""


class CalendarNotAccessible(Exception):
    """O Outlook desta máquina é de outra pessoa e a caixa de quem clicou
    não abriu por ele."""


def _naive(dt):
    # O pywin32 devolve a hora LOCAL marcada como UTC: tira-se o fuso e fica a
    # hora que o Outlook mostra.
    try:
        return datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    except Exception:                                    # noqa: BLE001
        return None


def _profile_emails(ns):
    """Os endereços do PERFIL do Outlook desta máquina (contas + o usuário
    Exchange), em minúsculas."""
    out = set()
    try:
        for acc in ns.Accounts:
            a = str(getattr(acc, 'SmtpAddress', '') or '').strip().lower()
            if a:
                out.add(a)
    except Exception:                                    # noqa: BLE001
        pass
    try:
        ex = ns.CurrentUser.AddressEntry.GetExchangeUser()
        a = str(getattr(ex, 'PrimarySmtpAddress', '') or '').strip().lower() if ex is not None else ''
        if a:
            out.add(a)
    except Exception:                                    # noqa: BLE001
        pass
    return out


def is_profile_owner(email, profile):
    """`email` é do dono do perfil? Pelo endereço inteiro ou pela parte antes
    do `@` (o phonebook e o Exchange nem sempre usam o mesmo domínio:
    `jpmorgan.com` × `jpmchase.com`)."""
    email = str(email or '').strip().lower()
    if not email:
        return False
    local = email.split('@', 1)[0]
    return any(p == email or p.split('@', 1)[0] == local for p in profile)


def _calendar(ns, email):
    if email:
        try:
            rec = ns.CreateRecipient(email)
            rec.Resolve()
            if rec.Resolved:
                return ns.GetSharedDefaultFolder(rec, OL_FOLDER_CALENDAR)
        except Exception:                                # noqa: BLE001
            log.warning('[user-home] calendário de %s não abriu pela caixa', email)
    if not is_profile_owner(email, _profile_emails(ns)):
        raise CalendarNotAccessible(email or '(no e-mail)')
    return ns.GetDefaultFolder(OL_FOLDER_CALENDAR)


def _item(it):
    start, end = _naive(it.Start), _naive(it.End)
    if start is None or end is None:
        return None
    try:
        if int(getattr(it, 'MeetingStatus', 0) or 0) in _CANCELED:
            return None
    except Exception:                                    # noqa: BLE001
        pass
    body = ''
    try:
        body = str(it.Body or '')[:20000]
    except Exception:                                    # noqa: BLE001
        pass
    loc = str(getattr(it, 'Location', '') or '')
    m = _JOIN_RE.search(loc) or _JOIN_RE.search(body)
    nomes = [n.strip() for n in str(getattr(it, 'RequiredAttendees', '') or '').split(';') if n.strip()]
    return {
        'id': '%s|%s' % (str(getattr(it, 'EntryID', '') or '')[-24:], start.isoformat()),
        'title': str(it.Subject or '').strip(),
        'start': start.isoformat(), 'end': end.isoformat(),
        'location': str(getattr(it, 'Location', '') or '').strip(),
        'all_day': bool(getattr(it, 'AllDayEvent', False)),
        'busy': int(getattr(it, 'BusyStatus', 2) or 0),
        'organizer': str(getattr(it, 'Organizer', '') or '').strip(),
        'attendees': nomes[:12],
        'join_url': m.group(0).rstrip('.,;)') if m else '',
    }


def _restrict(items, start, end, fmt):
    flt = "[Start] < '%s' AND [End] > '%s'" % (end.strftime(fmt), start.strftime(fmt))
    found = items.Restrict(flt)
    out, n = [], 0
    it = found.GetFirst()
    while it is not None and n < _MAX_ITEMS:
        n += 1
        try:
            ev = _item(it)
            if ev and ev['start'] < end.isoformat() and ev['end'] > start.isoformat():
                out.append(ev)
        except Exception:                                # noqa: BLE001
            log.warning('[user-home] item do calendário ilegível', exc_info=True)
        it = found.GetNext()
    return out


def read_calendar(email, start, end):
    """Os eventos entre `start` e `end` (datetimes ingênuos, hora local),
    ordenados. Levanta `OutlookUnavailable` fora do Windows."""
    from apps.pages import otc_boxscan
    try:
        _w, pythoncom = otc_boxscan._win32()
    except EnvironmentError as e:
        raise OutlookUnavailable(str(e))
    pythoncom.CoInitialize()
    try:
        try:
            ns = _w.Dispatch('Outlook.Application').GetNamespace('MAPI')
        except Exception as e:                           # noqa: BLE001
            raise OutlookUnavailable('Outlook did not open: %s' % e)
        cal = _calendar(ns, email)
        eventos = []
        for fmt in _FORMATOS:
            items = cal.Items
            items.Sort('[Start]')
            items.IncludeRecurrences = True
            try:
                eventos = _restrict(items, start, end, fmt)
            except Exception:                            # noqa: BLE001
                log.warning('[user-home] filtro de data %r recusado pelo Outlook', fmt, exc_info=True)
                continue
            if eventos:
                break
        vistos, out = set(), []
        for ev in sorted(eventos, key=lambda e: (e['start'], e['title'])):
            if ev['id'] not in vistos:
                vistos.add(ev['id'])
                out.append(ev)
        return out
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:                                # noqa: BLE001
            pass
