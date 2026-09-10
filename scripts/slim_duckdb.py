#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slim_duckdb.py — emagrece os bancos de arquivo-dia do armazém, NO LUGAR.

    python scripts/slim_duckdb.py [--db-dir PASTA] [--only SUBCAMINHO] [--dry-run]

Por quê: o DuckDB lê o CATÁLOGO inteiro a cada `connect`, e as tabelas-dia
tinham as colunas tipadas do layout ao lado do `_raw` — 250 dias × 170
colunas do DPOSICAO-TER são 524 blocos de metadado (134 MB em sub-blocos de
4 KB), cada um uma ida e volta no share: minutos por abertura (HANDOFF §437).
O app só lê o `_raw`. Desde §437 o motor grava as tabelas-dia só com
`_seq`/`_raw`; este script leva os bancos JÁ existentes à mesma forma,
copiando do PRÓPRIO banco (nunca do JSON do disco, que está velho desde o
cutover): para cada banco de `cache/` com `_manifest`, um arquivo novo é
montado ao lado — listas só com `_seq`/`_raw`, payload-objeto só com a
`<tabela>__raw`, o resto copiado igual — e trocado pelo antigo.

Rode com o APP PARADO (o arquivo é substituído; um processo com o banco
aberto seguraria o antigo). Toma a trava exclusiva da camada para a
instância vizinha esperar. Idempotente: banco já magro é pulado.

