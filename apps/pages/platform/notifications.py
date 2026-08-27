# -*- coding: utf-8 -*-
"""As notificações do sino e do Web Push — a maior horizontal do app.

Movida VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10): era o nome que
as features mais alcançavam por busca atrasada (`_create_notification`, 118
pontos de chamada). O `routes.py` mantém os nomes como ALIAS, então features e
testes que trocam a FUNÇÃO lá (`R._create_notification = espião`) seguem
valendo sem mudar.

O que fica AQUI é o estado e o miolo: o mapa de destino do clique
(`_NOTIF_PAGE_URL`), a conexão com o banco de notificações, o schema, a
migração da subida e o disparo (`_create_notification` → `_push_notify`).
Quem troca o ESTADO (`_notif_db_done`, `_notif_db_retry_at`,
`_notif_schema_pronto`) troca NESTE módulo — é onde ele mora.

O que ainda é do `routes` — os caminhos (`DB_PATH`, `NOTIF_DB_PATH`,
`_B3_DATA_DIR`) e as primitivas de banco (`_DuckDBHandle`, `duckdb_read`,
`duckdb_write`, `duckdb_read_unlocked`) — é alcançado por busca ATRASADA
(`from apps.pages import routes` dentro da função), andaime declarado até a
camada de banco ter a própria fatia. É o que mantém válidos os testes que os
trocam no `routes` (`R.NOTIF_DB_PATH = tmp`, `R.duckdb_write = contador`).

Os ENDPOINTS (`/api/notifications` GET/POST) continuam no `routes.py`: rota é
casca, e a casca do sino ainda mora lá.
"""
import logging
import os
import threading
import time
import traceback

log = logging.getLogger('otc_tracker')

# Rótulo do Daily Settlement › NDF › Other Publisher. Ele NÃO pode ser o mesmo
# do New Deals ('NDF Other Publisher', que vem do `_GENERIC_ND_PRODUCTS`): o
# rótulo é a chave que decide DUAS coisas — para onde o sino leva ao clicar e
# QUEM enxerga a notificação (o filtro por acesso de página). Compartilhado, a
# notificação da tela de liquidação abria a de New Deals e sumia para quem só
# tem a de liquidação liberada.
_NOTIF_DS_OTHERPUB = 'NDF Other Publisher (Settlement)'

# Notification "page" label → the sidebar URL it belongs to (for feed filtering).
# ⚠️ Este mapa tem MAIS DUAS cópias, no navegador: `PAGE_URL` em
# partials/topbar.html (clique no sino) e em static/js/sw-push.js (clique no push
# do sistema). Os três têm de concordar, senão o mesmo aviso leva a lugares
# diferentes conforme onde foi clicado — `check_notif_page_url.py` prova isso.
_NOTIF_PAGE_URL = {
    'NDF Comm': '/new_deals-ndf-commodities', 'Opt Comm': '/new_deals-opt-commodities',
    'Opt FXO': '/new_deals-opt-fxo', 'NDF FWD Start': '/new_deals-ndf-fwdstart',
    'NDF Other Publisher': '/new_deals-ndf-otherpublisher', 'NDF Vanilla': '/new_deals-ndf-vanilla',
    _NOTIF_DS_OTHERPUB: '/ndf-other-publisher',
    'Index B3': '/index-b3',
    'Users': '/users-roles', 'Recon Comitente': '/reconciliation-comitente',
    'Recon FXO': '/reconciliation-fxo',
    'Reference Data': '/reference-data', 'Control Panel': '/control-panel',
    'Accrual': '/accrual-swap', 'MtM': '/mtm-swap', 'Intrag Option': '/intrag-option',
    'Intrag NDF': '/intrag-ndf', 'Intrag Swap': '/intrag-swap',
    'Reconciliation': '/reconciliation-payrec',
    'Pending Confirmation': '/pending-confirmation',
    # A esteira de confirmação manual. O rótulo é 'Confirmation' (e não
    # 'Manual Confirmation') porque é o que as notificações já gravadas
    # carregam: renomear deixaria o histórico do sino sem destino.
    'Confirmation': '/manual-confirmation/monitor',
    'Support': '/tickets-list',
    # Nove páginas gravavam notificação SEM entrada aqui — o aviso aparecia no
    # sino e o clique não ia a lugar nenhum (o TED Release do Other Products
    # Summary foi como isso apareceu). Todo rótulo `page` passado a
    # `_create_notification` TEM de existir neste mapa (e nas duas cópias do
    # navegador) — `check_notif_page_url.py` agora prende isso.
    'Other Products Summary': '/other-products-summary',
    'NDF Summary':            '/ndf-summary',
    'Operations B3':          '/operations-b3',
    'OTM Settlements':        '/otm-settlements',
    'Latam Desk Position':    '/other-products-swap-latamdeskposition',
    'NDF Cockpit':            '/ndf-cockpit',
    'Cognos':                 '/cognos',
    # A tela chama-se **File Interpreter** desde a renomeação; o rótulo aqui
    # continua 'File Interface' porque é o que as notificações JÁ GRAVADAS
    # carregam, e é por ele que o clique acha o destino — mesma razão do
    # 'Confirmation' lá em cima. Um segundo rótulo apontando para a mesma URL
    # também não serve: `check_notif_page_url.py` recusa destino repetido, e com
    # razão, porque aí o mesmo aviso teria duas chaves.
    'File Interface':         '/file-interpreter',
    'File Interpreter':       '/file-interpreter',
    'Mapping':                '/mapping',
    'Holidays Calendar':      '/holidays-calendar',
}


