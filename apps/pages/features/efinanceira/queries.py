# -*- coding: utf-8 -*-
"""Leitura da E-Financeira: os eventos do mês (o que as telas de liquidação
montam, dia a dia) e a página de um sistema de origem.

As FONTES são as mesmas linhas das telas de liquidação, nunca uma segunda
leitura dos arquivos — o desenho do WHT (§692):

  · `ndf` — o NDF Summary (`_ndfsum_collect(...)['email_trades']`: o termo de
    moeda do Cockpit e as recompras do dia), com o vencimento e o valor do lado
    B3 de cada operação;
  · `ops` — o Trade Level do Other Products (`_ops_trade_rows`: swap, termo de
    mercadoria e opção), com o vencimento, o prêmio e quem o paga, da posição;
  · `exp` — as opções que VENCEM no dia na posição (`_lpopt_collect`): a que
    vence sem caixa não aparece em tela de liquidação nenhuma, e é ela que
    leva o Saldo (o prêmio recebido) e a data de encerramento ao arquivo.

A recompra encerra o contrato? Quem diz é a vertical de Unwinds
(`_unwind_engine().encerramentos`), pela mesma regra do Termo de Resilição.
"""
import traceback
from datetime import date, datetime, timedelta

from apps.pages.features.efinanceira import domain
from apps.pages.features.efinanceira.infra import store


def _R():
    from apps.pages import routes
    return routes


# ── Cadastros ───────────────────────────────────────────────────────────────
def declarants():
    """{LE: {'ente', 'cnpj', 'name'}} do cadastro `efin-declarant`."""
    out = {}
    for r in _R()._mapping_rows('efin-declarant'):
        le = domain.norm(r.get('LE'))
        if le and le not in out:
            out[le] = {'ente': str(r.get('ENTE') or '').strip(), 'cnpj': domain.digits(r.get('CNPJ')),
                       'name': str(r.get('NAME') or '').strip()}
    return out


def le_token(legal):
    """A entidade (`JPM`, `MGT`…) a partir do NOME da entidade da linha. Ignora
    pontuação e espaço ("J.P." ≡ "JP"); o nome do `le-spn` também vale (o
    prefixo só com 6+ caracteres: "BANCO" sozinho não é o Banco J.P. Morgan)."""
    s = domain.alnum(legal)
    if not s:
        return ''
    if s in ('JPM', 'MGT', 'LAWTON', 'ATACAMA'):
        return s
    if s.startswith('BANCOJP'):
        return 'JPM'
    if s.startswith('JPMORGANCHASE'):
        return 'MGT'
    for r in _R()._mapping_rows('le-spn'):
        nome = domain.alnum(r.get('NAME'))
        if nome and (s == nome or (len(s) >= 6 and (s.startswith(nome) or nome.startswith(s)))):
            return domain.norm(r.get('LE'))
    return domain.norm(legal)


def _conta_le(account):
    """A entidade nossa dona da conta (`b3-accounts`), ou ''. A guarda-chuva
    (CLIENT 1/2) é do Banco mas a conta é do CLIENTE: não responde."""
    R = _R()
    if not domain.digits(account):
        return ''
    try:
        if R._b3_is_omnibus(account):
            return ''
        return domain.norm(R._b3_account_le(account))
    except Exception:                                       # noqa: BLE001
        return ''


def le_of(account, legal):
    """A entidade da linha: pela CONTA da parte quando a linha a traz (o nome da
    parte na posição de opção é apelido de conta, `JPMORGANBM`), senão pelo nome."""
    return _conta_le(account) or le_token(legal)


def _refdata_index():
    """{nome/acrônimo sem pontuação: CNPJ} do Reference Data. O Trade Level de
    mercadoria fala pelo ACRÔNIMO, o resto pelo nome."""
    try:
        from apps.pages import duck_read
        data = duck_read.refdata_rows() or []
    except Exception:                                       # noqa: BLE001
        data = []
    out = {}
    for rec in data if isinstance(data, list) else []:
        tax = str(rec.get('TAX ID', '') or '').strip()
        if not domain.cnpj_key(tax):
            continue
        for k in ('COUNTERPARTY', 'COMMODITIES ACCRONYM', 'FX CASH ACCRONYM'):
            a = domain.alnum(rec.get(k))
            if a and a not in out:
                out[a] = tax
    return out


