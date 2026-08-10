#!/usr/bin/env python3
"""check_fi_ter.py — TER (Termo Multiclasses) pelo motor do File Interface.

Prova que a troca da montagem hardcoded pelos templates do cadastro
(`_fi_build_line('termo-multiclasses', ...)`) não mudou UM byte dos arquivos
que vão para a B3. As funções `_legacy_*` abaixo são cópias autocontidas da
lógica ANTIGA (goldens capturados antes da refatoração) — cobrem FWD Start,
Other Publisher e NDF Commodities, deal com e sem janela de fixing (linhas
tipo 2) e campos vazios. Também prova que editar um literal Fixed no cadastro
muda a linha (o cadastro é a autoridade), usando um template em tempfile —
o JSON versionado não é tocado.
"""
import json
import os
import random
import re
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R  # noqa: E402

FAILS = []


def check(name, cond, extra=''):
    if cond:
        print('  ok    ' + name)
    else:
        print(' FAIL   ' + name + (' — ' + extra if extra else ''))
        FAILS.append(name)


# ───────────────────────────────────────────────────────────────────────────
# GOLDENS — cópias autocontidas da montagem ANTIGA (pré-refatoração)
# ───────────────────────────────────────────────────────────────────────────

def _lg_s(v):
    return re.sub(r'<[^>]+>', '', str(v or '')).strip()


def _lg_pos(s, width, align='left', fill=' '):
    s = str(s or '')[:width]
    return s.rjust(width, fill) if align == 'right' else s.ljust(width, fill)


