# -*- coding: utf-8 -*-
"""Pending Confirmations Spreadsheet Metrics — a planilha do time global.

Grava "PENDING - Outstanding Confirmation OTC.xlsx" no share de Movimento
(sobrescrevendo a anterior) todo dia útil ANBIMA às 10:45 BRT (= 19:15 IST).
O layout inteiro é contrato com quem consome por OLEDB; data anterior grava a
FOTO do snapshot daquele dia no MESMO nome canônico, com a `ref` no status.

O `_pcx_is_bizday` NÃO veio junto: é o calendário útil de meia dúzia de
schedulers (plataforma) e ficou no `routes.py`.
"""
