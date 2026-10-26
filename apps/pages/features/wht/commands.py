# -*- coding: utf-8 -*-
"""Escrita do WHT: as liquidações que FLUEM das telas de liquidação, o Import
Settlements do decêndio, o relatório do HUB que entra pelo dropzone e o
arquivo que leva ao HUB o que ele não tem.

As telas de liquidação (NDF Summary, Other Products) entregam aqui as linhas
que acabaram de montar (`flow`): a fatia do dia daquela fonte é SUBSTITUÍDA e
só gravada se mudou. A importação do Cockpit e o Save Daily Settlement Files
pedem a mesma coisa em background (`refresh_async`) — o dia que eles acabaram
de gravar passa a valer aqui sem ninguém abrir o Summary.
"""
import os
import threading
import traceback
from datetime import date, datetime, timedelta

from apps.pages.features.wht import domain, queries
from apps.pages.features.wht.infra import store


def _R():
    from apps.pages import routes
    return routes


def _put(day, source, rows, by='', keep_missing=False):
    """Substitui a fatia (dia × fonte). Com `keep_missing`, uma coleta VAZIA não
    cria a fatia que ainda não existe: a tela de liquidação aberta num dia sem
    importação diria ao WHT que o dia foi importado e não teve nada — e o aviso
    "dia sem liquidação importada" sumiria."""
    def fn(doc):
        dia = (doc['otc'].get(day.isoformat()) or {})
        if keep_missing and not rows and source not in dia:
            return False
        dia = doc['otc'].setdefault(day.isoformat(), {})
        atual = (dia.get(source) or {}).get('rows')
        if atual == rows:
            return False
        dia[source] = {'rows': rows, 'at': store.now(), 'by': by}
        return True
    return store.mutate(domain.month_key(day), fn)


def flow(day, source, trades, by=''):
    """As linhas que uma tela de liquidação acabou de montar para `day`. Melhor
    esforço: a tela de liquidação nunca cai por causa do WHT (falha vai para o
    log)."""
    try:
        d = day.date() if isinstance(day, datetime) else day
        rows = queries.ndf_rows(d, trades) if source == 'ndf' else queries.ops_rows(d, trades)
        return _put(d, source, rows, by, keep_missing=True)
    except Exception:                                       # noqa: BLE001
        _R().log.warning('[wht] a liquidação de %s (%s) não fluiu para o WHT:\n%s',
                         day, source, traceback.format_exc())
        return False


def import_settlements(ref, by=''):
    """O botão Import Settlements: recoleta TODOS os dias úteis do decêndio de
    `ref` (até hoje) das duas fontes, e os dias dos decêndios ANTERIORES do mês
    que ainda não têm fatia — o piso de R$ 1,00 é do mês. Dia que falha fica
    como estava e volta em `failed`."""
    R = _R()
    y, m, n = domain.decendio_of(ref)
    ini, fim = domain.decendio_bounds(y, m, n)
    hoje = R._br_now().date()
    doc = store.load(domain.month_key(ref))
    dias = []
    d = date(y, m, 1)
    while d <= min(fim, hoje):
        if R._pcx_is_bizday(d):
            tem = (doc.get('otc') or {}).get(d.isoformat()) or {}
            fontes = ('ndf', 'ops') if d >= ini else tuple(s for s in ('ndf', 'ops') if s not in tem)
            if fontes:
                dias.append((d, fontes))
        d += timedelta(days=1)
    feitos, falhas, linhas = [], [], 0
    for d, fontes in dias:
        res = queries.collect_day(d, fontes)
        for src, rows in res.items():
            if isinstance(rows, Exception):
                falhas.append({'day': d.isoformat(), 'source': src,
                               'error': '%s: %s' % (type(rows).__name__, rows)})
                continue
            _put(d, src, rows, by)
            linhas += len(rows)
        feitos.append(d.isoformat())
    return {'days': feitos, 'failed': falhas, 'rows': linhas}


def refresh_async(day, sources=('ndf', 'ops'), by=''):
    """A recoleta de `day` numa thread própria (Cockpit importado, Daily
    Settlement salvo). Desligada com `OTC_DISABLE_SCHEDULERS=1` (os testes) e
    com `OTC_WHT_AUTOFLOW=0`."""
    if os.getenv('OTC_DISABLE_SCHEDULERS') == '1' or os.getenv('OTC_WHT_AUTOFLOW', '1') == '0':
        return False
    R = _R()
    app = getattr(R, '_FLASK_APP', None)
    if app is None:
        return False
    d = day.date() if isinstance(day, datetime) else day

    def corre():
        try:
            with R._app_context(), app.test_request_context('/__wht-refresh'):
                for src, rows in queries.collect_day(d, sources).items():
                    if not isinstance(rows, Exception):
                        _put(d, src, rows, by, keep_missing=True)
        except Exception:                                   # noqa: BLE001
            R.log.warning('[wht] recoleta de %s falhou:\n%s', d, traceback.format_exc())
    threading.Thread(target=corre, name='wht-refresh', daemon=True).start()
    return True


