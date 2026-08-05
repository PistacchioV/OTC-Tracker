"""NDF Summary: a luz de fundo dos cards de reconciliacao (OK x Check).

Os quatro cards do topo ganharam o halo colorido do New Deals Monitor — verde
quando B3 e Interno batem, ambar quando nao batem. Tres coisas quebram esse
efeito SEM erro nenhum no console, e sao elas que este script prende:

  1. o nome da classe. O JS escreve `is-ok`/`is-check` no card e o CSS le. Sao
     duas copias do mesmo acordo dentro do arquivo; renomear de um lado apaga a
     cor do outro em silencio.

  2. a ORDEM do :hover. `.ops-widget:hover` troca o box-shadow inteiro por um
     cinza. Se a regra colorida de hover subir para antes dela, o halo some no
     passar do mouse — e so no hover, que e o jeito mais facil de nao notar.

  3. o peso no tema CLARO. O pedido foi explicito: no branco a luz tem de ser
     MAIS forte que no escuro, porque cor clara sobre fundo claro se dissolve.
     Um ajuste no dark que passe do claro inverte isso sem quebrar nada.

Le so o template. Nao encosta em dado real nem sobe servidor.
"""
import io
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


SRC = io.open('apps/templates/pages/ndf-summary.html', encoding='utf-8').read()
CSS = SRC.split('<style>', 1)[1].split('</style>', 1)[0]


def block(selector, css=CSS):
    """Corpo da regra de SOMBRA cujo seletor termina em `selector`.

    O mesmo seletor aparece duas vezes de proposito — uma so para registrar a
    cor (`--ops-glow`) e outra com a receita — entao nao basta o primeiro
    casamento: procuramos o bloco que de fato declara `box-shadow`.
    """
    for m in re.finditer(re.escape(selector) + r'\s*\{', css):
        body = css[m.end():css.find('}', m.end())]
        if 'box-shadow' in body:
            return body
    return ''


def alphas(body):
    """Os alphas das camadas de sombra, na ordem (contato, media, halo)."""
    return [float(a) for a in re.findall(r'rgba\(var\(--ops-glow\), (\.\d+)\)', body)
            ][-3:]


print('\n== 1. o JS escreve o estado no card, do mesmo `ok` do badge ==')
JS = SRC.split('{% block extra_javascript %}', 1)[1]
check('badge e card saem da mesma variavel',
      "badge.className = 'ops-recon-badge ' + (ok ? 'is-ok' : 'is-check');" in JS, True)
check('o card recebe is-ok', "card.classList.toggle('is-ok', ok);" in JS, True)
check('o card recebe is-check', "card.classList.toggle('is-check', !ok);" in JS, True)
check('is-unmatched continua (anel ambar)', "card.classList.toggle('is-unmatched', !ok);" in JS, True)

print('\n== 2. o CSS consome exatamente essas classes ==')
check('verde registrado no is-ok', '.ops-recon.is-ok    { --ops-glow:  22, 163,  74; }' in CSS, True)
check('ambar registrado no is-check', '.ops-recon.is-check { --ops-glow: 245, 158,  11; }' in CSS, True)
light = block('.ops-recon.is-check')
check('a receita clara tem as 3 camadas', len(alphas(light)), 3)
dark = block('[data-bs-theme=dark] .ops-recon.is-check')
check('a receita escura tem as 3 camadas', len(alphas(dark)), 3)

print('\n== 3. no claro a luz e MAIS forte que no escuro ==')
for n, (lo, dk) in enumerate(zip(alphas(light), alphas(dark))):
    check('camada %d: claro (%.2f) > escuro (%.2f)' % (n + 1, lo, dk), lo > dk, True)

print('\n== 4. o hover colorido vence o cinza do .ops-widget ==')
generic = CSS.find('.ops-widget:hover')
colored = CSS.find('.ops-recon.is-ok:hover')
check('.ops-widget:hover existe', generic != -1, True)
check('o hover colorido vem depois', colored > generic, True)
check('o hover escuro tambem', CSS.find('[data-bs-theme=dark] .ops-recon.is-ok:hover') > colored, True)
hov = block('.ops-recon.is-check:hover')
check('e o hover espalha mais que o repouso', alphas(hov)[2] >= alphas(light)[2], True)

print('\n== 5. o anel ambar divide a propriedade via variavel ==')
# box-shadow nao se soma entre regras: se `.is-unmatched` declarar a sua propria,
# a ultima declaracao apaga o halo inteiro. Por isso o anel e --ops-ring.
check('is-unmatched nao declara box-shadow proprio',
      re.search(r'\.ops-recon(--total)?\.is-unmatched\s*\{[^}]*box-shadow', CSS) is not None, False)
check('o anel do card comum e variavel',
      '.ops-recon.is-unmatched  { --ops-ring: inset 0 0 0 1px rgba(245, 158, 11, .5); }' in CSS, True)
check('o anel do Total (mais grosso) tambem',
      '.ops-recon--total.is-unmatched { --ops-ring: inset 0 0 0 2px rgba(245, 158, 11, .9); }' in CSS, True)
check('e toda receita comeca pelo anel', CSS.count('box-shadow: var(--ops-ring),'), 4)
check('o padrao e um anel transparente (senao a variavel fica invalida)',
      '--ops-ring: 0 0 0 0 rgba(0, 0, 0, 0);' in CSS, True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
