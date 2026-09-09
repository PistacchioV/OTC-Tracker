# -*- coding: utf-8 -*-
"""Leitura DB-ONLY com CURA SÍNCRONA — a fase 3 da migração, endurecida
(2026-09-02: leitura servida só pelos bancos; o JSON fica como meio de
ESCRITA, com o espelho convertendo).

O leitor continua não confiando cegamente no banco: o `_manifest` (caminho,
mtime, tamanho — gravado pelo motor a cada conversão) tem de provar que a
tabela reflete o JSON **como ele está agora** em disco. O que mudou é o
DESFECHO quando não prova: em vez de devolver `None` e deixar o chamador
servir o JSON, o leitor **converte AGORA** (`duck_mirror.convert_sync` —
a tarefa entra na fila da thread do espelho e é esperada, então nunca há
dois escritores no mesmo banco) e relê. A resposta sai do banco; o JSON só é
LIDO pelo conversor. É o que mantém a garantia do §6 ("edição na tela vale no
request seguinte") com a leitura DB-only: a escrita grava o JSON, e a
primeira leitura que chegar antes do espelho paga a conversão e lê o banco já
curado.

`None` ainda existe, e é o canal de EMERGÊNCIA (o chamador mantém o caminho
JSON de sempre): espelho DESLIGADO (`OTC_DISABLE_SCHEDULERS`/
`OTC_DISABLE_DUCK_MIRROR` — os testes, que trocam caminhos e leem o JSON),
timeout da fila num share atolado, conversão que falhou (JSON corrompido), o
`expected_path` de um caminho trocado, e os payloads que o banco não
reconstrói (objeto — as recons).

As conexões aqui são as CRUAS do DuckDB (como as do motor/espelho), não as do
`database_access`: os bancos espelhados têm um escritor só (a thread do
espelho, ou o script de carga) e leitores de melhor esforço — a colisão
intra-processo com o espelho escrevendo vira exceção, capturada, cura, releitura.
"""
import json
import logging
import os
import threading
import time

import duckdb

# A abertura vai pela CAMADA (`duckdb_read`) e não pelo `duckdb.connect` cru: é
# ela que emite os eventos do farol do `database_access` (`connection_opened`,
# `file_lock_*`, os tempos de espera) e que cria o `.lock` do banco na primeira
# vez. Sem isso, os bancos do espelho — dezenas, e um NOVO a cada produto ou
# cadastro que aparece — ficavam fora do painel: nenhum evento, nenhum lock, e
# nenhuma pista de por que uma leitura DB-first demorou ou recusou.
#
# Não são caminhos que caibam no `DATABASE_ACCESS_PATHS` do config: aquela
# tupla é a lista FIXA que a subida confere, e a árvore do espelho nasce dos
# dados (um banco por produto de arquivo-dia, um por JSON avulso). O `.lock`
# vem de graça na primeira abertura, que é o que a camada faz.
#
# Medido: 12,67 ms por abertura pela camada contra 12,82 ms crua — a abertura
# do DuckDB domina, e o lock compartilhado mais o permit somem no ruído.
from apps.pages.database_access import duckdb_read, db_gate

from apps.pages.json_to_duckdb import q


log = logging.getLogger('otc_tracker')

# ── O cronômetro do share (era o FREIO) ──────────────────────────────────────
# O flip DB-first foi medido em disco local (~12 ms por abertura); no SHARE a
# mesma abertura custa segundos, e havia aqui um freio ADAPTATIVO que armava
# um modo só-JSON por 10 min quando uma leitura estourava o teto. Com a
# leitura DB-ONLY (2026-09-02) o modo só-JSON deixou de existir — não há mais
# fallback para o freio escolher —, então o que sobra é a TELEMETRIA: a
# leitura lenta continua cronometrada e avisada no log (com a mesma janela de
# 10 min silenciando a repetição, senão o aviso seria o log inteiro), para a
# lentidão do share não virar um "a tela demora" sem pista. Se a instância do
# time sofrer com isso, a resposta é operacional (mover os bancos, ajustar o
# storage) — não um retorno silencioso ao JSON.
#
# `OTC_DUCK_READ_SLOW_SECONDS` ajusta o teto do aviso; `0` desliga a medição.
try:
    _FREIO_LIMIAR = float(os.getenv('OTC_DUCK_READ_SLOW_SECONDS', '0.35') or 0)
