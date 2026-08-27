# -*- coding: utf-8 -*-
"""Os leitores do Operations B3 — o arquivo-dia (`_opb3_load`/`_opb3_import`),
as regras de evento do cadastro `opb3-events`, o breakdown, os mapas de perna
interna (TER/swap/NDFC/swap-prem) e a mensageria de liquidação.

Movido VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). É a fonte de
"que linhas entram numa apuração de liquidação" — o NDF Summary, o Other
Products, os avisos e a mensageria respondem por aqui (§6, `opb3-events`).

O `routes.py` mantém os nomes como ALIAS. O **`_OPB3_MSG_RECIPIENTS_FILE`
FICA no `routes`** (é caminho construído sobre `_DAILY_METRIC_DIR`, que os
testes patcham), e `B3_JSON_ROOT`/`OTM_JSON_ROOT`/`OPB3_SOURCE_ROOT`, os
leitores `_ds_*` do Daily Settlement, os `_fcst_*` do forecast e o
`_mapping_rows` são alcançados por busca atrasada `routes.<nome>` — o que
mantém os espiões dos testes (check_opb3_events, check_opb3_mensageria,
check_ds_operacoes) interceptando. O `@_req_cached` vem do `request_cache`
por import direto, como na fatia da liquidação (§316).
"""
import json
import logging
import traceback
from datetime import datetime
import os
import re

from apps.pages.data_paths import data_path
from apps.pages.request_cache import req_cached as _req_cached

log = logging.getLogger('otc_tracker')

def _ops_norm_event(v):
    """Tipo Operação normalizado para comparação: `_fcst_norm` cuida de caixa e
    acento, e o `\\s+` colapsa o espaço. Os arquivos da B3 vêm com padding e
    espaço duplo entre palavras; sem o colapso, `PAGAMENTO DE  DIF. DE JUROS`
    simplesmente não casa com a linha cadastrada — e o swap some da tela sem
    nenhum sinal de que houve comparação."""
    from apps.pages import routes
    return re.sub(r'\s+', ' ', routes._fcst_norm(v)).strip()


def _opb3_ev_key(v):
    """Chave de comparação de Tipo Título / Tipo Operação / Status B3.

    Além de caixa e acento (`_fcst_norm`), colapsa PONTUAÇÃO em espaço: a B3
    escreve o mesmo status como `CANCELADA: COMANDADA` num arquivo e
    `CANCELADA:COMANDADA` noutro, e quem cadastra digita de um jeito ou de
    outro. Comparar o texto cru fazia a regra simplesmente não valer — sem erro
    nenhum, que é o pior desfecho possível para um filtro."""
    from apps.pages import routes
    return re.sub(r'[^a-z0-9]+', ' ', routes._fcst_norm(v)).strip()


def _opb3_event_rules():
    """(consider, disregard) do cadastro `opb3-events`, cada regra já como a
    tripla normalizada (tipo título, tipo operação, status B3). `''` é coringa.

    USE em branco vale como **Consider**: é o que as linhas do antigo
    `swap-b3-events` queriam dizer, e é a leitura inofensiva das duas."""
    from apps.pages import routes
    cons, dis = [], []
    for r in routes._mapping_rows('opb3-events'):
        rule = (_opb3_ev_key(r.get('TIPO TITULO', '')),
                _opb3_ev_key(r.get('TIPO OPERACAO', '')),
                _opb3_ev_key(r.get('STATUS B3', '')))
        if not any(rule):
            continue                       # linha totalmente vazia não é regra
        (dis if routes._fcst_norm(r.get('USE', '')).strip().startswith('disreg')
         else cons).append(rule)
    return cons, dis


def _opb3_rule_hit(rule, tit, op, st):
    rt, ro, rs = rule
    return ((not rt or rt == tit) and (not ro or ro == op) and (not rs or rs == st))


