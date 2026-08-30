#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert 02_daily_settlement_swap_kapital_hybrids — o bloco `daily settlement/swap-kapital-hybrids` de cache/.

O ESCOPO é UM bloco de cache/: **daily settlement/swap-kapital-hybrids**.

O Swap Kapital Hybrids.

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
    sys.exit(run(escopo='cache/daily settlement/swap-kapital-hybrids (arquivo-dia)',
                 conversores=('daily',), familias=['daily settlement/swap-kapital-hybrids'],
                 doc=__doc__))
