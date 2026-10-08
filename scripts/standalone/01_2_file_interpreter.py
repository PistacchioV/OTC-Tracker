#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""convert 01_file_interpreter — a pasta de cadastro `file-interpreter`.

Os templates e variantes do File Interpreter.

Versão AUTOCONTIDA: roda em QUALQUER máquina, sem o código do OTC Tracker por
perto — com o `_motor.py` desta pasta ao lado (copie a pasta inteira).
Requisito único:  pip install duckdb

    Origem : o static\data do share — o UNC
             (\\Nawest.ad.jpmorganchase.com\lac\BRA\intra\...) ou a letra I:,
             o que existir na máquina. `--data-dir` manda em qualquer caso.
    Destino: ...\static\data\db   (a pasta db dentro da origem)

Uso:
    python 01_2_file_interpreter.py
    python 01_2_file_interpreter.py --dry-run
    python 01_2_file_interpreter.py --data-dir "D:\outra\pasta" --out-dir "D:\saida"

O ESCOPO é UMA pasta de cadastro do DATA_DIR: **file-interpreter\**.

Os templates e variantes do File Interpreter.

É UM BANCO POR ARQUIVO, na mesma árvore do JSON (db\file-interpreter\<arquivo>.db),
com uma tabela por arquivo e a coluna _raw guardando o registro exato. Juntar a
pasta inteira num banco só criava contenção onde ela não precisa existir — o
espelho reconvertendo UM cadastro fechava a leitura dos outros.

Como os bancos são um por arquivo, este script NÃO escreve em nada que os outros
escrevem: pode rodar ao mesmo tempo que eles.

É IDEMPOTENTE e INCREMENTAL: cada banco guarda um `_manifest` com
caminho/mtime/tamanho e só reconverte o arquivo que mudou — rodar de novo com
nada alterado não reescreve nada. `--force` reconverte tudo; `--dry-run` só
lista. Erro num arquivo não para o resto: sai no resumo do fim.

GERADO por scripts/build_duckdb_standalone.py a partir de
apps/pages/json_to_duckdb.py — não edite à mão: mexer no motor e não regerar
estes arquivos é como eles passam a discordar.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _motor import (_data_dir_padrao, _resumo, convert_daily,  # noqa: F401
                        convert_datasets, convert_holidays, convert_refdata,
                        data_de_corte)
except ModuleNotFoundError as e:
    if e.name != '_motor':
        raise
    sys.exit('falta o _motor.py ao lado deste script: copie a pasta '
             'scripts/standalone INTEIRA')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--data-dir', default=None,
                    help='origem dos JSONs (padrão: o static\\data do share — o UNC '
                         'ou a letra I:, o que existir na máquina)')
    ap.add_argument('--out-dir', default=None,
                    help='destino dos .db (padrão: a pasta db dentro da origem)')
    ap.add_argument('--force', action='store_true', help='reconverte mesmo sem mudança')
    ap.add_argument('--dry-run', action='store_true', help='só lista o que converteria')
    args = ap.parse_args(argv)

    data_dir = os.path.abspath(args.data_dir or _data_dir_padrao())
    out_dir = os.path.abspath(args.out_dir or os.path.join(data_dir, 'db'))
    print('origem : %s' % data_dir)
    print('destino: %s' % out_dir)
    print('escopo : file-interpreter/ (um banco por arquivo)')

    houve_erro = [False]
    # UMA pasta de cadastro. Os bancos sao um por ARQUIVO, entao esta fatia nao
    # escreve em nada que as outras escrevem.
    _resumo('datasets', convert_datasets(data_dir, out_dir, force=args.force,
                                         dry_run=args.dry_run,
                                         pastas=['file-interpreter']), houve_erro)
    return 1 if houve_erro[0] else 0


if __name__ == '__main__':
    sys.exit(main())
