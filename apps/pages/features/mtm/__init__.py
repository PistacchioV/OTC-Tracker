# -*- coding: utf-8 -*-
"""MtM — Swap Mark-to-Market por linha de negócio (+ COE).

Fronteira decidida: `domain.py` (o layout das duas tabelas, o reconhecimento do
arquivo pelo nome, o parse de número BR, as constantes de geração do arquivo B3
e as consultas sobre a tabela em memória — PURO), `queries.py` (o build do dia:
Swap × LOB, COE, a normalização dos zeros e a varredura da pasta),
`infra/persistence.py` (o arquivo-dia, a pasta de origem no share e o caminho
do dia), `infra/mappers.py` (planilha de valores → coluna Valor, um formato por
LOB, mais o de-para do Hybrids), `infra/mail.py` (os dois e-mails) e
`commands.py` (a geração das linhas do arquivo B3, a gravação no Batch Conecta
e o batimento).

`_mtm_path_for` mora em `infra/persistence`, não no domain: ele monta caminho
sobre o `MTM_JSON_ROOT` — pareceria regra, mas é disco.
"""