except ValueError:
    _FREIO_LIMIAR = 0.35
_FREIO_ESPERA = 600.0
_freio = {'ate': 0.0}

# Quanto o leitor espera uma ESCRITA do espelho em curso no mesmo banco antes
# de conectar (§422). Passado o teto ele conecta assim mesmo: se a escrita
# ainda estiver aberta o DuckDB recusa, o `_ler` devolve None e a cura síncrona
# — que entra na MESMA fila do espelho — espera a escrita terminar de graça.
_GATE_READ_WAIT_SECONDS = 10.0

# ── Cura que NÃO cura: a quarentena ─────────────────────────────────────────
# A cura síncrona resolve o banco frio ou defasado, e para isso vale a espera.
# Mas há falha de conversão que NÃO passa com uma segunda tentativa: no share
# do JPM o DuckDB devolve `IO Error: Could not move file: Access is denied`
# ao renomear o arquivo do banco, e ali toda leitura do dia pagava a fila do
# espelho, a conversão inteira, o segundo `_ler` — e caía no JSON do mesmo
# jeito. Pior: o `_cura()` do fim ainda ENFILEIRAVA uma retentativa, que
# atravancava a cura síncrona da leitura seguinte. Uma tela que abre oito
# arquivos-dia pagava isso oito vezes, e o Summary não terminava de carregar.
#
# Então o arquivo cuja cura não resolveu entra em QUARENTENA: pela janela, a
# leitura vai DIRETO ao JSON, sem fila e sem retentativa. É a mesma forma do
# `_ensure_notif_db` que falha e espera 5 min antes de tentar de novo — a
# diferença entre um banco frio (curável, e a espera se paga) e um banco que
# o ambiente não deixa escrever (incurável até alguém mexer no share).
#
# A quarentena é por ARQUIVO de origem e vive só no processo: reiniciar o app
# ou esperar a janela tenta de novo, que é o que faz a correção do share valer
# sem ninguém rodar nada. `OTC_DUCK_HEAL_RETRY_SECONDS` ajusta; `0` desliga.
try:
    _CURA_ESPERA = float(os.getenv('OTC_DUCK_HEAL_RETRY_SECONDS', '300') or 0)
except ValueError:
    _CURA_ESPERA = 300.0
# Quantas curas seguidas podem falhar antes de a quarentena valer para TODOS os
# arquivos. A marca por arquivo sozinha não bastava: quando o share recusa a
# escrita, TODA conversão falha, e uma tela que abre dez arquivos-dia ainda
# pagava dez curas — cada uma até o timeout de 30s do `convert_sync`, porque a
# marca do arquivo A não diz nada sobre o B. Cinco minutos de espera não
# ajudam quem está esperando a PRIMEIRA carga. Com o disjuntor, a primeira
# falha custa uma cura e o resto da tela vai direto ao JSON.
_CURA_FALHAS_SEGUIDAS = 2
_cura_falhou = {}
_cura_geral = {'ate': 0.0, 'seguidas': 0}
_cura_lock = threading.Lock()


def _cura_em_quarentena(jpath):
    if not _CURA_ESPERA:
        return False
    with _cura_lock:
        agora = time.monotonic()
        return agora < _cura_geral['ate'] or agora < _cura_falhou.get(jpath, 0.0)


