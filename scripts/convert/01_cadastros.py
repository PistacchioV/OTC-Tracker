#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert 01_cadastros — os JSONs ÚNICOS (sem quebra por dia).

O ESCOPO são os JSONs ÚNICOS — os que NÃO têm quebra por dia:

  - holiday_calendars.db  uma tabela por calendário do registro (+ _registry);
  - reference_data.db     refdata e counterparty_details, TUDO VARCHAR;
  - <pasta>/<arquivo>.db  UM BANCO POR JSON para o resto — db/mappings/mt300.db,
                          db/control-panel/mt300_status.db,
                          db/file-interpreter/termo.db, e o JSON da raiz na raiz.

A pasta translations/ fica FORA de propósito: os 3 JSONs de i18n são os únicos
que permanecem como JSON. Os arquivo-dia de cache/ são dos outros scripts, e
por isso esta fatia não recebe `--meses`: nenhum destes JSONs tem data para
cortar.

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
    sys.exit(run(escopo='cadastros (sem quebra por dia)',
                 conversores=('holidays', 'refdata', 'datasets'),
                 doc=__doc__))