def _opb3_settle_ok(rec, rules=None):
    """A linha do Operations B3 entra numa apuração de liquidação? Cadastro
    `opb3-events`, e é a MESMA resposta para o NDF Summary, o Other Products, os
    avisos e a mensageria — o mesmo negócio não pode contar numa tela e sumir na
    outra.

    Precedência:
      1. **Disregard** vence sempre. É o que tira a operação `CANCELADA:
         COMANDADA`, que continua no arquivo com o valor cheio e somava um caixa
         que não vai acontecer.
      2. Um Tipo Título com ao menos um **Consider** próprio vira LISTA BRANCA —
         é o caso do SWAP, onde só amortização, juros e prêmio são liquidação
         (resgate é vencimento). Regra de título em branco também conta como
         casamento aqui: ela vale para qualquer título.
      3. Tipo Título sem nenhum Consider não é filtrado — é como TER e OPC se
         comportam hoje, e é o que mantém a tela igual para quem não cadastrar
         nada.

    "Nenhum swap entra" continua sendo possível, mas agora se DIZ: uma linha
    Tipo Título = SWAP, resto em branco, Disregard. Antes isso se fazia
    esvaziando a tabela, o que não distinguia "não quero nenhum" de "ainda não
    cadastrei".

    `rules` é o par já lido por quem varre muitas linhas: sem ele cada registro
    reabre o cadastro (um `stat` por linha, por tela)."""
    cons, dis = rules if rules is not None else _opb3_event_rules()
    tit = _opb3_ev_key(rec.get('Tipo Título', ''))
    op = _opb3_ev_key(rec.get('Tipo Operação', ''))
    st = _opb3_ev_key(rec.get('Status', ''))
    if any(_opb3_rule_hit(r, tit, op, st) for r in dis):
        return False
    if any(r[0] == tit for r in cons if r[0]):
        return any(_opb3_rule_hit(r, tit, op, st) for r in cons)
    return True


@_req_cached
def _opb3_settle_rows(ref):
    """Linhas do Operations B3 de `ref` que valem para liquidação — o
    `_opb3_load` já peneirado pelo cadastro. A PÁGINA Operations B3 segue lendo
    o arquivo inteiro: ela é a fonte, e esconder linha lá deixaria o time sem
    onde ver a operação cancelada que a regra descartou."""
    _jp, data = _opb3_load(ref)
    if not data:
        return []
    rules = _opb3_event_rules()
    return [r for r in data if _opb3_settle_ok(r, rules)]

_OPB3_COLUMNS = [
    'Conta', 'Tipo Operação', 'C/V', 'Título', 'Tipo Título', 'Tipo de Regime', 'Data Vencimento',
    'Valor', 'Modalidade Liquidação', 'Status', 'Data Liquidação', 'Contraparte (Nome Simpl.)',
    'Conta Contraparte', 'Num Ctrl Operação',
]
_OPB3_DATE_COLS = {'Data Vencimento', 'Data Liquidação'}
_OPB3_HEADER_ROW = 5                                   # 1-based
_OPB3_META_KEYS = ('_ob_status', '_ob_maker', '_ob_checker', '_ob_id')


# ── Operations B3 maker/checker meta (standard: same pattern as OTM) ──────────
def _opb3_ensure_meta(data, default_status='New'):
    """Ensure every record has status/maker/checker/id meta. Returns True if any
    record changed (caller may persist — one-time migration for legacy JSONs).
    Imported rows default to 'New' (matches the page's historical badge)."""
    from apps.pages import routes
    changed = False
    for rec in data:
        if not rec.get('_ob_id'):
            rec['_ob_id'] = routes._otm_new_id(); changed = True
        if '_ob_status' not in rec:
            rec['_ob_status'] = default_status; changed = True
        for k in ('_ob_maker', '_ob_checker'):
            if k not in rec:
                rec[k] = ''; changed = True
    return changed


@_req_cached
def _opb3_load_cached(ref):
    """A leitura em si — é este resultado que o cache guarda. Ver `_opb3_load`."""
    jp = _opb3_json_path(ref)
    if not os.path.isfile(jp):
        return jp, None
    try:
        with open(jp, encoding='utf-8') as fh:
            data = json.load(fh) or []
    except Exception:
        return jp, None
    _opb3_ensure_meta(data)
    return jp, data


