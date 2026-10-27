"""Tema e aparência: um atributo, aplicado ANTES do primeiro paint, e um arquivo
de cada (rebranding de 19/10/2026).

O tema antigo eram três atributos (`data-bs-theme`, `data-menu-color`,
`data-topbar-color`) que andavam juntos pelo LayoutCustomizer do app.js — e
desandavam quando alguém trocava só um. No tema novo a casca inteira lê UM:
`data-bs-theme`. Destaque, papel de parede e vidro são atributos próprios, e
o modo opaco (máquina sem GPU) é a classe `is-solid`.

O que este script protege:

  1. o <head> aplica a aparência de forma SÍNCRONA e ANTES do CSS — senão a
     página pisca no tema errado até o otc.js rodar;
  2. a preferência antiga (`__OTCTRACKER_CONFIG__`) é migrada, e o modo opaco
     continua obedecendo `__OTC_TRACKER_FX__` (a saída de emergência);
  3. o botão sol/lua troca pelo `otcUI.set` (que grava e reaplica), e a troca
     suprime as transições dos DOIS lados (JS e CSS);
  4. UM arquivo de cada: o <head> carrega só vendors.min.css + otc.css, o
     rodapé só vendors.min.js + otc.js + clipboard.js, e nenhum template volta
     a carregar as camadas removidas.

Não encosta em dado real: lê arquivos-fonte.
"""
import io
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
os.chdir(ROOT)

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(path):
    return io.open(path, encoding='utf-8').read()


HEAD = read('apps/templates/partials/head-css.html')
FOOT = read('apps/templates/partials/footer-scripts.html')
JS = read('apps/static/js/otc.js')
SCSS = read('apps/static/scss/otc.scss')

print('\n== 1. a aparência vai para o <html> antes do CSS ==')
script_at = HEAD.find('<script>')
css_at = HEAD.find('otc.css')
check('o <head> tem o script inline', script_at >= 0, True)
check('e ele vem ANTES do otc.css', 0 <= script_at < css_at, True)
for attr in ('data-bs-theme', 'data-accent', 'data-wall', 'data-glass'):
    check('o script escreve %s' % attr, ("setAttribute('%s'" % attr) in HEAD, True)
check('e marca o modo opaco', "classList.add('is-solid')" in HEAD, True)
check('auto segue o sistema', 'prefers-color-scheme: dark' in HEAD, True)

print('\n== 2. preferência antiga e saída de emergência ==')
check('lê __OTC_TRACKER_UI__', '__OTC_TRACKER_UI__' in HEAD and '__OTC_TRACKER_UI__' in JS, True)
check('migra __OTCTRACKER_CONFIG__', '__OTCTRACKER_CONFIG__' in HEAD, True)
check('o modo opaco obedece __OTC_TRACKER_FX__', '__OTC_TRACKER_FX__' in HEAD and '__OTC_TRACKER_FX__' in JS, True)
check('e o otc.js detecta GPU por software', 'swiftshader|llvmpipe|software|basic render' in JS, True)

print('\n== 3. o botão sol/lua ==')
btn = re.search(r'function initThemeButton\(\)\s*\{.*?\n  \}\n', JS, re.DOTALL)
btn = btn.group(0) if btn else ''
check('initThemeButton encontrado', bool(btn), True)
check('troca pelo otcUI.set', 'otcUI.set({ theme:' in btn, True)
check('o JS suprime as transições na troca', "classList.add('otc-theme-switching')" in JS, True)
check('e as devolve', "classList.remove('otc-theme-switching')" in JS, True)
check('o CSS tem a regra',
      bool(re.search(r'html\.otc-theme-switching \*[^{]*\{\s*transition:\s*none\s*!important', SCSS)), True)

print('\n== 4. um arquivo de cada ==')
check('o <head> carrega vendors.min.css + otc.css, e só',
      re.findall(r'}}/css/([\w.-]+\.css)', HEAD), ['vendors.min.css', 'otc.css'])
# + o `date-std.js` (§675): o padrão de TODO datepicker, que tem de rodar antes
# dos scripts da página para embrulhar o flatpickr antes de alguma tela criar um
check('o rodapé carrega vendors.min.js + otc.js + clipboard.js + date-std.js, e só',
      re.findall(r'}}/js/([\w.-]+\.js)', FOOT), ['vendors.min.js', 'otc.js', 'clipboard.js', 'date-std.js'])
check('só existe UM scss', sorted(f for f in os.listdir('apps/static/scss')), ['otc.scss'])
GONE = ('app.css', 'app.min.css', 'visual-refresh.css', 'streamflow.css', 'tools.css', 'js/app.js',
        'js/config.js', 'visual-refresh.js', 'streamflow.js', 'sidenav-drilldown.js', 'sticky-tables.js')
volta = []
for dp, dn, fn in os.walk('apps/templates'):
    for f in fn:
        if f.endswith('.html'):
            txt = read(os.path.join(dp, f))
            for g in GONE:
                if re.search(r'(src|href)="[^"]*' + re.escape(g), txt):
                    volta.append('%s -> %s' % (f, g))
check('nenhum template carrega as camadas removidas', volta, [])

print('\n== 5. o ícone do título vem do menu lateral ==')
LAYOUT = read('apps/templates/layouts/vertical.html')
check('o layout copia o ícone do item do menu para o título',
      '.menu-icon > :first-child' in LAYOUT and 'otc-page-product-icon' in LAYOUT, True)
check('e o faz logo depois do conteúdo, antes do rodapé',
      0 <= LAYOUT.find('endblock page_content') < LAYOUT.find('otc-page-product-icon') < LAYOUT.find("partials/footer.html"), True)

# O CSS de PLUGIN (daterangepicker, flatpickr) vai no `extra_css`, ANTES do
# otc.css: carregado no fim da página ele vence o tema, e o calendário saía
# branco com o texto claro no escuro (o Reference date do Pay/Rec, §701).
tardios = []
for raiz, _d, arqs in os.walk(os.path.join(ROOT, 'apps', 'templates', 'pages')):
    for a in arqs:
        if not a.endswith('.html'):
            continue
        t = io.open(os.path.join(raiz, a), encoding='utf-8').read()
        fim = t.find('{% endblock extra_css %}')
        if fim < 0:
            fim = t.find('{% block page_content %}')
        for m in re.finditer(r'plugins/(daterangepicker|flatpickr)/[^"]+\.css', t):
            if fim >= 0 and m.start() > fim:
                tardios.append(a)
check('CSS de calendário só no extra_css (antes do tema)', sorted(set(tardios)), [])

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
