#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert 02_new_deals_intrag_dce_option — o bloco `new deals/Intrag/DCE Option` de cache/.

O ESCOPO é UM bloco de cache/: **new deals/Intrag/DCE Option**.

A opção de câmbio do DCE da Intrag (o extrato
ITAUDataExtract importado do bob-report, §409).
Nasceu depois das fatias (por isso é a última:
renumerar as outras trocaria o nome de vinte
scripts) e caía só no 99_outros:
sem banco próprio, parecia que o import não
gravava nada.

Cada produto vira um banco e a pasta db/ espelha a árvore de cache/; só
ano/mês/dia não viram pasta — cada dia é uma tabela dentro do banco.

A janela padrão é de 12 meses (`--meses`); `--meses 0` traz o histórico inteiro,
e é essa passada que remove os bancos de formato antigo.

Se nesta instância o bloco ainda for grande demais, `--bloco NOME` desce mais um
nível (ex.: `--bloco Vanilla`). Ele SUBSTITUI o escopo desta fatia — não rode a
fatia inteira em paralelo com um bloco dela.

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
    sys.exit(run(escopo='cache/new deals/Intrag/DCE Option (arquivo-dia)',
                 conversores=('daily',), familias=['new deals/Intrag/DCE Option'],
                 doc=__doc__))
