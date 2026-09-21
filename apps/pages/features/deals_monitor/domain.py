# -*- coding: utf-8 -*-
"""As regras puras do New Deals Monitor — o catálogo de cards, a entidade (LE)
de uma linha, a taxonomia do e-mail e o parse dos horários do aviso. Sem
Flask, sem arquivo, sem rede.
"""
import os
import re

# As RECOMPRAS moram em `cache/unwinds/`, fora da árvore de New Deals, e o
# pkey delas entra prefixado: sem isto um `NDF/FX` de lá cairia no mesmo balde
# de um `NDF/FX` criado aqui — duas coisas diferentes somadas num card só.
PREFIXO_UNWIND = 'Unwind/'

# As pastas de SWAP que se dividem pela LOB da linha (ver os dois cards de swap
# abaixo e `_ndm_bucket`). `Swap/Equities` e `Swap/CEM` são as pastas que os
# dois cards já declaravam antes de existir página: ficam, para o dia em que
# alguém gravar nelas.
_NDM_SWAP_DIRS = ('Swap/Bullet', 'Swap/Cashflow', 'Swap/Equities', 'Swap/CEM',
                  PREFIXO_UNWIND + 'Swap/EDG', PREFIXO_UNWIND + 'Swap/CEM')

# O que a varredura acrescenta ao pkey da linha cuja LOB não diz o card: ela
# NÃO é chutada para um dos dois — sobra sem dono e vira o card genérico do
# grupo Others (`Swap Bullet No LOB`), que é a tela dizendo o que falta.
SEM_LOB = 'No LOB'

