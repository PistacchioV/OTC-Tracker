"""Confere o e-mail do Stratos (stratos/src/email_stratos.py): o `smtplib.SMTP`
do app vira o Email block do stratos-blocks.

O `stratosblocks.email.send` é de mentira e GUARDA o que recebe, inclusive o
conteúdo dos arquivos de anexo e de imagem no momento do envio (depois eles são
apagados). A mensagem é montada como os senders do app a montam: `mixed` com
`related` + `alternative` (texto e HTML), o logo por `cid:otc_logo`, um PDF
anexo, Cc no cabeçalho e um Cco só no envelope.

  1. a tradução: assunto com acento, remetente, Para/Cc/Cco, o HTML com o
     `cid:` reescrito para o nome do arquivo da imagem, o anexo com o nome e os
     bytes, os temporários apagados;
  2. só texto: `is_html_message=False`; sem To/Cc no cabeçalho, o envelope é o
     destinatário; `send_message` também passa;
  3. falha do `send` vira `smtplib.SMTPException` (os senders tratam a do SMTP);
  4. `instala`: troca o `smtplib.SMTP`; com `OTC_STRATOS_EMAIL=0` ou sem o
     `stratosblocks.email`, não troca.

    python stratos/tests/check_email_stratos.py
"""
import os
import smtplib
import sys
import types
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'src'))

FALHAS = []
ENVIOS = []
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


def ok(cond, msg):
    print(('ok    ' if cond else 'FAIL  ') + msg)
    if not cond:
        FALHAS.append(msg)


def _send(**kw):
    if kw.get('subject') == 'quebra':
        raise RuntimeError('relay recusou')
    lidos = {}
    for p in list(kw.get('attachments') or []) + list(kw.get('inline_images') or []):
        with open(p, 'rb') as fh:
            lidos[os.path.basename(p)] = fh.read()
    ENVIOS.append(dict(kw, _lidos=lidos))


def _mensagem():
    msg = MIMEMultipart('mixed')
    msg['Subject'] = 'Liquidação de Operação — teste'
    msg['From'] = 'OTC Tracker <otc.tracker@jpmorgan.com>'
    msg['To'] = 'fulana@jpmorgan.com, Beltrano <beltrano@jpmorgan.com>'
    msg['Cc'] = 'ops@jpmorgan.com'
    rel = MIMEMultipart('related')
    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText('Use um cliente HTML.', 'plain'))
    alt.attach(MIMEText('<p>Olá</p><img src="cid:otc_logo" alt="logo">', 'html', 'utf-8'))
    rel.attach(alt)
    logo = MIMEImage(PNG, 'png')
    logo.add_header('Content-ID', '<otc_logo>')
    logo.add_header('Content-Disposition', 'inline', filename='logo.png')
    rel.attach(logo)
    msg.attach(rel)
    pdf = MIMEApplication(b'%PDF-1.4 aviso', 'pdf')
    pdf.add_header('Content-Disposition', 'attachment', filename='Aviso de Liquidação.pdf')
    msg.attach(pdf)
    return msg


def main():
    sys.modules['stratosblocks'] = types.ModuleType('stratosblocks')
    sys.modules['stratosblocks.email'] = types.ModuleType('stratosblocks.email')
    sys.modules['stratosblocks.email'].send = _send
    import email_stratos as E
    original = smtplib.SMTP

    # 1. A tradução
    with E.SmtpStratos('mailhost.jpmchase.net', 25, timeout=20) as server:
        r = server.sendmail('otc.tracker@jpmorgan.com',
                            ['fulana@jpmorgan.com', 'beltrano@jpmorgan.com', 'ops@jpmorgan.com',
                             'oculto@jpmorgan.com'], _mensagem().as_string())
    ok(r == {} and len(ENVIOS) == 1, 'sendmail: um envio pelo Email block')
    e = ENVIOS[-1]
    ok(e['subject'] == 'Liquidação de Operação — teste', 'assunto decodificado (%r)' % e['subject'])
    ok(e['sender'] == 'otc.tracker@jpmorgan.com', 'remetente = o do envelope')
    ok(e['recipient'] == ['fulana@jpmorgan.com', 'beltrano@jpmorgan.com']
       and e.get('cc_receiver') == ['ops@jpmorgan.com']
       and e.get('bcc_receiver') == ['oculto@jpmorgan.com'],
       'Para e Cc do cabecalho, Cco = o que so esta no envelope (%r %r %r)'
       % (e['recipient'], e.get('cc_receiver'), e.get('bcc_receiver')))
    ok(e['is_html_message'] is True and '<p>Olá</p>' in e['body'], 'o corpo e a parte HTML')
    imgs = [os.path.basename(p) for p in e.get('inline_images') or ()]
    ok(imgs == ['otc_logo.png'] and 'cid:otc_logo.png' in e['body']
       and 'cid:otc_logo"' not in e['body'],
       'imagem do corpo: arquivo com o nome do cid e o cid reescrito (%r)' % imgs)
    ok(e['_lidos'].get('otc_logo.png') == PNG, 'imagem com os bytes do logo')
    anexos = [os.path.basename(p) for p in e['attachments']]
    ok(anexos == ['Aviso de Liquidação.pdf'],
       'anexo com o nome que o destinatario ve, acento e espacos inclusos (%r)' % anexos)
    ok(list(e['_lidos'].get(anexos[0], b''))[:4] == list(b'%PDF'), 'anexo com os bytes do PDF')
    ok(not any(os.path.exists(p) for p in list(e['attachments']) + list(e['inline_images'])),
       'os temporarios sao apagados depois do envio')

    # 2. Só texto, envelope sem cabeçalho, send_message
    m = MIMEText('codigo 123456', 'plain', 'utf-8')
    m['Subject'] = 'Codigo'
    m['From'] = 'otc.tracker@jpmorgan.com'
    E.SmtpStratos('h', 25).sendmail('otc.tracker@jpmorgan.com', 'a@jpmorgan.com', m.as_string())
    e = ENVIOS[-1]
    ok(e['is_html_message'] is False and e['body'] == 'codigo 123456'
       and e['recipient'] == ['a@jpmorgan.com'] and 'bcc_receiver' not in e,
       'so texto, sem To: o envelope e o destinatario (%r)' % e['recipient'])
    m['To'] = 'b@jpmorgan.com'
    E.SmtpStratos('h', 25).send_message(m)
    ok(ENVIOS[-1]['recipient'] == ['b@jpmorgan.com'], 'send_message passa pelo mesmo caminho')

    # 3. Falha
    m = MIMEText('x')
    m['Subject'] = 'quebra'
    m['To'] = 'a@jpmorgan.com'
    try:
        E.SmtpStratos('h', 25).sendmail('otc.tracker@jpmorgan.com', ['a@jpmorgan.com'], m.as_string())
        ok(False, 'falha do send levanta')
    except smtplib.SMTPException as ex:
        ok('relay recusou' in str(ex), 'falha do send vira SMTPException com o motivo')

    # 4. instala
    os.environ['OTC_STRATOS_EMAIL'] = '0'
    ok(E.instala() is False and smtplib.SMTP is original, 'OTC_STRATOS_EMAIL=0: fica o SMTP')
    os.environ.pop('OTC_STRATOS_EMAIL')
    ok(E.instala() is True and smtplib.SMTP is E.SmtpStratos, 'instala: smtplib.SMTP vira o Email block')
    smtplib.SMTP = original
    sys.modules['stratosblocks.email'] = None
    ok(E.instala() is False and smtplib.SMTP is original, 'sem stratosblocks.email: fica o SMTP')
    print('\n%d falha(s)' % len(FALHAS))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
