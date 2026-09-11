# -*- coding: utf-8 -*-
"""Other Products — leituras. Hoje: a página Swap VCP com os FATORES (§452).

O que a tela mostra sai de SEIS fontes que não se conhecem, todas do dia da
liquidação (`ref`), e cada uma responde por uma chave:

    Operations B3 ─AVISO DE INEXISTENCIA DE PU─> os contratos (`_vcp_collect`)
         │ Título = CETIP ID ─> Swap Athena ──> Athena ID (Kapital ID)
         │                         └─ Kapital ID = Trade Id ─> OTM ──> as CURVAS
         │                                         (+ = Parte/JP recebe, − = Contraparte)
         ├─ Título = Código do Contrato ─> Swap Eventos ──> Valor Juros / Fator de
         │                                  Juros que a B3 calculou, por perna
         ├─ Título = Contrato ─> POSIÇÃO ──> VBR, valor original, tipo de
         │                                   amortização, LOB (identificador)
         └─ Título = Contrato ─> DFLUXO ──> o % e a base da amortização do
                                            evento que liquida em `ref`
                                            (a regra do Swap Calculator)

O arquivo-dia dos fatores (`persistence`) traz o que a mesa editou e o
status; o `domain.calcular` fecha a conta. Nada aqui grava."""
from datetime import datetime

from apps.pages.features.other_products import domain
from apps.pages.features.other_products.infra import persistence
from apps.pages.platform import swap_flows as _sf


def _R():
    from apps.pages import routes
    return routes


COLUNAS_FATORES = ['Athena ID', 'Código do Contrato', 'Contraparte', 'VBR',
                   '% Amortização do Fluxo', 'Tipo Amortização', 'Notional Amortizado',
                   'Juros Parte', 'Diff B3', 'Juros Contraparte', 'Diff B3',
                   'Fator Parte', 'Fator Contraparte']


def _by_cetip_athena(R, ref):
    athena = R._athena_settlements(ref)
    ai = {c: i for i, c in enumerate(athena.get('columns') or [])}
    out = {}
    for row in athena.get('rows') or []:
        cet = str(row[ai['CETIP ID']] if 'CETIP ID' in ai else '').strip().upper()
        if cet:
            out.setdefault(cet, row)
    return out, ai


def _curvas_otm(R, ref):
    """{Trade Id → (Σ recebimentos, Σ pagamentos em módulo)} do OTM do dia."""
    _jp, otm = R._otm_load(ref)
    out = {}
    for rec in (otm or []):
        tid = str(rec.get('Trade Id', '') or '').strip().upper()
        amt = R._conf_to_float(rec.get('Amount'))
        if not tid or amt is None:
            continue
        pos, neg = out.get(tid, (0.0, 0.0))
        if amt >= 0:
            pos += amt
        else:
            neg += -amt
        out[tid] = (pos, neg)
    return out


_EVENT_COLS = ('PARTE / Valor Juros', 'CONTRAPARTE / Valor Juros', 'PARTE / Fator de Juros',
               'CONTRAPARTE / Fator de Juros', 'Valor Base Remanescente', 'Valor Base')


def _by_contract_events(R, ref):
    """{contrato → {coluna: texto cru}} do arquivo de eventos. Lê os REGISTROS
    crus (`_db_day_records`), não a coleta de exibição: aquela formata as
    colunas de valor em `#,##0.00`, e o `Fator de Juros` da B3 (1,0169) saía
    como 1,02. A primeira resposta não vazia de cada campo vence, campo a
    campo — o mesmo contrato aparece em várias linhas (§431)."""
    jp = R._ds_display_json_path(ref, 'eventos-swap-jpm')
    out = {}
    try:
        if not R._store.isfile(jp):
            return out
        data = R._db_day_records(jp) or []
    except Exception:                                       # noqa: BLE001
        return out
    if not data:
        return out
    keys = list(data[0].keys())
    chaves = {col: R._fcst_resolve_key(keys, [col]) for col in _EVENT_COLS}
    kc = R._fcst_resolve_key(keys, ['código do contrato', 'codigo do contrato', 'contrato'])
    for rec in data:
        k = str(rec.get(kc, '') or '').strip().upper() if kc else ''
        if not k:
            continue
        atual = out.setdefault(k, {})
        for col, chave in chaves.items():
            v = str(rec.get(chave, '') or '').strip() if chave else ''
            if v and not atual.get(col):
                atual[col] = v
    return out


def vcp_payload(ref):
    """O payload da página: as linhas de sempre (`_vcp_collect`) com o Athena
    ID entre Contraparte e Código do Contrato e os fatores preenchidos, mais
    `statuses` (a esteira, por linha) e `factors` (a segunda tabela)."""
    R = _R()
    base = R._vcp_collect(ref)
    cols = list(base.get('columns') or [])
    rows = [list(r) for r in (base.get('rows') or [])]
    if 'Athena ID' not in cols:
        cols.insert(1, 'Athena ID')
        for r in rows:
            r.insert(1, '')
    ci = {c: i for i, c in enumerate(cols)}
    factors = vcp_factor_rows(ref, rows, ci)
    by_ct = {f['contrato'].upper(): f for f in factors}
    statuses = []
    for r in rows:
        f = by_ct.get(str(r[ci['Código do Contrato']] or '').strip().upper())
        if f:
            r[ci['Athena ID']] = f['athena_id']
            r[ci['PARTE / Fator']] = _f8(f['fator_p']) if f['vcp_p'] else ''
            r[ci['CONTRAPARTE/ Fator']] = _f8(f['fator_c']) if f['vcp_c'] else ''
            statuses.append(f['status'])
        else:
            statuses.append('New')
    base.update({'columns': cols, 'rows': rows, 'statuses': statuses,
                 'factors': factors, 'factor_columns': list(COLUNAS_FATORES)})
    return base