def _cura_marca_falha(jpath):
    """A cura rodou e o banco continua sem responder — não insista já."""
    if not _CURA_ESPERA:
        return
    with _cura_lock:
        agora = time.monotonic()
        novo = _cura_falhou.get(jpath, 0.0) < agora
        _cura_falhou[jpath] = agora + _CURA_ESPERA
        _cura_geral['seguidas'] += 1
        disjuntor = (_cura_geral['seguidas'] >= _CURA_FALHAS_SEGUIDAS
                     and _cura_geral['ate'] < agora)
        if disjuntor:
            _cura_geral['ate'] = agora + _CURA_ESPERA
    if disjuntor:
        log.warning('[duck-read] %d curas seguidas não resolveram (a última em %s) — '
                    'toda leitura vai ao JSON pelos próximos %.0f min, sem tentar '
                    'converter. O log do duck-mirror diz o motivo; ajuste em '
                    'OTC_DUCK_HEAL_RETRY_SECONDS',
                    _cura_geral['seguidas'], os.path.basename(jpath), _CURA_ESPERA / 60.0)
    elif novo:
        log.warning('[duck-read] a cura não resolveu %s — servindo o JSON e '
                    'sem tentar de novo por %.0f min (o log do duck-mirror diz '
                    'por quê; ajuste em OTC_DUCK_HEAL_RETRY_SECONDS)',
                    os.path.basename(jpath), _CURA_ESPERA / 60.0)


def _cura_marca_ok(jpath):
    """Leitura pelo banco deu certo: some a marca do arquivo e o disjuntor
    volta a zero — a contagem é de falhas SEGUIDAS, e uma conversão que
    funcionou diz que o share voltou."""
    if not _CURA_ESPERA:
        return
    if jpath in _cura_falhou or _cura_geral['seguidas']:
        with _cura_lock:
            _cura_falhou.pop(jpath, None)
            _cura_geral['seguidas'] = 0


def _memo_req():
    """Memo por REQUEST (Flask `g`); None fora de request. O mesmo arquivo-dia
    é lido várias vezes na montagem de UMA tela (o Other Products Summary abre
    o banco de NDF Commodities oito vezes), e no share cada abertura é ida e
    volta de rede. A chave leva mtime e tamanho do JSON, então uma gravação no
    meio do request invalida sozinha; e o que se guarda são os `_raw` (texto),
    reparseados a cada hit — cada consumidor recebe objetos SEUS, como se
    tivesse lido o arquivo."""
    try:
        from flask import g, has_app_context
        if not has_app_context():
            return None
        return g.setdefault('_duck_read_memo', {})
    except Exception:                                       # noqa: BLE001
        return None
_freio_lock = threading.Lock()


def _freio_armado():
    return time.monotonic() < _freio['ate']


def _freio_mede(segundos, db):
    """Cronômetro de UMA leitura de espelho: acima do teto, WARNING no log
    (um por janela de 10 min). Chamado também no caminho de exceção — uma
    abertura que estourou depois de pendurar no lock é o mesmo sintoma."""
    if not _FREIO_LIMIAR or segundos < _FREIO_LIMIAR:
        return
    with _freio_lock:
        rearmando = _freio_armado()
        _freio['ate'] = time.monotonic() + _FREIO_ESPERA
    if not rearmando:
        log.warning(
            '[duck-read] leitura do espelho levou %.2fs (%s) — a leitura é '
            'DB-only, então isto é latência de tela, não troca de fonte '
            '(teto do aviso em OTC_DUCK_READ_SLOW_SECONDS)',
            segundos, os.path.basename(str(db)), )


def _data_root():
    from apps.pages import routes
    return os.path.normpath(routes._B3_DATA_DIR)


def _limpo(rows):
    """NULL → '' nas colunas de texto: o JSON de origem guarda string em tudo
    que existe, e um `str(None)` no consumidor viraria o literal 'None'."""
    out = []
    for r in rows:
        out.append({k: ('' if v is None else v) for k, v in r.items()})
    return out