# A data do CGD (`conta_dtabertu`, "data do CGD da contraparte"): a do
# REFERENCE DATA primeiro — o CGD Active da contraparte no Counterparty Details,
# o mesmo que as confirmações imprimem (`_conf_cgd_lookup`) —, e só sem ele a
# do Tracking Docs (equipe, 30/10/2026: linhas sem data com a data no Reference
# Data). No Tracking Docs, a da ASSINATURA e, sem ela, a da emissão.
CGD_DATE_COLUMNS = ('Signature Date', 'Emissão')


def _refdata_spns():
    """({CNPJ: [SPN…]}, {nome/acrônimo sem pontuação: [SPN…]}) do Reference
    Data: a ponte da linha (que traz CNPJ e nome, não o SPN) até o Counterparty
    Details, que é por SPN. O mesmo CNPJ pode ter mais de um registro."""
    R = _R()
    try:
        from apps.pages import duck_read
        data = duck_read.refdata_rows() or []
    except Exception:                                       # noqa: BLE001
        data = []
    por_cnpj, por_nome = {}, {}
    for rec in data if isinstance(data, list) else []:
        spn = R._norm_spn(rec.get('SPN'))
        if not spn:
            continue
        chaves = [(por_cnpj, domain.cnpj_key(rec.get('TAX ID')))] + [
            (por_nome, domain.alnum(rec.get(c))) for c in ('COUNTERPARTY', 'COMMODITIES ACCRONYM', 'FX CASH ACCRONYM')]
        for alvo, k in chaves:
            if k and spn not in alvo.setdefault(k, []):
                alvo[k].append(spn)
    return por_cnpj, por_nome


def refdata_cgd_index():
    """({CNPJ: data ISO}, {nome: data ISO}) — a data do CGD no Reference Data:
    por SPN, o PRIMEIRO item Active do CGD da contraparte no Counterparty
    Details cujo valor é uma data (a regra do `_conf_cgd_lookup`; o Pending do
    maker/checker não vale). Banco ocupado SOBE (503), nunca vira "sem data"."""
    R = _R()
    por_spn = {}
    for rec in R._cpd_load() or []:
        spn = R._norm_spn(rec.get('SPN'))
        if not spn or spn in por_spn:
            continue
        for item in R._cgd_norm(rec.get('CGD')):
            d = domain.parse_date(item.get('value')) if (item.get('status') or 'Active') == 'Active' else None
            if d:
                por_spn[spn] = d.isoformat()
                break
    por_cnpj, por_nome = _refdata_spns()

    def data_de(spns):
        return next((por_spn[x] for x in spns if x in por_spn), '')
    return ({k: v for k, v in ((k, data_de(x)) for k, x in por_cnpj.items()) if v},
            {k: v for k, v in ((k, data_de(x)) for k, x in por_nome.items()) if v})


def cgd_index():
    """{(LE, CNPJ): data ISO} e {('', CNPJ): data} dos CGDs do Tracking Docs
    (Onboarding): só o Doc Type CGD e não cancelado; com mais de um, o MAIS
    ANTIGO (é a abertura do relacionamento). CNPJ de cada entidade do grupo."""
    from apps.pages import cgd_docs
    out = {}
    for r in cgd_docs.load_all() or []:
        if domain.norm(r.get('Doc Type')) != 'CGD':
            continue
        if cgd_docs.outcome(r) == 'cancelled':
            continue
        d = next((domain.parse_date(r.get(c)) for c in CGD_DATE_COLUMNS if domain.parse_date(r.get(c))), None)
        if not d:
            continue
        le = domain.norm(r.get('Legal Entity'))
        for parte in str(r.get('CNPJ') or '').split(';'):
            k = domain.cnpj_key(parte)
            if not k:
                continue
            for chave in ((le, k), ('', k)):
                if chave not in out or d.isoformat() < out[chave]:
                    out[chave] = d.isoformat()
    return out


def cgd_of(idx, le, taxid):
    k = domain.cnpj_key(taxid)
    if not k:
        return ''
    return idx.get((domain.norm(le), k)) or idx.get(('', k)) or ''


