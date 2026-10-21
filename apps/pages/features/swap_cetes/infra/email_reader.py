# -*- coding: utf-8 -*-
"""O e-mail das Cetes no dropzone → (assunto, linhas do corpo).

Lido pelo CONTEÚDO, nunca pela extensão (o Outlook renomeia anexo): o `.msg`
(CFB), o `.eml` (MIME) ou o corpo solto (HTML colado/salvo, ou texto). O corpo
HTML vira linhas pelo `swap_deal_ticket.html_to_lines` — um parágrafo por
linha, e na tabela do Outlook (um `<p>` dentro de cada `<td>`) uma CÉLULA por
linha; o `domain.blocks` lê as duas formas. O corpo em TEXTO se quebra aqui,
linha a linha: o `html_to_lines` decide que é HTML por qualquer `<`, e o texto
do Outlook traz `<mailto:…>` e `<https://…>` — lido como HTML, o e-mail
inteiro viraria UMA linha."""
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
    html = bool(str(corpo).strip())
    if not html:
        corpo = str(getattr(msg, 'body', '') or '')
    return str(getattr(msg, 'subject', '') or ''), corpo, html


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
    return str(msg.get('subject', '') or ''), html or texto, bool(html)


def read(filename, data):
    """→ (assunto, [linhas]). Levanta ValueError para o que não é e-mail nem
    texto (planilha, PDF)."""
    tipo = _sw.kind_of(data)
    if tipo == 'msg':
        assunto, corpo, html = _msg(data)
    elif tipo == 'eml':
        assunto, corpo, html = _eml(data)
    elif tipo in ('xlsx', 'pdf'):
        raise ValueError('drop the Cetes e-mail (.msg/.eml) or its body (.htm/.txt) — not a spreadsheet or PDF')
    else:
        corpo = bytes(data).decode('utf-8', 'replace')
        if '�' in corpo:
            corpo = bytes(data).decode('cp1252', 'replace')
        html = bool(_HTML.search(corpo))
        m = re.search(r'<title>(.*?)</title>', corpo, re.I | re.S)
        assunto = m.group(1).strip() if m else str(filename or '')
    return assunto, (_dtk.html_to_lines(corpo) if html else _texto(corpo))


_HTML = re.compile(r'<\s*(html|body|table|tr|td|p|div|br|span)\b', re.I)


def _texto(corpo):
    """O corpo em texto puro → as linhas, com tabulação e espaços colapsados
    (a célula da tabela do Outlook chega separada por TAB)."""
    return [re.sub(r'[ \t\u00a0]+', ' ', ln).strip() for ln in str(corpo or '').splitlines() if ln.strip()]
