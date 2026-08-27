# -*- coding: utf-8 -*-
"""Save CETIP Files — a rotina que filtra, renomeia e distribui os arquivos B3.

Movido VERBATIM do routes.py (nomes internos preservados — o check_cetip_bacc
os troca). As RAÍZES (CETIP_SOURCE_ROOT/DEST_ROOT, os shares planos e as caixas
de e-mail) ficaram no routes: recon_fxo/recon_cgd leem a mesma raiz de destino
e o Settlement Forecast e o MtM usam a caixa do OTC Ops — são plataforma. O
`_CETIP_FILES_SEED` também ficou: é o seed do cadastro `cetip-files` no
`_MAPPING_DEFS`, que é o registro (plataforma) — a regra viva continua sendo o
cadastro, lido aqui por `_R()._mapping_rows`.
"""
import os
import re
import shutil
import tempfile
import traceback
from datetime import datetime

from flask import render_template


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


_CETIP_RECIPIENTS_FILE = os.path.normpath(os.path.join(
    _R().data_dir(), 'control-panel',
    'cetip_distribution_recipients.json'))

_CETIP_RECIPIENT_KEYS = ('ss_to', 'cem_to', 'bacc_to', 'hub_to')

def _load_cetip_recipients():
    try:
        with open(_CETIP_RECIPIENTS_FILE, encoding='utf-8') as fh:
            d = _R().json.load(fh)
        if isinstance(d, dict):
            return {k: d.get(k, '') or '' for k in _CETIP_RECIPIENT_KEYS}
    except Exception:
        pass
    return {k: '' for k in _CETIP_RECIPIENT_KEYS}

def _save_cetip_recipients(rec):
    """Grava as três listas. Recebe o DICIONÁRIO inteiro, não um argumento por
    lista: com três chaves, uma assinatura posicional deixaria uma chamada de dois
    argumentos apagar a terceira em silêncio — que é justamente o que o POST
    fazia quando o payload vinha sem uma delas (ver `_cetip_merge_recipients`)."""
    os.makedirs(os.path.dirname(_CETIP_RECIPIENTS_FILE), exist_ok=True)
    with open(_CETIP_RECIPIENTS_FILE, 'w', encoding='utf-8') as fh:
        _R().json.dump({k: str((rec or {}).get(k, '') or '') for k in _CETIP_RECIPIENT_KEYS},
                  fh, ensure_ascii=False, indent=2)

def _cetip_merge_recipients(payload):
    """As listas salvas com as do payload por cima — só as chaves que VIERAM.

    Sobrescrever as três com o que o payload traz apagaria a lista de quem não
    está no corpo: o botão Run manda o que está na tela, e uma tela antiga (ou um
    POST de fora) não conhece a chave nova. Devolve (rec, mudou)."""
    rec = _load_cetip_recipients()
    mudou = False
    for k in _CETIP_RECIPIENT_KEYS:
        if k in (payload or {}):
            rec[k] = str(payload.get(k) or '').strip()
            mudou = True
    return rec, mudou

def _ensure_cetip_roots():
    """At server start, make sure the CETIP source/destination ROOT folders exist;
    create them if missing. Windows-only (the I:\\ paths are JPM network paths) —
    skipped elsewhere so dev machines don't create junk dirs from backslash paths."""
    if os.name != 'nt':
        return
    for root in (_R().CETIP_SOURCE_ROOT, _R().CETIP_DEST_ROOT):
        try:
            if not os.path.isdir(root):
                os.makedirs(root, exist_ok=True)
                _R().log.info("[cetip] created root folder: %s", root)
        except Exception:
            _R().log.warning("[cetip] could not create root %s:\n%s", root, traceback.format_exc())

