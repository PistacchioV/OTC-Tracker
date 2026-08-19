# -*- coding: utf-8 -*-
"""Latam Desk Position — qual arquivo é o relatório do dia.

O relatório é reemitido no mesmo dia. Quando é, a pasta passa a ter DOIS
`FbiRptLatamDeskPostion-NY-*`: o da manhã só é apagado quando alguma linha
entrou, e o novo chega ao lado. A escolha antiga era `sorted(...)[0]` — o
PRIMEIRO em ordem alfabética, que é o antigo —, e o import regravava o JSON do
dia com a posição da manhã dizendo "sucesso, N linhas". A página ficava sem a
atualização e nada no caminho acusava.

Este script prova as três garantias do `_latam_pick_source`:
  1. vence o mtime mais novo, e o nome só desempata;
  2. os preteridos voltam na lista (ficam em disco — não se apaga o que não se leu);
  3. o Save Daily Settlement usa o MESMO critério, senão os dois caminhos
     discordam sobre qual é o relatório do dia.
"""
import io
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)

falhas = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        falhas.append(msg)


from apps.pages import routes as R                     # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    nomes = ['FbiRptLatamDeskPostion-NY-20260818-0800.xls',
             'FbiRptLatamDeskPostion-NY-20260818-1600.xls',
             'OTM_Cashflows.txt']
    for i, n in enumerate(nomes):
        with io.open(os.path.join(tmp, n), 'w', encoding='utf-8') as fh:
            fh.write('x')
        os.utime(os.path.join(tmp, n), (1000 + i * 60, 1000 + i * 60))
    # o MAIS NOVO tem o nome alfabeticamente maior aqui; para o teste valer,
    # inverte-se o mtime: o alfabeticamente PRIMEIRO passa a ser o mais recente.
    os.utime(os.path.join(tmp, nomes[0]), (9000, 9000))

    escolhido, preteridos = R._latam_pick_source(os.listdir(tmp), tmp)
    ok(escolhido == nomes[0], 'vence o mtime mais recente, não a ordem alfabética')
    ok(preteridos == [nomes[1]], 'o preterido volta na lista (e só ele)')
    ok(all(os.path.isfile(os.path.join(tmp, n)) for n in nomes),
       'nenhum arquivo é apagado na escolha')

    # desempate por nome quando o mtime é o mesmo
    os.utime(os.path.join(tmp, nomes[0]), (5000, 5000))
    os.utime(os.path.join(tmp, nomes[1]), (5000, 5000))
    escolhido, _ = R._latam_pick_source(os.listdir(tmp), tmp)
    ok(escolhido == nomes[1], 'mtime empatado → nome decrescente (o mais novo por nome)')

    # arquivo que não é do relatório nunca é candidato
    escolhido, preteridos = R._latam_pick_source(['OTM_Cashflows.txt'], tmp)
    ok(escolhido is None and preteridos == [],
       'pasta sem relatório devolve (None, []) em vez de um arquivo qualquer')

# o Save Daily Settlement chama o mesmo seletor — os dois caminhos têm de
# concordar sobre qual é o relatório do dia
src = io.open(os.path.join(ROOT, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()
ini = src.index('def api_cp_daily_settlement_save')
corpo = src[ini:ini + 4000]
ok('_latam_pick_source(folder_files, SETTLEMENTS_ROOT)' in corpo,
   'Save Daily Settlement usa o mesmo _latam_pick_source')
ok('folder_files.sort()' in corpo,
   'a varredura da pasta é ordenada (os.listdir não tem ordem garantida)')
ok('sorted(f for f in os.listdir(LATAM_SOURCE_ROOT)' not in src,
   'o sorted(...)[0] antigo não sobrou em lugar nenhum')

print('')
print('FALHAS: {}'.format(len(falhas)))
sys.exit(1 if falhas else 0)