def _opb3_load(ref):
    """(json_path, data|None) for `ref`; ensures meta on the loaded records.

    Devolve uma CÓPIA dos registros, nunca a lista que está no cache. Os
    endpoints de add/edit/delete carregam o dia, mexem na lista e só então
    gravam (`data.remove(rec)`, `rec[c] = ...`): com o objeto do cache na mão,
    essa mutação passa a valer para todo mundo ANTES do save — e continua
    valendo quando o save FALHA. A linha some da tela de quem não pediu nada, e
    o request seguinte, que dentro do TTL recebe o mesmo objeto, grava por cima
    o estado que nunca chegou ao disco. É perda de dado sem erro nenhum.

    A cópia é rasa por registro porque toda escrita destes endpoints é escalar
    (`rec[k] = v`), e ela custa uma fração da leitura do share que o cache
    existe para poupar.
    """
    jp, data = _opb3_load_cached(ref)
    return jp, (None if data is None else [dict(r) for r in data])


def _opb3_find(data, rid):
    for rec in data:
        if str(rec.get('_ob_id', '')) == str(rid):
            return rec
    return None


def _opb3_ref_from(payload):
    ds = str((payload or {}).get('date', '') or '').strip()
    try:
        return datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        return datetime.now()


def _opb3_json_path(ref):
    from apps.pages import routes
    return os.path.join(routes.OTM_JSON_ROOT, ref.strftime('%Y'), ref.strftime('%m'), ref.strftime('%d'),
                        'operations-b3_{}.json'.format(ref.strftime('%Y%m%d')))


def _opb3_extract(rows):
    """Rows → (records, updated_time). Header on row 5; keep the reporting columns
    by header name. Time = row 2 col A (HH:MM:SS)."""
    from apps.pages import routes
    updated = routes._ds_cell(rows[1], 0) if len(rows) >= 2 else ''
    hidx = _OPB3_HEADER_ROW - 1
    if len(rows) <= hidx:
        return [], updated
    header = [routes._ds_cell(rows[hidx], i) for i in range(len(rows[hidx]))]
    hnorm = [routes._fcst_norm(h) for h in header]

    def col_idx(name):
        n = routes._fcst_norm(name)
        if n in hnorm:
            return hnorm.index(n)
        for i, h in enumerate(hnorm):
            if h and (n in h or h in n):
                return i
        return None
    idx_map = {c: col_idx(c) for c in _OPB3_COLUMNS}

    out = []
    for r in rows[hidx + 1:]:
        if not any(routes._ds_cell(r, i) for i in range(len(r))):
            continue
        out.append({c: routes._ds_cell(r, idx_map.get(c)) for c in _OPB3_COLUMNS})
    return out, updated


def _opb3_spec():
    from apps.pages import routes
    return next((s for s in routes._DS_IMPORTS if s.get('key') == 'operacoes-jpm'), None)


def _opb3_map_recs(recs):
    """Map the FILTERED _ds_process recs (dicts keyed by the full header) to the 14
    Operations B3 reporting columns by header name — so the page shows exactly the
    rows that were processed (house account + operation-type filter), not the raw file."""
    from apps.pages import routes
    if not recs:
        return []
    keys = list(recs[0].keys())
    knorm = [(k, routes._fcst_norm(k)) for k in keys]

    def resolve(name):
        n = routes._fcst_norm(name)
        for k, kn in knorm:
            if kn == n:
                return k
        for k, kn in knorm:
            if kn and (n in kn or kn in n):
                return k
        return None
    idx = {c: resolve(c) for c in _OPB3_COLUMNS}
    return [{c: (rec.get(idx[c], '') if idx[c] else '') for c in _OPB3_COLUMNS} for rec in recs]


def _opb3_merge(existing, new_recs, src_key):
    """Merge freshly-mapped rows from ONE source (e.g. operacoes-jpm / operacoes-mgt)
    into the day's Operations B3 records WITHOUT clobbering rows from the other
    sources. Rows carry a hidden `_ob_src` tag: re-processing a source replaces only
    its own rows (idempotent) and preserves maker/checker meta per Num Ctrl Operação.
    Legacy untagged rows are treated as operacoes-jpm (the only source that fed this
    page before MGT was added). Manually-added rows (_ob_src='manual') are kept."""
    existing = existing or []
    _opb3_ensure_meta(existing)
    for rec in existing:                                # migrate legacy rows (no source tag)
        if not rec.get('_ob_src'):
            rec['_ob_src'] = 'operacoes-jpm'
    old_by_ctrl = {}
    for rec in existing:
        if rec.get('_ob_src') == src_key:
            k = str(rec.get('Num Ctrl Operação', '') or '').strip()
            if k:
                old_by_ctrl[k] = rec
    result = [r for r in existing if r.get('_ob_src') != src_key]
    for rec in new_recs:
        rec['_ob_src'] = src_key
        prev = old_by_ctrl.get(str(rec.get('Num Ctrl Operação', '') or '').strip())
        if prev:                                        # carry status/maker/checker/id forward
            for m in _OPB3_META_KEYS:
                rec[m] = prev.get(m, '')
        else:
            _opb3_ensure_meta([rec])
        result.append(rec)
    return result


