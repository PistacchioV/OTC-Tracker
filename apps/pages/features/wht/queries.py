# -*- coding: utf-8 -*-
"""Leitura do WHT: o lado OTC (as liquidações que o NDF Summary e o Other
Products já montam) e a página de um decêndio.

As FONTES são as mesmas linhas das duas telas de liquidação, nunca uma
segunda leitura dos arquivos: o NDF Summary entrega as operações do aviso
(`_ndfsum_collect(...)['email_trades']`, com as recompras do dia) e o Other
Products o Trade Level (`_ops_trade_rows`: swap, termo de mercadoria e opção).
Só entra a liquidação em que o BANCO (ou a MGT) PAGA — valor negativo, a ótica
das duas telas —, com ou sem imposto: a isenta também é informada ao HUB. O
prêmio de opção entra como UMA linha com o net da contraparte no dia.

O imposto de cada operação (`devido`) é o dela, ANTES do piso de R$ 1,00:
0,005% do bruto no termo de moeda, no de mercadoria e no prêmio de opção
(isento pelo `ndfc-ir-exempt`); a tabela regressiva no swap (o `_tax_n` do
Trade Level, que já é por operação e não tem piso). Quanto cada uma INFORMA
ao HUB é a quebra do piso, feita na leitura pelo `domain.allocate`.
"""
import traceback
from datetime import date, datetime, timedelta

from apps.pages.features.wht import domain
from apps.pages.features.wht.infra import store


def _R():
    from apps.pages import routes
    return routes


# ── Cadastros ───────────────────────────────────────────────────────────────
def code_rows():
    return _R()._mapping_rows('wht-codes')


def company_rows():
    return _R()._mapping_rows('wht-company')


def non_resident_keys():
    """CNPJs e nomes do `wht-non-resident` (o código 5286 é do não residente)."""
    cnpjs, nomes = set(), set()
    for r in _R()._mapping_rows('wht-non-resident'):
        c = domain.cnpj_key(r.get('CNPJ'))
        if c:
            cnpjs.add(c)
        n = domain.alnum(r.get('COUNTERPARTY'))
        if n:
            nomes.add(n)
    return cnpjs, nomes


def le_token(legal):
    """A entidade da linha (`JPM`, `MGT`…) a partir do texto do LEGAL do Cockpit
    ou da entidade do Trade Level. Ignora pontuação e espaço ("J.P." ≡ "JP"),
    como o filtro do próprio Cockpit; o nome do `le-spn` também vale."""
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
        if nome and (s == nome or s.startswith(nome) or nome.startswith(s)):
            return domain.norm(r.get('LE'))
    return domain.norm(legal)


def companies():
    """({LE: (empresa, filial)}, {empresa: LE}) do `wht-company`."""
    por_le, por_emp = {}, {}
    for r in company_rows():
        le = domain.norm(r.get('LE'))
        emp = domain.digits(r.get('COMPANY')).zfill(5) if domain.digits(r.get('COMPANY')) else ''
        if not le or not emp:
            continue
        por_le.setdefault(le, (emp, domain.digits(r.get('BRANCH')).zfill(4) or '0001'))
        por_emp.setdefault(emp, le)
    return por_le, por_emp


def _refdata_index():
    """{nome/acrônimo sem pontuação: CNPJ} do Reference Data. O Trade Level de
    mercadoria fala pelo ACRÔNIMO (`LAWTONMULTIME`), o resto pelo nome."""
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


# ── As fontes → as linhas do lado OTC ───────────────────────────────────────
def _linha(day, source, seq, internal_id, b3_id, product, lob, event, gross, devido,
           taxable, counterparty, taxid, legal, ir_unknown=False):
    return {'day': day.isoformat(), 'source': source, 'seq': seq,
            'internal_id': str(internal_id or '').strip(), 'b3_id': str(b3_id or '').strip(),
            'product': product, 'lob': str(lob or '').strip().upper(),
            'event': str(event or '').strip().upper(),
            'gross': domain.r2(gross), 'devido': domain.r2(devido or 0.0),
            'taxable': bool(taxable), 'counterparty': str(counterparty or '').strip(),
            'taxid': str(taxid or '').strip(), 'le': le_token(legal),
            'ir_unknown': bool(ir_unknown)}


def _ids(rows):
    """Identidade estável de cada linha dentro do dia: fonte × entidade × id,
    com um contador para o mesmo id que aparece duas vezes."""
    vistos = {}
    for r in rows:
        base = '%s|%s|%s|%s' % (r['day'], r['source'], r['le'], r['internal_id'] or r['b3_id'])
        vistos[base] = vistos.get(base, 0) + 1
        r['id'] = '%s|%d' % (base, vistos[base])
    return rows


