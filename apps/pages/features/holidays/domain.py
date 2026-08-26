# -*- coding: utf-8 -*-
"""As regras do Holidays Calendar. Puras — sem I/O, sem Flask.

O registro (`CAL_SEED`) é a fonte ÚNICA das quatro superfícies da tela: as pills
da barra lateral, as opções do `<select>` do modal, o mapa de cores do popup e o
CSS. Eram cinco listas escritas à mão, e nenhuma delas podia conhecer um
calendário criado pela própria tela (HANDOFF §288).

O `HC_CAL_FALLBACK` do `apps-holidays-calendar.js` é a cópia desta lista para o
fetch que falha, e o `check_holiday_calendars.py` compara as duas campo a campo.
"""
import random
import re
from datetime import datetime

CAL_FILE = 'holiday-calendars.json'
CAL_SEED = [
    {'name': 'ANBIMA', 'file': 'anbima.json',
     'class': 'bg-primary-subtle text-primary',
     'drag': 'bg-primary-subtle text-primary border-primary', 'color': '#0d6efd'},
    {'name': 'BURSA', 'file': 'bursa.json',
     'class': 'bg-secondary-subtle text-secondary',
     'drag': 'bg-secondary-subtle text-secondary border-secondary', 'color': '#6c757d'},
    {'name': 'CBY_AGS', 'file': 'cby_ags.json',
     'class': 'bg-success-subtle text-success',
     'drag': 'bg-success-subtle text-success border-success', 'color': '#198754'},
    {'name': 'EURIBOR', 'file': 'euribor.json',
     'class': 'bg-danger-subtle text-danger',
     'drag': 'bg-danger-subtle text-danger border-danger', 'color': '#dc3545'},
    {'name': 'ICEAGS', 'file': 'iceags.json',
     'class': 'bg-info-subtle text-info',
     'drag': 'bg-info-subtle text-info border-info', 'color': '#0dcaf0'},
    {'name': 'IPE', 'file': 'ipe.json',
     'class': 'bg-warning-subtle text-warning',
     'drag': 'bg-warning-subtle text-warning border-warning', 'color': '#f59e0b'},
    {'name': 'LME', 'file': 'lme.json',
     'class': 'bg-dark-subtle text-dark',
     'drag': 'bg-dark-subtle text-dark border-dark', 'color': '#374151'},
    {'name': 'NYMEX', 'file': 'nymex.json',
     'class': 'bg-purple-subtle text-purple',
     'drag': 'bg-purple-subtle text-purple border-purple', 'color': '#8b5cf6'},
    {'name': 'PLATTS-ASIA', 'file': 'platts_asia.json',
     'class': 'bg-teal-subtle text-teal',
     'drag': 'bg-teal-subtle text-teal border-teal', 'color': '#14b8a6'},
    {'name': 'PLATTS-EUROPE', 'file': 'platts_europe.json',
     'class': 'bg-indigo-subtle text-indigo',
     'drag': 'bg-indigo-subtle text-indigo border-indigo', 'color': '#6366f1'},
    {'name': 'SOFR', 'file': 'sofr.json',
     'class': 'bg-pink-subtle text-pink',
     'drag': 'bg-pink-subtle text-pink border-pink', 'color': '#ec4899'},
]

# A cor do calendário novo é sorteada DESTA paleta, e não gerada por acaso: um
# `hsl` aleatório sai com saturação e luminosidade fora do padrão da tela, e mais
# cedo ou mais tarde ilegível sobre o fundo `rgba(cor, .15)` que a pill usa. São
# tons de mesma família e contraste dos onze de sempre. O sorteio evita as cores
# JÁ EM USO enquanto houver alguma livre — duas pills da mesma cor são dois
# calendários que se leem como um.
CAL_PALETTE = [
    '#0891b2', '#7c3aed', '#db2777', '#ea580c', '#65a30d', '#0d9488',
    '#4f46e5', '#b91c1c', '#a16207', '#0369a1', '#9333ea', '#047857',
]


def slug(name):
    """Nome do calendário → nome de arquivo.

    Só `[a-z0-9_-]`, porque este valor vira **caminho em disco e classe de
    CSS**: qualquer outra coisa é uma barra a caminho de um `os.path.join`.
    Nome sem letra nem dígito devolve `''`, e quem chama recusa a criação.
    """
    return re.sub(r'[^a-z0-9]+', '_', str(name or '').strip().lower()).strip('_')


def pick_color(rows):
    """Sorteia uma cor da paleta, preferindo as que ninguém está usando."""
    usadas = {str(r.get('color', '')).strip().lower() for r in rows}
    livres = [c for c in CAL_PALETTE if c not in usadas]
    return random.choice(livres or CAL_PALETTE)


def rows_from_sheet(rows, calendar_name):
    """Linhas da planilha → feriados `{date, title, calendar}`.

    A aba tem três colunas — Holiday, Description e Holiday Type —, e só as
    DUAS primeiras viram feriado: a data (coluna A) e o texto (coluna B).

    O cabeçalho não é pulado por POSIÇÃO e sim por não ser data: a linha 1 diz
    'Holiday' e não parseia, e é o mesmo teste que descarta a linha em branco no
    fim e o rodapé de total que planilha de mesa costuma trazer. Pular
    `rows[1:]` cegamente jogaria fora o primeiro feriado de uma planilha
    exportada sem cabeçalho.

    A data chega das duas formas que o Excel produz: `datetime` quando a célula
    é data de verdade, e texto `yyyy-mm-dd` quando a coluna foi salva como
    texto. Ler só uma delas deixa metade das planilhas voltando vazia.
    """
    import datetime as _dt        # o módulo; `datetime` no topo é a CLASSE
    out, vistos = [], set()
    for r in rows or []:
        if not r:
            continue
        bruto = r[0] if len(r) > 0 else None
        desc = r[1] if len(r) > 1 else ''
        if isinstance(bruto, datetime):
            iso = bruto.strftime('%Y-%m-%d')
        elif isinstance(bruto, _dt.date):
            iso = bruto.strftime('%Y-%m-%d')
        else:
            txt = str(bruto or '').strip()
            # `2026-01-01 00:00:00` é o que sai quando a data virou texto com
            # hora junto; o corte no espaço resolve sem um parser a mais.
            txt = txt.split(' ')[0].split('T')[0]
            try:
                iso = _dt.datetime.strptime(txt, '%Y-%m-%d').strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                continue
        titulo = str('' if desc is None else desc).strip()
        if not titulo:
            continue
        if iso in vistos:
            continue
        vistos.add(iso)
        out.append({'date': iso, 'title': titulo, 'calendar': calendar_name})
    out.sort(key=lambda x: x['date'])
    return out