def _legacy_generic_line(deal, is_fwd):
    """Golden: linha tipo 1 do api_generic_nd_send_conecta ANTES do motor."""
    _s, _pos = _lg_s, _lg_pos

    def _znum(val, int_digits, dec_digits):
        try:
            from decimal import Decimal
            d = abs(Decimal(str(val).replace(',', '')))
            ip = int(d)
            fp = int(((d - ip) * (10 ** dec_digits)).to_integral_value())
            return str(ip).zfill(int_digits) + str(fp).zfill(dec_digits)
        except Exception:
            return '0' * (int_digits + dec_digits)

    def _d8(v):
        dt = R._parse_date_any(_s(v))
        return dt.strftime('%Y%m%d') if dt else ''

    def _is_jpm(c):
        return bool(re.search(r'J\.?P\.?\s*MORGAN', c.upper()))

    def _is_mgt(c):
        return 'MGT' in c.upper()

    def _is_lawton(c):
        return 'LAWTON' in c.upper()

    if str(deal.get('Status', '') or '').strip() == 'Canceled':
        return None
    client   = _s(deal.get('Client', ''))
    le       = _s(deal.get('LE', '')).upper()
    deal_id  = _s(deal.get('Deal', ''))
    publisher = _s(deal.get('Publisher', ''))
    qty_ccy  = _s(deal.get('QuantityCurrency', '')).upper()
    oth_ccy  = _s(deal.get('OtherQuantityCurrency', '')).upper()

    if 'LAWTON' in le:
        bucket, participant, cpty = 'LAWTON', '00041007', '73760009'
    elif _is_jpm(client):
        bucket, participant = 'LAWTON', '00041007'
        cpty = '04880006' if le == 'MGT' else '73760009'
    else:
        bucket = 'MGT' if le == 'MGT' else 'BANCO'
        participant = '04880006' if le == 'MGT' else '73760009'
        if _is_lawton(client):
            cpty = '00041007'
        elif le == 'MGT':
            cpty = '73760009' if _is_jpm(client) else '04880109'
        else:
            cpty = '04880006' if _is_mgt(client) else '73760102'
    taxid = '' if ('LAWTON' in le or _is_jpm(client) or _is_lawton(client) or _is_mgt(client)) \
        else re.sub(r'[.\-\/]', '', _s(deal.get('TaxID', '')))

    last_fix_dt = R._parse_date_any(_s(deal.get('LastFixingDate', '')))
    settl_dt    = R._parse_date_any(_s(deal.get('SettlementDate', '')))
    biz_diff    = R._anbima_biz_diff(last_fix_dt, settl_dt)

    strike_set_dt = R._parse_date_any(_s(deal.get('StrikeSetDate', '')))
    fixacao_dt    = R._anbima_add_biz(strike_set_dt, biz_diff) if strike_set_dt else None

    fonte_info = R._ndf_publisher_fonte_info(publisher)
    boletim    = ('3' if fonte_info.strip() == '0' else '1') if is_fwd else ' '

    notional_s = (_s(deal.get('TotalNotional', '')) or _s(deal.get('Notional', ''))).replace(' ', '')
    if ',' in notional_s and '.' in notional_s:
        notional_s = (notional_s.replace('.', '').replace(',', '.')
                      if notional_s.rfind(',') > notional_s.rfind('.')
                      else notional_s.replace(',', ''))
    elif notional_s.count('.') > 1:
        notional_s = notional_s.replace('.', '')
    else:
        notional_s = notional_s.replace(',', '')
    try:
        qty_int = int(round(float(notional_s)))
        qty_str = str(qty_int).rjust(14, '0') + '00'
    except Exception:
        qty_str = '0' * 16

    fix_start = _d8(deal.get('FirstFixingDate', ''))
    fix_end   = _d8(deal.get('LastFixingDate', ''))
    asian_fix  = bool(fix_start and fix_end and fix_start != fix_end)
    fix_single = '' if asian_fix else (fix_end or fix_start)
    if not is_fwd:
        fix_single = ''
    tipo_media = 'A' if asian_fix else 'N'

    if is_fwd:
        taxa_termo   = _pos('', 20)
        cot_venc     = str(biz_diff)[:1] or '0'
        fonte_cons   = ''
        tela_cons    = ''
        cot_rs_usd   = ''
        cot_paridade = ''
        data_aval    = ''
        termo_flag   = 'S'
        forma_atu    = 'V'
        valor_perc   = _znum(_s(deal.get('StrikeSetOffset', '')) or '0', 4, 8)
    else:
        rate_raw = R._fxo_num(_s(deal.get('Rate', '')))
        _inv = R._mapping_ccy_maps()[2]
        if rate_raw and qty_ccy in _inv:
            rate_val = round(1.0 / rate_raw, _inv[qty_ccy])
        else:
            rate_val = rate_raw
        taxa_termo   = _znum(rate_val if rate_val is not None else '0', 12, 8)
        cot_venc     = ' '
        pub = R._ndf_publisher_codes(publisher)
        fonte_cons   = pub.get('consulta', '')
        tela_cons    = pub.get('info', '')
        cot_rs_usd   = '1'
        cot_paridade = '3'
        data_aval    = _d8(deal.get('LastFixingDate', ''))
        termo_flag   = 'N'
        forma_atu    = ' '
        valor_perc   = (_znum(_s(deal.get('StrikeSetOffset', '')), 4, 8)
                        if _s(deal.get('StrikeSetOffset', '')) else _pos('', 12))

    dir_code = '0' if _s(deal.get('Direction', '')).upper() == 'BUY' else '1'
    my_number = str(random.randint(1000000000, 9999999999))

    brl_fixed = (not is_fwd) and _s(deal.get('IsBRRFixed', '')).upper() == 'YES'
    moeda_ref, moeda_cot = (oth_ccy, qty_ccy) if brl_fixed else (qty_ccy, oth_ccy)

    line = (
        _pos('TER  ', 5)                         +
        _pos('1', 1)                             +
        _pos('0001', 4)                          +
        _pos(my_number, 10)                      +
        _pos(participant, 8)                     +
        _pos(dir_code, 1)                        +
        _pos('', 14)                             +
        _pos(cpty, 8)                            +
        _pos(taxid, 14)                          +
        _pos('S', 1)                             +
        _pos('2', 20, 'right')                   +
        _pos(fonte_info, 4)                      +
        _pos(R._moeda_num_code(moeda_ref), 3)    +
        _pos(R._moeda_num_code(moeda_cot), 3)    +
        _pos(cot_venc, 1)                        +
        _pos(qty_str, 16)                        +
        _pos('', 10)                             +
        _pos(taxa_termo, 20)                     +
        _pos(fix_single, 8)                      +
        _pos(_d8(deal.get('TradeDate', '')), 8)  +
        _pos(_d8(deal.get('SettlementDate', '')), 8) +
        _pos(boletim, 1)                         +
        _pos(' ', 1)                             +
        _pos('', 8)                              +
        _pos('', 1)                              +
        _pos(fonte_cons, 1)                      +
        _pos(tela_cons, 8, 'right')              +
        _pos('', 8)                              +
        _pos('', 8)                              +
        _pos(cot_rs_usd, 1)                      +
        _pos(cot_paridade, 1)                    +
        _pos(data_aval, 8)                       +
        _pos('', 10)                             +
        _pos('', 8)                              +
        _pos(termo_flag, 1)                      +
        _pos(fixacao_dt.strftime('%Y%m%d') if fixacao_dt else '', 8) +
        _pos(forma_atu, 1)                       +
        _pos(valor_perc, 12)                     +
        _pos((str(biz_diff)[:1] or '0') if is_fwd else ' ', 1) +
        _pos('N', 1)                             +
        _pos('', 12)                             +
        _pos('N', 1)                             +
        _pos('', 1)                              +
        _pos('', 8)                              +
        _pos('', 8)                              +
        _pos('', 1)                              +
        _pos('', 14)                             +
        _pos('', 14)                             +
        _pos('', 8)                              +
        _pos('', 1)                              +
        _pos('', 16)                             +
        _pos('', 1)                              +
        _pos('', 1)                              +
        _pos('', 8)                              +
        _pos('S' if _s(deal.get('IsBRRFixed', '')).upper() == 'YES' else '', 1) +
        _pos('', 280)                            +
        _pos(deal_id[-14:], 14, 'right')         +
        _pos(tipo_media, 1)                      +
        _pos(str(R._anbima_biz_diff(
            R._parse_date_any(_s(deal.get('FirstFixingDate', ''))),
            R._parse_date_any(_s(deal.get('LastFixingDate', ''))))
            + 1).zfill(3) if asian_fix else '000', 3)
    )
    return bucket, line


