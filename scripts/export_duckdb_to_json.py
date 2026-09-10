# -*- coding: utf-8 -*-
"""Exporta os DuckDB de volta para os JSONs — o caminho do ROLLBACK (HANDOFF §434).

Desde 09/09/2026 o app grava e lê SÓ nos bancos: os JSONs do `DATA_DIR` que
ainda existem em disco são os de antes do cutover e não recebem escrita
nenhuma. Se a decisão for voltar ao desenho anterior (reverter o commit da
migração), este script é o que traz o dado gravado desde então de volta para
os arquivos, para o código antigo encontrá-lo onde sempre leu.

O que ele faz: para cada banco da pasta `db/` (`Config.DATABASE_DIR`, ou
`--db-dir`), lê o `_manifest` — uma linha por caminho de JSON que o banco
guarda — e reconstrói cada payload EXATO (lista de registros pelo `_seq`/
`_raw`; objeto pelo `__raw`; calendário pela tabela tipada), gravando em
`<DATA_DIR>/<caminho>`. Só escreve **o que tem diferença**: arquivo ausente
no disco, ou mais velho do que o carimbo do banco (o mtime que o manifest
guarda — o relógio da gravação pela app). `--force` reescreve tudo,
`--dry-run` só lista, `--only <prefixo>` restringe a uma subárvore
(`cache/new deals`, `mappings`).

Idempotente: rodar de novo sem nada mudado não grava nada. Não apaga nem
altera banco nenhum — é leitura dos bancos e escrita de arquivos.

    python scripts/export_duckdb_to_json.py --dry-run
    python scripts/export_duckdb_to_json.py
    python scripts/export_duckdb_to_json.py --only "cache/new deals" --force
"""
import argparse
import json
import os
import sys
import time
import traceback

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)

import duckdb                                                # noqa: E402

from apps.pages import json_to_duckdb as core                # noqa: E402


def _bancos(db_dir):
    for dirpath, dirs, files in os.walk(db_dir):
        dirs.sort()
        for f in sorted(files):
            if f.endswith('.db'):
                yield os.path.join(dirpath, f)


def _kind_of(rel, tabela_registry):
    """O `kind` de um caminho do manifest — o mesmo corte do `target_of`."""
    if rel in dict(core._REFDATA_TABLES):
        return core.KIND_REFDATA
    if rel == core.REGISTRY_FILE:
        return core.KIND_REGISTRY
    if '/' not in rel and rel.lower() in tabela_registry:
        return core.KIND_CALENDAR
    return core.KIND_DAILY if rel.startswith('cache/') else core.KIND_DATASET


def _registro(db_dir):
    """`{arquivo.lower(): tabela}` dos calendários — do `holiday_calendars.db`."""
    caminho = os.path.join(db_dir, 'holiday_calendars.db')
    if not os.path.isfile(caminho):
        return {}
    con = duckdb.connect(caminho, read_only=True)
    try:
        try:
            rows = [json.loads(r) for (r,) in con.execute(
                'SELECT "_raw" FROM "_registry" ORDER BY CAST("_seq" AS BIGINT)').fetchall()]
        except Exception:                                    # noqa: BLE001
            return {}
    finally:
        con.close()
    out = {}
    for r in rows:
        arq = str(r.get('file', '') or '').strip().lower()
        if arq:
            out[arq] = core.norm_ident(str(r.get('name', '') or '').strip(), 'cal')
    return out


def _tabela_de(rel, kind, targets, cal):
    if kind == core.KIND_REFDATA:
        return dict(core._REFDATA_TABLES)[rel]
    if kind == core.KIND_REGISTRY:
        return '_registry'
    if kind == core.KIND_CALENDAR:
        return cal[rel.lower()]
    # A tabela do caminho é a que o MOTOR diz (`target_of`): num payload-objeto
    # os targets são `<tabela>__meta` + `<tabela>__raw` (a própria `<tabela>`
    # pode nem existir), e "o primeiro que não é __raw" devolvia o `__meta` —
    # o `ler_payload` procurava `__meta__raw`, não achava, e o rollback dizia
    # "sem canal" (ou reconstruía uma lista das sub-tabelas). Com o `__raw`
    # presente, o nome sai dele; senão, do motor; por último, do manifest.
    for t in targets:
        nome = t.split('.', 1)[-1]
        if nome.endswith(core.RAW_SUFIXO):
            return nome[:-len(core.RAW_SUFIXO)]
    alvo = core.target_of(rel, cal)
    if alvo:
        return alvo[2]
    for t in targets:
        nome = t.split('.', 1)[-1]
        if not nome.endswith('__meta'):
            return nome
    return targets[0].split('.', 1)[-1] if targets else ''


