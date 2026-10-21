"""Papel de parede: toda parede da lista existe nos QUATRO lugares (21/10/2026).

Parede nova mexe em:
  * a lista `WALLS` do `otc.js` (a ordem das gavetas);
  * a paleta no `otc.scss` §2b (o `otc.css` compilado tem o `data-wall`);
  * o nome nas três línguas da tela Settings (`settings.js`, `walls`);
  * e, nas paredes FLOW (Canyon, Fjord, Glacier), o segundo desenho do
    partial (`otc-wall__flow`), ligado por `--w-flow` e com a miniatura
    própria (`otc-flow-art`).

Sem um deles a parede nasce sem cor (cai na base do Ash), sem nome na
Settings ou com o desenho errado — e nada dá erro. Também prende que o modo
opaco tira o halo desfocado do flow (`.g`) e que todo `href` do partial
aponta para um id que existe.
"""
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
fails = []


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


js = read('apps/static/js/otc.js')
st = read('apps/static/js/pages/settings.js')
css = read('apps/static/css/otc.css')
scss = read('apps/static/scss/otc.scss')
part = read('apps/templates/partials/wallpaper.html')

m = re.search(r"var WALLS = \[([^\]]*)\]", js)
walls = re.findall(r"'([a-z]+)'", m.group(1)) if m else []
check(len(walls) == 13 and walls[0] == 'ash', 'WALLS: treze paredes, o Ash (padrão) primeiro')
FLOW = ('canyon', 'fjord', 'glacier')
check(walls[-3:] == list(FLOW), 'as três flow no fim da lista')

# 1 · paleta compilada (o Ash é o :root, sem data-wall)
for w in walls[1:]:
    check(re.search(r'\[data-wall=["\']?%s["\']?\]' % w, css) is not None, 'otc.css tem a paleta de %s' % w)

# 2 · nome nas três línguas da Settings
maps = re.findall(r"walls: \{([^}]*)\}", st)
check(len(maps) == 3, 'settings.js: três mapas de nomes (en, br, es)')
for i, mp in enumerate(maps):
    keys = set(re.findall(r"(\w+):", mp))
    falta = [w for w in walls if w not in keys]
    check(not falta, 'mapa %d da Settings sem falta (%s)' % (i + 1, ', '.join(falta) or 'ok'))

# 3 · o desenho: dois grupos, e as flow ligam o segundo
check('class="otc-wall__pane"' in part and 'class="otc-wall__flow"' in part, 'o partial tem os dois desenhos')
check('display: var(--w-pane)' in scss and 'display: var(--w-flow)' in scss, 'o display dos grupos sai das variáveis')
for w in FLOW:
    bloco = re.search(r':root\[data-wall=%s\], \[data-art=%s\] \{([^}]*)\}' % (w, w), css)
    check(bloco is not None and '--w-flow: inline' in bloco.group(1) and '--w-pane: none' in bloco.group(1),
          '%s liga o desenho flow e desliga o do Pane' % w)
    for tema in ('', r'\[data-bs-theme=dark\] '):
        check(re.search(r'%s\[data-art=%s\] \{\s*--w-art: url\("data:image/svg\+xml' % (tema, w), css) is not None,
              '%s tem miniatura própria %s' % (w, 'no escuro' if tema else 'no claro'))
for w in walls:
    if w in FLOW:
        continue
    bloco = re.search(r':root\[data-wall=%s\][^{]*\{([^}]*)\}' % w, css)
    check(bloco is None or '--w-flow: inline' not in bloco.group(1), '%s segue no desenho do Pane' % w)

# 4 · referências do partial e o modo opaco
ids = set(re.findall(r'id="([^"]+)"', part))
refs = set(re.findall(r'href="#([^"]+)"', part)) | set(re.findall(r'url\(#([^)]+)\)', part))
check(refs <= ids, 'todo href/url(#…) do partial aponta para um id que existe (%s)' % (', '.join(sorted(refs - ids)) or 'ok'))
check(re.search(r':root\.is-solid \.otc-wall__flow \.g \{\s*display: none', css) is not None,
      'modo opaco tira o halo e o reflexo desfocados do flow')
check(all('filter=' not in g for g in re.findall(r'<use (?![^>]*class="g")[^>]*>', part)),
      'só os elementos `.g` levam filtro (o resto aparece no modo opaco)')

print()
print('TUDO OK' if not fails else '%d FALHA(S)' % len(fails))
sys.exit(1 if fails else 0)
