# -*- coding: utf-8 -*-
"""As escritas do Intrag — a linha espelhada de cada produto (termo de
mercadoria, termo de moeda e opção) e o mapeamento do B3 ID vindo do retorno.
"""
import json
import os
import re
import traceback
from datetime import datetime

from apps.pages.features.intrag import domain, queries
from apps.pages.features.intrag.infra import mappers, persistence

def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _save_intrag_ndf_entry(deal):
    """Compute all Intrag NDF fields and append/update in the daily JSON file."""
    td = _R()._parse_deal_date(deal.get('TradeDate', '') or '')
    sd = _R()._parse_deal_date(deal.get('SettlementDate', '') or '')
    fx = _R()._parse_deal_date(deal.get('FXConvDate', '') or '')
    fe = _R()._parse_deal_date(deal.get('FixingEndDate', '') or '')

    fmt_d = lambda d: d.strftime('%Y-%m-%d') if d else ''

    direction = (deal.get('Direction', '') or '').upper()
    position = 'VENDEDOR' if direction == 'SELL' else ('COMPRADOR' if direction == 'BUY' else '')

    try:
        total_notional = float(str(deal.get('TotalNotional', 0) or 0).replace(',', ''))
    except (ValueError, TypeError):
        total_notional = 0.0
    try:
        strike_val = float(str(deal.get('Strike', 0) or 0).replace(',', ''))
    except (ValueError, TypeError):
        strike_val = 0.0

    qic = (deal.get('QuotedInCents', 'NO') or 'NO').upper() == 'YES'
    strike_effective = strike_val / 100.0 if qic else strike_val
    notional_value_str = f'{total_notional * strike_effective:.2f}' if (total_notional and strike_val) else ''
    qty_str = str(int(round(total_notional))) if total_notional else ''
    strike_str = f'{strike_effective:.4f}' if strike_val else ''

    underlying_asset = (deal.get('UnderlyingAsset', '') or '').strip()
    subj = _R()._subjacente_by_code().get(underlying_asset.upper(), {})
    reference_exchange = (subj.get('Bolsa de Negociacao') or '').strip()
    commodity = (deal.get('Commodities', '') or '').strip()
    unit = (subj.get('Unidade de Negociacao') or '').strip()
    strike_ccy = (deal.get('StrikeCurrency', '') or '').strip()

    # Maturity Month/Year: o vencimento do CONTRATO do subjacente, pelo cadastro
    # da Index B3 (Mes/Ano Vencimento do Código do Ativo Subjacente). O `Month`
    # do deal é o mês de pricing e nem sempre coincide com o mês embutido no
    # código (AULF27 = jan/2027) — era dele que o campo saía, e saía errado
    # quando os dois divergiam. Código sem cadastro cai no comportamento
    # antigo (Month, depois Settlement), que é também o caminho dos deals
    # antigos re-salvos.
    expiry_str = ''
    try:
        mes_v = int(float(subj.get('Mes Vencimento') or 0))
        ano_v = int(float(subj.get('Ano Vencimento') or 0))
        # Faixa sã: o cadastro tem linhas com ano digitado errado (AGD1 →
        # 2202), e '12-2202' num arquivo de registro é pior que o fallback.
        if 1 <= mes_v <= 12 and 2000 <= ano_v <= 2099:
            expiry_str = '{:02d}-{:04d}'.format(mes_v, ano_v)
    except (ValueError, TypeError):
        expiry_str = ''
    if not expiry_str:
        month_raw = (deal.get('Month', '') or '').strip().upper()
        m = re.match(r'^([A-Z]{3})(\d{2,4})$', month_raw)
        if m:
            mon_num = _R()._MONTH_ABBR.get(m.group(1), '')
            yr = m.group(2) if len(m.group(2)) == 4 else '20' + m.group(2)
            if mon_num:
                expiry_str = f'{mon_num}-{yr}'
        elif re.match(r'^\d{4}-\d{2}$', month_raw):
            parts = month_raw.split('-')
            expiry_str = f'{parts[1]}-{parts[0]}'
        elif sd:
            expiry_str = sd.strftime('%m-%Y')

    # ANBIMA biz days between FXConvDate and SettlementDate
    anbima_days = ''
    if fx and sd:
        lo, hi = (fx, sd) if fx < sd else (sd, fx)
        anbima_days = f'D-{_R()._anbima_bizdays_between(lo, hi)}'

    # Weekday biz days between SettlementDate and FixingEndDate
    weekday_days = ''
    if sd and fe:
        lo, hi = (sd, fe) if sd < fe else (fe, sd)
        weekday_days = f'D-{_R()._weekday_bizdays_between(lo, hi)}'

    trade_type = (deal.get('TradeType', '') or '').upper()
    trade_type_label = 'ASIATICO' if 'ASIAN' in trade_type else ('FINAL' if 'VANILLA' in trade_type else '')

    strike_ccy_label = 'Strike em BRL' if strike_ccy.upper() == 'BRL' else ''

    entry = {
        'contract_type':          'NDF - TERMO MERCADORIA',
        'b3_id':                  deal.get('B3_ID', '') or '',
        'portfolio_code':         'INTRAGJP552',
        'participant_position':   position,
        'party_tax_id':           '',
        'counterparty':           'JPM',
        'cpty_tax_id':            '',
        'cpty_collateral_basket': 'NÃO',
        'party_collateral_basket':'NÃO',
        'notional_value':         notional_value_str,
        'trade_date':             fmt_d(td),
        'registration_date':      fmt_d(td),
        'maturity_date':          fmt_d(sd),
        'currency':               'N/A',
        'reference_exchange':     reference_exchange,
        'commodity':              commodity,
        'underlying_asset':       underlying_asset,
        'quantity':               qty_str,
        'unit_of_negotiation':    unit,
        'strike':                 strike_str,
        'strike_currency':        strike_ccy,
        'expiry_month_year':      expiry_str,
        'anbima_bizdays':         anbima_days,
        'fixed_0':                '0',
        'na_1':                   'N/A',
        'na_2':                   'N/A',
        'weekday_bizdays':        weekday_days,
        'trade_type_label':       trade_type_label,
        'strike_ccy_label':       strike_ccy_label,
        'na_3':                   'N/A',
        '_deal':                  deal.get('Deal', '') or '',
        '_client':                deal.get('Client', '') or '',
        'status':                 'New',
        'maker':                  '',
        'checker':                '',
    }

    persistence._intrag_ndf_persist(entry, td)


