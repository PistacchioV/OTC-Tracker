"""Fictional-data generator for OTC Tracker screenshots.
Reuses the REAL column headers returned by each API (non-sensitive) and
fabricates plausible rows/widgets with 100% fictitious values."""
import random, json

random.seed(42)

CPTY = ['AURORA TRADING LTDA', 'BLUE HARBOR FUNDO MM', 'MONTE VERDE S.A.',
        'RIO BRANCO INVEST', 'CEDRO CAPITAL FIM', 'ORION ASSET FIM',
        'PONTAL INVESTIMENTOS', 'VELMONT S.A.', 'SERRA AZUL FUNDO',
        'DELTA PRIME LTDA', 'NOVA LISBOA CAPITAL', 'PORTO SEGURO FIM']
CNPJ = ['12.345.678/0001-90', '23.456.789/0001-01', '34.567.890/0001-12',
        '45.678.901/0001-23', '56.789.012/0001-34', '67.890.123/0001-45']
ACCT = ['99001234', '88007654', '77006543', '66005432', '95104321', '90209876']
CCY = ['USD', 'BRL', 'EUR', 'GBP', 'JPY']
PAIRS = ['USD/BRL', 'EUR/BRL', 'GBP/BRL', 'USD/EUR']
CLASSE = ['Taxas de Câmbio', 'Commodities', 'Taxas de Câmbio', 'Taxas de Câmbio']
TIPO = ['SISBACEN', 'FEEDER', 'SISBACEN', 'SISBACEN']
COMMOD = ['Milho', 'Soja', 'Café Arábica', 'Boi Gordo', 'Açúcar', 'Petróleo Brent']
SITU = ['Ativo', 'Ativo', 'Ativo', 'Antecipado']
OPTYPE = ['Call', 'Put']
EXERC = ['Europeu', 'Americano']


def _date(i):
    d = 1 + (i * 3) % 27
    m = 1 + (i * 2) % 12
    return f'{d:02d}/{m:02d}/2026'


def _money(i):
    base = [125000, 480000, 1250000, 92000, 3400000, 750000, 210000, 5600000]
    v = base[i % len(base)] + (i * 1375.5)
    return f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _val_for(col, i):
    c = col.lower()
    if 'data' in c or c.startswith('dt') or 'vencimento' in c or 'fixing' in c:
        return _date(i)
    if 'cpf' in c or 'cnpj' in c:
        return CNPJ[i % len(CNPJ)]
    if 'conta' in c:
        return ACCT[i % len(ACCT)]
    # code columns (Codigo/Código da Parte/Contraparte/IF/Operação) -> codes, not names
    if ('codigo' in c or 'código' in c) and 'cpf' not in c and 'cnpj' not in c:
        if 'parte' in c or 'contraparte' in c or 'cliente' in c:
            return ACCT[i % len(ACCT)]
        if 'if' in c or 'contrato' in c or 'operaç' in c or 'operac' in c or 'instrumento' in c:
            return f'NDF{100000 + i*137:06d}'
        return f'COD{5000 + i*13}'
    if ('nome' in c or 'parte' in c or 'cliente' in c or 'client' in c or
            'contraparte' in c or 'owner' in c) and 'código' not in c and 'codigo' not in c and 'conta' not in c:
        return CPTY[i % len(CPTY)]
    if 'percentual' in c or '(%' in c or c.endswith('%'):
        return f'{(90 + i) % 130},{(i*7) % 100:02d}%'
    if ('valor' in c or 'notional' in c or 'prêmio' in c or 'premio' in c or 'nocional' in c
            or 'financeiro' in c or 'rebate' in c or 'amount' in c or 'strike (valor)' in c
            or 'base' in c or 'mtm' in c):
        return _money(i)
    if 'quantidade' in c or 'qty' in c or 'quantity' in c:
        return f'{(i+1)*1000:,}'.replace(',', '.')
    if 'strike' in c:
        return f'{5 + i*0.13:.4f}'.replace('.', ',')
    if 'cotação' in c or 'cotacao' in c or 'rate' in c or 'taxa' in c:
        return f'{5 + (i % 5)*0.21:.4f}'.replace('.', ',')
    if 'moeda' in c or 'currency' in c or 'ccy' in c:
        return CCY[i % len(CCY)]
    if 'par' == c or 'pair' in c or ('ativo' in c and 'subjacente' in c and 'classe' not in c):
        return PAIRS[i % len(PAIRS)]
    if 'classe' in c:
        return CLASSE[i % len(CLASSE)]
    if 'mercadoria' in c or 'commodit' in c:
        return COMMOD[i % len(COMMOD)]
    if 'tipo de opção' in c or 'tipo de opcao' in c:
        return OPTYPE[i % len(OPTYPE)]
    if 'exercício' in c or 'exercicio' in c:
        return EXERC[i % len(EXERC)]
    if 'situação' in c or 'situacao' in c or 'status' in c or 'contrato' in c:
        return SITU[i % len(SITU)]
    if 'tipo' in c or 'publisher' in c or 'publicador' in c:
        return TIPO[i % len(TIPO)]
    if 'código if' in c or 'codigo if' in c or 'código' in c or 'codigo' in c or 'id' in c or 'código da' in c:
        return f'NDF{100000 + i*137:06d}'
    if 'combinação' in c or 'combinacao' in c:
        return f'CMB{200 + i}'
    if 'posição' in c or 'posicao' in c or 'direção' in c or 'direction' in c or 'direcao' in c:
        return ['Comprado', 'Vendido'][i % 2]
    if 'periodicidade' in c:
        return 'Diária'
    if 'sim' in c or 'não' in c or 'proteção' in c:
        return ['Sim', 'Não'][i % 2]
    return f'{col[:6].upper()}-{i+1:02d}'


