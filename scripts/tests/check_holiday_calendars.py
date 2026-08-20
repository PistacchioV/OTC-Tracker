#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_holiday_calendars.py — os calendarios da tela de feriados.

A lista de calendarios estava escrita a mao em CINCO lugares: o
`_HOLIDAY_FILE_MAP` do `routes.py`, o `CALENDAR_CONFIG` e o `HC_CAL_COLORS` do
`apps-holidays-calendar.js`, as pills da barra lateral e o `<select>` do modal.
Nenhum deles pode conhecer um calendario criado pela tela — e o que acontecia
sem erro nenhum era: o calendario novo nao aparecia em lugar nenhum, e o
`/api/holidays/save` respondia "Unknown calendar" para um nome que a propria
pagina teria acabado de mostrar.

Agora a lista e DADO (`holiday-calendars.json`, semeado com os onze de sempre).
O que este script prova:

  1. o seed do servidor e o fallback do navegador sao a MESMA lista, campo a
     campo — o fallback existe para o fetch que falha, e divergindo ele mostra
     uma tela que nao e a de ninguem;
  2. o template NAO tem mais pill nem `<option>` escrita a mao (com elas, a
     lista do JS e a do HTML voltariam a divergir na primeira criacao);
  3. o parser da planilha: coluna A a data, coluna B a descricao, e o cabecalho
     descartado por NAO SER DATA — nao por posicao;
  4. o slug vira nome de arquivo e classe de CSS, entao so aceita
     `[a-z0-9_-]`: e ele que entra num `os.path.join`;
  5. a cor sai da paleta e foge das que ja estao em uso;
  6. o rotulo `page` da notificacao existe nos TRES mapas de destino.