_CETIP_BEHAVIOUR = {
    'NDF Position (DPOSICAO C21)': {},
    'SWAP Position (DPOSICAO-SWAP)': {
        'attach_sales_support': True,      # SWAP position also e-mailed to Sales Support
        'attach_hub': True,                # BACC HUB EQT MO — arquivo INTEIRO, só renomeado
        # BACC: Participante (coluna D) × Contraparte (coluna H) — os nomes vêm do
        # `_B3_SWAP_HEADERS['swap_position']`, que é o cabeçalho padrão deste
        # arquivo (ele chega SEM cabeçalho).
        'attach_bacc': True,
        'bacc': {'has_header': False,
                 'parte':       {'column': ['participante'], 'index': 3},
                 'contraparte': {'column': ['contraparte'],  'index': 7}},
        'json': {'category': 'Swap', 'has_header': False, 'header_key': 'swap_position',
                 # de-dup: Conta Parte (coluna D = "Participante")
                 'filter': {'column': ['participante'], 'index': 3,
                            'allowed': ['73760009', '04880006']}}},
    'Option Position (OPC DPOSICAO)': {
        'attach_cem_latam': True,          # this .OPC file is e-mailed to CEM Latam BA
        'attach_sales_support': True,      # .OPC position also e-mailed to Sales Support
        'attach_bacc': True,
        'attach_hub': True,                # BACC HUB EQT MO — arquivo INTEIRO, só renomeado
        # 'parte (conta)' é SUBSTRING de 'contraparte (conta)': o `avoid` é o que
        # impede o lado da parte de casar com a coluna da contraparte quando ela
        # vem antes no cabeçalho — sem ele o filtro compararia a mesma coluna duas
        # vezes e deixaria passar linha de conta externa.
        'bacc': {'has_header': True,
                 'parte':       {'column': ['parte (conta)', 'parte(conta)', 'parte'],
                                 'index': 4, 'avoid': 'contraparte'},
                 'contraparte': {'column': ['contraparte (conta)', 'contraparte(conta)',
                                            'contraparte'], 'index': 7}},
        'json': {'category': 'Option', 'has_header': True,
                 # de-dup: keep only our side (Parte/conta = coluna E)
                 'filter': {'column': ['parte (conta)', 'parte(conta)', 'parte'], 'index': 4,
                            'allowed': ['73760009']}}},
    'Option Movement (OPC DMOVIMENTO)': {},
    'NDF Movement (DMOVIMENTO C21)': {},
    'SWAP Movement (DMOVIMENTO-SWAP)': {},
    'SWAP Flow (DFLUXO_SWAP)': {
        # Este é o único dos quatro do BACC que não vai para mais ninguém: ele não
        # tem `attach_sales_support`, então o BACC é a razão de ele ser anexado.
        'attach_bacc': True,
        'bacc': {'has_header': False,
                 'parte':       {'column': ['código conta cetip parte',
                                            'codigo conta cetip parte',
                                            'conta cetip parte'],
                                 'index': 2, 'avoid': 'contraparte'},
                 'contraparte': {'column': ['código conta cetip contraparte',
                                            'codigo conta cetip contraparte',
                                            'conta cetip contraparte'], 'index': 5}},
        'json': {'category': 'Swap', 'has_header': False, 'header_key': 'swap_fluxo',
                 # de-dup: Conta Parte (coluna C = "Código Conta Cetip Parte")
                 'filter': {'column': ['código conta cetip parte', 'codigo conta cetip parte',
                                       'conta cetip parte'], 'index': 2,
                            'allowed': ['73760009', '04880006']}}},
    'SWAP Premium Agenda (DAGENDAPREMIOS)': {
        'attach_hub': True,                # BACC HUB EQT MO — arquivo INTEIRO, só renomeado
        'json': {'category': 'Swap', 'has_header': False, 'header_key': 'swap_premio',
                 # de-dup: Conta da Parte (coluna D = "Parte")
                 'filter': {'column': ['parte'], 'index': 3,
                            'allowed': ['73760009', '04880006']}}},
    'SWAP Indexers (INDEXADORESSWAP_VCP)': {
        # Not a position file: after saving, its rows refresh the VCP indexer
        # reference JSON (see _cetip_update_vcp_json), used by the Swap
        # Characteristics page. A=Qualification ID, B=Description, C=Additional
        # Description, D=Level 1 Classification, E=Status
        # (Habilitado→Active / Bloqueado→Inactive).
        'vcp_update': True},
    'Operations (DOPERACOES)': {
        # DOPERACOES ships WITH a header row (first line); data from the 2nd line —
        # like the Save-Settlements "operações" file. Keep only our accounts
        # (Conta = col B) and the derivative title types (Tipo Titulo = col J).
        'json': {'category': 'Operations', 'has_header': True,
                 'filters': [
                     {'column': ['conta'], 'index': 1,
                      'allowed': ['73760009', '04880006']},
                     {'column': ['tipo titulo', 'tipo título'], 'index': 9,
                      'allowed': ['TER', 'SWAP', 'OPC'], 'match': 'text'},
                 ]}},
    'COE (DRESUMOEMISSOR-COE)': {},
    'Accelerator Agent (MID DAGENTEACELERADOR)': {},
    # Posição de estratégia (MID). Existe para o BACC HUB EQT MO: ele não vira
    # JSON e não alimenta rotina nenhuma — é salvo na pasta do dia como os outros
    # e anexado inteiro. Sem a linha aqui e no cadastro, a rotina não conheceria o
    # arquivo e o e-mail sairia com três anexos em vez de quatro.
    #
    # O nome do TIPO é o que está no cadastro do time — `SWAP (Strategy)`, e não
    # um nome descritivo inventado aqui: `_cetip_rules` une os dois pela coluna
    # TYPE, e um rótulo que não bate deixa a regra sem cadastro, ou seja, sem
    # efeito nenhum, em silêncio.
    'SWAP (Strategy)': {
        'attach_hub': True},               # BACC HUB EQT MO — arquivo INTEIRO, só renomeado
    'NDF Position (DPOSICAO-TER)': {
        'attach_sales_support': True,      # .TER position also e-mailed to Sales Support
        'attach_bacc': True,
        'attach_hub': True,                # BACC HUB EQT MO — arquivo INTEIRO, só renomeado
        'bacc': {'has_header': True,
                 'parte':       {'column': ['código da parte', 'codigo da parte'],
                                 'index': 1, 'avoid': 'contraparte'},
                 'contraparte': {'column': ['código da contraparte',
                                            'codigo da contraparte'], 'index': 3}},
        'json': {'category': 'NDF', 'has_header': True,
                 # de-dup: keep only our side (Código da Parte = coluna B)
                 'filter': {'column': ['código da parte', 'codigo da parte'], 'index': 1,
                            'allowed': ['73760009', '04880006']}}},
    'SIC Contract Position (DPOSCONTRATOSIC)': {
        'attach_sales_support': True},   # this file is e-mailed to Sales Support
    'Comitente Registry (DCADCOMITENTES)': {},
    # Salvo e mais nada, DE PROPÓSITO — como os outros `{}` daqui. A entrada
    # vazia não é decoração: `_cetip_behaviour_for` avisa em WARNING quando um
    # TYPE do cadastro não casa com nada, justamente para um `attach_*` perdido
    # não passar calado (§269). Sem a linha, o CGD acenderia esse aviso todo dia
    # por estar certo, e um aviso que sempre aparece deixa de ser lido.
    'CGD (NET)': {},
}

