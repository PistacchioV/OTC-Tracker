# -*- coding: utf-8 -*-
"""DIAGNÓSTICO: onde a subida gasta os minutos entre o .bat e o `Serving on`.

O `start-otc-tracker.bat` imprime `[TIME] entregando ao Python` e, a partir
dali, a instância fica MUDA por minutos. Não é falta de log: é o farol do
`database_access` só avisar acima de ~5 s por operação (`file_lock_held_slow`).
Dezenas de aberturas de 2-4 s cada passam caladas, e foi essa mesma cegueira
que escondeu a semeadura da subida até 21/09/2026 (§519).

Medido na instância em 21/09/2026, com o carimbo da semeadura JÁ gravado (ou
seja, com a semeadura PULADA):

    13:51:04  entregando ao Python
    13:53:34  primeira linha do log          ← 2,5 min de silêncio
    13:55:49 ─ 13:59:50                      ← 4 min sem uma linha
    13:59:50 ─ 14:03:06                      ← 3,3 min sem uma linha
    14:03:07  Serving on

São ~9,5 min DENTRO do `register_blueprints` — o import do `routes.py` e das 49
features. O carimbo resolveu o que ele prometia e não mexeu neste número: a
subida que RODOU a semeadura inteira levou 7 min e a que a PULOU levou 13. A
variação do share é maior que o ganho, então a conta é outra.

Este script responde QUAL import custa, com o cronômetro do próprio Python
(`-X importtime`): ele imprime, por módulo, o tempo PRÓPRIO e o CUMULATIVO.
A diferença entre os dois é o que separa as duas hipóteses:

  · tempo PRÓPRIO espalhado por centenas de módulos = é o custo de LER o
    código pelo SMB (cada `.py` do share é um `stat` para validar o `.pyc`
    local), e o remédio é de empacotamento;
  · tempo PRÓPRIO concentrado em poucos módulos = é código de nível de módulo
    indo ao banco durante o import, e o remédio é adiar essa leitura.

Ele roda o MESMO import da instância, no MESMO lugar, e sai — não sobe
servidor nenhum (`OTC_DISABLE_SCHEDULERS=1`). Leva o tempo de uma subida.

Uso, da pasta da versão que o `link.txt` aponta:

    python scripts\\diag_boot_imports.py

O relatório sai na tela e o bruto fica ao lado do log da instância, em
`%LOCALAPPDATA%\\OTC-Tracker\\diag-boot-imports.txt`.
"""
import os
import subprocess
import sys
import time

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

TOPO = 25


def _prefixo_de_bytecode():
    """O MESMO `PYTHONPYCACHEPREFIX` do .bat, e pelo mesmo motivo (§322).

    Sem ele este script compila os ~600 módulos do app e grava cada `.pyc` DE
    VOLTA no share — justamente o custo que viemos medir, pago de novo e do
    lado errado. E a medição sairia adulterada: a primeira execução gravaria o
    cache e a segunda leria outro cenário.
    """
    prefixo = os.environ.get('PYTHONPYCACHEPREFIX')
    if prefixo:
        return prefixo
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('TMPDIR') or '/tmp'
    return os.path.join(base, 'OTC-Tracker', 'pycache', os.path.basename(ROOT))


def _destino_do_bruto():
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('TMPDIR') or '/tmp'
    return os.path.join(base, 'OTC-Tracker', 'diag-boot-imports.txt')


def _linhas_de_importtime(texto):
    """Só as linhas do cronômetro — o app loga no mesmo stderr.

    Formato: `import time:  <self> | <cumulative> | <nome indentado>`. A
    indentação do nome é a profundidade, e é ela que diz quem importou quem.
    """
    for linha in texto.splitlines():
        if not linha.startswith('import time:'):
            continue
        corpo = linha[len('import time:'):]
        partes = corpo.split('|')
        if len(partes) < 3:
            continue
        nome = '|'.join(partes[2:]).rstrip()
        try:
            proprio = int(partes[0].strip())
            cumulativo = int(partes[1].strip())
        except ValueError:
            continue                       # o cabeçalho `self | cumulative`
        nivel = (len(nome) - len(nome.lstrip())) // 2
        yield proprio / 1e6, cumulativo / 1e6, nome.strip(), nivel


