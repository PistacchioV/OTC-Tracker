# -*- coding: utf-8 -*-
"""Intrag — o espelho intragrupo de NDF, Opção e Swap, e o mapeamento do B3 ID.

Fronteira decidida: `domain.py` (as duas contas do par JPM × Lawton, o nome do
participante de cada lado e a chave de casamento do retorno — PURO),
`queries.py` (achar a linha de um deal nos arquivos-dia e o CSV de retorno),
`infra/persistence.py` (os arquivos-dia, um por produto, e a gravação sob o
`_cache_lock`), `infra/mappers.py` (o CSV do Batch Conecta → `{chave: B3 ID}`)
e `commands.py` (as linhas espelhadas dos três produtos e o mapeamento).

O `routes._intrag_engine()` — o gancho que os saves do New Deals usam — aponta
para `commands`: os quatro nomes que ele expõe são todos de escrita.
"""