def table_rows(db_name, table, rel, schema='main', order_by=None, heal=None,
               manifest_key=None, expected_path=None, sync_kind=None):
    """As linhas de `table`, servidas pelo BANCO. Banco frio ou defasado é
    CURADO na hora (`convert_sync`) e relido — `None` só sobra para a
    emergência: espelho desligado (testes), timeout, conversão que falhou.

    `rel` é o caminho relativo à raiz de dados; `manifest_key` é a CHAVE no
    `_manifest` quando ela difere do caminho (as tabelas de cadastro levam a
    versão do formato no sufixo — um banco no formato antigo simplesmente não
    casa e a cura reconverte no novo). `heal` troca o aviso ASSÍNCRONO padrão
    (`notify_write` do caminho) e `sync_kind` força a tarefa da cura síncrona
    — os arquivos de calendário precisam dos dois ('holidays'), porque o nome
    deles só o registro conhece."""
    try:
        raiz = _data_root()
        jpath = os.path.join(raiz, rel.replace('/', os.sep))
        # `expected_path` é o guarda da SUPERFÍCIE DE PATCH: o chamador diz de
        # que arquivo ELE leria, e se não for o canônico que o espelho cobre
        # (um `_cpd_path`/`data_path` trocado por teste ou config), o banco não
        # responde — refletir OUTRO arquivo com carimbo de fresco seria a
        # fonte errada.
        if expected_path is not None and \
                os.path.normpath(str(expected_path)) != os.path.normpath(jpath):
            return None
        st = os.stat(jpath)
    except Exception:                                       # noqa: BLE001
        return None

    def _cura():
        try:
            from apps.pages import duck_mirror
            if heal is not None:
                heal()
            else:
                duck_mirror.notify_write(jpath)
        except Exception:                                   # noqa: BLE001
            pass

    def _ler():
        """Uma tentativa de leitura pelo banco; None = frio/defasado/em uso —
        o chamador cura e tenta de novo. Exceção aqui é o mesmo sintoma
        (banco sendo escrito pelo espelho neste instante), então vira None
        também: a cura síncrona ESPERA a fila do espelho, que é justamente o
        que resolve a colisão."""
        try:
            from apps.pages import duck_mirror
            # `db_name` pode ser um CAMINHO relativo (`cache/new deals/NDF/Vanilla.db`):
            # a pasta `db/` espelha a árvore de origem desde a quebra em subpastas.
            db = os.path.join(duck_mirror._out_dir(raiz), *db_name.split('/'))
            if not os.path.isfile(db):
                return None
            t0 = time.monotonic()
            gate = db_gate(db)
            gate.enter_read(_GATE_READ_WAIT_SECONDS)
            try:
                with duckdb_read(db) as con:
                    row = con.execute('SELECT mtime, fsize FROM _manifest WHERE path = ?',
                                      [manifest_key or rel]).fetchone()
                    if not row or abs(row[0] - st.st_mtime) >= 1e-6 or row[1] != st.st_size:
                        return None
                    sql = 'SELECT * FROM %s.%s' % (q(schema), q(table))
                    if order_by:
                        sql += ' ORDER BY ' + order_by
                    cur = con.execute(sql)
                    cols = [d[0] for d in cur.description]
                    return _limpo(dict(zip(cols, r)) for r in cur.fetchall())
            finally:
                gate.exit_read()
                _freio_mede(time.monotonic() - t0, db)
        except Exception:                                   # noqa: BLE001
            return None

    try:
        rows = _ler()
        if rows is None:
            # CURA SÍNCRONA: converte AGORA (na fila da thread do espelho —
            # serializado, nunca dois escritores no mesmo banco) e relê. Com o
            # espelho desligado ou no timeout, sobra o aviso assíncrono e o
            # chamador cai no JSON — o canal de emergência.
            if _cura_em_quarentena(jpath):
                return None                       # já se sabe que não resolve
            from apps.pages import duck_mirror
            if duck_mirror.convert_sync(jpath, kind=sync_kind):
                rows = _ler()
            if rows is None:
                _cura_marca_falha(jpath)
                _cura()
        else:
            _cura_marca_ok(jpath)
        return rows
    except Exception:                                       # noqa: BLE001
        return None