def _legacy_generic_headers(today):
    _pos = _lg_pos
    return {
        'BANCO':  _pos('TER  ', 5) + '0' + '0001' + 'JPMORGANBM' + ' ' * 10 + today + '00003',
        'LAWTON': _pos('TER  ', 5) + '0' + '0001' + 'INTRAGLAWTONFDO' + ' ' * 5 + today + '00003',
        'MGT':    _pos('TER  ', 5) + '0' + '0001' + 'MORGANBC' + ' ' * 12 + today + '00003',
    }


def _legacy_comm_lines(deal):
    """Golden: linhas tipo 1 + tipo 2 do api_ndf_send_conecta ANTES do motor."""
    from decimal import Decimal
    import datetime as _dt

    def _sh(v):
        return re.sub(r'<[^>]+>', '', str(v or '')).strip()

    def _date(val):
        val = _sh(val)
        if not val:
            return ''
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                return _dt.datetime.strptime(val, fmt).strftime('%Y%m%d')
            except ValueError:
                continue
        return ''

    def _cpty(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '00041007'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '73760009'
        return '73760102'

    def _taxid(client, taxid):
        c = client.upper()
        if 'LAWTON' in c or 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return ''
        return re.sub(r'[.\-/]', '', _sh(taxid))

    def _pos(s, width, align='left', fill=' '):
        s = str(s or '')
        if len(s) > width:
            s = s[:width]
        return s.rjust(width, fill) if align == 'right' else s.ljust(width, fill)

    def _pos_num(val, int_digits, dec_digits, div100=False):
        v = _sh(str(val or ''))
        if not v:
            return '0' * (int_digits + dec_digits)
        try:
            d = Decimal(v.replace(',', ''))
            if div100:
                d = d / Decimal('100')
            d = abs(d)
            int_part = int(d)
            frac_int = int(((d - int_part) * Decimal(10 ** dec_digits)).to_integral_value())
            return str(int_part).zfill(int_digits) + str(frac_int).zfill(dec_digits)
        except Exception:
            return '0' * (int_digits + dec_digits)

    client           = _sh(deal.get('Client', ''))
    taxid            = _sh(deal.get('TaxID', ''))
    direction        = _sh(deal.get('Direction', ''))
    trade_type       = _sh(deal.get('TradeType', '')).upper()
    strike_ccy       = _sh(deal.get('StrikeCurrency', '')).upper()
    underlying       = _sh(deal.get('UnderlyingAsset', '')).upper()
    instrument       = _sh(deal.get('Instrument', '')).upper()
    _cu              = client.upper()
    is_jpmorgan      = bool(re.search(r'J\.?P\.?\s*MORGAN', _cu))
    part_account     = '00041007' if is_jpmorgan else '73760009'
    fx_holiday_sched = _sh(deal.get('FXHolidaySchedule', ''))
    qic              = _sh(deal.get('QuotedInCents', 'NO')).upper() == 'YES'
    asian            = trade_type == 'ASIAN'
    vanilla          = trade_type == 'VANILLA'
    brl              = strike_ccy == 'BRL'
    is_tas           = instrument.startswith('TAS')

    dir_code   = '0' if direction.upper() == 'BUY' else '1'
    fix_start  = _date(deal.get('FixingStartDate', ''))
    fix_end    = _date(deal.get('FixingEndDate', ''))
    fxconv     = _date(deal.get('FXConvDate', ''))
    trade_date = _date(deal.get('TradeDate', ''))
    settl_date = _date(deal.get('SettlementDate', ''))
    deal_id    = _sh(deal.get('Deal', ''))
    notional   = _sh(deal.get('TotalNotional', ''))
    strike_str = _pos_num(deal.get('Strike', ''), 12, 8, div100=qic)

    try:
        qty_int = int(round(float(notional.replace(',', ''))))
        qty_str = str(qty_int).rjust(14, '0') + '00'
    except Exception:
        qty_str = '0' * 16

    _q           = R._b3_quote_cfg(underlying)
    tipo_cotacao = _q['ndf']
    fonte_info   = _q['source']

    fix_single = fix_start if (fix_start and fix_start == fix_end) else ''
    tipo_media = 'N' if fix_single else 'A'

    _deal_holidays = set()
    if not vanilla and fx_holiday_sched:
        _sched_file = re.sub(r'[^A-Za-z0-9_]', '', fx_holiday_sched.replace('-', '_'))
        holiday_path = os.path.join(
            ROOT, 'apps', 'static', 'data', f'{_sched_file}.json'
        ) if _sched_file else None
        try:
            with open(holiday_path, encoding='utf-8') as _hf:
                _raw = json.load(_hf)
            _deal_holidays = set(
                item['date'] if isinstance(item, dict) else item
                for item in _raw
            )
        except Exception:
            pass

    biz_count = 0
    if not vanilla and fix_start and fix_end:
        try:
            _s = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
            _e = _dt.datetime.strptime(fix_end,   '%Y%m%d').date()
            _cur = _s
            while _cur <= _e:
                if _cur.weekday() < 5 and _cur.strftime('%Y-%m-%d') not in _deal_holidays:
                    biz_count += 1
                _cur += _dt.timedelta(days=1)
        except Exception:
            pass

    if vanilla:
        biz_str = '000'
    else:
        biz_str = str(biz_count).zfill(3)
    my_number = str(random.randint(1000000000, 9999999999))

    line = (
        _pos('TER  ', 5)                        +
        _pos('1', 1)                             +
        _pos('0001', 4)                          +
        _pos(my_number, 10)                      +
        _pos(part_account, 8)                    +
        _pos(dir_code, 1)                        +
        _pos('', 14)                             +
        _pos(_cpty(client), 8)                   +
        _pos(_taxid(client, taxid), 14)          +
        _pos('S', 1)                             +
        _pos('4', 20, 'right')                   +
        _pos(' ' + fonte_info, 4)                +
        _pos('', 3)                              +
        _pos('', 3)                              +
        _pos('', 1)                              +
        _pos(qty_str, 16)                        +
        _pos(underlying, 10, 'right')            +
        _pos(strike_str, 20)                     +
        _pos(fix_single, 8)                      +
        _pos(trade_date, 8)                      +
        _pos(settl_date, 8)                      +
        _pos('', 1)                              +
        _pos(tipo_cotacao, 1)                    +
        _pos('' if brl else fxconv, 8)           +
        _pos('', 1)                              +
        _pos('', 1)                              +
        _pos('', 8)                              +
        _pos('', 8)                              +
        _pos('', 8)                              +
        _pos('', 1)                              +
        _pos('', 1)                              +
        _pos('', 8)                              +
        _pos('', 10)                             +
        _pos('', 8)                              +
        _pos('S' if is_tas else 'N', 1)          +
        _pos(trade_date if is_tas else '', 8)    +
        _pos('V' if is_tas else '', 1)           +
        _pos('', 12)                             +
        _pos('', 1)                              +
        _pos('N', 1)                             +
        _pos('', 12)                             +
        _pos('N', 1)                             +
        _pos('', 1)                              +
        _pos('', 8)                              +
        _pos('', 8)                              +
        _pos('', 1)                              +
        _pos('', 14)                             +
        _pos('', 14)                             +
        _pos('', 8)                              +
        _pos('', 1)                              +
        _pos('', 16)                             +
        _pos('', 1)                              +
        _pos('', 1)                              +
        _pos('', 8)                              +
        _pos('S' if brl else '', 1)              +
        _pos('', 280)                            +
        _pos(deal_id, 14, 'right')               +
        _pos(tipo_media, 1)                      +
        _pos(biz_str, 3)
    )
    lines = [line]

    if asian and fix_start and fix_end:
        try:
            _s2 = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
            _e2 = _dt.datetime.strptime(fix_end,   '%Y%m%d').date()
            _cur2 = _s2
            while _cur2 <= _e2:
                if _cur2.weekday() < 5 and _cur2.strftime('%Y-%m-%d') not in _deal_holidays:
                    _d  = _cur2.strftime('%Y%m%d')
                    _fx = _d if brl else ''
                    fix_line = (
                        _pos('TER  ', 5)   +
                        _pos('2', 1)        +
                        _pos('0001', 4)     +
                        _pos(_d, 8)         +
                        _pos('0' * 16, 16)  +
                        _pos(_fx, 8)        +
                        _pos('', 10)
                    )
                    lines.append(fix_line)
                _cur2 += _dt.timedelta(days=1)
        except Exception:
            pass
    return is_jpmorgan, lines


def _legacy_comm_headers(today):
    _pos = _lg_pos
    return {
        'LAWTON': (_pos('TER  ', 5) + _pos('0', 1) + _pos('0001', 4) +
                   'INTRAGLAWTONFDO' + '     ' + today + '00003'),
        'BANCO':  (_pos('TER  ', 5) + _pos('0', 1) + _pos('0001', 4) +
                   'JPMORGANBM' + '          ' + today + '00003'),
    }


# ───────────────────────────────────────────────────────────────────────────
# Deals sintéticos — os ramos relevantes de cada gerador
# ───────────────────────────────────────────────────────────────────────────

GENERIC_DEALS = {
    'fwdstart asiático (janela de fixing)': dict(
        Deal='FWDS-2026-000123456', Client='ACME EXPORTADORA S.A.', LE='JPM',
        Status='Success', Direction='BUY', TaxID='12.345.678/0001-90',
        TradeDate='2026-08-03', SettlementDate='2026-09-15',
        FirstFixingDate='2026-09-01', LastFixingDate='2026-09-10',
        StrikeSetDate='2026-08-20', StrikeSetOffset='0.05',
        Publisher='PTAX', QuantityCurrency='USD', OtherQuantityCurrency='BRL',
        Notional='5,158,000.00', IsBRRFixed='NO'),
    'fwdstart fixing único (sem first fixing)': dict(
        Deal='FWDS-77', Client='BANCO SAFRA S.A.', LE='JPM',
        Status='Success', Direction='SELL', TaxID='58.160.789/0001-28',
        TradeDate='2026-08-03', SettlementDate='2026-10-01',
        FirstFixingDate='', LastFixingDate='2026-09-29',
        StrikeSetDate='', StrikeSetOffset='',
        Publisher='', QuantityCurrency='USD', OtherQuantityCurrency='BRL',
        Notional='1000000', IsBRRFixed='NO'),
    'fwdstart perna Lawton (client JPM)': dict(
        Deal='FWDS-LAW-1', Client='BANCO J.P. MORGAN S.A.', LE='JPM',
        Status='Success', Direction='BUY', TaxID='',
        TradeDate='2026-08-04', SettlementDate='2026-09-04',
        FirstFixingDate='', LastFixingDate='2026-09-02',
        StrikeSetDate='2026-08-15', StrikeSetOffset='',
        Publisher='PTAX', QuantityCurrency='USD', OtherQuantityCurrency='BRL',
        Notional='250000.00', IsBRRFixed='NO'),
    'fwdstart LE MGT': dict(
        Deal='FWDS-MGT-9', Client='CLIENTE MGT LTDA', LE='MGT',
        Status='Success', Direction='SELL', TaxID='11.222.333/0001-44',
        TradeDate='2026-08-04', SettlementDate='2026-11-16',
        FirstFixingDate='2026-11-03', LastFixingDate='2026-11-12',
        StrikeSetDate='2026-08-28', StrikeSetOffset='1.25',
        Publisher='PTAX', QuantityCurrency='USD', OtherQuantityCurrency='BRL',
        Notional='750000', IsBRRFixed='NO'),
    'otherpublisher com rate e BRR fixed': dict(
        Deal='OTHP-2026-42', Client='MONDELEZ BRASIL LTDA', LE='JPM',
        Status='Success', Direction='BUY', TaxID='33.033.028/0001-84',
        TradeDate='2026-08-03', SettlementDate='2026-09-30',
        FirstFixingDate='', LastFixingDate='2026-09-28',
        StrikeSetDate='', StrikeSetOffset='',
        Publisher='PTAX|BRR|PTAX', QuantityCurrency='USD',
        OtherQuantityCurrency='BRL', Notional='3,000,000.00',
        Rate='5.43210000', IsBRRFixed='YES'),
    'otherpublisher campos vazios': dict(
        Deal='OTHP-EMPTY', Client='EMPRESA VAZIA S.A.', LE='',
        Status='Success', Direction='', TaxID='',
        TradeDate='', SettlementDate='', FirstFixingDate='',
        LastFixingDate='', StrikeSetDate='', StrikeSetOffset='',
        Publisher='', QuantityCurrency='', OtherQuantityCurrency='',
        Notional='', Rate='', IsBRRFixed=''),
    'otherpublisher janela asiática': dict(
        Deal='OTHP-ASIAN-5', Client='ATACAMA COMERCIO LTDA', LE='JPM',
        Status='Success', Direction='SELL', TaxID='44.555.666/0001-77',
        TradeDate='2026-08-05', SettlementDate='2026-12-15',
        FirstFixingDate='2026-12-01', LastFixingDate='2026-12-10',
        StrikeSetDate='', StrikeSetOffset='',
        Publisher='PTAX|USB|WMR|4', QuantityCurrency='USD',
        OtherQuantityCurrency='BRL', Notional='980000.50',
        Rate='5.10', IsBRRFixed='NO'),
}

COMM_DEALS = {
    'commodities vanilla fixing único': dict(
        Deal='TCO-2026-1', Client='USINA BOA VISTA S.A.',
        TaxID='55.666.777/0001-88', Direction='BUY', TradeType='VANILLA',
        StrikeCurrency='USD', UnderlyingAsset='BRT_IPE', Instrument='FWD BRENT',
        FXHolidaySchedule='', QuotedInCents='NO',
        FixingStartDate='2026-09-10', FixingEndDate='2026-09-10',
        FXConvDate='2026-09-11', TradeDate='2026-08-03',
        SettlementDate='2026-09-15', TotalNotional='10,000',
        Strike='72.55'),
    'commodities asiático BRL (linhas tipo 2 com fx)': dict(
        Deal='TCO-2026-2', Client='COOPERATIVA AGRO LTDA',
        TaxID='66.777.888/0001-99', Direction='SELL', TradeType='ASIAN',
        StrikeCurrency='BRL', UnderlyingAsset='SOJA', Instrument='FWD SOY',
        FXHolidaySchedule='', QuotedInCents='YES',
        FixingStartDate='2026-09-01', FixingEndDate='2026-09-10',
        FXConvDate='2026-09-11', TradeDate='2026-08-03',
        SettlementDate='2026-09-15', TotalNotional='5000',
        Strike='1234.56'),
    'commodities asiático USD (tipo 2 sem fx)': dict(
        Deal='TCO-2026-3', Client='BANCO J.P. MORGAN S.A.',
        TaxID='', Direction='BUY', TradeType='ASIAN',
        StrikeCurrency='USD', UnderlyingAsset='ALUMINIO', Instrument='TAS ALUM',
        FXHolidaySchedule='', QuotedInCents='NO',
        FixingStartDate='2026-10-05', FixingEndDate='2026-10-09',
        FXConvDate='2026-10-12', TradeDate='2026-08-04',
        SettlementDate='2026-10-15', TotalNotional='2500.00',
        Strike='2380.25'),
    'commodities campos vazios': dict(
        Deal='', Client='', TaxID='', Direction='', TradeType='',
        StrikeCurrency='', UnderlyingAsset='', Instrument='',
        FXHolidaySchedule='', QuotedInCents='', FixingStartDate='',
        FixingEndDate='', FXConvDate='', TradeDate='', SettlementDate='',
        TotalNotional='', Strike=''),
}


def main():
    today = '20260810'

    # ── Generic NDF (FWD Start / Other Publisher) ──────────────────────────
    for name, deal in GENERIC_DEALS.items():
        is_fwd = name.startswith('fwdstart')
        random.seed(4321)
        legacy = _legacy_generic_line(dict(deal), is_fwd)
        random.seed(4321)
        new = R._generic_ndf_ter_line(dict(deal), is_fwd)
        check(name + ': bucket', legacy[0] == new[0],
              '{!r} != {!r}'.format(legacy[0], new[0]))
        check(name + ': linha == golden', legacy[1] == new[1],
              _first_diff(legacy[1], new[1]))
        check(name + ': largura 648', len(new[1]) == 648, str(len(new[1])))

    # deal cancelado fica fora do arquivo, como antes
    canc = dict(GENERIC_DEALS['fwdstart fixing único (sem first fixing)'])
    canc['Status'] = 'Canceled'
    check('generic: deal Canceled devolve None', R._generic_ndf_ter_line(canc, True) is None)

    # headers dos três arquivos
    legacy_h = _legacy_generic_headers(today)
    for bucket in ('BANCO', 'LAWTON', 'MGT'):
        got = R._ter_file_header(R._TER_PARTICIPANT_NAME[bucket], today,
                                 '/new_deals-ndf-fwdstart')
        check('generic header ' + bucket + ' == golden', got == legacy_h[bucket],
              _first_diff(legacy_h[bucket], got))

    # ── NDF Commodities ────────────────────────────────────────────────────
    for name, deal in COMM_DEALS.items():
        random.seed(99)
        leg_jpm, leg_lines = _legacy_comm_lines(dict(deal))
        random.seed(99)
        new_jpm, new_lines = R._ndf_comm_ter_lines(dict(deal))
        check(name + ': destino (Lawton × Banco)', leg_jpm == new_jpm)
        check(name + ': nº de linhas (tipo 1 + tipo 2)',
              len(leg_lines) == len(new_lines),
              '{} != {}'.format(len(leg_lines), len(new_lines)))
        for i, (a, b) in enumerate(zip(leg_lines, new_lines)):
            check(name + ': linha {} == golden'.format(i), a == b, _first_diff(a, b))
        check(name + ': tipo 1 com 648 chars', len(new_lines[0]) == 648,
              str(len(new_lines[0])))
        if len(new_lines) > 1:
            check(name + ': tipo 2 com 52 chars',
                  all(len(l) == 52 for l in new_lines[1:]),
                  str([len(l) for l in new_lines[1:]]))

    # o asiático emite mesmo as linhas tipo 2 (sem elas o teste acima passaria
    # trivialmente com listas de 1 linha)
    random.seed(99)
    _, _asian_lines = R._ndf_comm_ter_lines(dict(COMM_DEALS['commodities asiático BRL (linhas tipo 2 com fx)']))
    check('commodities asiático: emite linhas tipo 2', len(_asian_lines) > 1,
          str(len(_asian_lines)))

    legacy_ch = _legacy_comm_headers(today)
    for kind, participant in (('LAWTON', 'INTRAGLAWTONFDO'), ('BANCO', 'JPMORGANBM')):
        got = R._ter_file_header(participant, today, '/new_deals-ndf-commodities')
        check('commodities header ' + kind + ' == golden', got == legacy_ch[kind],
              _first_diff(legacy_ch[kind], got))

    # ── Editar um Fixed no cadastro muda a linha ───────────────────────────
    tmp = tempfile.mkdtemp(prefix='fi-ter-')
    src = os.path.join(ROOT, 'apps', 'static', 'data', 'file-interface',
                       'termo-multiclasses.json')
    try:
        with open(src, encoding='utf-8') as fh:
            tpl = json.load(fh)
        for b in tpl['blocks']:
            if b['id'] == 'registro-dados-fixos':
                for f in b['fields']:
                    if f['seq'] == '10':          # Contrato Global: 'S' → 'X'
                        f['source_detail'] = 'X'
        with open(os.path.join(tmp, 'termo-multiclasses.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(tpl, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        old_dir = R._FILE_INTERFACE_DIR
        R._FILE_INTERFACE_DIR = tmp
        R._fi_tpl_cache.clear()
        try:
            random.seed(4321)
            edited = R._generic_ndf_ter_line(
                dict(GENERIC_DEALS['fwdstart asiático (janela de fixing)']), True)[1]
        finally:
            R._FILE_INTERFACE_DIR = old_dir
            R._fi_tpl_cache.clear()
        random.seed(4321)
        base = R._generic_ndf_ter_line(
            dict(GENERIC_DEALS['fwdstart asiático (janela de fixing)']), True)[1]
        check('Fixed editado no cadastro muda a linha (posição 66)',
              edited[65] == 'X' and base[65] == 'S' and
              edited[:65] == base[:65] and edited[66:] == base[66:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILS:
        print('{} FAIL'.format(len(FAILS)))
        sys.exit(1)
    print('all ok')
    sys.exit(0)


def _first_diff(a, b):
    if a == b:
        return ''
    if len(a) != len(b):
        return 'len {} != {}'.format(len(a), len(b))
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return 'primeiro byte diferente na posição {} (1-based {}): {!r} != {!r}'.format(
                i, i + 1, a[max(0, i - 5):i + 6], b[max(0, i - 5):i + 6])
    return '?'


if __name__ == '__main__':
    main()