def _opb3_side_write(recs, raw, ref, src_key):
    """Write/merge the FILTERED operacoes recs into the day's Operations B3 json."""
    from apps.pages import routes
    b3_new = _opb3_map_recs(recs)
    b3_jp = _opb3_json_path(ref)
    existing = []
    if os.path.isfile(b3_jp):
        try:
            with open(b3_jp, encoding='utf-8') as fh:
                existing = json.load(fh) or []
        except Exception:
            existing = []
    b3_rows = _opb3_merge(existing, b3_new, src_key)
    os.makedirs(os.path.dirname(b3_jp), exist_ok=True)
    with open(b3_jp, 'w', encoding='utf-8') as fh:
        json.dump(b3_rows, fh, ensure_ascii=False, indent=2)
    routes._bump_cache_gen(b3_jp)                             # ver o comentário em `_ds_write`
    routes._ds_write_updated(b3_jp, _opb3_updated_from(routes._ds_read_rows(raw)) or ref.strftime('%H:%M:%S'))


def _opb3_updated_from(rows):
    from apps.pages import routes
    return routes._ds_cell(rows[1], 0) if len(rows) >= 2 else ''


def _opb3_import(ref=None):
    from apps.pages import routes
    ref = ref or datetime.now()
    if not os.path.isdir(routes.OPB3_SOURCE_ROOT):
        return {'success': False, 'error': 'Source folder not found: {}'.format(routes.OPB3_SOURCE_ROOT)}
    # Pick up every source that feeds this page (operacoes* → JPM, mgt.* → MGT). Each
    # is filtered by its own spec (house account + operation-type) and MERGED into the
    # day's json so the two counterparties coexist instead of overwriting each other.
    files = sorted(f for f in os.listdir(routes.OPB3_SOURCE_ROOT)
                   if os.path.isfile(os.path.join(routes.OPB3_SOURCE_ROOT, f)))
    handled, total_rows, last_updated = [], 0, ''
    for name in files:
        spec = routes._ds_match_spec(name)
        if not spec or not spec.get('opb3'):
            continue
        src_path = os.path.join(routes.OPB3_SOURCE_ROOT, name)
        try:
            with open(src_path, 'rb') as fh:
                raw = fh.read()
        except Exception:
            log.warning("[opb3] read failed for %s:\n%s", src_path, traceback.format_exc())
            continue
        filtered, _tot = routes._ds_process(raw, spec)
        _opb3_side_write(filtered, raw, ref, spec['key'])
        handled.append(name)
        total_rows += len(filtered)
        last_updated = _opb3_updated_from(routes._ds_read_rows(raw)) or last_updated
        try:
            os.remove(src_path)
        except OSError:
            log.warning("[opb3] could not delete source %s", src_path)
    if not handled:
        return {'success': False, 'error': 'No Operacoes*/MGT* file found in {}'.format(routes.OPB3_SOURCE_ROOT)}
    return {'success': True, 'file': ', '.join(handled), 'rows': total_rows,
            'updated': last_updated, 'date': ref.strftime('%Y-%m-%d')}


def _opb3_breakdown(data, col):
    """Dynamic count per distinct value of `col` (skip blanks). Returns
    {total, items:[{label,count}]} sorted by count desc then label."""
    counts = {}
    for rec in data:
        v = str(rec.get(col, '') or '').strip()
        if not v:
            continue
        counts[v] = counts.get(v, 0) + 1
    items = [{'label': k, 'count': counts[k]}
             for k in sorted(counts, key=lambda k: (-counts[k], k))]
    return {'total': sum(counts.values()), 'items': items}


