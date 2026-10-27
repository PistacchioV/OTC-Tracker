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


def _dias_do_import(ref):
    """[(dia, fontes)] do Import Settlements: TODOS os dias úteis do decêndio de
    `ref` (até hoje), das duas fontes, e os dias dos decêndios ANTERIORES do mês
    que ainda não têm fatia — o piso de R$ 1,00 é do mês."""
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
    return dias


try:
    IMPORT_WORKERS = int(os.getenv('OTC_WHT_IMPORT_WORKERS', '4') or 4)
except ValueError:
    IMPORT_WORKERS = 4


def import_settlements(ref, by='', workers=1, contexto=None, progresso=None):
    """O Import Settlements: recoleta os dias de `_dias_do_import`. Dia que falha
    fica como estava e volta em `failed`.

    No share, cada dia custa o NDF Summary e o Other Products inteiros (de
    segundos a minutos), e uma quinzena um a um passava de meia hora. Com
    `workers` > 1 os dias são coletados AO MESMO TEMPO, cada um numa thread com
    o seu request-context (`contexto()`, um gerenciador de contexto: os
    coletores memoizam no `g`). `progresso(dia, falhas)` é chamado a cada dia
    que termina."""
    from concurrent.futures import ThreadPoolExecutor
    dias = _dias_do_import(ref)

    def um(item):
        d, fontes = item
        falhas, linhas = [], 0
        try:
            if contexto is not None:
                with contexto():
                    res = queries.collect_day(d, fontes)
            else:
                res = queries.collect_day(d, fontes)
            for src, rows in res.items():
                if isinstance(rows, Exception):
                    falhas.append({'day': d.isoformat(), 'source': src,
                                   'error': '%s: %s' % (type(rows).__name__, rows)})
                    continue
                _put(d, src, rows, by)
                linhas += len(rows)
        except Exception as exc:                            # noqa: BLE001
            falhas.append({'day': d.isoformat(), 'source': '+'.join(fontes),
                           'error': '%s: %s' % (type(exc).__name__, exc)})
        if progresso:
            progresso(d, falhas)
        return d, falhas, linhas

    if workers > 1 and len(dias) > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            res = list(ex.map(um, dias))
    else:
        res = [um(x) for x in dias]
    return {'days': [d.isoformat() for d, _f, _n in res],
            'failed': [f for _d, fs, _n in res for f in fs],
            'rows': sum(n for _d, _f, n in res)}


# ── O Import em segundo plano ───────────────────────────────────────────────
#  Uma quinzena no share leva minutos mesmo em paralelo, e segurar o request
#  deixava a tela parada no spinner. O Import vira um TRABALHO por decêndio
#  (em memória: um processo só serve a instância), que a tela acompanha pelo
#  `job_status` — fechar a janela não para nada, e clicar de novo no mesmo
#  decêndio devolve o trabalho que já está rodando.
_jobs = {}
_jobs_lock = threading.Lock()


def _snapshot(job):
    return {k: (list(v) if isinstance(v, list) else v) for k, v in job.items()}


def job_status(ref):
    key = domain.decendio_key(*domain.decendio_of(ref))
    with _jobs_lock:
        job = _jobs.get(key)
        return _snapshot(job) if job else None


def start_import(ref, by=''):
    """Dispara (ou devolve, se já roda) o Import Settlements do decêndio de `ref`."""
    R = _R()
    key = domain.decendio_key(*domain.decendio_of(ref))
    dias = _dias_do_import(ref)
    with _jobs_lock:
        atual = _jobs.get(key)
        if atual and atual['state'] == 'running':
            return _snapshot(atual)
        job = {'key': key, 'state': 'running', 'total': len(dias), 'done': 0,
               'days': [], 'failed': [], 'rows': 0, 'by': by,
               'started': store.now(), 'finished': '', 'error': ''}
        _jobs[key] = job
    app = getattr(R, '_FLASK_APP', None)

    def contexto():
        from contextlib import ExitStack
        pilha = ExitStack()
        pilha.enter_context(R._app_context())
        if app is not None:
            pilha.enter_context(app.test_request_context('/__wht-import'))
        return pilha

    def progresso(d, falhas):
        with _jobs_lock:
            job['done'] += 1
            job['days'].append(d.isoformat())
            job['failed'].extend(falhas)

    def corre():
        try:
            res = import_settlements(ref, by, workers=IMPORT_WORKERS, contexto=contexto,
                                     progresso=progresso)
            with _jobs_lock:
                job['rows'] = res['rows']
        except Exception as exc:                            # noqa: BLE001
            R.log.warning('[wht] Import Settlements de %s falhou:\n%s', key, traceback.format_exc())
            with _jobs_lock:
                job['error'] = '%s: %s' % (type(exc).__name__, exc)
        finally:
            with _jobs_lock:
                job['state'] = 'done'
                job['finished'] = store.now()
            R.log.warning('[wht] Import Settlements de %s: %d dia(s), %d linha(s), %d falha(s)',
                          key, job['done'], job['rows'], len(job['failed']))
    threading.Thread(target=corre, name='wht-import', daemon=True).start()
    return _snapshot(job)


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
    # As MESMAS linhas que a tela mostra, com as correções (§702).
    payload = queries.build(ref, with_lines=True)
    otc_por_id = payload.pop('_otc')
    y, m, n = domain.decendio_of(ref)
    ini, fim = domain.decendio_bounds(y, m, n)
    escolhidas = set(keys or ())
    alvo = [r for r in payload['rows'] if r['key'] in otc_por_id and (
        r['key'] in escolhidas if escolhidas else r['status'] == domain.ST_ONLY_OTC)]
    if not alvo:
        raise domain.WhtError('hub_file_empty', 'Nenhuma operação para o arquivo do HUB no decêndio')
    # A correção que ninguém confirmou não vai ao HUB (o 4-olhos, §702).
    pendentes = [r['Internal ID'] or r['key'] for r in alvo if r.get('review') == domain.REVIEW_PENDING]
    if pendentes:
        raise domain.WhtError('hub_file_pending', 'Linha(s) com edição ainda não confirmada: {ids}',
                              ids=', '.join(pendentes[:10]))
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


