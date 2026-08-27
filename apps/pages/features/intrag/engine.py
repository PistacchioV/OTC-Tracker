# -*- coding: utf-8 -*-
"""Intrag (NDF / Option / Swap) — os day-files, o ciclo maker/checker e o
mapeamento do Intrag ID a partir do CSV de export da B3.

Movido VERBATIM do routes.py (nomes preservados). Os GRAVADORES
(`_save_intrag_ndf_entry`, `_save_intrag_ndf_moeda_entry`,
`_maybe_save_intrag_opt`, `_maybe_save_intrag_fxo`) são chamados pelos saves
do New Deals — o routes os alcança pelo gancho `_intrag_engine()` (import
atrasado), como o `record_rebooks` do mdea.
"""
import csv
import io
import json
import os
import re
import traceback
from datetime import datetime


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


INTRAG_NDF_CACHE_DIR = _R().os.path.normpath(_R().os.path.join(
    _R().data_dir(), "cache", "new deals", "Intrag", "NDF"
))

INTRAG_OPT_CACHE_DIR = _R().os.path.normpath(_R().os.path.join(
    _R().data_dir(), "cache", "new deals", "Intrag", "Option"
))

INTRAG_SWAP_CACHE_DIR = _R().os.path.normpath(_R().os.path.join(
    _R().data_dir(), "cache", "new deals", "Intrag", "Swap"
))

INTRAG_NDF_SEND_DIR = _R().os.path.join(
    _R().Config.SHARED_DRIVE_ROOT, 'Confirmation', 'Derivativos', 'OTC Tracker', 'Intrag')

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
        m = _R().re.match(r'^([A-Z]{3})(\d{2,4})$', month_raw)
        if m:
            mon_num = _R()._MONTH_ABBR.get(m.group(1), '')
            yr = m.group(2) if len(m.group(2)) == 4 else '20' + m.group(2)
            if mon_num:
                expiry_str = f'{mon_num}-{yr}'
        elif _R().re.match(r'^\d{4}-\d{2}$', month_raw):
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

    _intrag_ndf_persist(entry, td)

