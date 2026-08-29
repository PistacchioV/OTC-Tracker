#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert 02_pending_confirmation — a rotina `pending-confirmation` de cache/.

O ESCOPO é UMA rotina de cache/: **pending-confirmation**.

Os snapshots diários do Pending Confirmation.

Cada produto vira um banco e a pasta db/ espelha a árvore de cache/; só
ano/mês/dia não viram pasta — cada dia é uma tabela dentro do banco.

A janela padrão é de 12 meses (`--meses`); `--meses 0` traz o histórico
inteiro, e é essa passada que remove os bancos de formato antigo.

Usa o `Config` do app para achar a origem e o destino — é a versão para rodar
DENTRO do checkout. Para uma máquina sem o código do OTC Tracker existe o
`scripts/standalone/`, com o mesmo corte em fatias.

As fatias são independentes: os bancos são um por produto, então duas nunca
escrevem no mesmo arquivo e podem rodar AO MESMO TEMPO, em máquinas
diferentes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from convert_json_to_duckdb import run    # noqa: E402


if __name__ == '__main__':
    sys.exit(run(escopo='cache/pending-confirmation (arquivo-dia)',
                 conversores=('daily',), familias=['pending-confirmation'],
                 doc=__doc__))