def _save_intrag_ndf_moeda_entry(deal):
    """NDF de moeda (Vanilla / Other Publisher contra o Lawton) → entrada na
    Intrag NDF no layout do arquivo "Instrucao NDF Moeda" (NDF - TERMO DE
    MOEDAS): campos de mercadoria em N/A, moeda = perna estrangeira do par,
    valor nocional na moeda estrangeira, taxa forward em R$/moeda na coluna
    Forward Rate (R$/CCY) e o publisher na coluna Information Source — da
    coluna Trade Price em diante o layout de moeda anda uma casa à esquerda
    em relação ao de mercadoria."""
    td = _R()._parse_deal_date(deal.get('TradeDate', '') or '')
    sd = _R()._parse_deal_date(deal.get('SettlementDate', '') or '')
    lf = _R()._parse_deal_date(deal.get('LastFixingDate', '') or '')
    fmt_d = lambda d: d.strftime('%Y-%m-%d') if d else ''

    # A linha das páginas genéricas é a ponta do banco CONTRA o Lawton; a
    # carteira registrada (INTRAGJP552) é a do fundo, então a posição do
    # participante é a inversa da Direction da linha (banco SELL → fundo compra).
    direction = (deal.get('Direction', '') or '').upper()
    position = 'COMPRADOR' if direction == 'SELL' else ('VENDEDOR' if direction == 'BUY' else '')

    # _conf_to_float detecta BR ("1.234,56") e US ("1,234.56") — o Notional das
    # páginas genéricas é gravado no formato US ('{:,.2f}').
    rate_val = _R()._conf_to_float(deal.get('Rate', ''))
    notional_val = _R()._conf_to_float(deal.get('Notional', ''))
    qty_ccy = (deal.get('QuantityCurrency', '') or '').strip().upper()
    oth_ccy = (deal.get('OtherQuantityCurrency', '') or '').strip().upper()
    foreign_ccy = oth_ccy if qty_ccy == 'BRL' else qty_ccy

    # Valor nocional na moeda estrangeira: nocional em BRL ÷ taxa (R$/moeda);
    # quando a quantidade do deal já está na moeda estrangeira, é o próprio.
    if notional_val is not None and qty_ccy == 'BRL' and rate_val:
        foreign_notional = notional_val / rate_val
    else:
        foreign_notional = notional_val
    notional_str = '{:.2f}'.format(foreign_notional) if foreign_notional is not None else ''

    rate_str = '{:.8f}'.format(rate_val).rstrip('0').rstrip('.') if rate_val is not None else ''
    # No template o publisher sai com espaços ("PTAX USB WMR 4") — nunca o
    # pipe/colchete/chave do texto cru (`PTAX|BRR[PTAX` → `PTAX BRR PTAX`).
    publisher = domain._intrag_info_source(deal.get('Publisher', '') or 'PTAX') or 'PTAX'

    # Offset do fixing (dias úteis ANBIMA entre o último fixing e o vencimento);
    # o padrão de NDF de moeda é D-2.
    fixing_off = 'D-2'
    if lf and sd:
        lo, hi = (lf, sd) if lf < sd else (sd, lf)
        fixing_off = 'D-{}'.format(_R()._anbima_bizdays_between(lo, hi))

    entry = {
        'contract_type':          'NDF - TERMO DE MOEDAS',
        'b3_id':                  deal.get('B3_ID', '') or '',
        'portfolio_code':         'INTRAGJP552',
        'participant_position':   position,
        'party_tax_id':           '',
        'counterparty':           'JPM',
        'cpty_tax_id':            '',
        'cpty_collateral_basket': 'NÃO',
        'party_collateral_basket':'NÃO',
        'notional_value':         notional_str,
        'trade_date':             fmt_d(td),
        'registration_date':      fmt_d(td),
        'maturity_date':          fmt_d(sd),
        'currency':               foreign_ccy,
        'reference_exchange':     'N/A',
        'commodity':              'N/A',
        'underlying_asset':       'N/A',
        'quantity':               'N/A',
        'unit_of_negotiation':    '0',
        # Da coluna Trade Price em diante o termo de MOEDA anda uma casa à
        # esquerda em relação ao termo de mercadoria (as chaves são nomes
        # legados; o comentário ao lado é a coluna que cada uma alimenta).
        'strike':                 '0',         # Trade Price
        'strike_currency':        'BRL',       # Settlement Parity
        'expiry_month_year':      'N/A',       # Maturity Month/Year
        'anbima_bizdays':         'N/A',       # Spot Fixing
        'fixed_0':                rate_str,    # Forward Rate (R$/CCY)
        'na_1':                   'N/A',       # Asian Fwd Avg Rate
        'na_2':                   publisher,   # Information Source
        'weekday_bizdays':        fixing_off,  # Comm Fixing
        'trade_type_label':       'N/A',       # Adjustment Type
        'strike_ccy_label':       'N/A',       # Observation
        'na_3':                   'N/A',       # Discount Factor
        '_deal':                  deal.get('Deal', '') or '',
        '_client':                deal.get('Client', '') or '',
        'status':                 'New',
        'maker':                  '',
        'checker':                '',
    }
    persistence._intrag_ndf_persist(entry, td)