def raw_records(db_name, table, rel, expected_path=None, manifest_key=None):
    """Os REGISTROS ORIGINAIS de uma tabela de registros — a coluna `_raw`
    (cada registro exatamente como está no JSON), na ordem do arquivo
    (`_seq`; o CAST cobre a tabela que o gravou como texto).

    É o canal de fidelidade do flip: reconstruir pelo conjunto de colunas
    poria chave com NULL onde o JSON não tinha chave nenhuma, e há consumidor
    que decide pela AUSÊNCIA (o `_contacts_norm` do CounterpartyDetails).
    Linha sem `_raw`/`_seq` (banco em formato antigo) devolve `None` — o
    manifest versionado já impede o caso, isto é o cinto de segurança."""
    from apps.pages.json_to_duckdb import _refdata_manifest_key
    mkey = manifest_key or _refdata_manifest_key(rel)
    memo, chave = None, None
    try:
        jpath = os.path.join(_data_root(), rel.replace('/', os.sep))
        if expected_path is None or \
                os.path.normpath(str(expected_path)) == os.path.normpath(jpath):
            st = os.stat(jpath)
            memo = _memo_req()
            chave = ('raw', jpath, mkey, st.st_mtime, st.st_size)
    except Exception:                                       # noqa: BLE001
        memo = None
    if memo is not None and chave in memo:
        return [json.loads(c) for c in memo[chave]]
    rows = table_rows(db_name, table, rel, manifest_key=mkey,
                      order_by='CAST("_seq" AS BIGINT)',
                      expected_path=expected_path)
    if rows is None:
        return None
    crus, out = [], []
    for r in rows:
        cru = r.get('_raw')
        if not cru:
            return None
        try:
            out.append(json.loads(cru))
        except ValueError:
            return None
        crus.append(cru)
    if memo is not None:
        memo[chave] = crus
    return out


def day_payload(path):
    """O conteúdo de UM arquivo-dia pelo banco da rotina — a LISTA original,
    na ordem do arquivo. Banco frio ou defasado é CURADO na hora
    (`convert_sync`) e relido; `None` sobra para a emergência (espelho
    desligado, timeout, conversão falhou) e para o payload-OBJETO.

    Só o payload-LISTA reconstrói (é a forma dos New Deals, Pending
    Confirmation, arquivos B3…): o manifest diz que a conversão gerou UMA
    tabela, e ela carrega `_raw`/`_seq`. Payload-objeto (as recons, que viram
    sub-tabelas + `_meta`) fica com o JSON — remontar o objeto pelas tabelas
    normalizadas seria adivinhar chave e ordem — e NÃO dispara cura: converter
    de novo não muda a forma dele."""
    try:
        from apps.pages import duck_mirror
        from apps.pages import json_to_duckdb as core
        raiz = _data_root()
        jpath = os.path.normpath(str(path))
        rel = os.path.relpath(jpath, raiz)
        if rel.startswith('..'):
            return None
        rel = rel.replace(os.sep, '/')
        alvo = core._daily_rel_target(rel)
        if alvo is None:
            return None
        db_name, schema, tabela = alvo
        st = os.stat(jpath)
        memo = _memo_req()
        chave = ('day', jpath, st.st_mtime, st.st_size)
        if memo is not None and chave in memo:
            crus = memo[chave]
            return None if crus is None else [json.loads(c) for c in crus]

        _OBJETO = object()       # sentinela: payload que o banco não reconstrói

        def _ler():
            """(dados) | None = frio/defasado (curável) | _OBJETO = fica no JSON."""
            try:
                # `db_name` pode ser um CAMINHO relativo
                # (`cache/new deals/NDF/Vanilla.db`): a pasta `db/` espelha a
                # árvore de origem desde a quebra em subpastas.
                db = os.path.join(duck_mirror._out_dir(raiz), *db_name.split('/'))
                if not os.path.isfile(db):
                    return None
                t0 = time.monotonic()
                gate = db_gate(db)
                gate.enter_read(_GATE_READ_WAIT_SECONDS)
                try:
                    with duckdb_read(db) as con:
                        row = con.execute(
                            'SELECT mtime, fsize, targets FROM _manifest WHERE path = ?',
                            [core._dataset_manifest_key(rel)]).fetchone()
                        if not row or abs(row[0] - st.st_mtime) >= 1e-6 or row[1] != st.st_size:
                            return None
                        if json.loads(row[2] or '[]') != ['%s.%s' % (schema, tabela)]:
                            return _OBJETO     # payload-objeto: fica no JSON
                        alvo_sql = '%s.%s' % (q(schema), q(tabela))
                        cols = [d[0] for d in
                                con.execute('SELECT * FROM %s LIMIT 0' % alvo_sql).description]
                        if cols == ['_empty']:
                            return []          # o dia existe e está vazio
                        if '_raw' not in cols or '_seq' not in cols:
                            return None
                        crus = []
                        for (cru,) in con.execute(
                                'SELECT "_raw" FROM %s ORDER BY CAST("_seq" AS BIGINT)'
                                % alvo_sql).fetchall():
                            if not cru:
                                return None
                            json.loads(cru)                 # valida agora; reparse no consumo
                            crus.append(cru)
                        return crus                          # os _raw, em TEXTO
                finally:
                    gate.exit_read()
                    _freio_mede(time.monotonic() - t0, db)
            except Exception:                               # noqa: BLE001
                return None

        dados = _ler()
        if dados is None:
            # CURA SÍNCRONA — ver table_rows; espelho desligado/timeout →
            # aviso assíncrono e o chamador cai no JSON.
            if _cura_em_quarentena(jpath):
                return None                       # já se sabe que não resolve
            if duck_mirror.convert_sync(jpath):
                dados = _ler()
            if dados is None:
                _cura_marca_falha(jpath)
                duck_mirror.notify_write(jpath)
        elif dados is not _OBJETO:
            _cura_marca_ok(jpath)
        if dados is _OBJETO:
            if memo is not None:
                memo[chave] = None           # payload-objeto: não reabrir o banco neste request
            return None
        if dados is None:
            return None
        if memo is not None:
            memo[chave] = dados
        return [json.loads(c) for c in dados]
    except Exception:                                       # noqa: BLE001
        return None


