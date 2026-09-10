"""Shared database lock and transaction contexts for standalone database files."""

from __future__ import annotations

import logging
import os
import hashlib
import re
import socket
import sqlite3
import threading
import traceback
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping, Optional, Union

import duckdb
import portalocker


_LOG = logging.getLogger(__name__)
_PathLike = Union[str, os.PathLike[str]]


class DatabaseAccessError(RuntimeError):
    """Base error for the shared database access layer."""


class DatabaseLockTimeout(DatabaseAccessError):
    """A local permit or cross-machine file lock was not acquired in time."""

    def __init__(self, database_path: str, mode: str, timeout_seconds: float):
        self.database_path = database_path
        self.mode = mode
        self.timeout_seconds = timeout_seconds
        super().__init__(
            "Timed out acquiring {} access to {} after {} seconds".format(
                mode, database_path, timeout_seconds
            )
        )


class NestedDatabaseTransaction(DatabaseAccessError):
    """A write context attempted to re-enter the same database on one thread."""


class TransactionOutcomeUnknown(DatabaseAccessError):
    """Commit failed, so persistence must be verified by a business key."""

    def __init__(self, database_path: str, operation_id: str):
        self.database_path = database_path
        self.operation_id = operation_id
        super().__init__(
            "Commit outcome is unknown for operation {} on {}".format(
                operation_id, database_path
            )
        )


class DatabaseCleanupError(DatabaseAccessError):
    """The database outcome is known but connection or lock cleanup failed."""


@dataclass(frozen=True)
class DatabaseAccessSettings:
    local_semaphore_timeout_seconds: float = 30.0
    read_lock_timeout_seconds: float = 15.0
    write_lock_timeout_seconds: float = 30.0
    sqlite_busy_timeout_seconds: int = 10_000
    slow_lock_warning_seconds: float = 5.0
    retry_limit: int = 2
    read_concurrency: int = 8

    @classmethod
    def from_mapping(cls, settings: Mapping[str, object]) -> "DatabaseAccessSettings":
        return cls(
            local_semaphore_timeout_seconds=float(
                settings.get("DATABASE_LOCAL_SEMAPHORE_TIMEOUT_SECONDS", 30)
            ),
            read_lock_timeout_seconds=float(settings.get("DATABASE_READ_LOCK_TIMEOUT_SECONDS", 15)),
            write_lock_timeout_seconds=float(settings.get("DATABASE_WRITE_LOCK_TIMEOUT_SECONDS", 30)),
            sqlite_busy_timeout_seconds=int(settings.get("DATABASE_SQLITE_BUSY_TIMEOUT_SECONDS", 10_000)),
            slow_lock_warning_seconds=float(settings.get("DATABASE_SLOW_LOCK_WARNING_SECONDS", 5)),
            retry_limit=int(settings.get("DATABASE_LOCK_RETRY_LIMIT", 2)),
            read_concurrency=int(settings.get("DATABASE_READ_CONCURRENCY", 8)),
        )


@dataclass(frozen=True)
class DatabaseOperation:
    operation_id: str
    database_path: str
    lock_path: str
    mode: str
    started_at: float
    engine: str = ""


@dataclass
class _DatabaseSemaphores:
    read: threading.BoundedSemaphore
    write: threading.BoundedSemaphore


class _SemaphoreRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, _DatabaseSemaphores] = {}

    def get(self, database_path: str, read_concurrency: int) -> _DatabaseSemaphores:
        with self._lock:
            entry = self._entries.get(database_path)
            if entry is None:
                entry = _DatabaseSemaphores(
                    read=threading.BoundedSemaphore(read_concurrency),
                    write=threading.BoundedSemaphore(1),
                )
                self._entries[database_path] = entry
            return entry


