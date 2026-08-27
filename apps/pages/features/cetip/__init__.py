# -*- coding: utf-8 -*-
"""Save CETIP Files — a rotina que filtra, renomeia e distribui os arquivos B3.

Fronteira decidida: `domain.py` (o catálogo de comportamento por arquivo, o
reconhecimento do nome padrão × data e os nomes de saída — PURO, com o logger
vindo do `logging` direto), `queries.py` (o cadastro `cetip-files`, que é a
regra VIVA de quais arquivos existem), `infra/persistence.py` (destinatários,
cópia do arquivo do dia e o JSON de posição), `infra/mappers.py` (cabeçalho do
arquivo → índice de coluna) `infra/mail.py` (o MIME e o envio) e `commands.py`
(o recorte do BACC, as cópias e a distribuição das quatro caixas).

Ficaram no `routes` de propósito: as RAÍZES (`CETIP_SOURCE_ROOT`/`DEST_ROOT`,
que a recon_fxo e a recon_cgd também leem), as caixas de e-mail e o
`_CETIP_FILES_SEED` — seed do cadastro no `_MAPPING_DEFS`, que é registro de
plataforma.
"""
