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
    {'key': 'unwind-ndf-fx',      'label': 'Unwind NDF FX',       'url': '/unwinds/ndf/fx',               'dirs': (PREFIXO_UNWIND + 'NDF/FX',),                  'done': ('Sent', 'Success')},
    # As recompras do CATÁLOGO (`unwinds/catalog.py`): a pasta é o `dir` da
    # entrada, e o mesmo raciocínio do card acima — registro na B3, fecha em
    # `Sent`, sem `les`. O swap NÃO tem card de recompra: `Unwind/Swap/CEM` e
    # `Unwind/Swap/EDG` já somam nos dois cards de swap pela LOB da linha (§517).
    {'key': 'unwind-ndf-commodities', 'label': 'Unwind NDF Commodities', 'url': '/unwinds/ndf/commodities', 'dirs': (PREFIXO_UNWIND + 'NDF/Commodities',), 'done': ('Sent', 'Success')},
    {'key': 'unwind-opt-fxo',     'label': 'Unwind Options FXO',  'url': '/unwinds/options/fxo',          'dirs': (PREFIXO_UNWIND + 'Options/FXO',),             'done': ('Sent', 'Success')},
    {'key': 'unwind-opt-commodities', 'label': 'Unwind Options Commodities', 'url': '/unwinds/options/commodities', 'dirs': (PREFIXO_UNWIND + 'Options/Commodities',), 'done': ('Sent', 'Success')},
    {'key': 'unwind-opt-edg',     'label': 'Unwind Options EDG',  'url': '/unwinds/options/edg',          'dirs': (PREFIXO_UNWIND + 'Options/EDG',),             'done': ('Sent', 'Success')},
    # COE e DCE não têm arquivo da B3 (`b3: None` no catálogo): não existe
    # `Sent` para eles. Fecham na linha CONFERIDA — `Imported` (intocada) ou
    # `Approved`; só a edição sem segundo par de olhos (`Pending`) fica pendente.
    {'key': 'unwind-coe',         'label': 'Unwind COE',          'url': '/unwinds/coe',                  'dirs': (PREFIXO_UNWIND + 'COE',),                     'done': ('Imported', 'Approved')},
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
    # A RECOMPRA na visão do fundo (§488): a linha nasce no IMPORT da recompra
    # (§582 — nunca no Send) e vai à Intrag na planilha de onze colunas. Não declara `les`
    # pela mesma razão do DCE — a entidade do fundo está na CARTEIRA, e não
    # numa coluna que o `_ndm_deal_le` saiba ler. E `done` é `Sent`: a Intrag
    # não devolve id nenhum que faça a linha virar Success, e sem isto toda
    # recompra já instruída ficaria pendente no aviso das 19h para sempre.
    {'key': 'intrag-unwind',      'label': 'Intrag Unwind',       'url': '/intrag-unwind',                'dirs': ('Intrag/Unwind',),                            'done': ('Sent', 'Success')},
    {'key': 'intrag-dce-option',  'label': 'Intrag DCE Option',   'url': '/intrag-dce-option',            'dirs': ('Intrag/DCE Option',)},
    {'key': 'intrag-dce-ndf',     'label': 'Intrag DCE NDF',      'url': '/intrag-dce-ndf',               'dirs': ('Intrag/DCE NDF',)},
    {'key': 'intrag-dce-swap',    'label': 'Intrag DCE Swap',     'url': '/intrag-dce-swap',              'dirs': ('Intrag/DCE Swap',)},
    # A recompra de DCE: o DCE vive na zona Intrag (os quatro cards acima), e a
    # recompra dele também — por isso o prefixo `intrag-`, que é o teste de zona
    # do e-mail. Sem arquivo da B3, fecha na linha conferida (ver `unwind-coe`).
    {'key': 'intrag-unwind-dce-deliverable-forward', 'label': 'Unwind DCE Deliverable Forward', 'url': '/unwinds/dce/deliverable-forward', 'dirs': (PREFIXO_UNWIND + 'DCE/Deliverable Forward',), 'done': ('Imported', 'Approved')},
    {'key': 'intrag-unwind-dce-ndf',    'label': 'Unwind DCE NDF',    'url': '/unwinds/dce/ndf',    'dirs': (PREFIXO_UNWIND + 'DCE/NDF',),    'done': ('Imported', 'Approved')},
    {'key': 'intrag-unwind-dce-option', 'label': 'Unwind DCE Option', 'url': '/unwinds/dce/option', 'dirs': (PREFIXO_UNWIND + 'DCE/Option',), 'done': ('Imported', 'Approved')},
    {'key': 'intrag-unwind-dce-swap',   'label': 'Unwind DCE Swap',   'url': '/unwinds/dce/swap',   'dirs': (PREFIXO_UNWIND + 'DCE/Swap',),   'done': ('Imported', 'Approved')},
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
    'unwind-ndf-commodities': ('NDF', 'Unwind Commodities'),
    'unwind-opt-fxo':     ('Option', 'Unwind FX'),
    'unwind-opt-commodities': ('Option', 'Unwind Commodities'),
    'unwind-opt-edg':     ('Option', 'Unwind Equity'),
    'unwind-coe':         ('COE', 'Unwind'),
    'intrag-unwind-dce-deliverable-forward': ('NDF', 'Unwind DCE Deliverable Forward'),
    'intrag-unwind-dce-ndf': ('NDF', 'Unwind DCE'),
    'intrag-unwind-dce-option': ('Option', 'Unwind DCE'),
    'intrag-unwind-dce-swap': ('Swap', 'Unwind DCE'),
    # Intrag não tem sub-variante: o tipo da linha já diz Intrag, e repetir a
    # palavra na coluna Detail não acrescenta nada.
    'intrag-ndf':         ('NDF', '—'),
    'intrag-option':      ('Option', '—'),
    'intrag-swap':        ('Swap', '—'),
    # A Intrag Unwind é de TODOS os produtos (mesa, 22/09/2026): no e-mail ela
    # é o produto `Unwind`, como o bloco próprio da tela — `NDF` afirmava que a
    # recompra espelhada é de termo de moeda.
    'intrag-unwind':      ('Unwind', '—'),
    # O Termo de Resilição só existe na zona Confirmations (não há card da B3
    # de que ele seja o `conf-` gêmeo): chave inteira.
    'conf-unwind-termo':  ('Unwind', 'Termo de Resilição'),
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


