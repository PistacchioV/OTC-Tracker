# -*- coding: utf-8 -*-
"""Accrual de Swap — fatores por LOB, ciclo da linha, geração e recon.

Fronteira decidida: `domain.py` (layout das colunas, parse/formatação de fator,
o de-para de chave do Código IF, a aplicação dos fatores e as consultas sobre a
tabela em memória — PURO, sem `routes`), `queries.py` (o build do dia a partir
da posição de swap), `infra/persistence.py` (o arquivo-dia e a pasta de origem
no share), `infra/mappers.py` (planilha de fatores → mapa, um formato por LOB) e
`commands.py` (os arquivos de Batch Conecta e o batimento).

Ficaram no `routes` de propósito: `_acc_digits` (o b3-accounts e o NDF
Commodities comparam contas com ele), `_accrual_lob` (o forecast rotula pela
mesma regra), `_accrual_parse_date` (o MtM parseia a data com ele) e a lista
`_ACC_ENDPROC_CC` (o e-mail do forecast copia as mesmas caixas).
"""