def ndf_rows(day, trades):
    """As operações do NDF Summary (`email_trades`) que o banco paga."""
    R = _R()
    rate = R._NDFADV_IR_RATE
    refdata = None
    out = []
    for r in trades or ():
        s = r.get('settlement')
        if s is None or s >= 0:
            continue
        cpty = str(r.get('counterparty', '') or '').strip()
        exempt = R._ndfc_ir_exempt(cpty)
        gross = abs(float(s))
        taxid = r.get('taxid') or ''
        if not taxid:
            refdata = _refdata_index() if refdata is None else refdata
            taxid = refdata.get(domain.alnum(cpty), '')
        event = r.get('settle_type') or ('UNWIND' if r.get('unwind') else 'MATURITY')
        # O NDF de moeda vem do Cockpit: é da CEM (`domain.produto_lob`).
        out.append(_linha(day, 'ndf', len(out), r.get('athena'), r.get('b3'), 'NDF',
                          domain.LOB_NDF_PADRAO,
                          event, gross, 0.0 if exempt else gross * rate, not exempt,
                          cpty, taxid, r.get('legal')))
    return _ids(out)


def _produto_ops(r):
    """(PRODUCT, LOB) da linha do Trade Level: SWAP, NDF (o termo de
    mercadoria, LOB COMMODITIES) ou OPTION com a LOB da classe do ativo — a
    regra é a de `domain.produto_lob`."""
    prod = domain.norm(r.get('product'))
    if prod not in ('SWAP', 'TERMO', 'NDF COMMODITIES'):
        prod = 'OPTION'
    return domain.produto_lob(prod, r.get('lob'), 'ops')


def _ops_id(r, product):
    """O identificador que vai ao HUB. Na liquidação de COMMODITIES (termo e
    opção) é o Trade Id do OTM (`85000H-1PMHHP`), que a linha do Trade Level
    traz em `_otm_id`; o Nº da Confirmação do Athena só tem o mesmo sufixo e
    não casa com o Docto do HUB. Sem OTM, fica o de antes."""
    if domain.norm(r.get('lob')) == domain.LOB_COMMODITIES and product in ('NDF', 'OPTION'):
        otm = str(r.get('_otm_id') or '').strip()
        if otm:
            return otm
    return r.get('internal_id')


def ops_rows(day, trades):
    """As linhas do Trade Level do Other Products que o banco (ou a MGT) PAGA —
    tenha ou não imposto: a isenta também é informada ao HUB.

    O PRÊMIO de opção sai numa linha SÓ, com o NET da contraparte no dia
    (entidade × contraparte × produto): é o caixa que liquida e é sobre ele que
    o imposto incide (`_optadv_apply_ir`) — dois prêmios que se anulam não
    pagam nada. Só o net em que o banco paga entra; a linha leva o id da
    operação que mais paga, e `net_of` diz quais entraram no net."""
    R = _R()
    rate = R._NDFADV_IR_RATE
    refdata = _refdata_index()
    out, premios, ordem = [], {}, []
    for r in trades or ():
        s = r.get('_settle_n')
        if s is None:
            continue
        product, lob = _produto_ops(r)
        event = str(r.get('settle_type', '') or '')
        if product == 'OPTION' and 'PREMIUM' in domain.norm(event):
            k = (domain.alnum(r.get('_legal')), domain.alnum(r.get('counterparty')), product, lob)
            if k not in premios:
                premios[k] = []
                ordem.append(k)
            premios[k].append(r)
            continue
        if s >= 0:
            continue
        cpty = str(r.get('counterparty', '') or '').strip()
        gross = abs(float(s))
        unknown = False
        if product == 'SWAP':
            tax = r.get('_tax_n')
            unknown = tax is None
            devido = abs(float(tax)) if tax is not None else 0.0
            taxable = unknown or devido > 0
        else:
            # Termo de mercadoria paga por contrato; na opção, exercício e
            # recompra são liquidação isenta (só o prêmio paga, acima).
            taxable = product == 'NDF' and not R._ndfc_ir_exempt(cpty)
            devido = gross * rate if taxable else 0.0
        out.append(_linha(day, 'ops', len(out), _ops_id(r, product), r.get('id_b3'), product,
                          lob, event, gross, devido, taxable, cpty,
                          refdata.get(domain.alnum(cpty), ''), r.get('_legal'), unknown))
    for k in ordem:
        linhas = premios[k]
        net = sum(float(r['_settle_n']) for r in linhas)
        if net >= 0:
            continue
        rep = min(linhas, key=lambda r: float(r['_settle_n']))      # a que mais paga
        cpty = str(rep.get('counterparty', '') or '').strip()
        gross = abs(net)
        taxable = not R._ndfc_ir_exempt(cpty)
        x = _linha(day, 'ops', len(out), _ops_id(rep, k[2]), rep.get('id_b3'), k[2],
                   k[3], 'PREMIUM', gross, gross * rate if taxable else 0.0, taxable,
                   cpty, refdata.get(domain.alnum(cpty), ''), rep.get('_legal'))
        if len(linhas) > 1:
            x['net_of'] = [str(_ops_id(r, k[2]) or r.get('id_b3') or '') for r in linhas]
        out.append(x)
    return _ids(out)


