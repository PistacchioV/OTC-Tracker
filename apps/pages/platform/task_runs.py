# -*- coding: utf-8 -*-
"""O REGISTRO DE EXECUÇÕES das rotinas do dia — quem rodou o quê, e quando.

O Intraday Monitor pergunta "a Recon X já rodou hoje?", e nem toda recon sabe
responder: a Comitente reescreve UMA tabela a cada execução (sem data nem
hora), o Pay/Rec não grava hora nenhuma e as outras gravam por DATA DE
REFERÊNCIA — que não é o dia em que alguém rodou (a CGD lê o D-1). Em vez de
cinco perguntas diferentes, cada rotina conta aqui, no fim de uma execução bem
sucedida, o que aconteceu; o Monitor lê um lugar só.

A chave é o DIA DA EXECUÇÃO no horário do Brasil (é "a tarefa de hoje foi
feita?"), e a data de referência que a tela pediu vai junto, como informação.

Um arquivo-dia por data (`cache/intraday-monitor/AAAA/MM/AAAAMMDD_task-runs.json`),
lista de registros, gravado pelo funil (`_atomic_write_json` → o banco, §434)
num read-modify-write sob o `_cache_lock` inteiro. A leitura para GRAVAR é
estrita: banco ocupado sobe, nunca vira "dia vazio" — lido como vazio, o
registro novo seria gravado sozinho por cima das execuções do dia (§548).

Platform: não importa feature nem nome do routes.
"""
import logging

from apps.pages import data_store as _store
from apps.pages.data_paths import data_write
from apps.pages.platform import json_cache as _jc
from apps.pages.platform.anbima import _br_now

log = logging.getLogger('otc_tracker')

# O que a tela mostra por registro — o resto do payload do chamador é
# descartado (o `summary` é livre, mas é dele que o card tira as contagens).
_CAMPOS = ('task', 'at', 'time', 'sid', 'name', 'ref', 'summary', 'event')


def day_path(day):
    """O arquivo-dia do registro de `day` (date/datetime)."""
    return data_write('cache', 'intraday-monitor', day.strftime('%Y'), day.strftime('%m'),
                      day.strftime('%Y%m%d') + '_task-runs.json')


def _le(path, strict):
    try:
        data = _store.read(path)
    except FileNotFoundError:
        return []
    except Exception:
        if strict:
            raise
        log.warning('[task-runs] leitura falhou (%s)', path, exc_info=True)
        return []
    return [r for r in (data if isinstance(data, list) else []) if isinstance(r, dict)]


def runs_of(day):
    """As execuções registradas no dia `day`, na ordem em que aconteceram.
    Leitura TOLERANTE — é a da tela: falha vira lista vazia com a causa no log."""
    return _le(day_path(day), strict=False)


def _em_teste():
    """Chamado DENTRO de um app de teste (`TESTING`): não grava.

    Dezenas de testes sobem o app sobre o `DATA_DIR` do checkout e chamam o
    `run` das recons com os motores trocados por espiões — antes do registro,
    nada disso gravava dado. Com o gancho no `run`, cada bateria deixava
    execuções de mentira no registro real da dev ("Alice Souza rodou a Recon
    FXO"), e o Monitor as mostrava. O teste que exercita o registro de propósito
    (`check_intraday_monitor.py`) chama `record` fora de request, num DATA_DIR
    tmp, e não passa por aqui.

    Nem todo teste liga o `TESTING`; o que TODOS têm é o cliente de teste do
    Flask, que se apresenta como `Werkzeug/<versão>` no User-Agent — nenhum
    navegador manda isso."""
    try:
        from flask import current_app, has_app_context, has_request_context, request
        if has_app_context() and current_app.config.get('TESTING'):
            return True
        return bool(has_request_context() and
                    str(request.headers.get('User-Agent') or '').startswith('Werkzeug/'))
    except Exception:                                       # noqa: BLE001
        return False


def record(task, sid='', name='', ref='', summary=None, event='run', now=None):
    """Registra UMA execução de `task` agora. Nunca derruba quem chamou: a
    rotina já rodou e gravou o que devia, e perder o registro custa só o card
    do Monitor — que seria reconstruído pela próxima execução. A falha vai
    para o log em WARNING (o nível que aparece na instância)."""
    if _em_teste():
        return None
    now = now or _br_now()
    reg = {
        'task': str(task), 'at': now.strftime('%Y-%m-%dT%H:%M:%S'),
        'time': now.strftime('%H:%M'), 'sid': str(sid or ''), 'name': str(name or ''),
        'ref': str(ref or ''), 'summary': dict(summary or {}), 'event': str(event or 'run'),
    }
    path = day_path(now)
    try:
        with _jc._cache_lock:
            linhas = _le(path, strict=True)
            linhas.append({k: reg[k] for k in _CAMPOS})
            _jc._atomic_write_json(path, linhas)
    except Exception:                                       # noqa: BLE001
        log.warning('[task-runs] não registrou %s (%s)', task, path, exc_info=True)
        return None
    return reg