def _opb3_tipo_maps(ref):
    """{'TER'|'OPC'|'SWAP': {contrato_upper: tipo}} a partir dos snapshots de
    posição (DPOSICAO*) mais recentes até D-1 ANBIMA de `ref` (walk-back de até
    10 dias úteis por categoria — mesmo fallback do Live Position):
      TER  → chave "Contrato";   valor da "Classe do Ativo Subjacente" (como está)
      OPC  → chave "Código IF";  valor da "Classe do ativo subjacente" (como está)
      SWAP → chave "Contrato";   valor do "Código Identificador"
    """
    from apps.pages import routes
    specs = {
        'TER':  ('NDF',    lambda r: '73760_{}_DPOSICAO-TER.json'.format(r)),
        'OPC':  ('Option', lambda r: '73760_{}_DPOSICAO.json'.format(r)),
        'SWAP': ('Swap',   lambda r: '73760_{}_DPOSICAO-SWAP.json'.format(r)),
    }
    out = {k: {} for k in specs}
    for key, (cat, fname) in specs.items():
        probe = routes._prev_anbima_bizday(ref)
        path = None
        for _ in range(10):
            p = os.path.join(routes.B3_JSON_ROOT, cat, routes._b3_date_subpath(probe.strftime('%y%m%d')),
                             fname(probe.strftime('%y%m%d')))
            if os.path.isfile(p):
                path = p
                break
            probe = routes._prev_anbima_bizday(probe)
        if not path:
            continue
        try:
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh) or []
        except Exception:
            continue
        if not data:
            continue
        keys = list(data[0].keys())
        # A posição de opções não tem coluna "Contrato" — o contrato dela é o
        # "Código IF". Procurar por 'Contrato' ali caía no fallback por substring
        # e resolvia para "Situação do contrato", então o Título do Operations B3
        # nunca casava e a coluna Type saía vazia para todo OPC.
        if key == 'OPC':
            k_contr = routes._fcst_resolve_key(keys, ('Código IF', 'Codigo IF', 'Contrato'))
        else:
            k_contr = routes._fcst_resolve_key(keys, ('Contrato', 'Título', 'Titulo', 'Codigo do Contrato'))
        k_classe = routes._fcst_resolve_key(keys, ('Classe do Ativo Subjacente', 'Classe do Ativo', 'Classe'))
        k_ident = routes._fcst_resolve_key(keys, ('Código Identificador', 'Codigo Identificador'))
        for rec in data:
            contrato = str(rec.get(k_contr, '') or '').strip().upper() if k_contr else ''
            if not contrato:
                continue
            if key == 'SWAP':
                tipo = str(rec.get(k_ident, '') or '').strip().upper() if k_ident else ''
            else:                                       # TER e OPC: classe como está
                tipo = str(rec.get(k_classe, '') or '').strip().upper() if k_classe else ''
            if tipo:
                out[key].setdefault(contrato, tipo)
    return out


def _opb3_tipo_for(rec, maps):
    """Tipo derivado de uma linha do Operations B3 (match Título × posição)."""
    from apps.pages import routes
    titn = routes._fcst_norm(str(rec.get('Tipo Título', '') or ''))
    key = 'SWAP' if 'swap' in titn else ('OPC' if 'opc' in titn else ('TER' if 'ter' in titn else None))
    if not key:
        return ''
    titulo = str(rec.get('Título', '') or '').strip().upper()
    return maps.get(key, {}).get(titulo, '')