def _intrag_ndf_persist(entry, td):
    """Append/update uma entrada no day-file da Intrag NDF (chave = _deal)."""
    ref = td or _R().datetime.now()
    dir_path = _R().os.path.join(INTRAG_NDF_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'))
    _R().os.makedirs(dir_path, exist_ok=True)
    fname = ref.strftime('%Y%m%d') + '_intrag_ndf.json'
    file_path = _R().os.path.join(dir_path, fname)

    with _R()._cache_lock:
        if _R().os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    entries = _R().json.load(fh)
                if not isinstance(entries, list):
                    entries = []
            except (_R().json.JSONDecodeError, ValueError):
                entries = []
        else:
            entries = []
        deal_id = entry['_deal']
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            # Preserve the existing lifecycle state on re-save — only the very
            # first time an entry lands in the JSON does it start as 'New'.
            entry['status']  = entries[idx].get('status') or 'New'
            entry['maker']   = entries[idx].get('maker', '')
            entry['checker'] = entries[idx].get('checker', '')
            entries[idx] = entry
        else:
            entries.append(entry)
        _R()._atomic_write_json(file_path, entries)
    _R().log.info('[INTRAG NDF] Saved entry deal=%r → %s', deal_id, file_path)

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
    # No template o publisher sai com espaços ("PTAX USB WMR 4"), não pipes.
    publisher = (deal.get('Publisher', '') or 'PTAX').replace('|', ' ').strip() or 'PTAX'

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
    _intrag_ndf_persist(entry, td)

_INTRAG_OPT_JPM_ACC    = '73760.00-9'

_INTRAG_OPT_LAWTON_ACC = '00041.00-7'

_INTRAG_OPT_JPM_NAME    = 'BANCO J.P MORGAN S.A'

_INTRAG_OPT_LAWTON_NAME = 'LAWTON MULTIMERCADO-FI'

def _intrag_opt_name_for(acc):
    if acc == _INTRAG_OPT_JPM_ACC:
        return _INTRAG_OPT_JPM_NAME
    if acc == _INTRAG_OPT_LAWTON_ACC:
        return _INTRAG_OPT_LAWTON_NAME
    return ''

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
        buyer_account = _INTRAG_OPT_LAWTON_ACC
    elif direction == 'SELL':
        buyer_account = _INTRAG_OPT_JPM_ACC
    else:
        buyer_account = ''
    buyer_name = _intrag_opt_name_for(buyer_account)
    # Seller is the inverse account/name of the buyer.
    if buyer_account == _INTRAG_OPT_JPM_ACC:
        seller_account = _INTRAG_OPT_LAWTON_ACC
    elif buyer_account == _INTRAG_OPT_LAWTON_ACC:
        seller_account = _INTRAG_OPT_JPM_ACC
    else:
        seller_account = ''
    seller_name = _intrag_opt_name_for(seller_account)

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

    ref = td or _R().datetime.now()
    dir_path = _R().os.path.join(INTRAG_OPT_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'))
    _R().os.makedirs(dir_path, exist_ok=True)
    fname = ref.strftime('%Y%m%d') + '_intrag_opt.json'
    file_path = _R().os.path.join(dir_path, fname)

    with _R()._cache_lock:
        if _R().os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    entries = _R().json.load(fh)
                if not isinstance(entries, list):
                    entries = []
            except (_R().json.JSONDecodeError, ValueError):
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

def _find_intrag_ndf_entry(deal_id, trade_date):
    """Locate an Intrag NDF entry by deal id (+ optional trade date to narrow the
    daily file). Returns (file_path, entries_list, idx) or (None, None, None)."""
    if not deal_id:
        return None, None, None
    ref = _R()._parse_date_any(trade_date) if trade_date else None
    candidate_files = []
    if ref is not None:
        fp = _R().os.path.join(
            INTRAG_NDF_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
            ref.strftime('%Y%m%d') + '_intrag_ndf.json'
        )
        if _R().os.path.isfile(fp):
            candidate_files.append(fp)
    if not candidate_files and _R().os.path.isdir(INTRAG_NDF_CACHE_DIR):
        for root, _, files in _R().os.walk(INTRAG_NDF_CACHE_DIR):
            for fname in files:
                if fname.endswith('_intrag_ndf.json'):
                    candidate_files.append(_R().os.path.join(root, fname))
    for fp in candidate_files:
        try:
            with open(fp, 'r', encoding='utf-8') as fh:
                entries = _R().json.load(fh)
            if not isinstance(entries, list):
                continue
        except (_R().json.JSONDecodeError, ValueError, OSError):
            continue
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            return fp, entries, idx
    return None, None, None

def _find_intrag_opt_entry(deal_id, trade_date):
    """Locate an Intrag Option entry by deal id (+ optional trade date)."""
    if not deal_id:
        return None, None, None
    ref = _R()._parse_date_any(trade_date) if trade_date else None
    candidate_files = []
    if ref is not None:
        fp = _R().os.path.join(INTRAG_OPT_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
                          ref.strftime('%Y%m%d') + '_intrag_opt.json')
        if _R().os.path.isfile(fp):
            candidate_files.append(fp)
    if not candidate_files and _R().os.path.isdir(INTRAG_OPT_CACHE_DIR):
        for root, _, files in _R().os.walk(INTRAG_OPT_CACHE_DIR):
            for fname in files:
                if fname.endswith('_intrag_opt.json'):
                    candidate_files.append(_R().os.path.join(root, fname))
    for fp in candidate_files:
        try:
            with open(fp, 'r', encoding='utf-8') as fh:
                entries = _R().json.load(fh)
            if not isinstance(entries, list):
                continue
        except (_R().json.JSONDecodeError, ValueError, OSError):
            continue
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            return fp, entries, idx
    return None, None, None

def _intrag_b3_key(v):
    """B3 ID match key — stripped, leading zeros dropped (both sides)."""
    s = str(v or '').strip()
    return s.lstrip('0') or s

def _intrag_find_export_csv():
    """Most recent Boletas*.csv in the Return folder, or None."""
    try:
        cands = [_R().os.path.join(_R().RETURN_PATH, fn) for fn in _R().os.listdir(_R().RETURN_PATH)
                 if fn.lower().startswith('boletas') and fn.lower().endswith('.csv')]
    except OSError:
        return None
    cands = [p for p in cands if _R().os.path.isfile(p)]
    return max(cands, key=lambda p: _R().os.path.getmtime(p)) if cands else None

def _intrag_build_b3_map(csv_path, match_col, match_val, b3_col):
    """Parse the Boletas CSV (no header) → {b3_key → Intrag ID (col A)} for rows whose
    `match_col` equals `match_val`."""
    import csv as _csv
    out = {}
    with open(csv_path, 'r', encoding='latin-1', newline='') as fh:
        sample = fh.read(4096); fh.seek(0)
        delim = ';' if sample.count(';') > sample.count(',') else ','
        for row in _csv.reader(fh, delimiter=delim):
            if len(row) <= max(match_col, b3_col):
                continue
            if str(row[match_col]).strip().upper() != match_val:
                continue
            b3, intrag_id = _intrag_b3_key(row[b3_col]), str(row[0]).strip()
            if b3 and intrag_id:
                out.setdefault(b3, intrag_id)
    return out

def _intrag_run_mapping(deals, match_col, match_val, b3_col, finder):
    """Map each requested deal's B3 ID → Intrag ID via the export CSV, persist the
    intrag_id onto the matching JSON entry (loaded rows only). Returns (results, err)."""
    csv_path = _intrag_find_export_csv()
    if not csv_path:
        return None, 'No Boletas CSV found in the Return folder.'
    try:
        b3map = _intrag_build_b3_map(csv_path, match_col, match_val, b3_col)
    except Exception:
        _R().log.error('[intrag-map] CSV parse failed:\n%s', _R().traceback.format_exc())
        return None, 'Failed to read the Boletas CSV.'
    results = []
    with _R()._cache_lock:
        for d in (deals or []):
            did = str(d.get('id') or '').strip()
            b3  = _intrag_b3_key(d.get('b3_id'))
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
                _R().log.error('[intrag-map] save failed %s:\n%s', fp, _R().traceback.format_exc())
                results.append({'id': did, 'intrag_id': intrag_id, 'status': 'Error'})
                continue
            results.append({'id': did, 'intrag_id': intrag_id, 'status': 'Success'})
    return results, None

def _find_intrag_swap_entry(deal_id, trade_date):
    """Locate an Intrag Swap entry by deal id (+ optional start date to narrow
    the daily file). Returns (file_path, entries_list, idx) or (None, None, None)."""
    if not deal_id:
        return None, None, None
    ref = _R()._parse_date_any(trade_date) if trade_date else None
    candidate_files = []
    if ref is not None:
        fp = _R().os.path.join(
            INTRAG_SWAP_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
            ref.strftime('%Y%m%d') + '_intrag_swap.json'
        )
        if _R().os.path.isfile(fp):
            candidate_files.append(fp)
    if not candidate_files and _R().os.path.isdir(INTRAG_SWAP_CACHE_DIR):
        for root, _, files in _R().os.walk(INTRAG_SWAP_CACHE_DIR):
            for fname in files:
                if fname.endswith('_intrag_swap.json'):
                    candidate_files.append(_R().os.path.join(root, fname))
    for fp in candidate_files:
        try:
            with open(fp, 'r', encoding='utf-8') as fh:
                entries = _R().json.load(fh)
            if not isinstance(entries, list):
                continue
        except (_R().json.JSONDecodeError, ValueError, OSError):
            continue
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            return fp, entries, idx
    return None, None, None
