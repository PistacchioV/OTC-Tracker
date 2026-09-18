"""
Automatic Outlook box scan for the New Deals pages (NDF Comm / Opt Comm).

When the Import button is clicked with an EMPTY dropzone, the client asks the
server to sweep the shared Outlook mailbox for "Brazil Booking Recap" emails and
returns each matching email's HTML body. The client then runs that HTML through
the SAME parse pipeline used for dropzone-dropped files (otc-fileupload.js) — so
this is just a more automatic route to the identical processing.

Mirrors the Outlook COM (win32com/MAPI) approach used by
``recon_comitente.run_auto``:
  - Reads the logged-in Windows Outlook profile (no password).
  - Shared mailbox 'brazil.otc.ops@jpmorgan.com' -> Inbox.

Product routing (by subject):
  - NDF Comm  -> subject must contain 'Swap'
      e.g. "Brazil Booking Recap - MAL_LME Swap ( LibRequestAction.AMEND ) 13Jul2026"
  - Opt Comm  -> subject must contain 'Option'
      e.g. "Brazil Booking Recap - BO_CBOT Option (Put) ( LibRequestAction.AMEND ) 09Jul2026"

Cancel handling:
  - Any matching email whose subject mentions 'Cancel' is DELETED from the box
    (a cancellation carries no data to import).

Archiving:
  - After the client confirms an email's deals were imported it calls
    ``archive_email`` (route /api/new-deals/box-archive), which MOVES that email
    into  Inbox > New deals > B2Bs Automatic  (subfolders created on demand).

Windows-only: degrades with ``EnvironmentError`` when win32com/Outlook is absent
(e.g. the Linux app server), so the client can fall back to the manual dropzone.
"""
import logging
import os

_LOG = logging.getLogger(__name__)

# Shared Outlook mailbox scanned by the New Deals import (same box the Recon de
# Comitentes automatic mode uses). Override with OTC_BOX_MAILBOX if needed.
_MAILBOX = os.getenv('OTC_BOX_MAILBOX', 'brazil.otc.ops@jpmorgan.com')

# Where processed booking-recap emails are archived, as an Inbox subfolder path.
_ARCHIVE_PATH = ('New deals', 'B2Bs Automatic')

# Subject anchor shared by every booking-recap email.
_SUBJECT_ANCHOR = 'Brazil Booking Recap'

# Positive subject keyword that routes an email to each page's product.
_PRODUCT_KEYWORD = {'ndf': 'Swap', 'opt': 'Option'}

# olMail message class (MailItem).
_OL_MAIL = 43

# PidTagNormalizedSubjectW — subject property tag, for the MAPI Restrict filter.
_MAPI_SUBJECT = 'http://schemas.microsoft.com/mapi/proptag/0x0E1D001F'


def _win32():
    """Import win32com/pythoncom or raise EnvironmentError (non-Windows)."""
    try:
        import win32com.client as _w
        import pythoncom
        return _w, pythoncom
    except ImportError:
        raise EnvironmentError(
            'win32com não disponível. A varredura automática do box requer '
            'Windows com Outlook instalado.'
        )


def _connect_mailbox(_w, mailbox=None):
    """(outlook MAPI namespace, mailbox root folder)."""
    outlook = _w.Dispatch('Outlook.Application').GetNamespace('MAPI')
    return outlook, outlook.Folders[mailbox or _MAILBOX]


def _connect_inbox(_w, mailbox=None):
    """(outlook MAPI namespace, Inbox folder) for the shared mailbox."""
    outlook, root = _connect_mailbox(_w, mailbox)
    return outlook, root.Folders['Inbox']


def _child(folder, name):
    """A subpasta com esse nome (sem caixa/acento), ou None. O COM do Outlook
    indexa a partir de 1 e nao tem busca por nome tolerante."""
    subs = folder.Folders
    alvo = str(name).strip().lower()
    for i in range(1, subs.Count + 1):
        f = subs.Item(i)
        if str(f.Name).strip().lower() == alvo:
            return f
    return None


def _walk(folder, path, create=False):
    """Desce `path` (tupla de nomes) a partir de `folder`. Sem `create`,
    devolve None no primeiro nivel ausente em vez de criar."""
    for name in path or ():
        sub = _child(folder, name)
        if sub is None:
            if not create:
                return None
            sub = folder.Folders.Add(name)
        folder = sub
    return folder


