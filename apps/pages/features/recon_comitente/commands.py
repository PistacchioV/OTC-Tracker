# -*- coding: utf-8 -*-
"""O Run da reconciliação: bater, gravar e mandar o e-mail do resumo."""


def _routes():
    from apps.pages import routes
    return routes


def run(mode, recon_date, files=None):
    """Roda o batimento (auto ou com os 3 arquivos) e dispara o e-mail do
    resumo quando houve registro. Devolve o `result` do motor, já sem o
    caminho do arquivo (que é detalhe do envio)."""
    R = _routes()
    if mode == 'auto':
        from apps.pages.recon_comitente import run_auto
        result = run_auto(recon_date)
    else:
        from apps.pages.recon_comitente import run_reconciliation
        f_b3_cgd, f_dcad, f_party = files
        result = run_reconciliation(f_b3_cgd, f_dcad, f_party, recon_date)

    # Envia email com sumário + Excel em background (não bloqueia resposta)
    file_path = result.pop('file_path', None)
    filename = result.pop('filename', None)
    counts = result.get('counts', {})
    if counts.get('total', 0) > 0:
        try:
            from apps.pages.recon_comitente import send_recon_comitente_email
            send_recon_comitente_email(recon_date, counts, file_path, filename)
        except Exception as mail_err:                       # noqa: BLE001
            R.log.warning('[reconciliation_comitente_run] email não enviado: %s', mail_err)
    return result
