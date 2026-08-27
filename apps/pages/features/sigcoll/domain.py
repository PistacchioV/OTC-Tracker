# -*- coding: utf-8 -*-
"""As regras do e-mail de cobrança — puras (o cadastro chega por parâmetro)."""

FROM = 'is.trade.doc@jpmchase.com'
CC_FIXED = ['brazil.otc.ops@jpmorgan.com', 'is.trade.doc@jpmchase.com']
PENDING = {'pendingdigitalsignature', 'pendingoriginal'}
PORTAL = 'www.jpmorganportaldigital.com'
TO_KEYWORDS = ('confirmation', 'confirmacao', 'confirmação', 'confirm',
               'assinatura', 'signature')


def esc(v):
    return (str(v if v is not None else '')
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def disclaimer(status_norm):
    return ('Pendente de Assinatura Digital' if status_norm == 'pendingdigitalsignature'
            else 'Pendente de Assinatura')


def table_html(rows):
    """Aging | Product Type | Trade Date | Maturity Date | Trade Number — blue header,
    thin-bordered, centred (matches the legacy confirmation e-mail)."""
    head = ''.join(
        '<th style="background:#2E75B6;color:#ffffff;border:1px solid #123c66;'
        'padding:5px 12px;font-weight:bold;text-align:center;white-space:nowrap;">'
        + esc(h) + '</th>'
        for h in ('Aging', 'Product Type', 'Trade Date', 'Maturity Date', 'Trade Number'))
    body = []
    for r in rows:
        cells = [r.get('Aging', ''), r.get('Product Type', ''), r.get('Trade Date', ''),
                 r.get('Maturity Date', ''), r.get('Trade Number', '')]
        body.append('<tr>' + ''.join(
            '<td style="border:1px solid #000000;padding:4px 12px;text-align:center;'
            'white-space:nowrap;">' + esc(c) + '</td>' for c in cells) + '</tr>')
    return ('<table cellspacing="0" cellpadding="0" style="border-collapse:collapse;'
            'font-family:Arial,sans-serif;font-size:12px;color:#000000;">'
            '<thead><tr>' + head + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table>')


def signature_html():
    return (
        '<div style="font-family:Arial,sans-serif;font-size:11px;color:#333333;line-height:1.5;">'
        'Banco J.P. Morgan S.A. | Av. Brigadeiro Faria Lima, 3729 - 15º andar - São Paulo - SP<br>'
        '<a href="mailto:is.trade.doc@jpmchase.com" style="color:#1155cc;">is.trade.doc@jpmchase.com</a>'
        ' | jpmorgan.com | Ouvidoria JPMorgan: Tel.: 0800 – 7700847 / E-mail: '
        '<a href="mailto:ouvidoria.jp.morgan@jpmorgan.com" style="color:#1155cc;">ouvidoria.jp.morgan@jpmorgan.com</a>'
        '</div>')


def email_html(rows):
    P = ('margin:0 0 12px;font-family:Arial,sans-serif;font-size:14px;color:#000000;')
    return (
        '<div style="font-family:Arial,sans-serif;font-size:14px;color:#000000;">'
        '<p style="' + P + '">Prezados,</p>'
        '<p style="' + P + '">Os documentos listados abaixo encontram-se pendentes de '
        'assinatura por V.Sas. junto ao J.P. Morgan</p>'
        + table_html(rows) + '<br>'
        '<p style="' + P + '">Solicitamos que nos auxiliem na solução das pendências listadas '
        'acima e reiteramos a importância desse procedimento para o fiel cumprimento do Contrato. '
        'Sem mais para o momento, agradecemos a atenção e permanecemos à disposição para quaisquer '
        'esclarecimentos que se fizerem necessários.</p>'
        '<p style="' + P + '">Acesse o portal em '
        '<a href="https://' + PORTAL + '" style="color:#1155cc;">' + PORTAL + '</a></p>'
        '<br>' + signature_html() + '</div>')

