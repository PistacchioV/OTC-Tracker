# -*- coding: utf-8 -*-
"""Page Access e o menu lateral SEM o prefixo do Stratos (§716).

No Stratos o app mora sob `/76521/<solução>` e a ponte reescreve o HTML: todo
`href="/dashboard"` sai `href="/76521/<solução>/dashboard"`. A tela /page-access
monta as caixas pelos links do MENU (`getAttribute('href')`) e o menu esconde o
que o usuário não pode ver comparando o mesmo `href` com o acesso gravado — que
é SEM prefixo. Resultado no Stratos: todo mundo aparecia sem acesso, o Save
mandava os endereços com prefixo, o servidor descartava todos e gravava `[]`
(nenhuma página), e o menu de quem tem acesso restrito ficava vazio.

O que se prende:

  1. os dois scripts (page-access.html e sidenav.html) leem o href do menu pelo
     `appPath`, que tira o `window.__OTC_BASE__` (o prefixo que o shim do
     Stratos publica);
  2. o `appPath` de cada um, executado no node: sem base devolve o href como
     está (a dev e a instância); com base tira o prefixo, e não mexe no que
     não começa por ele (`#`, outro caminho, o prefixo sem a barra).

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_page_access_prefix.py
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
FONTES = {
    'page-access': os.path.join(ROOT, 'apps', 'templates', 'pages', 'page-access.html'),
    'sidenav': os.path.join(ROOT, 'apps', 'templates', 'partials', 'sidenav.html'),
}
fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


CASOS = [
    ('', '/dashboard', '/dashboard'),
    ('/76521/otc', '/76521/otc/dashboard', '/dashboard'),
    ('/76521/otc', '/76521/otc/new-deals/ndf/vanilla', '/new-deals/ndf/vanilla'),
    ('/76521/otc', '/dashboard', '/dashboard'),
    ('/76521/otc', '#', '#'),
    ('/76521/otc', '/76521/otcX/x', '/76521/otcX/x'),
]

node = shutil.which('node')
print('== 1. o href do menu passa pelo appPath ==')
for nome, fp in FONTES.items():
    txt = open(fp, encoding='utf-8').read()
    check('%s: lê o prefixo do shim' % nome, "window.__OTC_BASE__" in txt)
    crus = re.findall(r"var href = (.*?getAttribute\('href'\).*?);", txt)
    check('%s: toda leitura do href do menu é appPath(...)' % nome,
          bool(crus) and all(c.startswith('appPath(') for c in crus), True)

    print('\n== 2. %s: o appPath no node ==' % nome)
    m = re.search(r"(function appPath\(h\) \{.*?\n  \})", txt, re.S)
    check('%s: a função existe' % nome, m is not None)
    if not m or not node:
        if not node:
            print('  skip: sem node')
        continue
    js = ('var out = [];\n' + ''.join(
        '(function(){ var OTC_BASE = %s; %s out.push(appPath(%s)); })();\n'
        % (json.dumps(b), m.group(1), json.dumps(h)) for b, h, _e in CASOS)
        + 'console.log(JSON.stringify(out));')
    r = subprocess.run([node, '-e', js], capture_output=True, text=True)
    got = json.loads(r.stdout or '[]')
    for (b, h, e), g in zip(CASOS, got):
        check('%s: base %r, href %r → %r' % (nome, b, h, e), g, e)

print(('\nFALHAS (%d): %s' % (len(fails), fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
