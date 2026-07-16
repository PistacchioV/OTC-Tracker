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


def _connect_inbox(_w):
    """(outlook MAPI namespace, Inbox folder) for the shared mailbox."""
    outlook = _w.Dispatch('Outlook.Application').GetNamespace('MAPI')
    mailbox = outlook.Folders[_MAILBOX]
    inbox = mailbox.Folders['Inbox']
    return outlook, inbox


def _ensure_archive_folder(inbox):
    """Return Inbox > New deals > B2Bs Automatic, creating each level if absent."""
    folder = inbox
    for name in _ARCHIVE_PATH:
        sub = None
        subs = folder.Folders
        for i in range(1, subs.Count + 1):
            f = subs.Item(i)
            if str(f.Name).strip().lower() == name.lower():
                sub = f
                break
        folder = sub if sub is not None else folder.Folders.Add(name)
    return folder


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