def collect_day(d, sources=('ndf', 'ops')):
    """As linhas OTC de UM dia, das fontes pedidas: {fonte: linhas | Exception}.
    Precisa de um request-context (os coletores memoizam no `g`)."""
    from flask import g
    R = _R()
    ref = datetime(d.year, d.month, d.day)
    out = {}
    if 'ndf' in sources:
        try:
            out['ndf'] = ndf_rows(d, R._ndfsum_collect(ref).get('email_trades') or [])
        except Exception as exc:                            # noqa: BLE001
            R.log.warning('[wht] NDF Summary de %s não coletado:\n%s', d, traceback.format_exc())
            out['ndf'] = exc
    if 'ops' in sources:
        try:
            g._ops_trade_failed = []
            trade = R._ops_trade_rows(d)
            falhou = list(g.get('_ops_trade_failed') or [])
            # Família que estourou deixaria a fatia do dia sem ela — e gravada,
            # o HUB pareceria ter operações que o OTC não tem.
            out['ops'] = (RuntimeError('Other Products: %s' % ', '.join(falhou)) if falhou
                          else ops_rows(d, trade))
        except Exception as exc:                            # noqa: BLE001
            R.log.warning('[wht] Other Products de %s não coletado:\n%s', d, traceback.format_exc())
            out['ops'] = exc
    return out


# ── A página de um decêndio ─────────────────────────────────────────────────
def parse_ref(raw):
    """A data da tela; sem ela, o decêndio do dia útil ANTERIOR — no dia do
    recolhimento o que se confere é o decêndio que acabou de fechar."""
    d = domain.parse_date(raw)
    if d:
        return d
    hoje = _R()._br_now()
    return _R()._prev_anbima_bizday(datetime(hoje.year, hoje.month, hoje.day)).date()