_CETIP_DATE_TOKEN = 'YYMMDD'

def _cetip_split_pattern(pattern):
    """`'CETIP21_YYMMDD_DPOSICAO-SWAP'` → `(8, '_dposicao-swap')`.

    Devolve (offset da data, final do nome em minúsculas) ou None se o padrão
    não tiver o `YYMMDD`. A extensão é descartada: o cadastro guarda o nome sem
    `.TXT` (é o formato que o usuário digita) e a comparação é feita contra o
    nome do arquivo sem extensão, o que faz `.TXT` e `.txt` casarem sozinhos.
    """
    s = os.path.splitext(str(pattern or '').strip())[0]
    i = s.upper().find(_CETIP_DATE_TOKEN)
    if i < 0:
        return None
    return i, s[i + len(_CETIP_DATE_TOKEN):].lower()

def _cetip_apply_date(pattern, yymmdd):
    """Troca o `YYMMDD` do padrão pela data (case-insensitive, todas as ocorrências)."""
    return re.sub(_CETIP_DATE_TOKEN, yymmdd, str(pattern or ''), flags=re.I)

def _cetip_make_matcher(pattern, label):
    """Predicado de match do padrão, ou None se o padrão for inválido.

    Casa pelo FINAL do nome (sem extensão) mais 6 dígitos na posição que o
    padrão indica. O prefixo literal ('CETIP21_', 'TER_') NÃO é comparado, só
    o seu tamanho: os nomes de origem nunca foram confirmados com a B3 (era uma
    pendência aberta desde a §27) e exigir o prefixo poderia parar de salvar um
    arquivo que hoje funciona. Quando o prefixo do arquivo não bate com o do
    cadastro fica um aviso no log — dá o diagnóstico sem o risco.
    """
    parts = _cetip_split_pattern(pattern)
    if not parts:
        return None
    idx, tail = parts
    head = os.path.splitext(str(pattern or '').strip())[0][:idx].lower()

    def _match(name_lower):
        stem = os.path.splitext(name_lower)[0]
        if tail and not stem.endswith(tail):
            return False
        date = stem[idx:idx + 6]
        if len(date) != 6 or not date.isdigit():
            return False
        if head and stem[:idx] != head:
            _R().log.warning('[cetip] %s: prefixo do arquivo (%r) difere do cadastro (%r) — '
                        'salvando mesmo assim', label, stem[:idx], head)
        return True

    return _match

