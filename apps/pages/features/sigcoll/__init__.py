# -*- coding: utf-8 -*-
"""Signature Collection ("Cobrança") — os rascunhos da coleta de assinatura.

Segrega as confirmações pendentes de assinatura (base: Pending Confirmation)
por contraparte e gera UM rascunho .eml editável por contraparte (.zip quando
há vários) — o espelho da macro "MassEmail" da planilha legada, gerando revisão
em vez de envio. To = contatos de confirmação do Counterparty Details; Cc = os
bankers do grupo (cadastro `bankers-email`) + OTC Ops + IS Trade Doc.
"""