def resolve_folder(_w, mailbox, path, create=False):
    """A pasta de `path` na caixa, procurando na RAIZ e, se nao achar, dentro
    do Inbox — e dizendo no log por onde achou.

    As duas buscas existem porque a arvore do Outlook nao diz, para quem olha,
    se uma pasta pende da caixa ou do Inbox: o painel desenha as duas do mesmo
    jeito. Presumir uma das duas e arquivar e-mail numa pasta nova, vazia, com
    o mesmo nome da certa, e ninguem percebe — o e-mail sai da caixa de
    entrada e ninguem procura por ele. Com `create`, a pasta so nasce depois
    de as duas buscas falharem, e o log diz que nasceu."""
    outlook, root = _connect_mailbox(_w, mailbox)
    f = _walk(root, path)
    if f is not None:
        return outlook, f
    inbox = _child(root, 'Inbox')
    if inbox is not None:
        f = _walk(inbox, path)
        if f is not None:
            _LOG.info('[boxscan] pasta %s achada sob o Inbox', '/'.join(path))
            return outlook, f
    if not create:
        return outlook, None
    _LOG.warning('[boxscan] pasta %s nao existia na caixa %s — criada na RAIZ',
                 '/'.join(path), mailbox or _MAILBOX)
    return outlook, _walk(root, path, create=True)


def _ensure_archive_folder(inbox):
    """Return Inbox > New deals > B2Bs Automatic, creating each level if absent."""
    return _walk(inbox, _ARCHIVE_PATH, create=True)


def scan_new_deals_box(product):
    """
    Sweep the shared box's Inbox for "Brazil Booking Recap" emails of one product.

    product: 'ndf' (keep subjects containing 'Swap') or 'opt' ('Option').

    Returns {'ok': True, 'emails': [{'entry_id', 'subject', 'html'}, ...],
             'cancelled': [subject, ...]}.
    'Cancel' emails for this product are deleted from the box and reported in
    'cancelled'. Emails are NOT moved here — the client archives each one only
    after its deals are imported (see archive_email).
    """
    product = (product or '').strip().lower()
    keyword = _PRODUCT_KEYWORD.get(product)
    if not keyword:
        raise ValueError("product deve ser 'ndf' ou 'opt' (recebido: %r)" % product)

    _w, pythoncom = _win32()
    kw_low = keyword.lower()
    anchor_low = _SUBJECT_ANCHOR.lower()

    pythoncom.CoInitialize()
    try:
        _outlook, inbox = _connect_inbox(_w)
        restriction = '@SQL="%s" LIKE \'%%%s%%\'' % (_MAPI_SUBJECT, _SUBJECT_ANCHOR)
        try:
            messages = inbox.Items.Restrict(restriction)
        except Exception:
            # If the MAPI pre-filter is rejected, fall back to a full scan.
            messages = inbox.Items

        emails = []
        cancelled = []
        for msg in list(messages):
            try:
                if getattr(msg, 'Class', None) != _OL_MAIL:
                    continue
                subject = str(msg.Subject or '')
                s_low = subject.lower()
                if anchor_low not in s_low:
                    continue
                # Route by product first — never touch the other page's emails.
                if kw_low not in s_low:
                    continue
                # Cancellation → delete from the box (nothing to import).
                if 'cancel' in s_low:
                    cancelled.append(subject)
                    try:
                        msg.Delete()
                    except Exception as e:
                        _LOG.warning('[boxscan] could not delete cancel email %r: %s',
                                     subject, e)
                    continue
                emails.append({
                    'entry_id': str(getattr(msg, 'EntryID', '') or ''),
                    'subject': subject,
                    'html': str(getattr(msg, 'HTMLBody', '') or ''),
                })
            except Exception as e:
                _LOG.warning('[boxscan] skipped a message: %s', e)
                continue
        return {'ok': True, 'emails': emails, 'cancelled': cancelled}
    finally:
        pythoncom.CoUninitialize()


def archive_email(entry_id):
    """Move the email with this EntryID to Inbox > New deals > B2Bs Automatic."""
    if not entry_id:
        raise ValueError('entry_id vazio')
    _w, pythoncom = _win32()
    pythoncom.CoInitialize()
    try:
        outlook, inbox = _connect_inbox(_w)
        item = outlook.GetItemFromID(entry_id)
        dest = _ensure_archive_folder(inbox)
        item.Move(dest)
        return {'ok': True}
    finally:
        pythoncom.CoUninitialize()


# ==============================================================================
#  UNWIND NOTIFICATIONS  (recompra de NDF de moeda)
# ==============================================================================
# O e-mail e automatico do Athena (`athena_gem_tech@jpmorgan.com`), endereçado a
# 'Brazil Unwind Notifications', e traz DUAS tabelas Atributo|Valor no corpo.
# Quem le o HTML e `features/unwinds/domain.parse_notification` — aqui so se
# varre a caixa e se arquiva.
#
# Caixa e pastas saem de variavel de ambiente com o mesmo desenho do
# `_MAILBOX` acima: a instancia muda sem tocar no codigo. Se um dia a mesa
# precisar editar isso pela tela, vira cadastro do /mapping.
# A caixa e a `brazil.otc.ops`: a `brazil_otc_settlements` esta DENTRO dela
# (confirmado pela mesa em 18/09/2026, pela arvore do Outlook), e nao e uma
# caixa propria. Apontar a caixa para o endereco das liquidacoes resolveria
# para outro lugar — ou para lugar nenhum, calado.
UNWIND_MAILBOX = os.getenv('OTC_UNWIND_MAILBOX', 'brazil.otc.ops@jpmorgan.com')