def _cetip_paren_key(label):
    """`'NDF Position (DPOSICAO-TER)'` → `'DPOSICAO-TER'`; sem parênteses, o
    rótulo inteiro. É o NOME DO ARQUIVO da CETIP dentro do rótulo — a parte que
    identifica de que arquivo a linha fala, ao contrário do prefixo descritivo,
    que é como o time escolheu chamá-lo."""
    m = re.search(r'\(([^)]*)\)\s*$', str(label or ''))
    return (m.group(1) if m else str(label or '')).strip().upper()

_CETIP_BEHAVIOUR_BY_PAREN = {_cetip_paren_key(k): v for k, v in _CETIP_BEHAVIOUR.items()}

def _cetip_behaviour_for(label):
    """Comportamento da linha do cadastro, pelo TYPE — e, se ele não bater, pelo
    NOME DO ARQUIVO entre parênteses.

    O rótulo é digitado na tela, e o prefixo dele é DESCRIÇÃO. A posição de termo
    já se chamou `Term Position (DPOSICAO-TER)` aqui e `NDF Position
    (DPOSICAO-TER)` no cadastro do time — TER é termo, e a mesa chama termo de
    NDF, então quem renomeou tinha razão. Com a junção só pelo rótulo inteiro,
    essa linha perdia o comportamento por completo: o arquivo continuava sendo
    salvo (SOURCE e DEST vêm do cadastro), mas não virava JSON, não ia para o
    Sales Support e não entrava no recorte do BACC — **sem erro nenhum**, porque
    `dict.get` de uma chave que não existe devolve um dicionário vazio, que é
    exatamente o que uma linha sem comportamento parece. Foi assim que o `.TER`
    sumiu do e-mail do intragrupo.

    Os rótulos daqui já foram alinhados com os da mesa (`Term …` virou `NDF …`
    nos dois arquivos de termo), mas o fallback FICA: ele não existe para aquele
    caso, existe porque uma coluna de texto numa tela convida a ser reescrita, e
    o próximo rename não pode custar outra caçada.

    O que identifica o arquivo é o que está ENTRE PARÊNTESES, e ele é único nas
    17 entradas (`check_cetip_bacc.py` prova). O prefixo pode mudar à vontade.

    Rótulo que não casa por nenhum dos dois é **avisado no log**: a linha existe
    de propósito (há tipos sem comportamento nenhum, que só são salvos), mas um
    `attach_*` que deixa de valer por causa de um parêntese perdido não pode
    passar calado uma segunda vez.
    """
    label = str(label or '').strip()
    if label in _CETIP_BEHAVIOUR:
        return _CETIP_BEHAVIOUR[label]
    achado = _CETIP_BEHAVIOUR_BY_PAREN.get(_cetip_paren_key(label))
    # WARNING, e não INFO: na instância do time o log de módulo só sai a partir de
    # WARNING, e um aviso que ninguém lê é o mesmo que não avisar.
    if achado is not None:
        _R().log.warning('[cetip] %r não é um TYPE conhecido; o comportamento foi resolvido '
                    'pelo nome do arquivo entre parênteses (%r). Renomeie a linha no '
                    '/mapping para o TYPE do código, ou ignore — o efeito é o mesmo.',
                    label, _cetip_paren_key(label))
        return achado
    _R().log.warning('[cetip] %r não tem comportamento registrado: o arquivo é SALVO, mas '
                'não vira JSON nem é anexado a e-mail nenhum. Se ele deveria ir para '
                'alguma área, o TYPE não está batendo com o código.', label)
    return {}