def _notif_page_url(page, action=''):
    """Destino do clique de uma notificação.

    O par (ação, página) da Recon FXO nasceu trocado — a ação era 'Recon FXO' e a
    página 'Reconciliation', que é a do Pay/Rec —, então o sino levava para a
    recon errada. O cadastro foi corrigido na origem, mas as notificações **já
    gravadas** carregam o par antigo: sem esta tradução, o histórico do sino
    continuaria abrindo o Pay/Rec para sempre. Mesma razão do rótulo
    'Confirmation' logo acima — o que está no banco não se reescreve.

    A cópia desta regra vive no `partials/topbar.html` (é lá que o clique
    acontece); as duas têm de dizer a mesma coisa.
    """
    if page == 'Reconciliation' and action == 'Recon FXO':
        return _NOTIF_PAGE_URL['Recon FXO']
    return _NOTIF_PAGE_URL.get(page)


def get_notif_connection(readonly=False, unlocked=False):
    """Abre o banco de NOTIFICAÇÕES. Mesmo contrato do `get_db_connection`:
    `conn = ...` seguido de `try: … finally: conn.close()`.

    `readonly=True` para quem só faz SELECT — lock COMPARTILHADO, que não entra
    na fila de escrita (CLAUDE.md §4).

    **`unlocked=True` é o poll do sino, e SÓ ele.** Ele dispensa até o lock
    compartilhado, então a leitura não espera nem por uma gravação de
    notificação em curso. O preço é real: sem coordenação entre processos, a
    leitura pode pegar o arquivo no meio de um commit e falhar — ou, no share,
    ver um estado parcial. É aceitável ali porque o sino é uma consulta de
    MELHOR ESFORÇO: ele repete a cada poucos segundos, o endpoint já trata a
    consulta que falha devolvendo o sino vazio (e não um 500 a cada aba), e um
    aviso que aparece um poll depois não muda decisão nenhuma.

    NÃO use em nada que decida: a allowlist do `Page_Access`, o login, o papel
    que filtra os tickets. Ali um dado parcial vira uma AUTORIZAÇÃO errada, e o
    `check_unlocked_reads.py` recusa a chamada fora do lugar permitido.
    """
    # **O ensure é do caminho de ESCRITA, e isto não é economia.** Ele abre o
    # banco em modo READ-WRITE e, na primeira vez, migra o banco antigo: no
    # share isso segurou o lock exclusivo por 9,4 SEGUNDOS. Chamado aqui em
    # cima, quem pagava essa conta era o poll do sino — a consulta mais
    # repetida do app, declarada MELHOR ESFORÇO, e a única que abre sem lock
    # nenhum. Uma leitura best-effort virava a escrita mais cara do sistema.
    #
    # E o DuckDB não deixa isso passar em silêncio: um handle read-only aberto
    # (outra aba, outra thread, a outra instância que enxerga o mesmo share)
    # BLOQUEIA a abertura read-write, e o open estoura com *"the process cannot
    # access the file because it is being used by another process"*. Como o
    # `_notif_db_done` só é marcado no fim, a falha deixava o flag em False e
    # TODO poll seguinte tentava de novo: um 500 por aba a cada 8 segundos,
    # cada um custando uma tentativa de lock exclusivo no share.
    #
    # Quem cria o schema é a subida (`_capture_flask_app`) e, depois dela, só
    # quem vai GRAVAR. O leitor não cria banco — no pior caso ele lê um banco
    # que ainda não existe, e o sino fica vazio, que é o desfecho que este
    # endpoint já tratava.
    from apps.pages import routes
    if not (readonly or unlocked):
        _ensure_notif_db()
    if unlocked:
        if not readonly:
            # A gravação sem lock corrompe o arquivo em vez de só ler torto.
            raise ValueError('unlocked só vale para leitura')
        return routes._DuckDBHandle(routes.duckdb_read_unlocked(routes.NOTIF_DB_PATH))
    if readonly:
        return routes._DuckDBHandle(routes.duckdb_read(routes.NOTIF_DB_PATH))
    return routes._DuckDBHandle(routes.duckdb_write(routes.NOTIF_DB_PATH))


