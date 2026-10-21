# -*- coding: utf-8 -*-
"""A pílula de STATUS é uma só em toda tela (mesa, 21/10/2026, HANDOFF §649):
texto BRANCO e em Proper — a primeira letra de cada palavra maiúscula, as
demais minúsculas (o PROPER/PRI.MAIÚSCULA do Excel).

  1. o tema: `.otc-status` com o texto branco (classe DOBRADA, para vencer o
     `.text-success` & cia. que vêm depois) e o TOM da tela virando fundo
     CHEIO — `text-bg-*`, `bg-*`, `bg-*-subtle`, `badge-soft-*`;
  2. no Chromium, com o `otc.css` e o `otc.js` de verdade: cada tom sai branco
     sobre a cor cheia, o texto em Proper (inclusive o que chega DEPOIS, como
     a tradução do I18nManager), e o badge SEM a marca fica como está ("NDF"
     não vira "Ndf"); o export do DataTables (Buttons.stripData) sai em Proper;
  3. o funil e o Advanced Export passam pela mesma função (`otcProperize`);
  4. toda função de status das telas (`statusBadge`, `STATUS_BADGE`,
     `statusPill`, `badgeStatus`, `STATUS_META`, `STATUS_CLASS`) está num
     arquivo que marca a pílula — tela nova com status sem a marca cai aqui.
"""
import io
import os
import re
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
STATIC = os.path.join(ROOT, 'apps', 'static')
TPL = os.path.join(ROOT, 'apps', 'templates')
fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '  (got %r, expected %r)' % (got, exp)))
    if not ok:
        fails.append(label)


def ler(*partes):
    return io.open(os.path.join(*partes), encoding='utf-8').read()


SCSS = ler(STATIC, 'scss', 'otc.scss')
OTCJS = ler(STATIC, 'js', 'otc.js')

print('=== 1. O tema ===')
base = re.search(r'\n\.otc-status\.otc-status \{([^}]*)\}', SCSS)
check('a regra-base com a classe dobrada', bool(base), True)
check('   texto branco com !important', bool(base) and 'color: #fff !important' in base.group(1), True)
tons = re.search(r'\.otc-status:is\(([^)]*)\)', SCSS)
check('o tom da tela vira fundo cheio (sólido, suave, soft e outline)',
      bool(tons) and all(k in tons.group(1) for k in ('.text-bg-#{$name}', '.bg-#{$name}', '.bg-#{$name}-subtle', '.badge-soft-#{$name}')),
      True)
check('o otc.css compilado tem a regra', '.otc-status.otc-status' in ler(STATIC, 'css', 'otc.css'), True)

print('=== 2. No Chromium ===')
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
    print('  (sem playwright: seção pulada)')
TONS = [('text-bg-warning bg-gradient', 'PENDING OTC', 'Pending Otc', 'rgb(217, 138, 0)'),
        ('text-bg-success', 'SENT', 'Sent', 'rgb(34, 165, 89)'),
        ('bg-success-subtle text-success', 'active', 'Active', 'rgb(34, 165, 89)'),
        ('badge-soft-danger', 'NOK', 'Nok', 'rgb(217, 45, 58)'),
        ('text-bg-light', 'Unmatched B3', 'Unmatched B3', 'rgb(138, 143, 153)'),
        ('bg-warning-subtle text-warning', 'in progress', 'In Progress', 'rgb(217, 138, 0)'),
        ('bg-info text-white', 'go-live', 'Go-Live', 'rgb(10, 143, 196)')]