# ── As fontes → os eventos do dia ───────────────────────────────────────────
def _ev(day, source, seq, *, legal='', account='', internal_id='', b3_id='', product='', lob='',
        kinds=(), value=None, b3_value=None, counterparty='', taxid='', cpty_account='',
        trade_date='', maturity='', premium=None, premium_date='', holder=None, closes=None):
    return {'day': day.isoformat(), 'source': source, 'seq': seq,
            'legal': str(legal or '').strip(), 'account': str(account or '').strip(),
            'internal_id': str(internal_id or '').strip(), 'b3_id': str(b3_id or '').strip().upper(),
            'product': product, 'lob': lob, 'kinds': list(kinds),
            'value': None if value is None else domain.r2(value),
            'b3_value': None if b3_value is None else domain.r2(b3_value),
            'counterparty': str(counterparty or '').strip(), 'taxid': str(taxid or '').strip(),
            'cpty_account': str(cpty_account or '').strip(),
            'trade_date': domain.iso(trade_date), 'maturity': domain.iso(maturity),
            'premium': premium, 'premium_date': domain.iso(premium_date),
            'holder': holder, 'closes': closes}


def _fecha(closings, kinds, b3_id):
    """A recompra encerra? Só se pergunta à vertical na recompra; sem resposta
    (a vertical não leu) é None — e a data de encerramento fica em branco."""
    if domain.UNWIND not in kinds or closings is None:
        return None
    return closings.get(str(b3_id or '').strip().upper())


def ndf_events(day, trades, closings, refdata=None):
    """As operações do NDF Summary (`email_trades`): o valor do Cockpit (a ótica
    do banco: negativo é o banco pagando), o do lado B3 e o vencimento."""
    out = []
    for r in trades or ():
        s = r.get('settlement')
        if s is None:
            continue
        unwind = bool(r.get('unwind'))
        kinds = domain.kinds_of(r.get('settle_type') or 'MATURITY', unwind)
        b3 = str(r.get('b3') or '').strip()
        cpty = str(r.get('counterparty') or '').strip()
        taxid = r.get('taxid') or ''
        if not taxid:
            refdata = _refdata_index() if refdata is None else refdata
            taxid = refdata.get(domain.alnum(cpty), '')
        out.append(_ev(day, 'ndf', len(out), legal=r.get('legal'), internal_id=r.get('athena'),
                       b3_id=b3, product='NDF', lob='', kinds=kinds, value=float(s),
                       b3_value=r.get('b3_value'), counterparty=cpty, taxid=taxid,
                       trade_date=r.get('trade_date'),
                       # na recompra a `settle_date` é a da recompra, não o vencimento
                       maturity='' if unwind else r.get('maturity'),
                       closes=_fecha(closings, kinds, b3)))
    return out


def ops_events(day, trades, closings, refdata=None):
    """As linhas do Trade Level do Other Products — swap, termo de mercadoria e
    opção — com o que a posição sabe do prêmio (o da opção e o do termo)."""
    out = []
    for r in trades or ():
        product, lob = domain.produto_lob(r.get('product'), r.get('lob'), 'ops')
        kinds = domain.kinds_of(r.get('settle_type'))
        b3 = str(r.get('id_b3') or '').strip()
        cpty = str(r.get('counterparty') or '').strip()
        taxid = r.get('_taxid') or ''
        if not taxid:
            refdata = _refdata_index() if refdata is None else refdata
            taxid = refdata.get(domain.alnum(cpty), '')
        out.append(_ev(day, 'ops', len(out), legal=r.get('_legal'), account=r.get('_party_account'),
                       internal_id=r.get('internal_id'), b3_id=b3, product=product, lob=lob,
                       kinds=kinds, value=r.get('_settle_n'), b3_value=r.get('_b3_n'),
                       counterparty=cpty, taxid=taxid, trade_date=r.get('_trade_date'),
                       maturity=r.get('_maturity'), premium=domain.num(r.get('_premium')),
                       premium_date=r.get('_premium_date'),
                       holder=domain.holder_of(r.get('_premium_side')),
                       closes=_fecha(closings, kinds, b3)))
    return out