_notif_db_done = False
_notif_db_lock = threading.Lock()
# O ensure que FALHA não pode ser tentado de novo na chamada seguinte: a falha
# típica é o arquivo em uso por outro processo, ela demora (é um lock no share
# que expira) e ela se repete enquanto a outra ponta não soltar. Sem espera, o
# app tenta a cada gravação de notificação — e as notificações acontecem a cada
# ação de qualquer pessoa.
_notif_db_retry_at = 0.0
_NOTIF_DB_RETRY_SECONDS = 300


def _notif_init_schema(conn, seq_start=1):
    """As duas tabelas do banco de notificações.

    `seq_start` existe porque o DuckDB NÃO deixa mexer numa sequência de que uma
    coluna depende: `ALTER SEQUENCE … RESTART` não é implementado, e o
    `DROP`/`CREATE OR REPLACE` batem em *"Cannot drop entry because there are
    entries that depend on it"*. Como o `id` das notificações migradas vem do
    banco antigo, a sequência tem de NASCER depois do maior deles — depois da
    tabela criada, não há mais como corrigi-la, e o próximo INSERT colidiria com
    uma linha migrada.
    """
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_notif_id START {}".format(
        max(1, int(seq_start or 1))))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER DEFAULT nextval('seq_notif_id') PRIMARY KEY,
            actor_sid   VARCHAR NOT NULL DEFAULT '',
            actor_name  VARCHAR NOT NULL DEFAULT '',
            action      VARCHAR NOT NULL DEFAULT '',
            page        VARCHAR NOT NULL DEFAULT '',
            detail      VARCHAR DEFAULT '',
            target_role VARCHAR DEFAULT '',
            target_sid  VARCHAR DEFAULT '',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            endpoint   VARCHAR PRIMARY KEY,
            sid        VARCHAR NOT NULL DEFAULT '',
            role       VARCHAR DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _notif_migrar_do_antigo(conn):
    """Traz `notifications` e `push_subscriptions` do banco de usuários.

    Roda uma vez, na subida, e é IDEMPOTENTE: o banco da instância já tem as
    duas tabelas cheias, e um script separado ("rode isto depois do pull") é a
    forma mais confiável de a mesa ficar sem o sino — já aconteceu com as
    migrações do Pending Confirmation.

    O que veio NÃO é apagado do banco antigo. Renomear ou dropar deixaria a
    volta atrás sem dado, e o custo de manter as linhas lá é algumas dezenas de
    KB num arquivo que ninguém mais lê. O que impede a duplicação é o `id`:
    a cópia pula o que já está aqui.
    """
    from apps.pages import routes
    inseriu = False
    if not os.path.isfile(routes.DB_PATH):
        return inseriu                                      # instalação nova
    # Pela CAMADA (`duckdb_read`) e não pelo `duckdb.connect` cru: ela toma o
    # lock compartilhado do arquivo, então a migração não atropela quem estiver
    # lendo o banco de usuários nesse instante. E o módulo nem importa o
    # `duckdb` — foi assim que a primeira versão disto falhou com `NameError`,
    # engolido por um `except` mudo, deixando o banco novo vazio em silêncio.
    try:
        with routes.duckdb_read(routes.DB_PATH) as antigo:
            for tabela, chave in (('notifications', 'id'),
                                  ('push_subscriptions', 'endpoint')):
                try:
                    res = antigo.execute('SELECT * FROM {}'.format(tabela))
                    # `description` ANTES do `fetchall`: depois de consumir o
                    # resultado o DuckDB a zera, e `[d[0] for d in None]`
                    # estoura um TypeError que cairia no mesmo `except` de "a
                    # tabela não existe" — a migração pularia a tabela CHEIA
                    # sem dizer nada.
                    cols = [d[0] for d in res.description]
                    linhas_antigas = res.fetchall()
                except Exception:                           # noqa: BLE001
                    log.info('[notif-db] nada a migrar de %s: %s', tabela,
                             traceback.format_exc(limit=0).strip()[:140])
                    continue
                if not linhas_antigas:
                    continue
                existentes = {r[0] for r in conn.execute(
                    'SELECT "{}" FROM {}'.format(chave, tabela)).fetchall()}
                i = cols.index(chave)
                novas = [l for l in linhas_antigas if l[i] not in existentes]
                if not novas:
                    continue
                ph = ', '.join('?' for _ in cols)
                nomes = ', '.join('"{}"'.format(x) for x in cols)
                # NULL vira '' nas colunas que o schema novo declara NOT NULL.
                # UMA linha antiga com nulo abortaria o lote inteiro — e o lote
                # é a migração toda. O default do schema não salva: ele só vale
                # quando a coluna é OMITIDA, e aqui ela vem com o valor nulo.
                nn = {'actor_sid', 'actor_name', 'action', 'page', 'sid', 'endpoint'}
                idx_nn = [k for k, nome in enumerate(cols) if nome in nn]
                if idx_nn:
                    novas = [tuple('' if (k in idx_nn and v is None) else v
                                   for k, v in enumerate(l)) for l in novas]
                conn.executemany('INSERT INTO {} ({}) VALUES ({})'.format(
                    tabela, nomes, ph), novas)
                inseriu = True
                log.info('[notif-db] %d linha(s) de %s migradas do banco de usuários',
                         len(novas), tabela)
    except Exception:                                       # noqa: BLE001
        # A migração falhando NÃO pode impedir o app de subir: sem ela o sino
        # nasce sem histórico; com ela quebrada, ninguém entra. O motivo vai
        # inteiro para o log.
        log.error('[notif-db] a migração do banco antigo falhou:\n%s',
                  traceback.format_exc())
    return inseriu


