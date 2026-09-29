# -*- coding: utf-8 -*-
"""Pending Confirmation › Dashboard — a fila de pendências numa tabela dinâmica.

Linhas por Economic Group × Owner × Signature Type, colunas por trimestre da
Trade Date × Pending Status, e o total. O filtro é a FAIXA de pendência (a
coluna Status do Pending Confirmation Main, que o app calcula pelo aging): a
tela escolhe as faixas e a tabela se refaz.

A fonte é a MESMA do Daily Metric (`_pc_latest_snapshot_rows`, plataforma): o
banco `pending` lido ao vivo, sem as linhas que já contam como resolvidas. Duas
leituras diferentes da mesma fila fariam a tela e o e-mail cobrarem números
diferentes no mesmo dia.
"""
