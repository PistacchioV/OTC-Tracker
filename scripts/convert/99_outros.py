#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert 99_outros — as rotinas de cache/ que não têm arquivo próprio.

O ESCOPO é o RESTO de cache/: toda rotina que não tem arquivo próprio ao lado
deste. Ele existe para uma rotina NOVA nunca ficar sem conversor — hoje as
cobertas são:

  - new deals
  - b3 files
  - daily settlement
  - pending-confirmation
  - payrec
  - reconciliation

Se não houver nenhuma rotina fora dessa lista, este script não faz nada, e isso
é o resultado esperado.

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
    sys.exit(run(escopo='cache/ menos as rotinas com arquivo próprio',
                 conversores=('daily',), excluir=['new deals', 'b3 files', 'daily settlement', 'pending-confirmation', 'payrec', 'reconciliation'],
                 doc=__doc__))