def expiry_events(day, lp, refdata=None):
    """As opções da posição (`_lpopt_collect`) que VENCEM em `day`: sem valor
    (o caixa, quando há, vem do Trade Level), com o prêmio e quem o pagou. A
    contraparte pela regra do Live Position: a coluna do CPF/CNPJ (que já é o
    NOME quando há cadastro), senão a conta CETIP, senão o apelido da B3."""
    R = _R()
    cols = lp.get('columns') or []
    ci = {c: i for i, c in enumerate(cols)}

    def cel(row, nome):
        i = ci.get(nome)
        return '' if i is None or i >= len(row) else str(row[i] or '').strip()
    alvo = day.strftime('%d/%m/%Y')
    out = []
    for row in lp.get('rows') or ():
        if cel(row, 'Data Vencimento') != alvo:
            continue
        conta_cp = cel(row, 'Contraparte (Conta)')
        doc = cel(row, 'CPF/CNPJ Cliente Contraparte')
        taxid, nome = (doc, '') if (doc and R._lp_is_taxid(doc)) else ('', doc)
        if not nome:
            try:
                nome = R._lp_cpty_by_account(conta_cp)
            except Exception:                               # noqa: BLE001
                nome = ''
        nome = nome or cel(row, 'Contraparte (Nome simplificado)')
        if not taxid:
            refdata = _refdata_index() if refdata is None else refdata
            taxid = refdata.get(domain.alnum(nome), '')
        product, lob = domain.produto_lob('OPTION', cel(row, 'Classe do ativo subjacente'), 'exp')
        out.append(_ev(day, 'exp', len(out), legal=cel(row, 'Parte (Nome simplificado)'),
                       account=cel(row, 'Parte (Conta)'),
                       internal_id=cel(row, 'Combinação de operações'), b3_id=cel(row, 'Código IF'),
                       product=product, lob=lob, kinds=[domain.EXPIRY], counterparty=nome,
                       taxid=taxid, cpty_account=conta_cp,
                       trade_date=cel(row, 'Data Início') or cel(row, 'Data Registro'), maturity=day,
                       premium=domain.num(cel(row, 'Valor financeiro total do prêmio')),
                       premium_date=cel(row, 'Data de Liquidação do Prêmio'),
                       holder=domain.holder_of(cel(row, 'Posição da Parte'))))
    return out


def collect_day(d, sources=domain.SOURCES):
    """Os eventos de UM dia, das fontes pedidas: {fonte: eventos | Exception}.
    Precisa de um request-context (os coletores memoizam no `g`)."""
    from flask import g
    R = _R()
    ref = datetime(d.year, d.month, d.day)
    out = {}
    try:
        closings = R._unwind_engine().encerramentos(d) or {}
    except Exception:                                       # noqa: BLE001
        R.log.warning('[efin] recompras de %s: encerramento não lido:\n%s', d, traceback.format_exc())
        closings = None
    refdata = _refdata_index()
    if 'ndf' in sources:
        try:
            out['ndf'] = ndf_events(d, R._ndfsum_collect(ref).get('email_trades') or [], closings, refdata)
        except Exception as exc:                            # noqa: BLE001
            R.log.warning('[efin] NDF Summary de %s não coletado:\n%s', d, traceback.format_exc())
            out['ndf'] = exc
    if 'ops' in sources:
        try:
            g._ops_trade_failed = []
            trade = R._ops_trade_rows(d)
            falhou = list(g.get('_ops_trade_failed') or [])
            # Família que estourou deixaria o dia sem ela — e gravado, o mês
            # pareceria não ter as operações que ela traria.
            out['ops'] = (RuntimeError('Other Products: %s' % ', '.join(falhou)) if falhou
                          else ops_events(d, trade, closings, refdata))
        except Exception as exc:                            # noqa: BLE001
            R.log.warning('[efin] Other Products de %s não coletado:\n%s', d, traceback.format_exc())
            out['ops'] = exc
    if 'exp' in sources:
        try:
            out['exp'] = expiry_events(d, R._lpopt_collect(ref) or {}, refdata)
        except Exception as exc:                            # noqa: BLE001
            R.log.warning('[efin] vencimentos de opção de %s não lidos:\n%s', d, traceback.format_exc())
            out['exp'] = exc
    return out


# ── A página de um mês ──────────────────────────────────────────────────────
def parse_ref(raw):
    """A data da tela (o mês dela); sem ela, o último dia do mês ANTERIOR — o
    arquivo que se gera é o do mês que acabou de fechar."""
    d = domain.parse_date(raw)
    if d:
        return d
    hoje = _R()._br_now()
    return date(hoje.year, hoje.month, 1) - timedelta(days=1)


def bizdays(ini, fim):
    R = _R()
    d, out = ini, []
    while d <= fim:
        if R._pcx_is_bizday(d):
            out.append(d)
        d += timedelta(days=1)
    return out


_INV = {campo: col for col, (campo, _t) in domain.EDIT_COLS.items()}