def import_hub(files, sid=''):
    """O relatório do HUB (um ou mais arquivos: o HUB manda o 5557 num e o 5273
    noutro, ou tudo junto). Cada linha vai para o mês da sua data (Fato
    Gerador); o que entra SUBSTITUI, no decêndio, as linhas da mesma empresa e
    do mesmo DARF — reenviar um relatório corrigido não duplica nem deixa a
    linha que o HUB tirou. Devolve o resumo por arquivo."""
    R = _R()
    por_mes, resumo = {}, []
    for nome, raw in files:
        try:
            linhas, fmt = R._latam_read_rows(raw)
        except Exception as exc:                            # noqa: BLE001
            resumo.append({'file': nome, 'rows': 0, 'error': '%s: %s' % (type(exc).__name__, exc)})
            continue
        recs, info = domain.parse_hub_report(linhas, nome)
        sem_data = [r for r in recs if not r.get('date')]
        recs = [r for r in recs if r.get('date')]
        resumo.append({'file': nome, 'format': fmt, 'rows': len(recs), 'no_date': len(sem_data),
                       'ignored': info['ignored'], 'companies': info['empresas'],
                       'header': info['header']})
        for r in recs:
            por_mes.setdefault(domain.month_key(r['date']), []).append(r)
    if not any(r.get('rows') for r in resumo):
        raise domain.WhtError('hub_empty', 'Nenhuma linha de operação no(s) arquivo(s) do HUB',
                              files=', '.join(r['file'] for r in resumo))
    decendios = set()
    for mk, recs in por_mes.items():
        escopo = {(domain.decendio_key(*domain.decendio_of(r['date'])), r['empresa'],
                   domain.darf_of(r['tributo'] or r['code'])) for r in recs}
        novos, vistos = [], set()
        for r in recs:
            x = dict(r)
            for k in ('date', 'emissao', 'vcto', 'pagto'):
                x[k] = x[k].isoformat() if x.get(k) else ''
            k = domain.hub_key(x)
            if k in vistos:
                continue
            vistos.add(k)
            novos.append(x)
        decs = sorted({e[0] for e in escopo})
        decendios.update(decs)

        def fn(doc, escopo=escopo, novos=novos, decs=decs):
            def no_escopo(h):
                d = domain.parse_date(h.get('date'))
                return d and (domain.decendio_key(*domain.decendio_of(d)), h.get('empresa'),
                              domain.darf_of(h.get('tributo') or h.get('code'))) in escopo
            doc['hub'] = [h for h in doc.get('hub') or () if not no_escopo(h)] + novos
            doc.setdefault('hub_files', []).extend(
                {'name': r['file'], 'at': store.now(), 'sid': sid, 'rows': r['rows'], 'scope': decs}
                for r in resumo if r.get('rows'))
        store.mutate(mk, fn)
    return {'files': resumo, 'decendios': sorted(decendios)}


def hub_file(ref, keys=None):
    """O arquivo que a equipe do HUB insere à mão: as operações que o OTC tem e
    o HUB não tem (`Unmatched OTC`) do decêndio de `ref` — ou as linhas
    marcadas na tela (`keys`), desde que tenham o lado OTC. Devolve (nome,
    bytes, quantas)."""
    R = _R()
    payload = queries.build(ref)
    otc_por_id = {}
    y, m, n = domain.decendio_of(ref)
    ini, fim = domain.decendio_bounds(y, m, n)
    doc = store.load(domain.month_key(ref))
    mes = []
    for day, fatias in (doc.get('otc') or {}).items():
        for src in ('ndf', 'ops'):
            mes.extend(((fatias or {}).get(src) or {}).get('rows') or [])
    for o in queries.enrich_otc(mes):
        otc_por_id[o['id']] = o
    escolhidas = set(keys or ())
    alvo = [r for r in payload['rows'] if r['key'] in otc_por_id and (
        r['key'] in escolhidas if escolhidas else r['status'] == domain.ST_ONLY_OTC)]
    if not alvo:
        raise domain.WhtError('hub_file_empty', 'Nenhuma operação para o arquivo do HUB no decêndio')
    itens, sem_emp = [], []
    for r in alvo:
        o = otc_por_id[r['key']]
        emp, filial = o['company']
        if not emp:
            sem_emp.append(o.get('le') or '—')
            continue
        ir = r['OTC_IR'] or 0.0
        itens.append({'empresa': emp, 'filial': filial, 'cnpj': o.get('taxid'), 'doc': o['doc'],
                      'date': o['date'], 'code': o['code'], 'gross': o['gross'], 'ir': ir,
                      'rate': (100.0 * ir / o['gross']) if (ir and o['gross']) else 0.0})
    if sem_emp:
        raise domain.WhtError('no_company', 'Entidade sem empresa no cadastro WHT Company: {les}',
                              les=', '.join(sorted(set(sem_emp))))
    linhas = domain.hub_file_lines(itens, R._br_now().date())
    nome = 'WHT_HUB_%s_%s.txt' % (ini.strftime('%Y%m%d'), fim.strftime('%Y%m%d'))
    return nome, ('\r\n'.join(linhas) + '\r\n').encode('cp1252', errors='replace'), len(itens)