# De onde varrer, a partir da caixa. Vazio = o Inbox (o padrao); aqui e a
# subpasta das liquidacoes, resolvida pelo `resolve_folder` (raiz, depois
# Inbox) — a arvore do Outlook nao distingue os dois niveis.
UNWIND_SOURCE_PATH = tuple(p for p in os.getenv(
    'OTC_UNWIND_SOURCE_FOLDER', 'brazil_otc_settlements@jpmorgan.com').split('/') if p)

# Para onde o e-mail vai DEPOIS de importado: a pasta `Unwind`, irma da
# origem dentro das liquidacoes.
UNWIND_ARCHIVE_PATH = tuple(p for p in os.getenv(
    'OTC_UNWIND_ARCHIVE_FOLDER',
    'brazil_otc_settlements@jpmorgan.com/Unwind').split('/') if p)

# Ancora de assunto: 'BRL NDF Unwind Notification_<athena id>_<id>'. Deixada
# sem o produto de proposito — o roteamento por produto e a chave abaixo, e e
# assim que a recompra de outro produto entra sem mexer na varredura.
UNWIND_SUBJECT_ANCHOR = 'Unwind Notification'
UNWIND_PRODUCT_KEYWORD = {'ndf': 'NDF'}


def scan_unwind_box(product='ndf'):
    """Varre a caixa das liquidacoes por avisos de recompra de um produto.

    Devolve {'ok': True, 'emails': [{'entry_id','subject','html','received'}]}.
    NAO move nada: o e-mail so e arquivado depois de os dados entrarem, pelo
    `archive_unwind_email` — se a importacao falhar, ele continua na caixa e a
    rodada seguinte o pega de novo. Cancelamento NAO e apagado aqui (ao
    contrario do recap do New Deals): recompra cancelada e informacao, e quem
    decide o que fazer com ela e a mesa.
    """
    keyword = UNWIND_PRODUCT_KEYWORD.get((product or '').strip().lower())
    if not keyword:
        raise ValueError("product sem palavra-chave de assunto: %r" % product)

    _w, pythoncom = _win32()
    anchor_low = UNWIND_SUBJECT_ANCHOR.lower()
    kw_low = keyword.lower()

    pythoncom.CoInitialize()
    try:
        _outlook, origem = resolve_folder(_w, UNWIND_MAILBOX, UNWIND_SOURCE_PATH)
        if origem is None:
            _outlook, raiz = _connect_mailbox(_w, UNWIND_MAILBOX)
            origem = _child(raiz, 'Inbox') or raiz
        restriction = '@SQL="%s" LIKE \'%%%s%%\'' % (_MAPI_SUBJECT, UNWIND_SUBJECT_ANCHOR)
        try:
            messages = origem.Items.Restrict(restriction)
        except Exception:
            messages = origem.Items

        emails = []
        for msg in list(messages):
            try:
                if getattr(msg, 'Class', None) != _OL_MAIL:
                    continue
                subject = str(msg.Subject or '')
                s_low = subject.lower()
                if anchor_low not in s_low or kw_low not in s_low:
                    continue
                emails.append({
                    'entry_id': str(getattr(msg, 'EntryID', '') or ''),
                    'subject': subject,
                    'html': str(getattr(msg, 'HTMLBody', '') or ''),
                    'received': str(getattr(msg, 'ReceivedTime', '') or ''),
                })
            except Exception as e:
                _LOG.warning('[boxscan] unwind: mensagem pulada: %s', e)
                continue
        return {'ok': True, 'emails': emails}
    finally:
        pythoncom.CoUninitialize()


def archive_unwind_email(entry_id):
    """Move o aviso de recompra para a pasta Unwind, DEPOIS de importado."""
    if not entry_id:
        raise ValueError('entry_id vazio')
    _w, pythoncom = _win32()
    pythoncom.CoInitialize()
    try:
        outlook, dest = resolve_folder(_w, UNWIND_MAILBOX, UNWIND_ARCHIVE_PATH, create=True)
        outlook.GetItemFromID(entry_id).Move(dest)
        return {'ok': True}
    finally:
        pythoncom.CoUninitialize()
