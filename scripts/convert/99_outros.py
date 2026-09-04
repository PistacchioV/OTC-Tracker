#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert 99_outros — os blocos de cache/ que não têm arquivo próprio.

O ESCOPO é o RESTO de cache/: todo bloco que não tem arquivo próprio ao lado
deste. Ele existe para um bloco NOVO nunca ficar sem conversor, e a poda é por
CAMINHO — tanto uma rotina nova (`cache/equity`) quanto uma pasta nova dentro de
uma já coberta (`cache/new deals/Equity`) caem aqui. Hoje os cobertos são:

  - new deals/NDF/Vanilla
  - new deals/NDF/FwdStart
  - new deals/NDF/OtherPublisher
  - new deals/NDF/Commodities
  - new deals/Option/FXO
  - new deals/Option/Commodities
  - new deals/Swap/Rates
  - new deals/Swap/Commodities
  - new deals/Intrag/NDF
  - new deals/Intrag/Option
  - new deals/Intrag/Swap
  - b3 files/NDF
  - b3 files/Option
  - b3 files/Swap
  - b3 files/Operations
  - daily settlement/otm-settlement
  - daily settlement/ndf-cockpit
  - daily settlement/operations-b3
  - daily settlement/operacoes-jpm
  - daily settlement/operacoes-mgt
  - daily settlement/eventos-swap-jpm
  - daily settlement/eventos-swap-mgt
  - daily settlement/latam-desk-position
  - daily settlement/swap-kapital-hybrids
  - daily settlement/cognos
  - daily settlement/br-onshore-settlements
  - daily settlement/other-products-summary
  - pending-confirmation
  - payrec
  - reconciliation/fxo
  - reconciliation/cgd
  - reconciliation/payrec
  - new deals/Intrag/DCE Option

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
                 conversores=('daily',), excluir=['new deals/NDF/Vanilla', 'new deals/NDF/FwdStart', 'new deals/NDF/OtherPublisher', 'new deals/NDF/Commodities', 'new deals/Option/FXO', 'new deals/Option/Commodities', 'new deals/Swap/Rates', 'new deals/Swap/Commodities', 'new deals/Intrag/NDF', 'new deals/Intrag/Option', 'new deals/Intrag/Swap', 'b3 files/NDF', 'b3 files/Option', 'b3 files/Swap', 'b3 files/Operations', 'daily settlement/otm-settlement', 'daily settlement/ndf-cockpit', 'daily settlement/operations-b3', 'daily settlement/operacoes-jpm', 'daily settlement/operacoes-mgt', 'daily settlement/eventos-swap-jpm', 'daily settlement/eventos-swap-mgt', 'daily settlement/latam-desk-position', 'daily settlement/swap-kapital-hybrids', 'daily settlement/cognos', 'daily settlement/br-onshore-settlements', 'daily settlement/other-products-summary', 'pending-confirmation', 'payrec', 'reconciliation/fxo', 'reconciliation/cgd', 'reconciliation/payrec', 'new deals/Intrag/DCE Option'],
                 doc=__doc__))
