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
import datetime as _dt
import io


def _cell_text(v, number_format=''):
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'TRUE' if v else 'FALSE'
    if isinstance(v, _dt.datetime):
        return v.strftime('%Y-%m-%d')
    if isinstance(v, _dt.date):
        return v.strftime('%Y-%m-%d')
    if isinstance(v, (int, float)):
        f = float(v)
        if f != f:
            return ''
        if '%' in str(number_format or ''):
            return ('%.4f' % (f * 100)).rstrip('0').rstrip('.') + '%'
        if f.is_integer() and abs(f) < 1e15:
            return str(int(f))
        return ('%.10f' % f).rstrip('0').rstrip('.')
    return str(v)


def sheets_from_xlsx(data):
    """[(título, grade)] de todas as abas, células como texto."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        grid = []
        for row in ws.iter_rows():
            grid.append([_cell_text(c.value, getattr(c, 'number_format', '')) for c in row])
        out.append((ws.title, grid))
    wb.close()
    return out


def pages_from_pdf(data):
    """[texto] por página do PDF. Levanta ValueError se o pypdf não estiver
    instalado ou o arquivo não for legível."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:                              # pragma: no cover
        raise ValueError('pypdf is not installed (pip install pypdf)') from exc
    reader = PdfReader(io.BytesIO(data))
    return [(p.extract_text() or '') for p in reader.pages]


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