def cgd_of_op(o, rdcgd, cgd):
    """(data ISO, fonte) do CGD da operação: o Reference Data pelo CNPJ e, sem
    ele, pelo nome; depois o Tracking Docs. Fonte `refdata`/`trackdocs`/''."""
    por_cnpj, por_nome = rdcgd
    d = por_cnpj.get(domain.cnpj_key(o.get('taxid'))) or por_nome.get(domain.alnum(o.get('counterparty')))
    if d:
        return d, 'refdata'
    d = cgd_of(cgd, o.get('le'), o.get('taxid'))
    return (d, 'trackdocs') if d else ('', '')


def operations(doc, ym, decl=None, cgd=None, rdcgd=None):
    """As operações do mês, TODAS as páginas, fechadas e com o status — a leitura
    da tela, da correção e do arquivo, uma só. → (operações, excluídas), com
    `excluídas` = {página: {'intragroup': {chave}, 'not_declarant': {LE: {chave}}}}
    — cada página avisa só o que saiu DELA."""
    decl = declarants() if decl is None else decl
    cgd = cgd_index() if cgd is None else cgd
    rdcgd = refdata_cgd_index() if rdcgd is None else rdcgd
    eventos, excl = [], {}
    les, cps = {}, {}
    for _dia, fatias in sorted((doc.get('days') or {}).items()):
        for src in domain.SOURCES:
            for e in ((fatias or {}).get(src) or {}).get('rows') or []:
                e = dict(e)
                k = (e.get('account'), e.get('legal'))
                if k not in les:
                    les[k] = le_of(*k)
                e['le'] = les[k]
                kc = (e.get('cpty_account'), e.get('counterparty'))
                if kc not in cps:
                    cps[kc] = le_of(*kc)
                chave = domain.op_key(e['le'], e.get('b3_id'), e.get('internal_id'))
                fora = excl.setdefault(domain.page_of(*domain.produto_lob(
                    e.get('product'), e.get('lob'), e.get('source'))) or '',
                    {'intragroup': set(), 'not_declarant': {}})
                # Contraparte que é declarante é o intragrupo (Banco × MGT): as
                # duas pontas são nossas e nenhuma é cliente.
                if cps[kc] in decl:
                    fora['intragroup'].add(chave)
                    continue
                if e['le'] not in decl:
                    fora['not_declarant'].setdefault(e['le'] or '—', set()).add(chave)
                    continue
                eventos.append(e)
    ops = domain.aggregate(eventos)
    for m in doc.get('manual') or ():
        o = dict(m)
        o.update({'kinds': [], 'days': [], 'sources': [], 'internal_value': None, 'b3_value': None,
                  'tol': 0.0, 'manual': True, 'event': 'Manual'})
        for c in domain.OUTPUT_FIELDS:
            o.setdefault(c, 0.0)
        ops[o['key']] = o
    edits, apagadas, arquivos = doc.get('edits') or {}, doc.get('deleted') or {}, doc.get('files') or {}
    out = []
    for k, o in ops.items():
        if k in apagadas:
            continue
        e = edits.get(k) or {}
        fields = e.get('fields') or {}
        o['orig'] = {c: o.get(c) for c in fields}
        domain.finish(o, fields)
        # digitada (a correção, o Add Row) vence; senão o Reference Data e,
        # sem ele, o Tracking Docs — e a linha diz de onde veio
        if 'cgd_date' in fields or o.get('cgd_date'):
            o['cgd_src'] = 'edit' if o.get('cgd_date') else ''
        else:
            o['cgd_date'], o['cgd_src'] = cgd_of_op(o, rdcgd, cgd)
        o['review'] = e.get('status') or ''
        o['review_by'] = (e.get('checker_name') or e.get('checker') or e.get('maker_name') or e.get('maker') or '')
        o['review_at'] = e.get('checked_at') or e.get('at') or ''
        o['maker'] = e.get('maker') or ''
        o['edited'] = [_INV.get(c, c) for c in fields]
        o['missing'] = domain.missing(o, decl)
        o['line'] = ';'.join(domain.file_record(o, decl.get(o.get('le')) or {}, ym))
        ultimo = (arquivos.get(o.get('page') or '') or {}).get('lines') or {}
        o['status'] = domain.status_of(o['review'], ultimo.get(k) == o['line'])
        out.append(o)
    return out, excl


