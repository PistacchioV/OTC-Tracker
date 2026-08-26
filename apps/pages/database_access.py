"""Shared database lock and transaction contexts for standalone database files."""

from __future__ import annotations

import logging
import os
import hashlib
import re
import socket
import sqlite3
import threading
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
    local_semaphore_timeout_seconds: float = 15.0
    read_lock_timeout_seconds: float = 15.0
    write_lock_timeout_seconds: float = 30.0
    sqlite_busy_timeout_seconds: int = 10_000
    slow_lock_warning_seconds: float = 5.0
    retry_limit: int = 2
    read_concurrency: int = 4

    @classmethod
    def from_mapping(cls, settings: Mapping[str, object]) -> "DatabaseAccessSettings":
        return cls(
            local_semaphore_timeout_seconds=float(
                settings.get("DATABASE_LOCAL_SEMAPHORE_TIMEOUT_SECONDS", 15)
            ),
            read_lock_timeout_seconds=float(settings.get("DATABASE_READ_LOCK_TIMEOUT_SECONDS", 15)),
            write_lock_timeout_seconds=float(settings.get("DATABASE_WRITE_LOCK_TIMEOUT_SECONDS", 30)),
            sqlite_busy_timeout_seconds=int(settings.get("DATABASE_SQLITE_BUSY_TIMEOUT_SECONDS", 10_000)),
            slow_lock_warning_seconds=float(settings.get("DATABASE_SLOW_LOCK_WARNING_SECONDS", 5)),
            retry_limit=int(settings.get("DATABASE_LOCK_RETRY_LIMIT", 2)),
            read_concurrency=int(settings.get("DATABASE_READ_CONCURRENCY", 4)),
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


_semaphores = _SemaphoreRegistry()
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
    if not semaphore.acquire(timeout=_settings.local_semaphore_timeout_seconds):
        _log_event(
            "local_permit_wait_timed_out", operation, logging.WARNING,
            wait_seconds=round(time.monotonic() - started_at, 3),
        )
        raise DatabaseLockTimeout(
            operation.database_path, operation.mode, _settings.local_semaphore_timeout_seconds
        )
    _log_event(
        "local_permit_acquired", operation,
        wait_seconds=round(time.monotonic() - started_at, 3),
    )


def _acquire_file_lock(operation: DatabaseOperation) -> portalocker.Lock:
    timeout = (
        _settings.write_lock_timeout_seconds
        if operation.mode == "write"
        else _settings.read_lock_timeout_seconds
    )
    lock_mode = (
        portalocker.LockFlags.EXCLUSIVE
        if operation.mode == "write"
        else portalocker.LockFlags.SHARED
    )
    lock = portalocker.Lock(
        operation.lock_path,
        mode="a+b",
        timeout=timeout,
        flags=lock_mode | portalocker.LockFlags.NON_BLOCKING,
    )
    _log_event("file_lock_wait_started", operation)
    started_at = time.monotonic()
    try:
        lock.acquire()
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
) -> Iterator[object]:
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
            file_lock = _acquire_file_lock(operation)
            file_lock_acquired_at = time.monotonic()
            connection = _open_connection(engine, normalized_path, write)
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


def sqlite_write(
    database_path: _PathLike, *, operation_id: Optional[str] = None
) -> Iterator[sqlite3.Connection]:
    """Open a fresh transactional SQLite connection under an exclusive file lock."""
    return _database_context(
        database_path, engine="sqlite", write=True, operation_id=operation_id
    )  # type: ignore[return-value]