#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert 01_cadastros — os cadastros sem pasta própria (calendários, RefData/CPD, raiz).

O ESCOPO são os cadastros que NÃO têm pasta própria ao lado deste script:

  - holiday_calendars.db  uma tabela por calendário do registro (+ _registry);
  - reference_data.db     refdata e counterparty_details, TUDO VARCHAR;
  - <arquivo>.db          os JSONs da RAIZ do DATA_DIR (Subjacente, Dominio, …).

As pastas com muitos arquivos saíram para fatias próprias — 01_1 em diante:

  - mappings
  - file-interpreter
  - control-panel
  - tickets

Este é o COMPLEMENTO delas, como o 99_outros é o dos blocos de cache/: pasta de
cadastro NOVA cai aqui sozinha, sem ninguém tocar em nada.

A pasta translations/ fica FORA de propósito: os 3 JSONs de i18n são os únicos
que permanecem como JSON. Os arquivo-dia de cache/ são dos outros scripts, e por
isso esta fatia não recebe `--meses`: nenhum destes JSONs tem data para cortar.

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
    sys.exit(run(escopo='cadastros: calendarios, RefData/CPD e os JSONs de raiz',
                 conversores=('holidays', 'refdata', 'datasets'),
                 excluir_pastas=['mappings', 'file-interpreter', 'control-panel', 'tickets'],
                 doc=__doc__))
