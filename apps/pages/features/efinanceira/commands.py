# -*- coding: utf-8 -*-
"""Escrita da E-Financeira: o Import Settlements do mês (um TRABALHO em segundo
plano, os dias em paralelo — o desenho do WHT, §694), a correção da tela (Edit,
Confirm, Delete, Add Row, com o 4-olhos) e o arquivo do mês, gravado no share e
devolvido para download.

O arquivo vai para `Regulatory\\E-Financeira\\AAAA\\MM. Month` (equipe,
30/10/2026), um por página, e só sai com TODAS as linhas completas e
confirmadas: é declaração à Receita, e uma linha sem CNPJ ou sem a data do CGD
não se corrige depois de entregue.
"""
import os
import threading
import traceback

from apps.pages.features.efinanceira import domain, queries
from apps.pages.features.efinanceira.infra import store


def _R():
    from apps.pages import routes
    return routes


# ── O Import Settlements ────────────────────────────────────────────────────
def _put(day, source, rows, by=''):
    """Substitui a fatia (dia × fonte) do mês; grava só se mudou."""
    def fn(doc):
        dia = doc['days'].setdefault(day.isoformat(), {})
        if (dia.get(source) or {}).get('rows') == rows and source in dia:
            return False
        dia[source] = {'rows': rows, 'at': store.now(), 'by': by}
        return True
    return store.mutate(domain.month_key(day), fn)


def _dias_do_import(ref):
    """Os dias úteis do mês de `ref` até hoje — todos: a liquidação de um dia
    muda depois (o evento da B3 chega, a recompra é corrigida), e o arquivo é
    do mês inteiro."""
    R = _R()
    ini, fim = domain.month_bounds(ref)
    return queries.bizdays(ini, min(fim, R._br_now().date()))


try:
    IMPORT_WORKERS = int(os.getenv('OTC_EFIN_IMPORT_WORKERS', '4') or 4)
except ValueError:
    IMPORT_WORKERS = 4