def _opb3_collect(ref):
    from apps.pages import routes
    jp = _opb3_json_path(ref)
    rows_out, data = [], []
    tipo_maps = _opb3_tipo_maps(ref)
    if os.path.isfile(jp):
        try:
            with open(jp, encoding='utf-8') as fh:
                data = json.load(fh) or []
        except Exception:
            data = []
        if _opb3_ensure_meta(data) and data:             # legacy JSON w/o meta → migrate once
            try:
                routes._otm_save(jp, data)
            except Exception:
                pass
        for rec in data:
            row = []
            for c in _OPB3_COLUMNS:
                v = rec.get(c, '')
                if c in _OPB3_DATE_COLS:
                    d = routes._fcst_parse_date(v)
                    v = d.strftime('%d/%m/%Y') if d else (v or '')
                elif c == 'Valor':
                    v = routes._swapchar_fmt_value(v)
                row.append('' if v is None else v)
            # Coluna derivada Type (não persistida): match do Título na posição.
            row.append(_opb3_tipo_for(rec, tipo_maps))
            # Append maker/checker meta as the row tail: [...data..., status, maker, checker, id]
            row += [rec.get('_ob_status', 'New'), rec.get('_ob_maker', ''),
                    rec.get('_ob_checker', ''), rec.get('_ob_id', '')]
            rows_out.append(row)
    # Dynamic breakdown widgets: Tipo Operação, Tipo Título, Modalidade Liquidação.
    widgets = {
        'total': len(data),
        'tipo_operacao': _opb3_breakdown(data, 'Tipo Operação'),
        'tipo_titulo':   _opb3_breakdown(data, 'Tipo Título'),
        'modalidade':    _opb3_breakdown(data, 'Modalidade Liquidação'),
    }
    return {'widgets': widgets, 'columns': _OPB3_COLUMNS + ['Type'], 'rows': rows_out,
            'updated': routes._ds_read_updated(jp)}

# BCC de compliance (GDT) dos intragrupo — ver regra no loop da geração.
_OPB3_MSG_GDT_BCC = 'gdt.br.derivatives@restricted.chase.com'
# Contas de casa dos dois arquivos que alimentam a página (ver _DS_IMPORTS):
# operacoes-jpm = Banco J.P. Morgan, mgt.* = MGT. Elas sobrevivem aqui porque o
# `_OPB3_LEGAL_SIDES` traduz o LEGAL do Cockpit ("BANCOJP…") em conta, e essa é
# uma pergunta sobre o texto do Cockpit, não sobre o cadastro de contas. QUE
# VISÃO gera mensagem deixou de ser decidido aqui: é a coluna Messaging do
# `b3-accounts` (ver `_b3_msg_view_use`).
_OPB3_ACCT_BANCO = '73760009'
_OPB3_ACCT_MGT = '04880006'
# Status local de uma linha já transformada em e-mail de mensageria.
_OPB3_STATUS_GENERATED = 'Generated'
# Status B3 gravado na linha quando o e-mail sai (a B3 fecha a operação depois
# da mensagem; a página passa a refletir isso sem esperar o próximo arquivo).
_OPB3_B3_STATUS_DONE = 'FINALIZADA'


def _opb3_msg_load_recipients():
    from apps.pages import routes
    try:
        with open(routes._OPB3_MSG_RECIPIENTS_FILE, encoding='utf-8') as fh:
            d = json.load(fh) or {}
    except Exception:
        d = {}
    out = {}
    for k in ('cem', 'equities'):
        v = d.get(k) or {}
        out[k] = {'to': str(v.get('to', '') or ''), 'cc': str(v.get('cc', '') or '')}
    return out


def _opb3_msg_save_recipients(payload):
    # Ler → mesclar → gravar sob o lock: o payload traz só os cards alterados, e
    # sem isso dois usuários salvando cards diferentes perderiam um dos dois.
    from apps.pages import routes
    with routes._cache_lock:
        cur = _opb3_msg_load_recipients()
        for k in ('cem', 'equities'):
            v = (payload or {}).get(k)
            if isinstance(v, dict):
                cur[k] = {'to': str(v.get('to', '') or '').strip(),
                          'cc': str(v.get('cc', '') or '').strip()}
        os.makedirs(routes._DAILY_METRIC_DIR, exist_ok=True)
        routes._atomic_write_json(routes._OPB3_MSG_RECIPIENTS_FILE, cur)
    return cur


def _opb3_msg_route_key(tipo):
    """Card de destinatários por tipo: EQUITIES/EDG/AÇÕES → equities; resto → cem."""
    from apps.pages import routes
    tn = routes._fcst_norm(str(tipo or ''))
    return 'equities' if ('equit' in tn or 'edg' in tn or 'acao' in tn or 'acoes' in tn) else 'cem'


