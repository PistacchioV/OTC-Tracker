# -*- coding: utf-8 -*-
"""O motor de confirmações do New Deals (`_conf_*`) — o compartilhado das
quatro famílias: NDF Commodities, Opção de Commodities, Opção de FX e
NDF FWD Start.

Movido VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). Daqui saem a
segregação por contraparte × mercadoria (`_conf_segregate`), o estado
New → Generated → Success de cada grupo (`_conf_state_*`), a tradução das
etapas da esteira (`_conf_esteira_stages` — é o que faz o card do New Deals
Monitor parar no Pending OTC, §254), as páginas de geração das quatro famílias
e o XML da B3. O `routes.py` mantém os nomes como ALIAS, então features e
testes seguem alcançando por `routes.<nome>`.

O ESTADO fica AQUI: `_conf_subj_cache` (o Subjacente.json indexado, cache por
mtime) é mutado in place e o alias do routes continua vivo — mas teste que o
zera troca a chave NESTE módulo.

O que ainda é do `routes` — os caminhos de cache dos arquivos-dia
(`NDF_COMM_CACHE_DIR`…), o Pending Confirmation (`_PC_*`, `duckdb_write`), o
Counterparty Details (`_cpd_*`), os mappings e o calendário
(`_anbima_holidays`, que o check_co12_roll troca por espião no `routes`) — é
alcançado por import ATRASADO dentro da função, andaime declarado até cada
camada ter a própria fatia.
"""
import json
import logging
import os
import re
import traceback
from collections import Counter
from datetime import datetime, timedelta

from flask import redirect, render_template, request, session, url_for

from apps.pages.data_paths import data_dir, data_path

log = logging.getLogger('otc_tracker')

_CONF_INTERNAL_RE = re.compile(r'J\.?P\.?\s*MORGAN|LAWTON', re.IGNORECASE)
# A confirmação só pode ser gerada quando as operações estão com status
# Success (registro concluído); Canceled nunca conta para nada.
_CONF_GEN_ELIGIBLE_STATUS = 'Success'
_CONF_MONTHS_PT = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                   'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
# Código de mês dos contratos futuros (Jan..Dez) — usado no texto do CO1-2.
_CONF_FUT_MONTH_CODE = {1: 'F', 2: 'G', 3: 'H', 4: 'J', 5: 'K', 6: 'M',
                        7: 'N', 8: 'Q', 9: 'U', 10: 'V', 11: 'X', 12: 'Z'}
# Normalizações de tickers legados (herdadas da macro).
_CONF_TICKER_MAP = {'NACX0005': 'VLSFO (AMFSA00)', 'PEURNPHY': 'PAAL00',
                    'PCRUDTB1': 'PCAAS00'}

_conf_subj_cache = {'mtime': None, 'map': {}}


def _conf_subjacente_map():
    """Subjacente.json indexado pelo código do ativo → bolsa/fator/mercadoria.
    Cache por mtime (o arquivo muda pouco e tem ~8k registros).

    O caminho sai do `data_path` — antes era montado do `__file__` e apontava
    para `apps/Subjacente.json`, um arquivo que não existe em lugar nenhum (o
    real está em `apps/static/data/`). O `getmtime` estourava, a função devolvia
    `{}` e TODA operação saía com o aviso "Ativo X sem cadastro no Subjacente
    (bolsa/fator ausentes)" — inclusive as que estão cadastradas. O mapa nunca
    teve uma linha, e nada na tela dizia isso: o aviso parecia um cadastro
    faltando, e a bolsa e o fator sumiam da confirmação em silêncio.

    Sem o arquivo o mapa continua vazio e o aviso volta a ser verdadeiro — mas
    agora ele também DIZ que o problema é o arquivo, e não o cadastro."""
    fp = data_path('Subjacente.json')
    try:
        mt = os.path.getmtime(fp)
    except OSError:
        log.warning('[conf] Subjacente.json não encontrado em %s — toda operação '
                    'vai sair com "sem cadastro no Subjacente".', fp)
        return {}
    if _conf_subj_cache['mtime'] == mt:
        return _conf_subj_cache['map']
    out = {}
    try:
        from apps.pages import duck_read
        for rec in duck_read.dataset_rows(fp):
                if not isinstance(rec, dict):
                    continue
                code = str(rec.get('Codigo do Ativo Subjacente') or '').strip()
                if not code:
                    continue
                out.setdefault(code, {
                    'bolsa':      str(rec.get('Bolsa de Negociacao') or '').strip(),
                    'fator':      rec.get('Fator Conversao'),
                    'mercadoria': str(rec.get('Commodity') or '').strip(),
                })
    except Exception:
        log.error('[conf] Subjacente.json load failed:\n%s', traceback.format_exc())
        return {}
    _conf_subj_cache['mtime'] = mt
    _conf_subj_cache['map'] = out
    return out


def _conf_fmt_date(v):
    from apps.pages import routes
    d = routes._parse_date_any(v)
    return d.strftime('%d/%m/%Y') if d else str(v or '').strip()


def _conf_date_extenso(v):
    from apps.pages import routes
    d = routes._parse_date_any(v)
    if not d:
        return str(v or '').strip()
    return '{:02d} de {} de {}'.format(d.day, _CONF_MONTHS_PT[d.month - 1], d.year)


def _conf_fmt_cnpj(v):
    digits = re.sub(r'\D', '', str(v or ''))
    if len(digits) > 14 and digits.endswith('0'):   # sobra de '.0' de planilha
        digits = digits[:14]
    if len(digits) != 14:
        return str(v or '').strip()
    return '{}.{}.{}/{}-{}'.format(digits[:2], digits[2:5], digits[5:8],
                                   digits[8:12], digits[12:])


def _conf_to_float(v):
    s = str(v if v is not None else '').strip().replace(' ', '')
    if not s:
        return None
    # "1.234,56" (BR) vs "1,234.56" (US) vs "1234.56"
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') \
            else s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def _conf_fmt_num(v, dec=4):
    """Formato pt-BR: milhar '.', decimal ','. dec=None mantém 0–4 casas."""
    n = _conf_to_float(v)
    if n is None:
        return str(v or '').strip()
    if dec is None:
        dec = 0 if float(n).is_integer() else 4
    s = '{:,.{d}f}'.format(n, d=dec)
    return s.replace(',', '\x00').replace('.', ',').replace('\x00', '.')


def _conf_prev_biz(dt, n):
    """dt recuado n dias úteis ANBIMA (espelho de _anbima_add_biz)."""
    from apps.pages import routes
    hols, cur, left = routes._anbima_holidays(), dt, n
    while left > 0:
        cur -= timedelta(days=1)
        if cur.weekday() < 5 and cur.strftime('%Y-%m-%d') not in hols:
            left -= 1
    return cur