Banco com `.wal.checkpoint`/`.wal.recovery` ao lado (o limbo de checkpoint
do DuckDB, HANDOFF §442) é RECUSADO com a mensagem: nele o `ATTACH` refaz o
replay do WAL inteiro pelo share. Esse passa pelo `recover_duckdb_wal.py`,
que recupera FORA do share e emagrece de caminho.
"""
import argparse
import io
import json
import os
import sys
import time
import traceback

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

import duckdb                                                # noqa: E402
from apps.pages import json_to_duckdb as core                # noqa: E402
from apps.pages import data_store as _store                 # noqa: E402


ORIGEM = '_slim_origem'


def _q(schema, tabela):
    return '%s.%s' % (core.q(schema), core.q(tabela))


def _tabelas(con, catalogo):
    return con.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_catalog = ? AND table_type = 'BASE TABLE' "
        "ORDER BY table_schema, table_name", [catalogo]).fetchall()


def _colunas(con, catalogo, schema, tabela):
    return [r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_catalog = ? "
        "AND table_schema = ? AND table_name = ? ORDER BY ordinal_position",
        [catalogo, schema, tabela]).fetchall()]


def _blocos_meta(con):
    try:
        return con.execute('SELECT count(*) FROM pragma_metadata_info()').fetchone()[0]
    except Exception:                                        # noqa: BLE001
        return -1


def planejar(con, catalogo):
    """(magras, apagadas, manifest_novo) — o que muda neste banco.

    `magras`: tabelas-lista com colunas além de `_seq`/`_raw`; `apagadas`:
    sub-tabelas e `__meta` de payload-objeto que já tem a `__raw`;
    `manifest_novo`: {path: targets} das linhas do manifest que mudam."""
    magras, apagadas, manifest_novo = [], [], {}
    linhas = con.execute('SELECT path, targets FROM %s._manifest' % core.q(catalogo)).fetchall()
    for path, targets in linhas:
        rel = str(path or '').split('#', 1)[0]
        alvo = core.target_of(rel)
        if not alvo or alvo[3] != core.KIND_DAILY:
            continue
        try:
            tg = json.loads(targets) if targets else []
        except ValueError:
            continue
        raws = [t for t in tg if t.endswith(core.RAW_SUFIXO)]
        if raws:
            sobra = [t for t in tg if t not in raws]
            if sobra:
                apagadas.extend(sobra)
                manifest_novo[path] = raws[:1]
            continue
        if len(tg) != 1:
            continue
        partes = [p for p in tg[0].split('.') if p]
        schema, tabela = (partes[0], partes[1]) if len(partes) == 2 else ('main', partes[-1])
        cols = _colunas(con, catalogo, schema, tabela)
        if '_raw' in cols and '_seq' in cols and len(cols) > 2:
            magras.append((schema, tabela))
    return magras, apagadas, manifest_novo


def emagrecer(db, dry_run=False):
    """Um banco: devolve um dict com o resumo, ou None quando não é do armazém.

    Banco em limbo de checkpoint do DuckDB (§442) é RECUSADO: o `ATTACH`
    refaria o replay do WAL inteiro pelo share — foi onde a primeira rodada
    na instância travou, deixando `.db.slim` de 12 KB ao lado. O caminho
    dele é o `recover_duckdb_wal.py`, que emagrece de caminho."""
    irm = _store.wal_irmaos(db)
    if _store.wal_em_limbo(irm):
        raise RuntimeError('%s: em recuperação de checkpoint (%s) — rode '
                           'scripts/recover_duckdb_wal.py com o app parado; ele emagrece de caminho'
                           % (db, ', '.join('%s %.0f MB' % (s, b / 1e6) for s, b in sorted(irm.items()))))
    novo = db + '.slim'
    trocado = False
    try:
        return _emagrecer(db, novo, dry_run)
    finally:
        # o `.slim` só fica quando virou o banco (o `os.replace` o consome);
        # pulado, sem manifest ou erro, ele sai — a rodada seguinte não pode
        # tropeçar num arquivo de 12 KB deixado por uma abertura que não deu
        if os.path.isfile(novo):
            os.remove(novo)
        if os.path.isfile(novo + '.wal'):
            os.remove(novo + '.wal')


def _emagrecer(db, novo, dry_run):
    con = duckdb.connect(novo if not dry_run else ':memory:')
    try:
        # O alias não pode ser o nome de banco nenhum: o DuckDB batiza o catálogo
        # principal pelo nome do arquivo, e `velho.db` colidiria com `AS velho`.
        con.execute("ATTACH '%s' AS %s (READ_ONLY)" % (db.replace("'", "''"), ORIGEM))
        if not con.execute("SELECT count(*) FROM information_schema.tables WHERE table_catalog=? "
                           "AND table_name='_manifest'", [ORIGEM]).fetchone()[0]:
            return None
        magras, apagadas, manifest_novo = planejar(con, ORIGEM)
        antes = _blocos_meta(con) if dry_run else None
        resumo = {'db': db, 'magras': len(magras), 'apagadas': len(apagadas),
                  'bytes_antes': os.path.getsize(db), 'blocos_antes': -1, 'blocos_depois': -1}
        if not magras and not apagadas:
            resumo['pulado'] = True
            return resumo
        if dry_run:
            return resumo
        apagar = set()
        for t in apagadas:
            partes = [p for p in t.split('.') if p]
            apagar.add((partes[0], partes[1]) if len(partes) == 2 else ('main', partes[-1]))
        magras_set = set(magras)
        for schema, tabela in _tabelas(con, ORIGEM):
            if (schema, tabela) in apagar:
                continue
            if schema != 'main':
                con.execute('CREATE SCHEMA IF NOT EXISTS %s' % core.q(schema))
            origem = '%s.%s' % (core.q(ORIGEM), _q(schema, tabela))
            destino = _q(schema, tabela)
            if (schema, tabela) in magras_set:
                con.execute('CREATE TABLE %s ("_seq" BIGINT, "_raw" VARCHAR)' % destino)
                con.execute('INSERT INTO %s SELECT CAST("_seq" AS BIGINT), "_raw" FROM %s '
                            'ORDER BY CAST("_seq" AS BIGINT)' % (destino, origem))
            else:
                con.execute('CREATE TABLE %s AS SELECT * FROM %s' % (destino, origem))
        for path, targets in manifest_novo.items():
            con.execute('UPDATE main._manifest SET targets = ? WHERE path = ?',
                        [json.dumps(targets), path])
        con.execute('DETACH %s' % core.q(ORIGEM))
        con.execute('CHECKPOINT')
    finally:
        con.close()
    # o novo abre e responde pelo manifest inteiro antes de tomar o lugar
    chk = duckdb.connect(novo, read_only=True)
    try:
        n_novo = chk.execute('SELECT count(*) FROM _manifest').fetchone()[0]
        resumo['blocos_depois'] = _blocos_meta(chk)
    finally:
        chk.close()
    old = duckdb.connect(db, read_only=True)
    try:
        n_velho = old.execute('SELECT count(*) FROM _manifest').fetchone()[0]
        resumo['blocos_antes'] = _blocos_meta(old)
    finally:
        old.close()
    if n_novo != n_velho:
        os.remove(novo)
        raise RuntimeError('%s: manifest com %d linhas no novo e %d no velho — não troquei'
                           % (db, n_novo, n_velho))
    for sufixo in ('.wal',):
        if os.path.isfile(db + sufixo):
            os.remove(db + sufixo)
    os.replace(novo, db)
    resumo['bytes_depois'] = os.path.getsize(db)
    return resumo


def _trava(db):
    """A trava exclusiva da camada (a instância vizinha espera); sem a camada
    (máquina sem o app inteiro), segue sem ela."""
    try:
        from apps.pages import database_access as DA
        return DA.hold_file_lock(db, write=True, timeout_seconds=30)
    except ImportError:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db-dir', default=None, help='a pasta db/ (padrão: Config.DATABASE_DIR)')
    ap.add_argument('--only', default='cache', help='subcaminho dentro de db/ (padrão: cache)')
    ap.add_argument('--dry-run', action='store_true', help='só lista o que mudaria')
    args = ap.parse_args(argv)
    db_dir = args.db_dir
    if not db_dir:
        from apps.config import Config
        db_dir = Config.DATABASE_DIR
    raiz = os.path.join(db_dir, *args.only.replace('\\', '/').strip('/').split('/')) if args.only else db_dir
    bancos = []
    for pasta, dirs, arquivos in os.walk(raiz):
        dirs[:] = [d for d in dirs if not d.startswith(_store.RECUPERADO_DIR)]
        for a in arquivos:
            if a.lower().endswith('.db'):
                bancos.append(os.path.join(pasta, a))
    bancos.sort()
    print('%d banco(s) em %s%s' % (len(bancos), raiz, ' (dry-run)' if args.dry_run else ''))
    total_antes = total_depois = 0
    erros = []
    for db in bancos:
        t0 = time.time()
        trava = None
        try:
            if not args.dry_run:
                trava = _trava(db)
            r = emagrecer(db, dry_run=args.dry_run)
        except RuntimeError as exc:
            erros.append(db)
            print('  !!   %s' % exc)
            continue
        except Exception:                                    # noqa: BLE001
            erros.append(db)
            print('  ERRO %s\n%s' % (db, traceback.format_exc()))
            continue
        finally:
            if trava is not None:
                trava.release()
        if r is None:
            continue
        rel = os.path.relpath(db, db_dir)
        if r.get('pulado'):
            print('  =    %s (já magro)' % rel)
            continue
        if args.dry_run:
            print('  ~    %s: %d tabela(s) a emagrecer, %d a apagar' % (rel, r['magras'], r['apagadas']))
            continue
        total_antes += r['bytes_antes']
        total_depois += r['bytes_depois']
        print('  ok   %s: %d emagrecida(s), %d apagada(s); metadado %d → %d blocos; %.0f → %.0f MB; %.1fs'
              % (rel, r['magras'], r['apagadas'], r['blocos_antes'], r['blocos_depois'],
                 r['bytes_antes'] / 1e6, r['bytes_depois'] / 1e6, time.time() - t0))
    if not args.dry_run:
        print('total: %.0f → %.0f MB' % (total_antes / 1e6, total_depois / 1e6))
    if erros:
        print('%d banco(s) com erro' % len(erros))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