def import_settlements(ref, by='', workers=1, contexto=None, progresso=None):
    """Recoleta os dias de `_dias_do_import`, das três fontes. Dia × fonte que
    falha fica como estava e volta em `failed`. Com `workers` > 1 os dias são
    coletados AO MESMO TEMPO, cada um no seu request-context (`contexto()`)."""
    from concurrent.futures import ThreadPoolExecutor
    dias = _dias_do_import(ref)

    def um(d):
        falhas, linhas = [], 0
        try:
            if contexto is not None:
                with contexto():
                    res = queries.collect_day(d)
            else:
                res = queries.collect_day(d)
            for src, rows in res.items():
                if isinstance(rows, Exception):
                    falhas.append({'day': d.isoformat(), 'source': src,
                                   'error': '%s: %s' % (type(rows).__name__, rows)})
                    continue
                _put(d, src, rows, by)
                linhas += len(rows)
        except Exception as exc:                            # noqa: BLE001
            falhas.append({'day': d.isoformat(), 'source': '+'.join(domain.SOURCES),
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


#  Um mês no share leva minutos mesmo em paralelo: o Import é um TRABALHO por
#  mês (em memória — um processo só serve a instância), que a tela acompanha
#  pelo `job_status`. Fechar a janela não para nada, e clicar de novo no mesmo
#  mês (de qualquer uma das quatro páginas) devolve o trabalho que já roda.
_jobs = {}
_jobs_lock = threading.Lock()


def _snapshot(job):
    return {k: (list(v) if isinstance(v, list) else v) for k, v in job.items()}


def job_status(ref):
    with _jobs_lock:
        job = _jobs.get(domain.month_key(ref))
        return _snapshot(job) if job else None


def start_import(ref, by=''):
    """Dispara (ou devolve, se já roda) o Import Settlements do mês de `ref`."""
    R = _R()
    key = domain.month_key(ref)
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
            pilha.enter_context(app.test_request_context('/__efin-import'))
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
            R.log.warning('[efin] Import Settlements de %s falhou:\n%s', key, traceback.format_exc())
            with _jobs_lock:
                job['error'] = '%s: %s' % (type(exc).__name__, exc)
        finally:
            with _jobs_lock:
                job['state'] = 'done'
                job['finished'] = store.now()
            R.log.warning('[efin] Import Settlements de %s: %d dia(s), %d evento(s), %d falha(s)',
                          key, job['done'], job['rows'], len(job['failed']))
    threading.Thread(target=corre, name='efin-import', daemon=True).start()
    return _snapshot(job)


# ── A correção da tela (Edit, Confirm, Delete, Add Row) ─────────────────────
#  A operação é montada na LEITURA e a coleta seguinte substitui a fatia do
#  dia: a correção fica à parte (`edits`), pela CHAVE da operação, e é aplicada
#  antes de fechar a linha — sobrevive a um novo Import. Nasce `Pending` (o
#  maker é quem editou) e outro usuário a confirma (§553). Tudo-ou-nada: o lote
#  é conferido inteiro antes de gravar.
def _ops_por_chave(ref):
    """{chave: operação} do mês (todas as páginas) — lido FORA da trava do
    armazém: a leitura passa pelo Tracking Docs e pelos cadastros."""
    ym = domain.month_key(ref)
    ops, _excl = queries.operations(store.load(ym), ym)
    return {o['key']: o for o in ops}


def _confere(ops, items):
    for it in items or ():
        k = str(it.get('key') or '')
        if k not in ops:
            raise domain.EfinError('edit_row_gone', 'A linha {key} não está mais na E-Financeira — '
                                   'recarregue a tela', key=k or '?')


def edit(ref, items, sid='', name=''):
    """`items` = [{key, changes: {coluna: valor}}] — a mesma `changes` em várias
    linhas é o lote. Cada linha corrigida volta a `Pending`. → quantas."""
    ops = _ops_por_chave(ref)
    _confere(ops, items)
    selects = {'LE': sorted(queries.declarants())}
    plano = []
    for it in items or ():
        k = it['key']
        for col, raw in (it.get('changes') or {}).items():
            campo = domain.EDIT_COLS.get(col, (None,))[0]
            plano.append((k, campo, domain.clean_edit(col, raw, selects), ops[k].get('orig', {}).get(
                campo, ops[k].get(campo))))
    if not plano:
        return 0
    agora = store.now()

    def fn(doc):
        edits = doc.setdefault('edits', {})
        tocadas = set()
        for k, campo, valor, origem in plano:
            e = edits.setdefault(k, {'fields': {}, 'orig': {}})
            if campo not in e['orig']:
                e['orig'][campo] = origem
            e['fields'][campo] = valor
            tocadas.add(k)
        for k in tocadas:
            edits[k].update({'status': domain.REVIEW_PENDING, 'maker': sid, 'maker_name': name,
                             'at': agora, 'checker': '', 'checker_name': '', 'checked_at': ''})
        return len(tocadas)
    return store.mutate(domain.month_key(ref), fn)


def approve(ref, items, sid='', name=''):
    """Confirma as correções `Pending` de `items` = [{key}]. O próprio maker não
    confirma (`authz.is_own_change`, §553) — o lote inteiro recusa. → quantas."""
    from apps.pages.platform import authz
    agora = store.now()

    def fn(doc):
        edits = doc.get('edits') or {}
        alvo = []
        for it in items or ():
            e = edits.get(str(it.get('key') or ''))
            if e and e.get('status') == domain.REVIEW_PENDING:
                if authz.is_own_change(e.get('maker'), sid):
                    raise domain.EfinError('approve_own', 'Quem editou não confirma a própria edição')
                alvo.append(e)
        if not alvo:
            raise domain.EfinError('approve_none', 'Nenhuma edição pendente nas linhas escolhidas')
        for e in alvo:
            e.update({'status': domain.REVIEW_APPROVED, 'checker': sid, 'checker_name': name,
                      'checked_at': agora})
        return len(alvo)
    return store.mutate(domain.month_key(ref), fn)


def delete(ref, items, sid='', name=''):
    """Tira as operações `items` = [{key}] do mês: vão para `deleted`, e o
    Import seguinte não as traz de volta. → quantas."""
    ops = _ops_por_chave(ref)
    _confere(ops, items)
    agora = store.now()

    def fn(doc):
        apagadas = doc.setdefault('deleted', {})
        for it in items or ():
            apagadas[it['key']] = {'by': sid, 'name': name, 'at': agora}
        return len(items or ())
    return store.mutate(domain.month_key(ref), fn)


def add(ref, items, sid='', name=''):
    """Inclui à mão as operações `items` = [{fields: {coluna: valor}}] no mês: a
    identidade, o prêmio e as datas vão na linha; os totais do arquivo (Total
    Débito/Crédito, Saldo, Pagamento Acumulado) como CORREÇÃO, para valerem
    sobre o calculado. Nasce `Pending` — outro usuário a confirma. → quantas."""
    selects = {'LE': sorted(queries.declarants())}
    novas = []
    for it in items or ():
        f = dict(it.get('fields') or {})
        falta = [c for c in domain.ADD_REQUIRED if not str(f.get(c) or '').strip()]
        if falta:
            raise domain.EfinError('add_missing', 'Preencha: {cols}', cols=', '.join(falta))
        base, totais = {}, {}
        for col, raw in f.items():
            if col not in domain.EDIT_COLS:
                continue
            campo = domain.EDIT_COLS[col][0]
            valor = domain.clean_edit(col, raw, selects)
            if campo in domain.OUTPUT_FIELDS:
                if str(raw or '').strip():
                    totais[campo] = valor
            else:
                base[campo] = valor
        novas.append((base, totais))
    agora = store.now()

    def fn(doc):
        lista = doc.setdefault('manual', [])
        edits = doc.setdefault('edits', {})
        for base, totais in novas:
            raiz = 'M|' + domain.op_key(base.get('le'), base.get('b3_id'), base.get('internal_id'))
            n = 1 + sum(1 for r in lista if str(r.get('key') or '').startswith(raiz + '|'))
            linha = dict(base, key='%s|%d' % (raiz, n), by=sid, at=agora)
            lista.append(linha)
            edits[linha['key']] = {'fields': totais, 'orig': {}, 'added': True,
                                   'status': domain.REVIEW_PENDING, 'maker': sid, 'maker_name': name,
                                   'at': agora, 'checker': '', 'checker_name': '', 'checked_at': ''}
        return len(novas)
    return store.mutate(domain.month_key(ref), fn)


# ── O arquivo do mês ────────────────────────────────────────────────────────
# O teste aponta a raiz para um tmp trocando este atributo; None = o share.
ROOT = None


def file_dir(ref):
    """`<share>\\Confirmation\\Derivativos\\OTC Tracker\\Regulatory\\E-Financeira\\AAAA\\MM. Month`."""
    R = _R()
    base = ROOT or os.path.join(R.Config.SHARED_DRIVE_ROOT, 'Confirmation', 'Derivativos', 'OTC Tracker',
                                'Regulatory', 'E-Financeira')
    return os.path.join(base, ref.strftime('%Y'),
                        ref.strftime('%m') + '. ' + R._EN_MONTH_NAMES[ref.month - 1])


def generate(page, ref, sid=''):
    """O arquivo da página `page` no mês de `ref`: as MESMAS linhas da tela, no
    layout da equipe, gravado no share (substitui o do mês) e devolvido. Recusa
    com linha pendente de confirmação e com linha incompleta (diz quais).
    → (nome, bytes, quantas, caminho)."""
    payload = queries.build(page, ref, with_ops=True)
    ops = payload.pop('_ops')
    if not ops:
        raise domain.EfinError('file_empty', 'Nenhuma operação desta página no mês')
    pend = [o.get('b3_id') or o['key'] for o in ops if o.get('review') == domain.REVIEW_PENDING]
    if pend:
        raise domain.EfinError('file_pending', 'Linha(s) com correção ainda não confirmada: {ids}',
                               ids=', '.join(pend[:10]))
    falta = [(o.get('b3_id') or o.get('internal_id') or o['key'], o['missing']) for o in ops if o['missing']]
    if falta:
        raise domain.EfinError('file_missing', '{n} linha(s) incompleta(s): {rows}', n=len(falta),
                               rows='; '.join('%s (%s)' % (k, ', '.join(m)) for k, m in falta[:8]))
    ym = payload['month']['key']
    nome = domain.file_name(page, ym)
    corpo = domain.file_text([o['line'].split(';') for o in ops]).encode(domain.ENCODING, errors='replace')
    pasta = file_dir(ref)
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, nome)
    tmp = caminho + '.tmp'
    with open(tmp, 'wb') as fh:
        fh.write(corpo)
    os.replace(tmp, caminho)
    agora = store.now()

    def fn(doc):
        doc.setdefault('files', {})[page] = {'name': nome, 'path': caminho, 'at': agora, 'sid': sid,
                                             'n': len(ops), 'lines': {o['key']: o['line'] for o in ops}}
        doc.setdefault('history', []).append({'page': page, 'name': nome, 'path': caminho, 'at': agora,
                                              'sid': sid, 'n': len(ops)})
    store.mutate(ym, fn)
    return nome, corpo, len(ops), caminho
