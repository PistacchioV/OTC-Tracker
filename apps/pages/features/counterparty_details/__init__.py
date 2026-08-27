# -*- coding: utf-8 -*-
"""Counterparty Details — o registro por SPN (CGD, contatos, banking, NET) com
maker/checker por item, e o import da planilha CONTATO DE CLIENTES.

Fronteira decidida: os LEITORES e os normalizadores são da
`platform/counterparty.py` (`_cpd_path/_cpd_load/_cpd_find/_cpd_save_list`,
`_norm_spn/_bank_norm/_cgd_norm/_contacts_norm/_net_norm` e o parser `_cc_*`)
— summaries, advices, TED e o e-mail de cobrança leem o mesmo registro. Aqui
vive só o que é DESTA tela: `domain.py` (exibição e payload), `infra/
persistence.py` (achar/criar o record de um SPN normalizado) e `commands.py`
(o import da planilha e o aviso do sino do maker/checker).
"""