class _UnlockedReadGate:
    """Coordena, DENTRO do processo, as leituras sem lock com as escritas.

    O DuckDB guarda UMA instância por arquivo dentro do processo, e recusa a
    segunda conexão que chegue com outra configuração: um poll do sino aberto
    `read_only` no instante em que o `duckdb_write` conecta derruba a ESCRITA
    com *"Can't open a connection to same database file with a different
    configuration than existing connections"* — a notificação se perde, e o
    poll seguinte nem fica sabendo. O conflito é exclusivamente
    intra-processo (entre processos o sintoma é outro: lock de arquivo), então
    a coordenação pode ser toda em memória — nenhuma ida ao share.

    As leituras COM lock não precisam disto: o lock de arquivo compartilhado ×
    exclusivo já as exclui do escritor, inclusive entre handles do mesmo
    processo. Só a leitura `unlocked` convive no tempo com uma escrita — e é
    ela que se registra aqui.

    O portão é de MELHOR ESFORÇO nos dois lados, de propósito:

    - o leitor espera um pouco (`_GATE_READ_WAIT_SECONDS`) por um escritor em
      curso — na maioria das vezes a escrita fecha em milissegundos e a leitura
      que hoje falharia passa a responder com dado — e, esgotada a espera,
      SEGUE para o connect e falha como sempre falhou (o poll já devolve o sino
      vazio). Esperar sem teto seria devolver ao sino a fila que o `unlocked`
      existe para evitar;
    - o escritor declara a intenção (leitor novo recua), espera os leitores em
      voo fecharem (`_GATE_WRITE_WAIT_SECONDS` — eles são SELECTs curtos) e,
      esgotada a espera, segue e deixa o connect decidir. O teto é o que impede
      um leitor doente de calar as notificações do app inteiro.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._readers = 0
        self._writers = 0

    def enter_read(self, timeout_seconds: float) -> None:
        """Registra uma leitura sem lock, esperando (com teto) escritor em curso."""
        deadline = time.monotonic() + timeout_seconds
        with self._cond:
            while self._writers:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
            self._readers += 1

    def exit_read(self) -> None:
        with self._cond:
            self._readers -= 1
            if self._readers <= 0:
                self._cond.notify_all()

    def declare_write(self) -> None:
        """Declara a escrita: leitor NOVO passa a esperar em `enter_read`."""
        with self._cond:
            self._writers += 1

    def await_readers(self, timeout_seconds: float) -> bool:
        """Espera (com teto) os leitores em voo fecharem. False quando o teto
        venceu com leitores ainda abertos — a escrita segue assim mesmo, e o
        `duckdb.connect` dirá se deu."""
        deadline = time.monotonic() + timeout_seconds
        with self._cond:
            while self._readers:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return True

    def enter_write(self, timeout_seconds: float) -> bool:
        """`declare_write` + `await_readers`."""
        self.declare_write()
        return self.await_readers(timeout_seconds)

    def exit_write(self) -> None:
        with self._cond:
            self._writers -= 1
            self._cond.notify_all()


class _UnlockedGateRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, _UnlockedReadGate] = {}

    def get(self, database_path: str) -> _UnlockedReadGate:
        with self._lock:
            entry = self._entries.get(database_path)
            if entry is None:
                entry = _UnlockedReadGate()
                self._entries[database_path] = entry
            return entry


_GATE_READ_WAIT_SECONDS = 1.0
_GATE_WRITE_WAIT_SECONDS = 10.0
_LOCK_CHECK_INTERVAL_SECONDS = 0.05

# As assinaturas de "o arquivo tem outro dono", nos dois sistemas. O Windows
# responde com a frase do próprio SO; o Linux e o macOS, com a do lock do
# DuckDB. `already open` e `different configuration` cobrem o conflito DENTRO
# do processo, que é o mesmo problema por outro caminho (o DuckDB guarda uma
# instância por arquivo e recusa a segunda com outra configuração). A lista
# nasceu no sino (`_notif_arquivo_em_uso`) e mora AQUI porque o leitor do
# espelho (`duck_read`) precisa da mesma resposta: banco OCUPADO não é banco
# defasado, e tratá-lo como defasado custava uma reconversão inteira. UMA
# lista — o sino delega para cá.
FILE_IN_USE_SIGNATURES = (
    'used by another process',
    'being used by another',
    'could not set lock',
    'conflicting lock',
    'already open',
    'different configuration',
)


def is_file_in_use(exc: BaseException) -> bool:
    """A falha foi DISPUTA pelo arquivo (outro processo, outra configuração no
    mesmo processo, ou o teto de trava desta camada), e não outra coisa?"""
    if isinstance(exc, DatabaseLockTimeout):
        return True
    texto = str(exc).lower()
    return any(marca in texto for marca in FILE_IN_USE_SIGNATURES)


@contextmanager
def read_timeout(seconds: Optional[float]) -> Iterator[None]:
    """Teto MENOR de espera (permit + trava de arquivo) para as LEITURAS
    abertas dentro do bloco, nesta thread.

    Existe para o leitor do espelho: os tetos do ajuste (30 s de permit, 15 s
    de trava) foram pensados para o banco de usuários, onde não há para onde
    cair. O `duck_read` TEM para onde cair — o JSON é o canal de emergência —,
    e uma thread do waitress parada 45 s esperando um banco que a instância
    vizinha está convertendo é pior do que servir o JSON desta vez. Vale só
    para leitura: a escrita continua com o teto cheio, porque para ela não há
    emergência. `None` não muda nada."""
    anterior = getattr(_thread_state, "read_timeout", None)
    # Blocos ANINHADOS ficam com o MENOR teto: o armazém abre cada leitura com
    # o teto dele, e quem o envolveu com um teto mais curto (um teste, um
    # chamador com orçamento) não pode ver o seu ser alongado por dentro.
    if seconds is not None and anterior is not None:
        seconds = min(seconds, anterior)
    _thread_state.read_timeout = seconds
    try:
        yield
    finally:
        _thread_state.read_timeout = anterior


def _read_timeout_override() -> Optional[float]:
    return getattr(_thread_state, "read_timeout", None)

_semaphores = _SemaphoreRegistry()
_unlocked_gates = _UnlockedGateRegistry()


def db_gate(database_path: _PathLike) -> _UnlockedReadGate:
    """O portão intra-processo leitor × escritor de UM banco, pelo caminho.

    Nasceu para o poll sem lock do sino (§323) e passou a servir também os
    bancos do ARMAZÉM (§422/§434): o leitor do `data_store` abre `read_only`
    e o funil abre o mesmo arquivo em escrita, no mesmo processo, e o DuckDB
    recusa a segunda configuração. O lock de arquivo (compartilhado × exclusivo)
    não separa os dois dentro de um processo, então o que resta é a
    coordenação em memória, que é exatamente o que este portão faz."""
    return _unlocked_gates.get(normalize_database_path(database_path))
# Os bancos já avisados de que estão sendo lidos sem lock — ver `skip_file_lock`.
_unlocked_warned: set = set()
_thread_state = threading.local()
_settings = DatabaseAccessSettings()

# A telemetria estruturada desta camada é INFO e sai UMA LINHA POR OPERAÇÃO — por
# leitura e por escrita, em todo banco de arquivo do app. Com os bancos no share
# e o sino consultando de tempos em tempos por aba aberta, isso vira a maior
# parte do log e enterra o que se procura nele.
#
# Desligada por padrão. `OTC_DB_LOG=1` religa na instância sem tocar no arquivo —
# é o que se faz quando o assunto É o lock.
_DATABASE_LOGGING_ENABLED = os.getenv('OTC_DB_LOG', '').strip().lower() in (
    '1', 'true', 'yes', 'on')


def _database_id(database_path: str) -> str:
    """Return a stable identifier without exposing a potentially sensitive path."""
    return hashlib.sha256(database_path.encode("utf-8")).hexdigest()[:16]


def _sanitize_error(error: BaseException, operation: DatabaseOperation) -> str:
    message = str(error).replace(operation.database_path, "<database>")
    message = message.replace(operation.lock_path, "<lock>")
    message = re.sub(r"(?i)(?:[a-z]:\\|\\\\)[^\s'\"<>]+", "<path>", message)
    message = re.sub(r"\b[a-z][a-z0-9+.-]*://[^\s'\"<>]+", "<url>", message)
    return message[:500]


# ── O rastro POR REQUEST ─────────────────────────────────────────────────────
# O farol emite um evento por OPERAÇÃO, e o `[slow-request]` do routes diz só
# quanto o request inteiro levou. Entre os dois faltava a resposta à pergunta
# que se faz olhando o log da instância — "esse request está parado ONDE?":
# quantos bancos abriu, quais, quanto cada um custou, quantas esperas de lock
# estouraram, quantas leituras caíram para o JSON. Sem isso, um Summary que
# leva minutos aparece como dezenas de `file_lock_held_slow` de bancos
# identificados por hash, sem dizer que request os pediu — e o request que
# NUNCA termina não aparece em lugar nenhum, porque o `[slow-request]` só sai
# no fim.
#
# O rastro é um objeto por THREAD (`trace_begin`/`trace_end`), alimentado por
# esta camada no fim de cada operação e pelo `duck_read` nas quedas para o
# JSON e nas curas; o `routes` o abre no `before_request`, resume-o na linha
# do `[slow-request]` e um laço lê os que ainda estão em voo
# (`traces_in_flight`). Custo por operação: um append sob lock, nada de I/O.
class DbTrace:
    __slots__ = ("label", "started_at", "thread", "thread_id", "ops", "notes", "_lock")

    def __init__(self, label: str) -> None:
        self.label = label
        self.started_at = time.monotonic()
        self.thread = threading.current_thread().name
        self.thread_id = threading.get_ident()
        self.ops: list = []          # (banco, modo, segundos, categoria)
        self.notes: list = []        # (tipo, detalhe)
        self._lock = threading.Lock()

    def record(self, database_path: str, mode: str, seconds: float, category: str) -> None:
        with self._lock:
            self.ops.append((_database_label(database_path), mode, float(seconds), category))

    def note(self, kind: str, detail: object) -> None:
        with self._lock:
            self.notes.append((kind, str(detail)))

    def age(self) -> float:
        return time.monotonic() - self.started_at

    def summary(self, top: int = 4) -> str:
        """Uma frase para o log: aberturas, os bancos mais caros, timeouts, quedas."""
        with self._lock:
            ops = list(self.ops)
            notes = list(self.notes)
        if not ops and not notes:
            return "nenhuma abertura de banco"
        total = sum(seg for _n, _m, seg, _c in ops)
        por_banco: dict = {}
        for nome, modo, seg, _cat in ops:
            chave = "%s %s" % (nome, modo)
            n, s = por_banco.get(chave, (0, 0.0))
            por_banco[chave] = (n + 1, s + seg)
        maiores = sorted(por_banco.items(), key=lambda kv: kv[1][1], reverse=True)[:top]
        cabeca = "%d abertura(s) de banco em %.1fs" % (len(ops), total)
        if maiores:
            cabeca += " (" + " · ".join(
                "%s %s%.1fs" % (chave, ("%dx " % n) if n > 1 else "", s)
                for chave, (n, s) in maiores) + ")"
        partes = [cabeca]
        timeouts = sum(1 for _n, _m, _s, cat in ops if cat == "lock_timeout")
        if timeouts:
            partes.append("%d espera(s) de lock estourada(s)" % timeouts)
        json_ = sum(1 for kind, _d in notes if kind == "json")
        if json_:
            partes.append("%d leitura(s) servida(s) pelo JSON" % json_)
        curas = sum(1 for kind, _d in notes if kind == "cura")
        if curas:
            partes.append("%d cura(s) sincrona(s)" % curas)
        return "; ".join(partes)


_traces_lock = threading.Lock()
_traces: dict = {}


def _database_label(path: object) -> str:
    """Os dois últimos segmentos (`NDF/Vanilla.db`): identifica o banco sem
    expor o caminho do share, como o `_database_id` — só que legível."""
    parts = str(path).replace("\\", "/").rstrip("/").split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else str(path)


def trace_begin(label: str) -> DbTrace:
    """Abre o rastro desta thread e o registra entre os em voo."""
    trace = DbTrace(label)
    _thread_state.trace = trace
    with _traces_lock:
        _traces[id(trace)] = trace
    return trace


def trace_end(trace: Optional[DbTrace]) -> None:
    if trace is None:
        return
    with _traces_lock:
        _traces.pop(id(trace), None)
    if getattr(_thread_state, "trace", None) is trace:
        _thread_state.trace = None


def trace_current() -> Optional[DbTrace]:
    return getattr(_thread_state, "trace", None)


def trace_note(kind: str, detail: object) -> None:
    """Anota um fato fora da camada (queda para o JSON, cura) no rastro em curso."""
    trace = trace_current()
    if trace is not None:
        try:
            trace.note(kind, detail)
        except Exception:                                   # noqa: BLE001
            pass


def trace_stack(trace: DbTrace, limit: int = 8) -> str:
    """A pilha ATUAL da thread do rastro, do quadro mais interno para fora.

    É o que responde "parado ONDE?" quando o rastro não tem operação nenhuma
    — o request preso num lock em memória, numa cura síncrona, numa leitura
    de JSON no share. `sys._current_frames` é uma foto; custa só quando o
    laço de vigilância pede, para um request já lento."""
    try:
        frame = sys._current_frames().get(trace.thread_id)
        if frame is None:
            return ""
        quadros = traceback.extract_stack(frame)
        partes = []
        for fs in reversed(quadros):
            partes.append("%s:%d %s" % (os.path.basename(fs.filename), fs.lineno, fs.name))
            if len(partes) >= limit:
                break
        return " <- ".join(partes)
    except Exception:                                       # noqa: BLE001
        return ""


def traces_in_flight(min_age_seconds: float = 0.0) -> list:
    with _traces_lock:
        vivos = list(_traces.values())
    return [t for t in vivos if t.age() >= min_age_seconds]


def _trace_record(operation: DatabaseOperation, seconds: float, category: str) -> None:
    trace = trace_current()
    if trace is not None:
        try:
            trace.record(operation.database_path, operation.mode, seconds, category)
        except Exception:                                   # noqa: BLE001
            pass


def _log_event(event: str, operation: DatabaseOperation, level: int = logging.INFO, **fields: object) -> None:
    """Emit one structured lifecycle event; observability cannot affect database safety."""
    # O silêncio vale para o ROTINEIRO (INFO), nunca para WARNING e ERROR. Oito
    # eventos desta camada saem nesses dois níveis — `file_lock_wait_timed_out`,
    # `local_permit_wait_timed_out`, `file_lock_held_slow`,
    # `transaction_outcome_unknown`, `file_lock_release_failed` e afins —, e são
    # exatamente o que diz se o banco está em contenção e se um timeout novo
    # começou a fazer request desistir. Calá-los junto com o ruído tiraria a
    # visão no momento em que ela é necessária: o app seguiria falhando igual, só
    # que sem deixar rastro.
    if level < logging.WARNING and not _DATABASE_LOGGING_ENABLED:
        return
    payload = {
        "event": event,
        "operation_id": operation.operation_id,
        "database_id": _database_id(operation.database_path),
        "engine": operation.engine,
        "mode": operation.mode,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "thread": threading.current_thread().name,
        **fields,
    }
    try:
        _LOG.log(level, "database_access %s", " ".join(
            "{}={}".format(key, value) for key, value in payload.items()
        ))
    except Exception:
        pass


def configure_database_access(settings: Mapping[str, object]) -> None:
    """Load the application configuration used by newly opened contexts."""
    global _settings
    _settings = DatabaseAccessSettings.from_mapping(settings)


def normalize_database_path(database_path: _PathLike) -> str:
    """Return the canonical local spelling used for registry and lock identity."""
    return os.path.normcase(os.path.abspath(os.fspath(database_path)))


def lock_file_path(database_path: _PathLike) -> str:
    """Return the one persistent sidecar lock path for a database file."""
    return normalize_database_path(database_path) + ".lock"


def validate_database_paths(database_paths: tuple[_PathLike, ...]) -> None:
    """Ensure database directories and persistent lock files are writable at startup."""
    for database_path in {normalize_database_path(path) for path in database_paths}:
        directory = os.path.dirname(database_path)
        try:
            os.makedirs(directory, exist_ok=True)
            with open(lock_file_path(database_path), "a+b"):
                pass
        except OSError as exc:
            raise DatabaseAccessError(
                "Database path or lock file is inaccessible: {}".format(database_path)
            ) from exc


def _active_write_paths() -> set[str]:
    paths = getattr(_thread_state, "write_paths", None)
    if paths is None:
        paths = set()
        _thread_state.write_paths = paths
    return paths


def _acquire_permit(
    semaphore: threading.BoundedSemaphore,
    operation: DatabaseOperation,
) -> None:
    _log_event("local_permit_wait_started", operation)
    started_at = time.monotonic()
    timeout = _settings.local_semaphore_timeout_seconds
    override = _read_timeout_override() if operation.mode == "read" else None
    if override is not None:
        timeout = min(timeout, override)
    if not semaphore.acquire(timeout=timeout):
        _log_event(
            "local_permit_wait_timed_out", operation, logging.WARNING,
            wait_seconds=round(time.monotonic() - started_at, 3),
        )
        raise DatabaseLockTimeout(operation.database_path, operation.mode, timeout)
    _log_event(
        "local_permit_acquired", operation,
        wait_seconds=round(time.monotonic() - started_at, 3),
    )


# ── a INTENÇÃO de escrita, entre processos ───────────────────────────────────
# O portão em memória dá preferência ao escritor DENTRO do processo; entre
# instâncias sobre o mesmo db/ do share ele não alcança, e a trava exclusiva,
# pedida por tentativa, só entra num instante em que nenhum leitor da OUTRA
# instância segura a compartilhada — com leitores em laço lá, o escritor daqui
# esperava até 8 s (medido em 10/09/2026; tentar mais vezes não muda). O
# escritor deixa um arquivo de intenção ao lado do `.lock` enquanto pede a
# trava; o leitor que vai abrir COM trava olha o `stat` dele (uma ida ao share,
# no custo de uma abertura que já é várias) e, se é recente, recua por até
# `_WRITE_INTENT_BACKOFF_SECONDS`. Intenção velha (o processo morreu) é
# ignorada pela idade — ninguém fica preso a um arquivo órfão.
_WRITE_INTENT_SUFFIX = ".w"
_WRITE_INTENT_MAX_AGE_SECONDS = 15.0
_WRITE_INTENT_BACKOFF_SECONDS = 1.0


def _write_intent_touch(path: str) -> None:
    try:
        with open(path, "a"):
            pass
        os.utime(path, None)
    except OSError:
        pass


def _write_intent_clear(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _write_intent_backoff(path: str) -> None:
    deadline = time.monotonic() + _WRITE_INTENT_BACKOFF_SECONDS
    while time.monotonic() < deadline:
        try:
            st = os.stat(path)
        except OSError:
            return
        if time.time() - st.st_mtime > _WRITE_INTENT_MAX_AGE_SECONDS:
            return
        time.sleep(_LOCK_CHECK_INTERVAL_SECONDS)


def _acquire_file_lock(
    operation: DatabaseOperation,
    timeout_seconds: Optional[float] = None,
) -> portalocker.Lock:
    timeout = timeout_seconds if timeout_seconds is not None else (
        _settings.write_lock_timeout_seconds
        if operation.mode == "write"
        else _settings.read_lock_timeout_seconds
    )
    if timeout_seconds is None and operation.mode == "read":
        override = _read_timeout_override()
        if override is not None:
            timeout = min(timeout, override)
    lock_mode = (
        portalocker.LockFlags.EXCLUSIVE
        if operation.mode == "write"
        else portalocker.LockFlags.SHARED
    )
    # `check_interval`: a trava é pedida por TENTATIVA (NON_BLOCKING). O
    # padrão do portalocker (0,25 s) fazia um escritor esperar um quarto de
    # segundo por uma leitura de milissegundos; 50 ms é uma chamada de lock
    # por tentativa, sem leitura de dado. Quem resolve a disputa com leitores
    # em LAÇO de outra instância não é o intervalo, é a intenção de escrita
    # (abaixo).
    lock = portalocker.Lock(
        operation.lock_path,
        mode="a+b",
        timeout=timeout,
        check_interval=_LOCK_CHECK_INTERVAL_SECONDS,
        flags=lock_mode | portalocker.LockFlags.NON_BLOCKING,
    )
    _log_event("file_lock_wait_started", operation)
    started_at = time.monotonic()
    intent = operation.lock_path + _WRITE_INTENT_SUFFIX
    if operation.mode == "write":
        _write_intent_touch(intent)
    else:
        _write_intent_backoff(intent)
    try:
        try:
            lock.acquire()
        finally:
            if operation.mode == "write":
                _write_intent_clear(intent)
    except portalocker.exceptions.LockException as exc:
        _log_event(
            "file_lock_wait_timed_out", operation, logging.WARNING,
            wait_seconds=round(time.monotonic() - started_at, 3),
            error_type=type(exc).__name__, error_message=_sanitize_error(exc, operation),
        )
        raise DatabaseLockTimeout(operation.database_path, operation.mode, timeout) from exc
    waited = time.monotonic() - started_at
    _log_event("file_lock_acquired", operation, wait_seconds=round(waited, 3))
    if waited >= _settings.slow_lock_warning_seconds:
        _log_event(
            "file_lock_wait_slow", operation, logging.WARNING,
            wait_seconds=round(waited, 3),
        )
    return lock


class HeldFileLock:
    """A trava de arquivo de uma conexão cujo tempo de vida é do CHAMADOR.

    O `_database_context` cobre o caso normal — abre, trava, fecha, destrava —,
    mas o motor do espelho (`json_to_duckdb`) tem um par `ABRIR_BANCO` /
    `FECHAR_BANCO` e mantém a conexão viva através de muitos arquivos. Para ele
    a trava precisa ser um OBJETO, não um `with`. Os eventos são os mesmos do
    farol, então a escrita do espelho passa a aparecer no painel ao lado das
    leituras — que era metade do problema: ela era a única operação do app que
    tocava o share sem deixar rastro.
    """

    __slots__ = ("_lock", "_operation", "_acquired_at", "_released")

    def __init__(self, lock, operation: DatabaseOperation) -> None:
        self._lock = lock
        self._operation = operation
        self._acquired_at = time.monotonic()
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        held = time.monotonic() - self._acquired_at
        _trace_record(self._operation, held,
                      "committed" if self._operation.mode == "write" else "completed")
        try:
            self._lock.release()
        except Exception as exc:                            # noqa: BLE001
            _log_event(
                "operation_completed", self._operation, logging.ERROR,
                category="cleanup_failed", operation_seconds=round(held, 3),
                lock_hold_seconds=round(held, 3),
                error_type=type(exc).__name__,
                error_message=_sanitize_error(exc, self._operation),
            )
            return
        _log_event(
            "operation_completed", self._operation,
            category="committed" if self._operation.mode == "write" else "completed",
            operation_seconds=round(held, 3), lock_hold_seconds=round(held, 3),
            error_type="", error_message="",
        )
        if held >= _settings.slow_lock_warning_seconds:
            _log_event(
                "file_lock_held_slow", self._operation, logging.WARNING,
                lock_hold_seconds=round(held, 3),
            )


def hold_file_lock(
    database_path: _PathLike,
    *,
    write: bool,
    engine: str = "duckdb",
    operation_id: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
) -> HeldFileLock:
    """Toma a trava de arquivo (EXCLUSIVA em escrita, COMPARTILHADA em leitura)
    para uma conexão que o chamador vai abrir e fechar por conta própria.

    `timeout_seconds` sobrepõe o teto do ajuste: quem chama pode ter um
    orçamento MENOR que o da camada — o espelho tem, porque a cura síncrona da
    tela espera por ele e esperar o teto de 30s garantiria o estouro dela.

    Levanta `DatabaseLockTimeout` como o caminho normal — quem chama decide se
    espera, desiste ou segue sem coordenação."""
    normalized_path = normalize_database_path(database_path)
    operation = DatabaseOperation(
        operation_id=operation_id or uuid.uuid4().hex,
        database_path=normalized_path,
        lock_path=lock_file_path(normalized_path),
        mode="write" if write else "read",
        started_at=time.monotonic(),
        engine=engine,
    )
    try:
        lock = _acquire_file_lock(operation, timeout_seconds)
    except DatabaseLockTimeout:
        _trace_record(operation, time.monotonic() - operation.started_at, "lock_timeout")
        raise
    return HeldFileLock(lock, operation)


def _open_connection(engine: str, database_path: str, write: bool):
    if engine == "duckdb":
        return duckdb.connect(database_path, read_only=not write)
    if engine == "sqlite":
        timeout_seconds = _settings.sqlite_busy_timeout_seconds / 1000
        if write:
            connection = sqlite3.connect(database_path, timeout=timeout_seconds, isolation_level=None)
        else:
            connection = sqlite3.connect(
                Path(database_path).as_uri() + "?mode=ro",
                uri=True,
                timeout=timeout_seconds,
                isolation_level=None,
            )
        connection.execute("PRAGMA busy_timeout = {}".format(_settings.sqlite_busy_timeout_seconds))
        return connection
    raise ValueError("Unsupported database engine: {}".format(engine))


def _open_with_retry(engine: str, database_path: str, write: bool,
                     operation: DatabaseOperation):
    """`_open_connection` com retentativa curta na ESCRITA quando a abertura
    falha por DISPUTA pelo arquivo.

    O `DATABASE_LOCK_RETRY_LIMIT` do config era lido e não fazia nada — os
    docstrings da esteira e do Pending Confirmation diziam que "o retry passou
    a ser do `duckdb_write`", e não tinha passado. O caso que ele cobre é o do
    share: a trava de arquivo exclusiva já veio, mas a instância vizinha ainda
    está FECHANDO um handle read-only (aberto sem a camada, ou antes de a
    trava valer), e o `duckdb.connect` estoura com *"used by another process"*
    por alguns milissegundos. Só disputa é retentada (`is_file_in_use`); outra
    falha sobe na hora, como sempre. A leitura não retenta: quem lê tem o
    canal de emergência dele."""
    tentativas = max(0, int(_settings.retry_limit)) if write else 0
    for i in range(tentativas + 1):
        try:
            return _open_connection(engine, database_path, write)
        except Exception as exc:                            # noqa: BLE001
            if i >= tentativas or not is_file_in_use(exc):
                raise
            _log_event(
                "connection_open_retry", operation, logging.WARNING,
                attempt=i + 1, error_type=type(exc).__name__,
                error_message=_sanitize_error(exc, operation),
            )
            time.sleep(0.25 * (i + 1))


def _begin_transaction(connection, engine: str) -> None:
    connection.execute("BEGIN IMMEDIATE" if engine == "sqlite" else "BEGIN TRANSACTION")


def _rollback(connection, operation: DatabaseOperation) -> None:
    try:
        connection.execute("ROLLBACK")
        _log_event("transaction_rolled_back", operation)
    except Exception as exc:
        _log_event(
            "transaction_rollback_failed", operation, logging.ERROR,
            error_type=type(exc).__name__, error_message=_sanitize_error(exc, operation),
        )


@contextmanager
def _database_context(
    database_path: _PathLike,
    *,
    engine: str,
    write: bool,
    operation_id: Optional[str] = None,
    skip_file_lock: bool = False,
) -> Iterator[object]:
    if skip_file_lock and write:
        # The exclusive file lock is what keeps two writers from touching the
        # file at once; bypassing it for a write would corrupt data, not just
        # risk a stale read.
        raise ValueError("skip_file_lock is only permitted for read operations")
    normalized_path = normalize_database_path(database_path)
    operation = DatabaseOperation(
        operation_id=operation_id or uuid.uuid4().hex,
        database_path=normalized_path,
        lock_path=lock_file_path(normalized_path),
        mode="write" if write else "read",
        started_at=time.monotonic(),
        engine=engine,
    )
    active_writes = _active_write_paths()
    if write and normalized_path in active_writes:
        raise NestedDatabaseTransaction(
            "Nested write context is prohibited for {}".format(normalized_path)
        )

    permits = _semaphores.get(normalized_path, _settings.read_concurrency)
    permit = permits.write if write else permits.read
    # O portão intra-processo leitor-sem-lock × escritor é do DuckDB, e só dele:
    # é a instância única por arquivo dele que recusa configurações mistas.
    gate = _unlocked_gates.get(normalized_path) if engine == "duckdb" else None
    gate_read = False
    gate_write = False
    file_lock = None
    file_lock_acquired_at: Optional[float] = None
    connection = None
    transaction_started = False
    primary_error: Optional[BaseException] = None
    cleanup_error: Optional[BaseException] = None
    outcome = "committed" if write else "completed"
    if write:
        active_writes.add(normalized_path)

    try:
        _acquire_permit(permit, operation)
        try:
            if skip_file_lock:
                # No cross-process coordination: this read may overlap an
                # in-flight write on the share and see a torn/partial file.
                #
                # WARNING once PER PATH, not per operation. The one caller of
                # this is the bell poll, which runs every few seconds per open
                # tab: a warning per read would be most of the log, and burying
                # the log is exactly what `_DATABASE_LOGGING_ENABLED` was added
                # to stop — and WARNING bypasses that gate. The fact worth
                # recording is that a given database is being read unlocked at
                # all, and that is said once.
                if normalized_path not in _unlocked_warned:
                    _unlocked_warned.add(normalized_path)
                    _log_event("file_lock_skipped", operation, logging.WARNING)
                if gate is not None:
                    gate.enter_read(_GATE_READ_WAIT_SECONDS)
                    gate_read = True
            else:
                if write and gate is not None:
                    # A escrita é DECLARADA no portão ANTES da trava de
                    # arquivo, e os leitores do armazém (`data_store`, que
                    # entram no portão antes de pedir a trava COMPARTILHADA)
                    # são drenados aqui. Na ordem inversa — trava primeiro,
                    # portão depois — o escritor segurava a trava exclusiva
                    # esperando um leitor que segurava o portão esperando a
                    # trava compartilhada: um ciclo que só o timeout desfazia
                    # (12 s por gravação com leitores ativos, §434). E é a
                    # declaração antes da trava que dá ao escritor a
                    # preferência: com leitores em laço a trava exclusiva,
                    # pedida por tentativa, não entrava nunca.
                    gate_write = True
                    gate.declare_write()
                    gate.await_readers(_GATE_WRITE_WAIT_SECONDS)
                file_lock = _acquire_file_lock(operation)
                file_lock_acquired_at = time.monotonic()
                if write and gate is not None:
                    # Segunda drenagem: o poll sem trava do sino pode ter
                    # entrado enquanto a trava era pedida.
                    if not gate.await_readers(_GATE_WRITE_WAIT_SECONDS):
                        _log_event("unlocked_gate_wait_timed_out", operation,
                                   logging.WARNING)
            connection = _open_with_retry(engine, normalized_path, write, operation)
            _log_event("connection_opened", operation)
            if write:
                _begin_transaction(connection, engine)
                transaction_started = True
                _log_event("transaction_began", operation)
            try:
                yield connection
            except BaseException:
                if write and transaction_started:
                    _rollback(connection, operation)
                    outcome = "rolled_back"
                raise
            if write:
                try:
                    connection.execute("COMMIT")
                    transaction_started = False
                    _log_event("transaction_committed", operation)
                except Exception as exc:
                    outcome = "outcome_unknown"
                    _log_event(
                        "transaction_outcome_unknown", operation, logging.ERROR,
                        error_type=type(exc).__name__, error_message=_sanitize_error(exc, operation),
                    )
                    raise TransactionOutcomeUnknown(
                        operation.database_path, operation.operation_id
                    ) from exc
        finally:
            if connection is not None:
                try:
                    connection.close()
                    _log_event("connection_closed", operation)
                except Exception as exc:
                    cleanup_error = exc
                    outcome = "cleanup_failed"
                    _log_event(
                        "connection_close_failed", operation, logging.ERROR,
                        error_type=type(exc).__name__, error_message=_sanitize_error(exc, operation),
                    )
            if file_lock is not None:
                try:
                    file_lock.release()
                except Exception as exc:
                    cleanup_error = cleanup_error or exc
                    outcome = "cleanup_failed"
                    _log_event(
                        "file_lock_release_failed", operation, logging.ERROR,
                        error_type=type(exc).__name__, error_message=_sanitize_error(exc, operation),
                    )
            if gate_read:
                gate.exit_read()
            if gate_write:
                gate.exit_write()
            permit.release()
    except BaseException as exc:
        primary_error = exc
        if isinstance(exc, DatabaseLockTimeout):
            outcome = "lock_timeout"
        elif isinstance(exc, TransactionOutcomeUnknown):
            outcome = "outcome_unknown"
        raise
    finally:
        if write:
            active_writes.remove(normalized_path)
        if cleanup_error is not None and primary_error is None:
            _log_event(
                "operation_completed", operation, logging.ERROR,
                category="cleanup_failed",
                operation_seconds=round(time.monotonic() - operation.started_at, 3),
                lock_hold_seconds=round(time.monotonic() - file_lock_acquired_at, 3)
                if file_lock_acquired_at is not None else 0,
                error_type=type(cleanup_error).__name__, error_message=_sanitize_error(cleanup_error, operation),
            )
            raise DatabaseCleanupError(
                "Cleanup failed after {} operation {} on {}".format(
                    operation.mode, operation.operation_id, operation.database_path
                )
            ) from cleanup_error
        hold_seconds = time.monotonic() - operation.started_at
        lock_hold_seconds = (
            time.monotonic() - file_lock_acquired_at
            if file_lock_acquired_at is not None else 0
        )
        _trace_record(operation, hold_seconds, outcome)
        _log_event(
            "operation_completed", operation,
            logging.WARNING if outcome in {"lock_timeout", "outcome_unknown", "cleanup_failed"} else logging.INFO,
            category=outcome, operation_seconds=round(hold_seconds, 3),
            lock_hold_seconds=round(lock_hold_seconds, 3),
            error_type=type(primary_error).__name__ if primary_error else "",
            error_message=_sanitize_error(primary_error, operation) if primary_error else "",
        )
        if file_lock is not None and lock_hold_seconds >= _settings.slow_lock_warning_seconds:
            _log_event(
                "file_lock_held_slow", operation, logging.WARNING,
                lock_hold_seconds=round(lock_hold_seconds, 3),
            )


def verify_sqlite_integrity(database_path: _PathLike) -> bool:
    """Run SQLite quick_check under the normal read lock and record its outcome."""
    normalized_path = normalize_database_path(database_path)
    operation = DatabaseOperation(
        operation_id=uuid.uuid4().hex,
        database_path=normalized_path,
        lock_path=lock_file_path(normalized_path),
        mode="read",
        started_at=time.monotonic(),
        engine="sqlite",
    )
    _log_event("integrity_verification_requested", operation)
    try:
        with sqlite_read(normalized_path) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
        passed = bool(result and result[0] == "ok")
        _log_event(
            "integrity_verification_completed", operation,
            logging.INFO if passed else logging.ERROR, passed=passed,
        )
        return passed
    except Exception as exc:
        _log_event(
            "integrity_verification_completed", operation, logging.ERROR, passed=False,
            error_type=type(exc).__name__, error_message=_sanitize_error(exc, operation),
        )
        raise


def duckdb_read(database_path: _PathLike) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open a fresh DuckDB read-only connection under a shared file lock."""
    return _database_context(database_path, engine="duckdb", write=False)  # type: ignore[return-value]


