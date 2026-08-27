# -*- coding: utf-8 -*-
"""Holidays Calendar — os calendários de feriado que a tela desenha e cria.

Quinta vertical, e a primeira em que a fronteira precisou de decisão: o grupo
tinha TRÊS referências de entrada, e as três eram para o `_anbima_holidays`.

Esse não é o calendário DESTA tela — é o calendário de dias úteis que o app
inteiro usa (o SLA da esteira, o aging do CGD, os schedulers, o D-1 das recons).
Ele é **horizontal**, e por isso ficou no `routes.py` esperando o `platform/`,
em vez de vir junto e obrigar meia dúzia de features a importar a vertical de
Feriados para saber se sexta é dia útil.

O que veio foi a tela: o registro de calendários, o Save de um feriado avulso e
a criação de um calendário a partir de planilha.
"""
