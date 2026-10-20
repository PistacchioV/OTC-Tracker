# -*- coding: utf-8 -*-
"""Projects (Apps › Projects) — os projetos do time, no desenho do Pane.

Uma lista de projetos (status On going / On hold / Concluded) e, para cada um,
a página com visão geral, marcos, burn-up, tarefas por status (com subtarefas e
comentários) e a atividade recente.

    entrypoint.py   as rotas: sessão → comando/consulta → JSON
    commands.py     escrita (projeto, tarefa, subtarefa, comentário, marco)
    queries.py      leitura e o payload que as telas desenham
    domain.py       as regras — validação, progresso, burn-up — puras, sem I/O
    infra/          o armazém (store.py) e o cadastro de usuários (people.py)
"""