def _bizdays(ini, fim):
    R = _R()
    d, out = ini, []
    while d <= fim:
        if R._pcx_is_bizday(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def enrich_otc(rows, codes=None, por_le=None, nonres=None):
    """Código, tributo, piso e documento de cada linha OTC — na LEITURA, para a
    edição do cadastro valer no request seguinte."""
    codes = code_rows() if codes is None else codes
    por_le = companies()[0] if por_le is None else por_le
    nr_cnpj, nr_nome = non_resident_keys() if nonres is None else nonres
    out = []
    for r in rows:
        o = dict(r)
        o['date'] = domain.parse_date(o.get('day'))
        # O mês gravado antes da regra (`NDF COMM`, `OPTION COMM`, NDF sem LOB,
        # `INDICES INTERNACIONAIS`) sai certo sem recoletar.
        o['product'], o['lob'] = domain.produto_lob(o.get('product'), o.get('lob'), o.get('source'))
        resident = not (domain.cnpj_key(o.get('taxid')) in nr_cnpj
                        or domain.alnum(o.get('counterparty')) in nr_nome)
        c = domain.resolve_code(codes, o.get('product'), o.get('lob'), o.get('event'),
                                o.get('taxable'), resident)
        o['code'] = str((c or {}).get('CODE') or '').strip().upper()
        o['tributo'] = str((c or {}).get('TRIBUTO') or '').strip().upper()
        o['floor'] = domain.yes((c or {}).get('MONTHLY FLOOR'))
        o['doc'] = domain.doc_number((c or {}).get('DOC PREFIX'), o.get('internal_id') or o.get('b3_id'))
        o['resident'] = resident
        o['no_code'] = c is None
        o['company'] = (por_le.get(o.get('le')) or ('', ''))
        out.append(o)
    return out


def hub_rows_of(doc, ini, fim, por_emp=None):
    por_emp = companies()[1] if por_emp is None else por_emp
    out = []
    for h in doc.get('hub') or ():
        d = domain.parse_date(h.get('date'))
        if not d or not (ini <= d <= fim):
            continue
        x = dict(h)
        x['date'] = d
        x['le'] = por_emp.get(domain.digits(h.get('empresa')).zfill(5), '')
        x['key'] = domain.hub_key(dict(h, date=d))
        out.append(x)
    return out


def build(ref):
    """O payload da página para o decêndio de `ref`."""
    R = _R()
    y, m, n = domain.decendio_of(ref)
    ini, fim = domain.decendio_bounds(y, m, n)
    doc = store.load(domain.month_key(ref))
    por_le, por_emp = companies()
    codes, nonres = code_rows(), non_resident_keys()

    # O mês até o fim do decêndio: o piso precisa dos decêndios anteriores.
    mes = []
    for day, fatias in sorted((doc.get('otc') or {}).items()):
        dd = domain.parse_date(day)
        if not dd or dd > fim:
            continue
        for src in ('ndf', 'ops'):
            mes.extend(((fatias or {}).get(src) or {}).get('rows') or [])
    mes = enrich_otc(mes, codes, por_le, nonres)
    informado = domain.allocate([{'id': o['id'], 'bucket': '%s|%s' % (
        o.get('le'), domain.cnpj_key(o.get('taxid')) or domain.alnum(o.get('counterparty'))),
        'date': o['date'], 'devido': o.get('devido'), 'floor': o.get('floor'),
        'seq': (o.get('source') == 'ops', o.get('seq') or 0)} for o in mes if o.get('date')])
    otc = []
    for o in mes:
        if o.get('date') and ini <= o['date'] <= fim:
            o['ir'] = informado.get(o['id'], 0.0)
            otc.append(o)
    hub = hub_rows_of(doc, ini, fim, por_emp)

    rows = [domain.row_of(o, h) for o, h in domain.match(otc, hub)]
    ordem = {s: i for i, s in enumerate(domain.STATUSES)}
    rows.sort(key=lambda r: (ordem.get(r['status'], 9), r['Product'], r['OTC_TD'] or r['HUB_TD'],
                             domain.norm(r['OTC_cntpy'] or r['HUB_cntpy'])))

    hoje = R._br_now().date()
    avisos = []
    fatias = doc.get('otc') or {}

    def sem_fatia(d):
        f = fatias.get(d.isoformat()) or {}
        return [s for s in ('ndf', 'ops') if s not in f]
    faltam = [(d, sem_fatia(d)) for d in _bizdays(ini, min(fim, hoje))]
    faltam = [(d, s) for d, s in faltam if s]
    if faltam:
        avisos.append(domain.aviso('missing_days', 'Dias do decêndio sem liquidação importada: {days}',
                                   days=', '.join(domain.dmy(d) for d, _ in faltam)))
    antes = [d for d in _bizdays(date(y, m, 1), ini - timedelta(days=1)) if sem_fatia(d)]
    if antes:
        avisos.append(domain.aviso('missing_prev', 'O piso de R$ 1,00 é do mês: os dias {days} '
                                   'dos decêndios anteriores não foram importados',
                                   days=', '.join(domain.dmy(d) for d in antes)))
    sem_codigo = [o for o in otc if o.get('no_code')]
    if sem_codigo:
        avisos.append(domain.aviso('no_code', '{n} operação(ões) sem linha no cadastro WHT Codes: {sample}',
                                   n=len(sem_codigo), sample=', '.join(sorted({
                                       '%s/%s' % (o['product'], 'T' if o['taxable'] else 'E')
                                       for o in sem_codigo}))))
    sem_ir = [o for o in otc if o.get('ir_unknown')]
    if sem_ir:
        avisos.append(domain.aviso('ir_unknown', '{n} swap(s) sem alíquota de IR no Trade Level '
                                   '(prazo ou direção ausente): {sample}', n=len(sem_ir),
                                   sample=', '.join(o['internal_id'] or o['b3_id'] for o in sem_ir[:5])))
    sem_emp = sorted({o.get('le') or '—' for o in otc if not o['company'][0]})
    if sem_emp:
        avisos.append(domain.aviso('no_company', 'Entidade sem empresa no cadastro WHT Company: {les}',
                                   les=', '.join(sem_emp)))

    arquivos = [f for f in (doc.get('hub_files') or ())
                if domain.decendio_key(y, m, n) in (f.get('scope') or ())]
    return {
        'ref': ref.isoformat(),
        'decendio': {'key': domain.decendio_key(y, m, n), 'n': n,
                     'start': ini.isoformat(), 'end': fim.isoformat(),
                     'start_fmt': domain.dmy(ini), 'end_fmt': domain.dmy(fim),
                     'payment': domain.dmy(domain.payment_date(fim, R._pcx_is_bizday))},
        'rows': rows,
        'summary': domain.summary(rows),
        'counts': domain.counts(rows),
        'warnings': avisos,
        'hub_files': arquivos,
        'imported_days': sorted(d for d in fatias if ini.isoformat() <= d <= fim.isoformat()),
    }
