# -*- coding: utf-8 -*-
"""Recon de FXO — posição B3/CETIP (DPOSICAO `.OPC`) × Athena (EOD FXO).

Terceira vertical. O **motor é o `apps/pages/recon_fxo.py`** e fica onde está:
ele é o domínio desta recon (a chave, a perna interna, os cortes por cadastro, o
comentário) e já tem o `check_recon_fxo.py` com 117 asserções em cima dele.

O que estava no `routes.py` era só a casca — sessão, data, o encaminhamento dos
arquivos do upload manual — e ela guardava três decisões que não davam erro
nenhum quando caíam. Elas agora estão presas pelo `check_recon_fxo_api.py`,
escrito ANTES desta extração.

    entrypoint.py   as 4 rotas
    commands.py     rodar a recon e gravar a justificativa
    queries.py      ler a última recon
    infra/          o seed dos cadastros que o motor não tem como semear
"""