def _cetip_rules():
    """Regras da rotina = cadastro (/mapping) + comportamento (código), unidos
    pela coluna TYPE — ou, quando ela não bate, pelo nome do arquivo entre
    parênteses (ver `_cetip_behaviour_for`). Uma linha com padrão inválido é
    ignorada com aviso no log, para um erro de digitação na tela não derrubar a
    rotina inteira."""
    rules = []
    for row in _R()._mapping_rows('cetip-files'):
        label = str(row.get('TYPE') or '').strip()
        source = str(row.get('SOURCE') or '').strip()
        dest = str(row.get('DEST') or '').strip()
        if not label or not source or not dest:
            continue
        matcher = _cetip_make_matcher(source, label)
        parts = _cetip_split_pattern(source)
        if matcher is None or parts is None:
            _R().log.warning('[cetip] %r ignorado: SOURCE %r não tem %s',
                        label, source, _CETIP_DATE_TOKEN)
            continue
        if _CETIP_DATE_TOKEN not in dest.upper():
            _R().log.warning('[cetip] %r: DEST %r não tem %s — o nome salvo não terá data',
                        label, dest, _CETIP_DATE_TOKEN)
        rule = dict(_cetip_behaviour_for(label))
        rule.update({
            'label': label,
            'match': matcher,
            'date_start': parts[0],
            'dest_name': (lambda d: (lambda r: _cetip_apply_date(d, r)))(dest),
        })
        extra = str(row.get('EXTRA DEST') or '').strip()
        if extra:
            rule['extra_dest'] = extra
        rules.append(rule)
    return rules

def _cetip_save_file(src_path, dest_path):
    """Replicate the Alteryx DynamicInput→DbFileOutput pass: read the raw file as
    Latin-1 (CodePage 28591) and rewrite it with CRLF line endings to the new
    location. Latin-1 is a byte-for-byte mapping, so content is preserved; only
    line endings are normalised to CRLF — matching what the KPI process expects."""
    with open(src_path, 'r', encoding='latin-1', newline='') as f:
        lines = f.read().splitlines()
    out = '\r\n'.join(lines)
    if lines:
        out += '\r\n'
    with open(dest_path, 'w', encoding='latin-1', newline='') as f:
        f.write(out)

def _cetip_update_vcp_json(src_path):
    """Refresh the existing VCP.json IN PLACE from the saved INDEXADORESSWAP_VCP
    file (';'-delimited, Latin-1). File columns: A=Qualification ID, B=Description,
    C=Additional Description, D=Level 1 Classification, E=Status (Habilitado →
    ACTIVE / Bloqueado → INACTIVE).

    Upsert by "ID da Qualificação": existing rows have their STATUS/descriptions/
    classification updated (MAKER/CHECKER preserved); new IDs are appended with
    Produto=SWAP. Rows not present in the file (e.g. the OPC entries) are left
    untouched. Best-effort — returns the path or None."""
    try:
        with open(src_path, 'r', encoding='latin-1', newline='') as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        if not lines:
            return None
        # Skip a header row if the file ships with one.
        first = [c.strip().lower() for c in lines[0].split(';')]
        if any('qualif' in c or c == 'status' or 'classif' in c or 'descri' in c for c in first):
            lines = lines[1:]

        # Load the existing table + index by Qualification ID (as string).
        current = []
        if os.path.isfile(_R().VCP_JSON):
            try:
                with open(_R().VCP_JSON, encoding='utf-8') as fh:
                    current = _R().json.load(fh) or []
            except Exception:
                current = []
        by_id = {str(r.get('ID da Qualificação')): r for r in current}

        added = updated = 0
        for ln in lines:
            f = ln.split(';')
            def g(i):
                return f[i].strip() if i < len(f) else ''
            qid_raw = g(0)
            if not qid_raw:
                continue
            try:
                qid = int(''.join(ch for ch in qid_raw if ch.isdigit() or ch == '-'))
            except ValueError:
                qid = qid_raw
            st = _R()._fcst_norm(g(4))
            status = 'ACTIVE' if 'habilitad' in st else ('INACTIVE' if 'bloquead' in st else g(4))
            row = by_id.get(str(qid))
            if row is None:
                current.append({
                    'STATUS':                              status,
                    'ID da Qualificação':                  qid,
                    'Descrição da Qualificação':           g(1),
                    'Descrição Adicional da Qualificação': g(2),
                    'Classificação Nível 1':               g(3),
                    'Produto':                             'SWAP',
                    'MAKER':                               None,
                    'CHECKER':                             None,
                })
                by_id[str(qid)] = current[-1]
                added += 1
            else:
                row['STATUS'] = status
                row['Descrição da Qualificação'] = g(1)
                row['Descrição Adicional da Qualificação'] = g(2)
                row['Classificação Nível 1'] = g(3)
                updated += 1

        with open(_R().VCP_JSON, 'w', encoding='utf-8') as fh:
            _R().json.dump(current, fh, ensure_ascii=False, indent=2)
        _R().log.info("[cetip] VCP.json refreshed: %d updated, %d added (%d total)",
                 updated, added, len(current))
        return _R().VCP_JSON
    except Exception:
        _R().log.warning("[cetip] VCP.json update failed:\n%s", traceback.format_exc())
        return None