def fake_rows(columns, n=12):
    return [[_val_for(col, i) for col in columns] for i in range(n)]


def fill_widgets(widgets, nrows=12):
    """Give every numeric widget slot a plausible fictional count."""
    if not isinstance(widgets, dict):
        return widgets
    presets = {'total': nrows, 'vanilla': 5, 'other_publisher': 3, 't0': 2,
               'commodities': 2, 'a': 4, 'b': 5, 'c': 3}
    out = {}
    for k, v in widgets.items():
        if isinstance(v, (int, float)):
            out[k] = presets.get(k, 3 + (hash(k) % 7))
        else:
            out[k] = v
    return out


def _dashboard_mock(obj):
    o = dict(obj)
    o.update({
        'ndf_total': 48, 'opt_total': 27, 'swap_total': 63, 'total_deals': 138,
        'pending_total': 6,
        'dist_ndf': 48, 'dist_opt': 15, 'dist_fxo': 12, 'dist_swap': 63,
        'monthly_ndf': [3, 5, 4, 6, 5, 7, 4, 3, 5, 2, 4, 0],
        'monthly_opt': [2, 1, 3, 2, 4, 1, 3, 2, 2, 1, 3, 0],
        'monthly_fxo': [1, 2, 1, 0, 2, 1, 1, 2, 0, 1, 1, 0],
        'monthly_swap': [4, 6, 5, 7, 6, 8, 5, 4, 6, 5, 7, 0],
        'top5_clients': [{'label': n, 'count': c} for n, c in
                         zip(CPTY, [28, 22, 19, 15, 11])],
        'top5_products': [{'label': n, 'count': c} for n, c in
                          [('NDF Vanilla', 34), ('Swap Pré x CDI', 27),
                           ('FX Option', 18), ('NDF Commodities', 12), ('COE', 7)]],
        'top5_underlying': [{'label': n, 'count': c} for n, c in
                            [('USD/BRL', 41), ('EUR/BRL', 16), ('Milho', 9),
                             ('Soja', 7), ('Café Arábica', 5)]],
        'recent_deals': [
            {'deal': f'NDF{100000 + i*137:06d}',
             'product': ['ndf', 'option', 'swap', 'ndf', 'fxo'][i % 5],
             'type': ['Vanilla', 'FXO', 'Pré x CDI', 'Commodities', 'FXO'][i % 5],
             'client': CPTY[i % len(CPTY)], 'date': _date(i),
             'status': ['confirmed', 'pending', 'confirmed'][i % 3]}
            for i in range(8)],
    })
    o['success'] = True
    return o


def transform(obj, nrows=12):
    """Given a parsed API JSON dict, inject fictional data. Returns (changed, obj)."""
    if not isinstance(obj, dict):
        return False, obj
    # generic table contract
    cols = obj.get('columns')
    if isinstance(cols, list) and cols and 'rows' in obj:
        obj = dict(obj)
        obj['rows'] = fake_rows(cols, nrows)
        if 'widgets' in obj:
            obj['widgets'] = fill_widgets(obj.get('widgets'), nrows)
        obj['success'] = True
        return True, obj
    # dashboard-stats
    if 'total_deals' in obj and 'top5_clients' in obj:
        return True, _dashboard_mock(obj)
    # ndf-summary cards
    if 'cards' in obj and isinstance(obj.get('cards'), dict):
        o = dict(obj)
        o['cards'] = {'vanilla': 18, 'other_publisher': 9, 't0': 5, 'total': 32}
        o['ter_date'] = '2026-07-07'
        o['success'] = True
        return True, o
    # other-products-summary widgets
    if 'widgets' in obj and isinstance(obj.get('widgets'), dict) and 'summary' in obj:
        o = dict(obj)
        o['widgets'] = {'coe': {'total': 7},
                        'ndf': {'maturity': 12, 'total': 40},
                        'option': {'maturity': 5, 'premium': 9, 'total': 22},
                        'swap': {'flow': 8, 'maturity': 14, 'premium': 6, 'total': 55}}
        o['success'] = True
        return True, o
    return False, obj
