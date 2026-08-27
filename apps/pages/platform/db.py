# -*- coding: utf-8 -*-
"""O acesso ao banco de USUÁRIOS: o adaptador de compatibilidade e a abertura
com a disciplina de locks do CLAUDE.md §4.

Movido VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). As PRIMITIVAS
(`duckdb_read`/`duckdb_write`, lock de arquivo, retry) continuam no
`database_access.py` — que sempre foi um módulo próprio, a mesma camada que
esta. O que ainda é do `routes` — o caminho (`DB_PATH`), a inicialização
preguiçosa do schema (`_ensure_db_initialized`, que arrasta `init_db` e as
migrações de autenticação) e as próprias primitivas COMO ATRIBUTO — é
alcançado por busca atrasada: é a superfície que os testes trocam
(`R.DB_PATH = tmp`, `R.duckdb_write = contador`).

O banco de NOTIFICAÇÕES tem o próprio módulo (`platform/notifications.py`).
"""


class _DuckDBHandle:
    """Adaptador de compatibilidade para os chamadores antigos, que usam `close()`.

    O banco de usuários passou a ser aberto pelo `duckdb_write` do
    `database_access` — um contexto (`with`) cujo lock é de ARQUIVO, e por isso
    vale também ENTRE PROCESSOS. Os ~21 chamadores das rotas seguem o contrato
    antigo (`conn = get_db_connection()` … `finally: conn.close()`), e reescrever
    os 21 no mesmo commit seria trocar a disciplina de fechamento de todos de uma
    vez; este adaptador é o que permite migrá-los aos poucos.

    O `close()` é o `__exit__` do contexto: é ele que comita, fecha a conexão e
    solta o lock. A regra do `finally` continua valendo palavra por palavra
    (CLAUDE.md §4) — sem ela o lock não é liberado e o app trava para todos.
    """
    __slots__ = ('_context', '_conn', '_closed')

    def __init__(self, context):
        self._context = context
        self._conn = context.__enter__()
        self._closed = False

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        if not self._closed:
            self._closed = True
            self._context.__exit__(None, None, None)

    def commit(self):
        """O contexto de escrita comita quando o dono do handle o fecha."""


def get_db_connection(readonly=False):
    """Abre o banco de Usuários pelo contexto de transação comum.

    Era uma conexão SINGLETON atrás de um `threading.Lock` de módulo, com retry,
    backoff e reconexão quando ela adoecia. O lock de thread protegia UM
    processo: um script de manutenção rodando ao lado do servidor abria o mesmo
    arquivo sem pedir licença a ninguém. O `duckdb_write` põe o lock no ARQUIVO,
    então a exclusão vale entre processos — e o retry, o backoff e a checagem de
    saúde passam a ser dele, num lugar só, para todos os bancos.

    **`readonly=True` para quem só faz SELECT**, e não é otimização de detalhe.
    O caminho de escrita é EXCLUSIVO nos dois níveis: um `BoundedSemaphore(1)`
    dentro do processo e um lock de arquivo exclusivo entre eles. Abrir uma
    consulta por ali põe toda leitura na mesma fila de UM: com o banco no share,
    onde cada operação custa ida e volta de rede, a topbar consultando o sino
    por aba aberta consome sozinha a fila inteira, e a página que o usuário
    pediu espera atrás dela. Era o que fazia a tela levar minutos para aparecer
    com o banco em `\\Nawest…` — sem erro nenhum no log, porque ninguém falhou:
    todo mundo esperou.

    A leitura toma lock COMPARTILHADO e um semáforo de `DATABASE_READ_CONCURRENCY`
    permissões, então leitores não se bloqueiam entre si nem bloqueiam outra
    instância — e continuam excluídos do escritor, que é a garantia que importa.
    """
    from apps.pages import routes
    routes._ensure_db_initialized()     # lazy, one-time schema/migrations (no-op after first run)
    if readonly:
        return _DuckDBHandle(routes.duckdb_read(routes.DB_PATH))
    return _DuckDBHandle(routes.duckdb_write(routes.DB_PATH))
