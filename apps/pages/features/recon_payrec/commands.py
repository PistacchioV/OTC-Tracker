# -*- coding: utf-8 -*-
"""O Run e a justificativa do Pay/Rec."""


def _routes():
    from apps.pages import routes
    return routes


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
    return run_payrec(recon_date, files=files, mode=mode)


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
