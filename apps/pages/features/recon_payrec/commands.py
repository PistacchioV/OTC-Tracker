# -*- coding: utf-8 -*-
"""O Run e a justificativa do Pay/Rec."""
import traceback


def _routes():
    from apps.pages import routes
    return routes


class NdfSourceError(RuntimeError):
    """A liquidação de NDF (API + recompras) não pôde ser lida; a mensagem é o
    motivo, e a tela a mostra sob o código `ndf_source_failed`."""


def run(recon_date, files=None, mode='auto'):
    from apps.pages.recon_payrec import run_payrec
    # Toca o cadastro GDT Codes para o SEED ser materializado em disco, pela
    # mesma razão da Recon FXO: o motor lê o JSON direto (importar `routes`
    # de lá seria circular) e não tem como semear. Sem isto, na instância em
    # que ninguém abriu a tela de /mapping o arquivo não existe, o de-para
    # volta vazio e todo lançamento do extrato volta a ser NDF — sem erro
    # nenhum, e com a recon acusando netting que não existe.
    R = _routes()
    R._mapping_rows('gdt-codes')
    R._mapping_rows('settlement-exception')
    # O lado JPM de NDF é a liquidação do dia como o Cockpit a monta — a API
    # `getTradesBySettle` mais as recompras que ela ainda não traz —, e não mais
    # o `settlement.csv` da pasta. Falha aqui LEVANTA com o motivo: sem o NDF a
    # recon acusaria toda perna de cliente de NDF como pendente.
    ref = R._parse_date_any(recon_date) or R._br_now()
    try:
        ndf_rows = R._ndfc_liquidacao_do_dia(ref)
    except Exception as exc:                                # noqa: BLE001
        raise NdfSourceError(str(exc)) from exc
    # Branch Settlement: as liquidações do dia no Operations B3 e as contas do
    # controle, pelo cadastro `b3-accounts` (LE × tipo) — número de conta não se
    # escreve no código. Falha aqui não derruba a recon inteira: o controle fica
    # sem linha e o log diz por quê.
    try:
        ops_rows = R._opb3_settle_rows(ref) or []
    except Exception:                                       # noqa: BLE001
        R.log.warning('[recon_payrec] Operations B3 ilegível — Branch Settlement sem '
                      'linhas:\n%s', traceback.format_exc())
        ops_rows = []
    return run_payrec(recon_date, files=files, mode=mode, ndf_rows=ndf_rows,
                      ops_rows=ops_rows, branch_accounts=branch_accounts())


# (LE, tipo) no `b3-accounts` → papel da conta na Branch Settlement.
_BRANCH_ACCOUNT_ROLES = {('MGT', 'OWN'): 'mgt_own', ('JPM', 'CLIENT 2'): 'bank_client',
                         ('MGT', 'CLIENT 1'): 'mgt_client'}


def branch_accounts():
    """As contas do controle pelo cadastro `b3-accounts`: MGT própria
    (04880.00-6), a guarda-chuva do Banco para o cliente da MGT (73760.20-5,
    CLIENT 2) e a guarda-chuva da MGT (04880.10-9, CLIENT 1) — a rota antiga,
    só avisada."""
    out = {}
    for row in _routes()._mapping_rows('b3-accounts') or []:
        papel = _BRANCH_ACCOUNT_ROLES.get((str(row.get('LE', '') or '').strip().upper(),
                                           str(row.get('ACCOUNT TYPE', '') or '').strip().upper()))
        if papel and papel not in out:
            out[papel] = str(row.get('ACCOUNT', '') or '').strip()
    return out


def justify(recon_date, table, index, comment, status):
    from apps.pages.recon_payrec import justify_row
    return justify_row(recon_date, table, index, comment, status)


def end_process(recon_date):
    """(saved, emailed). Persiste PRIMEIRO o histórico datado do dia — o registro
    do dia finalizado independe de o SMTP estar de pé — e só então manda o
    e-mail da situação final para o OTC Ops."""
    from apps.pages.recon_payrec import send_payrec_email, finalize_history
    saved = finalize_history(recon_date)
    if not saved:
        return False, False
    return True, bool(send_payrec_email(recon_date))


def save_recipients(d):
    from apps.pages.features.recon_payrec.infra import persistence
    persistence.save_recipients(d)


class BranchDraftError(RuntimeError):
    """Não há o que pedir ao VP; `code` diz por quê (a tela traduz)."""

    def __init__(self, code, text):
        super().__init__(text)
        self.code = code


def branch_draft(recon_date):
    """(filename, bytes do .eml, avisos) do pedido de aprovação da reversão da
    Branch Settlement para o VP.

    Sai do resultado GRAVADO do dia — o e-mail diz o que a tela mostra —, e as
    contas do Counterparty Details são lidas agora (cadastro corrigido vale no
    clique seguinte, sem rodar a recon de novo)."""
    from apps.pages.features.recon_payrec import queries
    from apps.pages.features.recon_payrec.infra import branch_mail
    from apps.pages.recon_payrec import _load_flat, _fmt_date
    R = _routes()
    data = _load_flat(recon_date, strict=True) or {}
    branch = data.get('branch') or {}
    if not branch.get('has_settlement'):
        raise BranchDraftError('branch_none', 'No settlement with the Branch on this date — '
                                              'run the reconciliation first.')
    rec = queries.recipients()
    to_list, cc_list = R._parse_emails(rec['to']), R._parse_emails(rec['cc'])
    if not to_list:
        raise BranchDraftError('branch_no_recipient',
                               'No TO recipient saved in Control Panel › Branch Settlement '
                               'Reverse Approval.')
    if not branch.get('pay_receive'):
        # Sem perna de cliente na 73760.20-5 (ou com ela netando zero) não há
        # reversão para aprovar.
        raise BranchDraftError('branch_no_reversal',
                               'No Branch client settlement (73760.20-5 × 04880.00-6) in '
                               'Operations B3 for this date — there is no reversal to approve.')
    source, dest, avisos = queries.branch_accounts(branch['pay_receive'])
    # A validação extra enquanto a rota antiga existir: ela fica FORA da
    # reversão, e quem aprova tem de saber que há mais liquidação com a MGT.
    if branch.get('legacy'):
        avisos.append({'code': 'branch_legacy_route',
                       'params': {'n': len(branch['legacy']),
                                  'value': '{:,.2f}'.format(branch.get('legacy_net') or 0)},
                       'text': '{} settlement(s) still through the MGT omnibus 04880.10-9 '
                               '(net {:,.2f}) — not in the reversal.'.format(
                                   len(branch['legacy']), branch.get('legacy_net') or 0)})
    ref_fmt = _fmt_date(recon_date)
    raw = branch_mail.build(ref_fmt, branch, source, dest, to_list, cc_list)
    fname = 'Branch_Settlement_Reverse_Approval_{}.eml'.format(ref_fmt.replace('/', ''))
    return fname, raw, avisos