# ══════════════════════════════════════════════════════════════════════════
# INTRAG DESDE O IMPORT (§567)
# --------------------------------------------------------------------------
# A linha da Intrag só NASCE quando a operação do New Deals ganha B3 ID (o
# espelho é gravado no Success, pelos `_save_intrag_*` / `_maybe_save_intrag_*`
# e pelo `swap_new_deals.b3_mapped`). Contar só o arquivo da Intrag deixava a
# zona zerada o dia inteiro, com a operação já importada e a instrução ao
# custodiante por fazer: a mesa só via a pendência DEPOIS do registro. Agora a
# operação que VAI para a Intrag conta na zona desde o import, com o status
# `AWAITING_B3`; quando o espelho nasce, quem conta é a linha real da Intrag —
# a operação em `Success` sai daqui, e ninguém é contado duas vezes.
#
# A regra é a MESMA dos pontos que gravam o espelho — escrita aqui porque
# feature não importa feature. Mudou lá, muda aqui (`check_intraday_monitor.py`
# prende os casos):
#   · NDF Commodities, Commodities Options e FX Options contra o BANCO J.P.
#     MORGAN (`'banco' in cl and 'morgan' in cl`, a grafia do espelho);
#   · NDF Vanilla e Other Publisher contra o LAWTON (FWD Start fica fora: o
#     strike só existe na strike set date, e o espelho também não o grava);
#   · Swap no B2B Banco × Atacama (`swap_deal_ticket.is_b2b`).
# ══════════════════════════════════════════════════════════════════════════
AWAITING_B3 = 'Awaiting B3 ID'

_INTRAG_BANCO_DIRS = {'NDF/Commodities': 'Intrag/NDF',
                      'Option/Commodities': 'Intrag/Option',
                      'Option/FXO': 'Intrag/Option'}
_INTRAG_LAWTON_DIRS = {'NDF/Vanilla': 'Intrag/NDF', 'NDF/OtherPublisher': 'Intrag/NDF'}
_INTRAG_SWAP_DIRS = ('Swap/Bullet', 'Swap/Cashflow')


