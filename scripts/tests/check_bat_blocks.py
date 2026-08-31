# -*- coding: utf-8 -*-
"""Parenteses dentro de bloco `( ... )` de .bat precisam vir escapados.

O `cmd` nao tem parser de expressao: dentro de um bloco entre parenteses, o
PRIMEIRO `)` nao escapado FECHA o bloco, esteja ele onde estiver — inclusive no
meio do texto de um `echo`. Foi o que aconteceu com

    if /I "%~1"=="noinstall" (
        echo [INFO] Instalacao de dependencias pulada (noinstall).
    ) else (

O `)` de `(noinstall)` fechou o `if`, sobrou um `.` solto como comando, e o
start-debug.bat morria com

    . was unexpected at this time.

antes de chegar no `run.py`. E o erro e de PARSE, entao acontece mesmo quando o
ramo nunca seria executado — rodar sem argumento nenhum quebrava igual.

Nao ha erro de sintaxe visivel no arquivo, o editor nao acusa nada, e o unico
sintoma e uma linha cripitica no terminal de quem tentou subir a aplicacao. Por
isso vira guarda.

Duas asercoes por arquivo versionado:

  1. nenhum `echo` DENTRO de um bloco carrega `(` ou `)` sem o `^` na frente;
  2. os blocos fecham (contagem equilibrada no fim do arquivo).

A linha `REM`/`::` fica de fora: comentario nao e comando, e o `cmd` nao conta
parentese dele.
"""
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

CRU = re.compile(r'(?<!\^)[()]')
ABRE = re.compile(r'(?<!\^)\(')
FECHA = re.compile(r'(?<!\^)\)')
ECHO = re.compile(r'(?i)^\s*echo\b')
COMENTARIO = re.compile(r'(?i)^\s*(rem\b|::)')

falhas = []


def check(rotulo, ok):
    print(('  ok  ' if ok else '  FAIL ') + rotulo)
    if not ok:
        falhas.append(rotulo)


def analisa(caminho):
    """(linhas com parentese cru dentro de bloco, profundidade final)."""
    with open(caminho, 'r', encoding='utf-8', errors='replace') as fh:
        linhas = fh.read().splitlines()
    profundidade = 0
    crus = []
    for numero, bruta in enumerate(linhas, 1):
        linha = bruta.rstrip('\r').strip()
        if COMENTARIO.match(linha):
            continue
        if profundidade > 0 and ECHO.match(linha) and CRU.search(linha):
            crus.append((numero, linha[:70]))
        profundidade += len(ABRE.findall(linha)) - len(FECHA.findall(linha))
        profundidade = max(profundidade, 0)
    return crus, profundidade


alvos = sorted(n for n in os.listdir(ROOT) if n.lower().endswith('.bat'))
if not alvos:
    print('FAIL  nenhum .bat encontrado na raiz — o guarda perdeu o alvo')
    sys.exit(1)

for nome in alvos:
    crus, profundidade = analisa(os.path.join(ROOT, nome))
    detalhe = '' if not crus else '  ->  ' + '; '.join('L%d %s' % c for c in crus)
    check('%s: echo dentro de bloco sem parentese cru%s' % (nome, detalhe), not crus)
    check('%s: blocos fecham (sobra %d)' % (nome, profundidade), profundidade == 0)

# A guarda so vale se ela REPROVA o caso real. Sem isto, um refactor que
# afrouxasse a regex passaria despercebido: o teste ficaria verde por nao
# enxergar mais nada, que e o mesmo verde de "esta tudo certo".
import tempfile                                            # noqa: E402

with tempfile.NamedTemporaryFile('w', suffix='.bat', delete=False, encoding='utf-8') as fh:
    fh.write('if /I "%~1"=="x" (\r\n    echo texto (parentese).\r\n) else (\r\n    echo ok\r\n)\r\n')
    ruim = fh.name
crus, _ = analisa(ruim)
os.unlink(ruim)
check('o guarda reprova o caso que quebrou o start-debug.bat', len(crus) == 1)

print('FALHOU' if falhas else 'TUDO OK')
sys.exit(1 if falhas else 0)
