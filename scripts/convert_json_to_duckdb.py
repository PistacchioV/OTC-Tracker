#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert_json_to_duckdb.py — a carga completa da conversão JSON → DuckDB.

CLI fina sobre o MOTOR `apps/pages/json_to_duckdb.py` (fase 2 da migração —
HANDOFF §324–§326): o motor virou módulo do app porque o **espelho vivo**
(`apps/pages/duck_mirror.py`) reconverte na hora cada JSON gravado, e a regra
de conversão não pode existir em dois lugares. Este script é a carga completa
— a primeira materialização numa instância, ou a reconciliação depois de um
período com o app parado. Idempotente e incremental (manifest por banco):
rodar de novo só reconverte o que mudou.

Origem: `Config.DATA_DIR` (na instância do JPM, o `...\\static\\data` do
share). Destino: `Config.DATABASE_DIR` — a pasta `db/` de todos os bancos
(CLAUDE.md §4). `--data-dir`/`--out-dir` mudam; com `--data-dir` apontando
para fora do `Config.DATA_DIR`, os bancos saem em `<data-dir>/db`, a mesma
regra do espelho vivo.

A quebra é POR PRODUTO (§336): o caminho inteiro de `cache/` nomeia cada
`daily_*.db` (`daily_new_deals_ndf_vanilla.db`, `daily_new_deals_option_fxo.db`)
e cada dia é uma tabela; o Daily Settlement, que não se ramifica em pastas,
quebra pelo NOME do arquivo (`daily_settlement_otm.db`, …). Os demais JSONs
viram um banco cada (`mappings_mt300.db`, `file_interpreter_termo.db`). Esta
carga completa é também quem REMOVE os bancos dos desenhos anteriores — o
espelho vivo, que enxerga um arquivo por vez, não tem como saber que um banco
ficou órfão.

Uso:
    python scripts/convert_json_to_duckdb.py [--only holidays|refdata|daily]
        [--data-dir X] [--out-dir Y] [--force] [--dry-run]

Teste de regressão: `scripts/tests/check_json_to_duckdb.py`.
"""
import argparse
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)
# Fora do Windows o default `I:\` do share é relativo e o import do Config
# recusa; para ESTE script os caminhos relevantes são explícitos ou do
# DATA_DIR, então o default de dev (a raiz do repo) basta — é o mesmo que os
# scripts de teste fazem.
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)

from apps.pages.json_to_duckdb import (            # noqa: E402
    convert_daily, convert_datasets, convert_holidays, convert_refdata)


def _default_data_dir():
    from apps.config import Config
    return Config.DATA_DIR


def _default_out_dir(data_dir):
    """A pasta de TODOS os bancos (`Config.DATABASE_DIR`) quando a origem é o
    `DATA_DIR` do app; para uma origem avulsa, o `db/` ao lado dela — a mesma
    regra do `duck_mirror`."""
    from apps.config import Config
    if os.path.normpath(os.path.abspath(data_dir)) == os.path.normpath(Config.DATA_DIR):
        return Config.DATABASE_DIR
    return os.path.join(data_dir, 'db')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--data-dir', default=None, help='origem dos JSONs (padrão: Config.DATA_DIR)')
    ap.add_argument('--out-dir', default=None,
                    help='destino dos .db (padrão: Config.DATABASE_DIR — a pasta db/ existente)')
    ap.add_argument('--only', choices=('holidays', 'refdata', 'datasets', 'daily'),
                    default=None)
    ap.add_argument('--force', action='store_true', help='reconverte mesmo sem mudança')
    ap.add_argument('--dry-run', action='store_true', help='só lista o que converteria')
    args = ap.parse_args(argv)

    data_dir = os.path.abspath(args.data_dir or _default_data_dir())
    out_dir = os.path.abspath(args.out_dir or _default_out_dir(data_dir))
    print('origem : %s' % data_dir)
    print('destino: %s' % out_dir)
    antigo = os.path.join(data_dir, 'duckdb')
    if os.path.isdir(antigo) and os.path.abspath(antigo) != out_dir:
        print('aviso  : %s era o destino da versão anterior — os bancos agora '
              'saem na pasta db/; a pasta antiga pode ser removida.' % antigo)

    conversores = {'holidays': convert_holidays, 'refdata': convert_refdata,
                   'datasets': convert_datasets, 'daily': convert_daily}
    escolhidos = [args.only] if args.only else list(conversores)
    houve_erro = False
    for nome in escolhidos:
        stats = conversores[nome](data_dir, out_dir, force=args.force, dry_run=args.dry_run)
        print('\n== %s -> %s' % (nome, os.path.basename(stats['db'])))
        print('   convertidos: %d | inalterados: %d%s%s' % (
            len(stats['converted']), len(stats['skipped']),
            ' | já cobertos por outro conversor: %d' % len(stats['cobertos'])
            if stats.get('cobertos') else '',
            ' | fora deste conversor: %d' % len(stats['ignored'])
            if stats.get('ignored') else ''))
        for aviso in stats.get('avisos') or ():
            print('   ! %s' % aviso)
        for item in stats['converted']:
            print('   + %s' % item)
        for rel, erro in stats['errors']:
            houve_erro = True
            print('   ERRO %s: %s' % (rel, erro.strip().splitlines()[-1]))
    return 1 if houve_erro else 0


if __name__ == '__main__':
    sys.exit(main())