def _send_cetip_email(to_list, cc_list, subject, greeting, message_html,
                      ref_date_fmt, saved, dest_folder='', attachments=None, missing=None):
    """Render the CETIP HTML template and send it FROM the OTC Tracker mailbox
    (SHARED_MAILBOX) with the embedded logo (cid:otc_logo) and optional file
    attachments. Best-effort — returns True on success or an error string."""
    from email.mime.image import MIMEImage
    from email.mime.base import MIMEBase
    from email import encoders
    attachments = attachments or []
    missing = missing or []
    try:
        attach_names = [os.path.basename(p) for p in attachments]
        html = render_template(
            'pages/email-template-cetip-saved.html',
            subject=subject, greeting=greeting, message_html=message_html,
            ref_date_fmt=ref_date_fmt, file_count=len(saved), saved_files=saved,
            missing_files=missing, missing_count=len(missing),
            attachment_names=attach_names, dest_folder=dest_folder,
            current_year=datetime.now().year)

        # mixed > [ related > [ alternative > [plain, html], logo ], attachment... ]
        msg = _R().MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = _R().SHARED_MAILBOX
        msg['To'] = ', '.join(to_list)
        if cc_list:
            msg['Cc'] = ', '.join(cc_list)

        related = _R().MIMEMultipart('related')
        alt = _R().MIMEMultipart('alternative')
        alt.attach(_R().MIMEText('CETIP files saved.', 'plain', 'utf-8'))
        alt.attach(_R().MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)

        logo_path = _R()._get_logo_path()
        if logo_path:
            with open(logo_path, 'rb') as f:
                img = MIMEImage(f.read())
            img.add_header('Content-ID', '<otc_logo>')
            img.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(img)
        _R()._attach_email_gradient(related)
        msg.attach(related)

        for path in attachments:
            try:
                with open(path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment',
                                filename=os.path.basename(path))
                msg.attach(part)
            except Exception:
                _R().log.warning("[cetip] could not attach %s:\n%s", path, traceback.format_exc())

        recipients = list(to_list) + list(cc_list or [])
        with _R().smtplib.SMTP(_R().SMTP_HOST, _R().SMTP_PORT, timeout=20) as server:
            server.sendmail(_R().SHARED_MAILBOX, recipients, msg.as_string())
        _R().log.info("[cetip] e-mail '%s' sent to %s", subject, recipients)
        return True
    except Exception as e:
        _R().log.error("[cetip] e-mail '%s' FAILED:\n%s", subject, traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)   # error string surfaced to the UI

_CETIP_BACC_ACCOUNTS = frozenset(('00041007',      # Lawton   00041.00-7
                                  '73760009',      # Banco    73760.00-9
                                  '85398005'))     # Atacama  85398.00-5

def _cetip_acct_key(v):
    """Conta comparável: só dígitos, completada com zeros à esquerda até 8.

    O Lawton é `00041.00-7`; um exportador que trate a conta como NÚMERO devolve
    `41007`, que sem o zfill não casaria com nada — e o recorte sairia vazio sem
    erro nenhum."""
    d = re.sub(r'\D', '', str(v or ''))
    return d.zfill(8) if 0 < len(d) <= 8 else d

