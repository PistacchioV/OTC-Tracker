"""Os .bat do Windows: CRLF, ASCII, UNC-safe e com `pause` em toda saida.

Tres formas de um .bat "abrir e fechar sem fazer nada", todas silenciosas — o
cmd nao deixa rastro, e da maquina de quem desenvolve nao da para reproduzir:

  1. QUEBRA DE LINHA UNIX. O `cmd` precisa de CRLF: com LF ele nao fecha os
     blocos `if (...)`, a janela fecha na mesma fracao de segundo e nem o
     `pause` do fim chega a rodar. O `start-prod.bat` e o `start-debug.bat`
     nasceram num macOS e foram para o share em LF;
  2. `cd /d` NUM CAMINHO UNC. A instancia roda de
     `\\\\NAWEST...\\Application`, e `cd /d` nao aceita UNC — o cmd responde
     "UNC paths are not supported", cai em `C:\\Windows` e SEGUE. Dali o
     `run:app` do waitress nao acha o `run.py` e o servidor nem sobe. Quem
     resolve e o `pushd`, que mapeia o share numa letra temporaria;
  3. SAIDA SEM `pause`. O `new-otc-deploy.bat` terminava toda saida com
     `exit /b` e nenhuma com `pause`: no duplo clique a janela fechava antes de
     alguem ler o resultado — inclusive o erro, que e quando a mensagem importa.

E ainda o ACENTO: o cmd le o .bat na codepage OEM (850/437), nao em UTF-8, e um
acento vira caractere estranho no meio da mensagem. Os arquivos ficam em ASCII.
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


BATS = sorted(f for f in os.listdir(ROOT) if f.lower().endswith(('.bat', '.cmd')))
check('achei os .bat', len(BATS) >= 3, True)

for nome in BATS:
    p = os.path.join(ROOT, nome)
    bruto = io.open(p, 'rb').read()
    texto = bruto.decode('utf-8', 'replace')
    linhas = texto.split('\n')
    print('\n== %s ==' % nome)

    # 1. CRLF em TODA linha. Uma unica linha em LF ja quebra o bloco em que ela
    #    estiver, e o resto do arquivo vira lixo para o interpretador.
    lf_sozinho = [i + 1 for i, l in enumerate(linhas[:-1]) if not l.endswith('\r')]
    check('  toda linha termina em CRLF', lf_sozinho, [])

    # 2. ASCII: o cmd le na codepage OEM, e o acento sai como outro caractere.
    nao_ascii = [i + 1 for i, l in enumerate(linhas) if any(ord(c) > 126 for c in l)]
    check('  sem caractere fora do ASCII', nao_ascii, [])

    limpo = texto.replace('\r\n', '\n')
    codigo = [l for l in limpo.split('\n')
              if l.strip() and not l.strip().upper().startswith('REM')]

    # 3. UNC-safe: `cd /d` nao aceita `\\servidor\...`, e a instancia roda de la.
    check('  nao usa cd /d (nao funciona em UNC)',
          [l.strip() for l in codigo if re.search(r'\bcd\s+/d\b', l, re.I)], [])

    # 4. Toda saida mostra o resultado antes de fechar. `exit /b` sem `pause`
    #    antes e a janela fechando com a mensagem dentro.
    sem_pause = []
    linhas_codigo = limpo.split('\n')
    for i, l in enumerate(linhas_codigo):
        if not re.search(r'\bexit\s+/b\b', l, re.I):
            continue
        # olha as tres linhas anteriores por um `pause`
        janela = linhas_codigo[max(0, i - 3):i]
        if not any(re.match(r'\s*pause\s*$', x, re.I) for x in janela):
            sem_pause.append(i + 1)
    check('  toda saida tem pause antes', sem_pause, [])

    # 5. Quem faz `pushd` tem de fazer `popd` — senao a letra de unidade
    #    temporaria fica mapeada depois que a janela fecha.
    if any(re.search(r'^\s*pushd\b', l, re.I) for l in codigo):
        check('  quem faz pushd faz popd',
              any(re.search(r'^\s*popd\b', l, re.I) for l in codigo), True)

print('\n== o .gitattributes ==')
# Sem ele, o proximo checkout numa maquina com `core.autocrlf` desligado (a
# instancia do time) traz os .bat de volta em LF, e o problema volta inteiro.
ga = os.path.join(ROOT, '.gitattributes')
check('existe', os.path.isfile(ga), True)
if os.path.isfile(ga):
    conteudo = io.open(ga, encoding='utf-8').read()
    check('   e fixa CRLF para .bat',
          bool(re.search(r'\*\.bat\s+.*eol=crlf', conteudo)), True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
