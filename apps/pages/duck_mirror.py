# -*- coding: utf-8 -*-
"""O espelho vivo JSON → DuckDB — a fase 2 da migração (HANDOFF §326).

Toda escrita de um JSON coberto pelos bancos (arquivo-dia sob `cache/`, o
registro de calendários, `RefData.json`, `CounterpartyDetails.json`) avisa
este módulo, e uma thread daemon reconverte NA HORA usando o mesmo motor da
carga completa (`apps/pages/json_to_duckdb.py`) — os `.db` da pasta `db/`
ficam sempre atualizados sem ninguém rodar script. Os JSONs continuam sendo a
fonte de LEITURA do app (a fase 3 religa os consumidores um a um); o espelho
é o que torna esse flip possível sem uma janela de recarga.

Três decisões que não são detalhe:

- **Assíncrono e fora do `_cache_lock`.** O funil `_atomic_write_json` roda
  com o lock global de cache tomado, e escrever DuckDB no share ali dentro é
  exatamente o "trabalho lento segurando o lock" que o §4 do CLAUDE.md proíbe.
  O aviso só enfileira (`put` em fila de memória) e volta; quem paga a
  conversão é a thread do espelho.
- **Melhor esforço de ponta a ponta.** O aviso nunca levanta exceção para o
  chamador (gravar o JSON não pode falhar por causa do espelho), e a conversão
  que falha fica no log — o manifest do motor faz a PRÓXIMA rodada (o próximo
  aviso, ou a carga completa do script) reconverter o que ficou para trás,
  porque o mtime do JSON não casa mais.
- **Os bancos moram ao lado do dado espelhado**: `Config.DATABASE_DIR` quando
  a raiz de dados é a do app (`Config.DATA_DIR`), e `<raiz>/db` quando a raiz
  foi trocada — é o que faz os testes, que apontam `routes._B3_DATA_DIR` para
  um tmp, espelharem dentro do próprio tmp em vez de escrever num banco real.

Kill-switch: `OTC_DISABLE_DUCK_MIRROR=1` desliga só o espelho;
`OTC_DISABLE_SCHEDULERS=1` (o dos testes que sobem o app) também desliga,
porque o espelho é trabalho de fundo da instância, como os schedulers.

Teste de regressão: `scripts/tests/check_duck_mirror.py`.
"""
import logging
import os
import queue
import threading
import time
import traceback

log = logging.getLogger('otc_tracker')

_q = queue.Queue()
_worker_lock = threading.Lock()
_worker_started = False

# Os JSONs de primeiro nível que têm banco. O registro de calendários dispara
# a conversão de HOLIDAYS inteira — é ela que cria a tabela do calendário
# recém-registrado a partir do arquivo gravado logo antes.
_TOP_LEVEL_TASKS = {
    'RefData.json': 'refdata',
    'CounterpartyDetails.json': 'refdata',
    'holiday-calendars.json': 'holidays',
}


def _enabled():
    return not (os.getenv('OTC_DISABLE_DUCK_MIRROR', '').strip()
                or os.getenv('OTC_DISABLE_SCHEDULERS', '').strip())


def _data_root():
    from apps.pages import routes
    return os.path.normpath(routes._B3_DATA_DIR)


def _out_dir(data_dir):
    from apps.config import Config
    if os.path.normpath(data_dir) == os.path.normpath(Config.DATA_DIR):
        return Config.DATABASE_DIR
    return os.path.join(data_dir, 'db')


def _classify(file_path):
    """Caminho → tarefa do espelho `(kind, raiz, rel)`, ou None para o que não
    tem banco. É a triagem que o `notify_write` sempre fez, extraída para o
    `convert_sync` classificar IGUAL — duas triagens divergindo fariam a cura
    síncrona converter num banco e o espelho noutro."""
    raiz = _data_root()
    rel = os.path.relpath(os.path.normpath(str(file_path)), raiz)
    if rel.startswith('..'):
        return None
    rel = rel.replace(os.sep, '/')
    tarefa = _TOP_LEVEL_TASKS.get(rel)
    if tarefa:
        return (tarefa, raiz, None)
    if not rel.endswith('.json') or os.path.basename(rel).startswith('_'):
        return None
    if rel.startswith('cache/'):
        return ('daily', raiz, rel)
    if rel.split('/', 1)[0] not in ('db', 'duckdb'):
        # Qualquer OUTRO JSON do DATA_DIR é um dataset (mappings, cadastros
        # B3, templates, configs) — a cobertura total. Arquivo de
        # CALENDÁRIO também cai aqui pelo gancho genérico, e é o motor
        # (`_dataset_rel_target`, na thread) que o reconhece pelo registro
        # e o devolve como `ignored`: o dele é o `notify_holidays`.
        return ('datasets', raiz, rel)
    return None


