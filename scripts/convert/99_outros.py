#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert 99_outros — os blocos de cache/ que não têm arquivo próprio.

O ESCOPO é o RESTO de cache/: todo bloco que não tem arquivo próprio ao lado
deste. Ele existe para um bloco NOVO nunca ficar sem conversor, e a poda é por
CAMINHO — tanto uma rotina nova (`cache/equity`) quanto uma pasta nova dentro de
uma já coberta (`cache/new deals/Equity`) caem aqui. Hoje os cobertos são:

  - new deals/NDF
  - new deals/Option
  - new deals/Swap
  - new deals/Intrag
  - b3 files/NDF
  - b3 files/Option
  - b3 files/Swap
  - b3 files/Operations
  - daily settlement
  - pending-confirmation
  - payrec
  - reconciliation

Se não houver nada fora dessa lista, este script não faz nada, e isso é o
resultado esperado.

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
    sys.exit(run(escopo='cache/ menos os blocos com arquivo próprio',
                 conversores=('daily',), excluir=['new deals/NDF', 'new deals/Option', 'new deals/Swap', 'new deals/Intrag', 'b3 files/NDF', 'b3 files/Option', 'b3 files/Swap', 'b3 files/Operations', 'daily settlement', 'pending-confirmation', 'payrec', 'reconciliation'],
                 doc=__doc__))
