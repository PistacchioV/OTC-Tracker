"""E-mail no Stratos: o `smtplib.SMTP` do app vira o Email block do stratos-blocks.

O app manda e-mail em 23 lugares, todos do mesmo jeito: monta uma mensagem
MIME (multipart com o HTML, o logo e o gradiente por `cid:`, os anexos) e faz

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT[, timeout]) as server:
        server.sendmail(remetente, destinatarios, msg.as_string())

O relay do JPM (`mailhost.jpmchase.net:25`) não responde de dentro do
contêiner, e o caminho do Stratos é o `stratosblocks.email.send(subject, body,
sender, recipient, cc_receiver, bcc_receiver, is_html_message, attachments,
inline_images)`. Em vez de mexer nos 23 senders da dev, a ponte troca o
`smtplib.SMTP` por `SmtpStratos` (`instala`): `smtplib` é UM módulo para o app
inteiro (é o mesmo objeto que os testes da dev trocam por `R.smtplib.SMTP`), e
cada sender o lê na hora do envio. A dev nunca importa isto.

O que a tradução faz com a mensagem:
  · assunto e endereços decodificados dos cabeçalhos (`=?utf-8?…?=`);
  · destinatário que está no ENVELOPE do `sendmail` e não no To/Cc é Cco —
    é o que o SMTP faz com ele;
  · o corpo é a parte HTML (`is_html_message=True`), senão a de texto;
  · parte com `Content-ID` é imagem do corpo (`inline_images`); o Email block
    casa o `cid:` pelo NOME do arquivo, então a imagem vai para um arquivo
    temporário com o nome do cid mais a extensão, e o `cid:` do HTML é
    reescrito para esse nome (`cid:otc_logo` → `cid:otc_logo.png`);
  · parte com nome de arquivo é anexo, também por arquivo temporário (a forma
    de caminho é a que a documentação dá sem ambiguidade);
  · os temporários são apagados depois do envio.

O que se perde: cabeçalhos que o `send` não recebe (Reply-To, Importance). Os
avisos de recompra em alta prioridade (`otc_emails`, §569) são rascunho `.eml`
baixado pela tela, não envio, e não passam por aqui.
"""
import logging
import mimetypes
import os
import re
import shutil
import smtplib
import tempfile
from email import message_from_string
from email.header import decode_header, make_header
from email.utils import getaddresses

log = logging.getLogger('otc_tracker')

_CID_LIVRE = re.compile(r'[^A-Za-z0-9._-]+')


def _texto(valor):
    if not valor:
        return ''
    try:
        return str(make_header(decode_header(str(valor))))
    except Exception:                                       # noqa: BLE001
        return str(valor)


def _enderecos(*valores):
    return [a for _n, a in getaddresses([_texto(v) for v in valores if v]) if a]


def _lista(x):
    if not x:
        return []
    if isinstance(x, (str, bytes)):
        x = [x.decode() if isinstance(x, bytes) else x]
    return [a for v in x for a in _enderecos(v)]


def _carga(parte):
    dado = parte.get_payload(decode=True)
    return dado if dado is not None else (parte.get_payload() or '').encode('utf-8')


def _texto_da_parte(parte):
    charset = parte.get_content_charset() or 'utf-8'
    try:
        return _carga(parte).decode(charset, errors='replace')
    except LookupError:
        return _carga(parte).decode('utf-8', errors='replace')


def _nome_do_anexo(nome, padrao):
    """O nome do anexo como veio: é o NOME do arquivo temporário que o
    destinatário vê no anexo (`Termo de Resilição - ACME.pdf`, com o acento e
    os espaços). Sai só o que um nome de arquivo no Linux não aceita."""
    nome = (nome or '').replace('\x00', '').replace('\\', '/').split('/')[-1].strip()
    return nome if nome not in ('', '.', '..') else padrao


def _nome_livre(nome, padrao):
    nome = os.path.basename(_CID_LIVRE.sub('_', nome or '').strip('._'))
    return nome or padrao


