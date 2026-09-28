# -*- coding: utf-8 -*-
"""De um arquivo de e-mail solto para (html, assunto).

O dropzone da recompra recebe o que a mesa arrasta do Outlook, e isso pode ser
`.msg` (o formato nativo), `.eml` (MIME) ou o corpo salvo como `.htm`. Pedir
que se salve como HTML antes era uma etapa manual que as paginas de New Deals
nao pedem — e que so existia porque o leitor daqui nasceu simples.

**Quem decide o formato e o CONTEUDO, nao a extensao.** O Outlook renomeia
anexo, a mesa salva com o nome do assunto, e um `.msg` chega como `.txt` sem
aviso; pelo conteudo, o arquivo certo e lido de qualquer jeito e o errado
falha dizendo o que era.

O `.msg` e o MESMO caminho do `/api/parse-msg-html` (o `extract_msg`), para
nao existirem duas leituras do mesmo formato nesta casa.
"""
import email
import email.header
import email.policy
import io
import logging
import re

log = logging.getLogger('otc_tracker')

# O parser OLE/CFB nao pode receber um arquivo sem teto (o mesmo limite do
# `/api/parse-msg-html`).
MAX_BYTES = 25 * 1024 * 1024

# Assinatura do Compound File Binary, que e o que um `.msg` e por dentro.
_MAGIC_MSG = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'

# Cabecalho MIME no inicio do arquivo: e o que distingue um `.eml` de um corpo
# HTML salvo. `Content-Type` sozinho nao basta — ele tambem aparece no <meta>
# do HTML do Word.
_MIME_RE = re.compile(
    r'^(?:[A-Za-z-]+:[^\n]*\n(?:[ \t][^\n]*\n)*)*?'
    r'(?:MIME-Version|Content-Transfer-Encoding|X-MS-Has-Attach|Message-ID)\s*:',
    re.IGNORECASE)


def _texto(dados):
    if isinstance(dados, bytes):
        return dados.decode('utf-8', 'replace')
    return str(dados or '')


def _assunto_mime(msg):
    bruto = msg.get('Subject') or ''
    try:
        partes = email.header.decode_header(bruto)
        return ''.join(
            (p.decode(enc or 'utf-8', 'replace') if isinstance(p, bytes) else p)
            for p, enc in partes).strip()
    except Exception:                                       # noqa: BLE001
        return str(bruto).strip()


def _do_msg(dados):
    import extract_msg
    msg = extract_msg.openMsg(io.BytesIO(dados))
    corpo = getattr(msg, 'htmlBody', None)
    if not corpo:
        # Sem corpo HTML o texto vai entre <pre>: o leitor de tabelas nao
        # achara nada e o import falha DIZENDO que nao achou tabela, que e
        # melhor que uma linha montada de um corpo que nao era o esperado.
        corpo = '<pre>' + _texto(getattr(msg, 'body', None) or '') + '</pre>'
    return _texto(corpo), str(getattr(msg, 'subject', '') or '').strip()


def _do_mime(dados):
    msg = email.message_from_bytes(dados, policy=email.policy.default)
    assunto = _assunto_mime(msg)
    html, texto = '', ''
    for parte in (msg.walk() if msg.is_multipart() else [msg]):
        tipo = (parte.get_content_type() or '').lower()
        if tipo not in ('text/html', 'text/plain'):
            continue
        if (parte.get_content_disposition() or '') == 'attachment':
            continue
        try:
            conteudo = parte.get_content()
        except Exception:                                   # noqa: BLE001
            carga = parte.get_payload(decode=True) or b''
            conteudo = carga.decode(parte.get_content_charset() or 'utf-8', 'replace')
        if tipo == 'text/html' and not html:
            html = conteudo
        elif tipo == 'text/plain' and not texto:
            texto = conteudo
    return (html or ('<pre>' + texto + '</pre>')), assunto