def _opb3_refdata_by_account():
    """Conta CETIP ('B3 ACCOUNT', ex. 74220.00-5) → nome da contraparte (RefData)."""
    out = {}
    try:
        with open(data_path('RefData.json'),
                  encoding='utf-8') as fh:
            for r in json.load(fh) or []:
                acc = str(r.get('B3 ACCOUNT', '') or '').strip()
                name = str(r.get('COUNTERPARTY', '') or '').strip()
                if acc and name and acc not in out:
                    out[acc] = name
    except Exception:
        pass
    return out


# LEGAL do Cockpit ↔ conta de casa da B3. O Cockpit exibe as duas entidades
# (`_ndfc_collect` filtra por BANCOJP*/JPMORGANCHASE*), então um negócio
# intragrupo aparece DUAS vezes sob o mesmo contrato, uma perna por entidade e
# com sinais opostos.
_OPB3_LEGAL_SIDES = ((_OPB3_ACCT_BANCO, 'BANCOJP'), (_OPB3_ACCT_MGT, 'JPMORGANCHASE'))


def _opb3_legal_side(legal):
    """LEGAL do Cockpit → conta de casa correspondente ('' quando não classifica).
    Ignora pontuação/espaço ("J.P." ≡ "JP"), como o filtro do próprio Cockpit."""
    s = re.sub(r'[^A-Z0-9]', '', str(legal or '').upper())
    for acct, prefix in _OPB3_LEGAL_SIDES:
        if s.startswith(prefix):
            return acct
    return ''


def _opb3_internal_ter_map(ref):
    """B3 ID (upper) → {conta de casa: Σ SETTLEMENT interno} — lado JP do
    batimento para Tipo Título = TER (NDF de moeda).

    É o par (B3 ID, SETTLEMENT) do card Trade Level do NDF Summary: as mesmas
    linhas de exibição do Cockpit (CD_CETIP_RETURN já com os resgates de contrato
    aplicados) e a coluna SETTLEMENT pura — não a SETTLEMENT B3, que é o lado da
    B3 e é justamente o outro lado da comparação.

    A quebra por conta de casa existe por causa do intragrupo: somar as duas
    pernas do mesmo contrato dava exatamente zero, e o "Favor considerar" saía
    R$ 0,00 em vez do valor da perna que assina a mensagem."""
    from apps.pages import routes
    out = {}
    try:
        ci = {c: i for i, c in enumerate(routes._NDFC_COLUMNS)}
        for row in routes._ndfc_collect(ref)['rows']:
            b3 = str(row[ci['CD_CETIP_RETURN']] or '').strip().upper()
            if not b3 or b3 == routes._NDFC_MISSING_B3.upper():
                continue
            v = routes._mtm_parse_num(row[ci['[PROD] Cockpit.SETTLEMENT']])
            if v is None:
                continue
            legs = out.setdefault(b3, {})
            side = _opb3_legal_side(row[ci['LEGAL']])
            legs[side] = legs.get(side, 0.0) + v
    except Exception:
        return {}
    return out


def _opb3_internal_leg(ter_map, contrato, casa):
    """SETTLEMENT interno do contrato pela ótica de `casa` (conta do participante
    do e-mail). Sem perna daquele lado — negócio de uma entidade só, ou LEGAL que
    não classifica — soma o que houver, que é o valor único do contrato."""
    legs = ter_map.get(contrato)
    if not legs:
        return None
    if casa and casa in legs:
        return legs[casa]
    return sum(legs.values())


def _opb3_internal_swapprem_map(ref):
    """Contrato (upper) → Σ valor da agenda de prêmios (DAGENDAPREMIOS) — lado JP
    do batimento para PAGAMENTO DE PREMIO × SWAP. {} quando não há arquivo."""
    from apps.pages import routes
    out = {}
    probe = routes._prev_anbima_bizday(ref)
    path = None
    for _ in range(10):
        p = os.path.join(routes.B3_JSON_ROOT, 'Swap', routes._b3_date_subpath(probe.strftime('%y%m%d')),
                         '73760_{}_DAGENDAPREMIOS.json'.format(probe.strftime('%y%m%d')))
        if os.path.isfile(p):
            path = p
            break
        probe = routes._prev_anbima_bizday(probe)
    if not path:
        return out
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh) or []
        if not data:
            return out
        keys = list(data[0].keys())
        k_contr = routes._fcst_resolve_key(keys, ('Contrato', 'Codigo do Contrato', 'Título', 'Titulo'))
        k_val = routes._fcst_resolve_key(keys, ('Valor do Evento', 'Valor'))
        for rec in data:
            contrato = str(rec.get(k_contr, '') or '').strip().upper() if k_contr else ''
            v = routes._ndfc_valnum(rec.get(k_val)) if k_val else None
            if contrato and v is not None:
                out[contrato] = out.get(contrato, 0.0) + v
    except Exception:
        return {}
    return out


