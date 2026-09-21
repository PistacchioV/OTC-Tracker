# -*- coding: utf-8 -*-
"""O Deal Ticket solto no dropzone → o que o `domain` sabe ler.

xlsx/xlsm: UMA grade por aba (a primeira aba é o DT contra o cliente, a
segunda o B2B Banco × Atacama; 'Recap' e outras são ignoradas por não terem
Valor Base + Vencimento). A célula vira texto de forma determinística: data →
ISO; número com formato de porcentagem → 'NN.NN%' (o Excel guarda 100,00%
como 1.0 — sem o formato o parser leria 1%); inteiro sem `.0`.

PDF: o texto de cada página (pypdf). O DT em PDF é o mesmo layout impresso,
uma operação por página.
"""
from apps.pages.platform import swap_new_deals as _sw

# A leitura da grade e do PDF mora na horizontal desde 21/09/2026 (o Swap
# Cashflow lê o mesmo Deal Ticket). O Bullet segue decidindo pela EXTENSÃO
# (`read_upload` abaixo), como sempre fez.
_cell_text = _sw.cell_text
sheets_from_xlsx = _sw.sheets_from_xlsx
pages_from_pdf = _sw.pages_from_pdf


def read_upload(filename, data):
    """(kind, itens): ('grid', [(título, grade)]) para planilha, ('text',
    [(título, texto)]) para PDF. Levanta ValueError para o resto."""
    name = str(filename or '').lower()
    if name.endswith(('.xlsx', '.xlsm')):
        return 'grid', sheets_from_xlsx(data)
    if name.endswith('.pdf'):
        pages = pages_from_pdf(data)
        return 'text', [('page %d' % (i + 1), t) for i, t in enumerate(pages)]
    raise ValueError('unsupported file type — drop the Deal Ticket as .xlsx or .pdf')