def ler(filename, dados):
    """(html, assunto) de um arquivo de e-mail. Levanta ValueError com o
    motivo quando nao da para ler.

    `assunto` volta VAZIO quando o formato nao o carrega (um `.htm` e so o
    corpo): quem chama cai para o nome do arquivo, que e onde o Outlook poe o
    assunto ao salvar."""
    if not isinstance(dados, (bytes, bytearray)):
        dados = _texto(dados).encode('utf-8')
    dados = bytes(dados)
    if not dados:
        raise ValueError('the file is empty')
    if len(dados) > MAX_BYTES:
        raise ValueError('file too large')
    nome = str(filename or '')
    if dados[:8] == _MAGIC_MSG:
        try:
            return _do_msg(dados)
        except Exception as exc:                            # noqa: BLE001
            log.error('[UNWIND NDF FX] .msg ilegivel (%s): %s', nome, exc)
            raise ValueError('could not read the .msg file: %s' % exc)
    cabeca = _texto(dados[:4096])
    if _MIME_RE.search(cabeca):
        try:
            return _do_mime(dados)
        except Exception as exc:                            # noqa: BLE001
            log.error('[UNWIND NDF FX] .eml ilegivel (%s): %s', nome, exc)
            raise ValueError('could not read the e-mail file: %s' % exc)
    return _texto(dados), ''


def tabelas(html):
    """Todas as <table> de um corpo de e-mail, cada uma como [[celula]].

    A mesa cola no e-mail um trecho do Excel, e o Outlook o guarda como uma
    <table> com cada celula dentro de `<p class=MsoNormal><span>` — o texto e o
    que importa, a marcacao nao. Vem TODAS as tabelas, porque o corpo pode ter
    outras antes (assinatura, banner): quem escolhe e quem reconhece as colunas.
    Tabela dentro de tabela sai separada (a de dentro e a que tem os dados).
    `colspan` repete a celula vazia, para as colunas seguintes nao andarem, e o
    `&nbsp;` do Outlook vira espaco (senao `1 234` e numero nenhum).

    Sem <table> (o e-mail em texto puro), o trecho colado do Excel chega
    separado por TAB: cada linha com TAB vira uma linha da tabela."""
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self):
            HTMLParser.__init__(self, convert_charrefs=True)
            self.prontas, self.pilha = [], []     # pilha: [linhas, linha, celula, span]
            self.texto = []

        def handle_starttag(self, tag, attrs):
            if tag == 'table':
                self.pilha.append([[], None, None, 1])
            elif not self.pilha:
                if tag in ('br', 'p', 'div'):
                    self.texto.append('\n')
            elif tag == 'tr':
                self.pilha[-1][1] = []
            elif tag in ('td', 'th') and self.pilha[-1][1] is not None:
                span = dict(attrs).get('colspan') or '1'
                self.pilha[-1][2] = []
                self.pilha[-1][3] = int(span) if str(span).isdigit() else 1
            elif tag in ('br', 'p', 'div') and self.pilha[-1][2] is not None:
                self.pilha[-1][2].append(' ')

        def handle_endtag(self, tag):
            if not self.pilha:
                if tag in ('p', 'div'):
                    self.texto.append('\n')
                return
            t = self.pilha[-1]
            if tag in ('td', 'th') and t[2] is not None:
                cel = re.sub(r'\s+', ' ', ''.join(t[2]).replace('\xa0', ' ')).strip()
                t[1].extend([cel] + [''] * (max(t[3], 1) - 1))
                t[2] = None
            elif tag == 'tr' and t[1] is not None:
                t[0].append(t[1])
                t[1] = None
            elif tag == 'table':
                self.pilha.pop()
                if t[0]:
                    self.prontas.append(t[0])

        def handle_data(self, data):
            if self.pilha and self.pilha[-1][2] is not None:
                self.pilha[-1][2].append(data)
            elif not self.pilha:
                self.texto.append(data)

    p = _P()
    p.feed(_texto(html))
    p.close()
    out = [t for t in p.prontas if t]
    if not out:
        linhas = [ln.replace('\xa0', ' ') for ln in ''.join(p.texto).splitlines()]
        tab = [[c.strip() for c in ln.split('\t')] for ln in linhas if '\t' in ln]
        if tab:
            out.append(tab)
    return out
