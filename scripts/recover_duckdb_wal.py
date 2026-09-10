#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recover_duckdb_wal.py — tira um banco do LIMBO DE CHECKPOINT do DuckDB,
recuperando-o FORA do share, e o devolve magro.

    python scripts/recover_duckdb_wal.py [--db-dir PASTA] [--only SUBCAMINHO]
                                         [--work-dir PASTA_LOCAL] [--dry-run]
                                         [--no-slim] [--all]

O estado (HANDOFF §442): ao lado do `.db` há um `.wal.checkpoint` — um
checkpoint do DuckDB COMEÇOU (o `.wal` bateu o `checkpoint_threshold` de
16 MB), as gravações seguintes foram para esse segundo WAL e o processo
morreu antes de terminar (restart) — e/ou um `.wal.recovery`, a fusão dos
dois WALs que TODA abertura em escrita refaz antes de repetir o replay. Na
instância eram 75 MB a 1,1 GB por banco, com o `.db` parado em 31/08: cada
abertura, mesmo só leitura, relia tudo isso pelo share (minutos), o
`store-import` ficava meia hora dentro do `duckdb.connect` segurando a trava
exclusiva, e o `slim_duckdb.py` travava no `ATTACH` deixando `.db.slim` de
12 KB. O DuckDB sai do limbo sozinho num disco local em segundos; pelo share
nunca chega ao fim antes do restart seguinte.

O que este script faz, banco a banco (só nos que estão em limbo — ver
`data_store.wal_em_limbo`; `--all` pega qualquer `.wal`):
  1. copia `.db` + WALs para `--work-dir` (local; padrão
     `%LOCALAPPDATA%\\OTC-Tracker\\recover`);
  2. abre a cópia em escrita (o DuckDB funde e refaz o replay), `CHECKPOINT`,
     fecha — e confere que não sobrou WAL nenhum;
  3. emagrece a cópia (`slim_duckdb.emagrecer`, a forma do §437; `--no-slim`
     pula) e lê o `_manifest` dela;
  4. copia de volta como `<db>.novo`, MOVE o `.db` velho e os WALs para
     `db/_recuperado/<AAAAMMDD-HHMMSS>/<caminho>` (renome: instantâneo no
     share; apague a pasta quando o app estiver de pé e conferido), troca o
     `.novo` pelo `.db` e relê o `_manifest` no share.