def _notif_maior_id_antigo():
    """O maior `id` de `notifications` no banco de usuários, ou 0.

    Lido ANTES de criar o schema — é ele que decide onde a sequência começa.
    """
    from apps.pages import routes
    if not os.path.isfile(routes.DB_PATH):
        return 0
    try:
        with routes.duckdb_read(routes.DB_PATH) as antigo:
            return int(antigo.execute(
                'SELECT COALESCE(MAX(id), 0) FROM notifications').fetchone()[0] or 0)
    except Exception:                                       # noqa: BLE001
        return 0


def _notif_avanca_sequencia(conn):
    """Empurra a sequência para além do maior `id` da tabela, se ela ficou atrás.

    O caminho normal já nasce certo (`seq_start`). Isto é o conserto do caso
    torto: uma primeira subida em que o schema foi criado e a migração falhou no
    meio deixaria a sequência em 1 com linhas de id alto na tabela, e o INSERT
    seguinte colidiria — o sino pararia de gravar, e o erro apareceria uma vez
    por ação de qualquer pessoa. Queimar `nextval` é O(n) e feio, mas é a única
    coisa que o DuckDB permite fazer numa sequência com dependente, e o n aqui é
    de algumas centenas.
    """
    try:
        maior = int(conn.execute(
            'SELECT COALESCE(MAX(id), 0) FROM notifications').fetchone()[0] or 0)
        if maior <= 0:
            return
        for _ in range(maior + 2):
            atual = int(conn.execute("SELECT nextval('seq_notif_id')").fetchone()[0])
            if atual > maior:
                return
        log.warning('[notif-db] não consegui avançar a sequência além de %d', maior)
    except Exception:                                       # noqa: BLE001
        log.warning('[notif-db] avanço da sequência falhou:\n%s', traceback.format_exc())


