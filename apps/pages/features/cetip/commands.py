# -*- coding: utf-8 -*-
"""As escritas da rotina — o recorte do BACC (só as contas da casa), a cópia
dos .txt e a distribuição por e-mail das quatro caixas.
"""
import os
import shutil
import tempfile
import traceback

from apps.pages.features.cetip import domain, queries
from apps.pages.features.cetip.infra import mail, mappers


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _cetip_bacc_copy(src_path, cfg, out_dir):
    """Cópia de `src_path` com só as linhas do intragrupo → (path, mantidas, total).

    None quando o par de colunas não resolve: nesse caso o arquivo **não** é
    anexado. Mandar o arquivo inteiro com o nome de um recorte é pior do que não
    mandar — quem recebe não tem como perceber, e o painel diz que foi.

    O arquivo é gravado em `out_dir` (temporário), nunca ao lado do arquivo salvo
    na pasta de liquidação — que é o que o KPI lê.

    O nome do original é MANTIDO e ganha **`.txt` no fim**
    (`73760_260817_DPOSICAO-SWAP.CETIP21.txt`). As extensões da CETIP
    (`.CETIP21`, `.OPC`, `.TER`) não são associadas a programa nenhum: o anexo
    chega sem ícone, não abre com um duplo clique e é o tipo de arquivo que
    filtro de e-mail costuma barrar. O `.txt` vai ACRESCENTADO e não no lugar da
    extensão porque é pelo nome que o outro lado reconhece o arquivo — trocar
    `.OPC` por `.txt` apagaria justamente a parte que diz qual dos quatro é.
    O conteúdo não muda: já era texto (latin-1 + CRLF).
    """
    try:
        with open(src_path, 'r', encoding='latin-1', newline='') as fh:
            linhas = [ln for ln in fh.read().splitlines() if ln.strip()]
    except Exception:
        _R().log.warning('[cetip] BACC: não consegui ler %s:\n%s', src_path, traceback.format_exc())
        return None
    if not linhas:
        return None
    tem_header = bool(cfg.get('has_header'))
    header = [h.strip() for h in linhas[0].split(';')] if tem_header else []
    dados = linhas[1:] if tem_header else linhas
    i_parte = mappers._cetip_bacc_col(header, cfg.get('parte') or {})
    i_cpty = mappers._cetip_bacc_col(header, cfg.get('contraparte') or {})
    if i_parte is None or i_cpty is None:
        _R().log.warning('[cetip] BACC: colunas não resolvidas em %s (parte=%s contraparte=%s) '
                    '— arquivo NÃO anexado', os.path.basename(src_path), i_parte, i_cpty)
        return None

    def _conta(campos, i):
        return domain._cetip_acct_key(campos[i]) if i < len(campos) else ''

    mantidas = [ln for ln in dados
                if _conta(ln.split(';'), i_parte) in domain._CETIP_BACC_ACCOUNTS
                and _conta(ln.split(';'), i_cpty) in domain._CETIP_BACC_ACCOUNTS]
    out_path = os.path.join(out_dir, domain._cetip_txt_name(src_path))
    saida = ([linhas[0]] if tem_header else []) + mantidas
    try:
        # Latin-1 + CRLF: o mesmo formato do `_cetip_save_file`, para o recorte ser
        # byte a byte o arquivo original menos as linhas de fora.
        with open(out_path, 'w', encoding='latin-1', newline='') as fh:
            fh.write('\r\n'.join(saida) + ('\r\n' if saida else ''))
    except Exception:
        _R().log.warning('[cetip] BACC: não consegui gravar o recorte de %s:\n%s',
                    os.path.basename(src_path), traceback.format_exc())
        return None
    _R().log.info('[cetip] BACC: %s → %d de %d linha(s) intragrupo',
             os.path.basename(src_path), len(mantidas), len(dados))
    return out_path, len(mantidas), len(dados)