def notify_write(file_path):
    """O gancho dos funis de escrita: classifica o caminho e enfileira.

    Barato de propósito (comparação de string + `put`), porque roda no caminho
    de TODA gravação de JSON do app — inclusive sob o `_cache_lock`. Caminho
    que não tem banco é ignorado em silêncio; a triagem fina do arquivo-dia
    (data no nome, ponteiros `_last`) é do motor, na thread do espelho."""
    try:
        if not _enabled():
            return
        tarefa = _classify(file_path)
        if tarefa:
            _put(tarefa)
    except Exception:                                       # noqa: BLE001
        # O espelho nunca derruba a gravação que o avisou.
        pass


def convert_sync(file_path, timeout=30.0, kind=None):
    """Converte AGORA o JSON dado e espera terminar — a CURA da leitura
    DB-only (duck_read) que achou o banco frio ou defasado.

    A conversão roda na MESMA thread do espelho (a tarefa entra na fila com um
    Event anexado): serializa com o trabalho assíncrono de graça, então nunca
    há dois escritores no mesmo banco. Devolve True quando AQUELA tarefa
    terminou (o manifest então reflete o JSON, salvo erro de conversão — que o
    chamador detecta ao reler o manifest); False com o espelho DESLIGADO
    (`OTC_DISABLE_DUCK_MIRROR`/`OTC_DISABLE_SCHEDULERS` — os testes, que leem
    o JSON com caminhos trocados) ou no timeout (fila atolada num share lento:
    o chamador cai no JSON desta vez e a tarefa segue na fila para a próxima).

    `kind` força a tarefa ('holidays' para arquivo de calendário, cujo nome só
    o registro conhece — a triagem genérica o mandaria para datasets)."""
    try:
        if not _enabled():
            return False
        if kind:
            tarefa = (kind, _data_root(), None)
        else:
            tarefa = _classify(file_path)
        if not tarefa:
            return False
        feito = threading.Event()
        _put(tarefa + (feito,))
        return feito.wait(timeout)
    except Exception:                                       # noqa: BLE001
        return False


def notify_holidays():
    """Aviso explícito dos arquivos de calendário: eles são JSONs de primeiro
    nível cujo NOME só o registro conhece, então o gancho genérico não os
    classifica — quem grava um calendário chama aqui."""
    try:
        if _enabled():
            _put(('holidays', _data_root(), None))
    except Exception:                                       # noqa: BLE001
        pass


def flush(timeout=10.0):
    """Espera a fila esvaziar — é para TESTE, não para o request."""
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        if _q.unfinished_tasks == 0:
            return True
        time.sleep(0.05)
    return False


def _put(tarefa):
    _ensure_worker()
    _q.put(tarefa)


def _ensure_worker():
    global _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        threading.Thread(target=_loop, name='duck-mirror', daemon=True).start()
        _worker_started = True


# Quanto o escritor espera os leitores em voo fecharem antes de conectar. São
# SELECTs curtos; no share um banco grande pode levar alguns segundos, e passado
# o teto o connect decide (falha → erro de conversão no log, como antes).
_GATE_WRITE_WAIT_SECONDS = 10.0

# Quanto o escritor espera a trava EXCLUSIVA entre processos. É bem menor que o
# teto da camada (30s) de propósito: a cura síncrona da tela espera esta tarefa
# com 30s de orçamento, e gastar todos eles esperando trava garantiria o
# estouro dela — a tela cairia no JSON justamente por causa da coordenação que
# existe para mantê-la no banco. Leitor do espelho é SELECT curto; o que passa
# de alguns segundos é outra instância em conversão, e aí a rodada seguinte
# converte.
_FILE_LOCK_WAIT_SECONDS = 6.0


# As travas de arquivo das conexões de escrita vivas, por conexão. O motor tem
# um par ABRIR/FECHAR e mantém a conexão através de muitos arquivos, então a
# trava não cabe num `with` — ela é presa aqui e solta no fechar.
_travas = {}
_travas_lock = threading.Lock()