Le o `routes.py`, o JS e o template; nao escreve nada e nao toca em dado real.
"""
import datetime
import io
import json
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, 'scripts', 'tests'))

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8').read()


JS = read('apps/static/js/pages/apps-holidays-calendar.js')
TPL = read('apps/templates/pages/holidays-calendar.html')
SRC = read('apps/pages/routes.py')

print('\n== 1. o seed do servidor x o fallback do navegador ==')
check('o seed tem os onze de sempre',
      [c['name'] for c in R._HOLIDAY_CAL_SEED],
      ['ANBIMA', 'BURSA', 'CBY_AGS', 'EURIBOR', 'ICEAGS', 'IPE', 'LME',
       'NYMEX', 'PLATTS-ASIA', 'PLATTS-EUROPE', 'SOFR'])

# O fallback do JS e um literal; le-lo por regex e o preco de nao ter um
# runtime de JS aqui — o que importa e comparar os CAMPOS, um a um.
bloco = JS.split('const HC_CAL_FALLBACK = [', 1)[1].split('];', 1)[0]
fallback = []
for linha in re.findall(r'\{([^}]*)\}', bloco):
    row = {}
    for k, v in re.findall(r"(\w+):\s*'([^']*)'", linha):
        row[k] = v
    fallback.append(row)
check('o fallback tem onze linhas', len(fallback), 11)
for i, seed in enumerate(R._HOLIDAY_CAL_SEED):
    fb = fallback[i] if i < len(fallback) else {}
    for campo in ('name', 'file', 'class', 'drag', 'color'):
        check('   %s.%s' % (seed['name'], campo), fb.get(campo), seed[campo])

print('\n== 2. a tela nao tem mais lista escrita a mao ==')
corpo = TPL.split('{% block page_content %}', 1)[1].split('{% endblock page_content %}', 1)[0]
# Uma pill escrita no HTML nunca sumiria nem apareceria com o registro.
check('nenhuma pill de calendario no HTML',
      len(re.findall(r'class="external-event', corpo)), 0)
# O `<select>` fica com a opcao-guia desabilitada e nada mais.
opcoes = re.findall(r'<option[^>]*>([^<]*)</option>', corpo)
check('o select so tem a opcao-guia', opcoes, ['Select a Calendar'])
check('e o JS monta as duas coisas',
      'function hcRenderCalendarList' in JS, True)
check('a lista vem do endpoint', "fetch('/api/holidays/calendars')" in JS, True)
check('com queda para o fallback', 'cals = HC_CAL_FALLBACK' in JS, True)

print('\n== 3. o botao, o modal e a dropzone ==')
check('botao Create New Calendar', 'btn-new-calendar' in corpo, True)
check('modal proprio', 'id="calendar-modal"' in corpo, True)
check('campo do nome', 'id="hc-cal-name"' in corpo, True)
check('dropzone', 'id="hc-dropzone"' in corpo, True)
check('aceita so .xlsx/.xlsm', 'accept=".xlsx,.xlsm"' in corpo, True)
# A dropzone tem de reagir ao arrastar; sem o dragover ela e so um botao.
check('o JS trata dragover/drop', "dz.addEventListener(ev" in JS and "'drop'" in JS, True)
# Tokens do tema, nunca --bs-*: senao a dropzone sai branca no tema escuro.
css = TPL.split('{% block extra_css %}', 1)[1].split('{% endblock extra_css %}', 1)[0]
dz_css = css.split('.hc-dropzone {', 1)[1].split('}', 1)[0]
check('a dropzone usa --ins-*, nao --bs-*',
      ('--ins-' in dz_css, '--bs-' in dz_css), (True, False))

print('\n== 4. a planilha: coluna A a data, coluna B a descricao ==')
linhas = [
    ['Holiday', 'Description', 'Holiday Type'],          # cabecalho
    [datetime.datetime(2026, 1, 1), 'New Year', 'Full'],  # data de verdade
    ['2026-04-03', 'Good Friday', 'Full'],                # data como texto
    ['2026-12-25 00:00:00', 'Christmas', 'Full'],         # texto com hora
    [datetime.date(2026, 5, 1), 'Labour Day', 'Full'],    # date sem hora
    [datetime.datetime(2026, 4, 3), 'Repetida', 'Full'],  # data ja vista
    [None, None, None],                                   # linha em branco
    ['2026-07-04', '', 'Full'],                           # sem descricao
    ['Total', 4, ''],                                     # rodape
]
got = R._holiday_rows_from_sheet(linhas, 'CME')
check('so as linhas que sao feriado', [r['date'] for r in got],
      ['2026-01-01', '2026-04-03', '2026-05-01', '2026-12-25'])
check('e ordenadas por data', got == sorted(got, key=lambda r: r['date']), True)
check('a descricao e o titulo', got[0]['title'], 'New Year')
check('o calendario vai na linha', {r['calendar'] for r in got}, {'CME'})
# O cabecalho e descartado por nao ser data, e nao por ser a linha 1: uma
# planilha exportada sem cabecalho perderia o primeiro feriado.
sem_cab = R._holiday_rows_from_sheet([['2026-01-01', 'New Year', 'Full']], 'CME')
check('planilha SEM cabecalho nao perde o primeiro feriado', len(sem_cab), 1)
# A terceira coluna existe na planilha e nao entra: o pedido e explicito.
check('Holiday Type nao vira campo', sorted(got[0].keys()),
      ['calendar', 'date', 'title'])
check('planilha sem data nenhuma devolve vazio',
      R._holiday_rows_from_sheet([['a', 'b', 'c']], 'X'), [])

print('\n== 5. o slug vira caminho em disco e classe de CSS ==')
check('espaco vira _', R._holiday_cal_slug('Platts Asia'), 'platts_asia')
check('hifen tambem', R._holiday_cal_slug('PLATTS-EUROPE'), 'platts_europe')
check('acento e pontuacao caem', R._holiday_cal_slug('Ação B3!'), 'a_o_b3')
check('nao sobra _ nas pontas', R._holiday_cal_slug('  CME  '), 'cme')
# Sem isso o nome do calendario escreveria fora da pasta de dados.
check('travessia de caminho nao sobrevive',
      R._holiday_cal_slug('../../etc/passwd'), 'etc_passwd')
check('nome sem letra nem digito devolve vazio', R._holiday_cal_slug('///'), '')
for nome in ('CME', 'Platts Asia', '../x'):
    slug = R._holiday_cal_slug(nome)
    check('   %r produz slug seguro' % nome,
          bool(re.fullmatch(r'[a-z0-9_-]*', slug)), True)

print('\n== 6. a cor sai da paleta e foge das usadas ==')
check('a paleta nao repete cor',
      len(R._HOLIDAY_CAL_PALETTE), len(set(R._HOLIDAY_CAL_PALETTE)))
check('nem colide com as dos onze',
      sorted(set(R._HOLIDAY_CAL_PALETTE) &
             {c['color'] for c in R._HOLIDAY_CAL_SEED}), [])
check('toda cor da paleta e hex de 6 digitos',
      all(re.fullmatch(r'#[0-9a-f]{6}', c) for c in R._HOLIDAY_CAL_PALETTE), True)
# Duas pills da mesma cor sao dois calendarios que se leem como um.
quase_todas = [{'color': c} for c in R._HOLIDAY_CAL_PALETTE[:-1]]
check('com uma cor livre, e ela que sai',
      R._holiday_pick_color(quase_todas), R._HOLIDAY_CAL_PALETTE[-1])
check('esgotada a paleta, ainda devolve cor dela',
      R._holiday_pick_color([{'color': c} for c in R._HOLIDAY_CAL_PALETTE])
      in R._HOLIDAY_CAL_PALETTE, True)
check('cor nova nunca fica sem CSS: o JS gera a regra',
      'function hcInjectCalendarCss' in JS, True)
check('e so para as classes geradas',
      "/^hc-cal-[a-z0-9_-]+$/.test(cls)" in JS, True)

print('\n== 7. o Save aceita calendario criado pela tela ==')
# Era um mapa fixo: o calendario novo levava "Unknown calendar" do endpoint que
# a propria pagina chama ao gravar um feriado avulso.
check('o mapa fixo saiu do codigo', '_HOLIDAY_FILE_MAP' in SRC, False)
check('o Save resolve pelo registro', '_holiday_file_for(calendar_name)' in SRC, True)
check('ANBIMA resolve', R._holiday_file_for('ANBIMA'), 'anbima.json')
check('cego a caixa e espaco', R._holiday_file_for(' sofr '), 'sofr.json')
check('calendario que nao existe devolve None', R._holiday_file_for('XPTO'), None)
check('nome vazio devolve None', R._holiday_file_for(''), None)
# O registro mora na pasta dos dados e NAO e uma agenda de feriados.
bloco_sys = SRC.split('def api_fx_holiday_schedules', 1)[1] \
               .split('_SYSTEM_FILES = {', 1)[1].split('}', 1)[0]
check('o registro nao vira FX holiday schedule',
      '_HOLIDAY_CAL_FILE' in bloco_sys, True)

print('\n== 8. o aviso do sino tem destino nos TRES mapas ==')
check('routes', R._NOTIF_PAGE_URL.get('Holidays Calendar'), '/holidays-calendar')
check('topbar',
      "'Holidays Calendar':      '/holidays-calendar'"
      in read('apps/templates/partials/topbar.html'), True)
check('service worker',
      "'Holidays Calendar': '/holidays-calendar'"
      in read('apps/static/js/sw-push.js'), True)

print('\n== 9. o texto novo nasce em ingles e tem data-lang ==')
CHAVES = ['hc-new-holiday', 'hc-new-calendar', 'hc-new-calendar-title', 'hc-hint',
          'hc-calendar', 'hc-cal-name', 'hc-cal-file', 'hc-dz', 'hc-dz-spec',
          'hc-close', 'hc-import']
LANGS = {l: json.loads(read('apps/static/data/translations/%s.json' % l))
         for l in ('en', 'br', 'es')}
for k in CHAVES:
    check('%s nos tres idiomas' % k,
          sorted(l for l in LANGS if not str(LANGS[l].get(k, '')).strip()), [])
    check('   e no template', 'data-lang="%s"' % k in corpo, True)

print('\nFALHAS: %d' % len(fails))
sys.exit(1 if fails else 0)