def _conf_load_ndfcomm(ref):
    """Deals do day-file de NDF Commodities da reference date (lista de dicts)."""
    from apps.pages import routes
    fname = ref.strftime('%Y%m%d') + '_ndfcomm.json'
    fp = os.path.join(routes.NDF_COMM_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'), fname)
    if not os.path.isfile(fp):
        return []
    try:
        from apps.pages import duck_read
        data = duck_read.day_records(fp)
        return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []
    except Exception:
        log.warning('[conf] cannot read %s', fp)
        return []


def _conf_deal_family(deal, subj):
    """Família de template de um deal: strike-usd | brl | brl-platts | platts | palm-oil."""
    ccy = str(deal.get('StrikeCurrency') or '').strip().upper()
    is_brl = ccy in ('BRR', 'BRL')
    merc = str(deal.get('Commodities') or (subj or {}).get('mercadoria') or '').strip().upper()
    bolsa = str((subj or {}).get('bolsa') or '').upper()
    is_platts = 'BLOOMB' in bolsa          # na macro: exchange "BLOOMBGERG" = Platts
    if merc == 'OLEO DE PALMA EM USD':
        return 'palm-oil'
    if is_brl and is_platts:
        return 'brl-platts'
    if is_brl:
        return 'brl'
    if is_platts:
        return 'platts'
    return 'strike-usd'


# ── Estado das confirmações (ciclo próprio: New → Generated → Success) ───────
# Persistido por reference date em day-files próprios; a chave é o grupo
# (acronym | mercadoria | família). Generated = Word+PDF salvos no Inventory;
# Success = validado na janela de checklist com o preview do PDF.
CONF_STATE_DIR = os.path.normpath(os.path.join(
    data_dir(), "cache", "confirmations", "ndf-comm"
))


def _conf_state_path(ref, product='ndf-comm'):
    base = os.path.join(os.path.dirname(CONF_STATE_DIR), product)
    return os.path.join(base, ref.strftime('%Y'), ref.strftime('%m'),
                        ref.strftime('%Y%m%d') + '_conf.json')


def _conf_key(acr, merc, fam):
    return '{}|{}|{}'.format(acr, merc, fam)


def _conf_state_load(ref, product='ndf-comm'):
    fp = _conf_state_path(ref, product)
    if not os.path.isfile(fp):
        return {}
    try:
        with open(fp, encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _conf_state_save(ref, state, product='ndf-comm'):
    """Os 4 callers já envolvem _conf_state_load + este save num `with
    _cache_lock` — é lá que o ciclo tem de ser atômico. O lock aqui é
    reentrante e serve de rede: gravação de estado nunca sai destravada."""
    from apps.pages import routes
    with routes._cache_lock:
        fp = _conf_state_path(ref, product)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        routes._atomic_write_json(fp, state)


def _conf_segregate(deals, family_fn, merc_fn=None):
    """Segregação das confirmações da data: um grupo por contraparte ×
    mercadoria × família de template (pontas internas fora, Canceled fora).
    Retorna (groups, status_counter, total_considerado).

    `merc_fn(deal)` troca o eixo do meio para produtos que não têm mercadoria:
    no NDF de moeda ele devolve a Moeda Base. Sem ele vale a regra histórica
    (Commodities → Subjacente → Underlying Asset). O eixo TEM de ser o mesmo
    aqui e no `_conf_pick_eligible`, senão a tela lista um grupo que a geração
    não encontra."""
    subj_map = _conf_subjacente_map()
    groups, statuses, total = {}, Counter(), 0
    for deal in deals:
        st = str(deal.get('Status') or 'New').strip() or 'New'
        if st == 'Canceled':
            continue
        client = str(deal.get('Client') or '').strip()
        if _CONF_INTERNAL_RE.search(client):
            continue                        # pontas banco/lawton não confirmam
        ua = str(deal.get('UnderlyingAsset') or '').strip()
        subj = subj_map.get(ua)
        merc = (str(merc_fn(deal) or '').strip().upper() if merc_fn else
                str(deal.get('Commodities') or (subj or {}).get('mercadoria') or ua or '').strip().upper())
        fam = family_fn(deal, subj)
        acr = str(deal.get('Acronym') or '').strip() or client or '(sem contraparte)'
        key = (acr, merc, fam)
        g = groups.setdefault(key, {
            'acronym': acr, 'client': client, 'mercadoria': merc, 'family': fam,
            'count': 0, 'eligible': 0, 'trades': [],
        })
        g['count'] += 1
        # Os identificadores das operações do grupo. É por eles que o Monitor
        # acha a confirmação na esteira: `Trade ID` de lá é o Deal para quase
        # todo produto e o B3 ID para o FWD Start, então os dois vão juntos.
        # Casar por contraparte × mercadoria seria um de-para por texto entre
        # dois cadastros que normalizam nomes de jeitos diferentes.
        for _c in ('Deal', 'B3_ID'):
            _v = str(deal.get(_c) or '').strip()
            if _v:
                g['trades'].append(_v)
        if not g['client'] and client:
            g['client'] = client
        if st == _CONF_GEN_ELIGIBLE_STATUS:
            g['eligible'] += 1
        statuses[st] += 1
        total += 1
    ordered = sorted(groups.values(),
                     key=lambda g: (g['acronym'], g['mercadoria'], g['family']))
    return ordered, statuses, total


def _conf_ndfcomm_groups(ref):
    return _conf_segregate(_conf_load_ndfcomm(ref), _conf_deal_family)


# A esteira continua o ciclo do documento — mas o ciclo do MONITOR termina no
# OTC. Depois do New → Generated → Success da geração vem só o Pending OTC:
# validado o OTC, a confirmação está 100% para o card/seção Confirmations e
# para o e-mail de pendências. Pending MO/FO é assunto do Confirmations
# Monitor, não daqui — o New Deals Monitor cobra a ação da mesa de OTC, e
# manter o grupo aberto por uma etapa que não é dela cobraria trabalho alheio.
# (`_conf_esteira_stages` traduz toda etapa depois do OTC para Ok.)
#
# Ordem da MENOS avançada para a mais: um grupo do New Deals cobre várias
# operações, e o grupo vale pela que está mais atrás — dizer 'Ok' porque UMA das
# dez foi validada esconderia as nove que faltam. As etapas de MO/FO seguem na
# lista por defesa: uma linha que escape da tradução não pode virar rank
# desconhecido.
_CONF_STAGE_ORDER = ('Pending OTC', 'Pending MO/FO', 'Pending MO', 'Pending FO', 'Ok')


def _conf_esteira_stages():
    """Trade ID → etapa da esteira, de TODAS as linhas (pendentes e concluídas).

    Uma leitura só por request: o Monitor tem quatro cards de confirmação e
    dezenas de grupos, e um `find_row` por operação abriria o DuckDB uma vez por
    trade. Falha em silêncio devolvendo {} — sem a esteira o card volta a mostrar
    o status do documento, que é o que ele mostrava antes.
    """
    out = {}
    try:
        from apps.pages import manual_conf as _mc
        for base in ('pending', 'ok'):
            for r in _mc.load_rows(base):
                tid = str(r.get(_mc.KEY_COLUMN, '') or '').strip()
                if not tid:
                    continue
                st = str(r.get('Pending', '') or '') or _mc.STATUS_OK
                # Só o Pending OTC segura o grupo aberto no Monitor: validado o
                # OTC, a confirmação conta como 100% aqui e no e-mail de
                # pendências — Pending MO/FO segue vivo no Confirmations
                # Monitor, que é de quem essa etapa é.
                out[tid] = st if st == _mc.PENDING_OTC else _mc.STATUS_OK
    except Exception:
        log.warning('[deals-monitor] não consegui ler a esteira:\n%s', traceback.format_exc())
    return out


def _conf_group_stage(group, stages):
    """A etapa da esteira de UM grupo, ou None se nenhuma operação dele chegou lá.

    Vale a operação MENOS avançada (ver `_CONF_STAGE_ORDER`). Operação que ainda
    não entrou na esteira não conta: o grupo do New Deals nasce antes dela, e
    tratá-la como 'atrasada' pintaria de vermelho um documento recém-gerado.
    """
    def rank(s):
        # Etapa fora da lista fica no fim: uma etapa nova que ninguém mapeou aqui
        # não pode segurar o grupo inteiro no vermelho.
        return _CONF_STAGE_ORDER.index(s) if s in _CONF_STAGE_ORDER else len(_CONF_STAGE_ORDER)

    pior = None
    for tid in (group.get('trades') or ()):
        st = stages.get(tid)
        if not st:
            continue
        if pior is None or rank(st) < rank(pior):
            pior = st
    return pior


def _conf_stage_counts(groups, doc_state, key_fn=None, stages=None):
    """Os chips do card: um por grupo, na etapa em que ele está.

    A etapa da esteira VENCE o status do documento quando existe — ela é o passo
    seguinte do mesmo ciclo, e mostrar 'Generated' numa confirmação que já está
    em Pending MO seria parar o relógio na metade.

    `stages` vem de fora porque o Monitor monta QUATRO cards por request: lido
    aqui dentro, o índice da esteira abriria os dois DuckDB oito vezes na mesma
    tela.
    """
    if stages is None:
        stages = _conf_esteira_stages() if any(g.get('trades') for g in groups) else {}
    counts = Counter()
    for g in groups:
        st = _conf_group_stage(g, stages)
        if not st:
            entry = (doc_state.get(key_fn(g)) if key_fn else None) or {}
            st = entry.get('status') or 'New'
        counts[st] += 1
    return dict(counts)


def _conf_co12_text(deal, index):
    """Texto dinâmico do ticker CO1-2 (Brent rolling), portado da macro:
    mercados CO<letra><dígito do ano> dos dois meses seguintes ao settlement.

    **Quantas Datas de Verificação são do SEGUNDO futuro depende do mês** (§178):

      * dezembro  → as **duas últimas** (última e penúltima);
      * demais    → só a **última**.

    O código aplicava a regra de dezembro o ano inteiro, então em qualquer outro
    mês a penúltima data saía apontada para o segundo futuro — um dia a mais de
    rolagem do que a operação tem.

    Quem decide o mês é a **última** Data de Verificação (a Data Final de
    Verificação de Mercadoria), que é a data em que a rolagem acontece. Uma
    janela que atravessa a virada do ano (verificações em dezembro terminando em
    janeiro) cai na regra do mês de janeiro, que é o mês do dia que rola.
    """
    from apps.pages import routes
    settle = routes._parse_date_any(deal.get('SettlementDate'))
    refd = routes._parse_date_any(deal.get('FixingEndDate'))
    if not settle or not refd:
        return 'CO1-2'

    def _mkt(offset):
        m = settle.month + offset
        y = settle.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        letter = _CONF_FUT_MONTH_CODE.get(m, '?')
        return 'CO{}{}'.format(letter, str(y)[-1])

    if refd.month == 12:
        corte = _conf_prev_biz(refd, 2)
        segundo = ('para as Datas de Verificação em {} e {}, significa {}'
                   .format(_conf_prev_biz(refd, 1).strftime('%d/%m/%Y'),
                           refd.strftime('%d/%m/%Y'), _mkt(2)))
    else:
        corte = _conf_prev_biz(refd, 1)
        segundo = ('para a Data de Verificação em {}, significa {}'
                   .format(refd.strftime('%d/%m/%Y'), _mkt(2)))

    return ('Para as Datas de Verificação entre a Data Inicial de Verificação de Mercadoria e '
            '{} significa {} e {}'.format(corte.strftime('%d/%m/%Y'), _mkt(1), segundo))


def _conf_cgd_lookup(first):
    """Data do CGD da contraparte (CounterpartyDetails, primeiro item Active),
    por extenso quando o valor cadastrado é uma data."""
    from apps.pages import routes
    cgd_txt = ''
    try:
        rec = routes._cpd_find(routes._cpd_load(), str(first.get('SPN') or '').strip())
        for item in routes._cgd_norm((rec or {}).get('CGD')):
            if (item.get('status') or 'Active') == 'Active' and item.get('value'):
                cgd_txt = item['value']
                break
    except Exception:
        log.warning('[conf] CGD lookup failed:\n%s', traceback.format_exc())
    if cgd_txt and routes._parse_date_any(cgd_txt):
        cgd_txt = _conf_date_extenso(cgd_txt)
    return cgd_txt


# Palm Oil: no TERMO - PALM OIL.doc a bolsa e a taxa de conversão são texto
# fixo do documento (a macro escrevia as duas constantes, não o cadastro do
# Subjacente) — o Anexo II define a "MYR USD" nominalmente e o Anexo I cita a
# Bursa. Não é de-para: não há chave, é o texto legal desta família.
_CONF_PALMOIL_BOLSA = 'MDE-BURSA MALAYSIA'
_CONF_PALMOIL_TAXA_CONV = 'MYR USD'

# Famílias com template web disponível: template Jinja + rota de geração.
# (brl-platts entra quando o respectivo .doc for enviado.)
_CONF_FAMILY_TEMPLATES = {
    'strike-usd': ('confirmations/ndf-comm-strike-usd.html',        '/confirmation/ndf-comm/strike-usd'),
    'platts':     ('confirmations/ndf-comm-platts-strike-usd.html', '/confirmation/ndf-comm/platts-strike-usd'),
    'brl':        ('confirmations/ndf-comm-strike-brl.html',        '/confirmation/ndf-comm/strike-brl'),
    'palm-oil':   ('confirmations/ndf-comm-palmoil-strike-myrusd.html',
                   '/confirmation/ndf-comm/palmoil-strike-myrusd'),
}


def _conf_sort_key_venc(item):
    """Ordena a Tabela de Referência pela Data de Vencimento, do vencimento mais
    próximo ao mais distante. Deal sem data parseável vai para o fim em vez de
    virar 'ano 1' e encabeçar a tabela; o sort do Python é estável, então
    vencimentos iguais mantêm a ordem em que o deal entrou no cache."""
    from apps.pages import routes
    d = routes._parse_date_any((item[0] or {}).get('SettlementDate'))
    return (1, datetime.max.date()) if d is None else (0, d)


def _conf_pick_eligible(deals, acr, merc, family, family_fn, merc_fn=None):
    """Deals elegíveis (status Success, pontas internas fora) de um grupo
    contraparte × mercadoria × família → [(deal, subj)], **ordenados por Data de
    Vencimento**: é assim que as linhas saem no Anexo I das confirmações e é
    também a ordem em que o XML soma as operações."""
    subj_map = _conf_subjacente_map()
    picked = []
    for deal in deals:
        st = str(deal.get('Status') or 'New').strip() or 'New'
        if st != _CONF_GEN_ELIGIBLE_STATUS:
            continue
        client = str(deal.get('Client') or '').strip()
        if _CONF_INTERNAL_RE.search(client):
            continue
        ua = str(deal.get('UnderlyingAsset') or '').strip()
        subj = subj_map.get(ua)
        d_merc = (str(merc_fn(deal) or '').strip().upper() if merc_fn else
                  str(deal.get('Commodities') or (subj or {}).get('mercadoria') or ua or '').strip().upper())
        d_acr = str(deal.get('Acronym') or '').strip() or client or '(sem contraparte)'
        if d_acr != acr or d_merc != merc:
            continue
        if family_fn(deal, subj) != family:
            continue
        picked.append((deal, subj))
    picked.sort(key=_conf_sort_key_venc)
    return picked


def _conf_pick_ndfcomm(ref, acr, merc, family):
    return _conf_pick_eligible(_conf_load_ndfcomm(ref), acr, merc, family,
                               _conf_deal_family)


def _conf_generation_page(family):
    """Renderiza a confirmação pré-preenchida (família dada) para um grupo
    contraparte × mercadoria da reference date. O template mantém o painel de
    edição — o usuário revisa/ajusta, imprime e salva no Inventory."""
    from apps.pages import routes
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ds = (request.args.get('date') or '').strip()
    acr = (request.args.get('acronym') or '').strip()
    merc = (request.args.get('mercadoria') or '').strip().upper()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()

    picked = _conf_pick_ndfcomm(ref, acr, merc, family)

    if not picked:
        return ('Nenhuma operação elegível para essa confirmação '
                '(contraparte {} × {} em {}).'.format(acr, merc, ref.strftime('%d/%m/%Y')), 404)

    first = picked[0][0]
    rows, warnings = [], []
    for i, (deal, subj) in enumerate(picked, start=1):
        ua = str(deal.get('UnderlyingAsset') or '').strip()
        ticker = _CONF_TICKER_MAP.get(ua, ua)
        if ua == 'CO1-2':
            ticker = _conf_co12_text(deal, i)
        fator = _conf_to_float((subj or {}).get('fator'))
        strike = _conf_to_float(deal.get('Strike'))
        forward = _conf_fmt_num(strike * (fator if fator else 1.0)) if strike is not None \
            else str(deal.get('Strike') or '').strip()
        f_ini = routes._parse_date_any(deal.get('FixingStartDate'))
        f_fim = routes._parse_date_any(deal.get('FixingEndDate'))
        bullet = bool(f_ini and f_fim and f_ini == f_fim)
        direction = str(deal.get('Direction') or '').strip().upper()
        row = {
            'num':       str(deal.get('Deal') or '').strip(),
            'comprador': 'Parte B' if direction.startswith('S') else 'Parte A',
            'ticker':    ticker,
            # No Platts a coluna é "Fonte de Divulgação" e o valor é PLATTS;
            # no Palm Oil a bolsa é fixa (a macro escrevia a constante, não o
            # cadastro do Subjacente — o documento cita a Bursa nominalmente).
            'bolsa':     'PLATTS' if family == 'platts'
                         else _CONF_PALMOIL_BOLSA if family == 'palm-oil'
                         else str((subj or {}).get('bolsa') or '').strip(),
            'qtd':       _conf_fmt_num(str(deal.get('TotalNotional') or '').replace('-', ''), dec=None),
            'premio':    'Não Aplicável',
            'devedor':   'Não Aplicável',
            'dtPremio':  'Não Aplicável',
            'forward':   forward,
            'dtIni':     'Não Aplicável' if bullet else _conf_fmt_date(deal.get('FixingStartDate')),
            'dtFim':     _conf_fmt_date(deal.get('FixingEndDate')),
            'dtVenc':    _conf_fmt_date(deal.get('SettlementDate')),
        }
        if family == 'palm-oil':
            # Três colunas a mais no Anexo I. A Data de Verificação da Taxa de
            # Conversão é a Data Final de Verificação da Mercadoria (na macro,
            # os dois campos saem do mesmo values[17]) — inclusive no bullet,
            # onde só a data INICIAL vira 'Não Aplicável'.
            row['bbg'] = 'Não Aplicável'
            row['taxaConv'] = _CONF_PALMOIL_TAXA_CONV
            row['dtTaxaConv'] = _conf_fmt_date(deal.get('FixingEndDate'))
        if family == 'brl':
            # BRL: janela de verificação da USD PTAX = janela de fixing (macro
            # legada usava as mesmas datas); bullet zera a inicial também.
            row['ptaxIni'] = 'Não Aplicável' if bullet else _conf_fmt_date(deal.get('FixingStartDate'))
            row['ptaxFim'] = _conf_fmt_date(deal.get('FixingEndDate'))
        else:
            row['ptax'] = _conf_fmt_date(deal.get('FXConvDate'))
        rows.append(row)
        if subj is None:
            warnings.append('Ativo {} sem cadastro no Subjacente (bolsa/fator ausentes).'.format(ua))

    # CGD da contraparte (CounterpartyDetails, primeiro item Active).
    cgd_txt = _conf_cgd_lookup(first)
    if not cgd_txt:
        warnings.append('CGD não cadastrado no Reference Data — preencha no painel.')

    trade_date = first.get('TradeDate') or ref
    conf = {
        'ref_date':     ref.strftime('%Y-%m-%d'),
        'cgd_date':     cgd_txt,
        'parteb_nome':  str(first.get('Client') or '').strip(),
        'parteb_cnpj':  _conf_fmt_cnpj(first.get('TaxID')),
        'data_neg':     _conf_fmt_date(trade_date),
        'data_extenso': _conf_date_extenso(trade_date),
        'mercadoria':   merc,
        'acronym':      acr,
        'rows':         rows,
        'warnings':     warnings,
    }
    return render_template(_CONF_FAMILY_TEMPLATES[family][0], conf=conf)


# ── XML do contrato (FepWeb) por confirmação ─────────────────────────────────
# Cada confirmação gerada produz um XML de mesmo nome-base do documento na mesma
# pasta.
#
# A moeda do XML NÃO é o ISO-4217 numérico: é o "código de cadastro" do BACEN,
# que a tabela Currency Base (/mapping) já registra por moeda — USD é 220 e não
# 840, BRL é 790 e não 986. Havia um dicionário ISO fixo aqui, e era ele que
# punha 840 no arquivo. Fora estar errado, era um de-para no código: o mapping
# é a fonte, e uma moeda nova passa a valer sem release.
_CONF_CNPJ_BANCO = '33172537000198'


def _conf_ccy_num(ccy):
    """Código de cadastro (3 dígitos) da moeda pelo mapping Currency Base.

    Aceita o SIMBOLO (USD) e o ATHENA CODE (USB, BRR) — o cache de deals traz
    ora um, ora outro. Vazio quando a moeda não está cadastrada; quem chama
    avisa, em vez de inventar um código."""
    from apps.pages import routes
    s = str(ccy or '').strip().upper()
    if not s:
        return ''
    code = routes._moeda_num_code(s)
    if code:
        return code
    ath, _weak, _inv = routes._mapping_ccy_maps()          # Athena → ISO
    return routes._moeda_num_code(ath.get(s, '')) if ath.get(s) else ''


def _conf_ccy_is_brl(ccy):
    """True para a moeda nacional em qualquer das grafias que aparecem nos
    caches (BRL, BRR e o próprio código de cadastro 790)."""
    from apps.pages import routes
    s = str(ccy or '').strip().upper()
    if s in ('BRL', 'BRR', '790'):
        return True
    ath, _weak, _inv = routes._mapping_ccy_maps()
    return ath.get(s, '') == 'BRL'


def _conf_strike_adj(deal, subj):
    """Strike ajustado pelo quoted-in-cents (Fator Conversão do Subjacente
    quando cadastrado; senão /100 quando o deal está marcado YES)."""
    strike = _conf_to_float(deal.get('Strike'))
    if strike is None:
        return None
    fator = _conf_to_float((subj or {}).get('fator'))
    if fator:
        return strike * fator
    if str(deal.get('QuotedInCents') or '').strip().upper() == 'YES':
        return strike / 100.0
    return strike


def _conf_fx_legs(deal, subj):
    """(valorEstrangeiro, valor em BRL) de uma perna de NDF de MOEDA.

    No termo de MERCADORIA o notional é uma QUANTIDADE e o strike um preço, então
    `quantidade × preço` é o valor da perna. No termo de MOEDA isso não vale: o
    notional já é um VALOR — em uma das duas moedas — e o strike é a taxa de
    câmbio entre elas. Aplicar a fórmula da mercadoria aqui multiplicaria
    dólares pela taxa e chamaria o resultado, que está em reais, de "valor
    estrangeiro".

    Por isso o strike converte, e o sentido depende de em que moeda o notional
    veio: cotado em BRL, o strike leva à moeda base (divide); cotado na moeda
    base, ele leva ao real (multiplica). Sem strike não há conversão possível e
    a perna fica de fora, com aviso — é o caso do forward start ainda não
    fixado."""
    qty = _conf_to_float(str(deal.get('Notional') or '').replace('-', ''))
    strike = _conf_to_float(deal.get('Strike'))
    if qty is None or not strike:
        return None
    if _conf_ccy_is_brl(str(deal.get('QuantityCurrency') or '')):
        return qty / strike, qty
    return qty, qty * strike


def _conf_ndf_xml(picked, merc, ref, tipo='NDF', prefixo='NDF_Comm',
                  ccy_field='StrikeCurrency', warn_no_spot=True, legs_fn=None, ccy=None):
    """(numero_contrato, xml_string, warnings) do grupo de deals da confirmação.

    valor            = Σ notional × strike ajustado × Spot FXRate
    valorEstrangeiro = Σ notional × strike ajustado
    numeroContrato   = DealName quando a confirmação tem 1 operação
                       (Mondelez: DealName_Mercadoria); com várias,
                       <prefixo>_YYYYMMDD_Mercadoria.
    Opções de Commodities usam o mesmo contrato com tipo='OPTION' e
    prefixo='Opt_Comm' — o resto do padrão é idêntico ao NDF. O tipo vai em
    MAIÚSCULO como o `NDF`: é o que o FepWeb lê, e o `Option` com inicial
    maiúscula era a única saída do app fora desse padrão.
    Opções de Câmbio (FXO) usam prefixo='Opt_FXO' e leem a moeda do
    ccy_field='UnderlyingAsset'; nelas o strike já é a cotação em BRL, então
    não há Spot FXRate para buscar e warn_no_spot=False cala o aviso que só
    faria sentido em commodities."""
    from apps.pages import routes
    warnings = []
    first = picked[0][0]
    trade_dt = routes._parse_date_any(first.get('TradeDate')) or ref
    merc_tag = re.sub(r'\s+', '_', str(merc or '').strip().upper())

    if len(picked) > 1:
        numero = '{}_{}_{}'.format(prefixo, trade_dt.strftime('%Y%m%d'), merc_tag)
    else:
        numero = str(first.get('Deal') or '').strip() or \
            '{}_{}_{}'.format(prefixo, trade_dt.strftime('%Y%m%d'), merc_tag)
        if 'MONDELEZ' in str(first.get('Client') or '').upper():
            numero = numero + '_' + merc_tag

    # `ccy` explícito ganha do campo: no termo de moeda a moeda do XML é a Moeda
    # Base do grupo, que é derivada do par (não há um campo do deal com ela).
    ccy = str(ccy or first.get(ccy_field) or '').strip().upper()
    # Strike em Reais não tem perna estrangeira: moedaEstrangeira e
    # valorEstrangeiro saem VAZIOS (preenchê-los com 790/valor em BRL declararia
    # uma operação em moeda estrangeira que não existe).
    is_brl = _conf_ccy_is_brl(ccy)
    ccy_num = '' if is_brl else _conf_ccy_num(ccy)
    if not is_brl and not ccy_num:
        warnings.append('Moeda do strike "{}" sem código de cadastro na tabela Currency Base '
                        '(/mapping) — moedaEstrangeira ficou vazia no XML.'.format(ccy))

    valor = 0.0
    valor_estr = 0.0
    venc = None
    for deal, subj in picked:
        # `legs_fn` troca a aritmética da perna (o termo de moeda não é
        # quantidade × preço, ver _conf_fx_legs); sem ele vale a da mercadoria.
        if legs_fn:
            legs = legs_fn(deal, subj)
            if legs is None:
                warnings.append('Operação {}: sem notional/strike numérico — fora dos valores '
                                'do XML.'.format(deal.get('Deal')))
                continue
            valor_estr += legs[0]
            valor += legs[1]
        else:
            qty = _conf_to_float(str(deal.get('TotalNotional') or '').replace('-', ''))
            strike_adj = _conf_strike_adj(deal, subj)
            if qty is None or strike_adj is None:
                warnings.append('Operação {}: notional/strike não numérico — fora dos valores do XML.'
                                .format(deal.get('Deal')))
                continue
            leg = qty * strike_adj
            valor_estr += leg
            spot = _conf_to_float(deal.get('SpotFXRate'))
            if spot is None:
                spot = 1.0
                if warn_no_spot and ccy not in ('BRL', 'BRR'):
                    warnings.append('Operação {}: sem Spot FXRate — valor em BRL ficou igual ao '
                                    'estrangeiro.'.format(deal.get('Deal')))
            valor += leg * spot
        sd = routes._parse_date_any(deal.get('SettlementDate'))
        if sd and (venc is None or sd > venc):
            venc = sd

    cnpj_cli = re.sub(r'\D', '', str(first.get('TaxID') or ''))
    if len(cnpj_cli) != 14:
        warnings.append('CNPJ da contraparte fora do padrão (14 dígitos): "{}".'
                        .format(first.get('TaxID')))

    return numero, _conf_xml_doc(numero, tipo, valor, ccy_num,
                                 '' if is_brl else valor_estr, cnpj_cli,
                                 trade_dt, venc), warnings


def _conf_xml_doc(numero, tipo, valor, ccy_num, valor_estr, cnpj_cli, trade_dt, venc):
    """XML do contrato. `valor_estr` vazio (strike em BRL) sai como tag vazia,
    igual aos campos que o FepWeb já recebe em branco."""
    return (
        '<contrato>\n'
        '  <numeroContrato>{numero}</numeroContrato>\n'
        '  <tipoOperacao>{tipo}</tipoOperacao>\n'
        '  <tipoEvento>N</tipoEvento>\n'
        '  <valor>{valor:.2f}</valor>\n'
        '  <moedaEstrangeira>{ccy}</moedaEstrangeira>\n'
        '  <valorEstrangeiro>{valor_estr}</valorEstrangeiro>\n'
        '  <codigoNatureza></codigoNatureza>\n'
        '  <descricaoNatureza></descricaoNatureza>\n'
        '  <pagadorRecebidorExterior></pagadorRecebidorExterior>\n'
        '  <cnpjBanco>{cnpj_banco}</cnpjBanco>\n'
        '  <cnpjCliente>{cnpj_cli}</cnpjCliente>\n'
        '  <cnpjCorretora></cnpjCorretora>\n'
        '  <dataOperacao>{dt_op}</dataOperacao>\n'
        '  <dataVencimento>{dt_venc}</dataVencimento>\n'
        '</contrato>\n'
    ).format(numero=numero, tipo=tipo, valor=valor, ccy=ccy_num,
             valor_estr=('{:.2f}'.format(valor_estr) if valor_estr != '' else ''),
             cnpj_banco=_CONF_CNPJ_BANCO, cnpj_cli=cnpj_cli,
             dt_op=trade_dt.strftime('%Y%m%d'),
             dt_venc=venc.strftime('%Y%m%d') if venc else '')

def _conf_pc_set_fepweb(trade_numbers, numero):
    """Grava o numeroContrato na coluna FepWeb ID das linhas do Pending
    Confirmation cujo Trade Number é uma das operações da confirmação
    (linhas de NDF Comm são chaveadas pelo Deal name). Varre os 3 DBs."""
    from apps.pages import routes
    tns = [str(t or '').strip() for t in trade_numbers if str(t or '').strip()]
    if not tns:
        return 0
    updated = 0
    placeholders = ', '.join('?' for _ in tns)
    for fname in routes._PC_DBS.values():
        path = os.path.join(routes._PC_DB_DIR, fname)
        if not os.path.isfile(path):
            continue
        try:
            with routes.duckdb_write(path) as con:
                before = con.execute(
                    'SELECT count(*) FROM {} WHERE trim("Trade Number") IN ({})'
                    .format(routes._PC_TABLE, placeholders), tns).fetchone()[0]
                if before:
                    con.execute(
                        'UPDATE {} SET "FepWeb ID" = ? WHERE trim("Trade Number") IN ({})'
                        .format(routes._PC_TABLE, placeholders), [numero] + tns)
                    updated += before
        except Exception:
            log.warning('[conf] FepWeb ID update failed em %s:\n%s', fname,
                        traceback.format_exc())
    return updated


def _conf_state_entry_or_404(args, product='ndf-comm'):
    """(ref, key, entry, err_response) para os endpoints de validação/preview."""
    ds = (args.get('date') or '').strip()
    acr = (args.get('acronym') or '').strip()
    merc = (args.get('mercadoria') or '').strip().upper()
    fam = (args.get('family') or 'strike-usd').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    key = _conf_key(acr, merc, fam)
    entry = _conf_state_load(ref, product).get(key)
    if not entry:
        return ref, key, None, ('Confirmação ainda não gerada para {} × {} em {}.'
                                .format(acr, merc, ref.strftime('%d/%m/%Y')), 404)
    return ref, key, entry, None


# ==============================================================================
# NEW DEALS — CONFIRMATIONS (Commodities Options · Opção de Commodities)
# Mesmo fluxo do NDF Commodities (segregação contraparte × mercadoria ×
# família, ciclo New → Generated → Success, Word+PDF+XML no Inventory), portado
# da macro legada de opções (criar_documento/process_documents). Diferenças:
# a coluna Nº do Anexo I usa o Deal name (opção não tem mais mnemônico), o
# ticker CO1-2 tem template legado próprio (família 'co1-2', pendente) e o XML
# sai com tipoOperacao Option e prefixo Opt_Comm no numeroContrato — o resto
# do padrão do contrato é idêntico ao do NDF.
# ==============================================================================

_CONF_OPT_FAMILY_TEMPLATES = {
    'strike-usd': ('confirmations/opt-comm-strike-usd.html', '/confirmation/opt-comm/strike-usd'),
    # Strike em BRL: MESMO texto legal do documento em USD (conferido palavra a
    # palavra contra o OPÇÃO COMMODITY - BRL.doc). O que muda é só o cabeçalho
    # do Anexo I — "Preço de Exercício i (em R$)", e os subscritos i de Tipo da
    # Opção / Quantidade / Data de Exercício. A cláusula da USD PTAX continua
    # valendo, porque ela trata do preço da MERCADORIA cotada em dólar, não do
    # strike; por isso a coluna de Data de Verificação da PTAX segue única aqui
    # (diferente do Termo em BRL, que tem a janela inicial/final).
    'brl':        ('confirmations/opt-comm-strike-brl.html', '/confirmation/opt-comm/strike-brl'),
    # Palm oil: o Anexo I ganha três colunas (Código da Bloomberg, Taxa de
    # Conversão da Mercadoria e a Data de Verificação dela) e o documento passa
    # a ter Anexo II — as mesmas do TERMO - PALM OIL.doc, porque a mercadoria é
    # cotada em MYR e o preço só vira USD dividido pela taxa de conversão.
    'palm-oil':   ('confirmations/opt-comm-palmoil-strike-myrusd.html',
                   '/confirmation/opt-comm/palmoil-strike-myrusd'),
}

# Família → variante do PDF (a réplica em reportlab). Sem entrada = 'usd'.
_CONF_OPT_PDF_VARIANT = {'brl': 'brl'}

# Famílias cujo PDF sai do HTML JÁ RENDERIZADO (`word_html_pdf`), e não da
# réplica em reportlab. É o padrão desde a Opção de Câmbio (§139) e o que vale
# para documento novo: o texto existe UMA vez, no template, em vez de ganhar uma
# segunda transcrição em Python que diverge na primeira revisão do jurídico.
# `opcao_pdf` continua servindo as duas famílias que nasceram antes disso.
_CONF_OPT_PDF_FROM_HTML = {'palm-oil'}


def _conf_load_optcomm(ref):
    """Deals do day-file de Option/Commodities da reference date."""
    from apps.pages import routes
    fname = ref.strftime('%Y%m%d') + '_optcomm.json'
    fp = os.path.join(routes.CACHE_BASE_DIR, ref.strftime('%Y'), ref.strftime('%m'), fname)
    if not os.path.isfile(fp):
        return []
    try:
        from apps.pages import duck_read
        data = duck_read.day_records(fp)
        return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []
    except Exception:
        log.warning('[conf] cannot read %s', fp)
        return []


def _conf_opt_family(deal, subj):
    """Família de template de uma opção: as mesmas do NDF + 'co1-2' (a macro
    legada tinha um OPÇÃO COMMODITY-CO1-2.doc próprio para o Brent rolling)."""
    if str(deal.get('UnderlyingAsset') or '').strip() == 'CO1-2':
        return 'co1-2'
    return _conf_deal_family(deal, subj)


def _conf_optcomm_groups(ref):
    return _conf_segregate(_conf_load_optcomm(ref), _conf_opt_family)


def _conf_pick_optcomm(ref, acr, merc, family):
    return _conf_pick_eligible(_conf_load_optcomm(ref), acr, merc, family,
                               _conf_opt_family)


def _conf_opt_generation_page(family):
    """Renderiza a confirmação de Opção pré-preenchida para um grupo
    contraparte × mercadoria da reference date (linhas no layout do Anexo I
    da macro legada de opções — 16 colunas)."""
    from apps.pages import routes
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ds = (request.args.get('date') or '').strip()
    acr = (request.args.get('acronym') or '').strip()
    merc = (request.args.get('mercadoria') or '').strip().upper()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()

    picked = _conf_pick_optcomm(ref, acr, merc, family)
    if not picked:
        return ('Nenhuma operação elegível para essa confirmação '
                '(contraparte {} × {} em {}).'.format(acr, merc, ref.strftime('%d/%m/%Y')), 404)

    first = picked[0][0]
    rows, warnings = [], []
    for i, (deal, subj) in enumerate(picked, start=1):
        ua = str(deal.get('UnderlyingAsset') or '').strip()
        ticker = _CONF_TICKER_MAP.get(ua, ua)
        # Mesmo texto de rolagem do Termo — a regra do primeiro × segundo futuro
        # é do ATIVO, não do produto (§178). O documento próprio do CO1-2 em
        # opção (família 'co1-2') ainda não existe; quando existir, já nasce com
        # o ticker certo em vez de repetir a regra numa terceira cópia.
        if ua == 'CO1-2':
            ticker = _conf_co12_text(deal, i)
        fator = _conf_to_float((subj or {}).get('fator'))
        strike = _conf_to_float(deal.get('Strike'))
        # Preço de Exercício = strike × Fator Conversão (mesma regra da Taxa
        # Forward do Termo; a macro usava strike_confirmation com o factor).
        strike_fmt = _conf_fmt_num(strike * (fator if fator else 1.0)) if strike is not None \
            else str(deal.get('Strike') or '').strip()
        premium = _conf_to_float(str(deal.get('Premium') or '').replace('-', ''))
        f_ini = routes._parse_date_any(deal.get('FixingStartDate'))
        f_fim = routes._parse_date_any(deal.get('FixingEndDate'))
        bullet = bool(f_ini and f_fim and f_ini == f_fim)
        direction = str(deal.get('Direction') or '').strip().upper()
        instrument = str(deal.get('Instrument') or '').upper()
        row = {
            'num':       str(deal.get('Deal') or '').strip(),
            'tipo':      'Venda' if 'PUT' in instrument else 'Compra',
            'forma':     'Europeia',
            'ticker':    ticker,
            # No Palm Oil a bolsa é fixa, como no Termo: a macro escrevia a
            # constante e o documento cita a Bursa nominalmente.
            'bolsa':     'PLATTS' if family in ('platts', 'brl-platts')
                         else _CONF_PALMOIL_BOLSA if family == 'palm-oil'
                         else str((subj or {}).get('bolsa') or '').strip(),
            'qtd':       _conf_fmt_num(str(deal.get('TotalNotional') or '').replace('-', ''), dec=None),
            'ptax':      _conf_fmt_date(deal.get('FXConvDate')),
            'comprador': 'Parte B' if direction.startswith('S') else 'Parte A',
            'premio':    'R$ ' + _conf_fmt_num(premium, dec=2) if premium is not None
                         else str(deal.get('Premium') or '').strip() or 'Não Aplicável',
            'dtPremio':  _conf_fmt_date(deal.get('SpotDate')) or 'Não Aplicável',
            'strike':    strike_fmt,
            # Asiática: janela de verificação preenchida, Data de Exercício N/A;
            # bullet (europeia de fato): só a Data de Exercício (= fixing end).
            'dtIni':     'Não Aplicável' if bullet else _conf_fmt_date(deal.get('FixingStartDate')),
            'dtFim':     'Não Aplicável' if bullet else _conf_fmt_date(deal.get('FixingEndDate')),
            'dtExerc':   _conf_fmt_date(deal.get('FixingEndDate')) if bullet else 'Não Aplicável',
            'dtVenc':    _conf_fmt_date(deal.get('SettlementDate')),
        }
        if family == 'palm-oil':
            # As três colunas a mais do Anexo I, na mesma leitura do Termo: a
            # Data de Verificação da Taxa de Conversão é a Data Final de
            # Verificação da Mercadoria (o fixing end), inclusive no bullet —
            # ali é a Data de Exercício, e é a mesma data.
            row['bbg'] = 'Não Aplicável'
            row['taxaConv'] = _CONF_PALMOIL_TAXA_CONV
            row['dtTaxaConv'] = _conf_fmt_date(deal.get('FixingEndDate'))
        rows.append(row)
        if subj is None:
            warnings.append('Ativo {} sem cadastro no Subjacente (bolsa/fator ausentes).'.format(ua))

    cgd_txt = _conf_cgd_lookup(first)
    if not cgd_txt:
        warnings.append('CGD não cadastrado no Reference Data — preencha no painel.')

    trade_date = first.get('TradeDate') or ref
    conf = {
        'ref_date':     ref.strftime('%Y-%m-%d'),
        'cgd_date':     cgd_txt,
        'parteb_nome':  str(first.get('Client') or '').strip(),
        'parteb_cnpj':  _conf_fmt_cnpj(first.get('TaxID')),
        'data_neg':     _conf_fmt_date(trade_date),
        'data_extenso': _conf_date_extenso(trade_date),
        'mercadoria':   merc,
        'acronym':      acr,
        'rows':         rows,
        'warnings':     warnings,
    }
    return render_template(_CONF_OPT_FAMILY_TEMPLATES[family][0], conf=conf)


# ==============================================================================
# NEW DEALS — CONFIRMATIONS (FX Options · Opção de Câmbio)
# Mesmo fluxo dos outros produtos (segregação contraparte × moeda base ×
# família, ciclo New → Generated → Success, Word+PDF+XML no Inventory). O que
# muda aqui:
#   • a família vem do TradeType da operação (VANILLA / ASIAN) e não da moeda
#     do strike — são dois documentos diferentes, não duas variantes do mesmo;
#   • no Vanilla a Data de Exercício é a Last Fixing Date; no Asian ela é "Não
#     Aplicável" e quem aparece é o par Data Inicial / Data Final de
#     Verificação (First e Last Fixing Date);
#   • a "mercadoria" da segregação é a Moeda Base (Underlying Asset) — opção de
#     câmbio não tem mercadoria;
#   • o XML sai com tipoOperacao Option, prefixo Opt_FXO e a moeda estrangeira
#     lida do Underlying Asset.
# ==============================================================================

_CONF_FXO_FAMILY_TEMPLATES = {
    'vanilla': ('confirmations/option-fx-vanilla-strike-me.html', '/confirmation/opt-fxo/vanilla'),
    'asian':   ('confirmations/option-fx-asian-strike-me.html',   '/confirmation/opt-fxo/asian'),
}


def _conf_load_optfxo(ref):
    """Deals do day-file de Opção de Câmbio (FXO) da reference date."""
    from apps.pages import routes
    fname = ref.strftime('%Y%m%d') + '_optfxo.json'
    fp = os.path.join(routes.OPT_FXO_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'), fname)
    if not os.path.isfile(fp):
        return []
    try:
        from apps.pages import duck_read
        data = duck_read.day_records(fp)
        return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []
    except Exception:
        log.warning('[conf] cannot read %s', fp)
        return []


def _conf_fxo_family(deal, subj):
    """Família do template de uma opção de câmbio: o Trade Type da operação.
    Sem First/Last Fixing Date o import já classifica como VANILLA, então o
    default aqui vale para o deal digitado à mão sem o campo."""
    return 'asian' if str(deal.get('TradeType') or '').strip().upper() == 'ASIAN' else 'vanilla'


def _conf_optfxo_groups(ref):
    return _conf_segregate(_conf_load_optfxo(ref), _conf_fxo_family)


def _conf_pick_optfxo(ref, acr, merc, family):
    return _conf_pick_eligible(_conf_load_optfxo(ref), acr, merc, family,
                               _conf_fxo_family)


def _conf_fxo_strike(v):
    """Preço de Exercício: no mínimo 4 casas, mais do que isso quando a taxa
    tem — o cache grava sempre 6 ('{:.6f}'), então zero à direita que não
    significa nada sai fora antes do piso de 4 casas."""
    n = _conf_to_float(v)
    if n is None:
        return str(v or '').strip()
    dec = len(('{:.8f}'.format(abs(n)).rstrip('0').split('.') + [''])[1])
    return _conf_fmt_num(n, dec=max(4, dec))


def _conf_fxo_conv_rate(moeda):
    """(Taxa de Conversão, Tipo) da Moeda Base pelo mapping FXO Conversion Rate.

    O Anexo II do documento define uma taxa por moeda ("USD PTAX" é a de venda
    do dólar, "ARS MAE" a do peso etc.), então isto é de-para de cadastro, não
    constante de código: moeda nova entra pela tela /mapping."""
    from apps.pages import routes
    key = str(moeda or '').strip().upper()
    for row in routes._mapping_rows('fxo-conv-rate'):
        if str(row.get('MOEDA BASE') or '').strip().upper() == key:
            return (str(row.get('TAXA DE CONVERSAO') or '').strip(),
                    str(row.get('TIPO') or '').strip())
    return '', ''


def _conf_fxo_generation_page(family):
    """Renderiza a confirmação de Opção de Câmbio pré-preenchida para um grupo
    contraparte × moeda base da reference date."""
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ds = (request.args.get('date') or '').strip()
    acr = (request.args.get('acronym') or '').strip()
    merc = (request.args.get('mercadoria') or '').strip().upper()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()

    picked = _conf_pick_optfxo(ref, acr, merc, family)
    if not picked:
        return ('Nenhuma operação elegível para essa confirmação '
                '(contraparte {} × {} em {}).'.format(acr, merc, ref.strftime('%d/%m/%Y')), 404)

    first = picked[0][0]
    rows, warnings, sem_taxa = [], [], set()
    for deal, _subj in picked:
        moeda = str(deal.get('UnderlyingAsset') or '').strip()
        premium = _conf_to_float(str(deal.get('Premium') or '').replace('-', ''))
        direction = str(deal.get('Direction') or '').strip().upper()
        instrument = str(deal.get('Instrument') or '').upper()
        row = {
            'num':       str(deal.get('Deal') or '').strip(),
            # Option (Call) = a contraparte compra; Option (Put) = vende.
            'tipo':      'Venda' if 'PUT' in instrument else 'Compra',
            'forma':     'Europeia',
            'comprador': 'Parte B' if direction.startswith('S') else 'Parte A',
            'moedaBase': moeda,
            'valorBase': _conf_fmt_num(str(deal.get('TotalNotional') or '').replace('-', ''), dec=2),
            'premio':    'R$ ' + _conf_fmt_num(premium, dec=2) if premium is not None
                         else str(deal.get('Premium') or '').strip() or 'Não Aplicável',
            'dtPremio':  _conf_fmt_date(deal.get('SpotDate')) or 'Não Aplicável',
            'strike':    _conf_fxo_strike(deal.get('Strike')),
            'dtVenc':    _conf_fmt_date(deal.get('SettlementDate')),
        }
        if family == 'asian':
            # Asiática: a janela de verificação é o par First/Last Fixing Date
            # e a Data de Exercício não se aplica (é a Data Final, por definição
            # da cláusula 4.2.c — por isso a coluna sai "Não Aplicável").
            row['dtIni'] = _conf_fmt_date(deal.get('FixingStartDate'))
            row['dtFim'] = _conf_fmt_date(deal.get('FixingEndDate'))
            row['dtExerc'] = 'Não Aplicável'
            taxa, tipo_taxa = _conf_fxo_conv_rate(moeda)
            row['taxaConv'] = taxa
            row['tipoTaxaConv'] = tipo_taxa
            if not taxa:
                sem_taxa.add(moeda or '(sem moeda)')
        else:
            row['dtExerc'] = _conf_fmt_date(deal.get('FixingEndDate'))
        rows.append(row)
    if sem_taxa:
        warnings.append('Moeda {} sem Taxa de Conversão cadastrada (mapping FXO Conversion Rate) '
                        '— preencha as colunas no painel.'.format(', '.join(sorted(sem_taxa))))

    cgd_txt = _conf_cgd_lookup(first)
    if not cgd_txt:
        warnings.append('CGD não cadastrado no Reference Data — preencha no painel.')

    trade_date = first.get('TradeDate') or ref
    conf = {
        'ref_date':     ref.strftime('%Y-%m-%d'),
        'cgd_date':     cgd_txt,
        'parteb_nome':  str(first.get('Client') or '').strip(),
        'parteb_cnpj':  _conf_fmt_cnpj(first.get('TaxID')),
        'data_neg':     _conf_fmt_date(trade_date),
        'data_extenso': _conf_date_extenso(trade_date),
        'mercadoria':   merc,
        'acronym':      acr,
        'rows':         rows,
        'warnings':     warnings,
    }
    return render_template(_CONF_FXO_FAMILY_TEMPLATES[family][0], conf=conf)


# ==============================================================================
# CONFIRMAÇÕES — NDF FWD START (Termo de Moeda com início a termo)
# Porte do fluxo de FXO. As diferenças que importam:
#   • o eixo do meio da segregação é a MOEDA BASE (o termo de moeda não tem
#     mercadoria) — daí o `merc_fn` do `_conf_segregate`;
#   • a Taxa Forward NÃO existe na contratação: no forward start ela só é fixada
#     na Strike Set Date, e o documento a declara "Não Aplicável" para que a
#     cláusula 4.2.l.2 a calcule como câmbio da Data de Verificação + Pontos de
#     Termo. Por isso `Rate` chega vazio do import (§ _ndf_api_*) e Pontos de
#     Termo é o Strike Set Offset;
#   • o Nº do Anexo I é o B3 ID — o número que a B3 devolve DEPOIS do registro,
#     não o Deal interno. Sem registro a coluna sai vazia, que é o pedido de
#     "registra primeiro" em vez de um número que a contraparte não reconhece.
# ==============================================================================

_CONF_FWDSTART_FAMILY_TEMPLATES = {
    'strike-me': ('confirmations/ndf-fwdstart-strike-me.html',
                  '/confirmation/ndf-fwdstart/strike-me'),
}

# Parte A do documento — a entidade JPM da operação. Os dois textos são os que o
# Word imprimia lado a lado com "OR" (o documento saía pedindo para riscar um à
# mão); a escolha é pela LE do deal, que as páginas genéricas de NDF carregam
# (campo `LE`, resolvido do Settlement Location pelo `le-accronym`). A grafia é
# a do documento assinado, não a do Reference Data (`le-spn` guarda a do
# RefData) — por isso o texto vive aqui, ao lado do template, e não num mapping.
_CONF_FWDSTART_PARTEA = {
    'JPM': ('BANCO J.P. MORGAN S.A.', '33.172.537/0001-98'),
    'MGT': ('J.P. Morgan Chase Bank, N.A. – Filial Brasileira', '46.518.205/0001-64'),
}


def _conf_fwdstart_partea(picked, warnings):
    """(nome, cnpj) da Parte A pelo campo LE dos deals do grupo.

    Em branco + aviso quando a LE falta, é mista no grupo ou não é JPM/MGT —
    em branco pede preenchimento no painel; um default afirmaria uma entidade
    errada num documento que vai assinado para a contraparte."""
    les = {str(d.get('LE') or '').strip().upper() for d, _s in picked}
    les.discard('')
    if len(les) == 1:
        nome, cnpj = _CONF_FWDSTART_PARTEA.get(next(iter(les)), ('', ''))
        if nome:
            return nome, cnpj
    if len(les) > 1:
        warnings.append('Operações de Legal Entities diferentes no mesmo grupo ({}) — '
                        'preencha a Parte A no painel.'.format(', '.join(sorted(les))))
    elif les:
        warnings.append('Legal Entity {} sem Parte A definida — preencha o nome e o '
                        'CNPJ da Parte A no painel.'.format(next(iter(les))))
    else:
        warnings.append('Operações sem Legal Entity — preencha o nome e o CNPJ da '
                        'Parte A no painel.')
    return '', ''


def _conf_load_ndffwdstart(ref):
    """Deals do day-file de NDF FWD Start da reference date."""
    from apps.pages import routes
    cfg = routes._GENERIC_ND_PRODUCTS['fwd-start']
    fname = ref.strftime('%Y%m%d') + cfg['suffix']
    fp = os.path.join(cfg['dir'], ref.strftime('%Y'), ref.strftime('%m'), fname)
    if not os.path.isfile(fp):
        return []
    try:
        from apps.pages import duck_read
        data = duck_read.day_records(fp)
        return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []
    except Exception:
        log.warning('[conf] cannot read %s', fp)
        return []


def _conf_fwdstart_family(deal, subj):
    """Uma família só: o documento do termo de moeda a termo é único."""
    return 'strike-me'


def _conf_fwdstart_moeda(deal):
    """Moeda Base da operação — a moeda ESTRANGEIRA do par.

    A Moeda Cotada do documento é fixa em BRL (cláusula 3.d), então a Moeda Base
    é o outro lado: a Quantity Currency quando ela não é o real, senão a Other
    Quantity Currency. Ler sempre a Quantity Currency faria a confirmação de um
    deal cotado em BRL sair com "Moeda Base: BRL" — a moeda cotada nas duas
    colunas, e o Valor Base deixando de ser o montante em moeda estrangeira que
    a cláusula 4.2.m define."""
    qty = str(deal.get('QuantityCurrency') or '').strip().upper()
    other = str(deal.get('OtherQuantityCurrency') or '').strip().upper()
    if qty and qty != 'BRL':
        return qty
    return other or qty


def _conf_fwdstart_groups(ref):
    return _conf_segregate(_conf_load_ndffwdstart(ref), _conf_fwdstart_family,
                           merc_fn=_conf_fwdstart_moeda)


def _conf_pick_fwdstart(ref, acr, merc, family):
    return _conf_pick_eligible(_conf_load_ndffwdstart(ref), acr, merc, family,
                               _conf_fwdstart_family, merc_fn=_conf_fwdstart_moeda)


def _conf_fwdstart_rows(picked, warnings):
    """Linhas do Anexo I a partir dos deals escolhidos.

    As três colunas que só existem neste documento:
      * **Pontos de Termo** = Strike Set Offset — os pontos que se somam ao
        câmbio da Data de Verificação para formar a Taxa Forward;
      * **Data de Verificação da Taxa Forward** = Strike Set Date, o dia em que
        esse câmbio é lido;
      * **Data Efetiva** = Trade Date.

    A janela de verificação segue o cadastro: First Fixing vazio ou igual ao
    Last Fixing é uma janela de UM dia, e aí a Data Inicial sai "Não Aplicável"
    (cláusula 4.2.j). Imprimir a mesma data nas duas colunas diria que há uma
    média a apurar onde há uma cotação só."""
    from apps.pages import routes
    rows, sem_taxa, sem_b3 = [], set(), 0
    for deal, _subj in picked:
        moeda = _conf_fwdstart_moeda(deal)
        direction = str(deal.get('Direction') or '').strip().upper()
        taxa, tipo_taxa = _conf_fxo_conv_rate(moeda)
        if not taxa:
            sem_taxa.add(moeda or '(sem moeda)')
        b3 = str(deal.get('B3_ID') or '').strip()
        if not b3:
            sem_b3 += 1
        d_ini = routes._parse_date_any(deal.get('FirstFixingDate'))
        d_fim = routes._parse_date_any(deal.get('LastFixingDate'))
        # Taxa Forward: o forward start não tem taxa na contratação (o import
        # zera o Rate). Quando existir, é ela que vale — a cláusula 4.2.l.1.
        taxa_fwd = _conf_fmt_num(deal.get('Rate'), dec=8) if str(deal.get('Rate') or '').strip() \
            else 'Não Aplicável'
        rows.append({
            'num':           b3,
            'comprador':     'Parte B' if direction.startswith('S') else 'Parte A',
            'moedaBase':     moeda,
            # O termo de moeda a termo não paga prêmio; as três colunas existem
            # no documento e saem declaradas, não em branco.
            'premio':        'Não Aplicável',
            'devedorPremio': 'Não Aplicável',
            'dtPremio':      'Não Aplicável',
            'taxaConv':      taxa,
            'tipoTaxaConv':  tipo_taxa,
            'dtEfetiva':     _conf_fmt_date(deal.get('TradeDate')),
            'dtVerifFwd':    _conf_fmt_date(deal.get('StrikeSetDate')),
            'pontosTermo':   str(deal.get('StrikeSetOffset') or '').strip(),
            'taxaFwd':       taxa_fwd,
            'valorBase':     _conf_fmt_num(str(deal.get('Notional') or '').replace('-', ''), dec=2),
            'dtIni':         'Não Aplicável' if (not d_ini or d_ini == d_fim)
                             else _conf_fmt_date(deal.get('FirstFixingDate')),
            'dtFim':         _conf_fmt_date(deal.get('LastFixingDate')),
            'dtVenc':        _conf_fmt_date(deal.get('SettlementDate')),
        })
    if sem_taxa:
        warnings.append('Moeda {} sem Taxa de Conversão cadastrada (mapping FXO Conversion Rate) '
                        '— preencha as colunas no painel.'.format(', '.join(sorted(sem_taxa))))
    if sem_b3:
        warnings.append('{} operação(ões) sem B3 ID — a coluna Nº do Anexo I sai vazia. '
                        'Faça o mapeamento do retorno da B3 antes de gerar a confirmação.'
                        .format(sem_b3))
    return rows