def day_records(path):
    """Leitura DB-ONLY de um arquivo-dia payload-LISTA, por caminho: o banco
    responde (curando-se na hora quando frio/defasado — `day_payload`); o JSON
    é a EMERGÊNCIA (espelho desligado nos testes, payload-objeto, conversão
    que falhou). Levanta as exceções de `open`/`json.load` quando nem o JSON
    dá — o transplante de um `with open(...)` existente preserva o `except`
    do chamador."""
    dados = day_payload(path)
    if dados is not None:
        return dados
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def dataset_rows(path):
    """Leitura DB-ONLY de um JSON de DATASET (mappings, cadastros B3,
    Subjacente…), por caminho — o gêmeo do `day_records` para o que não é
    arquivo-dia. Banco frio cura na hora (via table_rows); a emergência é o
    JSON, com as exceções do chamador preservadas."""
    dados = dataset_records(path)
    if dados is not None:
        return dados
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def dataset_records(path):
    """Os registros originais de um JSON coberto pelos DATASETS (mappings,
    cadastros B3, …), pelo caminho ABSOLUTO de quem lê — que também é o
    guarda: fora da raiz espelhada, ou arquivo de outro conversor, → `None`
    e vale o JSON. Payload que não é lista de registros (os dicts viram
    `_meta`/sub-tabelas) também devolve `None` — a reconstrução fiel é só da
    lista."""
    try:
        from apps.pages import json_to_duckdb as core
        raiz = _data_root()
        rel = os.path.relpath(os.path.normpath(str(path)), raiz)
        if rel.startswith('..'):
            return None
        rel = rel.replace(os.sep, '/')
        alvo = core._dataset_rel_target(rel, core._holiday_files(raiz))
        if alvo is None:
            return None
        db, tabela = alvo
        return raw_records(db, tabela, rel,
                           manifest_key=core._dataset_manifest_key(rel))
    except Exception:                                       # noqa: BLE001
        return None


def refdata_rows(expected_path=None):
    """Os registros originais do RefData — do `reference_data.db` quando fresco."""
    return raw_records('reference_data.db', 'refdata', 'RefData.json',
                       expected_path=expected_path)


def cpd_records(expected_path=None):
    """Os registros originais do CounterpartyDetails — fidelidade total,
    chave-ausente incluída."""
    return raw_records('reference_data.db', 'counterparty_details',
                       'CounterpartyDetails.json', expected_path=expected_path)