if sync_playwright:
    tmp = tempfile.mkdtemp(prefix='status-pill-')
    arq = os.path.join(tmp, 'p.html')
    js = ['js/vendors.min.js', 'plugins/jquery/jquery.min.js', 'plugins/datatables/dataTables.min.js',
          'plugins/datatables/dataTables.buttons.min.js', 'plugins/datatables/buttons.html5.min.js',
          'js/otc.js', 'js/export-advanced.js']
    io.open(arq, 'w', encoding='utf-8').write(
        '<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="file://%s/css/vendors.min.css">'
        '<link rel="stylesheet" href="file://%s/css/otc.css"></head><body><div class="content-page">' % (STATIC, STATIC) +
        ''.join('<span id="p%d" class="badge otc-status %s">%s</span>' % (i, c, txt) for i, (c, txt, _, _) in enumerate(TONS)) +
        '<span id="cru" class="badge text-bg-info">NDF</span><span id="tr" class="badge otc-status text-bg-primary">NEW</span>'
        '</div>' + ''.join('<script src="file://%s/%s"></script>' % (STATIC, j) for j in js) + '</body></html>')
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        erros = []
        pg.on('pageerror', lambda e: erros.append(str(e)))
        pg.goto('file://' + arq)
        pg.wait_for_timeout(400)
        got = pg.evaluate("""(n) => { const out = []; for (let i = 0; i < n; i++) { const e = document.getElementById('p' + i), c = getComputedStyle(e);
            out.push([e.textContent, c.color, c.backgroundColor]); } return out; }""", len(TONS))
        for (cls, _, prop, fundo), (txt, cor, bg) in zip(TONS, got):
            check('  [%s] texto em Proper, branco, fundo cheio do tom' % cls, (txt, cor, bg), (prop, 'rgb(255, 255, 255)', fundo))
        pg.evaluate("document.getElementById('tr').textContent = 'PENDENTE MO'")    # a tradução chega depois
        pg.wait_for_timeout(150)
        check('  o texto que chega DEPOIS (tradução, redraw) também vira Proper',
              pg.evaluate("document.getElementById('tr').textContent"), 'Pendente Mo')
        check('  o badge sem a marca fica como está', pg.evaluate("document.getElementById('cru').textContent"), 'NDF')
        check('  a regra do PROPER do Excel (maiúscula depois de não-letra)',
              pg.evaluate("['PENDING FEPWEB', 'aguardando b3 id', 'd+1', 'pending mo/fo', 'ok'].map(window.otcProper)"),
              ['Pending Fepweb', 'Aguardando B3 Id', 'D+1', 'Pending Mo/Fo', 'Ok'])
        check('  o export do DataTables sai em Proper (Buttons.stripData)',
              pg.evaluate("""jQuery.fn.dataTable.Buttons.stripData('<span class="badge otc-status text-bg-success">SENT</span>', {stripHtml: true, trim: true})"""),
              'Sent')
        check('  ...e só a pílula marcada', pg.evaluate(
            """jQuery.fn.dataTable.Buttons.stripData('<span class="badge text-bg-info">NDF</span>', {stripHtml: true, trim: true})"""), 'NDF')
        check('  sem erro de JS na página mínima', erros, [])
        b.close()

print('=== 3. O funil e o Advanced Export usam a mesma função ===')
check('o otc.js expõe otcProper/otcProperize e liga as pílulas no boot',
      all(x in OTCJS for x in ('window.otcProper = otcProper', 'window.otcProperize = properize', 'initStatusPills();')), True)
check('o funil (excel-filter) aplica o Proper no texto da célula',
      'window.otcProperize(_tmp)' in ler(STATIC, 'js', 'excel-filter.js'), True)
check('o Advanced Export também', 'plain(properStatus(data))' in ler(STATIC, 'js', 'export-advanced.js'), True)

print('=== 4. Toda função de status marca a pílula ===')
FUNCS = re.compile(r'function\s+(statusBadge|statusPill|badgeStatus)\s*\(|\b(STATUS_BADGE|STATUS_META|STATUS_CLASS|ACC_STATUS_BADGE)\s*=')
SEM_PILULA = {'pages/email-template-recon-payrec.html'}     # e-mail: estilo embutido, sem otc.js
achados, sem = 0, []
for raiz in (os.path.join(TPL), os.path.join(STATIC, 'js')):
    for d, _dirs, arqs in os.walk(raiz):
        if os.sep + 'plugins' in d:
            continue
        for a in arqs:
            if not a.endswith(('.html', '.js')):
                continue
            caminho = os.path.join(d, a)
            txt = ler(caminho)
            if not FUNCS.search(txt):
                continue
            rel = os.path.relpath(caminho, TPL if caminho.startswith(TPL) else os.path.join(STATIC, 'js')).replace(os.sep, '/')
            if rel in SEM_PILULA:
                continue
            achados += 1
            if 'otc-status' not in txt:
                sem.append(rel)
check('as telas com função de status foram achadas (34 em 21/10/2026)', achados >= 34, True)
check('nenhuma sem a marca otc-status', sem, [])

print()
if fails:
    print('FALHOU (%d):' % len(fails))
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('TUDO OK')