def intrag_destino(pkey, d):
    """O balde da Intrag para onde a operação `d` do New Deals VAI, enquanto o
    espelho ainda não existe — ou `None` (não vai, ou já foi: `Success` é
    contado pela linha real da Intrag; `Canceled` não conta em lugar nenhum)."""
    st = str(d.get('Status') or d.get('status') or '').strip().lower()
    if st in ('success', 'canceled'):
        return None
    cl = str(d.get('Client') or '').lower()
    if pkey in _INTRAG_BANCO_DIRS:
        return _INTRAG_BANCO_DIRS[pkey] if ('banco' in cl and 'morgan' in cl) else None
    if pkey in _INTRAG_LAWTON_DIRS:
        return _INTRAG_LAWTON_DIRS[pkey] if 'lawton' in cl else None
    if pkey in _INTRAG_SWAP_DIRS:
        from apps.pages.platform import swap_deal_ticket     # puro: só o parser do DT
        return 'Intrag/Swap' if swap_deal_ticket.is_b2b(d) else None
    return None


def intrag_destino_le(balde):
    """A entidade do espelho: o fundo que a Intrag carteira — Atacama no swap,
    Lawton nos demais (INTRAGJP633 × INTRAGJP552, a leitura do `_ndm_deal_le`)."""
    return 'ATA' if balde == 'Intrag/Swap' else 'LAW'


# ══════════════════════════════════════════════════════════════════════════
# INTRADAY MONITOR — as tarefas do dia (§567)
# --------------------------------------------------------------------------
# O catálogo diz QUAIS tarefas existem e de onde o estado de cada uma vem; a
# AGENDA (dias da semana e horário limite) é do Control Panel, card
# `intradaytasks`, e o que está aqui é só o padrão de quem nunca salvou.
#
# `kind`:
#   · `zone`  — as três zonas do monitor (registro na B3, confirmações,
#               Intrag). Conclui com ZERO em aberto, pela mesma regra do aviso
#               das 19h (`_ndm_pending_blocks`): duas definições de "em aberto"
#               fariam a tela e o e-mail cobrarem números diferentes;
#   · `recon` — conclui quando RODOU no dia (mesa, 28/09/2026): as quebras
#               abertas são informação do card, não o critério. Quem diz que
#               rodou é o registro de execuções (`platform/task_runs`). TODA
#               recon é uma tarefa aqui — a que nasce entra no catálogo e grava
#               `task_runs.record` no `run` dela (`check_intraday_monitor.py`
#               varre o `url_map` e recusa recon de fora). Quem a mesa não
#               cobra nasce com `days=()`: está no card, fora do Monitor.
#               Conf. Matching é diária (mesa, 28/09/2026);
#   · `routine` — rotina do Control Panel (mesa, 28/09/2026): conclui quando
#               RODOU no dia, pelo mesmo registro de execuções. O Save CETIP
#               Files grava no Save com ao menos um arquivo salvo; a cobrança das
#               confirmações, quando o PACOTE da rotina (segunda e quinta) sai
#               sem erro — pelo Run do card ou pelo disparo automático;
#   · `branch` — a reversão da Branch Settlement (§560/§566): só EXISTE no dia
#               em que o Pay/Rec achou liquidação com a Branch. Anda em três
#               passos — detectada, rascunho de aprovação ao VP gerado (o botão
#               Branch Settl.), a linha da reversão casada no Pay/Rec — e só o
#               último conclui: o rascunho é o pedido, o dinheiro é o fato.
#
# Dia da semana no padrão do Python: 0 = segunda … 6 = domingo. "Diário" é
# segunda a sexta, e feriado ANBIMA não tem tarefa.
# ══════════════════════════════════════════════════════════════════════════
DIAS_UTEIS = (0, 1, 2, 3, 4)
DEADLINE_PADRAO = '20:00'

