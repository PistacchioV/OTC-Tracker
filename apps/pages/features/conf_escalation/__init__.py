# -*- coding: utf-8 -*-
"""Confirmations Escalation — a cobrança das validações da esteira.

Lê a MESMA `manual_conf.load_all()` com o `Pending` derivado que o Track e o
Monitor mostram — um relatório que conta de outro jeito cobra uma fila que a
tela não tem, e a mesa deixa de acreditar nos dois.

Dois disparos no mesmo horário (17:00 BRT):

  * ROTINA — segunda e quinta (feriado ROLA para o próximo dia útil), o pacote
    completo: OTC + Sales Support (MO) + um e-mail POR GRUPO de Front Office;
  * ESCALATION — todo dia útil. Só o que está no ÚLTIMO DIA do prazo de MO ou
    já vencido, com lista própria: escalar diariamente para quem já recebe a
    rotina transformaria a cobrança em ruído.

Nada pendente, nada enviado — e-mail vazio é o jeito mais rápido de a mesa
parar de ler a rotina.

O `_otc_app_url` (endereço absoluto para botão de e-mail) NÃO veio junto: é
plataforma (CLAUDE.md §7) e ficou no `routes.py`. Como no `bacc`, o scheduler
roda aqui e o REGISTRO fica no wiring do routes.
"""