def _notif_schema_pronto():
    """As duas tabelas já existem? A pergunta é de LEITURA, e é ela que evita a
    abertura read-write no caso normal — que é a esmagadora maioria das vezes.

    Sem esta sonda, TODA subida da instância abria o banco de notificações em
    modo de escrita só para descobrir que não havia nada a fazer. Isso é um lock
    exclusivo no share, e é o que colide com a instância vizinha que já está de
    pé: o DuckDB recusa a abertura read-write enquanto qualquer handle read-only
    estiver aberto, e o erro que ele dá — *"used by another process"* — não diz
    nada sobre schema nenhum.

    O lock aqui é o COMPARTILHADO (`duckdb_read`, não o `unlocked`): a sonda roda
    uma vez por processo, não por request, então esperar por uma gravação em
    curso não custa nada — e é a resposta certa, porque uma leitura suja aqui
    decidiria criar schema por cima de um banco que já o tem.

    Qualquer falha responde **False** de propósito, inclusive o arquivo que não
    existe: "não consegui ver" e "não está lá" levam ao mesmo lugar, que é o
    caminho de criação — e ele é idempotente (`CREATE TABLE IF NOT EXISTS`).
    """
    from apps.pages import routes
    try:
        with routes.duckdb_read(routes.NOTIF_DB_PATH) as con:
            achadas = {r[0] for r in con.execute(
                "SELECT table_name FROM information_schema.tables").fetchall()}
    except Exception:                                       # noqa: BLE001
        return False
    return {'notifications', 'push_subscriptions'} <= achadas


def _ensure_notif_db():
    """Cria o schema e migra do banco antigo — uma vez por processo.

    Ele é chamado na SUBIDA (`_capture_flask_app`) e, depois dela, só por quem
    vai gravar. Nunca pelo poll do sino — ver o comentário em
    `get_notif_connection`.
    """
    from apps.pages import routes
    global _notif_db_done, _notif_db_retry_at
    if _notif_db_done:
        return
    with _notif_db_lock:
        if _notif_db_done:
            return
        if time.monotonic() < _notif_db_retry_at:
            return
        # A sonda primeiro: com o schema no lugar não se abre nada para escrita.
        if _notif_schema_pronto():
            _notif_db_done = True
            return
        # O `try` começa ANTES do primeiro `duckdb_write`, e é onde estava o
        # buraco: quem falhava era a ABERTURA (o arquivo em uso por outro
        # processo), fora de qualquer `except`. O flag ficava em False, nada
        # marcava a espera, e a tentativa seguinte vinha na próxima chamada.
        try:
            # DUAS transações, e a ordem importa. O schema vai sozinho e comita
            # primeiro; a migração vem depois, noutra. Juntos, um erro no meio da
            # cópia — uma linha com nulo numa coluna NOT NULL foi o que apareceu no
            # teste — desfazia TAMBÉM o `CREATE TABLE`, e o app subia com o banco de
            # notificações sem tabela nenhuma: o sino passava a estourar a cada
            # consulta, em cada aba. Separados, o pior caso é o sino sem histórico.
            conn = routes._DuckDBHandle(routes.duckdb_write(routes.NOTIF_DB_PATH))
            try:
                # O início da sequência sai do banco ANTIGO e é decidido antes do
                # schema: depois da tabela criada não há como corrigi-la.
                _notif_init_schema(conn, _notif_maior_id_antigo() + 1)
                conn.commit()
            except Exception:
                log.error('[notif-db] não consegui criar o schema:\n%s',
                          traceback.format_exc())
                conn.close()
                raise
            else:
                conn.close()

            conn = routes._DuckDBHandle(routes.duckdb_write(routes.NOTIF_DB_PATH))
            try:
                # O avanço só depois de uma migração que INSERIU: rodado sempre, ele
                # queimaria um id a cada subida da instância — inofensivo, mas é
                # efeito colateral por nada num caminho que roda todo dia.
                if _notif_migrar_do_antigo(conn):
                    _notif_avanca_sequencia(conn)
                conn.commit()
            finally:
                conn.close()
            _notif_db_done = True
            log.info('[notif-db] pronto em %s', os.path.abspath(routes.NOTIF_DB_PATH))
        except Exception:                                       # noqa: BLE001
            # Não relançar seria pior: quem grava notificação ficaria gravando
            # numa tabela que talvez não exista. Quem chama já engole (o
            # `_create_notification` inteiro é try/except) e a subida trata à
            # parte — o que muda aqui é só a ESPERA antes da próxima tentativa.
            _notif_db_retry_at = time.monotonic() + _NOTIF_DB_RETRY_SECONDS
            raise