def _save_intrag_opt_entry(deal, is_fxo=False):
    """Compute the Intrag Option fields from a New Deals Opt-Comm (or Opt-FXO)
    deal and append/update the daily JSON. Only the columns specified so far are
    filled; the rest are placeholders to be wired later. Random my_number /
    cetip_number are generated once and preserved on re-save (like the lifecycle
    state).

    FXO deals share the same intrag_opt.json file and the same filling logic,
    but override seven fields (information source, exchange, ticker, currency
    symbol, bulletin, bulletin time and SISBACEN currency code)."""
    td = _R()._parse_deal_date(deal.get('TradeDate', '') or '')
    sd = _R()._parse_deal_date(deal.get('SettlementDate', '') or '')
    fmt_br = lambda d: d.strftime('%d/%m/%Y') if d else ''

    direction = (deal.get('Direction', '') or '').upper()
    if direction == 'BUY':
        buyer_account = domain._INTRAG_OPT_LAWTON_ACC
    elif direction == 'SELL':
        buyer_account = domain._INTRAG_OPT_JPM_ACC
    else:
        buyer_account = ''
    buyer_name = domain._intrag_opt_name_for(buyer_account)
    # Seller is the inverse account/name of the buyer.
    if buyer_account == domain._INTRAG_OPT_JPM_ACC:
        seller_account = domain._INTRAG_OPT_LAWTON_ACC
    elif buyer_account == domain._INTRAG_OPT_LAWTON_ACC:
        seller_account = domain._INTRAG_OPT_JPM_ACC
    else:
        seller_account = ''
    seller_name = domain._intrag_opt_name_for(seller_account)

    instrument = (deal.get('Instrument', '') or '').upper()
    if 'PUT' in instrument:
        contract = 'OFVC'
    elif 'CALL' in instrument:
        contract = 'OFCC'
    else:
        contract = ''

    currency_symbol = (deal.get('Commodities', '') or '').strip()[:3].upper()

    # ── numeric columns ──────────────────────────────────────────────────
    def _f(v):
        try:
            return float(str(v if v is not None else '').replace(',', '').strip() or 0)
        except (ValueError, TypeError):
            return 0.0

    def _has(key):
        return str(deal.get(key, '') or '').strip() != ''

    qic = (deal.get('QuotedInCents', 'NO') or 'NO').upper() == 'YES'
    # Cotado em cents divide por 100 SEMPRE, seja o strike em USD ou em BRL: a
    # regra é do ativo (Fator Conversão 0,01 no Subjacente) e não da moeda do
    # deal. Antes o BRL era exceção aqui e não era no Conecta desta mesma
    # página — o mesmo deal saía com strike diferente nos dois arquivos. §172
    _cents = lambda v: (v / 100.0) if qic else v

    is_call = 'CALL' in instrument
    is_put  = 'PUT' in instrument

    premium_val  = _f(deal.get('Premium'))
    notional_val = _f(deal.get('TotalNotional'))
    strike_adj   = _cents(_f(deal.get('Strike')))
    ppu_adj      = _cents(_f(deal.get('PremiumPerUnit')))

    premium_str    = '{:.2f}'.format(premium_val)  if _has('Premium')       else ''
    fxbase_str     = '{:.2f}'.format(notional_val) if _has('TotalNotional') else ''
    quantity_str   = '{:.2f}'.format(notional_val) if _has('TotalNotional') else ''
    call_strike    = '{:.8f}'.format(strike_adj)   if (is_call and _has('Strike')) else ''
    put_strike     = '{:.8f}'.format(strike_adj)   if (is_put  and _has('Strike')) else ''
    call_premium   = '{:.8f}'.format(ppu_adj)      if (is_call and _has('PremiumPerUnit')) else ''
    put_premium    = '{:.8f}'.format(ppu_adj)      if (is_put  and _has('PremiumPerUnit')) else ''

    # Fixing = weekday biz-days (no calendar) between FixingEndDate and SettlementDate.
    fe = _R()._parse_deal_date(deal.get('FixingEndDate', '') or '')
    fixing_days = ''
    if fe and sd:
        lo, hi = (fe, sd) if fe < sd else (sd, fe)
        fixing_days = str(_R()._weekday_bizdays_between(lo, hi))
    fixing_desc = ('D-' + fixing_days) if fixing_days != '' else ''

    underlying_asset = (deal.get('UnderlyingAsset', '') or '').strip()
    subj = _R()._subjacente_by_code().get(underlying_asset.upper(), {})
    exchange = (subj.get('Bolsa de Negociacao') or '').strip()

    spot = _R()._parse_deal_date(deal.get('SpotDate', '') or '')
    trade_type = (deal.get('TradeType', '') or '').upper()
    if 'ASIAN' in trade_type:
        asian_label = 'APLICÁVEL'
    elif 'VANILLA' in trade_type:
        asian_label = 'NÃO APLICÁVEL'
    else:
        asian_label = ''

    # FXO overrides these seven columns; everything else uses the shared logic.
    if is_fxo:
        info_source   = 'SISBACEN'
        exchange_val  = 'BACEN'
        ticker_val    = 'USD'
        currency_sym  = 'USD'
        bulletin_val  = '3'
        bulletin_time = '18:00'
        sisbacen_ccy  = '220'
    else:
        info_source   = 'COMMODITIES'
        exchange_val  = exchange
        ticker_val    = underlying_asset
        currency_sym  = currency_symbol
        bulletin_val  = '9'
        bulletin_time = ''
        sisbacen_ccy  = 'COM'

    entry = {
        'portfolio':              'INTRAGJP552',
        'system_id':              'OPCAO',
        'line_type_id':           '1',
        'registration_date':      fmt_br(td),
        'buyer_account':          buyer_account,
        'buyer_name':             buyer_name,
        'contract':               contract,
        'b3_id':                  deal.get('B3_ID', '') or '',
        'my_number':              ''.join(_R().random.choice(_R().string.digits) for _ in range(10)),
        'trade_type':             '002',
        'seller_account':         seller_account,
        'seller_name':            seller_name,
        'start_date':             fmt_br(td),
        'maturity_date':          fmt_br(sd),
        'cetip_number':           ''.join(_R().random.choice(_R().string.digits) for _ in range(16)),
        'sisbacen_currency_code': sisbacen_ccy,
        'currency_symbol':        currency_sym,
        'investment_amount':      premium_str,        # Premium
        'fx_base_value':          fxbase_str,         # Total Notional
        'prepaid_value':          '',                 # Unwind Amount
        'prepayment_unit_price':  '',                 # Unwind Unit Price
        'redemption_value':       '0.00',
        'call_strike_price':      call_strike,
        'put_strike_price':       put_strike,
        'call_unit_premium':      call_premium,
        'put_unit_premium':       put_premium,
        'barrier_rate':           '',
        'exercise_type':          'EUROPEIA',
        'information_source':     info_source,
        'bulletin':               bulletin_val,
        'bulletin_time':          bulletin_time,
        'maturity_rate':          fixing_days,        # Fixing (biz-day count)
        'maturity_rate_desc':     fixing_desc,        # Fixing Description (D-n)
        'query_source':           exchange_val,       # Exchange (Bolsa de Negociacao)
        'ticker':                 ticker_val,
        'quantity':               quantity_str,
        'premium_payment_date':   spot.strftime('%d/%m/%Y') if spot else '',
        'asian_option_average':   asian_label,
        '_deal':   deal.get('Deal', '') or '',
        '_client': deal.get('Client', '') or '',
        'status':  'New',
        'maker':   '',
        'checker': '',
    }

    ref = td or datetime.now()
    dir_path = os.path.join(persistence.INTRAG_OPT_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'))
    os.makedirs(dir_path, exist_ok=True)
    fname = ref.strftime('%Y%m%d') + '_intrag_opt.json'
    file_path = os.path.join(dir_path, fname)

    with _R()._cache_lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    entries = json.load(fh)
                if not isinstance(entries, list):
                    entries = []
            except (json.JSONDecodeError, ValueError):
                entries = []
        else:
            entries = []
        deal_id = entry['_deal']
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            # Preserve lifecycle + the once-generated random numbers on re-save.
            for k in ('status', 'maker', 'checker', 'my_number', 'cetip_number'):
                if entries[idx].get(k):
                    entry[k] = entries[idx][k]
            entries[idx] = entry
        else:
            entries.append(entry)
        _R()._atomic_write_json(file_path, entries)
    _R().log.info('[INTRAG %s] Saved entry deal=%r → %s', 'FXO' if is_fxo else 'OPT', deal_id, file_path)


def _maybe_save_intrag_opt(deal):
    """Save to Intrag Option when the counterparty is Banco J.P. Morgan (intragroup)."""
    cl = (deal.get('Client', '') or '').lower()
    if 'banco' in cl and 'morgan' in cl:
        try:
            _save_intrag_opt_entry(deal)
        except Exception as exc:
            _R().log.error('[INTRAG OPT] save failed for deal=%r: %s', deal.get('Deal', ''), exc)


def _maybe_save_intrag_fxo(deal):
    """Save an Opt-FXO deal to Intrag Option (shared file) when the counterparty
    is Banco J.P. Morgan (intragroup). Same logic as opt-comm with FXO overrides."""
    cl = (deal.get('Client', '') or '').lower()
    if 'banco' in cl and 'morgan' in cl:
        try:
            _save_intrag_opt_entry(deal, is_fxo=True)
        except Exception as exc:
            _R().log.error('[INTRAG FXO] save failed for deal=%r: %s', deal.get('Deal', ''), exc)


# O endereço do extrato quando o cadastro ainda não tem a linha `Intrag DCE`:
# o `athena_api.registered_link` lê o JSON CRU, e o seed novo só chega ao
# arquivo quando alguém salva a tela /mapping — sem o fallback, a instância que
# nunca salvou ficaria com o Import morto pedindo um cadastro que o seed já
# conhece (o mesmo desenho do `_ATHENA_FXO_FALLBACK` da Recon FXO).
_DCE_OPT_URL_FALLBACK = ('http://169.19.201.153:8080/bob-reports/YYYY-MM-DD/'
                         'GEM/Reports/ITAU/ITAUDataExtract_FXO/'
                         'ITAUDataExtractor_FXOption')
_DCE_API_USE = 'Intrag DCE'
_DCE_API_PRODUCT = 'FXO'


def _dce_opt_url(ref_dt):
    """Endereço do extrato do dia, do cadastro `api-links` (uso `Intrag DCE`).

    Como na Recon FXO, a data vive no CAMINHO (`AAAA-MM-DD`) — a substituição é
    do placeholder, sem reescrever query string nenhuma."""
    template = None
    try:
        from apps.pages import athena_api
        template, _ = athena_api.registered_link(_DCE_API_USE, _DCE_API_PRODUCT)
    except Exception as exc:                       # pragma: no cover - defensivo
        _R().log.debug('[INTRAG DCE OPT] cadastro api-links indisponível: %s', exc)
    if not template:
        template = _DCE_OPT_URL_FALLBACK
    return re.sub(r'yyyy[-/. ]?mm[-/. ]?dd', ref_dt.strftime('%Y-%m-%d'),
                  template, flags=re.I)


def _dce_opt_import(ref_date=None, sid='', actor_name=''):
    """Baixa o extrato DCE de FX Option do bob-reports e o materializa nos
    arquivos-dia da página Intrag › DCE › Option.

    O `ref_date` é a data do CAMINHO do bob-report (o dia do extrato); cada
    linha vai para o arquivo-dia do PRÓPRIO Trade Date, que é a chave que a
    tela e o send usam — a mesma unidade das outras páginas de Intrag. O
    re-import upserta pela chave `_deal` (Trade ID) preservando status, maker,
    checker e o Intrag ID já mapeado: importar de novo não desfaz esteira.
    """
    ref_dt = _R()._api_ref_date(ref_date)
    url = _dce_opt_url(ref_dt)
    try:
        from apps.pages import athena_api
        session = athena_api.build_session()
    except Exception:
        import requests
        session = requests.Session()
        # Mesma razão do athena_api: o proxy corporativo recusa o host interno
        # que o navegador alcança direto.
        session.trust_env = False
    resp = session.get(url, timeout=180)
    resp.raise_for_status()
    try:
        text = resp.content.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = resp.content.decode('latin-1')

    rows, unknown = domain._dce_parse_report(text)
    if unknown:
        _R().log.warning('[INTRAG DCE OPT] colunas do extrato fora do mapa (ignoradas): %s',
                         ', '.join(unknown))

    groups, skipped = {}, 0
    for row in rows:
        deal_id = row.get('trade_id') or ''
        if not deal_id:
            skipped += 1
            continue
        td = _R()._parse_date_any(row.get('trade_date')) or ref_dt
        entry = dict(row)
        entry['_deal'] = deal_id
        entry['_client'] = row.get('counterparty') or ''
        entry['status'], entry['maker'], entry['checker'] = 'New', '', ''
        groups.setdefault(td.strftime('%Y%m%d'), {'ref': td, 'rows': []})['rows'].append(entry)

    imported = 0
    for key, grp in groups.items():
        ref = grp['ref']
        dir_path = os.path.join(persistence.INTRAG_DCE_OPT_CACHE_DIR,
                                ref.strftime('%Y'), ref.strftime('%m'))
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, key + '_intrag_dce_opt.json')
        with _R()._cache_lock:
            entries = []
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as fh:
                        entries = json.load(fh)
                    if not isinstance(entries, list):
                        entries = []
                except (json.JSONDecodeError, ValueError):
                    entries = []
            for entry in grp['rows']:
                idx = next((i for i, e in enumerate(entries)
                            if e.get('_deal') == entry['_deal']), None)
                if idx is not None:
                    # Preserva a esteira e o mapeamento no re-import.
                    for k in ('status', 'maker', 'checker', 'intrag_id'):
                        if entries[idx].get(k):
                            entry[k] = entries[idx][k]
                    entries[idx] = entry
                else:
                    entries.append(entry)
                imported += 1
            _R()._atomic_write_json(file_path, entries)
        _R().log.info('[INTRAG DCE OPT] Imported %d row(s) → %s', len(grp['rows']), file_path)

    return {'success': True, 'imported': imported, 'files': len(groups),
            'skipped': skipped, 'unknown_headers': unknown,
            'ref_date': ref_dt.strftime('%Y-%m-%d')}