def _opb3_internal_trade_map(rows):
    """B3 ID (upper) → Σ SETTLEMENT interno, a partir de linhas do Trade Level do
    Other Products Summary.

    Mesma ideia do `_opb3_internal_ter_map` para o NDF de moeda: o lado JP do
    batimento é a coluna SETTLEMENT que a tela já mostra, não uma segunda leitura
    dos arquivos. Se o "Favor considerar" do e-mail e o Settlement do Trade Level
    discordarem, não há como saber qual dos dois o time deve seguir."""
    out = {}
    for r in rows or []:
        b3 = str(r.get('id_b3', '') or '').strip().upper()
        v = r.get('_settle_n')
        if b3 and v is not None:
            out[b3] = out.get(b3, 0.0) + v
    return out


def _opb3_internal_swap_map(ref):
    """B3 ID → SETTLEMENT interno do SWAP (linhas de swap do Trade Level).

    Cobre os vencimentos (diferencial de amortização e de juros); o prêmio segue
    com a agenda de prêmios, que é a fonte dele. O valor é o do CONTRATO, não o
    do evento — por isso a mensageria junta amortização e juros da mesma
    contraparte antes de comparar: separados, cada e-mail acusaria uma
    divergência que é só a outra metade do mesmo pagamento."""
    from apps.pages import routes
    try:
        return _opb3_internal_trade_map(routes._ops_swap_trade_rows(ref.date()))
    except Exception:
        log.error('[opb3-msg] mapa interno de swap falhou:\n%s', traceback.format_exc())
        return {}


def _opb3_internal_ndfc_map(ref):
    """B3 ID → SETTLEMENT interno do TERMO DE COMMODITIES.

    O `_opb3_internal_ter_map` cobre o NDF de MOEDA (vem do Cockpit); a
    commodity não passa por lá e ficava sem lado interno — o e-mail saía sempre
    sem o "Favor considerar", que é indistinguível de "bateu"."""
    from apps.pages import routes
    try:
        return _opb3_internal_trade_map(routes._ops_ndfc_trade_rows(ref.date()))
    except Exception:
        log.error('[opb3-msg] mapa interno de termo de commodities falhou:\n%s',
                  traceback.format_exc())
        return {}

def _opb3_events_upgrade(rows):
    """Completa o arquivo já em disco com as linhas de Consider de TER e OPC.

    Sem isto, a instância que já tem o `opb3-events.json` (o arquivo é
    versionado, mas o da mesa pode ter sido editado) ficaria SEM regra para esses
    dois títulos — e "Tipo Título sem nenhum Consider não é filtrado" faria TODO
    evento de termo entrar no aviso no dia em que o `_ndfadv_collect` deixou de
    testar 'resgate' por conta própria. Um aviso que ganha linhas sozinho é pior
    do que um que falta.

    Só completa o que FALTA: um Tipo Título que já tem Consider próprio foi
    configurado por alguém, e sobrescrevê-lo apagaria a decisão da mesa."""
    from apps.pages import routes
    out = list(rows)
    # Quais títulos JÁ têm Consider é medido ANTES de acrescentar qualquer coisa:
    # medindo dentro do laço, a primeira linha de OPC que entra faz a segunda
    # (o prêmio) parecer configurada e ela nunca é acrescentada.
    tem_consider = {_opb3_ev_key(r.get('TIPO TITULO', '')) for r in out
                    if not routes._fcst_norm(r.get('USE', '')).strip().startswith('disreg')}
    for seed in routes._MAP_OPB3_SEED:
        tit = _opb3_ev_key(seed['TIPO TITULO'])
        if tit in ('ter', 'opc') and tit not in tem_consider:
            out.append(dict(seed))
    return out
