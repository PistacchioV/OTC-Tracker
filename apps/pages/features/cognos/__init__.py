# -*- coding: utf-8 -*-
"""Cognos (FXO Detail) — o import do dia e a coleta da tela.

Fronteira decidida: `domain.py` (a data de referência do payload — puro),
`queries.py` (as linhas formatadas do arquivo-dia) e `commands.py` (a
importação). O STORE por dia (`_cog_json_path/_cog_load/_cog_save/_cog_find/
_cog_read_rows/_cog_extract` e as colunas `_COG_*`) fica no `routes`: o Save
Daily Settlement grava o mesmo arquivo e o Settlement Advice de Opção lê o PRM
de lá.
"""
