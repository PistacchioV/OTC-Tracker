# -*- coding: utf-8 -*-
"""Daily Metric — Outstanding Confirmation Brazil OTC, como RASCUNHO.

O Run não envia nada: ele gera um `.eml` com `X-Unsent: 1` que volta em base64
no JSON e a página baixa — a pessoa abre no Outlook, revisa e envia ela mesma.
É um relatório nominal, e quem assina quer ler antes de sair. Pelo mesmo motivo
o Bcc vai no HEADER (um envio de verdade o deixaria só no envelope): o rascunho
precisa pré-preencher o campo para a revisão.

A fonte é o último SNAPSHOT do Pending Confirmation e a história de métricas —
`_pc_latest_snapshot_rows` / `_pc_metrics_history`, que são plataforma (o
/pending-confirmation/metrics também as lê) e ficaram no `routes.py`.
"""
