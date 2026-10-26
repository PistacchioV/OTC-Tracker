"""Papel de parede: toda parede da lista existe nos QUATRO lugares (21/10/2026).

Parede nova mexe em:
  * a lista `WALLS` do `otc.js` (a ordem das gavetas);
  * a paleta no `otc.scss` §2b (o `otc.css` compilado tem o `data-wall`);
  * o nome nas três línguas da tela Settings (`settings.js`, `walls`);
  * e, nas paredes FLOW (Fjord, Glacier), o segundo desenho do
    partial (`otc-wall__flow`), ligado por `--w-flow` e com a miniatura
    própria (`otc-flow-art`).

Sem um deles a parede nasce sem cor (cai na base do Ash), sem nome na
Settings ou com o desenho errado — e nada dá erro. Também prende que o modo
opaco tira o halo desfocado do flow (`.g`) e que todo `href` do partial
aponta para um id que existe.

As LISAS são a paleta do sistema (22/10/2026): uma cor por tom, as escuras só
no tema escuro e as claras só no claro (`WALL_TONE`/`WALL_PAIR` do otc.js,
`data-tone` na gaveta), e a padrão é a Frost — o `:root` sem `data-wall`. Ash,
Sand, Sage, Bloom, Ember, Grove e Canyon foram RETIRADAS (não combinavam com
ela): o guarda prende que não voltam por um dos quatro lugares e que a
preferência gravada de quem as tinha é migrada para a padrão no `<head>`.
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
head = read('apps/templates/partials/head-css.html')
RETIRADAS = ('ash', 'sand', 'sage', 'bloom', 'ember', 'grove', 'canyon')
# a parede SEM data-wall (o :root) e a escolhida por padrão (26/10/2026:
# Aurora com o vidro Clear) são duas coisas
PADRAO = 'frost'
ESCOLHA = 'aurora'
# a paleta do sistema, do mais escuro ao mais claro: (parede, tom, cor)
PALETA = (('abyss', 'dark', '#06141b'), ('midnight', 'dark', '#11212d'), ('slate', 'dark', '#253745'),
          ('steel', 'dark', '#4a5c6a'), ('fog', 'light', '#9ba8ab'), ('frost', 'light', '#ccd0cf'))

m = re.search(r"var WALLS = \[([^\]]*)\]", js)
walls = re.findall(r"'([a-z]+)'", m.group(1)) if m else []
check(len(walls) == 12, 'WALLS: doze paredes')
check(walls[:6] == [w for w, _, _ in PALETA], 'as seis lisas da paleta primeiro, do escuro ao claro')
FLOW = ('fjord', 'glacier')
check(walls[-2:] == list(FLOW), 'as duas flow no fim da lista')

# 1 · paleta compilada (a padrão é o :root, sem data-wall)
for w in walls:
    if w == PADRAO:
        continue
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

# 5 · as lisas: a cor EXATA da paleta no tema dela, a da outra ponta no outro
def base(seletor):
    m = re.search(r'(?:^|\})\s*%s \{([^}]*)\}' % seletor, css)
    c = re.search(r'--w-b1: (#[0-9a-f]{6})', m.group(1)) if m else None
    return c.group(1).lower() if c else None

cor = {w: c for w, _, c in PALETA}
par = {}
mp = re.search(r"var WALL_PAIR = \{([^}]*)\}", js)
par = dict(re.findall(r"(\w+): '(\w+)'", mp.group(1))) if mp else {}
mt = re.search(r"var WALL_TONE = \{([^}]*)\}", js)
tom = dict(re.findall(r"(\w+): '(\w+)'", mt.group(1))) if mt else {}
check(re.search(r"var WALL_BASE = '%s'" % PADRAO, js) is not None, 'otc.js: a %s é a sem data-wall' % PADRAO)
check(re.search(r"var WALL_DEFAULT = '%s'" % ESCOLHA, js) is not None, 'otc.js: a padrão é a %s' % ESCOLHA)
check("glass: p.glass || 'clear'" in js, "otc.js: o vidro padrão é o clear")
check(base(r':root, \[data-art\]') == cor['frost'], ':root claro = Frost (%s)' % cor['frost'])
check(base(r'\[data-bs-theme=dark\], \[data-bs-theme=dark\] \[data-art\]') == cor['abyss'], ':root escuro = Abyss (%s)' % cor['abyss'])
for w, t, c in PALETA:
    check(tom.get(w) == t, '%s é do tema %s (WALL_TONE)' % (w, 'escuro' if t == 'dark' else 'claro'))
    outra = par.get(w)
    check(outra in cor and tom.get(outra) != t, '%s tem par no outro tema (%s)' % (w, outra))
    if w == PADRAO:
        continue
    claro = base(r':root\[data-wall=%s\], \[data-art=%s\]' % (w, w))
    escuro = base(r':root\[data-wall=%s\]\[data-bs-theme=dark\], \[data-bs-theme=dark\] \[data-art=%s\]' % (w, w))
    proprio, outro = (escuro, claro) if t == 'dark' else (claro, escuro)
    check(proprio == c, '%s no seu tema é %s (%s)' % (w, c, proprio))
    check(outro == cor.get(outra), '%s no outro tema é a %s (%s)' % (w, outra, outro))
check(re.search(r':root\[data-bs-theme=dark\] \[data-wall-pick\]\[data-tone=light\],\s*'
                r':root\[data-bs-theme=light\] \[data-wall-pick\]\[data-tone=dark\] \{\s*display: none !important', css) is not None,
      'a gaveta esconde as lisas do outro tema')
check('data-tone="\' + WALL_TONE[k]' in js and "data-tone=\"' + tones[k]" in st,
      'a gaveta e a Settings marcam o tom de cada miniatura')
check(re.search(r"var wall = p\.wall \|\| '%s'" % ESCOLHA, head) is not None, 'o <head> nasce na %s' % ESCOLHA)
check(re.search(r"wall !== '%s'\) r\.setAttribute" % PADRAO, head) is not None, 'o <head> trata a %s como a sem data-wall' % PADRAO)
check("(p.glass || 'clear') === 'clear'" in head, 'o <head> nasce com o vidro clear')
check("wall: '%s', glass: 'clear'" % ESCOLHA in st, 'o Reset da Settings volta à %s com o vidro clear' % ESCOLHA)

# 6 · as retiradas não voltam e a preferência delas é migrada
for w in RETIRADAS:
    check(w not in walls, '%s fora da lista WALLS' % w)
    check(re.search(r'\[data-(wall|art)=["\']?%s["\']?\]' % w, css) is None, '%s sem paleta no otc.css' % w)
    check(all(re.search(r'\b%s:' % w, mp) is None for mp in maps), '%s sem nome na Settings' % w)
    check(re.search(r"\b%s: 1\b" % w, head) is not None, 'o <head> migra quem tinha %s gravada' % w)
check('delete p.wall' in head and "localStorage.setItem('__OTC_TRACKER_UI__'" in head,
      'a migração volta à padrão E grava (o otc.js lê o localStorage depois)')

print()
print('TUDO OK' if not fails else '%d FALHA(S)' % len(fails))
sys.exit(1 if fails else 0)