_NDM_CARDS = [
    {'key': 'ndf-commodities',    'label': 'NDF Commodities',     'url': '/new_deals-ndf-commodities',    'dirs': ('NDF/Commodities',),                          'les': ('JPM', 'LAW')},
    {'key': 'ndf-fwdstart',       'label': 'NDF FWD Start',       'url': '/new_deals-ndf-fwdstart',       'dirs': ('NDF/FwdStart',),                             'les': ('JPM', 'MGT', 'LAW')},
    {'key': 'ndf-otherpublisher', 'label': 'NDF Other Publisher', 'url': '/new_deals-ndf-otherpublisher', 'dirs': ('NDF/OtherPublisher',),                        'les': ('JPM', 'MGT', 'LAW')},
    {'key': 'ndf-vanilla',        'label': 'NDF Vanilla',         'url': '/new_deals-ndf-vanilla',        'dirs': ('NDF/Vanilla',),                              'les': ('JPM', 'MGT', 'LAW')},
    {'key': 'opt-commodities',    'label': 'Commodities Options', 'url': '/new_deals-opt-commodities',    'dirs': ('Option/Commodities',),                       'les': ('JPM', 'LAW')},
    {'key': 'opt-fxo',            'label': 'FX Options',          'url': '/new_deals-opt-fxo',            'dirs': ('Option/FXO',),                               'les': ('JPM', 'LAW')},
    {'key': 'opt-equity',         'label': 'Equity Options',      'url': None, 'soon': True,              'dirs': ('Option/Equity', 'Option/Equities'),          'les': ('JPM', 'ATA')},
    # Swap: DOIS cards, e quem decide em qual a operação cai é a coluna LOB da
    # linha (`EDG` → Swap Equities, `CEM` → Swap CEM), não a PÁGINA em que ela
    # nasceu (mesa, 21/09/2026). Bullet e Cashflow são FORMATO de contrato — a
    # CEM tem swap bullet e a EDG pode ter cashflow —, e o card `Swap Bullet`
    # somava as duas mesas num número que nenhuma delas conferia. As pastas são
    # as MESMAS nos dois cards; o `lob` é o que separa (`_ndm_bucket`). As de
    # recompra (`Unwind/Swap/...`) seguem a convenção do `cache/unwinds/` da
    # Fase 1: o backend delas ainda não existe, e quando nascer cai aqui.
    {'key': 'swap-equities',      'label': 'Swap Equities',       'url': '/new_deals-swap-bullet',        'dirs': _NDM_SWAP_DIRS, 'lob': 'EDG',                  'les': ('JPM', 'ATA')},
    # O backend do Cashflow existe desde 21/09/2026 (`features/swap_cashflow`,
    # arquivo-dia em `Swap/Cashflow`): o selo `soon` saiu.
    {'key': 'swap-cem',           'label': 'Swap CEM',            'url': '/new_deals-swap-cashflow', 'dirs': _NDM_SWAP_DIRS, 'lob': 'CEM',       'les': ('JPM', 'ATA')},
    # Recompra (unwind): registro na B3 como os demais desta coluna — o TER
    # 0014 vai para o mesmo Batch Conecta —, e por isso a chave NÃO leva
    # prefixo `intrag-`, que é o único teste de zona do e-mail.
    #
    # Sem `les` de propósito, pela mesma razão dos cards de DCE: a entidade da
    # recompra é a da CONTA do campo 5, e quem traduz conta → LE é o cadastro
    # `b3-accounts`. O `domain` é puro e não o lê; inventar a entidade pelo
    # nome do cliente desenharia um JPM/LAW que ninguém afirmou.
    #
    # `done` é o estado FECHADO deste produto. Os demais fecham em `Success`
    # (o B3 ID que volta), e a recompra ainda não tem esse retorno: ela acaba
    # em `Sent`. Sem declarar isto, TODA recompra já enviada apareceria como
    # pendência no aviso das 19h, todos os dias — o falso alarme diário é o
    # jeito mais rápido de a mesa parar de ler o e-mail.
    {'key': 'unwind-ndf-fx',      'label': 'Unwind NDF FX',       'url': '/unwinds/ndf/fx',               'dirs': (PREFIXO_UNWIND + 'NDF/FX',),                  'done': ('Sent',)},
    {'key': 'intrag-ndf',         'label': 'Intrag NDF',          'url': '/intrag-ndf',                   'dirs': ('Intrag/NDF',),                               'les': ('LAW', 'ATA')},
    {'key': 'intrag-option',      'label': 'Intrag Option',       'url': '/intrag-option',                'dirs': ('Intrag/Option',),                            'les': ('LAW', 'ATA')},
    {'key': 'intrag-swap',        'label': 'Intrag Swap',         'url': '/intrag-swap',                  'dirs': ('Intrag/Swap',),                              'les': ('LAW', 'ATA')},
    # As duas telas de DCE gravam arquivo-dia no MESMO cache (§454) (`Intrag/DCE
    # Option`, `Intrag/DCE Swap`), entao elas sempre entraram na varredura do
    # Monitor — so que sem entrada aqui caiam no card generico "e etc", que a
    # tela desenha no grupo *Others* do rodape, sem link para a pagina, e que o
    # e-mail de pendencias classificava como **Registration** (a chave
    # `extra-...` nao comeca com `intrag-`): cobranca de DCE misturada com
    # registro na B3. Elas nao declaram `les` de proposito — a entidade do
    # Intrag sai do portfolio code (`_ndm_deal_le`), e nenhuma das duas o traz
    # nessa grafia (o DCE Option carrega o codigo do extrato, tipo `GCCN`; o DCE
    # Swap vem da planilha e nao tem o campo). Sem a chave, o card nao desenha
    # subitem nenhum, em vez de desenhar um LAW/ATA inventado.
    # A RECOMPRA na visão do fundo (§488): a linha nasce no Send da recompra
    # para a B3 e vai à Intrag na planilha de onze colunas. Não declara `les`
    # pela mesma razão do DCE — a entidade do fundo está na CARTEIRA, e não
    # numa coluna que o `_ndm_deal_le` saiba ler. E `done` é `Sent`: a Intrag
    # não devolve id nenhum que faça a linha virar Success, e sem isto toda
    # recompra já instruída ficaria pendente no aviso das 19h para sempre.
    {'key': 'intrag-unwind',      'label': 'Intrag Unwind',       'url': '/intrag-unwind',                'dirs': ('Intrag/Unwind',),                            'done': ('Sent',)},
    {'key': 'intrag-dce-option',  'label': 'Intrag DCE Option',   'url': '/intrag-dce-option',            'dirs': ('Intrag/DCE Option',)},
    {'key': 'intrag-dce-ndf',     'label': 'Intrag DCE NDF',      'url': '/intrag-dce-ndf',               'dirs': ('Intrag/DCE NDF',)},
    {'key': 'intrag-dce-swap',    'label': 'Intrag DCE Swap',     'url': '/intrag-dce-swap',              'dirs': ('Intrag/DCE Swap',)},
]

