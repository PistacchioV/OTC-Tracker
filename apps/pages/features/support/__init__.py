# -*- coding: utf-8 -*-
"""Support Center — os chamados que a mesa abre para o time do OTC Tracker.

A primeira feature extraída do `routes.py`, e ela foi escolhida por dois
motivos que não se repetem em toda parte: NADA no resto do `routes.py` chamava
o código dela (zero referências de entrada), e o `check_tickets.py` já a
prendia ponta a ponta — 103 asserções por HTTP, cobrindo código de status,
permissão, notificação e e-mail. Extrair sem uma rede dessas é mudar 39 mil
linhas no escuro.

    entrypoint.py   as 6 rotas: sessão → comando/consulta → JSON
    commands.py     escrita (abrir, atualizar, comentar, apagar) + efeitos
    queries.py      leitura
    domain.py       as regras de quem vê e quem edita — puras, sem I/O
    infra/          o que fala com o mundo (banco, SMTP, formato de tela)
"""