def _intrag_run_mapping(deals, match_col, match_val, b3_col, finder):
    """Map each requested deal's B3 ID → Intrag ID via the export CSV, persist the
    intrag_id onto the matching JSON entry (loaded rows only). Returns (results, err)."""
    csv_path = queries._intrag_find_export_csv()
    if not csv_path:
        return None, 'No Boletas CSV found in the Return folder.'
    try:
        b3map = mappers._intrag_build_b3_map(csv_path, match_col, match_val, b3_col)
    except Exception:
        _R().log.error('[intrag-map] CSV parse failed:\n%s', traceback.format_exc())
        return None, 'Failed to read the Boletas CSV.'
    results = []
    with _R()._cache_lock:
        for d in (deals or []):
            did = str(d.get('id') or '').strip()
            b3  = domain._intrag_b3_key(d.get('b3_id'))
            if not did or not b3 or b3 not in b3map:
                continue
            intrag_id = b3map[b3]
            fp, entries, idx = finder(did, None)
            if idx is None:
                results.append({'id': did, 'intrag_id': intrag_id, 'status': 'Error'})
                continue
            entries[idx]['intrag_id'] = intrag_id
            entries[idx]['status']    = 'Success'          # mapped → Success
            try:
                _R()._atomic_write_json(fp, entries)
            except Exception:
                _R().log.error('[intrag-map] save failed %s:\n%s', fp, traceback.format_exc())
                results.append({'id': did, 'intrag_id': intrag_id, 'status': 'Error'})
                continue
            results.append({'id': did, 'intrag_id': intrag_id, 'status': 'Success'})
    return results, None