Rode com TODAS as instâncias PARADAS (a trava exclusiva da camada é tomada,
mas um `store-import` preso a segura por meia hora), na MESMA versão de
duckdb da instância (o WAL é da versão que o escreveu), a partir do python do
`.bat`. `--dry-run` só lista os bancos e os MB.
"""
import argparse
import io
import os
import shutil
import sys
import tempfile
import time
import traceback
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

import duckdb                                                # noqa: E402
from apps.pages import data_store as _store                 # noqa: E402
import slim_duckdb                                          # noqa: E402


def _mb(n):
    return '%.0f MB' % (n / 1e6)


def _diz(msg):
    print(msg, flush=True)


def _manifest_linhas(db):
    """Linhas do `_manifest` (ou -1 quando o banco não é do armazém), abrindo só leitura."""
    con = duckdb.connect(db, read_only=True)
    try:
        if not con.execute("SELECT count(*) FROM information_schema.tables "
                           "WHERE table_schema='main' AND table_name='_manifest'").fetchone()[0]:
            return -1
        return con.execute('SELECT count(*) FROM main._manifest').fetchone()[0]
    finally:
        con.close()


def _work_dir_padrao():
    base = os.environ.get('LOCALAPPDATA') or tempfile.gettempdir()
    return os.path.join(base, 'OTC-Tracker', 'recover')


def recuperar(db, work_dir, db_dir, slim=True, carimbo=None):
    """Um banco. Devolve o resumo (dict). Levanta se qualquer conferência falhar
    — e aí o share fica como estava (a troca é o ÚLTIMO passo)."""
    irm = _store.wal_irmaos(db)
    nome = os.path.basename(db)
    local = os.path.join(work_dir, nome)
    resumo = {'db': db, 'wal_mb': sum(irm.values()) / 1e6, 'irmaos': irm}
    os.makedirs(work_dir, exist_ok=True)
    for s in ('',) + _store.WAL_SUFIXOS + ('.slim', '.novo'):
        if os.path.isfile(local + s):
            os.remove(local + s)
    # 1. para o disco local
    t0 = time.time()
    shutil.copy2(db, local)
    for s in irm:
        shutil.copy2(db + s, local + s)
    resumo['t_copia'] = time.time() - t0
    _diz('     copiado %s + %s de WAL em %.0fs' % (_mb(os.path.getsize(db)), _mb(sum(irm.values())),
                                                  resumo['t_copia']))
    # 2. o DuckDB recupera no local
    t0 = time.time()
    con = duckdb.connect(local)
    try:
        con.execute('CHECKPOINT')
    finally:
        con.close()
    sobras = _store.wal_irmaos(local)
    if sobras:
        raise RuntimeError('%s: depois do CHECKPOINT ainda há WAL na cópia local (%s)'
                           % (db, ', '.join(sobras)))
    resumo['t_recupera'] = time.time() - t0
    resumo['manifest'] = _manifest_linhas(local)
    _diz('     recuperado em %.0fs; manifest com %s linha(s)'
         % (resumo['t_recupera'], resumo['manifest'] if resumo['manifest'] >= 0 else 'n/a'))
    # 3. magro
    resumo['slim'] = None
    if slim and resumo['manifest'] >= 0:
        r = slim_duckdb.emagrecer(local)
        if r and not r.get('pulado'):
            resumo['slim'] = r
            _diz('     emagrecido: %d tabela(s), %d apagada(s), %s → %s'
                 % (r['magras'], r['apagadas'], _mb(r['bytes_antes']), _mb(r['bytes_depois'])))
            if _manifest_linhas(local) != resumo['manifest']:
                raise RuntimeError('%s: o manifest mudou no slim — não troquei' % db)
    # 4. de volta ao share — a troca é o último passo
    t0 = time.time()
    novo = db + '.novo'
    shutil.copy2(local, novo)
    carimbo = carimbo or datetime.now().strftime('%Y%m%d-%H%M%S')
    rel = os.path.relpath(db, db_dir)
    guarda = os.path.join(db_dir, _store.RECUPERADO_DIR, carimbo, os.path.dirname(rel))
    os.makedirs(guarda, exist_ok=True)
    for s in ('',) + _store.WAL_SUFIXOS + ('.slim',):
        if os.path.isfile(db + s):
            os.replace(db + s, os.path.join(guarda, nome + s))
    os.replace(novo, db)
    resumo['guardado_em'] = guarda
    no_share = _manifest_linhas(db)
    if no_share != resumo['manifest']:
        raise RuntimeError('%s: o manifest no share tem %s linha(s) e o recuperado %s'
                           % (db, no_share, resumo['manifest']))
    resumo['t_volta'] = time.time() - t0
    resumo['bytes_depois'] = os.path.getsize(db)
    _diz('     no lugar (%s) em %.0fs; o antigo está em %s' % (_mb(resumo['bytes_depois']),
                                                              resumo['t_volta'], guarda))
    return resumo


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db-dir', default=None, help='a pasta db/ (padrão: Config.DATABASE_DIR)')
    ap.add_argument('--only', default='', help='subcaminho dentro de db/ (padrão: tudo)')
    ap.add_argument('--work-dir', default=None,
                    help='pasta LOCAL de trabalho (padrão: %%LOCALAPPDATA%%\\OTC-Tracker\\recover)')
    ap.add_argument('--dry-run', action='store_true', help='só lista os bancos em limbo e os MB')
    ap.add_argument('--no-slim', action='store_true', help='não emagrece de caminho')
    ap.add_argument('--all', action='store_true',
                    help='recupera qualquer banco com WAL ao lado, não só os em limbo')
    args = ap.parse_args(argv)
    db_dir = args.db_dir
    if not db_dir:
        from apps.config import Config
        db_dir = Config.DATABASE_DIR
    raiz = (os.path.join(db_dir, *args.only.replace('\\', '/').strip('/').split('/'))
            if args.only else db_dir)
    work_dir = args.work_dir or _work_dir_padrao()
    alvos = []
    for pasta, dirs, arquivos in os.walk(raiz):
        dirs[:] = sorted(d for d in dirs if not d.startswith(_store.RECUPERADO_DIR))
        for a in sorted(arquivos):
            if not a.lower().endswith('.db'):
                continue
            db = os.path.join(pasta, a)
            irm = _store.wal_irmaos(db)
            if irm and (args.all or _store.wal_em_limbo(irm)):
                alvos.append((db, irm))
    _diz('%d banco(s) %s em %s%s' % (len(alvos), 'com WAL' if args.all else 'em limbo de checkpoint',
                                     raiz, ' (dry-run)' if args.dry_run else ''))
    for db, irm in alvos:
        _diz('  %s: %s' % (os.path.relpath(db, db_dir),
                           ', '.join('%s %s' % (s, _mb(b)) for s, b in sorted(irm.items()))))
    if args.dry_run or not alvos:
        return 0
    _diz('trabalho local em %s' % work_dir)
    carimbo = datetime.now().strftime('%Y%m%d-%H%M%S')
    erros = []
    for db, _irm in alvos:
        _diz('  -> %s' % os.path.relpath(db, db_dir))
        trava = None
        t0 = time.time()
        try:
            trava = slim_duckdb._trava(db)
            recuperar(db, work_dir, db_dir, slim=not args.no_slim, carimbo=carimbo)
            _diz('  ok   %s em %.0fs' % (os.path.relpath(db, db_dir), time.time() - t0))
        except Exception:                                    # noqa: BLE001
            erros.append(db)
            _diz('  ERRO %s\n%s' % (db, traceback.format_exc()))
        finally:
            if trava is not None:
                trava.release()
    if erros:
        _diz('%d banco(s) com erro — o share ficou como estava neles' % len(erros))
        return 1
    _diz('pronto: o que foi substituído está em %s (apague depois de conferir o app)'
         % os.path.join(db_dir, _store.RECUPERADO_DIR, carimbo))
    return 0


if __name__ == '__main__':
    sys.exit(main())