def _f8(v):
    return '' if v is None else '{:.8f}'.format(float(v))


def vcp_factor_rows(ref, rows=None, ci=None):
    """Uma linha de fatores por contrato do VCP (a segunda tabela)."""
    R = _R()
    if rows is None:
        base = R._vcp_collect(ref)
        cols = list(base.get('columns') or [])
        rows = [list(r) for r in (base.get('rows') or [])]
        if 'Athena ID' not in cols:
            cols.insert(1, 'Athena ID')
            for r in rows:
                r.insert(1, '')
        ci = {c: i for i, c in enumerate(cols)}
    if not rows:
        return []
    by_cetip, ai = _by_cetip_athena(R, ref)
    curvas = _curvas_otm(R, ref)
    eventos = _by_contract_events(R, ref)
    posicoes, dref_iso = _sf.posicoes_swap(ref)
    dia_pos = datetime.strptime(dref_iso, '%Y-%m-%d').date() if dref_iso else None
    salvos = persistence._vcp_factors_load(ref)
    ref_iso = ref.strftime('%Y-%m-%d')

    def cel(r, nome):
        i = ci.get(nome)
        return str(r[i] or '').strip() if i is not None and i < len(r) else ''

    out = []
    for r in rows:
        contrato = cel(r, 'Código do Contrato')
        if not contrato:
            continue
        key = contrato.upper()
        arow = by_cetip.get(key)
        athena_id = str(arow[ai['Kapital ID']] if arow and 'Kapital ID' in ai else '').strip()
        pos = posicoes.get(_sf.norm(contrato).replace(' ', '')) or {}
        ev = eventos.get(key) or {}
        faltam = []
        if not athena_id:
            faltam.append('athena_id')
        # as curvas: o OTM pelo Athena ID; sem linha lá, as colunas do próprio Athena
        curva_p = curva_c = None
        if athena_id and athena_id.upper() in curvas:
            curva_p, curva_c = curvas[athena_id.upper()]
        elif arow:
            curva_p = domain.num(arow[ai['Owner curve']] if 'Owner curve' in ai else None)
            curva_c = domain.num(arow[ai['Counterparty curve']] if 'Counterparty curve' in ai else None)
        if curva_p is None and curva_c is None:
            faltam.append('curva')
        vbr = pos.get('remanescente')
        if vbr is None:
            vbr = domain.num(ev.get('Valor Base Remanescente'))
        if vbr is None:
            faltam.append('vbr')
        original = pos.get('valor_inicial') or pos.get('valor_base') or domain.num(ev.get('Valor Base'))
        ident = pos.get('identificador', '')
        lob = R._accrual_lob(ident) or 'CEM'
        tipo_pos = pos.get('tipo_amort', '')
        amort = None
        try:
            amort = _sf.amortizacao_do_dia(contrato, ident, ref_iso, tipo_pos, dia_pos)
        except Exception:                                   # noqa: BLE001
            R.log.warning('[swap-vcp] DFLUXO de %s falhou', contrato, exc_info=True)
        if amort:
            pct, tipo = amort.get('p_amort', ''), amort.get('tipo_amort') or tipo_pos
            base_amort = amort.get('p_base_amort', '')
        else:
            pct, tipo, base_amort = '0', tipo_pos, ''
            faltam.append('fluxo')
        salvo = salvos.get(key) or {}
        calc = domain.calcular({
            'vbr': vbr, 'original': original, 'pct': pct, 'tipo': tipo, 'base_amort': base_amort,
            'curva_p': curva_p, 'curva_c': curva_c,
            'b3_juros_p': ev.get('PARTE / Valor Juros'), 'b3_juros_c': ev.get('CONTRAPARTE / Valor Juros'),
            'b3_fator_p': ev.get('PARTE / Fator de Juros'), 'b3_fator_c': ev.get('CONTRAPARTE / Fator de Juros'),
            'idx_p': cel(r, 'PARTE / Indexador'), 'idx_c': cel(r, 'CONTRAPARTE / Indexador'),
        }, salvo.get('overrides'))
        item = {'contrato': contrato, 'athena_id': athena_id, 'contraparte': cel(r, 'Contraparte'),
                'conta_p': cel(r, 'PARTE / Conta'), 'conta_c': cel(r, 'CONTRAPARTE / Conta'),
                'idx_p': cel(r, 'PARTE / Indexador'), 'idx_c': cel(r, 'CONTRAPARTE / Indexador'),
                'lob': lob, 'curva_p': curva_p, 'curva_c': curva_c,
                'b3_juros_p': domain.num(ev.get('PARTE / Valor Juros')),
                'b3_juros_c': domain.num(ev.get('CONTRAPARTE / Valor Juros')),
                'status': salvo.get('status') or 'New', 'maker': salvo.get('maker', ''),
                'checker': salvo.get('checker', ''), 'files': salvo.get('files') or [],
                'missing': faltam, 'source_date': dref_iso or ''}
        item.update(calc)
        out.append(item)
    return out