def desmonta(from_addr, to_addrs, texto, pasta):
    """-> os argumentos do `stratosblocks.email.send` para a mensagem `texto`.
    Imagens e anexos vão para arquivos em `pasta`."""
    msg = message_from_string(texto)
    para = _enderecos(*msg.get_all('To', []))
    cc = _enderecos(*msg.get_all('Cc', []))
    envelope = _lista(to_addrs)
    vistos = {a.casefold() for a in para + cc}
    cco, ja = [], set()
    for a in envelope:
        k = a.casefold()
        if k not in vistos and k not in ja:
            cco.append(a)
            ja.add(k)
    if not para and not cc:
        para, cco = cco, []
    remetente = (_lista(from_addr) or _enderecos(msg.get('From')) or [''])[0]

    html = texto_puro = None
    anexos, imagens, cids = [], [], {}
    for i, parte in enumerate(msg.walk()):
        if parte.is_multipart():
            continue
        tipo = parte.get_content_type()
        cid = (parte.get('Content-ID') or '').strip().strip('<>')
        nome = _texto(parte.get_filename())
        disposicao = (parte.get('Content-Disposition') or '').split(';')[0].strip().lower()
        if cid:
            ext = os.path.splitext(nome)[1] or mimetypes.guess_extension(tipo) or ''
            base = _nome_livre(cid, 'imagem%d' % i)
            arquivo = base if base.lower().endswith(ext.lower()) else base + ext
            with open(os.path.join(pasta, arquivo), 'wb') as fh:
                fh.write(_carga(parte))
            imagens.append(os.path.join(pasta, arquivo))
            cids[cid] = arquivo
        elif nome or disposicao == 'attachment':
            arquivo = _nome_do_anexo(nome, 'anexo%d' % i)
            sub = os.path.join(pasta, 'anexo%d' % i)    # dois anexos com o mesmo nome
            os.makedirs(sub)
            with open(os.path.join(sub, arquivo), 'wb') as fh:
                fh.write(_carga(parte))
            anexos.append(os.path.join(sub, arquivo))
        elif tipo == 'text/html' and html is None:
            html = _texto_da_parte(parte)
        elif tipo == 'text/plain' and texto_puro is None:
            texto_puro = _texto_da_parte(parte)

    corpo = html if html is not None else (texto_puro or '')
    if html is not None:
        for cid, arquivo in cids.items():
            corpo = re.sub(r'cid:%s(?=["\'\s>)]|$)' % re.escape(cid), 'cid:' + arquivo, corpo)
    args = {'subject': _texto(msg.get('Subject')), 'body': corpo, 'sender': remetente,
            'recipient': para or None, 'is_html_message': html is not None,
            'attachments': anexos}
    if cc:
        args['cc_receiver'] = cc
    if cco:
        args['bcc_receiver'] = cco
    if imagens:
        args['inline_images'] = imagens
    return args


class SmtpStratos(object):
    """O que os senders do app usam do `smtplib.SMTP`: o `with`, o `sendmail`,
    o `send_message` e os no-ops de sessão. Host e porta são ignorados: quem
    entrega é o Email block."""

    def __init__(self, host='', port=0, *args, **kwargs):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self, *a, **k):
        return 250, b'stratos'

    helo = ehlo

    def starttls(self, *a, **k):
        return 220, b'stratos'

    def login(self, *a, **k):
        return 235, b'stratos'

    def noop(self):
        return 250, b'stratos'

    def quit(self):
        return 221, b'stratos'

    close = quit

    def set_debuglevel(self, *a):
        pass

    def sendmail(self, from_addr, to_addrs, msg, *a, **k):
        if isinstance(msg, bytes):
            msg = msg.decode('utf-8', errors='replace')
        from stratosblocks.email import send
        pasta = tempfile.mkdtemp(prefix='otc-mail-')
        try:
            args = desmonta(from_addr, to_addrs, msg, pasta)
            if not args['recipient'] and not args.get('cc_receiver') and \
                    not args.get('bcc_receiver'):
                raise smtplib.SMTPRecipientsRefused({})
            try:
                send(**args)
            except Exception as e:                          # noqa: BLE001
                # Os senders tratam a falha do SMTP; a mensagem diz que foi o Stratos.
                raise smtplib.SMTPException('stratosblocks.email.send: %s: %s'
                                            % (type(e).__name__, e)) from e
            log.warning('[stratos] e-mail enviado pelo Email block: %r para %s',
                        args['subject'], ', '.join((args['recipient'] or [])
                                                    + args.get('cc_receiver', [])))
        finally:
            shutil.rmtree(pasta, ignore_errors=True)
        return {}

    def send_message(self, msg, from_addr=None, to_addrs=None, *a, **k):
        para = to_addrs or [v for h in ('To', 'Cc', 'Bcc') for v in msg.get_all(h, [])]
        return self.sendmail(from_addr or msg.get('From'), para, msg.as_string())


def instala():
    """Troca o `smtplib.SMTP` pelo Email block. `OTC_STRATOS_EMAIL=0` mantém o
    SMTP (para um relay que responda), e sem o `stratosblocks.email` (fora do
    contêiner) nada muda. Devolve se instalou."""
    if os.getenv('OTC_STRATOS_EMAIL', '1').strip() == '0':
        log.warning('[stratos] OTC_STRATOS_EMAIL=0: o e-mail segue pelo SMTP')
        return False
    try:
        import stratosblocks.email  # noqa: F401
    except ImportError:
        log.warning('[stratos] sem o stratosblocks.email: o e-mail segue pelo SMTP')
        return False
    smtplib.SMTP = SmtpStratos
    log.warning('[stratos] e-mail pelo Email block do stratos-blocks')
    return True
