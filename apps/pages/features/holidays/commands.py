# -*- coding: utf-8 -*-
"""As escritas do Holidays Calendar: um feriado avulso e um calendário novo."""
import os
import traceback

from apps.pages.features.holidays import domain
from apps.pages.features.holidays.infra import persistence


class CalendarConflict(Exception):
    """O calendário não pode ser criado porque algo com esse nome já existe.

    Vira **409** no entrypoint, e não 400: o pedido está bem formado — o ESTADO
    é que recusa.
    """


def save_holiday(calendar_name, date, title):
    """Acrescenta um feriado. Devolve `(total, erro)`.

    A entrada guarda o `calendar` como veio, e é aí que mora uma verruga
    conhecida: o nome é usado como CHAVE de busca (cega a caixa) e como VALOR
    gravado (preservando a caixa), e a deduplicação compara o registro inteiro —
    então o mesmo feriado mandado como `sofr` e depois como `SOFR` entra duas
    vezes. Está registrado no `check_holidays_api.py` para não ser "corrigido"
    por acidente; consertar é mudança de comportamento.
    """
    filename = persistence.file_for(calendar_name)
    if not filename:
        return None, 'Unknown calendar: {}'.format(calendar_name)
    holidays = persistence.load_holidays(filename)
    nova = {'date': date, 'title': title, 'calendar': calendar_name}
    if nova not in holidays:
        holidays.append(nova)
        holidays.sort(key=lambda x: x.get('date', ''))
    erro = persistence.write_holidays(filename, holidays)
    return (None, erro) if erro else (len(holidays), None)


def create_calendar(nome, feriados):
    """Cria o calendário e a linha do registro. Devolve a linha criada.

    Levanta `CalendarConflict` nos três casos em que algo já ocupa o lugar. O
    terceiro — o ARQUIVO existir sem linha no registro — não é zelo: sobrescrever
    apagaria uma agenda que alguém pode estar consumindo pelo FX holiday
    schedule.

    Registro e arquivo são escritos SOB o lock, e a checagem de duplicidade é
    refeita dentro dele: dois uploads simultâneos do mesmo nome passariam os dois
    por um teste feito do lado de fora, e o segundo apagaria o primeiro.
    """
    from apps.pages import routes
    slug = domain.slug(nome)
    filename = '{}.json'.format(slug)
    with routes._cache_lock:
        rows = [dict(r) for r in persistence.calendars()]
        if any(str(r.get('name', '')).strip().upper() == nome for r in rows):
            raise CalendarConflict('Calendar {} already exists.'.format(nome))
        if any(str(r.get('file', '')).strip().lower() == filename for r in rows):
            raise CalendarConflict(
                'Another calendar already uses the file {}.'.format(filename))
        if os.path.exists(persistence.calendar_path(filename)):
            raise CalendarConflict(
                'The file {} already exists in the data folder.'.format(filename))
        classe = 'hc-cal-{}'.format(slug)
        linha = {'name': nome, 'file': filename, 'class': classe, 'drag': classe,
                 'color': domain.pick_color(rows)}
        try:
            routes._atomic_write_json(persistence.calendar_path(filename), feriados)
            rows.append(linha)
            routes._atomic_write_json(persistence.registry_path(), rows)
        except Exception:                                   # noqa: BLE001
            routes.log.error('[holidays] gravação do calendário %s falhou:\n%s',
                             nome, traceback.format_exc())
            raise
    return linha