_NDM_JPM_RE = re.compile(r'J\.?P\.?\s*MORGAN', re.IGNORECASE)

_NDM_ATA_DIRS = {'Option/Equity', 'Option/Equities'} | set(_NDM_SWAP_DIRS)

# As PASTAS das três páginas genéricas de NDF — sem espaço, que é como o
# `_GENERIC_ND_PRODUCTS` as grava. `FWD Start` e `Other Publisher` (com espaço)
# são os RÓTULOS, e conviviam aqui como se fossem "a outra grafia em produção":
# nunca foram, e um diretório que não existe casa com nada.
_NDM_GENERIC_NDF_DIRS = {'NDF/FwdStart', 'NDF/OtherPublisher', 'NDF/Vanilla'}

_NDM_LOBS = tuple(c['lob'] for c in _NDM_CARDS if c.get('lob'))


def _ndm_lob(d):
    """A LOB da linha como o card a declara (`EDG`/`CEM`), ou `''`. Só letras
    e dígitos, em maiúsculas — a mesma leitura que o Swap Bullet faz dela para
    o nome do arquivo —, porque nas páginas de recompra a coluna é texto livre."""
    return re.sub(r'[^A-Z0-9]', '', str((d or {}).get('LOB') or '').upper())


def _ndm_bucket(pkey, d):
    """O balde da contagem: o pkey, e nas pastas de swap o pkey + a LOB.

    O card pede `<pasta>#<LOB>` (ver `card_buckets`). LOB fora das declaradas
    devolve `<pasta>/No LOB`, que card nenhum pede: a linha aparece no grupo
    Others com esse nome, em vez de somar no card da outra mesa."""
    if pkey not in _NDM_SWAP_DIRS:
        return pkey
    lob = _ndm_lob(d)
    return pkey + '#' + lob if lob in _NDM_LOBS else pkey + '/' + SEM_LOB


def card_buckets(card):
    """Os baldes que o card soma — as `dirs`, com a LOB quando ele a declara."""
    lob = card.get('lob')
    return tuple(d + '#' + lob if lob else d for d in card['dirs'])


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
    # Swap Bullet: o B2B grava o deal Banco × Atacama com Client = 'Atacama'
    # (o DT chega assim) — é a perna da entidade intragrupo.
    if pkey in _NDM_ATA_DIRS and 'ATACAMA' in cl.upper():
        return 'ATA'
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
    'unwind-ndf-fx':      ('NDF', 'Unwind FX'),
    # Intrag não tem sub-variante: o tipo da linha já diz Intrag, e repetir a
    # palavra na coluna Detail não acrescenta nada.
    'intrag-ndf':         ('NDF', '—'),
    'intrag-option':      ('Option', '—'),
    'intrag-swap':        ('Swap', '—'),
    # A recompra TEM sub-variante: é o outro fluxo do mesmo produto, como o DCE.
    'intrag-unwind':      ('NDF', 'Unwind'),
    # O DCE, ao contrario, TEM sub-variante: e o outro fluxo do mesmo produto.
    'intrag-dce-option':  ('Option', 'DCE'),
    'intrag-dce-ndf':     ('NDF', 'DCE'),
    'intrag-dce-swap':    ('Swap', 'DCE'),
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

_NDM_PENDING_TIMES = os.getenv('DEALS_MONITOR_PENDING_TIMES', '19:00,19:30,20:00')

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
    return sorted(set(out)) or [(19, 0), (19, 30), (20, 0)]
