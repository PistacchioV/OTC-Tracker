#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert 01_control_panel — a pasta de cadastro `control-panel/`.

O ESCOPO é UMA pasta de cadastro do DATA_DIR: **control-panel/**.

O estado das rotinas do Control Panel.

É UM BANCO POR ARQUIVO, na mesma árvore do JSON: db/control-panel/<arquivo>.db, com
uma tabela por arquivo. Juntar a pasta inteira num banco só criava contenção
onde ela não precisa existir — o espelho reconvertendo UM cadastro fechava a
leitura dos outros.

Não recebe `--meses`: nenhum destes JSONs tem data para cortar.

GERADO por scripts/build_convert_split.py — não edite à mão.

Usa o `Config` do app para achar a origem e o destino: é a versão para rodar
DENTRO do checkout. Para uma máquina sem o código do OTC Tracker existe o
`scripts/standalone/`, com o mesmo corte em fatias.

As fatias são independentes: os bancos são um por produto, então duas nunca
escrevem no mesmo arquivo e podem rodar AO MESMO TEMPO, em máquinas diferentes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from convert_json_to_duckdb import run    # noqa: E402


if __name__ == '__main__':
    sys.exit(run(escopo='control-panel/ (um banco por arquivo)',
                 conversores=('datasets',), pastas=['control-panel'],
                 doc=__doc__))