def exportar(db_dir, data_dir, only='', force=False, dry_run=False):
    cal = _registro(db_dir)
    stats = {'escritos': 0, 'iguais': 0, 'erros': [], 'dbs': 0}
    only = (only or '').replace('\\', '/').strip('/')
    for db in _bancos(db_dir):
        try:
            con = duckdb.connect(db, read_only=True)
        except Exception as exc:                             # noqa: BLE001
            stats['erros'].append((db, str(exc).splitlines()[-1]))
            continue
        stats['dbs'] += 1
        try:
            try:
                linhas = core.manifest_rows(con)
            except Exception:                                # noqa: BLE001
                continue                                     # banco sem manifest: não é de dado
            for rel, (mtime, _fsize, targets) in sorted(linhas.items()):
                if only and not (rel == only or rel.startswith(only + '/')):
                    continue
                destino = os.path.join(data_dir, *rel.split('/'))
                if not force and os.path.isfile(destino) and os.path.getmtime(destino) >= mtime - 1e-6:
                    stats['iguais'] += 1
                    continue
                kind = _kind_of(rel, cal)
                schema = targets[0].split('.', 1)[0] if targets and '.' in targets[0] else 'main'
                tabela = _tabela_de(rel, kind, targets, cal)
                try:
                    payload = core.ler_payload(con, rel, kind, tabela, schema)
                except Exception:                            # noqa: BLE001
                    stats['erros'].append((rel, traceback.format_exc().splitlines()[-1]))
                    continue
                if payload is core.AUSENTE or payload is None:
                    stats['erros'].append((rel, 'sem canal de reconstrucao no banco'))
                    continue
                if dry_run:
                    print('  escreveria %s' % rel)
                    stats['escritos'] += 1
                    continue
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                tmp = destino + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as fh:
                    json.dump(payload, fh, ensure_ascii=False, indent=2)
                os.replace(tmp, destino)
                # o mtime do arquivo passa a ser o do banco: a segunda rodada não regrava
                os.utime(destino, (time.time(), mtime))
                stats['escritos'] += 1
        finally:
            con.close()
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db-dir', default=None, help='pasta dos .db (padrao: Config.DATABASE_DIR)')
    ap.add_argument('--data-dir', default=None, help='destino dos JSONs (padrao: Config.DATA_DIR)')
    ap.add_argument('--only', default='', help='so esta subarvore (ex.: "cache/new deals", "mappings")')
    ap.add_argument('--force', action='store_true', help='reescreve mesmo sem diferenca')
    ap.add_argument('--dry-run', action='store_true', help='so lista o que escreveria')
    args = ap.parse_args(argv)
    from apps.config import Config
    db_dir = os.path.abspath(args.db_dir or Config.DATABASE_DIR)
    data_dir = os.path.abspath(args.data_dir or Config.DATA_DIR)
    print('bancos em  %s' % db_dir)
    print('JSONs para %s%s' % (data_dir, ' (dry-run)' if args.dry_run else ''))
    t0 = time.time()
    stats = exportar(db_dir, data_dir, only=args.only, force=args.force, dry_run=args.dry_run)
    print('%d banco(s) lidos — %d arquivo(s) %s, %d iguais, %d erro(s) em %.1fs'
          % (stats['dbs'], stats['escritos'], 'a escrever' if args.dry_run else 'escritos',
             stats['iguais'], len(stats['erros']), time.time() - t0))
    for rel, erro in stats['erros'][:50]:
        print('  ERRO %s: %s' % (rel, erro))
    return 1 if stats['erros'] else 0


if __name__ == '__main__':
    sys.exit(main())
