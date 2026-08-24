#!/usr/bin/env python3
"""check_export_advanced.py — protege o `apps/static/js/export-advanced.js`.

O item Advanced do menu Export decide QUE LINHAS vão para o arquivo, e a decisão
é toda de comparação: a célula está dentro do intervalo? casa com o critério? O
resto do arquivo é DOM, mas essas funções erram em silêncio — uma data lida como
texto não levanta exceção nenhuma, só devolve o recorte errado, e quem recebe a
planilha não tem como saber.

Como o `check_boxparse.py`, este script roda a cópia real do JavaScript no `jsc`
do macOS (JavaScriptCore) em vez de reimplementar a regra em Python — uma
reimplementação seria uma segunda regra, e as duas divergiriam.

Precisa do `jsc`, então NÃO roda na máquina Windows do time (§163).
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JS = os.path.join(ROOT, 'apps', 'static', 'js', 'export-advanced.js')
JSC = ('/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/'
       'Helpers/jsc')

FAILURES = []


def check(label, got, want):
    ok = str(got) == str(want)
    print(('ok   ' if ok else 'FAIL ') + label + '  ->  ' + repr(got))
    if not ok:
        FAILURES.append('%s: esperado %r, veio %r' % (label, want, got))


def extract(src, name):
    """A função `name` do arquivo, por contagem de chaves."""
    i = src.index('function %s(' % name)
    j = src.index('{', i)
    depth = 0
    while True:
        ch = src[j]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1


def main():
    if not os.path.exists(JSC):
        print('jsc não encontrado — este check só roda no macOS (§163). Pulando.')
        return 0

    src = open(JS, encoding='utf-8').read()

    # O `plain` usa um <textarea> para decodificar entidades; fora do navegador
    # o stub faz o mesmo com o único caso que interessa aqui.
    harness = ("var _decoder = null;\n"
               "var document = { createElement: function () {\n"
               "  return { set innerHTML(v) { this.value = String(v)\n"
               "      .replace(/&amp;/g, '&').replace(/&lt;/g, '<')\n"
               "      .replace(/&gt;/g, '>').replace(/&quot;/g, '\"'); }, value: '' };\n"
               "} };\n")
    for name in ('plain', 'parseDate', 'parseNum', 'coerce', 'endKind'):
        harness += extract(src, name) + '\n'

    harness += r"""
    function out(k, v) { print(k + '\t' + v); }
    out('plain-tag',   plain('<span class="badge bg-success">Total Net</span>'));
    out('plain-ent',   plain('ACME &amp; CO'));
    out('date-br',     parseDate('10/05/2024') === Date.UTC(2024, 4, 10));
    out('date-iso',    parseDate('2024-05-10') === Date.UTC(2024, 4, 10));
    out('date-2dig',   parseDate('10/05/24')  === Date.UTC(2024, 4, 10));
    out('date-texto',  parseDate('SAFRABM'));
    out('num-en',      parseNum('1,234.56'));
    out('num-br',      parseNum('1.234,56'));
    out('num-neg',     parseNum('-42'));
    out('num-texto',   parseNum('ABC'));
    out('kind-datas',  endKind('01/01/2024', '31/12/2024'));
    out('kind-nums',   endKind('10', '20'));
    out('kind-texto',  endKind('AAA', ''));
    out('kind-vazio',  endKind('', ''));
    var lo = coerce('01/06/2024', 'date'), hi = coerce('30/06/2024', 'date');
    out('dentro',      coerce('15/06/2024', 'date') >= lo && coerce('15/06/2024', 'date') <= hi);
    out('fora',        coerce('01/07/2024', 'date') <= hi);
    out('nao-data',    coerce('SAFRABM', 'date'));
    out('num-dentro',  coerce('1.234,56', 'num') > coerce('1000', 'num'));
    out('texto-lower', coerce('  ACME  ', 'text'));
    """

    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                     encoding='utf-8') as fh:
        fh.write(harness)
        path = fh.name
    try:
        res = subprocess.run([JSC, path], capture_output=True, text=True)
    finally:
        os.unlink(path)

    if res.returncode != 0:
        print('FAIL o jsc não rodou o harness:\n' + (res.stderr or res.stdout))
        return 1

    got = {}
    for line in res.stdout.splitlines():
        if '\t' in line:
            k, v = line.split('\t', 1)
            got[k] = v

    # O badge de status vira o texto que está escrito nele: é assim que um
    # critério 'Status é exatamente Matched' casa a linha que a tela pinta.
    check('badge vira texto', got.get('plain-tag'), 'Total Net')
    check('entidade decodificada', got.get('plain-ent'), 'ACME & CO')

    check('data dd/mm/yyyy', got.get('date-br'), 'true')
    check('data yyyy-mm-dd', got.get('date-iso'), 'true')
    # Ano de dois dígitos: 24 é 2024 e não 1924 — a tabela é de operação, não de
    # arquivo histórico.
    check('data com ano de 2 dígitos', got.get('date-2dig'), 'true')
    check('texto não vira data', got.get('date-texto'), 'null')

    # As duas escritas convivem no app: a tela formata em en-US e o que vem de
    # planilha chega em pt-BR. Ler só uma faria metade dos intervalos vazios.
    check('número en-US', got.get('num-en'), '1234.56')
    check('número pt-BR', got.get('num-br'), '1234.56')
    check('número negativo', got.get('num-neg'), '-42')
    check('texto não vira número', got.get('num-texto'), 'null')

    # O tipo do intervalo sai das PONTAS digitadas, nunca do conteúdo da coluna:
    # adivinhar pelo conteúdo faria a mesma coluna mudar de regra por linha.
    check('duas datas → date', got.get('kind-datas'), 'date')
    check('dois números → num', got.get('kind-nums'), 'num')
    check('texto → text', got.get('kind-texto'), 'text')
    check('sem pontas → sem intervalo', got.get('kind-vazio'), 'null')

    check('data dentro do intervalo', got.get('dentro'), 'true')
    check('data fora do intervalo', got.get('fora'), 'false')
    # Célula que não é do tipo do intervalo fica de fora — incluí-la seria dizer
    # que ela está dentro de um intervalo que não sabe medir.
    check('célula não-data não entra', got.get('nao-data'), 'null')
    check('comparação numérica', got.get('num-dentro'), 'true')
    check('texto normalizado', got.get('texto-lower'), 'acme')

    print()
    if FAILURES:
        for f in FAILURES:
            print('FAIL ' + f)
        return 1
    print('todas as asserções passaram')
    return 0


if __name__ == '__main__':
    sys.exit(main())
