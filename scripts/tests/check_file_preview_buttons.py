"""Todo preview de arquivo (`otcFilePreview`) declara o rodapé.

O rodapé da casa é Export · Edit · Close (`buttons: { download, edit }`), ou
Send nas telas que enviam (`send: true`). Sem `buttons` o Swal abre só com o
X do canto: foi assim que as recompras, o Swap Bullet, o catálogo de New Deals
e a Intrag DCE Swap nasceram sem Export nem Edit, com o Vanilla ao lado tendo
os três — e nada acusou.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_file_preview_buttons.py
"""
import glob
import os
import re
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PAGINAS = os.path.join(RAIZ, 'apps', 'templates', 'pages', '*.html')

falhas = 0
vistos = 0
for caminho in sorted(glob.glob(PAGINAS)):
    texto = open(caminho, encoding='utf-8').read()
    for m in re.finditer(r'otcFilePreview\(\{', texto):
        # o objeto da chamada: até o `})` que fecha no mesmo nível de chaves
        i, nivel = m.end() - 1, 0
        for j in range(i, len(texto)):
            if texto[j] == '{':
                nivel += 1
            elif texto[j] == '}':
                nivel -= 1
                if nivel == 0:
                    break
        corpo = texto[i:j + 1]
        linha = texto.count('\n', 0, m.start()) + 1
        vistos += 1
        nome = '%s:%d' % (os.path.basename(caminho), linha)
        if re.search(r'\bbuttons\s*:', corpo):
            print('  ok    ', nome)
        else:
            falhas += 1
            print('  FAIL  ', nome, '— sem `buttons:` (rodapé Export · Edit · Close)')

if not vistos:
    print('  FAIL   nenhuma chamada otcFilePreview encontrada — o guarda está cego')
    falhas += 1
print('\nall ok' if not falhas else '\nFALHAS: %d' % falhas)
sys.exit(1 if falhas else 0)