def _cetip_bacc_col(header, spec):
    """Índice da coluna da parte (ou da contraparte) no arquivo salvo.

    Pelo NOME quando o arquivo traz cabeçalho; pelo índice quando não traz (aí o
    cabeçalho é o padrão do código — `_B3_SWAP_HEADERS` —, e resolver por nome não
    acrescentaria nada). O índice também é o último recurso quando o nome não casa,
    que é o mesmo desenho do `_b3_filter_rows`.

    `avoid` descarta a coluna cujo nome contenha aquele texto, e não é zelo: em
    `'contraparte (conta)'` cabe `'parte (conta)'` inteiro, então sem ele o lado da
    parte casaria com a coluna da contraparte quando ela vem antes no cabeçalho — o
    filtro compararia a MESMA coluna duas vezes e deixaria passar linha de cliente.
    """
    if header:
        alvo = [_R()._fcst_norm(t) for t in (spec.get('column') or [])]
        evitar = _R()._fcst_norm(spec.get('avoid', ''))
        nomes = [(i, _R()._fcst_norm(h)) for i, h in enumerate(header)]
        ok = lambda n: not (evitar and evitar in n)
        for t in alvo:
            for i, n in nomes:                       # nome exato primeiro
                if n == t and ok(n):
                    return i
        for t in alvo:
            for i, n in nomes:                       # depois por conteúdo
                if t and t in n and ok(n):
                    return i
    idx = spec.get('index')
    return idx if isinstance(idx, int) and idx >= 0 else None

def _cetip_txt_name(src_path):
    """Nome do anexo: o do arquivo salvo, com `.txt` no fim — e um só.

    O `.txt` é ACRESCENTADO, não substituído: as extensões da CETIP (`.CETIP21`,
    `.OPC`, `.TER`) não são associadas a programa nenhum e o anexo não abre com um
    duplo clique, mas é pelo nome inteiro que o outro lado reconhece QUAL arquivo
    é aquele — trocar `.OPC` por `.txt` apagaria justamente essa parte.

    Quando o DEST cadastrado já termina em `.txt` (o `SWAP (Strategy)` é assim),
    não ganha um segundo: `…_MID.txt.txt` é um nome que ninguém escreveu de
    propósito, e o casamento do outro lado é pelo nome."""
    nome = os.path.basename(src_path)
    return nome if nome.lower().endswith('.txt') else nome + '.txt'

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
    i_parte = _cetip_bacc_col(header, cfg.get('parte') or {})
    i_cpty = _cetip_bacc_col(header, cfg.get('contraparte') or {})
    if i_parte is None or i_cpty is None:
        _R().log.warning('[cetip] BACC: colunas não resolvidas em %s (parte=%s contraparte=%s) '
                    '— arquivo NÃO anexado', os.path.basename(src_path), i_parte, i_cpty)
        return None

    def _conta(campos, i):
        return _cetip_acct_key(campos[i]) if i < len(campos) else ''

    mantidas = [ln for ln in dados
                if _conta(ln.split(';'), i_parte) in _CETIP_BACC_ACCOUNTS
                and _conta(ln.split(';'), i_cpty) in _CETIP_BACC_ACCOUNTS]
    out_path = os.path.join(out_dir, _cetip_txt_name(src_path))
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
        out_path = os.path.join(out_dir, _cetip_txt_name(src_path))
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
    for rule in _cetip_rules():
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
        mail_ss = _send_cetip_email(
            ss_to_list, [_R().CETIP_OTC_OPS_EMAIL], ss_subject,
            'Hello, Sales Support.', ss_msg,
            ref_fmt, attach_saved, attachments=attach_paths)

        cem_msg = ('Please find attached the option position file (DPOSICAO.OPC), '
                   'as requested.' if opc_paths else
                   'The DPOSICAO.OPC file was not found for the reference date.')
        cem_subject = 'CETIP Option Position - CEM Latam - {}'.format(ref_yymmdd)
        mail_cem = _send_cetip_email(
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
            mail_bacc = _send_cetip_email(
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
            mail_hub = _send_cetip_email(
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


_ensure_cetip_roots()
