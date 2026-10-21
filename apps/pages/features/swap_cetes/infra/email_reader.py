# -*- coding: utf-8 -*-
"""O e-mail das Cetes no dropzone → (assunto, linhas do corpo).

Lido pelo CONTEÚDO, nunca pela extensão (o Outlook renomeia anexo): o `.msg`
(CFB), o `.eml` (MIME) ou o corpo solto (HTML colado/salvo, ou texto). O corpo
vira linhas pelo `swap_deal_ticket.html_to_lines` — um parágrafo, ou uma linha
de tabela, por linha —, que é como o bloco `#9 cetip usd irs` e os
`rótulo: valor` dele se leem nas duas formas em que o Outlook os manda."""
import io
import re

from apps.pages.platform import swap_deal_ticket as _dtk
from apps.pages.platform import swap_new_deals as _sw


def _msg(data):
    import extract_msg
    msg = extract_msg.openMsg(io.BytesIO(data))
    corpo = getattr(msg, 'htmlBody', None) or b''
    if isinstance(corpo, bytes):
        corpo = corpo.decode('utf-8', 'replace')
    if not str(corpo).strip():
        corpo = str(getattr(msg, 'body', '') or '')
    return str(getattr(msg, 'subject', '') or ''), corpo


def _eml(data):
    import email
    import email.policy
    msg = email.message_from_bytes(bytes(data), policy=email.policy.default)
    html, texto = '', ''
    for part in msg.walk():
        if part.is_multipart() or part.get_filename():
            continue
        try:
            conteudo = part.get_content()
        except Exception:                                   # noqa: BLE001
            conteudo = (part.get_payload(decode=True) or b'').decode('utf-8', 'replace')
        if part.get_content_type() == 'text/html' and not html:
            html = conteudo
        elif part.get_content_type() == 'text/plain' and not texto:
            texto = conteudo
    return str(msg.get('subject', '') or ''), html or texto


def read(filename, data):
    """→ (assunto, [linhas]). Levanta ValueError para o que não é e-mail nem
    texto (planilha, PDF)."""
    tipo = _sw.kind_of(data)
    if tipo == 'msg':
        assunto, corpo = _msg(data)
    elif tipo == 'eml':
        assunto, corpo = _eml(data)
    elif tipo in ('xlsx', 'pdf'):
        raise ValueError('drop the Cetes e-mail (.msg/.eml) or its body (.htm/.txt) — not a spreadsheet or PDF')
    else:
        corpo = bytes(data).decode('utf-8', 'replace')
        if '�' in corpo:
            corpo = bytes(data).decode('cp1252', 'replace')
        m = re.search(r'<title>(.*?)</title>', corpo, re.I | re.S)
        assunto = m.group(1).strip() if m else str(filename or '')
    return assunto, _dtk.html_to_lines(corpo)
