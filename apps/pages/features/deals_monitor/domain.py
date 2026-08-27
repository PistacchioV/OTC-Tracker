# -*- coding: utf-8 -*-
"""As regras puras do New Deals Monitor — o catálogo de cards, a entidade (LE)
de uma linha, a taxonomia do e-mail e o parse dos horários do aviso. Sem
Flask, sem arquivo, sem rede.
"""
import os
import re

_NDM_CARDS = [
    {'key': 'ndf-commodities',    'label': 'NDF Commodities',     'url': '/new_deals-ndf-commodities',    'dirs': ('NDF/Commodities',),                          'les': ('JPM', 'LAW')},
    {'key': 'ndf-fwdstart',       'label': 'NDF FWD Start',       'url': '/new_deals-ndf-fwdstart',       'dirs': ('NDF/FWD Start', 'NDF/FwdStart'),             'les': ('JPM', 'MGT', 'LAW')},
    {'key': 'ndf-otherpublisher', 'label': 'NDF Other Publisher', 'url': '/new_deals-ndf-otherpublisher', 'dirs': ('NDF/OtherPublisher', 'NDF/Other Publisher'), 'les': ('JPM', 'MGT', 'LAW')},
    {'key': 'ndf-vanilla',        'label': 'NDF Vanilla',         'url': '/new_deals-ndf-vanilla',        'dirs': ('NDF/Vanilla',),                              'les': ('JPM', 'MGT', 'LAW')},
    {'key': 'opt-commodities',    'label': 'Commodities Options', 'url': '/new_deals-opt-commodities',    'dirs': ('Option/Commodities',),                       'les': ('JPM', 'LAW')},
    {'key': 'opt-fxo',            'label': 'FX Options',          'url': '/new_deals-opt-fxo',            'dirs': ('Option/FXO',),                               'les': ('JPM', 'LAW')},
    {'key': 'opt-equity',         'label': 'Equity Options',      'url': None, 'soon': True,              'dirs': ('Option/Equity', 'Option/Equities'),          'les': ('JPM', 'ATA')},
    {'key': 'swap-equities',      'label': 'Swap Equities',       'url': None, 'soon': True,              'dirs': ('Swap/Equities',),                            'les': ('JPM', 'ATA')},
    {'key': 'swap-cem',           'label': 'Swap CEM',            'url': None, 'soon': True,              'dirs': ('Swap/CEM',),                                 'les': ('JPM', 'LAW')},
    {'key': 'intrag-ndf',         'label': 'Intrag NDF',          'url': '/intrag-ndf',                   'dirs': ('Intrag/NDF',),                               'les': ('LAW', 'ATA')},
    {'key': 'intrag-option',      'label': 'Intrag Option',       'url': '/intrag-option',                'dirs': ('Intrag/Option',),                            'les': ('LAW', 'ATA')},
]

_NDM_JPM_RE = re.compile(r'J\.?P\.?\s*MORGAN', re.IGNORECASE)

_NDM_ATA_DIRS = {'Option/Equity', 'Option/Equities', 'Swap/Equities'}

_NDM_GENERIC_NDF_DIRS = {'NDF/FWD Start', 'NDF/FwdStart',
                         'NDF/OtherPublisher', 'NDF/Other Publisher',
                         'NDF/Vanilla'}

def _ndm_deal_le(pkey, d):
    """Entidade (LE) de uma linha do monitor, para os subitens dos cards.
    Intrag: pelo portfolio code — INTRAGJP552 = LAW, INTRAGJP633 = ATA
    (Intrag NDF grava 'portfolio_code', Intrag Option grava 'portfolio').
    NDFs genéricos (Vanilla/Other Pub/FWD Start): LE = MGT → MGT;
    Client com LAWTON → LAW (operação contra a Lawton); resto → JPM. O teste
    "Client = Banco" não serve aqui: o nome da MGT no RefData também casa com
    J.P. Morgan, então as linhas JPM×MGT cairiam em LAW indevidamente.
    Demais produtos B3: linha cujo Client é o Banco J.P. Morgan é a
    perna-espelho da entidade intragrupo (ATA nos produtos de equities, LAW
    nos demais); o resto é registro do Banco → JPM."""
    if pkey.startswith('Intrag'):
        code = str(d.get('portfolio_code') or d.get('portfolio') or '').strip().upper()
        return {'INTRAGJP552': 'LAW', 'INTRAGJP633': 'ATA'}.get(code, 'ATA')
    cl = str(d.get('Client') or '')
    if pkey in _NDM_GENERIC_NDF_DIRS:
        if str(d.get('LE') or '').strip().upper() == 'MGT':
            return 'MGT'
        return 'LAW' if 'LAWTON' in cl.upper() else 'JPM'
    if _NDM_JPM_RE.search(cl):
        return 'ATA' if pkey in _NDM_ATA_DIRS else 'LAW'
    return 'JPM'

_NDM_TAXONOMY = {
    'ndf-commodities':    ('NDF', 'Commodities'),
    'ndf-fwdstart':       ('NDF', 'FWD Start'),
    'ndf-otherpublisher': ('NDF', 'Other Publisher'),
    'ndf-vanilla':        ('NDF', 'Vanilla'),
    'opt-commodities':    ('Option', 'Commodities'),
    'opt-fxo':            ('Option', 'FX'),
    'opt-equity':         ('Option', 'Equity'),
    'swap-equities':      ('Swap', 'Equities'),
    'swap-cem':           ('Swap', 'CEM'),
    # Intrag não tem sub-variante: o tipo da linha já diz Intrag, e repetir a
    # palavra na coluna Detail não acrescenta nada.
    'intrag-ndf':         ('NDF', '—'),
    'intrag-option':      ('Option', '—'),
    'intrag-swap':        ('Swap', '—'),
}

_NDM_TYPE_ORDER = ['Registration', 'Confirmation', 'Intrag']

def _ndm_card_taxonomy(card, zone):
    """(tipo, produto, detalhe) de um card. Produto fora do catálogo (os cards
    'Others', que nascem sozinhos quando aparece um diretório novo no cache)
    cai no label do próprio card, para nunca sumir do e-mail por falta de
    cadastro."""
    key = str(card.get('key') or '')
    if key in _NDM_TAXONOMY:
        product, detail = _NDM_TAXONOMY[key]
    elif key.startswith('conf-') and key[5:] in _NDM_TAXONOMY:
        product, detail = _NDM_TAXONOMY[key[5:]]
    else:
        label = str(card.get('label') or key or '—').strip()
        parts = label.split(None, 1)
        product, detail = (parts[0], parts[1]) if len(parts) == 2 else (label, '—')
    return zone, product, detail

_NDM_PENDING_DEFAULT_TO = 'brazil.otc.ops@jpmorgan.com'

_NDM_PENDING_TIMES = os.getenv('DEALS_MONITOR_PENDING_TIMES', '19:00,19:30')

def _ndm_pending_times():
    """Horários do dia em (hh, mm), ordenados. Entrada inválida cai no padrão —
    um typo na variável de ambiente não pode matar o aviso."""
    out = []
    for part in str(_NDM_PENDING_TIMES or '').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            hh, mm = (int(x) for x in part.split(':')[:2])
        except (ValueError, TypeError):
            continue
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            out.append((hh, mm))
    return sorted(set(out)) or [(19, 0), (19, 30)]
