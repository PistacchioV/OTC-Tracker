#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""envia_dados.py — leva o pacote dos bancos para o Shared Drive do Stratos.

    python stratos\\envia_dados.py --env dev [PACOTE] [--parte-mb 64]
                                   [--solution-id 76521] [--dry-run]
                                   [--drive-local PASTA]

Roda na máquina da REDE do JPM com o Python do DevShell (o do `stratosblocks`,
como a `ponte_share.py`), DEPOIS do `exporta_dados.py`. PACOTE é a PASTA
`otc-dados-<carimbo>` que ele montou; sem ela, a mais recente de
`%LOCALAPPDATA%\\OTC-Tracker\\exporta-stratos`. O `.zip` não serve: no drive o
pacote tem de estar aberto, e a pasta continua ao lado dele.

O que faz (HANDOFF §681 passo C, §708):
  1. recusa pacote INCOMPLETO (banco EM USO ou com erro no export);
  2. envia cada arquivo do `manifest.json` para `otc-tracker/pacotes/<nome>/`,
     os maiores que `--parte-mb` em PARTES (`<arquivo>.parte-0001`…): o limite
     por arquivo do cliente HTTP não está documentado;
  3. envia o `manifest.json` e, por ÚLTIMO, o `envio.json` (a lista das
     partes): sem ele o contêiner vê o pacote como "enviando" e não o confere.

Parou no meio (rede, Ctrl+C)? Rode de novo: o que já subiu está anotado em
`<pacote>\\.envio-<env>.json` e é pulado. Nada no drive é sobrescrito fora da
pasta do pacote, e os bancos em uso não são tocados.