def _notif_roles(target_role):
    """`target_role` normalizado: aceita '' , 'ADMIN' ou vários papéis.

    Uma etapa da esteira precisa avisar DUAS mesas (Pending MO é do MO e do BO),
    e a coluna sempre guardou um papel só. Vários papéis viram uma lista separada
    por vírgula na MESMA coluna — 'MO,BO' —, e quem lê parte a string. O valor
    antigo continua válido de graça: 'ADMIN' parte numa lista de um elemento.

    Criar uma tabela de destinatários para isto seria um join novo em cada
    consulta do sino, que a topbar faz a cada 8 s por aba aberta.
    """
    if not target_role:
        return ''
    if isinstance(target_role, str):
        partes = target_role.split(',')
    else:
        partes = list(target_role)
    vistos, out = set(), []
    for p in partes:
        p = str(p or '').strip().upper()
        if p and p not in vistos:
            vistos.add(p)
            out.append(p)
    return ','.join(out)


def _create_notification(actor_sid, actor_name, action, page, detail='', target_role='',
                         target_sid=''):
    """Publica uma notificação no sino. `target_role` restringe aos papéis
    listados (um só, ou vários separados por vírgula — ver `_notif_roles`),
    `target_sid` a UM usuário (os dois vazios = todo mundo). Ver o filtro em
    `api_get_notifications`."""
    target_role = _notif_roles(target_role)
    try:
        conn = get_notif_connection()
        try:
            conn.execute(
                "INSERT INTO notifications (actor_sid, actor_name, action, page, detail, target_role, target_sid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [actor_sid or '', actor_name or '', action, page, detail or '',
                 target_role or '', (target_sid or '').strip().upper()]
            )
            conn.commit()
        finally:
            conn.close()
        # Wake subscribers' devices via Web Push (best-effort, off the request path).
        try:
            threading.Thread(target=_push_notify,
                             args=(actor_sid or '', target_role or ''),
                             kwargs={'target_sid': (target_sid or '').strip().upper()},
                             daemon=True).start()
        except Exception:
            pass
    except Exception:
        log.error("[_create_notification] FAILED:\n%s", traceback.format_exc())


def _push_notify(actor_sid, target_role, target_sid=''):
    """Send a payloadless Web Push to every subscriber matching the
    notification's target_role (empty = everyone), except the actor. The
    Service Worker then fetches /api/notifications and shows it. Runs in a
    background thread; HTTP sends happen with no DB lock held.

    `target_sid` mirrors the feed filter: when set, only that user's devices
    are woken. Sem isso o celular do time inteiro apitaria por uma notificação
    que só o requester consegue abrir."""
    try:
        from apps.pages import webpush
        if not webpush.is_enabled():
            return
        conn = get_notif_connection()
        try:
            if target_sid:
                # O actor é excluído nos outros ramos porque não precisa ser
                # avisado do que ele mesmo fez; aqui não: o destinatário é
                # explícito e pode até ser o próprio actor.
                rows = conn.execute(
                    "SELECT endpoint FROM push_subscriptions WHERE sid = ?",
                    [target_sid]).fetchall()
            elif target_role:
                # Vários papéis na mesma notificação (Pending MO avisa MO e BO).
                # Os `?` são montados pela CONTAGEM e os papéis vão bindados —
                # o único jeito de escrever um IN, e o que o cheat sheet permite.
                papeis = [p for p in _notif_roles(target_role).split(',') if p]
                rows = conn.execute(
                    "SELECT endpoint FROM push_subscriptions WHERE role IN ({}) AND sid <> ?"
                    .format(','.join('?' * len(papeis))),
                    papeis + [actor_sid]).fetchall() if papeis else []
            else:
                rows = conn.execute(
                    "SELECT endpoint FROM push_subscriptions WHERE sid <> ?",
                    [actor_sid]).fetchall()
        finally:
            conn.close()
        dead = []
        for (endpoint,) in rows:
            code = webpush.send_push(endpoint)
            if code in (404, 410):   # subscription expired/unsubscribed
                dead.append(endpoint)
        if dead:
            conn = get_notif_connection()
            try:
                for ep in dead:
                    conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", [ep])
                conn.commit()
            finally:
                conn.close()
    except Exception:
        log.error("[_push_notify] FAILED:\n%s", traceback.format_exc())