def main():
    ambiente = dict(os.environ)
    ambiente['OTC_DISABLE_SCHEDULERS'] = '1'
    ambiente['PYTHONPYCACHEPREFIX'] = _prefixo_de_bytecode()
    ambiente['PYTHONIOENCODING'] = 'utf-8'

    print('raiz do app .........: %s' % ROOT)
    print('bytecode em .........: %s' % ambiente['PYTHONPYCACHEPREFIX'])
    print('\nimportando o app inteiro com o cronômetro do Python.')
    print('leva o tempo de uma subida — na instância, minutos. aguarde.\n')

    inicio = time.time()
    proc = subprocess.Popen([sys.executable, '-X', 'importtime', '-c', 'import run'],
                            cwd=ROOT, env=ambiente,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _saida, erro = proc.communicate()
    gasto = time.time() - inicio

    texto = erro.decode('utf-8', 'replace')
    destino = _destino_do_bruto()
    try:
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, 'w', encoding='utf-8') as fh:
            fh.write(texto)
    except (OSError, IOError) as exc:
        print('[aviso] não consegui gravar o bruto em %s (%s)' % (destino, exc))
        destino = None

    medidas = list(_linhas_de_importtime(texto))
    if not medidas:
        print('nenhuma linha de `-X importtime` na saída — o import FALHOU.')
        print('os últimos 40 caracteres de erro:\n')
        print(texto[-4000:])
        return 1

    print('=' * 78)
    print('TOTAL do import: %.1f s  (código de saída %s)' % (gasto, proc.returncode))
    print('=' * 78)

    # O tempo PRÓPRIO é o que o módulo gastou nele mesmo, fora dos que ele
    # importa; somá-lo dá o total, e é por ele que se acha o culpado.
    soma = sum(p for p, _c, _n, _v in medidas)
    print('\nmódulos cronometrados: %d   ·   soma dos tempos próprios: %.1f s' %
          (len(medidas), soma))

    print('\n── os %d módulos mais caros POR TEMPO PRÓPRIO ─────────────────────' % TOPO)
    print('%9s %9s  %s' % ('próprio', 'cumulat.', 'módulo'))
    for proprio, cumulativo, nome, _nivel in sorted(medidas, reverse=True)[:TOPO]:
        print('%8.2fs %8.2fs  %s' % (proprio, cumulativo, nome))

    # A árvore do app: quanto cada pedaço nosso custa COM o que ele arrasta.
    print('\n── o custo CUMULATIVO dos pedaços do app ─────────────────────────')
    nossos = [(c, n) for _p, c, n, _v in medidas
              if n == 'run' or n.startswith('apps')]
    for cumulativo, nome in sorted(nossos, reverse=True)[:TOPO]:
        print('%8.2fs  %s' % (cumulativo, nome))

    # Quantos módulos do app existem e quanto custam SOMADOS: é a resposta à
    # pergunta "é um módulo pesado ou são seiscentos módulos pelo SMB?".
    app_proprios = [p for p, _c, n, _v in medidas if n.startswith('apps')]
    if app_proprios:
        print('\n── a soma do app ────────────────────────────────────────────────')
        print('módulos sob `apps`: %d   ·   tempo próprio somado: %.1f s   ·   '
              'média: %.0f ms' % (len(app_proprios), sum(app_proprios),
                                  1000 * sum(app_proprios) / len(app_proprios)))
        acima = [p for p in app_proprios if p >= 1.0]
        print('desses, com 1 s ou mais: %d   (somam %.1f s)' % (len(acima), sum(acima)))

    if destino:
        print('\nbruto completo em: %s' % destino)
    return 0


if __name__ == '__main__':
    sys.exit(main())