# ── Edit, Confirm e Delete da tabela (§702) ─────────────────────────────────
#  A correção vai no documento do mês, por linha de ORIGEM (`domain.EDIT_COLS`
#  diz de que lado é cada coluna). Tudo-ou-nada: o lote inteiro é conferido
#  antes de gravar, dentro do mesmo `store.mutate`.
def _origens(doc):
    """({id da operação OTC: linha}, {HUB|chave: linha}) do documento — a
    linha COLETADA/IMPORTADA, sem correção (é ela o `orig` da edição)."""
    otc = {}
    for fatias in (doc.get('otc') or {}).values():
        for src in ('ndf', 'ops'):
            for r in ((fatias or {}).get(src) or {}).get('rows') or []:
                if r.get('id'):
                    otc[r['id']] = r
    for r in doc.get('manual') or ():
        if r.get('id'):
            otc[r['id']] = r
    hub = {}
    for h in doc.get('hub') or ():
        d = domain.parse_date(h.get('date'))
        if d:
            hub['HUB|' + domain.hub_key(dict(h, date=d))] = h
    return otc, hub


def _confere_chaves(item, otc, hub):
    ok = str(item.get('otc_key') or '')
    hk = str(item.get('hub_key') or '')
    if (ok and ok not in otc) or (hk and hk not in hub) or not (ok or hk):
        raise domain.WhtError('edit_row_gone', 'A linha {key} não está mais no WHT — recarregue a tela',
                              key=ok or hk or '?')
    return ok, hk


def edit(ref, items, sid='', name=''):
    """Grava as correções de `items` = [{otc_key, hub_key, changes: {coluna:
    valor}}] — a mesma `changes` em várias linhas é a edição em lote. Cada
    linha corrigida volta a `Pending`, com quem editou como maker. → quantas
    linhas."""
    mes = domain.month_key(ref)
    agora = store.now()

    def fn(doc):
        otc, hub = _origens(doc)
        plano = []
        for it in items or ():
            ok, hk = _confere_chaves(it, otc, hub)
            for col, raw in (it.get('changes') or {}).items():
                alvo = domain.edit_target(col, bool(ok))
                if not alvo:
                    raise domain.WhtError('edit_bad_column', 'A coluna {col} não se edita', col=col)
                lado, campo, tipo = alvo
                chave = ok if lado == 'otc' else hk
                if not chave:
                    raise domain.WhtError('edit_no_side', '{col}: a linha não tem o lado {side}',
                                          col=col, side=lado.upper())
                plano.append((chave, lado, campo, domain.clean_edit(col, tipo, raw, mes, campo),
                              (otc if lado == 'otc' else hub)[chave]))
        edits = doc.setdefault('edits', {})
        tocadas = set()
        for chave, lado, campo, valor, origem in plano:
            e = edits.setdefault(chave, {'side': lado, 'fields': {}, 'orig': {}})
            if campo not in e['orig']:
                e['orig'][campo] = origem.get(campo, origem.get('day') if campo == 'date' else None)
            e['fields'][campo] = valor
            tocadas.add(chave)
        for chave in tocadas:
            edits[chave].update({'status': domain.REVIEW_PENDING, 'maker': sid, 'maker_name': name,
                                 'at': agora, 'checker': '', 'checker_name': '', 'checked_at': ''})
        return len(items or ())
    return store.mutate(mes, fn)


