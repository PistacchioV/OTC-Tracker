"""Toggle claro/escuro: o tema sao TRES atributos, nao um.

O botao sol/lua do topbar trocava so `data-bs-theme`. Mas quem pinta a sidebar
e escolhe qual logo aparece sao outros dois:

    data-bs-theme     -> corpo da pagina (e o fundo da sidebar em
                         visual-refresh.css)
    data-menu-color   -> tema da SIDEBAR e logo dela   (structure/_layout.scss)
    data-topbar-color -> tema do TOPBAR e logo dele    (structure/_topbar.scss)

Com um atributo so, a sidebar e o logo do topbar ficavam no visual anterior ate
a proxima navegacao — porque quem realinha os tres e o config.js, e ele so roda
no load. Por isso parecia "so acontecer em algumas paginas": item FOLHA do menu
navega e conserta sozinho; item com ramificacao so abre o submenu (o drill-down
nao recarrega nada), entao o estado quebrado fica a vista.

O que este script protege:

  1. os tres atributos andam juntos, nos dois caminhos do toggle;
  2. a troca passa pelo LayoutCustomizer do app — trocar por fora deixava a
     copia de config dele defasada e o primeiro resize regravava o tema antigo;
  3. o resize nao persiste mais o config inteiro;
  4. a classe que suprime as transicoes existe dos DOIS lados (JS e CSS);
  5. o CSS compilado realmente depende de menu-color/topbar-color — se um dia
     nao depender mais, o item 1 virou zelo desnecessario e este teste avisa.

Nao encosta em dado real: le arquivos-fonte.
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


VR_JS = read('apps/static/js/visual-refresh.js')
APP_JS = read('apps/static/js/app.js')
VR_CSS = read('apps/static/css/visual-refresh.css')
APP_CSS = read('apps/static/css/app.css')

# O corpo do toggle: de `function initThemeToggle` ate o fim da funcao seguinte.
m = re.search(r'function initThemeToggle\(\)\s*\{.*?\n  \}\n', VR_JS, re.DOTALL)
TOGGLE = m.group(0) if m else ''

print('\n== 1. o toggle troca os TRES atributos ==')
check('initThemeToggle encontrado', bool(TOGGLE), True)
for attr in ('data-bs-theme', 'data-menu-color', 'data-topbar-color'):
    check('o fallback escreve %s' % attr,
          'setAttribute("%s", t)' % attr in TOGGLE, True)
check('e persiste a cor do menu', 'c.menu.color = t' in TOGGLE, True)
check('e a cor do topbar', 'c.topbar.color = t' in TOGGLE, True)

print('\n== 2. a troca passa pelo LayoutCustomizer ==')
check('o toggle delega quando ele existe',
      'lc.changeTheme(t)' in TOGGLE, True)
check('app.js expoe a instancia',
      'window.layoutCustomizer = new LayoutCustomizer()' in APP_JS, True)
check('e a inicializa', 'window.layoutCustomizer.init()' in APP_JS, True)
# changeTheme e a fonte da verdade: tem de escrever os tres.
ct = re.search(r'changeTheme\(color\)\s*\{.*?\n    \}', APP_JS, re.DOTALL)
ct = ct.group(0) if ct else ''
for attr in ('data-bs-theme', 'data-menu-color', 'data-topbar-color'):
    check('changeTheme escreve %s' % attr,
          'setAttribute("%s", theme)' % attr in ct, True)

print('\n== 3. o resize nao regrava o config (tema junto) ==')
adj = re.search(r'_adjustLayout\(\)\s*\{.*?\n    \}', APP_JS, re.DOTALL)
adj = adj.group(0) if adj else ''
check('_adjustLayout encontrado', bool(adj), True)
check('nenhum ramo do resize persiste',
      re.findall(r'changeLeftbarSize\([^)]*\)', adj),
      ["changeLeftbarSize('offcanvas', false)",
       "changeLeftbarSize(size === 'on-hover' ? 'condensed' : 'condensed', false)",
       "changeLeftbarSize(size, false)"])

print('\n== 4. a supressao de transicoes existe dos dois lados ==')
CLS = 'vr-theme-switching'
check('o JS adiciona a classe', 'classList.add("%s")' % CLS in TOGGLE, True)
check('e a remove', 'classList.remove("%s")' % CLS in TOGGLE, True)
check('o CSS tem a regra', ('html.%s' % CLS) in VR_CSS, True)
check('e ela zera transition',
      bool(re.search(r'html\.%s.*?\{[^}]*transition:\s*none\s*!important' % CLS,
                     VR_CSS, re.DOTALL)), True)

print('\n== 5. o CSS realmente depende dos outros dois atributos ==')
# Se estes contadores forem a zero, trocar so o data-bs-theme passaria a bastar
# e o item 1 vira zelo desnecessario — melhor o teste avisar do que ninguem ver.
check('regras presas ao menu-color',
      len(re.findall(r'data-menu-color=', APP_CSS)) > 0, True)
check('regras presas ao topbar-color',
      len(re.findall(r'data-topbar-color=', APP_CSS)) > 0, True)
check('o logo da sidebar sai do menu-color',
      'data-menu-color=dark] .logo.logo-light' in APP_CSS.replace('\n', ' ') or
      bool(re.search(r'data-menu-color=dark\][^{]*logo', APP_CSS)), True)
check('o logo do topbar sai do topbar-color',
      bool(re.search(r'data-topbar-color=dark\][^{]*logo', APP_CSS)), True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
