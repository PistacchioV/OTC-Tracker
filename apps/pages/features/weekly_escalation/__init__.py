# -*- coding: utf-8 -*-
"""Weekly Escalation (CEM/EDG) — a cobrança semanal aos banqueiros, como RASCUNHO.

Confirmações pendentes há 30+ dias, separadas por LOB (CEM, EDG), agrupadas por
BANQUEIRO com o total de cada um e a quebra por EMPRESA (o nome do cliente, não
o grupo econômico).

Mesma entrega do Daily Metric, e pela mesma razão: é uma cobrança nominal, então
quem assina quer ler antes de sair — o Run gera um `.eml` com `X-Unsent: 1` que
a página baixa, e o TO/CC salvo vira o pré-preenchido do rascunho, não o
destinatário de um envio.
"""