def duckdb_read_unlocked(database_path: _PathLike) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open a DuckDB read-only connection WITHOUT the cross-process file lock.

    DANGER: this file lives on a network share, and neither DuckDB nor the OS
    guarantee a consistent view of a file being written concurrently — this
    call can observe a torn/partial read while another process is mid-COMMIT.
    Use only where a stale or occasionally-inconsistent read is acceptable
    (e.g. a best-effort dashboard poll) and never for a read that feeds a
    write-back decision.
    """
    return _database_context(database_path, engine="duckdb", write=False, skip_file_lock=True)  # type: ignore[return-value]


def duckdb_write(
    database_path: _PathLike, *, operation_id: Optional[str] = None
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open a fresh transactional DuckDB connection under an exclusive file lock."""
    return _database_context(
        database_path, engine="duckdb", write=True, operation_id=operation_id
    )  # type: ignore[return-value]


def sqlite_read(database_path: _PathLike) -> Iterator[sqlite3.Connection]:
    """Open a fresh SQLite read-only connection under a shared file lock."""
    return _database_context(database_path, engine="sqlite", write=False)  # type: ignore[return-value]


def sqlite_read_unlocked(database_path: _PathLike) -> Iterator[sqlite3.Connection]:
    """SQLite equivalent of `duckdb_read_unlocked` — see its docstring for the risk."""
    return _database_context(database_path, engine="sqlite", write=False, skip_file_lock=True)  # type: ignore[return-value]


def sqlite_write(
    database_path: _PathLike, *, operation_id: Optional[str] = None
) -> Iterator[sqlite3.Connection]:
    """Open a fresh transactional SQLite connection under an exclusive file lock."""
    return _database_context(
        database_path, engine="sqlite", write=True, operation_id=operation_id
    )  # type: ignore[return-value]