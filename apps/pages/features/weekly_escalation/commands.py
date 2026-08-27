# -*- coding: utf-8 -*-
"""As escritas do card e a montagem do rascunho."""
from apps.pages.features.weekly_escalation import queries
from apps.pages.features.weekly_escalation.infra import mail, persistence


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`)."""
    from apps.pages import routes
    return routes


def save_recipients(to, cc):
    persistence.save_recipients(to, cc)


def build_draft(ref, to_list, cc_list):
    """(bytes, None) ou (None, erro): a cobrança da semana como rascunho."""
    R = _routes()
    try:
        rows, source = R._pc_latest_snapshot_rows()
        blocks = queries.blocks(rows)
    except Exception as e:                                  # noqa: BLE001
        import traceback
        R.log.error('[weekly-escalation] draft FAILED:\n%s', traceback.format_exc())
        return None, '{}: {}'.format(type(e).__name__, e)
    raw, err = mail.build(ref.strftime('%d/%m/%Y'), blocks, to_list, cc_list)
    if raw is not None:
        R.log.info('[weekly-escalation] draft built — to=%s cc=%s (%d LOB, source=%s)',
                   to_list, cc_list, len(blocks), source)
    return raw, err
