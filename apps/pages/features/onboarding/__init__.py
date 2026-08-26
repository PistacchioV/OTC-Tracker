# -*- coding: utf-8 -*-
"""Onboarding — o CGD que vem da lista do SharePoint (Overview e Tracking Docs).

Segunda vertical extraída do `routes.py`. Como a do Support Center, ela saiu por
ter ZERO referências de entrada; ao contrário dela, não havia teste da camada
HTTP — o `check_cgd_docs.py` protege o MÓDULO (aging, etapas, formulário) e não
o que a tela recebe. O `check_onboarding_api.py` foi escrito ANTES da extração,
com o código ainda no lugar, para o verde valer como linha de base.

**O domínio desta feature é o `apps/pages/cgd_docs.py`**, e ele fica onde está:
a Recon de CGD e o /mapping também o consultam, então ele é horizontal, não
vertical. Separá-lo em regra e persistência é outra fatia — hoje ele mistura as
duas (o `aging_of` e o `pending_stage` ao lado do DuckDB).

    entrypoint.py   as 6 rotas: sessão → consulta/comando → JSON
    commands.py     gravar e apagar, a linha e o lote
    queries.py      as duas leituras da tela
    infra/          o estado do banco e o formato do payload
"""