def _cetip_txt_copy(src_path, out_dir):
    """Cópia de `src_path` em `out_dir` com o mesmo nome + `.txt`, ou None.

    É o anexo do **BACC HUB EQT MO**: arquivo INTEIRO, sem recorte e sem
    releitura — é reconciliação de posição, e um arquivo filtrado bateria contra
    uma posição que não é a que a CETIP publicou. Por isso é `copy2` byte a byte,
    e não um `open`/`write` como no recorte do BACC: sem reencodar, sem tocar em
    fim de linha, sem chance de o latin-1 do arquivo virar outra coisa no caminho.

    O nome sai do `_cetip_txt_name`, o mesmo do recorte do BACC — inclusive a
    guarda do arquivo que JÁ é `.txt`, que é o caso do `SWAP (Strategy)`.

    A cópia vai para um temporário porque o anexo NÃO pode encostar na pasta de
    liquidação — é ela que o KPI lê.
    """
    try:
        out_path = os.path.join(out_dir, domain._cetip_txt_name(src_path))
        shutil.copy2(src_path, out_path)
        return out_path
    except Exception:
        _R().log.warning('[cetip] HUB: não consegui copiar %s:\n%s',
                    os.path.basename(src_path), traceback.format_exc())
        return None


def _cetip_distribute_emails(ref, dest_dir, send_mail, ss_to_list=None, cem_to_list=None,
                             bacc_to_list=None, hub_to_list=None):
    """Stage 2 of Save CETIP Files ("Send to other areas"): e-mail Sales Support
    (SIC + Term/Option/SWAP positions), CEM Latam BA (.OPC) and BACC (DFLUXO +
    the three positions, RECORTADOS para o intragrupo — ver `_cetip_bacc_copy`)
    with the files that stage 1 already saved to dest_dir — no re-save. Attachment
    paths are rebuilt from each rule's deterministic dest name for the reference
    date. TO lists come from the card (persisted); Sales Support e CEM Latam caem
    nos endereços históricos quando a lista está vazia, o BACC **não** — ele não
    tem default, e sem lista o e-mail dele simplesmente não sai. CC stays OTC Ops."""
    ss_to_list  = ss_to_list  or [_R().CETIP_SALES_SUPPORT_EMAIL]
    cem_to_list = cem_to_list or _R().CETIP_CEM_LATAM_EMAILS
    bacc_to_list = bacc_to_list or []
    hub_to_list  = hub_to_list  or []
    if not os.path.isdir(dest_dir):
        return _R().jsonify({'success': False,
                        'error': 'No saved files found for this date. Run "Save CETIP Files" first.'}), 400
    ref_yymmdd = ref.strftime('%y%m%d')
    ref_fmt    = ref.strftime('%d/%m/%Y')
    attach_paths, attach_saved = [], []   # Sales Support (SIC + positions)
    opc_paths,    opc_saved    = [], []   # CEM Latam (.OPC)
    bacc_paths,   bacc_saved   = [], []   # BACC (DFLUXO + 3 posições, recortados)
    bacc_skipped               = []       # recorte que não saiu (coluna não resolvida)
    hub_paths,    hub_saved    = [], []   # BACC HUB EQT MO (4 posições, INTEIRAS, .txt)
    hub_skipped                = []       # arquivo que faltou no dia, ou cópia que falhou
    # As cópias dos dois destinos são temporárias de propósito: elas não podem
    # encostar na pasta de liquidação, que é o que o KPI lê. Criadas sob demanda.
    bacc_tmp = hub_tmp = None
    for rule in queries._cetip_rules():
        quer_hub = bool(rule.get('attach_hub')) and bool(hub_to_list)
        if not (rule.get('attach_sales_support') or rule.get('attach_cem_latam')
                or rule.get('attach_bacc') or quer_hub):
            continue
        try:
            dest_name = rule['dest_name'](ref_yymmdd)
        except Exception:
            continue
        dest_path = os.path.join(dest_dir, dest_name)
        if not os.path.isfile(dest_path):
            # Só o HUB reclama do arquivo que faltou. É reconciliação de POSIÇÃO:
            # um e-mail com três dos quatro arquivos se parece com um e-mail
            # completo, e a posição que falta é a que ninguém vai conferir.
            if quer_hub:
                hub_skipped.append({'dest': dest_name, 'type': rule['label']})
            continue
        entry = {'src': dest_name, 'dest': dest_name, 'type': rule['label']}
        if rule.get('attach_sales_support'):
            attach_paths.append(dest_path); attach_saved.append(entry)
        if rule.get('attach_cem_latam'):
            opc_paths.append(dest_path); opc_saved.append(entry)
        if rule.get('attach_bacc') and bacc_to_list:
            if bacc_tmp is None:
                bacc_tmp = tempfile.mkdtemp(prefix='cetip-bacc-')
            cut = _cetip_bacc_copy(dest_path, rule.get('bacc') or {}, bacc_tmp)
            if cut is None:
                bacc_skipped.append({'dest': dest_name, 'type': rule['label']})
                continue
            cut_path, kept, total = cut
            bacc_paths.append(cut_path)
            # A contagem vai na coluna Type da tabela do e-mail: quem recebe tem de
            # ver que o anexo é um RECORTE, não o arquivo cheio. E o nome da tabela
            # é o do ANEXO (com o `.txt`), não o do arquivo salvo no share: a tabela
            # e a lista de anexos ficam lado a lado no mesmo e-mail, e dois nomes
            # para o mesmo arquivo fariam procurar um anexo que não existe.
            bacc_saved.append({'src': dest_name, 'dest': os.path.basename(cut_path),
                               'type': '{} — {} of {} line(s)'.format(rule['label'], kept, total)})
        if quer_hub:
            if hub_tmp is None:
                hub_tmp = tempfile.mkdtemp(prefix='cetip-hub-')
            hub_path = _cetip_txt_copy(dest_path, hub_tmp)
            if hub_path is None:
                hub_skipped.append({'dest': dest_name, 'type': rule['label']})
            else:
                hub_paths.append(hub_path)
                # Sem contagem de linhas na coluna Type: aqui o arquivo é INTEIRO,
                # e escrever "480 of 480" sugeriria que houve um corte.
                hub_saved.append({'src': dest_name, 'dest': os.path.basename(hub_path),
                                  'type': rule['label']})

    def _limpa_temp():
        for d in (bacc_tmp, hub_tmp):
            if d:
                shutil.rmtree(d, ignore_errors=True)

    if not attach_paths and not opc_paths and not bacc_paths and not hub_paths:
        _limpa_temp()
        return _R().jsonify({'success': False,
                        'error': 'No position files found for {}. Run "Save CETIP Files" first.'
                        .format(ref_fmt)}), 400

    mail_ss = mail_cem = mail_bacc = mail_hub = None
    if send_mail:
        ss_msg = ('Please find attached the position files (Contract/SIC — DPOSCONTRATOSIC, '
                  'Term — DPOSICAO-TER.TER, Option — DPOSICAO.OPC, and SWAP — DPOSICAO-SWAP), '
                  'as requested. The complete list is shown below.' if attach_paths else
                  'The requested position files were not found for the reference date.')
        ss_subject = 'CETIP Consolidated - Corporate - {}'.format(ref_yymmdd)
        mail_ss = mail._send_cetip_email(
            ss_to_list, [_R().CETIP_OTC_OPS_EMAIL], ss_subject,
            'Hello, Sales Support.', ss_msg,
            ref_fmt, attach_saved, attachments=attach_paths)

        cem_msg = ('Please find attached the option position file (DPOSICAO.OPC), '
                   'as requested.' if opc_paths else
                   'The DPOSICAO.OPC file was not found for the reference date.')
        cem_subject = 'CETIP Option Position - CEM Latam - {}'.format(ref_yymmdd)
        mail_cem = mail._send_cetip_email(
            cem_to_list, [_R().CETIP_OTC_OPS_EMAIL], cem_subject,
            'Hello CEM Latam BA,', cem_msg,
            ref_fmt, opc_saved, attachments=opc_paths)

        if bacc_paths:
            bacc_msg = (
                'Please find attached the SWAP flow (DFLUXO) and the Term, Option and '
                'SWAP position files, as requested. <b>These are filtered copies:</b> only '
                'the rows whose <i>party AND counterparty</i> are one of the intragroup '
                'accounts (00041.00-7 Lawton, 73760.00-9 Banco J.P. Morgan, 85398.00-5 '
                'Atacama) were kept — the line count of each file is shown below.')
            if bacc_skipped:
                bacc_msg += (' <b>{}</b> file(s) could not be filtered and were left out; '
                             'OTC Ops was notified.'.format(len(bacc_skipped)))
            mail_bacc = mail._send_cetip_email(
                bacc_to_list, [_R().CETIP_OTC_OPS_EMAIL],
                'CETIP Intragroup Position - BACC - {}'.format(ref_yymmdd),
                'Hello BACC,', bacc_msg,
                ref_fmt, bacc_saved, attachments=bacc_paths, missing=bacc_skipped)

        if hub_paths:
            hub_msg = (
                'Please find attached the Strategy (DPOSICAOESTRATEGIA_MID), NDF/Term '
                '(DPOSICAO-TER), Option (DPOSICAO.OPC), SWAP (DPOSICAO-SWAP) and SWAP '
                'Premium Agenda (DAGENDAPREMIOS) position files for position reconciliation. '
                '<b>These are the complete files</b> — no filter was applied; they are '
                'the same files saved to the settlement folder, renamed with a '
                '<code>.txt</code> extension so they open with a double click.')
            if hub_skipped:
                hub_msg += (' <b>{}</b> file(s) were not available for the reference date '
                            'and are listed below.'.format(len(hub_skipped)))
            mail_hub = mail._send_cetip_email(
                hub_to_list, [_R().CETIP_OTC_OPS_EMAIL],
                'CETIP Position Files - BACC HUB EQT MO - {}'.format(ref_yymmdd),
                'Hello BACC HUB EQT MO,', hub_msg,
                ref_fmt, hub_saved, attachments=hub_paths, missing=hub_skipped)

    # As cópias já foram lidas pelo `sendmail` — as pastas temporárias saem agora.
    _limpa_temp()

    areas = (['Sales Support', 'CEM Latam']
             + (['BACC'] if bacc_paths else [])
             + (['BACC HUB EQT MO'] if hub_paths else []))
    _R()._create_notification(_R().session.get('user_sid', ''), _R().session.get('user_name', ''),
                         'CETIP Files Distributed', 'Control Panel',
                         '{} ({})'.format(' + '.join(areas), ref.strftime('%Y-%m-%d')))

    msg = 'Distribution e-mails sent for <b>{}</b>.'.format(ref_fmt)
    if send_mail:
        probs = [v for v in (mail_ss, mail_cem, mail_bacc, mail_hub)
                 if v is not True and v is not None]
        if not probs:
            msg = '<br>Distribution e-mails sent ({}).'.format(' + '.join(areas))
            # Lista de BACC vazia é desfecho legítimo (ninguém cadastrado), mas o
            # painel tem de dizer — senão "enviado" some com o e-mail que não saiu.
            if not bacc_to_list:
                msg += ('<br><span class="text-muted">BACC: no TO saved — '
                        'e-mail not sent.</span>')
            elif bacc_skipped:
                msg += ('<br><span class="text-warning">BACC: {} file(s) left out '
                        '(column pair not resolved) — see the log.</span>'
                        .format(len(bacc_skipped)))
            if not hub_to_list:
                msg += ('<br><span class="text-muted">BACC HUB EQT MO: no TO saved — '
                        'e-mail not sent.</span>')
            elif hub_skipped:
                msg += ('<br><span class="text-warning">BACC HUB EQT MO: {} file(s) not '
                        'found for this date.</span>'.format(len(hub_skipped)))
        else:
            msg = ('<span class="text-warning">Some distribution e-mails failed: {}</span>'
                   .format(probs[0]))
    return _R().jsonify({'success': True, 'message': msg,
                    'email_sent': {'sales_support': mail_ss, 'cem_latam': mail_cem,
                                   'bacc': mail_bacc, 'hub': mail_hub},
                    'bacc_files': bacc_saved, 'bacc_skipped': bacc_skipped,
                    'hub_files': hub_saved, 'hub_skipped': hub_skipped,
                    'destination': dest_dir})