def build(page, ref, with_ops=False):
    """O payload da página `page` para o mês de `ref`. `with_ops`: devolve
    também as operações da página (`_ops`), para o arquivo ler as MESMAS linhas
    que a tela mostra."""
    R = _R()
    ym = domain.month_key(ref)
    ini, fim = domain.month_bounds(ref)
    doc = store.load(ym)
    decl = declarants()
    todas, excl = operations(doc, ym, decl)
    excl = excl.get(page) or {'intragroup': set(), 'not_declarant': {}}
    mine = [o for o in todas if o.get('page') == page]
    ordem = {s: i for i, s in enumerate(domain.STATUSES)}
    mine.sort(key=lambda o: (ordem.get(o['status'], 9), not o['missing'], domain.norm(o.get('counterparty')),
                             o.get('b3_id') or ''))
    rows = [domain.row_of(o) for o in mine]

    hoje = R._br_now().date()
    fatias = doc.get('days') or {}
    avisos = []
    faltam = [d for d in bizdays(ini, min(fim, hoje))
              if any(s not in (fatias.get(d.isoformat()) or {}) for s in domain.SOURCES)]
    if faltam:
        avisos.append(domain.aviso('missing_days', 'Dias úteis do mês sem liquidação importada: {days}',
                                   days=', '.join(d.strftime('%d/%m') for d in faltam)))
    falta = {}
    for o in mine:
        for c in o['missing']:
            falta[c] = falta.get(c, 0) + 1
    if falta:
        avisos.append(domain.aviso('missing_fields', '{n} linha(s) não vão ao arquivo sem: {fields}',
                                   n=sum(1 for o in mine if o['missing']),
                                   fields=', '.join('%s (%d)' % (c, n) for c, n in sorted(falta.items()))))

    def amostra(lista):
        return ', '.join(sorted(o.get('b3_id') or o.get('internal_id') or o['key'] for o in lista)[:8])
    sem_lob = [o for o in mine if not o.get('lob')]
    if sem_lob:
        avisos.append(domain.aviso('no_lob', '{n} operação(ões) sem LOB — a da EDG vai para o PYRAMID: {sample}',
                                   n=len(sem_lob), sample=amostra(sem_lob)))
    for code, flag, txt in (
            ('mixed', 'mixed', '{n} operação(ões) com prêmio e liquidação no mesmo caixa — o prêmio não foi '
                               'separado: {sample}'),
            ('unwind_unknown', 'unwind_unknown', '{n} recompra(s) sem saber se é total — a Data de '
                                                 'Encerramento ficou em branco: {sample}'),
            ('no_value', 'no_value', '{n} operação(ões) sem valor interno no Trade Level: {sample}')):
        lista = [o for o in mine if o.get(flag)]
        if lista:
            avisos.append(domain.aviso(code, txt, n=len(lista), sample=amostra(lista)))
    sem_premio = [o for o in mine if o.get('closing') and o.get('product') == 'OPTION' and o.get('premium') is None]
    if sem_premio:
        avisos.append(domain.aviso('premium_unknown', '{n} opção(ões) encerrada(s) sem o prêmio na posição — o '
                                   'Saldo ficou zero: {sample}', n=len(sem_premio), sample=amostra(sem_premio)))
    if excl['intragroup']:
        avisos.append(domain.aviso('intragroup', '{n} operação(ões) entre entidades declarantes (intragrupo) '
                                   'ficaram de fora', n=len(excl['intragroup'])))
    if excl['not_declarant']:
        avisos.append(domain.aviso('not_declarant', 'Operações de entidade fora do cadastro E-Financeira — '
                                   'Declarant ficaram de fora: {les}',
                                   les=', '.join('%s (%d)' % (le, len(ks))
                                                 for le, ks in sorted(excl['not_declarant'].items()))))

    ultimo = (doc.get('files') or {}).get(page) or {}
    return {
        'ref': ref.isoformat(),
        'page': page, 'page_label': domain.PAGES[page]['label'],
        'month': {'key': ym, 'label': '%02d/%04d' % (ref.month, ref.year),
                  'start_fmt': domain.dmy(ini), 'end_fmt': domain.dmy(fim)},
        'file_name': domain.file_name(page, ym),
        'last_file': {k: ultimo.get(k) for k in ('name', 'path', 'at', 'sid', 'n')} if ultimo else None,
        'history': [h for h in doc.get('history') or () if h.get('page') == page][-10:],
        'rows': rows,
        'counts': domain.counts(rows),
        'warnings': avisos,
        'imported_days': sorted(d for d in fatias if ini.isoformat() <= d <= fim.isoformat()),
        'le_options': sorted(decl),
        **({'_ops': mine} if with_ops else {}),
    }
