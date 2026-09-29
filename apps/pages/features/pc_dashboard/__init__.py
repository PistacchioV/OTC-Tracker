# -*- coding: utf-8 -*-
"""Pending Confirmation › Dashboard — a fila de pendências numa tabela dinâmica.

Linhas por Economic Group × Owner × Signature Type, colunas por trimestre da
Trade Date × Pending Status, e o total. O filtro é a FAIXA de pendência (a
coluna Status do Pending Confirmation Main, que o app calcula pelo aging): a
tela escolhe as faixas e a tabela se refaz.

A fonte é o banco `pending` do Pending Confirmation, lido AO VIVO a cada
chamada (`_pc_load_rows('pending', strict=True)`) — a mesma base que o Main
mostra —; a tela lê ao abrir, se atualiza sozinha e o Refresh lê na hora.
"""