def _abrir_com_portao(path):
    """`ABRIR_BANCO` do motor, na thread do espelho: toma a trava EXCLUSIVA de
    arquivo, declara a escrita no portão do banco (leitor novo espera; os em
    voo fecham) e só então conecta.

    São DUAS coordenações, e cada uma resolve o que a outra não alcança:

    · o **portão** é em MEMÓRIA e cobre este processo — sem ele o
      `duckdb.connect` em escrita colidia com um `read_only` aberto por uma
      tela, e a colisão não era rara: o Other Products Summary abre o mesmo
      banco oito vezes num request (§422);

    · a **trava de arquivo** é ENTRE PROCESSOS, e é ela que faltava. Cada
      pessoa roda a própria instância apontando para o mesmo `db/` do share
      (§8), e a escrita do espelho era a única operação do app que ia ao share
      sem passar pela camada: ela não excluía ninguém. Enquanto isso o leitor
      de outra instância mantém o arquivo ABERTO, e no SMB não se renomeia um
      arquivo que alguém tem aberto — o DuckDB estoura no checkpoint com
      `IO Error: Could not move file: Access is denied`, que não menciona nem
      lock nem concorrência. Com a trava exclusiva o escritor ESPERA os
      leitores fecharem, e o rename passa a ter o arquivo só para ele.

    Timeout da trava não aborta a conversão: segue sem ela, avisando. Onde a
    disputa não é a causa, o comportamento continua o de antes; onde é, o log
    passa a dizer."""
    import duckdb
    from apps.pages import database_access as DA
    trava = None
    try:
        trava = DA.hold_file_lock(path, write=True,
                                  timeout_seconds=_FILE_LOCK_WAIT_SECONDS)
    except DA.DatabaseLockTimeout:
        log.warning('[duck-mirror] a trava exclusiva de %s não veio a tempo — convertendo '
                    'sem ela (se o rename falhar com "Access is denied", é outra instância '
                    'com o banco aberto)', os.path.basename(path))
    except Exception:                                       # noqa: BLE001
        log.warning('[duck-mirror] não foi possível travar %s:\n%s',
                    os.path.basename(path), traceback.format_exc())
    gate = DA.db_gate(path)
    if not gate.enter_write(_GATE_WRITE_WAIT_SECONDS):
        log.warning('[duck-mirror] leitores ainda abertos em %s depois de %.0fs — '
                    'conectando assim mesmo', os.path.basename(path), _GATE_WRITE_WAIT_SECONDS)
    try:
        con = duckdb.connect(path)
    except Exception:
        gate.exit_write()
        if trava is not None:
            trava.release()
        raise
    if trava is not None:
        with _travas_lock:
            _travas[id(con)] = trava
    return con


def _fechar_com_portao(path, con):
    """A trava só é solta DEPOIS do `close()`: é no fechar que o DuckDB faz o
    checkpoint e mexe nos arquivos — soltar antes devolveria a corrida no exato
    instante em que ela dói."""
    from apps.pages import database_access as DA
    with _travas_lock:
        trava = _travas.pop(id(con), None)
    try:
        con.close()
    finally:
        try:
            DA.db_gate(path).exit_write()
        finally:
            if trava is not None:
                trava.release()


def _loop():
    from apps.pages import json_to_duckdb as core
    # A abertura em escrita do motor passa a ser a COM PORTÃO — só nesta
    # thread; os scripts de carga e os standalone ficam com o connect cru.
    core.ABRIR_BANCO = _abrir_com_portao
    core.FECHAR_BANCO = _fechar_com_portao
    while True:
        item = _q.get()
        # Tarefa síncrona (convert_sync) traz um Event como 4º elemento; o
        # aviso assíncrono continua a tripla de sempre.
        kind, data_dir, rel = item[:3]
        feito = item[3] if len(item) > 3 else None
        try:
            out = _out_dir(data_dir)
            if kind == 'daily':
                stats = core.convert_daily_files(data_dir, out, [rel])
            elif kind == 'datasets':
                stats = core.convert_dataset_files(data_dir, out, [rel])
            elif kind == 'holidays':
                stats = core.convert_holidays(data_dir, out)
            else:
                stats = core.convert_refdata(data_dir, out)
            for origem, erro in stats.get('errors', ()):
                log.warning('[duck-mirror] %s falhou para %s: %s',
                            kind, origem, str(erro).strip().splitlines()[-1])
        except Exception:                                   # noqa: BLE001
            log.warning('[duck-mirror] conversão %s falhou:\n%s',
                        kind, traceback.format_exc())
        finally:
            if feito is not None:
                feito.set()
            _q.task_done()
