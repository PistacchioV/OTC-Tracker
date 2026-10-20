"""Todo botao "Clear Filters" usa o MESMO icone: o funil cortado (`ti ti-filter-off`).

Pedido da mesa (20/10/2026): quatro telas tinham outro desenho — `filter-x`
(Accrual e MtM) e `x-circle` (Comitente e FXO) —, e o botao que faz a mesma
coisa em toda tela tem de ter a mesma cara. Varre templates e JS de pagina: o
botao e reconhecido pelo TEXTO ("Clear filter(s)") ou pelo id/data-lang de
limpar filtro. O "Clear Fields" da Index B3 limpa um formulario, nao filtro.
"""
import io
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


BOTAO = re.compile(r'(?is)<(button|a)\b[^>]*>(?:(?!</\1>).){0,400}?clear[ -]?filters?(?:(?!</\1>).){0,200}?</\1>')
ICONE = re.compile(r'(ti ti-[a-z0-9-]+|data-lucide="[a-z0-9-]+")')
achados, fora = 0, []
for raiz in ('apps/templates', 'apps/static/js'):
    for dp, _dn, fn in os.walk(os.path.join(ROOT, raiz)):
        if 'plugins' in dp:
            continue
        for f in fn:
            if not f.endswith(('.html', '.js')):
                continue
            caminho = os.path.join(dp, f)
            texto = io.open(caminho, encoding='utf-8').read()
            for m in BOTAO.finditer(texto):
                achados += 1
                ic = ICONE.findall(m.group(0))
                if not ic or ic[0] != 'ti ti-filter-off':
                    fora.append('%s:%d %s' % (os.path.relpath(caminho, ROOT), texto[:m.start()].count('\n') + 1,
                                              ic[0] if ic else '(sem icone)'))
check('ha botoes Clear Filters para conferir (a varredura acha algo)', achados > 30, True)
check('todos com o funil cortado (ti ti-filter-off)', fora, [])
print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
