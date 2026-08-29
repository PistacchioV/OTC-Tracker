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

A quebra é POR PRODUTO e a pasta `db/` ESPELHA a árvore de origem (§336/§342):
`cache/new deals/NDF/Vanilla/AAAA/MM/DD` vira `db/cache/new deals/NDF/Vanilla.db`
com cada dia como uma TABELA — só ano/mês/dia não viram pasta. Onde a rotina não
se ramifica em pastas, quem dá o banco é o NOME do arquivo
(`db/cache/daily settlement/otm-settlement.db`). Os demais JSONs viram um banco
cada, na pasta do JSON (`db/mappings/mt300.db`). Esta carga completa é também
quem REMOVE os bancos dos desenhos anteriores — o espelho vivo, que enxerga um
arquivo por vez, não tem como saber que um banco ficou órfão.

**A janela padrão é de 12 meses** (`--meses`), porque a carga no share leva
horas de rede e o dado recente é o que a mesa consulta; o histórico entra numa
SEGUNDA passada (`--meses 0`), que é também a única que limpa os bancos de
formato antigo. Ver §345.

Uso:
    python scripts/convert_json_to_duckdb.py [--only holidays|refdata|datasets|daily]
        [--data-dir X] [--out-dir Y] [--force] [--dry-run] [--meses N]

**Para repartir entre várias pessoas** — a carga inteira leva horas e ninguém
precisa esperar a fila — use `scripts/convert/`: uma fatia por BLOCO de `cache/`
(`01_cadastros`, um `02_*` por bloco, o `99_outros`) que rodam ao mesmo tempo,
sobre o `run()` deste arquivo. As duas rotinas grandes vão repartidas até o
PRODUTO, então o Vanilla, o FXO e o Swap/Rates são fatias independentes. O `00_completo.py` de lá é este script. Para uma
máquina SEM o código do app existe o `scripts/standalone/`, com o mesmo corte.

Testes de regressão: `scripts/tests/check_json_to_duckdb.py` (o motor) e
`scripts/tests/check_convert_split.py` (as fatias).
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
    convert_daily, convert_datasets, convert_holidays, convert_refdata,
    data_de_corte)


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


def run(argv=None, escopo=None, conversores=None, familias=None, excluir=None,
        doc=None):
    """A implementação ÚNICA da CLI, parametrizada pelo ESCOPO.

    `scripts/convert_json_to_duckdb.py` a chama sem escopo (a carga completa) e
    cada arquivo de `scripts/convert/` a chama com o seu — é o que dá o mesmo
    corte em blocos do `scripts/standalone/` sem uma segunda cópia da CLI.
    A diferença entre os dois splits é só de DEPENDÊNCIA: aqui os caminhos saem
    do `Config`, lá são fixos porque a máquina não tem o código do app.

    `conversores` restringe as ETAPAS (o `01_cadastros` não roda `daily`);
    `familias`/`excluir` restringem as rotinas de `cache/` dentro do `daily`.
    """
    ap = argparse.ArgumentParser(
        description=(doc or __doc__).splitlines()[0])
    ap.add_argument('--data-dir', default=None, help='origem dos JSONs (padrão: Config.DATA_DIR)')
    ap.add_argument('--out-dir', default=None,
                    help='destino dos .db (padrão: Config.DATABASE_DIR — a pasta db/ existente)')
    todos = {'holidays': convert_holidays, 'refdata': convert_refdata,
             'datasets': convert_datasets, 'daily': convert_daily}
    etapas = [n for n in todos if n in (conversores or todos)]
    if len(etapas) > 1:
        ap.add_argument('--only', choices=tuple(etapas), default=None)
    ap.add_argument('--force', action='store_true', help='reconverte mesmo sem mudança')
    ap.add_argument('--dry-run', action='store_true', help='só lista o que converteria')
    # A janela só existe onde há ARQUIVO-DIA: uma fatia só de cadastros não a
    # recebe, porque um argumento que não muda nada é pior do que não existir.
    tem_janela = 'daily' in etapas
    if tem_janela:
        ap.add_argument('--meses', type=int, default=12,
                        help='janela dos ARQUIVO-DIA: converte só os dos últimos N '
                             'meses (padrão 12). Use 0 para o histórico INTEIRO — é '
                             'a segunda passada, e é ela que remove os bancos de '
                             'formato antigo.')
    # `--bloco` desce mais um nível DENTRO da fatia — é para repartir onde a
    # instância tem mais pasta do que a dev, sem precisar de um arquivo novo.
    # Ele SUBSTITUI o escopo da fatia, não soma: rodar a fatia inteira e um
    # bloco dela ao mesmo tempo poria dois processos no mesmo banco.
    if familias and len(familias) == 1:
        ap.add_argument('--bloco', default=None,
                        help='restringe a UMA subpasta desta fatia (ex.: --bloco '
                             'Vanilla). Substitui o escopo da fatia — não rode a '
                             'fatia inteira em paralelo com um bloco dela.')
    args = ap.parse_args(argv)
    if getattr(args, 'bloco', None):
        familias = [familias[0].rstrip('/') + '/' + args.bloco.strip().strip('/')]
        # O escopo IMPRESSO passa a ser o efetivo — deixá-lo no da fatia faria a
        # tela dizer que converteu mais do que converteu.
        escopo = 'cache/%s (arquivo-dia)' % familias[0]

    data_dir = os.path.abspath(args.data_dir or _default_data_dir())
    out_dir = os.path.abspath(args.out_dir or _default_out_dir(data_dir))
    desde = data_de_corte(getattr(args, 'meses', 0)) if tem_janela else None
    print('origem : %s' % data_dir)
    print('destino: %s' % out_dir)
    if tem_janela:
        # A janela é DECLARADA na tela: o recorte silencioso faria a segunda
        # passada (a do histórico) parecer desnecessária.
        print('janela : %s' % ('arquivo-dia a partir de %s (%d meses)'
                               % (desde.strftime('%d/%m/%Y'), args.meses) if desde
                               else 'histórico INTEIRO (--meses 0)'))
    if escopo:
        print('escopo : %s' % escopo)
    antigo = os.path.join(data_dir, 'duckdb')
    if os.path.isdir(antigo) and os.path.abspath(antigo) != out_dir:
        print('aviso  : %s era o destino da versão anterior — os bancos agora '
              'saem na pasta db/; a pasta antiga pode ser removida.' % antigo)

    escolhidos = [getattr(args, 'only', None)] if getattr(args, 'only', None) else etapas
    houve_erro = False
    for nome in escolhidos:
        extra = {'desde': desde, 'familias': familias, 'excluir': excluir} \
            if nome == 'daily' else {}
        stats = todos[nome](data_dir, out_dir, force=args.force,
                            dry_run=args.dry_run, **extra)
        print('\n== %s -> %s' % (nome, os.path.basename(stats['db'])))
        print('   convertidos: %d | inalterados: %d%s%s%s' % (
            len(stats['converted']), len(stats['skipped']),
            ' | fora da janela: %d' % len(stats['antigos'])
            if stats.get('antigos') else '',
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


def main(argv=None):
    """A carga COMPLETA — sem escopo, que é o que faz dela a única que remove os
    bancos dos desenhos anteriores e a única que enxerga colisão de tabela entre
    rotinas diferentes."""
    return run(argv, escopo='tudo (cadastros + todas as rotinas de cache/)')


if __name__ == '__main__':
    sys.exit(main())
