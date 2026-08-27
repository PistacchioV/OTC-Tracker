# -*- coding: utf-8 -*-
"""As leituras do Holidays Calendar."""
from apps.pages.features.holidays.infra import persistence


def calendars():
    """Os calendários que a tela desenha.

    As pills da barra lateral, as opções do modal e o mapa de cores saem TODOS
    daqui — eram cinco listas escritas à mão, e nenhuma delas podia conhecer um
    calendário criado pela própria tela.
    """
    return persistence.calendars()


def fx_schedules():
    """As agendas que o FX holiday schedule oferece."""
    return persistence.fx_schedule_names()
