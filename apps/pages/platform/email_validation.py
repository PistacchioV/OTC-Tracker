# -*- coding: utf-8 -*-
"""Email Validation — o pedido de conferência que sai do Swap VCP e do NDF
Other Publisher quando a contraparte é INSTITUIÇÃO FINANCEIRA.

Contra cliente (conta guarda-chuva) só o Banco lança e não há o que casar.
Contra IF o lançamento é de DUPLO COMANDO: a B3 só aceita quando o valor das
duas pontas é o mesmo, e por isso outro integrante do time confere o número
antes de ele ir. São dois cenários, e a diferença entre eles é o ANEXO:

    if        a contraparte tem conta PRÓPRIA na B3 (não é guarda-chuva)
              → só o e-mail com a tabela para validação;
    if_fund   uma das pontas é fundo NOSSO (Lawton / Atacama)
              → a tabela MAIS o arquivo da visão do fundo, porque quem valida
                é quem insere essa ponta na B3.

É horizontal (duas verticais usam) e por isso mora na platform: quem decide o
cenário é a CONTA, pelo cadastro `b3-accounts` — nunca o nome da contraparte.
O que é do `routes` é busca atrasada dentro da função.
"""
import logging
import smtplib
import threading
import traceback
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from apps.pages.platform import mail as _mail

log = logging.getLogger('otc_tracker')

SCENARIO_IF = 'if'
SCENARIO_IF_FUND = 'if_fund'
FUND_LES = ('LAWTON', 'ATACAMA')

TEMPLATE = 'pages/email-template-email-validation.html'


def _R():
    from apps.pages import routes
    return routes


def _acct8(account):
    """A conta CETIP nos seus OITO dígitos. O Live Position de NDF entrega a
    do Lawton como `41007` — sem os zeros, ela não casa com o `00041.00-7` do
    cadastro nem com o prefixo `00041`, e a linha do fundo passava por IF
    comum, sem o anexo. É a mesma normalização do `_ndfop_acct8`."""
    d = ''.join(ch for ch in str(account or '') if ch.isdigit())
    return d.zfill(8) if d else ''


def fund_of(account):
    """'LAWTON' / 'ATACAMA' quando a conta é de um dos fundos, senão ''.

    O cadastro `b3-accounts` responde primeiro (é ele que lista as contas das
    nossas entidades); o prefixo do `pu_fator` é o plano B da instância que
    ainda não abriu o /mapping — é a MESMA leitura que decide quem gera a
    segunda visão do arquivo, então cenário e anexo não discordam."""
    # Import ATRASADO: o `pu_fator` lê o `Config` do routes no topo do módulo, e
    # importado antes do routes fecha o ciclo (routes → accrual → pu_fator pela metade).
    from apps.pages.platform import pu_fator as _pf
    account = _acct8(account)
    le = _R()._b3_account_le(account)
    if le in FUND_LES:
        return le
    view = _pf.view_of_account(account)
    return view if view in FUND_LES else ''


def scenario(conta_parte, conta_contraparte):
    """{'scenario': '' | 'if' | 'if_fund', 'funds': [...]} de uma linha.

    Conta da contraparte em branco NÃO é IF: sem a conta não há como dizer, e
    pedir validação de uma linha que pode ser de cliente é ruído — a linha
    fica de fora e a tela diz quantas ficaram."""
    funds = sorted({f for f in (fund_of(conta_parte), fund_of(conta_contraparte)) if f})
    if funds:
        return {'scenario': SCENARIO_IF_FUND, 'funds': funds}
    conta_contraparte = _acct8(conta_contraparte)
    if not conta_contraparte:
        return {'scenario': '', 'funds': []}
    if _R()._b3_is_omnibus(conta_contraparte):
        return {'scenario': '', 'funds': []}
    return {'scenario': SCENARIO_IF, 'funds': []}


def scenario_label(sc):
    """O que a coluna Scenario do e-mail diz: 'IF' ou 'IF + LAWTON'."""
    if sc.get('scenario') == SCENARIO_IF_FUND:
        return 'IF + ' + ' / '.join(sc.get('funds') or [])
    return 'IF' if sc.get('scenario') == SCENARIO_IF else ''


def send_email(subject, html, logo_path, attachments, tag='email-validation'):
    """SMTP do pedido de validação, de `otc.tracker@jpmorgan.com` (a caixa do
    sistema) para `brazil.otc.ops@jpmorgan.com` — e só: sem Cc. Anexos EM
    MEMÓRIA (`[(nome, bytes)]`). HTML e logo já vêm resolvidos de quem chama:
    isto roda numa thread, sem application context. Melhor esforço."""
    R = _R()
    to = R.CETIP_OTC_OPS_EMAIL
    try:
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = _mail.SHARED_MAILBOX
        msg['To'] = to
        related = MIMEMultipart('related')
        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText(subject, 'plain', 'utf-8'))
        alt.attach(MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)
        if logo_path:
            with open(logo_path, 'rb') as f:
                img = MIMEImage(f.read())
            img.add_header('Content-ID', '<otc_logo>')
            img.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(img)
        msg.attach(related)
        for name, data in attachments or []:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(data)
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment', filename=name)
            msg.attach(part)
        with smtplib.SMTP(_mail.SMTP_HOST, _mail.SMTP_PORT, timeout=20) as server:
            server.sendmail(_mail.SHARED_MAILBOX, [to], msg.as_string())
        log.info('[%s] e-mail sent to %s (%d attachment(s))', tag, to, len(attachments or []))
        return True
    except Exception as e:                                  # noqa: BLE001
        log.error('[%s] e-mail FAILED:\n%s', tag, traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)


def dispatch(product, value_name, ref, headers, rows, attachments, requester='', tag=''):
    """Monta o HTML (precisa do application context — é o request) e dispara o
    envio em background: SMTP lento ou fora do ar não segura a resposta.

    `rows` = [{'cells': [...], 'scenario': {...}}] já filtradas (só IF).
    Devolve o assunto."""
    from datetime import datetime
    from flask import render_template
    subject = '{} - {} - Validation'.format(product, ref.strftime('%d/%m/%Y'))
    html = render_template(
        TEMPLATE, product=product, value_name=value_name,
        ref_date_fmt=ref.strftime('%d/%m/%Y'), requester=requester,
        headers=list(headers) + ['Scenario'],
        rows=[list(r['cells']) + [scenario_label(r['scenario'])] for r in rows],
        funds=sorted({f for r in rows for f in (r['scenario'].get('funds') or [])}),
        attachment_names=[n for n, _ in attachments or []],
        current_year=datetime.now().year)
    threading.Thread(target=send_email,
                     args=(subject, html, _mail._get_logo_path(), list(attachments or [])),
                     kwargs={'tag': tag or 'email-validation'}, daemon=True).start()
    return subject