Depois, no Stratos: `/stratos/pacotes` (só o master) → Check → Activate → restart.
"""
import argparse
import io
import json
import logging
import os
import platform
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import ponte_share as PS  # noqa: E402

log = logging.getLogger('envia')

PASTA_DRIVE = 'pacotes'             # pacotes_dados.PASTA, do lado do contêiner
PARTE_MB = 64
TENTATIVAS = 4


def _padrao():
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    pasta = os.path.join(base, 'OTC-Tracker', 'exporta-stratos')
    try:
        nomes = sorted(n for n in os.listdir(pasta)
                       if n.startswith('otc-dados-') and os.path.isdir(os.path.join(pasta, n)))
    except FileNotFoundError:
        nomes = []
    return os.path.join(pasta, nomes[-1]) if nomes else ''


def plano(pacote, parte_bytes):
    """[(remoto relativo ao pacote, local, início, tamanho)] e as entradas do
    `envio.json`, na ordem do manifest."""
    with io.open(os.path.join(pacote, 'manifest.json'), encoding='utf-8') as fh:
        man = json.load(fh)
    passos, entradas = [], []
    for a in man.get('arquivos') or []:
        rel = a['caminho']
        local = os.path.join(pacote, *rel.split('/'))
        tam = os.path.getsize(local)
        if tam != int(a.get('bytes') or -1):
            raise RuntimeError('%s tem %d bytes e o manifest diz %s: o pacote mudou depois do '
                               'export' % (rel, tam, a.get('bytes')))
        if parte_bytes and tam > parte_bytes:
            partes = []
            for i, ini in enumerate(range(0, tam, parte_bytes), 1):
                p = '%s.parte-%04d' % (rel, i)
                partes.append(p)
                passos.append((p, local, ini, min(parte_bytes, tam - ini)))
            entradas.append({'caminho': rel, 'bytes': tam, 'partes': partes})
        else:
            passos.append((rel, local, 0, tam))
            entradas.append({'caminho': rel, 'bytes': tam, 'partes': []})
    return man, passos, entradas


def _sobe(drive, remoto, local, ini, tam):
    for n in range(1, TENTATIVAS + 1):
        try:
            with open(local, 'rb') as fh:
                fh.seek(ini)
                drive.save(remoto, io.BytesIO(fh.read(tam)))
            return
        except Exception:                                   # noqa: BLE001
            if n == TENTATIVAS:
                raise
            log.warning('  falhou (%d/%d), de novo em %ds: %s', n, TENTATIVAS, 5 * n, remoto,
                        exc_info=True)
            time.sleep(5 * n)


def envia(pacote, drive, raiz_drive='otc-tracker', parte_mb=PARTE_MB, estado_nome='.envio.json',
          dry_run=False):
    """Devolve o caminho do pacote no drive. Levanta com o motivo."""
    pacote = os.path.abspath(pacote.rstrip('\\/'))
    nome = os.path.basename(pacote)
    if not os.path.isfile(os.path.join(pacote, 'manifest.json')):
        raise RuntimeError('%s não é um pacote do exporta_dados.py (sem manifest.json)' % pacote)
    man, passos, entradas = plano(pacote, int(parte_mb * 1024 * 1024))
    if not man.get('completo'):
        raise RuntimeError('pacote INCOMPLETO (banco EM USO ou com erro no export): o Stratos o '
                           'recusaria. Rode o exporta_dados.py de novo com as instâncias fechadas.')
    destino = '%s/%s/%s' % (raiz_drive.strip('/'), PASTA_DRIVE, nome)
    total = sum(t for _r, _l, _i, t in passos)
    log.info('[envia] %s -> %s: %d envio(s), %.1f MB', pacote, destino, len(passos), total / 1048576.0)
    if dry_run:
        for remoto, _l, _i, tam in passos:
            print('  %s (%.1f MB)' % (remoto, tam / 1048576.0))
        return destino
    arq_estado = os.path.join(pacote, estado_nome)
    try:
        with io.open(arq_estado, encoding='utf-8') as fh:
            feitos = set(json.load(fh).get('feitos') or [])
    except (FileNotFoundError, ValueError):
        feitos = set()
    t0, enviados = time.time(), 0
    for remoto, local, ini, tam in passos:
        if remoto in feitos:
            enviados += tam
            continue
        _sobe(drive, '%s/%s' % (destino, remoto), local, ini, tam)
        feitos.add(remoto)
        enviados += tam
        with io.open(arq_estado, 'w', encoding='utf-8') as fh:
            json.dump({'feitos': sorted(feitos)}, fh)
        log.info('  ok %s (%.0f%%, %.0fs)', remoto, 100.0 * enviados / (total or 1), time.time() - t0)
    with open(os.path.join(pacote, 'manifest.json'), 'rb') as fh:
        drive.save('%s/manifest.json' % destino, io.BytesIO(fh.read()))
    envio = {'formato': 1, 'nome': nome, 'parte_bytes': int(parte_mb * 1024 * 1024),
             'enviado_em': time.strftime('%Y-%m-%dT%H:%M:%S'), 'maquina': platform.node(),
             'arquivos': entradas}
    # Por ÚLTIMO: é ele que diz ao contêiner que o envio terminou.
    drive.save('%s/envio.json' % destino,
               io.BytesIO(json.dumps(envio, ensure_ascii=False, indent=1).encode('utf-8')))
    log.info('[envia] pronto em %.0fs: %s', time.time() - t0, destino)
    return destino


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('pacote', nargs='?', default='')
    ap.add_argument('--env', default=os.getenv('OTC_PONTE_ENV', ''), type=lambda v: v.strip().lower())
    ap.add_argument('--solution-id', default=os.getenv('OTC_PONTE_SOLUTION_ID', PS.SOLUCAO))
    ap.add_argument('--drive-raiz', default=PS.DRIVE_RAIZ)
    ap.add_argument('--drive-local', default='', help='ensaio: uma pasta local no lugar do drive')
    ap.add_argument('--parte-mb', type=float, default=PARTE_MB,
                    help='arquivo maior que isto vai em partes (padrão %d MB)' % PARTE_MB)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    pacote = a.pacote or _padrao()
    if not pacote:
        ap.error('nenhum pacote em %%LOCALAPPDATA%%\\OTC-Tracker\\exporta-stratos: rode o '
                 'exporta_dados.py antes, ou passe a pasta')
    if pacote.lower().endswith('.zip'):
        ap.error('passe a PASTA do pacote, não o .zip (ela fica ao lado dele)')
    if a.drive_local:
        drive, ambiente = PS.DriveLocal(a.drive_local), 'local'
    else:
        if a.env not in PS.AMBIENTES:
            ap.error('--env dev ou --env prod é obrigatório: o ambiente em que a solução está '
                     'publicada. Cada um tem o seu Shared Drive.')
        drive, ambiente = (None if a.dry_run else PS.DriveHttp(a.solution_id, PS.AMBIENTES[a.env])), a.env
    try:
        envia(pacote, drive, a.drive_raiz, a.parte_mb, '.envio-%s.json' % ambiente, a.dry_run)
    except RuntimeError as e:
        log.error('[envia] %s', e)
        return 1
    if not a.dry_run:
        print('\nNo Stratos (só o master): /stratos/pacotes -> Check -> Activate -> restart.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