TASKS = (
    {'id': 'registration', 'kind': 'zone', 'zone': 'Registration', 'label': 'B3 Registration',
     'icon': 'ti-building-bank', 'url': '#ndm-detail', 'days': DIAS_UTEIS},
    {'id': 'confirmation', 'kind': 'zone', 'zone': 'Confirmation', 'label': 'Confirmations',
     'icon': 'ti-file-check', 'url': '/manual-confirmation/monitor', 'days': DIAS_UTEIS},
    {'id': 'intrag', 'kind': 'zone', 'zone': 'Intrag', 'label': 'Intrag',
     'icon': 'ti-building', 'url': '#ndm-detail', 'days': DIAS_UTEIS},
    # O Pay/Rec só conclui no END PROCESS (mesa, 28/09/2026): rodar é o meio
    # do caminho (em andamento, 50%) — o dia só fecha quando é finalizado.
    # `link_ref`: a data que o link de pendência leva à recon. A referência de
    # uma recon não é o dia em que ela roda — FXO, CGD, Comitente e Conf.
    # Matching rodam sobre o dia útil ANTERIOR (`prev`, o padrão de `recon`);
    # o Pay/Rec, sobre o próprio dia (`same`).
    {'id': 'recon-payrec', 'kind': 'recon', 'label': 'Recon Pay/Rec', 'done_on': 'end', 'link_ref': 'same',
     'icon': 'ti-arrows-left-right', 'url': '/reconciliation-payrec', 'days': DIAS_UTEIS},
    {'id': 'branch-reversal', 'kind': 'branch', 'label': 'Branch Reversal',
     'icon': 'ti-arrow-back-up', 'url': '/reconciliation-payrec', 'days': DIAS_UTEIS},
    {'id': 'recon-fxo', 'kind': 'recon', 'label': 'Recon FXO',
     'icon': 'ti-currency-dollar', 'url': '/reconciliation-fxo', 'days': DIAS_UTEIS},
    {'id': 'recon-comitente', 'kind': 'recon', 'label': 'Recon Comitente',
     'icon': 'ti-users', 'url': '/reconciliation-comitente', 'days': (1,)},
    {'id': 'recon-cgd', 'kind': 'recon', 'label': 'Recon CGD',
     'icon': 'ti-file-certificate', 'url': '/reconciliation-cgd', 'days': (4,)},
    {'id': 'recon-conf-matching', 'kind': 'recon', 'label': 'Recon Conf. Matching',
     'icon': 'ti-file-search', 'url': '/reconciliation-conf-matching', 'days': DIAS_UTEIS},
    {'id': 'save-cetip', 'kind': 'routine', 'label': 'Save CETIP Files',
     'icon': 'ti-file-download', 'url': '/control-panel', 'days': DIAS_UTEIS},
    {'id': 'conf-escalation', 'kind': 'routine', 'label': 'Confirmations Escalation',
     'icon': 'ti-mail-exclamation', 'url': '/control-panel', 'days': (0, 3)},
)
TASK_IDS = tuple(t['id'] for t in TASKS)

_HHMM = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')


def task_config(salvo):
    """A agenda de cada tarefa: o salvo no Control Panel por cima do padrão.

    Valor ruim de UMA tarefa cai no padrão DELA (e só dela): um horário
    digitado errado não pode tirar a tarefa da tela nem derrubar as outras.
    Dias fora de 0..6 somem; lista vazia é "nunca" — uma escolha, não um erro
    (é assim que se desliga uma tarefa sem apagar o horário)."""
    salvo = salvo if isinstance(salvo, dict) else {}
    out = {}
    for t in TASKS:
        s = salvo.get(t['id']) if isinstance(salvo.get(t['id']), dict) else {}
        dias = s.get('days')
        if isinstance(dias, (list, tuple)):
            dias = sorted({int(x) for x in dias
                           if str(x).lstrip('-').isdigit() and 0 <= int(x) <= 6})
        else:
            dias = list(t['days'])
        hora = str(s.get('deadline') or '').strip()
        out[t['id']] = {'days': dias,
                        'deadline': hora if _HHMM.match(hora) else DEADLINE_PADRAO}
    return out


def avalia(cfg, dia, agora, feriado, feito, iniciado, feito_em=None):
    """O estado de UMA tarefa em `dia`, visto em `agora` (datetime, BRT).

    Devolve `due` (a tarefa existe neste dia), o prazo e `state`:
      · `done`        — concluída (`late_done` quando depois do prazo);
      · `late`        — o prazo passou e ela não foi concluída;
      · `in_progress` — começou e não terminou (zona com parte fechada);
      · `todo`        — ainda nada.
    Dia que já passou e ficou por fazer é `late`; dia futuro é `todo`."""
    from datetime import datetime as _dt
    hh, mm = (int(x) for x in cfg['deadline'].split(':'))
    prazo = _dt(dia.year, dia.month, dia.day, hh, mm)
    due = (dia.weekday() in cfg['days']) and not feriado
    if feito:
        state = 'done'
    elif agora > prazo:
        state = 'late'
    elif iniciado:
        state = 'in_progress'
    else:
        state = 'todo'
    return {
        'due': due, 'state': state,
        'deadline': cfg['deadline'], 'deadline_at': prazo.strftime('%Y-%m-%dT%H:%M'),
        'late_done': bool(feito and feito_em and feito_em > prazo),
        'minutes_left': int((prazo - agora).total_seconds() // 60) if not feito else None,
    }
