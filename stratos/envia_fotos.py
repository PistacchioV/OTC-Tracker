#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""envia_fotos.py — leva as fotos dos usuários para o Shared Drive do Stratos.

    python OTC-Tracker-Stratos\\stratos\\envia_fotos.py --env dev PASTA [--dry-run]
                                    [--drive-local PASTA_LOCAL]

Roda na máquina da REDE do JPM com o Python do DevShell (o do `stratosblocks`,
como o `envia_dados.py`). PASTA é onde estão as fotos `<SID>.jpg` — a
`apps\\static\\images\\users` da instância, por exemplo. Elas vão para
`otc-tracker/images/users/` do drive, de onde o Stratos as serve (§715,
`src/fotos_stratos.py`). As fotos NÃO entram no git: são dos colegas, e o
repositório fica no GitHub.

O nome sobe em MINÚSCULAS (a tela pede `<sid minúsculo>.jpg`). Só `.jpg`,
`.jpeg` e `.png` até 5 MB; o resto é listado e pulado. Rodar de novo sobe tudo
outra vez (são poucos KB cada).
"""
import argparse
import io
import logging
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import ponte_share as PS  # noqa: E402

log = logging.getLogger('envia-fotos')

PASTA_DRIVE = 'images/users'          # fotos_stratos.pasta(), do lado do contêiner
EXTENSOES = ('.jpg', '.jpeg', '.png')
MAX_BYTES = 5 * 1024 * 1024


def plano(origem):
    """[(local, nome no drive)] e [(arquivo, motivo)] do que fica de fora."""
    vai, fora = [], []
    for nome in sorted(os.listdir(origem)):
        local = os.path.join(origem, nome)
        if not os.path.isfile(local):
            continue
        if not nome.lower().endswith(EXTENSOES):
            fora.append((nome, 'não é imagem'))
        elif os.path.getsize(local) > MAX_BYTES:
            fora.append((nome, 'maior que 5 MB'))
        else:
            vai.append((local, nome.lower()))
    return vai, fora


def envia(origem, drive, raiz_drive='otc-tracker', dry_run=False):
    vai, fora = plano(origem)
    destino = '%s/%s' % (raiz_drive.strip('/'), PASTA_DRIVE)
    for nome, motivo in fora:
        log.warning('  pulei %s: %s', nome, motivo)
    log.info('[envia-fotos] %d foto(s) de %s -> %s', len(vai), origem, destino)
    for local, nome in vai:
        if dry_run:
            print('  %s -> %s/%s' % (os.path.basename(local), destino, nome))
            continue
        with open(local, 'rb') as fh:
            drive.save('%s/%s' % (destino, nome), io.BytesIO(fh.read()))
        log.info('  ok %s', nome)
    return len(vai), len(fora)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('pasta')
    ap.add_argument('--env', default=os.getenv('OTC_PONTE_ENV', ''), type=lambda v: v.strip().lower())
    ap.add_argument('--solution-id', default=os.getenv('OTC_PONTE_SOLUTION_ID', PS.SOLUCAO))
    ap.add_argument('--drive-raiz', default=PS.DRIVE_RAIZ)
    ap.add_argument('--drive-local', default='', help='ensaio: uma pasta local no lugar do drive')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    if not os.path.isdir(a.pasta):
        ap.error('a pasta %s não existe' % a.pasta)
    if a.drive_local:
        drive = PS.DriveLocal(a.drive_local)
    elif a.dry_run:
        drive = None
    else:
        if a.env not in PS.AMBIENTES:
            ap.error('--env dev ou --env prod é obrigatório: o ambiente em que a solução está '
                     'publicada. Cada um tem o seu Shared Drive.')
        drive = PS.DriveHttp(a.solution_id, PS.AMBIENTES[a.env])
    n, _f = envia(a.pasta, drive, a.drive_raiz, a.dry_run)
    if not a.dry_run:
        print('\n%d foto(s) no drive. No Stratos elas aparecem em até um minuto, sem restart.' % n)
    return 0


if __name__ == '__main__':
    sys.exit(main())