def approve(ref, items, sid='', name=''):
    """Confirma as correções `Pending` das linhas `items` = [{otc_key,
    hub_key}]. O próprio maker não confirma (`authz.is_own_change`, §553) — o
    lote inteiro recusa antes de gravar. → quantas correções."""
    from apps.pages.platform import authz
    mes = domain.month_key(ref)
    agora = store.now()

    def fn(doc):
        edits = doc.get('edits') or {}
        alvo = []
        for it in items or ():
            for k in (it.get('otc_key'), it.get('hub_key')):
                e = edits.get(k) if k else None
                if e and e.get('status') == domain.REVIEW_PENDING:
                    if authz.is_own_change(e.get('maker'), sid):
                        raise domain.WhtError('approve_own', 'Quem editou não confirma a própria edição')
                    alvo.append(e)
        if not alvo:
            raise domain.WhtError('approve_none', 'Nenhuma edição pendente nas linhas escolhidas')
        for e in alvo:
            e.update({'status': domain.REVIEW_APPROVED, 'checker': sid, 'checker_name': name,
                      'checked_at': agora})
        return len(alvo)
    return store.mutate(mes, fn)


def delete(ref, items, sid='', name=''):
    """Tira as linhas `items` = [{otc_key, hub_key}] do WHT: as duas origens
    da linha (a operação OTC e a linha do HUB) vão para `deleted`, e a coleta
    seguinte não as traz de volta. → quantas linhas."""
    mes = domain.month_key(ref)
    agora = store.now()

    def fn(doc):
        otc, hub = _origens(doc)
        chaves = []
        for it in items or ():
            ok, hk = _confere_chaves(it, otc, hub)
            chaves += [k for k in (ok, hk) if k]
        apagadas = doc.setdefault('deleted', {})
        for k in chaves:
            apagadas[k] = {'by': sid, 'name': name, 'at': agora}
        return len(items or ())
    return store.mutate(mes, fn)


# As colunas do Add Row (§702): o lado OTC. Obrigatórias: produto, LOB,
# evento, LE, a data do evento, o valor e a contraparte — e o Trade Date no
# swap (o IR é regressivo).
ADD_REQUIRED = ('Product', 'LOB', 'Event', 'OTC_LE', 'OTC_ET', 'OTC_GV', 'OTC_cntpy')


def add(ref, items, sid='', name=''):
    """Inclui à mão as operações `items` = [{fields: {coluna: valor}}] no mês
    do decêndio (`manual`): o código, o tributo e o imposto saem do
    `queries.derive` (o IR digitado em `Devido` vence), e a linha nasce
    `Pending` — outro usuário a confirma, como uma edição. → quantas."""
    mes = domain.month_key(ref)
    agora = store.now()
    novas = []
    for it in items or ():
        f = dict(it.get('fields') or {})
        falta = [c for c in ADD_REQUIRED if not str(f.get(c) or '').strip()]
        if falta:
            raise domain.WhtError('add_missing', 'Preencha: {cols}', cols=', '.join(falta))
        v = {}
        for col, raw in f.items():
            alvo = domain.edit_target(col, True)
            if not alvo or alvo[0] != 'otc' or (col in ('OTC_IR', 'OTC_id', 'OTC_tributo')):
                continue
            if col == 'Devido' and not str(raw or '').strip():
                continue
            v[alvo[1]] = domain.clean_edit(col, alvo[2], raw, mes, alvo[1])
        calc = queries.derive({'product': v.get('product'), 'lob': v.get('lob'), 'event': v.get('event'),
                               'gross': v.get('gross'), 'counterparty': v.get('counterparty'),
                               'taxid': v.get('taxid'), 'trade_date': v.get('trade_date'),
                               'day': v.get('day'), 'le': v.get('le')})
        linha = {'day': v['day'], 'source': 'manual', 'seq': 0,
                 'internal_id': v.get('internal_id', ''), 'b3_id': v.get('b3_id', ''),
                 'product': v['product'], 'lob': v['lob'], 'event': domain.event_of(v['event']),
                 'trade_date': v.get('trade_date', ''), 'gross': v['gross'],
                 'devido': v['devido'] if 'devido' in v else calc['devido'], 'taxable': calc['taxable'],
                 'counterparty': v['counterparty'], 'taxid': v.get('taxid', ''), 'le': v['le'],
                 'ir_unknown': False, 'by': sid, 'at': agora}
        novas.append(linha)

    def fn(doc):
        lista = doc.setdefault('manual', [])
        edits = doc.setdefault('edits', {})
        for linha in novas:
            base = '%s|manual|%s|%s' % (linha['day'], linha['le'], linha['internal_id'] or linha['b3_id'] or 'X')
            n = 1 + sum(1 for r in lista if str(r.get('id') or '').startswith(base + '|'))
            linha['id'] = '%s|%d' % (base, n)
            linha['seq'] = len(lista)
            lista.append(linha)
            edits[linha['id']] = {'side': 'otc', 'fields': {}, 'orig': {}, 'added': True,
                                  'status': domain.REVIEW_PENDING, 'maker': sid, 'maker_name': name,
                                  'at': agora, 'checker': '', 'checker_name': '', 'checked_at': ''}
        return len(novas)
    return store.mutate(mes, fn)
